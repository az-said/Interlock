"""
Closed and protocol competitors: Salus, MCP gateways (Bifrost, IBM ContextForge, LiteLLM), HumanLayer/Orako,
AP2 alone, Stripe ACP. None of them is run against Stripe here: each row is PUBLIC SOURCES, NOT RUN.

What this script does instead of a live run:
  1. Re-fetches every primary source (docs pages, spec files, repo source, PyPI sdists, GitHub API) and checks
     that every quoted phrase the report relies on is still present, recording HTTP status, sha256 and fetch time.
  2. Writes results/competitors/closed_and_protocols.json and .md from the table below, with the verification.

Every claim in a cell names the quote(s) it rests on. Scenario verdicts are "caught / not caught / plausible only
if ..." read from those sources, never measured. Interlock's numbers are copied from this repo's results files.

    python3 experiments/competitor_closed_and_protocols.py            # fetch, verify, write
    python3 experiments/competitor_closed_and_protocols.py --offline  # write without fetching (verification: skipped)
"""
import datetime, hashlib, html, io, json, os, re, sys, tarfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "competitors")
UA = {"User-Agent": "Mozilla/5.0 (interlock competitor source check)"}

SCENARIOS = {
    "s1_crash_after_commit": "(1) worker SIGKILLed after Stripe committed the $20 refund, before anything recorded it",
    "s2_hand_refund_during_outage": "(2) SIGKILL before the refund POST; support refunds the $20 by hand during the outage",
    "s3_approval_revoked_during_outage": "(3) SIGKILL before the refund POST; the approval is revoked during the outage",
    "s4_shared_cap_race": "(4) two agents, two $20 refunds, one $30 approval cap, racing",
}

# Interlock's measured reference for the same four scenarios (copied, not re-run).
INTERLOCK = {
    "s1_crash_after_commit": "held; COMMITTED_BY_RETRY, 44.0s crash to close (hand check 14.7s); unsigned receipt "
                             "(results/e2e_live.md crash_after_commit)",
    "s2_hand_refund_during_outage": "held; REFUSED:stale_premise_at_recovery, 43.6s (hand check 16.0s) (results/e2e_live.md)",
    "s3_approval_revoked_during_outage": "held; REFUSED:lease_at_recovery, 43.6s (hand check 16.0s) (results/e2e_live.md)",
    "s4_shared_cap_race": "unmodified core 25/40 held; with the CapJournal scenario subclass 40/40, median 40.1s / 41.7s; "
                          "hand_lock (flock) 40/40 at 0.5s / 1.4s (results/scenarios/shared_cap.md)",
}

# kind: "page" (HTML or text, tags stripped), "json" (fields joined), "sdist" (member of a PyPI sdist), "file" (repo file)
SOURCES = {
    "yc_salus": {"kind": "page", "url": "https://www.ycombinator.com/companies/salus", "quotes": [
        "Salus maintains an evidence cache for each run that every proposed action is validated against",
        "PII detection, budget/loop protection, idempotency, human-in-the-loop escalation, content moderation",
        "In our benchmarks, 58% of blocked actions recover and complete the task correctly"]},
    "salus_product": {"kind": "page", "url": "https://usesalus.ai/product", "quotes": [
        "Every consequential action produces a receipt showing what was proposed, what Salus checked, why it decided, and whether execution occurred.",
        "For configured tools, use the receipt to review and approve a retry, rollback, or compensation path.",
        "Export decisions in CSV, JSON, agent JSON, or Markdown."]},
    "salus_integrations": {"kind": "page", "url": "https://usesalus.ai/integrations", "quotes": [
        "Run any protected action path in shadow to observe decisions, or enforcement to act on them before execution."]},
    "salus_pricing": {"kind": "page", "url": "https://usesalus.ai/pricing", "quotes": ["$500 / month"]},
    "salus_sdk_approvals": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                            "member": "salus/approvals/engine.py", "quotes": [
        "Approval engine with configurable timeout and escalation chains."]},
    "salus_sdk_revoke": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                         "member": "salus/approvals/__init__.py", "quotes": ["def revoke_approval(self, artifact_id: str) -> bool:"]},
    "salus_rewind_verify": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                            "member": "playground/backend/cloud/services/rewind.py", "quotes": [
        "\"url_template\": \"https://api.stripe.com/v1/refunds/{recovery.id}\"", "\"success_equals\": {\"status\": \"succeeded\"}"]},
    "salus_llms": {"kind": "page", "url": "https://usesalus.ai/llms.txt", "quotes": [
        "It checks each proposed tool action against policy and evidence before the action reaches a backend system"]},
    "salus_pypi": {"kind": "json", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                   "fields": ["info.version", "info.author_email", "info.description"], "quotes": [
        "0.3.7", "usesalus.ai",
        "On allow, Salus mints a single-use grant and executes the call server-side",
        "A bare `decide()` is advisory (cooperative).",
        "salus = Salus(api_key=\"sal_...\", mode=\"enforce\")",
        "Escalate high-risk actions to human reviewers. Slack notifications, dashboard UI."]},
    "salus_sdk_replay": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                         "member": "salus/cloud_sdk.py", "quotes": [
        "Refusing ambiguous duplicate execution",
        "self.run_id = _id(\"run\")",
        "The call is not retried automatically because",
        "self._execution_results: dict[str, Any] = {}"]},
    "salus_sdk_cap": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                      "member": "salus/temporal/constraints.py", "quotes": ["only 'session' is implemented"]},
    "salus_sdk_chain": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                        "member": "salus/enforcement/steps/conversation_bridge.py", "quotes": ["The SDK has no hash chain"]},
    "salus_cloud_idem": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                         "member": "playground/backend/cloud/routers/decide.py", "quotes": [
        "idempotency_key_reused_with_different_payload", "now() + interval '24 hours'"]},
    "salus_rewind_stripe": {"kind": "sdist", "url": "https://pypi.org/pypi/salus-ai/0.3.7/json",
                            "member": "playground/backend/cloud/services/connector_catalog.py", "quotes": [
        "Issues a full refund; it does not erase settlement, fees, disputes, or external ledger effects."]},

    "bifrost_overview": {"kind": "page", "url": "https://docs.getbifrost.ai/mcp/overview.md", "quotes": [
        "Tool calls from LLMs are suggestions only - execution requires separate API call"]},
    "bifrost_agent_mode": {"kind": "page", "url": "https://docs.getbifrost.ai/mcp/agent-mode.md", "quotes": [
        "By default, no tools are auto-executed.",
        "Non-auto-executable tools are returned to your application for approval"]},
    "bifrost_tool_exec": {"kind": "page", "url": "https://docs.getbifrost.ai/mcp/tool-execution.md", "quotes": [
        "tools annotated as destructive and not idempotent are never retried",
        "retries the same call inline, exactly once",
        "YOUR APPROVAL LOGIC HERE"]},
    "bifrost_audit": {"kind": "page", "url": "https://docs.getbifrost.ai/enterprise/audit-logs.md", "quotes": [
        "record administrative activity",
        "Audit log entries can be signed with an HMAC key"]},

    "cf_plugins": {"kind": "page", "url": "https://raw.githubusercontent.com/IBM/mcp-context-forge/main/docs/docs/using/plugins/index.md",
                   "quotes": ["Receives the tool name and arguments before execution. Can modify arguments or block the invocation entirely."]},
    "cf_audit_model": {"kind": "page", "url": "https://raw.githubusercontent.com/IBM/mcp-context-forge/main/mcpgateway/db.py",
                       "quotes": ["Comprehensive audit trail for data access and changes.", "requires_review: Mapped[bool]"]},
    "cf_tool_service": {"kind": "page", "url": "https://raw.githubusercontent.com/IBM/mcp-context-forge/main/mcpgateway/services/tool_service.py",
                        "quotes": ["cfg.get(\"max_retries\"), default=2, minimum=0", "action=\"delete_tool\""]},
    "cf_elicitation": {"kind": "page", "url": "https://raw.githubusercontent.com/IBM/mcp-context-forge/main/docs/docs/architecture/adr/022-elicitation-passthrough-implementation.md",
                       "quotes": ["MCPGATEWAY_ELICITATION_TIMEOUT=60"]},
    "cf_release": {"kind": "json", "url": "https://api.github.com/repos/IBM/mcp-context-forge/releases/latest",
                   "fields": ["tag_name", "published_at"], "quotes": ["v1.0.10"]},

    "litellm_38241": {"kind": "json", "url": "https://api.github.com/repos/BerriAI/litellm/pulls/38241",
                      "fields": ["title", "state", "body"], "quotes": [
        "add Microsoft Agent 365 MCP tool-call guardrail", "open",
        "New agent_365 guardrail evaluates every MCP tool call pre-execution",
        "fail_closed by default when unreachable"]},
    "litellm_37192": {"kind": "json", "url": "https://api.github.com/repos/BerriAI/litellm/pulls/37192",
                      "fields": ["title", "state", "body"], "quotes": [
        "Action Ledger exporter", "SHA-256 hash-chained JSONL receipts"]},
    "litellm_autoexec": {"kind": "page", "url": "https://raw.githubusercontent.com/BerriAI/litellm/main/litellm/responses/mcp/litellm_proxy_mcp_handler.py",
                         "quotes": ["Auto-execution requires EVERY MCP reference to opt in with"]},

    "humanlayer_sdk": {"kind": "sdist", "url": "https://pypi.org/pypi/humanlayer/0.7.9/json",
                       "member": "humanlayer/core/approval.py", "quotes": [
        "self.sleep(3)", "call_id = call_id or self.genid(\"call\")", "return fn(*args, **kwargs)"]},
    "orako_compare": {"kind": "page", "url": "https://orako.io/compare/humanlayer-alternative", "quotes": [
        "the approvals API is no longer on the site"]},

    "ap2_local_research": {"kind": "file", "path": "docs/09-research-ap2.md", "quotes": [
        "The SDK verifier is stateless:", "the same presentation verifies twice",
        "**Revocation is not covered.**", "**Refunds are not covered.**"]},
    "ap2_repo": {"kind": "json", "url": "https://api.github.com/repos/google-agentic-commerce/AP2",
                 "fields": ["full_name", "license.spdx_id"], "quotes": ["google-agentic-commerce/AP2", "Apache-2.0"]},

    "acp_checkout": {"kind": "page", "url": "https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.agentic_checkout.md",
                     "quotes": ["Servers **MUST NOT** re-execute side effects (e.g., payment capture, inventory reservation) on replay.",
                                "| Same key, original request still in flight | 409 | `idempotency_in_flight` |",
                                "`Signature: <base64url>` (**RECOMMENDED**)"]},
    "acp_delegate": {"kind": "page", "url": "https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.delegate_payment.md",
                     "quotes": ["multi-use tokens beyond allowance, refund semantics.",
                                "The token **MUST** become invalid at or after `allowance.expires_at`."]},
    "acp_orders": {"kind": "page", "url": "https://raw.githubusercontent.com/agentic-commerce-protocol/agentic-commerce-protocol/main/rfcs/rfc.orders.md",
                   "quotes": ["Track **adjustments** for refunds, credits, returns, and disputes"]},
    "stripe_acp": {"kind": "page", "url": "https://docs.stripe.com/agentic-commerce/acp.md", "quotes": [
        "is an open standard created by Stripe, OpenAI, and Meta"]},
    "stripe_spt": {"kind": "page", "url": "https://docs.stripe.com/agentic-commerce/concepts/shared-payment-tokens.md?agent-seller=seller",
                   "quotes": ["The SPT has been deactivated (consumed, expired, or revoked).",
                              "create a payment with a revoked SPT",
                              "The agent sets the maximum amount to match the total amount of the transaction."]},
}

NR = "PUBLIC_SOURCES"   # every cell: public sources only, not run


def cell(scenario, outcome, invariant, record, sources, lines=None):
    c = {"scenario": scenario, "outcome": "NOT RUN. " + outcome, "invariant_held": invariant,
         "record_quality": record, "status": NR, "ground_truth": "none: not run against Stripe", "sources": sources}
    if lines is not None:
        c["lines_of_user_code"] = lines
    return c


# invariant_held is what the sources say would happen, read from docs or code; never a measurement.
COMPETITORS = [
    {
        "key": "salus",
        "name": "Salus (YC W26)",
        "version_and_license": "salus-ai 0.3.7 on PyPI (uploaded 2026-08-19), MIT per its README; hosted control plane "
                               "(usesalus.ai), plans from $500/month. GitHub repo named in the README is not public (404).",
        "what_it_checks": "Before a protected tool executes: policy rules, evidence (facts from prior tool outputs and "
                          "conversation, with source, age and strength), limits, workflow state, confirmation and approval, "
                          "and a server-side idempotency cache. Non-allow returns a repair hint.",
        "when": "decision/send time, inside the wrapped executor, immediately before the call. Recovery: operator-reviewed "
                "retry, rollback or compensation from the receipt (Rewind); no automatic crash recovery in the SDK path read.",
        "record": "decision_events rows in the hosted Postgres (policy version, rule, evidence, provider status), exportable "
                  "as CSV/JSON/Markdown. Conversation turns are hash-chained in the cloud; the SDK source says it has no hash "
                  "chain. No public source says decision receipts are signed.",
        "lines_note": "3 statements per the README quickstart (import, client, protect), plus a policy authored in the "
                      "hosted dashboard; counted from docs, not from a run (salus_pypi).",
        "sources": ["yc_salus", "salus_product", "salus_integrations", "salus_llms", "salus_pricing", "salus_pypi",
                    "salus_sdk_replay", "salus_sdk_cap", "salus_sdk_chain", "salus_sdk_approvals", "salus_sdk_revoke",
                    "salus_cloud_idem", "salus_rewind_stripe", "salus_rewind_verify"],
        "cells": [
            cell("s1_crash_after_commit",
                 "Read from salus/cloud_sdk.py and cloud decide.py. With an explicit stable idempotency_key, the retry gets "
                 "the cached server decision (24h) and the new process has no local result, so the SDK raises 'Refusing "
                 "ambiguous duplicate execution': no second send, and the outcome stays unresolved with no provider lookup. "
                 "With the default key, run_id is random per Salus() instance, so a restarted process asks for a fresh "
                 "decision and duplicate safety rests on the tool body's own Stripe Idempotency-Key.",
                 "plausibly held (explicit key, or a Stripe key in the tool body); the SDK path does not confirm the refund",
                 "decision event in hosted Postgres; not stated as signed or tamper-evident",
                 ["salus_sdk_replay", "salus_cloud_idem"], lines=3),
            cell("s2_hand_refund_during_outage",
                 "Explicit stable key: the replayed allow is refused as ambiguous, so no agent refund lands (held, but it would "
                 "also refuse when nothing changed). Default key: a fresh decision, caught only if the policy requires a live "
                 "refunded-amount fact with a bounded age and the agent re-reads it; the sources show fact age checks but no "
                 "hand-refund example.",
                 "plausible only if configured as above",
                 "decision event names the missing or stale fact when it blocks",
                 ["salus_product", "salus_sdk_replay", "yc_salus"], lines=3),
            cell("s3_approval_revoked_during_outage",
                 "Explicit stable key: refused as an ambiguous replay (held). Default key: a fresh decision re-evaluates policy "
                 "and approvals; the SDK approvals module has a revoke path, but no public source walks through revocation "
                 "between allow and execution.",
                 "plausibly held",
                 "decision event; approvals have states and timeouts",
                 ["salus_sdk_replay", "yc_salus"], lines=3),
            cell("s4_shared_cap_race",
                 "The cumulative limit primitive is session-scoped only ('only session is implemented'); two agents in two "
                 "sessions are not covered by it. No source shows an atomic cross-session cap reservation.",
                 "not caught by the documented primitive",
                 "decision events per call",
                 ["salus_sdk_cap"]),
        ],
        "where_it_beats_interlock": [
            "Grounding of arguments against evidence (was the amount taken from the lookup, is the fact fresh): a class of "
            "wrong action Interlock does not judge at all (sources: yc_salus, salus_product).",
            "Brokered execution: on allow it mints a single-use grant and executes server-side, so the agent never holds the "
            "credential. Interlock is cooperative code the agent process runs (salus_pypi).",
            "Repair in the same response, shadow mode per route, approval workflows with Slack, timeouts and escalation "
            "chains, hosted dashboard and exports (salus_product, salus_integrations, salus_pypi, salus_sdk_approvals).",
            "Post-commit, operator-reviewed recovery: a Stripe compensation contract (full refund, verified by polling the "
            "refund status) driven from the receipt. Interlock has no post-commit or compensation path "
            "(salus_rewind_stripe, salus_rewind_verify, salus_product).",
            "State lives in a hosted Postgres, so it is not limited to one machine; Interlock's claim is one machine (read "
            "from source, not tested).",
            "A replay without a local result fails immediately in the code read, with no claim TTL wait; not timed here.",
        ],
        "where_interlock_beats_it": [
            "After a crash the SDK path read raises instead of resolving: no lookup, no retry under the provider key. "
            "Interlock resolves by tier (retry under key, lookup, or a recorded AMBIGUOUS) and was measured doing it on Stripe.",
            "The default idempotency key does not survive a process restart (random run_id), so crash safety needs an "
            "explicit key. Interlock binds the effect id to the approved request by construction.",
            "Premises are re-checked on the recovery path by default. Salus re-checks only through a fresh decision, and "
            "only facts the policy names.",
            "Per-effect hash-chained receipt with verify(); the Salus SDK source says it has no hash chain (both unsigned "
            "as far as sources show).",
            "Zero dependencies and no hosted service; runs offline.",
        ],
    },
    {
        "key": "bifrost",
        "name": "Maxim Bifrost (MCP gateway)",
        "version_and_license": "Apache-2.0 open-source gateway; audit logs are an Enterprise feature",
        "what_it_checks": "Tool calls are suggestions: the application calls the execute API itself. Agent Mode auto-executes "
                          "only tools in tools_to_auto_execute. Virtual keys, budgets and rate limits govern LLM usage; "
                          "guardrails inspect content.",
        "when": "decision time (the app's approval before the execute call). Retry: one inline retry on auth failure, never "
                "for tools annotated destructive and not idempotent. No crash recovery described.",
        "record": "Enterprise audit logs of administrative activity, optionally HMAC-signed, with retention and S3/GCS archive. "
                  "Request and MCP logs in the log store; no source says those are signed.",
        "sources": ["bifrost_overview", "bifrost_agent_mode", "bifrost_tool_exec", "bifrost_audit"],
        "cells": [
            cell("s1_crash_after_commit",
                 "Crash recovery and idempotency of the tool call are left to the application loop; the gateway itself will "
                 "not auto-retry a tool annotated destructive and not idempotent.",
                 "not caught by the gateway (depends on the tool's own key)", "request log; admin audit log is signed but "
                 "covers administrative activity, not tool effects", ["bifrost_tool_exec", "bifrost_overview"]),
            cell("s2_hand_refund_during_outage", "No fire-time re-check of facts is described; approval is the app's code.",
                 "not caught", "request log", ["bifrost_tool_exec"]),
            cell("s3_approval_revoked_during_outage",
                 "Approval is whatever the application writes at 'YOUR APPROVAL LOGIC HERE'; nothing re-checks it at send.",
                 "not caught by the gateway", "request log", ["bifrost_tool_exec"]),
            cell("s4_shared_cap_race", "Budgets are LLM spend governance; no source shows a cap on tool arguments.",
                 "not caught", "request log", ["bifrost_agent_mode"]),
        ],
        "where_it_beats_interlock": [
            "HMAC-signed audit events with retention and at-least-once archival to object storage (Interlock receipts are "
            "unsigned in every live run) (bifrost_audit).",
            "Explicit rule never to auto-retry destructive, non-idempotent tools, plus clustering, OIDC and budgets "
            "(bifrost_tool_exec).",
        ],
        "where_interlock_beats_it": [
            "Journaled intent before the send, recovery by tier, and premise and lease re-checks at dispatch and recovery; "
            "Bifrost documents none of these for tool effects.",
            "A per-effect receipt of what was checked when it fired; Bifrost's signed log covers administrative activity.",
        ],
    },
    {
        "key": "contextforge",
        "name": "IBM ContextForge (MCP gateway)",
        "version_and_license": "v1.0.10 (2026-09-07), Apache-2.0",
        "what_it_checks": "Plugin hooks: tool_pre_invoke can modify arguments or block a call; tool_post_invoke sees results. "
                          "Policy plugins (for example unified_pdp, default deny), RBAC and teams. Elicitation passthrough with "
                          "a 60s default timeout; the approval-by-elicitation example is for server configuration changes.",
        "when": "decision time (pre-invoke hook). Retry policy per tool with max_retries default 2 when configured. No crash "
                "recovery of in-flight effects described.",
        "record": "audit_trails table (action, resource, user, old/new values, requires_review) written for CRUD such as "
                  "create_tool and delete_tool; invocations recorded as tool metrics; OTel and SIEM export. No hash or "
                  "signature column in the model read.",
        "sources": ["cf_plugins", "cf_audit_model", "cf_tool_service", "cf_elicitation", "cf_release"],
        "cells": [
            cell("s1_crash_after_commit", "No idempotency key or lookup for tool effects is described; a configured retry "
                 "policy can re-send.", "not caught by the gateway", "tool metric and logs; not tamper-evident",
                 ["cf_tool_service"]),
            cell("s2_hand_refund_during_outage", "A custom tool_pre_invoke plugin could re-read Stripe; none ships for this.",
                 "plausible only with a custom plugin (user code)", "plugin violation logged", ["cf_plugins"]),
            cell("s3_approval_revoked_during_outage", "Same: a pre-invoke policy plugin evaluates at call time if the "
                 "restarted agent calls again through the gateway.", "plausible only with a policy plugin that reads the "
                 "approval", "plugin violation logged", ["cf_plugins"]),
            cell("s4_shared_cap_race", "No shared cap primitive for tool arguments in sources.", "not caught",
                 "none specific", ["cf_plugins"]),
        ],
        "where_it_beats_interlock": [
            "Federated gateway with RBAC, teams, OTel and SIEM export, and a plugin framework at pre and post invoke "
            "(cf_plugins, cf_audit_model).",
        ],
        "where_interlock_beats_it": [
            "Durable intent, claims and recovery for in-flight effects, and a per-effect chained receipt; the audit model has "
            "no chain or signature fields and covers CRUD, not effects.",
        ],
    },
    {
        "key": "litellm",
        "name": "LiteLLM: PR #38241 and MCP approval handling",
        "version_and_license": "MIT (litellm). PR #38241 is open, not merged.",
        "what_it_checks": "PR #38241 is not an approval PR: it adds an agent_365 guardrail (mode pre_mcp_call) that sends each "
                          "MCP tool call to Microsoft Agent 365 / Defender for an allow or block verdict, fail_closed by default. "
                          "Shipped code auto-executes MCP tools only when every reference sets require_approval=never; otherwise "
                          "tool calls go back to the caller. Separate open third-party PR #37192 proposes a SHA-256 hash-chained "
                          "JSONL Action Ledger.",
        "when": "decision time (pre-MCP-call). No crash recovery.",
        "record": "Spend logs record the guardrail status and Defender correlation id; Microsoft's audit trail attributes the "
                  "evaluation to the user. #37192 (unmerged) would add an unsigned hash chain written post-call.",
        "sources": ["litellm_38241", "litellm_autoexec", "litellm_37192"],
        "cells": [
            cell(s, "Verdicts are about threat and policy at call time; no idempotency, premise, revocation window or shared "
                 "cap is described.", "not caught", "spend log entry; Microsoft audit trail (not tamper-evidence we can check)",
                 ["litellm_38241"]) for s in SCENARIOS],
        "where_it_beats_interlock": [
            "Per-user attribution through Entra On-Behalf-Of and Defender threat detection on tool arguments; Interlock "
            "records who granted a lease but not who may (litellm_38241).",
            "Fail-closed default when approval is mixed within a request (litellm_autoexec).",
        ],
        "where_interlock_beats_it": [
            "Everything about effects after the verdict: journal, claims, recovery and receipts.",
        ],
    },
    {
        "key": "humanlayer_orako",
        "name": "HumanLayer (approval SDK, deprecated) and Orako",
        "version_and_license": "humanlayer 0.7.9 on PyPI (2025-06-03), Apache-2.0 per its README; the vendor now sells a coding "
                               "IDE. Orako is a hosted ask-a-human service for coding agents.",
        "what_it_checks": "require_approval creates a function call in HumanLayer cloud and polls every 3s until a person approves "
                          "or denies; on approval it runs the function. Orako routes questions to domain owners; it does not "
                          "gate effects.",
        "when": "decision time only; nothing re-checks between approval and the send, or after a crash.",
        "record": "The function call (run_id, call_id, spec, status, comment) in the vendor cloud. Not described as signed.",
        "sources": ["humanlayer_sdk", "orako_compare"],
        "cells": [
            cell("s1_crash_after_commit", "Read from approval.py: a re-run creates a new call_id, so a person is asked again and "
                 "an approval runs the function again; duplicate safety is the tool body's own key.",
                 "not caught by HumanLayer", "two approval records", ["humanlayer_sdk"]),
            cell("s2_hand_refund_during_outage", "The re-run asks a person again; whether they notice the hand refund is judgment, "
                 "not a mechanical check.", "plausible only by human review", "approval record", ["humanlayer_sdk"]),
            cell("s3_approval_revoked_during_outage", "The re-run needs a new approval, so a person who revoked would deny it.",
                 "plausibly held, at the cost of a second human review", "approval record", ["humanlayer_sdk"]),
            cell("s4_shared_cap_race", "Two separate approvals; no shared state.", "not caught", "approval records",
                 ["humanlayer_sdk"]),
        ],
        "where_it_beats_interlock": [
            "Real people in Slack and email, routing and escalation, deny-with-feedback to the agent (humanlayer_sdk).",
        ],
        "where_interlock_beats_it": [
            "Mechanical checks at fire time and after a crash with no second human review; the SDK's poll loop has no timeout "
            "and no recovery.",
        ],
    },
    {
        "key": "ap2",
        "name": "AP2 alone (Agent Payments Protocol)",
        "version_and_license": "v0.2.0, repo google-agentic-commerce/AP2 at e1ea56d, Apache-2.0",
        "what_it_checks": "Signed SD-JWT Checkout and Payment Mandates, open or closed, with amount range, payee, instrument, "
                          "currency and date constraints; verifier-signed receipts.",
        "when": "authorization time (mandate signing and verification). The spec assigns double-spend prevention and mandate "
                "management to stateful parties.",
        "record": "Signed mandates and ES256-signed receipts: cryptographic proof of what was authorized, not of what happened "
                  "once or whether it still held.",
        "sources": ["ap2_local_research", "ap2_repo"],
        "cells": [
            cell("s1_crash_after_commit", "The SDK verifier is stateless; this project's probe accepted the same presentation "
                 "twice (docs/09-research-ap2.md, probe 2, run locally, not against Stripe).", "not caught by AP2 alone",
                 "signed mandate; signed receipt only if the verifier issues one", ["ap2_local_research"]),
            cell("s2_hand_refund_during_outage", "No refund mandate and no premise concept in v0.2.", "not caught",
                 "signed mandate", ["ap2_local_research"]),
            cell("s3_approval_revoked_during_outage", "v0.2 has no revocation.", "not caught", "signed mandate",
                 ["ap2_local_research"]),
            cell("s4_shared_cap_race", "Budget checks need a caller-supplied usage context; a stale context was accepted in the "
                 "local probe (probe 14).", "not caught by AP2 alone", "signed mandate", ["ap2_local_research"]),
        ],
        "where_it_beats_interlock": [
            "Cryptographically signed authorization and receipts; Interlock receipts are unsigned in every live run.",
        ],
        "where_interlock_beats_it": [
            "State: at-most-once landing, revocation, re-check at dispatch and recovery. Measured with the AP2 adapter on "
            "Stripe (results/adk_live.md, results/adk_mandate_probes.md).",
        ],
    },
    {
        "key": "stripe_acp",
        "name": "Stripe ACP (Agentic Commerce Protocol) and Shared Payment Tokens",
        "version_and_license": "spec 2026-04-17, Apache-2.0, maintained by OpenAI, Stripe and Meta; SPTs are a Stripe preview API",
        "what_it_checks": "Server side on every POST: Idempotency-Key required; same key and body replays the original response "
                          "without re-executing side effects; a different body is 422; in flight is 409. Delegated payment "
                          "tokens are one-time with max_amount and expires_at; an SPT the agent revokes cannot pay.",
        "when": "send time, enforced by the receiving service. Post-commit: order webhooks carry adjustments for refunds and "
                "disputes, and a token deactivated webhook.",
        "record": "The seller's and Stripe's own objects and webhooks (Signature and Timestamp request headers are recommended, "
                  "not required, in the checkout RFC).",
        "sources": ["acp_checkout", "acp_delegate", "acp_orders", "stripe_acp", "stripe_spt"],
        "cells": [
            cell("s1_crash_after_commit", "For ACP POSTs, a retry with the same key and body returns the original response "
                 "without re-executing. Refunds are out of scope of the delegate payment RFC, so this refund scenario is not "
                 "an ACP call; Stripe's own refund idempotency key is the analogue (already measured as 'no check' columns).",
                 "held for ACP calls with a stable key; refund not covered by ACP", "service-side objects",
                 ["acp_checkout", "acp_delegate"]),
            cell("s2_hand_refund_during_outage", "A hand refund is a different request; key replay does not match it.",
                 "not caught", "order adjustments would show both refunds after the fact", ["acp_checkout", "acp_orders"]),
            cell("s3_approval_revoked_during_outage", "For purchases, a revoked SPT cannot create a payment, enforced by "
                 "Stripe. No refund-approval object exists.", "held for SPT purchases; not applicable to refunds",
                 "shared_payment.granted_token.deactivated webhook", ["stripe_spt"]),
            cell("s4_shared_cap_race", "Allowance is per one-time token; no shared cap across tokens.", "not caught",
                 "per-token usage_limits", ["acp_delegate", "stripe_spt"]),
        ],
        "where_it_beats_interlock": [
            "Enforced by the receiver, so a crashed or buggy client cannot bypass it; explicit 409 in-flight and 422 "
            "payload-conflict signals (acp_checkout).",
            "Revocation effective at the payment service, plus a deactivated webhook (stripe_spt).",
            "Post-commit visibility: order adjustments for refunds and disputes, the data a chargeback watch needs; Interlock "
            "has no post-commit watch (acp_orders).",
        ],
        "where_interlock_beats_it": [
            "Works for effects the protocol does not define (refunds, other services) and re-checks agent-side premises "
            "such as a hand refund. Measured on Stripe.",
        ],
    },
]


def _text(raw, is_html):
    t = raw.decode("utf-8", "replace")
    if is_html:
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
        t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def _get(url, cache):
    if url not in cache:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            cache[url] = (r.status, r.read())
    return cache[url]


def _field(obj, path):
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return "" if obj is None else str(obj)


def fetch_text(src, cache):
    kind = src["kind"]
    if kind == "file":
        raw = open(os.path.join(ROOT, src["path"]), "rb").read()
        return None, raw, _text(raw, False)
    status, raw = _get(src["url"], cache)
    if kind == "page":
        return status, raw, _text(raw, b"<html" in raw[:2000].lower() or b"<!doctype html" in raw[:200].lower())
    meta = json.loads(raw)
    if kind == "json":
        return status, raw, re.sub(r"\s+", " ", " | ".join(_field(meta, f) for f in src["fields"]))
    sdist = next(u["url"] for u in meta["urls"] if u["packagetype"] == "sdist")          # kind == "sdist"
    _, tar = _get(sdist, cache)
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        m = next(m for m in tf.getmembers() if m.name.endswith("/" + src["member"]))
        member = tf.extractfile(m).read()
    return status, member, _text(member, False)


def verify(offline):
    cache, out = {}, {}
    for key, src in SOURCES.items():
        rec = {"where": src.get("url") or src["path"], "kind": src["kind"], "member": src.get("member")}
        if offline and src["kind"] != "file":
            rec.update(checked=False, quotes={q: None for q in src["quotes"]})
        else:
            try:
                status, raw, text = fetch_text(src, cache)
                rec.update(checked=True, http_status=status, sha256=hashlib.sha256(raw).hexdigest(),
                           fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                           quotes={q: re.sub(r"\s+", " ", q) in text for q in src["quotes"]})
            except Exception as e:
                rec.update(checked=False, error=f"{type(e).__name__}: {e}", quotes={q: None for q in src["quotes"]})
        out[key] = rec
    return out


def link(key, v):
    s = SOURCES[key]
    where = s.get("url") or s["path"]
    if s["kind"] == "sdist":
        return f"[{key}]({where}) member `{s['member']}`"
    return f"[{key}]({where})" if where.startswith("http") else f"`{where}`"


def render(results, v):
    ok = sum(1 for r in v.values() for x in r["quotes"].values() if x)
    total = sum(len(r["quotes"]) for r in v.values())
    L = ["# Closed and protocol competitors: what each checks, when, and what record it keeps",
         "",
         f"Generated {results['generated_at']} by `experiments/competitor_closed_and_protocols.py`. **Every row is PUBLIC "
         "SOURCES, NOT RUN.** Nothing here touched Stripe or a model. Each verdict is read from the linked docs, spec or "
         "published source code, and the script re-fetched each source and checked every quoted phrase: "
         f"**{ok}/{total} quotes found** (details at the end). \"invariant held\" in these tables is what the sources say "
         "would happen, not a measurement. Interlock's column is copied from this repo's live results.",
         "",
         "Scenarios: " + "; ".join(SCENARIOS.values()) + ".",
         "",
         "## Summary",
         "",
         "| competitor | checks when | record | (1) crash after commit | (2) hand refund in outage | (3) revoked in outage | (4) shared $30 cap |",
         "|---|---|---|---|---|---|---|"]
    for c in COMPETITORS:
        by = {x["scenario"]: x["invariant_held"] for x in c["cells"]}
        L.append(f"| {c['name']} | {c['when'].split('.')[0]} | {c['record'].split('.')[0]} | "
                 + " | ".join(by[s] for s in SCENARIOS) + " |")
    L.append("| **Interlock (measured, live Stripe)** | dispatch and recovery | hash-chained receipt, unsigned | "
             + " | ".join(INTERLOCK[s] for s in SCENARIOS) + " |")
    L += ["", "Seconds to settle: not measured for any competitor here. Interlock's settle times above are the measured cost "
          "of its claim TTL wait after a SIGKILL.", ""]
    for c in COMPETITORS:
        L += [f"## {c['name']}", "", f"- **Version, license:** {c['version_and_license']}",
              f"- **What it checks:** {c['what_it_checks']}", f"- **When:** {c['when']}", f"- **Record:** {c['record']}"]
        if c.get("lines_note"):
            L.append(f"- **Lines of user code:** {c['lines_note']}")
        L += ["","| scenario | status | what the sources say | invariant | record | sources |", "|---|---|---|---|---|---|"]
        for x in c["cells"]:
            L.append(f"| {SCENARIOS[x['scenario']]} | PUBLIC SOURCES, NOT RUN | {x['outcome'][len('NOT RUN. '):]} | "
                     f"{x['invariant_held']} | {x['record_quality']} | {', '.join(x['sources'])} |")
        L += ["", "Where it does better than Interlock:", ""] + [f"- {b}" for b in c["where_it_beats_interlock"]]
        L += ["", "Where Interlock does better:", ""] + [f"- {b}" for b in c["where_interlock_beats_it"]]
        L += ["", "Sources: " + "; ".join(link(k, v) for k, v in [(k, v[k]) for k in c["sources"]]), ""]
    L += ["## Reading this honestly", "",
          "- The strongest competitor on this list is Salus. From its published SDK source it already covers pieces "
          "Interlock pitches (an idempotency cache, refusing an ambiguous replay, approvals with timeouts, a receipt per "
          "decision) and several Interlock lacks (argument grounding, brokered single-use credentials, reviewed "
          "compensation after commit, hosted multi-machine state). Where the code read suggests Interlock is ahead is "
          "crash resolution: the Salus SDK path raises on an ambiguous replay instead of resolving by lookup or provider "
          "key, and its default idempotency key does not survive a process restart. That is read from code, not measured.",
          "- `salus-ai` 0.3.7 is MIT on PyPI and its README describes a local quickstart, so a live run may be possible. "
          "It was out of scope for this report (the brief classed Salus as not runnable) and is the obvious next experiment.",
          "- The research notes (`kiro-research.md` section 3.3) call LiteLLM PR #38241 an approval PR. It is not: it is a "
          "Microsoft Agent 365 pre-call guardrail. The notes' label should be corrected.",
          "- Receipts: Bifrost Enterprise signs administrative audit events with HMAC, and AP2 signs mandates and receipts. "
          "Interlock's receipts were unsigned in every live run, so \"signed record\" is not an Interlock advantage over them.",
          "- Post-commit: ACP order adjustments (refunds, disputes) and Salus Rewind act after commit. Interlock has nothing "
          "there (the chargeback after a successful refund in `results/scenarios/stripe_dispute.md`).",
          "- No competitor's sources show a shared cap across agents or sessions that is reserved atomically. Interlock's "
          "core did not hold one either (25/40); only a scenario subclass did.",
          "", "## Source verification", "", "| source | fetched | http | sha256 (first 16) | quotes found |", "|---|---|---|---|---|"]
    for k, r in v.items():
        found = sum(1 for x in r["quotes"].values() if x)
        L.append(f"| {link(k, r)} | {r.get('fetched_at', 'local file' if r['kind'] == 'file' else 'not fetched')} | "
                 f"{r.get('http_status') or ''} |{r.get('sha256', '')[:16]} | {found}/{len(r['quotes'])}"
                 + (f" ({r['error']})" if r.get("error") else "")
                 + "".join(f"; MISSING: \"{q}\"" for q, x in r["quotes"].items() if x is False) + " |")
    L += ["", "## Re-run", "", "    python3 experiments/competitor_closed_and_protocols.py", ""]
    return "\n".join(L)


def main(argv):
    offline = "--offline" in argv
    v = verify(offline)
    results = {"key": "closed_and_protocols", "generated_at": datetime.datetime.now(datetime.timezone.utc)
               .strftime("%Y-%m-%d %H:%M UTC"), "status": "PUBLIC SOURCES, NOT RUN", "scenarios": SCENARIOS,
               "interlock_reference": INTERLOCK, "competitors": COMPETITORS, "sources": SOURCES, "verification": v}
    md = render(results, v)
    # self-checks: every cell is public-sources-only, cites known sources, and nothing uses an em dash
    for c in COMPETITORS:
        assert {x["scenario"] for x in c["cells"]} == set(SCENARIOS), c["key"]
        for x in c["cells"]:
            assert x["status"] == NR and x["outcome"].startswith("NOT RUN") and set(x["sources"]) <= set(SOURCES), x
    blob = md + json.dumps(results)
    assert "\u2014" not in blob and "\u2013" not in blob, "em or en dash in output"
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "closed_and_protocols.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(OUT, "closed_and_protocols.md"), "w") as f:
        f.write(md)
    missing = [(k, q) for k, r in v.items() for q, x in r["quotes"].items() if x is not True]
    print(f"wrote {OUT}/closed_and_protocols.{{md,json}}; quotes not confirmed: {len(missing)}")
    for k, q in missing:
        print(f"  {k}: {q!r} ({v[k].get('error', 'not found' if v[k]['checked'] else 'not fetched')})")


if __name__ == "__main__":
    main(sys.argv[1:])
