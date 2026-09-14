# Closed and protocol competitors: what each checks, when, and what record it keeps

Generated 2026-09-14 00:28 UTC by `experiments/competitor_closed_and_protocols.py`. **Every row is PUBLIC SOURCES, NOT RUN.** Nothing here touched Stripe or a model. Each verdict is read from the linked docs, spec or published source code, and the script re-fetched each source and checked every quoted phrase: **70/70 quotes found** (details at the end). "invariant held" in these tables is what the sources say would happen, not a measurement. Interlock's column is copied from this repo's live results.

Scenarios: (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it; (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage; (3) SIGKILL before the refund POST; the approval is revoked during the outage; (4) two agents, two $20 refunds, one $30 approval cap, racing.

## Summary

| competitor | checks when | record | (1) crash after commit | (2) hand refund in outage | (3) revoked in outage | (4) shared $30 cap |
|---|---|---|---|---|---|---|
| Salus (YC W26) | decision/send time, inside the wrapped executor, immediately before the call | decision_events rows in the hosted Postgres (policy version, rule, evidence, provider status), exportable as CSV/JSON/Markdown | plausibly held (explicit key, or a Stripe key in the tool body); the SDK path does not confirm the refund | plausible only if configured as above | plausibly held | not caught by the documented primitive |
| Maxim Bifrost (MCP gateway) | decision time (the app's approval before the execute call) | Enterprise audit logs of administrative activity, optionally HMAC-signed, with retention and S3/GCS archive | not caught by the gateway (depends on the tool's own key) | not caught | not caught by the gateway | not caught |
| IBM ContextForge (MCP gateway) | decision time (pre-invoke hook) | audit_trails table (action, resource, user, old/new values, requires_review) written for CRUD such as create_tool and delete_tool; invocations recorded as tool metrics; OTel and SIEM export | not caught by the gateway | plausible only with a custom plugin (user code) | plausible only with a policy plugin that reads the approval | not caught |
| LiteLLM: PR #38241 and MCP approval handling | decision time (pre-MCP-call) | Spend logs record the guardrail status and Defender correlation id; Microsoft's audit trail attributes the evaluation to the user | not caught | not caught | not caught | not caught |
| HumanLayer (approval SDK, deprecated) and Orako | decision time only; nothing re-checks between approval and the send, or after a crash | The function call (run_id, call_id, spec, status, comment) in the vendor cloud | not caught by HumanLayer | plausible only by human review | plausibly held, at the cost of a second human review | not caught |
| AP2 alone (Agent Payments Protocol) | authorization time (mandate signing and verification) | Signed mandates and ES256-signed receipts: cryptographic proof of what was authorized, not of what happened once or whether it still held | not caught by AP2 alone | not caught | not caught | not caught by AP2 alone |
| Stripe ACP (Agentic Commerce Protocol) and Shared Payment Tokens | send time, enforced by the receiving service | The seller's and Stripe's own objects and webhooks (Signature and Timestamp request headers are recommended, not required, in the checkout RFC) | held for ACP calls with a stable key; refund not covered by ACP | not caught | held for SPT purchases; not applicable to refunds | not caught |
| **Interlock (measured, live Stripe)** | dispatch and recovery | hash-chained receipt, unsigned | held; COMMITTED_BY_RETRY, 44.0s crash to close (hand check 14.7s); unsigned receipt (results/e2e_live.md crash_after_commit) | held; REFUSED:stale_premise_at_recovery, 43.6s (hand check 16.0s) (results/e2e_live.md) | held; REFUSED:lease_at_recovery, 43.6s (hand check 16.0s) (results/e2e_live.md) | unmodified core 25/40 held; with the CapJournal scenario subclass 40/40, median 40.1s / 41.7s; hand_lock (flock) 40/40 at 0.5s / 1.4s (results/scenarios/shared_cap.md) |

Seconds to settle: not measured for any competitor here. Interlock's settle times above are the measured cost of its claim TTL wait after a SIGKILL.

## Salus (YC W26)

- **Version, license:** salus-ai 0.3.7 on PyPI (uploaded 2026-08-19), MIT per its README; hosted control plane (usesalus.ai), plans from $500/month. GitHub repo named in the README is not public (404).
- **What it checks:** Before a protected tool executes: policy rules, evidence (facts from prior tool outputs and conversation, with source, age and strength), limits, workflow state, confirmation and approval, and a server-side idempotency cache. Non-allow returns a repair hint.
- **When:** decision/send time, inside the wrapped executor, immediately before the call. Recovery: operator-reviewed retry, rollback or compensation from the receipt (Rewind); no automatic crash recovery in the SDK path read.
- **Record:** decision_events rows in the hosted Postgres (policy version, rule, evidence, provider status), exportable as CSV/JSON/Markdown. Conversation turns are hash-chained in the cloud; the SDK source says it has no hash chain. No public source says decision receipts are signed.
- **Lines of user code:** 3 statements per the README quickstart (import, client, protect), plus a policy authored in the hosted dashboard; counted from docs, not from a run (salus_pypi).

| scenario | status | what the sources say | invariant | record | sources |
|---|---|---|---|---|---|
| (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it | PUBLIC SOURCES, NOT RUN | Read from salus/cloud_sdk.py and cloud decide.py. With an explicit stable idempotency_key, the retry gets the cached server decision (24h) and the new process has no local result, so the SDK raises 'Refusing ambiguous duplicate execution': no second send, and the outcome stays unresolved with no provider lookup. With the default key, run_id is random per Salus() instance, so a restarted process asks for a fresh decision and duplicate safety rests on the tool body's own Stripe Idempotency-Key. | plausibly held (explicit key, or a Stripe key in the tool body); the SDK path does not confirm the refund | decision event in hosted Postgres; not stated as signed or tamper-evident | salus_sdk_replay, salus_cloud_idem |
| (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage | PUBLIC SOURCES, NOT RUN | Explicit stable key: the replayed allow is refused as ambiguous, so no agent refund lands (held, but it would also refuse when nothing changed). Default key: a fresh decision, caught only if the policy requires a live refunded-amount fact with a bounded age and the agent re-reads it; the sources show fact age checks but no hand-refund example. | plausible only if configured as above | decision event names the missing or stale fact when it blocks | salus_product, salus_sdk_replay, yc_salus |
| (3) SIGKILL before the refund POST; the approval is revoked during the outage | PUBLIC SOURCES, NOT RUN | Explicit stable key: refused as an ambiguous replay (held). Default key: a fresh decision re-evaluates policy and approvals; the SDK approvals module has a revoke path, but no public source walks through revocation between allow and execution. | plausibly held | decision event; approvals have states and timeouts | salus_sdk_replay, yc_salus |
| (4) two agents, two $20 refunds, one $30 approval cap, racing | PUBLIC SOURCES, NOT RUN | The cumulative limit primitive is session-scoped only ('only session is implemented'); two agents in two sessions are not covered by it. No source shows an atomic cross-session cap reservation. | not caught by the documented primitive | decision events per call | salus_sdk_cap |

Where it does better than Interlock:

- Grounding of arguments against evidence (was the amount taken from the lookup, is the fact fresh): a class of wrong action Interlock does not judge at all (sources: yc_salus, salus_product).
- Brokered execution: on allow it mints a single-use grant and executes server-side, so the agent never holds the credential. Interlock is cooperative code the agent process runs (salus_pypi).
- Repair in the same response, shadow mode per route, approval workflows with Slack, timeouts and escalation chains, hosted dashboard and exports (salus_product, salus_integrations, salus_pypi, salus_sdk_approvals).
- Post-commit, operator-reviewed recovery: a Stripe compensation contract (full refund, verified by polling the refund status) driven from the receipt. Interlock has no post-commit or compensation path (salus_rewind_stripe, salus_rewind_verify, salus_product).
- State lives in a hosted Postgres, so it is not limited to one machine; Interlock's claim is one machine (read from source, not tested).
- A replay without a local result fails immediately in the code read, with no claim TTL wait; not timed here.

Where Interlock does better:

- After a crash the SDK path read raises instead of resolving: no lookup, no retry under the provider key. Interlock resolves by tier (retry under key, lookup, or a recorded AMBIGUOUS) and was measured doing it on Stripe.
- The default idempotency key does not survive a process restart (random run_id), so crash safety needs an explicit key. Interlock binds the effect id to the approved request by construction.
- Premises are re-checked on the recovery path by default. Salus re-checks only through a fresh decision, and only facts the policy names.
- Per-effect hash-chained receipt with verify(); the Salus SDK source says it has no hash chain (both unsigned as far as sources show).
- Zero dependencies and no hosted service; runs offline.

Sources: [yc_salus](https://www.ycombinator.com/companies/salus); [salus_product](https://usesalus.ai/product); [salus_integrations](https://usesalus.ai/integrations); [salus_llms](https://usesalus.ai/llms.txt); [salus_pricing](https://usesalus.ai/pricing); [salus_pypi](https://pypi.org/pypi/salus-ai/0.3.7/json); [salus_sdk_replay](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/cloud_sdk.py`; [salus_sdk_cap](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/temporal/constraints.py`; [salus_sdk_chain](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/enforcement/steps/conversation_bridge.py`; [salus_sdk_approvals](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/approvals/engine.py`; [salus_sdk_revoke](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/approvals/__init__.py`; [salus_cloud_idem](https://pypi.org/pypi/salus-ai/0.3.7/json) member `playground/backend/cloud/routers/decide.py`; [salus_rewind_stripe](https://pypi.org/pypi/salus-ai/0.3.7/json) member `playground/backend/cloud/services/connector_catalog.py`; [salus_rewind_verify](https://pypi.org/pypi/salus-ai/0.3.7/json) member `playground/backend/cloud/services/rewind.py`

## Maxim Bifrost (MCP gateway)

- **Version, license:** Apache-2.0 open-source gateway; audit logs are an Enterprise feature
- **What it checks:** Tool calls are suggestions: the application calls the execute API itself. Agent Mode auto-executes only tools in tools_to_auto_execute. Virtual keys, budgets and rate limits govern LLM usage; guardrails inspect content.
- **When:** decision time (the app's approval before the execute call). Retry: one inline retry on auth failure, never for tools annotated destructive and not idempotent. No crash recovery described.
- **Record:** Enterprise audit logs of administrative activity, optionally HMAC-signed, with retention and S3/GCS archive. Request and MCP logs in the log store; no source says those are signed.

| scenario | status | what the sources say | invariant | record | sources |
|---|---|---|---|---|---|
| (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it | PUBLIC SOURCES, NOT RUN | Crash recovery and idempotency of the tool call are left to the application loop; the gateway itself will not auto-retry a tool annotated destructive and not idempotent. | not caught by the gateway (depends on the tool's own key) | request log; admin audit log is signed but covers administrative activity, not tool effects | bifrost_tool_exec, bifrost_overview |
| (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage | PUBLIC SOURCES, NOT RUN | No fire-time re-check of facts is described; approval is the app's code. | not caught | request log | bifrost_tool_exec |
| (3) SIGKILL before the refund POST; the approval is revoked during the outage | PUBLIC SOURCES, NOT RUN | Approval is whatever the application writes at 'YOUR APPROVAL LOGIC HERE'; nothing re-checks it at send. | not caught by the gateway | request log | bifrost_tool_exec |
| (4) two agents, two $20 refunds, one $30 approval cap, racing | PUBLIC SOURCES, NOT RUN | Budgets are LLM spend governance; no source shows a cap on tool arguments. | not caught | request log | bifrost_agent_mode |

Where it does better than Interlock:

- HMAC-signed audit events with retention and at-least-once archival to object storage (Interlock receipts are unsigned in every live run) (bifrost_audit).
- Explicit rule never to auto-retry destructive, non-idempotent tools, plus clustering, OIDC and budgets (bifrost_tool_exec).

Where Interlock does better:

- Journaled intent before the send, recovery by tier, and premise and lease re-checks at dispatch and recovery; Bifrost documents none of these for tool effects.
- A per-effect receipt of what was checked when it fired; Bifrost's signed log covers administrative activity.

Sources: [bifrost_overview](https://docs.getbifrost.ai/mcp/overview.md); [bifrost_agent_mode](https://docs.getbifrost.ai/mcp/agent-mode.md); [bifrost_tool_exec](https://docs.getbifrost.ai/mcp/tool-execution.md); [bifrost_audit](https://docs.getbifrost.ai/enterprise/audit-logs.md)

## IBM ContextForge (MCP gateway)

- **Version, license:** v1.0.10 (2026-09-07), Apache-2.0
- **What it checks:** Plugin hooks: tool_pre_invoke can modify arguments or block a call; tool_post_invoke sees results. Policy plugins (for example unified_pdp, default deny), RBAC and teams. Elicitation passthrough with a 60s default timeout; the approval-by-elicitation example is for server configuration changes.
- **When:** decision time (pre-invoke hook). Retry policy per tool with max_retries default 2 when configured. No crash recovery of in-flight effects described.
- **Record:** audit_trails table (action, resource, user, old/new values, requires_review) written for CRUD such as create_tool and delete_tool; invocations recorded as tool metrics; OTel and SIEM export. No hash or signature column in the model read.

| scenario | status | what the sources say | invariant | record | sources |
|---|---|---|---|---|---|
| (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it | PUBLIC SOURCES, NOT RUN | No idempotency key or lookup for tool effects is described; a configured retry policy can re-send. | not caught by the gateway | tool metric and logs; not tamper-evident | cf_tool_service |
| (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage | PUBLIC SOURCES, NOT RUN | A custom tool_pre_invoke plugin could re-read Stripe; none ships for this. | plausible only with a custom plugin (user code) | plugin violation logged | cf_plugins |
| (3) SIGKILL before the refund POST; the approval is revoked during the outage | PUBLIC SOURCES, NOT RUN | Same: a pre-invoke policy plugin evaluates at call time if the restarted agent calls again through the gateway. | plausible only with a policy plugin that reads the approval | plugin violation logged | cf_plugins |
| (4) two agents, two $20 refunds, one $30 approval cap, racing | PUBLIC SOURCES, NOT RUN | No shared cap primitive for tool arguments in sources. | not caught | none specific | cf_plugins |

Where it does better than Interlock:

- Federated gateway with RBAC, teams, OTel and SIEM export, and a plugin framework at pre and post invoke (cf_plugins, cf_audit_model).

Where Interlock does better:

- Durable intent, claims and recovery for in-flight effects, and a per-effect chained receipt; the audit model has no chain or signature fields and covers CRUD, not effects.

Sources: [cf_plugins](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/docs/docs/using/plugins/index.md); [cf_audit_model](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/mcpgateway/db.py); [cf_tool_service](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/mcpgateway/services/tool_service.py); [cf_elicitation](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/docs/docs/architecture/adr/022-elicitation-passthrough-implementation.md); [cf_release](https://api.github.com/repos/IBM/mcp-context-forge/releases/latest)

## LiteLLM: PR #38241 and MCP approval handling

- **Version, license:** MIT (litellm). PR #38241 is open, not merged.
- **What it checks:** PR #38241 is not an approval PR: it adds an agent_365 guardrail (mode pre_mcp_call) that sends each MCP tool call to Microsoft Agent 365 / Defender for an allow or block verdict, fail_closed by default. Shipped code auto-executes MCP tools only when every reference sets require_approval=never; otherwise tool calls go back to the caller. Separate open third-party PR #37192 proposes a SHA-256 hash-chained JSONL Action Ledger.
- **When:** decision time (pre-MCP-call). No crash recovery.
- **Record:** Spend logs record the guardrail status and Defender correlation id; Microsoft's audit trail attributes the evaluation to the user. #37192 (unmerged) would add an unsigned hash chain written post-call.

| scenario | status | what the sources say | invariant | record | sources |
|---|---|---|---|---|---|
| (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it | PUBLIC SOURCES, NOT RUN | Verdicts are about threat and policy at call time; no idempotency, premise, revocation window or shared cap is described. | not caught | spend log entry; Microsoft audit trail (not tamper-evidence we can check) | litellm_38241 |
| (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage | PUBLIC SOURCES, NOT RUN | Verdicts are about threat and policy at call time; no idempotency, premise, revocation window or shared cap is described. | not caught | spend log entry; Microsoft audit trail (not tamper-evidence we can check) | litellm_38241 |
| (3) SIGKILL before the refund POST; the approval is revoked during the outage | PUBLIC SOURCES, NOT RUN | Verdicts are about threat and policy at call time; no idempotency, premise, revocation window or shared cap is described. | not caught | spend log entry; Microsoft audit trail (not tamper-evidence we can check) | litellm_38241 |
| (4) two agents, two $20 refunds, one $30 approval cap, racing | PUBLIC SOURCES, NOT RUN | Verdicts are about threat and policy at call time; no idempotency, premise, revocation window or shared cap is described. | not caught | spend log entry; Microsoft audit trail (not tamper-evidence we can check) | litellm_38241 |

Where it does better than Interlock:

- Per-user attribution through Entra On-Behalf-Of and Defender threat detection on tool arguments; Interlock records who granted a lease but not who may (litellm_38241).
- Fail-closed default when approval is mixed within a request (litellm_autoexec).

Where Interlock does better:

- Everything about effects after the verdict: journal, claims, recovery and receipts.

Sources: [litellm_38241](https://api.github.com/repos/BerriAI/litellm/pulls/38241); [litellm_autoexec](https://raw.githubusercontent.com/BerriAI/litellm/main/litellm/responses/mcp/litellm_proxy_mcp_handler.py); [litellm_37192](https://api.github.com/repos/BerriAI/litellm/pulls/37192)

## HumanLayer (approval SDK, deprecated) and Orako

- **Version, license:** humanlayer 0.7.9 on PyPI (2025-06-03), Apache-2.0 per its README; the vendor now sells a coding IDE. Orako is a hosted ask-a-human service for coding agents.
- **What it checks:** require_approval creates a function call in HumanLayer cloud and polls every 3s until a person approves or denies; on approval it runs the function. Orako routes questions to domain owners; it does not gate effects.
- **When:** decision time only; nothing re-checks between approval and the send, or after a crash.
- **Record:** The function call (run_id, call_id, spec, status, comment) in the vendor cloud. Not described as signed.

| scenario | status | what the sources say | invariant | record | sources |
|---|---|---|---|---|---|
| (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it | PUBLIC SOURCES, NOT RUN | Read from approval.py: a re-run creates a new call_id, so a person is asked again and an approval runs the function again; duplicate safety is the tool body's own key. | not caught by HumanLayer | two approval records | humanlayer_sdk |
| (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage | PUBLIC SOURCES, NOT RUN | The re-run asks a person again; whether they notice the hand refund is judgment, not a mechanical check. | plausible only by human review | approval record | humanlayer_sdk |
| (3) SIGKILL before the refund POST; the approval is revoked during the outage | PUBLIC SOURCES, NOT RUN | The re-run needs a new approval, so a person who revoked would deny it. | plausibly held, at the cost of a second human review | approval record | humanlayer_sdk |
| (4) two agents, two $20 refunds, one $30 approval cap, racing | PUBLIC SOURCES, NOT RUN | Two separate approvals; no shared state. | not caught | approval records | humanlayer_sdk |

Where it does better than Interlock:

- Real people in Slack and email, routing and escalation, deny-with-feedback to the agent (humanlayer_sdk).

Where Interlock does better:

- Mechanical checks at fire time and after a crash with no second human review; the SDK's poll loop has no timeout and no recovery.

Sources: [humanlayer_sdk](https://pypi.org/pypi/humanlayer/0.7.9/json) member `humanlayer/core/approval.py`; [orako_compare](https://orako.io/compare/humanlayer-alternative)

## AP2 alone (Agent Payments Protocol)

- **Version, license:** v0.2.0, repo google-agentic-commerce/AP2 at e1ea56d, Apache-2.0
- **What it checks:** Signed SD-JWT Checkout and Payment Mandates, open or closed, with amount range, payee, instrument, currency and date constraints; verifier-signed receipts.
- **When:** authorization time (mandate signing and verification). The spec assigns double-spend prevention and mandate management to stateful parties.
- **Record:** Signed mandates and ES256-signed receipts: cryptographic proof of what was authorized, not of what happened once or whether it still held.

| scenario | status | what the sources say | invariant | record | sources |
|---|---|---|---|---|---|
| (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it | PUBLIC SOURCES, NOT RUN | The SDK verifier is stateless; this project's probe accepted the same presentation twice (docs/09-research-ap2.md, probe 2, run locally, not against Stripe). | not caught by AP2 alone | signed mandate; signed receipt only if the verifier issues one | ap2_local_research |
| (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage | PUBLIC SOURCES, NOT RUN | No refund mandate and no premise concept in v0.2. | not caught | signed mandate | ap2_local_research |
| (3) SIGKILL before the refund POST; the approval is revoked during the outage | PUBLIC SOURCES, NOT RUN | v0.2 has no revocation. | not caught | signed mandate | ap2_local_research |
| (4) two agents, two $20 refunds, one $30 approval cap, racing | PUBLIC SOURCES, NOT RUN | Budget checks need a caller-supplied usage context; a stale context was accepted in the local probe (probe 14). | not caught by AP2 alone | signed mandate | ap2_local_research |

Where it does better than Interlock:

- Cryptographically signed authorization and receipts; Interlock receipts are unsigned in every live run.

Where Interlock does better:

- State: at-most-once landing, revocation, re-check at dispatch and recovery. Measured with the AP2 adapter on Stripe (results/adk_live.md, results/adk_mandate_probes.md).

Sources: `docs/09-research-ap2.md`; [ap2_repo](https://api.github.com/repos/google-agentic-commerce/AP2)

## Stripe ACP (Agentic Commerce Protocol) and Shared Payment Tokens

- **Version, license:** spec 2026-04-17, Apache-2.0, maintained by OpenAI, Stripe and Meta; SPTs are a Stripe preview API
- **What it checks:** Server side on every POST: Idempotency-Key required; same key and body replays the original response without re-executing side effects; a different body is 422; in flight is 409. Delegated payment tokens are one-time with max_amount and expires_at; an SPT the agent revokes cannot pay.
- **When:** send time, enforced by the receiving service. Post-commit: order webhooks carry adjustments for refunds and disputes, and a token deactivated webhook.
- **Record:** The seller's and Stripe's own objects and webhooks (Signature and Timestamp request headers are recommended, not required, in the checkout RFC).

| scenario | status | what the sources say | invariant | record | sources |
|---|---|---|---|---|---|
| (1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it | PUBLIC SOURCES, NOT RUN | For ACP POSTs, a retry with the same key and body returns the original response without re-executing. Refunds are out of scope of the delegate payment RFC, so this refund scenario is not an ACP call; Stripe's own refund idempotency key is the analogue (already measured as 'no check' columns). | held for ACP calls with a stable key; refund not covered by ACP | service-side objects | acp_checkout, acp_delegate |
| (2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage | PUBLIC SOURCES, NOT RUN | A hand refund is a different request; key replay does not match it. | not caught | order adjustments would show both refunds after the fact | acp_checkout, acp_orders |
| (3) SIGKILL before the refund POST; the approval is revoked during the outage | PUBLIC SOURCES, NOT RUN | For purchases, a revoked SPT cannot create a payment, enforced by Stripe. No refund-approval object exists. | held for SPT purchases; not applicable to refunds | shared_payment.granted_token.deactivated webhook | stripe_spt |
| (4) two agents, two $20 refunds, one $30 approval cap, racing | PUBLIC SOURCES, NOT RUN | Allowance is per one-time token; no shared cap across tokens. | not caught | per-token usage_limits | acp_delegate, stripe_spt |

Where it does better than Interlock:

- Enforced by the receiver, so a crashed or buggy client cannot bypass it; explicit 409 in-flight and 422 payload-conflict signals (acp_checkout).
- Revocation effective at the payment service, plus a deactivated webhook (stripe_spt).
- Post-commit visibility: order adjustments for refunds and disputes, the data a chargeback watch needs; Interlock has no post-commit watch (acp_orders).

Where Interlock does better:

- Works for effects the protocol does not define (refunds, other services) and re-checks agent-side premises such as a hand refund. Measured on Stripe.

Sources: [acp_checkout](https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.agentic_checkout.md); [acp_delegate](https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.delegate_payment.md); [acp_orders](https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.orders.md); [stripe_acp](https://docs.stripe.com/agentic-commerce/acp.md); [stripe_spt](https://docs.stripe.com/agentic-commerce/concepts/shared-payment-tokens.md?agent-seller=seller)

## Reading this honestly

- The strongest competitor on this list is Salus. From its published SDK source it already covers pieces Interlock pitches (an idempotency cache, refusing an ambiguous replay, approvals with timeouts, a receipt per decision) and several Interlock lacks (argument grounding, brokered single-use credentials, reviewed compensation after commit, hosted multi-machine state). Where the code read suggests Interlock is ahead is crash resolution: the Salus SDK path raises on an ambiguous replay instead of resolving by lookup or provider key, and its default idempotency key does not survive a process restart. That is read from code, not measured.
- `salus-ai` 0.3.7 is MIT on PyPI and its README describes a local quickstart, so a live run may be possible. It was out of scope for this report (the brief classed Salus as not runnable) and is the obvious next experiment.
- The research notes (`kiro-research.md` section 3.3) call LiteLLM PR #38241 an approval PR. It is not: it is a Microsoft Agent 365 pre-call guardrail. The notes' label should be corrected.
- Receipts: Bifrost Enterprise signs administrative audit events with HMAC, and AP2 signs mandates and receipts. Interlock's receipts were unsigned in every live run, so "signed record" is not an Interlock advantage over them.
- Post-commit: ACP order adjustments (refunds, disputes) and Salus Rewind act after commit. Interlock has nothing there (the chargeback after a successful refund in `results/scenarios/stripe_dispute.md`).
- No competitor's sources show a shared cap across agents or sessions that is reserved atomically. Interlock's core did not hold one either (25/40); only a scenario subclass did.

## Source verification

| source | fetched | http | sha256 (first 16) | quotes found |
|---|---|---|---|---|
| [yc_salus](https://www.ycombinator.com/companies/salus) | 2026-09-14T00:28:52+00:00 | 200 |59fe995cbe6847a7 | 3/3 |
| [salus_product](https://usesalus.ai/product) | 2026-09-14T00:28:52+00:00 | 200 |1b9739cb81c62e79 | 3/3 |
| [salus_integrations](https://usesalus.ai/integrations) | 2026-09-14T00:28:53+00:00 | 200 |dc0f1020c3642630 | 1/1 |
| [salus_pricing](https://usesalus.ai/pricing) | 2026-09-14T00:28:53+00:00 | 200 |18452d44eb4ae406 | 1/1 |
| [salus_sdk_approvals](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/approvals/engine.py` | 2026-09-14T00:28:53+00:00 | 200 |c0161c15a415adb6 | 1/1 |
| [salus_sdk_revoke](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/approvals/__init__.py` | 2026-09-14T00:28:53+00:00 | 200 |f1f0577da01030a0 | 1/1 |
| [salus_rewind_verify](https://pypi.org/pypi/salus-ai/0.3.7/json) member `playground/backend/cloud/services/rewind.py` | 2026-09-14T00:28:53+00:00 | 200 |8eee2d8f9cd9c67b | 2/2 |
| [salus_llms](https://usesalus.ai/llms.txt) | 2026-09-14T00:28:54+00:00 | 200 |dedcfb4695c816a9 | 1/1 |
| [salus_pypi](https://pypi.org/pypi/salus-ai/0.3.7/json) | 2026-09-14T00:28:54+00:00 | 200 |dd88f102e125b313 | 6/6 |
| [salus_sdk_replay](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/cloud_sdk.py` | 2026-09-14T00:28:54+00:00 | 200 |c61ed5138760f1a0 | 4/4 |
| [salus_sdk_cap](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/temporal/constraints.py` | 2026-09-14T00:28:54+00:00 | 200 |fd9ecf0144242953 | 1/1 |
| [salus_sdk_chain](https://pypi.org/pypi/salus-ai/0.3.7/json) member `salus/enforcement/steps/conversation_bridge.py` | 2026-09-14T00:28:54+00:00 | 200 |84e1d68cb5b9508e | 1/1 |
| [salus_cloud_idem](https://pypi.org/pypi/salus-ai/0.3.7/json) member `playground/backend/cloud/routers/decide.py` | 2026-09-14T00:28:54+00:00 | 200 |6066fa348d54a7e2 | 2/2 |
| [salus_rewind_stripe](https://pypi.org/pypi/salus-ai/0.3.7/json) member `playground/backend/cloud/services/connector_catalog.py` | 2026-09-14T00:28:54+00:00 | 200 |f6541d2ea3488ee3 | 1/1 |
| [bifrost_overview](https://docs.getbifrost.ai/mcp/overview.md) | 2026-09-14T00:28:54+00:00 | 200 |0b179d87dc63b522 | 1/1 |
| [bifrost_agent_mode](https://docs.getbifrost.ai/mcp/agent-mode.md) | 2026-09-14T00:28:55+00:00 | 200 |a0b877bec29fe4e1 | 2/2 |
| [bifrost_tool_exec](https://docs.getbifrost.ai/mcp/tool-execution.md) | 2026-09-14T00:28:55+00:00 | 200 |51c71502b9d647c1 | 3/3 |
| [bifrost_audit](https://docs.getbifrost.ai/enterprise/audit-logs.md) | 2026-09-14T00:28:55+00:00 | 200 |3445c7d03ec90c3e | 2/2 |
| [cf_plugins](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/docs/docs/using/plugins/index.md) | 2026-09-14T00:28:55+00:00 | 200 |7e1d7cad7066bae3 | 1/1 |
| [cf_audit_model](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/mcpgateway/db.py) | 2026-09-14T00:28:55+00:00 | 200 |e4308722feeab90a | 2/2 |
| [cf_tool_service](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/mcpgateway/services/tool_service.py) | 2026-09-14T00:28:55+00:00 | 200 |c33777d9902dc2b8 | 2/2 |
| [cf_elicitation](https://raw.githubusercontent.com/IBM/mcp-context-forge/main/docs/docs/architecture/adr/022-elicitation-passthrough-implementation.md) | 2026-09-14T00:28:55+00:00 | 200 |288c552463fad4eb | 1/1 |
| [cf_release](https://api.github.com/repos/IBM/mcp-context-forge/releases/latest) | 2026-09-14T00:28:55+00:00 | 200 |faf0b7d8eb93fce0 | 1/1 |
| [litellm_38241](https://api.github.com/repos/BerriAI/litellm/pulls/38241) | 2026-09-14T00:28:56+00:00 | 200 |ab7b8e6a64ec4d46 | 4/4 |
| [litellm_37192](https://api.github.com/repos/BerriAI/litellm/pulls/37192) | 2026-09-14T00:28:56+00:00 | 200 |c6be1b0490adabca | 2/2 |
| [litellm_autoexec](https://raw.githubusercontent.com/BerriAI/litellm/main/litellm/responses/mcp/litellm_proxy_mcp_handler.py) | 2026-09-14T00:28:56+00:00 | 200 |e74009a3d50573b7 | 1/1 |
| [humanlayer_sdk](https://pypi.org/pypi/humanlayer/0.7.9/json) member `humanlayer/core/approval.py` | 2026-09-14T00:28:56+00:00 | 200 |f24c1025a3327767 | 3/3 |
| [orako_compare](https://orako.io/compare/humanlayer-alternative) | 2026-09-14T00:28:57+00:00 | 200 |9523fc2a1061bed0 | 1/1 |
| `docs/09-research-ap2.md` | 2026-09-14T00:28:57+00:00 |  |2c6e1e637c60ef58 | 4/4 |
| [ap2_repo](https://api.github.com/repos/google-agentic-commerce/AP2) | 2026-09-14T00:28:57+00:00 | 200 |13f72436ba8ab64a | 2/2 |
| [acp_checkout](https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.agentic_checkout.md) | 2026-09-14T00:28:57+00:00 | 200 |6dd81e0f3e0767a3 | 3/3 |
| [acp_delegate](https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.delegate_payment.md) | 2026-09-14T00:28:57+00:00 | 200 |d9086ccbd0e8ec66 | 2/2 |
| [acp_orders](https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.orders.md) | 2026-09-14T00:28:57+00:00 | 200 |507ec20e5c10409a | 1/1 |
| [stripe_acp](https://docs.stripe.com/agentic-commerce/acp.md) | 2026-09-14T00:28:57+00:00 | 200 |8b232429d1f54d39 | 1/1 |
| [stripe_spt](https://docs.stripe.com/agentic-commerce/concepts/shared-payment-tokens.md?agent-seller=seller) | 2026-09-14T00:28:58+00:00 | 200 |818816fdfd05358f | 3/3 |

## Re-run

    python3 experiments/competitor_closed_and_protocols.py
