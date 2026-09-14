"""
The standalone demo's worker, as its own OS process. No Temporal.

    python backend/standalone_worker.py <task>      reads <task>.json: case_id, mode, payment_intent, lease_id, customer_text

It asks the model once and saves the decision to <task>.decision.json before any refund call; a restarted worker
loads that file instead of asking again. Then the refund step, by mode:

    standard   Stripe Idempotency-Key "refund/<case_id>", no re-checks
    checked    the same, after a hand-written check: this case's refund already in Stripe, the approval, the payment's refunds
    interlock  interlock.Gate over the same Stripe refund; gated() runs gate.recover() for this effect before any submit

Notes for the supervisor (backend/standalone.py) go to <task>.notes, one JSON object per line.
Crash injection: INTERLOCK_CRASH=before_send|after_commit with INTERLOCK_CRASH_MARKER, one-shot (config.crash_once).
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import agent, config
from backend.leases import DurableLeases
from interlock import Gate
from interlock.targets.stripe_api import StripeRefunds
from interlock.temporal import gated        # with raise_on_refusal=False it never imports temporalio

UNSETTLED = ("IN_FLIGHT", "UNRESOLVED")


class KillableRefunds(StripeRefunds):
    """Real Stripe refunds with the crash points on either side of the POST, as in backend/workflows.py."""
    def apply(self, eid, effect, crash_after_effect=False):
        config.crash_once("before_send")        # DISPATCHED is already durable
        out = super().apply(eid, effect)
        config.crash_once("after_commit")       # Stripe's response is in memory, not yet in the journal
        return out


def note(task, kind, **data):
    with open(task + ".notes", "a") as f:
        f.write(json.dumps({"kind": kind, "pid": os.getpid(), "t": time.time(), **data}) + "\n")


def decision(task, case, client, leases):
    path = task + ".decision.json"
    if os.path.exists(path):
        note(task, "resumed")
        with open(path) as f:
            return json.load(f)
    if not leases.is_live(case["lease_id"]):
        raise RuntimeError("approval not live at decision time")
    premises = StripeRefunds(client, case["payment_intent"]).capture()      # the facts the decision rests on
    d = {**agent.decide(case["customer_text"], client, case["payment_intent"], leases.max_cents(case["lease_id"])),
         "premises": premises}
    with open(path + ".tmp", "w") as f:
        json.dump(d, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(path + ".tmp", path)
    return d


def refund(case, d, client, leases):
    cid, pi, amount = case["case_id"], case["payment_intent"], d["amount_cents"]
    if case["mode"] == "interlock":
        gate = Gate(KillableRefunds(client, pi), config.path("journal.db"), leases, claim_ttl=config.CLAIM_TTL)
        return gated(gate, {"agent": d["model"], "lease": case["lease_id"], "request_id": cid,
                            "premises": d["premises"], "effect": {"amount": amount}}, raise_on_refusal=False)
    if case["mode"] == "checked":
        refunds = StripeRefunds(client, pi).refunds()
        if any(r["metadata"].get("case_id") == cid for r in refunds):
            return "FOUND_BY_LOOKUP"            # an earlier attempt's refund landed: never resend
        if not leases.allows(case["lease_id"], {"amount": amount}):
            return "REFUSED:lease"
        if sum(r["amount"] for r in refunds) != d["premises"]["refunded_by_others"]:
            return "REFUSED:stale_premise"
    config.crash_once("before_send")
    r = client.request("POST", "/refunds", {"payment_intent": pi, "amount": amount, "metadata": {"case_id": cid}},
                       idempotency_key="refund/" + cid)
    config.crash_once("after_commit")           # Stripe's response is in memory, nowhere else
    return "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED"


def main(task):
    with open(task + ".json") as f:
        case = json.load(f)
    client, leases = config.stripe(), DurableLeases(config.path("leases.db"))
    d = decision(task, case, client, leases)
    deadline, attempt = time.time() + 3 * config.CLAIM_TTL, 0
    while True:     # only Interlock answers "not settled yet": a dead worker's claim on the send has not expired
        attempt += 1
        outcome = refund(case, d, client, leases)
        if not outcome.startswith(UNSETTLED) or time.time() > deadline:
            break
        if attempt == 1:
            note(task, "waiting", attempt=attempt, status=outcome)
        time.sleep(1)
    note(task, "outcome", outcome=outcome, attempts=attempt)


if __name__ == "__main__":
    main(sys.argv[1])
