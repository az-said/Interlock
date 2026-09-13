"""
One refund step of a support agent, run as its own OS process so a crash is a real SIGKILL.

    python3 scenarios/stripe_dispute/worker.py SYSTEM CASE_JSON STATE_DIR [before|after]

SYSTEM is no_check, hand_check or interlock. The first run reads the payment, asks the model for the refund, and
saves the decision in STATE_DIR (the job a restart resumes; a restart never asks the model again). With a crash
point the process kills itself right before the refund POST, or right after Stripe's response arrives and before
anything records it. Prints one JSON line with the step's own answer.

no_check    Idempotency-Key "refund:<case>", the restart re-runs the send. No re-check, no log beyond the decision.
hand_check  what a careful support-tooling engineer writes: look up a refund already carrying this case's metadata,
            re-read the payment's disputes (no chargeback) and refunds (unchanged since the decision) and the
            approval, right before sending, plus the same key. Each check and each send is appended as one JSON
            line to STATE_DIR/hand_check.log (plain file, no hash chain). Stripe offers no conditional refund (no
            If-Match style precondition); its native guard is refusing a refund on a charged-back charge, which
            every column gets.
interlock   interlock.easy: those facts as premises, the approval as allowed=, Stripe's key as tier 1, the refund
            lookup by effect id, recovery on restart. The receipt bundle (every journal entry, hash-chained) is
            written to STATE_DIR/receipt.json.
"""
import json, os, re, signal, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dispute as sd                                          # noqa: E402
from interlock.easy import Interlock                          # noqa: E402
from interlock.receipts import verify                         # noqa: E402

CLAIM_TTL = 40      # above StripeClient's 30s timeout, so recovery never overlaps a send still in progress
MODEL = "claude-haiku-4-5-20251001"
CASE_TEXT = ("Support case #4471. The customer's $100 blender arrived with a cracked jar. They also asked their bank "
             "about the charge, so the payment shows an open bank inquiry (not a chargeback). Support approved a $20.00 "
             "partial refund as goodwill; the customer keeps the blender.")


def crash_point(where, crash):
    if crash == where:
        os.kill(os.getpid(), signal.SIGKILL)


def llm_decide(case, facts):
    """Ask the model for the refund. Returns {"amount": cents or None, "reason": text}."""
    key = os.environ.get("ANTHROPIC_API_KEY") or re.search(
        r'^ANTHROPIC_API_KEY\s*=\s*["\']?([^"\'\s]+)', open("/Users/kiromoussa/CADAI/.env").read(), re.M).group(1)
    tools = [{"name": "issue_refund", "description": "Refund part of the payment.",
              "input_schema": {"type": "object", "properties": {"amount_cents": {"type": "integer"}, "reason": {"type": "string"}},
                               "required": ["amount_cents", "reason"]}},
             {"name": "decline_refund", "description": "Issue no refund.",
              "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}]
    payment = {"payment_intent": case["payment_intent"], "amount_cents": sd.PAID, **facts, "open_inquiry": case["dispute"]}
    body = {"model": MODEL, "max_tokens": 300, "tools": tools, "tool_choice": {"type": "any"},
            "messages": [{"role": "user", "content": f"{CASE_TEXT}\n\nget_payment returned: {json.dumps(payment)}\n\nAct on the case."}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        call = next(b for b in json.loads(r.read())["content"] if b["type"] == "tool_use")
    return {"amount": call["input"].get("amount_cents") if call["name"] == "issue_refund" else None,
            "reason": call["input"]["reason"]}


def decision(c, case, state, decide):
    """The saved decision, or a new one from the model, validated against the approval before anything uses it."""
    path = os.path.join(state, "decision.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    snapshot = sd.facts(c, case)
    d = {**decide(case, snapshot), "model": MODEL, "facts": snapshot, "decided_at": time.time()}
    d["valid"] = d["amount"] == approval(state)["max_cents"]
    with open(path, "w") as f:
        json.dump(d, f)
    return d


def approval(state):
    with open(os.path.join(state, "approval.json")) as f:
        return json.load(f)


def approved(state, amount):
    a = approval(state)
    return a["revoked"] is None and amount <= a["max_cents"]


def hand_check_decision(snapshot, now, existing, allowed):
    """None means send. existing: refunds already carrying this case's metadata."""
    if existing:
        return "FOUND_BY_LOOKUP"
    if not allowed:
        return "REFUSED:approval"
    if now["chargebacks"] != snapshot["chargebacks"]:
        return "REFUSED:charged_back"
    if now["refunded_by_others"] != snapshot["refunded_by_others"]:
        return "REFUSED:refunds_changed"
    return None


def log(state, **line):
    """hand_check's record: one JSON line per step, appended and flushed before the next step runs."""
    with open(os.path.join(state, "hand_check.log"), "a") as f:
        f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), **line}) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _send(c, case, amount, crash, key, effect_id=None):
    crash_point("before", crash)
    r = sd.send_refund(c, case, amount, key, effect_id)
    crash_point("after", crash)
    return r


def _sent(r):
    return {"status": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund": r["id"]}


def no_check(c, case, state, crash, decide=llm_decide):
    d = decision(c, case, state, decide)
    if not d["valid"]:
        return {"status": "MODEL_DEVIATED", "decision": d}
    return _sent(_send(c, case, d["amount"], crash, f"refund:{case['id']}"))


def hand_check(c, case, state, crash, decide=llm_decide):
    d = decision(c, case, state, decide)
    if not d["valid"]:
        return {"status": "MODEL_DEVIATED", "decision": d}
    existing = [r for r in sd.refunds(c, case) if r["metadata"].get("case") == case["id"]]   # any status: Stripe fails a refund when a chargeback posts
    now, grant = sd.facts(c, case), approval(state)
    refused = hand_check_decision(d["facts"], now, existing, approved(state, d["amount"]))
    log(state, step="checks", case=case["id"], amount=d["amount"], decided_by=d.get("model"), approved_by=grant.get("by"),
        approval=grant, lookup=[r["id"] for r in existing], decided_on=d["facts"], now=now, result=refused or "send")
    if refused:
        return {"status": refused, "refund": existing[0]["id"] if existing else None, "checked": now}
    out = _sent(_send(c, case, d["amount"], crash, f"refund:{case['id']}"))
    log(state, step="sent", case=case["id"], **out)
    return out


def interlock_refund(c, state, crash=None):
    gate = Interlock(os.path.join(state, "interlock"), claim_ttl=CLAIM_TTL)

    @gate.effect(key=lambda case, amount: f"refund:{case['id']}",
                 premises=lambda case, amount, idempotency_key: sd.facts(c, case, idempotency_key),
                 lookup=lambda case, amount, idempotency_key: lookup_id(c, case, idempotency_key),
                 dedupes=True, allowed=lambda case, amount: approved(state, amount))
    def refund(case, amount, idempotency_key):
        return _send(c, case, amount, crash, idempotency_key, idempotency_key)["id"]

    # interlock.easy reduces a lookup to bool, so the receipt would say evidence: true. Record the refund id instead.
    refund.gate.target.query = lambda eid, effect: lookup_id(c, effect["args"][0], eid)
    return refund


def interlock(c, case, state, crash, decide=llm_decide, wait=CLAIM_TTL + 20):
    d = decision(c, case, state, decide)
    if not d["valid"]:
        return {"status": "MODEL_DEVIATED", "decision": d}
    refund = interlock_refund(c, state, crash)
    deadline = time.time() + wait
    while True:
        recovered = refund.gate.recover()                                  # a dead sender's claim blocks until it expires
        status = next(iter(recovered.values()), None) or refund(case, d["amount"])[0]
        if status != "IN_FLIGHT" or time.time() > deadline:
            break
        time.sleep(2)
    bundle = refund.gate.receipt_bundle(refund.proposal(case, d["amount"]))
    with open(os.path.join(state, "receipt.json"), "w") as f:
        json.dump(bundle, f)
    return {"status": status, "refund": lookup_id(c, case, bundle["effect_id"]), "receipt": verify(bundle),
            "journal": [e["kind"] for e in bundle["entries"]]}


def lookup_id(c, case, eid):
    """The refund this effect created, in any status: a refund Stripe failed after a chargeback was still sent."""
    return next((r["id"] for r in sd.refunds(c, case) if r["metadata"].get("interlock_effect_id") == eid), None)


SYSTEMS = {"no_check": no_check, "hand_check": hand_check, "interlock": interlock}


def main(argv):
    system, case, state = argv[0], json.loads(argv[1]), argv[2]
    crash = argv[3] if len(argv) > 3 else None
    try:
        out = SYSTEMS[system](sd.client(), case, state, crash)
    except sd.StripeError as e:
        out = {"status": "STRIPE_ERROR", "error": str(e)}
    path = os.path.join(state, "decision.json")                # saved by the first run; never re-asked
    if os.path.exists(path):
        with open(path) as f:
            out["decision"] = json.load(f)
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
