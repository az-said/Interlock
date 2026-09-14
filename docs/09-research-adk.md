# 09. Research: Google Agent Development Kit (ADK) for Python

Checked on 2026-09-13 by installing the package and reading its source. When these notes say "verified", it means the code ran here. When they say "source", it means the installed package code at the path given.

## Version and license

- `google-adk` 2.9.0. That is the latest version on PyPI (checked with `pypi.org/pypi/google-adk/json`). It needs Python 3.10 or newer. It ran here on Python 3.13 through uv.
- License: Apache 2.0 (package `LICENSE` file, and the classifier `License :: OSI Approved :: Apache Software License`).
- Repository: https://github.com/google/adk-python. Docs: https://google.github.io/adk-docs/
- Install: `uv run --no-project --with google-adk --with litellm python ...`. You need `litellm` (or `google-adk[extensions]`) for `LiteLlm`. Without it, `google.adk.models.lite_llm` raises `ImportError: LiteLLM support requires: pip install google-adk[extensions]`.

## Tool callbacks (the hook Interlock would use)

Source: `google/adk/agents/llm_agent.py` lines 101-129 and 530-566.

```python
# before_tool_callback
Callable[[BaseTool, dict[str, Any], ToolContext], Optional[dict] | Awaitable[Optional[dict]]]
# after_tool_callback
Callable[[BaseTool, dict[str, Any], ToolContext, dict[str, Any]], Optional[dict] | Awaitable[Optional[dict]]]
# on_tool_error_callback
Callable[[BaseTool, dict[str, Any], ToolContext, Exception], Optional[dict] | Awaitable[Optional[dict]]]
```

ADK passes these arguments as keywords: `tool=`, `args=`, `tool_context=`, and for the after callback `tool_response=` (source `flows/llm_flows/_tool_caller.py` lines 732-806). Name your parameters to match. A callback can be sync or async. You can also pass a list of callbacks. ADK calls them in order and stops at the first one that returns something other than None (`_stop_on_non_none`).

Execution order, from `_tool_caller.py` lines 720-812:

1. Plugin `before_tool_callback` (`plugin_manager.run_before_tool_callback(tool=, tool_args=, tool_context=)`). Note that the plugin keyword is `tool_args`, not `args`.
2. If the plugin returned None, the agent's `before_tool_callback` runs.
3. If both returned None, the tool body runs. **If either one returns a dict, ADK skips the tool body and uses that dict as the tool response.**
4. If the tool raises, `on_tool_error_callback` runs. A dict it returns becomes the response. If it returns None, the exception is re-raised.
5. Plugin `after_tool_callback`, then the agent's `after_tool_callback`. A dict returned here replaces the response.

**Verified detail that matters for receipts:** the after callbacks also run when a before callback skipped the tool. In the smoke test, the blocked call's response was `{'status': 'blocked', 'reason': 'over limit', 'receipt': 'r1'}`, which means the after callback decorated it. So an after callback cannot assume the tool actually ran. Interlock should record the outcome in the before callback or inside the tool, not infer it in the after callback.

Plugins (`google.adk.plugins.BasePlugin`, passed as `Runner(plugins=[...])` or `App(plugins=[...])`) apply to every agent and tool in the app. For "platform engineering installs it once", a plugin is the right hook, not a per-agent callback.

## ToolContext and session state

- `google.adk.tools.tool_context.ToolContext` is just an alias: `ToolContext = Context` (source `tools/tool_context.py` line 27, class defined in `agents/context.py`).
- Members that are useful to Interlock:
  - `state`: a mutable `State`. Writes are recorded as state deltas on the event and persisted by the session service. Verified: `tool_context.state["gate_seen"] = args` in a before callback showed up in `session.state` afterwards.
  - `function_call_id`: the model's tool call id. This is a natural per-call key.
  - `invocation_id`: the id of the current run. Setting it on `run_async` resumes that run.
  - `session`: the full session.
  - `actions`: `EventActions`, for example `skip_summarization`.
  - `request_confirmation(hint=, payload=)`: human confirmation.
- `FunctionTool(func, require_confirmation=bool | Callable[..., bool])` (source `tools/function_tool.py` line 104) pauses the call until a user confirms. This is ADK's own approval gate. It records that someone said yes. It does not re-check that the yes still holds when the effect fires, which is the gap Interlock covers.
- A plain Python function in `tools=[...]` is wrapped in `FunctionTool` automatically. ADK builds the schema from the type hints and the docstring. A parameter named `tool_context` is filled in by ADK and hidden from the model.

## Running an agent programmatically

Verified in `experiments/adk_smoke.py`:

```python
agent = LlmAgent(name=..., model=..., tools=[fn], instruction=...,
                 before_tool_callback=before, after_tool_callback=after)
svc = InMemorySessionService()
s = await svc.create_session(app_name="app", user_id="u")          # keyword-only
runner = Runner(agent=agent, app_name="app", session_service=svc)  # app_name required with agent=
async for ev in runner.run_async(user_id="u", session_id=s.id,
                                 new_message=types.Content(role="user", parts=[types.Part(text="...")])):
    ...  # ev.content.parts[i].function_call / .function_response / .text
```

Full signature: `Runner.run_async(*, user_id, session_id, invocation_id=None, new_message=None, state_delta=None, run_config=None, yield_user_message=False)` (source `runners.py` line 1030). You have to pass `invocation_id` or `new_message`.

## Models

- Gemini: pass the model name as a string, for example `model="gemini-2.5-flash"`. With an API key, set `GOOGLE_API_KEY` and `GOOGLE_GENAI_USE_VERTEXAI=FALSE`.
- Claude through LiteLLM: `from google.adk.models.lite_llm import LiteLlm`, then `model=LiteLlm(model="anthropic/claude-haiku-4-5-20251001")`. It reads `ANTHROPIC_API_KEY` from the environment. The source docstring also shows `vertex_ai/claude-...` for Claude on Vertex.

## Smoke test results

Script: `experiments/adk_smoke.py`. The model is told to call `refund` twice: once with 500 cents, where the before callback allows it, and once with 5000 cents, where the before callback returns a dict.

**Claude (`anthropic/claude-haiku-4-5-20251001` via LiteLlm): verified live.**

```
500 fn_response: {'status': 'refunded', 'id': 're_fake', 'receipt': 'r1'}
5000 fn_response: {'status': 'blocked', 'reason': 'over limit', 'receipt': 'r1'}
tool body calls: ['pi_123'] state: {'gate_seen': {'payment_intent': 'pi_123', 'amount_cents': 5000}}
```

The tool body ran exactly once. The blocked call never reached it. The state write persisted. The after callback ran on both calls.

**Gemini (`gemini-2.5-flash`): NOT VERIFIED LIVE.** Project `gen-lang-client-0277439345` already had a key named "Gemini API Key", restricted to `generativelanguage.googleapis.com`. I used that key and did not create a new one. It is stored only at `~/.config/interlock/gemini.env` (mode 600), and nowhere in the repo. The request authenticated, but the API returned `429 RESOURCE_EXHAUSTED: Your prepayment credits are depleted`. The code path is the same ADK flow as the Claude run. The only difference is the model string. Gemini will need billing credits added in AI Studio before it can be verified.

## Durability and resume in ADK itself

- `google.adk.apps.ResumabilityConfig(is_resumable=True)`, set on `App(resumability_config=...)` (source `apps/_configs.py` lines 29-47). It can pause a run at a long-running tool call, and it can resume a run from the last event if the run was paused or failed partway through. To resume, call `run_async(invocation_id=...)`.
- The source docstring says it plainly: *"ADK resumes the invocation in a best-effort manner: 1. Tool call to resume needs to be idempotent because we only guarantee an at-least-once behavior once resumed. 2. Any temporary / in-memory state will be lost upon resumption."*
- That is the gap Interlock fills. ADK resume promises at-least-once and leaves idempotency to the tool author. Interlock provides once-only execution plus a re-check of authority and facts at fire time, with no per-tool code.
- Durable session storage comes from session services: `InMemorySessionService`, a database-backed session service, and the Vertex Agent Engine sessions. ADK stores the event log and state. It does not guarantee that effects happen exactly once.

## ADK inside Temporal (official contrib)

`temporalio` 1.32.0 ships `temporalio.contrib.google_adk_agents`. Install it with `temporalio[google-adk]`, which pins `google-adk>=2.2.0,<3` and `mcp>=1.24,<2`. Without the extra, the import fails on `McpToolset`. Verified: the import works with 2.9.0 and exports `GoogleAdkPlugin`, `TemporalModel`, `TemporalMcpToolSet`, `TemporalMcpToolSetProvider`, `TemporalStatefulMcpToolSet`, and `TemporalStatefulMcpToolSetProvider`. `temporalio.contrib.google_adk_agents.workflow` also provides `activity_as_tool` and `ToolContextSnapshot` (both marked experimental).

From the contrib README and source:

- The agent loop runs as workflow code. `TemporalModel` turns each LLM call into an activity. `activity_as_tool(activity_fn, start_to_close_timeout=...)` turns a tool into an activity. `GoogleAdkPlugin` (a client or worker plugin) swaps in deterministic `time` and `uuid` and a Pydantic converter.
- An activity-backed tool can read `tool_context: ToolContextSnapshot`, a read-only copy of session state plus the function-call id. Changes made in the activity do not flow back to the session.
- ADK callbacks run in workflow code. They re-execute on every replay, and the README warns that ADK telemetry is re-recorded on each replay.

What this means for an Interlock integration (design notes, not yet built):

1. **Under Temporal, the fire-time check has to live inside the activity that performs the effect**, not in `before_tool_callback`. Callbacks replay and must be deterministic, so they cannot call Stripe or read a journal. Wrap the effect with Interlock inside the activity, then expose it with `activity_as_tool`. Temporal retries that activity after a worker crash. That retry is the double-refund case, and Interlock stops it.
2. **Without Temporal (plain ADK `Runner`)**, a `BasePlugin.before_tool_callback` can call the Interlock gate for every tool that performs an effect. It returns a dict (blocked, ambiguous, or a result replayed from a receipt) to skip the tool body, or None to let the tool run. The same middleware works in both setups. Only where it is attached changes.
3. Use `tool_context.function_call_id` together with `invocation_id` as the effect key. On resume the model may issue a new call id, so a key built from the business action (for example the PaymentIntent plus the approved amount) is safer for once-only execution. Record which key was used in the receipt.

## Sources

- Installed package `google-adk` 2.9.0: `agents/llm_agent.py`, `agents/context.py`, `tools/tool_context.py`, `tools/function_tool.py`, `flows/llm_flows/_tool_caller.py`, `runners.py`, `apps/_configs.py`, `sessions/in_memory_session_service.py`, `models/lite_llm.py`, and the package `METADATA` and `LICENSE`.
- Installed package `temporalio` 1.32.0: `contrib/google_adk_agents/README.md`, `workflow.py`, `_mcp.py`, `_model.py`, and `METADATA`.
- https://pypi.org/pypi/google-adk/json
- https://github.com/google/adk-python
- Run log: `experiments/adk_smoke.py` against Claude Haiku 4.5 (passed) and Gemini 2.5 Flash (429, no credits).
