# Temporal: the parity bar and the gap

Research date: 2026-09-13. All claims below come from Temporal's own docs, blog, repo, or pricing page, fetched today. Where a doc page did not state something, this file says so instead of filling it in from memory.

Versions checked (GitHub API): Temporal Server v1.32.0 (published 2026-09-11), Python SDK temporalio 1.32.0 (2026-08-24). Server license: MIT (github.com/temporalio/temporal/LICENSE). Python SDK: MIT (PyPI).

## 1. The parity bar (what the runtime must match)

| Feature | Temporal's documented behavior | Source |
|---|---|---|
| Event history | "Event History is durably persisted by the Temporal Service, so your application state survives crashes or failures." | docs.temporal.io/workflow-execution/event |
| Replay | Worker crash: "another Worker can pick up the Workflow Task and replay the entire history to reconstruct the exact state before continuing." Completed activity results are reused on replay, not recomputed. | docs.temporal.io/tasks |
| Determinism | Workflow code must make "the same Workflow API calls in the same sequence, given the same input." API calls and "LLM/AI invocations, database queries, and other external interactions" must be Activities. | docs.temporal.io/workflow-definition |
| Non-determinism failure | A NonDeterminismError (or any non-ApplicationError exception) fails only the Workflow Task, which is retried until the Workflow Execution Timeout (unlimited by default). The workflow gets stuck; it does not fail. | docs.temporal.io/develop/python/best-practices/error-handling |
| Python sandbox | Re-execs workflow modules and proxies known non-deterministic calls. It is "not completely isolated, and some libraries can internally mutate state, which can result in breaking determinism." | docs.temporal.io/develop/python/python-sdk-sandbox |
| Activity retries | Default policy: initial interval 1s, backoff 2.0, max interval 100x initial, max attempts unlimited. No non-retryable errors by default. Activities get a retry policy by default; workflows do not. | docs.temporal.io/encyclopedia/retry-policies |
| Activity timeouts | Schedule-To-Start (default infinite), Start-To-Close (defaults to Schedule-To-Close, strongly recommended), Schedule-To-Close (default infinite, caps all retries), Heartbeat. | docs.temporal.io/encyclopedia/detecting-activity-failures |
| Crash detection | "The Temporal Server doesn't detect failures when a Worker loses communication with the Server or crashes. Therefore, the Temporal Server relies on the Start-To-Close Timeout to force Activity retries." | same |
| Heartbeats | Worker throttles heartbeats (min of 0.8 x heartbeat timeout, or 30s default / 60s max) and sends only the latest. Heartbeat details let the next attempt resume progress. "Activities that don't Heartbeat can't receive a Cancellation." | same |
| Execution guarantee | "the Activity may be executed multiple times and may even partially complete more than once" but is "observed as completed exactly once." At-most-once needs maximumAttempts=1 and a normal (not local) activity. | docs.temporal.io/activity-definition; temporal.io/blog/idempotency-and-durable-execution |
| Local activities | Result durable only when the enclosing Workflow Task completes; a crash before that re-runs them. Workflow Task timeout default is 10 seconds. | docs.temporal.io/local-activity |
| Durable timers | Persisted; if Worker or Service is down when the timer fires, the await resolves once both are back. Duration is a minimum, rounded up. One second to years. Waiting costs no worker resources. | docs.temporal.io/workflow-execution/timers-delays |
| Signals | Async, fire and forget, recorded as WorkflowExecutionSignaled in history. Handlers can run concurrently (docs recommend asyncio.Lock). Signal-With-Start is atomic. | docs.temporal.io/develop/python/message-passing; docs.temporal.io/sending-messages |
| Updates | Synchronous tracked write. Optional validator; rejected updates never enter history. Max 10 in-flight, 2000 total per execution. Update-With-Start is not atomic. | docs.temporal.io/encyclopedia/workflow-message-passing; docs.temporal.io/cloud/limits |
| Queries | Read-only, "never add entries to the Workflow Event History." Work on completed workflows. | docs.temporal.io/encyclopedia/workflow-message-passing |
| Task queues | Workers long-poll with synchronous RPC and only when they have capacity. Sync match delivers without persisting; otherwise tasks persist and survive worker death. Server-side rate limiting on activity queues. | docs.temporal.io/task-queue |
| Sticky execution | Workflow Tasks routed to the worker holding cached state; if not started within 5s (default), stickiness drops and any worker can take it from the original queue. | docs.temporal.io/sticky-execution |
| Versioning | Two methods. Patching: `workflow.patched()` writes a marker; `deprecate_patch()` once old runs finish; replay tests recommended. Worker Versioning: Pinned (a run completes on one build) or Auto-Upgrade (needs patching). Requires server v1.29.1+ and blue-green or rainbow deploys; "Rolling deploys ... are incompatible." | docs.temporal.io/develop/python/versioning; docs.temporal.io/production-deployment/worker-deployments/worker-versioning |
| Continue-As-New | Same Workflow ID, new Run ID, fresh history; state passed as arguments. The SDK tells the workflow when to do it ("suggested continue-as-new"). | docs.temporal.io/workflow-execution/continue-as-new |
| Limits | History: warn 10,240 events / 10 MB, terminate at 51,200 events / 50 MB. Payload: warn 256 KB, error 2 MB. 2,000 pending activities/children/signals (500 or fewer recommended). 10,000 signals and 2,000 updates per history. | docs.temporal.io/self-hosted-guide/defaults; docs.temporal.io/cloud/limits |
| Visibility | List filters and custom search attributes over SQL (MySQL 8.0.17+, Postgres 12+) or Elasticsearch/OpenSearch. Eventually consistent: "a List or Count query can briefly return stale results." | docs.temporal.io/visibility |
| Operator tools | Workflow reset: terminate and replay history up to an event id, continuing with current code. Activity Pause, Unpause, Reset, Update Options: Public Preview, server v1.28.0+. | docs.temporal.io/cli/workflow; docs.temporal.io/activity-operations |

Minimum runtime to claim parity: journaled step results never re-run after completion; retry policy with those four knobs plus non-retryable errors; start-to-close and heartbeat timeouts as the worker-death detector; durable timers; signals recorded in history before handlers see them; queries that write nothing; leased task claims with takeover; a patch-marker equivalent that fails loudly on mismatch; a way to cut history (continue-as-new); a list/filter view. Updates with validators and sticky caching are nice to have, not core.

## 2. What Temporal tells users to do about external side effects

1. **Idempotency key.** "You can use a combination of the Workflow Run ID and the Activity ID as an idempotency key since this is guaranteed to be consistent across retry attempts but unique among Workflow Executions." The key is enforced "by the service you are calling from your Activity, not by the Activity itself." "The lack of idempotency might affect the correctness of your application but does not affect the Temporal Platform." (docs.temporal.io/activity-definition; temporal.io/blog/idempotency-and-durable-execution)
2. **Check before act.** The blog's example is to check whether the record already exists ("If it does, then you know the Activity has already successfully run"). For APIs with no idempotency support: "create an `operations` table with a uniqueness constraint." (temporal.io/blog/idempotency-and-durable-execution)
3. **Sagas.** Register the compensation before running the activity. "All compensations must be idempotent"; they "may run even when the forward Activity never executed ... or may run multiple times on retry." (docs.temporal.io/design-patterns/saga-pattern)
4. **Non-retryable errors plus manual intervention.** Mark permanent failures non-retryable, then compensate ("backward recovery"). (temporal.io/blog/failure-handling-in-practice) Operators can pause a failing activity and unpause it later. (docs.temporal.io/activity-operations)
5. **Human in the loop for agents.** A signal carries the approval into a `wait_condition` with a durable-timer timeout; the workflow then "Executes the action if ... human approved, or cancels if rejected/timed out." The cookbook does not re-check the conditions behind the approval at execution time. (docs.temporal.io/ai-cookbook/human-in-the-loop-python)
6. **LLM calls.** The OpenAI Agents SDK integration runs each model call as an Activity, "so they retry durably and are not repeated during Workflow replay." (docs.temporal.io/develop/python/integrations/openai-agents) The model output is stored as an activity result. Its inputs and the facts it relied on are not stored as premises.

### "The world changed during the outage"

No Temporal page I found documents a pattern for this. All the tools assume something else:

- The idempotency key protects against a *duplicate* of the same request. It does nothing when the request is still unique but no longer wanted (support refunded by hand, permission revoked). With Stripe, a retry outside the 24-hour key window is also a new request.
- Check-before-act, as the blog writes it, asks "did *my* operation already happen?" It does not ask "are the premises of the decision still true?" A competent engineer would add that second query (for example, list refunds on the charge before refunding). That is the fair baseline (b), and nothing in Temporal makes it durable, re-runs it at recovery, or ties it to what the LLM saw when it decided.
- Sagas compensate after the fact. That means a duplicate refund happens and then gets clawed back.
- Signals can carry revoke or cancel, but only if someone sends one. An activity that is mid-attempt only sees cancellation on its next heartbeat, and an activity that never heartbeats never sees it.
- Workflow reset reruns everything after the reset point with current code. Activity pause stops retries. Both are manual operator actions, not checks.
- Authority: Temporal has no concept of a permission lease on an effect. Namespace auth covers API callers, not whether a workflow may still issue a refund.

So the honest framing: Temporal gives at-least-once execution and durable state. Business correctness under changed external state is left to user code. Its docs say this directly: idempotency "does not affect the Temporal Platform."

## 3. Operational costs (documented)

- Four services (Frontend, History, Matching, Worker) plus a persistence store (Cassandra, MySQL, PostgreSQL, SQLite) and a visibility store. (docs.temporal.io/temporal-service)
- `numHistoryShards` "is immutable and will be ignored after the first run." Size it for peak load up front. (docs.temporal.io/references/configuration)
- Upgrades go "sequentially, one minor version at a time," with a schema upgrade first and "approximately 10 minutes on each version." "Temporal Server ensures backward compatibility only between two successive minor versions." (docs.temporal.io/self-hosted-guide/upgrade-server)
- Hosts should not be reachable from the public internet. Helm chart pins against server versions. (docs.temporal.io/self-hosted-guide/deployment)
- Worker Versioning needs blue-green or rainbow deploys. Rolling deploys are incompatible. (worker-versioning page)
- History caps force continue-as-new for long agent loops (51,200 events / 50 MB). A chatty agent with many tool calls reaches that sooner than a typical business workflow.
- Payload caps (2 MB) push LLM transcripts and large tool outputs into external storage.
- A deploy that breaks determinism leaves workflows stuck retrying Workflow Tasks rather than failing, until someone patches or resets.
- Temporal Cloud: Essentials from $100/mo (1M actions), Business from $500/mo (2.5M actions); extra actions from $50 per million down to $25; active storage $0.042 per GB-hour, retained $0.00105 per GB-hour. (temporal.io/pricing)

## 4. Implications for the Interlock runtime

Parity items to test head-to-head (same scenario, real SIGKILL):
1. A completed step is never re-run after a worker kill (Temporal: yes).
2. Retry backoff timing matches the policy.
3. A 1-hour timer fires correctly after both the worker and the store restart.
4. A signal sent while no worker is up is still delivered.
5. Two workers race for a task; one is killed while holding the lease; the other takes over after the timeout; the effect happens once.
6. A code change without a patch marker is detected on replay.

Where Interlock can honestly be better (Temporal documents no mechanism):
- Premises re-checked at send and at recovery (hand refund during an outage).
- Authority lease re-checked at dispatch and recovery (permission revoked mid-flight).
- A payload bound at approval (a re-decided $30 is refused, not sent under a new activity attempt).
- Tier-aware recovery that returns AMBIGUOUS for tier-3 targets instead of retrying forever by default.
- Verifiable hash-chained receipts (Temporal history is durable but not tamper-evident to a third party).
- An LLM decision stored with its premises, not just its output.

Where Temporal will likely stay better, and we should say so: multi-language SDKs, scale (sharded history, sync match), UI and visibility tooling, operator tools (reset, activity pause), Update with validators, sticky caching, maturity and years of production use.

Where it may be equal: baseline (b) with a pre-send check and a correct idempotency key covers the hand-refund case on the happy path. The difference shows up at recovery after a crash in the ambiguous window, and when authority changes. The experiments should show exactly where (b) stops holding, not assume it.
