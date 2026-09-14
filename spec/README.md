# spec/: TLA+ model of interlock_runtime and the two Temporal baselines

A model check for the stated constants, not a proof of the Python or SQL. It checks the protocol
in docs/07-runtime.md (sections 5 and 10) with bounded workers, clock, crashes and world events.

## Files

| file | what |
|---|---|
| `Runtime.tla` | claims, fence, step rows, gated effect (T_dispatch, send, T_commit, late result), recovery by tier, target with dedup store, world events, and `MODE` = `interlock`, `temporal_idem`, `temporal_precheck` |
| `Signals.tla` | suspend transaction, rt.signal, timers (NoLostWakeup, SignalExactlyOnceConsumed, TimerNotEarly) |
| `Runtime.cfg` | interlock mode, every safety invariant |
| `RuntimeTemporalIdem.cfg` | Temporal alone, key = run id + activity id |
| `RuntimeTemporalPrecheck.cfg` | Temporal plus the pre-send check of 11.1 (b), key = workflow id |
| `RuntimeLive.cfg` | Termination and EffectResolved under weak fairness |
| `Signals.cfg` | Signals invariants |
| `assumptions/Pause.cfg`, `assumptions/ServerSlow.cfg` | A1 and A2 violated on purpose |
| `broken/*.cfg` | deliberately broken designs; each must produce a counterexample |
| `COUNTEREXAMPLES.md` | every counterexample that matters, with its trace and the design fix |
| `run_tlc.sh` | downloads tla2tools.jar to `.tools/` (gitignored), checks its sha256, runs TLC |
| `tla2tools.sha256` | pinned hash of the jar |

## Run

Java: `/opt/homebrew/opt/openjdk/bin/java` (the `java` on PATH is broken on this machine; override with `JAVA=`).
TLC: `2026.09.12.025210 (rev: 867aefb)`, from the rolling `v1.8.0` release asset, pinned by sha256.

One config (from the repo root):

```
spec/run_tlc.sh Signals Signals.cfg
spec/run_tlc.sh Signals broken/WakeOnlyIfSleeping.cfg
spec/run_tlc.sh Runtime Runtime.cfg                      # interlock, tier 2, events G1
spec/run_tlc.sh Runtime broken/NoLocalLeaseCheck.cfg
spec/run_tlc.sh Runtime RuntimeLive.cfg
TLC_WORKERS=4 TLC_HEAP=8g spec/run_tlc.sh Runtime RuntimeTemporalPrecheck.cfg
```

Everything, with per-invariant outcomes, traces and `results/runtime_tlc.md`:

```
python3 experiments/runtime_tlc.py suite --jobs 3
python3 experiments/runtime_tlc.py one Runtime.cfg --set Tier=1 --set Queryable=FALSE --inv PayloadBound
python3 experiments/runtime_tlc.py one RuntimeTemporalPrecheck.cfg --inv NoSendUnderRevokedGrant,EffectAtMostOnceTier12 --peel
```

A `--peel` run checks a list of invariants, removes each one TLC reports violated, and re-checks the
rest until they hold, so one full exploration answers every invariant and every violation keeps its
shortest trace. Configs actually run are written to `spec/.tools/cfg/`.

## Constants actually run

The spec's base constants (10.1) are `MaxClock = 12`, `MaxCrashes = 2`, `DedupAge = 6`, all six events.
That space did not finish: at tier 2 with three events and one crash, MaxClock 8 is 6.6M distinct
states (65 s) and MaxClock 10 is 43.1M (7 min); each clock tick multiplies the space by about 2.5.
So the runs use:

| constant | run value | why |
|---|---|---|
| Workers | {w1, w2}, with symmetry | as specified |
| MaxClock | 10 (8 for witnesses and the two-crash runs, 9 for the assumption toggles, 20 for liveness) | state space |
| LeaseTTL, SendTimeout, SettleMargin | 3, 2, 2 (one run with LeaseTTL 2 < SendTimeout 3, the relation 5.4 recommends) | as specified |
| DedupAge | 5 | recovery starts at least SendTimeout + SettleMargin + 1 = 5 after dispatch; 5 keeps the tier-1 retry reachable and the downgrade reachable |
| MaxCrashes | 1 (2 in `interlock_*_crashes2` at MaxClock 8) | state space |
| Events | G1 = {revoke, hand_refund_full, cancel} and G2 = {prune_keys, redecide, revoke}, one run each | state space; revoke is in both so it meets every other event |
| broken configs | MaxClock 10, one crash, only the events the bug needs | the counterexample is shallow; a bigger space only slows BFS |

A partial hand refund behaves exactly like a full one in this model (both falsify the decision's
premise "no prior refunds", and both pass (b)'s eligibility check `hand + 20 <= 100`), so it is left out
of the groups. It is still an action in the spec.

Tier cases in every table: `t1q` tier 1 with lookup (Stripe-like), `t1n` tier 1 without lookup,
`t2` tier 2, `t3` tier 3.

## State spaces

@@STATES@@

## Modeling choices (read before trusting a result)

- **Database clock.** `now` is Postgres time. `now()` is the transaction start: `T_dispatch` is two steps,
  `TDispatchBegin` (fence UPDATE, row lock, `now()` fixed) and `TDispatchCommit` (every check of 5.7 (c),
  atomically), so time can pass inside it. Other transactions are one atomic step.
- **Locks.** The workflow row lock is modeled (`wf.lock`): claims, cancel and fenced writes wait for an
  open `T_dispatch`. The grant `FOR SHARE` lock is modeled by doing the grant check at commit, so a
  revoke is either before the dispatch commit or after it.
- **Crash.** SIGKILL and restart are one step: local state is lost and an open transaction rolls back.
  A down worker is an idle worker that takes no action. The watchdog exit (5.4) is the same step
  without spending the crash budget.
- **Heartbeat.** Renews only when the lease is within one tick of expiry; whether it runs at all is
  nondeterministic, so a missed heartbeat models a partition or a starved thread.
- **Network and target.** A request leaves at `Send` only before the sender's local deadline (unless it
  resumed from a pause). The target processes it at most `SettleMargin` ticks later (A2), or any time up
  to `MaxClock` under `SERVER_SLOW`; the clock cannot pass a request's bound. The response reaches the
  sender when processed if the sender still waits for it; a lost response is a sender that never acts
  on it. Tier 1 dedupes with Stripe semantics (same key and payload replays, different payload errors).
- **External premises** are read before the transaction (`ReadPremise`, A3), so NoSendOnStalePremise is
  judged at the read. `PremiseTrueAtSend` (not in 2.1) judges the premise at the moment the bytes leave
  and shows the A3 window in every mode. Local SQL premises are not modeled separately: they are checked
  at the same commit as the grant and behave like it.
- **Where send facts are measured.** `liveClaim` is whether the fence of the authorizing transaction
  matched a live claim (2.1's definition), `grantOk`, `afterRevoke` and `afterCancel` are true at that
  commit, `prevSendSettled` is "no earlier request for this effect is still unprocessed" at the send.
  For Temporal, the authorizing point is the send itself (there is no transaction before it).
- **Journal.** Kept as counters (DISPATCHED, COMMITTED, resolutions, LATE_RESULT) rather than a sequence.
  PROPOSED and AUTHORIZED entries are not modeled; no invariant reads them.
- **Redecide.** Interlock: the next offer is 30, as a fork or a re-run would offer at `T_dispatch`.
  Temporal: a reset to before the decision, a new run id, payload 30.
- **Temporal modes.** No fence, no claims, no effect journal. The plain step is pre-completed (not
  modeled). The server starts a retry only after the start-to-close timeout (a SIGKILLed worker does not
  report its death). An attempt sends only before its own timeout unless it was paused, the baseline's
  best case. Completion is accepted only from the current attempt inside its timeout. Cancel stops new
  attempts; a running attempt that does not heartbeat is not told.
- **URGENT** (liveness configs only): time advances only when no worker or target step is enabled, so
  the bounded clock cannot starve a fair run. Safety configs let time advance at any point.

## Reading two invariants correctly

- **Tier3NeverResends** counts sends into a window where the outcome cannot be known (tier 3, or tier 1
  without lookup once the effect is older than `DedupAge`). A violation is a retry that *could* double
  apply, not one that did. Example: both Temporal modes violate it at t1n with events G1, where no key
  is ever pruned, so EffectAtMostOnceTier12 still holds there. With G2 (pruning) the risk can become a
  real duplicate, which EffectAtMostOnceTier12 then reports.
- **NoSendOnStalePremise** judges the premise at the read (A3), as 2.1 defines it. PremiseTrueAtSend
  judges it when the bytes leave, and is violated in every mode, the runtime included: a hand refund
  between the read and the `T_dispatch` commit is missed. That is the conceded A3 window, not a bug.

## Invariants that are n/a for the Temporal modes

NoRerunAfterComplete, StepResultUnique (plain step not modeled); FencedWrites, LeaseMutex,
TakeoverOnlyAfterExpiry (no fence or claim in the baseline); AmbiguousOnlyWhenUnknowable (never writes
AMBIGUOUS); EffectCheckpointAtomic, LateResultPreserved, ReceiptChainLinear (no effect journal separate
from the history; the gap EffectCheckpointAtomic guards shows up as the duplicate in
EffectAtMostOnceTier12). 10.6 predicted V for EffectCheckpointAtomic in both Temporal modes; this model
reports it as not applicable instead of forcing a violation.

## Changes to the spec's model plan

- Added `broken/NoLocalLeaseCheck.cfg` and `broken/ThinDedupMargin.cfg` for the two design findings (C1, C2 in COUNTEREXAMPLES.md). The interlock mode includes both fixes.
- Added `Reach_*` witnesses: each must be violated where its path exists, so a hold is not vacuous.
- Added `PremiseTrueAtSend` (A3 window) and a liveness sanity run with a too-short clock (must violate Termination).
- **Prediction revised: NoFencing does not violate EffectAtMostOnceTier12.** 10.6 says the NoFencing
  config must violate SendRequiresLiveClaim, FencedWrites and EffectAtMostOnceTier12. TLC finds the first
  two (a zombie with a stale epoch does dispatch and write), but no duplicate application. Checked to
  completion without the fence: tier 2 with no events (3.35M distinct states), tier 2 with a hand refund
  (12.4M), and tier 1 with lookup and key pruning (3.8M). EffectAtMostOnceTier12, NoOverlappingSends and
  AtMostOneCommit hold in all three. The reason is in the design: at-most-once is carried by the effect
  row, not the workflow fence. T_dispatch refuses an open dispatch, recovery requires
  `now > send_deadline + settle_margin` and an unchanged dispatch pair under the effect row lock, and the
  late result is a compare-and-set on that pair. The fence is still required: without it a zombie
  writes step rows and workflow status (FencedWrites) and authorizes sends without a live claim
  (SendRequiresLiveClaim). This is a diagnosed disagreement with the prediction, not a model bug: the
  model exercises zombies (the same config reaches FencedWrites in 239 states).
- **NoOverlappingSends at tier 2 holds because a second request never exists.** `Reach_TwoSends` is
  unreachable at t2 while `Reach_RecoveryResend` is reachable: a tier-2 resend happens only when the
  lookup, run after `send_deadline + settle_margin`, finds nothing, which means the first request never
  left. At t1q two requests do occur (the idempotent retry), and the invariant is exercised there.
