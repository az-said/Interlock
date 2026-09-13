# Results: refund agent

Generated 2026-09-13 16:13 UTC by `experiments/run_all.py`. Cells: `outcome · refunds · invariant`. ✅ held · ❌ violated · ⚠️ held, but availability lost.

Customer paid $100. Case #4471 approves one $20 partial refund. Invariant: exactly $20
refunded (or $0 if the lease was revoked or the order became ineligible first).

| fault | naive | idempotency@tier1 | gate@tier1 | gate@tier2 | gate@tier3 |
|---|---|---|---|---|---|
| `happy_path` | APPLIED $20 ✅ | APPLIED:ok $20 ✅ | COMMITTED $20 ✅ | COMMITTED $20 ✅ | COMMITTED $20 ✅ |
| `crash_before_send` | RETRIED $20 ✅ | RETRIED $20 ✅ | COMMITTED_BY_RETRY $20 ✅ | REAPPLIED_AFTER_QUERY $20 ✅ | AMBIGUOUS $0 ⚠️ |
| `crash_before_ack` | RETRIED $40 ❌ | RETRIED $20 ✅ | COMMITTED_BY_RETRY $20 ✅ | COMMITTED_ON_QUERY $20 ✅ | AMBIGUOUS $20 ⚠️ |
| `duplicate_submit` | APPLIED $40 ❌ | APPLIED:already_processed $20 ✅ | DUPLICATE_IGNORED $20 ✅ | DUPLICATE_IGNORED $20 ✅ | DUPLICATE_IGNORED $20 ✅ |
| `model_redecides` | APPLIED $50 ❌ | APPLIED:key_reused_with_different_params $20 ✅ | REFUSED:conflicting_payload $20 ✅ | REFUSED:conflicting_payload $20 ✅ | REFUSED:conflicting_payload $20 ✅ |
| `conflicting_payload` | APPLIED $50 ❌ | APPLIED:key_reused_with_different_params $20 ✅ | REFUSED:conflicting_payload $20 ✅ | REFUSED:conflicting_payload $20 ✅ | REFUSED:conflicting_payload $20 ✅ |
| `lease_revoked` | APPLIED $20 ❌ | APPLIED:ok $20 ❌ | REFUSED:lease $0 ✅ | REFUSED:lease $0 ✅ | REFUSED:lease $0 ✅ |
| `stale_eligibility` | APPLIED $20 ❌ | APPLIED:ok $20 ❌ | REFUSED:stale_premise $0 ✅ | REFUSED:stale_premise $0 ✅ | REFUSED:stale_premise $0 ✅ |

## Faults

- `happy_path` — no fault (control)
- `crash_before_send` — in-flight marker durable, process dies before the request is sent
- `crash_before_ack` — service commits the refund; process dies before the ack is recorded
- `duplicate_submit` — the same approved request is submitted twice
- `model_redecides` — after crash_before_ack the re-run model says $30 instead of $20
- `conflicting_payload` — same approved request arrives with a different amount, no crash
- `lease_revoked` — refund permission revoked after the decision, before it lands
- `stale_eligibility` — order becomes ineligible after the decision, before it lands

## Reading it

- **naive** double-refunds on crash and duplicate delivery, refunds $50 when the re-run
  model says $30, and refunds under a revoked lease and an ineligible order. This is an
  agent framework with no gate.
- **idempotency@tier1** is the conventional durable operation: a stable key at a Stripe-
  like service, no agent runtime. It handles crash, duplicates, and the $30 re-decision
  (the service rejects a reused key with different params). It does **not** handle a
  revoked lease or a changed order, because the service can't see the agent's authority
  or premises. That gap is exactly what the runtime adds.
- **gate@tier1** (API dedupes on the effect id): every fault handled, including crash,
  by a safe retry. Exactly-once effect.
- **gate@tier2** (API has a lookup): every fault handled; the crash is resolved by
  asking the API what it has, then committing without re-sending.
- **gate@tier3** (API has neither): both crash cases end `AMBIGUOUS`. The gate refuses
  to retry, so there is no duplicate, but it cannot confirm the refund happened. Note
  `crash_before_send`: the refund never happened, and tier 3 still blocks it, because
  from the client the two crashes are indistinguishable. A refund that never happened
  may stay blocked. That is the stated cost.
  **That row is an impossibility, not a bug.** From the client side, "sent and ack
  lost" is indistinguishable from "never arrived". No protocol closes it without
  the target's cooperation. What the gate can still promise at tier 3 is at-most-once
  plus a surfaced ambiguity for a human or a later reconciliation job.
