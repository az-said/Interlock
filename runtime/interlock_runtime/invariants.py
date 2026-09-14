"""
Code checks of the invariants in docs/07-runtime.md 2.1, run over the records of real runs.

    INVARIANTS = {"Name": check_fn}      check_fn(conn, world) -> list of violations, or None

None means "not checked": the records this check needs are not in `world`, or the property is liveness and belongs to
the TLC model. A None is never reported as "held". `world` keys, all optional:
    invocations       [{workflow_id, name, started_at}]   step body starts, db clock (epoch seconds)
    ledger            [{effect_id, amount, source}]       the target's ledger (ground truth), source 'agent' or 'hand'
    access_log        [{effect_id, method, path, arrival, end}]  target requests, epoch seconds
    revokes           [{grant_id, returned, returned_at}] what rt.revoke returned, and when (epoch seconds)
    worker_versions   {owner: [[name, version], ...]}
    quiescent         True when no worker is running (EffectCheckpointAtomic needs it)
"""
import json
from interlock.receipts import RESENDS, verify


def _rows(conn, q, args=()):
    return conn.execute(q, args).fetchall()


def _journal(conn):
    return [json.loads(r["body"]) for r in _rows(conn, "select body from ilr.journal order by seq")]


def _effects(conn):
    return {r["effect_id"]: r for r in _rows(conn, "select * from ilr.effects")}


def _receipts(conn):
    by = {}
    for e in _journal(conn):
        by.setdefault(e["effect_id"], []).append(e)
    return {eid: verify({"effect_id": eid, "entries": es}) for eid, es in by.items()}


def no_rerun_after_complete(conn, w):
    if "invocations" not in w:
        return None
    rows = {(r["workflow_id"], r["name"]): r["created_at"] for r in _rows(
        conn, "select workflow_id, name, extract(epoch from created_at)::float8 as created_at from ilr.steps where kind = 'step'")}
    return [f"{i['workflow_id']}:{i['name']} started at {i['started_at']} after its row at {rows[(i['workflow_id'], i['name'])]}"
            for i in w["invocations"] if (i["workflow_id"], i["name"]) in rows and i["started_at"] > rows[(i["workflow_id"], i["name"])]]


def step_result_unique(conn, w):
    out = [f"{r['workflow_id']}:{r['seq']} has {r['n']} rows" for r in _rows(
        conn, "select workflow_id, seq, count(*) as n from ilr.steps group by 1, 2 having count(*) > 1")]
    if not _rows(conn, "select 1 from pg_trigger where tgname = 'steps_append_only' and tgenabled <> 'D'"):
        out.append("ilr.steps append-only trigger is missing or disabled")
    return out


def fenced_writes(conn, w):
    """Every step and dispatch carries an epoch that was claimed, and no later claim committed before it was written."""
    out = [f"step {r['workflow_id']}:{r['seq']} epoch {r['epoch']} was never claimed" for r in _rows(conn,
           "select s.* from ilr.steps s join ilr.workflows wf on wf.id = s.workflow_id where s.epoch > 0 and not exists "
           "(select 1 from ilr.claims c where c.workflow_id = s.workflow_id and c.epoch = s.epoch)")]
    out += [f"step {r['workflow_id']}:{r['seq']} epoch {r['epoch']} written after claim {r['later']}" for r in _rows(conn,
            "select s.workflow_id, s.seq, s.epoch, min(c.epoch) as later from ilr.steps s join ilr.claims c "
            "on c.workflow_id = s.workflow_id and c.epoch > s.epoch and c.claimed_at < s.created_at "
            "where s.epoch > 0 group by 1, 2, 3")]
    return out


def lease_mutex(conn, w):
    """With the eager fence, a claim holds only while unexpired, so mutual exclusion is: no takeover before expiry."""
    return takeover_only_after_expiry(conn, w)


def takeover_only_after_expiry(conn, w):
    return [f"{r['workflow_id']} epoch {r['epoch']} claimed at {r['claimed_at']} before lease expiry {r['prev_lease_expires_at']}"
            for r in _rows(conn, "select * from ilr.claims where prev_status = 'running' and prev_lease_expires_at > claimed_at")]


def at_most_one_commit(conn, w):
    return [f"{r['effect_id']} committed {r['n']} times" for r in _rows(
        conn, "select effect_id, count(*) as n from ilr.journal where kind = 'COMMITTED' group by 1 having count(*) > 1")]


def _ours(w):
    counts = {}
    for r in w["ledger"]:
        if r.get("effect_id"):
            counts[r["effect_id"]] = counts.get(r["effect_id"], 0) + 1
    return counts


def effect_at_most_once_tier12(conn, w):
    if "ledger" not in w:
        return None
    effs, ours = _effects(conn), _ours(w)
    return [f"{eid} applied {n} times at tier {effs[eid]['tier']}" for eid, n in ours.items()
            if eid in effs and effs[eid]["tier"] in (1, 2) and n > 1]


def tier3_never_resends(conn, w):
    if "access_log" not in w:
        return None
    effs, sends = _effects(conn), {}
    for r in w["access_log"]:
        if r["method"] == "POST" and r.get("effect_id"):
            sends[r["effect_id"]] = sends.get(r["effect_id"], 0) + 1
    return [f"{eid} sent {n} times at tier 3" for eid, n in sends.items() if eid in effs and effs[eid]["tier"] == 3 and n > 1]


def no_overlapping_sends(conn, w):
    if "access_log" not in w:
        return None
    by, out = {}, []
    for r in sorted((r for r in w["access_log"] if r["method"] == "POST" and r.get("effect_id")), key=lambda r: r["arrival"]):
        prev = by.get(r["effect_id"])
        if prev and r["arrival"] < prev["end"]:
            out.append(f"{r['effect_id']}: a send arrived at {r['arrival']} while the previous one ran until {prev['end']}")
        by[r["effect_id"]] = r
    return out


def committed_implies_applied(conn, w):
    if "ledger" not in w:
        return None
    ours = _ours(w)
    return [f"{e} committed but not on the target ledger" for e, row in _effects(conn).items()
            if row["state"] == "committed" and not ours.get(e)]


def ambiguous_only_when_unknowable(conn, w):
    out = []
    for e in _journal(conn):
        if e["kind"] == "AMBIGUOUS":
            tier = _effects(conn)[e["effect_id"]]["tier"]
            if tier == 2 and "no lookup" not in str(e.get("reason")):
                out.append(f"{e['effect_id']} AMBIGUOUS at tier 2 with a lookup")
    return out


def effect_checkpoint_atomic(conn, w):
    if not w.get("quiescent"):
        return None
    return [f"{r['effect_id']} committed with no step row while claim {r['dispatch_epoch']} is current" for r in _rows(conn,
            "select e.effect_id, e.dispatch_epoch from ilr.effects e join ilr.workflows wf on wf.id = e.dispatch_workflow_id "
            "where e.state = 'committed' and wf.epoch = e.dispatch_epoch and wf.status = 'running' and wf.lease_expires_at > now() "
            "and not exists (select 1 from ilr.steps s where s.workflow_id = wf.id and s.kind = 'effect' "
            "and s.fingerprint like e.effect_id || ':%%')")]


def send_requires_live_claim(conn, w):
    claims = _rows(conn, "select workflow_id, epoch, extract(epoch from claimed_at)::float8 as at from ilr.claims")
    out = []
    for e in _journal(conn):
        by = e.get("by") if e["kind"] == "DISPATCHED" else None
        if not by:
            continue
        mine = [c for c in claims if c["workflow_id"] == by["workflow_id"]]
        if not any(c["epoch"] == by["epoch"] for c in mine):
            out.append(f"{e['effect_id']} dispatched under unclaimed epoch {by['epoch']}")
        elif any(c["epoch"] > by["epoch"] and c["at"] <= e["ts"] for c in mine):
            out.append(f"{e['effect_id']} dispatched by epoch {by['epoch']} after a later claim")
    return out


def no_send_under_revoked_grant(conn, w):
    return [f"{eid}: {v['problems']}" for eid, v in _receipts(conn).items() if v["authorized_when_fired"] is False]


def revoke_linearizable(conn, w):
    if "revokes" not in w or "access_log" not in w:
        return None
    effs, out = _effects(conn), []
    for rv in w["revokes"]:
        for r in w["access_log"]:
            eid = r.get("effect_id")
            if (r["method"] == "POST" and eid in effs and effs[eid]["grant_id"] == rv["grant_id"]
                    and r["arrival"] > rv["returned_at"] and eid not in rv["returned"]):
                out.append(f"{eid} sent at {r['arrival']} after revoke of {rv['grant_id']} returned without it")
    return out


def no_send_on_stale_premise(conn, w):
    return [f"{eid}: {v['problems']}" for eid, v in _receipts(conn).items() if v["assumptions_held"] is False]


def recovery_rechecks(conn, w):
    return [f"{e['effect_id']} resent ({e['via']}) without a passing re-check" for e in _journal(conn)
            if e["kind"] == "COMMITTED" and e.get("via") in RESENDS
            and not ((e.get("rechecked") or {}).get("lease_live") is True and (e.get("rechecked") or {}).get("violations") == [])]


def payload_bound(conn, w):
    effs = _effects(conn)
    out = [f"{e['effect_id']} dispatched {e['effect']} but bound {effs[e['effect_id']]['payload']}" for e in _journal(conn)
           if e["kind"] == "DISPATCHED" and e["effect"] != effs[e["effect_id"]]["payload"]]
    for r in w.get("ledger", []):
        eid = r.get("effect_id")
        if eid in effs and r["amount"] != effs[eid]["payload"].get("amount"):
            out.append(f"{eid} applied {r['amount']} but bound {effs[eid]['payload']}")
    return out


def no_send_after_cancel(conn, w):
    cancels = {r["id"]: r["at"] for r in _rows(conn, "select id, extract(epoch from cancel_requested_at)::float8 as at "
                                                      "from ilr.workflows where cancel_requested_at is not null")}
    return [f"{e['effect_id']} dispatched after cancel of {e['by']['workflow_id']}" for e in _journal(conn)
            if e["kind"] == "DISPATCHED" and e.get("by") and not e["by"].get("compensation")
            and e["by"]["workflow_id"] in cancels and e["ts"] > cancels[e["by"]["workflow_id"]]]


def late_result_preserved(conn, w):
    return None     # needs the sender's own response log; exercised by the S08 scenarios and TLC


def receipt_chain_linear(conn, w):
    return [f"{eid}: chain broken: {v['problems']}" for eid, v in _receipts(conn).items() if not v["tamper_evident"]]


def receipt_truthful(conn, w):
    if "ledger" not in w:
        return None
    effs, ours, out = _effects(conn), _ours(w), []
    for eid, v in _receipts(conn).items():
        state = effs[eid]["state"]
        if v["happened"] is True and not ours.get(eid):
            out.append(f"{eid}: receipt says happened, ledger has nothing")
        if v["happened"] is False and ours.get(eid):
            out.append(f"{eid}: receipt says did not happen, ledger has it")
        if (v["happened"] == "unknown") != (state in ("ambiguous", "dispatched")):
            out.append(f"{eid}: happened={v['happened']} but state is {state}")
        if v["happened_once"] and ours.get(eid, 0) > 1:
            out.append(f"{eid}: receipt says once, ledger has {ours[eid]}")
    return out


def timer_not_early(conn, w):
    return [f"{r['workflow_id']}:{r['seq']} recorded {r['early']}s early" for r in _rows(conn,
            "select workflow_id, seq, (output->>'until')::float8 - extract(epoch from created_at) as early from ilr.steps "
            "where kind = 'sleep' and (output->>'until')::float8 > extract(epoch from created_at)")]


def signal_exactly_once_consumed(conn, w):
    return [f"signal {r['id']} consumed at {r['workflow_id']}:{r['consumed_seq']} but the step output differs" for r in _rows(conn,
            "select g.* from ilr.signals g left join ilr.steps s on s.workflow_id = g.workflow_id and s.seq = g.consumed_seq "
            "where g.consumed_seq is not null and (s.kind is distinct from 'signal' or s.output is distinct from g.payload)")]


def no_lost_wakeup(conn, w):
    return [f"{r['id']} sleeps forever on '{r['signal']}' with a signal waiting" for r in _rows(conn,
            "select wf.id, wf.waiting->>'signal' as signal from ilr.workflows wf where wf.status = 'sleeping' "
            "and wf.available_at = 'infinity' and wf.waiting->>'kind' = 'signal' and exists (select 1 from ilr.signals g "
            "where g.workflow_id = wf.id and g.name = wf.waiting->>'signal' and g.consumed_seq is null)")]


def version_pinned(conn, w):
    if "worker_versions" not in w:
        return None
    allowed = {o: {tuple(v) for v in vs} for o, vs in w["worker_versions"].items()}
    return [f"{r['workflow_id']}@{r['version']} claimed by {r['owner']}" for r in _rows(conn,
            "select c.*, wf.name from ilr.claims c join ilr.workflows wf on wf.id = c.workflow_id")
            if r["owner"] in allowed and (r["name"], r["version"]) not in allowed[r["owner"]]]


def non_determinism_loud(conn, w):
    return [f"{r['id']} is stuck at seq {r['seq']} but ran seq {r['ran']}" for r in _rows(conn,
            "select wf.id, (wf.error->>'seq')::int as seq, s.seq as ran from ilr.workflows wf join ilr.steps s "
            "on s.workflow_id = wf.id and s.seq >= (wf.error->>'seq')::int and s.epoch = wf.epoch "
            "where wf.status = 'stuck' and wf.error ? 'seq'")]


def fork_never_resends(conn, w):
    return [f"{r['workflow_id']} (fork) got {r['status']} for already committed {r['effect_id']}" for r in _rows(conn,
            "select s.workflow_id, s.output->>'status' as status, s.output->>'effect_id' as effect_id from ilr.steps s "
            "join ilr.workflows wf on wf.id = s.workflow_id and wf.forked_from is not null "
            "join ilr.journal j on j.effect_id = s.output->>'effect_id' and j.kind = 'COMMITTED' "
            "where s.kind = 'effect' and s.epoch > 0 and (j.body::jsonb->>'ts')::float8 < extract(epoch from wf.created_at) "
            "and s.output->>'status' not in ('DUPLICATE_IGNORED', 'REFUSED:conflicting_payload', 'REFUSED:lease', 'REFUSED:cancelled')")]


def _liveness(conn, w):
    return None     # checked by TLC under fairness (spec/Runtime.tla), not from finite run records


INVARIANTS = {
    "NoRerunAfterComplete": no_rerun_after_complete, "StepResultUnique": step_result_unique, "FencedWrites": fenced_writes,
    "LeaseMutex": lease_mutex, "TakeoverOnlyAfterExpiry": takeover_only_after_expiry, "AtMostOneCommit": at_most_one_commit,
    "EffectAtMostOnceTier12": effect_at_most_once_tier12, "Tier3NeverResends": tier3_never_resends,
    "NoOverlappingSends": no_overlapping_sends, "CommittedImpliesApplied": committed_implies_applied,
    "AmbiguousOnlyWhenUnknowable": ambiguous_only_when_unknowable, "EffectCheckpointAtomic": effect_checkpoint_atomic,
    "SendRequiresLiveClaim": send_requires_live_claim, "NoSendUnderRevokedGrant": no_send_under_revoked_grant,
    "RevokeLinearizable": revoke_linearizable, "NoSendOnStalePremise": no_send_on_stale_premise,
    "RecoveryRechecks": recovery_rechecks, "PayloadBound": payload_bound, "NoSendAfterCancel": no_send_after_cancel,
    "LateResultPreserved": late_result_preserved, "ReceiptChainLinear": receipt_chain_linear,
    "ReceiptTruthful": receipt_truthful, "TimerNotEarly": timer_not_early,
    "SignalExactlyOnceConsumed": signal_exactly_once_consumed, "NoLostWakeup": no_lost_wakeup,
    "VersionPinned": version_pinned, "NonDeterminismLoud": non_determinism_loud, "ForkNeverResends": fork_never_resends,
    "Termination": _liveness, "EffectResolved": _liveness,
}


def check(conn, world=None, names=None):
    """{name: violations list, or None when not checked}."""
    world = world or {}
    return {n: INVARIANTS[n](conn, world) for n in (names or INVARIANTS)}


def failing(results):
    return {n: v for n, v in results.items() if v}
