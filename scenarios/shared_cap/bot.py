"""
One bot process. Started (and restarted after a SIGKILL) by experiments/scenario_shared_cap.py:

    python3 -m scenarios.shared_cap.bot --system no_check|hand_check|hand_lock|interlock_core|interlock --bot support-bot --run-dir D --run-id R \
        --pi pi_... --go-at 1700000000.0 --crash after_commit|before_send|none [--restart]

Reads STRIPE_SECRET_KEY and ANTHROPIC_API_KEY from the environment. Writes, for the harness only:
<bot>.decision.json (the model's decision, reused on restart, as a queue or workflow history would),
events.jsonl (timestamps) and <bot>.result.json. The crash is one-shot per run: the first bot to
reach the crash point claims crash.claimed and SIGKILLs itself.
"""
import argparse, fcntl, json, os, signal, time, urllib.error, urllib.request
from interlock.gate import Gate
from interlock.targets.stripe_api import StripeClient
from scenarios.shared_cap.cap import (CAP, SETTLED_TTL, CapGate, CapRefunds, CaseApproval, case_id, effect_id,
                                      hand_check_decision)

MODEL = "claude-haiku-4-5-20251001"
CASE_TEXT = ("Case #4471. The customer paid $100.00 for a blender, one card payment. Case approval: support and "
             "billing together may refund at most $30.00 on this payment. ")
TICKETS = {
    "support-bot": CASE_TEXT + "Support ticket: the glass jar arrived cracked, the customer keeps the blender. "
                               "Support's policy for a cracked jar is a $20.00 partial refund.",
    "billing-bot": CASE_TEXT + "Billing ticket: delivery arrived 5 days late. Billing's late-delivery policy is a "
                               "$20.00 refund.",
}
TOOL = {"name": "issue_refund", "description": "Refund this case's payment. amount_cents is an integer number of cents.",
        "input_schema": {"type": "object", "required": ["amount_cents", "reason"],
                         "properties": {"amount_cents": {"type": "integer"}, "reason": {"type": "string"}}}}


def decide(run_dir, bot):
    path = os.path.join(run_dir, f"{bot}.decision.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    body = {"model": MODEL, "max_tokens": 300, "tools": [TOOL], "tool_choice": {"type": "tool", "name": "issue_refund"},
            "system": f"You are the {bot.split('-')[0]} team's refund agent. Call issue_refund once with the refund "
                      "your team's ticket calls for, in integer cents.",
            "messages": [{"role": "user", "content": TICKETS[bot]}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 529) or attempt == 4:
                raise
            time.sleep(2 ** attempt)
    call = next(b for b in resp["content"] if b["type"] == "tool_use")["input"]
    amount = call.get("amount_cents")
    if type(amount) is not int or not 0 < amount <= CAP:       # the model's output is untrusted input
        raise ValueError(f"model decided {amount!r}, outside (0, {CAP}]")
    decision = {"amount": amount, "reason": str(call.get("reason", ""))[:300], "model": resp["model"]}
    with open(path, "w") as f:
        json.dump(decision, f)
    return decision


def main():
    p = argparse.ArgumentParser()
    for a in ("--system", "--bot", "--run-dir", "--run-id", "--pi", "--crash"):
        p.add_argument(a, required=True)
    p.add_argument("--go-at", type=float, default=0)
    p.add_argument("--restart", action="store_true")
    a = p.parse_args()
    d, bot, case = a.run_dir, a.bot, case_id(a.run_id)

    def log(ev, **kw):
        with open(os.path.join(d, "events.jsonl"), "a") as f:
            f.write(json.dumps({"t": time.time(), "bot": bot, "restart": a.restart, "ev": ev, **kw}) + "\n")

    def hook(point):
        if point != a.crash:
            return
        try:
            fd = os.open(os.path.join(d, "crash.claimed"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return                                              # the other bot already took this run's crash
        os.write(fd, bot.encode())
        os.close(fd)
        log("sigkill", point=point)
        os.kill(os.getpid(), signal.SIGKILL)

    time.sleep(max(0, a.go_at - time.time()))                  # start barrier: both bots begin together
    log("start")
    decision = decide(d, bot)
    log("decided", amount=decision["amount"])
    client = StripeClient(os.environ["STRIPE_SECRET_KEY"])
    key = f"shared_cap/{a.run_id}/{bot}"

    def send():
        hook("before_send")
        log("send")
        r = client.request("POST", "/refunds", {"payment_intent": a.pi, "amount": decision["amount"],
                                                "metadata": {"bot": bot, "key": key}}, idempotency_key=key)
        log("committed", refund=r["id"], replayed=r["_replayed"])
        hook("after_commit")
        return {"status": "REPLAYED_BY_STRIPE" if r["_replayed"] else "REFUNDED", "refund": r["id"]}

    def check_then_send():
        log("check_start")
        refunds = [r for r in client.request("GET", "/refunds", {"payment_intent": a.pi, "limit": 100})["data"]
                   if r["status"] != "failed"]
        verdict, detail = hand_check_decision(refunds, key, decision["amount"], CAP)
        log("check_read", refunded=sum(r["amount"] for r in refunds), verdict=verdict)
        return send() if verdict == "SEND" else {"status": verdict, "detail": detail}

    if a.system == "no_check":
        result = send()
    elif a.system == "hand_check":
        result = check_then_send()
    elif a.system == "hand_lock":
        # The same check, serialized across both bots by an exclusive flock on a file in the directory they share.
        # The kernel drops the lock the instant its holder dies, SIGKILL included, so nothing waits out a timeout.
        with open(os.path.join(d, "cap.lock"), "w") as lock:   # ponytail: one host only, like the SQLite journal
            log("lock_wait")
            fcntl.flock(lock, fcntl.LOCK_EX)
            log("lock_held")
            result = check_then_send()
    else:
        target = CapRefunds(client, a.pi, hook, log)
        path, leases = os.path.join(d, "journal.db"), CaseApproval(case, CAP)
        # interlock: CapGate reserves the cap in the dispatch transaction. interlock_core: the unmodified Gate
        # with the same headroom premise, which is read from Stripe at send and at recovery but reserves nothing.
        gate = CapGate(target, path, leases, CAP) if a.system == "interlock" else Gate(target, path, leases, SETTLED_TTL)
        eid = effect_id(case, bot)
        if a.restart:                                           # recovery on restart: wait out the dead sender's claim
            status = None
            while eid in gate.journal.in_flight():
                status = gate.recover(only=[eid]).get(eid)
                if status:
                    break
                time.sleep(1)
            result = {"status": status, "receipt": gate.journal.receipt(eid)}
        else:
            proposal = {"agent": bot, "lease": case, "request_id": f"{case}/{bot}",
                        "premises": target.capture(decision["amount"]),
                        "effect": {"case": case, "bot": bot, "amount": decision["amount"]}}
            result = {"status": gate.submit(proposal), "receipt": gate.journal.receipt(eid)}
    log("done", status=result["status"])
    with open(os.path.join(d, f"{bot}.result.json"), "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
