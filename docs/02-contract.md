# Correctness contract

Given a journal `J`, an effect target `T` with declared tier, and a lease store `L`, Interlock guarantees:

## Safety invariants

- **I1. No effect without a journaled decision.** `T.apply` is never called for effect `e` unless a `DISPATCHED(e)` entry is durable in `J`.
- **I2. No duplicate committed effect.** For any effect id `e`, at most one `COMMITTED(e)` exists in `J`, and `T.apply(e)` is invoked at most once except under tier-1 idempotent retry.
- **I3. No stale premise lands.** `T.apply(e)` is called only if `T.validate_premises(premises(e))` returned empty immediately before `DISPATCHED(e)`.
- **I4. No effect under a dead lease.** `T.apply(e)` is called only if `L.is_live(lease(e))` immediately before `DISPATCHED(e)`.
- **I5. Payload binding.** The first `PROPOSED(e)` fixes `payload(e)`. Any later proposal for `e` with a different payload is `REFUSED`. In particular, recovery always uses the recorded payload and never a fresh model output. (The re-run model saying $30 cannot displace the recorded $20.)
- **I6. No duplicate implementation.** An effect that defines a symbol already present in the target, or claimed by another live agent, is `REFUSED` before it lands.

## Progress

- Any proposal whose premises hold and whose lease is live reaches `COMMITTED`.
- After a crash, `recover()` resolves every in-flight effect (latest entry `DISPATCHED`) to exactly one of `COMMITTED` or `AMBIGUOUS`. It never re-applies without either idempotency (tier 1) or a positive query result (tier 2).

## What the gate is allowed to do when it cannot establish the condition

Refuse (I3, I4) or mark `AMBIGUOUS` (crash at tier 3). It is never allowed to guess.

## Failure model

Faults are injected at the boundaries the brief names:

| fault | boundary |
|---|---|
| crash after in-flight marker, before send | between dispatch and execution |
| crash after effect, before ack | between execution and acknowledgment |
| model re-decides on re-run | nondeterministic decision under retry |
| same approved request, different payload | payload binding |
| two agents implement the same symbol | duplicated work (MAST top mode) |
| duplicate delivery of the same proposal | message duplication |
| lease revoked between proposal and dispatch | permission change during execution |
| concurrent actor invalidates a premise | partition-like divergence between decision snapshot and world |
| concurrent actor makes a benign change | control for availability |
| concurrent actor changes meaning, not signature | the class outside the guarantee |

## Cooperation ladder

| tier | target offers | guarantee on crash-before-ack |
|---|---|---|
| 1 | dedup on effect id | exactly-once effect, safe retry |
| 2 | lookup by effect id | exactly-once effect, one extra read |
| 3 | neither | at-most-once; `AMBIGUOUS` surfaced; liveness lost for that effect |

Tier 3 is an impossibility result, not a bug: two distinct real histories (sent-and-lost vs never-sent) produce identical client-observable histories, so no client-side algorithm can decide between them. The measured cost: at tier 3 a refund that *never happened* stays blocked after a crash-before-send, because the gate cannot tell it apart from crash-before-ack.

## Baselines

Two, because the brief says match evidence to the claim and the team spec says superiority must be measured, not assumed:

- **naive**: re-run the workflow, fresh attempt id each time, re-ask the model. Today's frameworks.
- **idempotency-only**: the conventional durable operation. A stable key at a cooperating service, no runtime. "Just use Stripe idempotency keys." This baseline handles crash, duplicate delivery, and payload conflicts *at the service*. It cannot handle a revoked lease or a changed premise, because the service cannot see either. The difference between this column and the gate columns is the runtime's measured contribution.

## Assumptions

- `J` is durable and trusted. If the journal's storage lies, nothing holds.
- Premises are captured by the harness at decision time, not self-reported by the model.
- `T.validate_premises` and `T.query` are correct for the target. A target that lies about its own state is outside the model.
- Effect ids are derived from decision content. Two genuinely different decisions that hash identically are outside the model (SHA-256 truncated to 48 bits in this demo; use the full digest in production).
- Single journal, single gate. Multiple gates over one target need a shared journal or a notary.

## Outside the contract

- The correctness of the decision itself. A correct execution of a wrong decision is a wrong decision.
- Semantic premises. Only mechanically extractable premises are checked; see Finding 2.
- Compensation after a legitimately committed effect whose authority is later revoked. That is a saga (Garcia-Molina & Salem, 1987) and a next step, not part of this contract.
