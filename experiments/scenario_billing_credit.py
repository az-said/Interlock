"""
Scenario billing_credit: a goodwill credit against a Stripe Billing renewal, with real SIGKILLs. One command:

    ANTHROPIC_API_KEY=$(grep ^ANTHROPIC_API_KEY= /path/to/.env | cut -d= -f2-) python3 experiments/scenario_billing_credit.py

Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only). Each cell: a new
$30/month subscriber on its own Stripe test clock and a support approval for one $10 credit; a worker process reads
the account, a real model (claude-haiku-4-5) decides the credit, and the worker SIGKILLs itself right before or right
after the credit POST; during the outage the harness advances the test clock through the renewal (plus a proration
downgrade, or a billing SLA credit note); a new worker process settles the case; ground truth is re-read from Stripe.
Every cell also records three candidate premises (customer balance, all
compensation by others, compensation for this incident) at decision time, at the crash and at restart, and keeps
Interlock's full receipt bundle so receipts.verify() can be re-run offline on the published JSON.
Writes results/scenarios/billing_credit.json and .md. Pass crash:outage:system arguments to run some cells and print
them only (e.g. before_send:billing_credit:interlock).
"""
import datetime, json, os, shutil, signal, statistics, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.receipts import verify  # noqa: E402
from scenarios.billing_credit.billing import (WANT, client, ensure_prices, ground_truth, judge, observations,  # noqa: E402
                                              open_case, outage)

WORKER = os.path.join(ROOT, "scenarios", "billing_credit", "worker.py")
SYSTEMS = ("no_check", "hand_check", "interlock")
ROWS = [("before_send", "renewal"), ("before_send", "billing_credit"), ("before_send", "proration"),
        ("after_send", "renewal"), ("after_send", "proration"), ("before_send", "unrelated_credit")]
CANDIDATES = ("customer_balance", "compensation_by_others", "incident_compensation")
OUTAGE = {"renewal": "test clock advanced through the renewal: Stripe invoices, applies any customer balance, charges the card",
          "billing_credit": "renewal as above, then billing's SLA automation issues a $10 credit note on the renewal "
                            "invoice for the same incident (credited to the customer balance)",
          "proration": "the customer downgrades $30 -> $20 with proration (credit line for unused time), then the renewal",
          "unrelated_credit": "renewal as above, then billing's SLA automation issues a $10 credit note on the renewal "
                              "invoice for a DIFFERENT incident (metadata.incident is another INC id)"}
CRASH = {"before_send": "worker SIGKILLed right before the balance-transaction POST",
         "after_send": "worker SIGKILLed after Stripe's response to the POST was parsed, before anything recorded it"}
CLOCK = ("time: Stripe test clock advanced ~30 days, so Stripe's own billing engine ran the renewal under simulated "
         "time; nobody waited a month")
SLA = ("the billing SLA automation is the harness calling POST /v1/credit_notes (credit_amount=1000) on the renewal "
       "invoice; the credit note is real")
PROOF_NOTE = {"no_check": "decision.json holds the model's decision; nothing records authority or checks",
              "hand_check": "plain append-only log file written by the same worker, not hash-chained or signed",
              "interlock": "hash-chained journal; receipts.verify() re-derives happened/authorized/assumptions"}


def run_cell(c, prices, run_dir, crash, kind, system):
    case_dir = tempfile.mkdtemp(prefix=f"{crash}-{kind}-{system}-", dir=run_dir)
    case = open_case(c, prices, f"billing_credit {crash}/{kind}/{system}")
    with open(os.path.join(case_dir, "case.json"), "w") as f:
        json.dump(case, f)
    cell = {"system": system, "crash": crash, "outage": kind, "case": case}
    env = {k: v for k, v in os.environ.items() if k != "CRASH"}
    p = subprocess.run([sys.executable, WORKER, "decide", system, case_dir], env={**env, "CRASH": crash},
                       capture_output=True, text=True, timeout=300)
    t_crash = time.time()
    cell["worker_exit_code"] = p.returncode
    if p.returncode != -signal.SIGKILL:
        return {**cell, "outcome": "HARNESS_ERROR", "error": (p.stdout + p.stderr)[-800:]}
    with open(os.path.join(case_dir, "decision.json")) as f:
        cell["decision"] = json.load(f)
    cell["observed_at_crash"] = observations(c, case)
    cell["outage_record"] = outage(c, case, prices, kind)
    cell["observed_at_restart"] = observations(c, case)
    cell["outage_s"] = round(time.time() - t_crash, 1)
    t_restart = time.time()
    r = subprocess.run([sys.executable, WORKER, "restart", system, case_dir], env=env, capture_output=True, text=True,
                       timeout=600)
    t_settled = time.time()
    if r.returncode != 0:
        return {**cell, "outcome": "HARNESS_ERROR", "error": (r.stdout + r.stderr)[-800:]}
    res = json.loads(r.stdout.strip().splitlines()[-1])
    truth = ground_truth(c, case)
    held, matches = judge(crash, kind, truth, res["status"])
    log_path = os.path.join(case_dir, "hand_check.log")
    log = [json.loads(l) for l in open(log_path)] if os.path.exists(log_path) else []
    if system == "interlock":
        with open(os.path.join(case_dir, "receipt.json")) as f:
            cell["receipt"] = json.load(f)          # the full hash-chained bundle, published so anyone can re-verify
        v = verify(cell["receipt"])
        cell["reverified_offline_matches_restart"] = v == res["verify"]
        proof = v["valid"] and (v["happened"] is True) == (truth["case_credit_count"] > 0)
    elif system == "hand_check":
        proof = matches and any(e["step"] in ("send", "premises", "approval", "lookup") for e in log)
    else:
        proof = False
    want_count, want_cents = WANT[(crash, kind)]
    emulated = CLOCK + ("; " + SLA if kind in ("billing_credit", "unrelated_credit") else "")
    return {**cell, "outcome": res["status"], "restart": res, "hand_check_log": log, "ground_truth": truth,
            "want": {"case_credit_count": want_count, "case_credit_cents": want_cents},
            "invariant_held": held, "answer_matches_stripe": matches, "can_prove_what_happened": proof,
            "proof_note": PROOF_NOTE[system], "seconds_to_settle": round(t_settled - t_crash, 1),
            "restart_to_settle_s": round(t_settled - t_restart, 1), "emulated": emulated}


def ids(cell):
    t, case = cell.get("ground_truth", {}), cell["case"]
    parts = [f"clock {case['clock']}", f"customer {case['customer']}", f"subscription {case['subscription']}"]
    if cell.get("outage_record"):
        parts += [f"{k} {v}" for k, v in cell["outage_record"].items()]
    parts.append("case credits " + (", ".join(x["id"] for x in t.get("case_credits", [])) or "none"))
    if cell.get("restart", {}).get("effect_id"):
        parts.append(f"effect {cell['restart']['effect_id']}")
    return "; ".join(parts)


def cell_text(cell):
    if cell["outcome"] == "HARNESS_ERROR":
        return "HARNESS_ERROR"
    t, w = cell["ground_truth"], cell["want"]
    via = f" via `{cell['restart']['via']}`" if cell["restart"].get("via") else ""
    return (f"{cell['outcome']}{via}; {t['case_credit_count']} case credit(s), ${t['case_credit_cents'] / 100:.0f} "
            f"(want {w['case_credit_count']}, ${w['case_credit_cents'] / 100:.0f}); "
            f"**{'held' if cell['invariant_held'] else 'VIOLATED'}**; "
            f"answer {'matches' if cell['answer_matches_stripe'] else 'CONTRADICTS'} Stripe; "
            f"proof {'yes' if cell['can_prove_what_happened'] else 'no'}; {cell['seconds_to_settle']}s crash to settled "
            f"({cell['restart_to_settle_s']}s after restart)")


def refuses(cell, when, key):
    return cell[when][key] != cell["decision"]["observed"][key]


def premise_table(cells):
    """For each row and candidate premise: its value at decision, crash and restart, and whether it refuses."""
    lines = ["## Premise candidates, from this run", "",
             "Each cell read all three candidates from Stripe at decision time, right after the SIGKILL, and right "
             "before the restart. Values are cents (customer_balance is negative when the customer is owed). "
             "\"Refuses\" means the value differs from decision time in that many of the row's cells. The right "
             "answer at restart is to refuse exactly when the row wants no credit from this case; a refusal after "
             "`after_send` would contradict a credit that already landed.", "",
             "| crash / outage | want | " + " | ".join(f"`{k}` decision -> crash -> restart" for k in CANDIDATES) + " |",
             "|---|---|" + "---|" * len(CANDIDATES)]
    for cr, k in ROWS:
        cs = [c for c in cells if (c["crash"], c["outage"]) == (cr, k) and c.get("observed_at_restart")]
        if not cs:
            continue
        want_none = WANT[(cr, k)][0] == 0
        row = []
        for key in CANDIDATES:
            vals = sorted({(c["decision"]["observed"][key], c["observed_at_crash"][key], c["observed_at_restart"][key])
                           for c in cs})
            at_restart = sum(refuses(c, "observed_at_restart", key) for c in cs)
            at_crash = sum(refuses(c, "observed_at_crash", key) for c in cs)
            right = all(refuses(c, "observed_at_restart", key) == want_none for c in cs)
            row.append(" / ".join(" -> ".join(str(v) for v in t) for t in vals)
                       + f"; refuses at restart {at_restart}/{len(cs)}"
                       + (f", would refuse at crash {at_crash}/{len(cs)}" if at_crash else "")
                       + f"; **{'right' if right else 'WRONG'}**")
        lines.append(f"| `{cr}` / `{k}` | {WANT[(cr, k)][0]} | " + " | ".join(row) + " |")
    return lines


def markdown(out):
    cells = {(c["crash"], c["outage"], c["system"]): c for c in out["cells"]}
    ok = [c for c in out["cells"] if c["outcome"] != "HARNESS_ERROR"]
    lines = [f"# Scenario billing_credit: goodwill credit vs a billing run", "",
             f"Generated {out['generated']} by `experiments/scenario_billing_credit.py`. Stripe Billing test mode with "
             f"test clocks, model `{out['model']}`, every crash a real SIGKILL of the worker process.", "",
             "| crash / outage | no_check | hand_check | interlock |", "|---|---|---|---|"]
    for crash, kind in ROWS:
        lines.append(f"| `{crash}` / `{kind}` | " + " | ".join(
            cell_text(cells[(crash, kind, s)]) if (crash, kind, s) in cells else "not run" for s in SYSTEMS) + " |")
    lines += [""]
    for s in SYSTEMS:
        cs = [c for c in ok if c["system"] == s]
        if cs:
            lines.append(f"- **{s}**: invariant held {sum(c['invariant_held'] for c in cs)}/{len(cs)}, answer matched "
                         f"Stripe {sum(c['answer_matches_stripe'] for c in cs)}/{len(cs)}, can prove what happened "
                         f"{sum(c['can_prove_what_happened'] for c in cs)}/{len(cs)}, median "
                         f"{statistics.median(c['seconds_to_settle'] for c in cs):.0f}s crash to settled (median "
                         f"{statistics.median(c['restart_to_settle_s'] for c in cs):.0f}s after restart)")
    diff = [f"`{cr}`/`{k}`" for cr, k in ROWS if (cr, k, "hand_check") in cells and (cr, k, "interlock") in cells
            and cells[(cr, k, "hand_check")].get("invariant_held") != cells[(cr, k, "interlock")].get("invariant_held")]
    lines += ["", f"Rows where hand_check and interlock differ on the invariant: {', '.join(diff) or 'none'}.", ""]
    lines += [VERDICT, "", *premise_table(out["cells"]), "", SETUP, "", "## Rows", ""]
    lines += [f"- `{cr}` / `{k}`: {CRASH[cr]}; outage: {OUTAGE[k]}. Want: {WANT[(cr, k)][0]} credit(s) from this case."
              for cr, k in ROWS]
    lines += ["", "## LLM decisions", ""]
    lines += [f"- `{c['crash']}`/`{c['outage']}`/{c['system']}: {c['decision']['amount']} cents, \"{c['decision']['description']}\""
              for c in out["cells"] if c.get("decision")]
    lines += ["", "## Ids, for checking in the Stripe test dashboard", ""]
    for c in out["cells"]:
        extra = ""
        if c["system"] == "interlock" and c.get("restart"):
            v = verify(c["receipt"])
            extra = (f"; receipt valid={v['valid']} happened={v['happened']} authorized_when_fired="
                     f"{v['authorized_when_fired']} assumptions_held={v['assumptions_held']} refused={v['refused']!r} "
                     f"rechecked_at_recovery={v['rechecked_at_recovery']}; journal {' '.join(c['restart']['journal'])}")
        if c["outcome"] == "HARNESS_ERROR":
            extra = f"; error: {c['error'][-300:]!r}"
        lines.append(f"- `{c['crash']}`/`{c['outage']}`/{c['system']}: {ids(c)}; worker exit {c['worker_exit_code']}{extra}")
    lines += ["", "## Re-run", "", "    ANTHROPIC_API_KEY=... python3 experiments/scenario_billing_credit.py", ""]
    return "\n".join(lines)


SETUP = """## Setup

- **Decision.** Support approves ONE $10 goodwill credit for the case (approval cap 1000 cents). The worker reads the
  account from Stripe, and the model (tools `get_account`, `issue_credit`) decides the amount and description; the
  call is validated against the approval cap. The credit is `POST /v1/customers/{id}/balance_transactions`
  (amount -1000, metadata case_id), which Stripe applies to the next finalized invoice.
- **Premises**, captured when the worker reads the account, re-checked before any send: `subscription_status` is
  still `active`; `incident_compensation`, the cents credited to the customer for THIS incident by anyone other than
  this case (issued credit notes and negative balance adjustments whose `metadata.incident` is the case's incident),
  is unchanged. Billing's SLA automation tags its credit notes with the incident, so the data to scope the premise
  is in Stripe. A renewal consuming the balance, proration lines, and a credit for another incident do not move it.
- **Invariant**: this case's credits in Stripe are exactly what the premises allow: one $10 credit, or none when
  billing already credited this incident during the outage. Ground truth is Stripe's balance transactions, credit
  notes and invoices for the customer, re-read after the case settles.
- **no_check**: the decision is saved before the send, and the restart re-sends it with the same Idempotency-Key
  (`goodwill-credit-<case>`). The standard setup: Stripe dedupes, nothing re-reads the world.
- **hand_check**: the idiomatic careful version. Stripe offers no precondition on a balance transaction (no If-Match,
  no expected-balance parameter), so its native tools are the Idempotency-Key and listing the customer's balance
  transactions by metadata. Before every send, first run and restart alike: look this case's credit up and stop if
  it is there; check the approval is unrevoked and covers the amount; compare the premises with the ones saved in
  decision.json; append each step to a log file before and after the POST. About fifteen lines.
- **interlock**: `interlock.gate.Gate` over `scenarios/billing_credit/billing.py:CreditTarget` (tier 1, queryable),
  the approval as the lease store, a JSONL journal, claim TTL 40s; the restart loops `gate.recover()` until the
  effect is resolved, then writes the receipt bundle and `receipts.verify()`.
- **can_prove_what_happened**: the system's own record, without reading Stripe, says who acted, under which
  approval, which checks ran, and an outcome that agrees with Stripe. no_check: never. hand_check: its log does when
  it agrees with Stripe (it is a plain file from the same worker, not tamper-evident; published in full as
  `hand_check_log`). interlock: verify() is valid and its `happened` agrees with Stripe. The full receipt bundle is
  published per cell as `receipt` (with `decision`), and the harness re-runs verify() on that published copy;
  `python3 -m unittest tests.test_scenario_billing_credit` re-checks every published receipt offline.
- **Timing**: seconds from the harness seeing the worker exit -9 to the restart process exiting, which includes the
  outage (the test clock advance, about 10 to 20s); the part after the restart is in parentheses. A SIGKILLed
  Interlock sender cannot release its claim, so recovery waits until 40s after DISPATCHED."""

VERDICT = """## Verdict

- **Money: hand_check ties interlock on every row (6 of 6).** Both kept the customer at one $10 credit when nothing
  else credited this incident. Both refused when billing's SLA credit note for the same incident landed during the
  outage. Both still credited when billing credited a different incident. Neither was fooled by the renewal eating
  the credit or by a proration credit line. no_check held 5 of 6. It failed the row that matters here: it re-sent
  after billing had already credited the incident, so the customer got $20 for one incident. The Idempotency-Key
  cannot help, because nothing had been sent under it yet.
- **The premise is scoped to the incident, because the data is there.** Billing's SLA credit notes carry
  `metadata.incident`, and the case file holds the incident id, so both columns compare `incident_compensation`
  (about two lines in `compensation_by_others`). An earlier version of this page said that data was missing. It was
  not, and it compared a coarser premise instead. Both columns read the same `facts()`, so the change moves them
  together and the tie stands.
- **What the coarser premises would have done, from the table below.** `customer_balance` and
  `compensation_by_others` give the same result as `incident_compensation` on the first five rows. That includes
  `before_send`/`billing_credit`: the balance went 0 -> -1000 at restart and would have refused, so an earlier claim
  here that a balance premise would have caught nothing was wrong. All three differ on `unrelated_credit`: both
  coarse premises refuse a goodwill credit the invariant allows, and a person would have to re-approve it. The
  balance also moves on our own send: after `after_send` it read -1000 until the renewal consumed it, so a restart
  before the renewal would see a changed balance. That one is harmless for both careful columns (not run):
  hand_check looks its credit up before comparing premises, and the gate queries the target before it refuses
  (`COMMITTED_ON_QUERY`). A check that compared the balance before looking would refuse a credit that already landed.
- **Where interlock is better: the record, not the outcome.** Both hand_check and interlock leave a record that
  agrees with Stripe, and both are published in full in the JSON (`hand_check_log`; `receipt` and `decision` per
  interlock cell). Interlock's is hash-chained, and verify() re-derives who acted, under which approval, and the lease
  and premise checks before the send and again at recovery; the harness and the unit test re-run it on the published
  copy. hand_check's log is a plain file written by the same worker. It is just as informative here, but nothing can
  check it. Neither is signed in this run (no key), so the chain shows internal consistency, not who wrote it. The
  honest gap is packaging, not correctness: the hand-written lines have to be written again, correctly, for every
  effect.
- **Where interlock is worse: time.** A SIGKILLed Interlock sender keeps its claim until the claim expires (40s
  after DISPATCHED), so every interlock cell settled 41 to 42s after the crash. The other two took 14 to 26s, mostly
  the test clock advance. The wait is what stops two workers sending the same effect at once. The other two columns
  rely on Stripe's 24h idempotency window for that.
- **Recovery path.** Every interlock commit here was `retry-idempotent`: the premises still held at recovery, so
  the gate re-sent under the same key (a first send after before_send, a Stripe replay after after_send). The one
  refusal queried Stripe first and found nothing. AMBIGUOUS never came up, because Stripe dedupes and can be queried.
- **No core change needed.** CreditTarget, the premise and the approval lease store live in scenarios/billing_credit/."""


def main(argv):
    md_path = os.path.join(ROOT, "results", "scenarios", "billing_credit.md")
    if argv == ["--md"]:                    # re-render the md from the published JSON, no Stripe calls
        with open(os.path.join(ROOT, "results", "scenarios", "billing_credit.json")) as f, open(md_path, "w") as g:
            g.write(markdown(json.load(f)))
        return
    only = {tuple(a.split(":")) for a in argv}
    todo = [(cr, k, s) for cr, k in ROWS for s in SYSTEMS if not only or (cr, k, s) in only]
    c = client()
    prices = ensure_prices(c)
    run_dir = tempfile.mkdtemp(prefix="interlock-billing-credit-")
    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            cells = list(pool.map(lambda t: run_cell(c, prices, run_dir, *t), todo))
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    out = {"scenario": "billing_credit", "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "model": os.environ.get("INTERLOCK_MODEL", "claude-haiku-4-5-20251001"), "cells": cells}
    for cell in cells:
        print(f"{cell['crash']}/{cell['outage']}/{cell['system']}: {cell_text(cell)}", flush=True)
    if only:
        return
    os.makedirs(os.path.join(ROOT, "results", "scenarios"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "scenarios", "billing_credit.json"), "w") as f:
        json.dump(out, f, indent=1)
    with open(os.path.join(ROOT, "results", "scenarios", "billing_credit.md"), "w") as f:
        f.write(markdown(out))


if __name__ == "__main__":
    main(sys.argv[1:])
