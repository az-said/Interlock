"""
A real agent workflow on interlock_runtime, end to end, nothing emulated except the shortened sleep:

    1. a real Stripe test-mode PaymentIntent for $100 is created
    2. the `refund` workflow runs in a real worker process; Claude (claude-haiku-4-5-20251001, via the anthropic SDK)
       decides the refund amount from the customer's message, recorded with the premises it was made on
    3. the workflow waits durably for a human approval signal (rt.approve: a grant bound to that exact payload
       and to the facts the approver saw)
    4. the gated effect sends the refund to Stripe: payload binding, grant and premises checked in the dispatch
       transaction, the send under a watchdog, the commit with the step row
    5. a durable sleep (5s here, EMULATED shortening of the workflow's 3600s), then a verify step queries Stripe

Crashes are optional real SIGKILLs at instrumented kill points: `--crash decide_after_response --crash effect_after_send`
runs one worker per crash in turn; each dies at its point and the next takes over after the lease expires.

    python3 experiments/runtime_pg.py start
    ILR_DSN=postgresql://localhost:55432/ilr uv run --no-project --with 'psycopg[binary]' --with anthropic \
        python experiments/runtime_live_agent.py --approve-as operator --crash effect_after_send

Keys come from the environment (ANTHROPIC_API_KEY, STRIPE_SECRET_KEY) or, if unset, from ANTHROPIC_ENV_FILE and
`stripe config --list` (test mode only). They are passed to the worker process environment and written nowhere.
Writes results/runtime_live_agent.md.
"""
import argparse, json, os, signal, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "runtime"), ROOT]
from experiments import runtime_flows as flows
from interlock.journal import effect_id_for
from interlock.receipts import verify
from interlock.targets.stripe_api import StripeClient
from interlock_runtime import Runtime

MESSAGE = ("Order #881: I paid $100.00 for a phone case bundle. The screen protector in the bundle (listed at $20.00) "
           "arrived cracked; the case itself is fine and I want to keep it. Please refund the screen protector.")
POLICY = ("Refund only the value of the damaged item, in cents. Do not refund items the customer is keeping. "
          "Never exceed the amount paid.")


def load_keys():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        path = os.environ.get("ANTHROPIC_ENV_FILE", "/Users/kiromoussa/CADAI/.env")
        with open(path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip("'\"")
    os.environ["STRIPE_SECRET_KEY"] = flows.stripe_key()          # test-mode keys only; refuses anything else


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--approve-as", help="approve as this operator without prompting (otherwise asks on stdin)")
    p.add_argument("--crash", action="append", default=[], help="kill point for the next worker (repeatable)")
    p.add_argument("--out", default=os.path.join(ROOT, "results", "runtime_live_agent.md"))
    a = p.parse_args()
    load_keys()
    dsn = os.environ["ILR_DSN"]
    rt = Runtime(dsn)
    stripe = StripeClient(os.environ["STRIPE_SECRET_KEY"])
    tmp = tempfile.mkdtemp(prefix="ilr-live-")
    t0 = time.time()

    pi = stripe.test_payment(10000)
    wf_id = f"live-{pi}"
    case = {"id": wf_id, "target": "stripe", "payment_intent": pi, "model": "anthropic",
            "model_id": "claude-haiku-4-5-20251001", "message": MESSAGE, "policy": POLICY,
            "sleep_seconds": 5, "approval_timeout": 3600}
    from interlock_runtime.worker import Worker
    Worker(rt, [flows.refund], worker_id="registrar")               # registers the deployment; runs nothing
    rt.start("refund", wf_id, case)
    print(f"PaymentIntent {pi}: $100.00 paid. Workflow {wf_id} started.")

    crashes, procs, log = list(a.crash), [], []

    def next_worker():
        crash = crashes.pop(0) if crashes else None
        proc = flows.spawn_worker(f"w{len(procs) + 1}", tmp, lease_ttl=10, poll=0.5, env={"ILR_KILL_AT": crash} if crash else {})
        procs.append((proc, crash))
        log.append(f"worker w{len(procs)} started" + (f" with instrumented SIGKILL at `{crash}`" if crash else ""))
        return proc

    def keep_running(until):
        """Start the next worker whenever the current one has died, until `until()` holds."""
        while not until():
            proc, crash = procs[-1]
            code = proc.poll()
            if code is not None:
                log.append(f"worker w{len(procs)} exited with {code}" + (" (SIGKILL)" if code == -signal.SIGKILL else ""))
                next_worker()
            time.sleep(0.3)

    next_worker()
    keep_running(lambda: (rt.describe(wf_id)["workflow"]["waiting"] or {}).get("signal") == "approve"
                 and rt.describe(wf_id)["workflow"]["status"] == "sleeping")
    decide = next(s for s in rt.describe(wf_id)["steps"] if s["kind"] == "decide")["output"]
    amount = decide["response"]["amount"]
    print(f"Claude decided: refund {amount} cents. Reason: {decide['response']['reason']}")
    print(f"Premises recorded with the decision: {decide['premises']}")

    approver = a.approve_as or input(f"Approve a refund of {amount} cents? Type your name to approve: ").strip()
    if not approver:
        sys.exit("not approved")
    grant = rt.approve(wf_id, {"amount": amount}, decide["premises"], by=approver)
    log.append(f"approved by `{approver}` as grant {grant}")
    print(f"Approved by {approver}: grant {grant}, bound to payload {{'amount': {amount}}}")

    keep_running(lambda: rt.describe(wf_id)["workflow"]["status"] in ("completed", "failed", "stuck", "cancelled"))
    for proc, _ in procs:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
    d = rt.describe(wf_id)
    eid = effect_id_for({"request_id": f"refund:{wf_id}"})
    receipt = rt.receipt(eid)
    v = verify(receipt)
    refunds = stripe.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]
    calls = rt.q("select count(*) as n from ilr.llm_calls where workflow_id = %s", (wf_id,))[0]["n"]
    wall = time.time() - t0
    result = d["workflow"]["result"]
    print(json.dumps({"status": d["workflow"]["status"], "result": result, "stripe_refunds": [(r["id"], r["amount"]) for r in refunds],
                      "verify": v}, indent=2, default=str))

    lines = [
        "# interlock_runtime live agent run", "",
        f"Run {time.strftime('%Y-%m-%d %H:%M:%S %Z')}, wall time {wall:.1f}s. Generated by `experiments/runtime_live_agent.py`.", "",
        "Live: Stripe test mode, Claude `claude-haiku-4-5-20251001` through the anthropic SDK, Postgres 17, worker processes.",
        "Crashes: instrumented SIGKILL (a real `kill -9` of the worker process at a named point).",
        "EMULATED: the workflow's post-refund sleep is 5s instead of 3600s. The approval was given by the operator named below "
        "through the script (`--approve-as`), after the workflow had durably suspended waiting for it.", "",
        "## Outcome", "",
        f"- PaymentIntent: `{pi}` (10000 cents paid)",
        f"- workflow `{wf_id}`: status `{d['workflow']['status']}`, effect result `{(result or {}).get('status')}`",
        f"- Stripe refunds on the PaymentIntent: {', '.join(f'`{r['id']}` {r['amount']} cents' for r in refunds) or 'none'}",
        f"- model decision: {amount} cents, \"{decide['response']['reason']}\"",
        f"- LLM calls started: {calls}; recorded decisions: 1; discarded by crashes: {calls - 1}",
        f"- effect sends authorized (effects.sends): {d['effects'][0]['sends'] if d['effects'] else 0}", "",
        "## Timeline", "", *[f"- {x}" for x in log], "",
        "## Steps", "", "| seq | kind | name | epoch |", "|---|---|---|---|",
        *[f"| {s['seq']} | {s['kind']} | {s['name']} | {s['epoch']} |" for s in d["steps"]], "",
        "## Claims", "", "| epoch | owner | previous status |", "|---|---|---|",
        *[f"| {c['epoch']} | {c['owner']} | {c['prev_status']} |" for c in d["claims"]], "",
        "## Receipt", "", "Journal entries: " + ", ".join(e["kind"] + (f" ({e['via']})" if e.get("via") else "") for e in receipt["entries"]), "",
        "`interlock.receipts.verify` output:", "", "```json", json.dumps(v, indent=2, default=str), "```", ""]
    with open(a.out, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
