"""
Receipts as OpenTelemetry spans over OTLP/HTTP JSON, to any collector or telemetry.googleapis.com. Stdlib only.

One span per effect, one span event per journal entry:

    traceId, spanId   derived from the effect id, so re-sending a receipt names the same span. OTLP is not
                      idempotent: Cloud Trace stored a second copy of the same span on a re-export (verified
                      live, results/export_live.md). Export each receipt once, or dedupe on traceId + spanId
    start, end        the first and last entry's recorded time
    attributes        interlock.effect_id, .agent, .lease, .state (final), and verify()'s claims
    events            name = entry kind; attributes entry_hash, prev_hash, entry_json (the entry, unchanged)
    status            ERROR when AMBIGUOUS or the receipt does not verify, OK when COMMITTED, else UNSET

Google's endpoint needs the resource attribute gcp.project_id (pass project=) and the Cloud Trace API enabled.
"""
import json
from ..receipts import verify
from ._common import ExportError, gcloud_token, nanos, request_json, span_id, states, trace_id, who

GOOGLE = "https://telemetry.googleapis.com"


def _attrs(values):
    def wrap(v):
        if isinstance(v, bool):
            return {"boolValue": v}
        if isinstance(v, int):
            return {"intValue": str(v)}
        return {"stringValue": v if isinstance(v, str) else json.dumps(v, sort_keys=True)}
    return [{"key": k, "value": wrap(v)} for k, v in values.items() if v is not None]


def span(bundle, key=None):
    es, eid = bundle["entries"], bundle["effect_id"]
    agent, lease = who(es)
    state, verdict = states(es)[-1], verify(bundle, key)
    status = ({"code": 2, "message": state if state == "AMBIGUOUS" else "receipt does not verify"}
              if state == "AMBIGUOUS" or not verdict["valid"] else {"code": 1} if state == "COMMITTED" else {"code": 0})
    return {
        "traceId": trace_id(eid), "spanId": span_id(eid), "name": "interlock.effect", "kind": 1,
        "startTimeUnixNano": str(nanos(es[0]["ts"])), "endTimeUnixNano": str(nanos(es[-1]["ts"])),
        "attributes": _attrs({
            "interlock.effect_id": eid, "interlock.agent": agent, "interlock.lease": lease, "interlock.state": state,
            "interlock.valid": verdict["valid"], "interlock.tamper_evident": verdict["tamper_evident"],
            "interlock.signed": verdict["signed"], "interlock.happened": str(verdict["happened"]),
            "interlock.happened_once": verdict["happened_once"],
            "interlock.authorized_when_fired": verdict["authorized_when_fired"],
            "interlock.assumptions_held": verdict["assumptions_held"],
            "interlock.head_hash": es[-1]["hash"], "interlock.entries": len(es)}),
        "events": [{"name": e["kind"], "timeUnixNano": str(nanos(e["ts"])),
                    "attributes": _attrs({"interlock.entry_hash": e["hash"], "interlock.prev_hash": e.get("prev"),
                                          "interlock.entry_json": json.dumps(e)})} for e in es],
        "status": status,
    }


def payload(bundles, project=None, service="interlock", key=None):
    resource = {"service.name": service, "gcp.project_id": project}
    return {"resourceSpans": [{"resource": {"attributes": _attrs(resource)},
                               "scopeSpans": [{"scope": {"name": "interlock.export"},
                                               "spans": [span(b, key) for b in bundles if b["entries"]]}]}]}


def export(bundles, endpoint=GOOGLE, project=None, token=gcloud_token, headers=None, key=None):
    """POST to <endpoint>/v1/traces. For a local collector pass token=None. Returns how many spans were sent."""
    body = payload(bundles, project, key=key)
    h = {**({"x-goog-user-project": project} if project else {}), **(headers or {})}
    status, resp = request_json(endpoint.rstrip("/") + "/v1/traces", body, token, h)
    rejected = int((resp.get("partialSuccess") or {}).get("rejectedSpans") or 0)
    if status != 200 or rejected:
        raise ExportError(f"OTLP endpoint returned {status}, {rejected} spans rejected: {str(resp)[:1000]}")
    return len(body["resourceSpans"][0]["scopeSpans"][0]["spans"])
