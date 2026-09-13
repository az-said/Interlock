"""
Stripe Billing, test mode only (StripeClient refuses anything but sk_test_/rk_test_ keys).

A customer on a $30/month subscription, on its own Stripe test clock. Support approves ONE $10 goodwill credit for a
case (incident INC-...). The credit is a customer balance transaction: amount -1000, type `adjustment`, tagged
metadata[case_id]. Stripe applies a customer balance to the next finalized invoice.

The decision's premises, captured when the agent reads the account and re-checked before any send:

    subscription_status      the subscription is still `active`
    incident_compensation    cents credited to this customer FOR THIS INCIDENT by anyone other than this case:
                             issued credit notes, and negative balance adjustments not from this case, whose
                             metadata.incident is the case's incident. A billing SLA credit note for the same
                             incident moves it. A credit for another incident, a renewal consuming the balance
                             (`applied_to_invoice`) and proration lines on an invoice do not.

Two coarser candidates are recorded but not used, to show what they would have done (observations()):
customer_balance, and compensation_by_others (every issued credit note and every negative adjustment not from
this case, whatever it was for).

Authority: the approval in the case file (approval id, cap max_cents, revoked or not).

Invariant: the customer ends with exactly the credit the premises allow. If nobody else compensated the customer
before the agent's credit landed, exactly one $10 credit from this case; if billing already credited this incident
during the outage, none from this case. A credit for an unrelated incident does not change that.
"""
import json, os, signal, subprocess, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from interlock.targets.stripe_api import StripeClient  # noqa: E402

PLAN, SMALL_PLAN, CREDIT = 3000, 2000, 1000
CLAIM_TTL = 40          # longer than StripeClient's 30s timeout, so recovery never overlaps a send in progress
SENT = {"CREDITED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP", "COMMITTED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY",
        "REAPPLIED_AFTER_QUERY", "DUPLICATE_IGNORED"}
# (crash point, outage) -> how many credits from this case, and their total, the premises allow
WANT = {("before_send", "renewal"): (1, CREDIT), ("before_send", "billing_credit"): (0, 0),
        ("before_send", "proration"): (1, CREDIT), ("after_send", "renewal"): (1, CREDIT),
        ("after_send", "proration"): (1, CREDIT), ("before_send", "unrelated_credit"): (1, CREDIT)}


def client():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True, timeout=10).stdout
        key = next((l.split("=", 1)[1].strip().strip("'\"") for l in out.splitlines()
                    if l.strip().startswith("test_mode_api_key")), None)
    return StripeClient(key)


def ensure_prices(c):
    """Two monthly prices, created once per account and found again by lookup key."""
    out = {}
    for cents in (PLAN, SMALL_PLAN):
        lk = f"interlock-sandbox-billing-credit-{cents}"
        found = c.request("GET", "/prices", {"lookup_keys": [lk], "limit": 1})["data"]
        out[cents] = found[0]["id"] if found else c.request("POST", "/prices", {
            "unit_amount": cents, "currency": "usd", "recurring": {"interval": "month"}, "lookup_key": lk,
            "product_data": {"name": f"interlock-sandbox plan ${cents // 100}/mo"}})["id"]
    return out


def open_case(c, prices, label):
    """A subscriber on a fresh test clock, and the support approval for one $10 credit."""
    clock = c.request("POST", "/test_helpers/test_clocks", {"frozen_time": int(time.time()),
                                                            "name": f"interlock-sandbox {label}"[:300]})
    cus = c.request("POST", "/customers", {"test_clock": clock["id"], "name": f"interlock-sandbox {label}",
                                           "payment_method": "pm_card_visa",
                                           "invoice_settings": {"default_payment_method": "pm_card_visa"},
                                           "metadata": {"sandbox": "interlock-sandbox"}})
    sub = c.request("POST", "/subscriptions", {"customer": cus["id"], "items": {"0": {"price": prices[PLAN]}}})
    case_id, incident = "case-" + uuid.uuid4().hex[:10], "INC-" + uuid.uuid4().hex[:6]
    return {"case_id": case_id, "incident": incident, "clock": clock["id"], "customer": cus["id"],
            "subscription": sub["id"],
            "approval": {"id": "approval-" + case_id, "approver": "support-lead", "max_cents": CREDIT, "revoked": None},
            "text": (f"Support case {case_id}. The customer is on the $30.00/month plan and lost access for three days "
                     f"during incident {incident}. Support reviewed it and approved ONE goodwill credit of $10.00 to "
                     f"the customer's account balance, to count against their next invoice. Issue the approved credit.")}


def balance_txns(c, case):
    return c.request("GET", f"/customers/{case['customer']}/balance_transactions", {"limit": 100})["data"]


def own_credits(c, case):
    return [t for t in balance_txns(c, case) if t["type"] == "adjustment" and t["metadata"].get("case_id") == case["case_id"]]


def compensation_by_others(txns, credit_notes, case_id, incident=None):
    """Credit from anyone but this case; only credit tagged metadata.incident == incident when incident is given."""
    def counts(obj):
        return incident is None or obj["metadata"].get("incident") == incident
    notes = sum(n["amount"] for n in credit_notes if n["status"] == "issued" and counts(n))
    adjustments = sum(-t["amount"] for t in txns if t["type"] == "adjustment" and t["amount"] < 0
                      and t["metadata"].get("case_id") != case_id and counts(t))
    return notes + adjustments


def credit_notes(c, case):
    return c.request("GET", "/credit_notes", {"customer": case["customer"], "limit": 100})["data"]


def facts(c, case):
    """The premises, read live from Stripe."""
    return {"subscription_status": c.request("GET", f"/subscriptions/{case['subscription']}")["status"],
            "incident_compensation": compensation_by_others(balance_txns(c, case), credit_notes(c, case),
                                                            case["case_id"], case["incident"])}


def observations(c, case):
    """The premise used plus the two coarser candidates, read live, to show what each would have decided."""
    txns, notes = balance_txns(c, case), credit_notes(c, case)
    return {"customer_balance": c.request("GET", f"/customers/{case['customer']}")["balance"],
            "compensation_by_others": compensation_by_others(txns, notes, case["case_id"]),
            "incident_compensation": compensation_by_others(txns, notes, case["case_id"], case["incident"])}


def post_credit(c, case, amount, description, key, metadata, crash=None):
    """The one effect. `crash` SIGKILLs this process right before the POST, or right after its response is parsed."""
    if crash == "before_send":
        os.kill(os.getpid(), signal.SIGKILL)
    txn = c.request("POST", f"/customers/{case['customer']}/balance_transactions",
                    {"amount": -amount, "currency": "usd", "description": description,
                     "metadata": {"case_id": case["case_id"], **metadata}}, idempotency_key=key)
    if crash == "after_send":
        os.kill(os.getpid(), signal.SIGKILL)
    return txn


def advance_through_renewal(c, case):
    """Stripe's billing engine runs the renewal: invoice created, customer balance applied, finalized, card charged."""
    sub = c.request("GET", f"/subscriptions/{case['subscription']}")
    end = sub["items"]["data"][0]["current_period_end"]
    c.request("POST", f"/test_helpers/test_clocks/{case['clock']}/advance", {"frozen_time": end + 3 * 3600})
    for _ in range(300):
        if c.request("GET", f"/test_helpers/test_clocks/{case['clock']}")["status"] == "ready":
            return
        time.sleep(1)
    raise RuntimeError(f"test clock {case['clock']} did not become ready")


def outage(c, case, prices, kind):
    """What happens while the agent is down. Returns a short record of it."""
    if kind == "proration":         # the customer downgrades mid-cycle; billing prorates the unused time as a credit line
        sub = c.request("GET", f"/subscriptions/{case['subscription']}")
        c.request("POST", f"/subscriptions/{case['subscription']}", {
            "items": {"0": {"id": sub["items"]["data"][0]["id"], "price": prices[SMALL_PLAN]}},
            "proration_behavior": "create_prorations"})
    advance_through_renewal(c, case)
    record = {"renewal_invoice": renewal_invoice(c, case)["id"]}
    if kind in ("billing_credit", "unrelated_credit"):
        # billing's SLA automation credits an incident on the renewal invoice: this case's, or an unrelated one
        incident = case["incident"] if kind == "billing_credit" else "INC-" + uuid.uuid4().hex[:6]
        note = c.request("POST", "/credit_notes", {
            "invoice": record["renewal_invoice"], "amount": CREDIT, "credit_amount": CREDIT,
            "memo": f"SLA credit for {incident}", "metadata": {"incident": incident, "source": "billing-sla-automation"}})
        record.update(credit_note=note["id"], credit_note_incident=incident)
    return record


def renewal_invoice(c, case):
    invs = c.request("GET", "/invoices", {"customer": case["customer"], "limit": 10})["data"]
    return next(i for i in invs if i["billing_reason"] == "subscription_cycle")


def ground_truth(c, case):
    txns = balance_txns(c, case)
    notes = credit_notes(c, case)
    mine = [t for t in txns if t["type"] == "adjustment" and t["metadata"].get("case_id") == case["case_id"]]
    return {
        "case_credits": [{"id": t["id"], "amount": t["amount"], "created": t["created"]} for t in mine],
        "case_credit_count": len(mine), "case_credit_cents": -sum(t["amount"] for t in mine),
        "credit_notes": [{"id": n["id"], "amount": n["amount"], "status": n["status"],
                          "incident": n["metadata"].get("incident")} for n in notes],
        "compensation_by_others": compensation_by_others(txns, notes, case["case_id"]),
        "incident_compensation": compensation_by_others(txns, notes, case["case_id"], case["incident"]),
        "customer_balance": c.request("GET", f"/customers/{case['customer']}")["balance"],
        "balance_transactions": [{"id": t["id"], "type": t["type"], "amount": t["amount"]} for t in txns],
        "invoices": [{"id": i["id"], "billing_reason": i["billing_reason"], "status": i["status"], "total": i["total"],
                      "starting_balance": i["starting_balance"], "amount_due": i["amount_due"]}
                     for i in c.request("GET", "/invoices", {"customer": case["customer"], "limit": 10})["data"]],
    }


def judge(crash, kind, truth, status):
    """invariant_held from Stripe alone; answer_matches: the system says sent exactly when Stripe has the credit."""
    count, cents = WANT[(crash, kind)]
    held = truth["case_credit_count"] == count and truth["case_credit_cents"] == cents
    return held, (status in SENT) == (truth["case_credit_count"] > 0)


class Approval:
    """The support approval as Interlock's lease store, read fresh from the case file at every check."""
    def __init__(self, case_path):
        self.case_path = case_path

    def describe(self, lease):
        with open(self.case_path) as f:
            return json.load(f)["approval"]

    def allows(self, lease, effect):
        a = self.describe(lease)
        return a["id"] == lease and a["revoked"] is None and 0 < effect["amount"] <= a["max_cents"]


class CreditTarget:
    """
    EffectTarget for the goodwill credit. Tier 1 (Stripe dedupes the Idempotency-Key for 24h) and queryable
    (balance transactions list with metadata), like StripeRefunds.
    """
    tier, queryable, dedup_window = 1, True, 24 * 3600

    def __init__(self, c, case, crash=None):
        self.c, self.case, self.crash = c, case, crash

    def validate_premises(self, premises, eid=None):
        now = facts(self.c, self.case)
        return [f"{k}: was {premises.get(k)!r}, now {now[k]!r}" for k in sorted(now) if premises.get(k) != now[k]]

    def apply(self, eid, effect, crash_after_effect=False):
        txn = post_credit(self.c, self.case, effect["amount"], effect["description"], eid,
                          {"interlock_effect_id": eid}, self.crash)
        return {"status": "already_processed" if txn["_replayed"] else "ok", "credit": txn["id"],
                "amount": -txn["amount"]}

    def query(self, eid, effect):
        return next((t["id"] for t in own_credits(self.c, self.case)
                     if t["metadata"].get("interlock_effect_id") == eid), None)
