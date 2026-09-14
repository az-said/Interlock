"""
Probe for the kernel-lock form of claim liveness (docs/11-weakness-audit.md L1, "robust form"). Local only.

Question: if the sender holds a per-effect fcntl.flock from before DISPATCHED is written until the effect is
resolved, and recovery takes an effect over only when it can take that lock (ignoring claim expiry), does
  1. recovery after a real SIGKILL stop waiting out claim_ttl, and
  2. a hung-but-alive sender (still inside apply after claim_ttl) stop being taken over?
Case 2 is the one the core's TTL rule gets wrong on a target with no dedup: recovery looks, finds nothing, and
re-applies while the first send is still coming.

interlock/ is imported, never edited. Targets are local files. Every sender is a separate OS process.

    python3 experiments/competitor_flock_claim.py > results/competitors/flock_claim.txt
"""
import fcntl, json, os, shutil, signal, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.gate import Gate                      # noqa: E402
from interlock.journal import Journal, SqliteJournal  # noqa: E402

TTL, REPS = 5, 3


class FlockClaims:
    """Mixin: a claim on this host is a kernel lock on <journal>.locks/<eid>. The kernel drops it when the holder dies."""
    def _lockfile(self, eid):
        d = self.path + ".locks"
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, eid)

    def _take(self, eid):
        fds = self.__dict__.setdefault("_fds", {})
        if eid in fds:
            return True
        fd = os.open(self._lockfile(eid), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        fds[eid] = fd
        return True

    def _drop(self, eid):
        fd = self.__dict__.get("_fds", {}).pop(eid, None)
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def dispatch(self, effect_id, effect, owner, ttl=TTL, **data):
        if not self._take(effect_id):                 # lock BEFORE DISPATCHED: no instant where it is written but unheld
            return "in_flight"
        blocker = super().dispatch(effect_id, effect, owner, ttl, **data)
        if blocker:
            self._drop(effect_id)
        return blocker

    def claim(self, effect_id, owner, ttl=TTL):
        if owner.endswith("/send"):
            return super().claim(effect_id, owner, ttl)
        if not self._take(effect_id):                 # a live process on this host holds it: never take over
            return False
        self._force(effect_id, owner, ttl)            # lock held: no live sender here, whatever the expiry says
        return True

    def release(self, effect_id, owner):
        super().release(effect_id, owner)
        self._drop(effect_id)


class FlockJournal(FlockClaims, Journal):
    def _force(self, eid, owner, ttl):
        with self._exclusive():
            claims = self._claims()
            claims[eid] = {"owner": owner, "expires": time.time() + ttl}
            self._save_claims(claims)


class FlockSqlite(FlockClaims, SqliteJournal):
    def _force(self, eid, owner, ttl):
        import contextlib
        with contextlib.closing(self._connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO claims (effect_id, owner, expires) VALUES (?, ?, ?)", (eid, owner, time.time() + ttl))


class NoDedupTarget:
    """Tier 2: no dedup, lookup by effect id. Every apply appends one effect. mode: after_commit, before_send, hung."""
    tier, queryable = 2, True

    def __init__(self, path, mode=None):
        self.path, self.mode = path, mode

    def load(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def validate_premises(self, premises, eid=None):
        return []

    def apply(self, eid, effect, crash_after_effect=False):
        if self.mode == "before_send":
            os.kill(os.getpid(), signal.SIGKILL); time.sleep(5)
        if self.mode == "hung":
            time.sleep(TTL + 4)                       # alive, still sending, past claim_ttl
        with open(self.path + ".lock", "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            data = self.load() + [eid]
            with open(self.path, "w") as f:
                json.dump(data, f)
        if self.mode == "after_commit":
            os.kill(os.getpid(), signal.SIGKILL); time.sleep(5)
        return {"status": "ok"}

    def query(self, eid, effect):
        return eid in self.load()


class Leases:
    def is_live(self, lease):
        return True


PROPOSAL = {"agent": "a", "lease": "L", "request_id": "case-1", "premises": {}, "effect": {"amount": 2000}}


def gate(kind, variant, d, mode=None):
    path = os.path.join(d, "j.db" if kind == "sqlite" else "j.jsonl")
    g = Gate(NoDedupTarget(os.path.join(d, "svc.json"), mode), path, Leases(), claim_ttl=TTL)
    if variant == "flock":
        g.journal = (FlockSqlite if kind == "sqlite" else FlockJournal)(path)
    return g


def trial(kind, variant, mode):
    d = tempfile.mkdtemp(prefix="flock-", dir=os.path.dirname(os.path.abspath(__file__)))
    try:
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "child", kind, variant, d, mode])
        if mode == "hung":
            time.sleep(TTL + 1.5)                     # claim expired, sender still alive inside apply
            took = gate(kind, variant, d).recover()
            p.wait()
            g = gate(kind, variant, d)
            commits = sum(1 for e in g.journal.entries() if e["kind"] == "COMMITTED")
            return {"pid": p.pid, "sender_exit": p.returncode, "recovery_during_live_send": list(took.values()),
                    "effects_at_target": len(NoDedupTarget(os.path.join(d, "svc.json")).load()), "committed_entries": commits}
        p.wait()
        t0, status = time.time(), None
        while time.time() - t0 < TTL + 10:
            status = next(iter(gate(kind, variant, d).recover().values()), None)
            if status:
                break
            time.sleep(0.05)
        return {"pid": p.pid, "sender_exit": p.returncode, "status": status,
                "crash_to_recovered_s": round(time.time() - t0, 2),
                "effects_at_target": len(NoDedupTarget(os.path.join(d, "svc.json")).load())}
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        gate(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]).submit(PROPOSAL)
        sys.exit(0)
    print(f"# flock claim probe, {time.strftime('%Y-%m-%d %H:%M:%S %Z')}, claim_ttl={TTL}s, {REPS} trials per cell, "
          "local tier-2 file target (no dedup, lookup by id)")
    for kind in ("jsonl", "sqlite"):
        for mode in ("after_commit", "before_send", "hung"):
            for variant in ("core_ttl", "flock"):
                for rep in range(REPS):
                    print(kind, mode, variant, rep, json.dumps(trial(kind, variant, mode)), flush=True)
