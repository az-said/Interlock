"""
EffectTarget: a simulated payments API. Effects are refunds.

The brief says a mock that always behaves perfectly proves nothing, so this
one is configurable to the three real-world levels of cooperation:

    tier 1  accepts an idempotency key and dedupes on it   (Stripe with Idempotency-Key)
    tier 2  no dedup, but refunds can be looked up by ref  (most APIs with a GET)
    tier 3  no dedup, no lookup                            (fire-and-forget: email,
                                                            webhooks, many internal services)

Premises an agent captures: the order's eligibility and amount as it saw them.
"""
from ..gate import SimulatedCrash


class Payments:
    def __init__(self, tier):
        assert tier in (1, 2, 3)
        self.tier = tier
        self.orders = {}
        self.refunds = []

    def create_order(self, order_id, amount, eligible=True):
        self.orders[order_id] = {"amount": amount, "eligible": eligible}

    def set_eligible(self, order_id, eligible):
        self.orders[order_id]["eligible"] = eligible

    def refunds_for(self, order_id):
        return [r for r in self.refunds if r["order"] == order_id]

    def refunded_total(self, order_id):
        return sum(r["amount"] for r in self.refunds_for(order_id))

    def capture(self, order_id):
        o = self.orders[order_id]
        return {"order": order_id, "eligible": o["eligible"], "amount": o["amount"]}

    def validate_premises(self, premises):
        o = self.orders.get(premises["order"])
        if o is None:                               return ["order gone"]
        if o["eligible"] != premises["eligible"]:   return ["eligibility changed"]
        if o["amount"] != premises["amount"]:       return ["amount changed"]
        return []

    def apply(self, eid, effect, crash_after_effect=False):
        if self.tier == 1:
            prior = [r for r in self.refunds if r["eid"] == eid]
            if prior:                                                # server-side dedup, Stripe-style:
                same = {k: v for k, v in prior[0].items() if k != "eid"} == effect
                return {"status": "already_processed" if same else "key_reused_with_different_params"}
        self.refunds.append({"eid": eid, **effect})
        if crash_after_effect:
            raise SimulatedCrash(eid)                                 # ack lost
        return {"status": "ok"}

    def query(self, eid, effect):
        if self.tier == 3:
            raise RuntimeError("tier-3 target has no lookup")
        return any(r["eid"] == eid for r in self.refunds)
