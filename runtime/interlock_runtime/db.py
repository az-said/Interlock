"""Connections, schema, and the fence: the first statement of every worker write (section 5.2)."""
import contextlib, datetime, hashlib, json, os
import psycopg
from psycopg.rows import dict_row
from psycopg.types.datetime import TimestamptzLoader
from psycopg.types.json import Jsonb

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
TERMINAL = ("completed", "failed", "cancelled", "continued")


class Fenced(Exception):
    """This worker's claim is no longer current (epoch moved, or its lease expired). Abandon the run."""


class _TimestamptzLoader(TimestamptzLoader):
    """available_at is 'infinity' while a workflow waits with no timeout; Python has no such datetime."""
    def load(self, data):
        if bytes(data) == b"infinity":
            return datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
        return super().load(data)


def connect(dsn):
    """Autocommit connection: every multi-statement write is an explicit `with conn.transaction()`."""
    conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    conn.adapters.register_loader("timestamptz", _TimestamptzLoader)
    return conn


def apply_schema(conn):
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(7411)")   # many workers may start at once
        with open(SCHEMA) as f:
            conn.execute(f.read())


def canonical(value):
    return json.dumps(json.loads(json.dumps(value, default=str)), sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def fence(conn, wf_id, epoch, ttl):
    """Extend the lease if this claim is still current. Returns (cancel_requested_at, now_epoch_seconds)."""
    row = conn.execute(
        "update ilr.workflows set lease_expires_at = now() + make_interval(secs => %s), updated_at = now() "
        "where id = %s and epoch = %s and status = 'running' and lease_expires_at > now() "
        "returning cancel_requested_at, extract(epoch from now())::float8 as now",
        (ttl, wf_id, epoch)).fetchone()
    if row is None:
        raise Fenced(f"{wf_id} epoch {epoch}")
    return row["cancel_requested_at"], row["now"]


@contextlib.contextmanager
def fenced(conn, wf_id, epoch, ttl):
    """One transaction whose first statement is the fence. Zero rows: roll back and raise Fenced."""
    with conn.transaction():
        yield fence(conn, wf_id, epoch, ttl)


def db_now(conn):
    return conn.execute("select extract(epoch from now())::float8 as now").fetchone()["now"]


def notify(conn):
    conn.execute("notify ilr_ready")


def wake(conn, wf_id):
    """Make a non-terminal workflow due now. Caller holds the row lock (lock order: workflow row first)."""
    conn.execute(
        "update ilr.workflows set available_at = now(), updated_at = now(), "
        "status = case when status = 'sleeping' then 'pending' else status end "
        "where id = %s and status not in ('completed','failed','cancelled','continued')", (wf_id,))
    notify(conn)


__all__ = ["Fenced", "Jsonb", "connect", "apply_schema", "fence", "fenced", "db_now", "wake", "notify", "sha", "canonical"]
