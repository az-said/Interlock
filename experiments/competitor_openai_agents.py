"""
Competitor run: the OpenAI Agents SDK (MIT) with needs_approval on the refund tool, its RunState serialize/resume
and a SQLiteSession, used as its human-in-the-loop docs describe, against Stripe test mode with real SIGKILLs.

    uv run --no-project --python 3.12 --with openai-agents==0.22.2 --with litellm \
        python experiments/competitor_openai_agents.py [--reps N] [--race-reps N] [scenario:mode ...]

Keys at runtime only: ANTHROPIC_API_KEY (else read from /Users/kiromoussa/CADAI/.env), STRIPE_SECRET_KEY (else
test_mode_api_key from `stripe config --list`, test keys only). The model is Claude Haiku 4.5 through the SDK's
LitellmModel; OpenAI tracing is disabled (no OpenAI key works here).

The documented flow (openai.github.io/openai-agents-python/human_in_the_loop): Runner.run pauses at a tool with
needs_approval; the app stores result.to_state().to_string(); later it reloads RunState.from_string(agent, s),
calls state.approve(item) or state.reject(item), and Runner.run(agent, state, session=session) continues. Every
phase below is its own OS process: decide (model runs until the approval pause), run (the approval is applied from
the approvals table and the tool executes; SIGKILL inside the send), resume (a new process repeats the documented
reload, approve, run). Ground truth is Stripe's refund list. Writes results/competitors/openai_agents.{json,md}.
"""
import ast, asyncio, datetime, fcntl, json, os, signal, sqlite3, statistics, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend import config
from interlock.gate import Gate
from interlock.journal import effect_id_for, entry_hash, open_journal
from interlock.receipts import bundle, verify
from interlock.targets.stripe_api import StripeRefunds
from scenarios.shared_cap.cap import CapGate, CapRefunds

MODEL = "anthropic/claude-haiku-4-5-20251001"
PAID, APPROVED, CAP = 10000, 2000, 3000
BOTS = ("support-bot", "billing-bot")
GO_DELAY = 15           # seconds from spawning both run processes to their shared start barrier (imports take ~5s)
SENT = {"REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP", "COMMITTED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY",
        "REAPPLIED_AFTER_QUERY", "DUPLICATE_IGNORED"}
CASE_TEXT = ("Order #881, paid $100.00 by card. The blender arrived with its glass jar cracked. Support case #4471: "
             "Finance approved ONE partial refund of $20.00 for the jar; the customer keeps the blender. "
             "Issue the approved refund.")
TICKETS = {"support-bot": "Support ticket on order #881: the glass jar arrived cracked. Refund $20.00 for the jar.",
           "billing-bot": "Billing ticket on order #881: delivery was three days late. Refund $20.00 as a delay credit."}
RACE_NOTE = " Case #4471 approves at most $30.00 of refunds in total on this order, across all teams."
INSTRUCTIONS = ("You are a payments support agent. Call get_payment, then call issue_refund exactly once with the refund "
                "the ticket asks for, in integer cents, and a short reason. Do not call issue_refund again. "
                "Finish with one sentence saying what happened.")

COLUMNS = {
    "sdk_nokey": "SDK needs_approval + RunState resume, tool sends with no idempotency key",
    "sdk": "SDK needs_approval + RunState resume, Idempotency-Key = case / tool_call_id (docs: make tools idempotent)",
    "sdk_sticky": "as sdk, but the approved RunState is saved and resumed as is (sticky approval, no re-decision)",
    "sdk_checked": "as sdk, plus a hand-written re-check at the top of the tool (lookup, approval, refunds unchanged)",
    "sdk_lock": "as sdk, plus the re-check inside an flock on the shared run dir (strongest hand-written arm)",
    "sdk_interlock": "as sdk, with the tool body sent through Interlock's Gate (CapGate for the race)",
}
SCENARIOS = {
    "crash_after_commit": dict(crash="after_commit", action=None, want_cents=APPROVED, want_refunds=1,
                               modes=("sdk_nokey", "sdk", "sdk_checked", "sdk_interlock"),
                               text="SIGKILL after Stripe's response to the refund POST arrived, before the SDK recorded the "
                                    "tool output; restarted and resumed. Want $20 in 1 refund"),
    "hand_refund_during_outage": dict(crash="before_send", action="hand_refund", want_cents=APPROVED, want_refunds=1,
                                      modes=("sdk", "sdk_checked", "sdk_interlock"),
                                      text="SIGKILL right before the refund POST; support refunds the same $20 by hand "
                                           "(no key, no metadata); restarted and resumed. Want only the hand refund"),
    "approval_revoked_during_outage": dict(crash="before_send", action="revoke", want_cents=0, want_refunds=0,
                                           modes=("sdk", "sdk_sticky", "sdk_checked", "sdk_interlock"),
                                           text="SIGKILL right before the refund POST; Finance revokes the approval in "
                                                "the approvals table; restarted and resumed. Want nothing"),
}
RACE_MODES = ("sdk", "sdk_lock", "sdk_interlock")
TAGS = {"sdk_nokey": ["common", "send"], "sdk": ["common", "send"], "sdk_sticky": ["common", "send", "sticky"],
        "sdk_checked": ["common", "send", "checked"], "sdk_lock": ["common", "send", "lock"],
        "sdk_interlock": ["common", "interlock"]}


# ---------------------------------------------------------------- shared by the agent process and the harness

class Approvals:
    """Finance's approval of a case, as the app stores it: a row with a cap and a revoked time. Also Interlock's lease store."""
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path, timeout=30) as db:
            db.execute("CREATE TABLE IF NOT EXISTS approvals (case_id TEXT PRIMARY KEY, max_cents INT, approved_by TEXT, "
                       "approved_at REAL, revoked_at REAL)")

    def grant(self, case, max_cents, by):
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, NULL)", (case, max_cents, by, time.time()))

    def revoke(self, case):
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("UPDATE approvals SET revoked_at = ? WHERE case_id = ?", (time.time(), case))

    def describe(self, case):
        with sqlite3.connect(self.path, timeout=30) as db:
            row = db.execute("SELECT max_cents, approved_by, approved_at, revoked_at FROM approvals WHERE case_id = ?", (case,)).fetchone()
        return {"case": case, "max_cents": row[0], "approved_by": row[1], "approved_at": row[2], "revoked": row[3]} if row else None

    def is_live(self, case):
        d = self.describe(case)
        return bool(d) and d["revoked"] is None

    def allows(self, case, effect):
        d = self.describe(case)
        return bool(d) and d["revoked"] is None and type(effect.get("amount")) is int and 0 < effect["amount"] <= d["max_cents"]


class KillableRefunds(StripeRefunds):
    """Real Stripe refunds with the crash points on either side of the POST (harness instrumentation)."""
    def apply(self, eid, effect, crash_after_effect=False):
        config.crash_once("before_send")
        out = super().apply(eid, effect)
        config.crash_once("after_commit")
        return out


def request_id(cell):
    return f"refund:{cell['case']}/{cell['bot']}"


def build_gate(cell, client, approvals):
    if cell["race"]:
        return CapGate(CapRefunds(client, cell["pi"], hook=config.crash_once), cell["journal"], approvals, CAP,
                       claim_ttl=config.CLAIM_TTL)
    return Gate(KillableRefunds(client, cell["pi"]), cell["journal"], approvals, claim_ttl=config.CLAIM_TTL)


def make_agent(cell, client, approvals, log=lambda **kw: None):
    from agents import Agent, function_tool
    from agents.extensions.models.litellm_model import LitellmModel
    from agents.tool_context import ToolContext
    mode = cell["mode"]

    # user:common
    @function_tool
    def get_payment(ctx: ToolContext) -> str:
        """Live facts for this case's Stripe payment, in cents."""
        refunds = StripeRefunds(client, ctx.context["pi"]).refunds()
        ctx.context["premises"] = {"payment_intent": ctx.context["pi"], "refunded_by_others": sum(r["amount"] for r in refunds)}
        return json.dumps({"paid_cents": PAID, "refunded_cents": ctx.context["premises"]["refunded_by_others"]})

    @function_tool(needs_approval=True)
    def issue_refund(ctx: ToolContext, amount_cents: int, reason: str) -> str:
        """Send the refund. A person approves every call before it runs."""
        c = ctx.context
        # end:common
        log(event="tool_start", call_id=ctx.tool_call_id, amount_cents=amount_cents)

        # user:send
        def send():
            key = None if mode == "sdk_nokey" else f"{c['case']}/{ctx.tool_call_id}"
            config.crash_once("before_send")  # harness
            r = client.request("POST", "/refunds", {"payment_intent": c["pi"], "amount": amount_cents,
                                                    "metadata": {"sdk_case": c["case"], "bot": c["bot"]}}, idempotency_key=key)
            config.crash_once("after_commit")  # harness
            return {"status": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund_id": r["id"]}
        # end:send

        # user:checked
        def checked():
            refunds = client.request("GET", "/refunds", {"payment_intent": c["pi"], "limit": 100})["data"]
            mine = [r["id"] for r in refunds if r["metadata"].get("sdk_case") == c["case"] and r["metadata"].get("bot") == c["bot"]]
            if mine:
                return {"status": "FOUND_BY_LOOKUP", "refund_id": mine[0]}
            checks = {"approval": approvals.describe(c["case"]), "refunded_at_decision": c["premises"]["refunded_by_others"],
                      "refunded_now": sum(r["amount"] for r in refunds if r["status"] != "failed")}
            if not approvals.allows(c["case"], {"amount": amount_cents}):
                return {"status": "REFUSED:approval", "checks": checks}
            if checks["refunded_now"] != checks["refunded_at_decision"]:
                return {"status": "REFUSED:stale_premise", "checks": checks}
            return {**send(), "checks": checks}
        # end:checked

        # user:lock
        def locked():
            with open(c["lock"], "a") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)          # the kernel drops it the moment a holder dies
                refunds = client.request("GET", "/refunds", {"payment_intent": c["pi"], "limit": 100})["data"]
                mine = [r["id"] for r in refunds if r["metadata"].get("sdk_case") == c["case"] and r["metadata"].get("bot") == c["bot"]]
                if mine:
                    return {"status": "FOUND_BY_LOOKUP", "refund_id": mine[0]}
                total = sum(r["amount"] for r in refunds if r["status"] != "failed")
                if total + amount_cents > CAP:
                    return {"status": "REFUSED:over_cap", "checks": {"refunded_now": total, "cap": CAP}}
                return {**send(), "checks": {"refunded_now": total, "cap": CAP}}
        # end:lock

        # user:interlock
        def gated():
            gate = build_gate(c, client, approvals)
            premises = {**c["premises"], "amount": amount_cents, "cap": CAP} if c["race"] else c["premises"]
            p = {"agent": c["bot"], "lease": c["case"], "request_id": request_id(c), "premises": premises,
                 "effect": {"amount": amount_cents, "case": c["case"]}}
            eid, deadline = effect_id_for(p), time.time() + 2 * config.CLAIM_TTL + 10
            status = "IN_FLIGHT"
            while time.time() < deadline:               # a dead sender's claim must expire before recovery may act
                status = gate.recover(only=[eid]).get(eid) or gate.submit(p)
                if status != "IN_FLIGHT" and not status.startswith("UNRESOLVED"):
                    break
                time.sleep(1)
            v = verify(bundle(gate.journal, eid))
            return {"status": status, "evidence": v["evidence"], "happened": v["happened"], "refused": v["refused"]}
        # end:interlock

        try:
            out = {"sdk_checked": checked, "sdk_lock": locked, "sdk_interlock": gated}.get(mode, send)()
        except Exception as e:      # the SDK hands tool errors to the model; keep a copy for the harness
            log(event="tool_error", call_id=ctx.tool_call_id, error=f"{type(e).__name__}: {e}")
            raise
        log(event="tool_return", call_id=ctx.tool_call_id, output=out)
        # user:common
        return json.dumps(out)

    return Agent(name="support", model=LitellmModel(MODEL), instructions=INSTRUCTIONS, tools=[get_payment, issue_refund])
    # end:common


# ---------------------------------------------------------------- the agent process

def agent_main(bot_dir, phase):
    from agents import Runner, RunState, SQLiteSession, set_tracing_disabled
    set_tracing_disabled(True)
    cell = json.load(open(os.path.join(bot_dir, "cell.json")))
    client, approvals = config.stripe(), Approvals(cell["approvals_db"])

    def log(**kw):
        with open(os.path.join(bot_dir, "agent.jsonl"), "a") as f:
            f.write(json.dumps({"ts": time.time(), "phase": phase, "pid": os.getpid(), **kw}, default=str) + "\n")

    agent = make_agent(cell, client, approvals, log)
    at = lambda name: os.path.join(bot_dir, name)

    async def drive():
        # user:common
        session = SQLiteSession(cell["session_id"], at("session.db"))
        if phase == "decide":
            result = await Runner.run(agent, cell["text"], session=session, context=dict(cell))
            with open(at("state.json"), "w") as f:
                f.write(result.to_state().to_string())
            # end:common
            log(event="paused", interruptions=[{"name": i.name, "arguments": i.arguments, "call_id": i.call_id}
                                               for i in result.interruptions], final_output=result.final_output)
            return
        if cell["mode"] == "sdk_interlock" and phase == "resume":
            # user:interlock
            gate, eid = build_gate(cell, client, approvals), effect_id_for({"request_id": request_id(cell)})
            deadline = time.time() + 2 * config.CLAIM_TTL + 10
            while eid in gate.journal.in_flight() and time.time() < deadline:    # recover on start, waiting out the claim
                out = gate.recover(only=[eid])
                # end:interlock
                if out:
                    log(event="recover_on_start", result=out)
                # user:interlock
                time.sleep(0 if out else 1)
            # end:interlock
        # user:sticky
        if cell["mode"] == "sdk_sticky" and os.path.exists(at("approved.json")):
            state = await RunState.from_string(agent, open(at("approved.json")).read())
            # end:sticky
            log(event="resumed_sticky_approval")
        else:
            # user:common
            state = await RunState.from_string(agent, open(at("state.json")).read())
            for item in state.get_interruptions():      # the person's decision, as recorded in the approvals table
                args = json.loads(item.arguments or "{}")
                if approvals.allows(cell["case"], {"amount": args.get("amount_cents")}):
                    state.approve(item)
                else:
                    state.reject(item, rejection_message="Not approved: the approval is revoked or does not cover this amount.")
                # end:common
                log(event="decision", call_id=item.call_id, approved=approvals.allows(cell["case"], {"amount": args.get("amount_cents")}),
                    approval=approvals.describe(cell["case"]))
            # user:sticky
            if cell["mode"] == "sdk_sticky":
                with open(at("approved.json"), "w") as f:
                    f.write(state.to_string())
            # end:sticky
        go = float(os.environ.get("RUN_GO_AT") or 0)
        if go:
            log(event="barrier", wait=round(go - time.time(), 2))
            time.sleep(max(0.0, go - time.time()))
        # user:common
        result = await Runner.run(agent, state, session=session)
        with open(at("final_state.json"), "w") as f:
            f.write(result.to_state().to_string())
        # end:common
        log(event="finished", final_output=result.final_output,
            pending=[{"name": i.name, "call_id": i.call_id, "arguments": i.arguments} for i in result.interruptions])

    asyncio.run(drive())


# ---------------------------------------------------------------- the harness

def spawn(bot_dir, phase, env):
    out = open(os.path.join(bot_dir, f"agent-{phase}.log"), "ab")
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "agent", bot_dir, phase], env=env, stdout=out, stderr=out)
    p.proc = {"pid": p.pid, "name": os.path.basename(sys.executable)}      # pid and process name only
    return p


def wait(p, timeout):
    try:
        return p.wait(timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        return "timeout"


def events(bot_dir):
    path = os.path.join(bot_dir, "agent.jsonl")
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def answer_of(evs):
    """The last tool return the agent got after the crash, or the approver's rejection when the tool never ran."""
    after = [e for e in evs if e["phase"] == "resume"]
    ret = [e["output"] for e in after if e["event"] == "tool_return"]
    if ret:
        return ret[-1]
    if any(e["event"] == "decision" and not e["approved"] for e in after):
        return {"status": "REJECTED_BY_APPROVER_ON_RESUME"}
    return None


def new_cell_files(bot_dir, **cell):
    os.makedirs(bot_dir, exist_ok=True)
    cell = {"session_id": f"{cell['case']}:{cell['bot']}", **cell}
    json.dump(cell, open(os.path.join(bot_dir, "cell.json"), "w"))
    return cell


def sdk_record(bot_dir, cell, own_ids, stripe_ids):
    """What the SDK's own artifacts (RunState JSON and the SQLiteSession) say, and whether an edited copy is caught."""
    from agents import RunState, SQLiteSession
    evs = events(bot_dir)
    paused = next((e for e in evs if e["event"] == "paused"), {})
    call_id = (paused.get("interruptions") or [{}])[0].get("call_id")
    fpath = os.path.join(bot_dir, "final_state.json")
    final = open(fpath).read() if os.path.exists(fpath) else None
    ctx = json.loads(final or open(os.path.join(bot_dir, "state.json")).read())["context"]
    approval = ctx.get("approvals", {}).get("issue_refund", {})
    items = asyncio.run(SQLiteSession(cell["session_id"], os.path.join(bot_dir, "session.db")).get_items())
    outs = [i for i in items if i.get("type") == "function_call_output" and i.get("call_id") == call_id]
    last = None
    if outs:
        raw = outs[-1].get("output")
        try:
            last = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            last = {"status": "REJECTED" if str(raw).startswith("Not approved") else "TEXT", "text": str(raw)[:160]}
    attempts = sum(e["event"] == "tool_start" for e in evs)
    executed_outs = [i for i in outs if not str(i.get("output", "")).startswith("Not approved")]   # a rejection is not a run
    rec = {"call_id": call_id,
           "approval_in_record": "approved" if call_id in (approval.get("approved") or []) else
                                 "rejected" if call_id in (approval.get("rejected") or []) else None,
           "approval_fields": sorted(approval),
           "approver_or_time_in_record": bool(set(approval) - {"approved", "rejected", "rejection_messages"}),
           "tool_attempts_actual": attempts, "tool_outputs_in_session": len(outs),
           "tool_run_outputs_in_session": len(executed_outs),
           "killed_attempt_visible": len(executed_outs) >= attempts and attempts > 0 and bool(final),
           "checks_in_record": bool(isinstance(last, dict) and last.get("checks")),
           "outcome_in_record": last.get("status") if isinstance(last, dict) else None}
    ev = last.get("evidence") if isinstance(last, dict) else None
    rid = isinstance(last, dict) and (last.get("refund_id") or (ev.get("refund") if isinstance(ev, dict) else ev))
    status = rec["outcome_in_record"] or ""
    rec["outcome_matches_stripe"] = (rid in own_ids and len(own_ids) == 1) if status in SENT else (not own_ids and bool(status))
    rec["tamper"] = None
    if final:
        async def load(text):
            try:
                await RunState.from_string(make_agent(cell, None, None), text)
                return True
            except Exception as e:      # noqa: BLE001
                return f"{type(e).__name__}: {str(e)[:120]}"
        edited = json.loads(final)
        a = edited["context"].setdefault("approvals", {}).setdefault("issue_refund", {"approved": [], "rejected": []})
        a["approved"], a["rejected"] = ([], [call_id]) if call_id in (a.get("approved") or []) else ([call_id], [])
        text = json.dumps(edited)
        for s in stripe_ids:
            text = text.replace(s, "re_FORGED0000000000000000")
        rec["tamper"] = {"original_loads": asyncio.run(load(final)) is True,
                         "edited_copy_loads": asyncio.run(load(text)) is True,
                         "edit": "approval decision flipped, Stripe refund ids replaced"}
        rec["tamper"]["detected"] = rec["tamper"]["original_loads"] and not rec["tamper"]["edited_copy_loads"]
    rec["signed"] = None
    return rec


def interlock_record(cell, crashed_at):
    eid = effect_id_for({"request_id": request_id(cell)})
    b = bundle(open_journal(cell["journal"]), eid)
    if not b["entries"]:
        return None
    v = verify(b)
    altered = json.loads(json.dumps(b))
    altered["entries"][-1]["forged"] = True
    forged = json.loads(json.dumps(altered))
    prev = None
    for e in forged["entries"]:              # whoever holds the journal rebuilds the chain
        e["prev"] = prev
        e["hash"] = entry_hash(e)
        prev = e["hash"]
    d = next((e for e in b["entries"] if e["kind"] == "DISPATCHED"), {})
    return {"effect_id": eid, "kinds": [e["kind"] for e in b["entries"]],
            "verify": {k: v[k] for k in ("valid", "tamper_evident", "signed", "happened", "happened_once",
                                         "authorized_when_fired", "assumptions_held", "refused", "evidence", "rechecked_at_recovery")},
            "killed_attempt_visible": bool(d) and d["ts"] < crashed_at,
            "settled_before_crash": any(e["kind"] in ("COMMITTED", "REFUSED", "AMBIGUOUS") and e["ts"] < crashed_at
                                        for e in b["entries"]),
            "approver_in_record": ((d.get("checks") or {}).get("lease") or {}).get("approved_by"),
            "edited_entry_rejected": not verify(altered)["valid"], "rebuilt_chain_accepted": verify(forged)["valid"]}


def refunds_of(client, pi):
    data = client.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]
    return [{"id": r["id"], "amount": r["amount"], "status": r["status"], "metadata": r["metadata"]} for r in data]


def run_cell(data, env, name, mode, rep):
    sc, client = SCENARIOS[name], config.stripe()
    cell_dir = os.path.join(data, f"{name}-{mode}-{rep}")
    os.makedirs(cell_dir)
    case, pi = "case-4471-" + os.urandom(5).hex(), client.test_payment(PAID)
    approvals = Approvals(os.path.join(cell_dir, "approvals.db"))
    approvals.grant(case, APPROVED, "finance-lead")
    cell = new_cell_files(cell_dir, mode=mode, scenario=name, case=case, pi=pi, bot="support-bot", race=False, text=CASE_TEXT,
                          approvals_db=approvals.path, journal=os.path.join(cell_dir, "interlock.db"), lock=None)
    child = {**env, "INTERLOCK_CRASH": sc["crash"], "INTERLOCK_CRASH_MARKER": os.path.join(cell_dir, "crash-marker")}
    print(f"[{name}:{mode}:{rep}] {case} {pi}", flush=True)
    decide = spawn(cell_dir, "decide", child)
    decide_exit = wait(decide, 180)
    paused = next((e for e in events(cell_dir) if e["event"] == "paused"), {})
    first = spawn(cell_dir, "run", child)
    first_exit = wait(first, 240)
    crashed_at = time.time()
    action = None
    if sc["action"] == "hand_refund":
        action = {"hand_refund": client.request("POST", "/refunds", {"payment_intent": pi, "amount": APPROVED})["id"]}
    elif sc["action"] == "revoke":
        approvals.revoke(case)
        action = {"revoked": case, "at": time.time()}
    second = spawn(cell_dir, "resume", child)
    second_exit = wait(second, 400)
    done_at = time.time()
    time.sleep(2)
    refunds = refunds_of(client, pi)
    live = [r for r in refunds if r["status"] != "failed"]
    eid = effect_id_for({"request_id": request_id(cell)})
    own = [r["id"] for r in live if r["metadata"].get("sdk_case") == case or r["metadata"].get("interlock_effect_id") == eid]
    total = sum(r["amount"] for r in live)
    evs = events(cell_dir)
    answer = answer_of(evs)
    status = (answer or {}).get("status")
    invalid = []
    if len(paused.get("interruptions") or []) != 1:
        invalid.append(f"decide paused with {len(paused.get('interruptions') or [])} approval requests")
    if first_exit != -signal.SIGKILL:
        invalid.append(f"run phase did not die by SIGKILL (exit {first_exit})")
    if any(e["phase"] == "run" and e["event"] == "tool_return" for e in evs):
        invalid.append("tool returned before the crash")
    ilock = interlock_record(cell, crashed_at) if mode == "sdk_interlock" else None
    if ilock and ilock["settled_before_crash"]:
        invalid.append("journal settled before the crash")
    return {"kind": "single", "scenario": name, "mode": mode, "rep": rep, "case": case, "payment_intent": pi,
            "ran_at": datetime.datetime.fromtimestamp(crashed_at, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "model_decision": paused.get("interruptions"), "processes": [decide.proc, first.proc, second.proc],
            "exit_codes": [decide_exit, first_exit, second_exit], "sigkill": first_exit == -signal.SIGKILL,
            "outage_action": action, "answer": answer, "outcome": status,
            "pending_after_resume": next((e.get("pending") for e in evs if e["event"] == "finished"), None),
            "final_text": next((e.get("final_output") for e in reversed(evs) if e["event"] == "finished"), None),
            "refunds": refunds, "own_refund_ids": own, "refunded_cents": total,
            "want_cents": sc["want_cents"], "want_refunds": sc["want_refunds"],
            "invariant_held": total == sc["want_cents"] and len(live) == sc["want_refunds"],
            "answer_matches_stripe": (len(own) == 1) if status in SENT else (len(own) == 0 and bool(status)),
            "seconds_to_settle": round(done_at - crashed_at, 1), "invalid": invalid,
            "sdk_record": sdk_record(cell_dir, cell, own, [r["id"] for r in refunds]),
            "interlock_record": ilock, "events": evs}


def run_race(data, env, mode, crash, rep):
    client = config.stripe()
    run_dir = os.path.join(data, f"race-{mode}-{crash}-{rep}")
    os.makedirs(run_dir)
    case, pi = "case-4471-" + os.urandom(5).hex(), client.test_payment(PAID)
    approvals = Approvals(os.path.join(run_dir, "approvals.db"))
    approvals.grant(case, CAP, "finance-lead")
    cells = {bot: new_cell_files(os.path.join(run_dir, bot), mode=mode, scenario="shared_cap_race", case=case, pi=pi, bot=bot,
                                 race=True, text=TICKETS[bot] + RACE_NOTE, approvals_db=approvals.path,
                                 journal=os.path.join(run_dir, "interlock.db"), lock=os.path.join(run_dir, "cap.lock"))
             for bot in BOTS}
    child = {**env, "INTERLOCK_CRASH": crash, "INTERLOCK_CRASH_MARKER": os.path.join(run_dir, "crash-marker")}
    print(f"[race:{mode}:{crash}:{rep}] {case} {pi}", flush=True)
    decides = {b: spawn(os.path.join(run_dir, b), "decide", child) for b in BOTS}
    decide_exits = {b: wait(p, 180) for b, p in decides.items()}
    go = {**child, "RUN_GO_AT": str(time.time() + GO_DELAY)}
    live = [(b, spawn(os.path.join(run_dir, b), "run", go)) for b in BOTS]
    exits, crashed, crashed_at, started = {b: [] for b in BOTS}, None, None, time.time()
    procs = {b: [decides[b].proc, p.proc] for b, p in live}
    while live and time.time() - started < 600:
        for b, p in list(live):
            if p.poll() is None:
                continue
            live.remove((b, p))
            exits[b].append(p.returncode)
            if p.returncode == -signal.SIGKILL and crashed is None:      # restart the killed bot at once
                crashed, crashed_at = b, time.time()
                r = spawn(os.path.join(run_dir, b), "resume", child)
                procs[b].append(r.proc)
                live.append((b, r))
        time.sleep(0.05)
    for b, p in live:
        p.kill()
        p.wait()
        exits[b].append("timeout")
    done_at = time.time()
    time.sleep(2)
    refunds = refunds_of(client, pi)
    live = [r for r in refunds if r["status"] != "failed"]
    total = sum(r["amount"] for r in live)
    bots = {}
    for b in BOTS:
        bd, evs = os.path.join(run_dir, b), events(os.path.join(run_dir, b))
        eid = effect_id_for({"request_id": request_id(cells[b])})
        own = [r["id"] for r in live if (r["metadata"].get("sdk_case") == case and r["metadata"].get("bot") == b)
               or r["metadata"].get("interlock_effect_id") == eid]
        rets = [e["output"] for e in evs if e["event"] == "tool_return"]
        answer = rets[-1] if rets else answer_of(evs)
        paused = next((e for e in evs if e["event"] == "paused"), {})
        bots[b] = {"model_decision": paused.get("interruptions"), "answer": answer, "own_refund_ids": own,
                   "barrier_wait": next((e["wait"] for e in evs if e["event"] == "barrier"), None),
                   "sdk_record": sdk_record(bd, cells[b], own, [r["id"] for r in refunds]),
                   "interlock_record": interlock_record(cells[b], crashed_at or done_at) if mode == "sdk_interlock" else None}
    invalid = [] if crashed else ["no bot died by SIGKILL"]
    invalid += [f"{b} decide paused with {len(v['model_decision'] or [])} approval requests" for b, v in bots.items()
                if len(v["model_decision"] or []) != 1]
    return {"kind": "race", "scenario": "shared_cap_race", "mode": mode, "crash": crash, "rep": rep, "case": case,
            "payment_intent": pi, "ran_at": datetime.datetime.fromtimestamp(started, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "killed": crashed, "exit_codes": exits, "decide_exit_codes": decide_exits,
            "processes": procs, "refunds": refunds, "refunded_cents": total, "count": len(live),
            "invariant_held": total <= CAP, "seconds_to_settle": round(done_at - crashed_at, 1) if crashed_at else None,
            "bots": bots, "invalid": invalid}


def user_lines():
    """Non-blank, non-comment lines inside the # user:<tag> regions of this file, harness lines excluded."""
    counts, tag = {}, None
    for line in open(os.path.abspath(__file__)):
        s = line.strip()
        if s.startswith("# user:"):
            tag = s.split(":", 1)[1]
            continue
        if s.startswith("# end:"):
            tag = None
            continue
        if tag and s and not s.startswith("#") and not s.endswith("# harness"):
            counts[tag] = counts.get(tag, 0) + 1
    cap_src = open(os.path.join(ROOT, "scenarios", "shared_cap", "cap.py")).read()
    lines = cap_src.splitlines()
    cap = 0
    for node in ast.parse(cap_src).body:
        if getattr(node, "name", None) in ("reserved_cents", "CapJournal", "CapGate"):
            doc_lines = set()
            for n in ast.walk(node):
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                        and isinstance(n.body[0].value, ast.Constant):
                    doc_lines |= set(range(n.body[0].lineno, n.body[0].end_lineno + 1))
            cap += sum(1 for i in range(node.lineno, node.end_lineno + 1)
                       if i not in doc_lines and lines[i - 1].strip() and not lines[i - 1].strip().startswith("#"))
    counts["interlock_cap_scenario_code"] = cap
    per = {m: sum(counts.get(t, 0) for t in tags) for m, tags in TAGS.items()}
    per["sdk_interlock (race, + scenarios/shared_cap/cap.py reserve code)"] = per["sdk_interlock"] + cap
    return {"regions": counts, "per_column": per}


# ---------------------------------------------------------------- report

def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def verdict(c):
    diff = c["refunded_cents"] - c["want_cents"]
    return "held" if c["invariant_held"] else f"VIOLATED, ${diff / 100:.0f} too much" if diff > 0 else f"SHORT by ${-diff / 100:.0f}" \
        if diff < 0 else "VIOLATED, wrong refund count"


def record_quality(c, rec=None, il=None):
    rec, il = rec or c["sdk_record"], il if il is not None else c.get("interlock_record")
    t = rec.get("tamper") or {}
    parts = [f"SDK RunState+session: approval {rec['approval_in_record'] or 'absent'} by call id only (fields {rec['approval_fields']})",
             f"tool outputs {rec['tool_outputs_in_session']} for {rec['tool_attempts_actual']} real attempts",
             "checks recorded" if rec["checks_in_record"] else "no checks recorded",
             f"outcome {'matches' if rec['outcome_matches_stripe'] else 'does NOT match'} Stripe",
             "edited copy rejected" if t.get("detected") else "edited copy loads (not tamper-evident)" if t else "no final state",
             "unsigned"]
    if il:
        v = il["verify"]
        parts.append(f"Interlock receipt {'/'.join(il['kinds'])}: valid={v['valid']}, happened={v['happened']}, "
                     f"killed attempt visible={il['killed_attempt_visible']}, approver={il['approver_in_record']}, "
                     f"edited entry rejected={il['edited_entry_rejected']}, rebuilt chain accepted={il['rebuilt_chain_accepted']}, signed={v['signed']}")
    return "; ".join(parts)


def cell_text(c):
    return (f"{c['outcome']}; ${c['refunded_cents'] / 100:.0f} in {len([r for r in c['refunds'] if r['status'] != 'failed'])} "
            f"(want ${c['want_cents'] / 100:.0f} in {c['want_refunds']}); **{verdict(c)}**; answer "
            f"{'matches' if c['answer_matches_stripe'] else 'CONTRADICTS'} Stripe; {c['seconds_to_settle']}s"
            + (f"; INVALID: {'; '.join(c['invalid'])}" if c["invalid"] else ""))


def summarize(out):
    rows = []
    valid = [c for c in out["cells"] if not c["invalid"]]
    for name, sc in SCENARIOS.items():
        for m in sc["modes"]:
            cs = [c for c in valid if c["scenario"] == name and c["mode"] == m]
            if cs:
                rows.append({"scenario": name, "mode": m, "n": len(cs), "held": sum(c["invariant_held"] for c in cs),
                             "answers_match": sum(c["answer_matches_stripe"] for c in cs),
                             "record_outcome_matches": sum(c["sdk_record"]["outcome_matches_stripe"] for c in cs),
                             "median_settle": med(c["seconds_to_settle"] for c in cs),
                             "outcomes": sorted({str(c["outcome"]) for c in cs})})
    for m in RACE_MODES:
        for crash in ("after_commit", "before_send"):
            cs = [c for c in out["races"] if c["mode"] == m and c["crash"] == crash and not c["invalid"]]
            if cs:
                rows.append({"scenario": f"shared_cap_race/{crash}", "mode": m, "n": len(cs), "held": sum(c["invariant_held"] for c in cs),
                             "median_settle": med(c["seconds_to_settle"] for c in cs),
                             "totals": sorted(f"${c['refunded_cents'] / 100:.0f}" for c in cs)})
    return rows


def markdown(out):
    L = []
    w = L.append
    w("# Competitor: OpenAI Agents SDK human-in-the-loop, Stripe test mode, real SIGKILL\n")
    w(f"Generated {out['generated']} by `experiments/competitor_openai_agents.py`. openai-agents {out['versions']['openai-agents']} (MIT), "
      f"litellm {out['versions']['litellm']}, model `{MODEL}` through the SDK's `LitellmModel`, Stripe test mode, Interlock claim TTL "
      f"{out['claim_ttl']}s. Invalid cells (crash window missed, model did not pause for approval) are listed and excluded from tallies.\n")
    w("## How the SDK was run\n")
    w("As its human-in-the-loop guide describes: `@function_tool(needs_approval=True)` on `issue_refund`; `Runner.run` pauses "
      "with `result.interruptions`; the app stores `result.to_state().to_string()`; later `RunState.from_string(agent, s)`, "
      "`state.approve(item)` or `state.reject(item)`, and `Runner.run(agent, state, session=session)` with a `SQLiteSession`. "
      "The person's decision lives in an approvals table (approved by finance-lead, cap, revoked time) and is applied to the "
      "state each time the app resumes, which is the documented reload-approve-run sequence. Each phase is a separate OS "
      "process: decide (the model reads the payment and asks to refund), run (approval applied, tool executes, SIGKILL in "
      "the send), resume (a new process repeats reload, approve, run). The guide's caveat, \"structure tools for "
      "idempotency\", is followed with `Idempotency-Key = case/tool_call_id`.\n")
    w("## Results\n")
    by = {}
    for c in out["cells"]:
        by.setdefault((c["scenario"], c["mode"]), []).append(c)
    for name, sc in SCENARIOS.items():
        w(f"### `{name}`\n\n{sc['text']}.\n")
        w("| column | cells |\n|---|---|")
        for m in sc["modes"]:
            cs = by.get((name, m), [])
            w(f"| {COLUMNS[m]} | " + "<br>".join(cell_text(c) for c in cs) + " |")
        w("")
    w("### `shared_cap_race`\n\nTwo agent processes (support-bot, billing-bot), each a separate SDK run and session on one $100 "
      "payment. Each asks for $20; each approval request shows only its own $20 and is approved (case cap $30). Both resume "
      f"from one barrier {GO_DELAY}s after spawn; the first to reach the crash point is SIGKILLed and restarted at once. "
      "Invariant: total refunded <= $30.\n")
    w("| column | crash | held | totals | median settle (s) | what each bot reported (killed / other) |\n|---|---|---|---|---|---|")
    for m in RACE_MODES:
        for crash in ("after_commit", "before_send"):
            cs = [c for c in out["races"] if c["mode"] == m and c["crash"] == crash]
            ok = [c for c in cs if not c["invalid"]]
            if not cs:
                continue
            rep = "; ".join(f"{(c['bots'][c['killed']]['answer'] or {}).get('status') if c['killed'] else '-'} / "
                            f"{(c['bots'][next(b for b in BOTS if b != c['killed'])]['answer'] or {}).get('status') if c['killed'] else '-'}"
                            for c in ok)
            w(f"| {COLUMNS[m]} | `{crash}` | {sum(c['invariant_held'] for c in ok)}/{len(ok)}"
              + (f" ({len(cs) - len(ok)} invalid)" if len(cs) != len(ok) else "")
              + f" | {', '.join(sorted(f'${c['refunded_cents'] / 100:.0f}' for c in ok))} | {med(c['seconds_to_settle'] for c in ok)} | {rep} |")
    w("\n## Tally (valid cells)\n")
    w("| scenario | column | held | answers match Stripe | median settle (s) |\n|---|---|---|---|---|")
    for r in out["summary"]:
        w(f"| `{r['scenario']}` | {r['mode']} | {r['held']}/{r['n']} | {r.get('answers_match', '-') if 'answers_match' in r else '-'}"
          f"{'/' + str(r['n']) if 'answers_match' in r else ''} | {r['median_settle']} |")
    w("\n## Lines of user code\n")
    w("Counted by the harness from `# user:<tag>` regions of the script (non-blank, non-comment; crash hooks and logging "
      "excluded). `common` is the agent, both tools' signatures, the approval pause, storing state, and the reload-approve-run "
      "resume every SDK column needs.\n")
    w("| column | lines |\n|---|---|")
    for k, v in out["user_lines"]["per_column"].items():
        w(f"| {k} | {v} |")
    w(f"\nRegions: {json.dumps(out['user_lines']['regions'])}. Interlock itself (`interlock/`) is a library and is not counted; "
      "the race's cap reservation is scenario code (`scenarios/shared_cap/cap.py`, `reserved_cents`, `CapJournal`, `CapGate`) and is.\n")
    w("## Records\n")
    w("Scored per cell from the artifacts each system leaves, by the harness after the run (JSON `sdk_record`, `interlock_record`).\n")
    for c in out["cells"]:
        if not c["invalid"]:
            w(f"- `{c['scenario']}` / {c['mode']} / rep {c['rep']}: {record_quality(c)}")
    w("\n" + out["reading"])
    w("\n## Ids, for checking in the Stripe test dashboard\n")
    for c in out["cells"]:
        w(f"- `{c['scenario']}` / {c['mode']} / rep {c['rep']}: PaymentIntent `{c['payment_intent']}`, refunds "
          + (", ".join(f"`{r['id']}` ${r['amount'] / 100:.0f} {r['status']}" for r in c["refunds"]) or "none")
          + f", processes {[(p['pid'], p['name']) for p in c['processes']]}, exits {c['exit_codes']}")
    for c in out["races"]:
        w(f"- race / {c['mode']} / {c['crash']} / rep {c['rep']}: PaymentIntent `{c['payment_intent']}`, killed {c['killed']}, "
          f"exits {c['exit_codes']}, refunds " + (", ".join(f"`{r['id']}` ${r['amount'] / 100:.0f} {r['metadata'].get('bot') or r['metadata'].get('interlock_effect_id')}"
                                                          for r in c["refunds"]) or "none"))
    w("\n## Re-run\n\n    uv run --no-project --python 3.12 --with openai-agents==0.22.2 --with litellm \\\n"
      "        python experiments/competitor_openai_agents.py --reps 3 --race-reps 5\n")
    return "\n".join(L)


def main():
    args = sys.argv[1:]
    reps = int(args[args.index("--reps") + 1]) if "--reps" in args else 3
    race_reps = int(args[args.index("--race-reps") + 1]) if "--race-reps" in args else 5
    only = {a for a in args if ":" in a}
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key and os.path.exists("/Users/kiromoussa/CADAI/.env"):
        key = next((l.split("=", 1)[1].strip().strip("'\"") for l in open("/Users/kiromoussa/CADAI/.env")
                    if l.startswith("ANTHROPIC_API_KEY=")), None)
    env = {**os.environ, "ANTHROPIC_API_KEY": key or "", "STRIPE_SECRET_KEY": config.stripe_key() or "", "LITELLM_LOG": "ERROR"}
    data = tempfile.mkdtemp(prefix="competitor-oai-", dir=os.environ.get("COMPETITOR_DATA"))
    print(f"data {data}", flush=True)
    jobs = [("single", s, m, r) for s, sc in SCENARIOS.items() for m in sc["modes"] for r in range(reps)
            if not only or f"{s}:{m}" in only]
    jobs += [("race", m, crash, r) for m in RACE_MODES for crash in ("after_commit", "before_send") for r in range(race_reps)
             if not only or f"race:{m}" in only]

    def go(job):
        try:
            return run_cell(data, env, *job[1:]) if job[0] == "single" else run_race(data, env, *job[1:])
        except Exception as e:      # noqa: BLE001  one broken cell must not lose the rest
            return {"kind": job[0], "job": list(job[1:]), "error": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(go, jobs))
    errors = [r for r in results if "error" in r]
    import importlib.metadata as md
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "model": MODEL,
           "versions": {p: md.version(p) for p in ("openai-agents", "litellm", "openai")}, "claim_ttl": config.CLAIM_TTL,
           "cells": [r for r in results if r.get("kind") == "single" and "error" not in r],
           "races": [r for r in results if r.get("kind") == "race" and "error" not in r],
           "errors": errors, "user_lines": user_lines(), "data_dir": data}
    out["summary"] = summarize(out)
    out["reading"] = "## Reading\n\n(written after the run from the numbers above; see results/competitors/openai_agents.md)"
    dest = os.path.join(ROOT, "results", "competitors")
    os.makedirs(dest, exist_ok=True)
    name = "openai_agents" if not only else "openai_agents_partial"
    json.dump(out, open(os.path.join(dest, f"{name}.json"), "w"), indent=2, default=str)
    open(os.path.join(dest, f"{name}.md"), "w").write(markdown(out))
    for r in out["summary"]:
        print(r)
    for e in errors:
        print("ERROR", e)


if __name__ == "__main__":
    if sys.argv[1:2] == ["agent"]:
        agent_main(sys.argv[2], sys.argv[3])
    else:
        main()
