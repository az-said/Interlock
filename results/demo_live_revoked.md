# Results: the Temporal demo page, driven in a real browser

Generated 2026-09-14 01:07 UTC by `experiments/demo_browser.py`: it started `demo/serve.py`, opened `/demo` in headless
Chromium, clicked "Run live" (and clicked it again at once, to check the double-click guard), waited for the run to
finish, then ran the checks below and clicked "Run mock (simulated, no Stripe)". Afterwards it re-read each live
column's PaymentIntent from Stripe directly, outside the page and the API.

Scenario `approval_revoked_during_outage`. Model claude-haiku-4-5-20251001. Interlock claim TTL 15s and Stripe request timeout
10s (demo settings; backend defaults 40s and 30s). Live run e7c266e058: 32.1s
from the click to the page showing the finished run; 2 support cases started for 2 columns.

Screenshots: `results/demo_live_revoked.png` (1440 wide, light), `results/demo_live_revoked_narrow_dark.png` (400 wide, dark,
page width 400px), `results/demo_live_revoked_mock.png` (the mock run, same scenario).

## Live run

Banner: "LIVE RUN: Stripe test mode, claude-haiku-4-5-20251001, Temporal dev server, worker processes killed with SIGKILL. Scenario: Approval revoked during the outage."
Status: "Run e7c266e058 finished in 30.5s."
MOCK badges on the live page: 0.

### Standard setup: Temporal and an idempotency key

- Page: Violated: $20.00 too much, "1 refund, $20.00 refunded"; outcome `REFUNDED` at refund attempt 2, 17.2s from crash to close
- PaymentIntent [`pi_3UFON688KhIqqdFL0H5BuUOm`](https://dashboard.stripe.com/test/payments/pi_3UFON688KhIqqdFL0H5BuUOm), workflow `refund-case-3096d6bcdce0`
- Refund ids on the page: `re_3UFON688KhIqqdFL0eTGNkGr`
- Refunds re-read from Stripe after the run: `re_3UFON688KhIqqdFL0eTGNkGr` 2000 cents metadata {"workflow_id": "refund-case-3096d6bcdce0"} (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker processes (pids in start order): 78449, 78658; crash: pid 78449, exit code -9 at `before_send`
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - customer keeps blender. Support case #4471 approved."

### Temporal plus Interlock

- Page: Held, "0 refunds, $0.00 refunded"; outcome `REFUSED:lease_at_recovery` at refund attempt 2, 16.1s from crash to close
- PaymentIntent [`pi_3UFON688KhIqqdFL0ugZrwUY`](https://dashboard.stripe.com/test/payments/pi_3UFON688KhIqqdFL0ugZrwUY), workflow `refund-case-8998565e824c`
- Refund ids on the page: none
- Refunds re-read from Stripe after the run: none (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker processes (pids in start order): 78446, 78608; crash: pid 78446, exit code -9 at `before_send`
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - support case #4471"
- Receipt for effect `b9a3e80ab1f7`: entries PROPOSED, AUTHORIZED, DISPATCHED, REFUSED; verify: valid=True, happened=False, happened_once=True, authorized_when_fired=None, assumptions_held=None, refused='lease at recovery', signed=None
- Receipt text on the page: "Interlock receipt for effect b9a3e80ab1f7: PROPOSED, AUTHORIZED, DISPATCHED, REFUSED.Verified from its entries: valid true, chain intact true, happened false, this effect committed at most once true, authorized when fired null, assumptions held null, refused "lease at recovery", signed no (no key configured)."

## Checks

- Elapsed of the finished run, read twice 3s apart: [30.5, 30.5]. The 400px page opened later says: "Run e7c266e058 finished in 30.5s."
- Poll race: a page held back its poll of run `e7c266e058` by 4s and clicked "Run mock". The server started
  `29554e571b`; 6s after the mock finished the page showed run `29554e571b` (mock),
  status "Run 29554e571b (MOCK) finished in 0s.". Held: **True**
- Cross-site POST from a page at `http://127.0.0.1:57287`: {"no_cors_text_plain": "sent, opaque response opaque", "cors_json": "blocked: Failed to fetch"}. Latest run before
  `e7c266e058`, after `e7c266e058`; a run started: **False**. Direct requests:
  {"text/plain from curl-like client": 403, "JSON with Origin http://evil.example": 403, "GET with Host rebound.example (DNS rebinding)": 403}

## Mock run

Banner: "MOCK RUN: simulated in this process by experiments/refund_agent.py. No Stripe, no model, no Temporal, no real crash. Not a live result."
Finished status: "Run 29554e571b (MOCK) finished in 0s."; at 400px dark: "Run 29554e571b (MOCK) finished in 0s." (`results/demo_live_revoked_mock_narrow_dark.png`)
Tab title: "MOCK: Interlock: one crash, two setups". Live settings line shown: False; "Live runs: ..." note shown: False

- MOCKDurable execution, simulated: Violated: $20 too much, "$20 refunded (simulated)"; 4 events, 0 without a MOCK badge
- MOCKInterlock gate, simulated: Held, "$0 refunded (simulated)"; 6 events, 0 without a MOCK badge

The mock run is `experiments/refund_agent.py` in the API process: no Stripe, no model, no Temporal, no process.

## Processes left after stopping

none
