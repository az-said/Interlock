# Correctness contract

Given a journal `J`, an effect target `T` with declared tier, and a lease store `L`, Interlock guarantees:

## Safety invariants

- **I1. No effect without a journaled decision.** `T.apply` is never called for effect `e` unless a `DISPATCHED(e)` entry is durable in `J`.
- **I2. No duplicate committed effect.** For any effect id `e`, at most one `COMMITTED(e)` exists in `J`, and `T.apply(e)` is invoked at most once except under tier-1 idempotent retry.
- **I3. No stale premise lands.** `T.apply(e)` is called only if `T.validate_premises(premises(e))` returned empty immediately before `DISPATCHED(e)`.
- **I4. No effect under a dead lease.** `T.apply(e)` is called only if `L.is_live(lease(e))` immediately before `DISPATCHED(e)`.
- **I5. Payload binding.** The first `PROPOSED(e)` fixes `payload(e)`. Any later proposal for `e` with a different payload is `REFUSED`. In particular, recovery always uses the recorded payload and never a fresh model output. (The re-run model saying $30 cannot displace the recorded $20.)
- **I6. No duplicate implementation.** An effect that defines a symbol already present in the target, or claimed by another live agent, is `REFUSED` before it lands.
- **I7. Decision binding.** Once an effect has an `ESCALATED` entry, it is dispatched only under a person's recorded `DECIDED` approval of its latest escalation, by a member of that escalation's group (checked when deciding and again at dispatch), with that escalation's facts as premises. Otherwise it is `REFUSED:awaiting_decision`. Policy never sends it again.
- **I8. Repairs are new decisions.** A suggested repair with a different payload is a new effect id, accepted only while the original never landed; accepting it closes the original, and a closed effect is `REFUSED:closed`. A repair never reuses the refused id (I5) and never skips the rules or a person.

## Progress

- Any proposal whose premises hold and whose lease is live reaches `COMMITTED`.
- After a crash, `recover()` resolves every in-flight effect (latest entry `DISPATCHED`) to exactly one of `COMMITTED`, `REFUSED`, or `AMBIGUOUS`. It never re-applies without either idempotency inside the provider's dedup window (tier 1) or a query showing the effect is absent (tier 2).
- **I3 and I4 hold on the recovery path.** A resend is a new dispatch, so the lease and premises are re-checked first. The outage is exactly when the world moves: support refunds the order by hand, or the grant is revoked. If the re-check fails, the gate commits only what a query proves already landed, and refuses or marks `AMBIGUOUS` otherwise.
- **No resend of an unresolved effect.** Submitting an effect with an open send (a `DISPATCHED` not yet resolved by `COMMITTED`, `AMBIGUOUS`, or a recovery-written `REFUSED`) returns `IN_FLIGHT` and writes nothing, so recovery still finds it. Submitting an `AMBIGUOUS` effect again returns `AMBIGUOUS`. Only `recover()` or a human reconciliation resolves either; a duplicate delivery never does.
- **One sender at a time, one recoverer at a time.** Dispatching an effect atomically claims it for the sender, and the claim is released when the send resolves. `recover()` takes an effect only after any other live claim has expired (`claim_ttl`, 120s by default), refreshes its own claim right before a resend, and releases it once the effect is resolved. So an effect still being applied, by this worker or another, is never sent a second time.
- **Recovery is per effect.** If recovering one effect raises (a network error from its lookup), it is reported `UNRESOLVED` and left in flight for a later attempt; the other effects are still recovered.
- **Premises are bound to an authority.** A re-proposal under the same lease is checked against the premises its decision was first recorded with, never facts re-read at retry time. A new authority (a person approving after a refusal) is a new decision with the premises that person saw. Recovery re-checks exactly the lease and premises recorded on the send.
- **P'. Every refused or unverifiable outcome of an inbox-owned effect ends in exactly one open escalation.** The inbox queue is a fold over the journal, and escalations and decisions are appended with a check under the journal lock, so a crash, a restart, or a second inbox can neither lose nor duplicate one. An unanswered escalation moves up its route's chain after its SLA; time comes from an injected clock.
- **Confirmation is evidence, not control.** A `CONFIRMED` entry (a signed Stripe webhook or a refunds lookup, matched by `interlock_effect_id`, payment and amount) never closes a dispatch and never changes gate or inbox behaviour.
- **A definite failure is settled, not resent.** When a target answers that a send failed (an MCP tool's `isError`), the gate confirms by lookup when it can and otherwise records the failure as `REFUSED`; it does not send again.

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
| a human performs the effect by hand during the outage | premise change on the recovery path |
| lease revoked during the outage | permission change on the recovery path |
| recovery runs after the provider's dedup window | tier 1 degrading to tier 2 |

## Cooperation ladder

| tier | target offers | guarantee on crash-before-ack |
|---|---|---|
| 1 | dedup on effect id, for a window (Stripe: 24h) | exactly-once effect, safe retry inside the window; after it, tier 2 if the target can be queried, else tier 3 |
| 2 | lookup by effect id | exactly-once effect, one extra read |
| 3 | neither | at-most-once; `AMBIGUOUS` surfaced; liveness lost for that effect |

Tier 3 is an impossibility result, not a bug: two distinct real histories (sent-and-lost vs never-sent) produce identical client-observable histories, so no client-side algorithm can decide between them. The measured cost: at tier 3 a refund that *never happened* stays blocked after a crash-before-send, because the gate cannot tell it apart from crash-before-ack.

## Baselines

Three, because the brief says match evidence to the claim and the team spec says superiority must be measured, not assumed:

- **naive**: re-run the workflow, fresh attempt id each time, re-ask the model. Today's frameworks.
- **idempotency-only**: the conventional durable operation. A stable key at a cooperating service, no runtime. "Just use Stripe idempotency keys." This baseline handles crash, duplicate delivery, and payload conflicts *at the service*. It cannot handle a revoked lease or a changed premise, because the service cannot see either. The difference between this column and the gate columns is the runtime's measured contribution.
- **durable execution**: Temporal, DBOS, or Restate used as their docs recommend, against a tier-1 target. A completed step's result is recorded and replayed; a step that dies before its result is recorded is re-run with a stable idempotency key. This handles crash, duplicate delivery, and a re-decided payload by replaying history. It cannot handle anything that changed after the decision was recorded, because it replays the decision instead of re-checking it.

## Assumptions

- `J` is durable and trusted. If the journal's storage lies, nothing holds.
- Premises are captured by the harness at decision time, not self-reported by the model.
- `T.validate_premises` and `T.query` are correct for the target. A target that lies about its own state is outside the model.
- Effect ids are derived from decision content. Two genuinely different decisions that hash identically are outside the model (SHA-256 truncated to 48 bits in this demo; use the full digest in production).
- Single journal, single gate. Multiple gates over one target need a shared journal or a notary.
- The target declares its dedup window (`dedup_window`) and whether it can be queried (`queryable`). A provider that shortens its window without saying so is outside the model. Recovery treats a key as expired 10 minutes early, to absorb clock skew between the worker that sent and the worker that recovers.
- A send, and a resend during recovery, finishes well inside `claim_ttl`. Targets must time out sooner than that (the Stripe target uses 30s, the MCP proxy 60s, against a 120s default). A send that outlives its claim can be taken over.
- Receipts: `verify()` checks the chain, that the bundle starts with a proposal, that every send follows an authorization, and that every commit closes a send. The recorded checks are the gate's own attestations. A signature binds them to whoever holds the key; without one, whoever controls the journal could rebuild a consistent chain. When a chain has escalations, `verify()` also checks that each person's send has that person's decision, on the latest escalation, on the facts shown, before the send, from a member of the group it was routed to; and it reports the escalation history and `confirmed_by_target`. Without a signature, whoever controls the journal could strip escalations so a chain looks like one from before this check; receipts from before it stay valid.

## Outside the contract

- The correctness of the decision itself. A correct execution of a wrong decision is a wrong decision.
- Semantic premises. Only mechanically extractable premises are checked; see Finding 2.
- Compensation after a legitimately committed effect whose authority is later revoked. That is a saga (Garcia-Molina & Salem, 1987) and a next step, not part of this contract.
