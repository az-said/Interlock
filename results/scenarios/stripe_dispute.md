# Scenario: stripe_dispute

Generated 2026-09-13 22:51 UTC by `experiments/scenario_stripe_dispute.py`. Status: **RAN**. Stripe test mode,
model `claude-haiku-4-5-20251001`, every crash a real SIGKILL of the worker process. Nothing emulated.

A $100 payment; the customer's bank opens an inquiry; support approves a $20 goodwill refund and the model decides
it; the worker dies; during the outage the bank escalates the inquiry to a chargeback; the worker restarts.
Invariant: no refund is issued on the charge once it is charged back, and a refund sent before the chargeback was
issued exactly once. Ground truth is Stripe's refund list (every status, re-read 60s after
the last cell) and the dispute's balance transaction.

| fault | no_check | hand_check | interlock |
|---|---|---|---|
| `crash_before_send_chargeback_during_outage` | STRIPE_ERROR; 0 refund object(s) (final: none), want 0; created at or after the chargeback: none; money returned: no; dispute needs_response; **held**; answer vs refund objects: matches; answer vs final money: matches; 6.8s; proof no (checks no, outcome no, tamper-evident no) | REFUSED:charged_back; 0 refund object(s) (final: none), want 0; created at or after the chargeback: none; money returned: no; dispute needs_response; **held**; answer vs refund objects: matches; answer vs final money: matches; 6.4s; proof yes (checks yes, outcome yes, tamper-evident no) | REFUSED:stale_premise_at_recovery; 0 refund object(s) (final: none), want 0; created at or after the chargeback: none; money returned: no; dispute needs_response; **held**; answer vs refund objects: matches; answer vs final money: matches; 42.4s; proof yes (checks yes, outcome yes, tamper-evident yes) |
| `crash_after_send_chargeback_during_outage` | REPLAYED_BY_STRIPE; 1 refund object(s) (final: failed (charge_for_pending_refund_disputed)), want 1; created at or after the chargeback: none; money returned: no; dispute needs_response; **held**; answer vs refund objects: matches; answer vs final money: CONTRADICTS; 8.6s; proof no (checks no, outcome no, tamper-evident no) | FOUND_BY_LOOKUP; 1 refund object(s) (final: failed (charge_for_pending_refund_disputed)), want 1; created at or after the chargeback: none; money returned: no; dispute needs_response; **held**; answer vs refund objects: matches; answer vs final money: CONTRADICTS; 11.2s; proof yes (checks yes, outcome yes, tamper-evident no) | COMMITTED_ON_QUERY; 1 refund object(s) (final: failed (charge_for_pending_refund_disputed)), want 1; created at or after the chargeback: none; money returned: no; dispute needs_response; **held**; answer vs refund objects: matches; answer vs final money: CONTRADICTS; 43.0s; proof yes (checks yes, outcome yes, tamper-evident yes) |

- no_check: invariant held 2/2, answer reflects final money 1/2, can prove 0/2, tamper-evident record 0/2
- hand_check: invariant held 2/2, answer reflects final money 1/2, can prove 2/2, tamper-evident record 0/2
- interlock: invariant held 2/2, answer reflects final money 1/2, can prove 2/2, tamper-evident record 2/2

## Reading

- **Equal on money in this run, and Stripe's own guards did the work, in test mode.** Two separate behaviors:
  1. Stripe refuses a refund on a charge that is already charged back (`400 ... has been charged back; cannot issue
     a refund`, the no_check restart here and every probe). That is a rule, not timing.
  2. A refund created before the chargeback ended `failed` with `charge_for_pending_refund_disputed`: 3 of
     3 such refunds here, created 5, 6, 7s before the chargeback. That is timing,
     not a rule, and it is only what test mode did with the refund seconds before the chargeback. The gap probe
     below left 300s between refund and chargeback: the refund stayed `succeeded` and the chargeback withdrew the
     full $100, so the merchant is out $120 on a $100 payment, in test mode. In live mode a card refund can settle
     sooner or later than that. None of the three columns checks for this case, and no premise can: the refund was
     right when it was sent, and the chargeback comes after the send, outside every column's window, Interlock's
     included. The invariant as scored (no refund created on a charged-back charge) holds there too, so this run's
     "held" does not mean no double loss; it means none within seconds of the send.
  hand_check and Interlock refuse before asking Stripe; the refund objects Stripe holds are the same in every column.
- **"Landed" means Stripe accepted the refund request, not that money came back.** In `crash_after_send`, every
  column answered landed (`REPLAYED_BY_STRIPE`, `FOUND_BY_LOOKUP`, `COMMITTED_ON_QUERY`) and every refund then
  failed, so no answer reflects the final money state (column "answer vs final money"). No record knows either:
  Interlock's receipt says `happened: true` and `assumptions_held: true` (true of the send: its re-check passed
  before the chargeback), with the refund id as evidence and the chargeback in `rechecked_at_recovery`, but nothing
  in it says the refund later failed. hand_check's log ends at the lookup.
  Seeing the failure needs a later re-read or Stripe's `refund.failed` event, which no column subscribes to.
- **Proof, scored from the records, not the system name.** Each cell's `record` in the JSON is what the system left
  in its state dir, copied before the dir was removed; `proof` is computed from that copy against Stripe
  (`dispute.proof`). hand_check appends each check (values read, lookup, result) and each send to a plain log, so
  its record is as complete as Interlock's and agrees with Stripe: a tie on "who decided, which checks ran, what
  Stripe accepted". The difference is tamper-evidence, measured: the harness alters one entry in a copy of each
  receipt and verify() rejects it; the log has no verifier, and an edited line reads the same as a true one. Both are
  unsigned, so neither stops whoever controls the machine from rewriting the whole file. no_check keeps only the
  saved decision. The full receipt bundles are in the JSON and re-verify there (`receipt_reverified_from_results`).
- **The receipt's evidence is the refund id because this scenario overrides the lookup.** `interlock.easy` reduces a
  lookup's answer to a bool (the previous run's receipt said `evidence: true`); worker.py replaces the target's
  `query` with one returning the refund id. Proposed core change: `easy._FunctionTarget.query` returns the lookup's
  value instead of `bool()`.
- **Every answer matched Stripe's refund objects, with one trap on the way.** The lookup (hand_check's and
  Interlock's) must match refunds in any status. The first version of this worker skipped failed refunds, and
  hand_check answered `REFUSED:charged_back` for a refund it had sent (smoke run, `pi_3UFLrq88KhIqqdFL1qOFLhXA`); the
  repo's `StripeRefunds.query` has the same filter.
- **Interlock is slower.** A SIGKILLed sender holds its claim for 40s (`CLAIM_TTL` in worker.py, above the Stripe
  client's 30s timeout), so recovery waits it out; the baselines settle once the chargeback shows.
- **Not run: a restart inside Stripe's ~4s escalation** (`warning_under_review`). A probe refund sent there was
  accepted and later failed. The harness restarts only after Stripe shows `needs_response`. Read from the code, not
  run: all three columns would read the same not-yet-charged-back facts there and send, and Stripe would fail it.
- **The premise is "no chargeback", not "no dispute".** The inquiry exists at decision time (Stripe's inquiry card is
  the only way to have a dispute open after a decision in test mode), so `charge.disputed` is already true then.
  hand_check and Interlock compare the set of chargeback disputes and the refunded total with the decision's.

## Design

- `crash_before_send_chargeback_during_outage`: worker SIGKILLed right before the refund POST; inquiry escalated to a chargeback; restarted. Want no refund.
- `crash_after_send_chargeback_during_outage` (control): worker SIGKILLed after Stripe's refund response, before anything recorded it; inquiry escalated; restarted. Want the $20 refund request issued before the chargeback, once, reported as accepted.
- Invariant, from Stripe: the number of refund objects on the payment (any status) is the wanted count, and none was created at or after the chargeback's balance transaction. Money returned (any refund `succeeded` or `pending` at the final read) is reported next to it.
- no_check: Idempotency-Key `refund:<case>`, the restart re-runs the send with the saved decision. No re-read, no log.
- hand_check: before sending, list refunds carrying this case's metadata (report one if found), re-check the approval, the payment's chargeback disputes and refunded total against the decision's snapshot, append the checks to `hand_check.log` (fsynced), send with the same key, append the send. Idiomatic: the lookup-then-send pattern with a stable key, a read of exactly the state Stripe's own refund error names, and a one-line-per-step audit log. Stripe has no conditional refund precondition to add; its native guard (refusing charged-back charges) applies to every column.
- interlock: `interlock.easy` with those facts as premises (its own refund excluded by effect id), the approval as `allowed=`, the key as tier 1, the refund lookup by metadata as the lookup (returning the id), recovery on restart, the receipt bundle written to `receipt.json`.
- can_prove_what_happened: the system's own record names the decision, lists the checks that ran with the values read, and its outcome (a refund id or a refusal) agrees with Stripe's refund objects. Tamper-evidence and knowledge of the final refund status are scored separately in `proof`.
- seconds_to_settle: from the harness seeing the SIGKILLed worker exit to the restarted worker's answer, including the ~4s the chargeback takes to post.

## Interlock receipts

- `crash_before_send_chargeback_during_outage`: journal ['PROPOSED', 'AUTHORIZED', 'DISPATCHED', 'REFUSED'], re-verified from this JSON: True, verify: {"valid": true, "signed": null, "happened": false, "assumptions_held": null, "refused": "stale_premise at recovery", "evidence": null, "rechecked_at_recovery": {"lease_live": true, "lease": null, "violations": ["chargebacks: was [], now ['du_1UFMFr88KhIqqdFLiWRWl4CZ']"]}}
- `crash_after_send_chargeback_during_outage`: journal ['PROPOSED', 'AUTHORIZED', 'DISPATCHED', 'COMMITTED'], re-verified from this JSON: True, verify: {"valid": true, "signed": null, "happened": true, "assumptions_held": true, "refused": null, "evidence": "re_3UFMH588KhIqqdFL0MBmVhm9", "rechecked_at_recovery": {"lease_live": true, "lease": null, "violations": ["chargebacks: was [], now ['du_1UFMH688KhIqqdFLHtQYBYrd']"]}}

## hand_check logs

- `crash_before_send_chargeback_during_outage`: checks pid 5126: lookup [], chargebacks now [], result send; checks pid 5161: lookup [], chargebacks now ['du_1UFMFg88KhIqqdFLKjVfPqp6'], result REFUSED:charged_back
- `crash_after_send_chargeback_during_outage`: checks pid 6843: lookup [], chargebacks now [], result send; checks pid 7055: lookup ['re_3UFMGp88KhIqqdFL0bDuQq0K'], chargebacks now ['du_1UFMGq88KhIqqdFLMTmeFAi0'], result FOUND_BY_LOOKUP

## Model decisions

- `crash_before_send_chargeback_during_outage` / no_check: 2000 cents, "Partial refund for cracked jar on blender (case #4471). Customer keeps the blender. Approved as goodwill gesture despite open bank inquiry."
- `crash_before_send_chargeback_during_outage` / hand_check: 2000 cents, "Partial refund for cracked jar on blender - customer keeps item. Support case #4471."
- `crash_before_send_chargeback_during_outage` / interlock: 2000 cents, "Partial refund for cracked jar - customer keeping blender. Support case #4471. $20 goodwill refund approved despite open bank inquiry du_1UFMFr88KhIqqdFLiWRWl4CZ."
- `crash_after_send_chargeback_during_outage` / no_check: 2000 cents, "Partial refund for cracked jar on blender - customer keeping item. Approved as goodwill. Open bank inquiry present on account."
- `crash_after_send_chargeback_during_outage` / hand_check: 2000 cents, "Goodwill partial refund for cracked jar on blender - case #4471"
- `crash_after_send_chargeback_during_outage` / interlock: 2000 cents, "Support case #4471: Partial refund for cracked jar on $100 blender. Customer approved for $20 goodwill refund and is keeping the item. Payment has open bank inquiry."

## Probes behind the design (Stripe test mode, this account)

- `pi_3UFLid88KhIqqdFL0ampZ1Yx` (pm_card_createDispute): chargeback `needs_response` 0.6s after confirm; a $20 refund got `400: Charge ... has been charged back; cannot issue a refund.`
- `pi_3UFLku88KhIqqdFL0eeS1JpB` (pm_card_createDisputeProductNotReceived): same 400.
- `pi_3UFLig88KhIqqdFL0kVeW9XO` (pm_card_createDisputeInquiry): inquiry `warning_needs_response` 0.4s after confirm; a $20 refund succeeded.
- `pi_3UFLkf88KhIqqdFL1feJQAUx`: inquiry escalated with `escalate_inquiry_evidence`, `needs_response` 4.4s later; a refund then got the same 400.
- `pi_3UFLnM88KhIqqdFL0KOe8GR2`: a refund sent right after escalation (status `warning_under_review`) was accepted as `succeeded`; after the chargeback posted it read `failed`.
- `re_3UFLig88KhIqqdFL06eJCJwL`, refunded during an inquiry never escalated: still `succeeded`. `re_3UFLkf88KhIqqdFL10AExShI`, refunded during an inquiry escalated afterwards: `failed`, `charge_for_pending_refund_disputed`.
- `pi_3UFLjG88KhIqqdFL1mI5oFtM` (pm_card_createDispute, manual capture): no dispute while authorized; chargeback 0.45s after capture.
- `pi_3UFLkz88KhIqqdFL0vU9aQ5m` (pm_card_createMultipleDisputes): both disputes within a second of the charge; winning the first opened nothing new.
- Gap probe, `pi_3UFM7Y88KhIqqdFL1xjLWAch`: $20 refund `re_3UFM7Y88KhIqqdFL1YCvLUoj` created during the inquiry, `succeeded`; 300s later the inquiry was escalated (`du_1UFM7Z88KhIqqdFLWKRcYQWo`, `needs_response` 7.1s later, balance transaction -10000). The refund read `succeeded` 10, 30, 60 and 120s after, and again 144s after (`failure_reason` null); the charge shows `amount_refunded` 2000 and `disputed` true. Out $120 on a $100 payment, in test mode.

## Ids

- `crash_before_send_chargeback_during_outage` / no_check: {"payment_intent": "pi_3UFMFV88KhIqqdFL0fK3svy5", "charge": "ch_3UFMFV88KhIqqdFL0gZbADzF", "dispute": "du_1UFMFW88KhIqqdFLNGFELqEE", "case": "interlock-sandbox-d5f8c375", "first_worker_exit": -9, "refunds": []}, chargeback `needs_response` at 1789339916 (6.4s after escalation), refunds at settle: none, final: none
- `crash_before_send_chargeback_during_outage` / hand_check: {"payment_intent": "pi_3UFMFf88KhIqqdFL0FKsLelI", "charge": "ch_3UFMFf88KhIqqdFL0jFEFdWC", "dispute": "du_1UFMFg88KhIqqdFLKjVfPqp6", "case": "interlock-sandbox-68aa0fc5", "first_worker_exit": -9, "refunds": []}, chargeback `needs_response` at 1789339926 (5.4s after escalation), refunds at settle: none, final: none
- `crash_before_send_chargeback_during_outage` / interlock: {"payment_intent": "pi_3UFMFq88KhIqqdFL1K3OZo0L", "charge": "ch_3UFMFq88KhIqqdFL1gwgYrj7", "dispute": "du_1UFMFr88KhIqqdFLiWRWl4CZ", "case": "interlock-sandbox-0d90bc13", "first_worker_exit": -9, "refunds": []}, chargeback `needs_response` at 1789339938 (6.6s after escalation), refunds at settle: none, final: none
- `crash_after_send_chargeback_during_outage` / no_check: {"payment_intent": "pi_3UFMGb88KhIqqdFL0scwI3qe", "charge": "ch_3UFMGb88KhIqqdFL0pUzlpTx", "dispute": "du_1UFMGc88KhIqqdFLtVBdjHhK", "case": "interlock-sandbox-93c54206", "first_worker_exit": -9, "refunds": ["re_3UFMGb88KhIqqdFL0En6hjgf"]}, chargeback `needs_response` at 1789339987 (7.9s after escalation), refunds at settle: ['re_3UFMGb88KhIqqdFL0En6hjgf (failed)'], final: ['re_3UFMGb88KhIqqdFL0En6hjgf failed']
- `crash_after_send_chargeback_during_outage` / hand_check: {"payment_intent": "pi_3UFMGp88KhIqqdFL0WthWowP", "charge": "ch_3UFMGp88KhIqqdFL0zsOb5hu", "dispute": "du_1UFMGq88KhIqqdFLMTmeFAi0", "case": "interlock-sandbox-c518e2a4", "first_worker_exit": -9, "refunds": ["re_3UFMGp88KhIqqdFL0bDuQq0K"]}, chargeback `needs_response` at 1789340002 (10.3s after escalation), refunds at settle: ['re_3UFMGp88KhIqqdFL0bDuQq0K (failed)'], final: ['re_3UFMGp88KhIqqdFL0bDuQq0K failed']
- `crash_after_send_chargeback_during_outage` / interlock: {"payment_intent": "pi_3UFMH588KhIqqdFL0n3kwR0A", "charge": "ch_3UFMH588KhIqqdFL04jrOCiG", "dispute": "du_1UFMH688KhIqqdFLHtQYBYrd", "case": "interlock-sandbox-0e3ef814", "first_worker_exit": -9, "refunds": ["re_3UFMH588KhIqqdFL0MBmVhm9"]}, chargeback `needs_response` at 1789340018 (9.2s after escalation), refunds at settle: ['re_3UFMH588KhIqqdFL0MBmVhm9 (failed)'], final: ['re_3UFMH588KhIqqdFL0MBmVhm9 failed']
