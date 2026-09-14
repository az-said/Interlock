"""The effect journal as interlock.journal._Queries, so interlock.receipts.bundle and verify run unchanged."""
import json
from interlock.journal import _Queries


class PgJournalView(_Queries):
    def __init__(self, rt):
        self.conn = rt.conn

    def entries(self, effect_id=None):
        if effect_id is None:
            rows = self.conn.execute("select body from ilr.journal order by seq")
        else:
            rows = self.conn.execute("select body from ilr.journal where effect_id = %s order by seq", (effect_id,))
        return [json.loads(r["body"]) for r in rows]
