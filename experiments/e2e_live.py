"""
End to end, nothing simulated in-process: a real LLM refund agent, Stripe test mode, a real Temporal
server, and worker processes killed with SIGKILL. One command:

    ANTHROPIC_API_KEY=$(grep ^ANTHROPIC_API_KEY= /path/to/.env | cut -d= -f2-) uv run --no-project --with temporalio python experiments/e2e_live.py

Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only).
Starts Temporal's dev server, then backend/api.py and backend/worker.py as their own processes, and
drives every cell only through the HTTP API and process control. Ground truth is Stripe's refund list
for the cell's PaymentIntent. Writes results/e2e_live.json and results/e2e_live.md; check them with
experiments/e2e_audit.py. Pass scenario:mode arguments (e.g. crash_after_commit:interlock) to run some
cells and print them only.
"""
import asyncio, datetime, json, os, signal, socket, statistics, subprocess, sys, tempfile, time, urllib.error, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import temporalio
from temporalio.testing import WorkflowEnvironment

PAID, APPROVED = 10000, 2000
MODES = ("temporal", "temporal_checked", "interlock")
COLUMNS = {"temporal": "Temporal: idempotency key, no re-check in the activity",
           "temporal_checked": "Temporal: idempotency key plus a hand-written re-check",
           "interlock": "Temporal with Interlock as the activity body"}
SENT = {"REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP", "COMMITTED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY",
        "REAPPLIED_AFTER_QUERY", "DUPLICATE_IGNORED"}
CASE_TEXT = ("Order #881, paid $100.00 by card. The blender arrived with its glass jar cracked. "
             "Support case #4471: support reviewed the photos and approved ONE partial refund of $20.00 for the jar; "
             "the customer keeps the blender. Issue the approved refund.")
KEY_PRUNED = (
    "Stripe keeps an idempotency key for at least 24 hours and cannot be made to forget one on demand, and nobody "
    "waited a day. The columns do not get the same emulated input. All three: after the restart, each refund POST "
    "uses Idempotency-Key '<original key>/emulated-pruned', a key Stripe has never seen, which is how a pruned key "
    "looks to Stripe (INTERLOCK_EMULATE_24H=1). Interlock only: its gate also recovers with its clock moved 25h "
    "ahead (EmulatedClockGate in backend/workflows.py), standing in for the day that would really have passed. "
    "Interlock's result in this row depends on that clock, not on the key: the gate compares the clock with the "
    "timestamp of its DISPATCHED entry, finds it older than Stripe's 24h window, and looks the refund up instead of "
    "resending, so it never sends the pruned key. Given the pruned key without the moved clock, it would resend under "
    "the pruned key and create a second refund, as plain Temporal did (read from gate.py, not run: a key lost inside "
    "24h is outside what Stripe documents). The hand-written re-check column needs no clock, because it looks up "
    "its own refund before every send; a Temporal activity could also compare activity.info().scheduled_time with "
    "now. The timing is emulated too: the retry came seconds after the crash. In this workflow a retry that late "
    "happens if no worker picks the task up for more than 24h (an attempt only starts, and only times out, once a "
    "worker takes it), or with a retry policy, schedule or reconciler that spans more than a day. What this row "
    "shows is that a key alone does not survive pruning and a lookup does.")
NO_LOOKUP = (
    "Emulated as in key_pruned_after_24h (pruned key, gate clock 25h ahead), and the Interlock target also declares "
    "that it cannot list refunds (INTERLOCK_NO_LOOKUP=1), as for a provider with no way to look up what it did. "
    "Stripe itself can list refunds. Run for Interlock only: it shows the gate saying AMBIGUOUS instead of guessing.")


def scenario(crash, text, want_cents=APPROVED, want_refunds=1, action=None, env=None, emulated=None, modes=MODES,
             before=None):
    return dict(crash=crash, text=text, want_cents=want_cents, want_refunds=want_refunds, action=action,
                env=env or {}, emulated=emulated, modes=modes, before=before)


AFTER = "worker SIGKILLed after Stripe's response to the refund POST arrived, before anything recorded it"
SCENARIOS = {
    "crash_after_commit": scenario("after_commit", f"{AFTER}; worker restarted"),
    "hand_refund_before_decision": scenario(
        "after_commit", "support refunds an unrelated $5 by hand before any worker runs the case, so the model reads a "
        f"payment with $5 already refunded; then {AFTER}; worker restarted. Want: both, $25 in 2 refunds",
        want_cents=APPROVED + 500, want_refunds=2, before=("manual-refund", 500)),
    "hand_refund_during_outage": scenario(
        "before_send", "worker SIGKILLed right before the refund POST; support refunds the same $20 by hand in Stripe; "
        "worker restarted. Want: only the hand refund", action=("manual-refund", APPROVED)),
    "unrelated_refund_during_outage": scenario(
        "before_send", "worker SIGKILLed right before the refund POST; support issues an unrelated $5 goodwill refund "
        "by hand; worker restarted. Want: both, $25 in 2 refunds", want_cents=APPROVED + 500, want_refunds=2,
        action=("manual-refund", 500)),
    "approval_revoked_during_outage": scenario(
        "before_send", "worker SIGKILLed right before the refund POST; the approval is revoked; worker restarted. "
        "Want: nothing", want_cents=0, want_refunds=0, action=("revoke", None)),
    "approval_revoked_after_commit": scenario(
        "after_commit", f"{AFTER}; the approval is revoked; worker restarted. "
        "Want: the one refund that landed while the approval was live, reported as sent", action=("revoke", None)),
    "key_pruned_after_24h": scenario(
        "after_commit", f"{AFTER}; restarted with Stripe's memory of the key EMULATED as gone (and, for Interlock "
        "only, its clock moved 25h)", env={"INTERLOCK_EMULATE_24H": "1"}, emulated=KEY_PRUNED),
    "no_lookup_after_24h": scenario(
        "after_commit", "as key_pruned_after_24h, with a target that cannot look refunds up (EMULATED). Want: no second "
        "refund, and an honest AMBIGUOUS", env={"INTERLOCK_EMULATE_24H": "1", "INTERLOCK_NO_LOOKUP": "1"},
        emulated=NO_LOOKUP, modes=("interlock",)),
}


def http(api, method, path, body=None):
    req = urllib.request.Request(api + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:500]}") from None


def spawn(script, env, log):
    return subprocess.Popen([sys.executable, os.path.join(ROOT, "backend", script)], env=env, stdout=log, stderr=log)


def run_cell(api, env, data, name, mode):
    sc = SCENARIOS[name]
    env = {**env, "INTERLOCK_CRASH": sc["crash"], "INTERLOCK_CRASH_MARKER": os.path.join(data, f"crash-{name}-{mode}")}
    log = open(os.path.join(data, f"worker-{name}-{mode}.log"), "ab")
    case = http(api, "POST", "/cases", {"customer_text": CASE_TEXT, "paid_cents": PAID, "approved_cents": APPROVED, "mode": mode})
    print(f"[{name}:{mode}] {case['case_id']} {case['payment_intent']} {case['workflow_id']}", flush=True)
    before = None
    if sc["before"]:            # no worker is polling yet, so the workflow waits and the model reads the changed payment
        kind, cents = sc["before"]
        before = {kind: http(api, "POST", f"/cases/{case['case_id']}/{kind}", {"amount_cents": cents})}
    worker = spawn("worker.py", env, log)
    deadline = time.time() + 240
    while worker.poll() is None and time.time() < deadline:
        time.sleep(0.2)
    if worker.poll() is None:
        worker.kill()
        raise RuntimeError(f"{name}:{mode}: worker never reached {sc['crash']}")
    exit_code, crashed_at = worker.returncode, time.time()
    print(f"[{name}:{mode}] worker exited {exit_code} at {sc['crash']}", flush=True)

    action = None
    if sc["action"]:
        kind, cents = sc["action"]
        action = {kind: http(api, "POST", f"/cases/{case['case_id']}/{kind}", {"amount_cents": cents} if cents else {})}
    worker = spawn("worker.py", {**env, **sc["env"]}, log)
    try:
        deadline = time.time() + 300
        while http(api, "GET", f"/cases/{case['case_id']}")["workflow"]["status"] == "RUNNING" and time.time() < deadline:
            time.sleep(2)
    finally:
        worker.terminate()
        worker.wait(10)
        log.close()

    time.sleep(2)                                           # then re-read Stripe once more for the record
    state = http(api, "GET", f"/cases/{case['case_id']}")
    wf, receipt = state["workflow"], state["interlock"]
    result = wf.get("result") or {}
    decision = result.get("decision") or {}
    outcome = result.get("outcome") or wf.get("failure")
    live = [r for r in state["stripe"]["refunds"] if r["status"] != "failed"]
    eid = receipt["effect_id"] if receipt else None
    own = [r["id"] for r in live if r["metadata"].get("workflow_id") == case["workflow_id"]
           or (eid and r["metadata"].get("interlock_effect_id") == eid)]
    refused = str(outcome).startswith("REFUSED")
    refunded = sum(r["amount"] for r in live)
    return {
        "scenario": name, "mode": mode, "case_id": case["case_id"], "payment_intent": case["payment_intent"],
        "workflow_id": case["workflow_id"], "workflow_status": wf["status"],
        "workflow_ok": wf["status"] == "COMPLETED" and (outcome in SENT or refused or outcome == "AMBIGUOUS"),
        "attempts": wf["attempts"].get("refund"), "attempts_by_activity": wf["attempts"],
        "llm_decision": {k: decision.get(k) for k in ("amount_cents", "reason", "model", "tool_call")},
        "approved_cents": APPROVED, "decision_matches_approval": decision.get("amount_cents") == APPROVED,
        "outcome": outcome, "agent_refund_ids": own,
        # does the run's own answer agree with Stripe: sent means exactly one refund of ours, refused means none
        "answer_matches_stripe": len(own) == 1 if outcome in SENT else len(own) == 0 if refused else outcome == "AMBIGUOUS",
        "refund_ids": [r["id"] for r in live], "refunds": state["stripe"]["refunds"],
        "refunded_cents": refunded, "expected_cents": sc["want_cents"], "expected_refunds": sc["want_refunds"],
        "invariant_held": refunded == sc["want_cents"] and len(live) == sc["want_refunds"],
        "receipt": receipt,
        "crash": {"point": sc["crash"], "worker_exit_code": exit_code, "sigkill": exit_code == -signal.SIGKILL},
        # from the harness seeing the SIGKILLed worker exit (polled every 0.2s) to Temporal's close time
        "seconds_crash_to_close": round(wf["close_time"] - crashed_at, 1) if wf.get("close_time") else None,
        "action_before_decision": before, "outage_action": action, "emulated": sc["emulated"],
    }


def run(address, only):
    data = tempfile.mkdtemp(prefix="interlock-e2e-")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "TEMPORAL_ADDRESS": address, "INTERLOCK_DATA": data, "INTERLOCK_API_PORT": str(port)}
    api_log = open(os.path.join(data, "api.log"), "ab")
    api_proc, api = spawn("api.py", env, api_log), f"http://127.0.0.1:{port}"
    print(f"data {data}  api {api}  temporal {address}", flush=True)
    try:
        for _ in range(120):
            try:
                if http(api, "GET", "/health")["temporal_serving"]:
                    break
            except (OSError, RuntimeError):
                time.sleep(0.5)
        cells = [run_cell(api, env, data, s, m) for s, sc in SCENARIOS.items() for m in sc["modes"]
                 if not only or f"{s}:{m}" in only]
    finally:
        api_proc.terminate()
        api_proc.wait(10)
    return cells


def cell_text(c):
    diff, n = c["refunded_cents"] - c["expected_cents"], len(c["refund_ids"])
    verdict = ("held" if c["invariant_held"] else f"VIOLATED, ${diff / 100:.0f} too much" if diff > 0
               else f"SHORT by ${-diff / 100:.0f}" if diff < 0 else "VIOLATED, wrong refund count")
    return (f"{c['outcome']}; ${c['refunded_cents'] / 100:.0f} in {n} refund{'s' if n != 1 else ''} "
            f"(want ${c['expected_cents'] / 100:.0f} in {c['expected_refunds']}); attempt {c['attempts']}, "
            f"{c['seconds_crash_to_close']}s crash to close; **{verdict}**; "
            f"answer {'matches' if c['answer_matches_stripe'] else 'CONTRADICTS'} Stripe"
            + ("" if c["workflow_ok"] else "; WORKFLOW DID NOT COMPLETE WITH A KNOWN OUTCOME"))


def receipt_text(r):
    v, b = r["verification"], r["bundle"]
    via = next((e.get("via") for e in b["entries"] if e["kind"] == "COMMITTED"), None)
    ev, rc = v.get("evidence"), v.get("rechecked_at_recovery")
    ev = f"refund {ev['refund']} ({ev['status']})" if isinstance(ev, dict) else ev
    recheck = rc and ("approval revoked" if not rc["lease_live"] else
                      f"premises changed: {'; '.join(rc['violations'])}" if rc.get("violations") else "passed")
    return (f", receipt `{b['summary']['final']}`" + (f" via `{via}`" if via else "")
            + f" (valid={v['valid']}, signed={v['signed']}, happened={v['happened']}, "
              f"authorized_when_fired={v['authorized_when_fired']}, assumptions_held={v['assumptions_held']}"
            + (f", evidence `{ev}`" if ev else "") + (f", re-check at recovery: {recheck}" if recheck else "")
            + (f", refused='{v['refused']}'" if v.get("refused") else "") + ")")


def markdown(out):
    by = {(c["scenario"], c["mode"]): c for c in out["cells"]}
    rows = "\n".join(f"| `{s}`{' (EMULATED)' if sc['emulated'] else ''} | "
                     + " | ".join(cell_text(by[s, m]) if (s, m) in by else "not run" if m in sc["modes"] else "n/a"
                                  for m in MODES) + " |"
                     for s, sc in SCENARIOS.items())
    shared = [s for s, sc in SCENARIOS.items() if sc["modes"] == MODES and all((s, m) in by for m in MODES)]
    real = [s for s in shared if not SCENARIOS[s]["emulated"]]

    def count(cs, key):
        return f"{sum(c[key] for c in cs)}/{len(cs)}"
    def line(m):
        cs, cr = [by[s, m] for s in shared], [by[s, m] for s in real]
        return (f"- {COLUMNS[m]}: {count(cs, 'invariant_held')} left Stripe as wanted ({count(cr, 'invariant_held')} "
                f"of the rows that are not emulated), {count(cs, 'answer_matches_stripe')} answers matched Stripe, "
                f"{count(cs, 'workflow_ok')} completed with a known outcome, median "
                f"{statistics.median(c['seconds_crash_to_close'] for c in cs):.0f}s from crash to close")
    tally = "\n".join(line(m) for m in MODES) if shared else "(no scenario ran in every column)"
    def med(m):
        return statistics.median(c["seconds_crash_to_close"] for c in out["cells"] if c["mode"] == m) if by else 0
    only = "; ".join(f"`{c['scenario']}` / {c['mode']}: {cell_text(c)}" for c in out["cells"] if c["scenario"] not in shared)
    same = [s for s in shared if all(by[s, "temporal_checked"][k] == by[s, "interlock"][k]
                                     for k in ("refunded_cents", "invariant_held", "answer_matches_stripe"))]
    differ = ", ".join(f"`{s}`" for s in shared if s not in same) or "none"
    ids = "\n".join(f"- `{c['scenario']}` / {c['mode']}: PaymentIntent `{c['payment_intent']}`, workflow `{c['workflow_id']}`, "
                    f"refunds {', '.join(f'`{r}`' for r in c['refund_ids']) or 'none'}, worker exit {c['crash']['worker_exit_code']}"
                    + (receipt_text(c["receipt"]) if c["receipt"] and c["receipt"]["verification"] else "")
                    for c in out["cells"])
    llm = "\n".join(f"- `{c['scenario']}` / {c['mode']}: {c['llm_decision']['amount_cents']} cents"
                    f"{'' if c['decision_matches_approval'] else ' (NOT the approved amount)'}, \"{c['llm_decision']['reason']}\""
                    for c in out["cells"])
    emulated = "\n\n".join(f"`{s}`: {sc['emulated']}" for s, sc in SCENARIOS.items() if sc["emulated"])
    return f"""# Results: refund agent, Temporal and Stripe, end to end with real crashes

Generated {out['generated']} by `experiments/e2e_live.py`. Model `{out['model']}`, temporalio {out['temporalio']},
Temporal's local dev server, Stripe test mode.

Each cell is one support case: a new $100 test card payment, one $20 refund approved by support (in the case
text, and as the approval's amount cap), a real LLM that reads the payment through a tool and decides the
refund, and a Temporal workflow that runs the decision on a worker process. Mid-refund, the worker kills itself
with SIGKILL. The harness then acts through the backend's HTTP API (a hand refund, a revocation, or nothing),
starts a new worker process, and lets Temporal's retry policy finish the case. Totals and refund counts are
Stripe's own refund list, re-read at the end. "Want" comes from the scenario and the approved $20, never from
the model's output. "Answer" is what the workflow itself reports (sent, refused, or AMBIGUOUS), checked against
the refunds carrying this case's own metadata.

| scenario | {' | '.join(COLUMNS[m] for m in MODES)} |
|---|---|---|---|
{rows}

Over the {len(shared)} rows every column ran ({len(real)} of them not emulated):

{tally}

Read the tally with this next to it: on {len(same)}/{len(shared)} of those rows the hand-written re-check left
Stripe with the same refunds, and gave the same answer, as Interlock (rows that differ: {differ}). Both beat the
column that re-checks nothing. So the difference from a careful Temporal activity is not the outcome in these
rows; it is that Interlock packages the re-check, the lookup after a crash and the claim once, instead of about
ten hand-written lines per activity, and adds AMBIGUOUS and a receipt. Interlock is also slower after every crash;
see "Timing" below. Not in the tally (run for Interlock only): {only or "none"}.

## Scenarios

""" + "\n".join(f"- `{s}`: {sc['text']}" for s, sc in SCENARIOS.items()) + f"""

## The three columns

- **Temporal, no re-check**: Temporal's retry policy, and a Stripe refund with Idempotency-Key = workflow run id +
  "/" + activity id (the key Temporal's docs suggest). The activity body re-checks nothing. This is "Temporal
  alone" as pitched, not the best a Temporal user can do.
- **Temporal plus a hand-written re-check**: the same, and at the top of the activity, in about ten lines: if a
  refund carrying this workflow's id is already in Stripe, report it (`FOUND_BY_LOOKUP`) and stop; otherwise the
  approval must be live and cover the amount, and the payment's refunds must be unchanged since the decision. A
  careful Temporal user can write this. The other documented Temporal route is a Signal (for example from the
  revocation, or from a Stripe `refund.created` webhook) that cancels the pending activity; this column does not
  use it. In this harness the retry cannot start until the new worker is up, so such a Signal would arrive first.
- **Interlock**: `interlock.temporal.gated()` as the activity body: a journaled intent before the send, a claim so
  no two workers send it at once, the lease and premises re-checked on the recovery path, a Stripe lookup when the
  key cannot be trusted, and a receipt recording what was checked.

## What the pitch can claim from this run

- "Temporal" should read "Temporal alone: an activity that does not re-read the world". Against that column,
  Interlock kept the hand refund during an outage from becoming a second $20 refund object, and kept a revoked
  approval from being used. A Temporal activity with the re-check above does the same; Interlock makes that
  re-check, and telling "my refund already landed" apart from "the world changed" after a crash, the default instead
  of something each activity author must remember.
- Within Stripe's key window, the idempotency key already answers "did it happen" and "may I retry": plain
  Temporal held `crash_after_commit`. What nothing checks without extra code is whether the refund is still
  allowed, whether the payment changed since the decision, and whether the key still exists after the window.
- Reproduced in Stripe test mode: the hand refund during an outage. Emulated, not reproduced: Stripe forgetting the
  key, by sending a key Stripe has never seen, because Stripe cannot be made to forget a key on demand.
- Interlock notices that the payment's refunds changed after the decision and stops for a person. It does not tell
  a duplicate from an unrelated refund, so it does not "recognize the same action arriving as a different request".
- The receipt is the gate's attestation: a hash-chained record, unsigned here, of what the gate observed. It is not
  proof; the evidence that a refund happened once is Stripe's refund list, re-read by `experiments/e2e_audit.py`.

## Timing

From the crash to the workflow closing, the median Interlock cell took {med('interlock'):.0f}s against
{med('temporal'):.0f}s and {med('temporal_checked'):.0f}s for the two Temporal columns. A SIGKILLed sender cannot release its
claim, so later attempts return IN_FLIGHT until the claim expires (`CLAIM_TTL` = 40s in `backend/config.py`, longer
than the Stripe client's 30s timeout so recovery never overlaps a send still in progress), and then one attempt
recovers. That wait is the price of never having two workers send the same effect at the same time; the Temporal
columns rely on Stripe's idempotency key for that, which holds only inside the key window.

## Limits of what this shows

- The premise is "the payment's refunds are what they were when the model decided". Interlock does not recognize a
  hand refund as the same action; it refuses because the refunds changed. `unrelated_refund_during_outage` shows
  the cost: a $5 goodwill refund also stops the approved $20, and a person has to re-approve. A hand refund made
  before the model decides is part of that premise, so it does not stop the refund (`hand_refund_before_decision`).
- The `after_commit` crash comes after Stripe's full response was received and parsed, before anything durable
  recorded it (the journal, or Temporal's history). The connection is never cut mid-response. Recovery sees the
  same state as a response lost in transit: Stripe has the refund, nothing on this side does. The outage rows crash
  before the send.
- Which recovery path an Interlock cell took is its receipt's `via` in the ids list below: `retry-idempotent` means
  it resent under the same key and Stripe replayed it; `recovery-query` means it asked Stripe. Outside the emulated
  rows, the lookup runs only when a re-check fails after a commit.
- AMBIGUOUS is produced end to end only in the emulated `no_lookup_after_24h` row, because Stripe can always be
  looked up.
- Receipts here are unsigned (verify reports signed=None), written by the same worker that sends. Each check the
  gate records carries what it read: the approval row (amount cap, revoked time) and the premise violations, where
  none means Stripe's refunds read back as recorded. Commits carry Stripe's refund id and whether Stripe replayed
  it, or the refund id a lookup found. A re-check that failed before a lookup found the refund is recorded too
  ("re-check at recovery" below). authorized_when_fired and assumptions_held are None when nothing fired.

## What is real

- Stripe: every payment, refund, lookup and idempotency replay is a real test-mode API call. No mock.
- LLM: every decision is a real Anthropic Messages API call; the model calls `get_payment` (a real Stripe
  read) and then `issue_refund`. Its output is validated before use, including against the approved amount.
  Temporal records the decision, so a retry does not ask the model again.
- Temporal: a real dev server, real workflow and activity retries, workers as separate OS processes. A refund
  activity that fails for any reason other than a refusal fails the workflow.
- Crashes: `os.kill(os.getpid(), SIGKILL)` in the worker, one-shot via a marker file. Exit code -9 is recorded per cell.
- Outage actions: a hand refund is a plain Stripe refund with no idempotency key and no metadata, as from
  the dashboard. A revocation updates the approval in SQLite, read by the worker process.

## What is emulated

Only the rows marked EMULATED. Nobody waited 24 hours.

{emulated}

## LLM decisions

{llm}

## Ids, for checking in the Stripe test dashboard

{ids}

## Re-run

    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python experiments/e2e_live.py
    python3 experiments/e2e_audit.py      # independent check of results/e2e_live.json against Stripe
"""


async def main():
    only = set(sys.argv[1:])
    async with await WorkflowEnvironment.start_local() as env:
        cells = await asyncio.to_thread(run, env.client.service_client.config.target_host, only)
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "model": next((c["llm_decision"]["model"] for c in cells if c["llm_decision"]["model"]), None),
           "temporalio": temporalio.__version__, "cells": cells}
    for c in cells:
        print(f"{c['scenario']:32} {c['mode']:17} {cell_text(c)}")
    if only:
        return
    with open(os.path.join(ROOT, "results", "e2e_live.json"), "w") as f:
        json.dump(out, f, indent=2)
    with open(os.path.join(ROOT, "results", "e2e_live.md"), "w") as f:
        f.write(markdown(out))


if __name__ == "__main__":
    asyncio.run(main())
