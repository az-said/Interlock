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
from ..escalation import diff
from ..gate import SimulatedCrash


def fits(amount, remaining, total):
    """Repairs for a refund of `amount` when `remaining` of `total` is left. Suggestions: rules or a person decide."""
    if 0 < amount <= remaining:
        return [{"code": "still_fits", "set": {},
                 "why": f"{amount} still fits: {remaining} of {total} is left to refund, if the other refund was not this one"}]
    if 0 < remaining < amount:
        return [{"code": "refund_remaining", "set": {"amount": remaining},
                 "why": f"{remaining} is what is left to refund on this order"}]
    return []


class Payments:
    dedup_window = 24 * 3600                        # Stripe prunes idempotency keys after 24h

    def __init__(self, tier):
        assert tier in (1, 2, 3)
        self.tier = tier
        self.queryable = tier in (1, 2)             # refunds can be listed and matched by reference
        self.orders = {}
        self.refunds = []
        self.dedup_keys = set()                     # tier 1 only; prune_keys() models expiry

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
        return {"order": order_id, "eligible": o["eligible"], "amount": o["amount"],
                "refunded": self.refunded_total(order_id)}

    def validate_premises(self, premises, eid=None):
        o = self.orders.get(premises["order"])
        if o is None:                               return ["order gone"]
        if o["eligible"] != premises["eligible"]:   return ["eligibility changed"]
        if o["amount"] != premises["amount"]:       return ["amount changed"]
        others = sum(r["amount"] for r in self.refunds_for(premises["order"]) if r["eid"] != eid)
        if others != premises.get("refunded", others): return ["refunded elsewhere since decision"]
        return []

    def explain(self, premises, eid=None, effect=None):
        """What changed, and what could still be sent. Violations come from validate_premises, so subclasses keep working."""
        violations = self.validate_premises(premises, eid)
        if not violations:
            return {"violations": [], "changes": [], "repairs": []}
        o = self.orders.get(premises["order"])
        if o is None:
            return {"violations": violations, "changes": [{"field": "order", "was": premises["order"], "now": None}],
                    "repairs": []}
        others = sum(r["amount"] for r in self.refunds_for(premises["order"]) if r["eid"] != eid)
        now = {"eligible": o["eligible"], "amount": o["amount"], "refunded": others}
        seen = {k: premises[k] for k in now if k in premises}
        repairs = []
        if o["eligible"] and o["amount"] == premises["amount"] and effect is not None:
            repairs = fits(effect["amount"], o["amount"] - others, o["amount"])
        return {"violations": violations, "changes": diff(seen, {k: now[k] for k in seen}), "repairs": repairs}

    def prune_keys(self):
        """The provider's dedup window passed. Refunds stay listable; retries are new requests."""
        self.dedup_keys.clear()

    def apply(self, eid, effect, crash_after_effect=False):
        if self.tier == 1:
            if eid in self.dedup_keys:                               # server-side dedup, Stripe-style:
                prior = next(r for r in self.refunds if r["eid"] == eid)
                same = {k: v for k, v in prior.items() if k != "eid"} == effect
                return {"status": "already_processed" if same else "key_reused_with_different_params"}
            self.dedup_keys.add(eid)
        self.refunds.append({"eid": eid, **effect})
        if crash_after_effect:
            raise SimulatedCrash(eid)                                 # ack lost
        return {"status": "ok"}

    def query(self, eid, effect):
        if self.tier == 3:
            raise RuntimeError("tier-3 target has no lookup")
        return any(r["eid"] == eid for r in self.refunds)
