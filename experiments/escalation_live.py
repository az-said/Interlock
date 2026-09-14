"""
Experiment: the escalation story end to end against real Stripe, in test mode. Not a simulation.

    python3 experiments/escalation_live.py

Key: STRIPE_SECRET_KEY, else the Stripe CLI's test_mode_api_key. Test-mode keys only; no money
moves. The key and the webhook signing secret are held in memory and never printed or written.

1. A real $100 test payment. The agent asks for a $50 refund, over the $10 auto-approve limit, so
   the inbox escalates it (needs_judgment) to ap-leads, and ana approves it (not yet sent).
2. Support refunds $30 by hand on the same payment through the Stripe API.
3. The send fires; the gate reads Stripe's refunds, refuses it (stale premise), and the inbox
   re-escalates with the change (refunded_by_others 0 -> 3000) and the target's repairs.
4. ana accepts the suggested repair; the refund goes out once.
5. Stripe confirms it: `stripe listen` forwards signed refund events to a local http.server that
   hands the raw body and Stripe-Signature header to confirm.confirm_event. If no event arrives in
   time, confirm.confirm_by_lookup is used instead and the writeup says so.
6. A second small request ($15) escalates too; the injected clock moves past the 4h SLA, so tick()
   moves it up the chain to finance-manager, and fm approves it. No sleeps: time is the clock.
7. Every receipt is checked with receipts.verify, and the scoreboard is read from the journal.

Writes results/escalation_live.jsonl (the journal), .json and .md. Stripe ids are safe to publish.
"""
import datetime, http.server, json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, effect_id_for
from interlock.approvals import Authority, Inbox, Route, Rule
from interlock.confirm import WebhookError, confirm_by_lookup, confirm_event
from interlock.escalation import describe
from interlock.receipts import bundle, verify
from interlock.scoreboard import scoreboard
from interlock.targets.stripe_api import StripeClient, StripeRefunds

STRIPE = "/opt/homebrew/bin/stripe"
PAID, ASK, HAND, SMALL, LIMIT = 10000, 5000, 3000, 1500, 1000     # cents
HOUR, WAIT = 3600, 60                                             # SLA unit; bounded webhook wait, seconds
GROUPS = {"ap-leads": {"ana"}, "finance-manager": {"fm"}}
RESULTS = os.path.join(ROOT, "results")


def api_key():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if key:
        return key
    out = subprocess.run([STRIPE, "config", "--list"], capture_output=True, text=True).stdout
    m = re.search(r"^test_mode_api_key\s*=\s*'([^']+)'", out, re.M)
    return m.group(1) if m else None


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class Listener:
    """stripe listen forwarding refund events to a local server that records them through confirm_event."""
    def __init__(self, key, journal, target):
        self.env = {**os.environ, "STRIPE_API_KEY": key}
        self.journal, self.target, self.results, self.proc = journal, target, [], None
        self.ready, self.arrived = threading.Event(), threading.Condition()

    def start(self):
        out = subprocess.run([STRIPE, "listen", "--print-secret"], capture_output=True, text=True, env=self.env, timeout=60)
        secret = out.stdout.strip()
        if out.returncode or not secret.startswith("whsec_"):
            raise RuntimeError("stripe listen --print-secret did not return a signing secret")
        listener = self

        class Hook(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                try:
                    status = confirm_event(listener.journal, listener.target, raw, self.headers.get("Stripe-Signature"), secret)
                    kind = json.loads(raw).get("type")
                except WebhookError as e:
                    status, kind = f"REJECTED:{e}", None
                self.send_response(200)
                self.end_headers()
                with listener.arrived:
                    listener.results.append({"at": utc(), "type": kind, "status": status})
                    listener.arrived.notify_all()

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hook)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        port = self.server.server_address[1]
        self.proc = subprocess.Popen(
            [STRIPE, "listen", "--forward-to", f"localhost:{port}/webhook",
             "--events", "refund.created,refund.updated,refund.failed"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=self.env)

        def drain():                          # the CLI prints the secret here: read it, never keep or print it
            for line in self.proc.stderr:
                if "Ready!" in line:
                    self.ready.set()
        threading.Thread(target=drain, daemon=True).start()
        return self.ready.wait(45)

    def wait_confirmed(self, eids, timeout=WAIT):
        """True once every effect has a CONFIRMED entry via webhook, or False after timeout."""
        deadline = time.monotonic() + timeout
        def done():
            return all(any(e["kind"] == "CONFIRMED" for e in self.journal.entries(x)) for x in eids)
        with self.arrived:
            while not done():
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.arrived.wait(min(left, 2))
        return True

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if getattr(self, "server", None):
            self.server.shutdown()


def main():
    try:
        client = StripeClient(api_key())
    except ValueError as e:
        sys.exit(f"{e}\nSet STRIPE_SECRET_KEY to a test-mode key, or log in with the Stripe CLI.")

    started, steps = utc(), []
    def step(name, **info):
        steps.append({"step": name, "at": utc(), **info})
        print(f"- {name}: " + ", ".join(f"{k}={v}" for k, v in info.items()))

    workdir = tempfile.mkdtemp(prefix="escalation-live-")
    path = os.path.join(workdir, "journal.jsonl")
    now = [float(int(time.time()))]
    clock = lambda: now[0]

    pi = client.test_payment(PAID)
    target = StripeRefunds(client, pi)
    step("payment", payment_intent=pi, amount=PAID)

    auth = Authority(groups=GROUPS, clock=clock)
    inbox = Inbox(Gate(target, path, auth), capture=lambda r: target.capture(), effect=lambda r: {"amount": r["amount"]},
                  rules=[Rule(f"amount at most {LIMIT} cents", lambda r, facts: r["amount"] <= LIMIT)],
                  routes=[Route("refunds", ["ap-leads", "finance-manager"], sla=4 * HOUR)], clock=clock)
    listener = Listener(api_key(), inbox.gate.journal, target)
    confirmation = {"path": None}
    try:
        listening = listener.start()
        step("listener", ready=listening)

        rid = f"refund-50/{pi}"
        status = inbox.submit({"id": rid, "amount": ASK})
        first = inbox.queue[rid]
        step("request", request_id=rid, status=status, reason=first["reason"], detail=first["detail"], group=first["group"])
        assert status == "QUEUED" and first["reason"] == "needs_judgment"

        now[0] += 20 * 60
        status = inbox.approve(rid, "ana", execute=False, seen=first["escalation"])
        step("approved", by="ana", status=status)
        assert status == "APPROVED"

        now[0] += 5 * 60
        hand = client.request("POST", "/refunds", {"payment_intent": pi, "amount": HAND})
        step("hand refund", refund=hand["id"], amount=hand["amount"], status=hand["status"])

        status = inbox.execute(rid)
        item = inbox.queue.get(rid)
        step("send", status=status, reason=item and item["reason"], changes=item and item["changes"],
             repairs=item and [r["code"] for r in item["repairs"]])
        assert status == "REFUSED:stale_premise"
        assert item["changes"] == [{"field": "refunded_by_others", "was": 0, "now": HAND}], item["changes"]
        assert item["repairs"], "the target suggested no repair"
        explained = describe(item)

        now[0] += 10 * 60
        codes = [r["code"] for r in item["repairs"]]
        status = inbox.repair(rid, "ana", index=0, seen=item["escalation"])
        step("repair accepted", by="ana", repair=codes[0], status=status)
        assert status == "COMMITTED"

        rid2 = f"refund-15/{pi}"
        now[0] += 5 * 60
        status = inbox.submit({"id": rid2, "amount": SMALL})
        step("second request", request_id=rid2, status=status, group=inbox.queue[rid2]["group"])
        now[0] += 4 * HOUR + 60
        moved = inbox.tick()
        late = inbox.queue[rid2]
        step("sla tick", moved=moved, group=late["group"], level=late["level"], breach=late["breach"])
        assert moved == {rid2: "finance-manager"}
        refused = inbox.approve(rid2, "ana", seen=late["escalation"])
        step("ap-leads after breach", by="ana", status=refused)
        assert refused == "REFUSED:lease"
        now[0] += 15 * 60
        status = inbox.approve(rid2, "fm", seen=late["escalation"])
        step("approved up the chain", by="fm", status=status)
        assert status == "COMMITTED"

        eids = [effect_id_for({"request_id": r}) for r in (rid, rid2)]
        if listening and listener.wait_confirmed(eids):
            confirmation["path"] = "webhook"
        else:
            confirmation["path"] = "lookup"
            confirmation["lookup"] = {e: confirm_by_lookup(inbox.gate.journal, target, e) for e in eids}
        step("confirmation", path=confirmation["path"])
        refunded = target.refunded_total()
    finally:
        listener.stop()
        confirmation["webhook_deliveries"] = listener.results

    journal = inbox.gate.journal
    receipts = {r: bundle(journal, effect_id_for({"request_id": r})) for r in (rid, rid2)}
    verified = {r: verify(b) for r, b in receipts.items()}
    board = scoreboard(journal)
    ours = [e for e in journal.entries() for x in [e.get("result") or {}] if x.get("refund")]
    refunds = {"hand": hand["id"], **{e["effect_id"]: e["result"]["refund"] for e in ours}}
    assert refunded == HAND + ASK + SMALL, refunded
    for r, v in verified.items():
        assert v["valid"], (r, v["problems"])

    os.makedirs(RESULTS, exist_ok=True)
    shutil.copyfile(path, os.path.join(RESULTS, "escalation_live.jsonl"))
    out = {"started": started, "finished": utc(), "mode": "stripe test mode", "payment_intent": pi,
           "refunds": refunds, "refunded_total_cents": refunded, "confirmation": confirmation, "steps": steps,
           "explained": explained, "receipts": receipts, "verify": verified, "scoreboard": board}
    with open(os.path.join(RESULTS, "escalation_live.json"), "w") as f:
        json.dump(out, f, indent=2)
    with open(os.path.join(RESULTS, "escalation_live.md"), "w") as f:
        f.write(writeup(out, rid, rid2))
    print(f"\nconfirmation path: {confirmation['path']}; receipts valid: {[v['valid'] for v in verified.values()]}")


def writeup(o, rid, rid2):
    v1, v2, s = o["verify"][rid], o["verify"][rid2], o["scoreboard"]
    rows = "\n".join(f"| {x['step']} | {x['at']} | " + ", ".join(f"{k}={v}" for k, v in x.items() if k not in ("step", "at")) + " |"
                     for x in o["steps"])
    deliveries = "\n".join(f"- {d['at']} `{d['type']}`: {d['status']}" for d in o["confirmation"]["webhook_deliveries"]) or "- none arrived"
    def vrow(r, v):
        return (f"| `{r}` | {v['valid']} | {v['happened']} | {v['happened_once']} | {v['authorized_when_fired']} | "
                f"{v['assumptions_held']} | {v['approved_by']} | {v['approval_verified']} | {v['confirmed_by_target']} | "
                f"{len(v['escalations'])} |")
    return f"""# Results: an explained escalation against real Stripe (test mode)

Generated {o['finished']} by `experiments/escalation_live.py`. Every step made real Stripe test-mode API calls
on one PaymentIntent, `{o['payment_intent']}`. No mock data. The journal is `results/escalation_live.jsonl`; the
receipts, verify output and scoreboard are in `results/escalation_live.json`.

Workflow time (`at`, SLA, decisions) is an injected clock advanced by the script, so a 4h SLA passes
without waiting 4h. Stripe calls, refund ids and webhook deliveries are real and wall clock.

## What happened

| step | wall clock (UTC) | detail |
|---|---|---|
{rows}

The reviewer saw, on the re-escalation: "{o['explained']}".

Refunded on the payment: {o['refunded_total_cents']} cents ($30 by hand, $50 by the agent once, $15 after the SLA
escalation). Refund ids: `{o['refunds']['hand']}` (hand), """ + ", ".join(f"`{v}`" for k, v in o["refunds"].items() if k != "hand") + f""".

## Confirmation by the target

Path used: **{o['confirmation']['path']}**. `stripe listen` forwarded refund events to a local server that passed the raw body and
`Stripe-Signature` header to `confirm.confirm_event`. Deliveries:

{deliveries}

Events for refunds this journal does not know (the hand refund, other test traffic on the account) are ignored.

## verify()

| request | valid | happened | once | authorized | assumptions held | approved by | approval verified | confirmed by target | escalations |
|---|---|---|---|---|---|---|---|---|---|
{vrow(rid, v1)}
{vrow(rid2, v2)}

Problems: {v1['problems'] or 'none'} and {v2['problems'] or 'none'}. Receipts are unsigned (no key), so they prove internal
consistency, not that the journal was never rebuilt.

## Scoreboard (derived from the journal)

| field | value |
|---|---|
""" + "\n".join(f"| {k} | {v} |" for k, v in s.items()) + """

Both requests were over the auto-approve limit by design, so no request cleared without a person here. This run
shows one story working end to end; it is not a measure of how many approvals Interlock removes. Goal: cut two
thirds of manual agent approvals.
"""


if __name__ == "__main__":
    main()
