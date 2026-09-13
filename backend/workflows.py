"""
A support case as a Temporal workflow: `decide` runs the LLM (its result is recorded in history, so
a retry never re-asks the model), then `refund` sends it, one of three ways:

    temporal          Idempotency-Key = workflow run id + "/" + activity id, as Temporal's docs suggest.
                      No re-check in the activity body.
    temporal_checked  the same, plus what a careful Temporal user writes by hand at the top of the activity:
                      if this workflow's own refund is already in Stripe, report it and stop; otherwise the
                      approval must be live and within its amount, with no refunds by others since the decision.
    interlock         the same activity with interlock.temporal.gated() as its body: a shared SQLite journal,
                      durable approval leases, premises captured when the model decided.

All modes check the approval when deciding. Crash points are real SIGKILLs (config.crash_once).
"""
import time
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from backend import agent, config
from backend.leases import DurableLeases
from interlock import Gate
from interlock.journal import effect_id_for
from interlock.targets.stripe_api import StripeRefunds
from interlock.temporal import gated

PRUNED = "/emulated-pruned"             # EMULATED suffix, see config.EMULATE_24H
REFUSALS = ("interlock: REFUSED", "interlock: AMBIGUOUS", "precheck: REFUSED")


class KillableRefunds(StripeRefunds):
    """Real Stripe refunds with the worker's crash points on either side of the POST."""
    queryable = not config.NO_LOOKUP    # EMULATED when False: Stripe can list refunds, this target says it cannot

    def idempotency_key(self, eid):
        return eid + (PRUNED if config.EMULATE_24H else "")

    def apply(self, eid, effect, crash_after_effect=False):
        config.crash_once("before_send")        # DISPATCHED is already durable
        out = super().apply(eid, effect)
        config.crash_once("after_commit")       # Stripe's response is in memory, not yet in the journal or Temporal's history
        return out


class EmulatedClockGate(Gate):
    """
    EMULATED: recovery runs with its clock 25h ahead, past Stripe's 24h idempotency window. This, not the
    pruned key, is what sends the gate to a lookup: without it the gate trusts the key and resends.
    """
    def recover(self, now=None, only=None):
        return super().recover(now=time.time() + 25 * 3600, only=only)


@activity.defn
def decide(case: dict) -> dict:
    leases = DurableLeases(config.path("leases.db"))
    if not leases.is_live(case["lease_id"]):
        raise ApplicationError("approval not live at decision time", non_retryable=True)
    client = config.stripe()
    premises = StripeRefunds(client, case["payment_intent"]).capture()     # the facts the decision rests on
    return {**agent.decide(case["customer_text"], client, case["payment_intent"], leases.max_cents(case["lease_id"])),
            "premises": premises}


@activity.defn
def refund(case: dict, decision: dict) -> dict:
    info, client, pi, amount = activity.info(), config.stripe(), case["payment_intent"], decision["amount_cents"]
    leases = DurableLeases(config.path("leases.db"))
    if case["mode"] != "interlock":
        key = f"{info.workflow_run_id}/{info.activity_id}" + (PRUNED if config.EMULATE_24H else "")
        if case["mode"] == "temporal_checked":
            refunds = StripeRefunds(client, pi).refunds()
            mine = [r["id"] for r in refunds if r["metadata"].get("workflow_id") == info.workflow_id]
            if mine:        # an earlier attempt's refund landed: report it, never resend (works after the key window too)
                return {"outcome": "FOUND_BY_LOOKUP", "refund_id": mine[0], "idempotency_key": key}
            others = sum(r["amount"] for r in refunds)
            if not leases.allows(case["lease_id"], {"amount": amount}):
                raise ApplicationError("precheck: REFUSED:lease", non_retryable=True)
            if others != decision["premises"]["refunded_by_others"]:
                raise ApplicationError("precheck: REFUSED:stale_premise", non_retryable=True)
        config.crash_once("before_send")
        r = client.request("POST", "/refunds", {"payment_intent": pi, "amount": amount,
                                                "metadata": {"workflow_id": info.workflow_id}}, idempotency_key=key)
        config.crash_once("after_commit")       # Stripe's response is in memory, not yet in Temporal's history
        return {"outcome": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund_id": r["id"], "idempotency_key": key}

    gate = (EmulatedClockGate if config.EMULATE_24H else Gate)(
        KillableRefunds(client, pi), config.path("journal.db"), leases, claim_ttl=config.CLAIM_TTL)
    proposal = {"agent": decision["model"], "lease": case["lease_id"], "request_id": case["case_id"],
                "premises": decision["premises"], "effect": {"amount": amount}}
    return {"outcome": gated(gate, proposal), "effect_id": effect_id_for(proposal)}


@workflow.defn
class RefundCase:
    @workflow.run
    async def run(self, case: dict) -> dict:
        decision = await workflow.execute_activity(
            decide, case, start_to_close_timeout=timedelta(seconds=120), retry_policy=RetryPolicy(maximum_attempts=3))
        try:
            result = await workflow.execute_activity(
                refund, args=[case, decision], start_to_close_timeout=timedelta(seconds=15),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=5),
                                         maximum_attempts=config.REFUND_ATTEMPTS))
        except ActivityError as e:
            cause = e.cause
            # A refusal is a final answer. Anything else (a Stripe error, retries used up while IN_FLIGHT)
            # fails the workflow, so a stuck run never reads as an outcome.
            if not (isinstance(cause, ApplicationError) and cause.non_retryable and cause.message.startswith(REFUSALS)):
                raise
            result = {"outcome": cause.message.split(": ", 1)[1]}
        return {"decision": decision, **result}
