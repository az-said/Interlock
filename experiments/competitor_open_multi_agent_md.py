"""Renders results/competitors/open_multi_agent.md from the JSON written by competitor_open_multi_agent.py."""
import json, statistics

ARM_TEXT = {
    "oma": "OMA strongest documented setup: durable tool approval (suspend, decideApproval with requestHash, restore), "
           "FileStore checkpoint, JsonlRunJournal, MemoryStoreRunStore lease (default 60s TTL, heartbeat), "
           "Idempotency-Key runId:taskId:toolCallId; revocation = RunLedger.cancel(runId)",
    "oma_no_runstore": "the same without the run store (the docs' sequential-restart boundary); OMA then has no way to revoke a recorded decision",
    "oma_lease5s": "`oma` with `leaseTtlMs: 5000` (heartbeat every 1.67s)",
    "oma_recheck": "`oma` plus a hand-written re-check in the tool body: look up a refund carrying this call's key, and refuse if the "
                   "payment's refunded total differs from a snapshot the gate saved when it suspended",
    "oma_cap": "`oma` plus a cap reservation with compareAndSet on a shared bundled FileStore before the refund POST",
}
INTERLOCK = {   # measured earlier in this repo; cited, not re-run here
    "S1_crash_after_commit": "held, 44.0s crash to close (`results/e2e_live.md`, crash_after_commit, claim TTL 40s)",
    "S2_hand_refund_during_outage": "held, REFUSED:stale_premise_at_recovery, 43.6s (`results/e2e_live.md`); hand re-check column also held, 16.0s",
    "S3_approval_revoked_during_outage": "held, REFUSED:lease_at_recovery, 43.6s (`results/e2e_live.md`); hand re-check column also held, 16.0s",
    "S4_two_approvals_racing_30_cap": "with crashes: unmodified Gate 25/40, CapJournal subclass 40/40 at ~40s, hand flock 40/40 at 0.5 to 1.4s "
                                      "(`results/scenarios/shared_cap.md`); no no-crash race was run for Interlock",
}


def yn(b):
    return "held" if b else ("VIOLATED" if b is False else "n/a")


def render(r):
    cells = r["cells"]
    groups = {}
    for x in cells:
        groups.setdefault((x["scenario"], x["arm"]), []).append(x)

    def summary_row(key, xs):
        ran = [x for x in xs if x.get("status") == "RAN"]
        held = sum(bool(x["invariant_held"]) for x in ran)
        settle = [x["seconds_to_settle"] for x in ran if x.get("seconds_to_settle") is not None]
        return (f"| {key[0]} | {key[1]} | {held}/{len(ran)} held" + (f" ({len(xs) - len(ran)} NOT_RUN)" if len(xs) > len(ran) else "")
                + f" | {'; '.join(sorted({x['outcome'] for x in ran})) or 'NOT_RUN'} | "
                + f"{'; '.join(sorted({x['ground_truth'] for x in ran}))} | "
                + (f"{statistics.median(settle):.1f} ({min(settle):.1f} to {max(settle):.1f})" if settle else "") + " | "
                + f"{ran[0]['lines_of_user_code'] if ran else ''} | {INTERLOCK.get(key[0], '')} |")
    table = "\n".join(summary_row(k, v) for k, v in groups.items())

    def cell_line(x):
        if x.get("status") != "RAN":
            return f"- {x['scenario']} / {x['arm']} rep {x.get('rep')}: NOT_RUN, {x['outcome']}"
        procs = ", ".join(f"{p['mode']} pid {p['pid']} ({p['process']}) exit {p['exit']}" for p in x["processes"])
        extra = ""
        if x.get("final_result") and x["final_result"].get("leaseHeldRetries") is not None:
            extra += f"; resume retried on RUN_LEASE_HELD {x['final_result']['leaseHeldRetries']}x"
        if x.get("outage"):
            extra += f"; outage: {json.dumps(x['outage'])}"
        if "cap_reservations_succeeded" in x and x["arm"] == "oma_cap":
            extra += f"; cap reservations that succeeded: {x['cap_reservations_succeeded']}/2"
        return (f"- {x['scenario']} / {x['arm']} rep {x['rep']}: **{yn(x['invariant_held'])}**, {x['outcome']}, Stripe "
                f"{x['ground_truth']}, refunds {[f['id'] + ' ' + str(f['amount']) for f in x['refunds']]}, "
                f"PaymentIntent `{x['payment_intent']}`, {x['seconds_to_settle']}s; {procs}{extra}")
    ids = "\n".join(cell_line(x) for x in cells)

    probed = next((x for x in cells if x.get("record", {}) and x["record"].get("tamper")), None)
    tamper = ""
    if probed:
        tamper = "\n".join(f"| `{k}` | {json.dumps(v)} |" for k, v in probed["record"]["tamper"].items())
    records = []
    for x in cells:
        rec = x.get("record")
        if not rec:
            continue
        a = rec["approvals"][0] if rec.get("approvals") else {}
        runs = rec.get("runRecords") or []
        records.append(f"- {x['scenario']} / {x['arm']} rep {x['rep']}: approval row `{a.get('request_id')}` {a.get('decision')} by "
                       f"`{a.get('reviewer')}` for {json.dumps(a.get('input'))}, hash recomputes {a.get('hash_recomputes')}; run record "
                       f"{json.dumps([{k: v for k, v in rr.items() if k != 'key'} for rr in runs]) if runs else 'none'}; journal "
                       f"{rec['journal']['events']} events, tool/call issue_refund x"
                       f"{sum(1 for e in rec['journal']['toolEvents'] if e['type'] == 'tool/call' and e['detail'].get('name') == 'issue_refund')}, "
                       f"verifyRun ok={rec['verifyRun']['ok']} ({rec['verifyRun']['stats']})")
    records = "\n".join(records)
    uc = r.get("user_code", {})
    return f"""# Competitor: open-multi-agent

Generated {r['generated']} by `experiments/competitor_open_multi_agent.py`. `@open-multi-agent/core` {r['versions']['oma']}
(MIT), zod {r['versions']['zod']}, node {r['versions']['node']}, model `{r['model']}` through OMA's native Anthropic
adapter, Stripe test mode. Every crash is a SIGKILL the harness sends to a separate node process while it is blocked
at the crash point. Ground truth is Stripe's refund list for each PaymentIntent. Interlock was not re-run; its column
cites earlier measured results in this repo.

{READING}

## Results

| scenario | arm | invariant | outcome (run status : tool outcome) | Stripe | seconds crash to settled, median (range) | user lines | Interlock, cited |
|---|---|---|---|---|---|---|---|
{table}

Arms:
{chr(10).join(f'- `{k}`: {v}' for k, v in ARM_TEXT.items())}

Scenarios: S1 worker SIGKILLed right after Stripe's refund response, before the tool returns; S2 SIGKILLed right before
the refund POST, then a $20 hand refund (no key, no metadata) in Stripe; S3 SIGKILLed right before the POST, then the
approval is revoked; S4 two runs on one $100 payment, a support ticket and a billing ticket, each asks the model for $20,
each reviewer approves after checking Stripe against a $30 cap, then both restores are released from one barrier (no
crash). Invariants from Stripe: S1 exactly one $20 refund, S2 only the hand refund, S3 none, S4 total <= $30.
"Seconds to settle": S1 to S3 from the SIGKILL to the last restore process exiting (node start and the model's closing
turn included); S4 from the barrier to both processes exiting.

Lines of user code are counted from the worker, one per tagged line (`// @u:<tag>`), excluding the Stripe HTTP fixture,
crash points and printing: base {uc.get('base')} (tools, gate, reviewer call, orchestrator and restore wiring), run store
{uc.get('runstore')}, lease-held retry loop {uc.get('lease_retry')}, 5s lease {uc.get('lease5s')}, revocation via cancel
{uc.get('revoke')}, hand re-check {uc.get('recheck')}, cap reservation {uc.get('cap')}.

## What the records prove

Per cell, what OMA left in its store and journal (read back after the run):

{records}

Tamper probes, run on copies of one S1 `oma` cell's records (`getApprovalRecord` is OMA's reader of the primary approval
row; `verifyRun` is its journal verifier; `hash_recomputes` is this harness recomputing `hashApprovalRequest` over the
stored content):

| probe | result |
|---|---|
{tamper}

## Cells

{ids}

## Re-run

    python3 experiments/competitor_open_multi_agent.py --reps 2 --race-reps 5
    python3 experiments/competitor_open_multi_agent.py --md-only
"""


READING = """## Reading

Every number here is from the tables below, except the Interlock column, which cites earlier runs in this repo
(`results/e2e_live.md`, `results/scenarios/shared_cap.md`). Items marked "read from code" were not run. After the run,
all 24 PaymentIntents were re-read from Stripe with `interlock.targets.stripe_api.StripeClient`: 24/24 refund lists
matched the JSON.

**Outcomes.** OMA as its docs recommend held S1 in 6/6 cells across three configurations (Stripe replayed the
toolCallId key every time). It held S3 in 2/2 only with the run store, where the revocation is `RunLedger.cancel`. It
lost S2 in 2/2 (a second $20 refund on top of the hand refund, $40), S3 without the run store in 2/2 (it has no way to
revoke a recorded decision), and S4 in 5/5 ($40 against a $30 cap). Nine hand-written lines in the tool (a lookup by
key plus "refunded total unchanged since the gate suspended") held S2 in 2/2, which is the same hand re-check that
ties Interlock in `results/e2e_live.md`. A cap reservation with `compareAndSet` on the bundled `FileStore` held S4 in
only 2/5: in the 3 violated runs both processes' reservations succeeded, because `FileStore` has no cross-process lock
(its docs say so). A database `MemoryStore` with atomic compare-and-set would be needed; none is bundled and none was
run. On the three crash scenarios Interlock held all three (cited); OMA holds all three only with the run store, the
cancel call, and the hand re-check.

**Where OMA is better than Interlock.**

1. Recovery latency, measured, when configured for it. S1 settled in 1.4 and 1.5s without the run store and 5.4 and
   5.5s with `leaseTtlMs: 5000`, against Interlock's 44.0s (claim TTL 40s). With OMA's default 60s lease it was slower
   than Interlock: 60.7 and 60.9s, and S2 took 61 to 63s in both arms for the same reason. What makes a short lease
   defensible is the heartbeat: a live worker renews every TTL/3, so a slow but alive sender keeps its lease while a
   dead one loses it at TTL (read from `run/ledger.ts`; the slow-sender case was not run). Interlock's claim has no
   heartbeat, so its TTL must exceed the Stripe client timeout, which is the source of its 30 to 43s wait.
2. Revocation latency, measured. S3 with the run store settled in 1.6 and 1.8s: `cancel` drops the dead worker's lease
   and bumps the fencing token, and the next `restore` fails with `RUN_ALREADY_TERMINAL` before any tool runs.
   Interlock took 43.6s. The cost: `cancel` ends the whole run, not one approval, and the approval row still reads
   `approved`.
3. The approval is bound to exact reviewed content (read from code, `approval/durable.ts`; the stale-hash path was not
   exercised live). `requestHash` is SHA-256 over canonical JSON of the tool name, the model's raw input, the
   Zod-validated input, the agent, task and toolCallId. `decideApproval` must be given that hash
   (`APPROVAL_STALE_DECISION` otherwise), the first decision wins by compare-and-set (`APPROVAL_CONFLICT`), and
   `restore` re-validates the input and compares it with the reviewed content before the tool runs. Every cell's
   approval row names the reviewer, the exact input, and a hash that recomputes. Interlock's `Inbox.approve` in this
   checkout records the approver and the facts but has no reviewed-content hash. The escalation build
   (`Interlock-build/interlock/approvals.py`, `seen=` checked against the escalation hash) has the equivalent; whether it
   is on `main` is unverified.
4. A record of what the model saw. The journal hashes every block of every model request and `verifyRun` checks that
   each block is reproduced by the event it names. Editing the refund id in the model-visible message was caught
   (`MISSING_CONTEXT_REPLACE`), and the journal shows each execution attempt of the tool call (issue_refund
   `tool/call` x3 in the S1 cells: suspension, the killed attempt, the completed one). Interlock records the gate's
   checks, not the model's context.
5. The model is not asked again after a crash, with no extra code: `restore` continues the checkpointed conversation,
   and the Stripe key carried the same model-issued toolCallId in every process of a cell.

**Where Interlock is better than OMA.**

1. Facts re-checked at the moment of sending (S2). OMA sent a second $20 refund in 2/2; Interlock refused in the cited
   run. OMA ties only with hand-written lines in each tool.
2. Revoking an approval. OMA has no revocation of a recorded decision (docs, durable-approvals "Explicit limits"): 2/2
   violated without the run store. With it, revocation is a run-wide `cancel` sent by an operator, not a lease the
   send is checked against.
3. Record integrity. The OMA journal has no hash chain and nothing is signed. On copies of an S1 record, `verifyRun`
   accepted: the last 4 events dropped, the `tool/result` holding the refund id deleted with the sequence links
   rewritten, the refund id edited in `tool/result` only, and the refund id edited everywhere with the block hashes
   recomputed. `getApprovalRecord` accepted a changed reviewer id, a decision flipped to `rejected` after the refund ran,
   and a changed amount once the hash, the id derived from it, and the row key were recomputed. It rejected an amount
   edited without that recomputation. Interlock's unsigned chain rejects a single altered entry but also accepted
   recomputed forgeries (6/6 in `results/scenarios/github_merge.md`). It does have an HMAC signing path
   (`receipts.sign`); OMA holds no key material. Neither is tamper-evident against whoever controls storage unless
   Interlock's receipts are signed with a key the writer does not hold.
4. Not run, read from docs and code: past Stripe's 24h key window OMA has only the key (Interlock falls back to a
   lookup, emulated in `results/e2e_live.md`). A tool call with no commit record is re-run "conservatively", so a target
   with no dedup and no lookup gets at-least-once; Interlock answers AMBIGUOUS there. Neither watches after the commit
   (the chargeback-after-refund gap in `results/scenarios/stripe_dispute.md`).

**Ties and limits.** Shared cap: neither core holds it. OMA's bundled store held 2/5 here (no crash); Interlock's
unmodified Gate held 25/40 with crashes, and its 40/40 needed a scenario subclass. A hand `flock` held 40/40 in 0.5 to
1.4s. These runs differ in design, so no winner is claimed. One to five repetitions per cell; S1 to S3 use a $100
`pm_card_visa` payment and a $20 approval, the same shape as `results/e2e_live.md`, but a different agent framework
and harness, so the Interlock times are comparable in kind, not cell for cell."""
