"""
Receipts to a BigQuery table, one row per journal entry. Stdlib only.

Two ways in, same rows:

    merge()   a MERGE on entry_hash through jobs.query. A row whose entry_hash the table already holds is not
              inserted again, so exporting the same receipt a second time adds no rows (verified live with two
              back-to-back merges, results/export_live.md). Two merges running at the same moment were not tested:
              if exports can overlap, read through DEDUP_VIEW_SQL. Needs DML, so not the BigQuery sandbox.
    stream()  tabledata.insertAll with insertId = <effect id>-<entry hash>. Google documents insertId dedup as best
              effort for about a minute, so the table can hold duplicates. Read through DEDUP_VIEW_SQL, which keeps
              one row per entry_hash.

entry_json keeps each entry byte for byte, so receipts.verify() can re-run on rows read back. AUDIT_QUERIES are the
queries docs/08-compliance-mapping.md shows each role; experiments/export_live.py runs them against the live table.
"""
import json
from ._common import ExportError, event_id, gcloud_token, request_json, rfc3339, states, text, who

API = "https://bigquery.googleapis.com/bigquery/v2"
TABLE = "receipt_entries"

SCHEMA = [  # (name, type, mode, description). No name may be a GoogleSQL reserved keyword (tests/test_export.py).
    ("effect_id", "STRING", "REQUIRED", "The effect this entry belongs to."),
    ("entry_index", "INTEGER", "REQUIRED", "Position in the effect's hash chain, from 0."),
    ("kind", "STRING", "REQUIRED", "PROPOSED, AUTHORIZED, DISPATCHED, COMMITTED, REFUSED or AMBIGUOUS."),
    ("state", "STRING", "REQUIRED", "The effect's state after this entry; its last row carries the final state."),
    ("recorded_at", "TIMESTAMP", "REQUIRED", "When the gate recorded the entry (the gate host's clock)."),
    ("agent", "STRING", "NULLABLE", "Who proposed the effect."),
    ("lease", "STRING", "NULLABLE", "The approval or lease the effect ran under."),
    ("reason", "STRING", "NULLABLE", "Why it was refused or left ambiguous."),
    ("via", "STRING", "NULLABLE", "How a commit was reached after a crash: retry-idempotent, recovery-query, ..."),
    ("entry_hash", "STRING", "REQUIRED", "sha256 of the entry. The dedup key."),
    ("prev_hash", "STRING", "NULLABLE", "Hash of the entry before it; null for the first."),
    ("entry_json", "STRING", "REQUIRED", "The journal entry exactly as recorded, for receipts.verify()."),
]

DEDUP_VIEW_SQL = """SELECT * FROM `{table}`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY entry_hash ORDER BY entry_index) = 1"""

AUDIT_QUERIES = {
    "Finance: what fired this month, under which approval": """SELECT lease, effect_id,
  COALESCE(JSON_VALUE(entry_json, '$.result.refund'), JSON_VALUE(entry_json, '$.found')) AS refund, recorded_at
FROM `{table}`
WHERE kind = 'COMMITTED' AND recorded_at >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH)""",
    "Risk and Compliance: every effect that ended refused or ambiguous, and why": """SELECT effect_id, state, reason, recorded_at
FROM `{table}`
WHERE kind IN ('REFUSED', 'AMBIGUOUS') ORDER BY recorded_at DESC""",
    "Platform Engineering / auditor: rebuild a chain and re-run the verifier": """SELECT entry_json
FROM `{table}`
WHERE effect_id = @effect ORDER BY entry_index""",
}


def rows(bundles):
    """One row per entry, each entry once even if a bundle is passed twice."""
    out = {}
    for b in bundles:
        es = b["entries"]
        agent, lease = who(es) if es else (None, None)
        for i, (e, state) in enumerate(zip(es, states(es) if es else [])):
            out[e["hash"]] = {"effect_id": e["effect_id"], "entry_index": i, "kind": e["kind"], "state": state,
                              "recorded_at": rfc3339(e["ts"]), "agent": agent, "lease": lease,
                              "reason": text(e.get("reason")), "via": e.get("via"), "entry_hash": e["hash"],
                              "prev_hash": e.get("prev"), "entry_json": json.dumps(e)}
    return list(out.values())


def ensure_table(project, dataset, table=TABLE, token=gcloud_token, location="US"):
    """Create the dataset and the table (partitioned by day of recorded_at, clustered by effect_id) if missing."""
    for url, body in ((f"{API}/projects/{project}/datasets",
                       {"datasetReference": {"projectId": project, "datasetId": dataset}, "location": location}),
                      (f"{API}/projects/{project}/datasets/{dataset}/tables",
                       {"tableReference": {"projectId": project, "datasetId": dataset, "tableId": table},
                        "schema": {"fields": [{"name": n, "type": t, "mode": m, "description": d} for n, t, m, d in SCHEMA]},
                        "timePartitioning": {"type": "DAY", "field": "recorded_at"}, "clustering": {"fields": ["effect_id"]}})):
        status, resp = request_json(url, body, token)
        if status not in (200, 409):                     # 409: already exists (an existing table's schema is not checked)
            raise ExportError(f"BigQuery returned {status} creating {url.rsplit('/', 1)[-1]}: {str(resp)[:500]}")


def merge_sql(project, dataset, table=TABLE):
    cols = ",\n    ".join(
        f"TIMESTAMP(JSON_VALUE(r, '$.{n}')) AS {n}" if t == "TIMESTAMP" else
        f"CAST(JSON_VALUE(r, '$.{n}') AS INT64) AS {n}" if t == "INTEGER" else
        f"JSON_VALUE(r, '$.{n}') AS {n}" for n, t, _, _ in SCHEMA)
    return (f"MERGE `{project}.{dataset}.{table}` t\n"
            f"USING (\n  SELECT\n    {cols}\n  FROM UNNEST(JSON_QUERY_ARRAY(@rows)) AS r\n) s\n"
            f"ON t.entry_hash = s.entry_hash\nWHEN NOT MATCHED THEN INSERT ROW")


def query(project, sql, params=None, token=gcloud_token, dry_run=False):
    """Run standard SQL through jobs.query, waiting for the job. Returns the final response."""
    body = {"query": sql, "useLegacySql": False, "timeoutMs": 60000, "dryRun": dry_run}
    if params:
        body["parameterMode"] = "NAMED"
        body["queryParameters"] = [{"name": k, "parameterType": {"type": "STRING"}, "parameterValue": {"value": v}}
                                   for k, v in params.items()]
    status, resp = request_json(f"{API}/projects/{project}/queries", body, token)
    while status == 200 and not dry_run and not resp.get("jobComplete"):
        job = resp["jobReference"]
        status, resp = request_json(f"{API}/projects/{project}/queries/{job['jobId']}?location={job['location']}"
                                    f"&timeoutMs=60000", token=token)
    if status != 200 or resp.get("errors"):
        raise ExportError(f"BigQuery query returned {status}: {str(resp.get('error') or resp.get('errors'))[:1000]}")
    return resp


def merge(bundles, project, dataset, table=TABLE, token=gcloud_token, chunk=500):
    """Insert rows whose entry_hash the table does not hold. Returns how many rows were inserted."""
    all_rows, inserted = rows(bundles), 0
    for start in range(0, len(all_rows), chunk):
        resp = query(project, merge_sql(project, dataset, table), {"rows": json.dumps(all_rows[start:start + chunk])}, token)
        inserted += int(resp.get("numDmlAffectedRows", 0))
    return inserted


def stream(bundles, project, dataset, table=TABLE, token=gcloud_token, chunk=500):
    """insertAll with insertId. Returns how many rows were sent. A 200 with insertErrors is a failure."""
    all_rows = rows(bundles)
    url = f"{API}/projects/{project}/datasets/{dataset}/tables/{table}/insertAll"
    for start in range(0, len(all_rows), chunk):
        batch = [{"insertId": event_id({"effect_id": r["effect_id"], "hash": r["entry_hash"]}), "json": r}
                 for r in all_rows[start:start + chunk]]
        status, resp = request_json(url, {"rows": batch}, token)
        if status != 200 or resp.get("insertErrors"):
            raise ExportError(f"BigQuery insertAll returned {status}: {str(resp.get('insertErrors') or resp)[:1000]}")
    return len(all_rows)


assert event_id({"effect_id": "e", "hash": "h"}) == "e-h"   # stream()'s insertId is the shared event id
