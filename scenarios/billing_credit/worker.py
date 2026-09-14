"""
The billing-credit agent, as its own OS process per attempt. The harness runs

    python3 scenarios/billing_credit/worker.py decide  <system> <case_dir>     CRASH=before_send|after_send
    python3 scenarios/billing_credit/worker.py restart <system> <case_dir>

and reads one JSON line from stdout. `decide` reads the account, asks the model, and sends; CRASH makes the process
SIGKILL itself at that point in post_credit, so it prints nothing. `restart` is the process that comes back.

Systems, all sending the same balance transaction through the same post_credit:

    no_check    the decision is saved before the send (as a workflow engine records it); restart sends it again
                under the same Idempotency-Key. No re-check.
    hand_check  what a careful engineer writes around the send. Stripe has no precondition on a balance transaction
                (no If-Match, no expected balance), so the native tools are the Idempotency-Key plus a lookup by
                metadata. Before every send: look this case's credit up and stop if it exists; check the approval is
                live and covers the amount; compare the premises with the ones saved at decision time. Each step is
                appended to a log file before and after the send.
    interlock   the same send as a Gate over CreditTarget; restart calls gate.recover().
"""
import json, os, sys, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from interlock.gate import Gate  # noqa: E402
from interlock.journal import effect_id_for  # noqa: E402
from interlock.receipts import bundle, verify  # noqa: E402
from scenarios.billing_credit.billing import (CLAIM_TTL, PLAN, Approval, CreditTarget, client, facts,  # noqa: E402
                                              observations, own_credits, post_credit)

MODEL = os.environ.get("INTERLOCK_MODEL", "claude-haiku-4-5-20251001")
SYSTEM = ("You are a billing support agent. Read the support case, look the account up with get_account, then call "
          "issue_credit exactly once for the credit support approved, in integer cents.")
TOOLS = [{"name": "get_account", "description": "Live Stripe facts for this case's customer and subscription.",
          "input_schema": {"type": "object", "properties": {}}},
         {"name": "issue_credit", "description": "Credit the customer's account balance. amount_cents is a positive integer.",
          "input_schema": {"type": "object", "required": ["amount_cents", "description"],
                           "properties": {"amount_cents": {"type": "integer"}, "description": {"type": "string"}}}}]


def anthropic(body):
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 529) or attempt == 4:
                raise
            time.sleep(2 ** attempt)


def decide_credit(case, account, max_cents):
    """The model decides; its tool call is untrusted input, validated against the approval."""
    messages = [{"role": "user", "content": "Support case:\n" + case["text"]}]
    for _ in range(4):
        resp = anthropic({"model": MODEL, "max_tokens": 1024, "system": SYSTEM, "tools": TOOLS,
                          "tool_choice": {"type": "any"}, "messages": messages})
        calls = [b for b in resp["content"] if b["type"] == "tool_use"]
        credit = next((b["input"] for b in calls if b["name"] == "issue_credit"), None)
        if credit:
            amount, description = credit.get("amount_cents"), credit.get("description")
            if type(amount) is not int or not 0 < amount <= max_cents:
                raise ValueError(f"model credit {amount!r} is outside (0, {max_cents}]")
            if not isinstance(description, str) or not description.strip():
                raise ValueError("model gave no description")
            return {"amount": amount, "description": description.strip()[:300], "model": resp["model"]}
        messages += [{"role": "assistant", "content": resp["content"]},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": b["id"],
                                                   "content": json.dumps(account)} for b in calls]}]
    raise ValueError("the model never called issue_credit")


def hand_checked_send(c, case, approval, decision, log, crash=None):
    key = "goodwill-credit-" + case["case_id"]
    found = own_credits(c, case)
    if found:
        log({"step": "lookup", "found": found[0]["id"]})
        return "FOUND_BY_LOOKUP"
    if approval["revoked"] is not None or decision["amount"] > approval["max_cents"]:
        log({"step": "approval", "refused": approval})
        return "REFUSED:approval"
    now = facts(c, case)
    if now != decision["premises"]:
        log({"step": "premises", "refused": {"was": decision["premises"], "now": now}})
        return "REFUSED:stale_premise"
    log({"step": "send", "key": key, "approval": approval, "premises": now})
    txn = post_credit(c, case, decision["amount"], decision["description"], key, {}, crash)
    log({"step": "sent", "credit": txn["id"], "replayed": txn["_replayed"]})
    return "REPLAYED_BY_STRIPE" if txn["_replayed"] else "CREDITED"


def file_log(path, **who):
    def log(entry):
        with open(path, "a") as f:
            f.write(json.dumps({"ts": time.time(), **who, **entry}) + "\n")
            f.flush()
            os.fsync(f.fileno())
    return log


def request_id(case):
    return "goodwill-credit:" + case["case_id"]


def main(phase, system, case_dir):
    case_path = os.path.join(case_dir, "case.json")
    with open(case_path) as f:
        case = json.load(f)
    c, crash = client(), os.environ.get("CRASH") if phase == "decide" else None
    gate = Gate(CreditTarget(c, case, crash), os.path.join(case_dir, "journal.jsonl"), Approval(case_path),
                claim_ttl=CLAIM_TTL) if system == "interlock" else None
    log = file_log(os.path.join(case_dir, "hand_check.log"), agent="billing-credit-agent", case_id=case["case_id"],
                   phase=phase)
    decision_path = os.path.join(case_dir, "decision.json")

    if phase == "decide":
        premises = facts(c, case)
        account = {"customer": case["customer"], "plan_cents_per_month": PLAN, **premises}
        decision = {**decide_credit(case, account, case["approval"]["max_cents"]), "premises": premises,
                    "observed": observations(c, case)}
        with open(decision_path, "w") as f:
            json.dump(decision, f)
            f.flush()
            os.fsync(f.fileno())
        if system == "interlock":
            status = gate.submit({"agent": "billing-credit-agent", "lease": case["approval"]["id"],
                                  "request_id": request_id(case), "premises": premises,
                                  "effect": {"customer": case["customer"], "amount": decision["amount"],
                                             "description": decision["description"]}})
        elif system == "hand_check":
            status = hand_checked_send(c, case, case["approval"], decision, log, crash)
        else:
            txn = post_credit(c, case, decision["amount"], decision["description"],
                              "goodwill-credit-" + case["case_id"], {}, crash)
            status = "REPLAYED_BY_STRIPE" if txn["_replayed"] else "CREDITED"
        return {"status": status}

    if system == "interlock":
        eid, status, start = effect_id_for({"request_id": request_id(case)}), None, time.time()
        while time.time() - start < 300:
            status = gate.recover().get(eid, status)       # {} while the crashed sender's claim is still live
            if eid not in gate.journal.in_flight():
                break
            time.sleep(1)
        receipt = bundle(gate.journal, eid)
        with open(os.path.join(case_dir, "receipt.json"), "w") as f:
            json.dump(receipt, f, indent=1)
        commit = next((e for e in receipt["entries"] if e["kind"] == "COMMITTED"), {})
        return {"status": status or receipt["summary"]["final"], "effect_id": eid, "via": commit.get("via"),
                "claim_wait_s": round(time.time() - start, 1), "verify": verify(receipt),
                "journal": [e["kind"] for e in receipt["entries"]]}

    with open(decision_path) as f:
        decision = json.load(f)
    with open(case_path) as f:
        approval = json.load(f)["approval"]                 # read fresh: an approval can change during the outage
    if system == "hand_check":
        return {"status": hand_checked_send(c, case, approval, decision, log)}
    txn = post_credit(c, case, decision["amount"], decision["description"], "goodwill-credit-" + case["case_id"], {})
    return {"status": "REPLAYED_BY_STRIPE" if txn["_replayed"] else "CREDITED", "credit": txn["id"]}


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:4])), flush=True)
