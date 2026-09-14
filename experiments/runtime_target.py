"""
A local HTTP payment target for interlock_runtime tests and the Prove harness (docs/07-runtime.md 11.2).

    python3 experiments/runtime_target.py --tier 1 --port 0 --db /path/ledger.sqlite [--paid 10000] [--no-lookup]

One real process per run, real sockets, a SQLite ledger that is the ground truth for correctness.
    tier 1  dedupes on Idempotency-Key with Stripe semantics: same params replay the stored refund (replayed: true),
            different params return 400 key_reused
    tier 2  no dedup; refunds can be listed by effect id
    tier 3  no dedup, no lookup (GET /refunds is 404)
Endpoints: POST /refunds, GET /refunds?payment=&key=, GET /payments/{id}, POST /admin/hand_refund {amount},
POST /admin/prune_keys (EMULATED key expiry standing in for Stripe's 24h pruning), POST /admin/delay {seconds},
POST /admin/eligible {eligible}, GET /admin/log, GET /admin/ledger.
The access log records every request with arrival, processing start and end, key, body, X-ILR-Worker and X-ILR-Epoch.

LocalRefunds is the EffectTarget client for it; spawn_target() starts a server process and returns its URL.
"""
import argparse, json, os, sqlite3, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAYMENT = "pay_881"


class Ledger:
    def __init__(self, path, tier, paid, lookup):
        self.tier, self.lookup, self.delay, self.lock = tier, lookup, 0.0, threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            pragma journal_mode = wal; pragma synchronous = full;
            create table if not exists payments (id text primary key, paid int not null, eligible int not null);
            create table if not exists refunds (id text primary key, payment text, amount int, effect_id text,
                                                source text, created_at real);
            create table if not exists keys (key text primary key, params text, refund_id text);
            create table if not exists log (id integer primary key, method text, path text, key text, effect_id text,
                body text, worker text, epoch text, arrival real, start real, end real, status int, response text);
        """)
        self.db.execute("insert or ignore into payments values (?, ?, 1)", (PAYMENT, paid))

    def rows(self, q, args=()):
        return [dict(r) for r in self.db.execute(q, args)]

    def refunded(self, payment):
        return self.db.execute("select coalesce(sum(amount), 0) from refunds where payment = ?", (payment,)).fetchone()[0]

    def refund(self, body, key):
        payment, amount = body.get("payment"), body.get("amount")
        eid = (body.get("metadata") or {}).get("effect_id")
        params = json.dumps({"payment": payment, "amount": amount, "metadata": body.get("metadata")}, sort_keys=True)
        with self.lock:
            if self.tier == 1 and key:
                k = self.db.execute("select * from keys where key = ?", (key,)).fetchone()
                if k:
                    if k["params"] != params:
                        return 400, {"error": "key_reused", "message": "Keys for idempotent requests can only be used with the same parameters"}
                    return 200, {**self.rows("select * from refunds where id = ?", (k["refund_id"],))[0], "replayed": True}
            p = self.db.execute("select * from payments where id = ?", (payment,)).fetchone()
            if p is None:
                return 404, {"error": "no_such_payment"}
            if not p["eligible"]:
                return 400, {"error": "not_eligible"}
            if type(amount) is not int or amount <= 0 or self.refunded(payment) + amount > p["paid"]:
                return 400, {"error": "amount_exceeds_refundable"}
            n = self.db.execute("select count(*) from refunds where effect_id is ?", (eid,)).fetchone()[0]
            rid = f"re_{eid or 'anon'}_{n + 1}"
            self.db.execute("insert into refunds values (?, ?, ?, ?, 'agent', ?)", (rid, payment, amount, eid, time.time()))
            if self.tier == 1 and key:
                self.db.execute("insert into keys values (?, ?, ?)", (key, params, rid))
            return 200, {**self.rows("select * from refunds where id = ?", (rid,))[0], "replayed": False}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        L, arrival = self.server.ledger, time.time()
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        url = urllib.parse.urlsplit(self.path)
        qs = dict(urllib.parse.parse_qsl(url.query))
        start, key = time.time(), self.headers.get("Idempotency-Key")
        if (method, url.path) == ("POST", "/refunds"):
            if L.delay:
                time.sleep(L.delay)                    # service time: the request is being processed
            code, out = L.refund(body, key)
        elif (method, url.path) == ("GET", "/refunds"):
            if not L.lookup:
                code, out = 404, {"error": "this target has no lookup"}
            else:
                with L.lock:
                    rows = L.rows("select * from refunds where payment = ?", (qs.get("payment", PAYMENT),))
                code, out = 200, {"data": [r for r in rows if "key" not in qs or r["effect_id"] == qs["key"]]}
        elif method == "GET" and url.path.startswith("/payments/"):
            with L.lock:
                p = L.rows("select * from payments where id = ?", (url.path.split("/")[-1],))
                code, out = (200, {"id": p[0]["id"], "paid": p[0]["paid"], "eligible": bool(p[0]["eligible"]),
                                   "refunded_total": L.refunded(p[0]["id"])}) if p else (404, {"error": "no_such_payment"})
        elif (method, url.path) == ("POST", "/admin/hand_refund"):
            with L.lock:
                rid = f"re_hand_{time.time_ns()}"
                L.db.execute("insert into refunds values (?, ?, ?, null, 'hand', ?)",
                             (rid, body.get("payment", PAYMENT), body["amount"], time.time()))
            code, out = 200, {"id": rid}
        elif (method, url.path) == ("POST", "/admin/prune_keys"):
            with L.lock:
                L.db.execute("delete from keys")
            code, out = 200, {"emulated": "key expiry by admin call"}
        elif (method, url.path) == ("POST", "/admin/delay"):
            L.delay, code, out = float(body["seconds"]), 200, {}
        elif (method, url.path) == ("POST", "/admin/eligible"):
            with L.lock:
                L.db.execute("update payments set eligible = ? where id = ?", (int(bool(body["eligible"])), body.get("payment", PAYMENT)))
            code, out = 200, {}
        elif (method, url.path) == ("GET", "/admin/log"):
            with L.lock:
                code, out = 200, {"data": L.rows("select * from log order by id")}
        elif (method, url.path) == ("GET", "/admin/ledger"):
            with L.lock:
                code, out = 200, {"data": L.rows("select * from refunds order by created_at")}
        else:
            code, out = 404, {"error": "no route"}
        if not url.path.startswith("/admin/log"):
            with L.lock:
                L.db.execute("insert into log (method, path, key, effect_id, body, worker, epoch, arrival, start, end, status, response) "
                             "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (method, url.path, key, (body.get("metadata") or {}).get("effect_id") if isinstance(body, dict) else None,
                              json.dumps(body), self.headers.get("X-ILR-Worker"), self.headers.get("X-ILR-Epoch"),
                              arrival, start, time.time(), code, json.dumps(out)))
        data = json.dumps(out).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass                                        # the client is gone; the ledger and log already hold the truth


# ---- client ---------------------------------------------------------------------------------------------
class LocalRefunds:
    """EffectTarget for the local server. Premises: eligibility and the amount refunded by others."""
    name, action = "local-refunds", "refund"

    def __init__(self, url, tier, payment=PAYMENT, send_timeout=3, settle_margin=5, dedup_window=None, queryable=None,
                 premise_max_age=5):
        self.url, self.tier, self.payment_id = url.rstrip("/"), tier, payment
        self.send_timeout, self.settle_margin, self.premise_max_age = send_timeout, settle_margin, premise_max_age
        self.dedup_window = float("inf") if dedup_window is None else dedup_window
        self.queryable = tier in (1, 2) if queryable is None else queryable

    def _req(self, method, path, body=None, headers=None, timeout=10):
        req = urllib.request.Request(self.url + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def payment(self):
        return self._req("GET", f"/payments/{self.payment_id}")[1]

    def refunds(self, key=None):
        q = urllib.parse.urlencode({"payment": self.payment_id, **({"key": key} if key else {})})
        code, out = self._req("GET", f"/refunds?{q}")
        if code == 404:
            raise RuntimeError("this target has no lookup")
        return out["data"]

    def capture(self):
        p = self.payment()
        return {"payment": self.payment_id, "eligible": p["eligible"], "refunded_by_others": p["refunded_total"]}

    def validate_premises(self, premises, eid=None):
        p = self.payment()
        if p["eligible"] != premises["eligible"]:
            return ["eligibility changed"]
        mine = sum(r["amount"] for r in self.refunds(eid)) if (self.queryable and eid) else 0
        was, now = premises["refunded_by_others"], p["refunded_total"] - mine
        return [] if now == was else [f"refunded by others: was {was}, now {now}"]

    def apply(self, eid, effect, crash_after_effect=False, timeout=None):
        try:
            from interlock_runtime.effects import current
        except ImportError:
            current = None
        headers = {"Idempotency-Key": eid, "X-ILR-Worker": str(getattr(current, "worker", "") or ""),
                   "X-ILR-Epoch": str(getattr(current, "epoch", "") or "")}
        code, out = self._req("POST", "/refunds", {"payment": self.payment_id, "amount": effect["amount"],
                                                   "metadata": {"effect_id": eid}}, headers, timeout or self.send_timeout)
        if 400 <= code < 500:
            from interlock_runtime import TargetRejected
            raise TargetRejected(f"{code} {out.get('error')}")
        if code != 200:
            raise RuntimeError(f"target returned {code}")
        if crash_after_effect:                          # only the in-process interlock.Gate reference uses this
            from interlock.gate import SimulatedCrash
            raise SimulatedCrash(eid)
        return {"status": "already_processed" if out["replayed"] else "ok", "refund": out["id"], "amount": out["amount"]}

    def query(self, eid, effect):
        rs = self.refunds(eid)
        return rs[0]["id"] if rs else None

    # admin, for tests and the harness
    def hand_refund(self, amount):
        return self._req("POST", "/admin/hand_refund", {"amount": amount})[1]

    def prune_keys(self):
        return self._req("POST", "/admin/prune_keys", {})[1]

    def set_delay(self, seconds):
        return self._req("POST", "/admin/delay", {"seconds": seconds})[1]

    def set_eligible(self, eligible):
        return self._req("POST", "/admin/eligible", {"eligible": eligible})[1]

    def log(self):
        return self._req("GET", "/admin/log")[1]["data"]

    def ledger(self):
        return self._req("GET", "/admin/ledger")[1]["data"]


def spawn_target(tier, db_path, paid=10000, lookup=None):
    """Start a target server process. Returns (process, url)."""
    cmd = [sys.executable, os.path.abspath(__file__), "--tier", str(tier), "--port", "0", "--db", db_path, "--paid", str(paid)]
    if lookup is False:
        cmd.append("--no-lookup")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    return proc, f"http://127.0.0.1:{json.loads(proc.stdout.readline())['port']}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tier", type=int, choices=(1, 2, 3), required=True)
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--db", required=True)
    p.add_argument("--paid", type=int, default=10000)
    p.add_argument("--no-lookup", action="store_true")
    a = p.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    server.daemon_threads = True
    server.ledger = Ledger(a.db, a.tier, a.paid, lookup=a.tier in (1, 2) and not a.no_lookup)
    print(json.dumps({"ready": True, "port": server.server_address[1]}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
