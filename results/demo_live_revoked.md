# Results: the demo page, driven in a real browser

Generated 2026-09-13 23:48 UTC by `experiments/demo_browser.py`: it started `demo/serve.py`, opened `/demo` in headless
Chromium, clicked "Run live" (and clicked it again at once, to check the double-click guard), waited for the run to
finish, then ran the checks below and clicked "Run mock (simulated, no Stripe)". Afterwards it re-read each live
column's PaymentIntent from Stripe directly, outside the page and the API.

Scenario `approval_revoked_during_outage`, with the hand-written check column. Model claude-haiku-4-5-20251001. Interlock claim TTL 15s and Stripe request timeout
10s (demo settings; backend defaults 40s and 30s). Live run 49da4aa4cf: 25.1s
from the click to the page showing the finished run; 3 support cases started for 3 columns.

Screenshots: `results/demo_live_revoked.png` (1440 wide, light), `results/demo_live_revoked_narrow_dark.png` (400 wide, dark,
page width 400px), `results/demo_live_revoked_mock.png` (the mock run, same scenario).

## Live run

Banner: "LIVE RUN: Stripe test mode, claude-haiku-4-5-20251001, Temporal dev server, worker processes killed with SIGKILL. Scenario: Approval revoked during the outage."
Status: "Run 49da4aa4cf finished in 23.7s."
MOCK badges on the live page: 0.

### Standard setup: Temporal and an idempotency key

- Page: Violated: $20.00 too much, "1 refund, $20.00 refunded"; outcome `REFUNDED` at refund attempt 2, 16.8s from crash to close
- PaymentIntent [`pi_3UFN8j88KhIqqdFL1d2iI3uW`](https://dashboard.stripe.com/test/payments/pi_3UFN8j88KhIqqdFL1d2iI3uW), workflow `refund-case-4707181529b6`
- Refund ids on the page: `re_3UFN8j88KhIqqdFL1jB4TG1C`
- Refunds re-read from Stripe after the run: `re_3UFN8j88KhIqqdFL1jB4TG1C` 2000 cents metadata {"workflow_id": "refund-case-4707181529b6"} (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker crash: pid 88300, exit code -9 at `before_send`
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - case #4471. Customer keeps blender."

### Temporal plus a hand-written check

- Page: Held, "0 refunds, $0.00 refunded"; outcome `REFUSED:lease` at refund attempt 2, 15.8s from crash to close
- PaymentIntent [`pi_3UFN8j88KhIqqdFL0Lal48XM`](https://dashboard.stripe.com/test/payments/pi_3UFN8j88KhIqqdFL0Lal48XM), workflow `refund-case-2f70393c9a59`
- Refund ids on the page: none
- Refunds re-read from Stripe after the run: none (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker crash: pid 88298, exit code -9 at `before_send`
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar. Customer approved for $20.00 refund. Support case #4471."

### Temporal plus Interlock

- Page: Held, "0 refunds, $0.00 refunded"; outcome `REFUSED:lease_at_recovery` at refund attempt 2, 15.8s from crash to close
- PaymentIntent [`pi_3UFN8i88KhIqqdFL1ASDmtA6`](https://dashboard.stripe.com/test/payments/pi_3UFN8i88KhIqqdFL1ASDmtA6), workflow `refund-case-f53e67205f76`
- Refund ids on the page: none
- Refunds re-read from Stripe after the run: none (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker crash: pid 88296, exit code -9 at `before_send`
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - customer keeps blender. Support case #4471 approved."
- Receipt for effect `d0dc8ce2fe4f`: entries PROPOSED, AUTHORIZED, DISPATCHED, REFUSED; verify: valid=True, happened=False, happened_once=True, authorized_when_fired=None, assumptions_held=None, refused='lease at recovery', signed=None
- Receipt text on the page: "Interlock receipt for effect d0dc8ce2fe4f: PROPOSED, AUTHORIZED, DISPATCHED, REFUSED.Verified from its entries: valid true, chain intact true, happened false, this effect committed at most once true, authorized when fired null, assumptions held null, refused "lease at recovery", signed no (no key configured)."

## Checks

- Elapsed of the finished run, read twice 3s apart: [23.7, 23.7]. The 400px page opened later says: "Run 49da4aa4cf finished in 23.7s."
- Poll race: a page held back its poll of run `49da4aa4cf` by 4s and clicked "Run mock". The server started
  `38b2eab97a`; 6s after the mock finished the page showed run `38b2eab97a` (mock),
  status "Run 38b2eab97a (MOCK) finished in 0s.". Held: **True**
- Cross-site POST from a page at `http://127.0.0.1:53705`: {"no_cors_text_plain": "sent, opaque response opaque", "cors_json": "blocked: Failed to fetch"}. Latest run before
  `49da4aa4cf`, after `49da4aa4cf`; a run started: **False**. Direct requests:
  {"text/plain from curl-like client": 403, "JSON with Origin http://evil.example": 403, "GET with Host rebound.example (DNS rebinding)": 403}

## Mock run

Banner: "MOCK RUN: simulated in this process by experiments/refund_agent.py. No Stripe, no model, no Temporal, no real crash. Not a live result."
Finished status: "Run 38b2eab97a (MOCK) finished in 0s."; at 400px dark: "Run 38b2eab97a (MOCK) finished in 0s." (`results/demo_live_revoked_mock_narrow_dark.png`)
Tab title: "MOCK: Interlock: one crash, two setups". Live settings line shown: False; "Live runs: ..." note shown: False

- MOCKDurable execution, simulated: Violated: $20 too much, "$20 refunded (simulated)"; 4 events, 0 without a MOCK badge
- MOCKInterlock gate, simulated: Held, "$0 refunded (simulated)"; 6 events, 0 without a MOCK badge

The mock run is `experiments/refund_agent.py` in the API process: no Stripe, no model, no Temporal, no process.

## Processes left after stopping

none
