"""
EffectTarget: a local code repository. Effects are file writes/appends.

Premises an agent can capture about a repo:
    files:   {path: sha256 of the content it READ}
    symbols: {"module.func": arity it CALLED}
mode="file" captures hashes (coarse); mode="symbol" captures symbols (fine).
The gap between those two modes is one of the results in this repo.

Tier 2: a filesystem is queryable after a crash.
"""
import ast, hashlib, os
from ..gate import SimulatedCrash


def _h(s): return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()[:12]


class LocalRepo:
    tier = 2

    def __init__(self, path):
        self.path = path

    def symbol_table(self):
        table = {}
        for fn in os.listdir(self.path):
            if fn.endswith(".py"):
                tree = ast.parse(open(os.path.join(self.path, fn)).read())
                for n in tree.body:
                    if isinstance(n, ast.FunctionDef):
                        table[f"{fn[:-3]}.{n.name}"] = len(n.args.args)
        return table

    def capture(self, files_read, symbols_called, mode="symbol"):
        st = self.symbol_table()
        return {"files": {p: _h(open(os.path.join(self.path, p), "rb").read()) for p in files_read}
                         if mode == "file" else {},
                "symbols": {s: st.get(s) for s in symbols_called}}

    def validate_premises(self, premises):
        bad = []
        for p, h in premises.get("files", {}).items():
            fp = os.path.join(self.path, p)
            if not os.path.exists(fp) or _h(open(fp, "rb").read()) != h:
                bad.append(f"{p} changed since read")
        st = self.symbol_table()
        for s, arity in premises.get("symbols", {}).items():
            if st.get(s) != arity:
                bad.append(f"{s}: expected arity {arity}, now {st.get(s)}")
        return bad

    def _post(self, effect):
        post = dict(effect.get("writes", {}))
        for p, extra in effect.get("appends", {}).items():
            fp = os.path.join(self.path, p)
            post[p] = (open(fp).read() if os.path.exists(fp) else "") + extra
        return post

    def apply(self, eid, effect, crash_after_effect=False):
        for p, content in self._post(effect).items():
            open(os.path.join(self.path, p), "w").write(content)
        if crash_after_effect:
            raise SimulatedCrash(eid)

    def query(self, eid, effect):
        for p, extra in effect.get("appends", {}).items():
            fp = os.path.join(self.path, p)
            if not (os.path.exists(fp) and extra in open(fp).read()):
                return False
        for p, content in effect.get("writes", {}).items():
            fp = os.path.join(self.path, p)
            if not (os.path.exists(fp) and open(fp).read() == content):
                return False
        return True
