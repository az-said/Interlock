"""
Gated effects: the Postgres port of interlock.gate.submit and gate._recover_one (docs/07-runtime.md 5.7).

    T_dispatch   fence, bind payload, cancel, grant FOR SHARE, local SQL premises, AUTHORIZED + DISPATCHED,
                 durable send_deadline. One transaction.
    send         under a watchdog that ends the process at the local deadline (A1).
    T_commit     fence, COMMITTED + the step row. One transaction.
    recovery     nothing queries or resends before now() > send_deadline + settle_margin; then by tier, with
                 grant and premises re-checked inside T_resolve. A resend never appends a second DISPATCHED.

Assumptions (section 2.4): A1 no pause across the local send deadline; A2 the target settles within settle_margin
after send_deadline; A3 external premises are as of their read; A4 durable commits; A5 clock rates agree within
settle_margin over one send_timeout.
"""
import hashlib, inspect, json, os, threading, time
from dataclasses import dataclass
from types import SimpleNamespace
from psycopg import sql
from interlock.gate import DEDUP_MARGIN
from interlock.journal import _plain, _seal, effect_id_for, open_dispatch
from . import killpoints
from .context import StepFailed, TargetRejected
from .db import Fenced, Jsonb

current = threading.local()      # the send in progress on this thread; adapters may send it as headers
DEFAULTS = {"send_timeout": 35, "settle_margin": 10, "premise_max_age": 5, "dedup_window": float("inf"),
            "action": "refund", "min_send_budget": 1.0}
UNQUERIED = object()
RESOLVED = object()      # recovery resolved an effect on behalf of a caller whose payload differs


@dataclass
class EffectResult:
    status: str
    effect_id: str
    result: object = None


class _Wait(Exception):
    """The effect cannot finish now: suspend until `until` (db epoch seconds), or the effect's settle point."""
    def __init__(self, until=None):
        self.until = until


class _Again(Exception):
    """Something moved under us: roll back and re-enter the effect call."""


class _Requery(Exception):
    pass


def attr(target, name):
    if name == "queryable":
        return getattr(target, "queryable", target.tier == 2)
    return getattr(target, name, DEFAULTS[name])


def payload_hash(payload):
    return hashlib.sha256(json.dumps(_plain(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def append(conn, kind, eid, **data):
    """Caller holds the effect row lock, so reading the chain head and inserting are one step. ts is the db clock."""
    head = conn.execute("select body, extract(epoch from now())::float8 as t from ilr.journal where effect_id = %s "
                        "order by seq desc limit 1", (eid,)).fetchone()
    ts = head["t"] if head else conn.execute("select extract(epoch from now())::float8 as t").fetchone()["t"]
    entry = _seal({"ts": ts, "kind": kind, "effect_id": eid, **data}, json.loads(head["body"]) if head else None)
    conn.execute("insert into ilr.journal (effect_id, kind, body, prev, hash) values (%s, %s, %s, %s, %s)",
                 (eid, kind, json.dumps(entry), entry["prev"], entry["hash"]))
    return entry


def entries(conn, eid):
    return [json.loads(r["body"]) for r in conn.execute(
        "select body from ilr.journal where effect_id = %s order by seq", (eid,))]


def decided_on(es, grant, offered):
    """gate.py's rule: a retry under the same authority is checked against the premises it was first decided on."""
    return next((e["premises"] for e in es if e["kind"] == "PROPOSED" and e.get("lease") == grant), offered)


def grant_checks(conn, grant_id, action, payload):
    """The lease check, observed with FOR SHARE, so a revoke waits for this transaction (RevokeLinearizable)."""
    g = conn.execute(
        "select *, (revoked_at is null and (expires_at is null or expires_at > now())) as live "
        "from ilr.grants where id = %s for share", (grant_id,)).fetchone()
    if g is None:
        return {"lease_live": False, "lease": None}
    amount = payload.get("amount") if isinstance(payload, dict) else None
    allowed = (g["live"] and g["action"] == action
               and (g["max_cents"] is None or (type(amount) is int and amount <= g["max_cents"]))
               and (g["payload_hash"] is None or g["payload_hash"] == payload_hash(payload)))
    iso = lambda t: t.isoformat() if t else None
    return {"lease_live": bool(allowed),
            "lease": {"grant_id": g["id"], "principal": g["principal"], "action": g["action"], "max_cents": g["max_cents"],
                      "payload_hash": g["payload_hash"], "expires_at": iso(g["expires_at"]),
                      "revoked": iso(g["revoked_at"]), "granted_by": g["granted_by"]}}


def local_violations(conn, local_premises, eid):
    """Registered SQL functions fn(args jsonb, effect_id text) returns jsonb (an array of violation strings)."""
    out = []
    for fn, args in local_premises:
        q = sql.SQL("select {}(%s::jsonb, %s) as v").format(sql.Identifier(*fn.split(".")))
        out += conn.execute(q, (Jsonb(args), eid)).fetchone()["v"] or []
    return out


def _effect_row(conn, eid, lock=False):
    return conn.execute(
        "select *, extract(epoch from send_deadline + settle_margin)::float8 as settle_at, "
        "extract(epoch from now())::float8 as now, extract(epoch from now() - first_dispatched_at)::float8 as age "
        "from ilr.effects where effect_id = %s" + (" for update" if lock else ""), (eid,)).fetchone()


# ---- the call ---------------------------------------------------------------------------------------
def effect(ctx, target, key, payload, premises, grant, name=None, local_premises=(), compensation=False,
           raise_on_refusal=False, decision=None):
    eid = effect_id_for({"request_id": key})
    payload = _plain(payload)
    ph = payload_hash(payload)
    c = SimpleNamespace(eid=eid, payload=payload, ph=ph, fp=f"{eid}:{ph}", name=name or "effect", target=target,
                        premises=_plain(premises), grant=grant, local=list(local_premises), compensation=compensation,
                        decision=decision)
    c.seq, row = ctx._next("effect", c.name, c.fp)
    res = EffectResult(**row["output"]) if row is not None else _run(ctx, c)
    if raise_on_refusal and res.status.startswith("REFUSED"):
        raise StepFailed({"type": "Refused", "status": res.status, "effect_id": eid})
    return res


def _run(ctx, c):
    force_query = False
    while True:
        eff = _effect_row(ctx.conn, c.eid)
        try:
            if eff and eff["state"] == "dispatched" and (eff["dispatch_workflow_id"], eff["dispatch_epoch"]) != (ctx.wf_id, ctx.epoch):
                # Resolve the recorded send first. A caller offering another payload does not get its status:
                # it goes round again and the submit path refuses it as conflicting_payload.
                c.resolve_only = eff["payload_hash"] != c.ph
                res = _recover(ctx, c, force_query)
                if res is not RESOLVED:
                    return res
                force_query = False
                continue
            c.resolve_only = False
            return _submit(ctx, c)
        except _Wait as w:
            until = w.until if w.until is not None else _effect_row(ctx.conn, c.eid)["settle_at"]
            ctx._suspend(c.seq, "effect", c.name, until=until, status="pending", record_when_due=False)
        except _Requery:
            force_query = True
        except _Again:
            pass


def _done(ctx, c, status, result=None):
    if getattr(c, "resolve_only", False):
        return RESOLVED
    ctx._record(c.seq, "effect", c.name, c.fp, output={"status": status, "effect_id": c.eid, "result": result})
    return EffectResult(status, c.eid, result)


def _submit(ctx, c):
    conn, t = ctx.conn, c.target
    basis = decided_on(entries(conn, c.eid), c.grant, c.premises)
    violations, read_t = t.validate_premises(basis, c.eid), time.monotonic()      # external, outside any transaction
    killpoints.hit("effect_before_dispatch")
    t0 = time.monotonic()                          # the stopwatch starts before T_dispatch's now()
    if t0 - read_t > attr(t, "premise_max_age"):
        raise _Again()
    with ctx.txn() as (cancel_at, _now):
        conn.execute("insert into ilr.effects (effect_id, workflow_id, target, tier, payload, payload_hash) "
                     "values (%s, %s, %s, %s, %s, %s) on conflict (effect_id) do nothing",
                     (c.eid, ctx.wf_id, getattr(t, "name", type(t).__name__), t.tier, Jsonb(c.payload), c.ph))
        eff = _effect_row(conn, c.eid, lock=True)
        es = entries(conn, c.eid)
        if open_dispatch(es):                      # another workflow or claim is sending: wait out its deadline
            raise _Wait(eff["settle_at"])
        if eff["payload_hash"] != c.ph:
            append(conn, "PROPOSED", c.eid, agent=ctx.name, lease=c.grant, premises=c.premises, effect=c.payload)
            append(conn, "REFUSED", c.eid, reason="payload differs from recorded decision", recorded=eff["payload"],
                   offered=c.payload)
            return _done(ctx, c, "REFUSED:conflicting_payload")
        if eff["state"] == "ambiguous":
            return _done(ctx, c, "AMBIGUOUS")
        if eff["state"] == "committed":
            return _done(ctx, c, "DUPLICATE_IGNORED")
        if decided_on(es, c.grant, c.premises) != basis:     # a proposal landed between the read and the lock
            raise _Again()
        proposed = {"agent": ctx.name, "lease": c.grant, "premises": c.premises, "effect": c.payload}
        if c.decision is not None:
            proposed["decision"] = c.decision
        append(conn, "PROPOSED", c.eid, **proposed)
        if cancel_at is not None and not c.compensation:
            append(conn, "REFUSED", c.eid, reason="cancelled")
            return _done(ctx, c, "REFUSED:cancelled")
        checks = grant_checks(conn, c.grant, attr(t, "action"), c.payload)
        if not checks["lease_live"]:
            append(conn, "REFUSED", c.eid, reason="lease not live, or it does not cover this effect", checks=checks)
            return _done(ctx, c, "REFUSED:lease")
        append(conn, "AUTHORIZED", c.eid, lease=c.grant)
        checks["violations"] = list(violations) + local_violations(conn, c.local, c.eid)
        if checks["violations"]:
            append(conn, "REFUSED", c.eid, reason=checks["violations"], checks=checks)
            return _done(ctx, c, "REFUSED:stale_premise")
        by = {"workflow_id": ctx.wf_id, "epoch": ctx.epoch}
        if c.compensation:
            by["compensation"] = True
        append(conn, "DISPATCHED", c.eid, effect=c.payload, lease=c.grant, premises=basis, checks=checks, by=by)
        _authorize_send(conn, ctx, c, first=True)
    killpoints.hit("effect_after_dispatch")
    return _send_and_commit(ctx, c, t0)


def _authorize_send(conn, ctx, c, first=False):
    """The durable record of a send attempt, committed before any bytes go out."""
    t = c.target
    conn.execute(
        "update ilr.effects set state = 'dispatched', grant_id = coalesce(%s, grant_id), dispatch_workflow_id = %s, "
        "dispatch_epoch = %s, first_dispatched_at = coalesce(first_dispatched_at, now()), "
        "send_deadline = now() + make_interval(secs => %s::float8), settle_margin = make_interval(secs => %s::float8), "
        "sends = sends + 1 where effect_id = %s",
        (c.grant if first else None, ctx.wf_id, ctx.epoch, attr(t, "send_timeout"), attr(t, "settle_margin"), c.eid))


def _send(ctx, c, t0):
    """Section 5.4: a total deadline. os._exit ends the process, so no bytes leave after it while the process runs (A1)."""
    t = c.target
    remaining = attr(t, "send_timeout") - (time.monotonic() - t0)
    if remaining < attr(t, "min_send_budget"):
        raise _Wait()
    watchdog = threading.Timer(remaining, os._exit, (75,))
    watchdog.daemon = True
    watchdog.start()
    current.workflow_id, current.epoch, current.worker = ctx.wf_id, ctx.epoch, getattr(ctx.worker, "worker_id", None)
    try:
        if "timeout" in inspect.signature(t.apply).parameters:
            return t.apply(c.eid, c.payload, timeout=remaining)
        return t.apply(c.eid, c.payload)
    finally:
        watchdog.cancel()


def _send_and_commit(ctx, c, t0, via=None, rechecked=None, status="COMMITTED"):
    try:
        result = _send(ctx, c, t0)
    except TargetRejected as e:
        return _settle_failed(ctx, c, str(e))
    except _Wait:
        raise
    except Exception:
        raise _Wait()          # a timeout says nothing about the target: recover after send_deadline + settle_margin
    killpoints.hit("resolve_after_send" if via else "effect_after_send")
    extra = {"via": via, "rechecked": rechecked} if via else {}
    conn, matched, res = ctx.conn, False, None
    try:
        with ctx.txn():
            eff = _effect_row(conn, c.eid, lock=True)
            if eff["state"] == "dispatched" and (eff["dispatch_workflow_id"], eff["dispatch_epoch"]) == (ctx.wf_id, ctx.epoch):
                append(conn, "COMMITTED", c.eid, result=result, **extra)
                conn.execute("update ilr.effects set state = 'committed' where effect_id = %s", (c.eid,))
                matched, res = True, _done(ctx, c, status, result)
    except Fenced:
        late_result(conn, c.eid, ctx.wf_id, ctx.epoch, result, extra)
        raise
    if not matched:            # the dispatch pair moved under a live claim: A1 or A2 did not hold
        late_result(conn, c.eid, ctx.wf_id, ctx.epoch, result, extra)
        raise _Again()
    killpoints.hit("effect_after_commit")
    return res


def late_result(conn, eid, wf_id, epoch, result, extra=None):
    """Unfenced; locks only the effect row. A response is never dropped (LateResultPreserved)."""
    with conn.transaction():
        eff = _effect_row(conn, eid, lock=True)
        if eff["state"] == "dispatched" and (eff["dispatch_workflow_id"], eff["dispatch_epoch"]) == (wf_id, epoch):
            append(conn, "COMMITTED", eid, result=result, **(extra or {}))    # no step row: the successor replays DUPLICATE_IGNORED
            conn.execute("update ilr.effects set state = 'committed' where effect_id = %s", (eid,))
            return "COMMITTED"
        body = {"result": result, "from_epoch": epoch, "state_at_arrival": eff["state"]}
        if eff["state"] == "proposed":
            body["assumption_violated"] = "A2"
        append(conn, "LATE_RESULT", eid, **body)
        conn.execute("update ilr.effects set late_result = %s where effect_id = %s", (Jsonb(body), eid))
        return "LATE_RESULT"


def _settle_failed(ctx, c, reason):
    """gate.settle_failed: confirm by lookup when possible, otherwise take the target at its word."""
    found = c.target.query(c.eid, c.payload) if attr(c.target, "queryable") else None
    conn = ctx.conn
    with ctx.txn():
        eff = _effect_row(conn, c.eid, lock=True)
        if eff["state"] != "dispatched" or (eff["dispatch_workflow_id"], eff["dispatch_epoch"]) != (ctx.wf_id, ctx.epoch):
            raise _Again()
        if found:
            append(conn, "COMMITTED", c.eid, via="failed-but-landed")
            conn.execute("update ilr.effects set state = 'committed' where effect_id = %s", (c.eid,))
            return _done(ctx, c, "COMMITTED_ON_QUERY")
        append(conn, "REFUSED", c.eid, reason=f"target reported failure: {reason}", resolves=True)
        conn.execute("update ilr.effects set state = 'proposed' where effect_id = %s", (c.eid,))
        return _done(ctx, c, "REFUSED:target_error")


def _recover(ctx, c, force_query=False):
    """gate._recover_one, row for row, with the checks inside T_resolve."""
    conn, t = ctx.conn, c.target
    eff = _effect_row(conn, c.eid)
    if eff["now"] <= eff["settle_at"]:
        raise _Wait(eff["settle_at"])
    d = [e for e in entries(conn, c.eid) if e["kind"] == "DISPATCHED"][-1]
    tier, queryable = t.tier, attr(t, "queryable")
    if tier == 1 and eff["age"] > attr(t, "dedup_window") - DEDUP_MARGIN:
        tier = 2 if queryable else 3              # the target forgot, or may have forgotten, the key
    violations, found = [], UNQUERIED
    if tier != 3:
        violations = t.validate_premises(d["premises"], c.eid)
        predicted_stale = bool(violations) or not _grant_peek(conn, d["lease"], attr(t, "action"), d["effect"])
        if queryable and (force_query or tier == 2 or predicted_stale):
            found = t.query(c.eid, d["effect"])
    t0 = time.monotonic()
    resend = None
    with ctx.txn():
        cur = _effect_row(conn, c.eid, lock=True)
        if (cur["state"] != "dispatched" or (cur["dispatch_workflow_id"], cur["dispatch_epoch"]) != (eff["dispatch_workflow_id"], eff["dispatch_epoch"])
                or cur["now"] <= cur["settle_at"]):
            raise _Again()
        if tier == 3:
            append(conn, "AMBIGUOUS", c.eid)
            conn.execute("update ilr.effects set state = 'ambiguous' where effect_id = %s", (c.eid,))
            return _done(ctx, c, "AMBIGUOUS")
        checks = grant_checks(conn, d["lease"], attr(t, "action"), d["effect"])
        stale = None
        if not checks["lease_live"]:
            stale = "lease"
        else:
            checks["violations"] = list(violations) + local_violations(conn, c.local, c.eid)
            stale = "stale_premise" if checks["violations"] else None
        if tier == 1 and not stale:
            resend = ("retry-idempotent", "COMMITTED_BY_RETRY")
        elif not queryable:
            append(conn, "AMBIGUOUS", c.eid, reason=f"{stale} at recovery, no lookup", rechecked=checks)
            conn.execute("update ilr.effects set state = 'ambiguous' where effect_id = %s", (c.eid,))
            return _done(ctx, c, "AMBIGUOUS")
        elif found is UNQUERIED:
            raise _Requery()
        elif found:
            append(conn, "COMMITTED", c.eid, via="recovery-query", rechecked=checks, found=found)
            conn.execute("update ilr.effects set state = 'committed' where effect_id = %s", (c.eid,))
            return _done(ctx, c, "COMMITTED_ON_QUERY")
        elif stale:
            append(conn, "REFUSED", c.eid, reason=f"{stale} at recovery", resolves=True, rechecked=checks)
            conn.execute("update ilr.effects set state = 'proposed' where effect_id = %s", (c.eid,))
            return _done(ctx, c, f"REFUSED:{stale}_at_recovery")
        else:
            resend = ("recovery-reapply", "REAPPLIED_AFTER_QUERY")
        _authorize_send(conn, ctx, c)
    killpoints.hit("resolve_after_commit")
    c.payload = d["effect"]
    return _send_and_commit(ctx, c, t0, via=resend[0], rechecked=checks, status=resend[1])


def _grant_peek(conn, grant_id, action, payload):
    """A lock-free guess at the lease, only to decide whether to query before T_resolve. T_resolve decides."""
    with conn.transaction():
        return grant_checks(conn, grant_id, action, payload)["lease_live"]
