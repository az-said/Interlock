"""
Competitor run: DBOS Transact (Python, MIT) against Interlock on the refund scenarios, live.

    uv run --no-project --python 3.13 --with dbos==2.31.1 python experiments/competitor_dbos.py
    ... --reps 1 --cap-reps 2 --no-write          # smoke run, prints only

DBOS is run the way its docs describe: the refund is a @DBOS.step inside a @DBOS.workflow on Postgres, the
model's decision is its own step (recorded, never re-asked), the approval arrives as a DBOS message
(DBOS.recv, sent by the approver through DBOSClient.send), the Stripe Idempotency-Key is the workflow id plus
DBOS.step_id (stable across replay), each process has its own executor_id and a restart with the same id
recovers its pending workflows at DBOS.launch(), revocation is DBOSClient.cancel_workflow, and the shared cap is
an exactly-once datasource transaction (a conditional UPDATE in the application database).

Arms, per scenario:
    dbos          the idiomatic workflow above, no re-check inside the step
    dbos_checked  the same, plus a hand-written re-check at the top of the refund step (lookup by workflow id,
                  approval row, the payment's refunds unchanged since the decision)
    interlock     interlock.easy in a plain process (no DBOS), recovery on restart, claim TTL 40s
    dbos_cap      scenario 4 only: two bot workflows, the cap reserved in a DBOS datasource transaction

Every crash is a real SIGKILL sent by this harness to a separate worker OS process, parked at the crash point.
Ground truth is Stripe's refund list. Keys come from the environment at runtime (STRIPE_SECRET_KEY or the
Stripe CLI's test_mode_api_key; ANTHROPIC_API_KEY or /Users/kiromoussa/CADAI/.env) and are passed to workers in
their environment only. Postgres: DBOS_PG (default postgresql://postgres@localhost:55441), databases
dbos_competitor_sys and dbos_competitor_app.
"""
import argparse, base64, collections, concurrent.futures, datetime, json, os, pickle, re, shutil, signal, statistics
import subprocess, sys, tempfile, time, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import sqlalchemy as sa                                                       # noqa: E402  (installed with dbos)
from dbos import DBOS, DBOSClient, SetWorkflowID                              # noqa: E402
from dbos._datasource import SQLAlchemyDatasource                             # noqa: E402
from interlock.easy import Interlock                                          # noqa: E402
from interlock.journal import entry_hash                                      # noqa: E402
from interlock.receipts import sign, verify                                   # noqa: E402
from interlock.targets.stripe_api import StripeClient, StripeError            # noqa: E402
from backend.agent import MODEL, decide, payment_facts                        # noqa: E402

PG = os.environ.get("DBOS_PG", "postgresql://postgres@localhost:55441")
SYS_URL, APP_URL = PG + "/dbos_competitor_sys", PG + "/dbos_competitor_app"
APP_NAME, APP_VERSION = "competitor-dbos", "competitor-dbos-1"
PAID, APPROVED, CAP, CLAIM_TTL = 10000, 2000, 3000, 40
CASE_TEXT = ("Support case #4471, order #881: the customer's $100 blender arrived with a cracked glass jar and they keep "
             "the blender. Support approved a partial refund of $20.00 (2000 cents).")
BOT_TEXT = {"support-bot": "Ticket from support, case #4471: cracked glass jar on a $100 blender. Refund $20.00 (2000 cents).",
            "billing-bot": "Ticket from billing, case #4471: the blender shipped a week late. Refund $20.00 (2000 cents) as a delay credit."}
BOTS = tuple(BOT_TEXT)
SCENARIOS = {
    "crash_after_commit": {"crash": "after_commit", "action": None, "want": (1, 2000),
                           "systems": ("dbos", "dbos_checked", "interlock"),
                           "text": "worker SIGKILLed after Stripe's refund response arrived, before anything recorded it; restarted"},
    "hand_refund_during_outage": {"crash": "before_send", "action": "hand_refund", "want": (1, 2000),
                                  "systems": ("dbos", "dbos_checked", "interlock"),
                                  "text": "worker SIGKILLed right before the refund POST; support refunds the same $20 by hand (no key, no metadata); restarted. Want only the hand refund"},
    "approval_revoked_during_outage": {"crash": "before_send", "action": "revoke_cancel", "want": (0, 0),
                                       "systems": ("dbos", "interlock"),
                                       "text": "worker SIGKILLed right before the refund POST; Finance revokes: the approval row is marked revoked AND the DBOS workflow is cancelled with DBOSClient.cancel_workflow (each system uses its native channel); restarted. Want nothing"},
    "approval_revoked_row_only": {"crash": "before_send", "action": "revoke_row", "want": (0, 0),
                                  "systems": ("dbos", "dbos_checked"),
                                  "text": "as above, but Finance only marks its approval row revoked and does not know the DBOS workflow id, so nothing calls cancel_workflow. Want nothing"},
    "takeover_by_other_executor": {"crash": "before_send", "action": None, "want": (1, 2000), "systems": ("dbos",),
                                   "text": "worker SIGKILLed right before the refund POST; the process that comes up has a DIFFERENT executor_id (the first host never returns); it waits 30s, then calls DBOS.resume_workflow. Want the one refund"},
}
LANDED = ("REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP", "COMMITTED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY",
          "REAPPLIED_AFTER_QUERY")


def crash_hook(point, **info):
    """Park this process at the crash point; the harness sends the SIGKILL. One crash per run (link is atomic)."""
    if os.environ.get("CRASH") != point:
        return
    marker = os.environ["CRASH_MARKER"]
    tmp = f"{marker}.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump({"pid": os.getpid(), "point": point, **info}, f)
    try:
        os.link(tmp, marker)
    except FileExistsError:
        return
    finally:
        os.unlink(tmp)
    while True:
        time.sleep(1)


def stripe():
    return StripeClient(os.environ["STRIPE_SECRET_KEY"])


def refunds_of(c, pi):
    return c.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]


# USER CODE send BEGIN
def send_refund(c, case, amount, key, metadata):
    crash_hook("before_send")                                                                  # harness
    r = c.request("POST", "/refunds", {"payment_intent": case["payment_intent"], "amount": amount,
                                       "metadata": metadata}, idempotency_key=key)
    crash_hook("after_commit", refund=r["id"])                                                 # harness
    return {"status": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund": r["id"]}
# USER CODE send END


def read_approval(case):
    with open(case["approval_path"]) as f:
        return json.load(f)


# ---------------------------------------------------------------------------------------------- DBOS arms
# USER CODE dbos BEGIN
@DBOS.step()
def decide_step(case):
    c = stripe()
    d = decide(CASE_TEXT, c, case["payment_intent"], approved_cents=APPROVED)
    return {"amount": d["amount_cents"], "reason": d["reason"],
            "refunded_at_decision": payment_facts(c, case["payment_intent"])["refunded_cents"]}


@DBOS.step()
def refund_step(case, decision):
    return send_refund(stripe(), case, decision["amount"], f"{DBOS.workflow_id}:{DBOS.step_id}",
                       {"dbos_workflow_id": DBOS.workflow_id})


@DBOS.workflow()
def refund_case(case, checked=False):
    decision = decide_step(case)
    DBOS.set_event("decision", decision)
    approval = DBOS.recv("approval", timeout_seconds=600)
    if not approval or decision["amount"] > approval["max_cents"]:
        return {"status": "REFUSED:not_approved"}
    return (checked_refund_step if checked else refund_step)(case, decision)
# USER CODE dbos END


@DBOS.step()
def checked_refund_step(case, decision):
    c, wf = stripe(), DBOS.workflow_id
    # USER CODE dbos_check BEGIN
    refunds = refunds_of(c, case["payment_intent"])
    mine = [r for r in refunds if r["metadata"].get("dbos_workflow_id") == wf]
    if mine:
        return {"status": "FOUND_BY_LOOKUP", "refund": mine[0]["id"]}
    grant = read_approval(case)
    if grant["revoked"] is not None or decision["amount"] > grant["max_cents"]:
        return {"status": "REFUSED:approval_revoked"}
    now = sum(r["amount"] for r in refunds if r["status"] != "failed")
    if now != decision["refunded_at_decision"]:
        return {"status": "REFUSED:stale_premise", "refunded_now": now}
    # USER CODE dbos_check END
    return send_refund(c, case, decision["amount"], f"{wf}:{DBOS.step_id}", {"dbos_workflow_id": wf})


# USER CODE dbos_cap BEGIN
CAP_DDL = ["CREATE TABLE IF NOT EXISTS cap_budget (case_id TEXT PRIMARY KEY, cap INT NOT NULL, used INT NOT NULL)",
           "CREATE TABLE IF NOT EXISTS cap_reservations (id SERIAL PRIMARY KEY, case_id TEXT, bot TEXT, amount INT, "
           "granted BOOLEAN, workflow_id TEXT, at TIMESTAMPTZ DEFAULT now())"]
CAP_DS = []


def reserve_body(case_id, bot, amount):
    s = CAP_DS[0].sql_session()
    row = s.execute(sa.text("UPDATE cap_budget SET used = used + :a WHERE case_id = :c AND used + :a <= cap "
                            "RETURNING used"), {"a": amount, "c": case_id}).first()
    s.execute(sa.text("INSERT INTO cap_reservations (case_id, bot, amount, granted, workflow_id) VALUES (:c, :b, :a, :g, :w)"),
              {"c": case_id, "b": bot, "a": amount, "g": row is not None, "w": DBOS.workflow_id})
    return {"granted": row is not None, "used_after": row[0] if row else None}


@DBOS.step()
def cap_decide_step(case, bot):
    return {"amount": decide(BOT_TEXT[bot], stripe(), case["payment_intent"], approved_cents=CAP)["amount_cents"]}


@DBOS.step()
def cap_refund_step(case, bot, amount):
    return send_refund(stripe(), case, amount, f"{DBOS.workflow_id}:{DBOS.step_id}",
                       {"bot": bot, "dbos_workflow_id": DBOS.workflow_id})


@DBOS.workflow()
def cap_refund(case, bot):
    decision = cap_decide_step(case, bot)
    grant = CAP_DS[1](case["id"], bot, decision["amount"])
    if not grant["granted"]:
        return {"status": "REFUSED:over_cap", **grant}
    return {**cap_refund_step(case, bot, decision["amount"]), **grant}
# USER CODE dbos_cap END


def dbos_worker(a, case):
    # USER CODE dbos_launch BEGIN
    DBOS(config={"name": f"{APP_NAME}-{a.app}", "system_database_url": SYS_URL, "executor_id": a.executor,
                 "application_version": f"{APP_VERSION}-{a.app}", "log_level": "WARNING"})
    if a.mode == "cap":
        CAP_DS[:] = [SQLAlchemyDatasource.create(APP_URL)]
        CAP_DS.append(CAP_DS[0].transaction(name="reserve_cap")(reserve_body))
    DBOS.launch()                                            # recovers this executor's PENDING workflows
    # USER CODE dbos_launch END
    if a.go_at:
        time.sleep(max(0, a.go_at - time.time()))
    notes = {}
    if a.takeover_wait:
        handle = DBOS.retrieve_workflow(a.wf)
        seen, t0 = [], time.time()
        while time.time() - t0 < a.takeover_wait:
            seen.append(handle.get_status().status)
            time.sleep(2)
        refunds = [r["id"] for r in refunds_of(stripe(), case["payment_intent"]) if r["metadata"].get("dbos_workflow_id") == a.wf]
        notes = {"status_while_waiting": sorted(set(seen)), "refunds_after_wait": refunds, "waited_s": a.takeover_wait}
        try:
            DBOS.resume_workflow(a.wf)
            notes["resume"] = "called DBOS.resume_workflow"
        except Exception as e:
            notes["resume"] = f"{type(e).__name__}: {e}"[:300]
    elif a.restart:
        handle = DBOS.retrieve_workflow(a.wf)
    else:
        with SetWorkflowID(a.wf):
            handle = (DBOS.start_workflow(cap_refund, case, a.bot) if a.mode == "cap"
                      else DBOS.start_workflow(refund_case, case, a.system == "dbos_checked"))
    try:
        out = handle.get_result()
    except Exception as e:
        out = {"status": handle.get_status().status, "error": type(e).__name__}
    if a.mode == "cap":
        # A DBOS app is a long-running service, and recovery re-enqueues a workflow on an internal queue that any
        # process of the same app can dequeue. Stay up while this run's other workflow is unfinished, so a workflow
        # this process dequeued is not abandoned by an early exit (a harness exit, not DBOS behavior).
        others = [DBOS.retrieve_workflow(f"cap-{a.app}-{b}") for b in BOTS]
        t0 = time.time()
        while time.time() - t0 < 120 and any(h.get_status().status in ("PENDING", "ENQUEUED") for h in others):
            time.sleep(0.2)
    DBOS.destroy()
    return {**out, **notes}


# ---------------------------------------------------------------------------------------------- Interlock arm
def interlock_worker(a, case):
    c = stripe()
    # USER CODE interlock_decision BEGIN
    path = os.path.join(case["state"], "decision.json")
    if not os.path.exists(path):
        d = decide(CASE_TEXT, c, case["payment_intent"], approved_cents=APPROVED)
        with open(path + ".tmp", "w") as f:
            json.dump({"amount": d["amount_cents"], "reason": d["reason"]}, f)
        os.replace(path + ".tmp", path)
    with open(path) as f:
        decision = json.load(f)
    while not os.path.exists(case["approval_path"]):
        time.sleep(0.2)
    # USER CODE interlock_decision END
    # USER CODE interlock BEGIN
    gate = Interlock(os.path.join(case["state"], "interlock"), claim_ttl=CLAIM_TTL)

    def lookup(case, eid):
        return next((r["id"] for r in refunds_of(c, case["payment_intent"])
                     if r["metadata"].get("interlock_effect_id") == eid), None)

    def approval_live(case, amount):
        grant = read_approval(case)
        return grant["revoked"] is None and amount <= grant["max_cents"]

    @gate.effect(key=lambda case, amount: f"refund:{case['id']}",
                 premises=lambda case, amount, idempotency_key: {"refunded_by_others": sum(
                     r["amount"] for r in refunds_of(c, case["payment_intent"])
                     if r["status"] != "failed" and r["metadata"].get("interlock_effect_id") != idempotency_key)},
                 lookup=lambda case, amount, idempotency_key: lookup(case, idempotency_key),
                 dedupes=True, allowed=approval_live)
    def refund(case, amount, idempotency_key):
        return send_refund(c, case, amount, idempotency_key, {"interlock_effect_id": idempotency_key})["refund"]

    refund.gate.target.query = lambda eid, effect: lookup(effect["args"][0], eid)      # keep the refund id, not bool
    deadline = time.time() + CLAIM_TTL + 30
    while True:
        status = next(iter(refund.gate.recover().values()), None) or refund(case, decision["amount"])[0]
        if status != "IN_FLIGHT" or time.time() > deadline:
            break
        time.sleep(1)
    # USER CODE interlock END
    bundle = refund.gate.receipt_bundle(refund.proposal(case, decision["amount"]))
    with open(os.path.join(case["state"], "receipt.json"), "w") as f:
        json.dump(bundle, f)
    return {"status": status, "effect_id": bundle["effect_id"], "refund": lookup(case, bundle["effect_id"]),
            "decision": decision}


def worker_main(argv):
    ap = argparse.ArgumentParser()
    for flag in ("--system", "--case", "--wf", "--executor", "--bot", "--app"):
        ap.add_argument(flag)
    ap.add_argument("--mode", default="single")
    ap.add_argument("--restart", action="store_true")
    ap.add_argument("--go-at", type=float, default=0)
    ap.add_argument("--takeover-wait", type=float, default=0)
    a = ap.parse_args(argv)
    case = json.loads(a.case)
    try:
        out = interlock_worker(a, case) if a.system == "interlock" else dbos_worker(a, case)
    except StripeError as e:
        out = {"status": "STRIPE_ERROR", "error": str(e)[:300]}
    name = f"result{'-' + a.bot if a.bot else ''}.json"
    with open(os.path.join(case["state"], name), "w") as f:
        json.dump(out, f, default=str)


# ---------------------------------------------------------------------------------------------- harness
def keys():
    s = os.environ.get("STRIPE_SECRET_KEY")
    if not s:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True).stdout
        s = next(iter(re.findall(r"^test_mode_api_key\s*=\s*'?(sk_test_[^'\s]+)", out, re.M)), None)
    k = os.environ.get("ANTHROPIC_API_KEY")
    if not k:
        with open("/Users/kiromoussa/CADAI/.env") as f:
            k = next(l.split("=", 1)[1].strip().strip("'\"") for l in f if l.startswith("ANTHROPIC_API_KEY="))
    if not (s or "").startswith(("sk_test_", "rk_test_")):
        sys.exit("refusing to run: a Stripe test-mode key is required")
    return s, k


def engine(url):
    return sa.create_engine(url.replace("postgresql://", "postgresql+psycopg://"))


def spawn(env, d, args, tag):
    log = open(os.path.join(d, f"{tag}.log"), "w")
    return subprocess.Popen([sys.executable, os.path.abspath(__file__), "worker", *args], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)


def wait_marker(d, procs, timeout=150):
    marker, t0 = os.path.join(d, "crash.json"), time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(marker):
            try:
                with open(marker) as f:
                    return json.load(f)
            except ValueError:
                pass
        if all(p.poll() is not None for p in procs):
            return None
        time.sleep(0.05)
    return None


def dbos_record(client, sys_engine, wf, tamper=True):
    """What DBOS keeps for a workflow, decoded, and what happens when a refund step's recorded output is edited."""
    with sys_engine.connect() as cx:
        st = cx.execute(sa.text("SELECT status, executor_id, recovery_attempts, created_at, updated_at FROM dbos.workflow_status "
                                "WHERE workflow_uuid = :w"), {"w": wf}).mappings().first()
    steps = client.list_workflow_steps(wf)
    rec = {"workflow_status": dict(st) if st else None,
           "steps": [{"function_id": s["function_id"], "function_name": s["function_name"],
                      "output": s["output"], "error": repr(s["error"]) if s["error"] else None,
                      "started_ms": s["started_at_epoch_ms"], "completed_ms": s["completed_at_epoch_ms"]} for s in steps],
           "hash_or_signature_columns": False}
    target = next((s for s in steps if "refund_step" in s["function_name"] and isinstance(s["output"], dict)), None)
    if tamper and target:
        forged = {**target["output"], "refund": "re_FORGED_BY_DB_WRITER", "status": "REFUSED:approval_revoked"}
        with sys_engine.begin() as cx:
            cx.execute(sa.text("UPDATE dbos.operation_outputs SET output = :o WHERE workflow_uuid = :w AND function_id = :f"),
                       {"o": base64.b64encode(pickle.dumps(forged)).decode(), "w": wf, "f": target["function_id"]})
        back = next(s for s in client.list_workflow_steps(wf) if s["function_id"] == target["function_id"])
        rec["tamper_test"] = {"edited": "operation_outputs.output of " + target["function_name"],
                              "forged": forged, "read_back_through_dbos": back["output"],
                              "detected": back["output"] != forged}
    return rec


def interlock_record(d):
    path = os.path.join(d, "receipt.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        b = json.load(f)
    v = verify(b)
    out = {"kinds": [e["kind"] for e in b["entries"]], "verify": {k: v[k] for k in (
        "valid", "tamper_evident", "signed", "happened", "happened_once", "authorized_when_fired", "assumptions_held",
        "refused", "evidence", "rechecked_at_recovery", "problems")}}
    edited = json.loads(json.dumps(b))
    edited["entries"][-1]["reason" if "reason" in edited["entries"][-1] else "via"] = "forged"
    forged = json.loads(json.dumps(edited))
    prev = None
    for e in forged["entries"]:                                    # a writer who rebuilds the chain
        e["prev"] = prev
        e["hash"] = entry_hash(e)
        prev = e["hash"]
    key = "harness-held-key"
    signed_original = {**b, "signature": sign(b["effect_id"], b["entries"], key)}
    out["tamper_test"] = {"one_entry_edited_valid": verify(edited)["valid"],
                          "chain_rebuilt_unsigned_valid": verify(forged)["valid"],
                          "chain_rebuilt_with_outside_key_valid": verify({**forged, "signature": signed_original["signature"]}, key)["valid"],
                          "original_with_outside_key_valid": verify(signed_original, key)["valid"]}
    out["bundle"] = b
    return out


def run_cell(env, client, sys_engine, scenario, system, rep, scratch):
    spec, t_start = SCENARIOS[scenario], time.time()
    pi = client.test_payment(PAID)
    run = uuid.uuid4().hex[:10]
    d = tempfile.mkdtemp(prefix=f"dbos-{scenario[:12]}-", dir=scratch)
    case = {"id": f"case-4471-{run}", "payment_intent": pi, "approval_path": os.path.join(d, "approval.json"), "state": d}
    wf, executor = f"refund-{run}", f"{run}-worker"
    base = ["--system", system, "--case", json.dumps(case), "--wf", wf, "--executor", executor, "--app", run]
    cenv = {**env, "CRASH": spec["crash"], "CRASH_MARKER": os.path.join(d, "crash.json")}
    dclient = (DBOSClient(system_database_url=SYS_URL, application_name=f"{APP_NAME}-{run}")
               if system.startswith("dbos") else None)
    p1, error = spawn(cenv, d, base, "worker1"), None
    if dclient:
        decision = dclient.get_event(wf, "decision", timeout_seconds=150)
    else:
        path, t0 = os.path.join(d, "decision.json"), time.time()
        while not os.path.exists(path) and time.time() - t0 < 150 and p1.poll() is None:
            time.sleep(0.1)
        decision = json.load(open(path)) if os.path.exists(path) else None
    grant = {"max_cents": APPROVED, "by": "support-lead", "approved_at": time.time(), "revoked": None}
    with open(case["approval_path"] + ".tmp", "w") as f:
        json.dump(grant, f)
    os.replace(case["approval_path"] + ".tmp", case["approval_path"])
    if dclient:
        dclient.send(wf, {"max_cents": APPROVED, "by": "support-lead"}, topic="approval")
    marker = wait_marker(d, [p1])
    exits, killed = [], None
    if marker:
        killed = {"pid": marker["pid"], "process": "python3.13 (competitor_dbos.py worker)", "point": marker["point"]}
        os.kill(marker["pid"], signal.SIGKILL)
    else:
        error = "crash point never reached"
        p1.kill()
    exits.append(p1.wait())
    t_crash = time.time()
    hand = None
    if spec["action"] == "hand_refund":
        hand = client.request("POST", "/refunds", {"payment_intent": pi, "amount": APPROVED})["id"]
    elif spec["action"] in ("revoke_cancel", "revoke_row"):
        grant["revoked"] = time.time()
        with open(case["approval_path"] + ".tmp", "w") as f:
            json.dump(grant, f)
        os.replace(case["approval_path"] + ".tmp", case["approval_path"])
        if spec["action"] == "revoke_cancel" and dclient:
            dclient.cancel_workflow(wf)
    renv = {**env, "CRASH": "none", "CRASH_MARKER": os.path.join(d, "crash.json")}
    rargs = list(base)
    if scenario == "takeover_by_other_executor":
        rargs[rargs.index("--executor") + 1] = executor + "-other"
        rargs += ["--takeover-wait", "30"]
    else:
        rargs.append("--restart")
    p2 = spawn(renv, d, rargs, "worker2")
    try:
        exits.append(p2.wait(timeout=240))
    except subprocess.TimeoutExpired:
        p2.kill()
        exits.append(p2.wait())
        error = (error or "") + " restart timed out"
    t_settled = time.time()
    try:
        result = json.load(open(os.path.join(d, "result.json")))
    except (FileNotFoundError, ValueError):
        result = {"status": None}
    refunds = refunds_of(client, pi)
    live = [r for r in refunds if r["status"] != "failed"]
    count, total = len(live), sum(r["amount"] for r in live)
    tag = ("interlock_effect_id", result.get("effect_id")) if system == "interlock" else ("dbos_workflow_id", wf)
    mine = [r["id"] for r in refunds if tag[1] and r["metadata"].get(tag[0]) == tag[1]]
    status = str(result.get("status"))
    answer_ok = bool(mine) == status.startswith(LANDED)
    record = dbos_record(dclient, sys_engine, wf) if dclient else interlock_record(d)
    logs = {n: open(os.path.join(d, n)).read()[-1500:] for n in os.listdir(d) if n.endswith(".log")}
    if dclient:
        dclient.destroy()
    shutil.rmtree(d)
    return {"scenario": scenario, "system": system, "rep": rep, "payment_intent": pi, "case": case["id"], "workflow_id": wf,
            "decision": decision, "killed": killed, "exit_codes": exits, "hand_refund": hand, "status": status,
            "result": result, "refunds": [{"id": r["id"], "amount": r["amount"], "status": r["status"],
                                           "metadata": r["metadata"]} for r in refunds],
            "count": count, "total_cents": total, "want": spec["want"],
            "invariant_held": (count, total) == tuple(spec["want"]), "agent_refunds": mine, "answer_matches_stripe": answer_ok,
            "seconds_crash_to_settled": round(t_settled - t_crash, 1), "seconds_total": round(t_settled - t_start, 1),
            "record": record, "error": error, "logs": {n: t for n, t in logs.items() if "Traceback" in t or error}}


def run_cap(env, client, sys_engine, app_engine, crash, rep, scratch):
    pi, run = client.test_payment(PAID), uuid.uuid4().hex[:10]
    d = tempfile.mkdtemp(prefix="dbos-cap-", dir=scratch)
    case = {"id": f"case-4471-{run}", "payment_intent": pi, "state": d}
    with app_engine.begin() as cx:
        cx.execute(sa.text("INSERT INTO cap_budget (case_id, cap, used) VALUES (:c, :cap, 0)"), {"c": case["id"], "cap": CAP})
    go_at = time.time() + 6
    cenv = {**env, "CRASH": crash, "CRASH_MARKER": os.path.join(d, "crash.json")}

    def args(bot):
        return ["--system", "dbos_cap", "--mode", "cap", "--bot", bot, "--case", json.dumps(case), "--wf", f"cap-{run}-{bot}",
                "--executor", f"{run}-{bot}", "--app", run, "--go-at", str(go_at)]

    procs = {b: spawn(cenv, d, args(b), b) for b in BOTS}
    exits, killed, t_crash, deadline, timed_out = collections.defaultdict(list), None, None, time.time() + 240, False
    marker_path = os.path.join(d, "crash.json")
    while procs:
        if killed is None and os.path.exists(marker_path):
            try:
                m = json.load(open(marker_path))
                bot = next(b for b, p in procs.items() if p.pid == m["pid"])
                killed = {"pid": m["pid"], "bot": bot, "point": m["point"], "process": "python3.13 (competitor_dbos.py worker)"}
                os.kill(m["pid"], signal.SIGKILL)
            except (ValueError, StopIteration):
                pass
        for bot, p in list(procs.items()):
            code = p.poll()
            if code is None:
                continue
            exits[bot].append(code)
            del procs[bot]
            if killed and bot == killed["bot"] and code == -9 and t_crash is None:
                t_crash = time.time()
                procs[bot] = spawn({**env, "CRASH": "none", "CRASH_MARKER": marker_path}, d,
                                   [x for x in args(bot) if x not in ("--go-at", str(go_at))] + ["--restart"], bot + ".restart")
        if time.time() > deadline:
            for p in procs.values():
                p.kill()
                p.wait()
            timed_out = True
            break
        time.sleep(0.05)
    t_settled = time.time()
    refunds = refunds_of(client, pi)
    live = [r for r in refunds if r["status"] != "failed"]
    total = sum(r["amount"] for r in live)
    results = {}
    for bot in BOTS:
        try:
            results[bot] = json.load(open(os.path.join(d, f"result-{bot}.json")))
        except (FileNotFoundError, ValueError):
            results[bot] = None
    with app_engine.connect() as cx:
        reservations = [dict(r) for r in cx.execute(sa.text(
            "SELECT bot, amount, granted, workflow_id, at::text FROM cap_reservations WHERE case_id = :c ORDER BY id"),
            {"c": case["id"]}).mappings()]
        budget = cx.execute(sa.text("SELECT used FROM cap_budget WHERE case_id = :c"), {"c": case["id"]}).scalar()
    with sys_engine.connect() as cx:
        wstatus = {r["workflow_uuid"]: dict(r) for r in cx.execute(sa.text(
            "SELECT workflow_uuid, status, recovery_attempts FROM dbos.workflow_status WHERE workflow_uuid LIKE :p"),
            {"p": f"cap-{run}-%"}).mappings()}
    logs = {n: open(os.path.join(d, n)).read()[-1500:] for n in os.listdir(d) if n.endswith(".log")}
    if not os.environ.get("COMPETITOR_KEEP"):
        shutil.rmtree(d)
    return {"scenario": "shared_cap", "system": "dbos_cap", "crash": crash, "rep": rep, "payment_intent": pi, "case": case["id"],
            "killed": killed, "exit_codes": dict(exits), "timed_out": timed_out,
            "statuses": {b: (results[b] or {}).get("status") for b in BOTS}, "results": results,
            "refunds": [{"id": r["id"], "amount": r["amount"], "status": r["status"], "bot": r["metadata"].get("bot")} for r in refunds],
            "count": len(live), "total_cents": total, "invariant_held": total <= CAP and not timed_out,
            "reservations": reservations, "budget_used": budget, "workflow_status": wstatus,
            "reservations_match_stripe": budget == total,
            "seconds_crash_to_settled": round(t_settled - t_crash, 1) if t_crash else None,
            "logs": {n: t for n, t in logs.items() if "Traceback" in t}}


def user_lines():
    """Non-blank, non-comment lines inside each USER CODE section of this file; harness hooks excluded."""
    sections, cur = collections.Counter(), None
    for line in open(os.path.abspath(__file__)):
        m = re.match(r"\s*# USER CODE (\w+) (BEGIN|END)", line)
        if m:
            cur = m.group(1) if m.group(2) == "BEGIN" else None
            continue
        s = line.strip()
        if cur and s and not s.startswith("#") and not s.endswith("# harness"):
            sections[cur] += 1
    arms = {"dbos": ["send", "dbos", "dbos_launch"], "dbos_checked": ["send", "dbos", "dbos_launch", "dbos_check"],
            "interlock": ["send", "interlock_decision", "interlock"], "dbos_cap": ["send", "dbos_cap", "dbos_launch"]}
    return {"sections": dict(sections), "arms": {a: sum(sections[s] for s in ss) for a, ss in arms.items()},
            "note": "dbos_launch includes the two datasource lines only dbos_cap uses; dbos_cap reuses nothing from the dbos section"}


def median(xs):
    return round(statistics.median(xs), 1) if xs else None


def summarize(runs, cap_runs):
    cells = []
    for sc, spec in SCENARIOS.items():
        for sy in spec["systems"]:
            rs = [r for r in runs if r["scenario"] == sc and r["system"] == sy]
            if rs:
                cells.append({"scenario": sc, "system": sy, "runs": len(rs), "held": sum(r["invariant_held"] for r in rs),
                              "answers_match": sum(r["answer_matches_stripe"] for r in rs),
                              "statuses": dict(collections.Counter(r["status"] for r in rs)),
                              "totals": dict(collections.Counter(f"${r['total_cents'] / 100:.0f} in {r['count']}" for r in rs)),
                              "median_settle_s": median([r["seconds_crash_to_settled"] for r in rs]),
                              "settle_s": [r["seconds_crash_to_settled"] for r in rs],
                              "sigkill_exits": sum(-9 in r["exit_codes"] for r in rs), "errors": [r["error"] for r in rs if r["error"]]})
    for crash in ("after_commit", "before_send"):
        rs = [r for r in cap_runs if r["crash"] == crash]
        if rs:
            cells.append({"scenario": "shared_cap", "system": "dbos_cap", "crash": crash, "runs": len(rs),
                          "held": sum(r["invariant_held"] for r in rs),
                          "reservations_match_stripe": sum(r["reservations_match_stripe"] for r in rs),
                          "outcomes": dict(collections.Counter(
                              f"crashed {r['statuses'].get((r['killed'] or {}).get('bot'))} / other "
                              f"{r['statuses'].get(next((b for b in BOTS if b != (r['killed'] or {}).get('bot')), None))}" for r in rs)),
                          "totals": dict(collections.Counter(f"${r['total_cents'] / 100:.0f} in {r['count']}" for r in rs)),
                          "median_settle_s": median([r["seconds_crash_to_settled"] for r in rs if r["seconds_crash_to_settled"]]),
                          "crashes": sum(bool(r["killed"]) for r in rs), "timed_out": sum(r["timed_out"] for r in rs)})
    return cells


def cell_text(c):
    if c["scenario"] == "shared_cap":
        return (f"**held {c['held']}/{c['runs']}**; Stripe: {', '.join(f'{v}x {k}' for k, v in sorted(c['totals'].items()))}; "
                f"crash in {c['crashes']}/{c['runs']}; median {c['median_settle_s']}s crash to settled; reservation rows equal "
                f"Stripe's total in {c['reservations_match_stripe']}/{c['runs']}")
    return (f"**held {c['held']}/{c['runs']}**; {', '.join(f'{v}x {k}' for k, v in c['statuses'].items())}; Stripe "
            f"{', '.join(f'{v}x {k}' for k, v in sorted(c['totals'].items()))}; answer matches Stripe {c['answers_match']}/{c['runs']}; "
            f"crash to settled {', '.join(str(s) for s in c['settle_s'])}s")


def write(out, path_md, path_json):
    with open(path_json, "w") as f:
        json.dump(out, f, indent=1, default=str)
    lines = [f"Generated {out['generated']} by `experiments/competitor_dbos.py`. dbos {out['versions']['dbos']}, Postgres "
             f"{out['versions']['postgres']}, Python {out['versions']['python']}, model `{MODEL}`, Stripe test mode.", "",
             "| scenario | system | result |", "|---|---|---|"]
    lines += [f"| `{c['scenario']}`{' / ' + c['crash'] if c.get('crash') else ''} | {c['system']} | {cell_text(c)} |" for c in out["cells"]]
    lines += ["", "Lines of user code per arm (non-blank, non-comment, harness hooks excluded): "
              + ", ".join(f"{a} {n}" for a, n in out["user_lines"]["arms"].items()), ""]
    lines += ["Ids:", ""] + [f"- `{r['scenario']}` / {r['system']} rep {r['rep']}: PaymentIntent `{r['payment_intent']}`, status "
                             f"{r['status']}, refunds {', '.join(x['id'] + ' ' + x['status'] for x in r['refunds']) or 'none'}, "
                             f"exits {r['exit_codes']}" for r in out["runs"]]
    lines += [f"- `shared_cap` / {r['crash']} rep {r['rep']}: PaymentIntent `{r['payment_intent']}`, killed "
              f"{(r['killed'] or {}).get('bot')}, statuses {r['statuses']}, refunds "
              f"{', '.join(x['id'] + ' ' + str(x['bot']) for x in r['refunds']) or 'none'}, exits {r['exit_codes']}" for r in out["cap_runs"]]
    with open(path_md, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--cap-reps", type=int, default=20)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--scratch", default=os.environ.get("COMPETITOR_SCRATCH"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "competitors"))
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    s, k = keys()
    client = StripeClient(s)
    env = {**os.environ, "STRIPE_SECRET_KEY": s, "ANTHROPIC_API_KEY": k, "PYTHONPATH": ROOT}
    sys_engine, app_engine = engine(SYS_URL), engine(APP_URL)
    with app_engine.begin() as cx:
        for ddl in CAP_DDL:
            cx.execute(sa.text(ddl))
    only = set(a.only) if a.only is not None else set(SCENARIOS) | {"shared_cap"}
    jobs = [(sc, sy, rep) for rep in range(a.reps) for sc, spec in SCENARIOS.items() if sc in only for sy in spec["systems"]]
    runs, cap_runs = [], []
    with concurrent.futures.ThreadPoolExecutor(a.parallel) as pool:
        for r in pool.map(lambda j: run_cell(env, client, sys_engine, *j, a.scratch), jobs):
            runs.append(r)
            print(f"{r['scenario']:32} {r['system']:13} rep {r['rep']}  {r['status']:34} ${r['total_cents'] / 100:.0f} in {r['count']} "
                  f"held={r['invariant_held']} answer_ok={r['answer_matches_stripe']} settle={r['seconds_crash_to_settled']}s "
                  f"exits={r['exit_codes']} {r['error'] or ''}", flush=True)
        if "shared_cap" in only:
            cjobs = [(c, rep) for rep in range(a.cap_reps) for c in ("after_commit", "before_send")]
            for r in pool.map(lambda j: run_cap(env, client, sys_engine, app_engine, *j, a.scratch), cjobs):
                cap_runs.append(r)
                print(f"shared_cap {r['crash']:12} rep {r['rep']:2} ${r['total_cents'] / 100:.0f} in {r['count']} held={r['invariant_held']} "
                      f"killed={(r['killed'] or {}).get('bot')} {r['statuses']} settle={r['seconds_crash_to_settled']}s", flush=True)
    import importlib.metadata as md
    with sys_engine.connect() as cx:
        pg_version = cx.execute(sa.text("SHOW server_version")).scalar()
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "model": MODEL,
           "versions": {"dbos": md.version("dbos"), "postgres": pg_version, "python": sys.version.split()[0]},
           "scenarios": {k: {x: v[x] for x in ("text", "want", "systems")} for k, v in SCENARIOS.items()},
           "user_lines": user_lines(), "cells": summarize(runs, cap_runs), "runs": runs, "cap_runs": cap_runs}
    for c in out["cells"]:
        print(cell_text(c) if c["scenario"] == "shared_cap" else f"{c['scenario']} / {c['system']}: {cell_text(c)}")
    print(json.dumps(out["user_lines"]))
    if not a.no_write:
        os.makedirs(a.out, exist_ok=True)
        write(out, os.path.join(a.out, "dbos.generated.md"), os.path.join(a.out, "dbos.json"))
        print("wrote", os.path.join(a.out, "dbos.json"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker_main(sys.argv[2:])
    else:
        main()
