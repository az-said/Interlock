# Results: the standalone demo page, driven in a real browser

Generated 2026-09-14 01:06 UTC by `experiments/demo_browser.py`: it started `demo/serve.py`, opened `/demo/standalone` in headless
Chromium, clicked "Run live" (and clicked it again at once, to check the double-click guard), waited for the run to
finish, then ran the checks below and clicked "Run mock (simulated, no Stripe)". Afterwards it re-read each live
column's PaymentIntent from Stripe directly, outside the page and the API.

Scenario `approval_revoked_during_outage`. Model claude-haiku-4-5-20251001. Interlock claim TTL 15s and Stripe request timeout
10s (demo settings; backend defaults 40s and 30s). Live run c5ab28a0f2: 25.1s
from the click to the page showing the finished run; 2 support cases started for 2 columns.

Screenshots: `results/demo_standalone_revoked.png` (1440 wide, light), `results/demo_standalone_revoked_narrow_dark.png` (400 wide, dark,
page width 400px), `results/demo_standalone_revoked_mock.png` (the mock run, same scenario).

## Live run

Banner: "LIVE RUN: Stripe test mode, claude-haiku-4-5-20251001, a separate worker process killed with SIGKILL and restarted. No Temporal. Scenario: Approval revoked during the outage."
Status: "Run c5ab28a0f2 finished in 23.5s."
MOCK badges on the live page: 0.

### Common agent pattern: saved decision and an idempotency key

- Page: Violated: $20.00 too much, "1 refund, $20.00 refunded"; outcome `REFUNDED` at refund attempt 1, 1.6s from crash to done
- PaymentIntent [`pi_3UFOMH88KhIqqdFL1kh4yQsw`](https://dashboard.stripe.com/test/payments/pi_3UFOMH88KhIqqdFL1kh4yQsw)
- Refund ids on the page: `re_3UFOMH88KhIqqdFL1VZKpTsM`
- Refunds re-read from Stripe after the run: `re_3UFOMH88KhIqqdFL1VZKpTsM` 2000 cents metadata {"case_id": "case-0962133d30f4"} (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker processes (pids in start order): 77702, 77715; crash: pid 77702, exit code -9 at `before_send`; restarted worker pid 77715 exited with code 0
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - customer retains blender (Order #881, Support case #4471)"

### The same worker with Interlock

- Page: Held, "0 refunds, $0.00 refunded"; outcome `REFUSED:lease_at_recovery` at refund attempt 15, 14.9s from crash to done
- PaymentIntent [`pi_3UFOMH88KhIqqdFL0w7qGT8v`](https://dashboard.stripe.com/test/payments/pi_3UFOMH88KhIqqdFL0w7qGT8v)
- Refund ids on the page: none
- Refunds re-read from Stripe after the run: none (amount received 10000 cents)
- Page matches Stripe exactly: **True**
- Worker processes (pids in start order): 77705, 77725; crash: pid 77705, exit code -9 at `before_send`; restarted worker pid 77725 exited with code 0
- Model decision: claude-haiku-4-5-20251001, 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Support case #4471)"
- Receipt for effect `7e6b5924e56d`: entries PROPOSED, AUTHORIZED, DISPATCHED, REFUSED; verify: valid=True, happened=False, happened_once=True, authorized_when_fired=None, assumptions_held=None, refused='lease at recovery', signed=None
- Receipt text on the page: "Interlock receipt for effect 7e6b5924e56d: PROPOSED, AUTHORIZED, DISPATCHED, REFUSED.Verified from its entries: valid true, chain intact true, happened false, this effect committed at most once true, authorized when fired null, assumptions held null, refused "lease at recovery", signed no (no key configured)."

## Checks

- Elapsed of the finished run, read twice 3s apart: [23.5, 23.5]. The 400px page opened later says: "Run c5ab28a0f2 finished in 23.5s."
- Poll race: a page held back its poll of run `c5ab28a0f2` by 4s and clicked "Run mock". The server started
  `19846de28b`; 6s after the mock finished the page showed run `19846de28b` (mock),
  status "Run 19846de28b (MOCK) finished in 0s.". Held: **True**
- Cross-site POST from a page at `http://127.0.0.1:57081`: {"no_cors_text_plain": "sent, opaque response opaque", "cors_json": "blocked: Failed to fetch"}. Latest run before
  `c5ab28a0f2`, after `c5ab28a0f2`; a run started: **False**. Direct requests:
  {"text/plain from curl-like client": 403, "JSON with Origin http://evil.example": 403, "GET with Host rebound.example (DNS rebinding)": 403}

## Mock run

Banner: "MOCK RUN: simulated in this process by experiments/refund_agent.py. No Stripe, no model, no worker process, no real crash. Not a live result."
Finished status: "Run 19846de28b (MOCK) finished in 0s."; at 400px dark: "Run 19846de28b (MOCK) finished in 0s." (`results/demo_standalone_revoked_mock_narrow_dark.png`)
Tab title: "MOCK: Interlock: one crash, the same refund". Live settings line shown: False; "Live runs: ..." note shown: False

- MOCKRetry with a stable key, simulated: Violated: $20 too much, "$20 refunded (simulated)"; 4 events, 0 without a MOCK badge
- MOCKInterlock gate, simulated: Held, "$0 refunded (simulated)"; 6 events, 0 without a MOCK badge

The mock run is `experiments/refund_agent.py` in the API process: no Stripe, no model, no Temporal, no process.

## The other page

`/` links to the Temporal demo: "Already on Temporal? See the Temporal demo". The Temporal page (`/demo`) on this server says:
"Temporal demo unavailable on this server: temporalio is not installed. The standalone demo runs without Temporal.".

## Processes left after stopping

none
