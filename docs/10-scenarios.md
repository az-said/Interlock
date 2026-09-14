# 10. Real-world scenarios: Interlock against a standard setup and a fair hand-written check

`results/e2e_live.md` showed that a hand-written pre-send check ties Interlock on money in the refund scenarios.
This suite asks whether that holds in other real services. Each scenario runs the same agent step against three
systems, with a real crash (SIGKILL of the agent or worker OS process) and ground truth read back from the real
service:

- **no_check**: the standard setup. A stable idempotency key or the service's native dedup, retry on restart, no re-check.
- **hand_check**: the idiomatic check a competent engineer writes, including the service's native preconditions
  (GitHub merge `sha`, Calendar client-supplied event id, GCS `ifGenerationMatch`, a Stripe lookup by metadata).
- **interlock**: the same step behind `interlock.gate.Gate` or `interlock.easy`, recovery on restart.

Every number below is copied from a file under `results/scenarios/`. Each scenario's `.md` there has the full
table, the ids to check in each service, what was emulated, and the re-run command.

## Results

"held" is the scenario's invariant, judged from the service's own state. "proof" is `can_prove_what_happened`: the
system left a record naming who did what and which checks ran, and that record agrees with the service. Each
scenario scores proof from the records it kept, so the bar differs slightly per scenario (for example, calendar's
hand_check keeps no record of its checks and scores 0; billing_credit's hand_check logs every check and scores 6/6).
"settle" is seconds from crash to settled, as each scenario defines it.

| scenario | system | held | proof | settle (s) | source |
|---|---|---|---|---|---|
| stripe_dispute | no_check | 2/2 | 0/2 | 6.8, 8.6 | `results/scenarios/stripe_dispute.md` |
| | hand_check | 2/2 | 2/2 | 6.4, 11.2 | same |
| | interlock | 2/2 | 2/2 | 42.4, 43.0 | same |
| shared_cap | no_check | 0/40 | 0/40 | median 1.1 / 2.3 | `results/scenarios/shared_cap.md` |
| | hand_check (no shared state) | 4/40 | 0/40 | median 1.1 / 2.3 | same |
| | hand_lock (hand_check inside an flock) | 40/40 | 0/40 | median 0.5 / 1.4 | same |
| | interlock_core (unmodified Gate) | 25/40 | 40/40 | median 40.1 / 41.0 | same |
| | interlock + CapJournal (scenario subclass) | 40/40 | 40/40 | median 40.1 / 41.7 | same |
| billing_credit | no_check | 5/6 | 0/6 | median 17 (13.7 to 25.7) | `results/scenarios/billing_credit.md` |
| | hand_check | 6/6 | 6/6 | median 17 (14.1 to 23.7) | same |
| | interlock | 6/6 | 6/6 | median 41 (41.0 to 41.8) | same |
| github_merge | no_check | 3/6 | 0/6 | median 8.5 / 2.4 | `results/scenarios/github_merge.md` |
| | hand_check | 6/6 | 6/6 | median 7.7 / 2.5 | same |
| | interlock | 6/6 | 6/6 | median 26.1 / 24.4 | same |
| calendar | no_check | 5/7 | 0/7 | median 0.6 | `results/scenarios/calendar.md` |
| | hand_check | 7/7 | 0/7 | median 0.6 | same |
| | interlock (slot premise must be empty) | 7/7 | 7/7 | median 31.2 | same |
| | interlock_change_only (easy.py as shipped) | 0/1 | 1/1 | 31.5 | same |
| email_tier3 | no_check | 2/3 | 0/3 | median 2 | `results/scenarios/email_tier3.md` |
| | hand_check (with key probe) | 3/3 | 3/3 | median 3 | same |
| | hand_check_noprobe (idiomatic) | 3/3 | 2/3 | median 2 | same |
| | interlock (with key probe) | 3/3 | 3/3 | median 37 | same |
| | interlock_noprobe | 3/3 | 1/3 | median 36 | same |
| | interlock_tier3 | 3/3 | 0/3 | median 36 | same |
| gcp_resource | no_check | 0/3 | 0/3 | 0.4 to 2.0 | `results/scenarios/gcp_resource.md` |
| | hand_check | 3/3 | 3/3 | 0.5 to 2.1 | same |
| | interlock | 3/3 | 3/3 | 30.6 to 30.9 | same |
| connect_payout | all | BLOCKED | BLOCKED | not run | `results/scenarios/connect_payout.md` |

Where two settle values are separated by "/", they are the two crash points in the scenario's table order
(shared_cap: `after_commit` / `before_send`; github_merge: `before_send` / `after_commit`). stripe_dispute lists
its two cells in table order. Cell counts: github_merge is 3 repetitions of 2 faults
(`results/scenarios/github_merge.json` `repeats: 3`); shared_cap is 20 runs of 2 crash points
(`results/scenarios/shared_cap.json` `reps: 20`).

## Better, equal or worse than hand_check

- **stripe_dispute: equal.** Money and record completeness tie; Stripe's own guards did the work (it refuses a
  refund on a charged-back charge, and in test mode refunds sent seconds before the chargeback ended `failed`).
  Interlock is better only on tamper evidence (an altered receipt copy fails `verify()`; the plain log has no
  verifier, and neither is signed) and worse on time, 42 to 43s against 6 to 11s. No column catches a chargeback
  that lands minutes after a refund succeeded: the gap probe lost $120 on a $100 payment in test mode.
  (`results/scenarios/stripe_dispute.md`, Reading)
- **shared_cap: equal on money against the fair arm, worse on time, better on record.** Against the spec's
  no-shared-state hand_check (4/40), interlock + CapJournal (40/40) is better, but hand_lock, the same check inside
  a five-line `fcntl.flock`, also held 40/40 and settled in 0.5s / 1.4s against 40.1s / 41.7s. Interlock's edge is
  the record, 40/40 against 0/40. Unmodified Interlock (interlock_core) held only 25/40, worse than hand_lock, so the
  40/40 is evidence for a proposed core hook, not for the current core. (`results/scenarios/shared_cap.md`, Reading it)
- **billing_credit: equal.** Both held 6/6 and both records agree with Stripe. no_check failed the one row that
  matters (it re-credited after billing's same-incident SLA credit note). Interlock is better only on tamper evidence
  (unsigned hash chain against a plain log) and worse on time, median 41s against 17s.
  (`results/scenarios/billing_credit.md`, Verdict)
- **github_merge: equal.** Both held 6/6 with matching answers; GitHub's `sha` merge precondition is what refused
  the stale merge, and the head re-read alone passed on a lagging read in 3/3 restarts. With a key held by the
  harness, both records are equally tamper-evident (unsigned receipt chains accepted 6/6 forgeries; keyed verify
  accepted 0/6). Interlock is marginally better on structure and worse on time, median about 25s against about 5s.
  (`results/scenarios/github_merge.md`, Records and Findings)
- **calendar: equal as configured here, worse as `interlock.easy` ships, better on record.** hand_check and
  interlock differ on no row, but only because the scenario overrides the slot premise to require an empty slot.
  With `easy.py` as shipped (a premise only has to stay unchanged), interlock_change_only double booked on
  `before_send/pre_busy`, where hand_check refused. Interlock's receipt is the only record of the checks (7/7
  against 0/7) and records the failed re-check at recovery after a commit. Worse on time, median 31.2s against 0.6s.
  (`results/scenarios/calendar.md`, Verdict)
- **email_tier3: equal against the strongest hand_check, better against the idiomatic one only with an
  undocumented probe.** Emails tie everywhere. hand_check with the key probe gives the same answer as Interlock on
  every fault. hand_check_noprobe logged `SKIPPED:refund_failed` in `refused_after_send` while the email had gone
  out; Interlock answered correctly there using the same undocumented probe, and on documented features alone
  (interlock_noprobe) it answers AMBIGUOUS, "cannot know" rather than wrong. Better on record, worse on time (about
  36s against about 3s). Past Resend's 24h key window hand_check would send a second email while Interlock would say
  AMBIGUOUS, read from code and not run. (`results/scenarios/email_tier3.md`, Better, equal, worse)
- **gcp_resource: equal on object, answer and record, worse on time.** Both held 3/3 and both records prove 3/3;
  GCS's `ifGenerationMatch` plus a version lookup by job id in hand_check matches Interlock's tier 2 query. Interlock
  took about 31s against about 2s. An earlier Interlock win came from a weak hand_check and disappeared once
  hand_check did the ten-line lookup. (`results/scenarios/gcp_resource.md`, Verdict)
- **connect_payout: no verdict.** BLOCKED, see below. The offline tests predict a tie on money with hand_check;
  that is a prediction, not a result. (`results/scenarios/connect_payout.md`)

**Across the seven scenarios that ran:** Interlock never beat the strongest hand-written arm on what the service
ended up holding. It tied on all seven, and in two of them only with code outside the core (the calendar premise
override, the shared_cap CapJournal subclass); without that code it lost both (a double booking; 25/40 held). It
was slower to settle in all seven because a SIGKILLed sender's claim must expire before recovery, with scenario
TTLs of 25 to 40s (`claim_ttl` or `CLAIM_TTL` in each scenario md). Its consistent advantage is the record: a
structured, hash-chained receipt that `verify()` re-derives verdicts from, which is tamper-evident only when signed
with a key the writer does not hold (`results/scenarios/github_merge.md`, Records). no_check violated its invariant
in six of seven scenarios (all but stripe_dispute).

## Blocked

- **connect_payout (Stripe Connect seller payout).** Stripe Connect is not enabled on the test platform
  `acct_1TJzu288KhIqqdFL`. `POST /v1/accounts` (express, standard, custom) returned `400 ... You can only create new
  accounts if you've signed up for Connect`, `POST /v2/core/accounts` returned `You must have Connect enabled to use
  this field`, and `GET /v1/accounts` returned 0 connected accounts (`results/scenarios/connect_payout.json`,
  `error` and `probe`). **To unblock:** the Stripe account owner signs up for Connect on the test account at
  https://dashboard.stripe.com/connect, then runs `python3 experiments/scenario_connect_payout.py` unchanged.

## Not attempted, for lack of credentials

No code and no results file exist for these.

- **Shipping labels** (buy a label, crash, a void or address change during the outage): needs an EasyPost or Shippo
  test API key.
- **Shopify order cancel** (cancel an order while fulfillment moves): needs a Shopify Partner development store and
  an Admin API access token for it.
- **HubSpot deal stage** (move a deal while a person edits it): needs a HubSpot developer account and a private app
  token.

## Proposed core changes, from the scenario reports

None were made; `interlock/gate.py`, `journal.py` and `receipts.py` were not edited by this suite.

1. **Cap reservation at dispatch.** `Journal.dispatch(..., reserve=fn)`, with `fn(entries, effect)` run inside the
   same lock or transaction as the DISPATCHED write, returning a refusal reason, and `Gate.submit` returning
   `REFUSED:<reason>` instead of `IN_FLIGHT` for it. Measured need: interlock_core held 25/40 without it, CapJournal
   40/40 with it. (`results/scenarios/shared_cap.md`, Proposed core change)
2. **Claim liveness.** A claim cannot tell a dead sender from a slow one, so recovery waits the full TTL; hand_lock's
   flock is released by the kernel at once. Proposed: record the claim owner (pid and host, or a per-sender lock or
   heartbeat) so recovery takes over as soon as the owner is known dead. This is the time loss in every scenario
   above; with the core default `CLAIM_TTL` of 120s (`interlock/journal.py`) it would be about 120s.
   (`results/scenarios/shared_cap.md`, Verdict; `results/scenarios/stripe_dispute.md`, "Interlock is slower")
3. **Premises with an expected value.** Let `gate.effect` declare `expect={"other_events_in_slot": []}` that
   `validate_premises` enforces at dispatch and recovery, alongside "unchanged since decided". Without it the
   shipped `easy.py` double booked. (`results/scenarios/calendar.md`, The systems)
4. **Keep what the target returned.** `easy._FunctionTarget.query` should return the lookup's value (a refund id,
   an event) instead of `bool()`, and `apply` should record the function's result instead of `{"status": "ok"}`.
   (`results/scenarios/stripe_dispute.md`, Reading; `results/scenarios/calendar.md`, The systems)
5. **Do not overclaim tamper evidence.** `verify()` reports `tamper_evident` for an unsigned chain
   (`interlock/receipts.py`), yet a rewritten final entry with a recomputed hash passed 6/6. Rename it
   `chain_consistent`, or set it only when signed; optionally anchor the chain head with an outside key holder at
   settle time. (`results/scenarios/github_merge.md`, Records and what they prove)
6. **Record what happened after the commit.** A receipt says `happened: true` for a Stripe refund that was accepted
   and then failed when the chargeback posted. Proposed: a journal entry appended by a later lookup or a
   `refund.failed` webhook that `verify()` reports as settled or reversed. A chargeback minutes after a refund
   succeeded needs a post-commit watch, not a pre-send premise. (`results/scenarios/stripe_dispute.md`, Reading)
7. **Make a blocked recovery visible.** After a SIGKILL, `Gate.recover()` skips an effect whose dead sender's claim
   is still live, returns nothing, and the next `submit` says `IN_FLIGHT`, so workers poll
   (`scenarios/connect_payout/worker.py`, `interlock()`). Proposed: report such effects as `CLAIMED` with the claim's
   expiry, or accept `wait=True`.
8. **Optional:** a `receipts` helper that writes the bundle next to the journal at `recover()`, so harnesses stop
   deleting receipts with their state dirs. billing_credit needed no core change
   (`results/scenarios/billing_credit.md`, Verdict).

## Re-run

    python3 experiments/scenario_<key>.py        # live; keys: stripe_dispute shared_cap connect_payout billing_credit github_merge calendar email_tier3 gcp_resource
    python3 -m unittest tests.test_scenario_<key>   # offline logic
