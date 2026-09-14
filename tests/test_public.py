"""
    python3 -m unittest tests.test_public

Offline checks for public mode in backend/api.py (docs/deploy.md): settings, the Host allowlist, which
X-Forwarded-For entry is trusted, per-client and daily limits on a fake clock, /healthz, security headers, errors
without exception text, and that with public mode off none of it applies. No Stripe, model, Temporal or worker.
"""
import base64, contextlib, hashlib, http.client, json, os, socket, subprocess, sys, tempfile, threading, time, types, unittest
from http.server import ThreadingHTTPServer
from unittest import mock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend import api, demo
from interlock.targets.stripe_api import StripeError

ENV = {"INTERLOCK_PUBLIC": "1", "INTERLOCK_ALLOWED_HOSTS": "demo.example.com, Other.example"}
HOST = "demo.example.com"


class Clock:
    def __init__(self, t=86400 * 20000 + 3600):
        self.t = t

    def __call__(self):
        return self.t


def take(limiter, ip):
    with limiter.slot(ip):
        pass


def serve(test):
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server


def send(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=30)
    conn.request(method, path, body=None if body is None else json.dumps(body), headers=headers or {})
    r = conn.getresponse()
    return r.status, r.read(), r.headers


class Settings(unittest.TestCase):
    def test_off_unless_exactly_1(self):
        for env in ({}, {"INTERLOCK_PUBLIC": "0", "INTERLOCK_ALLOWED_HOSTS": HOST}, {"INTERLOCK_PUBLIC": "true"}):
            self.assertIsNone(api.public_settings(env))

    def test_defaults_and_bad_settings(self):
        s = api.public_settings(ENV)
        self.assertEqual((s.hosts, s.hops, s.port, s.live.per_hour, s.live.per_day, s.live.per_ip_day, s.mock.per_hour,
                          s.mock.per_day, s.mock.per_ip_day),
                         (frozenset({HOST, "other.example"}), 0, 8787, 3, 40, 6, 30, None, None))
        self.assertEqual(api.public_settings({**ENV, "INTERLOCK_LIVE_PER_IP_DAY": "2"}).live.per_ip_day, 2)
        self.assertEqual(api.public_settings({**ENV, "PORT": "8080"}).port, 8080)
        self.assertEqual(api.public_settings({**ENV, "PORT": "8080", "INTERLOCK_API_PORT": "9000"}).port, 9000)
        for bad in ({"INTERLOCK_ALLOWED_HOSTS": " , "}, {"INTERLOCK_TRUSTED_PROXY_HOPS": "-1"},
                    {"INTERLOCK_LIVE_PER_DAY": "lots"}):
            with self.assertRaises(ValueError):
                api.public_settings({**ENV, **bad})

    def test_host_allowlist(self):
        hosts = api.public_settings(ENV).hosts
        for ok in (HOST, "DEMO.example.com", HOST + ":443", "other.example"):
            self.assertTrue(api.host_allowed(ok, hosts), ok)
        for bad in (None, "", "evil.example", HOST + ".evil.example", "x." + HOST, HOST + ":", HOST + ":443:1",
                    "user@" + HOST, "127.0.0.1:8787", "localhost", "[::1]:8787"):
            self.assertFalse(api.host_allowed(bad, hosts), bad)

    def test_trusted_proxy_hops(self):
        peer = "10.0.0.9"
        self.assertEqual(api.client_ip(peer, ["203.0.113.7"], 0), peer)                          # hops 0: ignored
        self.assertEqual(api.client_ip(peer, None, 1), peer)
        self.assertEqual(api.client_ip(peer, ["203.0.113.7"], 1), "203.0.113.7")
        self.assertEqual(api.client_ip(peer, ["1.1.1.1, 203.0.113.7"], 1), "203.0.113.7")        # client-sent entry ignored
        self.assertEqual(api.client_ip(peer, ["1.1.1.1", "203.0.113.7"], 1), "203.0.113.7")      # two header lines
        self.assertEqual(api.client_ip(peer, ["1.1.1.1, 203.0.113.7, 10.1.1.1"], 2), "203.0.113.7")
        self.assertEqual(api.client_ip(peer, ["203.0.113.7"], 2), peer)                          # fewer entries than hops
        self.assertEqual(api.client_ip(peer, ["1.1.1.1, not-an-ip"], 1), peer)
        self.assertEqual(api.client_ip(peer, ["2001:db8::1"], 1), "2001:db8::1")

    def test_pages_say_live_runs_are_limited(self):
        for name in ("standalone.html", "index.html"):
            with open(os.path.join(ROOT, "demo", name), encoding="utf-8") as f:
                page = f.read()
            # the limit sentence is added only when /info says public, since local mode has no per-visitor limit
            self.assertIn('<p class="fineprint" id="fineprint">Live runs use Stripe test mode and a real model.</p>', page)
            self.assertIn('if (info.public) $("#fineprint").append(" Limited to a few runs per visitor.");', page)
            for anchor in ('id="notice"', 'id="live"', 'id="mock"', 'id="scenario"', 'id="status"', 'id="banner"'):
                self.assertIn(anchor, page)

    def test_serve_refuses_public_mode_without_hosts(self):
        env = {k: v for k, v in os.environ.items() if k != "INTERLOCK_ALLOWED_HOSTS"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "demo", "serve.py")], env={**env, "INTERLOCK_PUBLIC": "1"},
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("INTERLOCK_ALLOWED_HOSTS", r.stderr)


class Limits(unittest.TestCase):
    def test_per_client_sliding_hour(self):
        clock = Clock()
        live = api.Limiter("live", 3, 40, clock)
        for _ in range(3):
            take(live, "203.0.113.1")
            clock.t += 60
        with self.assertRaises(api.Limited) as e:
            take(live, "203.0.113.1")
        self.assertIn("3 live runs per visitor per hour", str(e.exception))
        self.assertIn("Run mock still works", str(e.exception))
        take(live, "203.0.113.2")                   # another client is not affected
        clock.t += 3600 - 180 + 1                   # the first start is now more than an hour old
        take(live, "203.0.113.1")
        with self.assertRaises(api.Limited):
            take(live, "203.0.113.1")

    def test_daily_cap_across_clients_resets_at_utc_midnight(self):
        clock = Clock(86400 * 20000 + 86400 - 10)
        live = api.Limiter("live", 3, 2, clock)
        take(live, "a")
        take(live, "b")
        with self.assertRaises(api.Limited) as e:
            take(live, "c")
        self.assertIn("2 live runs for today (UTC)", str(e.exception))
        clock.t += 10
        take(live, "c")

    def test_per_visitor_daily_cap_under_the_global_cap(self):
        clock = Clock(86400 * 20000)
        live = api.Limiter("live", 3, 40, clock, per_ip_day=6)
        for _ in range(6):
            take(live, "203.0.113.1")
            clock.t += 3601                         # never over the hourly limit
        with self.assertRaises(api.Limited) as e:
            take(live, "203.0.113.1")
        self.assertIn("6 live runs per visitor per day (UTC)", str(e.exception))
        take(live, "203.0.113.2")
        clock.t = 86400 * 20001                     # next UTC day
        take(live, "203.0.113.1")

    def test_ipv6_counts_by_64(self):
        self.assertEqual(api.visitor("2001:db8::1"), "2001:db8::/64")
        self.assertEqual(api.visitor("2001:db8:0:0:ffff::9"), "2001:db8::/64")
        self.assertEqual(api.visitor("2001:db8:0:1::1"), "2001:db8:0:1::/64")
        self.assertEqual(api.visitor("203.0.113.7"), "203.0.113.7")
        self.assertEqual(api.visitor("::ffff:203.0.113.7"), "::ffff:203.0.113.7")
        self.assertEqual(api.visitor("not-an-ip"), "not-an-ip")
        live = api.Limiter("live", 3, 40, Clock())
        for i in range(3):
            take(live, f"2001:db8::{i + 1}")
        with self.assertRaises(api.Limited):
            take(live, "2001:db8::abcd")
        take(live, "2001:db8:0:1::1")

    def test_a_start_that_fails_gives_its_slot_back(self):
        live = api.Limiter("live", 1, 1, Clock())
        for exc in (demo.Busy("busy"), api.BadRequest("bad")):
            with self.assertRaises(type(exc)):
                with live.slot("a"):
                    raise exc
        take(live, "a")
        with self.assertRaises(api.Limited):
            take(live, "b")


class PublicServer(unittest.TestCase):
    def setUp(self):
        settings = api.public_settings({**ENV, "INTERLOCK_TRUSTED_PROXY_HOPS": "1", "INTERLOCK_LIVE_PER_IP_HOUR": "2",
                                        "INTERLOCK_LIVE_PER_DAY": "3", "INTERLOCK_MOCK_PER_IP_HOUR": "4"}, Clock())
        self.started = []

        def start(body, a):
            if body.get("kind") not in ("live", "mock"):
                raise a.BadRequest("need kind live|mock")
            if body.get("fail") == "busy":
                raise demo.Busy("a run is already going; wait for it to finish")
            if body.get("fail") == "boom":
                raise RuntimeError("detail from deep inside, sk_test_notreal")
            if body.get("fail") == "stripe":
                raise StripeError("401 POST /refunds: Invalid API Key provided: sk_test_notreal")
            self.started.append(body["kind"])
            return {"id": "stub1"}
        stub = types.SimpleNamespace(info=lambda: {"scenarios": {}, "live_missing": [], "latest": None}, start=start,
                                     view=lambda run_id, after: {"id": run_id})
        for p in (mock.patch.object(api, "PUBLIC", settings), mock.patch.dict(sys.modules, {"backend.standalone": stub}),
                  mock.patch.object(api.traceback, "print_exc")):
            p.start()
            self.addCleanup(p.stop)
        self.server = serve(self)

    def post(self, body, client="203.0.113.1", origin="https://" + HOST, path="/demo/standalone/runs"):
        status, data, _ = send(self.server, "POST", path, body, {"Host": HOST, "Content-Type": "application/json",
                                                                 "Origin": origin, "X-Forwarded-For": f"198.51.100.9, {client}"})
        return status, json.loads(data)

    def test_healthz_answers_any_host_and_touches_nothing(self):
        with mock.patch.object(api.config, "stripe_key", side_effect=AssertionError("healthz read Stripe")), \
                mock.patch.object(api, "health", side_effect=AssertionError("healthz asked Temporal")):
            status, data, headers = send(self.server, "GET", "/healthz", headers={"Host": "10.0.0.5:8080"})
        self.assertEqual((status, json.loads(data)), (200, {"ok": True}))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_host_allowlist_and_security_headers(self):
        port = self.server.server_port
        for host in ("evil.example", f"127.0.0.1:{port}", f"localhost:{port}"):
            for path in ("/", "/demo/standalone/info"):
                self.assertEqual(send(self.server, "GET", path, headers={"Host": host})[0], 403, (host, path))
        status, page, headers = send(self.server, "GET", "/", headers={"Host": HOST})
        self.assertEqual(status, 200)
        script = page.split(b"<script>", 1)[1].split(b"</script>", 1)[0]
        digest = base64.b64encode(hashlib.sha256(script).digest()).decode()
        csp = headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn(f"script-src 'self' 'sha256-{digest}';", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual((headers["X-Content-Type-Options"], headers["Referrer-Policy"]), ("nosniff", "no-referrer"))
        status, _, headers = send(self.server, "GET", "/demo/standalone/info", headers={"Host": "Demo.Example.com"})
        self.assertEqual((status, headers["Content-Security-Policy"]), (200, "default-src 'none'; frame-ancestors 'none'"))

    def test_posts_only_from_the_https_origin(self):
        self.assertEqual(self.post({"kind": "mock"}, origin="http://" + HOST)[0], 403)
        self.assertEqual(self.post({"kind": "mock"}, origin="https://evil.example")[0], 403)
        self.assertEqual(self.post({"kind": "mock"})[0], 200)
        self.assertEqual(self.started, ["mock"])

    def test_cases_routes_are_off(self):
        for method, path in (("POST", "/cases"), ("GET", "/cases/case-1"), ("POST", "/cases/case-1/revoke"),
                             ("POST", "/cases/case-1/manual-refund")):
            self.assertEqual(self.post({}, path=path)[0] if method == "POST" else
                             send(self.server, method, path, headers={"Host": HOST})[0], 404, path)

    def test_limits_per_client_and_per_day(self):
        self.assertEqual([self.post({"kind": "live"})[0] for _ in range(2)], [200, 200])
        status, answer = self.post({"kind": "live"})
        self.assertEqual(status, 429)
        self.assertIn("2 live runs per visitor per hour", answer["error"])
        self.assertEqual(self.post({"kind": "live"}, client="203.0.113.99, 203.0.113.1")[0], 429)   # a spoofed entry left of the proxy's is ignored
        self.assertEqual(self.post({"kind": "mock"})[0], 200)                                      # mock counted apart
        with mock.patch.object(api.demo, "start", lambda body, a: {"id": "temporal1"}), \
                mock.patch.object(api, "UNAVAILABLE", None):                                # the Temporal demo shares the limit
            self.assertEqual(self.post({"kind": "live"}, client="203.0.113.2", path="/demo/runs"), (200, {"id": "temporal1"}))
        status, answer = self.post({"kind": "live"}, client="203.0.113.3")
        self.assertEqual(status, 429)
        self.assertIn("3 live runs for today (UTC)", answer["error"])
        self.assertEqual([self.post({"kind": "mock"})[0] for _ in range(4)], [200, 200, 200, 429])

    def test_busy_and_bad_requests_do_not_use_a_slot(self):
        for _ in range(3):
            self.assertEqual(self.post({"kind": "live", "fail": "busy"}), (409, {"error": api.BUSY_PUBLIC}))
            self.assertEqual(self.post({"kind": "sideways"})[0], 400)
        self.assertEqual([self.post({"kind": "live"})[0] for _ in range(2)], [200, 200])
        self.assertEqual(api.BUSY_PUBLIC, "a run is in progress, try again in about 30 seconds")

    def test_errors_carry_no_exception_text(self):
        self.assertEqual(self.post({"kind": "mock", "fail": "boom"}), (500, {"error": "internal error"}))
        self.assertEqual(self.post({"kind": "mock", "fail": "stripe"}), (502, {"error": "Stripe test mode returned an error"}))

    def test_info_says_public(self):
        status, data, _ = send(self.server, "GET", "/demo/standalone/info", headers={"Host": HOST})
        self.assertEqual((status, json.loads(data)["public"]), (200, True))

    def test_run_events_carry_no_exception_text(self):
        def live(run, mode):
            raise RuntimeError("detail from deep inside")
        with mock.patch.object(demo, "PUBLIC", True):
            run = demo.Run("live", "hand_refund_during_outage", ("temporal", "interlock"))
            demo._column(run, "temporal", None, live=live)
        self.assertEqual((run.events[-1]["text"], run.error), ("This column stopped: RuntimeError", "temporal: RuntimeError"))


class PublicModeOff(unittest.TestCase):
    def test_nothing_public_applies(self):
        self.assertIsNone(api.PUBLIC)
        server = serve(self)
        local = f"127.0.0.1:{server.server_port}"
        status, _, headers = send(server, "GET", "/healthz", headers={"Host": local})
        self.assertEqual((status, headers["Content-Security-Policy"]), (404, None))
        self.assertEqual(send(server, "GET", "/healthz", headers={"Host": "10.0.0.5:8080"})[0], 403)
        self.assertEqual(send(server, "GET", "/demo/info", headers={"Host": HOST})[0], 403)
        self.assertIsNone(send(server, "GET", "/", headers={"Host": local})[2]["Content-Security-Policy"])
        stub = types.SimpleNamespace(info=lambda: {"latest": None})
        with mock.patch.dict(sys.modules, {"backend.standalone": stub}):
            self.assertEqual(json.loads(send(server, "GET", "/demo/standalone/info", headers={"Host": local})[1]), {"latest": None})
        self.assertEqual(send(server, "POST", "/demo/runs", {"kind": "sideways"},
                              {"Host": local, "Content-Type": "application/json", "Origin": "https://" + local})[0], 403)


class Runs(unittest.TestCase):
    def test_only_the_last_runs_are_kept(self):
        runs, latest = {f"old{i}": types.SimpleNamespace(done=True) for i in range(60)}, [None]
        runs["old5"].done = False                   # an unfinished run is never dropped

        def drive(run, a, live):
            run.done = True
            demo.BUSY.release()
        view = demo.start({"kind": "mock"}, api, drive=drive, runs=runs, latest=latest)
        self.assertTrue(demo.BUSY.acquire(timeout=10))
        demo.BUSY.release()
        self.assertEqual(len(runs), demo.KEEP_RUNS)
        self.assertEqual((latest[0], list(runs)[-1]), (view["id"], view["id"]))
        self.assertIn("old5", runs)
        self.assertNotIn("old11", runs)
        self.assertIn("old12", runs)


class PublicProcess(unittest.TestCase):
    def test_serve_stops_the_api_on_sigterm(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = {**os.environ, **ENV, "PORT": str(port), "INTERLOCK_DATA": tempfile.mkdtemp(),
               "INTERLOCK_TEMPORAL_CLI": os.path.join(tempfile.mkdtemp(), "no-temporal")}   # fail fast if temporalio is installed
        env.pop("INTERLOCK_API_PORT", None)
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "demo", "serve.py")], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 60
            while True:
                with contextlib.suppress(OSError):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                    conn.request("GET", "/healthz")
                    if conn.getresponse().status == 200:
                        break
                self.assertLess(time.time(), deadline, "serve.py never answered /healthz")
                time.sleep(0.2)
            children = subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True).stdout.split()
            self.assertEqual(len(children), 1, children)
            api_pid = int(children[0])
            proc.terminate()                            # SIGTERM
            proc.wait(30)
            with self.assertRaises(ProcessLookupError):
                os.kill(api_pid, 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(30)

    def test_api_binds_all_interfaces_and_serves_healthz(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = {**os.environ, **ENV, "PORT": str(port), "INTERLOCK_DATA": tempfile.mkdtemp(),
               "INTERLOCK_TEMPORAL_UNAVAILABLE": "not in this test"}
        env.pop("INTERLOCK_API_PORT", None)
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "backend", "api.py")], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            self.assertIn(f"api on http://0.0.0.0:{port} ", proc.stdout.readline())
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/healthz")
            r = conn.getresponse()
            self.assertEqual((r.status, json.loads(r.read())), (200, {"ok": True}))
        finally:
            proc.terminate()
            proc.wait(30)
            proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
