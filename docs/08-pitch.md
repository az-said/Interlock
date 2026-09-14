# 08. The pitch: Interlock as middleware at the moment an agent's effect fires

Status: 2026-09-13. Every factual sentence below names the file in this repo it comes from, in parentheses. Where
a result is not in a file yet, this doc says so and does not use it. Numbers are copied, not rounded, unless marked.

## The one-line version

Interlock is a small gate that runs inside whatever already executes your agent's tool calls (a Temporal activity,
a Google ADK tool callback, an MCP server's front door, or a plain Python function) and, at the instant a refund or
payment is sent, checks that the approval is still live, that the facts the decision relied on still hold, and that
this effect has not already been sent, then writes a hash-chained receipt of what it checked.

It is not a Temporal replacement. Temporal keeps the workflow alive and retries it; Interlock is the body of the one
step that moves money (`backend/README.md`, `results/e2e_live.md` "The three columns").

## The problem, in one real run

A $100 Stripe test payment, one $20 refund approved, a real Claude model deciding the refund, and a Temporal worker
SIGKILLed right before the refund call; while it is down, the demo refunds the $20 in Stripe the way support would
by hand, with no idempotency key (`results/demo_live.md`, run `09b281c272`). The crash point and that refund are
injected by the demo; every call is real.

- Standard setup (Temporal, Stripe idempotency key set to the workflow run id and activity id, as Temporal's docs
  suggest): Temporal retried at attempt 2 and Stripe ended with 2 refunds, $40.00, against a wanted $20
  (`results/demo_live.md`, "Standard setup").
- Temporal plus Interlock as the activity body: the retry was refused with `REFUSED:stale_premise_at_recovery` and
  Stripe ended with 1 refund, $20.00, the hand one (`results/demo_live.md`, "Temporal plus Interlock").
- Both columns' refund ids were re-read from Stripe after the run and matched the page exactly
  (`results/demo_live.md`).

The idempotency key did its job: it only matches the same request, and a hand refund is a different request
(`results/e2e_live.md`, "What the pitch can claim"). What nothing checked was whether the refund was still wanted.

## Middleware, not a new runtime

The same gate (`interlock/gate.py`) attaches wherever the framework calls the tool. Only the attachment point
changes.

| where it runs | how it attaches | what is shown, and where |
|---|---|---|
| **Temporal** | `interlock.temporal.gated()` is the activity body (`backend/README.md`) | 22 cells across 8 scenarios: 18 live and 4 with an emulated 24h key expiry (`key_pruned_after_24h` x3, `no_lookup_after_24h` x1), real Stripe, real model, real SIGKILLs. In all 22 the workflow's reported outcome matched Stripe's refund list; that is not 22 wanted outcomes, since plain Temporal ended with $40 against a wanted $20 in a passing cell (`results/e2e_live.md`, `results/e2e_audit.txt`). Earlier fault table on a Temporal dev server (`results/temporal_live.md`) |
| **Google ADK** | `Guard.before_tool_callback`, or `guard.plugin()` once for every agent in an `App` (`interlock/integrations/adk.py`) | Live, 16 cells: a real ADK `LlmAgent` (google-adk 2.9.0, Claude Haiku 4.5 through LiteLlm) under an AP2 mandate, the agent process SIGKILLed inside the send and the invocation resumed in a new process. Interlock 5/5 left Stripe as wanted, median 46s crash to done; ADK with a call-id idempotency key 2/5, median 8s; ADK with a hand-written re-check callback 5/5, median 10s. Every cell's crash was checked to land in its window (`results/adk_live.md`) |
| **MCP** | `python3 -m interlock.mcp_proxy --config ... -- <server command>`, no agent code change (`interlock/mcp_proxy.py`) | Tests run the proxy as a real process in front of a fake MCP server (`tests/fake_mcp_server.py`): the proxy killed mid-call recovers once on restart, and a hand refund during the outage is refused even when the agent retries (`tests/test_mcp_proxy.py`). No real MCP server was tested |
| **Plain code** | `@gate.effect(...)` decorator and `gate.recover()` on startup (`interlock/easy.py`) | Real Stripe test mode, no Temporal: the hand refund during the outage gave $40 with an idempotency key only and $20 through the gate (`results/stripe_live.md`) |

Platform Engineering installs it once per runtime, as the activity body, the ADK plugin, or the MCP proxy
(`docs/08-compliance-mapping.md`, "Who does what").

On the Temporal plus ADK combination: `temporalio` 1.32.0 ships `temporalio.contrib.google_adk_agents`, where ADK
callbacks run as replayed workflow code, so the gate has to sit inside the activity that sends the effect, not in
the callback (`docs/09-research-adk.md`, "ADK inside Temporal"). That combination is a design note and is not built
(`docs/09-research-adk.md`).

A runtime without Temporal is being built separately (`docs/07-runtime.md`, `runtime/`); it has no results file, so
this pitch claims nothing from it.

## Alongside AP2, not instead of it

**AP2 carries the signed proof of what was authorized. Interlock re-checks, when the effect fires, that the
authorization is still live and its facts still hold, lets that effect land at most once, and records all of it in
a receipt. Stripe's refund list is the evidence of what happened.**

"Land at most once", not "sent at most once": after a crash in the send, the gate resends only under the same
idempotency key inside the provider's key window (Stripe then answers with the first refund, recorded as
`already_processed`), otherwise it looks the effect up, or reports AMBIGUOUS when it cannot (`interlock/gate.py`,
`recover`; `results/e2e_live.md`, `crash_after_commit` / interlock, `retry-idempotent`). Inside the window, "once"
comes from Stripe's key; after it, from the lookup, and that row is emulated (`results/e2e_live.md`).

- AP2 v0.2 carries signed Payment and Checkout Mandates with constraints such as an amount range and allowed payees
  (`docs/09-research-ap2.md`, section 1).
- AP2 v0.2 has no revocation, no refund mandate, and a stateless verifier that accepted the same presentation twice
  in a probe (`docs/09-research-ap2.md`, sections 1 and 3).
- The AP2 spec assigns double-spend prevention and mandate management to stateful parties
  (`docs/09-research-ap2.md`, section 5). Interlock's adapter is one such party for these checks: it verifies the
  mandate chain with the AP2 SDK at dispatch and after a crash with zero clock skew, honors a local revocation row,
  issues the nonce the agent closes with, reserves each closed mandate for one effect, keeps the effects under one
  open mandate within its amount cap (an open mandate with no amount range authorizes nothing), reads the payment the
  refund is sent to from Stripe and requires it to be the mandate's transaction, customer and card, and records the
  same `reference` hash an AP2 receipt binds to (`interlock/integrations/ap2.py` docstring).
- Checked against real Stripe: an agent that re-closed the same mandate after a refusal was refused again (1 refund,
  the hand one); one $20 mandate paid one refund where it had paid three before the fix; a refund aimed at another
  customer's PaymentIntent under customer A's mandate was refused, where before the fix it landed on customer B's
  payment; and an open mandate with no amount range was refused three times, where before the fix it paid three
  refunds (`results/adk_mandate_probes.md`).
- For an auditor the two stack: the mandate is the authorization record, the receipt is the execution record
  (`docs/08-compliance-mapping.md`, "Where AP2 fits").

Claims this pitch does not make, per the research: that AP2 has revocation, that AP2 covers refunds, that the AP2
SDK prevents replay, or that the User Credential / OpenID4VP path was exercised (`docs/09-research-ap2.md`,
section 5). Using a Payment Mandate to authorize a refund, and reading its amount range as a total for the open
mandate, are the adapter's conventions, not AP2's (`interlock/integrations/ap2.py`).

## Three buyers, one receipt

The approval policy, the software that enforces it, and the authority to spend sit with three groups; the receipt
is how each checks the other two (`docs/08-compliance-mapping.md`, "Who does what").

| role | owns | what Interlock gives them |
|---|---|---|
| **Risk and Compliance** | the approval policy: caps, who may approve, when an approval lapses | refusals with their reasons, AMBIGUOUS effects, and whether `authorized_when_fired` and `assumptions_held` held for every send |
| **Platform Engineering** | the agent framework and runtime (Temporal, ADK, an MCP host) | one install point per runtime, the journal, the exporters, `valid` and `tamper_evident` on every chain |
| **Finance / line of business** | operational authority: grants and revokes approvals | what fired, under whose approval, for how much, with Stripe's refund id to reconcile against |

(All three rows: `docs/08-compliance-mapping.md`.) The split holds only if the agent cannot grant its own approval;
Interlock records who granted it and does not enforce who may (`docs/08-compliance-mapping.md`).

## The differentiator: receipts that export to audit tooling

What exists today is exporters and a batch script over saved receipts (`experiments/export_live.py` reads
`results/e2e_live.json` or a journal file). Neither the backend nor the demo page calls an exporter when a receipt
finalizes; that is not built.

A receipt is every journal entry for one effect (PROPOSED, AUTHORIZED, DISPATCHED, then COMMITTED, REFUSED or
AMBIGUOUS), hash-chained, and `verify()` re-derives the claims from the entries alone
(`docs/08-compliance-mapping.md`, "What a receipt is").

Exported from the 8 real Interlock receipts of the end-to-end run to project `gen-lang-client-0277439345`, each
destination exported twice and read back (`results/export_live.md`):

| destination | result, read back from Google Cloud | status |
|---|---|---|
| Cloud Logging | Both exports went to a log created for that run, so the read-back could only see them. 40 entries sent per export, a query returned 40 with 40 distinct insertIds, every one received after the run started, and the hash chain rebuilt from Logging's payload verified for 8/8 effects. Dedup is at query time only; sinks were not tested | query verified live; sinks NOT VERIFIED LIVE |
| BigQuery | into a table created for that run, `merge()` inserted 32 rows, then 0; the chain rebuilt from rows verified 8/8; the three role queries in `docs/08-compliance-mapping.md` ran. `stream()` held 64 raw rows after a late third export, 32 through the dedup view | verified live |
| Cloud Trace via OTLP (`telemetry.googleapis.com`) | each export stored another copy of the same span: 8 (from earlier runs), then 9, then 10 spans per trace, one distinct span id. Export once, or dedupe on traceId + spanId | verified live, not idempotent |
| SIEM files (JSONL and ArcSight CEF) | 32 lines written on the first export, 0 on the second | local files only, no real SIEM |

The first BigQuery run failed on a column named `at`, a reserved keyword; it is now `recorded_at`, and a test rejects
reserved names (`tests/test_export.py`).

Each receipt field maps to evidence for named controls in SOX ITGC, SOC 2, PCI DSS v4.0 Requirement 10, the EU AI
Act and NIST AI RMF, as evidence and never as certification; several rows are marked "related to" where the control
is about something broader (`docs/08-compliance-mapping.md`, "The mapping" and "Read this first").

The line for the room: logs record what the logger saw; a receipt records which decision, under whose approval,
produced which effect, and what was re-checked when it fired (`docs/08-compliance-mapping.md`, entry table).

## What the numbers say, including where Interlock does not win

From the end-to-end run, 7 rows every column ran (`results/e2e_live.md`):

| setup | left Stripe as wanted | median crash to close |
|---|---|---|
| Temporal, idempotency key, no re-check | 4/7 | 16s |
| Temporal plus a hand-written re-check (about ten lines) | 6/7 | 15s |
| Temporal with Interlock as the activity body | 6/7 | 43s |

- Plain Temporal refunded $40 for the hand refund during the outage and refunded under a revoked approval
  (`results/e2e_live.md`).
- The hand-written re-check left Stripe with the same refunds as Interlock on 7/7 rows (`results/e2e_live.md`), and
  the hand-written ADK callback matched Interlock on 5/5 ADK rows (`results/adk_live.md`).
- So the case against a careful team is not the money in these rows. It is that Interlock packages the re-check,
  the lookup after a crash and the claim across worker processes instead of per-tool code, and adds AMBIGUOUS and a
  receipt (`results/e2e_live.md`). The claim is atomic across processes on one machine only; see "Honest limits".

## 90-second demo script

This matches `demo/index.html` and the recorded run `09b281c272` in `results/demo_live.md`. Event times are seconds
from the click, as the page shows them (`results/demo_live.json`, `live_run.events`).

**Before you are on stage (not part of the 90 seconds).** Start the server so Temporal's dev server is already up:
`ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python demo/serve.py`, open
`http://127.0.0.1:8787/demo` (`demo/README.md`). The server uses a 15s claim TTL and a 10s Stripe timeout for the
demo, against backend defaults of 40s and 30s (`demo/README.md`, "Timing"). If the page shows "Run live is off on
this server", a key is missing; fix it before starting (`demo/index.html`).

| clock | on screen | click | say |
|---|---|---|---|
| 0:00 | Header "One crash, the same refund, two setups"; the Scenario select shows "Hand refund during the outage"; the story line below the header describes it | nothing. Leave "Live only: add Temporal plus a hand-written check" unchecked | "Production agents run on durable orchestration like Temporal. Left: the standard setup, Temporal plus a Stripe idempotency key. Right: the same workflow with Interlock as the refund step. Real Stripe test mode, a real Claude model, a real process kill." |
| 0:12 | | **Run live** | "One click. Every call is real: Stripe, the model, Temporal, a real SIGKILL. The crash point and the hand refund are injected by the demo so the timing is repeatable." |
| 0:13 (t=1s) | Green banner "LIVE RUN: Stripe test mode, claude-haiku-4-5-20251001, Temporal dev server, worker processes killed with SIGKILL." CASE rows: $100.00 paid, one refund of at most $20.00 approved. WORKER rows: set to SIGKILL itself right before the refund call | | "Each column just took a real $100 payment, and support approved one $20 refund." |
| 0:17 (t=4.6s) | LLM row: the model read the payment and called issue_refund for 2000 cents | | "The model decides $20." |
| 0:18 (t=5.1s to 6.2s) | Right column: JOURNAL rows PROPOSED, AUTHORIZED, DISPATCHED "on disk before the refund call", then CRASH exit code -9 (SIGKILL) in both columns. Then HAND REFUND rows and WORKER restarted | | "On the right, the intent and the facts it relied on are on disk before anything is sent. Both workers are killed right before calling Stripe, and while they are down the demo issues a $20 refund the way support would from the dashboard: no idempotency key, no metadata." |
| 0:19 to 0:31 | Nothing new until Temporal's activity timeout | | "Temporal does exactly what it promises: it will retry the step. The question is whether the retry should still happen." |
| 0:32 (t=19.6s) | TEMPORAL rows: refund attempt 2 after an activity StartToClose timeout | | "Here is the retry." |
| 0:33 (t=21.8s) | Left: STRIPE "Stripe now lists refund ... sent by the agent's workflow" | | "The standard setup sends a second refund. The idempotency key cannot help: the hand refund was a different request." |
| 0:34 (t=22.1s) | Right: JOURNAL "REFUSED: stale_premise at recovery, refunded by others: was 0, now 2000" | | "Interlock re-reads the payment first. The facts changed, so it refuses." |
| 0:36 (t=23.6s) | Status "Run ... finished in 23.6s." Left card red: "Violated: $20.00 too much", "2 refunds, $40.00 refunded". Right card green: "Held", "1 refund, $20.00 refunded" | | "Before: $40 out the door. After: $20, the hand refund only. Those refund ids are re-read from Stripe, not from our logs." |
| 0:45 | Right card, receipt lines: "Interlock receipt for effect ...: PROPOSED, AUTHORIZED, DISPATCHED, REFUSED." and "Verified from its entries: valid true, chain intact true, happened false, this effect committed at most once true ... signed no (no key configured)" | | "This is the receipt: what was proposed, what was checked when it would have fired, and why it stopped. It is the gate's own record, unsigned here; Stripe is the evidence. This page does not export it. The receipts from our end-to-end run were exported by a separate script to Cloud Logging and BigQuery and read back live." |
| 0:62 | Left card, "Payment in Stripe" link | optional: **Payment in Stripe** (needs the Stripe test dashboard logged in on this laptop) | "Two refund objects on the left payment in Stripe's own dashboard." |
| 0:72 | Controls area, "Run mock (simulated, no Stripe)" button | do not click | "That second button is a simulation for when there is no network. It is labeled MOCK on every line. Nothing you just saw came from it." |
| 0:80 | | | "Interlock is middleware: the same gate runs as a Temporal activity, an ADK tool callback, or in front of an MCP server. AP2 carries the proof of what was authorized; Interlock re-checks it when the effect fires, lets it land at most once, and writes the receipt." |
| 0:90 | | | end |

Where the script's timing comes from: the run took 25.1s from click to the finished page as the browser saw it, and
the page's own clock says 23.6s; the event times in the table are the recorded ones (`results/demo_live.md`,
`results/demo_live.json`). A live run will vary; the step that dominates is Temporal's 15s activity timeout before
the retry (`demo/README.md`, "Timing").

**Questions you will get, and the one-click answer.**

- "What about a revoked approval?" Choose "Approval revoked during the outage", tick "Live only: add Temporal plus a
  hand-written check", click **Run live**. Recorded run `49da4aa4cf`: plain Temporal refunded $20 against the revoked
  approval (Violated), the hand-written check refused with `REFUSED:lease`, Interlock refused with
  `REFUSED:lease_at_recovery`, and the page finished 25.1s after the click (`results/demo_live_revoked.md`). The
  page heading still says "two setups" with three columns (`demo/index.html`).
- "Couldn't I write that check myself?" Yes, and it ties on money in every row of the end-to-end and ADK runs; see
  the table above (`results/e2e_live.md`, `results/adk_live.md`).
- "Can the agent just authorize again after a refusal?" Not under the same approval: re-closing the same AP2 mandate
  is held to the first decision's facts and refused; a new mandate from Finance is a new decision
  (`results/adk_mandate_probes.md`).
- If live fails on stage: click **Run mock (simulated, no Stripe)** and say it is a simulation. The page then shows a
  striped banner "MOCK RUN: simulated in this process by experiments/refund_agent.py. No Stripe, no model, no
  Temporal, no real crash. Not a live result.", a MOCK badge on every column and event, a status line "Run ...
  (MOCK) finished in 0s.", "MOCK: " in the tab title, and no live settings line (`results/demo_live.md`, "Mock run";
  `results/demo_live_mock_narrow_dark.png`). The mock ignores the hand-written check checkbox (`demo/index.html`, "Live only").

## Honest limits

- **The claim is one machine.** The gate's claim on an effect is atomic across processes on one machine: a local
  SQLite file (`BEGIN IMMEDIATE`) or a flock'd JSONL file (`interlock/journal.py`; `backend/workflows.py` uses
  `journal.db`). Workers on several machines need a shared transactional store, which none of these runs tested:
  every live run had its workers on one host.
- **Emulated rows.** `key_pruned_after_24h` and `no_lookup_after_24h` are emulated: Stripe cannot be made to forget
  an idempotency key on demand, and Interlock's clock was moved 25h ahead (`results/e2e_live.md`, "What is
  emulated"). AMBIGUOUS end to end comes only from the emulated `no_lookup_after_24h` row, because Stripe can always
  be looked up (`results/e2e_live.md`, "Limits"). The demo page never runs emulated: live workers do not inherit
  those switches (`demo/README.md`, "Limits").
- **A hand-written check ties on money, and is faster.** It left Stripe the same as Interlock on 7/7 rows, with a
  median of 15s from crash to close against Interlock's 43s (`results/e2e_live.md`), and on 5/5 ADK rows, 10s
  against 46s (`results/adk_live.md`).
- **Latency.** With the backend's 40s claim TTL, a SIGKILLed sender's claim blocks recovery until it expires, which is
  the 43s median (`results/e2e_live.md`, "Timing"). The demo's 15s TTL brought Interlock to 16.3s against 16.7s for
  plain Temporal (`results/demo_live.md`); that is a demo setting, not the default (`demo/README.md`).
- **Unsigned receipts, and what `happened_once` means.** Every receipt in these runs reports `signed=None`, and each
  is written by the same process that sends: the gate's attestation, not proof (`results/e2e_live.md`,
  `results/demo_live.md`). `happened_once` means this effect id committed at most once; it is true on a receipt that
  never fired, and it does not see other effect ids or hand refunds (`interlock/receipts.py`). Stripe's refund list is
  the evidence (`results/e2e_audit.txt`).
- **It does not recognize the same action.** Interlock refuses because the payment's refunds changed, so an
  unrelated $5 goodwill refund also stopped the approved $20, leaving Stripe short by $20 until a person re-approves
  (`results/e2e_live.md`, `unrelated_refund_during_outage`).
- **What the model says.** Given a refusal, the ADK agent's final message said the refund "was refused with a
  "stale_premise_at_recovery" error. This indicates a business logic issue" in one cell (`results/adk_live.md`, "Model decisions"), even though the tool
  response now says it is not a technical error and not to retry (`interlock/integrations/adk.py`). Re-authorizing
  under the same mandate is refused either way (`results/adk_mandate_probes.md`).
- **AP2 adapter scope.** No refund mandate exists in AP2 v0.2; revocation and reservations are rows in one SQLite
  store, not cryptographic, and atomic across processes on one machine only; a reservation is not released when its
  effect is refused; budget and recurrence constraints always fail closed (`interlock/integrations/ap2.py`,
  `results/adk_mandate_probes.md`, `docs/09-research-ap2.md`). The misuse probes crash in-process, not by SIGKILL
  (`results/adk_mandate_probes.md`).
- **Gemini is not verified live.** The project's key returned `429 RESOURCE_EXHAUSTED` (`docs/09-research-adk.md`,
  "Models" and smoke test); every live cell used Claude Haiku 4.5 (`results/e2e_live.md`, `results/demo_live.md`,
  `results/adk_live.md`). ADK inside Temporal is not built (`docs/09-research-adk.md`).
- **Export.** Cloud Logging dedup is at query time only, and a sink may deliver a re-exported entry twice; sinks were
  not tested. Cloud Trace stores a duplicate span on every re-export. Concurrent BigQuery merges were not tested.
  Nothing was sent to a real SIEM (`results/export_live.md`).
- **The AI Act rows do not apply yet.** Regulation (EU) 2026/1744 moved Chapter III (Arts. 12, 14, 19, 26) to 2
  December 2027 for Annex III systems and 2 August 2028 for Annex I systems (`docs/08-compliance-mapping.md`,
  "Citations").
- **Compliance.** The mapping is evidence, not certification; the PCI DSS 10.2.2 field list and 10.5.1 retention
  come from secondary sources and are marked NOT VERIFIED (`docs/08-compliance-mapping.md`). Cloud Logging's
  `_Default` bucket keeps 30 days, short of both PCI's 12 months and the AI Act's six (`docs/08-compliance-mapping.md`).
- **Demo scope.** Results files exist only for the hand refund and revoked approval scenarios; the "Crash after
  Stripe answered (control)" scenario has no recorded page run (`results/demo_live.md`,
  `results/demo_live_revoked.md`, `demo/README.md`). The API has no auth; it answers only to a 127.0.0.1 or localhost
  Host and takes POSTs only as JSON from its own origin, so another web page cannot start a run, but any local
  process can. One run at a time (`demo/README.md`, "Limits"; `results/demo_live.md`, "Checks").

## Proposed replacement for the README's opening section

README.md belongs to another session. This block is a proposal to replace everything from the title down to, but not
including, `## What it is`. Its citations are links, so the README stays readable.

```markdown
# Interlock

**Middleware for the moment an AI agent's action fires.** It runs inside what already executes your agent's tool
calls (a Temporal activity, a Google ADK tool callback, an MCP server's front door, or a plain Python function) and
checks, at the instant a refund or payment is sent, that the approval is still live, that the facts the decision
relied on still hold, and that this effect has not already been sent. Then it writes a hash-chained receipt of what
it checked. Python, zero dependencies.

## Before and after, on real infrastructure

A $100 Stripe test payment. One $20 refund approved. A Claude model decides the refund, and the Temporal worker is
SIGKILLed right before it calls Stripe. While it is down, support refunds the $20 by hand.

| | Temporal with a Stripe idempotency key | Temporal with Interlock as the refund activity |
|---|---|---|
| after the retry | 2 refunds, $40.00 | 1 refund, $20.00 (the hand one) |
| outcome | `REFUNDED` | `REFUSED:stale_premise_at_recovery`, with a receipt |

Refund ids on both sides were re-read from Stripe after the run ([results/demo_live.md](results/demo_live.md)).
Temporal did what it promises; the idempotency key only matches the same request, and a hand refund is a different
one ([results/e2e_live.md](results/e2e_live.md)).

Run it yourself: `ANTHROPIC_API_KEY=... uv run --no-project --with temporalio python demo/serve.py`, open
`http://127.0.0.1:8787/demo`, click **Run live**. The separate **Run mock (simulated, no Stripe)** button is a
simulation and is labeled MOCK everywhere ([demo/README.md](demo/README.md)).

## Where it plugs in

- **Temporal:** `interlock.temporal.gated()` as the activity body. 22 cells (18 live, 4 with an emulated 24h key
  expiry); in all 22 the workflow's reported outcome matched Stripe's refund list
  ([results/e2e_live.md](results/e2e_live.md), [results/e2e_audit.txt](results/e2e_audit.txt)).
- **Google ADK:** `Guard.before_tool_callback` or one plugin for the whole app. 16 live cells with real crashes and
  ADK's own resume ([results/adk_live.md](results/adk_live.md)).
- **MCP:** a proxy in front of an MCP server, no agent code change; tested as a real process in front of a fake
  server ([tests/test_mcp_proxy.py](tests/test_mcp_proxy.py)).
- **Plain code:** a decorator ([results/stripe_live.md](results/stripe_live.md)).

## With AP2

AP2 carries the signed proof of what was authorized. Interlock re-checks it when the effect fires, lets the effect
land at most once (after a crash it resends only under the same idempotency key inside the provider's key window,
otherwise it looks the effect up or reports AMBIGUOUS), and records that in a receipt; Stripe's refund list is the
evidence. AP2 v0.2 has no revocation and its verifier is stateless ([docs/09-research-ap2.md](docs/09-research-ap2.md));
the adapter re-verifies the mandate at dispatch and after a crash, checks that the payment the refund goes to is the
mandated one as Stripe reports it, reserves each mandate for one effect within its cap, and records the same
reference hash as an AP2 receipt ([interlock/integrations/ap2.py](interlock/integrations/ap2.py),
[results/adk_mandate_probes.md](results/adk_mandate_probes.md)).

## For whom

Risk and Compliance set the approval policy, Platform Engineering installs the gate once per runtime, Finance holds
the authority to grant and revoke. Receipts export to Cloud Logging and BigQuery (both read back live), OpenTelemetry
(a re-export duplicates spans) and SIEM file formats ([docs/08-compliance-mapping.md](docs/08-compliance-mapping.md),
[results/export_live.md](results/export_live.md)).

## What it does not do

A Temporal activity with about ten hand-written re-check lines left Stripe the same as Interlock in every live row,
and recovered faster (15s against 43s median); so did a hand-written ADK callback. Interlock's case is no per-tool
code, a claim across worker processes (on one machine; several machines need a shared store, not tested), AMBIGUOUS
instead of a guess, and a receipt. Receipts in these runs are unsigned. Two scenarios (four cells) are emulated
([results/e2e_live.md](results/e2e_live.md), [docs/08-pitch.md](docs/08-pitch.md)).
```
