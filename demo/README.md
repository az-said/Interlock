# demo: one crash, the same refund, two setups

Two pages run the same real refund case side by side, with and without Interlock. The standalone demo needs no
Temporal: a plain worker process, killed and restarted. The Temporal demo runs the same scenarios as Temporal
workflows. Every call on a live path is real: Stripe test mode, the model, a SIGKILLed worker process, and a
restart. The crash point and the outage action (the hand refund or the revocation) are injected by the demo, so
the timing is repeatable.

## Standalone demo (no Temporal)

    ANTHROPIC_API_KEY=... python3 demo/serve.py
    # open http://127.0.0.1:8787/

Python 3.9 or later and the standard library; nothing to install. `backend/api.py` serves the page (also at
`/demo/standalone`) and starts, kills and restarts the worker processes for each run. Ctrl-C stops all of it.

Stripe key: `STRIPE_SECRET_KEY`, else `test_mode_api_key` from `stripe config --list`. Test keys only; the client
refuses anything else. Keys stay in the server's environment. The page never receives one, and the info routes only
name what is missing. The API binds to 127.0.0.1 and has no auth.

Each column is one support case, and the columns run at the same time:

1. A new $100 Stripe test payment and an approval capped at $20 (`backend/leases.py`).
2. A worker process (`backend/standalone_worker.py`) starts with `INTERLOCK_CRASH` set. The model
   (`backend/agent.py`, a real Anthropic call) reads the payment through `get_payment` and calls `issue_refund`.
   The worker then SIGKILLs itself at the crash point, and the server records its exit code (-9).
3. The outage action: a $20 refund straight to Stripe with no key and no metadata, as from the dashboard, or a
   revoked approval.
4. The server starts a new worker process, which picks the case up again, and the column ends when it is done.
5. The result card re-reads Stripe's refund list for that payment and, for Interlock, the receipt and `verify()`.

Columns:

- Standard: the common agent pattern. The decision is saved to a local file before the send, the Stripe
  Idempotency-Key is derived from the case, and the restarted worker retries. Nothing is re-checked.
- Interlock: the same worker with the refund behind `interlock.Gate`, and `gate.recover()` on restart.
- With the checkbox, a third column: the same worker with a hand-written re-check.

The engine is `backend/standalone.py`; it reuses the scenarios, event kinds and result wording of `backend/demo.py`.

## Temporal demo

    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python demo/serve.py
    # open http://127.0.0.1:8787/demo

With temporalio installed, the same command first starts Temporal's local dev server (with its web UI) and serves
both pages. Without temporalio, or when the dev server does not start, `/demo` says so in one line and links to the
standalone demo; its mock button still works.

Each column is one support case, and the columns run at the same time:

1. A new $100 Stripe test payment, an approval capped at $20 (`backend/leases.py`), and a `RefundCase` workflow
   on that column's own Temporal task queue.
2. A worker process starts with `INTERLOCK_CRASH` set. The model (`backend/agent.py`, a real Anthropic call) reads
   the payment through `get_payment` and calls `issue_refund`. The worker then SIGKILLs itself at the crash point.
3. The outage action goes through the API: a $20 refund straight to Stripe with no key and no metadata, as from
   the dashboard, or a revoked approval.
4. A new worker process starts, Temporal retries the refund activity, and the column ends when the workflow closes.
5. The result card re-reads Stripe's refund list for that payment and, for Interlock, the receipt and `verify()`.

The checkbox adds a third column: Temporal plus about ten hand-written lines that do the same re-check
(`temporal_checked` in `backend/workflows.py`). It ties with Interlock on the money in these scenarios; see
`results/e2e_live.md` for where they differ.

Every event on a live run was read during that run: Temporal's describe and history (the model's recorded
decision, each retry and why the last attempt failed), the Interlock journal, Stripe's refund list, and each
worker's pid and exit code.

## Scenarios (both demos)

| scenario | crash | during the outage | wanted in Stripe |
|---|---|---|---|
| Hand refund during the outage | right before the refund call | support refunds $20 by hand | one $20 refund, the hand one |
| Approval revoked during the outage | right before the refund call | support revokes the approval | no refund |
| Crash after Stripe answered (control) | right after Stripe's response, before anything recorded it | nothing | one $20 refund |

## Run mock (simulated, no Stripe)

Each page has its own mock button. It runs `experiments/refund_agent.py` inside the API process: the in-memory
payments simulator, a fixed proposal instead of a model, no Temporal, no process to kill. Mock runs get a striped
MOCK banner, a MOCK badge on every column, event and result, "MOCK." at the start of every line, "(MOCK)" in the run
status while running and when finished, and "MOCK: " at the start of the tab title. The live settings line and the
"Live runs: ..." note are hidden while a mock run is shown. A page only ever shows one run at a time, so mock and
live results are never on screen together.

## Timing

The backend defaults are a 40s claim TTL and a 30s Stripe timeout. `demo/serve.py` sets
`INTERLOCK_CLAIM_TTL=15` and `INTERLOCK_STRIPE_TIMEOUT=10` unless you set them. `backend/config.py` refuses a
timeout less than 5s inside the claim, because the gate must never take over a send that may still be in
flight. In the Temporal demo, Temporal's own 15s activity timeout sets when the retry starts after the kill.

## Check it

    ANTHROPIC_API_KEY=... uv run --no-project --with playwright python experiments/demo_browser.py --standalone
    ANTHROPIC_API_KEY=... uv run --no-project --with temporalio --with playwright python experiments/demo_browser.py

The first drives the standalone demo only and writes `results/demo_standalone_live.md`. The second drives both
(`--temporal` for the Temporal demo alone, which writes `results/demo_live.md` as before). For each page it starts
`demo/serve.py`, clicks both buttons in headless Chromium, saves screenshots at 1440px light and 400px dark,
re-reads each payment from Stripe, and checks, in the browser, that a finished run's time stops growing, that a slow
poll of an old run cannot repaint the page over a new run, and that a page on another origin cannot start a run.
Offline tests: `python3 -m unittest tests.test_demo`.

## Limits

- Interlock refuses because the payment's refunds changed after the model decided. It does not recognize the hand
  refund as the same action, so an unrelated refund would stop the approved one too, and a person re-approves.
- Receipts are hash-chained and unsigned (no key configured), written by the worker that sends. They are the
  gate's record of what it checked, not proof. Stripe's refund list is the evidence.
- One run at a time across both pages (a second start gets HTTP 409). Runs live in the API process's memory and are
  gone after a restart. Cases, approvals and the journal persist in `.interlock/demo/`.
- No auth. What stops another web page in the presenter's browser from starting runs: the API answers only when
  the Host header is `127.0.0.1:<port>` or `localhost:<port>` (against DNS rebinding), and takes a POST only with
  `Content-Type: application/json` (which makes a browser send a CORS preflight the API does not grant) and, when
  the browser sends an Origin, only from the page's own origin. `experiments/demo_browser.py` checks this from a page
  on another origin. Any local process can still call the API.
- A live Temporal run never inherits `INTERLOCK_EMULATE_24H` or `INTERLOCK_NO_LOOKUP` (the emulated switches in
  `backend/config.py`): `demo.worker_env` drops them, so a run labeled live uses Stripe's real key and lookup.
