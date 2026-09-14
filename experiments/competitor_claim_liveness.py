"""
Probe for proposed core change 2 (claim liveness), docs/11-weakness-audit.md. Not a live-service result.

Question: if a claim whose owner is a dead process on this host may be taken over at once, does recovery after a
real SIGKILL stop waiting out claim_ttl, and does it still never take over from a live sender?

The gate already writes the owner as host:pid:uuid (interlock/gate.py:66). LiveJournal and LiveSqlite subclass the
core journals here; interlock/ is imported, never edited. The target is a local tier-1 file that dedupes on the
effect id. Every sender is a separate OS process that SIGKILLs itself. One trial per cell.

    python3 experiments/competitor_claim_liveness.py > results/competitors/claim_liveness.txt
"""
import contextlib, json, os, shutil, signal, socket, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.gate import Gate                      # noqa: E402
from interlock.journal import Journal, SqliteJournal  # noqa: E402

TTL = 10


def dead_local(owner):
    """The claim holder is a process on this host that no longer exists. Remote or unreadable: treated as alive."""
    try:
        host, pid = owner.split(":")[:2]
        if host != socket.gethostname():
            return False
        os.kill(int(pid), 0)
        return False
    except ProcessLookupError:
        return True
    except (ValueError, OSError):
        return False


class LiveJournal(Journal):
    def claim(self, effect_id, owner, ttl=120):
        with self._exclusive():
            claims = self._claims()
            held = claims.get(effect_id)
            if held and held.get("owner") != owner and dead_local(held["owner"]):
                del claims[effect_id]
                self._save_claims(claims)
            return super().claim(effect_id, owner, ttl)


class LiveSqlite(SqliteJournal):
    def claim(self, effect_id, owner, ttl=120):
        with contextlib.closing(self._connect()) as db, db:
            row = db.execute("SELECT owner FROM claims WHERE effect_id = ?", (effect_id,)).fetchone()
            if row and row[0] != owner and dead_local(row[0]):
                db.execute("DELETE FROM claims WHERE effect_id = ? AND owner = ?", (effect_id, row[0]))
        return super().claim(effect_id, owner, ttl)


class FileTarget:
    """Tier 1, dedupes on the effect id. mode: after_commit, before_send (both SIGKILL), slow (alive for 3s)."""
    tier, queryable = 1, True

    def __init__(self, path, mode=None):
        self.path, self.mode = path, mode

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
            return json.load(f)

    def validate_premises(self, premises, eid=None):
        return []

    def apply(self, eid, effect, crash_after_effect=False):
        if self.mode == "before_send":
            os.kill(os.getpid(), signal.SIGKILL)
            time.sleep(5)                                 # macOS delivers SIGKILL asynchronously
        data = self._load()
        replayed = eid in data
        data.setdefault(eid, effect)
        with open(self.path, "w") as f:
            json.dump(data, f)
        if self.mode == "after_commit":
            os.kill(os.getpid(), signal.SIGKILL)
            time.sleep(5)
        if self.mode == "slow":
            time.sleep(3)
        return {"status": "replayed" if replayed else "ok"}

    def query(self, eid, effect):
        return eid in self._load()


class Leases:
    def is_live(self, lease):
        return True


PROPOSAL = {"agent": "a", "lease": "L", "request_id": "case-1", "premises": {}, "effect": {"amount": 2000}}


def gate(kind, live, d, mode=None):
    path = os.path.join(d, "j.db" if kind == "sqlite" else "j.jsonl")
    g = Gate(FileTarget(os.path.join(d, "svc.json"), mode), path, Leases(), claim_ttl=TTL)
    if live:
        g.journal = (LiveSqlite if kind == "sqlite" else LiveJournal)(path)
    return g


def trial(kind, live, mode):
    d = tempfile.mkdtemp(prefix="liveness-", dir=os.path.dirname(os.path.abspath(__file__)))
    try:
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "child", kind, str(live), d, mode])
        if mode == "slow":                                # the sender is alive mid-send: recovery must not take over
            time.sleep(1.0)
            took = gate(kind, live, d).recover()
            p.wait()
            return {"sender_exit": p.returncode, "took_over_live_sender": bool(took)}
        p.wait()
        t0, status = time.time(), None
        while time.time() - t0 < TTL + 10:
            status = next(iter(gate(kind, live, d).recover().values()), None)
            if status:
                break
            time.sleep(0.1)
        effects = len(FileTarget(os.path.join(d, "svc.json"))._load())
        return {"sender_exit": p.returncode, "status": status, "crash_to_recovered_s": round(time.time() - t0, 2),
                "effects_at_target": effects}
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        gate(sys.argv[2], sys.argv[3] == "True", sys.argv[4], sys.argv[5]).submit(PROPOSAL)
        sys.exit(0)
    print(f"# claim liveness probe, {time.strftime('%Y-%m-%d %H:%M:%S %Z')}, claim_ttl={TTL}s, one trial per cell, local file target")
    for kind in ("jsonl", "sqlite"):
        for mode in ("after_commit", "before_send", "slow"):
            for live in (False, True):
                print(kind, mode, "liveness" if live else "core_ttl", json.dumps(trial(kind, live, mode)), flush=True)
