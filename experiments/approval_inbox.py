"""
Experiment 5: of a day's refund requests, how many still need a person?

    python3 experiments/approval_inbox.py

A synthetic day of 100 refund requests. The mix below is an ASSUMPTION, not measured data,
and the seed fixes it. Change MIX and re-run; the counts move with it. What does not move:
rules alone pay out wrong whenever facts change between the decision and the send, and
the gate does not.

Three ways to run the same day, against the same tier-1 payments API:
    everyone approves    every request waits for a person, then sends with an idempotency key
    rules only           requests that pass the rules send automatically with an idempotency
                         key; the rest wait for a person
    rules + Interlock    same rules; every send goes through the gate, which re-checks facts and
                         authority right before it and after a crash (interlock/approvals.py)

People here approve what they are shown unless the order is ineligible or the customer is
flagged, and close anything the gate refused. Writes results/approval_inbox.md and .json.
"""
import json, os, random, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, IdempotencyOnly, SimulatedCrash
from interlock.approvals import Authority, Inbox, Rule
from interlock.targets import Payments

SEED, LIMIT = 4471, 50
MIX = {                      # requests per kind; sums to 100
    "routine":          60,  # under the limit, eligible, nothing goes wrong
    "over_limit":       15,  # needs judgment; 3 of these get refunded by hand after approval
    "flagged":           5,  # customer flagged: a person rejects
    "ineligible":        5,  # order not eligible: a person rejects
    "duplicate":         5,  # a routine request delivered a second time
    "crash":             5,  # routine, but the sender crashes after the refund, before the ack
    "refunded_by_hand":  5,  # routine, but support refunds it by hand before the agent's send
}
STALE_APPROVALS = 3

RULES = [Rule(f"amount under ${LIMIT}", lambda r, facts: r["amount"] <= LIMIT),
         Rule("customer not flagged", lambda r, facts: not r["flagged"]),
         Rule("order eligible", lambda r, facts: facts["eligible"])]


class World(Payments):
    """Tier-1 payments API. Scheduled events fire the moment a send reaches their order."""
    def __init__(self, requests):
        super().__init__(1)
        self.pending, self.crash_once = {}, set()
        for r in requests:
            if r["order"] not in self.orders:
                self.create_order(r["order"], 400, eligible=not r["ineligible"])
            if r["by_hand"]:
                self.pending[r["order"]] = r["amount"]
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
             "flagged": False, "ineligible": False, "by_hand": False, "crash": False, **flags}
        reqs.append(r)
        return r

    small = lambda: rng.randint(5, LIMIT)
    for _ in range(MIX["routine"]): new("routine", small())
    for i in range(MIX["over_limit"]): new("over_limit", rng.randint(LIMIT + 1, 300), by_hand=i < STALE_APPROVALS)
    for _ in range(MIX["flagged"]): new("flagged", small(), flagged=True)
    for _ in range(MIX["ineligible"]): new("ineligible", small(), ineligible=True)
    for _ in range(MIX["crash"]): new("crash", small(), crash=True)
    for _ in range(MIX["refunded_by_hand"]): new("refunded_by_hand", small(), by_hand=True)
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


def with_gate(reqs):
    api = World(reqs)
    gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), Authority(approvers={"reviewer"}))
    inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                  effect=lambda r: {"order": r["order"], "amount": r["amount"]}, rules=RULES)
    reviews, why = 0, {}
    for r in reqs:
        try:
            inbox.submit(r)
        except SimulatedCrash:
            inbox.reconcile(gate.recover())
    while inbox.queue:
        for rid, item in list(inbox.queue.items()):
            reviews += 1
            why[item["why"]] = why.get(item["why"], 0) + 1
            if item["why"] != "needs judgment" or rejects(item["request"], item["facts"]):
                inbox.reject(rid, "reviewer")                 # refused by the gate: the person closes it
            else:
                inbox.approve(rid, "reviewer", execute=False)
        inbox.execute_approved()                              # sent later in the day
    return {"reviews": reviews, "wrong_orders": wrong_orders(api, reqs), "why": why}


def main():
    reqs = day()
    results = {"mix": MIX, "stale_approvals": STALE_APPROVALS, "requests": len(reqs),
               "systems": {"everyone approves": without_gate(reqs, everyone=True),
                           "rules only": without_gate(reqs, everyone=False),
                           "rules + Interlock": with_gate(reqs)}}
    rows = "\n".join(f"| {name} | {s['reviews']} | {len(s['wrong_orders'])} |" for name, s in results["systems"].items())
    why = results["systems"]["rules + Interlock"]["why"]
    md = f"""# Results: how many refund requests still need a person

Generated by `experiments/approval_inbox.py` (seed {SEED}). A synthetic day of {len(reqs)}
refund requests. **The mix is an assumption, not measured data**; change `MIX` and re-run.

| system | reviews a person did | orders refunded the wrong amount |
|---|---|---|
{rows}

## Mix

""" + "\n".join(f"- {k}: {v}" for k, v in MIX.items()) + f"""
- of the over-limit requests, {STALE_APPROVALS} are refunded by hand between approval and send

## Why rules + Interlock still sent things to a person

""" + "\n".join(f"- {k}: {v}" for k, v in why.items()) + """

## Reading it

Rules take routine requests off people's plates, but without the gate they pay out wrong
whenever the facts changed between the decision (or the approval) and the send: support had
already refunded it by hand. Idempotency keys cannot see that. The gate re-checks the facts
and the approver's authority right before sending, refuses, and sends the item back to a
person saying what changed. Every refusal is a person closing an item, not a person
re-deciding a refund.
"""
    with open(os.path.join(ROOT, "results", "approval_inbox.md"), "w") as f:
        f.write(md)
    with open(os.path.join(ROOT, "results", "approval_inbox.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(md)


if __name__ == "__main__":
    main()
