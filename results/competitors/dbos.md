# Competitor: DBOS Transact against Interlock, live

Generated 2026-09-14 00:40 UTC by `experiments/competitor_dbos.py`. DBOS Transact (Python) 2.31.1, MIT license. Postgres 17.11 (a
private instance, databases `dbos_competitor_sys` and `dbos_competitor_app`), Python 3.13.13, model
`claude-haiku-4-5-20251001` (every decision was 2000 cents), Stripe test mode. Full per-run data: `dbos.json`. Per-run
ids: `dbos.generated.md`.

Every cell is a new $100 test payment. A real model decides the refund: it reads the payment through a tool, and
then a person approves one $20 refund. The worker is a separate OS process. It parks at the crash point, and the
harness sends it a real SIGKILL (exit -9 recorded in every cell). The harness then acts during the outage and
restarts the worker at once. Ground truth is Stripe's refund list, read after the restarted worker exits. "Settle" is
the time from the harness seeing the SIGKILLed process exit to the restarted process exiting with its answer, process
start included.

## Results

| scenario | DBOS idiomatic (`dbos`) | DBOS plus a hand-written re-check in the step (`dbos_checked`) | Interlock (`interlock.easy`, claim TTL 40s) |
|---|---|---|---|
| 1. `crash_after_commit`: killed after Stripe's refund response arrived | **held 3/3**, REPLAYED_BY_STRIPE, $20 in 1, median settle **3.3s** | **held 3/3**, FOUND_BY_LOOKUP, $20 in 1, median **3.6s** | **held 3/3**, COMMITTED_BY_RETRY, $20 in 1, median **41.2s** |
| 2. `hand_refund_during_outage`: killed before the POST, support refunds the same $20 by hand | **VIOLATED 0/3**, REFUNDED, $40 in 2 every time, median 5.3s | **held 3/3**, REFUSED:stale_premise, $20 in 1, median **5.6s** | **held 3/3**, REFUSED:stale_premise_at_recovery, $20 in 1, median **42.2s** |
| 3. `approval_revoked_during_outage`: killed before the POST, Finance revokes (approval row marked revoked and `DBOSClient.cancel_workflow`) | **held 3/3**, CANCELLED, $0, median **2.9s** | not run (cancel stops the workflow before the check could run) | **held 3/3**, REFUSED:lease_at_recovery, $0, median **41.3s** |
| 3b. `approval_revoked_row_only`: the same, but the revocation lives only in Finance's approval row (nobody calls cancel) | **VIOLATED 0/3**, REFUNDED, $20 in 1, median 3.9s | **held 3/3**, REFUSED:approval_revoked, $0, median **4.0s** | not re-run: Interlock reads the same row, as in 3 |
| 4. `shared_cap`: two bots, one $30 cap, the first bot to reach the crash point is killed | **held 20/20** at `after_commit`, median **3.3s**; **held 20/20** at `before_send`, median **4.1s** (cap as a DBOS datasource transaction, `dbos_cap`) | n/a | not re-run here. The earlier run (`results/scenarios/shared_cap.md`, same design, 20 reps per crash point): unmodified Gate 25/40; with the CapJournal scenario subclass 40/40, median 40.1s / 41.7s |
| 5. `takeover_by_other_executor`: killed before the POST, and the process that comes up has a different executor_id | **held 3/3** only after a person called `DBOS.resume_workflow`: the workflow stayed PENDING with no refund for the whole 30s wait in 3/3, then refunded once. Median 33.9s, of which 30s is the scripted wait | n/a | not run. Every Interlock restart above is already a new process with a new owner id; recovery does not care which process takes over |

Every answer matched Stripe in every cell (33/33 single cells, 40/40 cap runs), including the violations: idiomatic
DBOS reported REFUNDED and Stripe did hold that refund, next to the hand refund.

In the 40 cap runs, the bot that reserved the cap was the one killed in all 20 `before_send` runs and all 20
`after_commit` runs. Its recovered workflow replayed the recorded reservation and sent the refund. The other bot
was refused over the cap each time, and the reservation table's `used` equalled Stripe's total in 40/40.

## Lines of user code

Non-blank, non-comment lines in the `USER CODE` sections of `experiments/competitor_dbos.py`. The harness's crash
hooks are excluded.

| arm | lines | what the lines are |
|---|---|---|
| `dbos` | 28 | decision step, refund step with the workflow id plus step id as the Idempotency-Key, workflow with `set_event` and `recv`, DBOS config and launch (4 shared send lines included; 2 datasource lines in the launch section are only used by `dbos_cap`) |
| `dbos_checked` | 38 | `dbos` plus 10 lines of re-check (lookup by workflow id, approval row, refunds unchanged since the decision) |
| `interlock` | 36 | 10 lines to persist the decision and wait for the approval (DBOS gives both for free as a step and `recv`), 22 lines of the `@gate.effect` decorator, lookup, approval check and recovery loop, 4 send lines |
| `dbos_cap` | 35 | two DDL statements, a conditional `UPDATE ... WHERE used + :a <= cap` in a datasource transaction, decision and refund steps, workflow, launch. No subclass of anything. The Interlock arm that held 40/40 needed the CapJournal scenario subclass (about 60 lines, `scenarios/shared_cap/cap.py`) |

## What DBOS does better than Interlock, measured

- **Recovery latency, by an order of magnitude.** Median settle of 2.9 to 5.6s against Interlock's 41.2 to 42.2s in
  the same harness on the same scenarios. The shared cap took 3.3s / 4.1s against the earlier Interlock CapJournal
  run's 40.1s / 41.7s. DBOS resumes at `DBOS.launch()` in a process restarted with the same executor_id and waits
  for no lease. Interlock waits out the dead sender's claim (40s here), because a claim cannot tell a dead sender
  from a slow one.
- **Revocation is a native operation.** `DBOSClient.cancel_workflow` during the outage left the workflow CANCELLED,
  and the restart did not resume it: 3/3 held, 2.9s median, zero re-check lines. DBOS's docs say cancellation
  preempts a running workflow "at the beginning of its next step".
- **The shared cap is in the product.** A datasource transaction records its output in the same database
  transaction, so the recovered workflow replayed the reservation instead of re-running it: 40/40 held, 35 lines, no
  framework extension. Interlock's core Gate held 25/40 on this scenario and needed a subclass to reach 40/40.
- **The decision and the approval are durable for free.** The model's decision is a recorded step (never re-asked
  on replay), and the approval is a recorded `recv`. Interlock's arm needed 10 extra lines to persist the decision
  and wait for the approval.
- **A strong fair arm is cheap.** DBOS plus a 10-line re-check tied Interlock on every outcome it ran (scenarios 1, 2
  and 3b, 9/9 held) and settled in 3.6 to 5.6s against 41 to 42s. This matches `results/e2e_live.md` and
  `docs/10-scenarios.md`: a fair hand-written check ties Interlock on outcomes.
- **Operations tooling.** `list_workflow_steps` gives every step's output with start and end times, and
  `cancel_workflow`, `resume_workflow` and `fork_workflow` are public APIs. Interlock has none of these.
- **Not measured here:** DBOS's state is Postgres, so workers on different hosts share it. Interlock's claim is
  atomic on one machine only (`docs/08-pitch.md`, Honest limits). No run on this page used more than one host.

## Where Interlock beats DBOS, measured

- **Idiomatic DBOS acts on stale facts.** Run as its docs describe, with a stable idempotency key and no re-check,
  DBOS refunded twice when support refunded by hand during the outage: $40 in 2, 3/3. It also refunded under a
  revoked approval whenever the revocation lived in the approval system instead of a `cancel_workflow` call: 3/3.
  Interlock held both with no extra code. This is a win against idiomatic DBOS only. DBOS plus the 10-line check
  held both, faster.
- **Takeover by a process with a different identity.** Self-hosted DBOS without Conductor recovers only the pending
  workflows of the restarting process's own executor_id. When a process with a different executor_id came up, the
  workflow stayed PENDING with no refund for 30s in 3/3, until someone called `DBOS.resume_workflow`. DBOS's docs
  put automatic recovery of a dead executor's workflows in Conductor, which by default waits 60 seconds after an
  executor disconnects. In Interlock, any process opening the journal recovers after the claim TTL; every Interlock
  restart in this run was a new owner.
- **What the record says.** DBOS keeps `workflow_status` (status, executor_id, recovery_attempts, timestamps) and
  one `operation_outputs` row per completed step. In scenario 2 the DBOS record reads SUCCESS, with `refund_step`
  output REFUNDED and a refund id, while Stripe held $40 against a wanted $20. Nothing in that record names the hand
  refund, a check, or the approval at send time. The killed first attempt of the step left no row at all, only
  `recovery_attempts: 2`. A CANCELLED workflow records no reason and no actor. Interlock's receipt for the same
  scenario is PROPOSED, AUTHORIZED, DISPATCHED (on disk before the crash), REFUSED. It carries the re-check
  `refunded_by_others: was 0, now 2000`, and `verify()` re-derives `happened: false` from the entries.
- **Tamper evidence, partly.** The DBOS system tables have no hash or signature column. Replacing a refund step's
  recorded output in `operation_outputs` with a forged one ("re_FORGED_BY_DB_WRITER", REFUSED) was returned by
  DBOS's own `list_workflow_steps` with no error in 21/21 tests. Interlock: editing one entry of a receipt made
  `verify()` fail in 9/9. But a writer who rebuilt the whole chain passed `verify()` unsigned in 9/9, and was caught
  only when the bundle had been signed with a key the writer did not hold (9/9 rejected). So Interlock's advantage
  over DBOS here is edit detection, plus forgery detection only when signed. The receipts in this run are unsigned,
  like every earlier run.

## Ties and shared gaps

- Neither system recognizes the hand refund as the same action. `dbos_checked` and Interlock both refuse because
  the refunded total changed, so an unrelated $5 refund would stop the approved $20 in both (shown for Interlock in
  `results/e2e_live.md`; not re-run here).
- Neither watches after the commit. A chargeback landing minutes after a successful refund is invisible to both;
  DBOS's record would say SUCCESS just as Interlock's receipt says `happened: true` (`results/scenarios/stripe_dispute.md`).
- Both rely on Stripe's idempotency key for the crash after commit: DBOS's step key replayed (REPLAYED_BY_STRIPE
  3/3), Interlock resent under its effect id (COMMITTED_BY_RETRY 3/3).

## Caveats found while running it

- **A recovered workflow can be picked up by another process of the same application.** DBOS recovery re-enqueues a
  pending workflow on an internal queue (`dbos/_recovery.py`, `_recover_workflow`). In the smoke run, two cap runs
  shared one application name and version. The restarted bot of one run ended up owned by a process of the other
  run (workflow `cap-f3a35f4025-support-bot`, executor `832f4ad381-support-bot`). That process exited after its own
  work, and the workflow stayed PENDING. Worker processes that exit are a harness choice, not how a DBOS service
  runs. The recorded run gives each cell its own application name and version, and keeps each cap bot process up
  until both of its run's workflows are terminal. In a long-running service that same queue handoff is what lets
  recovery spread across processes.
- **Step outputs are stored as base64 pickles** (`serialization = py_pickle` in `operation_outputs`), read back
  by every worker that replays the workflow. Anyone who can write the system database controls what workers
  deserialize. Observed in the table, not exploited.
- `@DBOS.transaction` is documented as the older option. This run used the recommended sync datasource
  (`SQLAlchemyDatasource.create(...).transaction`), SERIALIZABLE by default.

## The arms, precisely

- **dbos**: `@DBOS.workflow refund_case`: `decide_step` (a Claude call that reads Stripe, recorded), then
  `DBOS.set_event("decision")`, `DBOS.recv("approval")` sent by the approver with `DBOSClient.send`, then
  `refund_step`. That step POSTs the refund with `Idempotency-Key = DBOS.workflow_id + ":" + DBOS.step_id` (stable
  across replay) and metadata `dbos_workflow_id`. Each worker has its own `executor_id`, and the restart uses the
  same one. Revocation in scenario 3 is `cancel_workflow`.
- **dbos_checked**: the same, with the refund step first listing the payment's refunds. If one carries this
  workflow id it returns FOUND_BY_LOOKUP. Otherwise the approval row must be unrevoked and cover the amount, and
  the payment's refunded total must equal the one recorded at decision; if either fails it refuses, and if both
  pass it sends as above.
- **interlock**: `interlock.easy` in a plain process with no DBOS. The decision is saved to a file and the approval
  row is polled. The effect is keyed on the case, with premises = refunds by others, `allowed=` the approval row,
  `dedupes=True`, and a lookup by `interlock_effect_id` returning the refund id. The restart runs `gate.recover()`
  and polls until the claim (40s, above the Stripe client's 30s timeout) expires.
- **dbos_cap**: two bot processes (own executor_ids) start behind a barrier. Each workflow decides (Claude, $20 per
  ticket) and reserves in a datasource transaction (`UPDATE cap_budget SET used = used + :a WHERE case_id = :c AND
  used + :a <= cap RETURNING used`, plus a reservation row). If the reservation is granted it sends with the step
  key; if not, it returns REFUSED:over_cap.

## What is real, what is not

- Real: every Stripe payment, refund, list and idempotent replay; every Claude decision; every SIGKILL (a separate
  OS process, killed by pid from the harness, exit -9 in 33/33 single cells and 40/40 cap runs); DBOS 2.31.1 on
  Postgres 17 with fsync on.
- Scripted: the timing of the outage action (right after the kill), the approver (the harness sends the approval
  message and writes the approval row), and the 30s wait before `resume_workflow` in scenario 5.
- Not run: multiple hosts, Conductor, a restart delayed by minutes, an unrelated refund during the outage, a
  post-commit chargeback. Interlock was not re-run on scenario 4 or 3b (its prior shared_cap numbers are cited).

## Re-run

    # a Postgres 17 on port 55441 with databases dbos_competitor_sys and dbos_competitor_app, then:
    uv run --no-project --python 3.13 --with dbos==2.31.1 python experiments/competitor_dbos.py --reps 3 --cap-reps 20
    # writes results/competitors/dbos.json and dbos.generated.md; --no-write for a smoke run
