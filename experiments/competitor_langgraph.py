"""
Competitor: LangGraph (MIT) with its production checkpointer (PostgresSaver), live.

    uv run --no-project --python 3.12 --with langgraph==1.2.11 --with langgraph-checkpoint-postgres==3.1.2 \
        --with "psycopg[binary,pool]" --with langchain-anthropic==1.7.2 --with pycryptodome \
        python experiments/competitor_langgraph.py [--reps 3] [--cap-reps 10] [--parallel 4] [--only s1,s2,s3,s4]

The refund agent as LangGraph's docs build it: an agent node (ChatAnthropic, claude-haiku-4-5) reads the payment
through a ToolNode and proposes issue_refund; an approval node calls interrupt(); a person resumes it with
Command(resume=...); a refund node sends the Stripe refund with an idempotency key derived from the thread id.
Every invoke uses durability="sync". After a crash the thread is resumed with invoke(None, same thread_id).

Columns (the refund node differs, the graph around it is the same):
  langgraph           the docs pattern: approval honoured from state, idempotency key, cap via the Store (s4)
  langgraph_checked   plus the docs' "verify existing results": look up this thread's refund, re-read the
                      payment's refunds against the decision, and for s4 a Postgres advisory lock around the cap
  langgraph_interlock the refund node body is interlock.gate.Gate (CapGate from scenarios/shared_cap for s4)

Scenarios: s1 crash after Stripe commits; s2 crash before send, a person refunds the same $20 by hand during the
outage; s3 crash before send, the approval is revoked during the outage (graph.update_state); s4 two approved
agents race one $30 cap, one of them SIGKILLed (before_send or after_commit) and restarted at once.

Crashes: the worker process reaches the crash point, then blocks; the harness SIGKILLs it from outside
(macOS os.kill(getpid, SIGKILL) is not synchronous, docs/07-runtime.md 13.4). Ground truth: Stripe's refund list.
Keys at runtime only: STRIPE_SECRET_KEY or test_mode_api_key from `stripe config --list`; ANTHROPIC_API_KEY or
the line in /Users/kiromoussa/CADAI/.env. Postgres: a throwaway cluster started and stopped by this harness.
Writes results/competitors/langgraph.json and results/competitors/langgraph_tables.md.
"""
import argparse, collections, concurrent.futures, datetime, json, os, re, shutil, signal, socket, statistics, subprocess
import sys, tempfile, time, uuid
from typing import Annotated, TypedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.targets.stripe_api import StripeClient, StripeRefunds

MODEL = "claude-haiku-4-5-20251001"
PAID, APPROVED, CAP = 10000, 2000, 3000
CLAIM_TTL = 40                     # as backend/config.py and scenarios/shared_cap: longer than the Stripe client's 30s timeout
COLUMNS = ("langgraph", "langgraph_checked", "langgraph_interlock")
SENT = {"REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP", "COMMITTED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY",
        "REAPPLIED_AFTER_QUERY", "DUPLICATE_IGNORED"}
CASE_TEXT = ("Order #881, paid $100.00 by card. The blender arrived with its glass jar cracked. Support case #4471: "
             "support reviewed the photos and approved ONE partial refund of $20.00 for the jar; the customer keeps the "
             "blender. Issue the approved refund.")
CAP_TEXT = ("Case #4471. The customer paid $100.00 for a blender, one card payment. Case approval: support and billing "
            "together may refund at most $30.00 on this payment. ")
TICKETS = {"support-bot": CAP_TEXT + "Support ticket: the glass jar arrived cracked, the customer keeps the blender. "
                                     "Support's policy for a cracked jar is a $20.00 partial refund.",
           "billing-bot": CAP_TEXT + "Billing ticket: delivery arrived 5 days late. Billing's late-delivery policy is a "
                                     "$20.00 refund."}
SCENARIOS = {
    "s1": dict(name="crash_after_commit", crash="after_commit", action=None, want=(APPROVED, 1),
               text="worker SIGKILLed after Stripe's refund response arrived, before the node returned; resumed"),
    "s2": dict(name="hand_refund_during_outage", crash="before_send", action="hand_refund", want=(APPROVED, 1),
               text="worker SIGKILLed right before the refund POST; a person refunds the same $20 by hand; resumed. "
                    "Want: only the hand refund"),
    "s3": dict(name="approval_revoked_during_outage", crash="before_send", action="revoke", want=(0, 0),
               text="worker SIGKILLed right before the refund POST; the approval is revoked with graph.update_state; "
                    "resumed. Want: nothing"),
}

# ---------------------------------------------------------------- harness hooks used inside the worker process
RUN_DIR, BOT = os.environ.get("LG_RUN_DIR", ""), os.environ.get("LG_BOT", "agent")
_stripe = None


def stripe():
    global _stripe
    _stripe = _stripe or StripeClient(os.environ["STRIPE_SECRET_KEY"])
    return _stripe


def event(ev, **kw):
    if RUN_DIR:
        with open(os.path.join(RUN_DIR, "events.jsonl"), "a") as f:
            f.write(json.dumps({"t": time.time(), "bot": BOT, "pid": os.getpid(), "ev": ev, **kw}) + "\n")


def crash_point(point):
    """One crash per run: the first process to reach LG_CRASH claims it, then blocks until the harness SIGKILLs it."""
    if os.environ.get("LG_CRASH") != point:
        return
    try:
        fd = os.open(os.path.join(RUN_DIR, "crash.claimed.tmp." + BOT), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, BOT.encode())
        os.close(fd)
        os.link(os.path.join(RUN_DIR, "crash.claimed.tmp." + BOT), os.path.join(RUN_DIR, "crash.claimed"))
    except FileExistsError:
        return
    event("at_crash_point", point=point)
    time.sleep(3600)


def send_refund(pi, amount, key, metadata):
    """The Stripe POST with the harness's crash points around it. Counted as one line of user code."""
    crash_point("before_send")
    event("send")
    r = stripe().request("POST", "/refunds", {"payment_intent": pi, "amount": amount, "metadata": metadata},
                         idempotency_key=key)
    event("committed", refund=r["id"], replayed=r["_replayed"])
    crash_point("after_commit")
    return r


class HookedRefunds(StripeRefunds):
    """Interlock's Stripe target with the same crash points around the real POST (harness, not user code)."""
    def apply(self, eid, effect, crash_after_effect=False):
        crash_point("before_send")
        out = super().apply(eid, effect)
        crash_point("after_commit")
        return out


def live_refunds(pi):
    return [r for r in stripe().request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]
            if r["status"] != "failed"]


def payment_facts(pi):
    p, refunded = stripe().request("GET", f"/payment_intents/{pi}"), sum(r["amount"] for r in live_refunds(pi))
    return {"paid_cents": p["amount_received"], "refunded_cents": refunded,
            "refundable_cents": p["amount_received"] - refunded}


# >>> user:base  the graph, as LangGraph's docs build a tool-calling agent with an approval interrupt
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import InjectedState, ToolNode
from langgraph.types import Command, interrupt


class Case(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    payment_intent: str
    case: str
    cap_cents: int
    decision: dict
    approval: dict
    outcome: str
    refund_id: str


@tool
def get_payment(state: Annotated[dict, InjectedState]) -> dict:
    """Live facts for this case's Stripe payment: amount paid, already refunded, and still refundable, in cents."""
    return payment_facts(state["payment_intent"])


@tool
def issue_refund(amount_cents: int, reason: str) -> str:
    """Propose the refund for this case's payment, in integer cents. A person approves it before it is sent."""
    raise RuntimeError("routed to approval, never executed")


SYSTEM = ("You are a payments support agent. Read the support case, look up the payment with get_payment, then call "
          "issue_refund exactly once for the refund the case approves, in integer cents.")
llm = ChatAnthropic(model=MODEL, max_tokens=1024, max_retries=5, timeout=60).bind_tools(
    [get_payment, issue_refund], tool_choice="any")


def agent(state: Case):
    return {"messages": [llm.invoke([SystemMessage(SYSTEM)] + state["messages"])]}


def route(state: Case):
    return "propose" if any(c["name"] == "issue_refund" for c in state["messages"][-1].tool_calls) else "tools"


def propose(state: Case):
    args = next(c for c in state["messages"][-1].tool_calls if c["name"] == "issue_refund")["args"]
    facts, amount = payment_facts(state["payment_intent"]), args.get("amount_cents")
    if type(amount) is not int or not 0 < amount <= min(facts["refundable_cents"], state.get("cap_cents") or PAID):
        return Command(goto=END, update={"outcome": f"REFUSED:invalid_decision {amount!r}"})
    return Command(goto="approve", update={"decision": {"amount_cents": amount, "reason": str(args.get("reason"))[:300],
                                                        "refunded_cents_at_decision": facts["refunded_cents"]}})


def approve(state: Case):
    # A static edge to refund, not Command(goto=...): update_state during an outage drops a Command-routed pending
    # node (routing_probe below), so the refund node itself honours a rejection or revocation.
    return {"approval": interrupt({"refund": state["decision"], "payment_intent": state["payment_intent"]})}


def build(column, checkpointer, store):
    g = StateGraph(Case)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode([get_payment]))
    g.add_node("propose", propose)
    g.add_node("approve", approve)
    g.add_node("refund", REFUND_NODES[column])
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["tools", "propose"])
    g.add_edge("tools", "agent")
    g.add_edge("approve", "refund")
    g.add_edge("refund", END)
    return g.compile(checkpointer=checkpointer, store=store)
# <<< user:base


# >>> user:langgraph  the docs pattern: honour the approval in state, idempotency key, Store for the shared cap
from langgraph.config import get_store


def refund_langgraph(state: Case, config):
    thread, d, a = config["configurable"]["thread_id"], state["decision"], state["approval"]
    if not a.get("approved") or a.get("revoked_at") or d["amount_cents"] > a["max_cents"]:
        return {"outcome": "REFUSED:not_approved"}
    if state.get("cap_cents"):                       # cross-thread shared state: LangGraph's Store
        ns = ("refund_caps", state["case"])
        used = sum(i.value["cents"] for i in get_store().search(ns) if i.key != thread)
        if used + d["amount_cents"] > state["cap_cents"]:
            return {"outcome": "REFUSED:over_cap"}
        get_store().put(ns, thread, {"cents": d["amount_cents"]})
    r = send_refund(state["payment_intent"], d["amount_cents"], f"{thread}/refund", {"thread_id": thread, "bot": BOT})
    return {"outcome": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund_id": r["id"]}
# <<< user:langgraph


# >>> user:langgraph_checked  plus "verify existing results": lookup, premise re-read, advisory lock for the cap
import psycopg


def refund_checked(state: Case, config):
    thread, d, a, pi = config["configurable"]["thread_id"], state["decision"], state["approval"], state["payment_intent"]
    if not a.get("approved") or a.get("revoked_at") or d["amount_cents"] > a["max_cents"]:
        return {"outcome": "REFUSED:not_approved"}
    with psycopg.connect(os.environ["LG_DB"], autocommit=True) as lock:
        if state.get("cap_cents"):                   # session lock: Postgres drops it when the holder's connection dies
            lock.execute("SELECT pg_advisory_lock(hashtext(%s))", (state["case"],))
        refunds = live_refunds(pi)
        mine = next((r for r in refunds if r["metadata"].get("thread_id") == thread), None)
        if mine:
            return {"outcome": "FOUND_BY_LOOKUP", "refund_id": mine["id"]}
        others = sum(r["amount"] for r in refunds)
        if state.get("cap_cents") and others + d["amount_cents"] > state["cap_cents"]:
            return {"outcome": "REFUSED:over_cap"}
        if not state.get("cap_cents") and others != d["refunded_cents_at_decision"]:
            return {"outcome": f"REFUSED:stale_premise refunded {d['refunded_cents_at_decision']} -> {others}"}
        r = send_refund(pi, d["amount_cents"], f"{thread}/refund", {"thread_id": thread, "bot": BOT})
    return {"outcome": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund_id": r["id"]}
# <<< user:langgraph_checked


# >>> user:langgraph_interlock  the refund node body is Interlock's gate
from interlock.gate import Gate
from interlock.journal import effect_id_for
from interlock.receipts import bundle, verify
from scenarios.shared_cap.cap import CapGate, CapRefunds


class StateApproval:
    """The approval in the thread's state as Interlock's lease: re-read on every node run, so a revocation lands."""
    def __init__(self, approval):
        self.a = approval

    def is_live(self, lease):
        return bool(self.a.get("approved")) and not self.a.get("revoked_at")

    def allows(self, lease, effect):
        return self.is_live(lease) and effect["amount"] <= self.a["max_cents"]

    def describe(self, lease):
        return {"approver": self.a.get("approver"), "max_cents": self.a.get("max_cents"), "revoked": self.a.get("revoked_at")}


def refund_interlock(state: Case, config):
    thread, d, pi, cap = config["configurable"]["thread_id"], state["decision"], state["payment_intent"], state.get("cap_cents")
    path, leases = os.path.join(os.environ["LG_JOURNAL_DIR"], "journal.db"), StateApproval(state["approval"])
    if cap:
        gate, target = CapGate(CapRefunds(stripe(), pi, hook=crash_point), path, leases, cap), None
        premises = gate.target.capture(d["amount_cents"], cap)
        effect = {"case": state["case"], "bot": BOT, "amount": d["amount_cents"]}
    else:
        gate = Gate(HookedRefunds(stripe(), pi), path, leases, claim_ttl=CLAIM_TTL)
        premises = {"payment_intent": pi, "refunded_by_others": d["refunded_cents_at_decision"]}
        effect = {"amount": d["amount_cents"]}
    eid = effect_id_for({"request_id": thread})
    while eid in gate.journal.in_flight():           # an earlier run of this node died mid-send: recover it
        status = gate.recover(only=[eid]).get(eid)
        if status:
            break
        time.sleep(1)
    else:
        status = gate.submit({"agent": BOT, "lease": thread, "request_id": thread, "premises": premises, "effect": effect})
    evidence = verify(bundle(gate.journal, eid))["evidence"]
    return {"outcome": status, "refund_id": evidence.get("refund") if isinstance(evidence, dict) else evidence}
# <<< user:langgraph_interlock

REFUND_NODES = {"langgraph": refund_langgraph, "langgraph_checked": refund_checked, "langgraph_interlock": refund_interlock}


# ---------------------------------------------------------------- worker process
def worker(argv):
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.store.postgres import PostgresStore
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=("start", "resume", "revoke", "recover"))
    for a in ("--column", "--thread", "--pi", "--out"):
        p.add_argument(a, required=True)
    p.add_argument("--case", default="")
    p.add_argument("--cap", type=int, default=0)
    p.add_argument("--max-cents", type=int, default=APPROVED)
    p.add_argument("--go-at", type=float, default=0)
    a = p.parse_args(argv)
    db = os.environ["LG_DB"]
    with PostgresSaver.from_conn_string(db) as cp, PostgresStore.from_conn_string(db) as store:
        graph, cfg = build(a.column, cp, store), {"configurable": {"thread_id": a.thread}, "recursion_limit": 25}
        event(a.cmd + "_begin")
        if a.cmd == "start":
            text = TICKETS[BOT] if a.cap else CASE_TEXT
            out = graph.invoke({"messages": [HumanMessage(f"Support case:\n{text}")], "payment_intent": a.pi,
                                "case": a.case, "cap_cents": a.cap}, cfg, durability="sync")
        elif a.cmd == "resume":                      # a person approves: scripted here, standing in for the reviewer
            time.sleep(max(0, a.go_at - time.time()))
            out = graph.invoke(Command(resume={"approved": True, "approver": "support-lead (scripted)",
                                               "max_cents": a.max_cents}), cfg, durability="sync")
        elif a.cmd == "revoke":                      # LangGraph's API for editing a paused or failed thread
            approval = {**graph.get_state(cfg).values["approval"], "approved": False, "revoked_at": time.time(),
                        "revoked_by": "finance (scripted)"}
            graph.update_state(cfg, {"approval": approval})
            out = graph.get_state(cfg).values
        else:                                        # the docs' resume after a failure: invoke(None, same thread)
            out = graph.invoke(None, cfg, durability="sync")
        state = graph.get_state(cfg)
    event(a.cmd + "_end", outcome=out.get("outcome"))
    with open(a.out, "w") as f:
        json.dump({"outcome": out.get("outcome"), "refund_id": out.get("refund_id"), "decision": out.get("decision"),
                   "approval": out.get("approval"), "interrupted": bool(out.get("__interrupt__")), "next": list(state.next),
                   "model": next((m.response_metadata.get("model_name") for m in out.get("messages", [])
                                  if getattr(m, "response_metadata", None)), None)}, f, default=str)


# ---------------------------------------------------------------- harness
def keys():
    sk = os.environ.get("STRIPE_SECRET_KEY")
    if not sk:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True).stdout
        sk = next(iter(re.findall(r"^test_mode_api_key\s*=\s*'?(sk_test_[^'\s]+)", out, re.M)), None)
    ak = os.environ.get("ANTHROPIC_API_KEY")
    if not ak:
        with open(os.environ.get("ANTHROPIC_ENV_FILE", "/Users/kiromoussa/CADAI/.env")) as f:
            ak = next(l.split("=", 1)[1].strip().strip("'\"") for l in f if l.startswith("ANTHROPIC_API_KEY="))
    return sk, ak


class Postgres:
    """A throwaway Postgres 17 cluster on a free localhost port, stopped on exit."""
    def __init__(self, scratch):
        self.dir = tempfile.mkdtemp(prefix="lg-pg-", dir=scratch)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        bindir = os.environ.get("PG_BIN", "/opt/homebrew/opt/postgresql@17/bin")
        self.pg_ctl = os.path.join(bindir, "pg_ctl")
        subprocess.run([os.path.join(bindir, "initdb"), "-D", self.dir + "/data", "-U", "lg", "-A", "trust"], check=True,
                       capture_output=True)
        subprocess.run([self.pg_ctl, "start", "-D", self.dir + "/data", "-w", "-l", self.dir + "/log", "-o",
                        f"-p {self.port} -c unix_socket_directories='' -c listen_addresses=127.0.0.1 -c max_connections=300"],
                       check=True, capture_output=True)
        self.url = f"postgresql://lg@127.0.0.1:{self.port}/postgres"

    def stop(self):
        subprocess.run([self.pg_ctl, "-D", self.dir + "/data", "-m", "fast", "-w", "stop"], capture_output=True)


class Harness:
    def __init__(self, env, scratch):
        self.env, self.scratch, self.client = env, scratch, StripeClient(env["STRIPE_SECRET_KEY"])

    def spawn(self, run_dir, bot, cmd, column, thread, pi, extra=(), crash=None, journal_dir=None):
        env = {**self.env, "LG_RUN_DIR": run_dir, "LG_BOT": bot, "LG_CRASH": crash or "none",
               "LG_JOURNAL_DIR": journal_dir or run_dir}
        out = os.path.join(run_dir, f"{bot}.{cmd}.json")
        log = open(os.path.join(run_dir, f"{bot}.{cmd}.log"), "ab")
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "worker", cmd, "--column", column,
                                 "--thread", thread, "--pi", pi, "--out", out, *extra], env=env, stdout=log, stderr=log,
                                cwd=ROOT)
        proc.out, proc.bot, proc.cmd = out, bot, cmd
        return proc

    @staticmethod
    def result(proc):
        try:
            with open(proc.out) as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    @staticmethod
    def crashed_bot(run_dir):
        try:
            with open(os.path.join(run_dir, "crash.claimed")) as f:
                return f.read() or None
        except FileNotFoundError:
            return None

    def kill(self, proc):
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        return {"pid": proc.pid, "process": os.path.basename(sys.executable), "exit": proc.returncode,
                "sigkill": proc.returncode == -signal.SIGKILL}

    def truth(self, pi):
        return [{"id": r["id"], "amount": r["amount"], "status": r["status"], "metadata": r["metadata"]}
                for r in live_refunds_with(self.client, pi)]

    # ---- s1..s3: one agent, one approval
    def run_cell(self, key, column, rep):
        sc = SCENARIOS[key]
        pi, thread = self.client.test_payment(PAID), f"lg-{sc['name']}-{column}-{uuid.uuid4().hex[:8]}"
        d = tempfile.mkdtemp(prefix=f"lgrun-{key}-{column}-", dir=self.scratch)
        start = self.spawn(d, "agent", "start", column, thread, pi)
        start.wait(300)
        begun = self.result(start)
        if not begun or not begun["interrupted"]:
            return {"scenario": key, "column": column, "rep": rep, "error": f"start did not reach approval: {begun}",
                    "payment_intent": pi, "thread": thread, "run_dir": d}
        resume = self.spawn(d, "agent", "resume", column, thread, pi, crash=sc["crash"])
        deadline = time.time() + 180
        while not self.crashed_bot(d) and resume.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        if not self.crashed_bot(d):
            resume.kill()
            return {"scenario": key, "column": column, "rep": rep, "error": "never reached the crash point",
                    "payment_intent": pi, "thread": thread, "run_dir": d, "resume_result": self.result(resume)}
        crash = self.kill(resume)
        t_crash, action = time.time(), None
        if sc["action"] == "hand_refund":            # as from the dashboard: no idempotency key, no metadata
            action = {"hand_refund": self.client.request("POST", "/refunds", {"payment_intent": pi, "amount": APPROVED})["id"]}
        elif sc["action"] == "revoke":
            rv = self.spawn(d, "agent", "revoke", column, thread, pi)
            rv.wait(120)
            action = {"revoke": self.result(rv)}
        t_restart = time.time()
        rec = self.spawn(d, "agent", "recover", column, thread, pi)
        rec.wait(300)
        t_done = time.time()
        final = self.result(rec) or {}
        refunds = self.truth(pi)
        total, n = sum(r["amount"] for r in refunds), len(refunds)
        own = [r["id"] for r in refunds if r["metadata"].get("thread_id") == thread
               or r["metadata"].get("interlock_effect_id") == effect_id_for({"request_id": thread})]
        outcome = str(final.get("outcome"))
        refused = outcome.startswith("REFUSED")
        return {"scenario": key, "name": sc["name"], "column": column, "rep": rep, "payment_intent": pi, "thread": thread,
                "run_dir": d, "decision": begun["decision"], "model": begun["model"], "crash": crash, "outage_action": action,
                "outcome": outcome, "refund_id": final.get("refund_id"), "refunds": refunds, "refunded_cents": total,
                "refund_count": n, "want_cents": sc["want"][0], "want_count": sc["want"][1],
                "invariant_held": (total, n) == sc["want"],
                "answer_matches_stripe": len(own) == 1 if outcome in SENT else len(own) == 0 if refused else False,
                "seconds_crash_to_settled": round(t_done - t_crash, 2), "seconds_restart_to_settled": round(t_done - t_restart, 2),
                "record": self.record(column, thread, d, [effect_id_for({"request_id": thread})])}

    # ---- s4: two agents, two approvals, one $30 cap
    def run_cap(self, column, crash_point_, rep):
        pi, case = self.client.test_payment(PAID), f"cap-{uuid.uuid4().hex[:8]}"
        d = tempfile.mkdtemp(prefix=f"lgrun-s4-{column}-", dir=self.scratch)
        bots = ("support-bot", "billing-bot")
        threads = {b: f"lg-shared_cap-{column}-{case}-{b}" for b in bots}
        extra = ["--case", case, "--cap", str(CAP)]
        starts = [self.spawn(d, b, "start", column, threads[b], pi, extra) for b in bots]
        for s in starts:
            s.wait(300)
        begun = {s.bot: self.result(s) for s in starts}
        if not all(r and r["interrupted"] for r in begun.values()):
            return {"scenario": "s4", "column": column, "crash_at": crash_point_, "rep": rep, "payment_intent": pi,
                    "error": f"start did not reach approval: {begun}", "run_dir": d}
        go_at = time.time() + 2.0
        procs = {b: self.spawn(d, b, "resume", column, threads[b], pi, extra + ["--go-at", str(go_at)], crash=crash_point_)
                 for b in bots}
        finals, crash, crashed, t_crash, t_last = {}, None, None, None, None
        deadline = time.time() + 300
        while procs and time.time() < deadline:
            who = self.crashed_bot(d)
            if who and crashed is None and who in procs and procs[who].cmd == "resume":
                crashed, crash = who, self.kill(procs[who])
                t_crash = time.time()
                procs[who] = self.spawn(d, who, "recover", column, threads[who], pi, extra)
            for b, p in list(procs.items()):
                if p.poll() is not None and not (b == who and crashed is None):
                    finals[b] = self.result(p) or {"outcome": f"exit {p.returncode}"}
                    t_last = time.time()
                    del procs[b]
            time.sleep(0.05)
        for p in procs.values():
            p.kill()
            p.wait()
        refunds = self.truth(pi)
        eids = {effect_id_for({"request_id": threads[b]}): b for b in bots}
        for r in refunds:
            r["bot"] = r["metadata"].get("bot") or eids.get(r["metadata"].get("interlock_effect_id"))
        total = sum(r["amount"] for r in refunds)
        answers = {b: (sum(r["bot"] == b for r in refunds) == 1) if str(finals.get(b, {}).get("outcome")) in SENT
                   else (sum(r["bot"] == b for r in refunds) == 0) for b in bots}
        return {"scenario": "s4", "name": "shared_cap", "column": column, "crash_at": crash_point_, "rep": rep,
                "payment_intent": pi, "case": case, "run_dir": d, "timed_out": bool(procs),
                "decisions": {b: begun[b]["decision"] for b in bots}, "model": begun[bots[0]]["model"],
                "crashed_bot": crashed, "crash": crash, "outcomes": {b: finals.get(b, {}).get("outcome") for b in bots},
                "refunds": refunds, "refunded_cents": total, "refund_count": len(refunds), "invariant_held": total <= CAP,
                "answers_match_stripe": answers,
                "seconds_crash_to_settled": round(t_last - t_crash, 2) if t_crash and t_last else None,
                "timeline": timeline(d),
                "record": self.record(column, None, d, list(eids), threads=list(threads.values()))}

    # ---- what the system itself recorded
    def record(self, column, thread, run_dir, eids, threads=None):
        from langgraph.checkpoint.postgres import PostgresSaver
        out = {"threads": {}}
        with PostgresSaver.from_conn_string(self.env["LG_DB"]) as cp:
            graph = build(column, cp, None)
            for t in threads or [thread]:
                hist = list(graph.get_state_history({"configurable": {"thread_id": t}}))
                last = hist[0].values if hist else {}
                with cp._cursor() as cur:
                    cur.execute("SELECT channel, count(*) FROM checkpoint_writes WHERE thread_id = %s GROUP BY channel", (t,))
                    writes = {r["channel"]: r["count"] for r in cur.fetchall()}
                out["threads"][t] = {
                    "checkpoints": len(hist), "sources": [h.metadata.get("source") for h in reversed(hist)],
                    "refund_node_completions": sum(1 for h in hist if h.metadata.get("source") == "loop"
                                                   and "outcome" in h.values and h.values.get("approval")),
                    "task_errors": sum(1 for h in hist for tk in h.tasks if tk.error),
                    "names_decision": bool(last.get("decision")), "names_approver": bool((last.get("approval") or {}).get("approver")),
                    "names_outcome": bool(last.get("outcome")), "names_refund_id": bool(last.get("refund_id")),
                    "names_revocation": bool((last.get("approval") or {}).get("revoked_at")),
                    "pending_write_channels": writes, "hashes_or_signatures": False}
        if column == "langgraph_interlock" and os.path.exists(os.path.join(run_dir, "journal.db")):
            from interlock.journal import SqliteJournal
            j = SqliteJournal(os.path.join(run_dir, "journal.db"))
            out["interlock"] = {eid: {"kinds": [e["kind"] for e in j.entries(eid)],
                                      **{k: v for k, v in verify(bundle(j, eid)).items() if k != "effect_id"}} for eid in eids}
        return out


def live_refunds_with(client, pi):
    return [r for r in client.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"] if r["status"] != "failed"]


def timeline(run_dir):
    try:
        with open(os.path.join(run_dir, "events.jsonl")) as f:
            return [json.loads(l) for l in f]
    except FileNotFoundError:
        return []


# ---------------------------------------------------------------- record integrity probes
def tamper_probes(env, cells):
    """Forge the record after the fact and ask each system's own reader whether anything noticed."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
    out = {}
    real = next((c for c in cells if c.get("scenario") == "s1" and c["column"] == "langgraph" and not c.get("error")), None)
    if real:
        cfg = {"configurable": {"thread_id": real["thread"]}}
        with PostgresSaver.from_conn_string(env["LG_DB"]) as cp:
            g = build("langgraph", cp, None)
            before = g.get_state(cfg).values
            with cp._cursor() as cur:
                cur.execute("UPDATE checkpoints SET checkpoint = jsonb_set(checkpoint, '{channel_values,outcome}', '\"REFUSED:not_approved\"') "
                            "WHERE thread_id = %s AND checkpoint_id = (SELECT max(checkpoint_id) FROM checkpoints WHERE thread_id = %s)",
                            (real["thread"], real["thread"]))
                edited = cur.rowcount
                cur.execute("UPDATE checkpoints SET checkpoint = checkpoint #- '{channel_values,refund_id}' "
                            "WHERE thread_id = %s AND checkpoint_id = (SELECT max(checkpoint_id) FROM checkpoints WHERE thread_id = %s)",
                            (real["thread"], real["thread"]))
            try:
                after, err = g.get_state(cfg).values, None
            except Exception as e:
                after, err = {}, repr(e)[:200]
        out["langgraph_plain_edit_latest_checkpoint"] = {
            "thread": real["thread"], "rows_edited": edited, "before": {k: before.get(k) for k in ("outcome", "refund_id")},
            "after": {k: after.get(k) for k in ("outcome", "refund_id")}, "reader_error": err,
            "detected": bool(err) or after.get("outcome") == before.get("outcome")}
    # EncryptedSerializer (AES-EAX, the docs' encryption option) on a fresh thread with the same graph shape
    key = os.urandom(32)
    with PostgresSaver.from_conn_string(env["LG_DB"]) as cp:
        cp.serde = EncryptedSerializer.from_pycryptodome_aes(key=key)
        g = build("langgraph", cp, None)

        def fresh():                                 # each probe gets its own thread, so one forgery cannot mask another
            t = f"lg-tamper-encrypted-{uuid.uuid4().hex[:8]}"
            c = {"configurable": {"thread_id": t}}
            g.update_state(c, {"payment_intent": "pi_probe", "outcome": "REFUNDED", "refund_id": "re_probe",
                               "decision": {"amount_cents": 2000}, "messages": [HumanMessage("probe")]}, as_node="refund")
            g.update_state(c, {"outcome": "REFUNDED", "refund_id": "re_probe_2"}, as_node="refund")
            return t, c

        t, cfg = fresh()
        with cp._cursor() as cur:
            cur.execute("SELECT checkpoint FROM checkpoints WHERE thread_id = %s ORDER BY checkpoint_id DESC LIMIT 1", (t,))
            plaintext_outcome = "REFUNDED" in json.dumps(cur.fetchone()["checkpoint"])
            cur.execute("SELECT count(*) FROM checkpoint_blobs WHERE thread_id = %s", (t,))
            blobs = cur.fetchone()["count"]
        results = {}
        for name, sql in (
                ("edit_inline_value", "UPDATE checkpoints SET checkpoint = jsonb_set(checkpoint, '{channel_values,outcome}', '\"REFUSED:not_approved\"') "
                                      "WHERE thread_id = %(t)s AND checkpoint_id = (SELECT max(checkpoint_id) FROM checkpoints WHERE thread_id = %(t)s)"),
                ("flip_byte_in_encrypted_blob", "UPDATE checkpoint_blobs SET blob = set_byte(blob, length(blob) - 1, (get_byte(blob, length(blob) - 1) + 1) %% 256) "
                                                "WHERE thread_id = %(t)s"),
                ("delete_latest_checkpoint", "DELETE FROM checkpoints WHERE thread_id = %(t)s AND checkpoint_id = "
                                             "(SELECT max(checkpoint_id) FROM checkpoints WHERE thread_id = %(t)s)")):
            t, cfg = fresh()
            before = None
            try:
                before = g.get_state(cfg).values
            except Exception:
                pass
            with cp._cursor() as cur:
                cur.execute(sql, {"t": t})
                rows = cur.rowcount
            try:
                after, err = g.get_state(cfg).values, None
            except Exception as e:
                after, err = {}, repr(e)[:200]
            results[name] = {"rows": rows, "reader_error": err, "detected": bool(err),
                             "before": {k: (before or {}).get(k) for k in ("outcome", "refund_id")},
                             "after": {k: after.get(k) for k in ("outcome", "refund_id")}}
        out["langgraph_encrypted"] = {"thread": t, "outcome_stored_in_plaintext": plaintext_outcome, "blob_rows": blobs,
                                      "probes": results}
    # Interlock's receipt on a real s1 journal: rewrite the commit with a recomputed hash, and truncate, keyed and not
    icell = next((c for c in cells if c.get("scenario") == "s1" and c["column"] == "langgraph_interlock" and not c.get("error")), None)
    if icell:
        from interlock.journal import SqliteJournal, entry_hash
        j, eid = SqliteJournal(os.path.join(icell["run_dir"], "journal.db")), effect_id_for({"request_id": icell["thread"]})
        hmac_key = os.urandom(16).hex()
        signed = bundle(j, eid, key=hmac_key)
        forged = json.loads(json.dumps(signed))
        last = forged["entries"][-1]
        last["result"] = {**(last.get("result") or {}), "refund": "re_FORGED"}
        last["hash"] = entry_hash(last)
        truncated = {**json.loads(json.dumps(signed)), "entries": signed["entries"][:-1]}
        out["interlock_receipt"] = {
            "effect_id": eid, "kinds": [e["kind"] for e in signed["entries"]],
            "forged_commit_unsigned_verify_valid": verify(forged)["valid"],
            "forged_commit_keyed_verify_valid": verify(forged, key=hmac_key)["valid"],
            "truncated_unsigned_verify_valid": verify(truncated)["valid"],
            "truncated_keyed_verify_valid": verify(truncated, key=hmac_key)["valid"],
            "truncated_unsigned_happened": verify(truncated)["happened"],
            "note": "the HMAC key is held by the harness here; a key the writer also holds proves nothing against the writer"}
    return out


def routing_probe(env):
    """
    The docs' approve/reject pattern routes with Command(goto=...). A step after it fails (here an exception; the smoke
    run did the same with SIGKILL), the approval is revoked with update_state, the thread is resumed with invoke(None).
    Does the failed step still run? Compared with a static edge. No Stripe, no model.
    """
    from langgraph.checkpoint.postgres import PostgresSaver
    out = {}
    for routing in ("command_goto", "static_edge"):
        class S(TypedDict, total=False):
            approval: dict
            outcome: str
        calls = []

        def approve_(s):
            a = interrupt("approve?")
            return Command(goto="act", update={"approval": a}) if routing == "command_goto" else {"approval": a}

        def act(s):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("the worker died mid-send")
            return {"outcome": "SENT" if s["approval"].get("approved") else "REFUSED:not_approved"}

        g = StateGraph(S)
        g.add_node("approve", approve_, destinations=("act",))
        g.add_node("act", act)
        g.add_edge(START, "approve")
        if routing == "static_edge":
            g.add_edge("approve", "act")
        g.add_edge("act", END)
        with PostgresSaver.from_conn_string(env["LG_DB"]) as cp:
            graph, cfg = g.compile(checkpointer=cp), {"configurable": {"thread_id": f"lg-routing-{routing}-{uuid.uuid4().hex[:8]}"}}
            graph.invoke({}, cfg, durability="sync")
            try:
                graph.invoke(Command(resume={"approved": True}), cfg, durability="sync")
            except RuntimeError:
                pass
            failed_next = list(graph.get_state(cfg).next)
            graph.update_state(cfg, {"approval": {"approved": False, "revoked_at": time.time()}})
            revoked_next = list(graph.get_state(cfg).next)
            final = graph.invoke(None, cfg, durability="sync")
        out[routing] = {"next_after_failure": failed_next, "next_after_update_state": revoked_next,
                        "final_outcome": (final or {}).get("outcome"), "act_runs": len(calls)}
    return out


# ---------------------------------------------------------------- user code size
def user_lines():
    src, out, name = open(os.path.abspath(__file__)).read().splitlines(), {}, None
    for line in src:
        m = re.match(r"# (>>>|<<<) user:(\w+)", line)
        if m:
            name = m.group(2) if m.group(1) == ">>>" else None
            continue
        s = line.strip()
        if name and s and not s.startswith("#") and not (s.startswith('"""') and s.endswith('"""')):
            out[name] = out.get(name, 0) + 1
    return out


def summarize(cells, runs):
    rows = []
    for key in SCENARIOS:
        for col in COLUMNS:
            cs = [c for c in cells if c["scenario"] == key and c["column"] == col and not c.get("error")]
            if cs:
                rows.append({"scenario": key, "name": SCENARIOS[key]["name"], "column": col, "n": len(cs),
                             "held": sum(c["invariant_held"] for c in cs), "answers_match": sum(c["answer_matches_stripe"] for c in cs),
                             "outcomes": dict(collections.Counter(c["outcome"].split(" ")[0] for c in cs)),
                             "stripe": dict(collections.Counter(f"${c['refunded_cents'] / 100:.0f} in {c['refund_count']}" for c in cs)),
                             "median_crash_to_settled": statistics.median(c["seconds_crash_to_settled"] for c in cs),
                             "median_restart_to_settled": statistics.median(c["seconds_restart_to_settled"] for c in cs),
                             "errors": sum(1 for c in cells if c["scenario"] == key and c["column"] == col and c.get("error"))})
    for crash in ("after_commit", "before_send"):
        for col in COLUMNS:
            rs = [r for r in runs if r["crash_at"] == crash and r["column"] == col and not r.get("error")]
            if rs:
                settle = [r["seconds_crash_to_settled"] for r in rs if r["seconds_crash_to_settled"] is not None]
                rows.append({"scenario": "s4", "name": "shared_cap", "crash_at": crash, "column": col, "n": len(rs),
                             "held": sum(r["invariant_held"] for r in rs),
                             "answers_match": sum(all(r["answers_match_stripe"].values()) for r in rs),
                             "outcomes": dict(collections.Counter(
                                 f"crashed {r['outcomes'].get(r['crashed_bot'])} / other "
                                 f"{next(v for b, v in r['outcomes'].items() if b != r['crashed_bot'])}" for r in rs if r["crashed_bot"])),
                             "stripe": dict(collections.Counter(f"${r['refunded_cents'] / 100:.0f} in {r['refund_count']}" for r in rs)),
                             "crashes": sum(bool(r["crashed_bot"]) for r in rs), "timed_out": sum(r["timed_out"] for r in rs),
                             "median_crash_to_settled": statistics.median(settle) if settle else None,
                             "errors": sum(1 for r in runs if r["crash_at"] == crash and r["column"] == col and r.get("error"))})
    return rows


def tables(out):
    lines = [f"# LangGraph competitor run: tables (generated {out['generated']})", "",
             "| scenario | column | n | held | answers match Stripe | Stripe end state | outcomes | median crash to settled (s) |",
             "|---|---|---|---|---|---|---|---|"]
    for r in out["summary"]:
        sc = r["name"] + (f" / {r['crash_at']}" if r.get("crash_at") else "")
        lines.append(f"| {sc} | {r['column']} | {r['n']} | {r['held']}/{r['n']} | {r['answers_match']}/{r['n']} | "
                     f"{', '.join(f'{v}x {k}' for k, v in sorted(r['stripe'].items()))} | "
                     f"{'; '.join(f'{v}x {k}' for k, v in sorted(r['outcomes'].items()))} | {r['median_crash_to_settled']} |")
    lines += ["", "User code lines (non-blank, non-comment): " + json.dumps(out["user_lines"]), "",
              "Tamper probes: ```" + json.dumps(out["tamper"], indent=1) + "```", ""]
    return "\n".join(lines)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        return worker(sys.argv[2:])
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--cap-reps", type=int, default=10)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--only", default="s1,s2,s3,s4")
    ap.add_argument("--columns", default=",".join(COLUMNS))
    ap.add_argument("--scratch", default=os.environ.get("LG_SCRATCH", tempfile.gettempdir()))
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    only, cols = args.only.split(","), args.columns.split(",")
    sk, ak = keys()
    pg = Postgres(args.scratch)
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from langgraph.store.postgres import PostgresStore
        env = {**os.environ, "STRIPE_SECRET_KEY": sk, "ANTHROPIC_API_KEY": ak, "LG_DB": pg.url, "PYTHONPATH": ROOT}
        os.environ.update({"STRIPE_SECRET_KEY": sk, "LG_DB": pg.url})
        with PostgresSaver.from_conn_string(pg.url) as cp, PostgresStore.from_conn_string(pg.url) as st:
            cp.setup()
            st.setup()
        h = Harness(env, args.scratch)
        jobs = [("cell", k, c, rep) for rep in range(args.reps) for k in SCENARIOS if k in only for c in cols]
        jobs += [("cap", crash, c, rep) for rep in range(args.cap_reps) if "s4" in only
                 for crash in ("after_commit", "before_send") for c in cols]
        cells, runs = [], []
        with concurrent.futures.ThreadPoolExecutor(args.parallel) as pool:
            futs = [pool.submit(h.run_cell, k, c, rep) if kind == "cell" else pool.submit(h.run_cap, c, k, rep)
                    for kind, k, c, rep in jobs]
            for f in concurrent.futures.as_completed(futs):
                try:
                    r = f.result()
                except Exception as e:
                    print("JOB FAILED", repr(e), flush=True)
                    continue
                (runs if r["scenario"] == "s4" else cells).append(r)
                print(r["scenario"], r["column"], r.get("crash_at", ""), "ERROR " + r["error"] if r.get("error") else
                      f"held={r['invariant_held']} ${r['refunded_cents'] / 100:.0f} in {r['refund_count']} "
                      f"outcome={r.get('outcome') or r.get('outcomes')} settle={r['seconds_crash_to_settled']} "
                      f"exit={(r.get('crash') or {}).get('exit')} {r['payment_intent']}", flush=True)
        import importlib.metadata as md
        out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "model": MODEL,
               "versions": {p: md.version(p) for p in ("langgraph", "langgraph-checkpoint", "langgraph-checkpoint-postgres",
                                                        "langgraph-prebuilt", "langchain-anthropic", "langchain-core", "psycopg")},
               "postgres": subprocess.run([os.path.join(os.path.dirname(pg.pg_ctl), "postgres"), "--version"],
                                          capture_output=True, text=True).stdout.strip(),
               "python": sys.version.split()[0], "reps": args.reps, "cap_reps": args.cap_reps, "parallel": args.parallel,
               "claim_ttl": CLAIM_TTL, "user_lines": user_lines(), "summary": summarize(cells, runs),
               "tamper": tamper_probes(env, cells), "routing_probe": routing_probe(env), "cells": cells, "runs": runs}
        print(json.dumps(out["routing_probe"], indent=1))
        for r in out["summary"]:
            print(json.dumps(r))
        print(json.dumps(out["tamper"], indent=1))
        if not args.no_write:
            os.makedirs(os.path.join(ROOT, "results", "competitors"), exist_ok=True)
            with open(os.path.join(ROOT, "results", "competitors", "langgraph.json"), "w") as f:
                json.dump(out, f, indent=1, default=str)
            with open(os.path.join(ROOT, "results", "competitors", "langgraph_tables.md"), "w") as f:
                f.write(tables(out))
    finally:
        pg.stop()


if __name__ == "__main__":
    main()
