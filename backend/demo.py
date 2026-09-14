"""
The before/after demo, served by backend/api.py (page: demo/index.html, one command: demo/serve.py).

    GET  /demo/info               scenarios, columns, settings, and what a live run is missing (never a secret)
    POST /demo/runs               {"kind": "live"|"mock", "scenario": ..., "hand_check": bool}; 409 while a run is going
    GET  /demo/runs/{id}/{after}  the run, with its events from seq `after` on

Live: each column is a real support case made through api.create (a $100 Stripe test payment, an approval
capped at $20, a RefundCase workflow on the column's own task queue) and its own worker process, started here
with INTERLOCK_CRASH so it SIGKILLs itself at the scenario's crash point. The outage action goes through
api.manual_refund or api.revoke, a new worker process starts, and the column ends when Temporal closes the
workflow. Columns run at the same time. Every event is something read in this run: Temporal's describe and
history, the Interlock journal, Stripe's refund list, a worker's exit code.

Mock: experiments/refund_agent.py in this process (the payments simulator: no Stripe, no LLM, no Temporal,
no process). Every mock event and result carries mock=True.
"""
import os, subprocess, sys, threading, time, uuid
from backend import agent, config
from interlock.journal import effect_id_for, open_journal

PAID, APPROVED = 10000, 2000
CASE_TEXT = ("Order #881, paid $100.00 by card. The blender arrived with its glass jar cracked. "
             "Support case #4471: support reviewed the photos and approved ONE partial refund of $20.00 for the jar; "
             "the customer keeps the blender. Issue the approved refund.")
DASHBOARD = "https://dashboard.stripe.com/test/payments/"
WHERE = {"before_send": "right before the refund call to Stripe",
         "after_commit": "right after Stripe confirmed the refund, before anything recorded it"}
SCENARIOS = {
    "hand_refund_during_outage": dict(
        title="Hand refund during the outage", crash="before_send", action="manual-refund", want=(APPROVED, 1),
        want_text="one $20 refund: the one support made by hand", mock="refund_during_outage",
        mock_outage="support refunds $20 by hand",
        story="A customer paid $100 and support approved one $20 refund. An LLM agent decides the refund, and the "
              "worker process is killed right before it calls Stripe. While the worker is down, support refunds the "
              "$20 by hand. Then the worker restarts and Temporal retries."),
    "approval_revoked_during_outage": dict(
        title="Approval revoked during the outage", crash="before_send", action="revoke", want=(0, 0),
        want_text="no refund", mock="lease_revoked_during_outage", mock_outage="support revokes the approval",
        story="A customer paid $100 and support approved one $20 refund. An LLM agent decides the refund, and the "
              "worker process is killed right before it calls Stripe. While the worker is down, support revokes the "
              "approval. Then the worker restarts and Temporal retries."),
    "crash_after_commit": dict(
        title="Crash after Stripe answered (control)", crash="after_commit", action=None, want=(APPROVED, 1),
        want_text="one $20 refund", mock="crash_before_ack", mock_outage="nothing else changes",
        story="A customer paid $100 and support approved one $20 refund. An LLM agent decides the refund, and the "
              "worker process is killed right after Stripe confirmed it, before anything recorded that. Nothing "
              "else changes. Then the worker restarts and Temporal retries. Both setups should hold here."),
}
COLUMNS = {
    "temporal": ("Standard setup: Temporal and an idempotency key",
                 "Temporal retries the activity. Stripe Idempotency-Key is the workflow run id and activity id, as "
                 "Temporal's docs suggest. The activity re-checks nothing."),
    "temporal_checked": ("Temporal plus a hand-written check",
                         "About ten lines at the top of the activity: find this workflow's refund in Stripe, then "
                         "re-check the approval and the payment's refunds."),
    "interlock": ("Temporal plus Interlock",
                  "interlock.temporal.gated() is the activity body: intent on disk before the send, a claim, the "
                  "approval and the facts re-checked at recovery, and a receipt."),
}
MOCK_COLUMNS = {
    "temporal": ("durable", "Durable execution, simulated",
                 "DurableExecution from interlock.gate: re-runs an unfinished step with a stable key. In memory."),
    "interlock": ("gate", "Interlock gate, simulated",
                  "interlock.Gate over the in-memory payments simulator. No Stripe, no Temporal."),
    "standard": ("durable", "Retry with a stable key, simulated",       # backend/standalone.py's mock column
                 "DurableExecution from interlock.gate: re-runs an unfinished step with the same key, re-checks "
                 "nothing. In memory."),
}


class Busy(RuntimeError):
    pass


class DemoError(RuntimeError):
    pass


RUNS, BUSY, LATEST = {}, threading.Lock(), [None]
KEEP_RUNS = 50          # start() drops the oldest finished runs past this, so memory stays bounded


class Run:
    def __init__(self, kind, scenario, modes, columns=None):
        self.id, self.kind, self.scenario, self.modes = uuid.uuid4().hex[:10], kind, scenario, modes
        self.columns = columns or COLUMNS           # live column titles; backend/standalone.py passes its own
        self.events, self.done, self.error, self.started, self.finished = [], False, None, time.time(), None
        self._lock = threading.Lock()

    def emit(self, col, kind, text, **data):
        with self._lock:
            self.events.append({"seq": len(self.events), "col": col, "kind": kind, "text": text, "data": data,
                                "t": round(time.time() - self.started, 1), "mock": self.kind == "mock"})

    def view(self, after=0):
        mock = self.kind == "mock"
        with self._lock:
            return {"id": self.id, "kind": self.kind, "mock": mock, "scenario": self.scenario, "done": self.done,
                    "error": self.error, "elapsed": round((self.finished or time.time()) - self.started, 1),
                    "columns": [{"mode": m, "title": (MOCK_COLUMNS[m][1:] if mock else self.columns[m])[0],
                                 "sub": (MOCK_COLUMNS[m][1:] if mock else self.columns[m])[1]} for m in self.modes],
                    "events": self.events[after:]}


def missing():
    """What a live run needs and this server does not have. Names only."""
    out = [] if os.environ.get("ANTHROPIC_API_KEY") else ["ANTHROPIC_API_KEY"]
    return out + ([] if config.stripe_key() else ["a Stripe test key (STRIPE_SECRET_KEY, or `stripe login`)"])


def info():
    return {"scenarios": {k: {x: s[x] for x in ("title", "story", "want_text")} for k, s in SCENARIOS.items()},
            "live_missing": missing(), "model": agent.MODEL, "claim_ttl": config.CLAIM_TTL,
            "stripe_timeout": config.STRIPE_TIMEOUT, "temporal_ui": os.environ.get("TEMPORAL_UI"), "latest": LATEST[0]}


def view(run_id, after, runs=RUNS):
    if run_id not in runs:
        raise LookupError(f"no run {run_id}")
    return runs[run_id].view(after)


def start(body, api, drive=None, modes=("temporal", "temporal_checked", "interlock"), columns=None, runs=RUNS,
          latest=LATEST, live=None):
    """modes: the three live columns, the middle one only with hand_check. backend/standalone.py passes its own
    modes, columns, runs, latest and live (the function that runs one live column, called as live(run, mode))."""
    kind, name = body.get("kind"), body.get("scenario", "hand_refund_during_outage")
    if kind not in ("live", "mock") or name not in SCENARIOS:
        raise api.BadRequest(f"need kind live|mock and scenario {'|'.join(SCENARIOS)}")
    if kind == "live" and missing():
        raise api.BadRequest("a live run needs " + " and ".join(missing()))
    if not BUSY.acquire(blocking=False):
        raise Busy("a run is already going; wait for it to finish")
    run = Run(kind, name, modes if kind == "live" and body.get("hand_check") is True else (modes[0], modes[2]), columns)
    runs[run.id], latest[0] = run, run.id
    for old in [r for r, v in runs.items() if v.done][:max(0, len(runs) - KEEP_RUNS)]:     # oldest first
        del runs[old]
    threading.Thread(target=drive or _drive, args=(run, api, live), daemon=True).start()
    return run.view()


def _drive(run, api, live=None):
    try:
        if run.kind == "mock":
            mock(run)
        else:
            threads = [threading.Thread(target=_column, args=(run, m, api, live)) for m in run.modes]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    except Exception as e:
        run.error = f"{type(e).__name__}" + ("" if PUBLIC else f": {e}")
    finally:
        run.finished, run.done = time.time(), True
        BUSY.release()


# Public mode (docs/deploy.md): a run's events name an exception's type, never its text, which can carry upstream detail.
PUBLIC = os.environ.get("INTERLOCK_PUBLIC") == "1"
WITHHELD = "an error (details are in the server log)"


def shown(failure):
    """A Temporal failure message as run events may carry it: in public mode a fixed label, since the message is an
    exception's text (an Anthropic error body, Stripe's message)."""
    return WITHHELD if PUBLIC and failure else failure


def _column(run, mode, api, live=None):
    try:
        live(run, mode) if live else live_column(run, mode, api)
    except Exception as e:
        run.emit(mode, "error", f"This column stopped: {type(e).__name__}" + ("" if PUBLIC else f": {e}"))
        run.error = run.error or f"{mode}: " + (type(e).__name__ if PUBLIC else f"{e}")


# ---- live ----------------------------------------------------------------------------------------------------

def spawn(env, log):
    return subprocess.Popen([sys.executable, os.path.join(config.ROOT, "backend", "worker.py")],
                            env=env, stdout=log, stderr=log)


def live_column(run, mode, api):
    sc = SCENARIOS[run.scenario]
    emit = lambda kind, text, **data: run.emit(mode, kind, text, **data)
    queue = f"interlock-demo-{run.id}-{mode}"
    case = api.create({"customer_text": CASE_TEXT, "paid_cents": PAID, "approved_cents": APPROVED, "mode": mode},
                      task_queue=queue)
    cid, pi = case["case_id"], case["payment_intent"]
    emit_case(emit, pi, cid, f". Temporal workflow {case['workflow_id']} started.", workflow_id=case["workflow_id"])
    watch = Watch(api, case, emit)
    env = worker_env(queue)
    with open(config.path(f"worker-{run.id}-{mode}.log"), "ab") as log:
        worker = spawn({**env, "INTERLOCK_CRASH": sc["crash"],
                        "INTERLOCK_CRASH_MARKER": config.path(f"crash-{run.id}-{mode}")}, log)
        emit_started(emit, sc, worker.pid)
        try:
            until(lambda: worker.poll() is not None or watch.closed, watch, 150, "the worker never reached the crash point")
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait()
        if worker.returncode != -9:
            raise DemoError(f"worker pid {worker.pid} exited with {worker.returncode}, not SIGKILL "
                            f"(workflow closed: {watch.closed}); see {log.name}")
        crashed_at = time.time()
        watch.poll()                                    # entries written just before the kill
        emit_crash(emit, sc, worker.pid, worker.returncode)
        outage(emit, sc, lambda cents: api.manual_refund({"amount_cents": cents}, cid), lambda: api.revoke({}, cid))
        worker = spawn(env, log)
        emit("worker", f"Worker process restarted, pid {worker.pid}. Temporal will retry the refund activity.",
             pid=worker.pid)
        try:
            until(lambda: watch.closed, watch, 150, "the workflow did not close in time")
        finally:
            worker.terminate()
            worker.wait(10)
    state = api.show({}, cid)                           # Stripe re-read once more, for the record
    data = result_data(state, sc, mode)
    close = state["workflow"].get("close_time")
    data.update(worker_exit_code=-9, crash_to_close=round(close - crashed_at, 1) if close else None)
    emit("result", data["headline"], **data)


def emit_case(emit, pi, cid, then, **data):
    emit("case", f"Stripe test payment {pi}: {money(PAID)} paid. Support approves one refund of at most {money(APPROVED)}"
                 + then, payment_intent=pi, case_id=cid, dashboard=DASHBOARD + pi, **data)


def emit_started(emit, sc, pid):
    emit("worker", f"Worker process started, pid {pid}. It is set to SIGKILL itself {WHERE[sc['crash']]}.", pid=pid)


def emit_crash(emit, sc, pid, code):
    emit("crash", f"Worker pid {pid} is dead: exit code {code} (SIGKILL), {WHERE[sc['crash']]}.",
         pid=pid, exit_code=code, point=sc["crash"])


def outage(emit, sc, refund, revoke):
    """The scenario's action while the worker is down. refund(cents) -> {refund_id, amount}; revoke() -> {lease_id, live}."""
    if sc["action"] == "manual-refund":
        r = refund(APPROVED)
        emit("hand_refund", f"While the worker is down, support refunds {money(r['amount'])} by hand in Stripe: "
                            f"{r['refund_id']}. No idempotency key, no metadata, as from the dashboard.",
             refund_id=r["refund_id"], amount=r["amount"])
    elif sc["action"] == "revoke":
        r = revoke()
        emit("revoke", f"While the worker is down, support revokes approval {r['lease_id']}. "
                       f"Approval live now: {r['live']}.", lease_id=r["lease_id"], live=r["live"])


def until(done, watch, seconds, message):
    deadline = time.time() + seconds
    while True:
        watch.poll()
        if done():
            return
        if time.time() > deadline:
            raise DemoError(message)
        time.sleep(0.5)


async def snapshot(client, workflow_id):
    """Workflow status, the model's recorded decision, and the refund activity's current attempt."""
    from temporalio.converter import DataConverter
    handle = client.get_workflow_handle(workflow_id)
    d = await handle.describe()
    out = {"status": d.status.name if d.status else None, "decision": None, "attempt": None}
    for p in d.raw_description.pending_activities:
        if p.activity_type.name == "refund":
            out["attempt"] = (p.attempt, p.last_failure.message or None)
    async for e in handle.fetch_history_events():
        if e.HasField("activity_task_completed_event_attributes"):
            value = DataConverter.default.payload_converter.from_payloads(
                e.activity_task_completed_event_attributes.result.payloads)[0]
            if isinstance(value, dict) and "amount_cents" in value:
                out["decision"] = value
    return out


class Watch:
    """Turns what Temporal, the journal and Stripe say into events, once each. backend/standalone.py subclasses it."""
    def __init__(self, api, case, emit):
        self.api, self.case, self.emit = api, case, emit
        self.eid = effect_id_for({"request_id": case["case_id"]}) if case["mode"] == "interlock" else None
        self.journal = open_journal(config.path("journal.db")) if self.eid else None
        self.decision, self.attempt, self.closed, self.entries, self.refunds, self.stripe_read = None, None, False, 0, set(), 0

    def poll(self):
        snap = self.api.wait(snapshot(self.api.TEMPORAL, self.case["workflow_id"]))
        d = snap["decision"]
        if d and not self.decision:
            self.decided(d)
        if snap["attempt"] and snap["attempt"][0] > 1 and snap["attempt"] != self.attempt:
            n, failure = self.attempt = snap["attempt"]
            failure = shown(failure)
            self.emit("retry", f"Temporal runs refund attempt {n}." + (f" Attempt {n - 1} failed: {failure}" if failure else ""),
                      attempt=n, last_failure=failure)
        self.follow(config.stripe, snap["status"] != "RUNNING")
        self.closed = snap["status"] != "RUNNING"

    def decided(self, d, then=""):
        self.decision = d
        self.emit("decision", f"{d['model']} read the payment with get_payment, then called issue_refund: "
                              f"{d['amount_cents']} cents, \"{d['reason']}\"{then}",
                  amount_cents=d["amount_cents"], reason=d["reason"], model=d["model"], premises=d["premises"])

    def follow(self, client, now=False):
        """New Interlock journal entries, and Stripe's refund list: at once when now, else at most every 1.5s.
        client() returns the Stripe client, called only when Stripe is read (config.stripe may run the Stripe CLI)."""
        if self.journal:
            entries = self.journal.entries(self.eid)
            for e in entries[self.entries:]:
                self.emit("journal", journal_text(e), entry=e)
            self.entries = len(entries)
        if now or time.time() - self.stripe_read > 1.5:
            self.stripe_read = time.time()
            data = client().request("GET", "/refunds", {"payment_intent": self.case["payment_intent"], "limit": 100})["data"]
            for r in sorted(data, key=lambda r: r["created"]):
                if r["id"] not in self.refunds and r["status"] != "failed":
                    self.refunds.add(r["id"])
                    self.emit("stripe", f"Stripe now lists refund {r['id']}: {money(r['amount'])}, {who(r)}.",
                              refund_id=r["id"], amount=r["amount"])


# ---- shared by live and mock, and tested offline ---------------------------------------------------------------

def money(cents, unit=100):
    return f"${cents / unit:.2f}" if unit == 100 else f"${cents}"


def who(refund):
    md = refund.get("metadata") or {}
    return ("sent by the agent's workflow" if md.get("workflow_id") else "sent by Interlock" if md.get("interlock_effect_id")
            else "sent by the agent's worker" if md.get("case_id") else "no metadata: the hand refund")


def journal_text(e, unit=100):
    kind = e["kind"]
    if kind == "PROPOSED":
        p = e.get("premises") or {}
        before = p.get("refunded_by_others", p.get("refunded"))
        return (f"PROPOSED by {e.get('agent')}: refund {money(e['effect']['amount'], unit)}. Premise: "
                f"{money(before, unit)} already refunded on this payment.")
    if kind == "AUTHORIZED":
        return f"AUTHORIZED: approval {e.get('lease')} is live."
    if kind == "DISPATCHED":
        grant = (e.get("checks") or {}).get("lease") or {}
        cap = f", capped at {money(grant['max_cents'])}" if grant.get("max_cents") else ""
        return f"DISPATCHED: on disk before the refund call. Checked just now: approval live{cap}, payment's refunds unchanged."
    if kind == "COMMITTED":
        result = e.get("result") or {}
        ref = result.get("refund") if isinstance(result, dict) else None
        found = e.get("found") if isinstance(e.get("found"), str) else None
        return "COMMITTED" + (f" via {e['via']}" if e.get("via") else "") + (f": refund {ref or found}" if ref or found else ".")
    if kind in ("REFUSED", "AMBIGUOUS"):
        rc = e.get("rechecked") or e.get("checks") or {}
        detail = "; ".join(rc.get("violations") or []) or ("approval not live" if rc.get("lease_live") is False else "")
        reason = e.get("reason")
        reason = "; ".join(reason) if isinstance(reason, list) else reason
        return f"{kind}: " + ", ".join(x for x in (reason, detail) if x) if (reason or detail) else kind
    return kind


def headline(refunds_cents, want_cents, want_refunds):
    """refunds_cents: the amount of each live refund in Stripe."""
    n, total = len(refunds_cents), sum(refunds_cents)
    held = total == want_cents and n == want_refunds
    diff = total - want_cents
    verdict = ("Held" if held else f"Violated: {money(diff)} too much" if diff > 0 else f"Short by {money(-diff)}" if diff < 0
               else "Violated: wrong number of refunds")
    return held, f"{n} refund{'' if n == 1 else 's'}, {money(total)} refunded", verdict


def explain(mode, outcome, violations=None):
    o = str(outcome or "")
    why = f" ({'; '.join(violations)})" if violations else ""
    if o in ("REFUNDED", "RERUN:ok"):
        return "The retry sent the refund. Nothing in the activity re-checked the approval or the payment after the crash."
    if o in ("REPLAYED_BY_STRIPE", "RERUN:already_processed"):
        return "The retry reused the same idempotency key, so the first refund was replayed instead of a second one created."
    if o == "FOUND_BY_LOOKUP":
        return "The hand-written check found this workflow's refund already in Stripe and did not send again."
    if o.startswith("REFUSED:lease"):
        who_ = "Interlock refused at recovery" if mode == "interlock" else "The hand-written check refused"
        return f"{who_}: the approval was revoked while the worker was down."
    if o.startswith("REFUSED:stale_premise"):
        who_ = "Interlock refused at recovery" if mode == "interlock" else "The hand-written check refused"
        return f"{who_}: the payment's refunds changed after the refund was decided{why}. A person decides what happens next."
    if o == "COMMITTED_BY_RETRY":
        return "Interlock re-checked the approval and the payment, then resent under the same key; the first refund was replayed."
    if o == "COMMITTED_ON_QUERY":
        return "Interlock looked the refund up and found it had already landed, so it did not send again."
    if o == "COMMITTED":
        return "Interlock sent the refund once."
    if o == "AMBIGUOUS":
        return "Interlock could not tell whether the refund landed, so it stopped for a person instead of guessing."
    return f"Outcome: {o or 'none reported'}"


def result_data(state, sc, mode):
    wf = state["workflow"]
    outcome = (wf.get("result") or {}).get("outcome") or shown(wf.get("failure"))
    return {**outcome_data(outcome, state["stripe"], state.get("interlock"), sc, mode), "workflow_id": wf["workflow_id"],
            "workflow_status": wf["status"], "refund_attempts": wf["attempts"].get("refund")}


def outcome_data(outcome, stripe, lock, sc, mode):
    """The result card from an outcome, Stripe's refund list and the Interlock receipt. No Temporal."""
    refunds = sorted((r for r in stripe["refunds"] if r["status"] != "failed"), key=lambda r: r["created"])
    held, head, verdict = headline([r["amount"] for r in refunds], *sc["want"])
    verification = lock and lock.get("verification")
    rc = (verification or {}).get("rechecked_at_recovery") or {}
    out = {"headline": head, "verdict": verdict, "held": held, "want_text": sc["want_text"], "outcome": outcome,
           "why": explain(mode, outcome, rc.get("violations")),
           "payment_intent": stripe["payment_intent"], "dashboard": DASHBOARD + stripe["payment_intent"],
           "refunds": [{"id": r["id"], "amount": r["amount"], "status": r["status"], "by": who(r)} for r in refunds],
           "refunded_cents": sum(r["amount"] for r in refunds), "receipt": None}
    if verification:
        out["receipt"] = {"effect_id": lock["effect_id"], "final": lock["bundle"]["summary"]["final"],
                          "entries": [e["kind"] for e in lock["bundle"]["entries"]],
                          "verification": {k: verification[k] for k in ("valid", "tamper_evident", "signed", "happened",
                                           "happened_once", "authorized_when_fired", "assumptions_held", "refused",
                                           "evidence", "problems")}}
    return out


# ---- mock ------------------------------------------------------------------------------------------------------

LIVE_WORKER_DROPS = ("INTERLOCK_CRASH", "INTERLOCK_EMULATE_24H", "INTERLOCK_NO_LOOKUP")


def live_env():
    """
    A live worker's environment: this server's, without crash injection (set per spawn) and without the EMULATED
    switches of backend/config.py, so a run labeled live never runs with an emulated Stripe key or lookup.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith(LIVE_WORKER_DROPS)}


def worker_env(queue):
    return {**live_env(), "INTERLOCK_TASK_QUEUE": queue}


def mock(run):
    """The in-process simulation. Labeled MOCK in every event; never touches Stripe, a model, or Temporal."""
    from experiments.refund_agent import run as simulate
    sc = SCENARIOS[run.scenario]
    where = "before the send" if sc["crash"] == "before_send" else "after the refund landed, before the ack"
    for mode in run.modes:
        system, _, _ = MOCK_COLUMNS[mode]
        emit = lambda kind, text, **data: run.emit(mode, kind, "MOCK. " + text, **data)
        cell = simulate(system, 1, sc["mock"], keep_journal=True)
        dies = f"Simulated process dies {where}. Outage: {sc['mock_outage']}. Restart and recover."
        emit("sim", "Simulated order paid $100 with one $20 refund approved, in memory. Agent is a fixed proposal, not an LLM.")
        if system == "gate":
            crashed = False
            for e in cell["journal"]:
                emit("journal", journal_text(e, unit=1))
                if e["kind"] == "DISPATCHED" and not crashed:
                    crashed = True
                    emit("sim", dies)
        else:           # DurableExecution keeps no journal: its steps, from the scenario and the simulator's answer
            emit("sim", "Durable step starts: refund $20 with a stable idempotency key. No approval or payment re-check.")
            emit("sim", dies)
            emit("sim", f"The engine re-runs the unfinished step with the same key. The simulator answers {cell['outcome']}.")
        refunded, expected = int(cell["refunded"].strip("$")), int(cell["expected"].strip("$"))
        diff = refunded - expected
        verdict = "Held" if cell["invariant_held"] else f"Violated: ${diff} too much" if diff > 0 else f"Short by ${-diff}"
        emit("result", f"{cell['refunded']} refunded in the simulator", headline=f"{cell['refunded']} refunded (simulated)",
             verdict=verdict, held=cell["invariant_held"], want_text=f"{cell['expected']} ({sc['want_text']})",
             outcome=cell["outcome"], why=explain(mode, cell["outcome"]))
