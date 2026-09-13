"""
Stripe disputes and refunds, test mode only (StripeClient refuses anything but sk_test_/rk_test_ keys).

A case is a $100 payment made with pm_card_createDisputeInquiry (card 4000000000001976), Stripe's documented test
card whose charge "succeeds, then is disputed as an inquiry": a dispute object in status warning_needs_response,
no funds withdrawn. Support approves a $20 goodwill refund while the inquiry is open; Stripe accepts refunds then.

During the outage the harness escalates the inquiry with the documented evidence value escalate_inquiry_evidence,
which turns it into a chargeback: status needs_response and a balance transaction withdrawing the $100. That is a
real dispute opening after the decision. Stripe's other dispute cards (pm_card_createDispute and friends) open
their chargeback within a second of the charge, before any decision could be made, so they cannot stage this.

Measured on this account before writing this (probe PaymentIntents in results/scenarios/stripe_dispute.md):
Stripe refuses a refund on a charged-back charge ("has been charged back; cannot issue a refund"), and during the
~4s escalation window (warning_under_review) it accepted one that later went to status failed.
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from interlock.targets.stripe_api import StripeClient, StripeError  # noqa: E402,F401

PAID, APPROVED = 10000, 2000
CARD = "pm_card_createDisputeInquiry"
CHARGEBACK = ("needs_response", "under_review", "won", "lost")     # statuses of a dispute that is a chargeback


def client():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True, timeout=10).stdout
        key = next((l.split("=", 1)[1].strip().strip("'\"") for l in out.splitlines()
                    if l.strip().startswith("test_mode_api_key")), None)
    return StripeClient(key)


def _wait(read, done, timeout=60):
    deadline = time.time() + timeout
    while True:
        value = read()
        if done(value) or time.time() > deadline:
            return value
        time.sleep(0.5)


def create_case(c, tag):
    """The customer pays $100; the bank opens an inquiry on it. Returns once Stripe shows the inquiry."""
    pi = c.request("POST", "/payment_intents", {
        "amount": PAID, "currency": "usd", "payment_method": CARD, "payment_method_types": ["card"],
        "confirm": "true", "metadata": {"case": tag, "sandbox": "interlock-sandbox"}})
    case = {"id": tag, "payment_intent": pi["id"], "charge": pi["latest_charge"]}
    ds = _wait(lambda: disputes(c, case), bool)
    if not ds or ds[0]["status"] != "warning_needs_response":
        raise StripeError(f"{pi['id']}: expected an inquiry, Stripe shows {[d['status'] for d in ds]}")
    return {**case, "dispute": ds[0]["id"]}


def disputes(c, case):
    return c.request("GET", "/disputes", {"payment_intent": case["payment_intent"], "limit": 100})["data"]


def refunds(c, case):
    """Every refund on the payment, failed ones included."""
    return c.request("GET", "/refunds", {"payment_intent": case["payment_intent"], "limit": 100})["data"]


def facts(c, case, idempotency_key=None):
    """What the refund decision rests on, read from Stripe now. A refund carrying this effect's id is not someone else's."""
    return {"chargebacks": sorted(d["id"] for d in disputes(c, case) if d["status"] in CHARGEBACK),
            "refunded_by_others": sum(r["amount"] for r in refunds(c, case) if r["status"] != "failed"
                                      and (idempotency_key is None or r["metadata"].get("interlock_effect_id") != idempotency_key))}


def send_refund(c, case, amount, key, effect_id=None):
    meta = {"case": case["id"], **({"interlock_effect_id": effect_id} if effect_id else {})}
    return c.request("POST", "/refunds", {"payment_intent": case["payment_intent"], "amount": amount,
                                          "metadata": meta}, idempotency_key=key)


def escalate(c, case):
    """The bank escalates the inquiry to a chargeback. Returns once Stripe shows it (needs_response)."""
    started = time.time()
    c.request("POST", f"/disputes/{case['dispute']}", {"evidence": {"uncategorized_text": "escalate_inquiry_evidence"},
                                                       "submit": "true"})
    d = _wait(lambda: c.request("GET", f"/disputes/{case['dispute']}"), lambda d: d["status"] in CHARGEBACK and chargeback_at(d))
    if d["status"] not in CHARGEBACK or not chargeback_at(d):
        raise StripeError(f"{case['dispute']} stayed {d['status']} after escalation")
    return {"dispute": d["id"], "status": d["status"], "chargeback_at": chargeback_at(d),
            "seconds_to_chargeback": round(time.time() - started, 1)}


def chargeback_at(dispute):
    """Stripe's own time the chargeback withdrew funds, or None."""
    return min((b["created"] for b in dispute["balance_transactions"] if b["amount"] < 0), default=None)


def verdict(rs, charged_back_at, want_issued):
    """
    (refunds issued, refunds issued at or after the chargeback) and whether the invariant held: exactly `want_issued`
    refunds were issued, none of them on the charged-back charge. Issued counts every status: Stripe fails a refund
    once a chargeback posts, but the request was still accepted.
    """
    late = [r["id"] for r in rs if charged_back_at is not None and r["created"] >= charged_back_at]
    return len(rs), late, len(rs) == want_issued and not late


def landed(status):
    """Whether a worker's answer says a refund was issued, meaning Stripe accepted a refund request."""
    return status in ("REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP", "COMMITTED", "COMMITTED_ON_QUERY",
                      "COMMITTED_BY_RETRY", "REAPPLIED_AFTER_QUERY")


def money_returned(rs):
    """Whether any refund on the payment moved money back to the customer (a failed refund moved none)."""
    return any(r["status"] in ("succeeded", "pending") for r in rs)


def proof(system, record, rs):
    """
    Score the record a system left in its state dir, not its name. rs: Stripe's refunds, read afterwards.
      decision_recorded   the saved decision names the model and its reason (every column saves it)
      checks_recorded     the record lists the checks that ran and the values they read
      outcome_matches     the record's last word is a refund id Stripe holds, or a refusal when Stripe holds none
      tamper_evident      the system's own verifier rejects a copy with one entry altered (run here, not assumed)
      final_status_known  the record says whether the refund later failed (no column's record can)
    """
    ids, rid = {r["id"] for r in rs}, None
    decided = bool((record.get("decision") or {}).get("reason"))
    checks = outcome = tamper = False
    if system == "interlock" and record.get("receipt"):
        from interlock.receipts import verify
        v, forged = verify(record["receipt"]), json.loads(json.dumps(record["receipt"]))
        forged["entries"][-1]["reason" if forged["entries"][-1]["kind"] == "REFUSED" else "found"] = "forged"
        checks = any("checks" in e or "rechecked" in e for e in record["receipt"]["entries"])
        rid = v["evidence"] if v["happened"] is True else None
        outcome = v["valid"] and ((rid in ids) if rs else v["happened"] is False)
        tamper = verify(forged)["valid"] is False
    elif system == "hand_check" and record.get("hand_check_log"):
        lines = record["hand_check_log"]
        last = lines[-1]
        checks = any(x["step"] == "checks" and "now" in x for x in lines)
        rid = last.get("refund") or next(iter(last.get("lookup") or []), None)
        outcome = (rid in ids) if rs else rid is None and last.get("result", "").startswith("REFUSED")
    return {"decision_recorded": decided, "checks_recorded": checks, "outcome_matches": bool(outcome),
            "refund_in_record": rid, "tamper_evident": tamper, "final_status_known": False}
