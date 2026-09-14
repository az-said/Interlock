# Results: Interlock receipts exported to Google Cloud audit tooling

Generated 2026-09-13 23:50 UTC by `experiments/export_live.py`, project `gen-lang-client-0277439345`. Source: `results/e2e_live.json`.
Every destination got the same 8 receipt bundles twice, then was read back with Google's own tools.

| effect | scenario | entries | verifies locally |
|---|---|---|---|
| `8f071607fe8d` | crash_after_commit | PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED | True |
| `d61055b11d73` | hand_refund_before_decision | PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED | True |
| `74065bf0aafe` | hand_refund_during_outage | PROPOSED > AUTHORIZED > DISPATCHED > REFUSED | True |
| `feafe9e2d080` | unrelated_refund_during_outage | PROPOSED > AUTHORIZED > DISPATCHED > REFUSED | True |
| `ffa06094439c` | approval_revoked_during_outage | PROPOSED > AUTHORIZED > DISPATCHED > REFUSED | True |
| `974833a0ea4a` | approval_revoked_after_commit | PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED | True |
| `3d085b1c0a0b` | key_pruned_after_24h | PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED | True |
| `6cce6c06a86a` | no_lookup_after_24h | PROPOSED > AUTHORIZED > DISPATCHED > AMBIGUOUS | True |

## Cloud Logging

- Log `interlock-receipts-run-1789343450`, new for this run, so the read-back sees only this run's two exports
- Sent per export: [40, 40] LogEntries (40 expected: one per journal entry plus one RECEIPT entry per effect)
- `gcloud logging read` returned 40 entries with 40 distinct insertIds, after 8s
- receiveTimestamp of the returned entries: 2026-09-13T23:50:51.581429818Z to 2026-09-13T23:50:51.581429818Z; the run started 2026-09-13T23:50:50Z; all received after the start: True
- Hash chain rebuilt from the returned jsonPayloads verifies: 8/8 effects
- What that shows: a query returns each entry once after two exports. Google documents this as query-time dedup on
  insertId + timestamp, with "no guarantees of de-duplication in the export of logs". Sinks were not tested here
  (NOT VERIFIED LIVE): a sink to BigQuery, Pub/Sub or a SIEM may deliver re-exported entries twice.
- Command: `gcloud logging read 'logName="projects/gen-lang-client-0277439345/logs/interlock-receipts-run-1789343450" AND labels.interlock_effect_id=("8f071607fe8d" OR "d61055b11d73" OR "74065bf0aafe" OR "feafe9e2d080" OR "ffa06094439c" OR "974833a0ea4a" OR "3d085b1c0a0b" OR "6cce6c06a86a")' --project=gen-lang-client-0277439345 --freshness=1d --order=asc --limit=1000 --format=json`

## BigQuery

- Table `gen-lang-client-0277439345.interlock_audit.receipt_entries_run_1789343450`, created for this run with the `receipt_entries` schema (expires in two days), so both merges below are this run's. Dry runs accepted by BigQuery: Finance: what fired this month, under which approval, Platform Engineering / auditor: rebuild a chain and re-run the verifier, Risk and Compliance: every effect that ended refused or ambiguous, and why, merge
- `merge()` twice: inserted [32, 0] rows; the table holds 32 rows for these effects (32 journal entries)
- Chain rebuilt from `entry_json` verifies: 8/8 effects
- `stream()` into `gen-lang-client-0277439345.interlock_audit.receipt_entries_stream_1789343450`: sent [32, 32, 32] rows (two back to back, a third 75s later); raw rows 32 after the first two, 64 after the third; through `DEDUP_VIEW_SQL`: 32
- Concurrent merges were not tested (NOT VERIFIED LIVE).

The compliance doc's queries, run against the table:

- Finance: what fired this month, under which approval: 4 rows

```sql
SELECT lease, effect_id,
  COALESCE(JSON_VALUE(entry_json, '$.result.refund'), JSON_VALUE(entry_json, '$.found')) AS refund, recorded_at
FROM `gen-lang-client-0277439345.interlock_audit.receipt_entries_run_1789343450`
WHERE kind = 'COMMITTED' AND recorded_at >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH)
```
- Risk and Compliance: every effect that ended refused or ambiguous, and why: 4 rows

```sql
SELECT effect_id, state, reason, recorded_at
FROM `gen-lang-client-0277439345.interlock_audit.receipt_entries_run_1789343450`
WHERE kind IN ('REFUSED', 'AMBIGUOUS') ORDER BY recorded_at DESC
```
- Platform Engineering / auditor: rebuild a chain and re-run the verifier: 4 rows; chain for `8f071607fe8d` rebuilt from rows verifies: True

```sql
SELECT entry_json
FROM `gen-lang-client-0277439345.interlock_audit.receipt_entries_run_1789343450`
WHERE effect_id = @effect ORDER BY entry_index
```

## Cloud Trace (OTLP to telemetry.googleapis.com)

- Sent per export: [8, 8] spans
- Spans stored per trace before this run: {'8f071607fe8d': 8, 'd61055b11d73': 8, '74065bf0aafe': 8, 'feafe9e2d080': 8, 'ffa06094439c': 8, '974833a0ea4a': 8, '3d085b1c0a0b': 8, '6cce6c06a86a': 8}
- After export 1 (23s): {'8f071607fe8d': 9, 'd61055b11d73': 9, '74065bf0aafe': 9, 'feafe9e2d080': 9, 'ffa06094439c': 9, '974833a0ea4a': 9, '3d085b1c0a0b': 9, '6cce6c06a86a': 9}
- After export 2 (23s): {'8f071607fe8d': 10, 'd61055b11d73': 10, '74065bf0aafe': 10, 'feafe9e2d080': 10, 'ffa06094439c': 10, '974833a0ea4a': 10, '3d085b1c0a0b': 10, '6cce6c06a86a': 10}
- Distinct span ids per trace after both exports: {8f071607fe8d: 1, d61055b11d73: 1, 74065bf0aafe: 1, feafe9e2d080: 1, ffa06094439c: 1, 974833a0ea4a: 1, 3d085b1c0a0b: 1, 6cce6c06a86a: 1}
- What that shows: every export stored another copy of the same span (same traceId and spanId). OTLP to Cloud Trace
  is not idempotent. Export each receipt once, or dedupe on traceId + spanId when reading.

## SIEM files

- JSONL: [32, 0] lines written per export, 32 lines in `results/export_live_siem.jsonl`
- CEF: [32, 0] lines written per export, 32 lines in `results/export_live_siem.cef`
- Local files only. No SIEM was running; ingestion by a real SIEM is NOT VERIFIED LIVE.

