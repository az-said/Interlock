"""
Workflows and shared setup for interlock_runtime: the tests, the Prove harness and the live example import this.

Everything runs against real Postgres and real worker subprocesses. `scripted_model` is EMULATED model variance
(a local function that returns scripted amounts); `anthropic_model` calls the real Anthropic API with the key from
the environment. Neither key is ever written anywhere.
"""
import json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "runtime"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import psycopg
from interlock_runtime import RetryPolicy, Runtime, TargetRejected, workflow
from experiments.runtime_target import LocalRefunds

DSN = os.environ.get("ILR_DSN")


# ---- shared setup -------------------------------------------------------------------------------------
def reset_db(dsn=None):
    """A clean ilr schema and invocation log. Returns a fresh Runtime."""
    with psycopg.connect(dsn or DSN, autocommit=True) as c:
        c.execute("drop schema if exists ilr cascade")
        c.execute("drop table if exists public.invocations")
        c.execute("create table public.invocations (id bigserial primary key, workflow_id text, name text, pid int, "
                  "started_at timestamptz not null default clock_timestamp())")
    return Runtime(dsn or DSN)


def log_invocation(wf_id, name):
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("insert into public.invocations (workflow_id, name, pid) values (%s, %s, %s)", (wf_id, name, os.getpid()))
        return c.execute("select count(*) from public.invocations where workflow_id = %s and name = %s", (wf_id, name)).fetchone()[0]


def invocations(dsn=None):
    with psycopg.connect(dsn or DSN, autocommit=True) as c:
        return [{"workflow_id": w, "name": n, "pid": p, "started_at": t} for w, n, p, t in c.execute(
            "select workflow_id, name, pid, extract(epoch from started_at)::float8 from public.invocations order by id")]


def spawn_worker(worker_id, log_dir, lease_ttl=2, poll=0.2, concurrency=4, env=None, only=None, args=()):
    """A real worker process. Its JSON event log is at proc.log_path."""
    log_path = os.path.join(log_dir, f"{worker_id}.log")
    cmd = [sys.executable, "-m", "interlock_runtime.worker", "--dsn", DSN, "--module", "experiments.runtime_flows",
           "--id", worker_id, "--lease-ttl", str(lease_ttl), "--poll", str(poll), "--concurrency", str(concurrency), *args]
    if only:
        cmd += ["--only", only]
    penv = {**os.environ, "PYTHONPATH": os.pathsep.join([os.path.join(ROOT, "runtime"), ROOT]), **(env or {})}
    with open(log_path, "a") as log:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=penv, stdout=log, stderr=subprocess.STDOUT)
    proc.log_path = log_path
    return proc


def events(proc):
    out = []
    with open(proc.log_path) as f:
        for line in f:
            if line.startswith("{"):
                out.append(json.loads(line))
    return out


def wait_for(pred, timeout=30, interval=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    raise TimeoutError("condition not met in time")


# ---- small workflows for the feature tests ---------------------------------------------------------------
def step_body(wf_id, name, seconds=0):
    log_invocation(wf_id, name)
    time.sleep(seconds)
    return name


@workflow("three_steps", "1")
def three_steps(ctx, inp):
    return [ctx.step(n, step_body, ctx.wf_id, n, inp.get("step_seconds", 0)) for n in ("one", "two", "three")]


@workflow("sleeper", "1")
def sleeper(ctx, inp):
    ctx.step("before", step_body, ctx.wf_id, "before")
    ctx.sleep(inp["seconds"])
    ctx.step("after", step_body, ctx.wf_id, "after")
    return "woke"


@workflow("waiter", "1")
def waiter(ctx, inp):
    return [ctx.wait_signal("go", timeout=inp.get("timeout")) for _ in range(inp.get("n", 1))]


class Flaky(Exception):
    pass


def flaky_body(wf_id, fails, error="Flaky"):
    n = log_invocation(wf_id, "flaky")
    if n <= fails:
        raise (ValueError if error == "ValueError" else Flaky)(f"attempt {n} fails")
    return n


@workflow("retrying", "1")
def retrying(ctx, inp):
    policy = RetryPolicy(initial=inp.get("initial", 0.5), max_attempts=inp.get("max_attempts", 0), non_retryable=("ValueError",))
    return ctx.step("flaky", flaky_body, ctx.wf_id, inp["fails"], inp.get("error", "Flaky"), retry=policy)


def scripted_model(request):
    """EMULATED model variance: the nth call for a case returns amounts[n-1] (the last one repeats)."""
    n = log_invocation(request["case"], "model")
    amounts = request["amounts"]
    return {"model": "EMULATED-scripted", "response": {"amount": amounts[min(n, len(amounts)) - 1]}, "usage": None}


@workflow("decider", "1")
def decider(ctx, inp):
    d = ctx.decide("pick_amount", call=scripted_model, request={"case": inp["case"], "amounts": inp["amounts"]},
                   premises=lambda: {"seen": inp.get("facts")})
    ctx.step("after_decide", step_body, ctx.wf_id, "after_decide")
    return d.output


@workflow("child_wf", "1")
def child_wf(ctx, inp):
    ctx.step("child_work", step_body, ctx.wf_id, "child_work")
    return inp["x"] * 2


@workflow("parent_wf", "1")
def parent_wf(ctx, inp):
    cid = ctx.child("child_wf", {"x": inp["x"]})
    return ctx.wait_child(cid)


@workflow("looper", "1")
def looper(ctx, inp):
    ctx.step("tick", step_body, ctx.wf_id, "tick")
    if inp["n"] > 0:
        ctx.continue_as_new({"n": inp["n"] - 1})
    return "done"


# ---- the refund workflows ------------------------------------------------------------------------------
def target_for(case):
    if case.get("target") == "stripe":
        return stripe_target(case["payment_intent"])
    return LocalRefunds(case["url"], case["tier"], send_timeout=case.get("send_timeout", 3),
                        settle_margin=case.get("settle_margin", 5), dedup_window=case.get("dedup_window"),
                        queryable=case.get("queryable"))


@workflow("refund_local", "1")
def refund_local(ctx, case):
    """The gated effect alone, under a grant named in the input (parity with interlock.Gate)."""
    t = target_for(case)
    facts = case["premises"] if "premises" in case else ctx.step("capture", t.capture)
    if case.get("pause"):
        ctx.step("pause", time.sleep, case["pause"])
    r = ctx.effect(t, key=case["key"], payload={"amount": case["amount"]}, premises=facts, grant=case["grant"],
                   local_premises=[tuple(p) for p in case.get("local", [])])
    return r.status


def model_for(case):
    return anthropic_model if case.get("model") == "anthropic" else scripted_model


def prompt_for(case):
    if case.get("model") == "anthropic":
        return {"model": case.get("model_id", "claude-haiku-4-5-20251001"), "case": case["id"], "message": case["message"],
                "policy": case["policy"]}
    return {"case": case["id"], "amounts": case.get("amounts", [2000])}


def notify_ops(effect_id):
    print(json.dumps({"event": "page_human", "effect_id": effect_id}), flush=True)
    return {"paged": effect_id}


def check_refund(case, effect_id):
    t = target_for(case)
    return {"found": t.query(effect_id, None)} if t.queryable else {"found": "no lookup"}


@workflow("refund", "2026-09-13.1")
def refund(ctx, case):
    """Decide with a model, wait for a human approval, send the gated refund, sleep, verify."""
    target = target_for(case)
    d = ctx.decide("pick_amount", call=model_for(case), request=prompt_for(case), premises=target.capture)
    approval = ctx.wait_signal("approve", timeout=case.get("approval_timeout", 24 * 3600))
    if approval is None:
        return {"status": "approval expired"}
    r = ctx.effect(target, key=f"refund:{case['id']}", payload={"amount": d.output["amount"]},
                   premises=approval["facts_seen"], grant=approval["grant_id"], decision=d.ref)
    if r.status == "AMBIGUOUS":
        ctx.step("page_human", notify_ops, r.effect_id)
    ctx.sleep(case.get("sleep_seconds", 3600))
    if ctx.patched("verify-after-refund"):
        ctx.step("verify", check_refund, case, r.effect_id)
    return {"status": r.status, "effect_id": r.effect_id, "amount": d.output["amount"], "result": r.result}


@workflow("refund", "2026-09-13.2")
def refund_v2(ctx, case):
    """A second deployment of the same code, so version pinning can be exercised."""
    return refund(ctx, case)


# ---- live adapters -----------------------------------------------------------------------------------
def anthropic_model(request):
    """
    A real Claude call through the official SDK (`uv run --with anthropic`). The client reads ANTHROPIC_API_KEY from the
    environment; the key is never recorded, only the response is.
    """
    import anthropic
    out = anthropic.Anthropic().messages.create(
        model=request["model"], max_tokens=1024,
        system="You decide refunds for a support desk. Reply with only a JSON object: "
               '{"amount_cents": <integer>, "reason": "<one sentence>"}.',
        messages=[{"role": "user", "content": f"Policy: {request['policy']}\nCustomer message: {request['message']}"}])
    text = "".join(b.text for b in out.content if b.type == "text")
    decision = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    return {"model": out.model, "usage": out.usage.model_dump(), "stop_reason": out.stop_reason,
            "response": {"amount": int(decision["amount_cents"]), "reason": decision.get("reason"), "text": text}}


def stripe_key():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True).stdout
        m = re.search(r"test_mode_api_key\s*=\s*['\"]?(sk_test_[A-Za-z0-9]+)", out)
        key = m and m.group(1)
    if not key or not key.startswith(("sk_test_", "rk_test_")):
        raise RuntimeError("a Stripe test-mode key is required (STRIPE_SECRET_KEY or `stripe config`)")
    return key


def stripe_target(payment_intent):
    """R7: interlock's StripeRefunds with the runtime's send deadline and a definite-failure mapping."""
    from interlock.targets.stripe_api import StripeClient, StripeError, StripeRefunds

    class StripeTarget(StripeRefunds):
        name, action, send_timeout, settle_margin = "stripe-refunds", "refund", 35, 10

        def apply(self, eid, effect):
            try:
                return super().apply(eid, effect)
            except StripeError as e:
                code = str(e).split(" ", 1)[0]
                if code.startswith("4") and code not in ("409", "429"):   # 409 key in use and 429 are not definite
                    raise TargetRejected(str(e)) from None
                raise

    return StripeTarget(StripeClient(stripe_key()), payment_intent)
