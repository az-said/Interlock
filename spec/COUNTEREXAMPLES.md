# Counterexamples found by TLC, and the design fixes

Model check for the stated constants, not a proof of the Python or SQL. Every trace below is the
shortest one TLC found (breadth-first search), copied from its JSON trace dump through
`experiments/runtime_tlc.py`. `Tick` advances the database clock by one. `Next` in a trace is the
target processing one request (TLC names that step after the `Next` disjunct it sits in). Fields not
shown did not change.

Two findings are against the runtime spec as written (docs/07-runtime.md) and need a change in the
runtime. The interlock mode of spec/Runtime.tla includes both fixes, and a broken config reproduces
each trace without its fix. The rest of this file is the Temporal baselines, where the counterexamples
are the expected result.

---

## C1. A plain step body can start after another worker recorded that step

**Invariant:** NoRerunAfterComplete. **Config:** `spec/broken/NoLocalLeaseCheck.cfg` (tier 2, no world
events, MaxClock 10, one crash budget, none used). An 11-state trace, found after about 1K distinct
states (the exact count at the moment of violation varies with TLC's worker scheduling).

```
 1. Init
 2. Claim(w1):     wf.epoch=1, wf.owner=w1, wf.lease=3, wf.status=running; w1 epoch 1, local lease 3
 3. Tick:          now=1
 4. Tick:          now=2
 5. Tick:          now=3            w1's lease has expired; w1 has not touched Postgres since the claim
 6. Replay(w1):    w1 routes to the plain step (its loaded rows show no step row)
 7. Claim(w2):     wf.epoch=2, wf.owner=w2, wf.lease=6      takeover, correctly after expiry
 8. Replay(w2):    w2 routes to the plain step
 9. RunPlain(w2):  w2 runs the body
10. RecordPlain(w2): wf.stepPlain=true                      step row committed
11. RunPlain(w1):  w1 starts the body again after the row committed   (NoRerunAfterComplete violated)
```

**What it means in the code.** 5.2 makes every write fenced, so w1's later record is refused, but the
body has already started. Between the claim and the first body there is no fenced write: the worker
loads the step rows and replays cached calls. If that load stalls longer than `lease_ttl` (Postgres
slow or unreachable from this worker, which is exactly when the heartbeat also cannot renew), the
lease expires, a second worker claims, runs and records the step, and then the load returns and the
first worker starts the same body. No process pause is needed, so A1 does not cover it. The heartbeat
setting `ctx.fenced` does not help: the heartbeat's own UPDATE is stuck on the same connection path.

Plain steps are at-least-once by design (5.5), so this is not an effect duplicate. It breaks the
stronger promise NoRerunAfterComplete makes ("a step body never starts after its step row
committed"), and the same gap lets a `decide` spend a model call after its row exists.

**Fix for the runtime builder.**

1. Keep a local lease deadline per claimed workflow: `local_lease = t0 + lease_ttl`, where
   `t0 = time.monotonic()` is read *before* the claim transaction begins, and again before every
   fenced transaction or heartbeat UPDATE that renews the lease (the same stopwatch-before-transaction
   rule as the send watchdog in 5.4, and correct for the same reason: `t0` precedes the transaction's
   `now()`, so `local_lease <= lease_expires_at` under A5).
2. Before starting any step body, and before the model call in `decide`, check
   `time.monotonic() < local_lease`; otherwise raise `Fenced` and abandon the run.
3. A takeover commits at database time `>= lease_expires_at >= local_lease`, and the successor's step
   row commits after that, so a body that passed the check started before the row existed.

**Residual.** A process pause between the check and the body start (A1) still reruns the body. That is
the same assumption the send watchdog makes, and it is stated.

**Test that must fail before the fix** (tests/test_runtime.py): put `experiments/runtime_fault_proxy.py`
between worker A and Postgres. After A's claim commits, blackhole the proxy for `lease_ttl + 2s`
(so the step-row load stalls). Worker B claims, runs and records step 1. Restore the proxy. Assert the
step-1 invocation table has exactly one row.

**In the model:** `RunPlain` requires `now < lw[w].lease`, where `lw[w].lease` is set by the claim and
by every fenced write that renews the lease. With the guard, NoRerunAfterComplete holds in every
interlock run (results/runtime_tlc.md).

---

## C2. Tier-1 dedup margin must exceed send_timeout + settle_margin

**Invariant:** EffectAtMostOnceTier12. **Config:** `spec/broken/ThinDedupMargin.cfg` (tier 1 with lookup,
`DedupAge = 5`, the target may prune keys as soon as the effect's age exceeds `DedupAge`).
A 26-state trace, found after about 250K distinct states.

```
 3. Claim(w1):          wf.epoch=1, wf.owner=w1, wf.lease=4                      (now=1)
10. TDispatchCommit(w1): eff.state=dispatched, eff.first=1, eff.deadline=3, dispatch pair (w1, 1)
12. Send(w1):           request 1, key E, payload 20, on the wire               (now=2)
15. Next:               target applies request 1, stores key E; ourApps=1       (now=4)
                        w1's response is never acted on (lost ack)
18. Claim(w2):          wf.epoch=2, wf.owner=w2                                 (now=6)
20. BeginRecovery(w2):  now=6 > deadline 3 + settle 2
22. TResolve(w2):       effect age = 6 - 1 = 5, not > DedupAge, so still tier 1 and not stale:
                        resend; dispatch pair (w2, 2), deadline 8
23. Send(w2):           request 2, key E, payload 20, on the wire
24. Tick:               now=7
25. Prune:              target forgets key E (age 6 > DedupAge)
26. Next:               target applies request 2 as new; ourApps=2               (EffectAtMostOnceTier12 violated)
```

**What it means in the code.** `gate._recover_one` and 5.7 downgrade tier 1 when
`now - first_dispatched_at > dedup_window - DEDUP_MARGIN`. That check runs once, at `T_resolve`. The
resend it authorizes can still be processed up to `send_timeout + settle_margin` later (A2). If the
provider can forget the key inside that interval, the resend is a new refund. The margin is therefore
safe only when

    DEDUP_MARGIN > send_timeout + settle_margin

(plus the `T_resolve` commit latency, which 5.4's stopwatch rule already charges to `send_timeout`).
With Stripe (`dedup_window` 24h, `DEDUP_MARGIN` 600s, `send_timeout` 35s, `settle_margin` 10s) it holds.
It is not checked anywhere, and a target with a short window or a long `send_timeout` breaks it
silently. S04 in the harness uses `dedup_window = 612s`, which holds only because `DEDUP_MARGIN` is 600.

**Fix for the runtime builder.** When a tier-1 target is used, assert
`DEDUP_MARGIN > target.send_timeout + target.settle_margin` and refuse to run otherwise (a startup
error naming the three numbers). Add a unit test with `send_timeout = 700` that expects the refusal.

**In the model:** the target may prune only when
`Age > DedupAge + SendTimeout + SettleMargin` (`PruneOK` in Runtime.tla), which is the constraint
above with `DedupAge` standing for `dedup_window - DEDUP_MARGIN`. With it, EffectAtMostOnceTier12
holds at tier 1 in every interlock run.

---

## Not model checked: the resend's stopwatch

`TResolve` is one atomic step in the model, so its local deadline equals `now + SendTimeout` by
construction. The code has the same begin/commit gap as `T_dispatch`: if the watchdog stopwatch for a
resend starts after `T_resolve` commits, the StopwatchAfterDispatch trace (results/runtime_tlc.md)
applies to the resend unchanged. 5.7's recovery table says "commit; kill point; watchdog; resend",
which reads as the watchdog starting after the commit. Start `t0` before `T_resolve` begins, and
compute `remaining = send_timeout - (monotonic() - t0)` exactly as 5.4 does for the first send.

---

## Baseline (b): Temporal plus the pre-send check. Counterexamples exist.

Mode `temporal_precheck`: the activity of docs/07-runtime.md 11.1 (b). Its reads (lookup by workflow
id, grant, amount against the approval, eligibility) are one step, and the send is a separate step. The
key is `<workflow id>-refund`, stable across retries and resets. The server retries only after the
start-to-close timeout, and an attempt sends only before its own timeout (the baseline's best case).

Every trace is the shortest TLC found, tier 1 with lookup unless stated.

**NoSendUnderRevokedGrant and RevokeLinearizable: revoke between the check and the send.**
```
2. TStart(w1):  attempt 1 starts
3. TCheck(w1):  lookup empty, grant not revoked, amount 20 = approved, eligible
4. Revoke:      grant revoked
5. TSend(w1):   refund 20 sent under the revoked grant
```
The check reads the same `ilr.grants` row the runtime locks, but reads it with a plain SELECT, and the
HTTP send happens after that read, with no lock across the two.

**NoSendOnStalePremise: a hand refund passes the eligibility check.**
```
2. HandRefund:  support refunds 20 by hand
3. TStart(w1)
4. TCheck(w1):  eligibility 20 + 20 <= 100 passes
5. TSend(w1):   refund 20 sent; the decision assumed no prior refund
```
The check tests whether a refund is allowed, not whether the facts the decision (and the approver) saw
still hold. That is the difference the runtime's `premises` carry.

**NoSendAfterCancel: cancel does not reach the running attempt.**
```
2. TStart(w1)
3. Cancel:      workflow cancelled
4. TCheck(w1)
5. TSend(w1):   refund sent after the cancel
```

**NoOverlappingSends and RecoveryRechecks: the retry's lookup runs before the first request is processed.**
```
2. TStart(w1)                        now=0
5. TSend(w1):   request 1 on the wire, processed by time 3
7. TStart(w2):  start-to-close timeout (2) passed: attempt 2 starts, now=2
8. TCheck(w2):  lookup finds nothing yet; checks pass (eligibility, not the decided premises)
9. TSend(w2):   request 2 on the wire while request 1 is unprocessed
```
At tier 1 the key dedupes the second request. At tier 2 the same shape is a duplicate refund
(EffectAtMostOnceTier12, 11 states):
```
 5. TSend(w1):  request 1, processed by time 3        now=1
 7. TStart(w2): retry after the timeout               now=2
 8. TCheck(w2): lookup: not found
 9. Next:       target applies request 1 (ourApps=1)
10. TSend(w2):  request 2
11. Next:       target applies request 2 (ourApps=2)
```

**SendRequiresLiveClaim (events G2): an attempt of a reset run still sends.**
```
2. TStart(w1):  run 1, attempt 1
3. Redecide:    reset to before the decision; run 2 scheduled
4. TCheck(w1)
5. TSend(w1):   run 1's attempt sends although its run is gone
```
Here the stable key and the amount check save (b): run 2 offers 30, the amount check refuses it, and
the workflow-id key dedupes at tier 1. PayloadBound and EffectAtMostOnceTier12 hold for (b) at tier 1.

**Which of these a better check could close** (reasoning, not model checked; a reviewer's better check
goes in as a fourth mode, per 11.1):

| gap | closable inside a Temporal activity? |
|---|---|
| revoke between check and send | only by holding a database transaction with the grant row locked across the HTTP call, which is the runtime's `T_dispatch` without the durable DISPATCHED record |
| hand refund passes eligibility | yes, if the activity is given the decision's premises and compares them (the runtime's `validate_premises`) |
| cancel not seen | partly, with activity heartbeats and a cancellation check just before the send; a check-then-send gap remains |
| retry lookup before the first request settles | yes at tier 2, with a retry initial interval longer than the target's settle time; the runtime makes that interval durable as `send_deadline + settle_margin` |

## Baseline (a): Temporal alone with its recommended key. Counterexamples exist.

Mode `temporal_idem`: no check, key `<run id>-<activity id>`. Everything (b) violates, (a) violates too.
In addition:

**PayloadBound and EffectAtMostOnceTier12: a reset pays 20 + 30.**
```
2. TStart(w1):  run 1, attempt 1
3. Redecide:    reset to before the decision: run 2, the model now says 30
4. TSend(w1):   run 1's attempt sends 20 with key run1
5. Next:        applied (ourApps=1)
6. TStart(w2):  run 2, attempt 1
7. TSend(w2):   sends 30 with key run2, a different key
8. Next:        applied (ourApps=2): the customer receives 50
```

The complete per-tier table (which invariants hold and which are violated in each mode) is in
results/runtime_tlc.md.

@@TEMPORAL_TABLE@@
