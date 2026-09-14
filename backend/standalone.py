"""
The standalone demo: backend/demo.py's refund case and scenarios with no Temporal anywhere.

    info()                scenarios, columns, settings, and what a live run is missing (never a secret)
    start(body, api)      {"kind": "live"|"mock", "scenario": ..., "hand_check": bool}; raises api.BadRequest, demo.Busy
    view(run_id, after)   the run, with its events from seq `after` on

Live: each column is a real support case (a $100 Stripe test payment, an approval capped at $20) and its own worker
process, backend/standalone_worker.py, started with INTERLOCK_CRASH so it SIGKILLs itself at the scenario's crash
point. This module is the supervisor: it records the exit code, does the outage action (a refund straight to Stripe
with no key and no metadata, or a revoked approval), restarts the worker and records how that one exits.

    standard   the common agent pattern: decision saved to a local file before the send, Idempotency-Key from the
               case, a restart loads the decision and sends again, no re-checks
    checked    the same plus a hand-written re-check (hand_check)
    interlock  the same worker with the refund behind interlock.Gate; a restart runs gate.recover() first

Every event is something read in this run: the worker's saved decision and notes, the Interlock journal, Stripe's
refund list, each worker's pid and exit code. Mock is demo.mock, labeled MOCK. One run at a time across both demos.
"""
import json, os, subprocess, sys, time, uuid
from backend import config, demo
from backend.demo import APPROVED, CASE_TEXT, PAID, SCENARIOS, DemoError
from backend.leases import DurableLeases
from interlock import receipts

COLUMNS = {
    "standard": ("Common agent pattern: saved decision and an idempotency key",
                 "The worker saves the model's decision to a local file before the refund call. Stripe Idempotency-Key "
                 "comes from the case. On restart it loads the decision and sends again. It re-checks nothing."),
    "checked": ("Plus a hand-written check",
                "About ten lines before the send: find this case's refund in Stripe, then re-check the approval and "
                "the payment's refunds."),
    "interlock": ("The same worker with Interlock",
                  "The refund goes through interlock.Gate: intent on disk before the send, a claim, and on restart "
                  "gate.recover() re-checks the approval and the payment before any resend. A receipt."),
}
WHY = {"REFUNDED": "The restarted worker sent the refund from its saved decision. Nothing re-checked the approval or "
                   "the payment after the crash.",
       "FOUND_BY_LOOKUP": "The hand-written check found this case's refund already in Stripe and did not send again."}
RUNS, LATEST = {}, [None]


def info():
    base = demo.info()
    for s in base["scenarios"].values():        # the shared stories end with Temporal's retry; this demo has none
        s["story"] = s["story"].replace("the worker restarts and Temporal retries", "the supervisor restarts the worker")
    return {**base, "columns": {k: {"title": t, "sub": s} for k, (t, s) in COLUMNS.items()},
            "temporal_ui": None, "latest": LATEST[0]}


def view(run_id, after):
    return demo.view(run_id, after, RUNS)


def start(body, api):
    return demo.start(body, api, modes=tuple(COLUMNS), columns=COLUMNS, runs=RUNS, latest=LATEST, live=live_column)


def spawn(task, env, log):
    return subprocess.Popen([sys.executable, os.path.join(config.ROOT, "backend", "standalone_worker.py"), task],
                            env=env, stdout=log, stderr=log)


def supervise(worker, watch, message):
    """Wait for the worker process to exit, turning what it leaves behind into events. Returns its exit code."""
    try:
        demo.until(lambda: worker.poll() is not None, watch, 150, message)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()
    watch.poll(stripe=True)                 # whatever it wrote just before exiting
    return worker.returncode


def live_column(run, mode):
    sc = SCENARIOS[run.scenario]
    emit = lambda kind, text, **data: run.emit(mode, kind, text, **data)
    client, leases = config.stripe(), DurableLeases(config.path("leases.db"))
    cid = "case-" + uuid.uuid4().hex[:12]
    pi = client.test_payment(PAID)
    case = {"case_id": cid, "mode": mode, "payment_intent": pi, "lease_id": "approval/" + cid, "customer_text": CASE_TEXT}
    leases.grant(case["lease_id"], APPROVED)
    task = config.path(f"standalone-{run.id}-{mode}")
    with open(task + ".json", "w") as f:
        json.dump(case, f)
    demo.emit_case(emit, pi, cid, f": approval {case['lease_id']}.")

    def hand_refund(cents):
        r = client.request("POST", "/refunds", {"payment_intent": pi, "amount": cents})
        return {"refund_id": r["id"], "amount": r["amount"]}

    def revoke():
        leases.revoke(case["lease_id"])
        return {"lease_id": case["lease_id"], "live": leases.is_live(case["lease_id"])}

    watch = Watch(case, task, client, emit)
    with open(task + ".log", "ab") as log:
        worker = spawn(task, {**demo.live_env(), "INTERLOCK_CRASH": sc["crash"], "INTERLOCK_CRASH_MARKER": task + ".crash"}, log)
        demo.emit_started(emit, sc, worker.pid)
        killed = supervise(worker, watch, "the worker never reached the crash point")
        if killed != -9:
            raise DemoError(f"worker pid {worker.pid} exited with {killed}, not SIGKILL; see {log.name}")
        crashed_at = time.time()
        demo.emit_crash(emit, sc, worker.pid, killed)
        demo.outage(emit, sc, hand_refund, revoke)
        worker = spawn(task, demo.live_env(), log)
        emit("worker", f"The supervisor restarted the worker: pid {worker.pid}, no crash switch. It runs the refund step again.",
             pid=worker.pid)
        restarted = supervise(worker, watch, "the restarted worker did not finish in time")
        if restarted != 0 or not watch.outcome:
            raise DemoError(f"restarted worker pid {worker.pid} exited with {restarted}; see {log.name}")
        emit("worker", f"Worker pid {worker.pid} exited with code 0.", pid=worker.pid, exit_code=restarted)
    refunds = client.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]    # re-read for the record
    lock = None
    if watch.eid:
        bundle = receipts.bundle(watch.journal, watch.eid)
        lock = {"effect_id": watch.eid, "bundle": bundle, "verification": receipts.verify(bundle) if bundle["entries"] else None}
    o = watch.outcome
    data = demo.outcome_data(o["outcome"], {"payment_intent": pi, "refunds": refunds}, lock, sc, mode)
    data.update(why=WHY.get(o["outcome"], data["why"]), case_id=cid, refund_attempts=o["attempts"],
                worker_exit_code=killed, restart_exit_code=restarted, crash_to_close=round(o["t"] - crashed_at, 1))
    emit("result", data["headline"], **data)


class Watch(demo.Watch):
    """demo.Watch with the worker's saved decision and notes in place of Temporal's describe and history."""
    def __init__(self, case, task, client, emit):
        super().__init__(None, case, emit)
        self.task, self.client, self.outcome, self.notes = task, client, None, 0

    def poll(self, stripe=False):
        if not self.decision and os.path.exists(self.task + ".decision.json"):
            with open(self.task + ".decision.json") as f:
                self.decided(json.load(f), ". The worker saved it to a local file before any refund call.")
        if os.path.exists(self.task + ".notes"):
            with open(self.task + ".notes") as f:
                lines = f.read().split("\n")[:-1]          # complete lines only
            for n in map(json.loads, lines[self.notes:]):
                self.note(n)
            self.notes = len(lines)
        self.follow(lambda: self.client, stripe)

    def note(self, n):
        pid = n["pid"]
        if n["kind"] == "resumed":
            self.emit("worker", f"Worker pid {pid} loaded the saved decision from its file. It did not ask the model again.", pid=pid)
        elif n["kind"] == "waiting":
            self.emit("retry", f"Refund attempt {n['attempt']} on pid {pid}: {n['status']}. The killed worker's claim on "
                               "this refund has not expired, so the worker tries again every second.",
                      pid=pid, attempt=n["attempt"], last_failure=n["status"])
        elif n["kind"] == "outcome":
            self.outcome = n
            self.emit("worker", f"Worker pid {pid} finished the refund step after {n['attempts']} "
                                f"attempt{'' if n['attempts'] == 1 else 's'}: {n['outcome']}.",
                      pid=pid, outcome=n["outcome"], attempts=n["attempts"])
