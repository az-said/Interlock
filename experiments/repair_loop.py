"""
Experiment 6: can an agent repair a refused refund without paying out wrong?

    python3 experiments/repair_loop.py

A synthetic day of 100 refunds, each order with one case approving $20 in total. The mix below is
an ASSUMPTION, not measured data, and the seed fixes it. The agent is a scripted loop, not a model
(experiments/repair_live_model.py runs a real one): it reads the order, decides, calls the tool, and on
a refusal it may read again and decide again, up to 3 attempts. What happens to each order:

    routine        nothing goes wrong
    partial_hand   support refunds $5 to $15 by hand after the agent read the order, before the send
    full_hand      support refunds the whole $20 by hand after the agent read the order
    overshoot      the model decides $30; after a refusal it decides what the approval leaves
    stubborn       the model decides $30 and keeps deciding $30
    crash          the service commits the refund and the answer never arrives; the agent retries
    duplicate      the same tool call is delivered twice

Four ways to run the same day, against the same payments service (no dedup, refunds can be looked up):

    no gate            the agent calls the tool directly and retries a call that did not answer
    hand check         the check an engineer writes by hand: a stable reference per case, look it up,
                       read what is left right before sending, say how much is left when it is over
    interlock          tools.protect() with premises and a lookup, no approval: a refusal goes to a person
    interlock+repair   the same, plus an approval (3 attempts): a refusal says what changed, and a
                       corrected call that fits the approval is sent, once

Counted per order: finished with no person, handed to a person, and wrong payout (the order got more
than its $20 in total, by hand and by agent together). Writes results/repair_loop.md and .json.
"""
import json, os, random, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import SimulatedCrash
from interlock.tools import protect

SEED, CASE, ATTEMPTS = 4471, 20, 3
MIX = {"routine": 60, "partial_hand": 12, "full_hand": 5, "overshoot": 10, "stubborn": 3, "crash": 5, "duplicate": 5}
SYSTEMS = ("no gate", "hand check", "interlock", "interlock+repair")
GATED = ("interlock", "interlock+repair")


class Shop:
    """
    Payments with no dedup; each order's case approves $20 in total. A refund in `by_hand` lands after the
    agent's first read of the order and before its send: on the order's second read, or when the refund
    call arrives, whichever comes first. An order in `crash` commits and then loses the answer.
    """
    def __init__(self):
        self.refunds, self.reads, self.by_hand, self.crash = [], {}, {}, set()

    def _hand(self, order_id):
        if order_id in self.by_hand:
            self.refunds.append({"order_id": order_id, "amount": self.by_hand.pop(order_id), "reference": None})

    def total(self, order_id):
        return sum(r["amount"] for r in self.refunds if r["order_id"] == order_id)

    def get_order(self, order_id):
        self.reads[order_id] = self.reads.get(order_id, 0) + 1
        if self.reads[order_id] == 2:
            self._hand(order_id)
        return {"order_id": order_id, "refunded_total": self.total(order_id)}

    def get_approval(self, order_id):
        return {"id": f"case-{order_id}", "match": {"order_id": order_id}, "max": {"amount": CASE - self.total(order_id)}}

    def create_refund(self, order_id, amount, reference=None):
        self._hand(order_id)
        self.refunds.append({"order_id": order_id, "amount": amount, "reference": reference})
        if order_id in self.crash:
            self.crash.discard(order_id)
            raise SimulatedCrash(reference)
        return {"refund": len(self.refunds)}

    def find_refund(self, reference):
        return {"found": any(r["reference"] == reference for r in self.refunds)}


def hand_check(shop):
    """The refund tool as a careful engineer writes it without Interlock. Same outcome shape as tools.run()."""
    def create_refund(order_id, amount):
        ref = f"case-{order_id}"                                # one refund per case, found again after a crash
        if shop.find_refund(ref)["found"]:
            return {"ok": True, "status": "ALREADY_REFUNDED", "repair": None,
                    "message": "Already refunded under this case; not sent again."}
        left = CASE - shop.get_order(order_id)["refunded_total"]
        if not isinstance(amount, int) or amount > left:
            step = f"You may send a refund of up to {left}." if left > 0 else "Nothing is left to refund on this case."
            return {"ok": False, "status": "OVER_LIMIT", "repair": {"may_retry": True},
                    "message": f"Not sent: amount {amount!r} is over the {left} left on this case. {step}"}
        try:
            shop.create_refund(order_id, amount, reference=ref)
        except SimulatedCrash:
            return {"ok": False, "status": "IN_FLIGHT", "repair": None,
                    "message": "The payments service did not answer. Retrying the same call is safe: this tool checks for an earlier refund first."}
        return {"ok": True, "status": "SENT", "repair": None, "message": "Refund sent."}
    return create_refund


def build(system, shop):
    fns = {n: getattr(shop, n) for n in ("get_order", "get_approval", "create_refund", "find_refund")}
    if system == "no gate":
        return fns
    if system == "hand check":
        return {**fns, "create_refund": hand_check(shop)}
    spec = {"key": ["order_id"],
            "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"}, "fields": ["refunded_total"]},
            "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
            "idempotency_argument": "reference"}
    if system == "interlock+repair":
        spec["approval"] = {"tool": "get_approval", "arguments": {"order_id": "order_id"}, "attempts": ATTEMPTS}
    return protect(fns, {"journal_dir": tempfile.mkdtemp(), "claim_ttl": 0, "tools": {"create_refund": spec}})


def call(tools, system, order, amount):
    if system != "no gate":
        return tools["create_refund"](order_id=order, amount=amount)
    try:
        tools["create_refund"](order_id=order, amount=amount)
        return {"ok": True}
    except SimulatedCrash:
        return {"ok": False, "status": "IN_FLIGHT", "repair": None}


def agent(tools, system, order, kind):
    tools["get_order"](order_id=order)                          # read the order, then decide
    amount = 30 if kind in ("overshoot", "stubborn") else CASE
    for attempt in range(ATTEMPTS):
        out = call(tools, system, order, amount)
        if kind == "duplicate" and attempt == 0:
            out = call(tools, system, order, amount)            # the same call, delivered twice
        if out["ok"]:
            return "no person"
        if out["status"] == "IN_FLIGHT":                        # no answer: settle what is known, then retry the call
            if system in GATED:
                tools.recover()
            continue
        if out["repair"] and out["repair"]["may_retry"]:
            tools["get_order"](order_id=order)                  # read again, decide again
            left = tools["get_approval"](order_id=order)["max"]["amount"]
            if left <= 0:
                return "no person"                              # the customer already has the $20
            amount = 30 if kind == "stubborn" else left
            continue
        return "person"
    return "person"


def results():
    kinds = [k for k, n in MIX.items() for _ in range(n)]
    random.Random(SEED).shuffle(kinds)
    out = {}
    for system in SYSTEMS:
        shop = Shop()
        tools = build(system, shop)
        by_kind = {k: {"no person": 0, "person": 0, "wrong payout": 0, "overpaid": 0} for k in MIX}
        for i, kind in enumerate(kinds):
            order = f"o{i}"
            if kind == "partial_hand":
                shop.by_hand[order] = 5 + i % 11
            elif kind == "full_hand":
                shop.by_hand[order] = CASE
            elif kind == "crash":
                shop.crash.add(order)
            row = by_kind[kind]
            row[agent(tools, system, order, kind)] += 1
            over = shop.total(order) - CASE
            row["wrong payout"] += over > 0
            row["overpaid"] += max(over, 0)
        total = {m: sum(r[m] for r in by_kind.values()) for m in ("no person", "person", "wrong payout", "overpaid")}
        out[system] = {"total": total, "by_kind": by_kind}
    return out


def markdown(r):
    lines = ["# Results: repair loop", "",
             "Generated by `experiments/repair_loop.py`. 100 refunds, one $20 case each. The mix is an assumption",
             "(see the script); the agent is a scripted loop, not a model. Wrong payout: the order got more than $20 in total.", "",
             "| system | no person | person | wrong payouts | overpaid |", "|---|---|---|---|---|"]
    lines += [f"| {s} | {t['no person']} | {t['person']} | {t['wrong payout']} | ${t['overpaid']} |"
              for s, t in ((s, r[s]["total"]) for s in SYSTEMS)]
    lines += ["", "## By kind (no person / person / wrong payouts)", "",
              "| kind | n | " + " | ".join(SYSTEMS) + " |", "|---|---|" + "---|" * len(SYSTEMS)]
    for k, n in MIX.items():
        cells = [f"{r[s]['by_kind'][k]['no person']} / {r[s]['by_kind'][k]['person']} / {r[s]['by_kind'][k]['wrong payout']}" for s in SYSTEMS]
        lines.append(f"| `{k}` | {n} | " + " | ".join(cells) + " |")
    lines += ["", "## Reading it", "",
              "- **no gate** pays out wrong whenever a fact moves, the model overshoots, a call is retried after a crash,",
              "  or a call arrives twice. It never asks a person.",
              "- **hand check** is written for exactly this refund: a reference per case, a lookup, and a read of what",
              "  is left right before the send. On this day it lands where interlock+repair does. It is new code per",
              "  tool, and it keeps no record of which checks ran.",
              "- **interlock** stops every stale send, crash retry and duplicate, and hands the stale ones to a person.",
              "  With no approval to bound it, a $30 decision on a $20 case goes through: premises say what must not",
              "  change, not how much is allowed. (An approvals.Inbox rule on the amount would catch it; this run has no rules.)",
              "- **interlock+repair** tells the agent what changed and what the approval leaves. A corrected call is",
              "  sent once. A model that keeps asking for more than the approval runs out of attempts and goes to a person.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    r = results()
    out_dir = os.path.join(ROOT, "results")
    with open(os.path.join(out_dir, "repair_loop.json"), "w") as f:
        json.dump(r, f, indent=2)
    with open(os.path.join(out_dir, "repair_loop.md"), "w") as f:
        f.write(markdown(r))
    print(markdown(r))
