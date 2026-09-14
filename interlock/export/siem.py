"""
Receipts as plain lines for a SIEM (Splunk, Sentinel, QRadar, ArcSight, ...). Stdlib only.

    jsonl_lines()  one JSON object per journal entry, keys sorted, the entry itself under "entry"
    cef_lines()    one ArcSight CEF line per journal entry
    append()       add lines to a file the SIEM's forwarder tails, skipping event ids the file already holds

Every line carries event_id = <effect id>-<entry hash> (CEF: externalId), the dedup key for the SIEM too.
"""
import json
from ._common import event_id, identities, rfc3339, states

CEF_SEVERITY = {"COMMITTED": 3, "REFUSED": 6, "AMBIGUOUS": 9}


def _events(bundles):
    for b in bundles:
        es = b["entries"]
        if not es:
            continue
        for i, (e, state, (agent, lease)) in enumerate(zip(es, states(es), identities(es))):
            yield {"event_id": event_id(e), "time": rfc3339(e["ts"]), "effect_id": e["effect_id"], "entry_index": i,
                   "kind": e["kind"], "state": state, "agent": agent, "lease": lease, "reason": e.get("reason"),
                   "via": e.get("via"), "entry_hash": e["hash"], "prev_hash": e.get("prev"), "entry": e}


def jsonl_lines(bundles):
    return [(ev["event_id"], json.dumps(ev, sort_keys=True)) for ev in _events(bundles)]


def _header(v):
    return str(v).replace("\\", "\\\\").replace("|", "\\|")


def _ext(v):
    s = v if isinstance(v, str) else json.dumps(v, sort_keys=True)
    return s.replace("\\", "\\\\").replace("=", "\\=").replace("\r", "\\r").replace("\n", "\\n")


def cef_lines(bundles, version="0.2.0"):
    out = []
    for ev in _events(bundles):
        ext = {"rt": int(round(ev["entry"]["ts"] * 1000)), "externalId": ev["event_id"], "act": ev["kind"],
               "outcome": ev["state"], "suser": ev["agent"], "reason": ev["reason"],
               "cs1Label": "effectId", "cs1": ev["effect_id"], "cs2Label": "lease", "cs2": ev["lease"],
               "cs3Label": "entryHash", "cs3": ev["entry_hash"], "cs4Label": "prevHash", "cs4": ev["prev_hash"],
               "cs5Label": "via", "cs5": ev["via"]}
        body = " ".join(f"{k}={_ext(v)}" for k, v in ext.items() if v is not None)
        head = "|".join(_header(x) for x in ("CEF:0", "Interlock", "interlock-gate", version, ev["kind"],
                                             f"Interlock {ev['kind']}", CEF_SEVERITY.get(ev["kind"], 1)))
        out.append((ev["event_id"], f"{head}|{body}"))
    return out


def append(path, lines):
    """Append (event_id, line) pairs the file does not already hold. Returns how many were written."""
    try:
        with open(path) as f:
            seen = f.read()                 # ponytail: reads the whole file; keep an id index once files get large
    except FileNotFoundError:
        seen = ""
    new = [line for eid, line in lines if eid not in seen]
    with open(path, "a") as f:
        f.writelines(line + "\n" for line in new)
    return len(new)
