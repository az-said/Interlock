# Scenario: connect_payout

Generated 2026-09-13 22:22 UTC by `experiments/scenario_connect_payout.py`. Status: **BLOCKED**.

Stripe Connect is not enabled on the test platform `acct_1TJzu288KhIqqdFL`, so no connected account can be
created and no cell ran. Exact error from the first step of the run:

    400 POST /accounts: You can only create new accounts if you've signed up for Connect, which you can do at https://dashboard.stripe.com/connect.

Every route to a seller account was tried before recording this (see `probe` in the json):

- `POST /v1/accounts type=express`: 400 POST /accounts: You can only create new accounts if you've signed up for Connect, which you can do at https://dashboard.stripe.com/connect.
- `POST /v1/accounts type=standard`: 400 POST /accounts: You can only create new accounts if you've signed up for Connect, which you can do at https://dashboard.stripe.com/connect.
- `POST /v1/accounts type=custom`: 400 POST /accounts: You can only create new accounts if you've signed up for Connect, which you can do at https://dashboard.stripe.com/connect.
- `POST /v2/core/accounts recipient`: 400: Some fields in the request were invalid: 'configuration.recipient.capabilities.stripe_balance: You must have Connect enabled to use this field.'
- `GET /v1/accounts`: 0 existing connected accounts

Nothing was compared, so this scenario says nothing about no_check, hand_check or Interlock. To run it, enable
Connect for the test account at https://dashboard.stripe.com/connect and re-run `python3 experiments/scenario_connect_payout.py`.
The live cell path (account setup, the transfer, SIGKILL, ground truth) has not run against Stripe yet; only its
logic is tested offline, against an in-memory Stripe, in `tests/test_scenario_connect_payout.py`. Those tests
expect: all three land $20 once after `crash_after_commit`; with the order reversed during the outage, no_check
pays the seller $20 and hand_check and Interlock both refuse, a tie on money with Interlock adding a receipt.
They are a prediction, not a result.

## What the run does once Connect is on

- `crash_after_commit`: worker SIGKILLed after Stripe's response to the transfer POST, before anything recorded it; restarted. Want $20 in 1 transfer.
- `crash_before_send_order_reversed`: worker SIGKILLed right before the transfer POST; the buyer's payment is refunded in full; restarted. Want $0.
- `crash_before_send_seller_restricted`: worker SIGKILLed right before the transfer POST; the platform rejects the seller account (transfers capability inactive); restarted. Want $0. Stripe itself may refuse this transfer, which would make all three columns hold.
- no_check: stable Idempotency-Key `payout:<order>`, retry on restart, no re-read.
- hand_check: before sending, list transfers in the order's transfer_group (report one if found), re-read the charge (refunded?) and the seller's transfers capability, plus the same key and source_transaction. Idiomatic: these are the reads Stripe's separate-charges-and-transfers docs point to. It keeps no durable record of which checks ran.
- interlock: `interlock.easy` with those same facts as premises, the key as tier 1, the transfer_group lookup by effect id, recovery on restart (waits out the dead sender's 40s claim), and a verified hash-chained receipt.
- can_prove_what_happened is true only when a durable record says who decided, which checks ran and what landed: Interlock's receipt (verify() valid). The baselines leave Stripe's objects and nothing about the checks.
