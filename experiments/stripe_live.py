"""
Experiment 3: the refund faults against real Stripe, in test mode. Not a simulation.

    STRIPE_SECRET_KEY=sk_test_... python3 experiments/stripe_live.py

Each run makes a fresh $100 test-mode card payment and approves one $20 partial
refund, then injects the fault. Same gate, same baselines as experiment 1, pointed at
Stripe itself. Writes results/stripe_live.md. Test-mode keys only: no money moves.
"""
import datetime, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock import Gate, IdempotencyOnly, Leases, Naive, SimulatedCrash
from interlock.targets.stripe_api import StripeClient, StripeRefunds

PAID, AMOUNT = 10000, 2000          # cents
FAULTS = {
    "crash_before_ack":     "Stripe commits the refund; the process dies before the response is recorded",
    "duplicate_submit":     "the same approved request is submitted twice",
    "refund_during_outage": "crash before send; while the agent is down, support refunds $20 by hand",
}
SYSTEMS = {"naive": "naive (today)", "idempotency": "idempotency key only", "gate": "gate (Stripe: key + lookup)"}


def run(client, system, fault):
    pi = client.test_payment(PAID)
    api = StripeRefunds(client, pi)
    leases = Leases()
    leases.grant("L-refund")
    s = {"naive": lambda: Naive(api), "idempotency": lambda: IdempotencyOnly(api),
         "gate": lambda: Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)}[system]()
    P = {"agent": "refund-bot", "lease": "L-refund", "request_id": f"case-4471/{pi}",
         "premises": api.capture(), "effect": {"amount": AMOUNT}}

    def recover_or_retry():
        rec = s.recover()
        if rec:
            return list(rec.values())[0]
        s.submit(P)
        return "RETRIED"

    if fault == "crash_before_ack":
        try: s.submit(P, crash_after_effect=True)
        except SimulatedCrash: pass
        out = recover_or_retry()
    elif fault == "duplicate_submit":
        s.submit(P)
        out = s.submit(P)
    elif fault == "refund_during_outage":
        try: s.submit(P, crash_before_effect=True)
        except SimulatedCrash: pass
        client.request("POST", "/refunds", {"payment_intent": pi, "amount": AMOUNT})    # support, by hand
        out = recover_or_retry()

    total = api.refunded_total()
    return {"payment_intent": pi, "outcome": str(out), "refunded": f"${total // 100}", "invariant_held": total == AMOUNT}


def main():
    try:
        client = StripeClient(os.environ.get("STRIPE_SECRET_KEY"))
    except ValueError as e:
        sys.exit(f"{e}\nSet STRIPE_SECRET_KEY to a test-mode secret key and run again.")

    results = {f: {k: run(client, k, f) for k in SYSTEMS} for f in FAULTS}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    head = "| fault | " + " | ".join(SYSTEMS.values()) + " |\n|---|" + "---|" * len(SYSTEMS)
    rows = "\n".join(f"| `{f}` | " + " | ".join(
        f"{c['outcome']} {c['refunded']} {'✅' if c['invariant_held'] else '❌'}" for c in cells.values()) + " |"
        for f, cells in results.items())
    pis = "\n".join(f"- `{f}` / {k}: `{c['payment_intent']}`" for f, cells in results.items() for k, c in cells.items())
    md = f"""# Results: refund agent against real Stripe (test mode)

Generated {stamp} by `experiments/stripe_live.py`. Every row made real Stripe API calls:
a $100 test card payment, one approved $20 partial refund, then the fault.
Invariant: exactly $20 refunded on the payment.

{head}
{rows}

## Faults

""" + "\n".join(f"- `{k}`: {v}" for k, v in FAULTS.items()) + f"""

## Payments used

Each run's PaymentIntent, for checking in the Stripe test dashboard:

{pis}
"""
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "stripe_live.md")
    with open(out, "w") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
