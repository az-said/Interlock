# Results: the demo page, driven in a real browser

Generated 2026-09-13 23:48 UTC by `experiments/demo_browser.py`: it started `demo/serve.py`, opened `/demo` in headless
Chromium, clicked "Run live" (and clicked it again at once, to check the double-click guard), waited for the run to
finish, then ran the checks below and clicked "Run mock (simulated, no Stripe)". Afterwards it re-read each live
column's PaymentIntent from Stripe directly, outside the page and the API.

Scenario `hand_refund_during_outage`. Model claude-haiku-4-5-20251001. Interlock claim TTL 15s and Stripe request timeout
10s (demo settings; backend defaults 40s and 30s). Live run 09b281c272: 25.1s
from the click to the page showing the finished run; 2 support cases started for 2 columns.

Screenshots: `results/demo_live.png` (1440 wide, light), `results/demo_live_narrow_dark.png` (400 wide, dark,
page width 400px), `results/demo_live_mock.png` (the mock run, same scenario).

## Live run

Banner: "LIVE RUN: Stripe test mode, claude-haiku-4-5-20251001, Temporal dev server, worker processes killed with SIGKILL. Scenario: Hand refund during the outage."
Status: "Run 09b281c272 finished in 23.6s."
MOCK badges on the live page: 0.

### Standard setup: Temporal and an idempotency key

- Page: Violated: $20.00 too much, "2 refunds, $40.00 refunded"; outcome `REFUNDED` at refund attempt 2, 16.7s from crash to close
- PaymentIntent [`pi_3UFN8088KhIqqdFL1YpMQWGX`](https://dashboard.stripe.com/test/payments/pi_3UFN8088KhIqqdFL1YpMQWGX), workflow `refund-case-8abc6b425a92`
- Refund ids on the page: `re_3UFN8088KhIqqdFL1aLvuYqM`, `re_3UFN8088KhIqqdFL1SsDHLnR`
- Refunds re-read from Stripe after the run: `re_3UFN8088KhIqqdFL1aLvuYqM` 2000 cents metadata {}, `re_3UFN8088KhIqqdFL1SsDHLnR` 2000 cents metadata {"workflow_id": "refund-case-8abc6b425a92"} (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker crash: pid 88097, exit code -9 at `before_send`
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar on blender. Support case #4471 approved $20.00 refund; customer retains blender."

### Temporal plus Interlock

- Page: Held, "1 refund, $20.00 refunded"; outcome `REFUSED:stale_premise_at_recovery` at refund attempt 2, 16.3s from crash to close
- PaymentIntent [`pi_3UFN7z88KhIqqdFL0TFaNx4D`](https://dashboard.stripe.com/test/payments/pi_3UFN7z88KhIqqdFL0TFaNx4D), workflow `refund-case-87407bd16d7c`
- Refund ids on the page: `re_3UFN7z88KhIqqdFL03pkGgX3`
- Refunds re-read from Stripe after the run: `re_3UFN7z88KhIqqdFL03pkGgX3` 2000 cents metadata {} (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker crash: pid 88095, exit code -9 at `before_send`
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - support case #4471 approved. Customer keeps blender."
- Receipt for effect `115f7142a3fc`: entries PROPOSED, AUTHORIZED, DISPATCHED, REFUSED; verify: valid=True, happened=False, happened_once=True, authorized_when_fired=None, assumptions_held=None, refused='stale_premise at recovery', signed=None
- Receipt text on the page: "Interlock receipt for effect 115f7142a3fc: PROPOSED, AUTHORIZED, DISPATCHED, REFUSED.Verified from its entries: valid true, chain intact true, happened false, this effect committed at most once true, authorized when fired null, assumptions held null, refused "stale_premise at recovery", signed no (no key configured)."

## Checks

- Elapsed of the finished run, read twice 3s apart: [23.6, 23.6]. The 400px page opened later says: "Run 09b281c272 finished in 23.6s."
- Poll race: a page held back its poll of run `09b281c272` by 4s and clicked "Run mock". The server started
  `38a0ae898d`; 6s after the mock finished the page showed run `38a0ae898d` (mock),
  status "Run 38a0ae898d (MOCK) finished in 0s.". Held: **True**
- Cross-site POST from a page at `http://127.0.0.1:53452`: {"no_cors_text_plain": "sent, opaque response opaque", "cors_json": "blocked: Failed to fetch"}. Latest run before
  `09b281c272`, after `09b281c272`; a run started: **False**. Direct requests:
  {"text/plain from curl-like client": 403, "JSON with Origin http://evil.example": 403, "GET with Host rebound.example (DNS rebinding)": 403}

## Mock run

Banner: "MOCK RUN: simulated in this process by experiments/refund_agent.py. No Stripe, no model, no Temporal, no real crash. Not a live result."
Finished status: "Run 38a0ae898d (MOCK) finished in 0s."; at 400px dark: "Run 38a0ae898d (MOCK) finished in 0s." (`results/demo_live_mock_narrow_dark.png`)
Tab title: "MOCK: Interlock: one crash, two setups". Live settings line shown: False; "Live runs: ..." note shown: False

- MOCKDurable execution, simulated: Violated: $20 too much, "$40 refunded (simulated)"; 4 events, 0 without a MOCK badge
- MOCKInterlock gate, simulated: Held, "$20 refunded (simulated)"; 6 events, 0 without a MOCK badge

The mock run is `experiments/refund_agent.py` in the API process: no Stripe, no model, no Temporal, no process.

## Processes left after stopping

none
