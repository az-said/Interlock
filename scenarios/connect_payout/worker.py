"""
One payout step, run as its own OS process so a crash is a real SIGKILL.

    python3 scenarios/connect_payout/worker.py SYSTEM ORDER_JSON STATE_DIR [before|after]

SYSTEM is no_check, hand_check or interlock. With a crash point the process kills itself right
before the transfer POST, or right after Stripe's response arrives and before anything records it.
Prints one JSON line with the step's own answer.

no_check    a stable Idempotency-Key per order ("payout:<order>"), the retry re-runs the step. No re-check.
hand_check  what a careful marketplace engineer writes before a Connect transfer: look up a transfer already
            in this order's transfer_group (Stripe's native grouping for separate charges and transfers), and
            re-read the charge (not refunded) and the seller account (transfers capability active) right before
            sending, plus the same idempotency key and source_transaction, Stripe's native tie of a transfer to
            the charge that funds it. Stripe's docs recommend exactly these reads; nothing is recorded durably.
interlock   interlock.easy: facts saved at decision time, re-checked before send and at recovery, Stripe's key
            as tier 1, the transfer_group lookup by effect id, recovery on restart, a hash-chained receipt.
"""
import json, os, signal, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stripe_connect as sc                                   # noqa: E402
from interlock.easy import Interlock                          # noqa: E402
from interlock.receipts import verify                         # noqa: E402

CLAIM_TTL = 40      # above StripeClient's 30s timeout, so recovery never overlaps a send still in progress


def crash_point(where, crash):
    if crash == where:
        os.kill(os.getpid(), signal.SIGKILL)


def hand_check_decision(facts, existing):
    """None means send. existing: transfers already in this order's group."""
    if existing:
        return "FOUND_BY_LOOKUP"
    if facts["order_refunded_cents"]:
        return "REFUSED:order_reversed"
    if facts["seller_transfers"] != "active":
        return "REFUSED:seller_restricted"
    return None


def _send(c, order, crash, key, effect_id=None):
    crash_point("before", crash)
    t = sc.send_transfer(c, order, key, effect_id)
    crash_point("after", crash)
    return t


def no_check(c, order, state, crash):
    t = _send(c, order, crash, f"payout:{order['id']}")
    return {"status": "REPLAYED_BY_STRIPE" if t["_replayed"] else "TRANSFERRED", "transfer": t["id"]}


def hand_check(c, order, state, crash):
    existing = sc.transfers(c, order)
    refused = hand_check_decision(sc.facts(c, order), existing)
    if refused:
        return {"status": refused, "transfer": existing[0]["id"] if existing else None}
    t = _send(c, order, crash, f"payout:{order['id']}")
    return {"status": "REPLAYED_BY_STRIPE" if t["_replayed"] else "TRANSFERRED", "transfer": t["id"]}


def interlock_payout(c, state, crash=None):
    gate = Interlock(state, claim_ttl=CLAIM_TTL)

    def lookup(order, idempotency_key):
        return next((t["id"] for t in sc.transfers(c, order)
                     if t["metadata"].get("interlock_effect_id") == idempotency_key), None)

    @gate.effect(key=lambda order: f"payout:{order['id']}", premises=lambda order: sc.facts(c, order),
                 lookup=lookup, dedupes=True)
    def payout(order, idempotency_key):
        return _send(c, order, crash, idempotency_key, idempotency_key)["id"]

    return gate, payout


def interlock(c, order, state, crash, wait=CLAIM_TTL + 20):
    gate, payout = interlock_payout(c, state, crash)
    deadline = time.time() + wait
    while True:
        recovered = next(iter(gate.recover().values()))                # a dead sender's claim blocks until it expires
        status = next(iter(recovered.values()), None) or payout(order)[0]
        if status != "IN_FLIGHT" or time.time() > deadline:
            break
        time.sleep(2)
    bundle = payout.gate.receipt_bundle(payout.proposal(order))
    return {"status": status, "transfer": lookup_id(c, order, bundle["effect_id"]), "receipt": verify(bundle),
            "journal": [e["kind"] for e in bundle["entries"]]}


def lookup_id(c, order, eid):
    return next((t["id"] for t in sc.transfers(c, order) if t["metadata"].get("interlock_effect_id") == eid), None)


SYSTEMS = {"no_check": no_check, "hand_check": hand_check, "interlock": interlock}


def main(argv):
    system, order, state = argv[0], json.loads(argv[1]), argv[2]
    crash = argv[3] if len(argv) > 3 else None
    try:
        out = SYSTEMS[system](sc.client(), order, state, crash)
    except sc.StripeError as e:
        out = {"status": "STRIPE_ERROR", "error": str(e)}
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
