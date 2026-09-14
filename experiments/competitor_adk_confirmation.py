"""
Competitor run: Google ADK's own approval gate and resume, with no Interlock anywhere in the agent.

    export ANTHROPIC_API_KEY=...        # else read from /Users/kiromoussa/CADAI/.env at runtime, never printed
    uv run --no-project --python 3.13 --with google-adk==2.9.0 --with litellm \
        python experiments/competitor_adk_confirmation.py [scenario:arm ...] [--reps N] [--cap-reps N]

Configured the way ADK's docs and source recommend for a tool with a side effect that needs a person:
`FunctionTool(issue_refund, require_confirmation=True)` pauses the call until a person answers
`adk_request_confirmation` with a ToolConfirmation; `App(resumability_config=ResumabilityConfig(is_resumable=True))`
over `SqliteSessionService` lets a new OS process resume the invocation with `run_async(invocation_id=...)`; and,
because the ResumabilityConfig docstring says resumed tools run at-least-once and must be idempotent, the refund
POST carries Idempotency-Key = invocation id + "/" + function call id. Shared cap state uses ADK's `app:` state.

Every Stripe call is test mode, every decision is a real Claude call through ADK's LiteLlm, and every crash is
`os.kill(os.getpid(), SIGKILL)` in a separate agent process (backend.config.crash_once). Ground truth is Stripe's
refund list. Writes results/competitors/adk_confirmation.json and .md unless cells are named on the command line.
Lines between `# >>> user:<tag>` and `# <<< user:<tag>` are the code an ADK user writes; they are counted per arm.
"""
import asyncio, datetime, fcntl, json, os, re, shutil, signal, sqlite3, statistics, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend import config                                   # Stripe test client and crash_once only
from backend.agent import AgentError, payment_facts, validate_refund

MODEL = os.environ.get("ADK_MODEL", "anthropic/claude-haiku-4-5-20251001")
PAID, APPROVED, CAP, APP, CONFIRM = 10000, 2000, 3000, "refunds", "adk_request_confirmation"
SENT = {"REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP"}
OUT = os.path.join(ROOT, "results", "competitors")
INSTRUCTION = ("You are a payments support agent. Call get_payment, then call issue_refund exactly once with the refund "
               "your ticket approves, in integer cents, and a short reason. A person must confirm issue_refund: calling "
               "it is how that confirmation is requested, so never ask for confirmation in text. If "
               "issue_refund is rejected or refused, do not call it again. Finish with one sentence saying what happened.")
CASE_TEXT = ("Order #881, paid $100.00 by card. The blender arrived with its glass jar cracked. Support case #4471: "
             "support reviewed the photos and approved ONE partial refund of $20.00 for the jar; the customer keeps "
             "the blender. Issue the approved refund.")
TICKETS = {
    "support-bot": "Case #4471, order #881, paid $100.00 by card. Support ticket: the glass jar arrived cracked; support "
                   "approved a $20.00 partial refund for the jar. Case #4471 allows at most $30.00 of refunds in total. "
                   "Issue the approved refund.",
    "billing-bot": "Case #4471, order #881, paid $100.00 by card. Billing ticket: delivery was six days late; billing "
                   "approved a $20.00 goodwill refund. Case #4471 allows at most $30.00 of refunds in total. "
                   "Issue the approved refund.",
}

ARMS = {
    "adk_confirm": ("ADK: require_confirmation + resumable App + SQLite sessions + call-id idempotency key",
                    ["tool", "wiring", "approver"]),
    "adk_confirm_reject": ("ADK as above; the approver's revocation is sent as ToolConfirmation(confirmed=False) and that "
                           "message resumes the invocation", ["tool", "wiring", "approver"]),
    "adk_confirm_checked": ("ADK as above plus a hand-written re-check in the tool body (lookup, approval row, refunds "
                            "unchanged)", ["tool", "wiring", "approver", "recheck"]),
    "adk_app_state": ("ADK as above; the $30 cap is ADK `app:` state shared by both bots' sessions",
                      ["tool", "wiring", "approver", "cap_app_state"]),
    "adk_flock": ("ADK as above; the cap check (Stripe read) and POST inside an fcntl.flock both bots open",
                  ["tool", "wiring", "approver", "cap_flock"]),
}
AFTER = "agent process SIGKILLed after Stripe's response to the refund POST arrived, before ADK recorded the tool response"
BEFORE = "agent process SIGKILLed right before the refund POST"
SCENARIOS = {
    "crash_after_commit": dict(crash="after_commit", action=None, want_cents=2000, want_refunds=1,
                               arms=["adk_confirm", "adk_confirm_checked"],
                               text=f"approved; {AFTER}; restarted and resumed. Want: $20 in 1 refund",
                               interlock="crash_after_commit"),
    "hand_refund_during_outage": dict(crash="before_send", action="hand_refund", want_cents=2000, want_refunds=1,
                                      arms=["adk_confirm", "adk_confirm_checked"],
                                      text=f"approved; {BEFORE}; support refunds the same $20 by hand in Stripe; "
                                           "restarted and resumed. Want: only the hand refund",
                                      interlock="hand_refund_during_outage"),
    "approval_revoked_during_outage": dict(crash="before_send", action="revoke", want_cents=0, want_refunds=0,
                                           arms=["adk_confirm", "adk_confirm_reject", "adk_confirm_checked"],
                                           text=f"approved; {BEFORE}; the approver revokes the approval; restarted and "
                                                "resumed. Want: nothing",
                                           interlock="mandate_revoked_during_outage"),
}
CAP_ARMS, CAP_CRASHES = ["adk_app_state", "adk_flock"], ["after_commit", "before_send", "none"]   # none: a pure race


# ---------------------------------------------------------------- the agent process

def agent_main(cell_dir, phase, bot):
    from google.adk.agents import LlmAgent
    from google.adk.apps import App, ResumabilityConfig
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions.sqlite_session_service import SqliteSessionService
    from google.adk.tools import FunctionTool, ToolContext
    from google.genai import types

    cell = json.load(open(os.path.join(cell_dir, "cell.json")))
    arm, pi, tag, client = cell["arm"], cell["payment_intent"], f"{cell['case_id']}/{bot}", config.stripe()
    ids_path, approval_path = os.path.join(cell_dir, f"ids-{bot}.json"), os.path.join(cell_dir, "approval.json")

    def log(**kw):
        with open(os.path.join(cell_dir, f"agent-{bot}.jsonl"), "a") as f:
            f.write(json.dumps({"ts": time.time(), "phase": phase, "pid": os.getpid(), **kw}, default=str) + "\n")

    def stripe_refunds():
        return [r for r in client.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"] if r["status"] != "failed"]

    def get_payment(tool_context: ToolContext) -> dict:
        """Live facts for this case's Stripe payment, in cents: paid, already refunded, still refundable."""
        facts = payment_facts(client, pi)
        if arm == "adk_confirm_checked":
            # >>> user:recheck
            tool_context.state["refunded_at_decision"] = facts["refunded_cents"]
            # <<< user:recheck
        return facts

    def issue_refund(amount_cents: int, reason: str, tool_context: ToolContext) -> dict:
        """Refund this case's payment by amount_cents (integer cents). A person must confirm the call first."""
        lock = None
        # >>> user:tool
        facts = payment_facts(client, pi)
        try:        # the model's arguments are untrusted input
            amount = validate_refund({"amount_cents": amount_cents, "reason": reason}, facts["paid_cents"],
                                     facts["refunded_cents"], APPROVED)["amount_cents"]
        except AgentError as e:
            return {"status": "REFUSED:invalid", "error": str(e)}
        key = f"{tool_context.invocation_id}/{tool_context.function_call_id}"     # stable across ADK's resume
        # <<< user:tool
        if arm == "adk_confirm_checked":
            # >>> user:recheck
            refunds = stripe_refunds()
            mine = [r["id"] for r in refunds if r["metadata"].get("adk_case") == tag]
            if mine:
                return {"status": "FOUND_BY_LOOKUP", "refund_id": mine[0]}
            if json.load(open(approval_path))["status"] != "approved":
                return {"status": "REFUSED:approval_revoked"}
            if sum(r["amount"] for r in refunds) != tool_context.state["refunded_at_decision"]:
                return {"status": "REFUSED:stale_premise"}
            # <<< user:recheck
        if arm == "adk_app_state":
            # >>> user:cap_app_state
            spent = tool_context.state.get("app:case_refunded_cents", 0)
            if spent + amount > CAP:
                return {"status": "REFUSED:over_cap", "spent_cents": spent}
            # <<< user:cap_app_state
        if arm == "adk_flock":
            # >>> user:cap_flock
            lock = open(os.path.join(cell_dir, "cap.lock"), "a")
            fcntl.flock(lock, fcntl.LOCK_EX)            # the kernel releases it the moment this process dies
            refunds = stripe_refunds()
            mine = [r["id"] for r in refunds if r["metadata"].get("adk_case") == tag]
            if mine or sum(r["amount"] for r in refunds) + amount > CAP:
                lock.close()
                return {"status": "FOUND_BY_LOOKUP", "refund_id": mine[0]} if mine else {"status": "REFUSED:over_cap"}
            # <<< user:cap_flock
        log(event="send", amount=amount, key=key)
        config.crash_once("before_send")
        # >>> user:tool
        r = client.request("POST", "/refunds", {"payment_intent": pi, "amount": amount, "metadata": {"adk_case": tag}},
                           idempotency_key=key)
        # <<< user:tool
        config.crash_once("after_commit")               # Stripe's answer is in memory, not in ADK's session
        if arm == "adk_app_state":
            # >>> user:cap_app_state
            tool_context.state["app:case_refunded_cents"] = spent + amount
            # <<< user:cap_app_state
        if lock:
            lock.close()
        # >>> user:tool
        return {"status": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund_id": r["id"]}
        # <<< user:tool

    # >>> user:wiring
    agent = LlmAgent(name="support", model=LiteLlm(model=MODEL), instruction=INSTRUCTION,
                     tools=[get_payment, FunctionTool(issue_refund, require_confirmation=True)])
    app = App(name=APP, root_agent=agent, resumability_config=ResumabilityConfig(is_resumable=True))
    sessions = SqliteSessionService(os.path.join(cell_dir, "sessions.db"))
    runner = Runner(app=app, session_service=sessions)
    # <<< user:wiring

    def confirmation(ids, confirmed):
        # >>> user:approver
        return types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
            id=ids["confirmation_call"], name=CONFIRM,
            response={"confirmed": confirmed, "payload": {"approver": "finance-lead"}}))])
        # <<< user:approver

    async def drive():
        if phase == "new":
            ids = {"session": (await sessions.create_session(app_name=APP, user_id=bot)).id}
            kw = {"new_message": types.Content(role="user", parts=[types.Part(text=cell.get("text") or TICKETS[bot])])}
        else:
            ids = json.load(open(ids_path))
            # >>> user:wiring
            kw = {"invocation_id": ids["invocation"]}        # a restart resumes the invocation
            # <<< user:wiring
            if phase in ("confirm", "reject"):
                kw["new_message"] = confirmation(ids, phase == "confirm")
        barrier = os.environ.get("ADK_BARRIER")
        if barrier and phase == "confirm":              # both approvals released at one instant
            open(os.path.join(barrier, f"ready-{bot}"), "w").close()
            while not os.path.exists(os.path.join(barrier, "go")):
                time.sleep(0.005)
        log(event="run", kw=sorted(kw))
        await consume(ids, kw)
        if phase == "new" and "confirmation_call" not in ids:     # the model asked in text: one plain follow-up
            ids["nudged"] = True
            log(event="nudge")
            await consume(ids, {"new_message": types.Content(role="user", parts=[types.Part(
                text="Yes. Call issue_refund now; that is how the confirmation is requested.")])})
        log(event="run_end")

    async def consume(ids, kw):
        async for ev in runner.run_async(user_id=bot, session_id=ids["session"], **kw):
            ids.setdefault("invocation", ev.invocation_id)
            for part in ev.content.parts if ev.content else []:
                if part.function_call:
                    if part.function_call.name == CONFIRM and phase == "new" and "confirmation_call" not in ids:
                        ids["confirmation_call"], ids["invocation"] = part.function_call.id, ev.invocation_id
                    log(event="adk", kind="call", name=part.function_call.name, id=part.function_call.id,
                        payload=part.function_call.args)
                elif part.function_response:
                    log(event="adk", kind="response", name=part.function_response.name, id=part.function_response.id,
                        payload=part.function_response.response)
                elif part.text:
                    log(event="adk", kind="text", payload=part.text)
            if phase == "new":
                json.dump(ids, open(ids_path, "w"))

    asyncio.run(drive())


# ---------------------------------------------------------------- the harness

def proc_name():
    return os.path.basename(sys.executable)


def start(cell_dir, phase, bot, env):
    out = open(os.path.join(cell_dir, f"agent-{bot}-{phase}.log"), "ab")
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "agent", cell_dir, phase, bot], env=env,
                         stdout=out, stderr=out)
    p.info = {"phase": phase, "bot": bot, "pid": p.pid, "process": proc_name()}
    return p


def finish(p, timeout):
    try:
        p.info["exit"] = p.wait(timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        p.info["exit"] = "timeout"
    return p.info


def new_case(client, label):
    customer = client.request("POST", "/customers", {"name": "Customer, order #881", "description": label})
    payment = client.request("POST", "/payment_intents", {
        "amount": PAID, "currency": "usd", "customer": customer["id"], "payment_method": "pm_card_visa",
        "payment_method_types": ["card"], "confirm": "true"})
    return customer["id"], payment["id"]


def events_of(cell_dir, bot):
    p = os.path.join(cell_dir, f"agent-{bot}.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def session_record(cell_dir, bot):
    """What ADK's own store holds for this bot: the confirmation(s), the tool calls and responses. Plain JSON rows."""
    db = sqlite3.connect(os.path.join(cell_dir, "sessions.db"))
    rows = [json.loads(r[0]) for r in db.execute("SELECT event_data FROM events WHERE user_id=? ORDER BY timestamp", (bot,))]
    state = db.execute("SELECT state FROM app_states WHERE app_name=?", (APP,)).fetchone()
    db.close()
    conf, calls, resps = [], [], []
    for e in rows:
        for part in (e.get("content") or {}).get("parts") or []:
            fr, fc = part.get("function_response") or part.get("functionResponse"), part.get("function_call") or part.get("functionCall")
            if fr and fr.get("name") == CONFIRM:
                conf.append({k: fr["response"].get(k) for k in ("confirmed", "payload")})
            elif fr and fr.get("name") == "issue_refund":
                resps.append(fr.get("response"))
            elif fc and fc.get("name") == "issue_refund":
                calls.append(fc.get("args"))
    return {"events": len(rows), "confirmations": conf, "issue_refund_calls": calls, "issue_refund_responses": resps,
            "app_state": json.loads(state[0]) if state else None,
            "integrity": "none: JSON rows in sessions.db, no hash chain, no signature"}


def answer_of(events):
    got = [e["payload"] for e in events if e.get("kind") == "response" and e.get("name") == "issue_refund"
           and e.get("phase") != "new"]
    if not got:
        return None, None
    a = got[-1]
    return a, a.get("status") or ("REJECTED_BY_APPROVER" if "rejected" in str(a.get("error", "")) else f"ERROR:{a.get('error')}")


def own_refunds(refunds, tag):
    return [r["id"] for r in refunds if r["metadata"].get("adk_case") == tag]


def run_cell(data, env, name, arm, rep):
    sc, client = SCENARIOS[name], config.stripe()
    cell_dir = os.path.join(data, f"{name}-{arm}-{rep}")
    os.makedirs(cell_dir)
    customer, pi = new_case(client, "Interlock experiments/competitor_adk_confirmation.py")
    case_id = os.urandom(6).hex()
    json.dump({"arm": arm, "scenario": name, "case_id": case_id, "payment_intent": pi, "text": CASE_TEXT},
              open(os.path.join(cell_dir, "cell.json"), "w"))
    child = {**env, "INTERLOCK_CRASH": sc["crash"], "INTERLOCK_CRASH_MARKER": os.path.join(cell_dir, "crash-marker")}
    print(f"[{name}:{arm}:{rep}] {pi}", flush=True)
    procs = [finish(start(cell_dir, "new", "agent", child), 240)]
    ids = json.load(open(os.path.join(cell_dir, "ids-agent.json"))) if os.path.exists(os.path.join(cell_dir, "ids-agent.json")) else {}
    if "confirmation_call" not in ids:
        return {"scenario": name, "arm": arm, "rep": rep, "payment_intent": pi, "invalid": "the model never asked for confirmation", "procs": procs}
    json.dump({"status": "approved", "by": "finance-lead", "at": time.time()}, open(os.path.join(cell_dir, "approval.json"), "w"))
    procs.append(finish(start(cell_dir, "confirm", "agent", child), 240))
    crashed_at = time.time()
    action = None
    if sc["action"] == "hand_refund":               # as from the dashboard: no idempotency key, no metadata
        action = {"hand_refund": client.request("POST", "/refunds", {"payment_intent": pi, "amount": APPROVED})["id"]}
    elif sc["action"] == "revoke":
        json.dump({"status": "revoked", "by": "finance-lead", "at": time.time()}, open(os.path.join(cell_dir, "approval.json"), "w"))
        action = {"revoked": True, "delivered_to_adk": arm == "adk_confirm_reject"}
    procs.append(finish(start(cell_dir, "reject" if arm == "adk_confirm_reject" else "resume", "agent", child), 240))
    done_at = time.time()
    time.sleep(2)
    refunds = [r for r in client.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"] if r["status"] != "failed"]
    evs = events_of(cell_dir, "agent")
    answer, status = answer_of(evs)
    own = own_refunds(refunds, f"{case_id}/agent")
    sent = status in SENT
    total = sum(r["amount"] for r in refunds)
    decided = next((e["payload"] for e in evs if e.get("kind") == "call" and e.get("name") == "issue_refund"), {})
    missed = [f"issue_refund answered in the confirm phase" for e in evs if e.get("phase") == "confirm"
              and e.get("kind") == "response" and e.get("name") == "issue_refund"]
    return {
        "scenario": name, "arm": arm, "rep": rep, "ran_at": datetime.datetime.fromtimestamp(crashed_at, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "payment_intent": pi, "customer": customer, "case_id": case_id, "procs": procs, "nudged": bool(ids.get("nudged")),
        "sigkill": procs[1]["exit"] == -signal.SIGKILL, "crash_window_missed": missed, "outage_action": action,
        "model_call": decided, "outcome": status, "answer": answer, "answer_sent": sent,
        "refund_ids": [r["id"] for r in refunds], "agent_refund_ids": own, "refunded_cents": total,
        "expected_cents": sc["want_cents"], "expected_refunds": sc["want_refunds"],
        "invariant_held": total == sc["want_cents"] and len(refunds) == sc["want_refunds"],
        "answer_matches_stripe": len(own) == 1 if sent else len(own) == 0 and bool(status),
        "seconds_crash_to_done": round(done_at - crashed_at, 1),
        "session_record": session_record(cell_dir, "agent"),
        "final_text": next((e["payload"] for e in reversed(evs) if e.get("kind") == "text"), None),
    }


def run_cap(data, env, crash, arm, rep):
    client, bots = config.stripe(), list(TICKETS)
    run_dir = os.path.join(data, f"cap-{crash}-{arm}-{rep}")
    os.makedirs(run_dir)
    customer, pi = new_case(client, "Interlock experiments/competitor_adk_confirmation.py shared cap")
    case_id = os.urandom(6).hex()
    json.dump({"arm": arm, "scenario": "shared_cap", "case_id": case_id, "payment_intent": pi},
              open(os.path.join(run_dir, "cell.json"), "w"))
    child = {**env, "INTERLOCK_CRASH": crash, "INTERLOCK_CRASH_MARKER": os.path.join(run_dir, "crash-marker"), "ADK_BARRIER": run_dir}
    print(f"[cap:{crash}:{arm}:{rep}] {pi}", flush=True)
    procs = [finish(p, 240) for p in [start(run_dir, "new", b, child) for b in bots]]
    idp = [os.path.join(run_dir, f"ids-{b}.json") for b in bots]
    if not all(os.path.exists(p) and "confirmation_call" in json.load(open(p)) for p in idp):
        return {"crash": crash, "arm": arm, "rep": rep, "payment_intent": pi, "invalid": "a bot never asked for confirmation", "procs": procs}
    live = {b: start(run_dir, "confirm", b, child) for b in bots}
    t0 = time.time()
    while not all(os.path.exists(os.path.join(run_dir, f"ready-{b}")) for b in bots) and time.time() - t0 < 120:
        time.sleep(0.01)
    open(os.path.join(run_dir, "go"), "w").close()
    go_at, crashed, crashed_at, restarted = time.time(), None, None, set()
    while live:
        for b, p in list(live.items()):
            if p.poll() is None:
                continue
            p.info["exit"] = p.returncode
            procs.append(p.info)
            del live[b]
            if p.returncode == -signal.SIGKILL and b not in restarted:
                crashed, crashed_at = b, time.time()
                restarted.add(b)
                live[b] = start(run_dir, "resume", b, child)
        if time.time() - t0 > 400:
            for b, p in live.items():
                p.kill(); p.wait(); p.info["exit"] = "timeout"; procs.append(p.info)
            live = {}
        time.sleep(0.02)
    done_at = time.time()
    time.sleep(2)
    refunds = [r for r in client.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"] if r["status"] != "failed"]
    total = sum(r["amount"] for r in refunds)
    per_bot = {}
    for b in bots:
        evs = events_of(run_dir, b)
        answer, status = answer_of(evs)
        own = own_refunds(refunds, f"{case_id}/{b}")
        sent = status in SENT
        per_bot[b] = {"outcome": status, "answer": answer, "own_refunds": own,
                      "nudged": bool(json.load(open(os.path.join(run_dir, f"ids-{b}.json"))).get("nudged")),
                      "answer_matches_stripe": len(own) == 1 if sent else len(own) == 0 and bool(status),
                      "model_call": next((e["payload"] for e in evs if e.get("kind") == "call" and e.get("name") == "issue_refund"), {}),
                      "session_record": session_record(run_dir, b)}
    return {
        "crash": crash, "arm": arm, "rep": rep, "payment_intent": pi, "customer": customer, "case_id": case_id,
        "ran_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "procs": procs,
        "crashed_bot": crashed, "sigkill": crashed is not None, "refund_ids": [r["id"] for r in refunds],
        "refunds": [{"id": r["id"], "amount": r["amount"], "bot": (r["metadata"].get("adk_case") or "").split("/")[-1]} for r in refunds],
        "refunded_cents": total, "invariant_held": total <= CAP, "per_bot": per_bot,
        "answers_match_stripe": all(v["answer_matches_stripe"] for v in per_bot.values()),
        "seconds_crash_to_settled": round(done_at - crashed_at, 1) if crashed_at else None,
        "seconds_approval_to_settled": round(done_at - go_at, 1),
    }


# ---------------------------------------------------------------- measurements that need no services

def user_lines():
    """Non-blank, non-comment lines inside each `# >>> user:<tag>` block of this file."""
    counts, tag = {}, None
    for line in open(os.path.abspath(__file__)):
        s = line.strip()
        m = re.match(r"# (>>>|<<<) user:(\w+)$", s)
        if m:
            tag = m.group(2) if m.group(1) == ">>>" else None
            continue
        if tag and s and not s.startswith("#"):
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def tamper_probe(cell_dir):
    """Edit ADK's stored record and see whether ADK notices; do the same to a stored Interlock receipt."""
    from google.adk.sessions.sqlite_session_service import SqliteSessionService
    from interlock.journal import entry_hash
    from interlock.receipts import sign, verify
    probe = os.path.join(tempfile.mkdtemp(prefix="adk-tamper-"), "sessions.db")
    shutil.copy(os.path.join(cell_dir, "sessions.db"), probe)
    ids = json.load(open(os.path.join(cell_dir, "ids-agent.json")))
    db = sqlite3.connect(probe)
    changed = 0
    for rowid, data in db.execute("SELECT rowid, event_data FROM events").fetchall():
        new = data.replace('"amount_cents":2000', '"amount_cents":1500').replace('"finance-lead"', '"someone-else"')
        if new != data:
            db.execute("UPDATE events SET event_data=? WHERE rowid=?", (new, rowid))
            changed += 1
    db.commit()
    db.close()
    s = asyncio.run(SqliteSessionService(probe).get_session(app_name=APP, user_id="agent", session_id=ids["session"]))
    text = json.dumps([e.model_dump(mode="json") for e in s.events])
    adk = {"rows_edited": changed, "loaded_without_error": s is not None, "edited_amount_visible": '"amount_cents": 1500' in text,
           "edited_approver_visible": "someone-else" in text,
           "adk_integrity_check": "none found in google/adk/sessions/sqlite_session_service.py"}
    shutil.rmtree(os.path.dirname(probe))

    src = json.load(open(os.path.join(ROOT, "results", "adk_live.json")))
    cell = next(c for c in src["cells"] if c["mode"] == "interlock" and c["scenario"] == "crash_after_commit")
    b = cell["receipt"]["bundle"]
    edit = json.loads(json.dumps(b))
    for e in edit["entries"]:
        if isinstance(e.get("effect"), dict):
            e["effect"]["amount"] = 1500
    rehashed = json.loads(json.dumps(edit))
    prev = None
    for e in rehashed["entries"]:
        e["prev"], e["hash"] = prev, None
        e["hash"] = prev = entry_hash({k: v for k, v in e.items() if k != "hash"})
    key = os.urandom(16).hex()                      # held by someone other than the journal writer
    signed = {**b, "signature": sign(b["effect_id"], b["entries"], key)}
    forged_signed = {**rehashed, "signature": signed["signature"]}
    interlock = {
        "source": "results/adk_live.json, crash_after_commit / interlock receipt",
        "unsigned_edit_without_rehash_valid": verify(edit)["valid"],
        "unsigned_edit_with_rehash_valid": verify(rehashed)["valid"],
        "unsigned_edit_with_rehash_tamper_evident_field": verify(rehashed)["tamper_evident"],
        "signed_original_valid_with_key": verify(signed, key)["valid"],
        "signed_then_rehashed_forgery_valid_with_key": verify(forged_signed, key)["valid"],
    }
    return {"adk": adk, "interlock": interlock}


# ---------------------------------------------------------------- report

def interlock_ref():
    src = json.load(open(os.path.join(ROOT, "results", "adk_live.json")))
    by = {(c["scenario"], c["mode"]): c for c in src["cells"]}
    return {s: {m: {k: by[(sc["interlock"], m)][k] for k in ("outcome", "invariant_held", "seconds_crash_to_done",
                                                              "refunded_cents", "answer_matches_stripe")}
                for m in ("interlock", "adk_checked") if (sc["interlock"], m) in by}
            for s, sc in SCENARIOS.items()}


def cell_text(c):
    if c.get("invalid"):
        return f"INVALID: {c['invalid']}"
    diff, n = c["refunded_cents"] - c["expected_cents"], len(c["refund_ids"])
    verdict = ("held" if c["invariant_held"] else f"VIOLATED, ${diff / 100:.0f} too much" if diff > 0
               else f"SHORT by ${-diff / 100:.0f}" if diff < 0 else "VIOLATED, wrong refund count")
    return (f"{c['outcome']}; ${c['refunded_cents'] / 100:.0f} in {n} refund{'s' if n != 1 else ''}; "
            f"{c['seconds_crash_to_done']}s crash to done; **{verdict}**; answer "
            f"{'matches' if c['answer_matches_stripe'] else 'CONTRADICTS'} Stripe"
            + ("" if c["sigkill"] else "; AGENT DID NOT CRASH, cell not valid")
            + (f"; CRASH WINDOW MISSED, cell not valid" if c["crash_window_missed"] else ""))


def valid(c):
    return not c.get("invalid") and c["sigkill"] and not c.get("crash_window_missed")


def markdown(out):
    ref, lines, cells, runs = out["interlock_reference"], out["user_lines"], out["cells"], out["cap_runs"]
    arms13 = ["adk_confirm", "adk_confirm_reject", "adk_confirm_checked"]

    def cell_group(s, a):
        cs = [c for c in cells if c["scenario"] == s and c["arm"] == a]
        if not cs:
            return "n/a"
        return "<br>".join(f"rep {c['rep']}: {cell_text(c)}" for c in cs)

    def ref_text(s, m):
        r = ref.get(s, {}).get(m)
        return (f"{r['outcome']}; ${r['refunded_cents'] / 100:.0f}; {r['seconds_crash_to_done']}s; "
                f"**{'held' if r['invariant_held'] else 'VIOLATED'}**") if r else "n/a"
    rows = "\n".join(f"| `{s}` | " + " | ".join(cell_group(s, a) for a in arms13) + f" | {ref_text(s, 'adk_checked')} | {ref_text(s, 'interlock')} |"
                     for s in SCENARIOS)

    def tally(a):
        cs = [c for c in cells if c["arm"] == a and valid(c)]
        return (f"- {ARMS[a][0]}: {sum(c['invariant_held'] for c in cs)}/{len(cs)} held, "
                f"{sum(c['answer_matches_stripe'] for c in cs)}/{len(cs)} answers matched Stripe, median "
                f"{statistics.median(c['seconds_crash_to_done'] for c in cs):.1f}s crash to done") if cs else f"- {a}: no valid cells"

    def cap_row(crash):
        out_ = []
        for a in CAP_ARMS:
            rs = [r for r in runs if r["crash"] == crash and r["arm"] == a and not r.get("invalid")]
            if not rs:
                out_.append("not run")
                continue
            dist = {}
            for r in rs:
                k = f"${r['refunded_cents'] / 100:.0f} in {len(r['refund_ids'])}"
                dist[k] = dist.get(k, 0) + 1
            field, label = (("seconds_approval_to_settled", "approval to settled") if crash == "none"
                            else ("seconds_crash_to_settled", "crash to settled"))
            secs = [r[field] for r in rs if r.get(field) is not None]
            out_.append(f"**held {sum(r['invariant_held'] for r in rs)}/{len(rs)}**; Stripe: "
                        + ", ".join(f"{v}x {k}" for k, v in dist.items())
                        + f"; crash in {sum(r['sigkill'] for r in rs)}/{len(rs)}; answers matched Stripe "
                        f"{sum(r['answers_match_stripe'] for r in rs)}/{len(rs)}; median "
                        + (f"{statistics.median(secs):.1f}s" if secs else "n/a") + f" {label}")
        return f"| `{crash}` | " + " | ".join(out_) + " |"

    def outcomes(crash, a):
        rs = [r for r in runs if r["crash"] == crash and r["arm"] == a and not r.get("invalid")]
        d = {}
        for r in rs:
            if r["crashed_bot"]:
                k = f"crashed {r['per_bot'][r['crashed_bot']]['outcome']} / other " + \
                    ", ".join(str(v["outcome"]) for b, v in r["per_bot"].items() if b != r["crashed_bot"])
            else:
                k = "no crash: " + " + ".join(sorted(str(v["outcome"]) for v in r["per_bot"].values()))
            d[k] = d.get(k, 0) + 1
        return "; ".join(f"{v}x {k}" for k, v in d.items())

    ledger = []
    for r in runs:
        if r.get("invalid") or r["arm"] != "adk_app_state":
            continue
        st = next((v["session_record"]["app_state"] for v in r["per_bot"].values()), None) or {}
        ledger.append((st.get("case_refunded_cents"), r["refunded_cents"]))
    ledger_wrong = sum(1 for l, t in ledger if l != t)
    loc = {a: sum(lines.get(t, 0) for t in tags) for a, (_, tags) in ARMS.items()}
    t = out["tamper"]
    invalid = [c for c in cells if not valid(c)] + [r for r in runs if r.get("invalid")]
    ids = "\n".join(f"- `{c['scenario']}` / {c['arm']} rep {c['rep']}: PaymentIntent `{c['payment_intent']}`, refunds "
                    + (", ".join(f"`{x}`" for x in c.get("refund_ids", [])) or "none")
                    + f", agent pids/exits {[(p['pid'], p['exit']) for p in c['procs']]}" for c in cells)
    capids = "\n".join(f"- `{r['crash']}` / {r['arm']} rep {r['rep']}: PaymentIntent `{r['payment_intent']}`, killed "
                       f"{r.get('crashed_bot')}, refunds " + (", ".join(f"`{x['id']}` ${x['amount'] / 100:.0f} {x['bot']}" for x in r.get("refunds", [])) or "none")
                       for r in runs)
    decisions = "\n".join(f"- `{c['scenario']}` / {c['arm']} rep {c['rep']}: issue_refund {c.get('model_call')}; final: "
                          f"\"{(c.get('final_text') or '').strip()[:140]}\"" for c in cells)
    return f"""# Competitor: Google ADK's approval gate and resume, no Interlock

Generated {out['generated']} by `experiments/competitor_adk_confirmation.py`""" + "".join(
        f"; cells added with --merge at {r['at']}: {', '.join(r['added'])}" for r in out.get("reruns", [])) + f""". google-adk {out['adk']}, model
`{out['model']}` through ADK's LiteLlm, Stripe test mode, real SIGKILL of separate agent OS processes.

ADK is run the way its source and docs recommend for a side effect that needs a person:
`FunctionTool(issue_refund, require_confirmation=True)`, `App(resumability_config=ResumabilityConfig(is_resumable=True))`,
`SqliteSessionService`, a new process resuming with `run_async(invocation_id=...)`, and Idempotency-Key = invocation id
+ "/" + function call id, because ResumabilityConfig's docstring says a resumed tool runs at-least-once and must be
idempotent. A script answers `adk_request_confirmation` with `{{"confirmed": true, "payload": {{"approver": "finance-lead"}}}}`,
standing in for a person. Ground truth is Stripe's refund list for each PaymentIntent, re-read after the last process
exits. Interlock columns are copied from `results/adk_live.json` (same harness shape: ADK agent, Stripe test mode,
SIGKILL inside the send, resume in a new process), not re-run here; there the approval was an AP2 mandate, not an
ADK confirmation.

## 1-3. One approved $20 refund, a crash inside the send

Each cell: a new $100 test payment. The agent calls `get_payment`, then `issue_refund`; ADK pauses the invocation for
confirmation (process 1 exits 0). The approval arrives and resumes it in process 2, which is SIGKILLed inside the tool
body. The harness acts during the outage, then process 3 resumes the invocation.

| scenario | {ARMS['adk_confirm'][0]} | {ARMS['adk_confirm_reject'][0]} | {ARMS['adk_confirm_checked'][0]} | ADK call-id key + hand re-check callback (`results/adk_live.md`, adk_checked) | Interlock Guard (`results/adk_live.md`) |
|---|---|---|---|---|---|
{rows}

{chr(10).join(tally(a) for a in arms13)}

Scenarios:

""" + "\n".join(f"- `{s}`: {sc['text']}. Interlock reference row: `{sc['interlock']}`" for s, sc in SCENARIOS.items()) + f"""

## 4. Two approvals racing one $30 cap, with a crash

Each run: a new $100 test payment and case #4471 capped at $30 of refunds. A support-bot and a billing-bot, each an
ADK agent in its own session of one App and one `sessions.db`, each decide a $20 refund from their own ticket and
pause for confirmation. Both approvals are then released from one barrier. The first bot to reach the crash point is
SIGKILLed and resumed at once; in the `none` row nobody crashes, which isolates the race between the two approved
calls. **Invariant: total refunded <= $30.** {out['cap_reps']} runs per cell.

| crash point | {ARMS['adk_app_state'][0]} | {ARMS['adk_flock'][0]} |
|---|---|---|
{cap_row('after_commit')}
{cap_row('before_send')}
{cap_row('none')}

What each bot reported (crashed bot / other bot):

""" + "\n".join(f"- `{cr}` / {a}: {outcomes(cr, a)}" for cr in CAP_CRASHES for a in CAP_ARMS) + f"""

ADK's `app:case_refunded_cents` ledger disagreed with Stripe's total in {ledger_wrong}/{len(ledger)} adk_app_state runs.

Interlock reference (`results/scenarios/shared_cap.md`, 20 runs per crash point, no approval step, plain processes
rather than ADK): unmodified Gate held 5/20 `after_commit` and 20/20 `before_send`; with the scenario's CapJournal
subclass (about 60 lines outside the core) 20/20 and 20/20, median 40.1s and 41.7s crash to settled; hand_lock (flock)
20/20 and 20/20, median 0.5s and 1.4s.

## Reading it against Interlock

Written after this run from the tables above and `results/adk_live.md` / `results/scenarios/shared_cap.md`.

What ADK does better than Interlock, measured:

- **Settle time.** Every ADK arm here resumed as soon as the new process started: crash to done 5.0 to 10.2s for
  single-agent cells, against 45.1 to 46.3s for Interlock's Guard in the matching `results/adk_live.md` rows. ADK has
  no claim to wait out; the call-id idempotency key makes the replay safe after a crash in the send.
- **Revocation, when the approver's answer reaches the agent.** A ToolConfirmation(confirmed=False) sent for the same
  confirmation call during the outage stopped the replayed refund in 2/2 cells, with zero user code beyond the
  approver reply, and ADK recorded the rejection in the session. Interlock needs a lease store for the same result.
- **A built-in pause for a person.** The confirmation is bound to the exact call arguments (ADK source
  `flows/llm_flows/request_confirmation.py` refuses a confirmation whose arguments differ from the call in history)
  and survives process death in the session store; Interlock's core has no human-in-the-loop pause of its own.

What Interlock does better, measured:

- **The world changing after approval.** ADK's gate as configured (no user re-check) re-applied the approved refund
  after a hand refund ($40, 2/2) and after a revocation recorded outside ADK ($20 refunded, 2/2). Interlock refused
  both in `results/adk_live.md`. So did a hand-written re-check (9 lines here, 6/6), so this is Interlock against ADK
  alone, not against a careful ADK user.
- **A shared cap.** ADK's shared `app:` state is read at process start and merged last-writer-wins with no
  compare-and-set (source `sessions/sqlite_session_service.py`, `_upsert_app_state`): two approved $20 refunds
  under a $30 cap landed together in 6/6 no-crash runs and 6/6 `after_commit` runs, and the ledger disagreed with
  Stripe in 12/18 runs. `before_send` held 6/6 only because the crash removed one sender until the other had written.
  Interlock's unmodified core held 25/40 on this scenario and 40/40 only with the CapJournal subclass; the flock arm
  here held 18/18, as hand_lock did. Neither framework ships a cap; Interlock's needs code outside the core.
- **Record integrity, partly.** An edit to ADK's `sessions.db` loads silently. An unsigned Interlock receipt catches
  a naive edit but not a rehashed one; only a signed receipt caught the forgery, and no live run in this repo signs.

Ties or gaps for both: neither watches after commit (a chargeback after a successful refund), from source, not run
here.

## Lines of user code

Counted from the `# >>> user:` blocks in the script (non-blank, non-comment lines): {json.dumps(lines)}.

| arm | lines |
|---|---|
""" + "\n".join(f"| {a} | {loc[a]} |" for a in ARMS) + f"""

The `approver` block is the approver side (building the ToolConfirmation reply); ADK's dev UI provides the same
reply without code. For reference, Interlock's ADK wiring in `experiments/adk_live.py` is 7 lines (the `Guard`
construction, `guard.gate(...)`, the callback assignment and `guard.recover()` on restart) on top of the same tool and
agent wiring, and a cross-bot cap needed the CapJournal subclass.

## Record: what proves what happened, and tamper probe

ADK's record is the session in `sessions.db`: the model's `issue_refund` call and its arguments, the user event with
the ToolConfirmation (`confirmed`, and a free-form `payload` the approver side fills in), and the tool's responses.
Per cell summaries are in the JSON (`session_record`). Measured here:

- ADK: {t['adk']['rows_edited']} rows of a copied `sessions.db` edited (amount 2000 to 1500, approver renamed); the
  session loaded without error: {t['adk']['loaded_without_error']}; edited amount visible: {t['adk']['edited_amount_visible']};
  edited approver visible: {t['adk']['edited_approver_visible']}. Integrity check: {t['adk']['adk_integrity_check']}.
- Interlock, on a stored receipt ({t['interlock']['source']}): the same amount edit without recomputing hashes: valid =
  {t['interlock']['unsigned_edit_without_rehash_valid']}; with the hash chain recomputed: valid =
  {t['interlock']['unsigned_edit_with_rehash_valid']} (and `tamper_evident` still reads
  {t['interlock']['unsigned_edit_with_rehash_tamper_evident_field']}); signed with a key the forger lacks, the
  rehashed forgery: valid = {t['interlock']['signed_then_rehashed_forgery_valid_with_key']} (original: {t['interlock']['signed_original_valid_with_key']}).
  Live Interlock runs in this repo are unsigned.

## Not valid evidence

""" + ("\n".join(f"- {c.get('scenario', 'cap')} / {c['arm']} rep {c['rep']}: {c.get('invalid') or 'crash did not land in its window'}" for c in invalid) or "- none") + f"""

## Model decisions

{decisions}

## Ids, for checking in the Stripe test dashboard

{ids}
{capids}

Process records hold pid, process name and exit code only.

## Re-run

    ANTHROPIC_API_KEY=... uv run --no-project --python 3.13 --with google-adk==2.9.0 --with litellm \\
        python experiments/competitor_adk_confirmation.py --reps {out['reps']} --cap-reps {out['cap_reps']}
"""


def main():
    args = sys.argv[1:]
    reps = int(args[args.index("--reps") + 1]) if "--reps" in args else 2
    cap_reps = int(args[args.index("--cap-reps") + 1]) if "--cap-reps" in args else 6
    only = {a for a in args if ":" in a}
    import google.adk
    if not os.environ.get("ANTHROPIC_API_KEY"):
        for line in open("/Users/kiromoussa/CADAI/.env"):
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip("'\"")
    env = {**os.environ, "STRIPE_SECRET_KEY": config.stripe_key() or ""}
    data = tempfile.mkdtemp(prefix="adk-confirm-", dir=os.path.dirname(ROOT))     # the session scratchpad
    print(f"data {data}", flush=True)
    todo = [(s, a, r) for s, sc in SCENARIOS.items() for a in sc["arms"] for r in range(reps) if not only or f"{s}:{a}" in only]
    captodo = [(cr, a, r) for cr in CAP_CRASHES for a in CAP_ARMS for r in range(cap_reps) if not only or f"cap_{cr}:{a}" in only]
    with ThreadPoolExecutor(2) as ex:
        cells = list(ex.map(lambda t: run_cell(data, env, *t), todo))
    with ThreadPoolExecutor(4) as ex:
        runs = list(ex.map(lambda t: run_cap(data, env, *t), captodo))
    for c in cells:
        print(f"{c['scenario']:32} {c['arm']:22} {cell_text(c)}")
    for r in runs:
        print(f"cap {r['crash']:13} {r['arm']:14} held={r.get('invariant_held')} ${r.get('refunded_cents', 0) / 100:.0f} "
              f"{r.get('invalid') or [v['outcome'] for v in r['per_bot'].values()]} {r.get('seconds_crash_to_settled')}s")
    probe_cell = next((os.path.join(data, f"{c['scenario']}-{c['arm']}-{c['rep']}") for c in cells
                       if c["arm"] == "adk_confirm" and not c.get("invalid")), None)
    tamper = tamper_probe(probe_cell) if probe_cell else None
    print(json.dumps(tamper, indent=1))
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if "--merge" in args:           # add the named cells to the existing results instead of replacing them
        out = json.load(open(os.path.join(OUT, "adk_confirmation.json")))
        out["cells"] += cells
        out["cap_runs"] += runs
        out["user_lines"] = user_lines()
        out.setdefault("reruns", []).append({"at": now, "added": sorted(only)})
    elif only:
        return
    else:
        out = {"generated": now, "model": MODEL, "adk": google.adk.__version__, "reps": reps, "cap_reps": cap_reps,
               "arms": {a: d for a, (d, _) in ARMS.items()}, "user_lines": user_lines(),
               "interlock_reference": interlock_ref(), "tamper": tamper, "cells": cells, "cap_runs": runs}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "adk_confirmation.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    with open(os.path.join(OUT, "adk_confirmation.md"), "w") as f:
        f.write(markdown(out))
    shutil.rmtree(data, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["agent"]:
        agent_main(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main()
