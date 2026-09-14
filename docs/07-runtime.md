# 07. interlock_runtime: the build spec

Status: final build spec, 2026-09-13. It merges the judged winner (the journal-native Postgres runtime), the grafts the judges required, and the fixes they found against this repo. Two builders work from it in parallel without talking: the runtime builder (sections 3 to 9) and the TLA+ modeler (section 10). The Prove harness (section 11) is built third, against the contracts in section 2. Where this document and an earlier design disagree, this document wins.

The decision to build this is settled. What stays open is the measured answer to one question: where is this runtime better than, equal to, and worse than (a) Temporal with its recommended idempotency key and (b) Temporal plus the pre-send check a competent engineer would write.

---

## 1. What we are building, in one page

A durable workflow runtime for agents. Postgres is the only required infrastructure. The package is `interlock_runtime` under `runtime/`, about 900 lines of Python, with one dependency: `psycopg[binary]>=3.2,<4`.

It matches Temporal's core:

- workflow state is durable, and a step result, once recorded, is never re-run;
- retries use backoff with Temporal's defaults;
- durable timers and long waits survive worker SIGKILL and a Postgres crash restart;
- signals (approve, revoke, cancel) are durable before workflow code sees them;
- many workers claim work under leases, and takeover is safe;
- workflow code versions are pinned, with `patched()` markers and loud non-determinism.

It adds what Temporal lacks:

- an LLM call is recorded as a decision, together with the premises it was made on;
- every external effect is gated: payload binding, premises and authority are checked in the same transaction that makes the send durable, and checked again at recovery;
- recovery depends on the target's tier (1 dedupes, 2 is queryable, 3 is neither);
- receipts are hash chained and verified by the existing `interlock.receipts.verify`, unchanged.

The design borrows from open source without vendoring any of it:

- from Absurd (Apache-2.0): the SKIP LOCKED claim with takeover on an expired lease, the database clock, and eager fencing;
- from DBOS (MIT): steps keyed by call order, fork, and first-writer-wins decisions;
- from Temporal (MIT): retry defaults, `patched()` semantics, and loud non-determinism;
- from Restate (design only): version pinning.

`runtime/NOTICE` credits all four.

Four mechanisms carry the design:

1. **One fenced transaction per worker write.** Every write a worker makes begins with an UPDATE on the workflow row. The UPDATE matches only if the claim epoch is current and the lease has not expired. It takes the row lock, which serializes the write against any claim, signal or cancel.
2. **A gated effect is two transactions around the send.**
   - `T_dispatch` binds the payload, checks cancel, locks the grant FOR SHARE, runs the local SQL premises, and writes AUTHORIZED and DISPATCHED. It also sets a durable `send_deadline`.
   - `T_commit` writes COMMITTED together with the step checkpoint.
   - Nothing may query or resend a dispatched effect before database `now() > send_deadline + settle_margin`.
3. **The effect journal keeps `interlock/journal.py`'s sealed entry format**, so `receipts.verify()` runs unchanged. Postgres constraints refuse a forked chain and a second COMMITTED.
4. **Recovery follows `gate._recover_one` row for row.** A differential test pins the two together.

---

## 2. Shared contracts (both builders and the harness use these names verbatim)

### 2.1 Invariant names

Code checks live in `runtime/interlock_runtime/invariants.py` as `INVARIANTS = {"Name": check_fn}`. TLA+ definitions use the same identifiers. The column "where" says which layer checks each one: M = TLC model, C = code checks over real runs.

| name | meaning | where |
|---|---|---|
| NoRerunAfterComplete | a step body never starts after its step row committed | M, C |
| StepResultUnique | at most one `ilr.steps` row per (workflow_id, seq), never updated or deleted | M, C |
| FencedWrites | every committed worker write carried the workflow's current epoch and a live lease at commit; the only exception is the late-result compare-and-set, which requires `dispatch_epoch` to equal the writer's epoch | M, C |
| LeaseMutex | two workers never both hold a non-expired claim on one workflow | M, C (claim history) |
| TakeoverOnlyAfterExpiry | claiming a `running` workflow succeeds only when `lease_expires_at <= now()` | M, C |
| AtMostOneCommit | at most one COMMITTED journal entry per effect_id | M, C |
| EffectAtMostOnceTier12 | at tier 1 inside the dedup window, and at tier 2, the target applies an effect_id at most once (assumes A1, A2) | M, C |
| Tier3NeverResends | at tier 3, and at tier 1 past its window with no lookup, at most one request for an effect_id ever goes on the wire | M, C |
| NoOverlappingSends | a second send of an effect_id starts only after `now() > send_deadline + settle_margin` of the previous send, so two sends are never in flight at once | M, C |
| CommittedImpliesApplied | COMMITTED implies the target ledger holds the effect | M, C |
| AmbiguousOnlyWhenUnknowable | AMBIGUOUS is written only at effective tier 3, or at tier 1 with a failed re-check and no lookup | M, C |
| EffectCheckpointAtomic | no state (outside an open `T_commit`) has a committed effect with no step row while its dispatching claim is still current | M, C |
| SendRequiresLiveClaim | every send follows a committed `T_dispatch` or `T_resolve` whose fence matched the current epoch with a live lease, and `effects.dispatch_epoch` equals that epoch | M, C |
| NoSendUnderRevokedGrant | at the commit of the transaction before every send, the grant was unrevoked and unexpired, matched the action, amount <= max_cents, and payload_hash matched | M, C |
| RevokeLinearizable | once a revoke of grant g commits, no later `T_dispatch` or `T_resolve` authorizes a send under g, and `rt.revoke` returned every effect that could still land | M, C (race loop) |
| NoSendOnStalePremise | every send was preceded by a premise check against `decided_on` with zero violations: local premises at the commit, external premises at the read (A3) | M, C |
| RecoveryRechecks | every recovery resend was preceded, in the same recovery, by a grant check and a premise check that passed, recorded as `rechecked` | M, C |
| PayloadBound | every sent payload equals the payload bound at the first PROPOSED; a different payload yields REFUSED:conflicting_payload and no send | M, C |
| NoSendAfterCancel | once `cancel_requested_at` commits, no later `T_dispatch` authorizes a non-compensation send | M, C |
| LateResultPreserved | a response that arrives after the effect was resolved by someone else is appended as LATE_RESULT, never dropped | M, C |
| ReceiptChainLinear | per effect_id, the entries form one chain (unique on effect_id and prev), and `verify()` reports `tamper_evident: true` | M, C |
| ReceiptTruthful | `verify()` reports happened, happened_once, authorized_when_fired and assumptions_held matching the target ledger, and `happened: "unknown"` exactly when the effect is AMBIGUOUS or still dispatched | C |
| TimerNotEarly | a sleep or wait-timeout step is recorded only at database time >= its recorded `until` | M (Signals), C |
| SignalExactlyOnceConsumed | each signal row is consumed by at most one wait step, and a consumed payload equals that step's output | M (Signals), C |
| NoLostWakeup | no state has a workflow sleeping with `available_at = infinity` while an unconsumed signal it waits on exists | M (Signals), C |
| VersionPinned | a workflow's steps run only on workers registered for its (name, version) | C |
| NonDeterminismLoud | a replay whose call at a seq differs in kind, name or fingerprint from the recorded row runs nothing, and the workflow becomes `stuck` | C |
| ForkNeverResends | a forked workflow that reaches an already committed effect returns DUPLICATE_IGNORED and sends nothing | C |
| Termination (liveness) | under fairness and a finite crash budget, with no pauses, every workflow reaches a terminal status or waits on a signal that is never sent | M |
| EffectResolved (liveness) | `dispatched` leads to committed, ambiguous, or a resolving REFUSED | M |

### 2.2 Kill points

Workers read kill points from the `ILR_KILL_AT` environment variable, a comma list of `name` or `name@n` (the nth time the point is hit). At a kill point the worker runs `os.kill(os.getpid(), signal.SIGKILL)`. This is a real SIGKILL at an instrumented point, and results label it `instrumented SIGKILL`. `ILR_STOP_AT` works the same way with SIGSTOP; the harness sends SIGCONT.

`runtime/interlock_runtime/killpoints.py` (about 15 lines) is the one implementation. The Temporal baseline activities import it too. The points:

| point | position |
|---|---|
| `claimed` | right after a claim commits |
| `step_before_record` | a step body returned; its step row is not written |
| `step_after_record` | |
| `decide_after_response` | the LLM response was received; the decide row is not written |
| `effect_before_dispatch` | premises read; `T_dispatch` not begun |
| `effect_after_dispatch` | `T_dispatch` committed; no bytes sent |
| `effect_after_send` | the target response was received; `T_commit` not begun |
| `effect_after_commit` | |
| `resolve_after_commit` | `T_resolve` committed a resend; no bytes sent |
| `resolve_after_send` | |
| `wait_after_suspend` | a sleep or wait_signal suspend committed |

For Temporal activities, `effect_before_dispatch` means before the HTTP send and `effect_after_send` means after the response, before returning.

### 2.3 Journal entry kinds, effect states, workflow statuses, step statuses

- **Journal kinds:** PROPOSED, AUTHORIZED, DISPATCHED, COMMITTED, REFUSED, AMBIGUOUS, LATE_RESULT. The first six are exactly `interlock/journal.py`'s. LATE_RESULT is new; `verify()` ignores kinds it does not know.
- **Effect states:** proposed, dispatched, committed, ambiguous. A refusal leaves or returns the state to `proposed`, as `dispatch_blocker` allows re-dispatch after a resolving refusal.
- **Workflow statuses:** pending, running, sleeping, completed, failed, cancelled, stuck, continued.
- **Effect result statuses** (strings returned to workflow code; identical to `gate.py` except REFUSED:cancelled): COMMITTED, DUPLICATE_IGNORED, COMMITTED_BY_RETRY, COMMITTED_ON_QUERY, REAPPLIED_AFTER_QUERY, AMBIGUOUS, REFUSED:lease, REFUSED:stale_premise, REFUSED:conflicting_payload, REFUSED:cancelled, REFUSED:target_error, REFUSED:lease_at_recovery, REFUSED:stale_premise_at_recovery.

### 2.4 Assumptions (stated in code comments, the spec and every results file)

- **A1 No long pause.** A worker process is not paused (GC stop-the-world, SIGSTOP, VM freeze) across its local send deadline. The send watchdog (5.4) enforces the deadline only while the process runs. The PAUSE toggle models violations, and S13 measures them.
- **A2 Settle.** The target finishes processing any request, including bytes delivered late from a kernel buffer, within `settle_margin` after `send_deadline`. It is set per target from measured behavior. The SERVER_SLOW toggle models violations, and S08c measures them.
- **A3 External premises are as of their read.** A change between the read and the `T_dispatch` commit is missed. Only premises in this Postgres (SQL premise readers) are atomic with dispatch. Baseline (b) has the same window, so no win is claimed there.
- **A4 Durable commits.** `synchronous_commit = on`, and no asynchronous replica failover.
- **A5 Clock rate.** Over one `send_timeout`, the database clock and the worker's monotonic clock differ in rate by less than `settle_margin`. Absolute clock offsets do not matter.

---

## 3. Package layout and ownership

```
runtime/                               RUNTIME BUILDER
  pyproject.toml                       name interlock-runtime; deps psycopg[binary]>=3.2,<4; python >=3.10
  .gitignore                           .data/
  NOTICE                               design credits (Absurd, DBOS, Temporal, Restate); psycopg LGPL-3.0 note
  interlock_runtime/
    __init__.py                        Runtime, Worker, workflow, RetryPolicy, TargetRejected, Cancelled, StepFailed, NonDeterminism
    schema.sql                         section 4
    db.py                              connect, apply schema, fenced() context manager, db_now()      ~70
    runtime.py                         Runtime client API, section 6                                    ~170
    context.py                         WorkflowContext, replay cursor, Suspend, section 5               ~200
    effects.py                         submit, T_dispatch, send, T_commit, late result, recovery        ~190
    worker.py                          claim loop, heartbeat, send watchdog, CLI                        ~140
    receipts.py                        PgJournalView(_Queries), bundle passthrough                      ~30
    invariants.py                      INVARIANTS registry, SQL and ledger checks, section 2.1          ~150
    killpoints.py                      section 2.2                                                      ~15
spec/                                  TLA+ MODELER
  Runtime.tla  Signals.tla
  Runtime.cfg  RuntimeTemporalIdem.cfg  RuntimeTemporalPrecheck.cfg  Signals.cfg
  assumptions/Pause.cfg  assumptions/ServerSlow.cfg
  broken/NaiveRecovery.cfg  broken/NoFencing.cfg  broken/GrantCheckOutsideTxn.cfg  broken/CommitWithoutCheckpoint.cfg
  broken/RecoverBeforeDeadline.cfg  broken/StopwatchAfterDispatch.cfg  broken/LateAckDropped.cfg  broken/WakeOnlyIfSleeping.cfg
  run_tlc.sh                           downloads tla2tools.jar, checks sha256 in spec/tla2tools.sha256, uses /opt/homebrew/opt/openjdk/bin/java
tests/                                 RUNTIME BUILDER
  test_runtime.py                      first gate (takeover and zombie fence) plus feature parity, real Postgres, real subprocesses
  test_runtime_sql_races.py            two-connection interleaved races, no subprocesses
  test_runtime_gate_parity.py          differential: interlock.Gate vs ctx.effect decision table and verify() output
  test_runtime_stateful.py             Hypothesis RuleBasedStateMachine, invariants by name
experiments/                           HARNESS (runtime builder after R6, or a third builder)
  runtime_pg.py                        start | stop | restart-immediate | reset | status for local Postgres 17
  runtime_target.py                    local HTTP payment target, tiers 1/2/3, SQLite ledger, admin endpoints
  runtime_fault_proxy.py               stdlib TCP fault proxy
  runtime_model_stub.py                local HTTP "model" with scripted amounts (EMULATED model variance)
  runtime_flows.py                     the refund workflow for the runtime; shared case setup
  runtime_temporal_baselines.py        the same workflow on temporalio 1.32, modes temporal and temporal_check, worker subcommand
  runtime_prove.py                     scenario runner and sweep, section 11
  runtime_audit.py                     can-prove auditor reading only each system's own records
  runtime_bench.py                     latency and throughput
  runtime_tlc.py                       runs every spec config, writes results/runtime_tlc.md (MODELER)
results/
  runtime_tlc.md  runtime_prove.md  runtime_prove.json  runtime_bench.md  runtime_prove_failures/
docs/07-runtime.md                     this file
```

**Environment.** The Docker daemon is down.

- **Postgres.** Run `brew install postgresql@17`. `experiments/runtime_pg.py` runs `initdb` into `runtime/.data/pg` and starts it on port 55432 with `fsync=on`, `synchronous_commit=on`, `max_connections=200`. It exports `ILR_DSN=postgresql://localhost:55432/ilr`. Tests skip with a clear message when `ILR_DSN` is unset.
- **Imports.** Tests and experiments add `runtime/` to `sys.path`. They run with `uv run --no-project --with 'psycopg[binary]' python ...`, adding `--with temporalio`, `--with hypothesis` as needed.
- **Keys.** They come from the environment only (`STRIPE_SECRET_KEY` test keys, or `ANTHROPIC_API_KEY`) and are never written to the repo, results or logs.
- **Java.** TLC uses `/opt/homebrew/opt/openjdk/bin/java`. The `java` on PATH is broken.

**Read-only imports from `interlock/`:**

- `journal._plain`, `journal._seal`, `journal._Queries`, `journal.open_dispatch`, `journal.effect_id_for`;
- `receipts.bundle`, `receipts.verify`;
- `gate.DEDUP_MARGIN`;
- `targets.stripe_api.StripeClient`, `targets.stripe_api.StripeRefunds`.

If any of them breaks under concurrent edits, report it. Never edit `interlock/`.

---

## 4. Postgres schema (`runtime/interlock_runtime/schema.sql`, idempotent, applied by `Runtime(dsn)`)

```sql
create schema if not exists ilr;

create table if not exists ilr.deployments (
  name text not null,
  version text not null,
  code_sha256 text not null,                -- sha256 of the workflow function's module source bytes
  created_at timestamptz not null default now(),
  retired_at timestamptz,
  primary key (name, version)
);

create table if not exists ilr.workflows (
  id text primary key,
  name text not null,
  version text not null,
  input jsonb not null,
  status text not null default 'pending' check (status in
    ('pending','running','sleeping','completed','failed','cancelled','stuck','continued')),
  epoch bigint not null default 0,          -- fencing token, +1 on every claim
  owner text,
  lease_expires_at timestamptz,
  takeovers int not null default 0,         -- claims that died since the last recorded step
  available_at timestamptz not null default now(),   -- 'infinity' while waiting with no timeout
  waiting jsonb,                            -- {seq, kind, until, signal, attempt}
  cancel_requested_at timestamptz,
  result jsonb,
  error jsonb,
  parent_id text,
  continued_from text,
  forked_from text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (name, version) references ilr.deployments
);
create index if not exists wf_due on ilr.workflows (available_at) where status in ('pending','sleeping');
create index if not exists wf_leased on ilr.workflows (lease_expires_at) where status = 'running';

create table if not exists ilr.steps (
  workflow_id text not null references ilr.workflows(id),
  seq int not null,
  name text not null,
  kind text not null check (kind in ('step','decide','effect','sleep','signal','patch','child')),
  fingerprint text,                         -- effect: effect_id||':'||payload_hash; decide: request_hash; else null
  output jsonb,
  error jsonb,
  epoch bigint not null,
  created_at timestamptz not null default now(),
  primary key (workflow_id, seq)
);

create table if not exists ilr.llm_calls (  -- written in autocommit BEFORE each model call; measures discarded calls
  id bigserial primary key,
  workflow_id text not null,
  seq int not null,
  epoch bigint not null,
  request_hash text not null,
  started_at timestamptz not null default now()
);

create table if not exists ilr.signals (
  id bigserial primary key,
  workflow_id text not null references ilr.workflows(id),
  name text not null,
  payload jsonb not null,
  sender text,
  consumed_seq int,
  created_at timestamptz not null default now(),
  unique (workflow_id, consumed_seq)
);

create table if not exists ilr.grants (     -- policy grants and human approvals
  id text primary key,
  principal text not null,
  action text not null,
  max_cents bigint,                         -- null: no cap
  payload_hash text,                        -- set by an approval: only this exact payload
  facts_seen jsonb,                         -- set by an approval: the premises it authorizes
  granted_by text not null,
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists ilr.effects (
  effect_id text primary key,               -- interlock.journal.effect_id_for({"request_id": key})
  workflow_id text not null references ilr.workflows(id),   -- first proposer
  target text not null,
  tier smallint not null check (tier in (1,2,3)),
  payload jsonb not null,
  payload_hash text not null,               -- bound at first proposal, immutable (trigger)
  state text not null default 'proposed' check (state in ('proposed','dispatched','committed','ambiguous')),
  grant_id text references ilr.grants(id),  -- grant of the current or last dispatch
  dispatch_workflow_id text,
  dispatch_epoch bigint,                    -- (dispatch_workflow_id, dispatch_epoch) may finish the current send
  first_dispatched_at timestamptz,          -- database clock; tier-1 window age is measured from here
  send_deadline timestamptz,                -- no query or resend before send_deadline + settle_margin
  settle_margin interval,
  sends int not null default 0,             -- incremented in the transaction that authorizes each send
  late_result jsonb,
  reconciled jsonb                          -- human attestation for AMBIGUOUS; never written into the journal
);
create index if not exists effects_open on ilr.effects (send_deadline) where state = 'dispatched';
create index if not exists effects_by_grant on ilr.effects (grant_id) where state = 'dispatched';

create table if not exists ilr.journal (
  seq bigserial primary key,
  effect_id text not null references ilr.effects(effect_id),
  kind text not null check (kind in ('PROPOSED','AUTHORIZED','DISPATCHED','COMMITTED','REFUSED','AMBIGUOUS','LATE_RESULT')),
  body text not null,                       -- json.dumps(_seal(entry, previous)), stored verbatim, never jsonb
  prev text,
  hash text not null unique,
  unique nulls not distinct (effect_id, prev)
);
create unique index if not exists one_commit on ilr.journal (effect_id) where kind = 'COMMITTED';

create or replace function ilr.append_only() returns trigger language plpgsql as
  $$ begin raise exception 'ilr.% is append-only', tg_table_name; end $$;
create or replace trigger steps_append_only before update or delete on ilr.steps
  for each statement execute function ilr.append_only();
create or replace trigger journal_append_only before update or delete on ilr.journal
  for each statement execute function ilr.append_only();

create or replace function ilr.effects_guard() returns trigger language plpgsql as $$
begin
  if new.payload_hash <> old.payload_hash then raise exception 'payload binding: % is immutable', old.effect_id; end if;
  if old.state in ('committed','ambiguous') and new.state <> old.state then
    raise exception 'effect % is terminal (%)', old.effect_id, old.state; end if;
  return new;
end $$;
create or replace trigger effects_guard before update on ilr.effects
  for each row execute function ilr.effects_guard();
```

**Lock order, asserted in review and in `test_runtime_sql_races.py`:** workflow row, then effect row, then grant row. Every transaction that takes more than one of these locks takes them in that order. The late-result transaction locks only the effect row.

**Clock.** Every time the protocol depends on comes from `now()` inside the transaction. That includes the journal entry `ts`, which is set to `extract(epoch from now())` read in the same transaction, so `ts` is the database clock too.

**Payload hash.** `sha256(json.dumps(_plain(payload), sort_keys=True, separators=(",", ":")))`.

---

## 5. Execution model (`context.py`, `effects.py`)

### 5.1 Replay from the top, with a step cache

A workflow is a plain function `f(ctx, input)`. Each durable call takes the next `seq`: `step`, `decide`, `effect`, `sleep`, `wait_signal`, `patched`, `child`, `wait_child`, `continue_as_new`.

When a worker claims a workflow, it loads all of the workflow's step rows in one query and runs `f` from the top.

- **A recorded row exists at `seq`.** The row's `kind` and `name` must match the call, and so must its `fingerprint` for effect and decide. Then the call returns the recorded output, or re-raises the recorded error, and runs nothing. On a mismatch, `NonDeterminism` sets `status='stuck'` with `error = {seq, recorded, called}`. There is no retry loop.
- **No recorded row.** This is the frontier, and the call executes for real.
- **The call cannot finish now.** A sleep is not due, a signal has not arrived, a retry is backing off, or an effect is in flight. The call writes `waiting` and releases the row in one fenced transaction (5.6), then raises `Suspend`.

`Suspend` subclasses `BaseException`. If `f` returns while the context has a suspend flag set (a bare `except:` swallowed it), the worker marks the workflow `stuck` with `error = "Suspend swallowed"`.

### 5.2 The fence (`db.fenced(conn, wf_id, epoch, ttl)`)

The first statement of every worker write:

```sql
update ilr.workflows
   set lease_expires_at = now() + make_interval(secs => $ttl), updated_at = now()
 where id = $wf and epoch = $epoch and status = 'running' and lease_expires_at > now()
returning cancel_requested_at, now();
```

Zero rows raises `Fenced`: roll back and abandon the run. This check is eager, on lease expiry as well as epoch. That makes "holds a live claim" one predicate, the one the spec names SendRequiresLiveClaim. The cost is that a sole worker whose lease lapsed abandons its run. That is a liveness cost only: its effects still resolve through the late-result path or through recovery.

A returned `cancel_requested_at` sets `ctx.cancelled`. The next durable call, other than a `T_commit` already in progress, raises `Cancelled` into workflow code. An uncaught `Cancelled` ends the workflow with status `cancelled`.

### 5.3 Claims, heartbeat, takeover (`worker.py`)

```sql
with c as (
  select id from ilr.workflows
   where ((status in ('pending','sleeping') and available_at <= now())
       or (status = 'running' and lease_expires_at <= now()))
     and (name, version) in (select * from unnest($1::text[], $2::text[]))
   order by available_at limit $3
   for update skip locked)
update ilr.workflows w
   set status = 'running', epoch = w.epoch + 1, owner = $4,
       takeovers = w.takeovers + (w.status = 'running')::int,
       lease_expires_at = now() + make_interval(secs => $5), updated_at = now()
  from c where w.id = c.id
returning w.id, w.name, w.version, w.input, w.epoch, w.waiting, w.takeovers, w.cancel_requested_at;
```

- **Heartbeat.** One thread per claimed workflow runs the fence UPDATE every `ttl/3` in autocommit. On zero rows it sets `ctx.fenced`, and the main thread raises `Fenced` at its next durable call.
- **Wakeups.** Workers `LISTEN ilr_ready`. It is NOTIFYed by start, signal, approve and cancel. Workers also poll every `poll` seconds (default 1.0), so a timer fires within one poll interval of its due time while a worker is up.
- **Attempts.** A recorded step resets `takeovers` to 0. The first unrecorded step computes `attempt = (waiting.attempt or 0) + takeovers`, so a crash loop counts against the step's retry policy.
- **Registration.** At startup a worker upserts `(name, version, code_sha256)` into `ilr.deployments` for each registered workflow. If a row exists with a different `code_sha256`, the worker exits with status 2 and prints both hashes.

### 5.4 The send watchdog (graft: total deadline, stopwatch before dispatch)

`ctx.effect` starts `t0 = time.monotonic()` before `T_dispatch` begins, so `t0` precedes the transaction's `now()`. `T_dispatch` sets `send_deadline = now() + target.send_timeout`.

After the commit, `remaining = send_timeout - (monotonic() - t0)`.

- If `remaining < min_send_budget` (default 1.0s), the worker does not send. The effect stays dispatched and the workflow suspends until `send_deadline + settle_margin`, when recovery handles it.
- Otherwise it starts `threading.Timer(remaining, os._exit, (75,))`, sets the target's socket timeout to `remaining` where the target supports it, calls `target.apply`, and cancels the timer.

`os._exit` ends the process, so no bytes can leave after the local deadline while the process runs (A1). A urllib socket timeout applies to each operation, not to the whole request, which is why the watchdog exists. Other workflows in the same process count as crashed and are recovered. `ponytail: whole-process exit, per-send subprocess isolation if concurrency makes this costly.`

Target attributes are read with `getattr` defaults:

| attribute | default |
|---|---|
| `send_timeout` | 35 |
| `settle_margin` | 10 |
| `premise_max_age` | 5 |
| `queryable` | `tier == 2` |
| `dedup_window` | `inf` |

The `send_timeout` default exceeds `StripeClient`'s urlopen timeout of 30s. The recommended lease ttl is 30s. The lease does not need to outlast a send, because safety comes from `send_deadline`.

### 5.5 Plain steps, retries, decisions

`ctx.step(name, fn, *args, retry=RetryPolicy())` runs `fn` and records the output in a fenced transaction.

- **fn raises a retryable error with attempts left:** the step writes `waiting = {seq, kind:'retry', attempt+1}`, sets `status='pending'` and `available_at = now() + backoff(attempt)`, and suspends.
- **Otherwise:** it records the error and raises `StepFailed`.

Steps are at least once: a crash between `fn` returning and the record re-runs `fn`, exactly like a Temporal activity. Anything with an external side effect must use `ctx.effect`. The worker enforces this for targets: `ctx.step` refuses to take an object with an `apply` attribute.

`RetryPolicy(initial=1.0, backoff=2.0, max_interval=None, max_attempts=0, non_retryable=())`. `max_interval=None` means 100 x initial, and `max_attempts=0` means unlimited. These are Temporal's defaults. `backoff(n) = min(initial * backoff**(n-1), max_interval)`.

`ctx.decide(name, call, request, premises=None, retry=RetryPolicy())`:

1. `captured = premises() if premises else None`, with `captured_at` taken from the database.
2. `request_hash = sha256(canonical request)`.
3. Insert into `ilr.llm_calls` in autocommit.
4. `response = call(request)`. The key is read from the environment inside `call`.
5. In a fenced transaction, insert the step with `kind='decide'`, `fingerprint=request_hash` and `output = {model, request_hash, response, usage, premises: captured, captured_at}`.

The primary key makes the record first-writer-wins. `ctx.decide` returns `Decision(output, premises, ref={workflow_id, seq, request_hash})`. The number of discarded LLM calls is `count(llm_calls) - count(decide steps)` per workflow, and the harness reports it.

### 5.6 Sleep, signals, suspend (fix: no lost wakeup)

**Suspend transaction.** One fenced transaction does all of the following. Because the fence locks the workflow row first, a concurrent `rt.signal` or `rt.cancel` either commits before it (and the mailbox check sees the row) or waits for it (and then wakes the row).

```
fence
if kind == 'signal':
    select id, payload from ilr.signals
     where workflow_id = $wf and name = $name and consumed_seq is null
     order by id limit 1 for update
    if found: update signals set consumed_seq = $seq; insert step(kind='signal', output=payload); commit; return payload
if waiting.until is not null and now() >= until: insert step (sleep: output null; signal: output null meaning timeout); commit; return
update ilr.workflows set status = 'sleeping', owner = null, lease_expires_at = null,
       waiting = {seq, kind, signal, until}, available_at = coalesce(until, 'infinity')
commit; raise Suspend
```

- **`ctx.sleep(seconds)`.** The first call records `waiting.until = now() + seconds`. On a later claim, the step is recorded only if `now() >= until`.
- **`rt.signal(wf_id, name, payload, sender=None)`.** One transaction: `select ... from ilr.workflows where id = $wf for update`, then insert the signal, then `update ilr.workflows set available_at = now(), status = case when status = 'sleeping' then 'pending' else status end where id = $wf and status not in ('completed','failed','cancelled','continued')`, then `NOTIFY ilr_ready`.

  Setting `available_at = now()` on every non-terminal status is deliberate. A running workflow that suspends later computes its own `available_at`, but the mailbox check inside the suspend transaction has already consumed the signal.
- **`rt.cancel(wf_id, by)`.** The same shape: lock the row, set `cancel_requested_at = now()`, wake it.

### 5.7 Gated effects (the Postgres port of `gate.submit` and `gate._recover_one`)

`ctx.effect(target, key, payload, premises, grant, name=None, local_premises=(), compensation=False, raise_on_refusal=False) -> EffectResult(status, effect_id, result)`

- `eid = effect_id_for({"request_id": key})`.
- `ph = payload_hash(payload)`.
- `fingerprint = eid + ":" + ph`.
- `local_premises` is a list of `(sql_fn, args)`. `sql_fn` is a registered SQL function `fn(args jsonb, effect_id text) returns jsonb`: an array of violation strings, reading its rows FOR SHARE.

**Replay.** If a step row exists at `seq`, compare fingerprints (mismatch: NonDeterminism), then return the recorded `EffectResult`.

Otherwise read the effect row and branch:

- no row, or `state = 'proposed'`: the submit path;
- `state = 'dispatched'` with `(dispatch_workflow_id, dispatch_epoch)` not equal to this claim: the recovery path;
- `state in ('committed','ambiguous')`: handled inside `T_dispatch` as below.

**Submit path.**

(a) **External premises, outside any transaction.**
- `decided_on` is the `premises` of the first PROPOSED entry whose `lease == grant`. If there is none, it is the `premises` argument. This is gate.py's rule.
- `violations = target.validate_premises(decided_on, eid)`.
- Remember `read_t = monotonic()`.

(b) **Kill point `effect_before_dispatch`.** Start the stopwatch `t0`. If `t0 - read_t > premise_max_age`, redo (a).

(c) **`T_dispatch`, fenced.** Steps in this order:
1. Insert the effects row on conflict do nothing, then `select ... for update`.
2. Read this effect's entries. The previous entry is `select body from ilr.journal where effect_id = $eid order by seq desc limit 1`.
3. **Open dispatch** by another workflow or claim (`open_dispatch(entries)`): commit nothing and suspend with `status='pending'` and `available_at = send_deadline + settle_margin`. The status is IN_FLIGHT, and no step is recorded.
4. **Stored `payload_hash` differs:** append PROPOSED (the offered payload) and REFUSED `{reason: "payload differs from recorded decision", recorded, offered}`. Record the step as REFUSED:conflicting_payload.
5. **State `ambiguous`:** record AMBIGUOUS with no entry. **State `committed`:** record DUPLICATE_IGNORED with no entry.
6. Append PROPOSED `{agent: workflow name, lease: grant, premises: offered premises, effect: payload, decision: ref if given}`.
7. **Cancel set and not `compensation`:** append REFUSED `{reason: "cancelled"}` and record REFUSED:cancelled.
8. `select * from ilr.grants where id = $grant for share`. Then `allowed = revoked_at is null and (expires_at is null or expires_at > now()) and action = $action and (max_cents is null or payload amount <= max_cents) and (payload_hash is null or payload_hash = $ph)`. Build `checks = {lease_live: allowed, lease: snapshot}`, where `snapshot = {grant_id, principal, action, max_cents, payload_hash, expires_at, revoked, granted_by}` and `revoked = revoked_at` (null or an ISO string). These are exactly the keys `receipts._lease_held` reads. If not allowed: append REFUSED `{reason: "lease not live, or it does not cover this effect", checks}` and record REFUSED:lease.
9. Append AUTHORIZED `{lease: grant}`.
10. Run each local premise function and concatenate its violations with the external ones into `checks.violations`. Any violation: append REFUSED `{reason: violations, checks}` and record REFUSED:stale_premise.
11. Append DISPATCHED `{effect: payload, lease: grant, premises: decided_on, checks}`.
12. Update effects: `state='dispatched'`, `grant_id`, `dispatch_workflow_id = $wf`, `dispatch_epoch = $epoch`, `first_dispatched_at = coalesce(first_dispatched_at, now())`, `send_deadline = now() + send_timeout`, `settle_margin`, `sends = sends + 1`.
13. COMMIT.

A refusal recorded in steps 4, 7, 8 or 10 inserts the step row in this same transaction.

(d) **Kill point `effect_after_dispatch`.** Watchdog and send (5.4): `result = target.apply(eid, payload)`.

(e) **Kill point `effect_after_send`, then `T_commit`, fenced.**
- `select ... from ilr.effects for update`.
- If `state = 'dispatched'` and the dispatch pair matches: append COMMITTED `{result}`, set `state = 'committed'`, and insert the step row with status COMMITTED.
- If the fence fails: roll back and run the late-result transaction.

(f) **Late-result transaction.** Unfenced, locks only the effect row.
- If `state = 'dispatched'` and `(dispatch_workflow_id, dispatch_epoch) = (mine)`: append COMMITTED `{result}` and set `state='committed'`. No step row; the successor's replay reads the committed effect as DUPLICATE_IGNORED.
- Otherwise: append LATE_RESULT `{result, from_epoch, state_at_arrival}` and set `late_result`. If `state_at_arrival` was `proposed`, meaning a resolving REFUSED closed the send, add `assumption_violated: "A2"`.

(g) **Exceptions from `apply`.**
- `TargetRejected`, a definite failure: settle as `gate.settle_failed` does. If the target is queryable and `query` finds the effect, append COMMITTED `{via: "failed-but-landed"}` and record COMMITTED_ON_QUERY. Otherwise append REFUSED `{reason: "target reported failure: ...", resolves: true}`, set `state='proposed'`, and record REFUSED:target_error.
- Any other exception, including a socket timeout: leave the effect dispatched and suspend with `status='pending'` and `available_at = send_deadline + settle_margin`. The next claim takes the recovery path.

This is the fix for the timeout-then-immediate-lookup duplicate.

**Recovery path** (`state='dispatched'`, no step row for this seq).

(a) In a short read, fetch the effect, its last DISPATCHED entry and `now()`. If `now() <= send_deadline + settle_margin`, suspend until then without writing anything. Also compute the tier: tier 1 with `now() - first_dispatched_at > dedup_window - DEDUP_MARGIN` becomes tier 2 if queryable, else tier 3.

(b) **Tier 3.** In `T_resolve` (below), append AMBIGUOUS, set `state='ambiguous'`, and record AMBIGUOUS.

(c) **Tiers 1 and 2, outside any transaction.** `violations = target.validate_premises(dispatched.premises, eid)`. At tier 2, and at tier 1 when the re-check might fail, also call `found = target.query(eid, payload)`.

(d) **`T_resolve`, fenced.**
- Lock the effect FOR UPDATE and require `state='dispatched'`, an unchanged `(dispatch_workflow_id, dispatch_epoch)`, and `now() > send_deadline + settle_margin`. If any of these fails, roll back and re-enter the effect call.
- Lock the grant FOR SHARE and rebuild `checks` exactly as in step 8. Add `violations` (external plus local) only when the lease holds, as `gate._recheck` does.
- Apply `gate._recover_one`'s table:

| condition | action |
|---|---|
| tier 1, not stale | update the dispatch pair to this claim, `send_deadline = now() + send_timeout`, `sends + 1`; commit; kill point `resolve_after_commit`; watchdog; resend; kill point `resolve_after_send`; then fenced append COMMITTED `{via: "retry-idempotent", rechecked: checks, result}` plus the step row: COMMITTED_BY_RETRY |
| stale, not queryable | append AMBIGUOUS `{reason: "<lease or stale_premise> at recovery, no lookup", rechecked}`: AMBIGUOUS |
| found | append COMMITTED `{via: "recovery-query", rechecked, found}`: COMMITTED_ON_QUERY |
| stale, not found | append REFUSED `{reason: "<stale> at recovery", resolves: true, rechecked}`, `state='proposed'`: REFUSED:<lease or stale_premise>_at_recovery |
| not stale, not found | dispatch pair update and resend as in the tier 1 row, then COMMITTED `{via: "recovery-reapply", rechecked, result}`: REAPPLIED_AFTER_QUERY |

A resend never appends a second DISPATCHED. The DISPATCHED entry stays open until COMMITTED, AMBIGUOUS or a resolving REFUSED, so `verify()` counts resends through `via` and does not report "sent again while an earlier send was unresolved". The durable record of a resend attempt is the effects row update (dispatch pair, `send_deadline`, `sends`), committed before any bytes go out.

**Orphans.** `rt.recover_orphans()` finds effects in `state='dispatched'` whose `dispatch_workflow_id` is `stuck`, `failed` or `cancelled`. For each one it runs the recovery path under a synthetic claim: an epoch bump with owner `$recovery`. It writes journal entries and the effects row only, then restores the workflow's previous status.

### 5.8 Versioning, children, continue-as-new, fork

- **`@workflow(name, version)`** registers the code. `rt.start(name, id, input, version=None)` uses the newest non-retired deployment when `version` is None. Workers claim only the (name, version) pairs they registered.
- **`ctx.patched(patch_id)`** follows Temporal's semantics:
  - at the frontier: record `kind='patch'` with name `patch_id` and return True;
  - if the recorded row at `seq` is that marker: consume it and return True;
  - if it is anything else: return False without consuming `seq`.
- **`rt.migrate(wf_id, to_version)`** changes `version` only while the workflow is not running.
- **`rt.drain_report()`** returns `select name, version, status, count(*) from ilr.workflows group by 1,2,3`. Retire a version only when it has no non-terminal rows.
- **`ctx.child(name, input, id=None)`** records the child id and inserts the child row in the same fenced transaction. `ctx.wait_child(id)` is `wait_signal('$done:' + id)`, and the child's completion transaction inserts that signal.
- **`ctx.continue_as_new(input)`** marks the run `continued` and inserts the successor with `continued_from` in one transaction.
- **`rt.fork(wf_id, at_seq, new_id)`** copies step rows with `seq < at_seq` into a new workflow with `forked_from`, and deletes nothing. Effects are keyed by the approved request, so a forked run that reaches a committed effect gets DUPLICATE_IGNORED (ForkNeverResends). A forked run that decides a different payload gets REFUSED:conflicting_payload.

---

## 6. Public Python API

```python
from interlock_runtime import Runtime, Worker, workflow, RetryPolicy, TargetRejected, Cancelled, StepFailed, NonDeterminism

rt = Runtime(dsn)                                             # applies schema.sql

@workflow(name="refund", version="2026-09-13.1")
def refund(ctx, case):
    target = targets_for(case)                                # EffectTarget: tier, apply, query, validate_premises, capture
    d = ctx.decide("pick_amount", call=model_call, request=prompt_for(case), premises=target.capture)
    approval = ctx.wait_signal("approve", timeout=24 * 3600)  # payload {grant_id, payload, facts_seen}
    if approval is None:
        return "approval expired"
    r = ctx.effect(target, key=f"refund:{case['id']}", payload={"amount": d.output["amount"]},
                   premises=approval["facts_seen"], grant=approval["grant_id"])
    if r.status == "AMBIGUOUS":
        ctx.step("page_human", notify_ops, r.effect_id)
    ctx.sleep(3600)
    if ctx.patched("verify-after-refund"):
        ctx.step("verify", check_refund, r.effect_id)
    return r.status
```

Client methods:

| method | behavior |
|---|---|
| `rt.start(name, wf_id, input, version=None) -> wf_id` | idempotent on `wf_id` |
| `rt.grant(principal, action, max_cents=None, expires_in=None, by, grant_id=None) -> grant_id` | policy grant |
| `rt.approve(wf_id, payload, facts_seen, by, expires_in=None, action="refund") -> grant_id` | one transaction: lock the workflow row; insert a grant with `payload_hash` and `facts_seen`; insert signal `approve` `{grant_id, payload, facts_seen}`; wake |
| `rt.revoke(grant_id, by) -> [effect_id]` | one transaction: `update ilr.grants set revoked_at = now() where id = $g` (waits for any `T_dispatch` holding FOR SHARE), then `select effect_id from ilr.effects where grant_id = $g and state = 'dispatched'`. The returned list is exactly what may still land |
| `rt.signal(wf_id, name, payload, sender=None)` | |
| `rt.cancel(wf_id, by)` | |
| `rt.describe(wf_id)` | workflow row, steps, effects, waiting; read only, never runs code |
| `rt.list(status=None, name=None, version=None)` | |
| `rt.result(wf_id, timeout=None)` | |
| `rt.drain_report()` | |
| `rt.fork(wf_id, at_seq, new_id)` | |
| `rt.migrate(wf_id, to_version)` | |
| `rt.recover_orphans()` | |
| `rt.receipt(effect_id, key=None)` | `interlock.receipts.bundle(PgJournalView(rt), effect_id, key)` plus top-level `late_result` and `reconciled` keys; `interlock.receipts.verify(bundle, key)` runs unchanged |
| `rt.ambiguous() -> [effect rows]` | |
| `rt.reconcile(effect_id, evidence, by)` | writes `effects.reconciled` only |

`PgJournalView(rt)` subclasses `interlock.journal._Queries` and implements only `entries(effect_id=None)`: `select body from ilr.journal [where effect_id = $1] order by seq`, then `json.loads`.

Worker:

```
Worker(rt, [refund], worker_id="w1", concurrency=4, lease_ttl=30, poll=1.0).run()
python -m interlock_runtime.worker --dsn $ILR_DSN --module experiments.runtime_flows --id w1 --lease-ttl 30 --concurrency 4
```

`SIGTERM` finishes in-flight sends, then exits.

---

## 7. What Temporal features are and are not matched (the parity claim to be measured)

**Equal, and must pass before any "better" claim:**
- step results are recorded and never re-run;
- retries use the four knobs and `non_retryable`;
- durable timers (the runtime's resolution is the poll interval; Temporal fires promptly);
- signals are durable before code sees them;
- cancellation;
- leased multi-worker claims with takeover after `lease_ttl`;
- version pinning;
- `patched()`;
- non-determinism detection (the runtime parks the workflow as `stuck`; Temporal retries the Workflow Task forever, and both need an operator);
- child workflows and continue-as-new.

**Better, only where Temporal documents no mechanism:**
- premises re-checked at send and at recovery;
- authority linearized with dispatch;
- approvals bound to a payload and to the facts the approver saw;
- recovery by tier, with AMBIGUOUS in place of unlimited retries;
- no query or resend before `send_deadline + settle_margin`;
- effect commit and step checkpoint in one transaction;
- fork that never re-sends;
- decisions recorded with their premises;
- verifiable receipts;
- one service to operate.

**Worse, conceded up front:**
- scale and throughput (one primary, polling, O(steps) replay per resume);
- no parallel steps inside one workflow (fan out with children);
- no Updates or query handlers;
- no UI;
- Python only;
- maturity;
- tier 3 blocks effects that were never sent;
- a pause beyond A1, or a target slower than A2, duplicates at tier 2 exactly as Temporal does.

---

## 8. Runtime build milestones (runtime builder)

Each milestone gates the next.

- **R0.** `experiments/runtime_pg.py`, `schema.sql`, `db.py`. Schema applies twice cleanly.
- **R1, the first gate.** `tests/test_runtime.py::test_takeover_and_zombie_fence`, built before any effect code:
  - two worker subprocesses run a 3-step workflow whose steps log invocations to a test table;
  - SIGKILL the claim holder mid-step; assert the second worker claims only after `lease_expires_at`, using database timestamps from the claim history;
  - SIGSTOP a third worker past its lease, let another claim, SIGCONT, and assert its write raises `Fenced` and changes nothing;
  - assert NoRerunAfterComplete, LeaseMutex and TakeoverOnlyAfterExpiry from the history.
- **R2.** `context.py`: step, retry, sleep, wait_signal, patched, NonDeterminism. Feature tests:
  - a step never re-runs across SIGKILL;
  - backoff gaps measured on the database clock;
  - a timer survives worker SIGKILL and `runtime_pg.py restart-immediate` (a real Postgres crash);
  - two signals buffered under one name;
  - cancel mid-sleep;
  - a v2-only worker never claims v1;
  - a changed step name leads to `stuck`.
- **R3.** `effects.py` submit path, `receipts.py`, and `test_runtime_sql_races.py`, which uses two connections with explicit BEGIN and interleaved statements:
  - revoke vs `T_dispatch` in both orders;
  - cancel vs `T_dispatch`;
  - signal vs the suspend transaction in both orders (NoLostWakeup);
  - concurrent submit with different payloads;
  - concurrent journal appends to one chain (the unique constraint must reject the loser);
  - a second COMMITTED (the partial index must reject it).
- **R4.** The recovery path, late result, orphans. `test_runtime_gate_parity.py` is a differential test, labeled as not live:
  - for each fault in `experiments/refund_agent.py` at tiers 1 to 3, build the same pre-recovery state in `interlock.Gate` (file journal) and in the runtime (a worker SIGKILLed at `effect_after_dispatch` or `effect_after_send` against `experiments/runtime_target.py`);
  - apply the same world events and recover both;
  - assert equal result statuses and equal `verify()` outputs, field by field, except `ts` and hashes;
  - also assert `verify()` reports `authorized_when_fired: false` for a DISPATCHED whose snapshot has `revoked` set (fix: snapshot shape).
- **R5.** `decide`, `child`, `continue_as_new`, `fork`, `migrate`, `drain_report`.
- **R6.** `invariants.py` and `test_runtime_stateful.py`: a Hypothesis `RuleBasedStateMachine` against real Postgres and worker subprocesses.
  - Rules: start, run_worker, sigkill_worker, sigstop and sigcont, approve, revoke, hand_refund (target admin), cancel, signal, advance_to_next_timer (a real sleep capped at 3s, with timers shortened in this test only and labeled EMULATED), deploy_v2.
  - After each rule, every `INVARIANTS` entry that applies runs.
  - Seed recorded, `max_examples` small.
- **R7.** Stripe test-mode adapter in `experiments/runtime_flows.py`: wraps `StripeRefunds`, maps `StripeError` with a 4xx code to `TargetRejected`, sets `send_timeout=35` and `settle_margin=10`.

---

## 9. Risks the builders must not paper over

- The fence is eager on lease expiry. A heartbeat thread starved by a C extension holding the GIL causes spurious abandonment. That is safe, but it costs availability. `lease_ttl` must exceed the worst heartbeat gap the harness observes, and the harness reports that gap.
- The send watchdog exits the whole process, so concurrency means collateral recoveries. The harness measures them.
- Revokes wait on in-flight `T_dispatch` transactions. External premises are read before the transaction to keep it short. A slow local premise function stalls revokes.
- Replay is O(steps) per resume, and the determinism burden is on user code. Long agent loops need `continue_as_new`.
- The hash chain lives in a database its operator controls. Without an HMAC key shared with a counterparty, receipts prove internal consistency only. `verify()` already says `signed: null`.
- psycopg is LGPL-3.0: fine as an unmodified import, and noted in NOTICE.
- Concurrent edits to `interlock/` can break receipt compatibility. The parity test fails loudly; report it, do not edit.

---

## 10. TLA+ model (TLA+ modeler)

Deliverables: `spec/Runtime.tla` for claims, the step journal, dispatch, recovery by tier, and premise and lease re-checks; `spec/Signals.tla` for suspend, signal and timer. Both are checked by TLC via `spec/run_tlc.sh`. `experiments/runtime_tlc.py` runs every config and writes `results/runtime_tlc.md`, labeled "model check for the stated constants, not a proof of the Python or SQL".

### 10.1 Runtime.tla constants

```
CONSTANTS Workers            \* {w1, w2}
          Tier               \* 1, 2 or 3 (one config per tier, or a model value set)
          Queryable          \* BOOLEAN (tier 1 Stripe-like: TRUE; tier 1 without lookup: FALSE)
          MODE               \* "interlock" | "temporal_idem" | "temporal_precheck"
          BROKEN             \* "none" | "naive_recovery" | "no_fencing" | "grant_check_outside_txn"
                             \*   | "commit_without_checkpoint" | "recover_before_deadline"
                             \*   | "stopwatch_after_dispatch" | "late_ack_dropped"
          PAUSE, SERVER_SLOW \* BOOLEAN assumption toggles (A1, A2)
          Events             \* subset of {"revoke", "hand_refund_full", "hand_refund_partial", "cancel", "prune_keys", "redecide"}
          MaxClock, LeaseTTL, SendTimeout, SettleMargin, DedupAge, MaxCrashes
```

Base constants: `Workers = {w1, w2}`, `MaxClock = 12`, `LeaseTTL = 3`, `SendTimeout = 2`, `SettleMargin = 2`, `DedupAge = 6`, `MaxCrashes = 2`, `PAUSE = SERVER_SLOW = FALSE`, `BROKEN = "none"`, `Events` = all of them.

`DedupAge` stands for `dedup_window - DEDUP_MARGIN`. `prune_keys` is enabled only when `now - firstDispatch > DedupAge`. The payload is 20; `redecide` makes a retry or fork offer 30.

### 10.2 Variables (names map to schema columns)

| variable | maps to |
|---|---|
| `now` | database clock, 0..MaxClock |
| `wfStatus`, `wfEpoch`, `wfOwner`, `leaseExp` | `ilr.workflows` |
| `stepRow` | `[ {"plain","effect"} -> BOOLEAN ]`: `ilr.steps` |
| `plainStarts`, `plainStartsAfterRow` | counts of plain body executions (NoRerunAfterComplete) |
| `effState` | `{"none","proposed","dispatched","committed","ambiguous"}` |
| `boundPayload` | `{0, 20, 30}` (0 = unbound) |
| `grantId`, `dispWorkerEpoch`, `firstDispatch`, `sendDeadline` | `ilr.effects` |
| `journal` | sequence of `[kind, via, resolves, recheckOk]` |
| `grantRevoked` | BOOLEAN |
| `revokeAt` | `-1` or the clock value when the revoke committed |
| `revokeReturned` | set of effects `rt.revoke` returned |
| `handRefund` | `{0, 10, 20}`: the external premise world |
| `localOk` | BOOLEAN: the SQL premise |
| `cancelAt` | `-1` or clock |
| `up[w]`, `paused[w]`, `pc[w]`, `myEpoch[w]`, `localDeadline[w]`, `readOk[w]` | per worker |
| `wire` | set of in-flight requests `[id, payload, key, sender, sentAt, processBy]` |
| `ledger` | bag of applied payloads for this effect |
| `keyLive` | BOOLEAN: the target's dedup key is still stored |
| `sendLog` | sequence of `[at, epoch, liveClaim, grantOk, premiseOk, payload, resend, afterRevoke, afterCancel, prevSendSettled]` |
| `lateResults` | Nat |
| `crashes` | Nat |
| `attempt`, `attemptStart`, `attemptKey` | temporal modes only |

### 10.3 Actions (MODE = "interlock"; each is one atomic step unless noted)

- **`Tick`**: `now' = now + 1` while `now < MaxClock`.
- **`Claim(w)`**: guard `up[w] /\ ~paused[w] /\ (wfStatus = "pending" \/ (wfStatus = "running" /\ leaseExp <= now))`. Effect: `wfEpoch' = wfEpoch + 1`, `wfOwner' = w`, `leaseExp' = now + LeaseTTL`, `myEpoch'[w] = wfEpoch + 1`.
- **`Heartbeat(w)`**: `Fence(w)` holds (below); `leaseExp' = now + LeaseTTL`.
- **`Fence(w)`** (predicate): `myEpoch[w] = wfEpoch /\ wfOwner = w /\ leaseExp > now`. With BROKEN = "no_fencing" it is TRUE.
- **`Crash(w)`**: `crashes < MaxCrashes`; `up'[w] = FALSE`; local state is lost; database and wire are kept.
- **`Restart(w)`**: `up'[w] = TRUE`, `pc'[w] = "idle"`.
- **`Pause(w)` / `Resume(w)`**: enabled only when PAUSE.
  - Paused workers take no steps.
  - A paused worker in `pc = "sending"` may, on Resume, still emit its request after `localDeadline[w]`. That is the A1 violation.
  - When PAUSE = FALSE, a worker whose `now >= localDeadline[w]` while `pc = "sending"` is forced to `Crash` (the watchdog).
- **`RunPlain(w)`**: `pc[w] = "plain"`; increments `plainStarts`, and also `plainStartsAfterRow` if `stepRow["plain"]`. **`RecordPlain(w)`**: `Fence(w)`; `stepRow'["plain"] = TRUE`.
- **`ReadPremise(w)`**: `readOk'[w] = (handRefund = 0)`, an external read. A later HandRefund before `TDispatch` models A3, and the invariant is stated relative to the read.
- **`TDispatch(w)`**: `Fence(w) /\ effState \in {"none","proposed"}`. Atomically:
  - payload binding: if `boundPayload \notin {0, offered}`, append REFUSED and record the step;
  - cancel (`cancelAt >= 0` gives REFUSED);
  - grant (`~grantRevoked`, else REFUSED);
  - `readOk[w] /\ localOk` (else REFUSED);
  - otherwise append PROPOSED, AUTHORIZED, DISPATCHED; `effState' = "dispatched"`, `dispWorkerEpoch' = <<w, myEpoch[w]>>`, `sendDeadline' = now + SendTimeout`, `firstDispatch` set if unset;
  - `localDeadline'[w] = now + SendTimeout`, or `now + 1 + SendTimeout` under BROKEN = "stopwatch_after_dispatch";
  - under BROKEN = "grant_check_outside_txn", the grant is read in `ReadPremise` instead.
- **`Send(w)`**: `pc[w] = "sending" /\ now < localDeadline[w]` (under PAUSE, a resumed worker skips this bound). Adds a request to `wire` with `processBy = now + SendTimeout + SettleMargin`, or `MaxClock` under SERVER_SLOW. Appends to `sendLog`.
- **`Process(m)`**: target side, any time `<= m.processBy`.
  - Tier 1 with `keyLive` and a prior application of this key: return "replayed", no new application.
  - Otherwise add to `ledger`; at tier 1 set `keyLive' = TRUE`.
  - Tier 1 with key reused under a different payload: return an error, no application.
- **`Ack(w)`**: the worker receives the response for its request.
- **`TCommit(w)`**: `Fence(w) /\ effState = "dispatched" /\ dispWorkerEpoch = <<w, myEpoch[w]>>`. Append COMMITTED, `effState' = "committed"`, `stepRow'["effect"] = TRUE`. Under BROKEN = "commit_without_checkpoint" this splits into `TCommitEffect` and `TCommitStep`, with Crash allowed between them.
- **`LateAck(w)`**: `~Fence(w)` after `Ack`.
  - If `effState = "dispatched" /\ dispWorkerEpoch = <<w, myEpoch[w]>>`: COMMITTED without a step row.
  - Else: `lateResults' = lateResults + 1` and append LATE_RESULT. Under BROKEN = "late_ack_dropped" it does nothing.
- **`BeginRecovery(w)`**: `Fence(w) /\ effState = "dispatched" /\ dispWorkerEpoch # <<w, myEpoch[w]>> /\ now > sendDeadline + SettleMargin`. BROKEN = "recover_before_deadline" drops the deadline conjunct. Computes `effTier` from `Tier`, `Queryable` and `now - firstDispatch > DedupAge`.
- **`Query(w)`**: `found'[w] = (ledger contains this effect)`.
- **`TResolve(w)`**: `Fence(w)`. Re-checks `~grantRevoked`, `handRefund = 0`, `localOk`, then the `_recover_one` table from 5.7. A resend sets `dispWorkerEpoch`, `sendDeadline` and `localDeadline` as TDispatch does, then goes through `Send`, `Ack`, `TCommit` with `via` recorded. BROKEN = "naive_recovery" skips the re-check, which is gate.py before Finding 4.
- **World events**, each at most once and enabled at any time:
  - `Revoke`: sets `grantRevoked` and `revokeAt = now`; `revokeReturned` gets the effect if `effState = "dispatched"`;
  - `HandRefundFull`, `HandRefundPartial`: `handRefund` becomes 20 or 10, and the ledger gains a hand entry that is not counted as ours;
  - `Cancel`;
  - `PruneKeys`: `keyLive' = FALSE`, only past DedupAge;
  - `Redecide`: the next offer carries payload 30.

**MODE = "temporal_idem".** The server schedules attempts.
- `TemporalAttempt(w)` is enabled when no attempt is live, or the live attempt's worker crashed, or `now >= attemptStart + SendTimeout` (the start-to-close timeout). There is no fence and no premise or grant check.
- The key is `<<runId, "refund">>`. `Redecide` models a reset, so the run id changes, the key changes, and the payload is 30.
- The activity sends with its key. Completion is recorded if its worker is up and within the timeout; otherwise the server retries.

**MODE = "temporal_precheck".** Same as above, and each attempt first does non-atomic reads:
- a lookup by `<<workflowId, "refund">>` (Queryable only);
- `~grantRevoked`;
- eligibility `handRefund + 20 <= 100` (true for full and partial hand refunds);
- `payload = approvedAmount`.

Then it sends with the stable key. The reads and the send are separate steps, so Revoke, HandRefund and a slow Process can interleave.

### 10.4 Invariants as TLA+ definitions (identifiers exactly as in 2.1)

```
NoRerunAfterComplete    == plainStartsAfterRow = 0
StepResultUnique        == \* by construction: stepRow assigned TRUE at most once; check via a history counter rowWrites[s] <= 1
FencedWrites            == \A i \in DOMAIN writeLog : writeLog[i].fenced \/ writeLog[i].kind = "late_commit_cas"
LeaseMutex              == Cardinality({w \in Workers : up[w] /\ Fence(w)}) <= 1
TakeoverOnlyAfterExpiry == \A i \in DOMAIN claimLog : claimLog[i].prevStatus = "running" => claimLog[i].leaseExp <= claimLog[i].at
AtMostOneCommit         == Len(SelectSeq(journal, LAMBDA e: e.kind = "COMMITTED")) <= 1
EffectAtMostOnceTier12  == (Tier \in {1,2} /\ ~(Tier = 1 /\ ~Queryable /\ keysPruned)) => OurApplications(ledger) <= 1
Tier3NeverResends       == (Tier = 3 \/ (Tier = 1 /\ ~Queryable /\ keysPruned)) => Len(sendLog) <= 1
NoOverlappingSends      == \A i \in 2..Len(sendLog) : sendLog[i].prevSendSettled
CommittedImpliesApplied == effState = "committed" => OurApplications(ledger) >= 1
AmbiguousOnlyWhenUnknowable == effState = "ambiguous" => (EffTier = 3 \/ (Tier = 1 /\ ~Queryable /\ lastRecheckFailed))
EffectCheckpointAtomic  == (effState = "committed" /\ ~stepRow["effect"]) => (\E w : pc[w] = "tcommit") \/ ~CurrentDispatcherLive
SendRequiresLiveClaim   == \A i \in DOMAIN sendLog : sendLog[i].liveClaim
NoSendUnderRevokedGrant == \A i \in DOMAIN sendLog : sendLog[i].grantOk
RevokeLinearizable      == \A i \in DOMAIN sendLog : sendLog[i].afterRevoke => sendLog[i].dispatchInRevokeReturned
NoSendOnStalePremise    == \A i \in DOMAIN sendLog : sendLog[i].premiseOk
RecoveryRechecks        == \A i \in DOMAIN sendLog : sendLog[i].resend => sendLog[i].recheckOk
PayloadBound            == \A i \in DOMAIN sendLog : sendLog[i].payload = FirstBoundPayload
NoSendAfterCancel       == \A i \in DOMAIN sendLog : ~sendLog[i].afterCancel
LateResultPreserved     == lateResults = acksAfterResolution
ReceiptChainLinear      == \* journal is a sequence by construction; check no two COMMITTED, and DISPATCHED count <= resolutions + 1
Termination             == <>(wfStatus \in {"completed","stuck","cancelled"})           \* PAUSE = FALSE, WF on Tick, Claim, Restart, Process, recovery actions
EffectResolved          == (effState = "dispatched") ~> (effState \in {"committed","ambiguous","proposed"})
```

`sendLog` fields are computed at the atomic step that authorized the send, and at the send itself for `liveClaim` and `prevSendSettled`.

### 10.5 Signals.tla

- **Variables:** `now`, `status \in {"running","sleeping","pending"}`, `availableAt \in 0..MaxClock \cup {Inf}`, `mailbox` (set of signal ids), `consumed` (function id -> seq), `until`, `pcS \in {"check","release","done"}`, `sent`.
- **`Suspend`** is one atomic action: check the mailbox, consume if non-empty, else set `status = "sleeping"` and `availableAt = until`. BROKEN = "wake_only_if_sleeping" splits it into `SuspendCheck` then `SuspendRelease`, and makes `SendSignal` wake only a sleeping workflow.
- **`SendSignal`**: adds to `mailbox`; `availableAt' = now`; status becomes pending if sleeping. Under the broken variant it wakes only if already sleeping.
- **`Claim`** is enabled when `availableAt <= now`. **`TimerFire`** records the step only when `now >= until`.
- **Invariants:** NoLostWakeup, SignalExactlyOnceConsumed, TimerNotEarly, as in 2.1.
- **Constants:** `MaxClock = 6`, two signals, one wait with `until \in {3, Inf}`.

### 10.6 Expected TLC outcome (the prediction; `results/runtime_tlc.md` must show the actual)

Key: "hold" = no counterexample; "V" = violated, with its shortest trace printed; "V@t2" = violated at tier 2 only.

| invariant | interlock | temporal_idem | temporal_precheck |
|---|---|---|---|
| NoRerunAfterComplete | hold | hold | hold |
| AtMostOneCommit | hold | hold | hold |
| EffectAtMostOnceTier12 | hold | V@t2, V after prune | V@t2 (retry overlaps a slow request) |
| Tier3NeverResends | hold | V | V |
| NoOverlappingSends | hold | V | V |
| SendRequiresLiveClaim | hold | V | V |
| NoSendUnderRevokedGrant | hold | V | V (revoke between check and send) |
| RevokeLinearizable | hold | V | V |
| NoSendOnStalePremise | hold | V | V (hand refund passes eligibility) |
| RecoveryRechecks | hold | V | V (re-checks eligibility, not decided premises) |
| PayloadBound | hold | V (reset changes key and payload) | hold (amount compared to approval) |
| NoSendAfterCancel | hold | V | V (no heartbeat, so cancel never reaches the activity) |
| CommittedImpliesApplied | hold | hold | hold |
| EffectCheckpointAtomic | hold | V | V |
| LateResultPreserved | hold | n/a | n/a |
| Termination, EffectResolved | hold | hold | hold |

With PAUSE = TRUE, EffectAtMostOnceTier12 is V@t2 in all three modes: a conceded equality. With SERVER_SLOW = TRUE, EffectAtMostOnceTier12 is V@t2 in all three modes, and `interlock` also records a LATE_RESULT.

Every broken config must produce a counterexample on the named invariant. If one does not, the model is wrong and gets fixed before any results are published.

| broken config | invariant it must violate |
|---|---|
| NaiveRecovery | RecoveryRechecks, NoSendOnStalePremise, NoSendUnderRevokedGrant |
| NoFencing | SendRequiresLiveClaim, FencedWrites, EffectAtMostOnceTier12 |
| GrantCheckOutsideTxn | RevokeLinearizable, NoSendUnderRevokedGrant |
| CommitWithoutCheckpoint | EffectCheckpointAtomic |
| RecoverBeforeDeadline | NoOverlappingSends, EffectAtMostOnceTier12 at tier 2 |
| StopwatchAfterDispatch | NoOverlappingSends |
| LateAckDropped | LateResultPreserved |
| WakeOnlyIfSleeping (Signals) | NoLostWakeup |

**Modeler milestones:**
- **M0:** `run_tlc.sh` with a pinned jar.
- **M1:** `Signals.tla` with its broken variant.
- **M2:** `Runtime.tla` in interlock mode, tiers 1 to 3, all broken variants rejected.
- **M3:** the two temporal modes, and the PAUSE and SERVER_SLOW toggles.
- **M4:** `runtime_tlc.py` and the results table.

Report state counts, diameter and TLC version. An optional follow-on is an Apalache inductive invariant for AtMostOneCommit, FencedWrites and PayloadBound.

---

## 11. The Prove harness

`experiments/runtime_prove.py` runs every scenario against three systems on the same laptop, with real processes, and writes `results/runtime_prove.md` and `results/runtime_prove.json`. Raw per-run artifacts go to `runtime/.data/prove/runs/` (gitignored). Up to 20 failing runs per cell are copied into `results/runtime_prove_failures/`. Nothing on a live path is mocked. Anything emulated is labeled EMULATED with its mechanism, in code and in results.

### 11.1 The three systems

All three run the same case:
- payment `pay_881` of 10000 cents;
- approved request `case-4471` for one 2000-cent refund;
- a decision from the model, an approval, the refund, a one-hour-scale sleep (shortened per scenario and labeled), done.

**`runtime`.** `experiments/runtime_flows.py::refund` on `interlock_runtime`, with 3 worker subprocesses (`lease_ttl=5`, `poll=0.5`, `send_timeout=3`, `settle_margin=5` on the local target unless a scenario says otherwise). Grant from `rt.approve`. Premises: `refunded_by_others` from the target.

**`temporal` (a), Temporal alone with its recommended idempotency key.** temporalio 1.32 dev server via `WorkflowEnvironment.start_local`, with `--db-filename` under `runtime/.data/temporal.db` so a server restart keeps state (verify that 1.32 accepts the argument; if not, run the downloaded `temporal server start-dev --db-filename` binary directly). Worker subprocesses connect to it. The workflow:
- a decision activity calls the model;
- then `workflow.wait_condition` on an `approve` signal carrying `{amount, grant_id}` (the HITL cookbook shape);
- then the refund activity with `start_to_close_timeout = 3s` (matching `send_timeout`) and the default `RetryPolicy`;
- then `workflow.sleep`.

The activity:

```python
@activity.defn
def refund(req):
    info = activity.info()
    key = f"{info.workflow_run_id}-{info.activity_id}"          # Temporal's recommended key
    return http_target.post_refund(req["payment"], req["amount"], idempotency_key=key)
```

**`temporal_check` (b), the same workflow with the check a competent engineer writes.** Temporal's docs tell you to "check whether my operation already happened". Keying on `workflow_id` (the business id, stable across retries and reset) is the careful choice.

```python
@activity.defn
def refund(req):
    info = activity.info()
    key = f"{info.workflow_id}-refund"                           # stable across retry and reset
    if http_target.tier_has_lookup:
        existing = http_target.find_refund(key)                  # "did my operation already happen?"
        if existing:
            return existing
    g = grants_db.fetch(req["grant_id"])                         # plain SELECT from the same ilr.grants table
    if g["revoked_at"] or (g["expires_at"] and g["expires_at"] <= now()) or req["amount"] > g["max_cents"]:
        raise ApplicationError("not authorized", non_retryable=True)
    if req["amount"] != req["approved_amount"]:
        raise ApplicationError("amount differs from approval", non_retryable=True)
    p = http_target.get_payment(req["payment"])
    if p["refunded_total"] + req["amount"] > p["paid"]:
        raise ApplicationError("not eligible", non_retryable=True)
    return http_target.post_refund(req["payment"], req["amount"], idempotency_key=key)
```

`results/runtime_prove.md` quotes both activity bodies verbatim so a reader can judge whether (b) is fair. If a reviewer shows a better idiomatic check, add it as a fourth column rather than editing (b).

**Crash mechanics.** Every crash is a real OS signal to a worker subprocess (instrumented SIGKILL via 2.2, or an external SIGKILL at a random time). The existing `experiments/temporal_live.py` raises in-process exceptions, and that pattern must not be reused here.

### 11.2 Shared infrastructure

**`experiments/runtime_target.py`.** An HTTP server with a SQLite ledger, one process per run.
- Tier set at start. Configurable service delay per request.
- Endpoints:
  - `POST /refunds` with `{payment, amount, metadata}` and an optional `Idempotency-Key`. Tier 1 dedupes on it with Stripe semantics: the same params return the stored refund with `replayed: true`; different params return 400 `key_reused`.
  - `GET /refunds?payment=&key=`: tiers 1 and 2 only; tier 3 returns 404.
  - `GET /payments/{id}`: `{paid, refunded_total}`.
  - `POST /admin/hand_refund {amount}`.
  - `POST /admin/prune_keys`: EMULATED key expiry.
  - `POST /admin/delay {seconds}`.
  - `GET /admin/log`.
- The access log records every request with arrival time, processing start and end, key, payload, and headers `X-ILR-Worker` and `X-ILR-Epoch` (sent by both systems' adapters).
- The ledger is the ground truth for correctness.

**`experiments/runtime_fault_proxy.py`.** A stdlib TCP proxy, real sockets, controlled by a small HTTP API. Modes:
- `pass`;
- `delay_response s`;
- `drop_response` (forward the request, discard the response, hold the socket until the client closes);
- `reset`;
- `blackhole` (accept and never forward).

One proxy sits between workers and the target. Another sits between workers and Postgres, or the Temporal server, for partition scenarios. Toxiproxy is not required.

**`experiments/runtime_model_stub.py`.** Returns scripted amounts per case: 2000 on the first call, 3000 afterwards when a scenario enables re-decision. Labeled EMULATED model variance. One live-Haiku row (S05L) shows that a real `claude-haiku-4-5-20251001` decision is recorded once across a SIGKILL. Its correctness does not depend on the model's answer.

### 11.3 Scenarios

Every scenario runs at tiers 1, 2 and 3 unless listed otherwise. "Down" means every worker subprocess of that system is SIGKILLed; "restart" means fresh worker subprocesses start.

The oracle is evaluated from the target ledger and access log only. Predicted outcomes are hypotheses, not results.

| id | scenario | fault injection | oracle (correct when) | predicted: runtime / (a) / (b) |
|---|---|---|---|---|
| S01 | crash after commit | kill at `effect_after_send`; restart | our applications = 1 (tier 3: <= 1, and the outcome is surfaced as unknown) | t1 $20 COMMITTED_BY_RETRY, t2 $20 COMMITTED_ON_QUERY, t3 $20 AMBIGUOUS / t1 $20, t2 $40, t3 $40 / t1 $20, t2 $20, t3 $40 |
| S02 | hand refund during the outage | kill at `effect_after_dispatch` (nothing sent); `hand_refund 2000` while down; restart | total refunded = $20 (hand only); agent refund refused and surfaced | t1,t2 REFUSED:stale_premise_at_recovery $20; t3 AMBIGUOUS $20 / $40 / $40 (eligibility 20+20 <= 100 passes) |
| S03 | approval revoked during the outage | kill at `effect_after_dispatch`; `rt.revoke` (for (a),(b): the same `revoked_at` update) while down; restart | total = $0 | t1,t2 REFUSED:lease_at_recovery $0; t3 AMBIGUOUS $0 / $20 / $0 (equal) |
| S04 | key pruned (EMULATED) | tier 1 only, queryable and non-queryable variants. Kill at `effect_after_send`; wait until the database-clock age exceeds `dedup_window - DEDUP_MARGIN` (`dedup_window = 612s`, so the downgrade point is 12s of real age); `POST /admin/prune_keys`; restart. EMULATED: key expiry is an admin call standing in for Stripe's 24h pruning; the runtime's downgrade uses real database-clock age | our applications = 1 | queryable: COMMITTED_ON_QUERY $20 / $40 / $20 (equal). Non-queryable: AMBIGUOUS $20 / $40 / $40 |
| S05 | model re-decides the amount | model stub returns 3000 after the first call. Kill at `effect_after_send`. Runtime: `rt.fork(wf, at_seq=<decide seq>)`. Temporal: `temporal workflow reset` to before the decision activity. Variant S05b: kill at `decide_after_response` with no fork (plain re-call) | total = $20; never $50 | runtime REFUSED:conflicting_payload $20 / $50 (new run id, new key) / $20 (amount != approved; equal). S05b: runtime $20 (grant payload_hash refuses 3000) / $30 at tier 1 if the approval does not bind the amount, measured / $20 |
| S05L | live decision recorded once | live Haiku; kill at `decide_after_response`, restart; then kill at `effect_after_send` | exactly one decide row; discarded LLM calls reported; one refund | recorded / recorded as an activity result / same |
| S06 | partial hand refund | as S02 with `hand_refund 1000` | agent refund refused (decision assumed $0 prior refunds); total = $10 | $10 refused / $30 / $30 (10+20 <= 100 passes) |
| S07 | two workers racing recovery | 3 workers; kill the owner at `effect_after_send`; survivors' poll phases randomized per seed | our applications = 1; LeaseMutex over claim history; exactly one COMMITTED | one recovery / server schedules one retry / same (equal) |
| S08a | late response after claim expiry, inside settle | tiers 1, 2. Target delay 2s; a database-side proxy (for Temporal, a server-side proxy) blackholes the sender from t=0.5s to t=12s, so its lease expires at ~5s and a successor claims; the successor waits until `send_deadline + settle_margin`; the original's `T_commit` fails the fence at t=12s | one application; late response preserved | COMMITTED_ON_QUERY plus LATE_RESULT / t1 $20, t2 $40 / $20 (lookup finds it; equal) |
| S08b | response arrives after timeout, inside settle | tiers 1, 2. Target delay `send_timeout + 2s`: the sender's watchdog exits, and the request finishes processing before `send_deadline + settle_margin` | one application | $20 / t1 $20, t2 $40 / t2 $40 (the retry's lookup runs before processing ends) |
| S08c | response beyond settle (A2 violated) | tiers 1, 2. Target delay `send_timeout + settle_margin + 3s` | recorded as the measured assumption boundary | t2 $40 in all three systems (conceded); runtime receipt keeps evidence |
| S09 | tier-3 effect with no lookup | tier 3. Variant pre: kill at `effect_after_dispatch`. Variant post: kill at `effect_after_send` | at most one application; outcome surfaced | pre: AMBIGUOUS $0 (availability cost counted) / $20 / $20. Post: AMBIGUOUS $20 / $40 / $40 |
| S10 | durable timer across a crash | workflow sleeps 20s (shortened from 3600, labeled) before the effect. t=5 down; t=8 `runtime_pg.py restart-immediate` (runtime) or SIGKILL and restart the dev server process with the same db file (Temporal); t=25 restart workers | timer step recorded once, at database time >= due; one application; lateness reported | equal; runtime lateness <= poll after workers return |
| S11 | signal during an outage | workflow waiting on `approve`; down at t=2; approve at t=4; restart at t=6. Variant S11r: 200 iterations with no crash, the approve sent at a random offset within +/-50ms of the suspend commit (runtime kill-free race; for Temporal the same timing) | consumed exactly once; the workflow proceeds; no wait exceeds its timeout (NoLostWakeup) | equal |
| S12 | revoke racing dispatch | 1000 iterations per tier; revoke fired at a random offset in [-20ms, +20ms] around the dispatch | count sends processed after the revoke returned whose effect was not in the revoke's returned list (the runtime) or at all (Temporal) | 0 / many / > 0 (measured) |
| S13 | zombie by SIGSTOP | SIGSTOP the sender at `effect_after_dispatch` (before its bytes are sent) for 2s (shorter than `send_timeout`) and for `send_timeout + settle_margin + 3s` (longer) | one application | short: $20 / $20 / $20. Long: tier 2 $40 in all three (A1, conceded) |
| S14 | versioning | 10 v1 workflows sleeping; start v2-only workers (none may claim); start a v1 worker (drains); then a v1 code change without a patch | VersionPinned; NonDeterminismLoud (stuck, nothing run) | equal (Temporal: Worker Versioning pinned plus a NonDeterminismError task retry) |

**Stripe test mode (live).** S01, S02 and S03 at tier 1 against `interlock.targets.stripe_api.StripeRefunds` for the runtime, and the same Stripe calls in the two Temporal activities (lookup through `GET /refunds` filtered by metadata). 3 seeds per system, so 27 PaymentIntents. Every PaymentIntent id is listed. Keys come from `STRIPE_SECRET_KEY` or `stripe config --list` test mode only.

### 11.4 Sweep size

- **Scenario cells.** A cell is (scenario, system, tier, variant). Each cell runs 100 seeds, except:
  - S08a/b/c, S10 and S13 run 20 seeds (long wall time);
  - S05 runs 50 seeds;
  - S12 is 1000 iterations and S11r is 200, each counted as one cell;
  - Stripe and live-Haiku cells run 3 seeds.
- **Crash point per seed.** Chosen by seeded RNG: with probability 0.5, one instrumented kill point uniformly from those the scenario allows; otherwise an external SIGKILL at a uniform random time in [0, p99 of that cell's no-fault run time]. A seed that crashes outside the scenario's intended window still counts, and its actual crash point is recorded.
- **Mixed sweep.** 2,000 runs per system, 6,000 total. Each run draws:
  - a random tier;
  - 0 to 2 crashes (instrumented or external);
  - 0 to 2 world events from {hand refund full, hand refund partial, revoke, prune_keys EMULATED, cancel, re-approve with a new grant}, each placed before the decision, during the outage, or after recovery;
  - a duplicate start of the same case (0 or 1).
- **Oracle for the mixed sweep.** Total refunded equals the amount the invariants allow given the event order: $20 if the refund may land, the hand amount if a premise changed before the send, $0 if revoked or cancelled before the send. A tier-3 unknown is allowed only when a crash hit the ambiguous window.
- **Concurrency and seeds.** Runs execute up to 8 in parallel, each with its own target process, its own workflow ids, and a Temporal task queue per run. The seed list and wall time are recorded.

### 11.5 Recorded per run (JSON, one file per run) and per cell (aggregated)

Per run:
- **Identity:** `system`, `scenario`, `variant`, `tier`, `seed`, `run_id`.
- **Versions:** git commit and dirty flag; Postgres, temporalio and Python versions.
- **Faults:**
  - `crash_plan` (instrumented point name, or external offset in ms);
  - `signals_sent` (pid, signal, monotonic and database time);
  - world events with timestamps;
  - proxy mode changes;
  - the `emulated` list (mechanism strings).
- **Ground truth:** target ledger rows (our applications, hand entries, amounts); access log (every request, its processing interval, sender worker and epoch).
- **Outcome:** oracle expected, observed, `correct` (bool); `duplicate_applications`; `wrong_amount`; `sent_under_revoked_grant`; `sent_on_changed_premise`; `blocked_never_sent` (tier-3 availability cost); `human_queue_items` (AMBIGUOUS, and refusals needing re-approval).
- **Runtime artifacts:**
  - `rt.describe(wf)`;
  - `rt.receipt(effect_id, key=<run HMAC key>)` bundle and `verify()` output;
  - `effects.sends`, `late_result`;
  - claim history (epoch, owner, database time);
  - discarded LLM calls;
  - failing `INVARIANTS` entries.
- **Temporal artifacts:** full workflow history JSON (`fetch_history`); activity attempt log from the worker (attempt, key, check results).
- **Timings:**
  - decision to effect committed (end to end);
  - dispatch to target arrival;
  - kill to next step recorded (resume latency);
  - timer due to fired (lateness);
  - signal commit to wait step recorded (wake latency).
- **History export:** the history in elle-cli list-append format (key = effect_id, value = application index) plus claim acquire and release pairs. When elle-cli is installed, the run is checked and `:valid? unknown` or an exception counts as failure. This is optional; the harness's own oracle is primary.

Per cell: n, correct count and rate with a 95% Wilson interval, and the sum of each outcome counter. Also latency p50 and p99 with counts, the can-prove mean, and the ids of failing runs.

### 11.6 Metrics

**1. Correctness.** Correct rate per cell. Duplicate applications, wrong amounts, sends under a revoked grant, and sends on changed premises, all per 1,000 runs. Availability cost is `blocked_never_sent` per 1,000 runs, reported in the same table so the tier-3 trade is visible.

**Verdict rule** (mechanical, per scenario and tier, against (a) and (b) separately):
- `better` when the runtime's correct-rate Wilson interval lies entirely above the baseline's;
- `worse` when it lies entirely below;
- otherwise `equal`.

A `better` on duplicates with a higher `blocked_never_sent` is printed as `better (duplicates), worse (availability)`.

**2. Can prove what happened.** `experiments/runtime_audit.py` reads only the system's own records (runtime: the receipt bundle; Temporal: workflow history plus the worker's attempt log). It never reads the target ledger. It answers five questions, and each answer is then compared with ground truth.

| question | runtime source | Temporal source |
|---|---|---|
| P1 did the effect happen (yes, no, unknown) | `verify().happened` | activity completed or failed in history |
| P2 at most once | `happened_once` | not derivable when a retry followed a timeout: answer unknown |
| P3 under which authority, and was it live at the send | DISPATCHED `checks.lease` and `authorized_when_fired` | not recorded: unknown |
| P4 were the decision's premises checked immediately before every send | `assumptions_held` and `rechecked` | not recorded: unknown |
| P5 tamper evident (the auditor flips one byte in a copy and re-verifies) | `tamper_evident` and signature | history is not signed: no |

Scoring:
- a correct definite answer scores 1;
- "unknown" scores 1 only where truth is unknowable by design (tier 3 in the ambiguous window) and 0 otherwise;
- a wrong definite answer scores 0 and is also counted in `false_claims`, reported separately because a confident wrong receipt is worse than no receipt.

Report the mean score out of 5 per cell, plus `false_claims` per 1,000 runs.

**3. Latency.** Measured in no-fault runs (n = 1,000 per system at tier 1 on the local target with a fixed 20ms service delay, and 3 runs on Stripe).

Report p50 and p99 of:
- end to end (decision to COMMITTED recorded);
- per-effect overhead (dispatch commit to commit recorded, minus target service time);
- plain step record latency.

From fault runs: resume latency after SIGKILL, timer lateness, signal wake latency. All values are labeled "one laptop; Temporal is the dev server with SQLite, not a production deployment".

**4. Throughput.** `experiments/runtime_bench.py`:
- closed loop, 60s runs, 3 repetitions;
- workers in {1, 4, 8};
- workflow = one plain step, one decide against the model stub with 50ms EMULATED latency, one tier-1 effect on the local target at 20ms.

Report completed workflows/s, effects/s, p50/p99 end to end, Postgres CPU, and the worst heartbeat gap observed (it bounds safe `lease_ttl`). Temporal runs the same shape on the dev server. The Temporal Cloud cost reference ($100/mo Essentials, 1M actions; fetched 2026-09-13) goes next to it as context, not as a measured number.

### 11.7 Output format

`results/runtime_prove.md` contains, in this order:

1. A header with versions, seeds, wall time, and every EMULATED mechanism.
2. The main table. Rows are scenario x tier x variant; columns are runtime / (a) / (b), each showing correct % (n), duplicates, blocked-never-sent and can-prove score, followed by the verdict vs (a) and vs (b).
3. The Stripe live table with PaymentIntent ids.
4. The latency and throughput tables.
5. The TLC cross-reference: for each scenario, the invariant in `results/runtime_tlc.md` that predicts it, and whether prediction and measurement agree. Any disagreement is a finding to diagnose, not to hide.
6. The two Temporal activity bodies, quoted verbatim.
7. The concessions: A1, A2, A3, tier-3 availability, and scale.

`results/runtime_prove.json` holds the aggregates.

---

## 12. Order of work across builders

| step | runtime builder | TLA+ modeler | harness |
|---|---|---|---|
| 1 | R0, R1 (first gate) | M0, M1 | runtime_target.py, runtime_fault_proxy.py (needs no runtime code) |
| 2 | R2, R3 | M2 | runtime_temporal_baselines.py for systems (a) and (b), S01 to S03 at all tiers |
| 3 | R4 (parity test must pass) | M3 | runtime flows and S01 to S09 for the runtime |
| 4 | R5, R6, R7 | M4 | S10 to S14, the sweeps, Stripe live, audit, bench |
| 5 | fix what the harness and TLC find; every fix gets a test that failed before it | reconcile any mismatch with measured results | publish results/runtime_prove.md |

No results are published until the parity test, the first gate, every broken TLC config, and the whole sweep have run. If a predicted row comes out the other way, the table shows the measured value, and this document's prediction is revised with the reason, the way Finding 4 was.

---

## 13. Build notes (runtime builder, 2026-09-13)

What was built against sections 3 to 9, how to run it, and every place the code differs from the text above.

### 13.1 Running it

```
brew install postgresql@17                         # the Docker daemon is not required
python3 experiments/runtime_pg.py start            # runtime/.data/pg, port 55432, fsync=on, synchronous_commit=on
export ILR_DSN=postgresql://localhost:55432/ilr
uv run --no-project --with 'psycopg[binary]' python -m unittest tests.test_runtime tests.test_runtime_sql_races tests.test_runtime_gate_parity -v
uv run --no-project --with 'psycopg[binary]' --with hypothesis python -m unittest tests.test_runtime_stateful -v
uv run --no-project --with 'psycopg[binary]' --with anthropic python experiments/runtime_live_agent.py --approve-as <name> --crash effect_after_send
```

The test suites reset the `ilr` schema; do not run them against a database holding work you want to keep, and do not run two suites at once.

### 13.2 Files

| file | what it is |
|---|---|
| `runtime/interlock_runtime/` | the package: `schema.sql`, `db.py`, `context.py`, `effects.py`, `worker.py`, `runtime.py`, `receipts.py`, `invariants.py`, `killpoints.py` |
| `experiments/runtime_pg.py` | local Postgres 17: start, stop, restart-immediate (a real crash), reset, status |
| `experiments/runtime_target.py` | the local HTTP payment target (tiers 1, 2, 3; SQLite ledger; access log) and its `LocalRefunds` client |
| `experiments/runtime_flows.py` | the refund workflows, small feature workflows, the Stripe adapter (R7), the Claude model call, shared test setup |
| `experiments/runtime_live_agent.py` | the live example: Claude decides, a person approves, the gated refund lands on a real Stripe test PaymentIntent |
| `tests/test_runtime.py` | first gate, steps, retries, timers across a Postgres crash, signals, cancel, versioning, decisions, children, continue-as-new, effects |
| `tests/test_runtime_sql_races.py` | revoke, cancel and signal races held open on a second connection, forked chains, a second COMMITTED |
| `tests/test_runtime_gate_parity.py` | the R4 differential against `interlock.Gate` for every refund fault at tiers 1 to 3 |
| `tests/test_runtime_stateful.py` | the R6 Hypothesis state machine |

### 13.3 Differences from sections 4 to 6

1. **Claim history table.** `ilr.claims (workflow_id, epoch, owner, version, claimed_at, prev_status, prev_lease_expires_at)` is written by the claim statement itself. LeaseMutex, TakeoverOnlyAfterExpiry, FencedWrites and SendRequiresLiveClaim are checked over it. Section 4 did not list a table for the claim history section 2.1 relies on.
2. **DISPATCHED names its sender.** The entry carries `by: {workflow_id, epoch}` (plus `compensation: true` for compensation sends). `verify()` ignores the key; SendRequiresLiveClaim and NoSendAfterCancel read it.
3. **A sleep step records `{"until": ...}`**, not null, so TimerNotEarly is checkable from the row. `ctx.sleep` still returns None.
4. **Cancelled is delivered once**, at the first frontier call after the cancel is seen, so workflow code can catch it and run compensation. Effects are not interrupted by the raise; `T_dispatch` refuses them with REFUSED:cancelled whenever `cancel_requested_at` is set and the call is not a compensation.
5. **Retry backoff survives an early wake.** A retry's `waiting` holds `until`; a signal that wakes the workflow early re-suspends it until the backoff is due.
6. **A caller offering a different payload for a dispatched effect** first resolves the recorded send by the recovery table, without taking that status, then goes round again and is refused as conflicting_payload.
7. **Stale external premises are re-read.** If more than `premise_max_age` passes between the read and the stopwatch start, the submit path reads again.
8. **Suspend swallowed.** The suspend transaction already released the row, so the `stuck` write is guarded by the unchanged epoch rather than the fence.
9. **Operator flags on the worker CLI.** `--only name@version,...` registers a subset (a v2-only worker). `--allow-code-change` accepts a changed `code_sha256` for an existing (name, version); without it a worker exits 2 as specified. The non-determinism tests need the override, because the hash check otherwise catches the unpatched change at deploy time, before replay can.
10. **Transaction bodies are importable.** `signal_in`, `cancel_in`, `revoke_in` run inside a caller's transaction, so the race tests hold them open on a second connection.
11. **`available_at = 'infinity'`** is loaded as `datetime.max` (psycopg has no infinite datetime).
12. **The local target's premises** are `{payment, eligible, refunded_by_others}`, so the refund faults that change eligibility run against it.
13. **Stripe adapter (R7).** 4xx maps to TargetRejected except 409 (idempotency key in use) and 429, which are not definite failures.
14. **The model call** uses the official `anthropic` SDK, imported only by the live path.
15. **Child and successor ids.** A child defaults to `<parent>/<seq>`; continue-as-new names the successor `<id>#<n>`.

### 13.4 Findings while building

- **Kill to self is not synchronous.** The first parity run failed at tier 2 only: a worker SIGKILLed at `effect_after_dispatch` still sent the refund, and once also committed it, because `os.kill(os.getpid(), SIGKILL)` returned and the thread kept running for a few milliseconds. Tier 1 hid it (the target deduped) and tier 3 hid it (AMBIGUOUS either way). `killpoints.hit` now blocks the calling thread after signalling itself, and the parity test asserts from the target's access log that a worker killed before the send made no request. Any earlier "instrumented SIGKILL" result on macOS that did not check the access log should be treated as unverified.
- **pg_stat_activity is a per-transaction snapshot.** A test that holds a transaction open and polls pg_stat_activity on the same connection never sees the lock wait. The race tests poll from a separate connection.

### 13.5 Live example run

`experiments/runtime_live_agent.py` ran once on 2026-09-13 (`results/runtime_live_agent.md`): a real Stripe test PaymentIntent `pi_3UFMX888KhIqqdFL0cZUF1Zw` for 10000 cents; Claude (`claude-haiku-4-5-20251001`) decided 2000 cents; worker w1 was SIGKILLed at `decide_after_response` (the response was discarded; 2 LLM calls, 1 recorded decision); the workflow suspended durably on `approve`; the approval came through `rt.approve`; worker w2 was SIGKILLed at `effect_after_send`; worker w3 took over after the lease, waited out `send_deadline + settle_margin` (35s + 10s), re-checked grant and premises against Stripe, and resent with the same idempotency key. Result: `COMMITTED_BY_RETRY`, Stripe returned the stored refund (`already_processed`), exactly one refund `re_3UFMX888KhIqqdFL0msPMC2c` for 2000 cents exists, and `verify()` reports valid, happened once, authorized when fired, assumptions held. The approval was given by the builder through `--approve-as`, standing in for a person; the 3600s post-refund sleep was shortened to 5s.

### 13.6 Test results at the time of writing

- `tests.test_runtime` (21), `tests.test_runtime_sql_races` (9), `tests.test_runtime_gate_parity` (12): 42 tests, all pass, in one run of about 120s. The parity suite covers happy_path, crash_before_send, crash_before_ack, duplicate_submit, model_redecides, conflicting_payload, lease_revoked, stale_eligibility, refund_during_outage and lease_revoked_during_outage at tiers 1, 2 and 3, and key_expired at tier 1, with statuses, `verify()` fields, journal summaries and ledgers equal to `interlock.Gate`.
- `tests.test_runtime_stateful`: passes with seed 20260913, 4 examples, 103s: 47 invariant checks, 7 worker processes, 1 SIGKILL, 4 SIGSTOP/SIGCONT, 2 approvals, 2 revokes, 3 hand refunds, 8 workflows, 1 effect committed and 1 refused. Coverage is thin (one send across the run); raise ILR_HYPOTHESIS_EXAMPLES for a real sweep. The first two versions of this test passed vacuously (zero-step examples, then no approvals); the test now fails unless workers ran and an effect was sent.
- Without `ILR_DSN` every runtime test skips cleanly under plain `python3 -m unittest discover -s tests`. That run showed 3 errors in `test_integrations.MandateChecks`, which belongs to the concurrent workflow, not this runtime.

### 13.7 Not built here

The Prove harness beyond the target (`runtime_fault_proxy.py`, `runtime_model_stub.py`, `runtime_temporal_baselines.py`, `runtime_prove.py`, `runtime_audit.py`, `runtime_bench.py`) and the TLA+ model (section 10) belong to the other builders. `LateResultPreserved` has no code check yet (it needs the sender's own response log); `Termination` and `EffectResolved` are liveness and belong to TLC. `rt.recover_orphans` does not re-run local SQL premises, because the original call's list is not stored.
