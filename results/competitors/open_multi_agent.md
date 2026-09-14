# Competitor: open-multi-agent

Generated 2026-09-14 00:38 UTC by `experiments/competitor_open_multi_agent.py`. `@open-multi-agent/core` 1.19.0
(MIT), zod 3.25.76, node v26.0.0, model `claude-haiku-4-5-20251001` through OMA's native Anthropic
adapter, Stripe test mode. Every crash is a SIGKILL the harness sends to a separate node process while it is blocked
at the crash point. Ground truth is Stripe's refund list for each PaymentIntent. Interlock was not re-run; its column
cites earlier measured results in this repo.

## Reading

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
and harness, so the Interlock times are comparable in kind, not cell for cell.

## Results

| scenario | arm | invariant | outcome (run status : tool outcome) | Stripe | seconds crash to settled, median (range) | user lines | Interlock, cited |
|---|---|---|---|---|---|---|---|
| S1_crash_after_commit | oma | 2/2 held | ok:REPLAYED_BY_STRIPE | 1 refund(s), $20.00 (want 1, $20.00) | 60.8 (60.7 to 60.9) | 47 | held, 44.0s crash to close (`results/e2e_live.md`, crash_after_commit, claim TTL 40s) |
| S1_crash_after_commit | oma_no_runstore | 2/2 held | ok:REPLAYED_BY_STRIPE | 1 refund(s), $20.00 (want 1, $20.00) | 1.4 (1.4 to 1.5) | 41 | held, 44.0s crash to close (`results/e2e_live.md`, crash_after_commit, claim TTL 40s) |
| S1_crash_after_commit | oma_lease5s | 2/2 held | ok:REPLAYED_BY_STRIPE | 1 refund(s), $20.00 (want 1, $20.00) | 5.5 (5.4 to 5.5) | 48 | held, 44.0s crash to close (`results/e2e_live.md`, crash_after_commit, claim TTL 40s) |
| S2_hand_refund_during_outage | oma | 0/2 held | ok:REFUNDED | 2 refund(s), $40.00 (want 1, $20.00) | 62.6 (62.5 to 62.7) | 47 | held, REFUSED:stale_premise_at_recovery, 43.6s (`results/e2e_live.md`); hand re-check column also held, 16.0s |
| S2_hand_refund_during_outage | oma_recheck | 2/2 held | ok:REFUSED:stale_premise | 1 refund(s), $20.00 (want 1, $20.00) | 61.7 (61.2 to 62.1) | 56 | held, REFUSED:stale_premise_at_recovery, 43.6s (`results/e2e_live.md`); hand re-check column also held, 16.0s |
| S3_approval_revoked_during_outage | oma | 2/2 held | ERROR:RUN_ALREADY_TERMINAL | 0 refund(s), $0.00 (want 0, $0.00) | 1.7 (1.6 to 1.8) | 49 | held, REFUSED:lease_at_recovery, 43.6s (`results/e2e_live.md`); hand re-check column also held, 16.0s |
| S3_approval_revoked_during_outage | oma_no_runstore | 0/2 held | ok:REFUNDED | 1 refund(s), $20.00 (want 0, $0.00) | 4.1 (3.8 to 4.4) | 41 | held, REFUSED:lease_at_recovery, 43.6s (`results/e2e_live.md`); hand re-check column also held, 16.0s |
| S4_two_approvals_racing_30_cap | oma | 0/5 held | ok:REFUNDED / ok:REFUNDED | 2 refund(s), $40.00 (cap $30.00) | 3.4 (3.3 to 4.1) | 47 | with crashes: unmodified Gate 25/40, CapJournal subclass 40/40 at ~40s, hand flock 40/40 at 0.5 to 1.4s (`results/scenarios/shared_cap.md`); no no-crash race was run for Interlock |
| S4_two_approvals_racing_30_cap | oma_cap | 2/5 held | ok:REFUNDED / ok:REFUNDED; ok:REFUNDED / ok:REFUSED:over_cap; ok:REFUSED:over_cap / ok:REFUNDED | 1 refund(s), $20.00 (cap $30.00); 2 refund(s), $40.00 (cap $30.00) | 3.2 (2.3 to 3.5) | 56 | with crashes: unmodified Gate 25/40, CapJournal subclass 40/40 at ~40s, hand flock 40/40 at 0.5 to 1.4s (`results/scenarios/shared_cap.md`); no no-crash race was run for Interlock |

Arms:
- `oma`: OMA strongest documented setup: durable tool approval (suspend, decideApproval with requestHash, restore), FileStore checkpoint, JsonlRunJournal, MemoryStoreRunStore lease (default 60s TTL, heartbeat), Idempotency-Key runId:taskId:toolCallId; revocation = RunLedger.cancel(runId)
- `oma_no_runstore`: the same without the run store (the docs' sequential-restart boundary); OMA then has no way to revoke a recorded decision
- `oma_lease5s`: `oma` with `leaseTtlMs: 5000` (heartbeat every 1.67s)
- `oma_recheck`: `oma` plus a hand-written re-check in the tool body: look up a refund carrying this call's key, and refuse if the payment's refunded total differs from a snapshot the gate saved when it suspended
- `oma_cap`: `oma` plus a cap reservation with compareAndSet on a shared bundled FileStore before the refund POST

Scenarios: S1 worker SIGKILLed right after Stripe's refund response, before the tool returns; S2 SIGKILLed right before
the refund POST, then a $20 hand refund (no key, no metadata) in Stripe; S3 SIGKILLed right before the POST, then the
approval is revoked; S4 two runs on one $100 payment, a support ticket and a billing ticket, each asks the model for $20,
each reviewer approves after checking Stripe against a $30 cap, then both restores are released from one barrier (no
crash). Invariants from Stripe: S1 exactly one $20 refund, S2 only the hand refund, S3 none, S4 total <= $30.
"Seconds to settle": S1 to S3 from the SIGKILL to the last restore process exiting (node start and the model's closing
turn included); S4 from the barrier to both processes exiting.

Lines of user code are counted from the worker, one per tagged line (`// @u:<tag>`), excluding the Stripe HTTP fixture,
crash points and printing: base 41 (tools, gate, reviewer call, orchestrator and restore wiring), run store
1, lease-held retry loop 5, 5s lease 1, revocation via cancel
2, hand re-check 9, cap reservation 9.

## What the records prove

Per cell, what OMA left in its store and journal (read back after the run):

- S1_crash_after_commit / oma rep 1: approval row `apr_020aad825a8845e594d280a2a491a4dc` approved by `support-lead-7` for {"payment_intent": "pi_3UFNkd88KhIqqdFL1FRIybCd", "amount_cents": 2000, "reason": "Partial refund for cracked jar - customer keeps blender"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 12})
- S1_crash_after_commit / oma rep 2: approval row `apr_7d4b450f1eb9195e3344d888009181ec` approved by `support-lead-7` for {"payment_intent": "pi_3UFNlj88KhIqqdFL16ZXy9Af", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender; customer keeps the item"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 10})
- S1_crash_after_commit / oma_no_runstore rep 1: approval row `apr_56ab693c65c4accf2888ac86c7e1b483` approved by `support-lead-7` for {"payment_intent": "pi_3UFNmr88KhIqqdFL1gh5Xq3g", "amount_cents": 2000, "reason": "Partial refund for cracked jar on $100 blender - customer keeping blender"}, hash recomputes True; run record none; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 10})
- S1_crash_after_commit / oma_no_runstore rep 2: approval row `apr_0b65e7bc0e4292b7fba63364ead9d2ab` approved by `support-lead-7` for {"payment_intent": "pi_3UFNmz88KhIqqdFL0dcpYrb0", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender; customer retains product"}, hash recomputes True; run record none; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 10})
- S1_crash_after_commit / oma_lease5s rep 1: approval row `apr_25d82f05c11b4e84b312b9fe6567c080` approved by `support-lead-7` for {"payment_intent": "pi_3UFNn788KhIqqdFL11W7SLLu", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender; customer retains product"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 12})
- S1_crash_after_commit / oma_lease5s rep 2: approval row `apr_ef3efa7a7927a3beb6e5c228398625a9` approved by `support-lead-7` for {"payment_intent": "pi_3UFNnJ88KhIqqdFL12ddasEN", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender - customer retains item"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 12})
- S2_hand_refund_during_outage / oma rep 1: approval row `apr_eac9bd6018255ab9c6cfff57932aa36e` approved by `support-lead-7` for {"payment_intent": "pi_3UFNnW88KhIqqdFL1SiYtOaX", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender - customer keeps blender"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 43 events, tool/call issue_refund x2, verifyRun ok=True ({'events': 43, 'requests': 3, 'blocksChecked': 10})
- S2_hand_refund_during_outage / oma rep 2: approval row `apr_92b6aa98fa84d68f1fc7296ce2e46f89` approved by `support-lead-7` for {"payment_intent": "pi_3UFNoc88KhIqqdFL1Ay25pIp", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender; customer retains product"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 43 events, tool/call issue_refund x2, verifyRun ok=True ({'events': 43, 'requests': 3, 'blocksChecked': 10})
- S2_hand_refund_during_outage / oma_recheck rep 1: approval row `apr_b779f5582160924014c381fe07966cfe` approved by `support-lead-7` for {"payment_intent": "pi_3UFNpi88KhIqqdFL0Ta15ZP5", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender; customer keeps product"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 10})
- S2_hand_refund_during_outage / oma_recheck rep 2: approval row `apr_cf49e782b2d166f16c1a9132e82cc368` approved by `support-lead-7` for {"payment_intent": "pi_3UFNqq88KhIqqdFL009V6T0R", "amount_cents": 2000, "reason": "Partial refund for cracked blender jar; customer retains blender"}, hash recomputes True; run record [{"status": "completed", "attempt": 2, "fencingToken": 3, "outcome": {"code": "ok"}}]; journal 48 events, tool/call issue_refund x3, verifyRun ok=True ({'events': 48, 'requests': 3, 'blocksChecked': 12})
- S3_approval_revoked_during_outage / oma rep 1: approval row `apr_1116876bf6ebaa91ee7ab355f8cc3006` approved by `support-lead-7` for {"payment_intent": "pi_3UFNry88KhIqqdFL1RuIuOtj", "amount_cents": 2000, "reason": "Partial refund for cracked blender jar; customer retains blender"}, hash recomputes True; run record [{"status": "cancelled", "attempt": 1, "fencingToken": 3, "outcome": {"code": "cancelled", "message": "approval revoked during outage"}}]; journal 25 events, tool/call issue_refund x1, verifyRun ok=True ({'events': 25, 'requests': 2, 'blocksChecked': 4})
- S3_approval_revoked_during_outage / oma rep 2: approval row `apr_0001d6b9da9b2eb692bbf45d4af91ef9` approved by `support-lead-7` for {"payment_intent": "pi_3UFNs888KhIqqdFL0PbAxjuu", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender - customer retains item"}, hash recomputes True; run record [{"status": "cancelled", "attempt": 1, "fencingToken": 3, "outcome": {"code": "cancelled", "message": "approval revoked during outage"}}]; journal 18 events, tool/call issue_refund x1, verifyRun ok=True ({'events': 18, 'requests': 1, 'blocksChecked': 1})
- S3_approval_revoked_during_outage / oma_no_runstore rep 1: approval row `apr_7ef321f77b54a679acbea94e99b008b8` approved by `support-lead-7` for {"payment_intent": "pi_3UFNsH88KhIqqdFL10NDcxra", "amount_cents": 2000, "reason": "Partial refund for cracked blender jar; customer retains blender"}, hash recomputes True; run record none; journal 43 events, tool/call issue_refund x2, verifyRun ok=True ({'events': 43, 'requests': 3, 'blocksChecked': 10})
- S3_approval_revoked_during_outage / oma_no_runstore rep 2: approval row `apr_f341b80fd4ef4c95d5625dfc34d63847` approved by `support-lead-7` for {"payment_intent": "pi_3UFNsY88KhIqqdFL1yvfllup", "amount_cents": 2000, "reason": "Partial refund for cracked jar on blender; customer keeps the blender"}, hash recomputes True; run record none; journal 43 events, tool/call issue_refund x2, verifyRun ok=True ({'events': 43, 'requests': 3, 'blocksChecked': 10})

Tamper probes, run on copies of one S1 `oma` cell's records (`getApprovalRecord` is OMA's reader of the primary approval
row; `verifyRun` is its journal verifier; `hash_recomputes` is this harness recomputing `hashApprovalRequest` over the
stored content):

| probe | result |
|---|---|
| `approval_amount_edited` | {"getApprovalRecord": "rejected:APPROVAL_INTEGRITY_ERROR", "hash_recomputes": false} |
| `approval_amount_edited_hash_recomputed` | {"getApprovalRecord": "rejected:APPROVAL_INTEGRITY_ERROR", "hash_recomputes": true} |
| `approval_amount_edited_hash_id_key_recomputed` | {"getApprovalRecord": "accepted", "hash_recomputes": true} |
| `reviewer_id_edited` | {"getApprovalRecord": "accepted", "hash_recomputes": true} |
| `decision_flipped_to_rejected` | {"getApprovalRecord": "accepted", "hash_recomputes": true} |
| `journal_refund_id_edited_in_tool_result_only` | {"ok": true, "failures": []} |
| `journal_refund_id_edited_everywhere` | {"ok": false, "failures": ["MISSING_CONTEXT_REPLACE"]} |
| `journal_refund_id_edited_everywhere_hashes_recomputed` | {"ok": true, "failures": []} |
| `journal_tail_dropped` | {"ok": true, "failures": []} |
| `journal_uncited_event_deleted_and_renumbered` | {"ok": true, "failures": []} |
| `journal_tool_result_deleted_and_renumbered_links_rewritten` | {"ok": true, "failures": []} |
| `journal_event_deleted_and_renumbered` | {"ok": false, "failures": ["BROKEN_LINK", "MISSING_CONTEXT_REPLACE"]} |

## Cells

- S1_crash_after_commit / oma rep 1: **held**, ok:REPLAYED_BY_STRIPE, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNkd88KhIqqdFL1r8M1l45 2000'], PaymentIntent `pi_3UFNkd88KhIqqdFL1FRIybCd`, 60.7s; start pid 26751 (node) exit 0, decide pid 26830 (node) exit 0, resume pid 26831 (node) exit -9, resume pid 26843 (node) exit 0; resume retried on RUN_LEASE_HELD 59x
- S1_crash_after_commit / oma rep 2: **held**, ok:REPLAYED_BY_STRIPE, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNlj88KhIqqdFL1JKetT70 2000'], PaymentIntent `pi_3UFNlj88KhIqqdFL16ZXy9Af`, 60.9s; start pid 28416 (node) exit 0, decide pid 28467 (node) exit 0, resume pid 28480 (node) exit -9, resume pid 28489 (node) exit 0; resume retried on RUN_LEASE_HELD 59x
- S1_crash_after_commit / oma_no_runstore rep 1: **held**, ok:REPLAYED_BY_STRIPE, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNmr88KhIqqdFL1sLTZgEG 2000'], PaymentIntent `pi_3UFNmr88KhIqqdFL1gh5Xq3g`, 1.5s; start pid 29615 (node) exit 0, decide pid 29637 (node) exit 0, resume pid 29638 (node) exit -9, resume pid 29647 (node) exit 0; resume retried on RUN_LEASE_HELD 0x
- S1_crash_after_commit / oma_no_runstore rep 2: **held**, ok:REPLAYED_BY_STRIPE, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNmz88KhIqqdFL08x8UcMX 2000'], PaymentIntent `pi_3UFNmz88KhIqqdFL0dcpYrb0`, 1.4s; start pid 29666 (node) exit 0, decide pid 29790 (node) exit 0, resume pid 29791 (node) exit -9, resume pid 29794 (node) exit 0; resume retried on RUN_LEASE_HELD 0x
- S1_crash_after_commit / oma_lease5s rep 1: **held**, ok:REPLAYED_BY_STRIPE, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNn788KhIqqdFL1FLxJH2C 2000'], PaymentIntent `pi_3UFNn788KhIqqdFL11W7SLLu`, 5.4s; start pid 29844 (node) exit 0, decide pid 29857 (node) exit 0, resume pid 29858 (node) exit -9, resume pid 29863 (node) exit 0; resume retried on RUN_LEASE_HELD 4x
- S1_crash_after_commit / oma_lease5s rep 2: **held**, ok:REPLAYED_BY_STRIPE, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNnJ88KhIqqdFL1wxjQBiA 2000'], PaymentIntent `pi_3UFNnJ88KhIqqdFL12ddasEN`, 5.5s; start pid 29918 (node) exit 0, decide pid 29948 (node) exit 0, resume pid 29949 (node) exit -9, resume pid 29993 (node) exit 0; resume retried on RUN_LEASE_HELD 4x
- S2_hand_refund_during_outage / oma rep 1: **VIOLATED**, ok:REFUNDED, Stripe 2 refund(s), $40.00 (want 1, $20.00), refunds ['re_3UFNnW88KhIqqdFL1BD3GAPw 2000', 're_3UFNnW88KhIqqdFL16EnXZPs 2000'], PaymentIntent `pi_3UFNnW88KhIqqdFL1SiYtOaX`, 62.5s; start pid 30056 (node) exit 0, decide pid 30145 (node) exit 0, resume pid 30149 (node) exit -9, resume pid 30164 (node) exit 0; resume retried on RUN_LEASE_HELD 59x; outage: {"hand_refund": "re_3UFNnW88KhIqqdFL16EnXZPs"}
- S2_hand_refund_during_outage / oma rep 2: **VIOLATED**, ok:REFUNDED, Stripe 2 refund(s), $40.00 (want 1, $20.00), refunds ['re_3UFNoc88KhIqqdFL1HSP5l50 2000', 're_3UFNoc88KhIqqdFL1o7yQ8Y8 2000'], PaymentIntent `pi_3UFNoc88KhIqqdFL1Ay25pIp`, 62.7s; start pid 31794 (node) exit 0, decide pid 31884 (node) exit 0, resume pid 31886 (node) exit -9, resume pid 31905 (node) exit 0; resume retried on RUN_LEASE_HELD 59x; outage: {"hand_refund": "re_3UFNoc88KhIqqdFL1o7yQ8Y8"}
- S2_hand_refund_during_outage / oma_recheck rep 1: **held**, ok:REFUSED:stale_premise, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNpi88KhIqqdFL0L7lC4tQ 2000'], PaymentIntent `pi_3UFNpi88KhIqqdFL0Ta15ZP5`, 62.1s; start pid 33668 (node) exit 0, decide pid 33755 (node) exit 0, resume pid 33761 (node) exit -9, resume pid 33866 (node) exit 0; resume retried on RUN_LEASE_HELD 59x; outage: {"hand_refund": "re_3UFNpi88KhIqqdFL0L7lC4tQ"}
- S2_hand_refund_during_outage / oma_recheck rep 2: **held**, ok:REFUSED:stale_premise, Stripe 1 refund(s), $20.00 (want 1, $20.00), refunds ['re_3UFNqq88KhIqqdFL0OXJVFFO 2000'], PaymentIntent `pi_3UFNqq88KhIqqdFL009V6T0R`, 61.2s; start pid 34952 (node) exit 0, decide pid 35036 (node) exit 0, resume pid 35038 (node) exit -9, resume pid 35105 (node) exit 0; resume retried on RUN_LEASE_HELD 58x; outage: {"hand_refund": "re_3UFNqq88KhIqqdFL0OXJVFFO"}
- S3_approval_revoked_during_outage / oma rep 1: **held**, ERROR:RUN_ALREADY_TERMINAL, Stripe 0 refund(s), $0.00 (want 0, $0.00), refunds [], PaymentIntent `pi_3UFNry88KhIqqdFL1RuIuOtj`, 1.6s; start pid 37639 (node) exit 0, decide pid 37748 (node) exit 0, resume pid 37756 (node) exit -9, resume pid 37775 (node) exit 0; resume retried on RUN_LEASE_HELD 0x; outage: {"revoked": "RunLedger.cancel", "exit": 0, "record": {"status": "cancelled", "fencingToken": 3, "outcome": {"code": "cancelled", "message": "approval revoked during outage"}}, "pid": 37766}
- S3_approval_revoked_during_outage / oma rep 2: **held**, ERROR:RUN_ALREADY_TERMINAL, Stripe 0 refund(s), $0.00 (want 0, $0.00), refunds [], PaymentIntent `pi_3UFNs888KhIqqdFL0PbAxjuu`, 1.8s; start pid 37847 (node) exit 0, decide pid 38031 (node) exit 0, resume pid 38041 (node) exit -9, resume pid 38097 (node) exit 0; resume retried on RUN_LEASE_HELD 0x; outage: {"revoked": "RunLedger.cancel", "exit": 0, "record": {"status": "cancelled", "fencingToken": 3, "outcome": {"code": "cancelled", "message": "approval revoked during outage"}}, "pid": 38047}
- S3_approval_revoked_during_outage / oma_no_runstore rep 1: **VIOLATED**, ok:REFUNDED, Stripe 1 refund(s), $20.00 (want 0, $0.00), refunds ['re_3UFNsH88KhIqqdFL1OqrQAs9 2000'], PaymentIntent `pi_3UFNsH88KhIqqdFL10NDcxra`, 4.4s; start pid 38276 (node) exit 0, decide pid 38430 (node) exit 0, resume pid 38453 (node) exit -9, resume pid 38538 (node) exit 0; resume retried on RUN_LEASE_HELD 0x; outage: {"revoked": "application record only (OMA: no revocation of a recorded decision)"}
- S3_approval_revoked_during_outage / oma_no_runstore rep 2: **VIOLATED**, ok:REFUNDED, Stripe 1 refund(s), $20.00 (want 0, $0.00), refunds ['re_3UFNsY88KhIqqdFL1ez2l1iC 2000'], PaymentIntent `pi_3UFNsY88KhIqqdFL1yvfllup`, 3.8s; start pid 38948 (node) exit 0, decide pid 39035 (node) exit 0, resume pid 39053 (node) exit -9, resume pid 39066 (node) exit 0; resume retried on RUN_LEASE_HELD 0x; outage: {"revoked": "application record only (OMA: no revocation of a recorded decision)"}
- S4_two_approvals_racing_30_cap / oma rep 1: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNsk88KhIqqdFL0IcpTb7N 2000', 're_3UFNsk88KhIqqdFL0UHv07yF 2000'], PaymentIntent `pi_3UFNsk88KhIqqdFL0uI8a0d4`, 3.4s; start pid 39390 (node) exit 0, start pid 39391 (node) exit 0, resume pid 39630 (node) exit 0, resume pid 39631 (node) exit 0
- S4_two_approvals_racing_30_cap / oma rep 2: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNsx88KhIqqdFL0lZVhWJp 2000', 're_3UFNsx88KhIqqdFL0Lvpf9px 2000'], PaymentIntent `pi_3UFNsx88KhIqqdFL0R52lLbE`, 3.4s; start pid 39881 (node) exit 0, start pid 39882 (node) exit 0, resume pid 40039 (node) exit 0, resume pid 40040 (node) exit 0
- S4_two_approvals_racing_30_cap / oma rep 3: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNt888KhIqqdFL1QUR5PHq 2000', 're_3UFNt888KhIqqdFL14W2maXC 2000'], PaymentIntent `pi_3UFNt888KhIqqdFL1XQ1VNdE`, 3.5s; start pid 40274 (node) exit 0, start pid 40275 (node) exit 0, resume pid 40492 (node) exit 0, resume pid 40493 (node) exit 0
- S4_two_approvals_racing_30_cap / oma rep 4: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNtL88KhIqqdFL1WLvvxXC 2000', 're_3UFNtL88KhIqqdFL1K709h2p 2000'], PaymentIntent `pi_3UFNtL88KhIqqdFL1YJ2vzN4`, 3.3s; start pid 40702 (node) exit 0, start pid 40703 (node) exit 0, resume pid 40887 (node) exit 0, resume pid 40888 (node) exit 0
- S4_two_approvals_racing_30_cap / oma rep 5: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNtZ88KhIqqdFL1u1JX3mu 2000', 're_3UFNtZ88KhIqqdFL16MwOUer 2000'], PaymentIntent `pi_3UFNtZ88KhIqqdFL12warcdi`, 4.1s; start pid 41222 (node) exit 0, start pid 41221 (node) exit 0, resume pid 41392 (node) exit 0, resume pid 41391 (node) exit 0
- S4_two_approvals_racing_30_cap / oma_cap rep 1: **held**, ok:REFUNDED / ok:REFUSED:over_cap, Stripe 1 refund(s), $20.00 (cap $30.00), refunds ['re_3UFNtm88KhIqqdFL1HOTH2Do 2000'], PaymentIntent `pi_3UFNtm88KhIqqdFL1nLxWAjh`, 2.3s; start pid 41656 (node) exit 0, start pid 41657 (node) exit 0, resume pid 41725 (node) exit 0, resume pid 41726 (node) exit 0; cap reservations that succeeded: 1/2
- S4_two_approvals_racing_30_cap / oma_cap rep 2: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNty88KhIqqdFL1P1GSy62 2000', 're_3UFNty88KhIqqdFL15O4lEmP 2000'], PaymentIntent `pi_3UFNty88KhIqqdFL1Uly8w86`, 3.2s; start pid 41790 (node) exit 0, start pid 41791 (node) exit 0, resume pid 41850 (node) exit 0, resume pid 41851 (node) exit 0; cap reservations that succeeded: 2/2
- S4_two_approvals_racing_30_cap / oma_cap rep 3: **held**, ok:REFUSED:over_cap / ok:REFUNDED, Stripe 1 refund(s), $20.00 (cap $30.00), refunds ['re_3UFNuB88KhIqqdFL1pDyz0bR 2000'], PaymentIntent `pi_3UFNuB88KhIqqdFL1272yAj4`, 2.5s; start pid 41964 (node) exit 0, start pid 41965 (node) exit 0, resume pid 42170 (node) exit 0, resume pid 42172 (node) exit 0; cap reservations that succeeded: 1/2
- S4_two_approvals_racing_30_cap / oma_cap rep 4: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNuO88KhIqqdFL1NQuzxEk 2000', 're_3UFNuO88KhIqqdFL1DKVqvIk 2000'], PaymentIntent `pi_3UFNuO88KhIqqdFL16Eq3Rbd`, 3.5s; start pid 42239 (node) exit 0, start pid 42238 (node) exit 0, resume pid 42395 (node) exit 0, resume pid 42396 (node) exit 0; cap reservations that succeeded: 2/2
- S4_two_approvals_racing_30_cap / oma_cap rep 5: **VIOLATED**, ok:REFUNDED / ok:REFUNDED, Stripe 2 refund(s), $40.00 (cap $30.00), refunds ['re_3UFNub88KhIqqdFL11drujvu 2000', 're_3UFNub88KhIqqdFL17xpk6tN 2000'], PaymentIntent `pi_3UFNub88KhIqqdFL1SagOyi3`, 3.5s; start pid 42563 (node) exit 0, start pid 42564 (node) exit 0, resume pid 42853 (node) exit 0, resume pid 42852 (node) exit 0; cap reservations that succeeded: 2/2

## Re-run

    python3 experiments/competitor_open_multi_agent.py --reps 2 --race-reps 5
    python3 experiments/competitor_open_multi_agent.py --md-only
