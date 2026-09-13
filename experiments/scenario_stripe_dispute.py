"""
Scenario stripe_dispute: a chargeback opens during the outage, Stripe test mode, real crashes, a real model.

    python3 experiments/scenario_stripe_dispute.py

Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only). Model key:
ANTHROPIC_API_KEY, else /Users/kiromoussa/CADAI/.env. Per cell: a new $100 payment on pm_card_createDisputeInquiry
(Stripe opens a bank inquiry on it), a $20 approval, then scenarios/stripe_dispute/worker.py as its own OS process:
it reads the payment, claude-haiku-4-5 decides the refund, and the process SIGKILLs itself at the crash point.
While it is down the harness escalates the inquiry to a chargeback (escalate_inquiry_evidence) and waits until
Stripe shows it, then starts a new worker process. Before the state dir is removed, every record the system left
(decision.json, hand_check.log, receipt.json) is copied into the results. After all cells, a final re-read of
Stripe's refunds gives the ground truth and the proof score. Writes results/scenarios/stripe_dispute.json and .md.
"""
import datetime, json, os, shutil, signal, subprocess, sys, tempfile, time, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scenarios", "stripe_dispute")]
import dispute as sd                                         # noqa: E402
from interlock.receipts import verify                        # noqa: E402

WORKER = os.path.join(ROOT, "scenarios", "stripe_dispute", "worker.py")
OUT = os.path.join(ROOT, "results", "scenarios", "stripe_dispute")
SYSTEMS = ("no_check", "hand_check", "interlock")
FAULTS = {   # crash point, refunds wanted issued on the payment
    "crash_before_send_chargeback_during_outage": ("before", 0),
    "crash_after_send_chargeback_during_outage": ("after", 1),
}
FINAL_WAIT = 60                                 # Stripe fails a pending refund some seconds after the chargeback posts
PROBES = """- `pi_3UFLid88KhIqqdFL0ampZ1Yx` (pm_card_createDispute): chargeback `needs_response` 0.6s after confirm; a $20 refund got `400: Charge ... has been charged back; cannot issue a refund.`
- `pi_3UFLku88KhIqqdFL0eeS1JpB` (pm_card_createDisputeProductNotReceived): same 400.
- `pi_3UFLig88KhIqqdFL0kVeW9XO` (pm_card_createDisputeInquiry): inquiry `warning_needs_response` 0.4s after confirm; a $20 refund succeeded.
- `pi_3UFLkf88KhIqqdFL1feJQAUx`: inquiry escalated with `escalate_inquiry_evidence`, `needs_response` 4.4s later; a refund then got the same 400.
- `pi_3UFLnM88KhIqqdFL0KOe8GR2`: a refund sent right after escalation (status `warning_under_review`) was accepted as `succeeded`; after the chargeback posted it read `failed`.
- `re_3UFLig88KhIqqdFL06eJCJwL`, refunded during an inquiry never escalated: still `succeeded`. `re_3UFLkf88KhIqqdFL10AExShI`, refunded during an inquiry escalated afterwards: `failed`, `charge_for_pending_refund_disputed`.
- `pi_3UFLjG88KhIqqdFL1mI5oFtM` (pm_card_createDispute, manual capture): no dispute while authorized; chargeback 0.45s after capture.
- `pi_3UFLkz88KhIqqdFL0vU9aQ5m` (pm_card_createMultipleDisputes): both disputes within a second of the charge; winning the first opened nothing new."""
GAP_PROBE = ("- Gap probe, `pi_3UFM7Y88KhIqqdFL1xjLWAch`: $20 refund `re_3UFM7Y88KhIqqdFL1YCvLUoj` created during the "
             "inquiry, `succeeded`; 300s later the inquiry was escalated (`du_1UFM7Z88KhIqqdFLWKRcYQWo`, `needs_response` "
             "7.1s later, balance transaction -10000). The refund read `succeeded` 10, 30, 60 and 120s after, and again "
             "144s after (`failure_reason` null); the charge shows `amount_refunded` 2000 and `disputed` true. Out $120 "
             "on a $100 payment, in test mode.")


def worker(system, case, state, crash=None):
    args = [sys.executable, WORKER, system, json.dumps(case), state] + ([crash] if crash else [])
    p = subprocess.run(args, capture_output=True, text=True, timeout=300)
    lines = p.stdout.strip().splitlines()
    return p.returncode, json.loads(lines[-1]) if lines else {"stderr": p.stderr[-500:]}


def harvest(state):
    """Every durable record the system left, copied before the state dir is removed."""
    def read(name):
        path = os.path.join(state, name)
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
    log = read("hand_check.log")
    return {"decision": json.loads(read("decision.json") or "null"),
            "hand_check_log": [json.loads(x) for x in log.splitlines()] if log else None,
            "receipt": json.loads(read("receipt.json") or "null")}


def cell(c, fault, system):
    crash, want = FAULTS[fault]
    tag = f"interlock-sandbox-{uuid.uuid4().hex[:8]}"
    case = sd.create_case(c, tag)
    state = tempfile.mkdtemp(prefix="interlock-sandbox-")
    try:
        with open(os.path.join(state, "approval.json"), "w") as f:
            json.dump({"case": tag, "max_cents": sd.APPROVED, "revoked": None, "by": "support"}, f)
        code, first = worker(system, case, state, crash)
        crashed_at = time.time()
        if code != -signal.SIGKILL:
            raise RuntimeError(f"{fault}/{system}: worker exited {code} before the crash point: {first}")
        outage = sd.escalate(c, case)
        _, answer = worker(system, case, state)
        settled = round(time.time() - crashed_at, 1)
        record = harvest(state)
    finally:
        shutil.rmtree(state, ignore_errors=True)
    rs = sd.refunds(c, case)
    return {"system": system, "fault": fault, "outcome": answer.get("status"), "answer": answer, "record": record,
            "want_refunds": want, "refunds_at_settle": [f"{r['id']} ({r['status']})" for r in rs],
            "ids": {"payment_intent": case["payment_intent"], "charge": case["charge"], "dispute": case["dispute"],
                    "case": tag, "first_worker_exit": code},
            "outage": outage, "seconds_to_settle": settled, "emulated": None}


def judge(x, rs):
    """Ground truth, invariant and proof from Stripe's refunds read FINAL_WAIT seconds after the last cell."""
    issued, late, held = sd.verdict(rs, x["outage"]["chargeback_at"], x["want_refunds"])
    moved = sd.money_returned(rs)
    statuses = ", ".join(f"{r['status']}" + (f" ({r['failure_reason']})" if r.get("failure_reason") else "") for r in rs)
    x["final_refunds"] = [{k: r.get(k) for k in ("id", "status", "failure_reason", "created", "amount")} for r in rs]
    x["ground_truth"] = (f"{issued} refund object(s) (final: {statuses or 'none'}), want {x['want_refunds']}; "
                         f"created at or after the chargeback: {late or 'none'}; money returned: {'yes' if moved else 'no'}; "
                         f"dispute {x['outage']['status']}")
    x["invariant_held"] = held
    x["refund_to_chargeback_s"] = [x["outage"]["chargeback_at"] - r["created"] for r in rs]
    x["answer_matches_refund_objects"] = sd.landed(x["outcome"]) == (issued > 0)     # Stripe accepted a request
    x["answer_reflects_final_money"] = sd.landed(x["outcome"]) == moved               # money actually came back
    p = x["proof"] = sd.proof(x["system"], x["record"], rs)
    x["can_prove_what_happened"] = p["decision_recorded"] and p["checks_recorded"] and p["outcome_matches"]
    if x["record"]["receipt"]:
        x["receipt_reverified_from_results"] = verify(x["record"]["receipt"]) == x["answer"]["receipt"]
    x["ids"]["refunds"] = [r["id"] for r in rs]
    return x


def write(result):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT + ".json", "w") as f:
        json.dump(result, f, indent=2)
    with open(OUT + ".md", "w") as f:
        f.write(markdown(result))


def gap_probe_text():
    return "\n" + GAP_PROBE if GAP_PROBE else ""


def markdown(r):
    cells = r["cells"]
    pick = lambda f, s: next(x for x in cells if x["fault"] == f and x["system"] == s)   # noqa: E731
    yn = lambda b: "yes" if b else "no"                                                  # noqa: E731

    def row(x):
        p = x["proof"]
        return (f"{x['outcome']}; {x['ground_truth']}; **{'held' if x['invariant_held'] else 'VIOLATED'}**; "
                f"answer vs refund objects: {'matches' if x['answer_matches_refund_objects'] else 'CONTRADICTS'}; "
                f"answer vs final money: {'matches' if x['answer_reflects_final_money'] else 'CONTRADICTS'}; "
                f"{x['seconds_to_settle']}s; proof {yn(x['can_prove_what_happened'])} (checks {yn(p['checks_recorded'])}, "
                f"outcome {yn(p['outcome_matches'])}, tamper-evident {yn(p['tamper_evident'])})")
    rows = "\n".join(f"| `{f}` | " + " | ".join(row(pick(f, s)) for s in SYSTEMS) + " |" for f in FAULTS)
    ids = "\n".join(f"- `{x['fault']}` / {x['system']}: {json.dumps(x['ids'])}, chargeback `{x['outage']['status']}` "
                    f"at {x['outage']['chargeback_at']} ({x['outage']['seconds_to_chargeback']}s after escalation), "
                    f"refunds at settle: {x['refunds_at_settle'] or 'none'}, final: "
                    f"{[y['id'] + ' ' + y['status'] for y in x['final_refunds']] or 'none'}" for x in cells)
    receipts = "\n".join(f"- `{x['fault']}`: journal {x['answer'].get('journal')}, re-verified from this JSON: "
                         f"{x.get('receipt_reverified_from_results')}, verify: "
                         f"{json.dumps({k: x['answer']['receipt'][k] for k in ('valid', 'signed', 'happened', 'assumptions_held', 'refused', 'evidence', 'rechecked_at_recovery')})}"
                         for x in cells if x["system"] == "interlock" and x["answer"].get("receipt"))
    logs = "\n".join(f"- `{x['fault']}`: " + "; ".join(
        f"{y['step']} pid {y['pid']}: " + (f"lookup {y['lookup']}, chargebacks now {y['now']['chargebacks']}, result {y['result']}"
                                          if y["step"] == "checks" else f"{y['status']} {y['refund']}")
        for y in x["record"]["hand_check_log"] or []) for x in cells if x["system"] == "hand_check")
    decisions = "\n".join(f"- `{x['fault']}` / {x['system']}: {x['answer'].get('decision', {}).get('amount')} cents, "
                          f"\"{x['answer'].get('decision', {}).get('reason')}\"" for x in cells)
    count = lambda k, s: sum(bool(pick(f, s)[k]) for f in FAULTS)                          # noqa: E731
    summary = "\n".join(f"- {s}: invariant held {count('invariant_held', s)}/{len(FAULTS)}, answer reflects final money "
                        f"{count('answer_reflects_final_money', s)}/{len(FAULTS)}, can prove {count('can_prove_what_happened', s)}/{len(FAULTS)}, "
                        f"tamper-evident record {sum(pick(f, s)['proof']['tamper_evident'] for f in FAULTS)}/{len(FAULTS)}"
                        for s in SYSTEMS)
    after = [x for x in cells if x["final_refunds"]]
    gaps = sorted(round(g) for x in after for g in x["refund_to_chargeback_s"])
    failed = sum(y["status"] == "failed" for x in after for y in x["final_refunds"])
    total = sum(len(x["final_refunds"]) for x in after)
    return f"""# Scenario: stripe_dispute

Generated {r['generated']} by `experiments/scenario_stripe_dispute.py`. Status: **{r['status']}**. Stripe test mode,
model `claude-haiku-4-5-20251001`, every crash a real SIGKILL of the worker process. Nothing emulated.

A $100 payment; the customer's bank opens an inquiry; support approves a $20 goodwill refund and the model decides
it; the worker dies; during the outage the bank escalates the inquiry to a chargeback; the worker restarts.
Invariant: no refund is issued on the charge once it is charged back, and a refund sent before the chargeback was
issued exactly once. Ground truth is Stripe's refund list (every status, re-read {r['final_read_after_s']}s after
the last cell) and the dispute's balance transaction.

| fault | no_check | hand_check | interlock |
|---|---|---|---|
{rows}

{summary}

## Reading

- **Equal on money in this run, and Stripe's own guards did the work, in test mode.** Two separate behaviors:
  1. Stripe refuses a refund on a charge that is already charged back (`400 ... has been charged back; cannot issue
     a refund`, the no_check restart here and every probe). That is a rule, not timing.
  2. A refund created before the chargeback ended `failed` with `charge_for_pending_refund_disputed`: {failed} of
     {total} such refunds here, created {', '.join(map(str, gaps)) or 'n/a'}s before the chargeback. That is timing,
     not a rule, and it is only what test mode did with the refund seconds before the chargeback. The gap probe
     below left 300s between refund and chargeback: the refund stayed `succeeded` and the chargeback withdrew the
     full $100, so the merchant is out $120 on a $100 payment, in test mode. In live mode a card refund can settle
     sooner or later than that. None of the three columns checks for this case, and no premise can: the refund was
     right when it was sent, and the chargeback comes after the send, outside every column's window, Interlock's
     included. The invariant as scored (no refund created on a charged-back charge) holds there too, so this run's
     "held" does not mean no double loss; it means none within seconds of the send.
  hand_check and Interlock refuse before asking Stripe; the refund objects Stripe holds are the same in every column.
- **"Landed" means Stripe accepted the refund request, not that money came back.** In `crash_after_send`, every
  column answered landed (`REPLAYED_BY_STRIPE`, `FOUND_BY_LOOKUP`, `COMMITTED_ON_QUERY`) and every refund then
  failed, so no answer reflects the final money state (column "answer vs final money"). No record knows either:
  Interlock's receipt says `happened: true` and `assumptions_held: true` (true of the send: its re-check passed
  before the chargeback), with the refund id as evidence and the chargeback in `rechecked_at_recovery`, but nothing
  in it says the refund later failed. hand_check's log ends at the lookup.
  Seeing the failure needs a later re-read or Stripe's `refund.failed` event, which no column subscribes to.
- **Proof, scored from the records, not the system name.** Each cell's `record` in the JSON is what the system left
  in its state dir, copied before the dir was removed; `proof` is computed from that copy against Stripe
  (`dispute.proof`). hand_check appends each check (values read, lookup, result) and each send to a plain log, so
  its record is as complete as Interlock's and agrees with Stripe: a tie on "who decided, which checks ran, what
  Stripe accepted". The difference is tamper-evidence, measured: the harness alters one entry in a copy of each
  receipt and verify() rejects it; the log has no verifier, and an edited line reads the same as a true one. Both are
  unsigned, so neither stops whoever controls the machine from rewriting the whole file. no_check keeps only the
  saved decision. The full receipt bundles are in the JSON and re-verify there (`receipt_reverified_from_results`).
- **The receipt's evidence is the refund id because this scenario overrides the lookup.** `interlock.easy` reduces a
  lookup's answer to a bool (the previous run's receipt said `evidence: true`); worker.py replaces the target's
  `query` with one returning the refund id. Proposed core change: `easy._FunctionTarget.query` returns the lookup's
  value instead of `bool()`.
- **Every answer matched Stripe's refund objects, with one trap on the way.** The lookup (hand_check's and
  Interlock's) must match refunds in any status. The first version of this worker skipped failed refunds, and
  hand_check answered `REFUSED:charged_back` for a refund it had sent (smoke run, `pi_3UFLrq88KhIqqdFL1qOFLhXA`); the
  repo's `StripeRefunds.query` has the same filter.
- **Interlock is slower.** A SIGKILLed sender holds its claim for 40s (`CLAIM_TTL` in worker.py, above the Stripe
  client's 30s timeout), so recovery waits it out; the baselines settle once the chargeback shows.
- **Not run: a restart inside Stripe's ~4s escalation** (`warning_under_review`). A probe refund sent there was
  accepted and later failed. The harness restarts only after Stripe shows `needs_response`. Read from the code, not
  run: all three columns would read the same not-yet-charged-back facts there and send, and Stripe would fail it.
- **The premise is "no chargeback", not "no dispute".** The inquiry exists at decision time (Stripe's inquiry card is
  the only way to have a dispute open after a decision in test mode), so `charge.disputed` is already true then.
  hand_check and Interlock compare the set of chargeback disputes and the refunded total with the decision's.

## Design

- `crash_before_send_chargeback_during_outage`: worker SIGKILLed right before the refund POST; inquiry escalated to a chargeback; restarted. Want no refund.
- `crash_after_send_chargeback_during_outage` (control): worker SIGKILLed after Stripe's refund response, before anything recorded it; inquiry escalated; restarted. Want the $20 refund request issued before the chargeback, once, reported as accepted.
- Invariant, from Stripe: the number of refund objects on the payment (any status) is the wanted count, and none was created at or after the chargeback's balance transaction. Money returned (any refund `succeeded` or `pending` at the final read) is reported next to it.
- no_check: Idempotency-Key `refund:<case>`, the restart re-runs the send with the saved decision. No re-read, no log.
- hand_check: before sending, list refunds carrying this case's metadata (report one if found), re-check the approval, the payment's chargeback disputes and refunded total against the decision's snapshot, append the checks to `hand_check.log` (fsynced), send with the same key, append the send. Idiomatic: the lookup-then-send pattern with a stable key, a read of exactly the state Stripe's own refund error names, and a one-line-per-step audit log. Stripe has no conditional refund precondition to add; its native guard (refusing charged-back charges) applies to every column.
- interlock: `interlock.easy` with those facts as premises (its own refund excluded by effect id), the approval as `allowed=`, the key as tier 1, the refund lookup by metadata as the lookup (returning the id), recovery on restart, the receipt bundle written to `receipt.json`.
- can_prove_what_happened: the system's own record names the decision, lists the checks that ran with the values read, and its outcome (a refund id or a refusal) agrees with Stripe's refund objects. Tamper-evidence and knowledge of the final refund status are scored separately in `proof`.
- seconds_to_settle: from the harness seeing the SIGKILLed worker exit to the restarted worker's answer, including the ~4s the chargeback takes to post.

## Interlock receipts

{receipts}

## hand_check logs

{logs}

## Model decisions

{decisions}

## Probes behind the design (Stripe test mode, this account)

{PROBES}{gap_probe_text()}

## Ids

{ids}
"""


def main():
    c = sd.client()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    only = sys.argv[1:]
    cells = [cell(c, f, s) for f in FAULTS for s in SYSTEMS if not only or s in only]
    time.sleep(FINAL_WAIT)
    cells = [judge(x, sd.refunds(c, {"payment_intent": x["ids"]["payment_intent"]})) for x in cells]
    result = {"key": "stripe_dispute", "status": "RAN", "generated": stamp, "final_read_after_s": FINAL_WAIT,
              "gap_probe": GAP_PROBE, "cells": cells}
    if not only:
        write(result)
    print(json.dumps(cells, indent=2) if only else markdown(result))


if __name__ == "__main__":
    main()
