"""
    python3 -m unittest tests.test_demo

Offline checks for backend/demo.py: the verdict and wording shown on the page, the one-run-at-a-time guard, and
that a mock run is the in-process simulation with every event marked mock. For backend/api.py: its routes for both
demos (the standalone engine stubbed), Temporal unavailable, one run across both demos, and that the server starts
without temporalio. No Stripe, model or Temporal.
"""
import contextlib, http.client, importlib.util, json, os, signal, socket, subprocess, sys, tempfile, threading, time, types, unittest
from unittest import mock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
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

    def test_stripe_client_is_made_only_when_stripe_is_read(self):
        # config.stripe may run `stripe config --list`, so polls between reads must not create a client
        made, client = [], mock.Mock()
        client.request.return_value = {"data": []}
        watch = demo.Watch(None, {"mode": "standard", "case_id": "case-1", "payment_intent": "pi_1"}, lambda *a, **k: None)
        factory = lambda: made.append(1) or client
        watch.follow(factory, True)
        for _ in range(5):
            watch.follow(factory)
        self.assertEqual((len(made), client.request.call_count), (1, 1))

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

        def drive(run, api, live=None):
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


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from backend import api
        cls.api = api
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def send(self, method, path, headers=None, body=None, raw=False):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        if method == "POST" and headers is None:
            headers, body = {"Content-Type": "application/json"}, json.dumps(body)
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read()
        return r.status, (data.decode() if raw else json.loads(data))


class ApiRequestChecks(Server):
    """A page on another site, or a DNS-rebound name, cannot drive the API. No run is started."""

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


def page(name):
    with open(os.path.join(ROOT, "demo", name)) as f:
        return f.read()


def stub_standalone():
    """backend/standalone.py's interface, holding demo.BUSY for its run the way the engine must."""
    def start(body, api):
        if body.get("kind") not in ("live", "mock"):
            raise api.BadRequest("need kind live|mock")
        if not demo.BUSY.acquire(blocking=False):
            raise demo.Busy("a run is already going; wait for it to finish")
        return {"id": "stub1", "kind": body["kind"]}

    def view(run_id, after):
        if run_id != "stub1":
            raise LookupError(f"no run {run_id}")
        return {"id": run_id, "after": after}
    return types.SimpleNamespace(info=lambda: {"scenarios": {}, "live_missing": [], "latest": None}, start=start, view=view)


class ApiRoutes(Server):
    def setUp(self):
        patches = [mock.patch.dict(sys.modules, {"backend.standalone": stub_standalone()}),
                   mock.patch.object(self.api, "UNAVAILABLE", "temporalio is not installed")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_pages(self):
        standalone = page("standalone.html")
        for path in ("/", "/demo/standalone", "/demo/standalone/"):
            self.assertEqual(self.send("GET", path, raw=True), (200, standalone), path)
        self.assertIn('href="/demo">Already on Temporal? See the Temporal demo', standalone)
        self.assertIn('"/demo/standalone"', standalone)
        self.assertEqual(self.send("GET", "/demo", raw=True), (200, page("index.html")))

    def test_standalone_routes(self):
        self.assertEqual(self.send("GET", "/demo/standalone/info"), (200, {"scenarios": {}, "live_missing": [], "latest": None}))
        self.assertEqual(self.send("POST", "/demo/standalone/runs", body={"kind": "sideways"})[0], 400)
        try:
            self.assertEqual(self.send("POST", "/demo/standalone/runs", body={"kind": "live"}), (200, {"id": "stub1", "kind": "live"}))
        finally:
            demo.BUSY.release()
        self.assertEqual(self.send("GET", "/demo/standalone/runs/stub1/3"), (200, {"id": "stub1", "after": 3}))
        self.assertEqual(self.send("GET", "/demo/standalone/runs/nope/0")[0], 404)

    def test_temporal_unavailable(self):
        status, info = self.send("GET", "/demo/info")
        self.assertEqual((status, info["temporal_unavailable"]), (200, "temporalio is not installed"))
        self.assertEqual(self.send("GET", "/health")[1]["temporal_serving"], False)
        for method, path, body in (("POST", "/demo/runs", {"kind": "live"}), ("POST", "/cases", {}), ("GET", "/cases/case-1", None)):
            status, answer = self.send(method, path, body=body)
            self.assertEqual(status, 400, path)
            self.assertIn("/demo/standalone", answer["error"])
        self.assertIn("info.temporal_unavailable", page("index.html"))
        self.assertIn('href: "/demo/standalone"', page("index.html"))

    def test_one_run_across_both_demos(self):
        self.assertEqual(self.send("POST", "/demo/standalone/runs", body={"kind": "mock"})[0], 200)
        try:
            self.assertEqual(self.send("POST", "/demo/runs", body={"kind": "mock"})[0], 409)
        finally:
            demo.BUSY.release()
        release = threading.Event()

        def drive(run, api, live=None):
            release.wait(5)
            run.done = True
            demo.BUSY.release()
        with mock.patch.object(demo, "_drive", drive):
            self.assertEqual(self.send("POST", "/demo/runs", body={"kind": "mock"})[0], 200)
            try:
                self.assertEqual(self.send("POST", "/demo/standalone/runs", body={"kind": "mock"})[0], 409)
            finally:
                release.set()
        self.assertTrue(demo.BUSY.acquire(timeout=5))
        demo.BUSY.release()


class NoTemporal(unittest.TestCase):
    def test_server_modules_import_without_temporalio(self):
        names = ["backend.api"] + (["backend.standalone"] if importlib.util.find_spec("backend.standalone") else [])
        code = ("import sys; sys.modules['temporalio'] = None; sys.path.insert(0, sys.argv[1]); "     # None: import raises
                "import importlib; [importlib.import_module(n) for n in sys.argv[2:]]")
        r = subprocess.run([sys.executable, "-c", code, ROOT] + names, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipIf(importlib.util.find_spec("temporalio"), "checks the start without temporalio installed")
    def test_serve_starts_without_temporalio(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = {**os.environ, "INTERLOCK_DATA": tempfile.mkdtemp()}
        serve = subprocess.Popen([sys.executable, os.path.join(ROOT, "demo", "serve.py"), "--port", str(port)], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            for _ in range(100):
                with contextlib.suppress(OSError):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    conn.request("GET", "/demo/info")
                    info = json.loads(conn.getresponse().read())
                    break
                time.sleep(0.2)
            else:
                self.fail("demo/serve.py did not serve")
            self.assertEqual(info["temporal_unavailable"], "temporalio is not installed")
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/")
            r = conn.getresponse()
            self.assertEqual((r.status, b"Already on Temporal?" in r.read()), (200, True))
        finally:
            os.killpg(serve.pid, signal.SIGINT)          # serve.py stops the API's process group on the way out
            serve.wait(30)


if __name__ == "__main__":
    unittest.main()
