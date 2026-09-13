"""
EffectTarget: real Stripe refunds against one PaymentIntent. Test-mode keys only.

Tier 1 with a lookup: Stripe dedupes on the Idempotency-Key header (for 24h), and
refunds can be listed by PaymentIntent and matched on metadata, so recovery can ask
Stripe what it has even after the key window.

Premise captured: how much has been refunded on this payment by anyone other than this
effect. A refund issued by hand from the dashboard changes that number; our own does not.
This detects that the payment's refunds changed after the decision. It does not recognize a
hand refund as the same action: an unrelated refund on the payment refuses too, and a person
re-approves.

Standard library only, like the rest of the repo.
"""
import base64, json, urllib.error, urllib.parse, urllib.request
from ..gate import SimulatedCrash
from .payments import fits

API = "https://api.stripe.com/v1"


class StripeError(RuntimeError):
    pass


def _form(params, prefix=""):
    """Stripe's form encoding: metadata[key]=v, list[]=v."""
    out = []
    for k, v in params.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out += _form(v, key)
        elif isinstance(v, list):
            out += [(f"{key}[]", str(x)) for x in v]
        else:
            out.append((key, str(v)))
    return out


class StripeClient:
    def __init__(self, api_key):
        if not api_key or not api_key.startswith(("sk_test_", "rk_test_")):
            raise ValueError("refusing to run: Interlock's Stripe target takes test-mode keys only (sk_test_ or rk_test_)")
        self._auth = "Basic " + base64.b64encode(f"{api_key}:".encode()).decode()

    def request(self, method, path, params=None, idempotency_key=None):
        query = urllib.parse.urlencode(_form(params or {}))
        url = f"{API}{path}" + (f"?{query}" if method == "GET" and query else "")
        body = query.encode() if method == "POST" else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", self._auth)
        if idempotency_key:
            req.add_header("Idempotency-Key", idempotency_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                obj = json.loads(r.read())
                obj["_replayed"] = r.headers.get("Idempotent-Replayed") == "true"
                return obj
        except urllib.error.HTTPError as e:
            message = json.loads(e.read() or b"{}").get("error", {}).get("message")
            raise StripeError(f"{e.code} {method} {path}: {message}") from None

    def test_payment(self, amount_cents):
        """A confirmed test-mode card payment to refund against."""
        return self.request("POST", "/payment_intents", {
            "amount": amount_cents, "currency": "usd", "payment_method": "pm_card_visa",
            "payment_method_types": ["card"], "confirm": "true"})["id"]


class StripeRefunds:
    tier = 1
    queryable = True
    dedup_window = 24 * 3600

    def __init__(self, client, payment_intent):
        self.client, self.payment_intent = client, payment_intent

    def refunds(self):
        data = self.client.request("GET", "/refunds", {"payment_intent": self.payment_intent, "limit": 100})["data"]
        return [r for r in data if r["status"] != "failed"]

    def refunded_total(self):
        return sum(r["amount"] for r in self.refunds())

    def _by_others(self, eid):
        return sum(r["amount"] for r in self.refunds() if r["metadata"].get("interlock_effect_id") != eid)

    def capture(self):
        # At decision time no refund of this effect exists yet, so every refund, hand refunds included, is someone else's.
        return {"payment_intent": self.payment_intent, "refunded_by_others": self.refunded_total()}

    def validate_premises(self, premises, eid=None):
        was, now = premises["refunded_by_others"], self._by_others(eid)
        return [] if now == was else [f"refunded by others: was {was}, now {now}"]

    def explain(self, premises, eid=None, effect=None):
        """
        Violations come from validate_premises, so subclasses keep working. Only a change in refunds by others is
        explained; the payment's amount is fetched only then, and if that fails, no repairs.
        """
        violations = self.validate_premises(premises, eid)
        if not violations:
            return {"violations": [], "changes": [], "repairs": []}
        was, now = premises["refunded_by_others"], self._by_others(eid)
        if now == was:
            return {"violations": violations, "changes": [], "repairs": []}
        repairs = []
        if effect is not None:
            try:
                total = self.client.request("GET", f"/payment_intents/{self.payment_intent}")["amount_received"]
                repairs = fits(effect["amount"], total - now, total)
            except (StripeError, OSError, KeyError):
                pass
        return {"violations": violations,
                "changes": [{"field": "refunded_by_others", "was": was, "now": now}], "repairs": repairs}

    def idempotency_key(self, eid):
        return eid

    def apply(self, eid, effect, crash_after_effect=False):
        refund = self.client.request("POST", "/refunds", {
            "payment_intent": self.payment_intent, "amount": effect["amount"],
            "metadata": {"interlock_effect_id": eid}}, idempotency_key=self.idempotency_key(eid))
        if crash_after_effect:
            raise SimulatedCrash(eid)                 # Stripe committed; we never record the response
        return {"status": "already_processed" if refund["_replayed"] else "ok", "refund": refund["id"],
                "amount": refund["amount"]}

    def query(self, eid, effect):
        """The id of the refund this effect created, or None."""
        return next((r["id"] for r in self.refunds() if r["metadata"].get("interlock_effect_id") == eid), None)
