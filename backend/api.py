"""
The refund backend over HTTP (stdlib ThreadingHTTPServer, JSON in and out).

    python backend/api.py [--port 8787]

    POST /cases                      {customer_text, paid_cents, approved_cents, mode}: a real test-mode
                                     payment, the approval lease granted for at most approved_cents,
                                     the RefundCase workflow started
    GET  /cases/{id}                 workflow status and attempts, Stripe ground truth re-read live,
                                     and for mode=interlock the receipt, its entries and verification
    POST /cases/{id}/revoke          withdraw the approval
    POST /cases/{id}/manual-refund   {amount_cents}: support refunds by hand, straight to Stripe, no key
    GET  /health

Pages: / and /demo/standalone (demo/standalone.html, backend/standalone.py, no Temporal needed); /demo (demo/index.html,
backend/demo.py). temporalio is imported only when this starts: without it, or without a Temporal server, the
standalone demo still runs, /cases and a live /demo run answer 400, and the /demo page says why.

No auth, bound to 127.0.0.1: this is a demo. The approval is whatever the caller of POST /cases asserts
(customer_text and approved_cents come from the same request); a real deployment takes approvals from
the support tool, not from the client.

INTERLOCK_PUBLIC=1 is public mode, for a hosted demo (docs/deploy.md): bind 0.0.0.0, Host only from
INTERLOCK_ALLOWED_HOSTS, POSTs only from https://<that host>, starts of runs rate-limited per client and per day, the
/cases routes off, security headers, GET /healthz, and no exception text in responses. Off, nothing here changes.
"""
import argparse, asyncio, base64, contextlib, hashlib, importlib, ipaddress, json, os, re, sqlite3, sys, threading, time, \
    traceback, types, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import config, demo
from backend.leases import DurableLeases
from interlock import receipts
from interlock.journal import effect_id_for, open_journal
from interlock.targets.stripe_api import StripeError

MODES = ("temporal", "temporal_checked", "interlock")
MAX_BODY, MAX_TEXT = 64 * 1024, 4000
TEMPORAL, UNAVAILABLE = None, "not connected yet"      # set by main(): the client, or why the Temporal demo is off
LOOP = asyncio.new_event_loop()
threading.Thread(target=LOOP.run_forever, daemon=True).start()


def wait(coro, timeout=60):
    return asyncio.run_coroutine_threadsafe(coro, LOOP).result(timeout)


class BadRequest(ValueError):
    pass


def cases():
    db = sqlite3.connect(config.path("cases.db"), timeout=30)
    db.row_factory = sqlite3.Row
    return contextlib.closing(db)


def load(case_id):
    with cases() as db:
        row = db.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if row is None:
        raise LookupError(f"no case {case_id}")
    return dict(row)


def need_temporal():
    if UNAVAILABLE:
        raise BadRequest(f"the Temporal demo is unavailable ({UNAVAILABLE}); the standalone demo at /demo/standalone runs without it")


def create(body, task_queue=None):
    need_temporal()
    mode, text, paid, approved = (body.get(k) for k in ("mode", "customer_text", "paid_cents", "approved_cents"))
    if mode not in MODES or not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT \
            or type(paid) is not int or type(approved) is not int or not 0 < approved <= paid:
        raise BadRequest(f"need mode {'|'.join(MODES)}, customer_text (at most {MAX_TEXT} characters), paid_cents "
                         "and approved_cents as integers with 0 < approved_cents <= paid_cents")
    case_id = "case-" + uuid.uuid4().hex[:12]
    row = {"case_id": case_id, "mode": mode, "payment_intent": config.stripe().test_payment(paid),
           "workflow_id": f"refund-{case_id}", "lease_id": f"approval/{case_id}", "customer_text": text,
           "paid_cents": paid, "approved_cents": approved, "created": time.time()}
    DurableLeases(config.path("leases.db")).grant(row["lease_id"], approved)
    with cases() as db, db:
        db.execute("INSERT INTO cases VALUES (:case_id, :mode, :payment_intent, :workflow_id, :lease_id, "
                   ":customer_text, :paid_cents, :approved_cents, :created)", row)
    arg = {k: row[k] for k in ("case_id", "mode", "payment_intent", "lease_id", "customer_text")}
    wait(TEMPORAL.start_workflow("RefundCase", arg, id=row["workflow_id"], task_queue=task_queue or config.TASK_QUEUE))
    return row


async def workflow_state(workflow_id):
    from temporalio.client import WorkflowExecutionStatus
    handle = TEMPORAL.get_workflow_handle(workflow_id)
    d = await handle.describe()
    out = {"workflow_id": workflow_id, "run_id": d.run_id, "status": d.status.name if d.status else None,
           "close_time": d.close_time.timestamp() if d.close_time else None, "attempts": {}, "result": None}
    scheduled = {}
    async for e in handle.fetch_history_events():
        if e.HasField("activity_task_scheduled_event_attributes"):
            scheduled[e.event_id] = e.activity_task_scheduled_event_attributes.activity_type.name
        elif e.HasField("activity_task_started_event_attributes"):     # written on close, with the last attempt number
            a = e.activity_task_started_event_attributes
            out["attempts"][scheduled[a.scheduled_event_id]] = a.attempt
    for p in d.raw_description.pending_activities:
        out["attempts"][p.activity_type.name] = p.attempt
    if d.status == WorkflowExecutionStatus.COMPLETED:
        out["result"] = await handle.result()
    elif d.status != WorkflowExecutionStatus.RUNNING:
        try:
            await handle.result()
        except Exception as e:
            out["failure"] = str(getattr(e, "cause", None) or e)
    return out


def show(body, case_id):
    need_temporal()
    case = load(case_id)
    refunds = config.stripe().request("GET", "/refunds", {"payment_intent": case["payment_intent"], "limit": 100})["data"]
    out = {"case": case, "workflow": wait(workflow_state(case["workflow_id"])),
           "approval_live": DurableLeases(config.path("leases.db")).is_live(case["lease_id"]),
           "stripe": {"payment_intent": case["payment_intent"],
                      "refunds": [{k: r[k] for k in ("id", "amount", "status", "metadata", "created")} for r in refunds],
                      "refunded_cents": sum(r["amount"] for r in refunds if r["status"] != "failed")},
           "interlock": None}
    if case["mode"] == "interlock":
        eid = effect_id_for({"request_id": case_id})
        bundle = receipts.bundle(open_journal(config.path("journal.db")), eid)
        out["interlock"] = {"effect_id": eid, "bundle": bundle,
                            "verification": receipts.verify(bundle) if bundle["entries"] else None}
    return out


def revoke(body, case_id):
    case, leases = load(case_id), DurableLeases(config.path("leases.db"))
    leases.revoke(case["lease_id"])
    return {"lease_id": case["lease_id"], "live": leases.is_live(case["lease_id"])}


def manual_refund(body, case_id):
    amount = body.get("amount_cents")
    if type(amount) is not int or amount <= 0:
        raise BadRequest("amount_cents must be a positive integer")
    r = config.stripe().request("POST", "/refunds", {"payment_intent": load(case_id)["payment_intent"], "amount": amount})
    return {"refund_id": r["id"], "amount": r["amount"], "status": r["status"]}


def health(body):
    return {"ok": True, "temporal": config.TEMPORAL, "temporal_unavailable": UNAVAILABLE,
            "temporal_serving": not UNAVAILABLE and wait(TEMPORAL.service_client.check_health())}


def demo_start(body):
    if body.get("kind") == "live":
        need_temporal()
    return demo.start(body, API)


standalone = lambda: importlib.import_module("backend.standalone")     # no temporalio anywhere it reaches


API = sys.modules[__name__]        # demo.py drives cases through this module's functions
PAGE = os.path.join(config.ROOT, "demo", "index.html")
STANDALONE_PAGE = os.path.join(config.ROOT, "demo", "standalone.html")
PAGES = {"/": STANDALONE_PAGE, "/demo/standalone": STANDALONE_PAGE, "/demo/standalone/": STANDALONE_PAGE,
         "/demo": PAGE, "/demo/": PAGE}
ROUTES = [("GET", r"/health", health), ("POST", r"/cases", create), ("GET", r"/cases/([\w-]+)", show),
          ("POST", r"/cases/([\w-]+)/revoke", revoke), ("POST", r"/cases/([\w-]+)/manual-refund", manual_refund),
          ("GET", r"/demo/info", lambda body: {**demo.info(), "temporal_unavailable": UNAVAILABLE}),
          ("POST", r"/demo/runs", demo_start),
          ("GET", r"/demo/runs/(\w+)/(\d+)", lambda body, run_id, after: demo.view(run_id, int(after))),
          ("GET", r"/demo/standalone/info", lambda body: standalone().info()),
          ("POST", r"/demo/standalone/runs", lambda body: standalone().start(body, API)),
          ("GET", r"/demo/standalone/runs/(\w+)/(\d+)", lambda body, run_id, after: standalone().view(run_id, int(after)))]


# ---- public mode (docs/deploy.md) ------------------------------------------------------------------------------

PUBLIC = None           # set by main(): public_settings(os.environ), None unless INTERLOCK_PUBLIC=1
BUSY_PUBLIC = "a run is in progress, try again in about 30 seconds"
LIMITED_ROUTES = ("/demo/runs", "/demo/standalone/runs")


class Limited(Exception):
    pass


class Limiter:
    """Starts of runs: at most per_hour per client address in any 60 minutes, and at most per_day across all clients
    in one UTC day (None: no daily cap). clock is injectable. A start that raises (bad request, busy) gives its slot
    back. In memory: a restart resets the counts, and each replica counts on its own."""
    def __init__(self, kind, per_hour, per_day=None, clock=time.time):
        self.kind, self.per_hour, self.per_day, self.clock = kind, per_hour, per_day, clock
        self.recent, self.day, self.lock = {}, [None, 0], threading.Lock()

    @contextlib.contextmanager
    def slot(self, ip):
        mock_ok = " Run mock still works." if self.kind == "live" else ""
        with self.lock:
            now = self.clock()
            day = int(now // 86400)
            if self.day[0] != day:
                self.day = [day, 0]
            # ponytail: prunes every address on each start; fine while starts are rate-limited and one at a time
            self.recent = {a: kept for a, ts in self.recent.items() if (kept := [t for t in ts if t > now - 3600])}
            if len(self.recent.get(ip, ())) >= self.per_hour:
                raise Limited(f"Limit reached: {self.per_hour} {self.kind} runs per visitor per hour. Try again later.{mock_ok}")
            if self.per_day is not None and self.day[1] >= self.per_day:
                raise Limited(f"This demo has used its {self.per_day} {self.kind} runs for today (UTC). "
                              f"Try again tomorrow.{mock_ok}")
            self.recent.setdefault(ip, []).append(now)
            self.day[1] += 1
        try:
            yield
        except BaseException:
            with self.lock:
                with contextlib.suppress(KeyError, ValueError):
                    self.recent[ip].remove(now)
                if self.day[0] == day:
                    self.day[1] -= 1
            raise


def public_settings(env, clock=time.time):
    """Public mode's settings from env, or None when INTERLOCK_PUBLIC is not "1". ValueError on a missing or malformed
    setting, so a misconfigured server does not start."""
    if env.get("INTERLOCK_PUBLIC") != "1":
        return None
    hosts = frozenset(h.strip().lower() for h in env.get("INTERLOCK_ALLOWED_HOSTS", "").split(",") if h.strip())
    if not hosts:
        raise ValueError("INTERLOCK_ALLOWED_HOSTS must name the public hostname(s), comma-separated")

    def number(name, default):
        value = int(env.get(name) or default)
        if value < 0:
            raise ValueError(f"{name} must be 0 or more")
        return value
    return types.SimpleNamespace(
        hosts=hosts, hops=number("INTERLOCK_TRUSTED_PROXY_HOPS", 0), port=number("INTERLOCK_API_PORT", number("PORT", 8787)),
        live=Limiter("live", number("INTERLOCK_LIVE_PER_IP_HOUR", 3), number("INTERLOCK_LIVE_PER_DAY", 40), clock),
        mock=Limiter("mock", number("INTERLOCK_MOCK_PER_IP_HOUR", 30), None, clock))


def host_allowed(host, hosts):
    """The Host header, with or without a port, is exactly one of hosts (case-insensitive)."""
    m = re.fullmatch(r"([A-Za-z0-9.-]+)(:\d+)?", host or "")
    return bool(m) and m.group(1).lower() in hosts


def client_ip(peer, forwarded, hops):
    """The address to rate-limit. Each trusted proxy appends the address it received from to X-Forwarded-For, so with
    `hops` of them the client is the hops-th entry from the right; anything further left is whatever the client sent.
    hops 0, no header, too few entries or a malformed entry: the socket peer."""
    parts = [p.strip() for p in ",".join(forwarded or ()).split(",") if p.strip()]
    if hops and len(parts) >= hops:
        with contextlib.suppress(ValueError):
            return str(ipaddress.ip_address(parts[-hops]))
    return peer


def page_csp(page):
    """Same origin only, plus the page's inline script by hash. Styles allow 'unsafe-inline' for the style attributes
    in the markup. Links out (Stripe dashboard, GitHub) are plain navigation, which CSP does not restrict."""
    hashes = "".join(" 'sha256-%s'" % base64.b64encode(hashlib.sha256(s).digest()).decode()
                     for s in re.findall(rb"<script>(.*?)</script>", page, re.S))
    return (f"default-src 'self'; script-src 'self'{hashes}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class Handler(BaseHTTPRequestHandler):
    def _headers(self, content_type, length, csp="default-src 'none'; frame-ancestors 'none'"):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        if PUBLIC:
            self.send_header("Content-Security-Policy", csp)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def _send(self, code, obj):
        data = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self._headers("application/json", len(data))
        self.wfile.write(data)

    def _route(self, method):
        path = self.path.split("?")[0]
        if PUBLIC and method == "GET" and path == "/healthz":    # before the Host check: a platform probe may use an IP
            return self._send(200, {"ok": True})
        if PUBLIC and not host_allowed(self.headers.get("Host"), PUBLIC.hosts):
            return self._send(403, {"error": "unknown host"})
        if method == "GET" and path in PAGES:
            with open(PAGES[path], "rb") as f:
                data = f.read()
            self.send_response(200)
            self._headers("text/html; charset=utf-8", len(data), page_csp(data) if PUBLIC else None)
            return self.wfile.write(data)
        try:
            host = self.headers.get("Host", "")
            if not PUBLIC and host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                return self._send(403, {"error": "Host must be this server (127.0.0.1 or localhost)"})   # DNS rebinding
            if PUBLIC and re.match(r"/cases(/|$)", path):     # real payments with no limit; demo runs call them in-process
                return self._send(404, {"error": "not found"})
            body = {}
            if method == "POST":
                # A cross-site page can POST text/plain without a preflight; application/json forces one, and a
                # browser always names the page's origin, which must be this server.
                origin = self.headers.get("Origin")
                if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json" \
                        or (origin is not None and origin != f"{'https' if PUBLIC else 'http'}://{host}"):
                    return self._send(403, {"error": "POST needs Content-Type application/json from this page's origin"})
                length = self.headers.get("Content-Length") or "0"
                if not (length.isascii() and length.isdigit()) or int(length) > MAX_BODY:     # rejects "-1", "abc", "²"
                    raise BadRequest(f"Content-Length must be an integer from 0 to {MAX_BODY}")
                body = json.loads(self.rfile.read(int(length)) or b"{}")
                if not isinstance(body, dict):
                    raise BadRequest("body must be a JSON object")
            for m, pattern, fn in ROUTES:
                match = re.fullmatch(pattern, path)
                if m == method and match:
                    limit = contextlib.nullcontext()
                    if PUBLIC and method == "POST" and path in LIMITED_ROUTES:
                        ip = client_ip(self.client_address[0], self.headers.get_all("X-Forwarded-For"), PUBLIC.hops)
                        limit = (PUBLIC.live if body.get("kind") == "live" else PUBLIC.mock).slot(ip)
                    with limit:
                        out = fn(body, *match.groups())
                    return self._send(200, out)
            self._send(404, {"error": "not found"})
        except Limited as e:
            self._send(429, {"error": str(e)})
        except (BadRequest, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})
        except LookupError as e:
            self._send(404, {"error": str(e)})
        except demo.Busy as e:
            self._send(409, {"error": BUSY_PUBLIC if PUBLIC else str(e)})
        except StripeError as e:
            self._send(502, {"error": "Stripe test mode returned an error" if PUBLIC else str(e)})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": "internal error" if PUBLIC else f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def main():
    global TEMPORAL, UNAVAILABLE, PUBLIC
    PUBLIC = public_settings(os.environ)
    port = argparse.ArgumentParser()
    port.add_argument("--port", type=int, default=PUBLIC.port if PUBLIC else int(os.environ.get("INTERLOCK_API_PORT", 8787)))
    args = port.parse_args()
    with cases() as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS cases (case_id TEXT PRIMARY KEY, mode TEXT, payment_intent TEXT, "
                   "workflow_id TEXT, lease_id TEXT, customer_text TEXT, paid_cents INTEGER, approved_cents INTEGER, created REAL)")
    UNAVAILABLE = os.environ.get("INTERLOCK_TEMPORAL_UNAVAILABLE")     # demo/serve.py sets it when it could not start one
    if not UNAVAILABLE:
        try:
            from temporalio.client import Client
            TEMPORAL = wait(Client.connect(config.TEMPORAL), timeout=20)
        except ImportError:
            UNAVAILABLE = "temporalio is not installed"
        except Exception as e:
            UNAVAILABLE = f"no Temporal server at {config.TEMPORAL}: {type(e).__name__}"
    bind = "0.0.0.0" if PUBLIC else "127.0.0.1"
    if PUBLIC:
        Handler.timeout = 30          # a client that stops sending cannot hold a thread
    server = ThreadingHTTPServer((bind, args.port), Handler)
    print(f"api on http://{bind}:{args.port} (temporal {UNAVAILABLE or config.TEMPORAL}, data {config.DATA})"
          + (f" public for {', '.join(sorted(PUBLIC.hosts))}" if PUBLIC else ""), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
