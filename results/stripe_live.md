# Results: refund agent against real Stripe (test mode)

Generated 2026-09-13 16:50 UTC by `experiments/stripe_live.py`. Every row made real Stripe API calls:
a $100 test card payment, one approved $20 partial refund, then the fault.
Invariant: exactly $20 refunded on the payment.

| fault | naive (today) | idempotency key only | gate (Stripe: key + lookup) |
|---|---|---|---|
| `crash_before_ack` | RETRIED $40 ❌ | RETRIED $20 ✅ | COMMITTED_BY_RETRY $20 ✅ |
| `duplicate_submit` | APPLIED $40 ❌ | APPLIED:already_processed $20 ✅ | DUPLICATE_IGNORED $20 ✅ |
| `refund_during_outage` | RETRIED $40 ❌ | RETRIED $40 ❌ | REFUSED:stale_premise_at_recovery $20 ✅ |

## Faults

- `crash_before_ack`: Stripe commits the refund; the process dies before the response is recorded
- `duplicate_submit`: the same approved request is submitted twice
- `refund_during_outage`: crash before send; while the agent is down, support refunds $20 by hand

## Payments used

Each run's PaymentIntent, for checking in the Stripe test dashboard:

- `crash_before_ack` / naive: `pi_3UFGbc88KhIqqdFL0a0LGFh4`
- `crash_before_ack` / idempotency: `pi_3UFGbf88KhIqqdFL1q7thO9J`
- `crash_before_ack` / gate: `pi_3UFGbi88KhIqqdFL0Gt9vV59`
- `duplicate_submit` / naive: `pi_3UFGbl88KhIqqdFL1edzOn1w`
- `duplicate_submit` / idempotency: `pi_3UFGbo88KhIqqdFL0QIYQxtp`
- `duplicate_submit` / gate: `pi_3UFGbq88KhIqqdFL1EoKVecN`
- `refund_during_outage` / naive: `pi_3UFGbt88KhIqqdFL0WanBRXo`
- `refund_during_outage` / idempotency: `pi_3UFGbw88KhIqqdFL1lL0ASsk`
- `refund_during_outage` / gate: `pi_3UFGbz88KhIqqdFL0AZx9jPr`
