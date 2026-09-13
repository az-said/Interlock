# Results: refund agent, Temporal and Stripe, end to end with real crashes

Generated 2026-09-13 21:57 UTC by `experiments/e2e_live.py`. Model `claude-haiku-4-5-20251001`, temporalio 1.32.0,
Temporal's local dev server, Stripe test mode.

Each cell is one support case: a new $100 test card payment, one $20 refund approved by support (in the case
text, and as the approval's amount cap), a real LLM that reads the payment through a tool and decides the
refund, and a Temporal workflow that runs the decision on a worker process. Mid-refund, the worker kills itself
with SIGKILL. The harness then acts through the backend's HTTP API (a hand refund, a revocation, or nothing),
starts a new worker process, and lets Temporal's retry policy finish the case. Totals and refund counts are
Stripe's own refund list, re-read at the end. "Want" comes from the scenario and the approved $20, never from
the model's output. "Answer" is what the workflow itself reports (sent, refused, or AMBIGUOUS), checked against
the refunds carrying this case's own metadata.

| scenario | Temporal: idempotency key, no re-check in the activity | Temporal: idempotency key plus a hand-written re-check | Temporal with Interlock as the activity body |
|---|---|---|---|
| `crash_after_commit` | REPLAYED_BY_STRIPE; $20 in 1 refund (want $20 in 1); attempt 2, 15.2s crash to close; **held**; answer matches Stripe | FOUND_BY_LOOKUP; $20 in 1 refund (want $20 in 1); attempt 2, 14.7s crash to close; **held**; answer matches Stripe | COMMITTED_BY_RETRY; $20 in 1 refund (want $20 in 1); attempt 8, 44.0s crash to close; **held**; answer matches Stripe |
| `hand_refund_before_decision` | REPLAYED_BY_STRIPE; $25 in 2 refunds (want $25 in 2); attempt 2, 15.1s crash to close; **held**; answer matches Stripe | FOUND_BY_LOOKUP; $25 in 2 refunds (want $25 in 2); attempt 2, 14.7s crash to close; **held**; answer matches Stripe | COMMITTED_BY_RETRY; $25 in 2 refunds (want $25 in 2); attempt 8, 42.8s crash to close; **held**; answer matches Stripe |
| `hand_refund_during_outage` | REFUNDED; $40 in 2 refunds (want $20 in 1); attempt 2, 16.8s crash to close; **VIOLATED, $20 too much**; answer matches Stripe | REFUSED:stale_premise; $20 in 1 refund (want $20 in 1); attempt 2, 16.0s crash to close; **held**; answer matches Stripe | REFUSED:stale_premise_at_recovery; $20 in 1 refund (want $20 in 1); attempt 8, 43.6s crash to close; **held**; answer matches Stripe |
| `unrelated_refund_during_outage` | REFUNDED; $25 in 2 refunds (want $25 in 2); attempt 2, 16.5s crash to close; **held**; answer matches Stripe | REFUSED:stale_premise; $5 in 1 refund (want $25 in 2); attempt 2, 15.7s crash to close; **SHORT by $20**; answer matches Stripe | REFUSED:stale_premise_at_recovery; $5 in 1 refund (want $25 in 2); attempt 8, 43.3s crash to close; **SHORT by $20**; answer matches Stripe |
| `approval_revoked_during_outage` | REFUNDED; $20 in 1 refund (want $0 in 0); attempt 2, 16.8s crash to close; **VIOLATED, $20 too much**; answer matches Stripe | REFUSED:lease; $0 in 0 refunds (want $0 in 0); attempt 2, 16.0s crash to close; **held**; answer matches Stripe | REFUSED:lease_at_recovery; $0 in 0 refunds (want $0 in 0); attempt 8, 43.6s crash to close; **held**; answer matches Stripe |
| `approval_revoked_after_commit` | REPLAYED_BY_STRIPE; $20 in 1 refund (want $20 in 1); attempt 2, 14.8s crash to close; **held**; answer matches Stripe | FOUND_BY_LOOKUP; $20 in 1 refund (want $20 in 1); attempt 2, 14.8s crash to close; **held**; answer matches Stripe | COMMITTED_ON_QUERY; $20 in 1 refund (want $20 in 1); attempt 8, 43.3s crash to close; **held**; answer matches Stripe |
| `key_pruned_after_24h` (EMULATED) | REFUNDED; $40 in 2 refunds (want $20 in 1); attempt 2, 15.9s crash to close; **VIOLATED, $20 too much**; answer CONTRADICTS Stripe | FOUND_BY_LOOKUP; $20 in 1 refund (want $20 in 1); attempt 2, 15.0s crash to close; **held**; answer matches Stripe | COMMITTED_ON_QUERY; $20 in 1 refund (want $20 in 1); attempt 8, 43.1s crash to close; **held**; answer matches Stripe |
| `no_lookup_after_24h` (EMULATED) | n/a | n/a | AMBIGUOUS; $20 in 1 refund (want $20 in 1); attempt 8, 42.1s crash to close; **held**; answer matches Stripe |

Over the 7 rows every column ran (6 of them not emulated):

- Temporal: idempotency key, no re-check in the activity: 4/7 left Stripe as wanted (4/6 of the rows that are not emulated), 6/7 answers matched Stripe, 7/7 completed with a known outcome, median 16s from crash to close
- Temporal: idempotency key plus a hand-written re-check: 6/7 left Stripe as wanted (5/6 of the rows that are not emulated), 7/7 answers matched Stripe, 7/7 completed with a known outcome, median 15s from crash to close
- Temporal with Interlock as the activity body: 6/7 left Stripe as wanted (5/6 of the rows that are not emulated), 7/7 answers matched Stripe, 7/7 completed with a known outcome, median 43s from crash to close

Read the tally with this next to it: on 7/7 of those rows the hand-written re-check left
Stripe with the same refunds, and gave the same answer, as Interlock (rows that differ: none). Both beat the
column that re-checks nothing. So the difference from a careful Temporal activity is not the outcome in these
rows; it is that Interlock packages the re-check, the lookup after a crash and the claim once, instead of about
ten hand-written lines per activity, and adds AMBIGUOUS and a receipt. Interlock is also slower after every crash;
see "Timing" below. Not in the tally (run for Interlock only): `no_lookup_after_24h` / interlock: AMBIGUOUS; $20 in 1 refund (want $20 in 1); attempt 8, 42.1s crash to close; **held**; answer matches Stripe.

## Scenarios

- `crash_after_commit`: worker SIGKILLed after Stripe's response to the refund POST arrived, before anything recorded it; worker restarted
- `hand_refund_before_decision`: support refunds an unrelated $5 by hand before any worker runs the case, so the model reads a payment with $5 already refunded; then worker SIGKILLed after Stripe's response to the refund POST arrived, before anything recorded it; worker restarted. Want: both, $25 in 2 refunds
- `hand_refund_during_outage`: worker SIGKILLed right before the refund POST; support refunds the same $20 by hand in Stripe; worker restarted. Want: only the hand refund
- `unrelated_refund_during_outage`: worker SIGKILLed right before the refund POST; support issues an unrelated $5 goodwill refund by hand; worker restarted. Want: both, $25 in 2 refunds
- `approval_revoked_during_outage`: worker SIGKILLed right before the refund POST; the approval is revoked; worker restarted. Want: nothing
- `approval_revoked_after_commit`: worker SIGKILLed after Stripe's response to the refund POST arrived, before anything recorded it; the approval is revoked; worker restarted. Want: the one refund that landed while the approval was live, reported as sent
- `key_pruned_after_24h`: worker SIGKILLed after Stripe's response to the refund POST arrived, before anything recorded it; restarted with Stripe's memory of the key EMULATED as gone (and, for Interlock only, its clock moved 25h)
- `no_lookup_after_24h`: as key_pruned_after_24h, with a target that cannot look refunds up (EMULATED). Want: no second refund, and an honest AMBIGUOUS

## The three columns

- **Temporal, no re-check**: Temporal's retry policy, and a Stripe refund with Idempotency-Key = workflow run id +
  "/" + activity id (the key Temporal's docs suggest). The activity body re-checks nothing. This is "Temporal
  alone" as pitched, not the best a Temporal user can do.
- **Temporal plus a hand-written re-check**: the same, and at the top of the activity, in about ten lines: if a
  refund carrying this workflow's id is already in Stripe, report it (`FOUND_BY_LOOKUP`) and stop; otherwise the
  approval must be live and cover the amount, and the payment's refunds must be unchanged since the decision. A
  careful Temporal user can write this. The other documented Temporal route is a Signal (for example from the
  revocation, or from a Stripe `refund.created` webhook) that cancels the pending activity; this column does not
  use it. In this harness the retry cannot start until the new worker is up, so such a Signal would arrive first.
- **Interlock**: `interlock.temporal.gated()` as the activity body: a journaled intent before the send, a claim so
  no two workers send it at once, the lease and premises re-checked on the recovery path, a Stripe lookup when the
  key cannot be trusted, and a receipt recording what was checked.

## What the pitch can claim from this run

- "Temporal" should read "Temporal alone: an activity that does not re-read the world". Against that column,
  Interlock kept the hand refund during an outage from becoming a second $20 refund object, and kept a revoked
  approval from being used. A Temporal activity with the re-check above does the same; Interlock makes that
  re-check, and telling "my refund already landed" apart from "the world changed" after a crash, the default instead
  of something each activity author must remember.
- Within Stripe's key window, the idempotency key already answers "did it happen" and "may I retry": plain
  Temporal held `crash_after_commit`. What nothing checks without extra code is whether the refund is still
  allowed, whether the payment changed since the decision, and whether the key still exists after the window.
- Reproduced in Stripe test mode: the hand refund during an outage. Emulated, not reproduced: Stripe forgetting the
  key, by sending a key Stripe has never seen, because Stripe cannot be made to forget a key on demand.
- Interlock notices that the payment's refunds changed after the decision and stops for a person. It does not tell
  a duplicate from an unrelated refund, so it does not "recognize the same action arriving as a different request".
- The receipt is the gate's attestation: a hash-chained record, unsigned here, of what the gate observed. It is not
  proof; the evidence that a refund happened once is Stripe's refund list, re-read by `experiments/e2e_audit.py`.

## Timing

From the crash to the workflow closing, the median Interlock cell took 43s against
16s and 15s for the two Temporal columns. A SIGKILLed sender cannot release its
claim, so later attempts return IN_FLIGHT until the claim expires (`CLAIM_TTL` = 40s in `backend/config.py`, longer
than the Stripe client's 30s timeout so recovery never overlaps a send still in progress), and then one attempt
recovers. That wait is the price of never having two workers send the same effect at the same time; the Temporal
columns rely on Stripe's idempotency key for that, which holds only inside the key window.

## Limits of what this shows

- The premise is "the payment's refunds are what they were when the model decided". Interlock does not recognize a
  hand refund as the same action; it refuses because the refunds changed. `unrelated_refund_during_outage` shows
  the cost: a $5 goodwill refund also stops the approved $20, and a person has to re-approve. A hand refund made
  before the model decides is part of that premise, so it does not stop the refund (`hand_refund_before_decision`).
- The `after_commit` crash comes after Stripe's full response was received and parsed, before anything durable
  recorded it (the journal, or Temporal's history). The connection is never cut mid-response. Recovery sees the
  same state as a response lost in transit: Stripe has the refund, nothing on this side does. The outage rows crash
  before the send.
- Which recovery path an Interlock cell took is its receipt's `via` in the ids list below: `retry-idempotent` means
  it resent under the same key and Stripe replayed it; `recovery-query` means it asked Stripe. Outside the emulated
  rows, the lookup runs only when a re-check fails after a commit.
- AMBIGUOUS is produced end to end only in the emulated `no_lookup_after_24h` row, because Stripe can always be
  looked up.
- Receipts here are unsigned (verify reports signed=None), written by the same worker that sends. Each check the
  gate records carries what it read: the approval row (amount cap, revoked time) and the premise violations, where
  none means Stripe's refunds read back as recorded. Commits carry Stripe's refund id and whether Stripe replayed
  it, or the refund id a lookup found. A re-check that failed before a lookup found the refund is recorded too
  ("re-check at recovery" below). authorized_when_fired and assumptions_held are None when nothing fired.

## What is real

- Stripe: every payment, refund, lookup and idempotency replay is a real test-mode API call. No mock.
- LLM: every decision is a real Anthropic Messages API call; the model calls `get_payment` (a real Stripe
  read) and then `issue_refund`. Its output is validated before use, including against the approved amount.
  Temporal records the decision, so a retry does not ask the model again.
- Temporal: a real dev server, real workflow and activity retries, workers as separate OS processes. A refund
  activity that fails for any reason other than a refusal fails the workflow.
- Crashes: `os.kill(os.getpid(), SIGKILL)` in the worker, one-shot via a marker file. Exit code -9 is recorded per cell.
- Outage actions: a hand refund is a plain Stripe refund with no idempotency key and no metadata, as from
  the dashboard. A revocation updates the approval in SQLite, read by the worker process.

## What is emulated

Only the rows marked EMULATED. Nobody waited 24 hours.

`key_pruned_after_24h`: Stripe keeps an idempotency key for at least 24 hours and cannot be made to forget one on demand, and nobody waited a day. The columns do not get the same emulated input. All three: after the restart, each refund POST uses Idempotency-Key '<original key>/emulated-pruned', a key Stripe has never seen, which is how a pruned key looks to Stripe (INTERLOCK_EMULATE_24H=1). Interlock only: its gate also recovers with its clock moved 25h ahead (EmulatedClockGate in backend/workflows.py), standing in for the day that would really have passed. Interlock's result in this row depends on that clock, not on the key: the gate compares the clock with the timestamp of its DISPATCHED entry, finds it older than Stripe's 24h window, and looks the refund up instead of resending, so it never sends the pruned key. Given the pruned key without the moved clock, it would resend under the pruned key and create a second refund, as plain Temporal did (read from gate.py, not run: a key lost inside 24h is outside what Stripe documents). The hand-written re-check column needs no clock, because it looks up its own refund before every send; a Temporal activity could also compare activity.info().scheduled_time with now. The timing is emulated too: the retry came seconds after the crash. In this workflow a retry that late happens if no worker picks the task up for more than 24h (an attempt only starts, and only times out, once a worker takes it), or with a retry policy, schedule or reconciler that spans more than a day. What this row shows is that a key alone does not survive pruning and a lookup does.

`no_lookup_after_24h`: Emulated as in key_pruned_after_24h (pruned key, gate clock 25h ahead), and the Interlock target also declares that it cannot list refunds (INTERLOCK_NO_LOOKUP=1), as for a provider with no way to look up what it did. Stripe itself can list refunds. Run for Interlock only: it shows the gate saying AMBIGUOUS instead of guessing.

## LLM decisions

- `crash_after_commit` / temporal: 2000 cents, "Partial refund approved for cracked glass jar - Support case #4471"
- `crash_after_commit` / temporal_checked: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Support case #4471)"
- `crash_after_commit` / interlock: 2000 cents, "Partial refund for cracked glass jar - customer retains blender (Support case #4471)"
- `hand_refund_before_decision` / temporal: 2000 cents, "Partial refund approved for cracked glass jar - customer retains blender. Support case #4471."
- `hand_refund_before_decision` / temporal_checked: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender. Support case #4471 approved $20.00 refund."
- `hand_refund_before_decision` / interlock: 2000 cents, "Partial refund for cracked glass jar - Order #881 Support Case #4471. Customer keeps blender."
- `hand_refund_during_outage` / temporal: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Support case #4471)"
- `hand_refund_during_outage` / temporal_checked: 2000 cents, "Partial refund for cracked glass jar on blender - Support case #4471 approved"
- `hand_refund_during_outage` / interlock: 2000 cents, "Partial refund for cracked glass jar. Customer approved refund of $20.00 while keeping the blender. Support case #4471."
- `unrelated_refund_during_outage` / temporal: 2000 cents, "Partial refund approved for cracked glass jar - customer retains blender (Support case #4471)"
- `unrelated_refund_during_outage` / temporal_checked: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender. Support case #4471"
- `unrelated_refund_during_outage` / interlock: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Support case #4471)"
- `approval_revoked_during_outage` / temporal: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Support case #4471)"
- `approval_revoked_during_outage` / temporal_checked: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Support case #4471)"
- `approval_revoked_during_outage` / interlock: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender. Case #4471 approved."
- `approval_revoked_after_commit` / temporal: 2000 cents, "Partial refund for cracked glass jar (support case #4471) - customer keeps blender"
- `approval_revoked_after_commit` / temporal_checked: 2000 cents, "Partial refund for cracked glass jar - Support case #4471 approved"
- `approval_revoked_after_commit` / interlock: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Support case #4471)"
- `key_pruned_after_24h` / temporal: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender. Support case #4471 approved $20.00 refund."
- `key_pruned_after_24h` / temporal_checked: 2000 cents, "Partial refund for cracked glass jar - customer keeps blender. Support case #4471 approved."
- `key_pruned_after_24h` / interlock: 2000 cents, "Partial refund approved for cracked glass jar - customer retains blender. Support case #4471"
- `no_lookup_after_24h` / interlock: 2000 cents, "Partial refund for cracked glass jar - customer keeping blender (Support case #4471)"

## Ids, for checking in the Stripe test dashboard

- `crash_after_commit` / temporal: PaymentIntent `pi_3UFLCJ88KhIqqdFL0ztvENXN`, workflow `refund-case-a5a52df220f4`, refunds `re_3UFLCJ88KhIqqdFL0sttM6ck`, worker exit -9
- `crash_after_commit` / temporal_checked: PaymentIntent `pi_3UFLCh88KhIqqdFL0fhR3J3C`, workflow `refund-case-60135745c493`, refunds `re_3UFLCh88KhIqqdFL0SYAwdkC`, worker exit -9
- `crash_after_commit` / interlock: PaymentIntent `pi_3UFLD488KhIqqdFL0yyILFry`, workflow `refund-case-2bec0a15821d`, refunds `re_3UFLD488KhIqqdFL0vZXMcLB`, worker exit -9, receipt `COMMITTED` via `retry-idempotent` (valid=True, signed=None, happened=True, authorized_when_fired=True, assumptions_held=True, evidence `refund re_3UFLD488KhIqqdFL0vZXMcLB (already_processed)`, re-check at recovery: passed)
- `hand_refund_before_decision` / temporal: PaymentIntent `pi_3UFLDw88KhIqqdFL0KrZwtXO`, workflow `refund-case-45ebe5c11858`, refunds `re_3UFLDw88KhIqqdFL0qyQgg4X`, `re_3UFLDw88KhIqqdFL0uwVEBVM`, worker exit -9
- `hand_refund_before_decision` / temporal_checked: PaymentIntent `pi_3UFLEM88KhIqqdFL0HFZSgIt`, workflow `refund-case-5a98bfa60198`, refunds `re_3UFLEM88KhIqqdFL0zPqKEnk`, `re_3UFLEM88KhIqqdFL0pLhEqoB`, worker exit -9
- `hand_refund_before_decision` / interlock: PaymentIntent `pi_3UFLEl88KhIqqdFL14RIXZOb`, workflow `refund-case-6a860c8c08db`, refunds `re_3UFLEl88KhIqqdFL1Baf5aiR`, `re_3UFLEl88KhIqqdFL1F0bp1E9`, worker exit -9, receipt `COMMITTED` via `retry-idempotent` (valid=True, signed=None, happened=True, authorized_when_fired=True, assumptions_held=True, evidence `refund re_3UFLEl88KhIqqdFL1Baf5aiR (already_processed)`, re-check at recovery: passed)
- `hand_refund_during_outage` / temporal: PaymentIntent `pi_3UFLFc88KhIqqdFL1GYvMoH5`, workflow `refund-case-9c7d47d97c03`, refunds `re_3UFLFc88KhIqqdFL1wespZDi`, `re_3UFLFc88KhIqqdFL1tMmzYZw`, worker exit -9
- `hand_refund_during_outage` / temporal_checked: PaymentIntent `pi_3UFLG288KhIqqdFL0RojYZFC`, workflow `refund-case-cb569da91f13`, refunds `re_3UFLG288KhIqqdFL0nyY6K7S`, worker exit -9
- `hand_refund_during_outage` / interlock: PaymentIntent `pi_3UFLGR88KhIqqdFL0CRX2N3s`, workflow `refund-case-2c6cf93e2009`, refunds `re_3UFLGR88KhIqqdFL0Iw28eMm`, worker exit -9, receipt `REFUSED` (valid=True, signed=None, happened=False, authorized_when_fired=None, assumptions_held=None, re-check at recovery: premises changed: refunded by others: was 0, now 2000, refused='stale_premise at recovery')
- `unrelated_refund_during_outage` / temporal: PaymentIntent `pi_3UFLHI88KhIqqdFL0Gu4S5tX`, workflow `refund-case-e1b335661018`, refunds `re_3UFLHI88KhIqqdFL0M6Be6Ph`, `re_3UFLHI88KhIqqdFL0hRY4pyV`, worker exit -9
- `unrelated_refund_during_outage` / temporal_checked: PaymentIntent `pi_3UFLHg88KhIqqdFL0t7YjYVe`, workflow `refund-case-ab11cc394068`, refunds `re_3UFLHg88KhIqqdFL0RXq9T8P`, worker exit -9
- `unrelated_refund_during_outage` / interlock: PaymentIntent `pi_3UFLI488KhIqqdFL06jKY2GF`, workflow `refund-case-c707abca4b95`, refunds `re_3UFLI488KhIqqdFL0PIfGTmF`, worker exit -9, receipt `REFUSED` (valid=True, signed=None, happened=False, authorized_when_fired=None, assumptions_held=None, re-check at recovery: premises changed: refunded by others: was 0, now 500, refused='stale_premise at recovery')
- `approval_revoked_during_outage` / temporal: PaymentIntent `pi_3UFLIu88KhIqqdFL1t09U4v0`, workflow `refund-case-932a20ddc4e6`, refunds `re_3UFLIu88KhIqqdFL13ma9bra`, worker exit -9
- `approval_revoked_during_outage` / temporal_checked: PaymentIntent `pi_3UFLJJ88KhIqqdFL0p816tcU`, workflow `refund-case-01a6508b806b`, refunds none, worker exit -9
- `approval_revoked_during_outage` / interlock: PaymentIntent `pi_3UFLJi88KhIqqdFL1ScyHvYz`, workflow `refund-case-74cc6f3789ee`, refunds none, worker exit -9, receipt `REFUSED` (valid=True, signed=None, happened=False, authorized_when_fired=None, assumptions_held=None, re-check at recovery: approval revoked, refused='lease at recovery')
- `approval_revoked_after_commit` / temporal: PaymentIntent `pi_3UFLKZ88KhIqqdFL0wXc5mIb`, workflow `refund-case-7b2bada89027`, refunds `re_3UFLKZ88KhIqqdFL0gWLvaWY`, worker exit -9
- `approval_revoked_after_commit` / temporal_checked: PaymentIntent `pi_3UFLKx88KhIqqdFL1chvXgVQ`, workflow `refund-case-d470e9e94b37`, refunds `re_3UFLKx88KhIqqdFL1BWmSm4f`, worker exit -9
- `approval_revoked_after_commit` / interlock: PaymentIntent `pi_3UFLLL88KhIqqdFL1rOXb7KZ`, workflow `refund-case-6bacaf2358e8`, refunds `re_3UFLLL88KhIqqdFL1nHHCzLv`, worker exit -9, receipt `COMMITTED` via `recovery-query` (valid=True, signed=None, happened=True, authorized_when_fired=True, assumptions_held=True, evidence `re_3UFLLL88KhIqqdFL1nHHCzLv`, re-check at recovery: approval revoked)
- `key_pruned_after_24h` / temporal: PaymentIntent `pi_3UFLMD88KhIqqdFL0YfikdAU`, workflow `refund-case-7e950f912412`, refunds `re_3UFLMD88KhIqqdFL0mPmfCpd`, `re_3UFLMD88KhIqqdFL0Z9Gizi0`, worker exit -9
- `key_pruned_after_24h` / temporal_checked: PaymentIntent `pi_3UFLMb88KhIqqdFL0SAT5p00`, workflow `refund-case-78b66e77feaf`, refunds `re_3UFLMb88KhIqqdFL0eZepcOf`, worker exit -9
- `key_pruned_after_24h` / interlock: PaymentIntent `pi_3UFLMz88KhIqqdFL15ms0IEw`, workflow `refund-case-4c3b9ced729c`, refunds `re_3UFLMz88KhIqqdFL1ujDkkHe`, worker exit -9, receipt `COMMITTED` via `recovery-query` (valid=True, signed=None, happened=True, authorized_when_fired=True, assumptions_held=True, evidence `re_3UFLMz88KhIqqdFL1ujDkkHe`, re-check at recovery: passed)
- `no_lookup_after_24h` / interlock: PaymentIntent `pi_3UFLNp88KhIqqdFL19fBdxOL`, workflow `refund-case-715746517075`, refunds `re_3UFLNp88KhIqqdFL1o1fWcTL`, worker exit -9, receipt `AMBIGUOUS` (valid=True, signed=None, happened=unknown, authorized_when_fired=True, assumptions_held=True)

## Re-run

    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python experiments/e2e_live.py
    python3 experiments/e2e_audit.py      # independent check of results/e2e_live.json against Stripe
