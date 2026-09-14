"""
Data for the viewer, from real runs. Nothing here is hand-written sample data.

    python3 viewer/build.py      then open viewer/index.html

traces.js       experiment 1: the gate's actual journal for each fault and tier (fault replay view).
escalations.js  two sources for the inbox, receipt, escalation, journal and scoreboard views:
    live  results/escalation_live.json, written by experiments/escalation_live.py against Stripe test mode.
          Absent when that file does not exist; the page then shows how to produce it.
    mock  the synthetic approval day of experiments/approval_inbox.py (seed 4471), run in-process.
          Labeled MOCK everywhere it is shown.
Receipts and the scoreboard are re-derived here with receipts.verify() and scoreboard() from raw entries.
"""
import json, os, re, sys
from datetime import datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "experiments"))
import approval_inbox, refund_agent
from interlock.escalation import WHY
from interlock.receipts import verify
from interlock.scoreboard import scoreboard

PAST = {"approve": "approved", "reject": "rejected", "repair": "repaired"}
SECRET = re.compile(r"sk_(test|live)_|rk_(test|live)_|whsec_")


class ListJournal:
    """scoreboard() only reads entries()."""
    def __init__(self, entries):
        self._entries = entries

    def entries(self, effect_id=None):
        return [e for e in self._entries if effect_id is None or e["effect_id"] == effect_id]


def derive(journal, cents):
    money = (lambda a: f"${a / 100:,.2f}") if cents else (lambda a: f"${a:,.2f}")
    chains = {}
    for e in journal:
        chains.setdefault(e["effect_id"], []).append(e)
    request_of = {eid: next((e["request"] for e in es if e["kind"] == "PROPOSED" and "request" in e), {})
                  for eid, es in chains.items()}
    effect_by_request = {r.get("id"): eid for eid, r in request_of.items()}

    effects, escalations, events = [], [], set()
    for eid, es in chains.items():
        request, kinds = request_of[eid], [e["kind"] for e in es]
        receipt = verify({"effect_id": eid, "entries": es})
        decided = {e["escalation"]: e for e in es if e["kind"] == "DECIDED"}
        esc = [e for e in es if e["kind"] == "ESCALATED"]
        repaired_by = next((d["repair"]["request_id"] for d in decided.values() if d.get("repair")), None)
        for i, e in enumerate(esc):
            d = decided.get(e["hash"])
            events.add(e["at"])
            if d:
                events.add(d["at"])
            escalations.append({
                "effect_id": eid, "request_id": request.get("id"), "amount_display": money(request.get("amount", 0)),
                **{k: e.get(k) for k in ("hash", "at", "reason", "why", "detail", "facts", "changes", "repairs",
                                         "route", "group", "routed_to", "level", "due", "breach")},
                "superseded_at": esc[i + 1]["at"] if i + 1 < len(esc) else None,
                "decision": d and {k: d.get(k) for k in ("by", "decision", "at", "repair")},
                "child_effect": d and d.get("repair") and effect_by_request.get(d["repair"]["request_id"]),
            })

        last = decided.get(esc[-1]["hash"]) if esc else None
        if request.get("repair_of"):
            parts = [f"repair of {request['repair_of']}"]
        else:
            parts = []
        if not esc:
            parts.append("cleared by policy" if "COMMITTED" in kinds else kinds[-1].lower())
        elif "COMMITTED" in kinds:
            parts.append(f"escalated, sent after {receipt['approved_by'] or 'policy'}")
        elif last is None:
            parts.append("escalated, still open")
        elif last["decision"] == "repair":
            parts.append(f"escalated, repaired to {money(effect_amount(last))}")
        else:
            parts.append(f"escalated, {PAST[last['decision']]} by {last['by']}")
        if receipt["confirmed_by_target"] is True:
            parts.append("confirmed by Stripe")
        category = [c for c, on in (("escalated", bool(esc)), ("policy", not esc and "COMMITTED" in kinds),
                                    ("repair", bool(repaired_by or request.get("repair_of"))),
                                    ("confirmed", receipt["confirmed_by_target"] is True)) if on]
        effects.append({
            "effect_id": eid, "request_id": request.get("id"), "amount_display": money(request.get("amount", 0)),
            "payment_intent": (es[0].get("premises") or {}).get("payment_intent"),
            "repair_of": effect_by_request.get(request.get("repair_of")), "repair_of_request": request.get("repair_of"),
            "repaired_by": effect_by_request.get(repaired_by), "repaired_by_request": repaired_by,
            "summary": ", ".join(parts), "category": category, "head": es[-1]["hash"],
            "entries": es, "receipt": receipt,
        })
    escalations.sort(key=lambda x: x["at"])
    return {"cents": cents, "effects": effects, "escalations": escalations, "events": sorted(events),
            "scoreboard": scoreboard(ListJournal(journal)), "entries": len(journal)}


def effect_amount(decision):
    return decision["repair"]["set"].get("amount", 0)


def live():
    path = os.path.join(ROOT, "results", "escalation_live.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        run = json.load(f)
    journal = sorted((e for r in run["receipts"].values() for e in r["entries"]), key=lambda e: e["ts"])
    out = derive(journal, cents=True)
    for rid, v in run["verify"].items():                      # what the run saw must match what we re-derive
        assert next(x["receipt"] for x in out["effects"] if x["request_id"] == rid) == v, rid
    assert out["scoreboard"] == run["scoreboard"]
    out.update(id="live", mock=False, label="Live Stripe run", clock="epoch", provenance={
        "file": "results/escalation_live.json", "runner": "experiments/escalation_live.py", "mode": run["mode"],
        "started": run["started"], "finished": run["finished"], "payment_intent": run["payment_intent"],
        "refunded_total_cents": run["refunded_total_cents"], "hand_refund": run["refunds"].get("hand"),
        "confirmation_path": run["confirmation"]["path"], "deliveries": run["confirmation"]["webhook_deliveries"],
        "note": "Stripe calls, refund ids and webhook deliveries are real. Workflow time (escalations, SLA, "
                "decisions) is an injected clock the script advanced, so a 4h SLA passed without waiting 4h. "
                "The run script made the decisions as the named reviewers."})
    return out


def mock():
    run = approval_inbox.with_gate(approval_inbox.day(), keep_journal=True)
    out = derive(run["journal"], cents=False)
    assert out["scoreboard"] == run["scoreboard"]
    out.update(id="mock", mock=True, label="Mock", clock="day", provenance={
        "file": "experiments/approval_inbox.py", "seed": approval_inbox.SEED,
        "note": "Synthetic approval day. The request mix, reviewer latency and routing are assumptions, "
                "not measured data. Not a Stripe run."})
    return out


def write(name, var, data):
    text = f"window.{var} = " + json.dumps(data, separators=(",", ":")) + ";\n"
    assert not SECRET.search(text), f"{name} would contain a secret-looking string"
    with open(os.path.join(HERE, name), "w") as f:
        f.write(text)
    return len(text)


traces = {
    "faults": refund_agent.FAULTS,
    "results": {fault: {name: refund_agent.run(system, tier, fault, keep_journal=True)
                        for system, tier, name in refund_agent.SYSTEMS}
                for fault in refund_agent.FAULTS},
}
with open(os.path.join(HERE, "traces.js"), "w") as f:
    f.write("window.INTERLOCK_TRACES = " + json.dumps(traces, indent=1) + ";\n")
print(f"wrote viewer/traces.js: {len(traces['faults'])} faults, 5 systems each")

sources = {k: v for k, v in (("live", live()), ("mock", mock())) if v is not None}
size = write("escalations.js", "INTERLOCK_ESCALATIONS", {
    "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "why": WHY,
    "goal": "Goal: cut two thirds of manual agent approvals. A goal, not a measured customer result.",
    "sources": sources})
print(f"wrote viewer/escalations.js: {size // 1024} KB, sources: "
      + ", ".join(f"{k} ({len(v['effects'])} effects, {v['entries']} entries)" for k, v in sources.items()))
