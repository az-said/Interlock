"""
EffectTarget: a local code repository. Effects are file writes/appends.

Premises an agent can capture about a repo:
    files:   {path: sha256 of the content it READ}
    symbols: {"module.func": arity it CALLED}
mode="file" captures hashes (coarse); mode="symbol" captures symbols (fine).
The gap between those two modes is one of the results in this repo.

Tier 1 with lookup: durable per-effect postimages make retries idempotent. Keep
.interlock-effects.jsonl and its sidecars with the repository for as long as effects
may be retried. Pre-upgrade unresolved effects need manual reconciliation before
using this adapter: older versions did not record their postimages.
"""
import ast, hashlib, os, stat, uuid
from ..gate import SimulatedCrash
from ..journal import Journal


def _h(s): return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()[:12]


def _read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8", "newline": ""})) as f:
        return f.read()


def _write(path, content):
    """Replace a whole file durably; a crash must not leave half a postimage."""
    path = os.path.realpath(path)             # write through a symlink, as open(path, "w") would, never replace it
    existed = os.path.exists(path)
    tmp = os.path.join(os.path.dirname(path), f".interlock-write-{uuid.uuid4().hex}")
    # 0o666 under the umask, as a plain open() creates it (mkstemp would make a new file 0600)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if existed:
            os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
        os.replace(tmp, path)
        if os.name != "nt":
            directory = os.open(os.path.dirname(path), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class LocalRepo:
    tier = 1
    queryable = True

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.effects = Journal(os.path.join(self.path, ".interlock-effects.jsonl"))

    def symbol_table(self, originals=None):
        table = {}
        for fn in os.listdir(self.path):
            if fn.endswith(".py"):
                source = originals.get(fn) if originals is not None and fn in originals else _read(os.path.join(self.path, fn))
                if source is None:
                    continue
                tree = ast.parse(source)
                for n in tree.body:
                    if isinstance(n, ast.FunctionDef):
                        table[f"{fn[:-3]}.{n.name}"] = len(n.args.args)
        return table

    def capture(self, files_read, symbols_called, mode="symbol"):
        st = self.symbol_table()
        return {"files": {p: _h(_read(os.path.join(self.path, p), "rb")) for p in files_read}
                         if mode == "file" else {},
                "symbols": {s: st.get(s) for s in symbols_called}}

    def validate_premises(self, premises, eid=None):
        bad = []
        plan = self._plan(eid) if eid else None
        originals = {p: plan["before"][p] for p, content in plan["after"].items()
                     if self._current(p) == content} if plan else {}
        for p, h in premises.get("files", {}).items():
            fp = os.path.join(self.path, p)
            if p in originals and originals[p] is not None and _h(originals[p]) == h:
                continue                              # this effect changed a file it read
            if not os.path.exists(fp) or _h(_read(fp, "rb")) != h:
                bad.append(f"{p} changed since read")
        st = self.symbol_table(originals)
        for s, arity in premises.get("symbols", {}).items():
            if st.get(s) != arity:
                bad.append(f"{s}: expected arity {arity}, now {st.get(s)}")
        return bad

    def _post(self, effect):
        post = dict(effect.get("writes", {}))
        for p, extra in effect.get("appends", {}).items():
            fp = os.path.join(self.path, p)
            post[p] = post.get(p, _read(fp) if os.path.exists(fp) else "") + extra
        return post

    def _current(self, path):
        fp = os.path.join(self.path, path)
        return _read(fp) if os.path.exists(fp) else None

    def _plan(self, eid):
        """The first PREPARED since the last DISCARDED: a plan a lookup proved never landed is not reused."""
        plan = None
        for e in self.effects.entries(eid):
            if e["kind"] == "PREPARED" and plan is None:
                plan = e
            elif e["kind"] == "DISCARDED":
                plan = None
        return plan

    def _check(self, plan, effect):
        if plan["effect"] != effect:
            raise ValueError("repository effect differs from its prepared payload")
        for p, content in plan["after"].items():
            if self._current(p) not in (plan["before"][p], content):
                raise RuntimeError(f"{p} changed outside the prepared repository effect")

    def apply(self, eid, effect, crash_after_effect=False):
        with self.effects._exclusive():
            plan = self._plan(eid)
            if plan is None:
                post = self._post(effect)
                plan = self.effects.append("PREPARED", eid, effect=effect,
                                           before={p: self._current(p) for p in post}, after=post)
            if plan["effect"] != effect:
                raise ValueError("repository effect differs from its prepared payload")
            if not self.effects.has("APPLIED", eid):
                self._check(plan, effect)
                for p, content in plan["after"].items():
                    if self._current(p) != content:
                        _write(os.path.join(self.path, p), content)
                self.effects.append("APPLIED", eid)
        if crash_after_effect:
            raise SimulatedCrash(eid)

    def query(self, eid, effect):
        with self.effects._exclusive():
            plan = self._plan(eid)
            if plan is None:
                return False
            if plan["effect"] != effect:
                raise ValueError("repository effect differs from its prepared payload")
            if self.effects.has("APPLIED", eid):
                return True
            self._check(plan, effect)
            if all(self._current(p) == content for p, content in plan["after"].items()):
                self.effects.append("APPLIED", eid)
                return True
            if any(self._current(p) != plan["before"][p] for p in plan["after"]):
                raise RuntimeError("repository effect is partially applied; outcome is not absence")
            # Nothing was written. A later send (a re-approved retry, after files moved on) prepares
            # from the files as they are then, instead of failing against this plan's preimage.
            self.effects.append("DISCARDED", eid)
            return False
