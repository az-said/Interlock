"""
How many agent requests still needed a person, derived from the journal alone.

Nothing here is kept in memory by the inbox, so the numbers survive a restart and anyone holding
the entries can recompute them. Workflow time is the inbox clock (`at`), never the wall clock `ts`.
Duplicate deliveries are not counted: a DUPLICATE_IGNORED writes nothing.
"""
import math, statistics
from .escalation import latest
from .receipts import verify

STALE = ("stale_premise", "approval_expired", "approver_removed")
CRASH = ("ambiguous", "stale_premise_at_recovery", "lease_at_recovery")


def _landed(es):
    """The lease on the send that landed: the last DISPATCHED before the COMMITTED."""
    lease = None
    for e in es:
        if e["kind"] == "DISPATCHED":
            lease = e.get("lease")
        elif e["kind"] == "COMMITTED":
            return lease
    return None


def scoreboard(journal, name="inbox"):
    chains = {}
    for e in journal.entries():
        chains.setdefault(e["effect_id"], []).append(e)
    chains = {eid: es for eid, es in chains.items() if es[0]["kind"] == "PROPOSED" and es[0].get("agent") == name}

    s = dict.fromkeys(("requests", "cleared_no_person", "cleared_verified", "sent_after_person", "rejected",
                       "closed_by_repair", "open", "escalated", "stale_approvals_caught", "crash_to_person",
                       "repairs_suggested", "repairs_accepted", "sla_breaches", "confirmed_by_target"), 0)
    by_reason, waits = {}, []
    for eid, es in chains.items():
        kinds = [e["kind"] for e in es]
        root = "repair_of" not in (es[0].get("request") or {})
        committed, escalated = "COMMITTED" in kinds, "ESCALATED" in kinds
        s["requests"] += root
        if committed:
            lease = _landed(es)
            if isinstance(lease, dict) and lease.get("by") != "policy":
                s["sent_after_person"] += 1
            if root and not escalated and all((e.get("lease") or {}).get("by") == "policy"
                                              for e in es if e["kind"] == "DISPATCHED"):
                s["cleared_no_person"] += 1
                s["cleared_verified"] += verify({"effect_id": eid, "entries": es})["valid"]
        s["escalated"] += escalated
        E, D = latest(es)
        s["open"] += E is not None and D is None
        confirmed = [e for e in es if e["kind"] == "CONFIRMED"]
        s["confirmed_by_target"] += bool(confirmed) and confirmed[-1].get("status") == "succeeded"

        approved, since = False, None
        for e in es:
            if e["kind"] == "ESCALATED":
                since = e["at"] if since is None else since
                if e.get("breach"):
                    s["sla_breaches"] += 1
                    continue
                by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
                s["stale_approvals_caught"] += e["reason"] in STALE and approved
                s["crash_to_person"] += e["reason"] in CRASH
                s["repairs_suggested"] += bool(e.get("repairs"))
            elif e["kind"] == "DECIDED":
                approved = approved or e["decision"] == "approve"
                s["rejected"] += e["decision"] == "reject"
                s["closed_by_repair"] += e["decision"] == "repair"
                if since is not None:
                    waits.append(e["at"] - since)
                since = None
    s["repairs_accepted"] = s["closed_by_repair"]

    waits.sort()
    n = len(waits)
    s.update(no_person_share=round(s["cleared_no_person"] / s["requests"], 3) if s["requests"] else 0,
             escalated_by_reason=by_reason,
             time_to_decision={"n": n, "median": statistics.median(waits) if n else None,
                               "p90": waits[math.ceil(0.9 * n) - 1] if n else None, "max": waits[-1] if n else None})
    return s
