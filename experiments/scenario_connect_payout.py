"""
Scenario connect_payout: a marketplace pays a seller $20 through Stripe Connect, test mode, with real crashes.

    python3 experiments/scenario_connect_payout.py

Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only).
Per cell: a new Custom connected account (the seller), a $100 buyer payment in the order's transfer_group, then
scenarios/connect_payout/worker.py as its own OS process, which SIGKILLs itself at the crash point. While it is
down the harness changes the world (refunds the order, or rejects the seller), starts a new worker process, and
reads ground truth back from Stripe's transfer list for that order and seller. If the platform has no Connect,
the first account create fails and the run is recorded BLOCKED with Stripe's exact error.
Writes results/scenarios/connect_payout.json and .md.
"""
import datetime, json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scenarios", "connect_payout"))
import stripe_connect as sc                                  # noqa: E402

WORKER = os.path.join(ROOT, "scenarios", "connect_payout", "worker.py")
OUT = os.path.join(ROOT, "results", "scenarios", "connect_payout")
SYSTEMS = ("no_check", "hand_check", "interlock")
FAULTS = {   # crash point, what happens during the outage, wanted (cents kept by the seller, transfers)
    "crash_after_commit": ("after", None, (sc.PAYOUT, 1)),
    "crash_before_send_order_reversed": ("before", sc.reverse_order, (0, 0)),
    "crash_before_send_seller_restricted": ("before", sc.restrict_seller, (0, 0)),
}


def worker(system, order, state, crash=None):
    args = [sys.executable, WORKER, system, json.dumps(order), state] + ([crash] if crash else [])
    p = subprocess.run(args, capture_output=True, text=True, timeout=300)
    lines = p.stdout.strip().splitlines()
    return p.returncode, json.loads(lines[-1]) if lines else {"stderr": p.stderr[-500:]}


def cell(c, fault, system):
    crash, during, want = FAULTS[fault]
    tag = f"interlock-sandbox-{uuid.uuid4().hex[:8]}"
    order = sc.create_order(c, sc.create_seller(c, tag), tag)
    state = tempfile.mkdtemp(prefix="interlock-sandbox-")
    try:
        code, _ = worker(system, order, state, crash)
        crashed_at = time.time()
        outage = during(c, order) if during else None
        _, answer = worker(system, order, state)
        settled = round(time.time() - crashed_at, 1)
    finally:
        shutil.rmtree(state, ignore_errors=True)
    ts = sc.transfers(c, order)
    kept = sc.paid_out(ts)
    receipt = answer.get("receipt") or {}
    return {"system": system, "fault": fault, "outcome": answer.get("status"), "answer": answer,
            "ground_truth": f"${kept[0] / 100:.2f} kept by seller in {kept[1]} transfer(s); want ${want[0] / 100:.2f} in {want[1]}",
            "invariant_held": kept == want, "can_prove_what_happened": system == "interlock" and receipt.get("valid") is True,
            "ids": {"seller": order["seller"], "payment_intent": order["payment_intent"], "charge": order["charge"],
                    "transfers": [t["id"] for t in ts], "outage_action": outage, "first_worker_exit": code},
            "seconds_to_settle": settled, "emulated": None}


def write(result):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT + ".json", "w") as f:
        json.dump(result, f, indent=2)
    with open(OUT + ".md", "w") as f:
        f.write(markdown(result))


def markdown(r):
    head = f"# Scenario: connect_payout\n\nGenerated {r['generated']} by `experiments/scenario_connect_payout.py`. Status: **{r['status']}**.\n\n"
    if r["status"] == "BLOCKED":
        probe = "\n".join(f"- `{k}`: {v}" for k, v in r["probe"].items())
        return head + f"""Stripe Connect is not enabled on the test platform `{r['platform']}`, so no connected account can be
created and no cell ran. Exact error from the first step of the run:

    {r['error']}

Every route to a seller account was tried before recording this (see `probe` in the json):

{probe}

Nothing was compared, so this scenario says nothing about no_check, hand_check or Interlock. To run it, enable
Connect for the test account at https://dashboard.stripe.com/connect and re-run `python3 experiments/scenario_connect_payout.py`.
The live cell path (account setup, the transfer, SIGKILL, ground truth) has not run against Stripe yet; only its
logic is tested offline, against an in-memory Stripe, in `tests/test_scenario_connect_payout.py`. Those tests
expect: all three land $20 once after `crash_after_commit`; with the order reversed during the outage, no_check
pays the seller $20 and hand_check and Interlock both refuse, a tie on money with Interlock adding a receipt.
They are a prediction, not a result.

## What the run does once Connect is on

{DESIGN}
"""
    rows = "\n".join(f"| `{f}` | " + " | ".join(
        (lambda x: f"{x['outcome']}; {x['ground_truth']}; **{'held' if x['invariant_held'] else 'VIOLATED'}**; "
                   f"{x['seconds_to_settle']}s; proof {'yes' if x['can_prove_what_happened'] else 'no'}")(
            next(x for x in r["cells"] if x["fault"] == f and x["system"] == s)) for s in SYSTEMS) + " |"
        for f in FAULTS)
    ids = "\n".join(f"- `{x['fault']}` / {x['system']}: {json.dumps(x['ids'])}" for x in r["cells"])
    return head + f"| fault | no_check | hand_check | interlock |\n|---|---|---|---|\n{rows}\n\n{DESIGN}\n\n## Ids\n\n{ids}\n"


DESIGN = """- `crash_after_commit`: worker SIGKILLed after Stripe's response to the transfer POST, before anything recorded it; restarted. Want $20 in 1 transfer.
- `crash_before_send_order_reversed`: worker SIGKILLed right before the transfer POST; the buyer's payment is refunded in full; restarted. Want $0.
- `crash_before_send_seller_restricted`: worker SIGKILLed right before the transfer POST; the platform rejects the seller account (transfers capability inactive); restarted. Want $0. Stripe itself may refuse this transfer, which would make all three columns hold.
- no_check: stable Idempotency-Key `payout:<order>`, retry on restart, no re-read.
- hand_check: before sending, list transfers in the order's transfer_group (report one if found), re-read the charge (refunded?) and the seller's transfers capability, plus the same key and source_transaction. Idiomatic: these are the reads Stripe's separate-charges-and-transfers docs point to. It keeps no durable record of which checks ran.
- interlock: `interlock.easy` with those same facts as premises, the key as tier 1, the transfer_group lookup by effect id, recovery on restart (waits out the dead sender's 40s claim), and a verified hash-chained receipt.
- can_prove_what_happened is true only when a durable record says who decided, which checks ran and what landed: Interlock's receipt (verify() valid). The baselines leave Stripe's objects and nothing about the checks."""


def main():
    c = sc.client()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    platform = c.request("GET", "/account")["id"]
    try:
        sc.create_seller(c, "interlock-sandbox-preflight")
    except sc.StripeError as e:
        if sc.NOT_ENABLED not in str(e):
            raise
        probe = {}
        for kind in ("express", "standard", "custom"):
            try:
                c.request("POST", "/accounts", {"type": kind, "country": "US"})
                probe[f"POST /v1/accounts type={kind}"] = "created (unexpected)"
            except sc.StripeError as pe:
                probe[f"POST /v1/accounts type={kind}"] = str(pe)
        try:
            v2 = urllib.request.Request("https://api.stripe.com/v2/core/accounts", method="POST", data=json.dumps(
                {"identity": {"country": "us"}, "configuration": {"recipient": {"capabilities": {
                    "stripe_balance": {"stripe_transfers": {"requested": True}}}}}}).encode(),
                headers={"Authorization": c._auth, "Content-Type": "application/json",
                         "Stripe-Version": "2025-09-30.preview"})
            urllib.request.urlopen(v2, timeout=30).close()
            probe["POST /v2/core/accounts recipient"] = "created (unexpected)"
        except urllib.error.HTTPError as pe:
            probe["POST /v2/core/accounts recipient"] = f"{pe.code}: " + json.loads(pe.read() or b"{}").get("error", {}).get("message", "")
        probe["GET /v1/accounts"] =f"{len(c.request('GET', '/accounts', {'limit': 10})['data'])} existing connected accounts"
        result = {"key": "connect_payout", "status": "BLOCKED", "generated": stamp, "platform": platform,
                  "error": str(e), "probe": probe, "cells": []}
        write(result)
        print(json.dumps(result, indent=2))
        return
    cells = [cell(c, f, s) for f in FAULTS for s in SYSTEMS]
    result = {"key": "connect_payout", "status": "RAN", "generated": stamp, "platform": platform, "cells": cells}
    write(result)
    print(markdown(result))


if __name__ == "__main__":
    main()
