"""
    python3 -m unittest tests.test_demo_standalone

Offline checks for backend/standalone.py and backend/standalone_worker.py: nothing they import pulls in temporalio,
the one-run guard is shared with the Temporal demo, the mock run is labeled, and the worker's saved decision and
refund step behave as described, against a fake Stripe. No Stripe, model, Temporal or worker process.
"""
import os, subprocess, sys, tempfile, time, unittest
from unittest import mock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend import demo, standalone, standalone_worker as worker
from interlock import Leases


class FakeApi:
    class BadRequest(ValueError):
        pass


class FakeStripe:
    def __init__(self, refunds=()):
        self.refunds, self.posts = list(refunds), []

    def request(self, method, path, params=None, idempotency_key=None):
        if method == "GET":
            return {"data": list(self.refunds)}
        self.posts.append((params, idempotency_key))
        r = {"id": f"re_{len(self.refunds)}", "amount": params["amount"], "status": "succeeded",
             "metadata": params.get("metadata", {}), "created": len(self.refunds)}
        self.refunds.append(r)
        return {**r, "_replayed": False}


class Died(BaseException):
    pass


CASE = {"case_id": "case-1", "payment_intent": "pi_1", "lease_id": "approval/case-1", "customer_text": "approve $20"}
DECISION = {"amount_cents": 2000, "reason": "jar", "model": "m", "premises": {"payment_intent": "pi_1", "refunded_by_others": 0}}
HAND = {"id": "re_hand", "amount": 2000, "status": "succeeded", "metadata": {}, "created": 0}


def wait_done(view):
    run = standalone.RUNS[view["id"]]
    for _ in range(300):
        if run.done:
            return run
        time.sleep(0.01)
    raise AssertionError("run did not finish")


class Standalone(unittest.TestCase):
    def test_nothing_it_imports_pulls_in_temporalio(self):
        code = "import sys, backend.standalone, backend.standalone_worker; print('temporalio' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "False", out.stderr)

    def test_info_has_the_temporal_demo_fields_and_its_own_columns(self):
        with mock.patch.object(demo.config, "stripe_key", return_value=None):
            got, theirs = standalone.info(), demo.info()
        self.assertLessEqual(set(theirs), set(got))
        self.assertEqual(list(got["columns"]), ["standard", "checked", "interlock"])
        self.assertIsNone(got["temporal_ui"])
        self.assertFalse([k for k, s in got["scenarios"].items() if "Temporal" in s["story"]])
        self.assertIn("Temporal retries", theirs["scenarios"]["hand_refund_during_outage"]["story"])    # /demo unchanged

    def test_one_run_at_a_time_across_both_demos(self):
        self.assertTrue(demo.BUSY.acquire(blocking=False))
        try:
            with self.assertRaises(demo.Busy):
                standalone.start({"kind": "mock"}, FakeApi)
        finally:
            demo.BUSY.release()
        with self.assertRaises(FakeApi.BadRequest):
            standalone.start({"kind": "sideways"}, FakeApi)
        with self.assertRaises(LookupError):
            standalone.view("nope", 0)

    def test_mock_run_is_the_simulation_and_says_so(self):
        run = wait_done(standalone.start({"kind": "mock", "scenario": "hand_refund_during_outage", "hand_check": True}, FakeApi))
        self.assertIsNone(run.error)
        self.assertEqual(run.modes, ("standard", "interlock"))
        self.assertTrue(run.events and all(e["mock"] and e["text"].startswith("MOCK.") for e in run.events))
        results = {e["col"]: e["data"] for e in run.events if e["kind"] == "result"}
        self.assertEqual((results["standard"]["headline"], results["standard"]["held"]), ("$40 refunded (simulated)", False))
        self.assertEqual((results["interlock"]["headline"], results["interlock"]["held"]), ("$20 refunded (simulated)", True))
        self.assertTrue(all(c["title"].endswith("simulated") for c in run.view()["columns"]))
        self.assertNotIn(run.id, demo.RUNS)         # the Temporal page never picks up a standalone run

    def test_decision_is_saved_once_and_a_restart_loads_it(self):
        leases = mock.Mock(is_live=mock.Mock(return_value=True), max_cents=mock.Mock(return_value=2000))
        decided = {"amount_cents": 2000, "reason": "jar", "model": "m", "tool_call": {}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(worker.agent, "decide", return_value=decided) as decide:
            task = os.path.join(tmp, "t")
            first = worker.decision(task, CASE, FakeStripe([HAND]), leases)
            again = worker.decision(task, CASE, FakeStripe(), leases)
            with open(task + ".notes") as f:
                notes = f.read()
        self.assertEqual(decide.call_count, 1)
        self.assertEqual(first, again)
        self.assertEqual(first["premises"]["refunded_by_others"], 2000)
        self.assertEqual(notes.count('"resumed"'), 1)

    def test_standard_and_checked_refund_steps(self):
        leases = mock.Mock(allows=mock.Mock(return_value=True))
        s = FakeStripe([HAND])
        self.assertEqual(worker.refund({**CASE, "mode": "standard"}, DECISION, s, leases), "REFUNDED")    # no re-check
        self.assertEqual(s.posts, [({"payment_intent": "pi_1", "amount": 2000, "metadata": {"case_id": "case-1"}}, "refund/case-1")])
        self.assertEqual(demo.who(s.refunds[-1]), "sent by the agent's worker")
        self.assertEqual(worker.refund({**CASE, "mode": "checked"}, DECISION, s, leases), "FOUND_BY_LOOKUP")
        self.assertEqual(worker.refund({**CASE, "mode": "checked"}, DECISION, FakeStripe([HAND]), leases), "REFUSED:stale_premise")
        leases.allows.return_value = False
        self.assertEqual(worker.refund({**CASE, "mode": "checked"}, DECISION, FakeStripe(), leases), "REFUSED:lease")

    def test_interlock_restart_refuses_after_a_hand_refund(self):
        leases, s, case = Leases(), FakeStripe(), {**CASE, "mode": "interlock"}
        leases.grant(case["lease_id"])

        def crash(point):
            if point == "before_send":
                raise Died(point)                   # the process is gone: no release, no COMMITTED
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(worker.config, "DATA", tmp), \
                mock.patch.object(worker.config, "CLAIM_TTL", 0.2):
            with mock.patch.object(worker.config, "crash_once", side_effect=crash), self.assertRaises(Died):
                worker.refund(case, DECISION, s, leases)
            self.assertEqual(worker.refund(case, DECISION, s, leases), "IN_FLIGHT")    # the dead send's claim holds
            s.refunds.append(HAND)
            time.sleep(0.3)
            self.assertEqual(worker.refund(case, DECISION, s, leases), "REFUSED:stale_premise_at_recovery")
        self.assertEqual(s.posts, [])


if __name__ == "__main__":
    unittest.main()
