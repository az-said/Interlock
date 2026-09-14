"""
WorkflowContext: replay from the top with a step cache (docs/07-runtime.md section 5).

A workflow is f(ctx, input). Each durable call takes the next seq. A recorded row at that seq is returned
(or its error re-raised) and nothing runs; a mismatch in kind, name or fingerprint is NonDeterminism and the
workflow parks as `stuck`. No row is the frontier, and the call runs for real. A call that cannot finish now
writes `waiting`, releases the row in one fenced transaction, and raises Suspend.
"""
import hashlib, inspect
from dataclasses import dataclass, field
from . import killpoints
from .db import Fenced, Jsonb, db_now, fenced, notify, sha, wake


def workflow(name, version):
    def wrap(fn):
        fn._ilr = (name, version)
        return fn
    return wrap


def code_sha256(fn):
    with open(inspect.getsourcefile(fn), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Suspend(BaseException):
    """Raised by a durable call that cannot finish now. BaseException, so `except Exception` does not swallow it."""


class ContinueAsNew(BaseException):
    pass


class Cancelled(Exception):
    pass


class StepFailed(Exception):
    def __init__(self, error):
        super().__init__(error)
        self.error = error


class NonDeterminism(Exception):
    def __init__(self, error):
        super().__init__(error)
        self.error = error


class TargetRejected(Exception):
    """A target's definite refusal (e.g. a 4xx): the effect did not land, unless a lookup says otherwise."""


@dataclass
class RetryPolicy:
    """Temporal's defaults: initial 1s, backoff 2.0, max_interval 100x initial, unlimited attempts."""
    initial: float = 1.0
    backoff: float = 2.0
    max_interval: float = None
    max_attempts: int = 0
    non_retryable: tuple = field(default_factory=tuple)

    def delay(self, attempt):
        return min(self.initial * self.backoff ** (attempt - 1), self.max_interval or 100 * self.initial)

    def retries(self, error, attempt):
        for c in self.non_retryable:
            if (isinstance(c, str) and type(error).__name__ == c) or (isinstance(c, type) and isinstance(error, c)):
                return False
        return not self.max_attempts or attempt < self.max_attempts


@dataclass
class Decision:
    output: object
    premises: object
    ref: dict


class WorkflowContext:
    def __init__(self, worker, conn, claim):
        self.worker, self.conn = worker, conn
        self.wf_id, self.name, self.version = claim["id"], claim["name"], claim["version"]
        self.input, self.epoch, self.ttl = claim["input"], claim["epoch"], worker.lease_ttl
        self.waiting = claim["waiting"] or {}
        self.takeovers = claim["takeovers"]
        self.cancelled = claim["cancel_requested_at"] is not None
        self.cancel_delivered = False
        self.fenced = False              # set by the heartbeat thread
        self.suspended = False
        self.seq = 0
        self.steps = {r["seq"]: r for r in conn.execute(
            "select * from ilr.steps where workflow_id = %s", (self.wf_id,))}

    # ---- plumbing -------------------------------------------------------------------------------
    def txn(self):
        return _Fence(self)

    def _next(self, kind, name, fingerprint=None):
        if self.suspended:
            raise Suspend()
        if self.fenced:
            raise Fenced(f"{self.wf_id} epoch {self.epoch}: heartbeat lost the lease")
        self.seq += 1
        row = self.steps.get(self.seq)
        if row is not None:
            if (row["kind"], row["name"]) != (kind, name) or (kind in ("effect", "decide") and row["fingerprint"] != fingerprint):
                raise NonDeterminism({"seq": self.seq,
                                      "recorded": {"kind": row["kind"], "name": row["name"], "fingerprint": row["fingerprint"]},
                                      "called": {"kind": kind, "name": name, "fingerprint": fingerprint}})
            return self.seq, row
        self._deliver_cancel(kind)
        return self.seq, None

    def _deliver_cancel(self, kind):
        """Cancelled is raised once, at the frontier, so workflow code may catch it and compensate."""
        if self.cancelled and not self.cancel_delivered and kind != "effect":   # effects refuse inside T_dispatch
            self.cancel_delivered = True
            raise Cancelled()

    def _record(self, seq, kind, name, fingerprint=None, output=None, error=None):
        """Call inside a fenced transaction."""
        self.conn.execute(
            "insert into ilr.steps (workflow_id, seq, name, kind, fingerprint, output, error, epoch) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (self.wf_id, seq, name, kind, fingerprint, Jsonb(output), None if error is None else Jsonb(error), self.epoch))
        self.conn.execute("update ilr.workflows set takeovers = 0, waiting = null where id = %s", (self.wf_id,))
        self.takeovers, self.waiting = 0, {}

    def _waiting(self, seq, kind):
        w = self.waiting
        return w if w and w.get("seq") == seq and w.get("kind") == kind else None

    def _suspend(self, seq, kind, name=None, until=None, delay=None, status="sleeping", attempt=None, record_when_due=True):
        """
        Section 5.6, one fenced transaction. Because the fence locks the workflow row first, a concurrent signal or
        cancel either commits before it (and the mailbox check sees it) or waits for it (and then wakes the row).
        Returns ("signal", payload) or ("due", None); otherwise commits the release and raises Suspend.
        """
        with self.txn() as (cancel_at, now):
            if cancel_at:
                self._deliver_cancel(kind)
            if kind == "signal":
                sig = self.conn.execute(
                    "select id, payload from ilr.signals where workflow_id = %s and name = %s and consumed_seq is null "
                    "order by id limit 1 for update", (self.wf_id, name)).fetchone()
                if sig:
                    self.conn.execute("update ilr.signals set consumed_seq = %s where id = %s", (seq, sig["id"]))
                    self._record(seq, "signal", name, output=sig["payload"])
                    return "signal", sig["payload"]
            if until is None and delay is not None:
                until = now + delay
            if until is not None and now >= until:
                if record_when_due:
                    self._record(seq, kind, name, output={"until": until} if kind == "sleep" else None)
                return "due", None
            self.conn.execute(
                "update ilr.workflows set status = %s, owner = null, lease_expires_at = null, waiting = %s, "
                "available_at = coalesce(to_timestamp(%s::float8), 'infinity'::timestamptz), updated_at = now() "
                "where id = %s",
                (status, Jsonb({"seq": seq, "kind": kind, "signal": name if kind == "signal" else None,
                                "until": until, "attempt": attempt}), until, self.wf_id))
        self.suspended = True
        killpoints.hit("wait_after_suspend")
        raise Suspend()

    def _attempt(self, seq, kind, name, body, retry, fingerprint=None):
        """Run a step body under its retry policy; record the output, or the final error."""
        retry = retry or RetryPolicy()
        w = self._waiting(seq, "retry")
        if w:
            self._suspend(seq, "retry", name, until=w["until"], status="pending", attempt=w["attempt"], record_when_due=False)
        attempt = (w["attempt"] if w else 1) + self.takeovers      # a crash loop counts against the policy
        self.takeovers = 0
        while True:
            try:
                out = body()
                break
            except (Fenced, Suspend):
                raise
            except Exception as e:
                error = {"type": type(e).__name__, "message": str(e), "attempt": attempt}
                if not retry.retries(e, attempt):
                    with self.txn():
                        self._record(seq, kind, name, fingerprint, error=error)
                    raise StepFailed(error) from e
                self._suspend(seq, "retry", name, delay=retry.delay(attempt), status="pending", attempt=attempt + 1,
                              record_when_due=False)          # returns only when the backoff is already due
                attempt += 1
        with self.txn():
            self._record(seq, kind, name, fingerprint, output=out)
        if kind == "step":
            killpoints.hit("step_after_record")
        return out

    # ---- durable calls ----------------------------------------------------------------------------
    def step(self, name, fn, *args, retry=None):
        """At least once, like a Temporal activity. External side effects belong in ctx.effect."""
        if hasattr(fn, "apply") or any(hasattr(a, "apply") for a in args):
            raise TypeError("ctx.step does not take an effect target; send effects through ctx.effect")
        seq, row = self._next("step", name)
        if row is not None:
            return _replay(row)

        def body():
            out = fn(*args)
            killpoints.hit("step_before_record")
            return out
        return self._attempt(seq, "step", name, body, retry)

    def decide(self, name, call, request, premises=None, retry=None):
        """An LLM call recorded as a decision with the premises it was made on. First writer wins."""
        request_hash = sha(request)
        seq, row = self._next("decide", name, request_hash)
        ref = {"workflow_id": self.wf_id, "seq": seq, "request_hash": request_hash}
        if row is not None:
            out = _replay(row)
            return Decision(out["response"], out["premises"], ref)

        def body():
            captured = premises() if premises else None
            captured_at = db_now(self.conn)
            self.conn.execute("insert into ilr.llm_calls (workflow_id, seq, epoch, request_hash) values (%s, %s, %s, %s)",
                              (self.wf_id, seq, self.epoch, request_hash))
            r = call(request)
            killpoints.hit("decide_after_response")
            if not (isinstance(r, dict) and "response" in r):
                r = {"response": r}
            return {"model": r.get("model"), "request_hash": request_hash, "response": r["response"],
                    "usage": r.get("usage"), "premises": captured, "captured_at": captured_at}
        out = self._attempt(seq, "decide", name, body, retry, fingerprint=request_hash)
        return Decision(out["response"], out["premises"], ref)

    def effect(self, target, key, payload, premises, grant, name=None, local_premises=(), compensation=False,
               raise_on_refusal=False, decision=None):
        from .effects import effect
        return effect(self, target, key, payload, premises, grant, name, local_premises, compensation,
                      raise_on_refusal, decision)

    def sleep(self, seconds):
        seq, row = self._next("sleep", "sleep")
        if row is not None:
            return None
        w = self._waiting(seq, "sleep")
        self._suspend(seq, "sleep", "sleep", until=w and w["until"], delay=seconds)
        return None

    def wait_signal(self, name, timeout=None):
        """The signal's payload, or None when the timeout passed first."""
        seq, row = self._next("signal", name)
        if row is not None:
            return row["output"]
        w = self._waiting(seq, "signal")
        return self._suspend(seq, "signal", name, until=w and w["until"], delay=None if w else timeout)[1]

    def patched(self, patch_id):
        """Temporal semantics: True at the frontier (recording a marker) or on a recorded marker, else False."""
        row = self.steps.get(self.seq + 1)
        if row is not None and (row["kind"], row["name"]) != ("patch", patch_id):
            return False
        seq, row = self._next("patch", patch_id)
        if row is None:
            with self.txn():
                self._record(seq, "patch", patch_id)
        return True

    def child(self, name, input, id=None, version=None):
        seq, row = self._next("child", name)
        if row is not None:
            return row["output"]
        child_id = id or f"{self.wf_id}/{seq}"
        with self.txn():
            self.conn.execute(
                "insert into ilr.workflows (id, name, version, input, parent_id) values (%s, %s, "
                "coalesce(%s, (select version from ilr.deployments where name = %s and retired_at is null "
                "order by created_at desc limit 1)), %s, %s) on conflict (id) do nothing",
                (child_id, name, version, name, Jsonb(input), self.wf_id))
            self._record(seq, "child", name, output=child_id)
            notify(self.conn)
        return child_id

    def wait_child(self, child_id, timeout=None):
        return self.wait_signal("$done:" + child_id, timeout)

    def continue_as_new(self, input):
        self._next("step", "$continue_as_new")    # takes a seq and checks the fence flags; never recorded
        base, _, n = self.wf_id.rpartition("#")
        new_id = f"{base}#{int(n) + 1}" if base and n.isdigit() else f"{self.wf_id}#1"
        with self.txn():
            self.conn.execute(
                "insert into ilr.workflows (id, name, version, input, parent_id, continued_from) "
                "select %s, name, version, %s, parent_id, id from ilr.workflows where id = %s on conflict (id) do nothing",
                (new_id, Jsonb(input), self.wf_id))
            self._end("continued", {"continued_as": new_id}, None)
        raise ContinueAsNew(new_id)

    # ---- endings ----------------------------------------------------------------------------------
    def _end(self, status, result, error):
        self.conn.execute(
            "update ilr.workflows set status = %s, result = %s, error = %s, owner = null, lease_expires_at = null, "
            "waiting = null, updated_at = now() where id = %s",
            (status, Jsonb(result), None if error is None else Jsonb(error), self.wf_id))
        notify(self.conn)

    def finish(self, status, result=None, error=None):
        with self.txn():
            self._end(status, result, error)
            parent = self.conn.execute("select parent_id from ilr.workflows where id = %s", (self.wf_id,)).fetchone()["parent_id"]
            if parent and status in ("completed", "failed", "cancelled"):
                self.conn.execute("select 1 from ilr.workflows where id = %s for update", (parent,))   # child row, then parent row
                self.conn.execute("insert into ilr.signals (workflow_id, name, payload, sender) values (%s, %s, %s, %s)",
                                  (parent, "$done:" + self.wf_id,
                                   Jsonb({"status": status, "result": result, "error": error}), self.wf_id))
                wake(self.conn, parent)

    def mark_stuck_after_release(self, error):
        """
        Workflow code swallowed Suspend and returned. The suspend already released the row, so the fence cannot
        match; this write is guarded by the unchanged epoch instead (no claim happened since).
        """
        self.conn.execute("update ilr.workflows set status = 'stuck', error = %s, updated_at = now() "
                          "where id = %s and epoch = %s and status in ('sleeping', 'pending')",
                          (Jsonb(error), self.wf_id, self.epoch))


class _Fence:
    def __init__(self, ctx):
        self.ctx, self.cm = ctx, None

    def __enter__(self):
        self.cm = fenced(self.ctx.conn, self.ctx.wf_id, self.ctx.epoch, self.ctx.ttl)
        cancel_at, now = self.cm.__enter__()
        if cancel_at is not None:
            self.ctx.cancelled = True
        return cancel_at, now

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc)


def _replay(row):
    if row["error"] is not None:
        raise StepFailed(row["error"])
    return row["output"]
