"""
The refund agent: a real model over the Anthropic Messages API, called with urllib so the repo
stays dependency-free. It reads live Stripe facts through get_payment and must answer with
issue_refund. It never sends a refund; it returns the decision, validated here.

Reads ANTHROPIC_API_KEY from the environment. INTERLOCK_MODEL picks the model.
"""
import json, os, time, urllib.error, urllib.request

MODEL = os.environ.get("INTERLOCK_MODEL", "claude-haiku-4-5-20251001")
SYSTEM = ("You are a payments support agent. Read the support case, look up the payment with get_payment, "
          "then call issue_refund exactly once for the refund support approved, in integer cents.")
TOOLS = [
    {"name": "get_payment",
     "description": "Live facts for this case's Stripe payment: amount paid, already refunded, and still refundable, in cents.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "issue_refund",
     "description": "Refund this case's payment. amount_cents is an integer number of cents.",
     "input_schema": {"type": "object", "required": ["amount_cents", "reason"],
                      "properties": {"amount_cents": {"type": "integer"}, "reason": {"type": "string"}}}},
]


class AgentError(RuntimeError):
    pass


def payment_facts(client, payment_intent):
    pi = client.request("GET", f"/payment_intents/{payment_intent}")
    refunds = client.request("GET", "/refunds", {"payment_intent": payment_intent, "limit": 100})["data"]
    refunded = sum(r["amount"] for r in refunds if r["status"] != "failed")
    return {"payment_intent": payment_intent, "status": pi["status"], "currency": pi["currency"],
            "paid_cents": pi["amount_received"], "refunded_cents": refunded,
            "refundable_cents": pi["amount_received"] - refunded}


def validate_refund(args, paid_cents, refunded_cents, approved_cents=None):
    """The trust boundary: a model's tool call is untrusted input. It may not exceed what support approved."""
    amount, reason = args.get("amount_cents"), args.get("reason")
    if type(amount) is not int:                 # rejects 20.0, "2000" and True
        raise AgentError(f"amount_cents must be an integer number of cents, got {amount!r}")
    if not 0 < amount <= paid_cents - refunded_cents:
        raise AgentError(f"amount_cents {amount} is outside (0, {paid_cents - refunded_cents}]")
    if approved_cents is not None and amount > approved_cents:
        raise AgentError(f"amount_cents {amount} is more than the {approved_cents} support approved")
    if not isinstance(reason, str) or not reason.strip():
        raise AgentError("reason must be a non-empty string")
    return {"amount_cents": amount, "reason": reason.strip()[:500]}


def _call(body):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AgentError("ANTHROPIC_API_KEY is not set")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 529) or attempt == 3:
                raise AgentError(f"Anthropic API {e.code}: {e.read()[:300]!r}") from None
            time.sleep(2 ** attempt)


def decide(customer_text, client, payment_intent, approved_cents=None, model=MODEL):
    """Run the model until it calls issue_refund. Returns the validated decision and the raw call."""
    messages = [{"role": "user", "content": f"Support case:\n{customer_text}"}]
    for _ in range(4):
        resp = _call({"model": model, "max_tokens": 1024, "system": SYSTEM, "tools": TOOLS,
                      "tool_choice": {"type": "any"}, "messages": messages})
        calls = [b for b in resp["content"] if b["type"] == "tool_use"]
        refund = next((c for c in calls if c["name"] == "issue_refund"), None)
        if refund:
            facts = payment_facts(client, payment_intent)
            return {**validate_refund(refund["input"], facts["paid_cents"], facts["refunded_cents"], approved_cents),
                    "model": resp["model"], "tool_call": {"name": refund["name"], "input": refund["input"]}}
        messages += [{"role": "assistant", "content": resp["content"]},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": c["id"],
                                                   "content": json.dumps(payment_facts(client, payment_intent))}
                                                  for c in calls]}]
    raise AgentError("the model never called issue_refund")
