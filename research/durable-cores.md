# Durable execution cores: what to build the Interlock runtime on

Checked on 2026-09-13. Licenses come from each repo's LICENSE file (`gh api repos/<r>/license`). Versions and push dates come from GitHub releases and PyPI JSON. Behavior claims come from each project's source, read in shallow clones, unless a doc page is named. "Postgres only" means the whole stack runs on a stock Postgres with nothing else, which is the runtime's hard constraint.

## Summary table

| core | license (server / SDK) | latest | last push | Python | Postgres only? | fit |
|---|---|---|---|---|---|---|
| Absurd | Apache-2.0 / Apache-2.0 | 0.5.0 (2026-08-04), SDK "Alpha" | 2026-08-10 | `absurd-sdk` 0.5.0, py>=3.9, classifiers list 3.14 | yes, one `absurd.sql` | **best base** |
| DBOS Transact | MIT / MIT | py 2.31.1 (2026-09-08), ts v4.27 | 2026-09-11 | first class, py>=3.10 | yes (or SQLite) | strong SDK, takeover needs proprietary Conductor |
| Hatchet | MIT | v0.106.5 (2026-09-08), `hatchet-sdk` 1.40.1 | 2026-09-12 | first class | yes with `SERVER_MSGQUEUE_KIND=postgres`, but a Go engine + API server | heavy to embed |
| Procrastinate | MIT | 3.9.0 (2026-06-20) | 2026-09-12 | native, py>=3.10, PG 13+ | yes | job queue, no steps |
| River | MPL-2.0 | v0.47.0 (2026-08-31) | 2026-09-10 | insert-only client (`riverqueue` 0.7.0) | yes | Go workers only; workflows are River Pro (paid) |
| pgmq | PostgreSQL License | v1.13.0 (2026-09-07) | 2026-09-10 | `pgmq` 1.1.3 | yes (extension) | queue primitive only |
| Restate | **BSL 1.1** server / MIT Python SDK | v1.7.9 (2026-09-04), `restate-sdk` 1.0.5 | 2026-09-11 | yes | **no**: RocksDB + own log | license and infra both disqualify |
| Inngest | **SSPL 1.0** server, Apache-2.0 after 3 years / Apache-2.0 SDK | v1.44.0 (2026-08-26), `inngest` 0.5.19 | 2026-09-13 | yes | **no**: needs Redis (in-process by default) + SQLite/Postgres | license and infra both disqualify |
| Temporal server | MIT | v1.32.0 (2026-09-11), `temporalio` 1.32.0 | 2026-09-13 | yes | Postgres works for persistence and visibility, but it is a multi-service Go server | the baseline to beat, not a base |

Flags: Restate's server is Business Source License 1.1 with an additional use grant that forbids offering a "Public Restate Platform Service". Inngest's server is SSPL with a grant of Apache-2.0 "effective on the third anniversary of the date we make the Software available". Both are source-available, not open source, for our purposes. DBOS Conductor is proprietary ("Self-hosted Conductor is released under a proprietary license and requires a license key", docs.dbos.dev/production/hosting-conductor); the DBOS library itself is MIT.

## Per core

### Absurd (earendil-works/absurd, Armin Ronacher)

- **Shape.** The engine is one 3,150-line PL/pgSQL file, `sql/absurd.sql`. SDKs call stored procedures: `spawn_task`, `claim_task`, `set_task_checkpoint_state`, `get_task_checkpoint_state(s)`, `extend_claim`, `complete_run`, `fail_run`, `schedule_run`, `retry_task`, `await_event`, `emit_event`, `cancel_task`, `get_task_result`, plus cleanup, weekly partitions and `enable_cron`. The Python SDK is a single 2,317-line `absurd_sdk/__init__.py` whose only dependency is `psycopg[binary]>=3`.
- **Tasks, runs, steps.** A task has runs (attempts). `ctx.step(name, fn)` looks up checkpoint `name` and returns the cached value if present; otherwise it runs `fn` and calls `set_task_checkpoint_state`. Repeated names become `name#2`, `name#3` (`_get_checkpoint_name`). There is no deterministic replay: the task function re-runs from the top and steps short-circuit on cached checkpoints. A step that ran but crashed before its checkpoint write runs again, so a step is at least once.
- **Retries.** A failed run makes a new run with backoff. Strategies are `fixed`, `exponential`, `none`. 0.5.0 caps automatic retry delay at one day.
- **Claims and takeover.** `claim_task(queue, worker_id, claim_timeout, qty)` selects candidates `for update skip locked`, sets `claimed_by` and `claim_expires_at`. At the start of each claim call it sweeps expired runs and fails them with `$ClaimTimeout`, which schedules a new run with a higher attempt. `extend_claim` and `ctx.heartbeat` renew.
- **Fencing (important for us).** `set_task_checkpoint_state` takes the owning `run_id`, raises `AB002` if that run already failed, raises `AB001` if the task was cancelled, and only overwrites an existing checkpoint when the writer's attempt is `>=` the owner's attempt. So a zombie worker whose claim expired cannot commit a checkpoint over its successor.
- **Timers.** `sleep_for` / `sleep_until` schedule the run for later and suspend; since 0.5.0 wake-ups use the database clock (`absurd.current_time()`), not the worker clock.
- **Signals.** `await_event(name)` / `emit_event(name, payload)`. Events are first-write-wins and immutable ("Events are immutable once emitted: first write wins", `on conflict (event_name)`). `cancel_task` is the cancel path. Approve then revoke needs two event names or a cancel, since one name cannot be emitted twice.
- **Versioning.** Nothing built in. docs/patterns/living-with-code-changes.md: "There is no magic fix for this", version step names (`fetch-user:v2`) or translate old checkpoint data forward.
- **Embedding the gate.** Easy, because the durable state is plain tables in the same Postgres. Move the Interlock journal into a table in that database. A gated effect becomes a special step: write `DISPATCHED` (with effect id, payload hash, premises, lease) in its own committed transaction, re-check premises and lease, call the target, then write `COMMITTED` and the Absurd checkpoint in one transaction. On a new run (after a SIGKILL or claim expiry) the effect step finds `DISPATCHED` without a checkpoint and calls the gate's tier-aware recovery instead of re-running `fn`. The attempt fencing above is what makes "safe takeover" hold for effect steps too, provided the gate's `COMMITTED` write checks the same run ownership.
- **Risks.** Pre-1.0 and marked Alpha; schema migrations between versions (`sql/migrations`). No workflow versioning. No deterministic replay, so code between steps runs again on every resume. Sync SDK uses one connection per task context.

### DBOS Transact (dbos-inc/dbos-transact-py, -ts)

- **Shape.** Library, MIT. System tables in Postgres (or SQLite): `workflow_status`, `operation_outputs` (primary key `(workflow_uuid, function_id)`), notifications, events, streams, schedules. Built on SQLAlchemy.
- **Steps.** `@DBOS.workflow()` / `@DBOS.step()`. Workflows must be deterministic; step outputs are recorded by `function_id` order. Docs: "steps get at-least-once guarantees and workflow outcomes are persisted exactly-once". Step retries: `max_attempts`, `interval_seconds`, `backoff_rate`.
- **Timers.** `DBOS.sleep()` stores the wake-up time.
- **Signals.** `DBOS.send` / `DBOS.recv(topic, timeout)`, `DBOS.set_event` / `DBOS.get_event`. Also `cancel_workflow`, `resume_workflow`, `fork_workflow` (restart from a given step).
- **Versioning.** Two mechanisms. `application_version` on every workflow row; recovery only picks up rows matching the executor's version (`get_pending_workflows(executor_id, app_version)`). And `DBOS.patch(name)` (needs `enable_patching`), which records a marker at the next `function_id`, the same idea as Temporal's `workflow.patched`.
- **Workers and takeover.** Workflow ids are idempotency keys. Concurrent execution of one workflow is detected when a step output or the final outcome is written (`DBOSWorkflowConflictIDError`, "Do not ignore that error"). There is no lease or heartbeat on a running workflow. Recovery is keyed on `executor_id`: an executor recovers its own pending workflows at startup, and recovering a dead executor's workflows needs either the admin endpoint called with that executor's id or Conductor, which is proprietary and needs a paid license for production. A self-hosted Postgres-only deployment therefore has no automatic safe takeover.
- **Embedding the gate.** A gated effect is a `@DBOS.step` whose body is the gate; the gate journal can share DBOS's database. The weak point is that a crashed step is re-run blindly as "at least once", so the gate's recovery must run inside the step body on every attempt, which it already does via `interlock/temporal.py`-style wrapping. We would still have to add leases and takeover ourselves.
- **Risks.** Large SDK surface; takeover story depends on a closed component.

### Hatchet (hatchet-dev/hatchet)

- **Shape.** Go engine, API server, migrate and admin containers (docker-compose.release.yml), gRPC to SDK workers. RabbitMQ is the default broker; docs/self-hosting: "This is optional: if you'd like to use Postgres as a message broker ... `SERVER_MSGQUEUE_KIND=postgres`".
- **Durable tasks.** `DurableContext.aio_sleep_for`, `aio_wait_for(signal_key, *conditions)` with sleep, user-event and OR conditions, `aio_wait_for_event`, and child spawns. Each wait or spawn writes a checkpoint to a durable event log; tasks can be evicted while waiting and replayed. Docs require "the code between checkpoints must be deterministic". Regular (non-durable) tasks retry with configured attempts. No workflow code versioning mechanism found in the durable-task docs.
- **Embedding the gate.** Only in the SDK task body. The engine's state lives behind its API, so tier-aware recovery and premise checks cannot sit next to the step journal in one transaction.
- **Risks.** Running a separate engine is the operational weight we are trying to remove from Temporal.

### Procrastinate (procrastinate-org/procrastinate)

- Python job queue on Postgres 13+, MIT, sync and async, Django integration. Retry strategies, `schedule_at`, periodic tasks, `lock` and `queueing_lock`. Workers send heartbeats; `JobManager.get_stalled_jobs(seconds_since_heartbeat=30)` finds jobs of dead workers so they can be retried.
- No steps, no durable waits or signals, no versioning. We would build the whole durable layer on top. Useful as a reference for heartbeats and LISTEN/NOTIFY wake-ups, not as the core.

### River (riverqueue/river)

- Go job queue, MPL-2.0. The core now has `ResumableStep` / `ResumableStepCursor`, which skip steps completed by an earlier attempt, and `RecordOutput`. The Python client is "insert-only ... doesn't support working jobs in Python". Workflows (DAGs, durable signals, timer waits) are documented under River Pro, a paid product. Not usable for a Python runtime.

### pgmq (pgmq/pgmq)

- Postgres extension, PostgreSQL License. SQS-style API: `send`, `send_batch`, `read`, `read_with_poll`, `pop`, `set_vt` (visibility timeout), `archive`, `delete`, FIFO grouped reads, `metrics`. A message becomes visible again when its visibility timeout lapses, but there is no owner token to fence a slow consumer. Absurd's own comparison: "PGMQ intentionally stops at the queue layer." Too low level; everything above the queue would be ours.

### Restate (restatedev/restate)

- Journal per invocation: `ctx.run` for side effects, `ctx.sleep`, awakeables (`ctx.awakeable`, `resolve_awakeable`) and workflow signals (`ctx.signal`, `resolve_signal`), virtual objects with keyed state, `ctx.random`/`ctx.uuid`/`ctx.time` recorded.
- Versioning is the best design in this list: deployments are immutable; "New invocations are always routed to the latest service revision, while old invocations will continue to use the previous deployment ... until completion" (docs/operate/versioning.mdx). A deployment can be removed only once drained.
- Disqualified: server is BSL 1.1 and stores state in RocksDB under `./restate-data` (Postgres port 9071 is read-only introspection), not Postgres.
- Borrow: pin in-flight workflows to the code version that started them.

### Inngest (inngest/inngest)

- Each step is a separate HTTP request to the app; `step.run` memoizes, `step.sleep`, `step.sleep_until`, `step.wait_for_event`, `step.invoke`, `step.send_event`, `parallel` (Python SDK `step_lib`). Per-step retries.
- Disqualified: SSPL server (Apache-2.0 only three years after each release), and self-hosting uses Redis for queue and state (in-process by default, external recommended for production) plus SQLite or Postgres.

### Temporal server (temporalio/temporal)

- MIT, v1.32.0. Event-sourced deterministic replay; activities with retry policies; durable timers; signals, queries, updates; task queues with sticky workers. Persistence and visibility can both be PostgreSQL 12+ (docs/self-hosted-guide/visibility), though Elasticsearch/OpenSearch is "recommended for any setup that spawns more than a few Workflow Executions".
- Versioning: `workflow.patched` / `workflow.deprecate_patch` (markers in history), and Worker Versioning with Worker Deployments (pinned vs auto-upgrade), which the current docs say "should be the default recommendation" for production.
- It is what we measure against, not something to embed: the gate can only live in an activity body, which is exactly the "Temporal + pre-send check" baseline.

## Recommendation

Build the runtime on **Absurd's design, vendoring `absurd.sql` pinned at 0.5.0** (Apache-2.0, keep the license header and a NOTICE line), with our own small Python worker and the Interlock journal as tables in the same database.

Why Absurd over DBOS: it is the only candidate that already has leased claims with expiry, automatic takeover on claim expiry, and attempt-based fencing of checkpoint writes, all inside Postgres with no other service and no closed component. DBOS has better Python ergonomics and a real `patch()`, but automatic takeover of a dead executor's work needs proprietary Conductor, and it has no lease to check at dispatch. Absurd's step model (cached checkpoints, no deterministic replay) also matches an agent loop better: LLM calls are non-deterministic anyway, so recording them as steps with premises is natural, while Temporal-style replay forces them into activities.

What we add on top (none of it exists in Absurd):

1. **Gated effect step.** `DISPATCHED` committed before the call; `COMMITTED` and the checkpoint in one transaction that also checks the run still owns the claim (reuse the `AB002` / attempt rule). On a new run, a `DISPATCHED` without checkpoint goes to tier-aware recovery, never to `fn`.
2. **Decision step.** An LLM call recorded as a checkpoint carrying model, prompt hash, output and premises.
3. **Versioning.** Record a code version at spawn; `patched(name)` returns whether the task started at or after that version (DBOS/Temporal marker idea), plus Restate-style pinning: workers only claim tasks whose version they can run. This is new code, roughly the size of a claim filter plus one helper.
4. **Revocable signals.** Absurd events are first-write-wins, so approve/revoke uses distinct event names per decision or `cancel_task`; lease revocation is checked by the gate at send, not delivered as an event.
5. **Receipts.** Existing hash-chained receipts, written from the journal table.

Fallback: if vendoring hits a wall (for example the gate needs the claim check inside its own transaction and Absurd's function boundaries make that awkward), write our own schema of about the same shape. The parts worth copying are small: `for update skip locked` claims with `claim_expires_at`, expired-claim sweep that bumps the attempt, owner-run and attempt checks on every checkpoint write, database clock for timers.

First check before committing to it: a live test with real SIGKILLs. Two worker processes, kill the one holding a claim mid-step, confirm the second takes over only after expiry and that a resumed zombie's checkpoint write is refused with `AB002`.

## Sources

- https://github.com/earendil-works/absurd (LICENSE, sql/absurd.sql, sdks/python, CHANGELOG.md, docs/comparison.md, docs/patterns/living-with-code-changes.md)
- https://github.com/dbos-inc/dbos-transact-py (LICENSE, dbos/_dbos.py, dbos/_sys_db.py, dbos/_recovery.py, dbos/_schemas/system_database.py)
- https://docs.dbos.dev/python/tutorials/workflow-tutorial
- https://docs.dbos.dev/explanations/concurrent-executions
- https://docs.dbos.dev/production/workflow-recovery
- https://docs.dbos.dev/production/hosting-conductor
- https://github.com/hatchet-dev/hatchet (LICENSE, sdks/python/hatchet_sdk/context/context.py, frontend/docs/content/docs/v1/durable-tasks.mdx, self-hosting/docker-compose.mdx, configuration-options.mdx)
- https://github.com/procrastinate-org/procrastinate (procrastinate/manager.py, docs/howto/production/retry_stalled_jobs.md)
- https://procrastinate.readthedocs.io/en/stable/
- https://github.com/riverqueue/river (LICENSE, resumable.go, recorded_output.go, CHANGELOG.md)
- https://github.com/riverqueue/riverqueue-python (README.md)
- https://riverqueue.com/docs/pro/workflows
- https://github.com/pgmq/pgmq (LICENSE, pgmq-extension/sql/pgmq.sql)
- https://github.com/restatedev/restate (LICENSE)
- https://github.com/restatedev/sdk-python (python/restate/context.py)
- https://github.com/restatedev/documentation (docs/operate/versioning.mdx, docs/deploy/deploy.mdx)
- https://github.com/inngest/inngest (LICENSE)
- https://github.com/inngest/inngest-py (step_lib)
- https://www.inngest.com/docs/learn/how-functions-are-executed
- https://www.inngest.com/docs/self-hosting
- https://github.com/temporalio/temporal (LICENSE, releases)
- https://docs.temporal.io/develop/python/versioning
- https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning
- https://docs.temporal.io/self-hosted-guide/visibility
- PyPI JSON for absurd-sdk, dbos, hatchet-sdk, procrastinate, restate-sdk, inngest, riverqueue, pgmq, temporalio
