"""
Experiment 4: durable execution on a real Temporal server, instead of modeled.

    uv run --with temporalio python experiments/temporal_live.py

Starts Temporal's local dev server (the SDK downloads it on first run), then runs the
refund step as a Temporal activity under Temporal's own retry policy, two ways:

    temporal             the activity refunds with the idempotency key Temporal's docs
                         recommend: workflow id + activity id
    temporal+interlock   the same activity, with the gate as its body

A worker crash looks to Temporal like an attempt that never reports a result, so each
fault fails the first attempt and lets Temporal schedule the next one. The payments API
is experiment 1's tier-1 simulation, so the only thing that differs from the
`durable@tier1` column is that Temporal itself does the retrying.
Writes results/temporal_live.md. temporalio is not a dependency of the repo.
"""
import asyncio, concurrent.futures, datetime, os, sys, tempfile, uuid
from datetime import timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import temporalio
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from interlock import Gate, Leases, SimulatedCrash
from interlock.targets import Payments

ORDER, AMOUNT = "881", 20
FAULTS = {
    "crash_before_ack":            "attempt 1 refunds, then the worker dies before reporting the result",
    "refund_during_outage":        "attempt 1 dies before sending; support refunds $20 by hand before attempt 2",
    "lease_revoked_during_outage": "attempt 1 dies before sending; refund permission revoked before attempt 2",
    "stale_eligibility":           "no crash; the order becomes ineligible after the decision, before the step runs",
}
EXPECT = {"lease_revoked_during_outage": 0, "stale_eligibility": 0}
RUNS = {}


def outage(run):
    if run["fault"] == "refund_during_outage":
        run["api"].refunds.append({"eid": "dashboard", "order": ORDER, "amount": AMOUNT})
    if run["fault"] == "lease_revoked_during_outage":
        run["leases"].revoke("L-refund")


@activity.defn
def refund_step(run_id: str) -> str:
    run, info = RUNS[run_id], activity.info()
    run["attempts"] = info.attempt
    first = info.attempt == 1
    before_send = first and run["fault"] in ("refund_during_outage", "lease_revoked_during_outage")
    after_effect = first and run["fault"] == "crash_before_ack"

    if run["system"] == "temporal":
        if before_send:
            outage(run)
            raise RuntimeError("worker died before sending")
        run["api"].apply(f"{info.workflow_id}/{info.activity_id}", {"order": ORDER, "amount": AMOUNT})
        if after_effect:
            raise RuntimeError("worker died before reporting the result")
        return "COMPLETED"

    gate = run["gate"]
    recovered = gate.recover()
    if recovered:
        return list(recovered.values())[0]
    try:
        return gate.submit(run["proposal"], crash_before_effect=before_send, crash_after_effect=after_effect)
    except SimulatedCrash:
        outage(run)
        raise RuntimeError("worker died mid-effect") from None


@workflow.defn
class RefundWorkflow:
    @workflow.run
    async def run(self, run_id: str) -> str:
        return await workflow.execute_activity(
            refund_step, run_id, start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(initial_interval=timedelta(milliseconds=200), maximum_attempts=5))


async def main():
    results = {}
    async with await WorkflowEnvironment.start_local() as env:
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            async with Worker(env.client, task_queue="interlock", workflows=[RefundWorkflow],
                              activities=[refund_step], activity_executor=pool,
                              workflow_runner=UnsandboxedWorkflowRunner()):
                for fault in FAULTS:
                    for system in ("temporal", "temporal+interlock"):
                        run_id = uuid.uuid4().hex
                        api = Payments(1)
                        api.create_order(ORDER, 100)
                        leases = Leases()
                        leases.grant("L-refund")
                        run = RUNS[run_id] = {"system": system, "fault": fault, "api": api, "leases": leases}
                        if system == "temporal+interlock":
                            run["gate"] = Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)
                            run["proposal"] = {"agent": "refund-bot", "lease": "L-refund", "request_id": f"case-4471/{run_id}",
                                               "premises": api.capture(ORDER), "effect": {"order": ORDER, "amount": AMOUNT}}
                        if fault == "stale_eligibility":
                            api.set_eligible(ORDER, False)
                        out = await env.client.execute_workflow(RefundWorkflow.run, run_id, id=f"refund-{run_id}", task_queue="interlock")
                        total = api.refunded_total(ORDER)
                        results.setdefault(fault, {})[system] = {
                            "outcome": out, "attempts": run["attempts"], "refunded": f"${total}",
                            "invariant_held": total == EXPECT.get(fault, AMOUNT)}

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = "\n".join(f"| `{f}` | " + " | ".join(
        f"{c['outcome']} · {c['attempts']} attempt{'s' if c['attempts'] != 1 else ''} · {c['refunded']} {'✅' if c['invariant_held'] else '❌'}"
        for c in cells.values()) + " |" for f, cells in results.items())
    md = f"""# Results: durable execution on a real Temporal server

Generated {stamp} by `experiments/temporal_live.py` with temporalio {temporalio.__version__}
and Temporal's local dev server. The refund step is a Temporal activity; Temporal's retry
policy schedules every retry. Invariant: exactly $20 refunded, or $0 if the permission
was revoked or the order became ineligible before the refund landed.

| fault | Temporal, recommended idempotency key | Temporal with Interlock as the activity body |
|---|---|---|
{rows}

## Faults

""" + "\n".join(f"- `{k}`: {v}" for k, v in FAULTS.items()) + """

## Reading it

Temporal does its job: the crashed attempt is retried, and with a stable key the
crash-before-ack refund lands once. In the other rows the facts behind the decision
changed before the retry, and Temporal's retry, correctly by its own contract, runs the
same step again. The same activity with Interlock as its body re-checks lease and
premises before sending and refuses.
"""
    with open(os.path.join(ROOT, "results", "temporal_live.md"), "w") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    asyncio.run(main())
