# Results: an explained escalation against real Stripe (test mode)

Generated 2026-09-13T23:10:53+00:00 by `experiments/escalation_live.py`. Every step made real Stripe test-mode API calls
on one PaymentIntent, `pi_3UFMXp88KhIqqdFL0YDJ0sBr`. No mock data. The journal is `results/escalation_live.jsonl`; the
receipts, verify output and scoreboard are in `results/escalation_live.json`.

Workflow time (`at`, SLA, decisions) is an injected clock advanced by the script, so a 4h SLA passes
without waiting 4h. Stripe calls, refund ids and webhook deliveries are real and wall clock.

## What happened

| step | wall clock (UTC) | detail |
|---|---|---|
| payment | 2026-09-13T23:10:45+00:00 | payment_intent=pi_3UFMXp88KhIqqdFL0YDJ0sBr, amount=10000 |
| listener | 2026-09-13T23:10:47+00:00 | ready=True |
| request | 2026-09-13T23:10:47+00:00 | request_id=refund-50/pi_3UFMXp88KhIqqdFL0YDJ0sBr, status=QUEUED, reason=needs_judgment, detail=['amount at most 1000 cents'], group=ap-leads |
| approved | 2026-09-13T23:10:47+00:00 | by=ana, status=APPROVED |
| hand refund | 2026-09-13T23:10:49+00:00 | refund=re_3UFMXp88KhIqqdFL0H2qsNzS, amount=3000, status=succeeded |
| send | 2026-09-13T23:10:49+00:00 | status=REFUSED:stale_premise, reason=stale_premise, changes=[{'field': 'refunded_by_others', 'was': 0, 'now': 3000}], repairs=['still_fits'] |
| repair accepted | 2026-09-13T23:10:50+00:00 | by=ana, repair=still_fits, status=COMMITTED |
| second request | 2026-09-13T23:10:50+00:00 | request_id=refund-15/pi_3UFMXp88KhIqqdFL0YDJ0sBr, status=QUEUED, group=ap-leads |
| sla tick | 2026-09-13T23:10:51+00:00 | moved={'refund-15/pi_3UFMXp88KhIqqdFL0YDJ0sBr': 'finance-manager'}, group=finance-manager, level=1, breach=True |
| ap-leads after breach | 2026-09-13T23:10:51+00:00 | by=ana, status=REFUSED:lease |
| approved up the chain | 2026-09-13T23:10:52+00:00 | by=fm, status=COMMITTED |
| confirmation | 2026-09-13T23:10:52+00:00 | path=webhook |

The reviewer saw, on the re-escalation: "a fact this action depends on changed since it was decided. Changed: refunded_by_others was 0, now 3000. Suggested, needs rules or a person: 5000 still fits: 7000 of 10000 is left to refund, if the other refund was not this one".

Refunded on the payment: 9500 cents ($30 by hand, $50 by the agent once, $15 after the SLA
escalation). Refund ids: `re_3UFMXp88KhIqqdFL0H2qsNzS` (hand), `re_3UFMXp88KhIqqdFL00Nz6DsF`, `re_3UFMXp88KhIqqdFL0NNT0LCm`.

## Confirmation by the target

Path used: **webhook**. `stripe listen` forwarded refund events to a local server that passed the raw body and
`Stripe-Signature` header to `confirm.confirm_event`. Deliveries:

- 2026-09-13T23:10:49+00:00 `refund.created`: IGNORED:unknown_effect
- 2026-09-13T23:10:49+00:00 `refund.updated`: IGNORED:unknown_effect
- 2026-09-13T23:10:51+00:00 `refund.created`: CONFIRMED
- 2026-09-13T23:10:51+00:00 `refund.updated`: DUPLICATE_IGNORED
- 2026-09-13T23:10:52+00:00 `refund.created`: CONFIRMED

Events for refunds this journal does not know (the hand refund, other test traffic on the account) are ignored.

## verify()

| request | valid | happened | once | authorized | assumptions held | approved by | approval verified | confirmed by target | escalations |
|---|---|---|---|---|---|---|---|---|---|
| `refund-50/pi_3UFMXp88KhIqqdFL0YDJ0sBr` | True | True | True | True | True | ana | True | True | 2 |
| `refund-15/pi_3UFMXp88KhIqqdFL0YDJ0sBr` | True | True | True | True | True | fm | True | True | 2 |

Problems: none and none. Receipts are unsigned (no key), so they prove internal
consistency, not that the journal was never rebuilt.

## Scoreboard (derived from the journal)

| field | value |
|---|---|
| requests | 2 |
| cleared_no_person | 0 |
| cleared_verified | 0 |
| sent_after_person | 2 |
| rejected | 0 |
| closed_by_repair | 0 |
| open | 0 |
| escalated | 2 |
| stale_approvals_caught | 1 |
| crash_to_person | 0 |
| repairs_suggested | 1 |
| repairs_accepted | 0 |
| sla_breaches | 1 |
| confirmed_by_target | 2 |
| no_person_share | 0.0 |
| escalated_by_reason | {'needs_judgment': 2, 'stale_premise': 1} |
| time_to_decision | {'n': 3, 'median': 1200.0, 'p90': 15360.0, 'max': 15360.0} |

Both requests were over the auto-approve limit by design, so no request cleared without a person here. This run
shows one story working end to end; it is not a measure of how many approvals Interlock removes. Goal: cut two
thirds of manual agent approvals.
