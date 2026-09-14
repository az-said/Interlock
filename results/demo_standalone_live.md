# Results: the standalone demo page, driven in a real browser

Generated 2026-09-14 01:05 UTC by `experiments/demo_browser.py`: it started `demo/serve.py`, opened `/demo/standalone` in headless
Chromium, clicked "Run live" (and clicked it again at once, to check the double-click guard), waited for the run to
finish, then ran the checks below and clicked "Run mock (simulated, no Stripe)". Afterwards it re-read each live
column's PaymentIntent from Stripe directly, outside the page and the API.

Scenario `hand_refund_during_outage`. Model claude-haiku-4-5-20251001. Interlock claim TTL 15s and Stripe request timeout
10s (demo settings; backend defaults 40s and 30s). Live run af55c33747: 23.1s
from the click to the page showing the finished run; 2 support cases started for 2 columns.

Screenshots: `results/demo_standalone_live.png` (1440 wide, light), `results/demo_standalone_live_narrow_dark.png` (400 wide, dark,
page width 400px), `results/demo_standalone_live_mock.png` (the mock run, same scenario).

## Live run

Banner: "LIVE RUN: Stripe test mode, claude-haiku-4-5-20251001, a separate worker process killed with SIGKILL and restarted. No Temporal. Scenario: Hand refund during the outage."
Status: "Run af55c33747 finished in 22.4s."
MOCK badges on the live page: 0.

### Common agent pattern: saved decision and an idempotency key

- Page: Violated: $20.00 too much, "2 refunds, $40.00 refunded"; outcome `REFUNDED` at refund attempt 1, 2.7s from crash to done
- PaymentIntent [`pi_3UFOKl88KhIqqdFL1UUuf5hL`](https://dashboard.stripe.com/test/payments/pi_3UFOKl88KhIqqdFL1UUuf5hL)
- Refund ids on the page: `re_3UFOKl88KhIqqdFL17OQa7Ts`, `re_3UFOKl88KhIqqdFL1duHDryd`
- Refunds re-read from Stripe after the run: `re_3UFOKl88KhIqqdFL17OQa7Ts` 2000 cents metadata {}, `re_3UFOKl88KhIqqdFL1duHDryd` 2000 cents metadata {"case_id": "case-b3f913a7b689"} (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker processes (pids in start order): 76213, 76284; crash: pid 76213, exit code -9 at `before_send`; restarted worker pid 76284 exited with code 0
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar on blender - support case #4471"

### The same worker with Interlock

- Page: Held, "1 refund, $20.00 refunded"; outcome `REFUSED:stale_premise_at_recovery` at refund attempt 14, 15.3s from crash to done
- PaymentIntent [`pi_3UFOKl88KhIqqdFL1gbNZoQP`](https://dashboard.stripe.com/test/payments/pi_3UFOKl88KhIqqdFL1gbNZoQP)
- Refund ids on the page: `re_3UFOKl88KhIqqdFL1a1o5MA5`
- Refunds re-read from Stripe after the run: `re_3UFOKl88KhIqqdFL1a1o5MA5` 2000 cents metadata {} (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker processes (pids in start order): 76211, 76286; crash: pid 76211, exit code -9 at `before_send`; restarted worker pid 76286 exited with code 0
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - customer keeping blender (Case #4471)"
- Receipt for effect `b503e7b05e9c`: entries PROPOSED, AUTHORIZED, DISPATCHED, REFUSED; verify: valid=True, happened=False, happened_once=True, authorized_when_fired=None, assumptions_held=None, refused='stale_premise at recovery', signed=None
- Receipt text on the page: "Interlock receipt for effect b503e7b05e9c: PROPOSED, AUTHORIZED, DISPATCHED, REFUSED.Verified from its entries: valid true, chain intact true, happened false, this effect committed at most once true, authorized when fired null, assumptions held null, refused "stale_premise at recovery", signed no (no key configured)."

## Checks

- Elapsed of the finished run, read twice 3s apart: [22.4, 22.4]. The 400px page opened later says: "Run af55c33747 finished in 22.4s."
- Poll race: a page held back its poll of run `af55c33747` by 4s and clicked "Run mock". The server started
  `39ffba1cb0`; 6s after the mock finished the page showed run `39ffba1cb0` (mock),
  status "Run 39ffba1cb0 (MOCK) finished in 0s.". Held: **True**
- Cross-site POST from a page at `http://127.0.0.1:56751`: {"no_cors_text_plain": "sent, opaque response opaque", "cors_json": "blocked: Failed to fetch"}. Latest run before
  `af55c33747`, after `af55c33747`; a run started: **False**. Direct requests:
  {"text/plain from curl-like client": 403, "JSON with Origin http://evil.example": 403, "GET with Host rebound.example (DNS rebinding)": 403}

## Mock run

Banner: "MOCK RUN: simulated in this process by experiments/refund_agent.py. No Stripe, no model, no worker process, no real crash. Not a live result."
Finished status: "Run 39ffba1cb0 (MOCK) finished in 0s."; at 400px dark: "Run 39ffba1cb0 (MOCK) finished in 0s." (`results/demo_standalone_live_mock_narrow_dark.png`)
Tab title: "MOCK: Interlock: one crash, the same refund". Live settings line shown: False; "Live runs: ..." note shown: False

- MOCKRetry with a stable key, simulated: Violated: $20 too much, "$40 refunded (simulated)"; 4 events, 0 without a MOCK badge
- MOCKInterlock gate, simulated: Held, "$20 refunded (simulated)"; 6 events, 0 without a MOCK badge

The mock run is `experiments/refund_agent.py` in the API process: no Stripe, no model, no Temporal, no process.

## The other page

`/` links to the Temporal demo: "Already on Temporal? See the Temporal demo". The Temporal page (`/demo`) on this server says:
nothing (Temporal is available).

## Processes left after stopping

none
