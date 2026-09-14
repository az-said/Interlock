"""
    python3 -m unittest tests.test_demo

Offline checks for backend/demo.py: the verdict and wording shown on the page, the one-run-at-a-time guard, and
that a mock run is the in-process simulation with every event marked mock. No Stripe, model or Temporal.
"""
import http.client, importlib.util, json, os, sys, threading, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import demo


class FakeApi:
    class BadRequest(ValueError):
        pass


def wait_done(view):
    run = demo.RUNS[view["id"]]
    for _ in range(200):
        if run.done:
            return run
        time.sleep(0.01)
    raise AssertionError("run did not finish")


class Demo(unittest.TestCase):
    def test_headline_counts_refund_objects_not_just_money(self):
        self.assertEqual(demo.headline([2000, 2000], 2000, 1), (False, "2 refunds, $40.00 refunded", "Violated: $20.00 too much"))
        self.assertEqual(demo.headline([2000], 2000, 1), (True, "1 refund, $20.00 refunded", "Held"))
        self.assertEqual(demo.headline([], 0, 0), (True, "0 refunds, $0.00 refunded", "Held"))
        self.assertEqual(demo.headline([1000, 1000], 2000, 1)[2], "Violated: wrong number of refunds")
        self.assertEqual(demo.headline([], 2000, 1)[2], "Short by $20.00")

    def test_result_reads_stripe_and_the_receipt(self):
        sc = demo.SCENARIOS["hand_refund_during_outage"]
        wf = {"workflow_id": "refund-case-1", "status": "COMPLETED", "attempts": {"refund": 2}}
        refunds = [{"id": "re_b", "amount": 2000, "status": "succeeded", "metadata": {"workflow_id": "refund-case-1"}, "created": 2},
                   {"id": "re_a", "amount": 2000, "status": "succeeded", "metadata": {}, "created": 1},
                   {"id": "re_x", "amount": 2000, "status": "failed", "metadata": {}, "created": 3}]
        state = {"workflow": {**wf, "result": {"outcome": "REFUNDED"}},
                 "stripe": {"payment_intent": "pi_1", "refunds": refunds}, "interlock": None}
        d = demo.result_data(state, sc, "temporal")
        self.assertEqual(([r["id"] for r in d["refunds"]], d["held"], d["refunded_cents"]), (["re_a", "re_b"], False, 4000))
        self.assertEqual(d["refunds"][0]["by"], "no metadata: the hand refund")
        self.assertIsNone(d["receipt"])

        verification = {"valid": True, "tamper_evident": True, "signed": None, "happened": False, "happened_once": True,
                        "authorized_when_fired": None, "assumptions_held": None, "refused": "stale_premise at recovery",
                        "evidence": None, "problems": [],
                        "rechecked_at_recovery": {"lease_live": True, "violations": ["refunded by others: was 0, now 2000"]}}
        state = {"workflow": {**wf, "result": {"outcome": "REFUSED:stale_premise_at_recovery"}},
                 "stripe": {"payment_intent": "pi_2", "refunds": refunds[1:]},
                 "interlock": {"effect_id": "e1", "verification": verification,
                               "bundle": {"summary": {"final": "REFUSED"}, "entries": [{"kind": "PROPOSED"}, {"kind": "REFUSED"}]}}}
        d = demo.result_data(state, sc, "interlock")
        self.assertTrue(d["held"])
        self.assertEqual((d["receipt"]["final"], d["receipt"]["entries"]), ("REFUSED", ["PROPOSED", "REFUSED"]))
        self.assertIn("Interlock refused at recovery", d["why"])
        self.assertIn("was 0, now 2000", d["why"])

    def test_journal_lines(self):
        refused = {"kind": "REFUSED", "reason": "stale_premise at recovery",
                   "rechecked": {"lease_live": True, "violations": ["refunded by others: was 0, now 2000"]}}
        self.assertEqual(demo.journal_text(refused), "REFUSED: stale_premise at recovery, refunded by others: was 0, now 2000")
        dispatched = {"kind": "DISPATCHED", "checks": {"lease_live": True, "lease": {"max_cents": 2000}, "violations": []}}
        self.assertIn("capped at $20.00", demo.journal_text(dispatched))
        committed = {"kind": "COMMITTED", "via": "recovery-query", "found": "re_1"}
        self.assertEqual(demo.journal_text(committed), "COMMITTED via recovery-query: refund re_1")
        self.assertEqual(demo.explain("temporal_checked", "REFUSED:lease"),
                         "The hand-written check refused: the approval was revoked while the worker was down.")

    def test_one_run_at_a_time(self):
        release = threading.Event()

        def drive(run, api):
            release.wait(5)
            run.done = True
            demo.BUSY.release()
        first = demo.start({"kind": "mock"}, FakeApi, drive=drive)
        with self.assertRaises(demo.Busy):
            demo.start({"kind": "mock"}, FakeApi, drive=drive)
        release.set()
        wait_done(first)
        with self.assertRaises(FakeApi.BadRequest):
            demo.start({"kind": "sideways"}, FakeApi)

    def test_live_needs_keys_and_says_which(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(demo.config, "stripe_key", return_value=None):
            with self.assertRaises(FakeApi.BadRequest) as e:
                demo.start({"kind": "live"}, FakeApi)
        self.assertIn("ANTHROPIC_API_KEY", str(e.exception))
        self.assertNotIn("sk_", str(e.exception))

    def test_elapsed_stops_when_the_run_ends(self):
        run = wait_done(demo.start({"kind": "mock"}, FakeApi))
        first = run.view()["elapsed"]
        time.sleep(0.25)
        self.assertEqual(run.view()["elapsed"], first)

    def test_live_workers_never_get_crash_or_emulation_switches(self):
        env = {"INTERLOCK_EMULATE_24H": "1", "INTERLOCK_NO_LOOKUP": "1", "INTERLOCK_CRASH": "before_send",
               "INTERLOCK_CRASH_MARKER": "/tmp/x", "INTERLOCK_CLAIM_TTL": "15"}
        with mock.patch.dict(os.environ, env):
            got = demo.worker_env("q")
        self.assertEqual([k for k in env if k in got], ["INTERLOCK_CLAIM_TTL"])
        self.assertEqual(got["INTERLOCK_TASK_QUEUE"], "q")

    def test_mock_run_is_the_simulation_and_says_so(self):
        from experiments import refund_agent
        real = refund_agent.run
        without_trace = lambda *a, **k: {x: v for x, v in real(*a, **k).items() if x != "trace"}
        with mock.patch.object(refund_agent, "run", side_effect=without_trace):    # the mock must not need the viewer's trace
            run = wait_done(demo.start({"kind": "mock", "scenario": "hand_refund_during_outage", "hand_check": True}, FakeApi))
        for col in run.modes:
            self.assertGreaterEqual(sum(1 for e in run.events if e["col"] == col and e["kind"] in ("sim", "journal")), 4, col)
        self.assertIsNone(run.error)
        self.assertEqual(run.modes, ("temporal", "interlock"))           # no simulated hand-written check column
        self.assertTrue(run.events and all(e["mock"] and e["text"].startswith("MOCK.") for e in run.events))
        results = {e["col"]: e["data"] for e in run.events if e["kind"] == "result"}
        self.assertEqual((results["temporal"]["headline"], results["temporal"]["held"]), ("$40 refunded (simulated)", False))
        self.assertEqual((results["interlock"]["headline"], results["interlock"]["held"]), ("$20 refunded (simulated)", True))
        self.assertTrue(run.view()["mock"] and all(c["title"].endswith("simulated") for c in run.view()["columns"]))
        self.assertEqual(sum(1 for e in run.events if e["col"] == "interlock" and "dies" in e["text"]), 1)

        revoked = wait_done(demo.start({"kind": "mock", "scenario": "approval_revoked_during_outage"}, FakeApi))
        self.assertEqual({e["col"]: e["data"]["outcome"] for e in revoked.events if e["kind"] == "result"},
                         {"temporal": "RERUN:ok", "interlock": "REFUSED:lease_at_recovery"})


@unittest.skipUnless(importlib.util.find_spec("temporalio"), "backend/api.py needs temporalio")
class ApiRequestChecks(unittest.TestCase):
    """A page on another site, or a DNS-rebound name, cannot drive the API. No run is started."""
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from backend import api
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def send(self, method, path, headers, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        conn.request(method, path, body=body, headers=headers)
        r = conn.getresponse()
        return r.status, json.loads(r.read())

    def test_checks(self):
        host = f"127.0.0.1:{self.server.server_port}"
        bad = json.dumps({"kind": "sideways"})          # reaches demo.start only when every check passes: 400, no run
        self.assertEqual(self.send("POST", "/demo/runs", {"Host": host, "Content-Type": "text/plain"}, bad)[0], 403)
        self.assertEqual(self.send("POST", "/demo/runs", {"Host": host, "Content-Type": "application/json",
                                                          "Origin": "http://localhost:" + str(self.server.server_port)}, bad)[0], 403)
        self.assertEqual(self.send("POST", "/demo/runs", {"Host": host, "Content-Type": "application/json",
                                                          "Origin": "http://evil.example"}, bad)[0], 403)
        self.assertEqual(self.send("GET", "/health", {"Host": "evil.example:" + str(self.server.server_port)})[0], 403)
        self.assertEqual(self.send("POST", "/demo/runs", {"Host": host, "Content-Type": "application/json",
                                                          "Origin": "http://" + host}, bad)[0], 400)
        self.assertEqual(self.send("POST", "/demo/runs", {"Host": host, "Content-Type": "application/json"}, bad)[0], 400)


if __name__ == "__main__":
    unittest.main()
