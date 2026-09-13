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

Mapping to the team spec's state names (docs/team-notes/refund-spec-shawn.md):
    Prepared = PROPOSED+AUTHORIZED · In flight = DISPATCHED · Confirmed = COMMITTED
    Needs reconciliation = AMBIGUOUS · Rejected = REFUSED

Because DISPATCHED is durable before the effect exists, recovery can always
find "things we started and never confirmed". Nothing else in the system
needs to remember anything.

Two backends, one set of queries:
    Journal         append-only JSONL file, fsync'd, flock'd (one machine, many processes)
    SqliteJournal   a .db file in WAL mode (many workers sharing one database)
Both make the two decisions that must be atomic across workers atomic: "dispatch this
effect unless someone already has" and "I will recover this effect, nobody else".
"""
import contextlib, hashlib, json, os, sqlite3, threading, time
try:
    import fcntl
except ImportError:                     # no flock (Windows): a file journal is single-process
    fcntl = None

CLAIM_TTL = 60                          # seconds before an abandoned recovery claim can be taken over


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
        """effect ids with an open dispatch: crashed between effect and ack."""
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
            "authority":  next((e.get("lease") for e in es if e["kind"] == "AUTHORIZED"), None),
        }


def _canonical(entry):
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


def entry_hash(entry):
    return hashlib.sha256(_canonical({k: v for k, v in entry.items() if k != "hash"}).encode()).hexdigest()


def _seal(entry, previous):
    """Chain the entry to this effect's previous entry, so edits, deletions and reordering show."""
    entry = json.loads(json.dumps(entry, default=str))     # hash exactly what will be stored
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


def _blocks_dispatch(entries):
    kinds = [e["kind"] for e in entries]
    return open_dispatch(entries) or "COMMITTED" in kinds or "AMBIGUOUS" in kinds


class Journal(_Queries):
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self._depth = 0
        open(path, "a").close()

    @contextlib.contextmanager
    def _exclusive(self):
        """Serialize journal access across threads (RLock) and processes (flock on a sidecar)."""
        with self._lock:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            with open(self.path + ".lock", "a") as f:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_EX)
                self._depth = 1
                try:
                    yield
                finally:
                    self._depth = 0
                    if fcntl:
                        fcntl.flock(f, fcntl.LOCK_UN)

    def append(self, kind, effect_id, **data):
        with self._exclusive():
            prior = self.entries(effect_id)
            entry = _seal({"ts": time.time(), "kind": kind, "effect_id": effect_id, **data}, prior[-1] if prior else None)
            with open(self.path, "a") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())        # durable before we return
        return entry

    def entries(self, effect_id=None):
        with self._exclusive(), open(self.path) as f:
            es = [json.loads(l) for l in f if l.strip()]
        return [e for e in es if effect_id is None or e["effect_id"] == effect_id]

    def dispatch(self, effect_id, effect, **data):
        """Write DISPATCHED unless another worker already dispatched or resolved it. False if it did."""
        with self._exclusive():
            if _blocks_dispatch(self.entries(effect_id)):
                return False
            self.append("DISPATCHED", effect_id, effect=effect, **data)
            return True

    def claim(self, effect_id, owner):
        """Take responsibility for recovering an effect. First live claim wins; stale claims expire."""
        claims_path = self.path + ".claims"
        with self._exclusive():
            claims = {}
            if os.path.exists(claims_path):
                with open(claims_path) as f:
                    claims = json.load(f)
            held = claims.get(effect_id)
            if held and held["owner"] != owner and time.time() - held["ts"] < CLAIM_TTL:
                return False
            claims[effect_id] = {"owner": owner, "ts": time.time()}
            with open(claims_path, "w") as f:
                json.dump(claims, f)
            return True


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
                    db.execute("CREATE TABLE IF NOT EXISTS claims (effect_id TEXT PRIMARY KEY, owner TEXT NOT NULL, ts REAL NOT NULL)")
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

    def entries(self, effect_id=None):
        with contextlib.closing(self._connect()) as db:
            if effect_id is None:
                rows = db.execute("SELECT body FROM entries ORDER BY seq")
            else:
                rows = db.execute("SELECT body FROM entries WHERE effect_id = ? ORDER BY seq", (effect_id,))
            return [json.loads(body) for (body,) in rows]

    def dispatch(self, effect_id, effect, **data):
        with contextlib.closing(self._connect()) as db:
            db.isolation_level = None
            db.execute("BEGIN IMMEDIATE")            # takes the write lock before reading
            entries = [json.loads(b) for (b,) in db.execute("SELECT body FROM entries WHERE effect_id = ? ORDER BY seq", (effect_id,))]
            if _blocks_dispatch(entries):
                db.execute("ROLLBACK")
                return False
            self._insert(db, "DISPATCHED", effect_id, {"effect": effect, **data})
            db.execute("COMMIT")
            return True

    def claim(self, effect_id, owner):
        now = time.time()
        with contextlib.closing(self._connect()) as db, db:
            cur = db.execute(
                "INSERT INTO claims (effect_id, owner, ts) VALUES (?, ?, ?) "
                "ON CONFLICT (effect_id) DO UPDATE SET owner = excluded.owner, ts = excluded.ts "
                "WHERE claims.owner = excluded.owner OR claims.ts < ?",
                (effect_id, owner, now, now - CLAIM_TTL))
            return cur.rowcount == 1


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
    canonical = json.dumps(key if key is not None else proposal["effect"], sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
