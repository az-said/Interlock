-- interlock_runtime schema (docs/07-runtime.md section 4). Idempotent: Runtime(dsn) applies it under an advisory lock.
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

-- Claim history, one row per successful claim, written by the claim statement itself.
-- Not in the section 4 listing; LeaseMutex and TakeoverOnlyAfterExpiry are checked over it.
create table if not exists ilr.claims (
  workflow_id text not null,
  epoch bigint not null,
  owner text not null,
  version text not null,
  claimed_at timestamptz not null,
  prev_status text not null,
  prev_lease_expires_at timestamptz,
  primary key (workflow_id, epoch)
);

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
