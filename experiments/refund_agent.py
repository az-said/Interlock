"""
Experiment 1: the refund agent. Built to the team's refund spec
(docs/team-notes/refund-spec-shawn.md) and the brief's own example.

A customer paid $100. Support case #4471 approves ONE $20 partial refund.
(Partial, so the remaining balance can't accidentally mask a duplicate.)
The agent decides; between its decision and the refund landing we inject a fault.

Systems compared:
    naive           re-run the workflow, fresh attempt id each time (today's agent frameworks)
    idempotency     the conventional durable operation: stable key at a cooperating service,
                    no agent runtime ("just use Stripe idempotency keys")
    gate@tier1/2/3  Interlock in front of a service at each cooperation tier

Invariant: exactly $20 is refunded on case #4471 (or $0 if the lease was revoked
or the order became ineligible before landing). Never $40, never $50, never $30.
"""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock import Gate, Naive, IdempotencyOnly, DurableExecution, Leases, SimulatedCrash
from interlock.targets import Payments

FAULTS = {
    "happy_path":              "no fault (control)",
    "crash_before_send":       "in-flight marker durable, process dies before the request is sent",
    "crash_before_ack":        "service commits the refund; process dies before the ack is recorded",
    "duplicate_submit":        "the same approved request is submitted twice",
    "model_redecides":         "after crash_before_ack the re-run model says $30 instead of $20",
    "conflicting_payload":     "same approved request arrives with a different amount, no crash",
    "lease_revoked":           "refund permission revoked after the decision, before it lands",
    "stale_eligibility":       "order becomes ineligible after the decision, before it lands",
    "refund_during_outage":    "crash before send; while the agent is down a human refunds the order by hand",
    "lease_revoked_during_outage": "crash before send; refund permission revoked before recovery",
    "key_expired":             "crash before ack; recovery runs after the provider's 24h idempotency window",
}

CASE, ORDER, AMOUNT = "case-4471", "881", 20

def proposal(api, amount=AMOUNT):
    return {"agent": "refund-bot", "lease": "L-refund", "request_id": CASE,
            "premises": api.capture(ORDER), "effect": {"order": ORDER, "amount": amount}}

def run(system, tier, fault, keep_journal=False):
    api = Payments(tier); api.create_order(ORDER, 100, eligible=True)
    leases = Leases(); leases.grant("L-refund")
    s = {"naive": lambda: Naive(api), "idempotency": lambda: IdempotencyOnly(api),
         "durable": lambda: DurableExecution(api),
         "gate": lambda: Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)}[system]()
    P = proposal(api)

    def recover_or_retry(retry_proposal, now=None):
        rec = s.recover(now=now)
        if rec: return list(rec.values())[0]
        s.submit(retry_proposal); return "RETRIED"          # baselines have no journal

    if fault == "happy_path":
        out = s.submit(P)
    elif fault == "crash_before_send":
        try: s.submit(P, crash_before_effect=True)
        except SimulatedCrash: pass
        out = recover_or_retry(P)
    elif fault == "crash_before_ack":
        try: s.submit(P, crash_after_effect=True)
        except SimulatedCrash: pass
        out = recover_or_retry(P)
    elif fault == "duplicate_submit":
        s.submit(P); out = s.submit(P)
    elif fault == "model_redecides":
        try: s.submit(P, crash_after_effect=True)
        except SimulatedCrash: pass
        s.recover()                                          # gate: resolves recorded $20
        out = s.submit(proposal(api, amount=30))             # everyone: re-run model says $30
    elif fault == "conflicting_payload":
        s.submit(P); out = s.submit(proposal(api, amount=30))
    elif fault == "lease_revoked":
        leases.revoke("L-refund"); out = s.submit(P)
    elif fault == "stale_eligibility":
        api.set_eligible(ORDER, False); out = s.submit(P)
    elif fault == "refund_during_outage":
        try: s.submit(P, crash_before_effect=True)
        except SimulatedCrash: pass
        api.refunds.append({"eid": "dashboard", "order": ORDER, "amount": AMOUNT})   # support refunds by hand
        out = recover_or_retry(P)
    elif fault == "lease_revoked_during_outage":
        try: s.submit(P, crash_before_effect=True)
        except SimulatedCrash: pass
        leases.revoke("L-refund")
        out = recover_or_retry(P)
    elif fault == "key_expired":
        try: s.submit(P, crash_after_effect=True)
        except SimulatedCrash: pass
        api.prune_keys()
        out = recover_or_retry(P, now=time.time() + api.dedup_window + 3600)

    total = api.refunded_total(ORDER)
    expect = 0 if fault in ("lease_revoked", "stale_eligibility", "lease_revoked_during_outage") else AMOUNT
    ambiguous = str(out) == "AMBIGUOUS"
    held = (total == expect) or (ambiguous and total <= expect)
    caveat = "liveness_lost" if ambiguous else ""
    cell = {"outcome": str(out), "refunded": f"${total}", "invariant_held": held, "caveat": caveat}
    if keep_journal:                                         # for viewer/build.py
        cell["expected"] = f"${expect}"
        if system == "gate":
            cell["journal"] = s.journal.entries()
    return cell

SYSTEMS = [("naive", 3, "naive"), ("idempotency", 1, "idempotency@tier1"), ("durable", 1, "durable@tier1"),
           ("gate", 1, "gate@tier1"), ("gate", 2, "gate@tier2"), ("gate", 3, "gate@tier3")]

def results():
    return {fault: {name: run(sysk, tier, fault) for sysk, tier, name in SYSTEMS} for fault in FAULTS}
