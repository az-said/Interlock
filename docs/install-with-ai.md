# Install Interlock with your coding agent

Paste the prompt below into Claude Code, Cursor, Codex, Copilot or any coding agent, from the root of the system
you want to protect. The landing page's "Copy prompt" button copies the same text; `tests/test_site.py` keeps the
two identical.

<!-- prompt:start -->
```text
Install Interlock (https://github.com/az-said/Interlock) into this codebase. Interlock journals each external side effect before it is sent, re-checks the facts the decision relied on right before the send and again after a crash, and recovers by what the target service supports. Work in small, reviewable steps.

1. Detect the stack and the orchestrator: plain Python, Temporal, MCP servers, OpenAI or Anthropic tool-calling loops, LangChain or LangGraph, or Google ADK. Interlock is Python; if an effect is sent from another language, report it and skip it.

2. Find every tool call or function with an external side effect: payments, refunds, payouts, emails, messages, merges, deploys, writes to other systems. Skip pure reads.

3. For each effect, decide and write down:
   - Effect key: built from the approved request (order id, case id, ticket id). Never from model output such as an amount or text the model produced.
   - Premises: the facts the decision relies on (still eligible, already refunded, still approved) and the exact call that re-reads each one from the system of record. A premise that would count this effect's own result takes idempotency_key and excludes it.
   - Tier: 1 if the service dedupes on a key you pass (dedupes=True), 2 if you can look up whether it already happened (lookup=), 3 if neither.

4. Install with: pip install git+https://github.com/az-said/Interlock
   Wrap each effect with the matching integration:
   - Plain Python: gate = Interlock(".interlock") and @gate.effect(key=..., premises=..., dedupes=True or lookup=...).
   - Temporal: the activity body returns interlock.temporal.gated(fn.gate, fn.proposal(...)).
   - MCP servers: python3 -m interlock.mcp_proxy --config interlock.mcp.json -- <server command>, with key, premises, lookup and idempotency_argument per gated tool.
   - OpenAI or Anthropic tool loops: interlock.tools.protect(tools, config); return out["message"] to the model.
   - LangChain or LangGraph: interlock.langchain_tools.protect_tools(tools, config).
   - Google ADK: interlock.integrations.adk.Guard, passed as before_tool_callback.
   Do not change prompts, models or planning code.

5. Call recover once on startup, before new work: gate.recover(), tools.recover() or guard.recover().

6. Add a test per effect that crashes after the send and asserts exactly one effect. For a decorated function: fn.gate.submit(fn.proposal(*args), crash_after_effect=True) raises SimulatedCrash; then simulate the restart: create a new Interlock on the same directory, decorate the same function on it again, call its recover() and check the status (AMBIGUOUS for tier 3), and assert the target recorded one effect.

7. Never claim exactly-once for a tier 3 service. After a crash it can end AMBIGUOUS, and that case goes to a person.

8. Run the existing tests and the new ones.

Finish with a report: each effect you wrapped (file, function, key, premises, tier, integration); each effect you could not wrap, and why; which tier 3 effects can end AMBIGUOUS; and the test results.
```
<!-- prompt:end -->
