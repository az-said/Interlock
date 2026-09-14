"""
Experiment 5: of a day's refund requests, how many still need a person?

    python3 experiments/approval_inbox.py

A synthetic day of 100 refund requests. The mix below is an ASSUMPTION, not measured data,
and the seed fixes it. So are reviewer latency and the routing. Change them and re-run; the
counts move with them. What does not move: rules alone pay out wrong whenever facts change
between the decision and the send, and the gate does not.

Three ways to run the same day, against the same tier-1 payments API:
    everyone approves    every request waits for a person, then sends with an idempotency key
    rules only           requests that pass the rules send automatically with an idempotency
                         key; the rest wait for a person
    rules + Interlock    same rules; every send goes through the gate, which re-checks facts and
                         authority right before it and after a crash (interlock/approvals.py).
                         Escalations are routed to a group, move up a chain after an SLA, and
                         the scoreboard is derived from the journal (interlock/scoreboard.py)

People here reject flagged or ineligible requests, accept a suggested refund of what is left,
close hand-refunded items (a premise cannot tell a hand refund of this same refund apart from a
different one), and approve the rest. Writes results/approval_inbox.md and .json.
"""
import json, os, random, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, IdempotencyOnly, SimulatedCrash
from interlock.approvals import Authority, Inbox, Route, Rule
from interlock.scoreboard import CRASH, scoreboard
from interlock.targets import Payments

SEED, LIMIT = 4471, 50
MIX = {                      # requests per kind; sums to 100
    "routine":          60,  # under the limit, eligible, nothing goes wrong
    "over_limit":       15,  # needs judgment; some get refunded by hand after approval
    "flagged":           5,  # customer flagged: a person rejects
    "ineligible":        5,  # order not eligible: a person rejects
    "duplicate":         5,  # a routine request delivered a second time
    "crash":             5,  # routine, but the sender crashes after the refund, before the ack
    "refunded_by_hand":  5,  # routine, but support refunds it by hand before the agent's send
}
STALE_APPROVALS = 3          # over-limit, refunded in full by hand between approval and send
PARTIAL_BY_HAND = 2          # over-limit, support refunds a third by hand between approval and send
HOUR, ARRIVAL, LATENCY = 3600, 5 * 60, 90 * 60   # seconds; reviewer latency is exponential, an assumption

RULES = [Rule(f"amount under ${LIMIT}", lambda r, facts: r["amount"] <= LIMIT),
         Rule("customer not flagged", lambda r, facts: not r["flagged"]),
         Rule("order eligible", lambda r, facts: facts["eligible"])]

GROUPS = {"ap-leads": {"ana"}, "controller": {"cy"}, "finance-manager": {"fm"},
          "payments-ops": {"ops"}, "risk": {"rita"}}
ROUTES = [Route("flagged", ["risk"], when=lambda i: i["request"]["flagged"]),
          Route("crash", ["payments-ops"], when=lambda i: i["reason"] in CRASH),
          Route("large", ["controller", "finance-manager"], when=lambda i: i["request"]["amount"] > 200, sla=4 * HOUR),
          Route("default", ["ap-leads", "finance-manager"], sla=4 * HOUR)]


class World(Payments):
    """Tier-1 payments API. Scheduled events fire the moment a send reaches their order."""
    def __init__(self, requests):
        super().__init__(1)
        self.pending, self.crash_once = {}, set()
        for r in requests:
            if r["order"] not in self.orders:
                full = r["kind"] == "over_limit"                     # over-limit requests refund the whole order
                self.create_order(r["order"], r["amount"] if full else 400, eligible=not r["ineligible"])
            if r["by_hand"]:
                self.pending[r["order"]] = r["by_hand"]
            if r["crash"]:
                self.crash_once.add(r["order"])

    def _fire(self, order):
        if order in self.pending:
            self.refunds.append({"eid": "support-by-hand", "order": order, "amount": self.pending.pop(order)})

    def validate_premises(self, premises, eid=None):
        self._fire(premises["order"])
        return super().validate_premises(premises, eid)

    def apply(self, eid, effect, crash_after_effect=False):
        self._fire(effect["order"])
        crash = effect["order"] in self.crash_once
        self.crash_once.discard(effect["order"])
        return super().apply(eid, effect, crash_after_effect or crash)


def day():
    rng, reqs = random.Random(SEED), []

    def new(kind, amount, **flags):
        n = len(reqs) + 1
        r = {"id": f"req-{n:03d}", "order": f"ord-{n:03d}", "amount": amount, "kind": kind,
             "flagged": False, "ineligible": False, "by_hand": 0, "crash": False, **flags}
        reqs.append(r)
        return r

    small = lambda: rng.randint(5, LIMIT)
    for _ in range(MIX["routine"]): new("routine", small())
    for i in range(MIX["over_limit"]):
        amount = rng.randint(LIMIT + 1, 300)
        hand = amount if i < STALE_APPROVALS else amount // 3 if i < STALE_APPROVALS + PARTIAL_BY_HAND else 0
        new("over_limit", amount, by_hand=hand)
    for _ in range(MIX["flagged"]): new("flagged", small(), flagged=True)
    for _ in range(MIX["ineligible"]): new("ineligible", small(), ineligible=True)
    for _ in range(MIX["crash"]): new("crash", small(), crash=True)
    for _ in range(MIX["refunded_by_hand"]):
        amount = small()
        new("refunded_by_hand", amount, by_hand=amount)
    routine = [r for r in reqs if r["kind"] == "routine"]
    reqs += [dict(r, kind="duplicate") for r in rng.sample(routine, MIX["duplicate"])]
    rng.shuffle(reqs)
    return reqs


def expected(r):
    return 0 if (r["flagged"] or r["ineligible"]) else r["amount"]


def wrong_orders(api, reqs):
    orders = {r["order"]: r for r in reqs}
    return sorted(o for o, r in orders.items() if api.refunded_total(o) != expected(r))


def rejects(request, facts):
    return request["flagged"] or not facts["eligible"]


def without_gate(reqs, everyone):
    api, reviews, approved = World(reqs), 0, []
    sender = IdempotencyOnly(api)

    def send(r):
        p = {"agent": "agent", "lease": None, "request_id": r["id"], "premises": {},
             "effect": {"order": r["order"], "amount": r["amount"]}}
        try:
            sender.submit(p)
        except SimulatedCrash:
            sender.submit(p)                                  # retry with the same key

    for r in reqs:
        facts = api.capture(r["order"])
        if not everyone and all(rule.check(r, facts) for rule in RULES):
            send(r)
            continue
        reviews += 1
        if not rejects(r, facts):
            approved.append(r)
    for r in approved:                                        # sent later in the day
        send(r)
    return {"reviews": reviews, "wrong_orders": wrong_orders(api, reqs)}


def with_gate(reqs, keep_journal=False):
    api, now, rng = World(reqs), [0.0], random.Random(SEED)
    clock = lambda: now[0]
    authority = Authority(groups=GROUPS, max_age=4 * HOUR, clock=clock)
    gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), authority)
    inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                  effect=lambda r: {"order": r["order"], "amount": r["amount"]}, rules=RULES,
                  routes=ROUTES, clock=clock)
    reviews, why, ready = 0, {}, {}                           # ready: escalation hash -> when its reviewer answers

    def decide(rid, item):
        by, seen, r, facts = min(authority.members(item["group"])), item["escalation"], item["request"], item["facts"]
        remaining = [i for i, x in enumerate(item["repairs"]) if x["code"] == "refund_remaining"]
        if item["reason"] == "needs_judgment" and not rejects(r, facts):
            return inbox.approve(rid, by, execute=False, seen=seen)
        if remaining and not rejects(r, facts):
            return inbox.repair(rid, by, index=remaining[0], seen=seen, execute=False)
        return inbox.reject(rid, by, seen=seen)               # flagged, ineligible, refunded by hand, or a crash case

    def review():
        nonlocal reviews
        inbox.tick()
        for rid, item in list(inbox.queue.items()):
            if ready.setdefault(item["escalation"], now[0] + rng.expovariate(1 / LATENCY)) <= now[0]:
                reviews += 1
                why[item["reason"]] = why.get(item["reason"], 0) + 1
                decide(rid, item)
        inbox.execute_approved()

    for r in reqs:
        now[0] += ARRIVAL
        try:
            inbox.submit(r)
        except SimulatedCrash:
            inbox.reconcile(gate.recover())
        review()
    while inbox.queue:                                        # the rest of the day: wait for the next answer
        for item in inbox.queue.values():
            ready.setdefault(item["escalation"], now[0] + rng.expovariate(1 / LATENCY))
        now[0] = max(now[0], min(ready[i["escalation"]] for i in inbox.queue.values()))
        review()
    out = {"reviews": reviews, "wrong_orders": wrong_orders(api, reqs), "why": why,
           "scoreboard": scoreboard(gate.journal)}
    if keep_journal:
        out["journal"] = gate.journal.entries()
    return out


def main():
    reqs = day()
    results = {"mix": MIX, "stale_approvals": STALE_APPROVALS, "partial_by_hand": PARTIAL_BY_HAND,
               "requests": len(reqs),
               "systems": {"everyone approves": without_gate(reqs, everyone=True),
                           "rules only": without_gate(reqs, everyone=False),
                           "rules + Interlock": with_gate(reqs)}}
    rows = "\n".join(f"| {name} | {s['reviews']} | {len(s['wrong_orders'])} |" for name, s in results["systems"].items())
    why = results["systems"]["rules + Interlock"]["why"]
    s = results["systems"]["rules + Interlock"]["scoreboard"]
    t = s["time_to_decision"]
    minutes = lambda v: "n/a" if v is None else f"{v / 60:.0f} min"
    board = "\n".join(f"| {k} | {v} |" for k, v in [
        ("requests (unique)", s["requests"]),
        ("cleared with no person", s["cleared_no_person"]),
        ("of those, receipts that verify", s["cleared_verified"]),
        ("share cleared with no person", s["no_person_share"]),
        ("sent after a person approved", s["sent_after_person"]),
        ("escalated", s["escalated"]),
        ("rejected", s["rejected"]),
        ("stale approvals caught", s["stale_approvals_caught"]),
        ("crash cases sent to a person", s["crash_to_person"]),
        ("repairs suggested", s["repairs_suggested"]),
        ("repairs accepted", s["repairs_accepted"]),
        ("SLA breaches", s["sla_breaches"]),
        ("still open", s["open"]),
        ("time to decision, median", minutes(t["median"])),
        ("time to decision, p90", minutes(t["p90"])),
        ("time to decision, max", minutes(t["max"]))])
    md = f"""# Results: how many refund requests still need a person

Generated by `experiments/approval_inbox.py` (seed {SEED}). A synthetic day of {len(reqs)}
refund requests. **The mix is an assumption, not measured data**; so are reviewer latency
(exponential, mean {LATENCY // 60} min) and the routing. Change them and re-run.

Goal: cut two thirds of manual agent approvals. On this synthetic day, whose mix is an assumption
and not measured data, {s["cleared_no_person"]} of {s["requests"]} requests cleared with no person, {s["cleared_verified"]} of those with receipts that verify.

| system | reviews a person did | orders refunded the wrong amount |
|---|---|---|
{rows}

## Scoreboard (derived from the journal)

| measure | value |
|---|---|
{board}

## Mix

""" + "\n".join(f"- {k}: {v}" for k, v in MIX.items()) + f"""
- of the over-limit requests, {STALE_APPROVALS} are refunded in full by hand between approval and send
- and {PARTIAL_BY_HAND} are refunded a third by hand between approval and send; the gate suggests refunding what is left

## Why rules + Interlock still sent things to a person

""" + "\n".join(f"- {k}: {v}" for k, v in why.items()) + """

Escalations by reason, first time only (SLA moves not counted):

""" + "\n".join(f"- {k}: {v}" for k, v in s["escalated_by_reason"].items()) + """

## Reading it

Rules take routine requests off people's plates, but without the gate they pay out wrong
whenever the facts changed between the decision (or the approval) and the send: support had
already refunded it by hand. Idempotency keys cannot see that. The gate re-checks the facts
and the approver's authority right before sending, refuses, and sends the item back to the
group it is routed to, saying what changed and what would still be safe to send. A suggested
repair is a new decision with its own receipt, never the refused one sent with a new amount.
"""
    with open(os.path.join(ROOT, "results", "approval_inbox.md"), "w") as f:
        f.write(md)
    with open(os.path.join(ROOT, "results", "approval_inbox.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(md)


if __name__ == "__main__":
    main()
