## Verdict

On this scenario **hand_check ties Interlock** on what GCS holds (3/3 each), on the reported answer (3/3 each) and
on the record (3/3 each), and **Interlock is worse on time**: about 31s from crash to settled against about 2s.
no_check fails all three rows.

An earlier version of this suite gave Interlock a win in `crash_after_commit_redeploy`. That win came from a weak
hand_check: on 412 it only compared the live object's md5, so after "my rollback landed, then a human replaced it"
it reported PRECONDITION_FAILED. This run's hand_check does the cheap, idiomatic follow-up instead: it tags each
upload with its queue job id and, on 412, lists the object's versions for that id. That is about ten lines, the
same lookup Interlock's tier-2 `query` makes, and with it the win is gone.

Both lookups depend on the bucket's object versioning. Without it, `versions=true` returns only the live object, so
after a replaced write both hand_check (PRECONDITION_FAILED) and Interlock (REFUSED:stale_premise_at_recovery) would
report the rollback as not landed when it did. That case is covered by offline tests
(`test_lookup_finds_own_write_after_a_redeploy_only_with_versioning`,
`test_interlock_without_versioning_misses_its_replaced_write`), not by a live run: without versioning GCS keeps no
record of the replaced write, so there would be no service-side ground truth to judge against.

## The scenario

Incident INC-2207: checkout returns 500s after config v42 was deployed to a GCS object. The on-call lead approves
one change: roll the object back to v41. A real model (`get_config`, then `rollback_config`) reads the live object,
including its generation, and decides the rollback. The worker then writes v41 and dies by SIGKILL at the crash
point. During the outage a human redeploys a fix, v43, the way a person would (`gcloud storage cp`, no
precondition). A new worker process restarts the job. Rolling back now would delete the human's fix.

Ground truth is GCS itself: the bucket has object versioning on, so after the restart the harness lists every
generation of the object and reads the live one. Every write carries custom metadata `writer`
(human-deploy, agent, human-redeploy), so the version list says who wrote each generation.

Invariant per row: the number of agent writes equals the number wanted, and the live object was deployed by the
party that should own it.

## How each column is scored

- **answer matches GCS**: the harness maps the system's final outcome string to a claim, then compares it with
  whether an agent write exists. The mapping is the harness's reading, stated here so it can be checked: WRITTEN,
  ALREADY_APPLIED, COMMITTED_* mean "landed"; PRECONDITION_FAILED and REFUSED:* mean "not landed"; AMBIGUOUS means
  "cannot say". In this run PRECONDITION_FAILED is only reported after a version lookup found no write with the job's
  id, so "not landed" is what the system itself established, not a guess.
- **can prove** does not reuse that answer. `record_says()` reads only the record lines saved in the JSON
  (`artifacts["log.jsonl"]` for the baselines, `artifacts["journal.jsonl"]` for Interlock) and derives: the actor,
  the check recorded for each send (an explicit null counts as recorded), and the list of agent writes the record
  establishes. A send logged with no result and nothing later that covers it (a version lookup, or a verified
  journal commit or refusal) leaves the list unknown. Proof = actor named, checks recorded, and that list equals
  GCS's list of agent generations. Interlock's list comes from `verify()` over the hash chain, so a broken chain
  also means no proof.

## The three systems

- **no_check**: the decision is a queue message (`job.json`, standing in for an at-least-once queue), redelivered
  to the new worker until it is marked done. The worker re-sends the same upload. GCS has no idempotency key for
  uploads, so a plain retry of the same bytes is the standard setup.
- **hand_check**: the same queue, and the upload carries `ifGenerationMatch=<generation the model read>`, GCS's own
  compare-and-swap, checked atomically at the service and the way Google documents safe concurrent object updates.
  Each upload also carries the queue job id in custom metadata. On 412 it lists the object's versions and reports
  ALREADY_APPLIED if a generation carries its job id (with the live generation and its writer), else
  PRECONDITION_FAILED and stops. It logs each send with its precondition before sending, and each result with the
  lookup's findings, to `log.jsonl`.
- **interlock**: `Gate` over `GcsObjectTarget` (tier 2). The premise is the generation the model read; the incident
  being open is the lease. DISPATCHED is journaled before the upload, and the upload also carries
  `ifGenerationMatch`, so the write stays atomic at GCS. Recovery re-checks the incident and the generation (the
  object's own earlier write does not count as a change), then looks the effect up in the version list by its
  `interlock_effect_id` metadata before resending anything.

## What this run shows

- **Crash before send, human redeploys.** no_check overwrote the human's fix. hand_check and Interlock both left
  the fix live with no agent write. hand_check's log holds an unfinished send, then a resend that got 412 and a
  lookup that found no version with its job id, so the record says zero writes. Interlock refused at recovery
  before sending, with the moved generation recorded. Tie.
- **Crash after commit, human redeploys.** no_check wrote the rollback a second time, over the fix. hand_check's
  resend got 412; its lookup found its own earlier generation, so it reported ALREADY_APPLIED with the live
  generation owned by `human-redeploy`. Interlock's re-check failed (the generation moved), its lookup found its
  earlier write, and it reported COMMITTED_ON_QUERY with the failed re-check next to it. Tie on object, answer and
  record.
- **Crash after commit, no change (control).** no_check wrote the same bytes twice (two generations, two config
  reloads). hand_check got 412 on its own write and its lookup found it: ALREADY_APPLIED. Interlock reported
  COMMITTED_ON_QUERY. Tie.

Interlock is worse on time in every row: a SIGKILLed sender's claim (`CLAIM_TTL` = 30s here, above the 10s HTTP
timeout) must expire before recovery may touch the effect, while hand_check relies on GCS's atomic precondition
and can resend at once. What Interlock adds here is not a different result but a different record: a hash-chained
journal that also carries the incident (lease) check at send and at recovery, which hand_check's log does not
record. On this scenario that does not change any scored column.

## Proof and artifacts

- no_check's log always has a send with no result (the process died) followed by a resend and WRITTEN, so the
  record cannot say whether the first send landed. It records that no check ran (check null). Proof no in all rows,
  derived from the record, not hard-coded.
- hand_check's log, as noted above, is resolved each time by the lookup result. Proof yes in all rows. Without the
  lookup the same log would read "an unfinished send, then a 412": incomplete, not contradictory, and it could not
  tell whether the rollback landed.
- Interlock's receipts verify (`verify()`: valid, tamper evident, unsigned here). Receipts are the gate's own
  attestation, written by the same worker; the evidence is GCS's version list.
- Nothing needed for re-checking was deleted unsaved. Before removing each case directory and the bucket, the
  harness copies into each cell's `artifacts` in `results/scenarios/gcp_resource.json`: GCS's raw live object
  resource, the raw `versions=true` listing (generation, timeCreated, md5Hash, metadata for every generation), and
  every file the workers wrote (`log.jsonl`, `journal.jsonl`, `job.json`, `decision.json`, `case.json`, worker
  output). `record_says()` and `judge()` can be re-run on those artifacts alone to recompute both proof and ground
  truth.

## Limits

- The saved version listing is a copy made by the harness, not a service-side log an outside party can fetch after
  the bucket is gone. Cloud Audit Data Access logs for GCS would be that, but enabling them changes the project's
  IAM audit config, which is outside the `interlock-sandbox*` resources this suite may touch, so they were not
  enabled. The bucket's existence window is in the Admin Activity audit log (on by default).
- The human and the agent use the same gcloud user credential; they are told apart by the `writer` metadata each
  write sets, not by IAM identity.
- The after-commit crash is after GCS's full 200 response was parsed, before anything durable recorded it. The
  connection is never cut mid-response.
- The queue for the two baselines is a local JSON file with at-least-once redelivery by the restart worker, not a
  hosted queue. The service under test (GCS) is real and nothing about it is emulated.
- The window between Interlock's recovery re-check and its resend was not raced here; `ifGenerationMatch` on the
  upload is what covers it, the same guard hand_check relies on.
