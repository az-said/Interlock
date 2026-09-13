# Results: durable execution on a real Temporal server

Generated 2026-09-13 17:15 UTC by `experiments/temporal_live.py` with temporalio 1.32.0
and Temporal's local dev server. The refund step is a Temporal activity; Temporal's retry
policy schedules every retry. Invariant: exactly $20 refunded, or $0 if the permission
was revoked or the order became ineligible before the refund landed.

| fault | Temporal, recommended idempotency key | Temporal with Interlock as the activity body |
|---|---|---|
| `crash_before_ack` | COMPLETED · 2 attempts · $20 ✅ | COMMITTED_BY_RETRY · 2 attempts · $20 ✅ |
| `refund_during_outage` | COMPLETED · 2 attempts · $40 ❌ | REFUSED:stale_premise_at_recovery · 2 attempts · $20 ✅ |
| `lease_revoked_during_outage` | COMPLETED · 2 attempts · $20 ❌ | REFUSED:lease_at_recovery · 2 attempts · $0 ✅ |
| `stale_eligibility` | COMPLETED · 1 attempt · $20 ❌ | REFUSED:stale_premise · 1 attempt · $0 ✅ |

## Faults

- `crash_before_ack`: attempt 1 refunds, then the worker dies before reporting the result
- `refund_during_outage`: attempt 1 dies before sending; support refunds $20 by hand before attempt 2
- `lease_revoked_during_outage`: attempt 1 dies before sending; refund permission revoked before attempt 2
- `stale_eligibility`: no crash; the order becomes ineligible after the decision, before the step runs

## Reading it

Temporal does its job: the crashed attempt is retried, and with a stable key the
crash-before-ack refund lands once. In the other rows the facts behind the decision
changed before the retry, and Temporal's retry, correctly by its own contract, runs the
same step again. The same activity with Interlock as its body re-checks lease and
premises before sending and refuses.
