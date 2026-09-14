"""The client API (docs/07-runtime.md section 6). Every method is one short transaction on the database clock."""
import time, uuid
from interlock.receipts import bundle
from .context import code_sha256
from .db import Jsonb, apply_schema, connect, notify, wake
from .effects import _Again, _Requery, _Wait, _recover, payload_hash
from .receipts import PgJournalView
from types import SimpleNamespace


class CodeChanged(Exception):
    pass


# Transaction bodies, callable inside a caller's transaction (the race tests hold them open on a second connection).
def lock_workflow(conn, wf_id):
    """Lock order: workflow row first."""
    if conn.execute("select 1 from ilr.workflows where id = %s for update", (wf_id,)).fetchone() is None:
        raise LookupError(wf_id)


def signal_in(conn, wf_id, name, payload, sender=None):
    lock_workflow(conn, wf_id)
    conn.execute("insert into ilr.signals (workflow_id, name, payload, sender) values (%s, %s, %s, %s)",
                 (wf_id, name, Jsonb(payload), sender))
    wake(conn, wf_id)


def cancel_in(conn, wf_id):
    lock_workflow(conn, wf_id)
    conn.execute("update ilr.workflows set cancel_requested_at = coalesce(cancel_requested_at, now()) where id = %s", (wf_id,))
    wake(conn, wf_id)


def revoke_in(conn, grant_id):
    """The UPDATE waits for any T_dispatch holding the grant FOR SHARE; the SELECT then sees what it dispatched."""
    conn.execute("update ilr.grants set revoked_at = coalesce(revoked_at, now()) where id = %s", (grant_id,))
    return [r["effect_id"] for r in conn.execute(
        "select effect_id from ilr.effects where grant_id = %s and state = 'dispatched'", (grant_id,))]


class Runtime:
    def __init__(self, dsn):
        self.dsn = dsn
        self.conn = connect(dsn)
        apply_schema(self.conn)

    def q(self, query, args=()):
        return self.conn.execute(query, args).fetchall()

    # ---- deployments ------------------------------------------------------------------------------
    def register(self, fn, allow_code_change=False):
        name, version = fn._ilr
        code = code_sha256(fn)
        with self.conn.transaction():
            row = self.conn.execute("select code_sha256 from ilr.deployments where name = %s and version = %s for update",
                                    (name, version)).fetchone()
            if row is None:
                self.conn.execute("insert into ilr.deployments (name, version, code_sha256) values (%s, %s, %s) "
                                  "on conflict do nothing", (name, version, code))
            elif row["code_sha256"] != code:
                if not allow_code_change:
                    raise CodeChanged(f"{name}@{version}: registered code_sha256 {row['code_sha256']}, this code {code}")
                self.conn.execute("update ilr.deployments set code_sha256 = %s where name = %s and version = %s",
                                  (code, name, version))

    def retire(self, name, version):
        self.conn.execute("update ilr.deployments set retired_at = now() where name = %s and version = %s", (name, version))

    # ---- workflows --------------------------------------------------------------------------------
    def start(self, name, wf_id, input, version=None):
        """Idempotent on wf_id."""
        with self.conn.transaction():
            version = version or (self.conn.execute(
                "select version from ilr.deployments where name = %s and retired_at is null order by created_at desc limit 1",
                (name,)).fetchone() or {}).get("version")
            if version is None:
                raise LookupError(f"no deployment registered for {name}")
            self.conn.execute("insert into ilr.workflows (id, name, version, input) values (%s, %s, %s, %s) "
                              "on conflict (id) do nothing", (wf_id, name, version, Jsonb(input)))
            notify(self.conn)
        return wf_id

    def signal(self, wf_id, name, payload, sender=None):
        with self.conn.transaction():
            signal_in(self.conn, wf_id, name, payload, sender)

    def cancel(self, wf_id, by):
        with self.conn.transaction():
            cancel_in(self.conn, wf_id)

    def _lock(self, wf_id):
        lock_workflow(self.conn, wf_id)

    def describe(self, wf_id):
        wf = self.conn.execute("select * from ilr.workflows where id = %s", (wf_id,)).fetchone()
        return {"workflow": wf, "waiting": wf and wf["waiting"],
                "steps": self.q("select * from ilr.steps where workflow_id = %s order by seq", (wf_id,)),
                "effects": self.q("select * from ilr.effects where workflow_id = %s or dispatch_workflow_id = %s", (wf_id, wf_id)),
                "signals": self.q("select * from ilr.signals where workflow_id = %s order by id", (wf_id,)),
                "claims": self.q("select * from ilr.claims where workflow_id = %s order by epoch", (wf_id,))}

    def list(self, status=None, name=None, version=None):
        return self.q("select * from ilr.workflows where (%s::text is null or status = %s) and (%s::text is null or name = %s) "
                      "and (%s::text is null or version = %s) order by created_at", (status, status, name, name, version, version))

    def result(self, wf_id, timeout=None):
        """Waits for a terminal (or stuck) status. Returns the workflow row."""
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            wf = self.conn.execute("select * from ilr.workflows where id = %s", (wf_id,)).fetchone()
            if wf["status"] in ("completed", "failed", "cancelled", "stuck", "continued"):
                return wf
            if end is not None and time.monotonic() > end:
                raise TimeoutError(f"{wf_id} is {wf['status']}")
            time.sleep(0.05)

    def drain_report(self):
        return self.q("select name, version, status, count(*) as n from ilr.workflows group by 1, 2, 3 order by 1, 2, 3")

    def fork(self, wf_id, at_seq, new_id):
        """Copies step rows with seq < at_seq into a new workflow. Deletes nothing. Effects stay keyed by request."""
        with self.conn.transaction():
            n = self.conn.execute("insert into ilr.workflows (id, name, version, input, forked_from) "
                                  "select %s, name, version, input, id from ilr.workflows where id = %s", (new_id, wf_id)).rowcount
            if n != 1:
                raise LookupError(wf_id)
            self.conn.execute("insert into ilr.steps (workflow_id, seq, name, kind, fingerprint, output, error, epoch) "
                              "select %s, seq, name, kind, fingerprint, output, error, 0 from ilr.steps "
                              "where workflow_id = %s and seq < %s", (new_id, wf_id, at_seq))
            notify(self.conn)
        return new_id

    def migrate(self, wf_id, to_version):
        n = self.conn.execute("update ilr.workflows set version = %s where id = %s and status <> 'running'",
                              (to_version, wf_id)).rowcount
        if n != 1:
            raise RuntimeError(f"{wf_id} is running or missing; migrate only a workflow that is not running")

    # ---- authority --------------------------------------------------------------------------------
    def grant(self, principal, action, max_cents=None, expires_in=None, by="policy", grant_id=None):
        gid = grant_id or "g-" + uuid.uuid4().hex[:12]
        self.conn.execute(
            "insert into ilr.grants (id, principal, action, max_cents, granted_by, expires_at) values (%s, %s, %s, %s, %s, "
            "now() + make_interval(secs => %s::float8))", (gid, principal, action, max_cents, by, expires_in))
        return gid

    def approve(self, wf_id, payload, facts_seen, by, expires_in=None, action="refund"):
        """A human approval: a grant bound to this exact payload and the facts the approver saw, plus the signal."""
        gid = "ap-" + uuid.uuid4().hex[:12]
        with self.conn.transaction():
            self._lock(wf_id)
            amount = payload.get("amount") if isinstance(payload, dict) else None
            self.conn.execute(
                "insert into ilr.grants (id, principal, action, max_cents, payload_hash, facts_seen, granted_by, expires_at) "
                "values (%s, %s, %s, %s, %s, %s, %s, now() + make_interval(secs => %s::float8))",
                (gid, wf_id, action, amount if type(amount) is int else None, payload_hash(payload), Jsonb(facts_seen), by, expires_in))
            self.conn.execute("insert into ilr.signals (workflow_id, name, payload, sender) values (%s, 'approve', %s, %s)",
                              (wf_id, Jsonb({"grant_id": gid, "payload": payload, "facts_seen": facts_seen}), by))
            wake(self.conn, wf_id)
        return gid

    def revoke(self, grant_id, by):
        """Waits for any T_dispatch holding the grant FOR SHARE. Returns exactly the effects that may still land."""
        with self.conn.transaction():
            return revoke_in(self.conn, grant_id)

    # ---- effects and receipts ---------------------------------------------------------------------
    def receipt(self, effect_id, key=None):
        b = bundle(PgJournalView(self), effect_id, key)
        row = self.conn.execute("select late_result, reconciled from ilr.effects where effect_id = %s", (effect_id,)).fetchone() or {}
        b["late_result"], b["reconciled"] = row.get("late_result"), row.get("reconciled")
        return b

    def ambiguous(self):
        return self.q("select * from ilr.effects where state = 'ambiguous' order by effect_id")

    def reconcile(self, effect_id, evidence, by):
        """A human attestation for an AMBIGUOUS effect. Never written into the journal."""
        self.conn.execute("update ilr.effects set reconciled = jsonb_build_object('evidence', %s::jsonb, 'by', %s::text, 'at', now()) "
                          "where effect_id = %s", (Jsonb(evidence), by, effect_id))

    def recover_orphans(self, target_for, lease_ttl=30):
        """
        Effects left dispatched by a workflow that is stuck, failed or cancelled. Each is recovered under a synthetic
        claim (epoch bump, owner $recovery) that writes journal entries and the effects row only, then the workflow's
        previous status is restored. `target_for(effect_row)` returns the EffectTarget. Returns {effect_id: status}.
        """
        out = {}
        for eff in self.q("select e.* from ilr.effects e join ilr.workflows w on w.id = e.dispatch_workflow_id "
                          "where e.state = 'dispatched' and w.status in ('stuck', 'failed', 'cancelled')"):
            wf_id = eff["dispatch_workflow_id"]
            claim = self.conn.execute(
                "with old as (select id, status from ilr.workflows where id = %s and status in ('stuck','failed','cancelled') for update) "
                "update ilr.workflows w set status = 'running', epoch = w.epoch + 1, owner = '$recovery', "
                "lease_expires_at = now() + make_interval(secs => %s::float8) from old where w.id = old.id "
                "returning w.id, w.name, w.epoch, old.status as prev_status", (wf_id, lease_ttl)).fetchone()
            if claim is None:
                continue
            self.conn.execute("insert into ilr.claims select id, epoch, owner, version, now(), %s, null from ilr.workflows where id = %s",
                              (claim["prev_status"], wf_id))
            ctx = _OrphanContext(self.dsn, claim, lease_ttl)
            c = SimpleNamespace(eid=eff["effect_id"], payload=eff["payload"], ph=eff["payload_hash"], fp=None, seq=None,
                                name="$recovery", target=target_for(eff), grant=eff["grant_id"], local=[])
            force = False
            try:
                while True:
                    state = ctx.conn.execute("select state from ilr.effects where effect_id = %s", (c.eid,)).fetchone()["state"]
                    if state != "dispatched":
                        out.setdefault(c.eid, state.upper())
                        break
                    try:
                        out[c.eid] = _recover(ctx, c, force).status
                        break
                    except _Wait:
                        out[c.eid] = "IN_FLIGHT"
                        break
                    except _Requery:
                        force = True
                    except _Again:
                        pass
            finally:
                ctx.conn.close()
                self.conn.execute("update ilr.workflows set status = %s, owner = null, lease_expires_at = null "
                                  "where id = %s and epoch = %s", (claim["prev_status"], wf_id, claim["epoch"]))
        return out


class _OrphanContext:
    """Just enough of WorkflowContext for the recovery path: a fence, no step rows."""
    def __init__(self, dsn, claim, ttl):
        from .context import _Fence
        self._fence_cls = _Fence
        self.conn, self.wf_id, self.name, self.epoch, self.ttl = connect(dsn), claim["id"], claim["name"], claim["epoch"], ttl
        self.worker, self.cancelled = None, False

    def txn(self):
        return self._fence_cls(self)

    def _record(self, *a, **k):
        pass
