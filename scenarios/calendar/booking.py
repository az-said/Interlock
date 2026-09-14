"""
Double booking on Google Calendar: one booking request, one 30-minute call, three ways to send it.

    no_check    a durable job queue, the standard setup: when the job is enqueued the request must be live and
                freebusy must show the slot free, then the send is queued with a client-supplied event id
                (Calendar's native dedup: a second insert with that id is a 409). A restart replays the queued
                send; nothing is re-read.
    hand_check  the same id, plus what a careful engineer writes at the top of the send: look the event up by its
                id first (so a restart after a commit reports the booking instead of refusing on its own event),
                then refuse if the request is no longer live or freebusy shows the slot taken. Runs on every
                attempt, restarts included.
    interlock   the same insert behind interlock.easy: the request is the authority, "other events in the slot"
                is the premise and must be [] when decided (see _gate_target), the event id is the effect id,
                Calendar's 409 is the dedup, events.get the lookup
    interlock_change_only
                interlock.easy as it ships: the premise only has to stay unchanged, so a slot already taken when
                the job was decided is not refused. Run on the pre_busy row only, to show the difference.

Standard library only. `crash(point)` is called right before the insert and right after it returns; the live
worker SIGKILLs itself there, the offline tests raise SimulatedCrash.
"""
import datetime, functools, hashlib, json, os, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from interlock.easy import Interlock          # noqa: E402
from interlock.journal import effect_id_for    # noqa: E402
from interlock.receipts import bundle, verify  # noqa: E402

API = "https://www.googleapis.com/calendar/v3"
TIMEOUT = 10            # every Calendar call; a send (insert, maybe a get) finishes well inside CLAIM_TTL
CLAIM_TTL = 30          # a SIGKILLed sender's claim blocks recovery this long
DURATION = 30           # minutes


class CalendarError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"{code} {message}")
        self.code = code


class Calendar:
    def __init__(self, token, calendar_id):
        self.token, self.calendar_id = token, calendar_id

    def _req(self, method, path, body=None, query=None):
        url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
        req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            message = json.loads(e.read() or b"{}").get("error", {}).get("message")
            raise CalendarError(e.code, f"{method} {path}: {message}") from None

    def _events(self):
        return f"/calendars/{urllib.parse.quote(self.calendar_id)}/events"

    def insert(self, event):
        return self._req("POST", self._events(), event)

    def get(self, event_id):
        """The event (a deleted one reads back with status cancelled), or None."""
        try:
            return self._req("GET", f"{self._events()}/{event_id}")
        except CalendarError as e:
            if e.code == 404:
                return None
            raise

    def list(self, time_min, time_max):
        """events.list: every non-deleted event overlapping [time_min, time_max)."""
        return self._req("GET", self._events(), query={"timeMin": time_min, "timeMax": time_max, "singleEvents": "true",
                                                       "showDeleted": "false", "maxResults": 250})["items"]

    def busy(self, time_min, time_max):
        body = {"timeMin": time_min, "timeMax": time_max, "items": [{"id": self.calendar_id}]}
        return self._req("POST", "/freeBusy", body)["calendars"][self.calendar_id]["busy"]

    def delete(self, event_id):
        self._req("DELETE", f"{self._events()}/{event_id}")


# ---- the booking request (the authority): a small JSON file per request, standing in for a booking system

def request_path(data, rid):
    return os.path.join(data, f"request-{rid}.json")


def write_json(path, obj):
    with open(path + ".tmp", "w") as f:
        json.dump(obj, f)
    os.replace(path + ".tmp", path)


def write_request(data, request):
    write_json(request_path(data, request["id"]), request)


def read_request(data, rid):
    with open(request_path(data, rid)) as f:
        return json.load(f)


# ---- decisions and events

def rfc3339(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def validate_decision(args, request):
    """The model's book_call arguments, checked against the request. Returns {start, end, summary}."""
    try:
        start = parse(str(args["start"]))
    except (KeyError, ValueError):
        raise ValueError(f"start is not an RFC3339 time: {args.get('start')!r}") from None
    if start.tzinfo is None or start != parse(request["slot_start"]):
        raise ValueError(f"model chose {args['start']}, the request asks for {request['slot_start']}")
    if args.get("duration_minutes") != DURATION:
        raise ValueError(f"model chose {args.get('duration_minutes')!r} minutes, the request asks for {DURATION}")
    summary = str(args.get("summary") or "").strip()[:100]
    if not summary:
        raise ValueError("summary must be a non-empty string")
    return {"start": rfc3339(start), "end": rfc3339(start + datetime.timedelta(minutes=DURATION)), "summary": summary}


def stable_event_id(rid):
    """Calendar event ids are base32hex (0-9, a-v), 5 to 1024 chars. Hex digits are a subset."""
    return "bk" + hashlib.sha256(rid.encode()).hexdigest()[:26]


def event_body(event_id, rid, system, decision):
    return {"id": event_id, "summary": decision["summary"],
            "start": {"dateTime": decision["start"]}, "end": {"dateTime": decision["end"]},
            "extendedProperties": {"private": {"booking_request": rid, "system": system}}}


def is_live(event):
    return bool(event) and event.get("status") != "cancelled"


def _insert_or_existing(cal, event):
    """Insert with a client-supplied id; a 409 means that id already exists (Calendar's dedup)."""
    try:
        return cal.insert(event), False
    except CalendarError as e:
        if e.code != 409:
            raise
        return cal.get(event["id"]), True


# ---- the systems. Each returns {"outcome", "answer": booked|not_booked|unknown, ...}

def no_check(cal, data, rid, decision, crash):
    eid = stable_event_id(rid)
    queued = os.path.join(data, f"queued-{rid}.json")
    if not os.path.exists(queued):                                  # enqueue: checked once, when the job is decided
        if read_request(data, rid)["status"] != "live":
            return {"outcome": "REFUSED:request_cancelled", "answer": "not_booked", "event_id": eid}
        busy = cal.busy(decision["start"], decision["end"])
        if busy:
            return {"outcome": "REFUSED:slot_busy", "answer": "not_booked", "event_id": eid, "busy": busy}
        write_json(queued, {"event_id": eid, "decision": decision, "checked_at": time.time()})
    crash("before_send")                                            # a restart replays from here
    event, existed = _insert_or_existing(cal, event_body(eid, rid, "no_check", decision))
    crash("after_commit")
    return {"outcome": "ALREADY_EXISTS_409" if existed else "BOOKED", "answer": "booked", "event_id": eid}


def hand_check(cal, data, rid, decision, crash):
    eid = stable_event_id(rid)
    if is_live(cal.get(eid)):                                       # a restart after the insert landed
        return {"outcome": "FOUND_BY_LOOKUP", "answer": "booked", "event_id": eid}
    if read_request(data, rid)["status"] != "live":
        return {"outcome": "REFUSED:request_cancelled", "answer": "not_booked", "event_id": eid}
    busy = cal.busy(decision["start"], decision["end"])
    if busy:
        return {"outcome": "REFUSED:slot_busy", "answer": "not_booked", "event_id": eid, "busy": busy}
    crash("before_send")
    event, existed = _insert_or_existing(cal, event_body(eid, rid, "hand_check", decision))
    crash("after_commit")
    return {"outcome": "FOUND_BY_409" if existed else "BOOKED", "answer": "booked", "event_id": eid}


def event_evidence(event, already_existed=None):
    out = {"event": event["id"], "created": event.get("created"), "status": event.get("status")}
    return out if already_existed is None else {**out, "already_existed": already_existed}


def _gate_target(target, cal, require_free):
    """
    Two changes to interlock.easy's function target, made on this one instance because interlock/ is off limits
    here (the core change is proposed in the md):
      - require_free: a premise that must EQUAL [] when decided, not only stay unchanged. easy.py's
        validate_premises compares the saved value with the current one, so a slot already taken at decision
        time passes every check.
      - the COMMITTED result and the lookup keep Calendar's answer (event id, created, and already_existed=True
        when the insert was a 409), where easy.py records {"status": "ok"} and True.
    """
    validate, apply = target.validate_premises, target.apply

    def validate_premises(premises, eid=None):
        taken = (premises or {}).get("facts", {}).get("other_events_in_slot")
        must = [f"other_events_in_slot: must be [], was {taken!r} when decided"] if require_free and taken else []
        return validate(premises, eid) + must

    def apply_keeping_response(eid, effect, crash_after_effect=False):
        return {**apply(eid, effect, crash_after_effect), **target.results[eid]}

    def query(eid, effect):
        event = cal.get(eid)
        return event_evidence(event) if is_live(event) else False

    target.validate_premises, target.apply, target.query = validate_premises, apply_keeping_response, query


def interlock(cal, data, rid, decision, crash, journal_dir, claim_ttl=CLAIM_TTL, recover_for=120, require_free=True):
    gate = Interlock(journal_dir, claim_ttl=claim_ttl)

    def others(start, end, event_id):
        return sorted(e["id"] for e in cal.list(start, end) if e["id"] != event_id)

    @gate.effect(key=lambda r, start, end, summary: f"booking:{r}",
                 premises=lambda r, start, end, summary, idempotency_key: {
                     "other_events_in_slot": others(start, end, idempotency_key)},
                 lookup=lambda r, start, end, summary, idempotency_key: is_live(cal.get(idempotency_key)),
                 allowed=lambda r, *_: read_request(data, r)["status"] == "live",
                 dedupes=True, dedup_window=float("inf"))        # a client-supplied id stays taken, even after delete
    def book_call(r, start, end, summary, idempotency_key):
        crash("before_send")
        event, existed = _insert_or_existing(
            cal, event_body(idempotency_key, r, "interlock", {"start": start, "end": end, "summary": summary}))
        crash("after_commit")
        return event_evidence(event, existed)

    g, deadline, recovered = book_call.gate, time.time() + recover_for, {}
    _gate_target(g.target, cal, require_free)
    while True:                                                     # on startup: wait out a dead sender's claim
        for statuses in gate.recover().values():
            recovered.update(statuses)
        if not g.journal.in_flight() or time.time() > deadline:
            break
        time.sleep(1)

    args = (rid, decision["start"], decision["end"], decision["summary"])
    status, _ = book_call(*args)
    eid = effect_id_for(book_call.proposal(*args))
    receipt_bundle = bundle(g.journal, eid)
    receipt = verify(receipt_bundle)
    executed = g.journal.receipt(eid)["executed"]
    return {"outcome": recovered.get(eid) or status, "submit_status": status, "recovered": recovered.get(eid),
            "answer": {True: "booked", False: "not_booked"}.get(executed, "unknown"), "event_id": eid,
            "effect_id": eid, "receipt": receipt, "receipt_bundle": receipt_bundle,
            "journal": [{k: e[k] for k in ("kind", "via", "reason", "checks", "rechecked", "result", "found") if k in e}
                        for e in g.journal.entries(eid)]}


SYSTEMS = {"no_check": no_check, "hand_check": hand_check, "interlock": interlock,
           "interlock_change_only": functools.partial(interlock, require_free=False)}


# ---- ground truth

# (crash point, what happens outside the agent). pre_busy: the customer's event is on the slot before the job is
# decided; the others happen during the outage. The crash is armed on pre_busy too, but a system that refuses
# never reaches the send, so there it may not fire.
FAULTS = (("after_commit", "none"), ("after_commit", "slot_busy"), ("after_commit", "request_cancelled"),
          ("before_send", "none"), ("before_send", "slot_busy"), ("before_send", "request_cancelled"),
          ("before_send", "pre_busy"))
# agent events wanted on the calendar. After a commit the booking landed while the slot was free and the request
# live, so it stands (a cancellation handler or a person deals with it next). Before the send, a slot taken or a
# request cancelled means nothing may land.
WANT = {(c, a): 1 if c == "after_commit" or a == "none" else 0 for c, a in FAULTS}


def grade(events, rid, want, answer, placed_before_other=()):
    """
    placed_before_other: ids of events already on the slot when the harness put the other (customer) event there.
    Calendar's `created` has whole-second precision, so a customer insert and a replayed agent insert in the same
    second cannot be ordered from the events themselves; the harness lists the slot right before its insert instead.
    """
    live = [e for e in events if is_live(e)]
    mine = lambda e: e.get("extendedProperties", {}).get("private", {}).get("booking_request") == rid  # noqa: E731
    ours, others = [e for e in live if mine(e)], [e for e in live if not mine(e)]

    def overlaps(a, b):
        return parse(a["start"]["dateTime"]) < parse(b["end"]["dateTime"]) and \
               parse(b["start"]["dateTime"]) < parse(a["end"]["dateTime"])

    # double booking: the agent put its call on top of an event that was already there
    double = any(overlaps(e, o) and e["id"] not in placed_before_other for e in ours for o in others)
    return {"agent_events": [e["id"] for e in ours], "other_events": [e["id"] for e in others],
            "double_booked": double, "invariant_held": len(ours) == want and not double,
            # "unknown" (AMBIGUOUS) claims nothing, so it neither matches nor contradicts
            "answer_matches_calendar": {"booked": len(ours) == 1, "not_booked": len(ours) == 0}.get(answer)}
