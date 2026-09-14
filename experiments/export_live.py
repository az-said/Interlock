"""
Real receipts into real Google Cloud audit tooling, exported twice, then read back with Google's own tools.

    python3 experiments/export_live.py [--project P] [--journal .interlock/backend/journal.db]

Receipts: the Interlock cells of results/e2e_live.json (a real backend run: Stripe test mode, a real model,
Temporal, a SIGKILLed worker), or every effect in a backend journal with --journal.
Each destination gets the same bundles twice. Reads back through `gcloud logging read`, BigQuery jobs.query (the
MERGE and the compliance doc's queries are dry-run first, then run), and the Cloud Trace v1 API (span count per
trace before and after each export). SIEM lines go to files under results/ (no SIEM is running here).
Writes results/export_live.json and results/export_live.md. Auth: `gcloud auth print-access-token`. No keys are
written anywhere.
"""
import argparse, json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import open_journal, receipts
from interlock.export import bigquery, cloud_logging, gcloud_token, otlp, siem
from interlock.export._common import request_json, trace_id

RUN = int(time.time())
DATASET, STREAM_TABLE = "interlock_audit", f"receipt_entries_stream_{RUN}"
LOG_ID = f"{cloud_logging.LOG_ID}-run-{RUN}"     # a fresh log per run: a read-back can only see this run's writes


def load(journal):
    if journal:
        j = open_journal(journal)
        return [receipts.bundle(j, eid) for eid in dict.fromkeys(e["effect_id"] for e in j.entries())]
    cells = json.load(open(os.path.join(ROOT, "results", "e2e_live.json")))["cells"]
    return [dict(c["receipt"]["bundle"], scenario=c["scenario"]) for c in cells if c.get("receipt")]


def sh(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {out.stderr.strip()[-500:]}")
    return out.stdout


def poll(read, done, timeout=150, every=5):
    """Read until done(result) or timeout; returns (result, seconds waited)."""
    start = time.time()
    while True:
        result = read()
        if done(result) or time.time() - start > timeout:
            return result, round(time.time() - start)
        time.sleep(every)


def chains_verify(by_effect):
    """Re-run receipts.verify on what the destination returned."""
    return {eid: receipts.verify({"effect_id": eid, "entries": es})["valid"] for eid, es in by_effect.items()}


def logging_section(bundles, project):
    ids = [b["effect_id"] for b in bundles]
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(RUN)) + "Z"
    sent = [cloud_logging.export(bundles, project, LOG_ID), cloud_logging.export(bundles, project, LOG_ID)]
    want = sum(len(b["entries"]) + 1 for b in bundles)
    filt = (f'logName="projects/{project}/logs/{LOG_ID}" AND '
            f'labels.interlock_effect_id=({" OR ".join(json.dumps(i) for i in ids)})')
    cmd = ["gcloud", "logging", "read", filt, f"--project={project}", "--freshness=1d", "--order=asc",
           "--limit=1000", "--format=json"]
    got, waited = poll(lambda: json.loads(sh(cmd) or "[]"), lambda r: len(r) >= want)
    received = sorted(le["receiveTimestamp"] for le in got)
    by_effect, per_effect = {}, {}
    for le in got:
        eid, kind = le["labels"]["interlock_effect_id"], le["labels"]["interlock_kind"]
        per_effect.setdefault(eid, []).append(kind)
        if kind != "RECEIPT":
            by_effect.setdefault(eid, []).append(le["jsonPayload"])
    for es in by_effect.values():
        es.sort(key=lambda e: e["ts"])
    receipts_read = {le["labels"]["interlock_effect_id"]: le["jsonPayload"]["verification"]
                     for le in got if le["labels"]["interlock_kind"] == "RECEIPT"}
    return {"log_id": LOG_ID, "run_started": started, "receive_timestamps": [received[0], received[-1]] if received else None,
            "all_received_after_run_started": bool(received) and received[0] >= started,
            "sent_per_export": sent, "expected_entries": want, "returned": len(got), "waited_s": waited,
            "distinct_insert_ids": len({le["insertId"] for le in got}), "command": " ".join(cmd[:3]) + f" '{filt}' " + " ".join(cmd[4:]),
            "kinds_by_effect": per_effect, "chain_verifies_from_logging": chains_verify(by_effect),
            "receipt_entries": {k: {f: v.get(f) for f in ("valid", "happened", "happened_once", "authorized_when_fired",
                                                          "assumptions_held")} for k, v in receipts_read.items()},
            "sample": got[:2] if got else []}


def bq_rows(resp):
    """jobs.query rows as dicts."""
    names = [f["name"] for f in resp.get("schema", {}).get("fields", [])]
    return [dict(zip(names, (c["v"] for c in r["f"]))) for r in resp.get("rows", [])]


def bigquery_section(bundles, project):
    ids = ", ".join(json.dumps(b["effect_id"]) for b in bundles)
    want = sum(len(b["entries"]) for b in bundles)
    merge_table = f"{bigquery.TABLE}_run_{RUN}"         # fresh, so the first merge must insert and the second must not
    table = f"{project}.{DATASET}.{merge_table}"
    bigquery.ensure_table(project, DATASET, merge_table)
    sh(["bq", f"--project_id={project}", "update", "--expiration=172800", f"{project}:{DATASET}.{merge_table}"])
    first = bundles[0]["effect_id"]

    def params(name):
        return {"effect": first} if "@effect" in name else None
    audit = {name: sql.format(table=table) for name, sql in bigquery.AUDIT_QUERIES.items()}
    dry = {"merge": bigquery.query(project, bigquery.merge_sql(project, DATASET, merge_table), {"rows": "[]"}, dry_run=True).get("totalBytesProcessed")}
    dry.update({name: bigquery.query(project, sql, params(sql), dry_run=True).get("totalBytesProcessed") for name, sql in audit.items()})

    inserted = [bigquery.merge(bundles, project, DATASET, merge_table), bigquery.merge(bundles, project, DATASET, merge_table)]
    count_sql = (f"SELECT effect_id, COUNT(*) AS rows_, COUNT(DISTINCT entry_hash) AS distinct_hashes, "
                 f"STRING_AGG(kind, ' > ' ORDER BY entry_index) AS chain, ARRAY_REVERSE(ARRAY_AGG(state ORDER BY entry_index))[OFFSET(0)] AS final_state "
                 f"FROM `{table}` WHERE effect_id IN ({ids}) GROUP BY effect_id ORDER BY effect_id")
    merged_rows = bq_rows(bigquery.query(project, count_sql))
    by_effect = {}
    for r in bq_rows(bigquery.query(project, f"SELECT effect_id, entry_json FROM `{table}` WHERE effect_id IN ({ids}) "
                                             f"ORDER BY effect_id, entry_index")):
        by_effect.setdefault(r["effect_id"], []).append(json.loads(r["entry_json"]))

    ran = {}
    for name, sql in audit.items():             # the queries docs/08-compliance-mapping.md shows each role
        rows = bq_rows(bigquery.query(project, sql, params(sql)))
        ran[name] = {"sql": sql, "rows": len(rows), "sample": rows[:3]}
        if "@effect" in sql:
            ran[name]["effect"] = first
            ran[name]["chain_verifies"] = receipts.verify({"effect_id": first, "entries": [json.loads(r["entry_json"]) for r in rows]})["valid"]

    # stream(): a fresh table that expires in two days, so each run shows insertAll's own behavior
    stream_table = f"{project}.{DATASET}.{STREAM_TABLE}"
    bigquery.ensure_table(project, DATASET, STREAM_TABLE)
    sh(["bq", f"--project_id={project}", "update", "--expiration=172800", f"{project}:{DATASET}.{STREAM_TABLE}"])
    time.sleep(10)                      # streaming into a table created seconds ago can be refused or delayed
    sent = [bigquery.stream(bundles, project, DATASET, STREAM_TABLE), bigquery.stream(bundles, project, DATASET, STREAM_TABLE)]
    raw_sql = f"SELECT COUNT(*) AS raw_rows FROM `{stream_table}`"
    view_sql = f"SELECT COUNT(*) AS dedup_rows FROM ({bigquery.DEDUP_VIEW_SQL.format(table=stream_table)})"
    count = lambda sql: int(bq_rows(bigquery.query(project, sql))[0][sql.split(" AS ")[1].split()[0]])
    raw_now, waited = poll(lambda: count(raw_sql), lambda n: n >= want)
    time.sleep(75)                      # past insertId's documented one-minute window
    sent.append(bigquery.stream(bundles, project, DATASET, STREAM_TABLE))
    time.sleep(5)
    return {"table": table, "expected_rows": want, "dry_runs_ok": sorted(dry), "merge_inserted_per_export": inserted,
            "merge_query": bigquery.merge_sql(project, DATASET, merge_table), "count_query": count_sql, "count_rows": merged_rows,
            "rows_for_these_effects": sum(int(r["rows_"]) for r in merged_rows),
            "chain_verifies_from_bigquery": chains_verify(by_effect), "audit_queries": ran,
            "stream_table": stream_table, "stream_sent_per_export": sent, "stream_waited_s": waited,
            "raw_query": raw_sql, "view_query": view_sql, "raw_after_two_back_to_back": raw_now,
            "raw_after_third_export_75s_later": count(raw_sql), "dedup_view_after_third": count(view_sql)}


def trace_section(bundles, project):
    url = f"https://cloudtrace.googleapis.com/v1/projects/{project}/traces/"

    def spans():
        out = {}
        for b in bundles:
            status, body = request_json(url + trace_id(b["effect_id"]), token=gcloud_token,
                                        headers={"x-goog-user-project": project})
            out[b["effect_id"]] = body.get("spans", []) if status == 200 else []
        return out

    counts = lambda s: {eid: len(v) for eid, v in s.items()}
    before = counts(spans())
    steps, sent = [], []
    for n in (1, 2):
        sent.append(otlp.export(bundles, project=project))
        got, waited = poll(spans, lambda s: all(len(s[e]) >= before[e] + n for e in s), timeout=240, every=10)
        steps.append({"after_export": n, "waited_s": waited, "spans_per_trace": counts(got)})
    last = got
    return {"read_url": url + "<traceId>", "sent_per_export": sent, "spans_per_trace_before": before, "steps": steps,
            "span_ids_per_trace": {eid: sorted({s["spanId"] for s in v}) for eid, v in last.items()},
            "span_names": sorted({s.get("name") for v in last.values() for s in v}),
            "labels_sample": {k: v for k, v in (next(iter(last.values()))[0].get("labels", {}) if last and next(iter(last.values())) else {}).items()
                              if k.startswith("interlock.") and k != "interlock.head_hash"},
            "trace_ids": {b["effect_id"]: trace_id(b["effect_id"]) for b in bundles}}


def siem_section(bundles):
    out = {}
    for name, lines in (("jsonl", siem.jsonl_lines(bundles)), ("cef", siem.cef_lines(bundles))):
        path = os.path.join(ROOT, "results", f"export_live_siem.{name}")
        if os.path.exists(path):
            os.remove(path)
        written = [siem.append(path, lines), siem.append(path, lines)]
        with open(path) as f:
            out[name] = {"file": os.path.relpath(path, ROOT), "written_per_export": written, "lines": sum(1 for _ in f)}
    out["cef_sample"] = siem.cef_lines(bundles)[0][1]
    return out


def markdown(r):
    lg, bq, tr, sm = (r.get(k, {}) for k in ("cloud_logging", "bigquery", "cloud_trace", "siem"))
    fail = lambda s: f"**FAILED LIVE**: `{s['error']}`\n" if "error" in s else None
    receipts_ = "\n".join(f"| `{x['effect_id']}` | {x['scenario']} | {' > '.join(x['kinds'])} | {x['verifies_locally']} |"
                          for x in r["receipts"])
    logging_md = fail(lg) or f"""- Log `{lg['log_id']}`, new for this run, so the read-back sees only this run's two exports
- Sent per export: {lg['sent_per_export']} LogEntries ({lg['expected_entries']} expected: one per journal entry plus one RECEIPT entry per effect)
- `gcloud logging read` returned {lg['returned']} entries with {lg['distinct_insert_ids']} distinct insertIds, after {lg['waited_s']}s
- receiveTimestamp of the returned entries: {lg['receive_timestamps'][0] if lg['receive_timestamps'] else None} to {lg['receive_timestamps'][-1] if lg['receive_timestamps'] else None}; the run started {lg['run_started']}; all received after the start: {lg['all_received_after_run_started']}
- Hash chain rebuilt from the returned jsonPayloads verifies: {sum(lg['chain_verifies_from_logging'].values())}/{len(lg['chain_verifies_from_logging'])} effects
- What that shows{'' if lg['all_received_after_run_started'] and lg['returned'] == lg['expected_entries'] else ' (NOT SHOWN: the read-back includes entries from before this run, or the count differs)'}: a query returns each entry once after two exports. Google documents this as query-time dedup on
  insertId + timestamp, with "no guarantees of de-duplication in the export of logs". Sinks were not tested here
  (NOT VERIFIED LIVE): a sink to BigQuery, Pub/Sub or a SIEM may deliver re-exported entries twice.
- Command: `{lg['command']}`
"""
    audit_md = "" if "error" in bq else "\n".join(
        f"- {name}: {q['rows']} rows" + (f"; chain for `{q['effect']}` rebuilt from rows verifies: {q['chain_verifies']}" if "effect" in q else "")
        + f"\n\n```sql\n{q['sql']}\n```" for name, q in bq["audit_queries"].items())
    bigquery_md = fail(bq) or f"""- Table `{bq['table']}`, created for this run with the `receipt_entries` schema (expires in two days), so both merges below are this run's. Dry runs accepted by BigQuery: {', '.join(bq['dry_runs_ok'])}
- `merge()` twice: inserted {bq['merge_inserted_per_export']} rows; the table holds {bq['rows_for_these_effects']} rows for these effects ({bq['expected_rows']} journal entries)
- Chain rebuilt from `entry_json` verifies: {sum(bq['chain_verifies_from_bigquery'].values())}/{len(bq['chain_verifies_from_bigquery'])} effects
- `stream()` into `{bq['stream_table']}`: sent {bq['stream_sent_per_export']} rows (two back to back, a third 75s later); raw rows {bq['raw_after_two_back_to_back']} after the first two, {bq['raw_after_third_export_75s_later']} after the third; through `DEDUP_VIEW_SQL`: {bq['dedup_view_after_third']}
- Concurrent merges were not tested (NOT VERIFIED LIVE).

The compliance doc's queries, run against the table:

{audit_md}
"""
    trace_md = fail(tr) or f"""- Sent per export: {tr['sent_per_export']} spans
- Spans stored per trace before this run: {tr['spans_per_trace_before']}
""" + "\n".join(f"- After export {s['after_export']} ({s['waited_s']}s): {s['spans_per_trace']}" for s in tr["steps"]) + f"""
- Distinct span ids per trace after both exports: {{{', '.join(f"{k}: {len(v)}" for k, v in tr['span_ids_per_trace'].items())}}}
- What that shows: every export stored another copy of the same span (same traceId and spanId). OTLP to Cloud Trace
  is not idempotent. Export each receipt once, or dedupe on traceId + spanId when reading.
"""
    siem_md = fail(sm) or f"""- JSONL: {sm['jsonl']['written_per_export']} lines written per export, {sm['jsonl']['lines']} lines in `{sm['jsonl']['file']}`
- CEF: {sm['cef']['written_per_export']} lines written per export, {sm['cef']['lines']} lines in `{sm['cef']['file']}`
- Local files only. No SIEM was running; ingestion by a real SIEM is NOT VERIFIED LIVE.
"""
    return f"""# Results: Interlock receipts exported to Google Cloud audit tooling

Generated {r['generated']} by `experiments/export_live.py`, project `{r['project']}`. Source: `{r['source']}`.
Every destination got the same {len(r['receipts'])} receipt bundles twice, then was read back with Google's own tools.

| effect | scenario | entries | verifies locally |
|---|---|---|---|
{receipts_}

## Cloud Logging

{logging_md}
## BigQuery

{bigquery_md}
## Cloud Trace (OTLP to telemetry.googleapis.com)

{trace_md}
## SIEM files

{siem_md}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="gen-lang-client-0277439345")
    ap.add_argument("--journal")
    args = ap.parse_args()
    bundles = load(args.journal)
    local = {b["effect_id"]: receipts.verify(b)["valid"] for b in bundles}
    print(f"{len(bundles)} receipts, all verify locally: {all(local.values())}")
    result = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "project": args.project,
              "source": args.journal or "results/e2e_live.json",
              "receipts": [{"effect_id": b["effect_id"], "scenario": b.get("scenario"), "kinds": [e["kind"] for e in b["entries"]],
                            "verifies_locally": local[b["effect_id"]]} for b in bundles]}
    for name, fn in (("cloud_logging", lambda: logging_section(bundles, args.project)),
                     ("bigquery", lambda: bigquery_section(bundles, args.project)),
                     ("cloud_trace", lambda: trace_section(bundles, args.project)),
                     ("siem", lambda: siem_section(bundles))):
        print(f"{name} ...", flush=True)
        try:
            result[name] = fn()
        except Exception as e:           # keep the other destinations' results; the report says what failed
            result[name] = {"error": f"{type(e).__name__}: {e}"}
        print(json.dumps(result[name], default=str)[:400])
    with open(os.path.join(ROOT, "results", "export_live.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)
    with open(os.path.join(ROOT, "results", "export_live.md"), "w") as f:
        f.write(markdown(result))


if __name__ == "__main__":
    main()
