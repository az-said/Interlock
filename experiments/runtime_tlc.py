"""
Run the TLA+ model checks in spec/ and write results/runtime_tlc.md.

A model check for the stated constants, not a proof of the Python or SQL.

    python3 experiments/runtime_tlc.py one Runtime.cfg --set Tier=1 --inv Reach_Committed
    python3 experiments/runtime_tlc.py suite [--jobs 3] [--only substring]

Each run writes a config under spec/.tools/cfg/, runs spec/run_tlc.sh, and records hold or
violated, state counts, diameter and wall time. A "peel" job checks a list of invariants: TLC
stops at the first violation, so the violated invariant is removed and the rest re-checked
until they hold. Every violation keeps TLC's shortest (breadth-first) trace.
"""
import argparse, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec")
CFGDIR = os.path.join(SPEC, ".tools", "cfg")
RESULTS = os.path.join(ROOT, "results")


def make_cfg(name, base, sets, invs, props=()):
    text = open(os.path.join(SPEC, base)).read()
    for k, v in sets.items():
        text, n = re.subn(rf"^(\s*){k} = .*$", lambda m: f"{m.group(1)}{k} = {v}", text, flags=re.M)
        if not n:
            raise SystemExit(f"{base}: no constant {k}")
    text = text.split("INVARIANTS")[0].split("PROPERTIES")[0]
    if props:                                   # TLC forbids SYMMETRY with temporal properties
        text = text.replace("SYMMETRY Sym\n", "").replace("SPECIFICATION Spec\n", "SPECIFICATION LiveSpec\n")
    if invs:
        text += "INVARIANTS\n" + "".join(f"  {i}\n" for i in invs)
    if props:
        text += "PROPERTIES\n" + "".join(f"  {p}\n" for p in props)
    text += "CHECK_DEADLOCK FALSE\n"
    os.makedirs(CFGDIR, exist_ok=True)
    path = os.path.join(CFGDIR, name + ".cfg")
    open(path, "w").write(text)
    return os.path.relpath(path, SPEC)


def flatten(v, prefix=""):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out.update(flatten(x, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: json.dumps(v, sort_keys=True)}


def trace_summary(path):
    """TLC's -dumpTrace json -> [(action, {field: new value})], only changed fields.
    Layout: counterexample.state = [[i, state]], counterexample.action = [[[i, s], {name, context}, [j, s']]]."""
    try:
        ce = json.load(open(path))["counterexample"]
    except Exception:
        return None
    states = [s[1] for s in ce["state"]]
    names = ["Init"] + [a[1]["name"] + ("(" + ",".join(str(v) for v in a[1].get("context", {}).values()) + ")"
                                        if a[1].get("context") else "") for a in ce["action"]]
    rows, prev = [], {}
    for i, st in enumerate(states):
        flat = flatten(st)
        rows.append((names[i] if i < len(names) else "?",
                     {k: v for k, v in flat.items() if prev.get(k) != v} if i else {}))
        prev = flat
    return rows


def tlc(name, module, base, sets, invs, props=(), workers="3", heap="6g", timeout=8 * 3600):
    cfg = make_cfg(name, base, sets, invs, props)
    tpath = os.path.join(CFGDIR, name + ".trace.json")
    if os.path.exists(tpath):
        os.remove(tpath)
    env = dict(os.environ, TLC_WORKERS=workers, TLC_HEAP=heap)
    t0 = time.time()
    try:
        p = subprocess.run([os.path.join(SPEC, "run_tlc.sh"), module, cfg, "-dumpTrace", "json", tpath],
                           capture_output=True, text=True, env=env, timeout=timeout)
        out = p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        out += "\nTIMEOUT"
    for f in os.listdir(SPEC):                  # TLC drops trace-exploration specs next to the module
        if "_TTrace_" in f:
            os.remove(os.path.join(SPEC, f))
    r = {"wall_s": round(time.time() - t0, 1)}
    m = re.search(r"([\d,]+) states generated, ([\d,]+) distinct states found", out)
    r["generated"], r["distinct"] = ((int(m.group(1).replace(",", "")), int(m.group(2).replace(",", "")))
                                     if m else (None, None))
    m = re.search(r"depth of the complete state graph search is (\d+)", out)
    r["depth"] = int(m.group(1)) if m else None
    m = re.search(r"TLC2 Version (\S+)", out)
    r["tlc"] = m.group(1) if m else None
    if "No error has been found" in out:
        r["outcome"] = "hold"
    elif (m := re.search(r"Invariant (\w+) is violated", out)):
        r["outcome"], r["violated"] = "violated", m.group(1)
    elif re.search(r"Temporal propert(?:y|ies)(?: \w+)? (?:was|were|is) violated", out):
        # this TLC build prints "Error: Temporal property Termination was violated."
        m = re.search(r"Temporal property (\w+) (?:was|is) violated", out)
        r["outcome"], r["violated"] = "violated", (m.group(1) if m else ",".join(props))
    elif "TIMEOUT" in out:
        r["outcome"] = "timeout"
    else:
        r["outcome"], r["error"] = "error", out[-3000:]
    if r["outcome"] == "violated":
        r["trace"] = trace_summary(tpath)
    return r


def run(job):
    """A job: plain (one TLC run) or peel (re-run without each violated invariant until the rest hold)."""
    base = {k: job.get(k) for k in ("name", "module", "base", "set", "expect", "group", "tier", "mode")}
    invs, props = list(job.get("inv", [])), list(job.get("props", []))
    if not job.get("peel"):
        r = tlc(job["name"], job["module"], job["base"], job.get("set", {}), invs, props)
        return {**base, "inv": invs, "props": props, **r}
    violations, runs, last = {}, [], None
    while invs:
        last = tlc(f"{job['name']}_{len(runs)}", job["module"], job["base"], job.get("set", {}), invs)
        runs.append({k: last.get(k) for k in ("outcome", "violated", "distinct", "wall_s")})
        if last["outcome"] != "violated":
            break
        violations[last["violated"]] = last.get("trace")
        invs.remove(last["violated"])
    status = {i: "V" for i in violations}
    for i in invs:
        status[i] = {"hold": "hold", "timeout": "timeout", "error": "error"}.get(last["outcome"], "?")
    return {**base, "inv": job["inv"], "status": status, "violations": violations, "runs": runs,
            "outcome": last["outcome"] if last else "hold", "distinct": last and last.get("distinct"),
            "depth": last and last.get("depth"), "tlc": last and last.get("tlc"), "error": last and last.get("error"),
            "wall_s": round(sum(x["wall_s"] for x in runs), 1)}


def fmt_trace(rows, skip=("hist.", "lw.", "sendLog")):
    lines = []
    for i, (act, ch) in enumerate(rows or []):
        shown = {k: v for k, v in ch.items() if not k.startswith(skip)}
        hidden = sum(1 for k in ch if k.startswith(skip))
        body = ", ".join(f"{k}={v}" for k, v in sorted(shown.items()))
        lines.append(f"{i + 1:>2}. {act}: {body}" + (f"  (+{hidden} local/history fields)" if hidden else ""))
    return "\n".join(lines)


# ------------------------------------------------------------------ the suite
TIERS = [("t1q", {"Tier": "1", "Queryable": "TRUE"}), ("t1n", {"Tier": "1", "Queryable": "FALSE"}),
         ("t2", {"Tier": "2", "Queryable": "TRUE"}), ("t3", {"Tier": "3", "Queryable": "FALSE"})]
MODES = {"interlock": "Runtime.cfg", "temporal_idem": "RuntimeTemporalIdem.cfg",
         "temporal_precheck": "RuntimeTemporalPrecheck.cfg"}
SAFETY = ["NoRerunAfterComplete", "StepResultUnique", "FencedWrites", "LeaseMutex", "TakeoverOnlyAfterExpiry",
          "AtMostOneCommit", "EffectAtMostOnceTier12", "Tier3NeverResends", "NoOverlappingSends",
          "CommittedImpliesApplied", "AmbiguousOnlyWhenUnknowable", "EffectCheckpointAtomic",
          "SendRequiresLiveClaim", "NoSendUnderRevokedGrant", "RevokeLinearizable", "NoSendOnStalePremise",
          "RecoveryRechecks", "PayloadBound", "NoSendAfterCancel", "LateResultPreserved", "ReceiptChainLinear",
          "PremiseTrueAtSend"]
# Not meaningful for the Temporal modes (no fence, no effect journal, plain step not modeled); see spec/README.md.
TEMPORAL_NA = {"NoRerunAfterComplete", "StepResultUnique", "FencedWrites", "LeaseMutex", "TakeoverOnlyAfterExpiry",
               "AmbiguousOnlyWhenUnknowable", "EffectCheckpointAtomic", "LateResultPreserved", "ReceiptChainLinear"}
BROKEN = {"NaiveRecovery": ["RecoveryRechecks", "NoSendOnStalePremise", "NoSendUnderRevokedGrant"],
          "NoFencing": ["SendRequiresLiveClaim", "FencedWrites", "EffectAtMostOnceTier12"],
          "GrantCheckOutsideTxn": ["RevokeLinearizable", "NoSendUnderRevokedGrant"],
          "CommitWithoutCheckpoint": ["EffectCheckpointAtomic"],
          "RecoverBeforeDeadline": ["NoOverlappingSends", "EffectAtMostOnceTier12"],
          "StopwatchAfterDispatch": ["NoOverlappingSends"],
          "LateAckDropped": ["LateResultPreserved"],
          "NoLocalLeaseCheck": ["NoRerunAfterComplete"],
          "ThinDedupMargin": ["EffectAtMostOnceTier12"]}
WITNESSES = ["Reach_Committed", "Reach_Completed", "Reach_Ambiguous", "Reach_RecoveryResend", "Reach_CommitByQuery",
             "Reach_RefusedAtRecovery", "Reach_LateResult", "Reach_Takeover", "Reach_Cancelled", "Reach_TwoSends"]
G1 = '{"revoke", "hand_refund_full", "cancel"}'
G2 = '{"prune_keys", "redecide", "revoke"}'
SAFETY_SET = {"MaxClock": "10", "MaxCrashes": "1", "DedupAge": "5"}
GROUPS = [("G1", G1), ("G2", G2)]


def suite():
    J = [{"name": "signals", "module": "Signals", "base": "Signals.cfg", "group": "signals",
          "inv": ["TypeOK", "NoLostWakeup", "SignalExactlyOnceConsumed", "TimerNotEarly"], "peel": True},
         {"name": "broken_WakeOnlyIfSleeping", "module": "Signals", "base": "broken/WakeOnlyIfSleeping.cfg",
          "inv": ["NoLostWakeup"], "expect": "violated", "group": "broken"}]
    for b, invs in BROKEN.items():
        for inv in invs:
            J.append({"name": f"broken_{b}_{inv}", "module": "Runtime", "base": f"broken/{b}.cfg",
                      "inv": [inv], "expect": "violated", "group": "broken"})
    for t, ts in TIERS:
        for g, ev in GROUPS:
            for mode, cfg in MODES.items():
                invs = [i for i in SAFETY if mode == "interlock" or i not in TEMPORAL_NA]
                J.append({"name": f"{mode}_{t}_{g}", "module": "Runtime", "base": cfg, "mode": mode, "tier": t,
                          "set": {**SAFETY_SET, **ts, "Events": ev, "MODE": f'"{mode}"'}, "inv": invs,
                          "group": f"safety_{g}", "peel": True})
        J.append({"name": f"witness_{t}", "module": "Runtime", "base": "Runtime.cfg", "tier": t, "group": "witness",
                  "set": {**SAFETY_SET, "MaxClock": "8", **ts, "Events": G1}, "inv": WITNESSES, "peel": True})
        J.append({"name": f"live_interlock_{t}", "module": "Runtime", "base": "RuntimeLive.cfg", "tier": t,
                  "set": ts, "props": ["Termination", "EffectResolved"], "group": "liveness"})
    for t, ts in [TIERS[0], TIERS[1]]:        # the prune path only exists at tier 1
        J.append({"name": f"witness_prune_{t}", "module": "Runtime", "base": "Runtime.cfg", "tier": t,
                  "group": "witness_prune", "peel": True, "inv": ["Reach_Pruned", "Reach_SendAfterPrune"],
                  "set": {**SAFETY_SET, **ts, "Events": G2}})
    # Sanity: with too little clock the run cannot finish, so Termination must be reported violated.
    J.append({"name": "live_sanity_short_clock", "module": "Runtime", "base": "RuntimeLive.cfg", "tier": "t2",
              "set": {"MaxClock": "3"}, "props": ["Termination"], "expect": "violated", "group": "liveness"})
    for t, ts in [TIERS[0], TIERS[2]]:
        J.append({"name": f"interlock_{t}_crashes2", "module": "Runtime", "base": "Runtime.cfg", "tier": t,
                  "mode": "interlock", "group": "crashes2", "peel": True, "inv": SAFETY,
                  "set": {**SAFETY_SET, "MaxClock": "8", "MaxCrashes": "2", **ts, "Events": G1}})
    J.append({"name": "interlock_t2_lease_shorter_than_send", "module": "Runtime", "base": "Runtime.cfg", "tier": "t2",
              "mode": "interlock", "group": "lease", "peel": True, "inv": SAFETY,
              "set": {**SAFETY_SET, **TIERS[2][1], "Events": G1, "LeaseTTL": "2", "SendTimeout": "3"}})
    for mode in MODES:
        for a in ["Pause", "ServerSlow"]:
            for t, ts in [TIERS[0], TIERS[2]]:
                J.append({"name": f"assume_{a}_{mode}_{t}", "module": "Runtime", "base": f"assumptions/{a}.cfg",
                          "mode": mode, "tier": t, "group": "assumptions",
                          "set": {"MODE": f'"{mode}"', **ts},
                          "inv": ["EffectAtMostOnceTier12"] + (["LateResultPreserved"] if mode == "interlock" else []),
                          "peel": True})
    return J


def write_report(results):
    by = {r["name"]: r for r in results}
    ver = next((r["tlc"] for r in results if r.get("tlc")), "?")

    def st(name, inv):
        r = by.get(name)
        if not r:
            return "not run"
        return r.get("status", {}).get(inv, "n/a")

    L = ["# TLC results: spec/Runtime.tla and spec/Signals.tla", "",
         "A model check for the stated constants, not a proof of the Python or SQL.", "",
         f"- TLC `{ver}`, tla2tools.jar pinned by sha256 in spec/tla2tools.sha256.",
         "- Generated by `python3 experiments/runtime_tlc.py suite`; the exact configs run are in spec/.tools/cfg/.",
         f"- Safety runs: Workers = {{w1, w2}}, LeaseTTL 3, SendTimeout 2, SettleMargin 2, overrides {SAFETY_SET}, "
         f"events G1 = {G1} or G2 = {G2}. Symmetry over workers.",
         "- Tier cases: t1q tier 1 with lookup (Stripe-like), t1n tier 1 without lookup, t2 tier 2, t3 tier 3.",
         "- V = TLC found a counterexample (trace below). hold = no counterexample in the full state space. "
         "n/a = not meaningful for that mode (spec/README.md).", ""]
    L += ["## State spaces", "", "| job | outcome | distinct states (last run) | depth | TLC runs | wall s |", "|---|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['name']} | {r['outcome']} | {r.get('distinct')} | {r.get('depth')} | "
                 f"{len(r.get('runs') or [1])} | {r['wall_s']} |")
    for g, ev in GROUPS:
        L += ["", f"## Invariants by mode and tier, events {g} = {ev}", "",
              "| invariant | " + " | ".join(f"{m} {t}" for m in MODES for t, _ in TIERS) + " |",
              "|---|" + "---|" * (len(MODES) * len(TIERS))]
        for inv in SAFETY:
            L.append(f"| {inv} | " + " | ".join(st(f"{m}_{t}_{g}", inv) for m in MODES for t, _ in TIERS) + " |")
    L += ["", "## Two crashes (MaxClock 8, G1) and lease shorter than send (LeaseTTL 2, SendTimeout 3)", "",
          "| job | violated | everything else |", "|---|---|---|"]
    for n in ["interlock_t1q_crashes2", "interlock_t2_crashes2", "interlock_t2_lease_shorter_than_send"]:
        r = by.get(n)
        if r:
            L.append(f"| {n} | {', '.join(r['violations']) or 'none'} | {r['outcome']} |")
    L += ["", "## Assumption toggles", "", "| toggle | tier | interlock | temporal_idem | temporal_precheck |", "|---|---|---|---|---|"]
    for a in ["Pause", "ServerSlow"]:
        for t in ["t1q", "t2"]:
            L.append(f"| {a} EffectAtMostOnceTier12 | {t} | " +
                     " | ".join(st(f"assume_{a}_{m}_{t}", "EffectAtMostOnceTier12") for m in MODES) + " |")
    L += ["", "## Broken variants (each must be V; anything else means the model is wrong)", "",
          "| config | invariant | outcome | trace steps |", "|---|---|---|---|"]
    for r in results:
        if r["group"] == "broken":
            flag = "" if r["outcome"] == "violated" else " MODEL WRONG"
            L.append(f"| {r['base']} | {r['inv'][0]} | {r['outcome']}{flag} | {len(r.get('trace') or [])} |")
    r = by.get("signals")
    if r:
        L += ["", "## Signals.tla", "", f"{r['status']}; {r['distinct']} distinct states, depth {r['depth']}."]
    L += ["", "## Liveness (RuntimeLive.cfg: URGENT time, weak fairness, one crash, no pause)", "",
          "| tier | outcome | distinct states | wall s |", "|---|---|---|---|"]
    for t, _ in TIERS:
        r = by.get(f"live_interlock_{t}")
        if r:
            L.append(f"| {t} | {r['outcome']} {r.get('violated', '')} | {r.get('distinct')} | {r['wall_s']} |")
    L += ["", "## Reachability witnesses (interlock, MaxClock 8, G1)", "",
          "Each Reach_X negates a path. V = the path is reachable, so the hold results are not vacuous for it.", "",
          "| witness | " + " | ".join(t for t, _ in TIERS) + " |", "|---|" + "---|" * len(TIERS)]
    for w in WITNESSES:
        L.append(f"| {w} | " + " | ".join({"V": "reachable", "hold": "unreachable"}.get(st(f"witness_{t}", w), st(f"witness_{t}", w))
                                         for t, _ in TIERS) + " |")
    L += ["", "## Shortest counterexample traces", "",
          "Breadth-first, so each is a shortest trace for its config. Changed database, world and wire fields shown; "
          "worker-local and history fields are counted, not printed.", ""]
    shown = set()
    for r in results:
        traces = r.get("violations") or ({r["violated"]: r.get("trace")} if r.get("violated") else {})
        for inv, tr in traces.items():
            key = (r.get("group"), r.get("mode"), inv)
            if r.get("group") == "witness" or key in shown or not tr:
                continue
            shown.add(key)
            L += [f"### {r['name']}: {inv}", "", "```", fmt_trace(tr), "```", ""]
    os.makedirs(RESULTS, exist_ok=True)
    open(os.path.join(RESULTS, "runtime_tlc.md"), "w").write("\n".join(L) + "\n")
    json.dump([{k: v for k, v in r.items() if k not in ("trace", "violations")} for r in results],
              open(os.path.join(CFGDIR, "suite_results.json"), "w"), indent=1)


def _invs_of(path):
    t = open(path).read()
    return t.split("INVARIANTS")[1].split("CHECK_DEADLOCK")[0].split() if "INVARIANTS" in t else []


def rebuild(results):
    """Re-attach traces from the dumps on disk: plain jobs use <name>.trace.json; a peel job's
    iteration i violated the invariant that is missing from iteration i+1's config."""
    for r in results:
        name = r["name"]
        if "status" in r:
            r["violations"] = {}
            for i in range(len(r.get("runs") or []) - 1):
                a, b = (os.path.join(CFGDIR, f"{name}_{k}.cfg") for k in (i, i + 1))
                gone = set(_invs_of(a)) - set(_invs_of(b))
                for inv in gone:
                    r["violations"][inv] = trace_summary(os.path.join(CFGDIR, f"{name}_{i}.trace.json"))
        elif r.get("violated"):
            r["trace"] = trace_summary(os.path.join(CFGDIR, f"{name}.trace.json"))
    return results


def predicted(inv, mode, tier):
    """docs/07-runtime.md 10.6 as a function; None where 10.6 says nothing or the formula is vacuous."""
    if mode == "interlock":
        return None if inv == "PremiseTrueAtSend" else "hold"
    if inv in ("AtMostOneCommit", "CommittedImpliesApplied"):
        return "hold"
    if inv == "EffectAtMostOnceTier12":            # vacuous at tier 3
        if tier == "t3":
            return "hold"
        if mode == "temporal_idem":
            return "V"                             # V at t2; at tier 1 after prune or a reset (G2)
        return "V" if tier == "t2" else "hold"     # precheck: V at t2 only
    if inv == "Tier3NeverResends":                 # vacuous at t1q and t2
        return "V" if tier in ("t1n", "t3") else "hold"
    if inv == "PayloadBound":
        return "V" if mode == "temporal_idem" else "hold"
    if inv in ("NoOverlappingSends", "SendRequiresLiveClaim", "NoSendUnderRevokedGrant", "RevokeLinearizable",
               "NoSendOnStalePremise", "RecoveryRechecks", "NoSendAfterCancel"):
        return "V"
    return None


def finalize():
    """After a suite: fill spec/README.md's state-space table and relabel TLC's 'Next' steps in the report."""
    results = json.load(open(os.path.join(CFGDIR, "suite_results.json")))
    rows = ["| job | mode | tier | events | invariants violated | distinct states (final full run) | depth | TLC runs | wall s |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r["group"] == "broken":
            continue
        ev = (r.get("set") or {}).get("Events", "")
        ev = "G1" if ev == G1 else "G2" if ev == G2 else ("cfg" if not ev else ev)
        nviol = sum(1 for v in (r.get("status") or {}).values() if v == "V")
        rows.append(f"| {r['name']} | {r.get('mode') or ''} | {r.get('tier') or ''} | {ev} | {nviol} | "
                    f"{r.get('distinct')} | {r.get('depth')} | {len(r.get('runs') or [1])} | {r['wall_s']} |")
    block = "<!-- states:begin -->\n" + "\n".join(rows) + "\n<!-- states:end -->"
    readme = os.path.join(SPEC, "README.md")
    text = open(readme).read()
    if "<!-- states:begin -->" in text:
        text = re.sub(r"<!-- states:begin -->.*?<!-- states:end -->", lambda m: block, text, flags=re.S)
    else:
        text = text.replace("@@STATES@@", block)
    open(readme, "w").write(text)
    by = {r["name"]: r for r in results}

    def agg(mode, t, inv):
        got = [by[n]["status"].get(inv) for n in (f"{mode}_{t}_G1", f"{mode}_{t}_G2") if n in by and by[n].get("status")]
        if not got or any(g is None for g in got):
            return "not run" if not got else "n/a"
        return "V" if "V" in got else ("hold" if all(g == "hold" for g in got) else "/".join(got))
    invs = [i for i in SAFETY if i not in TEMPORAL_NA]
    head = "| invariant | " + " | ".join(f"{m.replace('temporal_', '')} {t}" for m in MODES for t, _ in TIERS) + " |"
    table = [f"Summary over events G1 and G2 (V if violated in either). Constants: {SAFETY_SET}.", "", head,
             "|---|" + "---|" * (len(MODES) * len(TIERS))]
    for inv in invs:
        table.append(f"| {inv} | " + " | ".join(agg(m, t, inv) for m in MODES for t, _ in TIERS) + " |")
    block = "<!-- temporal:begin -->\n" + "\n".join(table) + "\n<!-- temporal:end -->"
    cx = os.path.join(SPEC, "COUNTEREXAMPLES.md")
    text = open(cx).read()
    if "<!-- temporal:begin -->" in text:
        text = re.sub(r"<!-- temporal:begin -->.*?<!-- temporal:end -->", lambda m: block, text, flags=re.S)
    else:
        text = text.replace("@@TEMPORAL_TABLE@@", block)
    open(cx, "w").write(text)
    report = os.path.join(RESULTS, "runtime_tlc.md")
    text = open(report).read()
    text = re.sub(r"^(\s*\d+)\. Next: ", r"\1. Process (target applies a request): ", text, flags=re.M)
    text = re.sub(r"^(\| broken/NoFencing\.cfg \| EffectAtMostOnceTier12 \| hold) MODEL WRONG",
                  r"\1 (prediction revised after diagnosis: at-most-once is carried by the effect row, not the fence; spec/README.md)",
                  text, flags=re.M)
    # 10.6's predictions against what TLC measured, per (invariant, mode, tier), over G1 and G2.
    agree, disagree, compared = 0, [], 0
    for inv in SAFETY:
        for m in MODES:
            for t, _ in TIERS:
                p = predicted(inv, m, t)
                got = agg(m, t, inv)
                if p is None or got in ("n/a", "not run"):
                    continue
                compared += 1
                if p == got:
                    agree += 1
                else:
                    disagree.append(f"| {inv} | {m} | {t} | {p} | {got} |")
    sec = ["<!-- predictions:begin -->", "## Prediction (docs/07-runtime.md 10.6) against measurement", "",
           f"{compared} cells compared (invariant, mode, tier; a cell is V if violated under G1 or G2). "
           f"{agree} agree, {len(disagree)} disagree. Cells marked n/a in this model are not compared; "
           "PremiseTrueAtSend is not in 10.6 and is not compared.", ""]
    if disagree:
        sec += ["| invariant | mode | tier | predicted | measured |", "|---|---|---|---|---|"] + disagree + [
            "", "Each disagreement is diagnosed in spec/COUNTEREXAMPLES.md or spec/README.md."]
    sec.append("<!-- predictions:end -->")
    block = "\n".join(sec)
    if "<!-- predictions:begin -->" in text:
        text = re.sub(r"<!-- predictions:begin -->.*?<!-- predictions:end -->", lambda m: block, text, flags=re.S)
    else:
        text = text.replace("## State spaces", block + "\n\n## State spaces", 1)
    open(report, "w").write(text)
    print(f"README state table: {len(rows) - 2} jobs; report relabeled")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("finalize")
    sub.add_parser("report")
    one = sub.add_parser("one")
    one.add_argument("base")
    one.add_argument("--module", default=None)
    one.add_argument("--set", action="append", default=[])
    one.add_argument("--inv", action="append", default=[])
    one.add_argument("--prop", action="append", default=[])
    one.add_argument("--workers", default="auto")
    one.add_argument("--peel", action="store_true")
    one.add_argument("--full", action="store_true", help="also print local and history fields")
    s = sub.add_parser("suite")
    s.add_argument("--jobs", type=int, default=3)
    s.add_argument("--only", default=None)
    a = ap.parse_args()
    if a.cmd == "finalize":
        finalize()
        return
    if a.cmd == "one":
        module = a.module or ("Signals" if "Signals" in a.base or "WakeOnly" in a.base else "Runtime")
        invs = [x for i in a.inv for x in i.split(",")]
        name = "one_" + re.sub(r"\W", "_", a.base + "_" + "_".join(a.set + invs + a.prop))[:100]
        job = {"name": name, "module": module, "base": a.base, "set": dict(x.split("=", 1) for x in a.set),
               "inv": invs, "props": a.prop, "peel": a.peel}
        os.environ.setdefault("TLC_WORKERS", a.workers)
        r = run(job)
        skip = () if a.full else ("hist.", "lw.", "sendLog")
        for inv, tr in (r.pop("violations", None) or ({r.get("violated"): r.pop("trace", None)} if r.get("violated") else {})).items():
            print(f"--- {inv}\n{fmt_trace(tr, skip)}")
        r.pop("trace", None)
        print(json.dumps(r, indent=1))
        return
    saved = os.path.join(CFGDIR, "suite_results.json")
    if a.cmd == "report":                        # rebuild the report from saved results and trace dumps
        write_report(rebuild(json.load(open(saved))))
        finalize()
        return
    jobs = [j for j in suite() if not a.only or a.only in j["name"]]
    results = []
    with ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(run, jobs):
            print(f"{r['name']:<48} {r['outcome']:<9} V={sorted(r.get('violations') or ([r['violated']] if r.get('violated') else []))} "
                  f"{r.get('distinct')} {r['wall_s']}s", flush=True)
            results.append(r)
    if a.only and os.path.exists(saved):         # a partial rerun replaces only its own jobs
        fresh = {r["name"]: r for r in results}
        old = json.load(open(saved))
        results = [fresh.pop(r["name"], r) for r in old] + list(fresh.values())
    write_report(rebuild(results))
    finalize()


if __name__ == "__main__":
    main()
