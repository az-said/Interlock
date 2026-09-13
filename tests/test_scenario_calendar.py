"""Offline logic for scenarios/calendar: an in-memory calendar stands in; the live run uses Google Calendar and SIGKILL."""
import os, re, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scenarios", "calendar"))
import booking                              # noqa: E402
from interlock.gate import SimulatedCrash   # noqa: E402

SLOT = "2026-10-14T15:00:00Z"
DECISION = {"start": SLOT, "end": "2026-10-14T15:30:00Z", "summary": "Call with Dana"}


class FakeCalendar:
    """The calls the scenario makes, with Calendar's 409 on a taken id."""
    calendar_id = "cal"

    def __init__(self):
        self.events = {}

    def insert(self, event):
        eid = event.get("id") or f"auto{len(self.events)}"
        if eid in self.events:
            raise booking.CalendarError(409, "The requested identifier already exists.")
        self.events[eid] = {**event, "id": eid, "status": "confirmed", "created": f"2026-09-13T00:00:{len(self.events):02d}Z"}
        return self.events[eid]

    def get(self, eid):
        return self.events.get(eid)

    def list(self, tmin, tmax):
        return [e for e in self.events.values() if booking.is_live(e) and booking.parse(e["start"]["dateTime"]) <
                booking.parse(tmax) and booking.parse(tmin) < booking.parse(e["end"]["dateTime"])]

    def busy(self, tmin, tmax):
        return [{"start": e["start"]["dateTime"], "end": e["end"]["dateTime"]} for e in self.list(tmin, tmax)]


def run(system, crash, action):
    cal, data = FakeCalendar(), tempfile.mkdtemp()
    booking.write_request(data, {"id": "r1", "slot_start": SLOT, "status": "live", "text": ""})
    extra = {"journal_dir": os.path.join(data, "journal")} if system.startswith("interlock") else {}
    customer = {"summary": "customer", "start": {"dateTime": SLOT}, "end": {"dateTime": DECISION["end"]}}
    fired, placed = [], []

    def crash_once(point):
        if point == crash and not fired:
            fired.append(point)
            raise SimulatedCrash(point)     # offline only: the live worker SIGKILLs itself here

    def put_customer():
        placed.extend(e["id"] for e in cal.list(SLOT, DECISION["end"]))
        cal.insert(customer)

    if action == "pre_busy":
        put_customer()
    try:
        booking.SYSTEMS[system](cal, data, "r1", DECISION, crash_once, **extra)
    except SimulatedCrash:
        pass
    if action != "pre_busy" and not fired:
        raise AssertionError("the crash never fired")
    if action == "slot_busy":
        put_customer()
    if action == "request_cancelled":
        booking.write_request(data, {"id": "r1", "slot_start": SLOT, "status": "cancelled", "text": ""})
    result = booking.SYSTEMS[system](cal, data, "r1", DECISION, crash_once, **extra)
    return result, booking.grade(list(cal.events.values()), "r1", booking.WANT[(crash, action)], result["answer"], placed)


class CalendarScenario(unittest.TestCase):
    def test_no_check_replays_a_queued_send_without_rechecking(self):
        for crash, action in booking.FAULTS:
            result, g = run("no_check", crash, action)
            self.assertEqual(g["invariant_held"], crash == "after_commit" or action in ("none", "pre_busy"),
                             (crash, action))
        self.assertTrue(run("no_check", "before_send", "slot_busy")[1]["double_booked"])
        self.assertEqual(run("no_check", "before_send", "pre_busy")[0]["outcome"], "REFUSED:slot_busy")

    def test_hand_check_and_interlock_hold_every_fault(self):
        for system in ("hand_check", "interlock"):
            for crash, action in booking.FAULTS:
                result, g = run(system, crash, action)
                self.assertTrue(g["invariant_held"], (system, crash, action, result["outcome"]))
                self.assertTrue(g["answer_matches_calendar"], (system, crash, action))

    def test_a_change_only_premise_books_over_a_slot_taken_before_the_decision(self):
        result, g = run("interlock_change_only", "before_send", "pre_busy")
        self.assertEqual(result["outcome"], "COMMITTED_BY_RETRY")
        self.assertTrue(g["double_booked"])

    def test_interlock_recovery_paths_and_receipts(self):
        want = {("before_send", "slot_busy"): "REFUSED:stale_premise_at_recovery",
                ("before_send", "request_cancelled"): "REFUSED:lease_at_recovery",
                ("before_send", "pre_busy"): "REFUSED:stale_premise",
                ("after_commit", "request_cancelled"): "COMMITTED_ON_QUERY",
                ("after_commit", "slot_busy"): "COMMITTED_ON_QUERY",
                ("after_commit", "none"): "COMMITTED_BY_RETRY"}
        for (crash, action), outcome in want.items():
            result, _ = run("interlock", crash, action)
            self.assertEqual(result["outcome"], outcome)
            self.assertTrue(result["receipt"]["valid"], result["receipt"]["problems"])
        # the retry after a commit got a 409: the receipt says the event already existed, not that the retry made it
        evidence = run("interlock", "after_commit", "none")[0]["receipt"]["evidence"]
        self.assertTrue(evidence["already_existed"])
        self.assertEqual(run("interlock", "after_commit", "slot_busy")[0]["receipt"]["evidence"]["status"], "confirmed")

    def test_decision_must_match_the_request(self):
        req = {"slot_start": SLOT}
        self.assertEqual(booking.validate_decision({"start": SLOT, "duration_minutes": 30, "summary": " x "}, req)["end"],
                         DECISION["end"])
        for bad in ({"start": "2026-10-14T16:00:00Z", "duration_minutes": 30, "summary": "x"},
                    {"start": SLOT, "duration_minutes": 60, "summary": "x"},
                    {"start": "2026-10-14T15:00:00", "duration_minutes": 30, "summary": "x"},
                    {"start": SLOT, "duration_minutes": 30, "summary": ""}):
            with self.assertRaises(ValueError):
                booking.validate_decision(bad, req)

    def test_event_ids_are_base32hex(self):
        self.assertRegex(booking.stable_event_id("any-request"), re.compile(r"^[0-9a-v]{5,1024}$"))


if __name__ == "__main__":
    unittest.main()
