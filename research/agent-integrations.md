# Agent-framework entry points for the Interlock runtime

Verified 2026-09-13 against primary sources: GitHub repo metadata (`gh api`), PyPI JSON, raw source files and official docs. Versions and licenses below were read today, not recalled.

## Summary table

| Component | Latest (date) | License | Entry point we hook | Minimal adapter |
|---|---|---|---|---|
| MCP Python SDK (`mcp`) | 2.2.0 (2026-09-07), spec 2026-07-28 | MIT | `Client.call_tool(...)` on the client side, or a stdio proxy on the wire | Wrap `call_tool` as a gated effect; extend existing `interlock/mcp_proxy.py` |
| LangGraph (`langgraph`) | 1.2.11 (2026-08-11) | MIT (repo and `libs/checkpoint-postgres/LICENSE`) | `BaseCheckpointSaver` (checkpointer), `interrupt()` / `Command(resume=)` | A Postgres checkpointer on our tables plus a gated-effect helper for use inside nodes/tasks |
| OpenAI Agents SDK (`openai-agents`) | 0.22.2 (2026-09-09) | MIT | `Model` calls, `@function_tool` / `needs_approval`, `RunState` JSON, `TracingProcessor` | Tool wrapper that gates the effect; store `RunState.to_json()` in our journal |
| Anthropic SDK (`anthropic`) | 1.5.0 (2026-09-10) | MIT | Raw `messages.create` loop, or `BaseToolRunner.generate_tool_call_response` / `append_messages` | Our own loop: each `messages.create` is a recorded decision, each `tool_use` block is a gated effect |
| Pydantic AI (`pydantic-ai-slim`) | 2.43.0 (2026-09-12) | MIT | Durable execution backend builder: `CallableOperationBackend.execute(...)` | One backend class routing model requests and tool calls into our runtime |
| OTel GenAI semconv | `open-telemetry/semantic-conventions-genai` (split out of core semconv, core at v1.44.0) | Apache-2.0 | `execute_tool {gen_ai.tool.name}` spans, `chat`, `invoke_agent`, `invoke_workflow` | Emit spans from journal transitions; receipts stay the source of truth |

All six are permissive. Nothing here forces copyleft on the runtime.

## 1. MCP Python SDK

Sources: https://github.com/modelcontextprotocol/python-sdk (MIT, v2.2.0), `src/mcp/client/client.py`, https://modelcontextprotocol.io/specification/2026-07-28/changelog, https://modelcontextprotocol.io/specification/2026-07-28/server/tools, `schema/2026-07-28/schema.ts`, https://modelcontextprotocol.io/extensions/tasks/overview

Current client API (v2, read from source):

```python
async def call_tool(self, name: str, arguments: dict[str, Any] | None = None,
    read_timeout_seconds: float | None = None, progress_callback: ProgressFnT | None = None, *,
    input_responses: InputResponses | None = None, request_state: str | None = None,
    meta: RequestParamsMeta | None = None) -> CallToolResult
```

Usage: `async with Client("http://localhost:8000/mcp") as client: await client.call_tool("add", {...})`. Server side is still `@mcp.tool()`.

Spec facts that matter to us (2026-07-28):
- MCP is now stateless: no `initialize` handshake, no `Mcp-Session-Id`. Protocol version and client capabilities travel in every request's `_meta`. Cross-call state uses server-minted handles passed as ordinary arguments. This makes a proxy simpler: every `tools/call` is self-contained.
- SSE resumability was removed: "A broken response stream loses the in-flight request; clients MUST re-issue it as a new request with a new request ID." So a lost ack is a real, spec-sanctioned case, and the JSON-RPC id is not a dedup key. The protocol has no idempotency key for `tools/call`. Our effect id must travel as a tool argument (what `mcp_proxy.py` already does via `idempotency_argument`) or not at all.
- `ToolAnnotations` still has `readOnlyHint`, `destructiveHint` (default true), `idempotentHint` (default false), `openWorldHint`. The schema says "Clients should never make tool use decisions based on `ToolAnnotations` received from untrusted servers." Use hints only as a default tier guess from a trusted server; config overrides.
- Multi Round-Trip Requests: a `tools/call` may return `resultType: "input_required"` with `inputRequests` and `requestState`; the client retries with `inputResponses` and a new JSON-RPC id. For the gate, that retry is the same effect, not a new one: key on the effect id, not the request id.
- Tasks moved to the extension `io.modelcontextprotocol/tasks`: server returns `resultType: "task"` with `taskId`, `ttlMs`, `pollIntervalMs`; client polls `tasks/get`, answers via `tasks/update`, cancels via `tasks/cancel` (cooperative). The doc says to "Store task IDs durably so polling can resume after a client crash." A tasks-capable server is effectively tier 2 once the `taskId` is journaled, but only after the response arrives; a crash between send and `CreateTaskResult` is still the ambiguous window.
- `_meta` carries W3C `traceparent` / `tracestate` / `baggage` (SEP-414), so OTel context propagates through the proxy for free.

Minimal adapter: keep `interlock/mcp_proxy.py` (stdio, standard library) as the zero-code path and port it onto the runtime's Postgres journal. For in-process agents, a 30-line wrapper `gated_call_tool(client, name, args, spec)` that journals DISPATCHED, calls `client.call_tool(..., meta={"io.interlock/effect_id": eid})`, and records the result. Put the effect id in `arguments` too, because `_meta` is not something target servers dedupe on.

Risk: v2 is "a major rework"; v1.x remains on a branch. Pin `mcp>=2.2,<3`. Stateful MCP servers (handles) break on takeover by a different worker unless the handle is journaled as a premise.

## 2. LangGraph

Sources: https://github.com/langchain-ai/langgraph (MIT), `libs/checkpoint/langgraph/checkpoint/base/__init__.py`, https://docs.langchain.com/oss/python/langgraph/checkpointers, /interrupts, /functional-api. `langgraph-checkpoint-postgres` 3.1.2, license expression MIT.

Checkpointer interface (from source). All base methods are required; missing ones raise `NotImplementedError`:

```python
get_tuple(config) -> CheckpointTuple | None
list(config, *, filter=None, before=None, limit=None) -> Iterator[CheckpointTuple]
put(config, checkpoint, metadata, new_versions) -> RunnableConfig
put_writes(config, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None
delete_thread(thread_id) -> None
# also delete_for_runs, copy_thread, prune(thread_ids, *, strategy="keep_latest"), get_next_version
# async: aget_tuple, alist, aput, aput_writes, adelete_thread
```

`CheckpointTuple` = `config, checkpoint, metadata, parent_config, pending_writes`. Pending writes from nodes that finished in a failed super-step are kept so "you don't re-run the successful nodes." Durability modes: `"exit"`, `"async"`, `"sync"`.

Interrupt semantics, quoted: "the runtime restarts the entire node from the beginning. It does not resume from the exact line where interrupt was called. This means any code that ran before the interrupt will execute again." Multiple interrupts in a node are matched by index order. Functional API: "A task that started but did not finish may run again on that resume, so design side effects to be idempotent," and "Use idempotency keys or verify existing results."

That last sentence is the exact gap Interlock fills: LangGraph hands the ambiguous window to the user. Its guarantee is step-level (task results are not re-run once written), same class as Temporal activities.

Minimal adapter, two pieces:
1. `InterlockCheckpointer(BaseCheckpointSaver)` on our Postgres schema, so a LangGraph graph uses the runtime as its store. Alternative with less code: use `PostgresSaver` unchanged against the same database and only add piece 2. Recommend the alternative first.
2. `gate.effect(...)` called inside a `@task` or node. Effect id derived from `thread_id` + task path + approved key, not from the LLM output, so node re-execution after `interrupt()` hits the same journaled effect and is refused or deduped instead of re-sent. Approve/revoke arrive as `Command(resume=...)`, which we map to runtime signals.

Risk: checkpoint schema is internal to the postgres package and changes across majors (checkpoint lib is at 4.x). Owning a checkpointer means tracking that. Resume-by-index makes approval routing fragile if a node branches around interrupts.

## 3. OpenAI Agents SDK

Sources: https://github.com/openai/openai-agents-python (MIT, v0.22.2), docs pages `human_in_the_loop`, `running_agents`, `guardrails`, `tracing`, `ref/lifecycle`; https://github.com/temporalio/sdk-python/tree/main/temporalio/contrib/openai_agents

Surfaces:
- Approval: `@function_tool(needs_approval=True | async callable)`. Paused run exposes `result.interruptions` (`ToolApprovalItem`). `state = result.to_state()`, `state.approve(item, always_approve=...)` / `state.reject(item, rejection_message=...)`, resume `Runner.run(agent, state)`. Persist with `state.to_json()` / `RunState.from_json(...)` or `to_string` / `from_string`.
- Tool guardrails: `@tool_input_guardrail` returns `ToolGuardrailFunctionOutput.allow()`, `.reject_content(msg)`, `.raise_exception()`. They apply only to function tools and local MCP servers; hosted tools (`HostedMCPTool`, `WebSearchTool`, ...) and built-in execution tools (`ComputerTool`, `ShellTool`, ...) bypass them.
- Hooks: `RunHooks` / `AgentHooks` with `on_llm_start`, `on_llm_end`, `on_tool_start`, `on_tool_end`, `on_handoff`, `on_agent_start`, `on_agent_end`. Docs do not describe hooks vetoing a call; treat them as observe-only.
- Tracing: `TracingProcessor` (`on_trace_start/end`, `on_span_start/end`, `shutdown`, `force_flush`), `add_trace_processor()`, spans `generation_span`, `function_span`, `agent_span`.
- Durable integrations listed in the docs: Temporal, Restate, DBOS, Dapr. The Temporal plugin (`OpenAIAgentsPlugin`) runs model calls as activities and offers `activity_as_tool()`; plain `@function_tool` runs in the workflow and must be deterministic; stateful MCP servers raise `ApplicationError` on failure and leave handling to the app.

Minimal adapter: wrap the side-effecting function inside `@function_tool` with a gate call (effect id from the approved `ToolApprovalItem` call id plus key), and journal `RunState.to_json()` at each pause. Record each model call as a decision via `on_llm_end` (observe) or, for real replay, a custom `Model` implementation that returns the journaled response on recovery. The custom `Model` is the piece that makes "LLM call recorded, not re-run" true; hooks alone only observe.

Risk: pre-1.0 (0.22.x); API churn is likely. Guardrails and approvals do not cover hosted tools, so effects through hosted tools cannot be gated client-side.

## 4. Anthropic SDK tool-use loop

Sources: https://github.com/anthropics/anthropic-sdk-python (MIT, v1.5.0), `tools.md`, `src/anthropic/lib/tools/_beta_runner.py`

- `@beta_tool` / `@beta_async_tool` build tools from functions; `client.beta.messages.tool_runner(model=..., tools=[...], messages=[...], max_iterations=...)` returns a `BetaToolRunner` iterator. Iteration follows `stop_reason`: on `tool_use` it runs tools and sends results; on `pause_turn` or `compaction` it resends unchanged; otherwise stops.
- From source, the runner exposes `set_messages_params`, `append_messages` (invalidates the cached tool response, so tools run again next iteration), `generate_tool_call_response` (cached), `until_done`. `_generate_tool_call_response` calls `tool.call(tool_use.input)` directly with no approval hook; exceptions become `is_error` tool results.

Implication: the runner has no pre-execution veto. Gating must live inside the tool function, or we skip the runner. Note the `append_messages` behavior: tools run again after it, so a gate inside the tool function is required, not optional, if the runner is used.

Minimal adapter: our own ~40-line loop over `client.messages.create`. Journal each response (model id, request hash, response content, `tool_use` ids) as a decision with its premises before acting on it. For each `tool_use` block, effect id = workflow id + approved key (not `tool_use.id`, which changes when the model is re-asked). On recovery, replay the journaled response instead of calling the model again. This is what `interlock/easy.py` style decorators already support at the effect level.

Risk: `tool_runner` is under `beta`; the raw Messages API is stable. Prefer the raw loop.

## 5. Pydantic AI durable execution

Sources: https://github.com/pydantic/pydantic-ai (MIT, v2.43.0), https://pydantic.dev/docs/ai/integrations/durable_execution/overview/, `.../temporal/`, https://pydantic.dev/docs/ai/capabilities/durable_execution/backends/, `.../tools-toolsets/deferred-tools/`

- Official engines (docs): Temporal, DBOS, Prefect, Restate, AWS Lambda durable functions. Third-party: Kitaru, Apache Airflow. PyPI extras present: `temporal`, `dbos`, `prefect`.
- Temporal: `TemporalDurability` capability (the older `TemporalAgent` wrapper is deprecated), `PydanticAIPlugin()`. Model requests, tool calls, MCP communication and tool argument validation run as activities. Requirements: agents need explicit `name`, toolsets need `id`, defined at module top level. Limits: 2 MB activity payload default, no `run_sync` in workflows, streaming buffered.
- Generic builder (the useful part for us): subclass `CallableOperationBackend` and implement

```python
async def execute(self, *, operation_id: DurableOperationId, name: str,
                  body: Callable[[], Awaitable[object]], cache_key: tuple[object, ...], config) -> object
```

  or `RegisteredOperationBackend` (`register`, `registrations`) for engines that register handlers before the worker starts. Operation ids include `ModelRequestId`, `ModelCompactMessagesId`, `EventStreamHandlerId`, `ToolsetGetToolsId`, `ToolsetValidateToolArgumentsId`, `ToolsetCallToolId`, `CapabilityOperationId`. Attach with `Agent(model, name=..., capabilities=[YourDurability()])`, where the capability subclasses `BaseDurabilityCapability` and provides `in_durable_context` and `get_durable_operation_backend()`. Docs warn `DurableOperationId` "grows in minor releases," so match with a default branch.
- Approval: `requires_approval=True` or raise `ApprovalRequired`; run ends with `DeferredToolRequests`; resume with `DeferredToolResults` (`ToolApproved(override_args=...)`, `ToolDenied`) plus `message_history`. `CallDeferred` for externally executed tools.

Minimal adapter: this is the cleanest entry point of the five. One `InterlockDurability` capability whose `execute` does:
- `ModelRequestId`: journal-or-replay by `cache_key` (the LLM decision record, with premises).
- `ToolsetCallToolId`: route through the gate (premises and lease re-checked at send and recovery, tier-aware recovery).
- anything else: journal-or-replay as a plain step.

`override_args` on `ToolApproved` is a payload change after approval; the gate must bind the effect id to the approved args and refuse a mismatch (same rule as the $30 row).

Absurd note: the docs link an Absurd backend at `pydantic-ai-harness/.../absurd`, but that path does not exist in the harness tree today (checked). Absurd itself (`earendil-works/absurd`, Apache-2.0, "An experiment in durability", Postgres-native) is a relevant prior art for a Postgres-only engine and is worth a look by the engine research track.

Risk: the builder is new; minor releases add operation kinds. JSON-serializable results only through the journal.

## 6. OpenTelemetry GenAI semantic conventions

Sources: https://github.com/open-telemetry/semantic-conventions-genai (Apache-2.0) `docs/gen-ai/gen-ai-spans.md`; https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/ (attributes marked "Moved to the OpenTelemetry GenAI semantic conventions repository"); https://github.com/open-telemetry/opentelemetry-python-genai `util/opentelemetry-util-genai/README.rst`

- GenAI conventions moved out of core semconv into their own repo. Document status: Development. Every attribute and operation below is Development, so names can change.
- `gen_ai.operation.name` values: `chat`, `create_agent`, `embeddings`, `execute_tool`, `generate_content`, `invoke_agent`, `invoke_workflow`, `retrieval`, `text_completion`.
- Execute tool span: name SHOULD be `execute_tool {gen_ai.tool.name}`. `gen_ai.tool.name` Required; `gen_ai.tool.call.id`, `gen_ai.tool.description`, `gen_ai.tool.type` Recommended; `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` Opt-In.
- Content (`gen_ai.system_instructions`, `gen_ai.input.messages`, `gen_ai.output.messages`) SHOULD NOT be captured by default. Python util env var: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` = `NO_CONTENT` (default) | `SPAN_ONLY` | `EVENT_ONLY` | `SPAN_AND_EVENT`; external upload hook via `OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK`.
- There is no convention for authorization, premises, dispatch state or ambiguity. Those are ours; use a vendor namespace (for example `interlock.effect.id`, `interlock.effect.state`, `interlock.premise.stale`, `interlock.receipt.hash`) on the same spans.

Minimal adapter: an exporter that reads journal transitions and emits `invoke_workflow` > `chat` / `execute_tool` spans, with our attributes added. Keep it one-way (journal to telemetry). Telemetry is lossy and sampled; receipts are not, so spans must never be the record. Only dependency is `opentelemetry-api` (1.44.0) and it stays optional.

## Recommendation

Build order, smallest surface first:
1. Anthropic raw loop (own code, no framework dependency): proves "LLM call is a recorded decision, effect is gated" end to end.
2. MCP: port the existing stdio proxy to the Postgres journal; add an in-process `call_tool` wrapper for `mcp` 2.x. Effect id goes in arguments, since MCP has no idempotency key and the spec now requires re-issuing lost requests with a new id.
3. Pydantic AI `CallableOperationBackend`: one class gives full coverage of model requests and tool calls with a documented, public extension point, which is the strongest evidence that the runtime replaces Temporal for a real framework.
4. LangGraph: gate helper inside `@task` with `PostgresSaver` on the same database; own checkpointer only if needed.
5. OpenAI Agents SDK: tool wrapper plus `RunState` journaling; custom `Model` only if replay is needed. Lowest priority because it is pre-1.0 and hosted tools cannot be gated client-side.
6. OTel export last and optional.

Adapter rule across all of them: the effect id comes from the workflow id and the approved request key, never from framework call ids (`tool_use.id`, JSON-RPC id, LangGraph re-executed node), because every one of these frameworks re-runs or re-issues the call on resume.
