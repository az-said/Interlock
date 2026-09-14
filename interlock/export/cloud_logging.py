"""
Receipts to Google Cloud Logging (entries.write). Stdlib only.

One LogEntry per journal entry, plus one RECEIPT entry per bundle with verify()'s result:

    logName      projects/P/logs/interlock-receipts
    insertId     <effect id>-<entry hash>
    timestamp    the entry's own recorded time. Logging treats entries with the same insertId AND timestamp
                 as duplicates and removes them from a query result. That is all Google promises: "there are no
                 guarantees of de-duplication in the export of logs", so a sink (to BigQuery, Pub/Sub or a SIEM)
                 can deliver a re-exported entry twice. Consumers of a sink dedupe on insertId.
    operation    id = effect id, producer = interlock: one effect's entries group together
    labels       interlock_effect_id, interlock_kind, interlock_agent, interlock_lease, interlock_state
                 (the effect's state after this entry: the last entry carries the final state)
    trace/spanId the ids the OTLP exporter gives this effect, so the log lines open the span
    jsonPayload  the journal entry, unchanged

Entries land in the project's _Default bucket (30 days unless changed). Audit retention is the customer's
log bucket or sink, not this module.
"""
from ..receipts import verify
from ._common import (TERMINAL, ExportError, batches, event_id, gcloud_token, request_json, rfc3339,
                      span_id, states, trace_id, who)

URL = "https://logging.googleapis.com/v2/entries:write"
LOG_ID = "interlock-receipts"
SEVERITY = {"COMMITTED": "NOTICE", "REFUSED": "WARNING", "AMBIGUOUS": "ERROR"}


def log_entries(bundle, project, log_id=LOG_ID, key=None):
    es = bundle["entries"]
    if not es:
        return []
    eid, (agent, lease) = bundle["effect_id"], who(es)
    base = {"logName": f"projects/{project}/logs/{log_id}",
            "resource": {"type": "global", "labels": {"project_id": project}},
            "trace": f"projects/{project}/traces/{trace_id(eid)}", "spanId": span_id(eid)}

    def labels(kind, state):
        return {"interlock_effect_id": eid, "interlock_kind": kind, "interlock_agent": agent or "",
                "interlock_lease": lease or "", "interlock_state": state}

    out = [{**base, "insertId": event_id(e), "timestamp": rfc3339(e["ts"]),
            "severity": SEVERITY.get(e["kind"], "INFO"), "labels": labels(e["kind"], state),
            "operation": {"id": eid, "producer": "interlock", "first": i == 0, "last": state in TERMINAL},
            "jsonPayload": e}
           for i, (e, state) in enumerate(zip(es, states(es)))]

    verdict, head = verify(bundle, key), es[-1]["hash"]
    out.append({**base, "insertId": f"{eid}-receipt-{head}", "timestamp": rfc3339(es[-1]["ts"]),
                "severity": "INFO" if verdict["valid"] else "ERROR", "labels": labels("RECEIPT", states(es)[-1]),
                "operation": {"id": eid, "producer": "interlock"},
                "jsonPayload": {"summary": bundle.get("summary"), "verification": verdict,
                                "signature": bundle.get("signature"), "head_hash": head, "entries": len(es)}})
    return out


def export(bundles, project, log_id=LOG_ID, token=gcloud_token, key=None):
    """Write every bundle's entries. Returns how many LogEntries were sent. Raises ExportError on any rejection."""
    entries = [le for b in bundles for le in log_entries(b, project, log_id, key)]
    for batch in batches(entries):
        status, body = request_json(URL, {"entries": batch, "partialSuccess": True}, token)
        if status != 200:   # with partialSuccess a 400 can still have stored the valid entries: never trust the status alone
            raise ExportError(f"Cloud Logging returned {status}; entries not named in logEntryErrors were stored: "
                              f"{str(body)[:1000]}")
    return len(entries)
