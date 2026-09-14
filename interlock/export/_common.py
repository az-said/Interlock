"""Shared by every exporter: stable ids, time formats, the effect's state per entry, auth, one HTTP call."""
import datetime, hashlib, json, subprocess, time, urllib.error, urllib.request
from ..journal import _Queries

TERMINAL = ("COMMITTED", "REFUSED", "AMBIGUOUS")


class ExportError(RuntimeError):
    """The destination did not confirm it stored everything it was sent. Re-exporting is safe."""


def event_id(entry):
    """One id per journal entry, the same on every export: the dedup key everywhere."""
    return f"{entry['effect_id']}-{entry['hash']}"


def trace_id(effect_id):
    return hashlib.sha256(f"interlock/trace/{effect_id}".encode()).hexdigest()[:32]


def span_id(effect_id):
    return hashlib.sha256(f"interlock/span/{effect_id}".encode()).hexdigest()[:16]


def rfc3339(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def nanos(ts):
    return int(round(ts * 1_000_000)) * 1000


def text(value):
    """A column or label value: strings as they are, anything else as JSON."""
    return value if value is None or isinstance(value, str) else json.dumps(value, sort_keys=True)


class _Prefix(_Queries):
    def __init__(self, entries):
        self._entries = entries

    def entries(self, effect_id=None):
        return self._entries


def states(entries):
    """
    The effect's state after each entry, summarized as the journal does (a commit stays COMMITTED).
    It depends only on the entries up to that point, so re-exporting a bundle that has grown since
    never changes what an earlier entry says.
    """
    return [_Prefix(entries[:i + 1]).receipt(entries[0]["effect_id"])["final"] for i in range(len(entries))]


def who(entries):
    """Authority of the committed send, or the latest decision if it has not committed."""
    values = identities(entries)
    return next((value for e, value in zip(entries, values) if e["kind"] == "COMMITTED"),
                values[-1] if values else (None, None))


def identities(entries):
    """Agent and authority at each entry, using only that entry's history."""
    agent = lease = dispatched = None
    out = []
    for e in entries:
        if e["kind"] == "PROPOSED":
            agent, lease = e.get("agent"), text(e.get("lease"))
        elif e["kind"] in ("AUTHORIZED", "DISPATCHED"):
            lease = text(e.get("lease"))
            if e["kind"] == "DISPATCHED":
                dispatched = (agent, lease)
        if e["kind"] == "COMMITTED" and dispatched is not None:
            agent, lease = dispatched
        out.append((agent, lease))
    return out


_token = (0.0, None)


def gcloud_token():
    """An access token for gcloud's active account. Cached 30 minutes; tokens last an hour."""
    global _token
    if time.time() - _token[0] > 1800:
        out = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, timeout=60)
        if out.returncode:
            raise ExportError("gcloud auth print-access-token failed: " + out.stderr.strip()[-300:])
        _token = (time.time(), out.stdout.strip())
    return _token[1]


def request_json(url, body=None, token=None, headers=None, method="POST", timeout=60):
    """(status, parsed body). Never raises on an HTTP error status: callers decide what counts as stored."""
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = "Bearer " + token()
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=h, method=method if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, {"raw": raw.decode(errors="replace")[:2000]}


def batches(items, max_bytes=5_000_000):
    """Split so each request body stays well under the 10 MB limit Logging and BigQuery share."""
    batch, size = [], 0
    for item in items:
        n = len(json.dumps(item))
        if batch and size + n > max_bytes:
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += n
    if batch:
        yield batch
