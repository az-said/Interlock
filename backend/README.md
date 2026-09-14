# backend: the refund case, end to end

A small real backend that shows where Temporal alone, Temporal with a hand-written re-check, and Temporal
with Interlock differ, with nothing simulated in-process.

## What runs

| process | file | does |
|---|---|---|
| HTTP API | `api.py` | creates cases (a real $100 test-mode payment, an approval capped at `approved_cents`, a Temporal workflow), reports status with Stripe ground truth and the Interlock receipt, revokes approvals, takes hand refunds |
| worker | `worker.py` | the Temporal worker for `RefundCase` (`workflows.py`), one OS process |
| agent | `agent.py` | the LLM: Anthropic Messages API over urllib, tools `get_payment` (real Stripe read) and `issue_refund` (validated, including against the approved amount, never sent by the model) |
| leases | `leases.py` | approvals in SQLite, so the API revokes what the worker checks; `allows()` also caps the amount |

`RefundCase` runs `decide` (the model, recorded in Temporal history) then `refund`:

- `temporal`: Stripe refund with `Idempotency-Key = workflow run id/activity id` (the key Temporal's docs
  suggest). No re-check in the activity body.
- `temporal_checked`: the same, plus about ten hand-written lines at the top of the activity: if this
  workflow's own refund is already in Stripe, report it (`FOUND_BY_LOOKUP`) and stop; otherwise the approval
  must be live and cover the amount, and the payment's refunds must be unchanged since the decision. What a
  careful Temporal user can write. It matches Interlock's Stripe outcome in the chaos rows; see
  `results/e2e_live.md` for where the two still differ (packaging, a claim across worker processes on one machine, AMBIGUOUS, receipts, speed).
- `interlock`: `interlock.temporal.gated(gate, proposal)` as the activity body, a shared SQLite journal
  (`journal.db`), durable leases, and premises captured when the model decided.

Only a refusal (`interlock: REFUSED`, `interlock: AMBIGUOUS`, `precheck: REFUSED`) becomes a workflow
outcome. Any other activity failure, including retries used up while `IN_FLIGHT`, fails the workflow.

State lives in `INTERLOCK_DATA` (default `.interlock/backend/`): `cases.db`, `leases.db`, `journal.db`.

## Run it

    # a Temporal server on TEMPORAL_ADDRESS (default localhost:7233), then:
    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python backend/api.py --port 8787
    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python backend/worker.py
    curl -s localhost:8787/cases -d '{"mode":"interlock","paid_cents":10000,"approved_cents":2000,"customer_text":"...approved one $20 refund..."}'

Stripe key: `STRIPE_SECRET_KEY`, else `test_mode_api_key` from `stripe config --list`. Test keys only.
The whole chaos run, with its own Temporal dev server: `experiments/e2e_live.py`, checked by `experiments/e2e_audit.py`.

## Faults

- `INTERLOCK_CRASH=before_send|after_commit` with `INTERLOCK_CRASH_MARKER=<file>`: the worker SIGKILLs
  itself right before the refund POST (for interlock, after DISPATCHED is durable) or right after Stripe's
  full response arrived and was parsed, before anything durable records it (the journal, or Temporal's
  history). The connection is never cut mid-response; recovery sees the same state as a lost response. One-shot: the marker is created first, so a
  restarted worker with the same env does not crash again.

## Real and emulated

Real: Stripe test mode, the LLM calls, the Temporal server and its retries, the SIGKILLs, cross-process
SQLite. Emulated, and only with these env vars:

- `INTERLOCK_EMULATE_24H=1`: Stripe forgetting an idempotency key after 24h, which cannot be triggered on
  demand. Every refund POST from that worker, in every mode, uses `<key>/emulated-pruned`, a key Stripe has
  never seen. Interlock only: its gate also recovers with its clock 25h ahead, and that clock, not the key, is
  what sends it to a lookup (without it the gate trusts the key and would resend). `temporal_checked` needs no
  clock: it looks its own refund up before every send. The timing is emulated too: reaching
  this for real needs no worker for over 24h, or a retry policy or reconciler spanning a day.
- `INTERLOCK_NO_LOOKUP=1`: the Interlock target declares it cannot list refunds (Stripe can), so a pruned
  key leaves the gate nothing to check, and it says AMBIGUOUS.

## What the mechanism is, and is not

- The premise is "the payment's refunds are what they were when the model decided" (hand refunds made before
  the decision included). It refuses on a hand refund of the same $20 and equally on an unrelated one; it does
  not recognize the same action.
- Receipts are hash-chained and unsigned here (no key is configured), written by the worker that sends: the
  gate's attestation, not proof. Each recorded check carries what the gate read (the approval row with its cap
  and revoked time, premise violations); each commit carries Stripe's refund id, or the id a lookup found.
  Stripe's refund list is the evidence a refund happened once; `experiments/e2e_audit.py` checks the receipt
  against it.
- The API has no auth and binds to 127.0.0.1. The approval is whatever the caller of `POST /cases` asserts
  (`approved_cents`); a real deployment takes approvals from the support tool. Bodies over 64 KiB and
  `customer_text` over 4000 characters are refused.
- Claim TTL is 40s, longer than the Stripe client's 30s timeout, so recovery never takes over a send that
  may still be in progress. That is why an Interlock retry after a crash waits about 40s, and why the
  refund activity allows `3 * CLAIM_TTL // 5` attempts. A recovery that fails before sending anything
  releases its claim, so the next attempt does not wait again.
