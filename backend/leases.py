"""
Approval leases in a SQLite file, so the API process can revoke what a worker process checks.
Same is_live() interface as interlock.Leases, plus allows(): live, and the effect's amount is
within what the person approved. The gate uses allows() when a lease store has it.
"""
import contextlib, sqlite3, time


class DurableLeases:
    def __init__(self, path):
        self.path = path
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS approvals (lease_id TEXT PRIMARY KEY, max_cents INTEGER, "
                       "granted REAL, revoked REAL)")

    @contextlib.contextmanager
    def _db(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            yield db

    def _row(self, lease_id):
        with self._db() as db:
            return db.execute("SELECT max_cents, revoked, granted FROM approvals WHERE lease_id = ?", (lease_id,)).fetchone()

    def describe(self, lease_id):
        """The grant as stored, recorded by the gate next to each check it makes."""
        row = self._row(lease_id)
        return row and {"lease_id": lease_id, "max_cents": row[0], "revoked": row[1], "granted": row[2]}

    def grant(self, lease_id, max_cents=None):
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO approvals VALUES (?, ?, ?, NULL)", (lease_id, max_cents, time.time()))

    def revoke(self, lease_id):
        with self._db() as db:
            db.execute("UPDATE approvals SET revoked = ? WHERE lease_id = ? AND revoked IS NULL", (time.time(), lease_id))

    def is_live(self, lease_id):
        row = self._row(lease_id)
        return row is not None and row[1] is None

    def max_cents(self, lease_id):
        row = self._row(lease_id)
        return row[0] if row else None

    def allows(self, lease_id, effect):
        row = self._row(lease_id)
        if row is None or row[1] is not None:
            return False
        amount = effect.get("amount") if isinstance(effect, dict) else None
        return row[0] is None or (type(amount) is int and 0 < amount <= row[0])     # a cap fails closed
