"""
Shared shapes for escalations, decisions and confirmations. Pure functions over journal entries.

    change  {"field", "was", "now"}
    repair  {"code", "set", "why"}   set == {} means the same payload re-decided on current facts

A repair is a new decision: it never reuses the refused effect id, and it goes back through
rules or a person before anything is sent.
"""

FIELDS = {"ESCALATED": ("at", "reason", "why", "detail", "facts", "changes", "repairs",
                        "route", "group", "routed_to", "level", "due", "breach"),
          "DECIDED":   ("at", "by", "decision", "escalation", "group", "members", "repair"),
          "CONFIRMED": ("via", "event", "refund", "status", "amount", "payment_intent", "created")}

WHY = {
    "needs_judgment": "a rule asks a person to decide this",
    "stale_premise": "a fact this action depends on changed since it was decided",
    "stale_premise_at_recovery": "a fact this action depends on changed while the agent was down",
    "lease": "the authority it was decided under is not live",
    "lease_at_recovery": "the authority it was decided under lapsed while the agent was down",
    "approval_expired": "the approval is older than the approval window, so the facts were read again",
    "approver_removed": "the approver no longer belongs to the group this was routed to",
    "conflicting_payload": "the same request was already decided with different arguments",
    "duplicate_symbol": "it defines something already defined or claimed by another agent",
    "target_error": "the tool reported an error, and nothing was sent again",
    "ambiguous": "a crash left it unclear whether it happened, and the tool gives no way to check",
    "in_flight": "its outcome is not known yet; Interlock will settle it before anything is sent again",
    "unresolved": "recovery could not settle it yet; it will be tried again",
    "awaiting_decision": "it is waiting for a person's decision on its latest escalation",
    "closed": "a person closed it, so it is never sent",
    "refused": "the gate could not send it safely",
}


def record(kind, **fields):
    """The fields of a new entry, exactly as 1.2 names them, so every lane writes the same shape."""
    want, got = set(FIELDS[kind]), set(fields)
    if got != want:
        raise ValueError(f"{kind}: missing {sorted(want - got)}, unknown {sorted(got - want)}")
    return fields


def code(status):
    if status.startswith("REFUSED:"):
        return status.split(":", 1)[1]
    if status.startswith("UNRESOLVED"):
        return "unresolved"
    return status.lower()


def status(entry):
    if entry["kind"] == "REFUSED":
        return "REFUSED:" + entry["code"] if entry.get("code") else "REFUSED"
    return entry["kind"]


def diff(was, now):
    return [{"field": k, "was": was.get(k), "now": now.get(k)}
            for k in sorted(set(was) | set(now)) if was.get(k) != now.get(k)]


def latest(entries):
    """The last escalation, and the decision that answers it (None while it waits)."""
    e = next((x for x in reversed(entries) if x["kind"] == "ESCALATED"), None)
    d = e and next((x for x in entries if x["kind"] == "DECIDED" and x.get("escalation") == e["hash"]), None)
    return e, d


def closed(entries):
    return next((x for x in entries if x["kind"] == "DECIDED" and x.get("decision") in ("reject", "repair")), None)


def explain(entries, of=None):
    """
    The last refusal or unverifiable outcome, unless the effect committed after it. Old entries read as 'refused'.
    `of` is the status a caller was handed, so a later unrelated refusal can't explain it. Without it, a
    refusal that only says a person owns the effect is passed over, as the inbox's state reading does.
    """
    for i in range(len(entries) - 1, -1, -1):
        e = entries[i]
        if e["kind"] in ("REFUSED", "AMBIGUOUS"):
            if (status(e) != of) if of else e.get("code") in ("awaiting_decision", "closed"):
                continue
            if any(x["kind"] == "COMMITTED" for x in entries[i + 1:]):
                return None
            reason = e.get("code") or ("ambiguous" if e["kind"] == "AMBIGUOUS" else "refused")
            return {"effect_id": e["effect_id"], "status": status(e), "reason": reason,
                    "why": WHY.get(reason, WHY["refused"]),
                    "changes": e.get("changes", []), "repairs": e.get("repairs", [])}
    return None


RANK = {"succeeded": 1, "failed": 2, "canceled": 2}   # anything else is pending; a refund never goes back


def final(statuses):
    """The target's last word on one refund: the furthest status, the latest among equals. Delivery order is not."""
    return max(reversed(statuses), key=lambda s: RANK.get(s, 0)) if statuses else None


def sent_refund(entries):
    """The refund id the commit recorded (a send's result, or a lookup's find), or None when the target names none."""
    for e in entries:
        if e.get("kind") == "COMMITTED":
            r, found = e.get("result"), e.get("found")
            return r.get("refund") if isinstance(r, dict) else found if isinstance(found, str) else None
    return None


def describe(esc):
    parts = [esc["why"]]
    if esc.get("changes"):
        parts.append("Changed: " + "; ".join(f"{c['field']} was {c['was']}, now {c['now']}" for c in esc["changes"]))
    if esc.get("repairs"):
        parts.append("Suggested, needs rules or a person: " + "; ".join(r["why"] for r in esc["repairs"]))
    return ". ".join(parts)
