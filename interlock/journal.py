"""
The append-only decision log. The one idea everything rests on:

    write what you are about to do, to disk, BEFORE you do it.

Entry kinds (the four facts from the brief, plus the failure states):

    PROPOSED    an agent produced an effect + the premises it relied on
    AUTHORIZED  the lease it holds was live at this instant
    DISPATCHED  we are about to apply the effect  (durable BEFORE applying)
    COMMITTED   the effect is applied and confirmed
    REFUSED     a premise, lease, claim, or payload-binding check failed; nothing applied
    AMBIGUOUS   we crashed mid-effect and cannot determine what happened
    ESCALATED   sent to a person: why, what changed, the facts shown, who it was routed to
    DECIDED     a person answered an escalation (approve, reject or repair)
    CONFIRMED   the target itself confirmed the effect (evidence only, never control flow)

Mapping to the team spec's state names (docs/team-notes/refund-spec-shawn.md):
    Prepared = PROPOSED+AUTHORIZED · In flight = DISPATCHED · Confirmed = COMMITTED
    Needs reconciliation = AMBIGUOUS · Rejected = REFUSED

Because DISPATCHED is durable before the effect exists, recovery can always
find "things we started and never confirmed". Nothing else in the system
needs to remember anything.

Two backends, one set of queries:
    Journal         append-only JSONL file, fsync'd, flock'd (one machine, many processes)
    SqliteJournal   a .db file in WAL mode (many workers sharing one database)

Three decisions must be atomic across workers, and are on both backends:
    dispatch  "send this effect, unless it is in flight, resolved, or recorded with another payload",
              which also claims the effect for the sender
    claim     "I will recover this effect", granted only if nobody holds a live claim
    release   give a claim up once the effect is resolved
A claim expires after its ttl, so a crashed sender or recoverer cannot block an effect forever.
A send, and a resend during recovery, must finish inside that ttl: time targets out sooner.
"""
import contextlib, errno, hashlib, json, os, sqlite3, threading, time
from .escalation import closed, latest
try:
    import fcntl
except ImportError:                     # Windows uses a byte-range lock on the same sidecar
    fcntl = None
    import msvcrt

CLAIM_TTL = 120                         # seconds


def _plain(value):
    """The value as it will read back from the journal."""
    return json.loads(json.dumps(value, default=str))


class _Queries:
    """Everything the gate asks a journal, written once over entries()."""

    def has(self, kind, effect_id):
        return any(e["kind"] == kind for e in self.entries(effect_id))

    def recorded_effect(self, effect_id):
        """The payload bound to this effect id at first proposal, if any."""
        for e in self.entries(effect_id):
            if e["kind"] == "PROPOSED":
                return e.get("effect")
        return None

    def in_flight(self):
        """effect ids with an open dispatch: being sent, or crashed between effect and ack."""
        by_effect = {}
        for e in self.entries():
            by_effect.setdefault(e["effect_id"], []).append(e)
        return [eid for eid, es in by_effect.items() if open_dispatch(es)]

    def receipt(self, effect_id):
        """
        The four facts, as one inspectable object. `executed` is what the target
        confirmed, not what was attempted: True once COMMITTED, "unknown" while a crash
        left it in flight or it is AMBIGUOUS, False otherwise. `final` describes the
        effect, so a later refused re-proposal doesn't hide a committed refund.
        `authority` is the lease (or approval) the effect was authorized under.
        """
        es = self.entries(effect_id)
        kinds = [e["kind"] for e in es]
        committed, ambiguous = "COMMITTED" in kinds, "AMBIGUOUS" in kinds
        unresolved = ambiguous or open_dispatch(es)
        return {
            "effect_id": effect_id,
            "proposed":   "PROPOSED"   in kinds,
            "authorized": "AUTHORIZED" in kinds,
            "executed":   True if committed else "unknown" if unresolved else False,
            "recorded":   committed,
            "final":      "COMMITTED" if committed else "AMBIGUOUS" if ambiguous else (kinds[-1] if kinds else None),
            "authority":  next((e.get("lease") for e in reversed(es) if e["kind"] == "DISPATCHED"),
                               next((e.get("lease") for e in es if e["kind"] == "AUTHORIZED"), None)),
        }


def _canonical(entry):
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


def entry_hash(entry):
    return hashlib.sha256(_canonical({k: v for k, v in entry.items() if k != "hash"}).encode()).hexdigest()


def _seal(entry, previous):
    """Chain the entry to this effect's previous entry, so edits, deletions and reordering show."""
    entry = _plain(entry)                                   # hash exactly what will be stored
    entry["prev"] = previous.get("hash") if previous else None
    entry["hash"] = entry_hash(entry)
    return entry


def open_dispatch(entries):
    """
    True while a DISPATCHED entry has not been resolved. Only COMMITTED, AMBIGUOUS, or a
    REFUSED written by recovery (resolves=True) resolve it. Other workers may append
    PROPOSED, AUTHORIZED or their own REFUSED after it; none of those close it.
    """
    open_ = False
    for e in entries:
        if e["kind"] == "DISPATCHED":
            open_ = True
        elif e["kind"] in ("COMMITTED", "AMBIGUOUS") or (e["kind"] == "REFUSED" and e.get("resolves")):
            open_ = False
    return open_


def dispatch_blocker(entries, effect, lease=None, premises=None):
    """
    Why this effect may not be dispatched now, or None. Once escalated, only a lease citing a
    person's approval of the latest escalation, in the group it was routed to, on the facts it
    showed, sends it (I7); a closed effect never goes (I8). The lease's group decides whose
    membership is_live checks, so it must be the escalation's, not whatever the caller names.
    lease and premises default to None so a journal override can call it with two arguments
    (scenarios/shared_cap/cap.py); I7 is then not enforced on that journal.
    """
    kinds = [e["kind"] for e in entries]
    if open_dispatch(entries):
        return "in_flight"
    if "COMMITTED" in kinds:
        return "committed"
    if "AMBIGUOUS" in kinds:
        return "ambiguous"
    recorded = next((e.get("effect") for e in entries if e["kind"] == "PROPOSED"), None)
    if recorded is not None and recorded != _plain(effect):
        return "conflicting_payload"
    if closed(entries):
        return "closed"
    settled = [i for i, e in enumerate(entries) if e["kind"] == "REFUSED" and e.get("code") == "target_error" and e.get("resolves")]
    if settled and not any(e["kind"] == "ESCALATED" for e in entries[settled[-1] + 1:]):
        return "target_error"           # the target said it failed, but it may have landed: only a person sends it again
    esc, dec = latest(entries)
    if esc is not None:
        ok = (isinstance(lease, dict) and lease.get("escalation") == esc["hash"] and dec is not None
              and dec["decision"] == "approve" and dec["by"] == lease.get("by") and dec["at"] == lease.get("at")
              and lease.get("group") == esc["group"] and _plain(premises) == esc["facts"])
        if not ok:
            return "awaiting_decision"
    return None


class Journal(_Queries):
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self._depth = 0
        open(path, "a").close()

    @contextlib.contextmanager
    def _exclusive(self):
        """Serialize journal access across threads and processes with an OS lock on a sidecar."""
        with self._lock:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            with open(self.path + ".lock", "a+b") as f:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_EX)
                else:
                    while True:
                        try:
                            f.seek(0)
                            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError as exc:
                            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                                raise
                            time.sleep(0.01)
                self._depth = 1
                try:
                    yield
                finally:
                    self._depth = 0
                    if fcntl:
                        fcntl.flock(f, fcntl.LOCK_UN)
                    else:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def _drop_torn_tail(self):
        """A final line with no newline is a write that never returned, so it was never acknowledged."""
        with open(self.path, "r+b") as f:
            data = f.read()
            if data and not data.endswith(b"\n"):
                f.truncate(data.rfind(b"\n") + 1)
                f.flush()
                os.fsync(f.fileno())

    def append(self, kind, effect_id, **data):
        with self._exclusive():
            self._drop_torn_tail()
            prior = self.entries(effect_id)
            entry = _seal({"ts": time.time(), "kind": kind, "effect_id": effect_id, **data}, prior[-1] if prior else None)
            with open(self.path, "a") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())        # durable before we return
        return entry

    def append_if(self, kind, effect_id, check, **data):
        """
        Append unless check(entries) names a blocker. Returns (entry, None) or (None, blocker).
        check runs under the lock, so it must be pure and fast.
        """
        with self._exclusive():
            blocker = check(self.entries(effect_id))
            return (None, blocker) if blocker else (self.append(kind, effect_id, **data), None)

    def entries(self, effect_id=None):
        with self._exclusive(), open(self.path, "rb") as f:
            data = f.read()
        complete = data[:data.rfind(b"\n") + 1]              # ignore a torn final line
        es = [json.loads(line) for line in complete.splitlines() if line.strip()]
        return [e for e in es if effect_id is None or e["effect_id"] == effect_id]

    def _claims(self):
        try:
            with open(self.path + ".claims") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return {}

    def _save_claims(self, claims):
        tmp = self.path + ".claims.tmp"
        with open(tmp, "w") as f:
            json.dump(claims, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path + ".claims")               # never a half-written claims file

    def dispatch(self, effect_id, effect, owner, ttl=CLAIM_TTL, **data):
        """Write DISPATCHED and claim the effect for `owner`, unless blocked. Returns the blocker, or None."""
        with self._exclusive():
            blocker = dispatch_blocker(self.entries(effect_id), effect, data.get("lease"), data.get("premises"))
            if blocker:
                return blocker
            self.append("DISPATCHED", effect_id, effect=effect, **data)
            claims = self._claims()
            claims[effect_id] = {"owner": owner, "expires": time.time() + ttl}
            self._save_claims(claims)
            return None

    def claim(self, effect_id, owner, ttl=CLAIM_TTL):
        """Take (or refresh) responsibility for an effect. Refused while someone else holds a live claim."""
        with self._exclusive():
            claims, now = self._claims(), time.time()
            held = claims.get(effect_id)
            if held and held.get("owner") != owner and held.get("expires", 0) > now:
                return False
            claims[effect_id] = {"owner": owner, "expires": now + ttl}
            self._save_claims(claims)
            return True

    def release(self, effect_id, owner):
        with self._exclusive():
            claims = self._claims()
            if claims.get(effect_id, {}).get("owner") == owner:
                del claims[effect_id]
                self._save_claims(claims)


class SqliteJournal(_Queries):
    def __init__(self, path):
        self.path = path
        for attempt in range(100):              # many workers may open the same new database at once
            try:
                with contextlib.closing(sqlite3.connect(self.path, timeout=30)) as db, db:
                    db.execute("PRAGMA journal_mode=WAL")   # a property of the file: set once here, never per connection
                    db.execute("CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                               "effect_id TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL)")
                    db.execute("CREATE INDEX IF NOT EXISTS entries_by_effect ON entries (effect_id, seq)")
                    db.execute("CREATE TABLE IF NOT EXISTS claims (effect_id TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL)")
                return
            except sqlite3.OperationalError as e:
                if "locked" not in str(e) or attempt == 99:
                    raise
                time.sleep(0.02)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA synchronous=FULL")    # durable before we return, like the fsync above
        return db

    @staticmethod
    def _insert(db, kind, effect_id, data):
        """Call inside BEGIN IMMEDIATE, so the chain link and the insert are one step."""
        row = db.execute("SELECT body FROM entries WHERE effect_id = ? ORDER BY seq DESC LIMIT 1", (effect_id,)).fetchone()
        entry = _seal({"ts": time.time(), "kind": kind, "effect_id": effect_id, **data}, json.loads(row[0]) if row else None)
        db.execute("INSERT INTO entries (effect_id, kind, body) VALUES (?, ?, ?)", (effect_id, kind, json.dumps(entry)))
        return entry

    def append(self, kind, effect_id, **data):
        with contextlib.closing(self._connect()) as db:
            db.isolation_level = None
            db.execute("BEGIN IMMEDIATE")
            entry = self._insert(db, kind, effect_id, data)
            db.execute("COMMIT")
            return entry

    def append_if(self, kind, effect_id, check, **data):
        with contextlib.closing(self._connect()) as db:
            db.isolation_level = None
            db.execute("BEGIN IMMEDIATE")            # takes the write lock before reading
            blocker = check(self._chain(db, effect_id))
            if blocker:
                db.execute("ROLLBACK")
                return None, blocker
            entry = self._insert(db, kind, effect_id, data)
            db.execute("COMMIT")
            return entry, None

    @staticmethod
    def _chain(db, effect_id):
        return [json.loads(b) for (b,) in db.execute("SELECT body FROM entries WHERE effect_id = ? ORDER BY seq", (effect_id,))]

    def entries(self, effect_id=None):
        with contextlib.closing(self._connect()) as db:
            if effect_id is None:
                rows = db.execute("SELECT body FROM entries ORDER BY seq")
            else:
                rows = db.execute("SELECT body FROM entries WHERE effect_id = ? ORDER BY seq", (effect_id,))
            return [json.loads(body) for (body,) in rows]

    def dispatch(self, effect_id, effect, owner, ttl=CLAIM_TTL, **data):
        with contextlib.closing(self._connect()) as db:
            db.isolation_level = None
            db.execute("BEGIN IMMEDIATE")            # takes the write lock before reading
            blocker = dispatch_blocker(self._chain(db, effect_id), effect, data.get("lease"), data.get("premises"))
            if blocker:
                db.execute("ROLLBACK")
                return blocker
            self._insert(db, "DISPATCHED", effect_id, {"effect": effect, **data})
            db.execute("INSERT OR REPLACE INTO claims (effect_id, owner, expires) VALUES (?, ?, ?)",
                       (effect_id, owner, time.time() + ttl))
            db.execute("COMMIT")
            return None

    def claim(self, effect_id, owner, ttl=CLAIM_TTL):
        now = time.time()
        with contextlib.closing(self._connect()) as db, db:
            cur = db.execute(
                "INSERT INTO claims (effect_id, owner, expires) VALUES (?, ?, ?) "
                "ON CONFLICT (effect_id) DO UPDATE SET owner = excluded.owner, expires = excluded.expires "
                "WHERE claims.owner = excluded.owner OR claims.expires < ?",
                (effect_id, owner, now + ttl, now))
            return cur.rowcount == 1

    def release(self, effect_id, owner):
        with contextlib.closing(self._connect()) as db, db:
            db.execute("DELETE FROM claims WHERE effect_id = ? AND owner = ?", (effect_id, owner))


def open_journal(path):
    """A .db / .sqlite path gets the shared SQLite journal; anything else the JSONL file."""
    return SqliteJournal(path) if str(path).endswith((".db", ".sqlite", ".sqlite3")) else Journal(path)


def effect_id_for(proposal):
    """
    The identity of an effect is fixed at the moment it is approved, and never
    derived from a model output or a retry.

    Two cases:
      - the proposal carries a request_id (an approved request supplied by the
        application, e.g. a support case authorising one $20 refund): the effect
        id is derived from that. A model that re-decides "$30" on retry produces
        the SAME effect id with a DIFFERENT payload, which the gate rejects.
      - no request_id (e.g. an agent's diff): the effect id is the hash of the
        decision content, so the same decision from any agent or retry is one effect.

    Either way: one approved decision -> one effect id -> at most one committed
    effect. This is why "preserve decision history" and "prevent duplicate
    effects" are one mechanism and not two.
    """
    key = proposal.get("request_id")
    canonical = json.dumps(key if key is not None else proposal["effect"], sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
