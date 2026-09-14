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

No auth, bound to 127.0.0.1: this is a demo. The approval is whatever the caller of POST /cases asserts
(customer_text and approved_cents come from the same request); a real deployment takes approvals from
the support tool, not from the client.
"""
import argparse, asyncio, contextlib, json, os, re, sqlite3, sys, threading, time, traceback, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from temporalio.client import Client, WorkflowExecutionStatus
from backend import config, demo
from backend.leases import DurableLeases
from interlock import receipts
from interlock.journal import effect_id_for, open_journal
from interlock.targets.stripe_api import StripeError

MODES = ("temporal", "temporal_checked", "interlock")
MAX_BODY, MAX_TEXT = 64 * 1024, 4000
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


def create(body, task_queue=None):
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
    return {"ok": True, "temporal": config.TEMPORAL, "temporal_serving": wait(TEMPORAL.service_client.check_health())}


API = sys.modules[__name__]        # demo.py drives cases through this module's functions
PAGE = os.path.join(config.ROOT, "demo", "index.html")
ROUTES = [("GET", r"/health", health), ("POST", r"/cases", create), ("GET", r"/cases/([\w-]+)", show),
          ("POST", r"/cases/([\w-]+)/revoke", revoke), ("POST", r"/cases/([\w-]+)/manual-refund", manual_refund),
          ("GET", r"/demo/info", lambda body: demo.info()), ("POST", r"/demo/runs", lambda body: demo.start(body, API)),
          ("GET", r"/demo/runs/(\w+)/(\d+)", lambda body, run_id, after: demo.view(run_id, int(after)))]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self, method):
        if method == "GET" and self.path.split("?")[0] in ("/", "/demo", "/demo/"):
            with open(PAGE, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        try:
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                return self._send(403, {"error": "Host must be this server (127.0.0.1 or localhost)"})   # DNS rebinding
            body = {}
            if method == "POST":
                # A cross-site page can POST text/plain without a preflight; application/json forces one, and a
                # browser always names the page's origin, which must be this server.
                origin = self.headers.get("Origin")
                if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json" \
                        or (origin is not None and origin != f"http://{host}"):
                    return self._send(403, {"error": "POST needs Content-Type application/json from this page's origin"})
                length = self.headers.get("Content-Length") or "0"
                if not (length.isascii() and length.isdigit()) or int(length) > MAX_BODY:     # rejects "-1", "abc", "²"
                    raise BadRequest(f"Content-Length must be an integer from 0 to {MAX_BODY}")
                body = json.loads(self.rfile.read(int(length)) or b"{}")
                if not isinstance(body, dict):
                    raise BadRequest("body must be a JSON object")
            for m, pattern, fn in ROUTES:
                match = re.fullmatch(pattern, self.path.split("?")[0])
                if m == method and match:
                    return self._send(200, fn(body, *match.groups()))
            self._send(404, {"error": "not found"})
        except (BadRequest, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})
        except LookupError as e:
            self._send(404, {"error": str(e)})
        except demo.Busy as e:
            self._send(409, {"error": str(e)})
        except StripeError as e:
            self._send(502, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def main():
    global TEMPORAL
    port = argparse.ArgumentParser()
    port.add_argument("--port", type=int, default=int(os.environ.get("INTERLOCK_API_PORT", 8787)))
    args = port.parse_args()
    with cases() as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS cases (case_id TEXT PRIMARY KEY, mode TEXT, payment_intent TEXT, "
                   "workflow_id TEXT, lease_id TEXT, customer_text TEXT, paid_cents INTEGER, approved_cents INTEGER, created REAL)")
    TEMPORAL = wait(Client.connect(config.TEMPORAL))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"api on http://127.0.0.1:{args.port} (temporal {config.TEMPORAL}, data {config.DATA})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
