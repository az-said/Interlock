"""
Stripe Connect, test mode only (StripeClient refuses anything but sk_test_/rk_test_ keys).

An order is a $100 buyer payment on the platform (separate charges and transfers, grouped by transfer_group).
The payout is a $20 transfer to the seller's connected account, funded from that charge (source_transaction).
Two real premises that can change during an outage:
    order reversed      the buyer's charge is refunded           (charge.amount_refunded > 0)
    seller restricted   the platform rejects the seller account  (capabilities.transfers != "active")
"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from interlock.targets.stripe_api import StripeClient, StripeError  # noqa: E402

PAID, PAYOUT = 10000, 2000
NOT_ENABLED = "signed up for Connect"      # Stripe's error text when the platform has no Connect


def client():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True, timeout=10).stdout
        key = next((l.split("=", 1)[1].strip().strip("'\"") for l in out.splitlines()
                    if l.strip().startswith("test_mode_api_key")), None)
    return StripeClient(key)


def create_seller(c, tag):
    """A Custom connected account with Stripe's test verification values, so transfers go active without a person."""
    acct = c.request("POST", "/accounts", {
        "type": "custom", "country": "US", "business_type": "individual", "email": f"{tag}@example.com",
        "capabilities": {"transfers": {"requested": "true"}},
        "business_profile": {"mcc": "5734", "url": "https://accessible.stripe.com", "name": tag},
        "individual": {"first_name": "Interlock", "last_name": "Sandbox", "email": f"{tag}@example.com",
                       "phone": "0000000000", "ssn_last_4": "0000", "id_number": "000000000",
                       "dob": {"day": 1, "month": 1, "year": 1901},
                       "address": {"line1": "address_full_match", "city": "Boston", "state": "MA",
                                   "postal_code": "02110", "country": "US"}},
        "external_account": "btok_us_verified",
        "tos_acceptance": {"date": int(time.time()), "ip": "127.0.0.1"},
        "metadata": {"sandbox": "interlock-sandbox"}})
    for _ in range(30):
        if acct["capabilities"].get("transfers") == "active":
            return acct["id"]
        time.sleep(1)
        acct = c.request("GET", f"/accounts/{acct['id']}")
    raise StripeError(f"seller {acct['id']} transfers capability stayed {acct['capabilities'].get('transfers')}")


def create_order(c, seller, order_id):
    """The buyer pays $100. pm_card_bypassPending makes the funds available at once, as a settled order."""
    pi = c.request("POST", "/payment_intents", {
        "amount": PAID, "currency": "usd", "payment_method": "pm_card_bypassPending", "payment_method_types": ["card"],
        "confirm": "true", "transfer_group": order_id, "metadata": {"order": order_id, "seller": seller}})
    return {"id": order_id, "seller": seller, "payment_intent": pi["id"], "charge": pi["latest_charge"]}


def facts(c, order):
    """What the payout decision rests on, read from Stripe now."""
    return {"order_refunded_cents": c.request("GET", f"/charges/{order['charge']}")["amount_refunded"],
            "seller_transfers": c.request("GET", f"/accounts/{order['seller']}")["capabilities"].get("transfers")}


def transfers(c, order):
    return c.request("GET", "/transfers", {"transfer_group": order["id"], "destination": order["seller"],
                                           "limit": 100})["data"]


def paid_out(ts):
    """(cents that stayed with the seller, transfers that did)."""
    kept = [t for t in ts if t["amount"] > t["amount_reversed"]]
    return sum(t["amount"] - t["amount_reversed"] for t in kept), len(kept)


def send_transfer(c, order, key, effect_id=None):
    meta = {"order": order["id"], **({"interlock_effect_id": effect_id} if effect_id else {})}
    return c.request("POST", "/transfers", {
        "amount": PAYOUT, "currency": "usd", "destination": order["seller"], "transfer_group": order["id"],
        "source_transaction": order["charge"], "metadata": meta}, idempotency_key=key)


def reverse_order(c, order):
    """The buyer's payment is refunded in full: the order is reversed."""
    return c.request("POST", "/refunds", {"payment_intent": order["payment_intent"]})["id"]


def restrict_seller(c, order):
    """The platform rejects the seller (Custom accounts only): transfers capability goes inactive."""
    return c.request("POST", f"/accounts/{order['seller']}/reject", {"reason": "fraud"})["id"]
