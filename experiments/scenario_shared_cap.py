"""
Scenario shared_cap, live: two agents share one $30 approval cap on one Stripe test payment.

    python3 experiments/scenario_shared_cap.py                      # 20 reps x 5 systems x 2 crash points
    python3 experiments/scenario_shared_cap.py --reps 1 --parallel 2 # smoke run, prints only

Per run: a new $100 test-mode PaymentIntent. A support-bot process and a billing-bot process start
behind a shared barrier; each asks claude-haiku-4-5 for its refund ($20 by its ticket), then sends it
through one system (no_check, hand_check, hand_lock, interlock_core, interlock). The first bot to reach
the crash point (before_send, or after_commit: Stripe's response received) SIGKILLs itself; the harness
restarts it at once while the other bot carries on. Ground truth is Stripe's refund list for the
payment, read after both processes exit. Invariant: total refunded <= $30.

Keys, read at runtime and passed to the bot processes in their environment only:
STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list` (test keys only);
ANTHROPIC_API_KEY, else the line in $ANTHROPIC_ENV_FILE (default /Users/kiromoussa/CADAI/.env).
Writes results/scenarios/shared_cap.json and .md when run with the default reps.
"""
import argparse, collections, concurrent.futures, datetime, json, os, re, shutil, statistics, subprocess, sys, tempfile, time, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.journal import SqliteJournal
from interlock.receipts import bundle, verify
from interlock.targets.stripe_api import StripeClient
from scenarios.shared_cap.bot import MODEL
from scenarios.shared_cap.cap import BOTS, CAP, PAID, SETTLED_TTL, case_id, effect_id, ground_truth, race_mechanism

SYSTEMS = ("no_check", "hand_check", "hand_lock", "interlock_core", "interlock")
CHECKERS = ("hand_check", "hand_lock", "interlock_core", "interlock")     # systems that read Stripe before sending
CRASHES = ("after_commit", "before_send")
RUN_TIMEOUT = 180


def keys():
    stripe = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe:
        out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True).stdout
        stripe = next(iter(re.findall(r"^test_mode_api_key\s*=\s*'?(sk_test_[^'\s]+)", out, re.M)), None)
    anthropic = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic:
        with open(os.environ.get("ANTHROPIC_ENV_FILE", "/Users/kiromoussa/CADAI/.env")) as f:
            anthropic = next(l.split("=", 1)[1].strip().strip("'\"") for l in f if l.startswith("ANTHROPIC_API_KEY="))
    return stripe, anthropic


def run_one(client, env, system, crash, rep):
    pi = client.test_payment(PAID)
    run_id, d = uuid.uuid4().hex[:10], tempfile.mkdtemp(prefix="interlock-sandbox-shared-cap-")
    case, go_at = case_id(run_id), time.time() + 2.0

    def spawn(bot, restart=False):
        cmd = [sys.executable, "-m", "scenarios.shared_cap.bot", "--system", system, "--bot", bot, "--run-dir", d,
               "--run-id", run_id, "--pi", pi, "--crash", "none" if restart else crash, "--go-at", str(go_at)]
        log = open(os.path.join(d, f"{bot}{'.restart' if restart else ''}.log"), "w")
        return subprocess.Popen(cmd + (["--restart"] if restart else []), cwd=ROOT, env=env, stdout=log, stderr=log)

    procs, exits, crashed, t_crash, timed_out = {b: spawn(b) for b in BOTS}, collections.defaultdict(list), None, None, False
    deadline = time.time() + RUN_TIMEOUT
    while procs:
        for bot, p in list(procs.items()):
            code = p.poll()
            if code is None:
                continue
            exits[bot].append(code)
            del procs[bot]
            if code == -9 and crashed is None:
                crashed, t_crash = bot, time.time()
                procs[bot] = spawn(bot, restart=True)
        if time.time() > deadline:
            for p in procs.values():
                p.kill()
                p.wait()
            timed_out = True
            break
        time.sleep(0.05)
    t_settled = time.time()

    truth = ground_truth(client.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"], case)
    results, decisions = {}, {}
    for bot in BOTS:
        for name, into in ((f"{bot}.result.json", results), (f"{bot}.decision.json", decisions)):
            try:
                with open(os.path.join(d, name)) as f:
                    into[bot] = json.load(f)
            except FileNotFoundError:
                into[bot] = None
    with open(os.path.join(d, "events.jsonl")) as f:
        events = [json.loads(l) for l in f]
    logs = {n: open(os.path.join(d, n)).read()[-800:] for n in os.listdir(d) if n.endswith(".log")}

    receipts, can_prove = {}, False
    why = "Stripe metadata names the bot on each refund; nothing records the cap check, its read, or the lock"
    if system.startswith("interlock") and os.path.exists(os.path.join(d, "journal.db")):
        journal, ok = SqliteJournal(os.path.join(d, "journal.db")), True
        for bot in BOTS:
            eid = effect_id(case, bot)
            v = verify(bundle(journal, eid))
            landed = any(r["bot"] == bot for r in truth["refunds"])
            ok &= v["valid"] and (v["happened"] is True) == landed
            receipts[bot] = {"effect_id": eid, "kinds": [e["kind"] for e in journal.entries(eid)],
                             **{k: v[k] for k in ("valid", "happened", "happened_once", "authorized_when_fired",
                                                  "assumptions_held", "refused", "evidence", "problems")}}
        can_prove = ok
        why = "every bot's receipt verifies and its happened claim matches Stripe" if ok else "a receipt failed to verify or contradicts Stripe"
    shutil.rmtree(d)

    tl = timeline(events, go_at)
    statuses = {b: (results[b] or {}).get("status") for b in BOTS}
    return {"system": system, "crash": crash, "rep": rep, "payment_intent": pi, "run_id": run_id, "case": case,
            "decisions": decisions, "statuses": statuses, "crashed_bot": crashed, "exit_codes": dict(exits),
            "timed_out": timed_out, **truth,
            "seconds_crash_to_settled": round(t_settled - t_crash, 2) if t_crash else None,
            "can_prove_what_happened": can_prove, "can_prove_why": why, "receipts": receipts,
            "timeline": tl, "mechanism": race_mechanism(tl, crashed) if crashed else None, "emulated": None,
            "logs": {n: t for n, t in logs.items() if "Traceback" in t}}


def timeline(events, go_at):
    """Seconds after the start barrier, per bot attempt: first time of each event, and what its first check read saw."""
    out = {}
    for e in events:
        row = out.setdefault(e["bot"] + (" (restart)" if e["restart"] else ""), {})
        row.setdefault(e["ev"], round(e["t"] - go_at, 3))
        if e["ev"] == "check_read":
            row.setdefault("check_read_refunded", e.get("refunded", e.get("refunded_by_others")))
    return out


def outcome(r):
    other = next(b for b in BOTS if b != r["crashed_bot"]) if r["crashed_bot"] else None
    if not r["crashed_bot"]:
        return "no crash: " + ", ".join(f"{b} {r['statuses'][b]}" for b in BOTS)
    return f"crashed {r['statuses'][r['crashed_bot']]} / other {r['statuses'][other]}"


def median(xs, nd=3):
    return round(statistics.median(xs), nd) if xs else None


def race_stats(runs):
    """How long each bot's check read was stale before its commit, how far apart the two bots read, how long a lock was waited on."""
    waits = [max(waited) for r in runs if (waited := [t["lock_held"] - t["lock_wait"] for t in r["timeline"].values()
                                                       if "lock_held" in t])]
    both_checked = [r for r in runs if sum("check_start" in r["timeline"].get(b, {}) for b in BOTS) == 2]
    return {"median_check_to_commit_s": median([t["committed"] - t["check_start"] for r in runs for t in r["timeline"].values()
                                               if "check_start" in t and "committed" in t]),
            "median_gap_between_bots_checks_s": median([abs(r["timeline"][BOTS[0]]["check_start"] - r["timeline"][BOTS[1]]["check_start"])
                                                        for r in both_checked]),
            "median_lock_wait_s": median(waits)}     # per run, the longest any attempt waited for the flock


def cell(runs):
    held = sum(r["invariant_held"] for r in runs)
    settle = [r["seconds_crash_to_settled"] for r in runs if r["seconds_crash_to_settled"] is not None]
    totals = collections.Counter(f"${r['total_cents'] / 100:.0f} in {r['count']}" for r in runs)
    broke = [r["mechanism"] for r in runs if not r["invariant_held"] and r["mechanism"]]
    return {"system": runs[0]["system"], "crash": runs[0]["crash"], "runs": len(runs), "invariant_held": held,
            "totals": dict(totals), "outcomes": dict(collections.Counter(outcome(r) for r in runs)),
            "crashes": sum(bool(r["crashed_bot"]) for r in runs),
            "sigkill_exit_codes": sum(-9 in c for r in runs for c in r["exit_codes"].values()),
            "timed_out": sum(r["timed_out"] for r in runs),
            "median_seconds_crash_to_settled": median(settle, 1),
            "can_prove_what_happened": sum(r["can_prove_what_happened"] for r in runs),
            "landed_was_crashed_bots": sum(r["count"] == 1 and r["refunds"][0]["bot"] == r["crashed_bot"] for r in runs),
            "model_amounts": dict(collections.Counter(str((d or {}).get("amount")) for r in runs for d in r["decisions"].values())),
            "broken_runs_mechanism": {"runs": len(broke), "other_saw_zero": sum(m["saw_cents"] == 0 for m in broke),
                                      **{k: sum(m[k] for m in broke) for k in (
                                          "read_started_before_crash", "read_done_before_crash",
                                          "read_done_before_restart_reread", "read_in_restart_gap",
                                          "read_done_before_rival_commit")}},
            **race_stats(runs), "payment_intents": [r["payment_intent"] for r in runs]}


COLUMNS = {"no_check": "no_check (stable idempotency key, retry on restart)",
           "hand_check": "hand_check (read Stripe refunds, then send; no shared state)",
           "hand_lock": "hand_lock (hand_check inside an flock on the shared dir)",
           "interlock_core": "interlock_core (unmodified Gate, headroom premise)",
           "interlock": "interlock + CapJournal (scenario subclass, cap reserved at dispatch)"}


def cell_text(c):
    totals = ", ".join(f"{v}x {k}" for k, v in sorted(c["totals"].items()))
    return (f"**held {c['invariant_held']}/{c['runs']}**; Stripe: {totals}; crash in {c['crashes']}/{c['runs']}; "
            f"median {c['median_seconds_crash_to_settled']}s crash to settled; provable {c['can_prove_what_happened']}/{c['runs']}")


def reading(by, systems):
    """The 'Reading it' section, every number taken from the cells."""
    n = lambda s: sum(by[s, k]["runs"] for k in CRASHES)
    held = lambda s: sum(by[s, k]["invariant_held"] for k in CRASHES)
    per = lambda s, f: " and ".join(f"{f(by[s, k])} in `{k}`" for k in CRASHES)
    settle = lambda s: per(s, lambda c: f"{c['median_seconds_crash_to_settled']}s")
    safe = [s for s in systems if held(s) == n(s)]
    out = ["Held on every run: " + (", ".join(f"`{s}`" for s in safe) or "none") + ". Per system, across both crash points:", ""]
    out += [f"- `{s}` held {held(s)}/{n(s)} ({per(s, lambda c: str(c['invariant_held']))}); median crash to settled "
            f"{settle(s)}; provable {sum(by[s, k]['can_prove_what_happened'] for k in CRASHES)}/{n(s)}." for s in systems]
    out += ["", "Why the check-then-send systems broke, measured from each run's timeline (runs where both $20 refunds landed):", ""]
    for s in [s for s in CHECKERS if s in systems]:
        for k in CRASHES:
            m = by[s, k]["broken_runs_mechanism"]
            if not m["runs"]:
                continue
            out.append(
                f"- `{k}` / {s}, {m['runs']} broken runs: the other bot's check read returned before the crashed bot's "
                f"refund committed in {m['read_done_before_rival_commit']}, and saw $0 in {m['other_saw_zero']}. Relative "
                f"to the crash, that read had started before the SIGKILL in {m['read_started_before_crash']} and finished "
                f"before it in {m['read_done_before_crash']}. It finished before the restarted process's own re-read in "
                f"{m['read_done_before_restart_reread']}, and landed between that re-read and the restarted bot's refund "
                f"in {m['read_in_restart_gap']}.")
    if "hand_lock" in systems:
        out += ["", f"- `hand_lock`: per run, the longest wait for the flock was a median "
                    f"{per('hand_lock', lambda c: str(c['median_lock_wait_s']) + 's')}; the waiter then ran the same Stripe read."]
    if {"interlock", "interlock_core"} <= set(systems):
        core_refused = {k: sum(v for o, v in by["interlock_core", k]["outcomes"].items()
                               if o.startswith("crashed REFUSED")) for k in CRASHES}
        out += [f"- `interlock_core` is Interlock without the scenario's CapJournal: the core `Gate` with the same headroom "
                f"premise, read from Stripe before the send and again at recovery. Each bot's refund is its own effect id, so "
                f"core dispatch reserves nothing across them. Recovery refused the crashed bot's resend in "
                + " and ".join(f"{core_refused[k]}/{by['interlock_core', k]['runs']} `{k}` runs" for k in CRASHES)
                + ", because its re-check ran after the dead sender's claim expired, when the other refund was visible. "
                  "The `interlock` column's result is the CapJournal subclass (`scenarios/shared_cap/cap.py`), so it is "
                  "evidence for the proposed `reserve=` hook below, not for the current core."]
    if {"interlock", "hand_lock"} <= set(systems):
        i, h = held("interlock") == n("interlock"), held("hand_lock") == n("hand_lock")
        out += ["", "Verdict against the strongest hand-written arm:", ""]
        if i and h:
            out.append("- On money, `interlock` + CapJournal ties `hand_lock`. Both serialize the cap decision on a "
                       "resource the two processes share on one host; neither is using Stripe alone.")
        else:
            out.append(f"- On money, `interlock` + CapJournal held {held('interlock')}/{n('interlock')} and `hand_lock` "
                       f"held {held('hand_lock')}/{n('hand_lock')}.")
        mean = lambda s: statistics.mean(by[s, k]["median_seconds_crash_to_settled"] or 0 for k in CRASHES)
        faster = "`hand_lock` is faster" if mean("hand_lock") < mean("interlock") else "`interlock` is not slower"
        out.append(f"- On settle time {faster}: {settle('hand_lock')} for hand_lock, against {settle('interlock')} for "
                   f"interlock. The kernel drops a dead process's flock at once; Interlock's recovery waits out the "
                   f"dead sender's {SETTLED_TTL}s claim, because a claim cannot tell a dead sender from a slow one.")
        out.append(f"- Which refund lands differs in `before_send`: under `hand_lock` it was the crashed bot's in "
                   f"{by['hand_lock', 'before_send']['landed_was_crashed_bots']}/{by['hand_lock', 'before_send']['runs']} "
                   f"runs (the other bot takes the freed lock and sends); under `interlock` in "
                   f"{by['interlock', 'before_send']['landed_was_crashed_bots']}/{by['interlock', 'before_send']['runs']} "
                   f"(the dead bot's reservation refuses the other bot, and recovery sends the dead bot's refund later).")
        out.append(f"- What remains in Interlock's favor is the record: provable "
                   f"{sum(by['interlock', k]['can_prove_what_happened'] for k in CRASHES)}/{n('interlock')} against "
                   f"{sum(by['hand_lock', k]['can_prove_what_happened'] for k in CRASHES)}/{n('hand_lock')}. Each "
                   f"interlock receipt names the bot, the approval it acted under, the headroom it read, and, for a "
                   f"bot refused over the cap, which effect held the reservation; `hand_lock` leaves only Stripe metadata naming the bot.")
    out += ["", "Limits that apply to every arm:", "",
            "- The bots start from one barrier, the worst case for check-then-send. Agents acting seconds apart would not race.",
            "- The flock and the SQLite journal both only coordinate processes on one host. Across machines both need a "
            "shared lock or a conditional write in a shared database (`UPDATE budget SET used = used + ? WHERE used + ? <= cap`), "
            "which is what CapJournal amounts to.",
            "- No arm coordinates with refunds made outside it (a person in the dashboard); only the Stripe re-read sees those, "
            "with its own check-then-send gap."]
    return "\n".join(out)


def markdown(out):
    systems = [s for s in SYSTEMS if any(c["system"] == s for c in out["cells"])]
    by = {(c["system"], c["crash"]): c for c in out["cells"]}
    header = "| crash point | " + " | ".join(COLUMNS[s] for s in systems) + " |\n|" + "---|" * (len(systems) + 1)
    rows = "\n".join(f"| `{k}` | " + " | ".join(cell_text(by[s, k]) for s in systems) + " |" for k in CRASHES)
    outcomes = "\n".join(f"- `{k}` / {s}: " + "; ".join(f"{v}x {o}" for o, v in sorted(by[s, k]["outcomes"].items()))
                         for k in CRASHES for s in systems)
    races = "\n".join(f"- `{k}` / {s}: a bot's check read was {by[s, k]['median_check_to_commit_s']}s old (median) when its "
                      f"refund committed; the two bots' check reads started {by[s, k]['median_gap_between_bots_checks_s']}s "
                      f"apart (median)" + (f"; the waiting bot held the lock after {by[s, k]['median_lock_wait_s']}s (median)"
                                           if by[s, k]["median_lock_wait_s"] is not None else "")
                      for k in CRASHES for s in systems if s in CHECKERS)
    ids = []
    for r in out["runs"]:
        refunds = ", ".join(f"`{x['id']}` ${x['amount'] / 100:.0f} {x['bot']}" for x in r["refunds"]) or "none"
        rec = "; ".join(f"{b} receipt {v['kinds'][-1]} valid={v['valid']} happened={v['happened']}"
                        for b, v in r["receipts"].items())
        ids.append(f"- `{r['crash']}` / {r['system']} rep {r['rep']}: PaymentIntent `{r['payment_intent']}`, case "
                   f"`{r['case']}`, killed {r['crashed_bot']} (exits {r['exit_codes']}), refunds {refunds}"
                   + (f"; {rec}" if rec else ""))
    return TEMPLATE.format(generated=out["generated"], model=out["model"], reps=out["reps"], parallel=out["parallel"],
                           table=header + "\n" + rows, outcomes=outcomes, races=races, ids="\n".join(ids),
                           reading=reading(by, systems), ttl=SETTLED_TTL)


TEMPLATE = """# Scenario shared_cap: two agents, one $30 approval cap, real Stripe, real SIGKILL

Generated {generated} by `experiments/scenario_shared_cap.py`. Model `{model}`, Stripe test mode, {reps} runs per
cell, {parallel} runs at a time (each run has its own PaymentIntent, run directory and journal).

Each run: a new $100 test card payment. Case #4471 approves at most $30 of refunds in total. A support-bot process
and a billing-bot process start behind one barrier; each asks the model for its refund from its own ticket (both
tickets call for $20) and sends it through the system under test. The first bot to reach the crash point is
SIGKILLed by its own process (`before_send`: right before the refund POST; `after_commit`: after Stripe's response
arrived, before anything recorded it). The harness restarts that bot immediately while the other bot carries on.
Ground truth is Stripe's refund list for the payment, read after both processes exit. **Invariant: total refunded
<= $30**, so at most one of the two $20 refunds may land.

{table}

"held" is the invariant from Stripe's refund list. "crash to settled" runs from the harness seeing the SIGKILLed
process exit to the last bot process exiting. "provable" means the system left a record naming who did what and
which checks ran, and that record agrees with Stripe (see below).

## Reading it

Every number in this section is computed from the runs by the harness.

{reading}

## What each bot reported (crashed bot / other bot)

{outcomes}

## The race window, measured

{races}

## The five systems

All five run as two OS processes that share one run directory on one host.

- **no_check**: the refund POST with a stable `Idempotency-Key` (`shared_cap/<run>/<bot>`), retried on restart
  from the recorded decision. Stripe dedupes a bot's own retry. Nothing reads the other bot's refunds.
- **hand_check**: the no-shared-state check this scenario's spec prescribes: right before the POST, list the
  payment's refunds; if this bot's refund (matched on metadata) is already there, report it and stop; if the refunds
  plus this one exceed $30, refuse; otherwise POST with the same stable idempotency key. It runs again on restart, so
  it is also the lookup after a crash. Stripe offers no native precondition that fits: a refund cannot be made
  conditional on the payment's refunded amount, and Stripe's own atomic check only stops refunds past the $100 paid.
  Without state shared between the bots, the check-then-send gap stays open.
- **hand_lock**: what a competent engineer adds once they know two bots share one cap on one host: the same
  hand_check read and POST inside an exclusive `fcntl.flock` on a lock file in the shared run directory. The kernel
  releases the lock the moment its holder dies, so a SIGKILLed bot never blocks the other. About five lines.
- **interlock_core**: the unmodified `interlock.gate.Gate` with a SQLite journal both bots open, the case approval as
  the lease, and a headroom premise (refunds on the payment by others plus this refund <= $30) captured at decision
  time and re-checked against Stripe right before the send and at recovery. No scenario subclass.
- **interlock + CapJournal**: the same, with `CapGate` and `CapJournal` from `scenarios/shared_cap/cap.py` (about 60
  lines). The cap is enforced in the dispatch transaction: under SQLite's `BEGIN IMMEDIATE` (one writer across both
  processes), a DISPATCHED that would take the case past $30, counting the other bot's in-flight, committed or
  AMBIGUOUS effect, is refused and journaled with who holds the reservation. For both interlock arms the crashed
  bot's restart runs `gate.recover()`: it waits out the dead sender's claim ({ttl}s, longer than the Stripe client's
  30s timeout), re-checks the approval and premises, then resends under its effect id as Stripe's idempotency key or,
  if the premise no longer holds, looks the refund up and refuses a resend.

## Proposed core change

The cap reservation lives in a scenario subclass because `interlock/journal.py` and `interlock/gate.py` were not
edited, and `interlock_core` above shows the core alone does not enforce a cross-effect cap. Proposed for core:
`Journal.dispatch(..., reserve=fn)`, where `fn(entries, effect)` runs inside the same lock or transaction as the
DISPATCHED write and returns a refusal reason or None, plus a `REFUSED:<reason>` status from `Gate.submit` for that
blocker (today an unknown blocker is reported as `IN_FLIGHT`, which `CapGate.submit` has to translate). A budget
over journaled effects (`reserved_cents` in `cap.py`) is then about fifteen lines for any shared limit: a refund cap,
a spend limit per agent, a quota of emails per case.

Its limit: the reservation only sees effects that go through this journal. A refund issued outside it (a person in
the dashboard) is seen by the premise re-check, which reads Stripe, and that read still has a check-then-send gap
against people. It closes the race between agents that share the journal, not against the rest of the world.

## What is real, what is emulated

- Stripe: every payment, refund, list and idempotent replay is a real test-mode API call. Ground truth is Stripe's
  refund list. Nothing is emulated in any cell.
- LLM: each bot's first attempt is a real Anthropic Messages call with a forced `issue_refund` tool; the amount is
  validated (integer cents, at most the $30 cap) before use. The decision is saved to a file and reused by the
  restarted process, as a job queue or workflow history would. Model amounts across all runs are in the JSON.
- Crashes: `os.kill(os.getpid(), SIGKILL)` in the bot process, one per run, claimed by whichever bot reaches the
  crash point first (`O_EXCL` marker file). Exit code -9 is recorded per run.
- Processes: two separate OS processes per run, plus the restarted one. The flock and the Interlock journal are
  files they all open; nothing is shared in memory.
- Concurrency across runs: {parallel} runs at a time on one machine, so Stripe and model latency are those of a
  loaded client. Within a run the two bots start from one barrier; their relative timing comes from real model and
  Stripe latency, not from a sleep.
- Journals and run directories are temporary and deleted after each run; receipts were verified before deletion
  and their summaries are in the JSON.

## Ids, for checking in the Stripe test dashboard

{ids}

## Re-run

    python3 experiments/scenario_shared_cap.py                  # writes results/scenarios/shared_cap.json and .md
    python3 experiments/scenario_shared_cap.py --from-json       # rewrite the .md from the JSON
    python3 -m unittest tests.test_scenario_shared_cap          # offline logic
"""


def write_markdown(out):
    with open(os.path.join(ROOT, "results", "scenarios", "shared_cap.md"), "w") as f:
        f.write(markdown(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--systems", nargs="+", default=SYSTEMS)
    ap.add_argument("--crashes", nargs="+", default=CRASHES)
    ap.add_argument("--from-json", action="store_true")
    args = ap.parse_args()
    if args.from_json:
        with open(os.path.join(ROOT, "results", "scenarios", "shared_cap.json")) as f:
            write_markdown(json.load(f))
        return print("wrote results/scenarios/shared_cap.md")
    stripe, anthropic = keys()
    client = StripeClient(stripe)
    env = {**os.environ, "STRIPE_SECRET_KEY": stripe, "ANTHROPIC_API_KEY": anthropic, "PYTHONPATH": ROOT}
    jobs = [(s, c, rep) for rep in range(args.reps) for c in args.crashes for s in args.systems]   # interleaved
    runs = []
    with concurrent.futures.ThreadPoolExecutor(args.parallel) as pool:
        for r in pool.map(lambda j: run_one(client, env, *j), jobs):
            runs.append(r)
            print(f"{r['system']:14} {r['crash']:12} rep {r['rep']:2}  ${r['total_cents'] / 100:.0f} in {r['count']}  "
                  f"held={r['invariant_held']}  {outcome(r)}  settle={r['seconds_crash_to_settled']}  {r['payment_intent']}",
                  flush=True)
    cells = [cell([r for r in runs if r["system"] == s and r["crash"] == c]) for c in args.crashes for s in args.systems]
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "model": MODEL,
           "cap_cents": CAP, "paid_cents": PAID, "reps": args.reps, "parallel": args.parallel, "cells": cells, "runs": runs}
    if set(args.crashes) == set(CRASHES):
        by = {(c["system"], c["crash"]): c for c in cells}
        print(reading(by, [s for s in SYSTEMS if s in args.systems]))
    if args.reps >= 20 and set(args.systems) == set(SYSTEMS) and set(args.crashes) == set(CRASHES):
        out["verdict"] = reading({(c["system"], c["crash"]): c for c in cells}, list(SYSTEMS))
        os.makedirs(os.path.join(ROOT, "results", "scenarios"), exist_ok=True)
        with open(os.path.join(ROOT, "results", "scenarios", "shared_cap.json"), "w") as f:
            json.dump(out, f, indent=1)
        write_markdown(out)
        print("wrote results/scenarios/shared_cap.json and .md")


if __name__ == "__main__":
    main()
