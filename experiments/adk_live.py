"""
Google ADK agent + AP2 mandate + Stripe test mode, end to end with real crashes. Nothing simulated in-process:

    export ANTHROPIC_API_KEY=...        # or GOOGLE_API_KEY with ADK_MODEL=gemini-2.5-flash
    uv run --no-project --python 3.13 --with google-adk==2.9.0 --with litellm \
        --with "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56d" python experiments/adk_live.py

Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only).

Each cell is one support case: a new $100 test card payment by a new Stripe customer, and Finance's approval of
one $20 refund issued as an AP2 open Payment Mandate (cap $20, payee the customer, instrument the card, signed
by a Finance key, closable only by the agent's key). A real ADK agent (LlmAgent, a real model, a SQLite session
store, resumability on) calls get_payment, then authorize_refund (closes the mandate for the model's amount and
verifies it with the AP2 SDK, as AP2's credential provider step does), then issue_refund. The agent process
SIGKILLs itself inside the send, before or after Stripe's POST. The harness then acts (a hand refund, Finance
revoking the mandate, or waiting past its expiry), starts a new agent process, and that process resumes the
ADK invocation, which replays the unanswered issue_refund call. Ground truth is Stripe's refund list for the
cell's PaymentIntent. Writes results/adk_live.json and .md. Pass scenario:mode arguments to run some cells
and print them only.
"""
import asyncio, datetime, json, os, signal, statistics, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend import config
from backend.agent import AgentError, payment_facts, validate_refund
from interlock.integrations.adk import Guard
from interlock.integrations.ap2 import Mandates, close_payment_mandate, open_mandate_id, open_payment_mandate, stripe_payment
from interlock.journal import effect_id_for, open_journal
from interlock.receipts import bundle, verify
from interlock.targets.stripe_api import StripeRefunds

MODEL = os.environ.get("ADK_MODEL", "anthropic/claude-haiku-4-5-20251001")
PAID, APPROVED, AUDIENCE, KID = 10000, 2000, "interlock-refund-gate", "finance-approvals-1"
EXPIRY_WINDOW = 90          # seconds the short-lived mandate lives: enough to reach the send, then the outage outlasts it
MODES = ("adk_nokey", "adk", "adk_checked", "interlock")
COLUMNS = {"adk_nokey": "ADK, tool sends with no idempotency key",
           "adk": "ADK, Idempotency-Key = invocation id / function call id",
           "adk_checked": "ADK with that key plus a hand-written before_tool_callback re-check",
           "interlock": "ADK with Interlock's Guard as the before_tool_callback"}
SENT = {"REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP"}
PAYEE_NAME = "Customer, order #881"
CASE_TEXT = ("Order #881, paid $100.00 by card. The blender arrived with its glass jar cracked. Support case #4471: "
             "support reviewed the photos and Finance approved ONE partial refund of $20.00 for the jar; the customer "
             "keeps the blender. Issue the approved refund.")
INSTRUCTION = ("You are a payments support agent. Read the support case. Call get_payment, then call authorize_refund "
               "exactly once with the refund that was approved, in integer cents, and a short reason, then call "
               "issue_refund exactly once. Finish with one sentence saying what happened.")


def scenario(crash, text, want_cents=APPROVED, want_refunds=1, action=None, modes=MODES[1:], short_mandate=False):
    return dict(crash=crash, text=text, want_cents=want_cents, want_refunds=want_refunds, action=action, modes=modes,
                short_mandate=short_mandate)


AFTER = "agent process SIGKILLed after Stripe's response to the refund POST arrived, before ADK recorded the tool response"
BEFORE = "agent process SIGKILLed right before the refund POST"
SCENARIOS = {
    "crash_after_commit": scenario("after_commit", f"{AFTER}; restarted, and the invocation resumed", modes=MODES),
    "hand_refund_during_outage": scenario(
        "before_send", f"{BEFORE}; support refunds the same $20 by hand in Stripe; restarted and resumed. "
        "Want: only the hand refund", action="hand_refund"),
    "mandate_revoked_during_outage": scenario(
        "before_send", f"{BEFORE}; Finance revokes the open mandate; restarted and resumed. Want: nothing",
        want_cents=0, want_refunds=0, action="revoke"),
    "mandate_expired_during_outage": scenario(
        "before_send", f"{BEFORE}; the mandate (issued with a {EXPIRY_WINDOW}s lifetime, verified at authorize_refund "
        "while live) expires before the restart; restarted and resumed. Want: nothing",
        want_cents=0, want_refunds=0, action="expire", short_mandate=True),
    "mandate_revoked_after_commit": scenario(
        "after_commit", f"{AFTER}; Finance revokes the open mandate; restarted and resumed. "
        "Want: the one refund that landed while the mandate was live, reported as sent", action="revoke"),
}


# ---------------------------------------------------------------- the agent process

class KillableRefunds(StripeRefunds):
    """Real Stripe refunds with the agent's crash points on either side of the POST."""
    def apply(self, eid, effect, crash_after_effect=False):
        config.crash_once("before_send")        # DISPATCHED is already durable
        out = super().apply(eid, effect)
        config.crash_once("after_commit")       # Stripe's response is in memory, not in the journal
        return out


def agent_main(cell_dir, phase):
    from google.adk.agents import LlmAgent
    from google.adk.apps import App, ResumabilityConfig
    from google.adk.runners import Runner
    from google.adk.sessions.sqlite_session_service import SqliteSessionService
    from google.adk.tools import ToolContext
    from google.genai import types
    from jwcrypto.jwk import JWK

    cell = json.load(open(os.path.join(cell_dir, "cell.json")))
    client, pi, case, mode = config.stripe(), cell["payment_intent"], cell["case_id"], cell["mode"]
    agent_key = JWK.from_json(os.environ["ADK_LIVE_AGENT_JWK"])     # throwaway key made by the harness, never on disk
    mandates = Mandates(os.path.join(cell_dir, "mandates.db"), {KID: cell["finance_public_jwk"]}, AUDIENCE,
                        observe=stripe_payment(client))     # the PaymentIntent actually refunded must be the mandate's

    def log(**kw):
        with open(os.path.join(cell_dir, "agent.jsonl"), "a") as f:
            f.write(json.dumps({"ts": time.time(), "phase": phase, **kw}, default=str) + "\n")

    def get_payment(tool_context: ToolContext) -> dict:
        """Live facts for this case's Stripe payment: amount paid, already refunded, and still refundable, in cents."""
        tool_context.state["premises"] = StripeRefunds(client, pi).capture()      # the facts the decision rests on
        return payment_facts(client, pi)

    def authorize_refund(amount_cents: int, reason: str, tool_context: ToolContext) -> dict:
        """Close Finance's AP2 refund mandate for this amount and verify it. Call once, before issue_refund."""
        facts = payment_facts(client, pi)
        try:        # the model's call is untrusted input
            decision = validate_refund({"amount_cents": amount_cents, "reason": reason}, facts["paid_cents"], facts["refunded_cents"])
        except AgentError as e:
            return {"authorized": False, "error": str(e)}
        p = client.request("GET", f"/payment_intents/{pi}")      # payee and instrument come from Stripe, not the model
        payee, card = {"id": p["customer"], "name": PAYEE_NAME}, {"id": p["payment_method"], "type": "card"}
        nonce = mandates.challenge()            # issued by the verifier's store, single use; not picked by the agent
        chain = close_payment_mandate(agent_key, cell["open_mandate"], decision["amount_cents"], "USD", payee, card, pi,
                                      nonce, AUDIENCE)
        lease = mandates.register(chain, nonce)
        effect = {"payment_intent": pi, "amount": decision["amount_cents"], "currency": "USD", "payee": payee["id"],
                  "instrument": card["id"], "transaction_id": pi}
        ok, record = mandates.allows(lease, effect), mandates.describe(lease)
        tool_context.state["authorization"] = {"lease": lease, "effect": effect, "verified": ok}
        log(event="authorized", ok=ok, lease=lease, amount_cents=decision["amount_cents"], reason=decision["reason"],
            exp=record.get("exp"), problems=record["problems"])
        return {"authorized": ok, "mandate_reference": lease, "amount_cents": decision["amount_cents"], "problems": record["problems"]}

    def issue_refund(tool_context: ToolContext) -> dict:
        """Send the refund that authorize_refund approved. Call once, after authorize_refund succeeded."""
        auth = tool_context.state.get("authorization")
        if not auth or not auth["verified"]:
            return {"status": "REFUSED:not_authorized"}
        key = None if mode == "adk_nokey" else f"{tool_context.invocation_id}/{tool_context.function_call_id}"
        config.crash_once("before_send")
        r = client.request("POST", "/refunds", {"payment_intent": pi, "amount": auth["effect"]["amount"],
                                                "metadata": {"adk_case": case}}, idempotency_key=key)
        config.crash_once("after_commit")       # Stripe's response is in memory, not in ADK's session
        return {"status": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund_id": r["id"], "idempotency_key": key}

    def precheck(tool, args, tool_context):
        """The hand-written alternative: before the body sends, re-read Stripe and re-verify the mandate."""
        if tool.name != "issue_refund":
            return None
        auth, refunds = tool_context.state.get("authorization"), StripeRefunds(client, pi).refunds()
        mine = [r["id"] for r in refunds if r["metadata"].get("adk_case") == case]
        if mine:                    # an earlier attempt's refund landed: report it, never resend
            return {"status": "FOUND_BY_LOOKUP", "refund_id": mine[0]}
        if not auth or not mandates.allows(auth["lease"], auth["effect"]):
            return {"status": "REFUSED:mandate", "problems": mandates.describe(auth["lease"])["problems"] if auth else []}
        if sum(r["amount"] for r in refunds) != tool_context.state["premises"]["refunded_by_others"]:
            return {"status": "REFUSED:stale_premise"}
        return None

    guard, callback = None, precheck if mode == "adk_checked" else None
    if mode == "interlock":
        guard = Guard(os.path.join(cell_dir, "interlock"), mandates, claim_ttl=config.CLAIM_TTL)
        guard.gate("issue_refund", target_for=lambda effect: KillableRefunds(client, effect["payment_intent"]),
                   proposal=lambda args, ctx: {"lease": ctx.state["authorization"]["lease"], "request_id": f"refund:{case}",
                                               "premises": ctx.state["premises"], "effect": ctx.state["authorization"]["effect"]})
        callback = guard.before_tool_callback
    if MODEL.startswith("gemini"):
        model = MODEL
    else:
        from google.adk.models.lite_llm import LiteLlm
        model = LiteLlm(model=MODEL)
    agent = LlmAgent(name="support", model=model, instruction=INSTRUCTION, before_tool_callback=callback,
                     tools=[get_payment, authorize_refund, issue_refund])
    app = App(name="refunds", root_agent=agent, resumability_config=ResumabilityConfig(is_resumable=True))
    sessions = SqliteSessionService(os.path.join(cell_dir, "sessions.db"))
    runner = Runner(app=app, session_service=sessions)
    ids_path = os.path.join(cell_dir, "ids.json")

    async def drive():
        if phase == "new":
            ids = {"session": (await sessions.create_session(app_name="refunds", user_id="support")).id}
            kw = {"new_message": types.Content(role="user", parts=[types.Part(text=CASE_TEXT)])}
        else:
            ids = json.load(open(ids_path))
            if guard:
                log(event="recover_on_start", result=guard.recover())
            kw = {"invocation_id": ids["invocation"]}
        async for ev in runner.run_async(user_id="support", session_id=ids["session"], **kw):
            if "invocation" not in ids:
                ids["invocation"] = ev.invocation_id
                json.dump(ids, open(ids_path, "w"))
            for part in ev.content.parts if ev.content else []:
                if part.function_call:
                    log(event="adk", kind="call", name=part.function_call.name, id=part.function_call.id, payload=part.function_call.args)
                elif part.function_response:
                    log(event="adk", kind="response", name=part.function_response.name, id=part.function_response.id,
                        payload=part.function_response.response)
                elif part.text:
                    log(event="adk", kind="text", payload=part.text)

    asyncio.run(drive())


# ---------------------------------------------------------------- the harness

def run_agent(cell_dir, phase, env, timeout):
    with open(os.path.join(cell_dir, f"agent-{phase}.log"), "ab") as out:
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "agent", cell_dir, phase], env=env, stdout=out, stderr=out)
        try:
            return p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return "timeout"


def run_cell(data, env, name, mode):
    from jwcrypto.jwk import JWK
    sc, client = SCENARIOS[name], config.stripe()
    cell_dir = os.path.join(data, f"{name}-{mode}")
    os.makedirs(cell_dir)
    customer = client.request("POST", "/customers", {"name": PAYEE_NAME, "description": "Interlock experiments/adk_live.py"})
    payment = client.request("POST", "/payment_intents", {
        "amount": PAID, "currency": "usd", "customer": customer["id"], "payment_method": "pm_card_visa",
        "payment_method_types": ["card"], "confirm": "true"})
    pi, case_id = payment["id"], os.urandom(6).hex()
    finance, agent_key = JWK.generate(kty="EC", crv="P-256", kid=KID), JWK.generate(kty="EC", crv="P-256", kid="support-agent-1")
    exp = int(time.time()) + (EXPIRY_WINDOW if sc["short_mandate"] else 3600)
    open_token = open_payment_mandate(finance, agent_key.export_public(as_dict=True), APPROVED, "USD",
                                      {"id": customer["id"], "name": PAYEE_NAME}, {"id": payment["payment_method"], "type": "card"}, exp)
    json.dump({"mode": mode, "scenario": name, "case_id": case_id, "payment_intent": pi, "open_mandate": open_token,
               "finance_public_jwk": finance.export_public()}, open(os.path.join(cell_dir, "cell.json"), "w"))
    print(f"[{name}:{mode}] case {case_id} {pi} customer {customer['id']}", flush=True)

    child = {**env, "ADK_LIVE_AGENT_JWK": agent_key.export(), "INTERLOCK_CRASH": sc["crash"],
             "INTERLOCK_CRASH_MARKER": os.path.join(cell_dir, "crash-marker")}
    first = run_agent(cell_dir, "new", child, 240)
    crashed_at = time.time()
    print(f"[{name}:{mode}] agent exited {first}", flush=True)
    action = None
    if sc["action"] == "hand_refund":       # as from the dashboard: no idempotency key, no metadata
        action = {"hand_refund": client.request("POST", "/refunds", {"payment_intent": pi, "amount": APPROVED})["id"]}
    elif sc["action"] == "revoke":
        Mandates(os.path.join(cell_dir, "mandates.db"), {}, AUDIENCE).revoke(open_mandate_id(open_token), by="finance")
        action = {"revoked_open_mandate": open_mandate_id(open_token), "at": time.time()}
    elif sc["action"] == "expire":
        wait = max(0.0, exp + 2 - time.time())
        time.sleep(wait)
        action = {"waited_seconds": round(wait, 1), "mandate_exp": exp, "restarted_at": time.time()}
    second = run_agent(cell_dir, "resume", child, 400)
    done_at = time.time()
    time.sleep(2)                                           # then re-read Stripe for the record

    refunds = StripeRefunds(client, pi).refunds()
    events = [json.loads(l) for l in open(os.path.join(cell_dir, "agent.jsonl"))] if os.path.exists(os.path.join(cell_dir, "agent.jsonl")) else []
    answers = [e["payload"] for e in events if e.get("event") == "adk" and e.get("kind") == "response" and e.get("name") == "issue_refund"]
    answer = answers[-1] if answers else None
    status = answer and (answer.get("interlock") or answer.get("status"))
    sent = bool(answer) and (answer.get("sent") is True or status in SENT)
    receipt, eid = None, effect_id_for({"request_id": f"refund:{case_id}"})
    if mode == "interlock":
        b = bundle(open_journal(os.path.join(cell_dir, "interlock", "issue_refund.db")), eid)
        receipt = {"bundle": b, "verification": verify(b)} if b["entries"] else None
    own = [r["id"] for r in refunds if r["metadata"].get("adk_case") == case_id or r["metadata"].get("interlock_effect_id") == eid]
    total = sum(r["amount"] for r in refunds)
    authorized = next((e for e in events if e.get("event") == "authorized"), {})
    # The crash must land where the scenario says: the first process never got issue_refund's answer, and for
    # Interlock never recorded COMMITTED (else the resume only reads a finished effect and proves nothing).
    missed = [f"{e['name']} answered before the crash" for e in events if e.get("phase") == "new" and e.get("kind") == "response"
              and e.get("name") == "issue_refund"]
    if receipt:
        missed += [f"{e['kind']} journaled at {e['ts']:.2f}, before the crash" for e in receipt["bundle"]["entries"]
                   if e["kind"] in ("COMMITTED", "REFUSED", "AMBIGUOUS") and e["ts"] < crashed_at]
    return {
        "ran_at": datetime.datetime.fromtimestamp(crashed_at, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "crash_window_missed": missed,
        "scenario": name, "mode": mode, "case_id": case_id, "payment_intent": pi, "customer": customer["id"],
        "payment_method": payment["payment_method"], "open_mandate_id": open_mandate_id(open_token), "mandate_exp": exp,
        "authorization": {k: authorized.get(k) for k in ("ts", "ok", "lease", "amount_cents", "reason", "problems")},
        "agent_exit_codes": [first, second], "sigkill": first == -signal.SIGKILL, "outage_action": action,
        "outcome": status, "answer": answer, "answer_sent": sent, "final_text": next((e["payload"] for e in reversed(events)
                                                                                     if e.get("kind") == "text"), None),
        "recover_on_start": next((e["result"] for e in events if e.get("event") == "recover_on_start"), None),
        "agent_refund_ids": own, "refund_ids": [r["id"] for r in refunds], "refunded_cents": total,
        "expected_cents": sc["want_cents"], "expected_refunds": sc["want_refunds"],
        "invariant_held": total == sc["want_cents"] and len(refunds) == sc["want_refunds"],
        # the agent's own answer agrees with Stripe: sent means exactly one refund of its own, refused means none
        "answer_matches_stripe": len(own) == 1 if sent else len(own) == 0 and bool(status),
        "seconds_crash_to_done": round(done_at - crashed_at, 1), "receipt": receipt,
    }


def cell_text(c):
    diff, n = c["refunded_cents"] - c["expected_cents"], len(c["refund_ids"])
    verdict = ("held" if c["invariant_held"] else f"VIOLATED, ${diff / 100:.0f} too much" if diff > 0
               else f"SHORT by ${-diff / 100:.0f}" if diff < 0 else "VIOLATED, wrong refund count")
    return (f"{c['outcome']}; ${c['refunded_cents'] / 100:.0f} in {n} refund{'s' if n != 1 else ''} "
            f"(want ${c['expected_cents'] / 100:.0f} in {c['expected_refunds']}); {c['seconds_crash_to_done']}s crash to done; "
            f"**{verdict}**; answer {'matches' if c['answer_matches_stripe'] else 'CONTRADICTS'} Stripe"
            + ("" if c["sigkill"] else f"; AGENT DID NOT CRASH (exit {c['agent_exit_codes'][0]})")
            + (f"; CRASH WINDOW MISSED, cell not valid: {'; '.join(c['crash_window_missed'])}" if c.get("crash_window_missed") else ""))


def receipt_text(r):
    v, b = r["verification"], r["bundle"]
    d = next((e for e in b["entries"] if e["kind"] == "DISPATCHED"), {})
    via = next((e.get("via") for e in b["entries"] if e["kind"] == "COMMITTED"), None)
    rc = v.get("rechecked_at_recovery") or {}
    problems = (rc.get("lease") or {}).get("problems") or []
    ev = v.get("evidence")
    ev = f"refund {ev['refund']} ({ev['status']})" if isinstance(ev, dict) and "refund" in ev else ev
    return (f"; receipt `{b['summary']['final']}`" + (f" via `{via}`" if via else "")
            + f" (valid={v['valid']}, happened={v['happened']}, authorized_when_fired={v['authorized_when_fired']}, "
              f"assumptions_held={v['assumptions_held']}"
            + (f", mandate at dispatch `{d['checks']['lease']['mandate_reference']}`" if d.get("checks") else "")
            + (f", evidence `{ev}`" if ev else "")
            + (f", at recovery: mandate {'; '.join(problems)}" if problems else "")
            + (f", at recovery: premises {'; '.join(rc['violations'])}" if rc.get("violations") else "")
            + (f", refused='{v['refused']}'" if v.get("refused") else "") + ")")


def markdown(out):
    by = {(c["scenario"], c["mode"]): c for c in out["cells"]}
    rows = "\n".join(f"| `{s}` | " + " | ".join(cell_text(by[s, m]) if (s, m) in by else "not run" if m in sc["modes"] else "n/a"
                                              for m in MODES) + " |" for s, sc in SCENARIOS.items())

    def line(m):
        cs = [c for c in out["cells"] if c["mode"] == m]
        return (f"- {COLUMNS[m]}: {sum(c['invariant_held'] for c in cs)}/{len(cs)} left Stripe as wanted, "
                f"{sum(c['answer_matches_stripe'] for c in cs)}/{len(cs)} answers matched Stripe, median "
                f"{statistics.median(c['seconds_crash_to_done'] for c in cs):.0f}s from crash to done") if cs else f"- {COLUMNS[m]}: not run"
    ids = "\n".join(f"- `{c['scenario']}` / {c['mode']}: PaymentIntent `{c['payment_intent']}`, customer `{c['customer']}`, refunds "
                    f"{', '.join(f'`{r}`' for r in c['refund_ids']) or 'none'}, agent exits {c['agent_exit_codes']}, "
                    f"closed mandate `{c['authorization']['lease']}`"
                    + (receipt_text(c["receipt"]) if c["receipt"] else "") for c in out["cells"])
    llm = "\n".join(f"- `{c['scenario']}` / {c['mode']}: authorize_refund {c['authorization']['amount_cents']} cents, "
                    f"\"{c['authorization']['reason']}\"; final message: \"{(c['final_text'] or '').strip()[:160]}\"" for c in out["cells"])
    reruns = "".join(f" Cells re-run on their own at {r['at']}: {', '.join(f'`{x}`' for x in r['cells'])}; each cell's run time is"
                     f" `ran_at` in results/adk_live.json." for r in out.get("reruns", []))
    return f"""# Results: a Google ADK agent under an AP2 mandate, Stripe test mode, real crashes

Generated {out['generated']} by `experiments/adk_live.py`.{reruns} Model `{out['model']}` through ADK's LiteLlm, google-adk
{out['adk']}, AP2 SDK at commit `{out['ap2_commit']}`, Stripe test mode.

Each cell is one support case: a new $100 test card payment by a new Stripe customer, and Finance's approval of one
$20 refund, issued as an AP2 open Payment Mandate signed with a Finance key (cap 2000 USD cents, payee that customer,
instrument that card, closable only by the agent's key). A real ADK `LlmAgent` with a SQLite session store and
resumability on reads the payment (`get_payment`), closes and verifies the mandate for the amount it chose
(`authorize_refund`), then sends (`issue_refund`). The agent process SIGKILLs itself inside the send. The harness
acts during the outage, starts a new agent process, and that process resumes the ADK invocation; ADK replays the
unanswered `issue_refund` call with the same function call id. Totals and refund counts are Stripe's refund list
for the PaymentIntent, re-read at the end. "Answer" is the last `issue_refund` response the agent got, checked
against the refunds carrying this case's metadata. A cell whose crash did not land where its scenario says (the
first process got `issue_refund`'s answer, or the Interlock journal settled the effect before the crash) is marked
CRASH WINDOW MISSED and is not valid evidence.

| scenario | {' | '.join(COLUMNS[m] for m in MODES)} |
|---|---|---|---|---|
{rows}

{chr(10).join(line(m) for m in MODES)}

## Scenarios

""" + "\n".join(f"- `{s}`: {sc['text']}" for s, sc in SCENARIOS.items()) + f"""

## The columns

- **ADK, no key**: the tool body posts the refund with no Idempotency-Key. Run for `crash_after_commit` only.
- **ADK, call-id key**: the same body with Idempotency-Key = invocation id + "/" + function call id. ADK's resume
  replays the call with the same ids (checked before this run: a SIGKILLed tool call was replayed with the same
  `function_call_id` and `invocation_id`, and no new model call), so this key is stable across the crash.
- **ADK plus a hand-written re-check**: the call-id key, and a `before_tool_callback` of about ten lines that, before
  the body sends, looks for a refund carrying this case's metadata (reports it if found), re-verifies the AP2 mandate
  (`Mandates.allows`, the same verification Interlock uses), and compares Stripe's refunds with what `get_payment` read.
- **Interlock**: `interlock.integrations.adk.Guard` as the `before_tool_callback`, with `Mandates` as its lease store.
  The callback sends through the gate: a journaled intent before the POST, the mandate re-verified and the premises
  re-checked at dispatch and again on recovery, the closed mandate reserved for this one effect and counted against
  the open mandate's $20 cap, a re-closing of the same mandate held to the first decision's premises, a Stripe
  lookup when a re-check fails after a crash, and a receipt.

In every column the mandate is verified once when the model decides (`authorize_refund`), as AP2's credential
provider step does, and that answer is part of the ADK session, so the replay does not repeat it.

## What AP2 verification covers here

Cryptographic, by the AP2 SDK against the Finance public key (looked up by `kid`, never supplied by the agent): the
open mandate's signature, the closed mandate's signature by the agent key named in `cnf`, the `sd_hash` binding between
them, `aud` and `nonce` on the closed hop, and `exp`/`iat` with zero clock skew. AP2's constraint evaluator then
checks the amount range, the payee and the instrument against the closed mandate.

Not cryptographic: revocation is a row in `mandates.db` that Finance writes (AP2 v0.2 has no revocation). That the
Stripe refund matches the mandate is a comparison: with the effect's fields, which the tool reads from Stripe
(customer and payment method of the PaymentIntent), not from the model, and, on every check, with the PaymentIntent
the refund is actually sent to, read from Stripe again by `stripe_payment()` (its id, customer, card and currency
must be the mandate's transaction, payee, instrument and currency). `transaction_id` is the PaymentIntent id here; in AP2 it
is the hash of a merchant-signed checkout. AP2 v0.2 has no refund mandate: expressing Finance's refund approval as a
Payment Mandate from the merchant to the customer is this demo's convention, and no AP2 party here authorizes a Stripe
refund as such.

## What is real

- Stripe: every customer, payment, refund, lookup and idempotency replay is a real test-mode API call.
- Model: every decision is a real call to `{out['model']}` through ADK's LiteLlm wrapper.
- ADK: a real `Runner` over `SqliteSessionService`, `ResumabilityConfig(is_resumable=True)`, and
  `run_async(invocation_id=...)` in a new OS process after the crash.
- AP2: mandates signed and verified with the AP2 Python SDK; keys are generated per cell and never written to disk.
- Crashes: `os.kill(os.getpid(), SIGKILL)` in the agent process, one-shot via a marker file. Exit codes are recorded.
- Expiry: a mandate issued with a {EXPIRY_WINDOW}s lifetime and a real wait past it. Nothing in this run is emulated.

## Not verified live

- Gemini. The same code runs with `ADK_MODEL=gemini-2.5-flash` and `GOOGLE_API_KEY`, but the project's Gemini API key
  returned `429 RESOURCE_EXHAUSTED: Your prepayment credits are depleted` on {out['generated'][:10]}, so every cell used Claude.
- ADK inside Temporal (`temporalio.contrib.google_adk_agents`). There the check must sit in the activity, not in a
  callback; see docs/09-research-adk.md.

## Limits of what this shows

- Interlock is slower after a crash that kills a send: the dead process's claim is held for `CLAIM_TTL`
  ({out['claim_ttl']}s) before the replayed call may resolve it. The ADK columns rely on Stripe's key instead.
- The premise is "the payment's refunds are what `get_payment` read". An unrelated refund during the outage also
  stops the approved one (shown for Temporal in results/e2e_live.md, not re-run here).
- The receipt is the gate's own hash-chained record, unsigned here. The evidence that a refund happened once is
  Stripe's refund list.

## Model decisions

{llm}

## Ids, for checking in the Stripe test dashboard

{ids}

## Re-run

    ANTHROPIC_API_KEY=... uv run --no-project --python 3.13 --with google-adk==2.9.0 --with litellm \\
        --with "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56d" python experiments/adk_live.py
"""


def main():
    merge = "--merge" in sys.argv       # re-run the named cells and replace them in results/adk_live.json
    only = {a for a in sys.argv[1:] if not a.startswith("--")}
    import google.adk
    data = tempfile.mkdtemp(prefix="interlock-adk-")
    env = {**os.environ, "STRIPE_SECRET_KEY": config.stripe_key() or ""}
    print(f"data {data}", flush=True)
    cells = [run_cell(data, env, s, m) for s, sc in SCENARIOS.items() for m in sc["modes"] if not only or f"{s}:{m}" in only]
    for c in cells:
        print(f"{c['scenario']:32} {c['mode']:12} {cell_text(c)}")
    if only and not merge:
        return
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if merge:
        out = json.load(open(os.path.join(ROOT, "results", "adk_live.json")))
        new = {(c["scenario"], c["mode"]): c for c in cells}
        out["cells"] = [new.pop((c["scenario"], c["mode"]), c) for c in out["cells"]] + list(new.values())
        out.setdefault("reruns", []).append({"at": now, "cells": sorted(only)})
    else:
        out = {"generated": now, "model": MODEL, "adk": google.adk.__version__, "ap2_commit": "e1ea56d",
               "claim_ttl": config.CLAIM_TTL, "cells": cells}
    with open(os.path.join(ROOT, "results", "adk_live.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    with open(os.path.join(ROOT, "results", "adk_live.md"), "w") as f:
        f.write(markdown(out))


if __name__ == "__main__":
    if sys.argv[1:2] == ["agent"]:
        agent_main(sys.argv[2], sys.argv[3])
    else:
        main()
