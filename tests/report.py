"""
    python3 tests/report.py

Regenerates tests/README.md from the repo: every test, every experiment, every bug our testing found.
Counts are read from files and from a run of the suite, so the page cannot drift from the code.
Not a test module (the name does not match test*.py), so discovery never picks it up.

Set HARDENING_JOURNAL to the escalation build's workflow journal.jsonl to check the hardening-round
lists below against the fixes each round reported; without it the lists are written unchecked.
"""
import io, json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "README.md")

# Result files use check marks; this page uses the words their own legend gives them.
MARKS = [("\u26a0\ufe0f", "held, availability lost"), ("\u26a0", "held, availability lost"), ("\u2705", "held"),
         ("\u274c", "VIOLATED"), ("\u00b7", "/")]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def words(text):
    for mark, word in MARKS:
        text = text.replace(mark, word)
    return text.replace("\u2014", ":")


def tables(md):
    """Every markdown table in md, as (heading above it, lines)."""
    out, cur, heading = [], [], None
    for line in md.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("# ").strip()
        if line.startswith("|"):
            cur.append(line)
        elif cur:
            out.append((heading, cur)); cur = []
    if cur:
        out.append((heading, cur))
    return out


def headline(md, under=None):
    for heading, lines in tables(md):
        if under is None or heading == under:
            return "\n".join(words(l) for l in lines)
    return None


def quotes(md, pattern, limit=3):
    """Sentences from the results file that say what is real, emulated or assumed, verbatim."""
    blocks, cur = [], []
    for line in md.splitlines():
        t = line.strip()
        if not t or line.startswith(("|", "#", "    ", "```")) or t.startswith("- "):
            if cur:
                blocks.append(" ".join(cur)); cur = []
            if t.startswith("- ") and not line.startswith("    "):
                cur = [t[2:]]
            continue
        cur.append(t)
    if cur:
        blocks.append(" ".join(cur))
    found = []
    for b in blocks:
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z*`])", b)
        for i, s in enumerate(parts):
            if not re.search(pattern, s) or re.search(r"\d\.$", s):
                continue
            if len(s) < 60 and i:
                s = parts[i - 1] + " " + s      # a short sentence needs the one it refers to
            if len(s) >= 300 or any(s in f for f in found):
                continue
            found = [f for f in found if f not in s] + [s]
    found.sort(key=lambda s: not re.search(r"EMULATED|[Nn]othing (is |about \w+ is )?emulated|Emulated:|\bassumption\b|"
                                           r"BLOCKED|No mock|not a model", s))
    return found[:limit]


# ---- tests ---------------------------------------------------------------------------------------

def flat(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from flat(t)
        else:
            yield t


def sentence(name):
    s = name[len("test_"):] if name.startswith("test_") else name
    s = s.replace("_", " ").strip()
    return s[:1].upper() + s[1:] + "."


def run_suite():
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    suite = unittest.defaultTestLoader.discover("tests")
    cases = list(flat(suite))
    broken = [t.id() for t in cases if type(t).__module__ == "unittest.loader"]
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=0, buffer=True).run(suite)
    bad = len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)
    return cases, broken, {
        "run": result.testsRun,
        "skipped": len(result.skipped),
        "failed": bad,
        "passed": result.testsRun - bad - len(result.skipped) - len(result.expectedFailures),
        "python": "%d.%d.%d" % sys.version_info[:3],
    }


def ci():
    y = read(".github/workflows/test.yml")
    versions = re.findall(r'"(\d+\.\d+)"', re.search(r"python-version:\s*\[(.*?)\]", y).group(1))
    steps = re.findall(r"- name: (.+)", y)
    return versions, steps


# ---- experiments ---------------------------------------------------------------------------------

REAL = (r"EMULATED|[Ee]mulated|\bassumption\b|No mock|not a model|[Nn]ot a simulation|test mode|dev server|real SIGKILL|"
        r"real (test-mode|Anthropic|Calendar|model|Stripe|LLM)|[Ee]very .* is a real")

# (script(s), results file, what it tests, how it ran, table heading or None for the first table)
EXPERIMENTS = [
    ("experiments/refund_agent.py (via run_all.py)", "results/refund_agent.md",
     "Whether one approved $20 refund lands exactly once under crashes, duplicates, a re-deciding model, a revoked "
     "approval, a changed order and an expired idempotency key, for a naive agent, idempotency keys, durable "
     "execution and the gate at tiers 1 to 3.",
     "Simulated in process: an in-memory payments service and injected `SimulatedCrash` faults; no network.", None),
    ("experiments/coding_agents.py (via run_all.py)", "results/coding_agents.md",
     "Whether two parallel coding agents can land a change that breaks at runtime, duplicates work, or lands under "
     "a revoked lease, with no gate, a file-hash gate and a symbol gate.",
     "Simulated in process: two scripted agents on a temporary repo, injected `SimulatedCrash` faults; the code B "
     "added is executed.", None),
    ("experiments/stripe_live.py", "results/stripe_live.md",
     "The refund faults from the refund agent experiment against real Stripe in test mode.",
     "Real: Stripe test-mode API calls, one new payment per row.", None),
    ("experiments/temporal_live.py", "results/temporal_live.md",
     "Whether Temporal's own retry policy, with the idempotency key its docs recommend, refunds correctly when the "
     "facts change during a worker outage, with and without Interlock as the activity body.",
     "Real Temporal dev server and retries; the refund target is the in-process payments service.", None),
    ("experiments/e2e_live.py", "results/e2e_live.md",
     "A real LLM refund agent on a real Temporal server against Stripe test mode, with workers killed by SIGKILL, "
     "comparing plain Temporal, Temporal plus a hand-written re-check, and Interlock.",
     "Real: Stripe test mode, Anthropic model calls, Temporal, SIGKILL. Two rows are EMULATED (a pruned idempotency "
     "key).", None),
    ("experiments/approval_inbox.py", "results/approval_inbox.md",
     "Of a synthetic day of refund requests, how many still need a person, and how many are refunded the wrong "
     "amount, with everyone approving, rules only, and rules plus Interlock.",
     "Simulated: a synthetic day whose mix is an assumption, not measured data.", None),
    ("experiments/repair_loop.py", "results/repair_loop.md",
     "Whether an agent told what changed and what the approval leaves can repair a refused refund without paying "
     "out wrong.",
     "Simulated: a scripted agent loop, not a model; the mix is an assumption.", None),
]

SCENARIOS = [
    ("stripe_dispute", "A refund decided before a chargeback opens during the worker outage, Stripe test mode.", None),
    ("shared_cap", "Two agents sharing one $30 approval cap on one Stripe test payment.", None),
    ("billing_credit", "A goodwill credit against a Stripe Billing renewal on test clocks.", None),
    ("github_merge", "Merging a reviewed PR after a human pushed to its branch during the outage, live GitHub.", None),
    ("calendar", "Double booking a slot on a real Google Calendar.", None),
    ("email_tier3", "An email that cannot be undone, sent through live Resend after a Stripe refund.", "Results"),
    ("gcp_resource", "Rolling back a live GCS config object that a human redeployed during the outage.", None),
    ("connect_payout", "A marketplace seller payout through Stripe Connect.", None),
]


def scenario_totals(readme):
    """Per system family, invariant held summed over cells, from results/scenarios/README.md."""
    rows, name = [], None
    for heading, lines in tables(readme):
        if heading != "Results":
            continue
        for line in lines[2:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            name = cells[0] or name
            m = re.match(r"(\d+)/(\d+)", cells[2])
            rows.append((name, cells[1], (int(m.group(1)), int(m.group(2))) if m else None))
    scenarios = sorted({r[0] for r in rows})
    ran = sorted({r[0] for r in rows if r[2]})
    fam = {"no_check": lambda s: s == "no_check", "hand": lambda s: s.startswith("hand_"),
           "interlock": lambda s: s.startswith("interlock")}
    tot = {}
    for key, match in fam.items():
        best, allv = [0, 0], [0, 0]
        for sc in ran:
            arms = [r[2] for r in rows if r[0] == sc and match(r[1].split(" ")[0]) and r[2]]
            if not arms:
                continue
            b = max(arms, key=lambda a: a[0] / a[1])
            best[0] += b[0]; best[1] += b[1]
            for a in arms:
                allv[0] += a[0]; allv[1] += a[1]
        tot[key] = (best, allv)
    return scenarios, ran, tot


# ---- bugs ----------------------------------------------------------------------------------------

BEFORE = [
    "Recovery resent an action without re-checking premises or the lease.",
    "A duplicate submission could resend an action whose outcome was still unresolved.",
    "Concurrent workers could dispatch the same action twice.",
    "An agent retrying after a refusal was checked against freshly read facts instead of the ones it decided on.",
    "A SQLite lock could make a concurrent worker lose its request.",
    "The approval inbox crashed reconciling after a crash.",
    "Critical: a recovery running while a send was still being applied could send it a second time.",
    "Recovery re-checked the wrong lease.",
    "A payload could win a race against the recorded decision.",
    "The MCP proxy could leave a call unanswered.",
    "One failing effect could stop recovery of the rest.",
    "Same-named functions shared a journal.",
    "A torn journal line stopped the gate.",
    "The Temporal helper reported an unsettled attempt as done.",
    "`verify()` accepted a forged lone commit.",
]

ROUNDS = {
    "fix:r1": [
        "A person's send could go out on facts they had not seen; dispatch now requires the latest escalation's facts.",
        "A lease naming a different group could send, so an approver removed from the routed group could still send.",
        "`explain` described an AMBIGUOUS status with a later conflicting_payload refusal.",
        "A restarted inbox lost the stale_premise reason and its still_fits repair.",
        "A retry with a different amount re-routed the escalation on the retry instead of the request bound in the journal.",
        "Resubmitting a different amount changed what the approval queue showed.",
        "A late, lower-ranked Stripe confirmation could overwrite a later status in receipts and the scoreboard.",
        "The scoreboard counted a superseded repair re-escalation as a second escalation and a second crash case.",
        "A late `succeeded` after `failed` was accepted and read as confirmed by the target.",
        "Same root cause as the first: an approved send could dispatch on re-read facts the approver never saw.",
        "Same root cause as the second: a group mismatch between lease and escalation was not refused at dispatch.",
        "After a commit, a webhook could confirm a refund id other than the one the commit recorded.",
        "Repairs computed on old facts were shown again after a restart, allowing a refund past the order total.",
        "An honest in-flight resend confirmed by a webhook failed `verify()` as never landed.",
        "The approval inbox results read as a double count of escalations (27 against 26); the counts were right and the label was rewritten.",
        "Same root cause as the out-of-order confirmation: a late `pending` after `succeeded` was recorded.",
        "`verify()` raised instead of reporting an altered receipt when an entry lacked `kind` or `hash`.",
    ],
    "fix:r2": [
        "The MCP proxy settled a failed send that belonged to another call, and returned IN_FLIGHT with nothing journaled.",
        "The backend Temporal workflow no longer reported AMBIGUOUS runs as AMBIGUOUS.",
        "After a crash, the inbox decided on re-read facts instead of the facts saved in the PROPOSED entry.",
        "One step raising in `refresh` or `reconcile` stopped the inbox from starting and other escalations from being written.",
        "One capture raising in `tick` stopped SLA moves for every other item.",
        "`tick` kept a due time when the route no longer had an SLA.",
        "`StripeRefunds.explain` skipped premise checks a subclass added, so a refund could go out.",
        "The README's approval inbox numbers disagreed with results/approval_inbox.md.",
    ],
    "fix:r3": [
        "A retry refused after an AMBIGUOUS entry cleared the item's ambiguous guard.",
        "A send the target turned down was not settled, so it could be sent again instead of going to a person.",
        "A second inbox's stale cached approval could override a newer decision and send.",
        "After an outage, `tick` recorded SLA breaches at the wrong times instead of each missed deadline.",
        "Webhook confirmation checked the refund against the caller's payment instead of the one the send recorded.",
        "`Inbox.cleared` counted repair children and disagreed with the scoreboard's cleared_no_person.",
        "The README's split of extra reviews into gate refusals and repair decisions was wrong.",
        "The scoreboard counted the instant approval of a repair child as a person's decision time.",
    ],
}

MERGE = [
    "A settled REFUSED:target_error could be dispatched again without a person's escalation; `verify()` now flags a send after one.",
    "The MCP proxy treated an upstream that exits mid-call as the tool saying no instead of outcome unknown.",
    "Under an approval, the same arguments after a refusal reused the effect id, so the re-decision was not checked on current facts.",
    "`_FunctionTarget.explain` read premises twice and did not record the structured change.",
    "`tools.WHY` lost its status keys, so REFUSED:lease no longer said no live approval covers it.",
    "Public names from before the merge were lost (`tools.repair` by effect id, mcp_proxy helpers, `.key` on gated tools).",
]


def check_bugs():
    readme = read("README.md")
    n = int(re.search(r"found (\d+) real bugs", readme).group(1))
    assert n == len(BEFORE), (n, len(BEFORE))
    merge_cases = len(re.findall(r"^class \w+\(unittest\.TestCase\)", read("tests/test_merge_defects.py"), re.M))
    assert merge_cases == len(MERGE), (merge_cases, len(MERGE))
    path = os.environ.get("HARDENING_JOURNAL")
    if not path:
        print("HARDENING_JOURNAL unset: hardening-round lists not checked against the journal", file=sys.stderr)
        return n
    labels, fixed = {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("type") == "started":
                labels[e["key"]] = e.get("label")
            elif e.get("type") == "result" and labels.get(e.get("key")) in ROUNDS:
                r = e["result"] if isinstance(e["result"], str) else json.dumps(e["result"])
                fixed[labels[e["key"]]] = len(re.findall(r"^\d+\. [Ff]ixed", r, re.M))
    for k, v in ROUNDS.items():
        assert fixed.get(k) == len(v), (k, fixed.get(k), len(v))
    return n


# ---- page ----------------------------------------------------------------------------------------

def main():
    cases, broken, res = run_suite()
    assert not broken, broken
    versions, steps = ci()
    before = check_bugs()
    inbox = read("results/approval_inbox.md")
    board = dict((c[0].strip(), c[1].strip()) for c in
                 (l.strip("|").split("|") for l in dict(tables(inbox))["Scoreboard (derived from the journal)"][2:]))
    requests, cleared = int(board["requests (unique)"]), int(board["cleared with no person"])
    verified = int(board["of those, receipts that verify"])
    scen_readme = read("results/scenarios/README.md")
    scenarios, ran, tot = scenario_totals(scen_readme)
    stripe_files = ["results/stripe_live.md", "results/e2e_live.md"] + \
        ["results/scenarios/%s.md" % k for k in ("stripe_dispute", "shared_cap", "billing_credit", "email_tier3")]
    ids = set()
    per_file = {}
    for p in stripe_files:
        found = set(re.findall(r"\b(?:pi|sub)_[A-Za-z0-9]{10,}", read(p)))
        per_file[p] = len(found); ids |= found
    audit = read("results/e2e_audit.txt").strip().splitlines()
    audit_line = audit[-1]

    o = []
    w = o.append
    w("# Tests and experiments\n")
    w("Generated by `python3 tests/report.py`; do not edit by hand. Every number here is read from the repo or from "
      "the suite run that produced this page, on Python %s.\n" % res["python"])

    w("## Numbers you can quote\n")
    w("- Tests: %d in %d files; %d passed, %d skipped, %d failed (Python %s)." %
      (res["run"], len({t.id().split(".")[0] for t in cases}), res["passed"], res["skipped"], res["failed"], res["python"]))
    w("- CI runs the suite on Python %s on every push and pull request, and fails if `results/` drifts from the code." %
      ", ".join(versions))
    w("- Live Stripe test-mode runs: %d Stripe test-mode payments and subscriptions recorded (unique `pi_` and `sub_` ids) across "
      "%d results files; the end-to-end audit reports \"%s\"." % (len(ids), len(stripe_files), audit_line))
    w("- Real-world scenarios: %d written, %d ran against live services, %d blocked. Invariant held, summed over the "
      "cells of the %d that ran: the standard setup (no_check) %d/%d; the strongest hand-written check %d/%d; the "
      "strongest Interlock arm %d/%d (in two scenarios only with code outside the core, per "
      "results/scenarios/README.md); every Interlock variant together %d/%d." %
      (len(scenarios), len(ran), len(scenarios) - len(ran), len(ran), tot["no_check"][1][0], tot["no_check"][1][1],
       tot["hand"][0][0], tot["hand"][0][1], tot["interlock"][0][0], tot["interlock"][0][1],
       tot["interlock"][1][0], tot["interlock"][1][1]))
    w("- Goal: cut two thirds of manual agent approvals. Synthetic day (the mix is an assumption, not measured data): "
      "%d of %d requests (%.1f%%) cleared with no person, %d of those with receipts that verify." %
      (cleared, requests, 100.0 * cleared / requests, verified))
    w("- Bugs found by our own testing and reviews and fixed, each with a test: %d before the escalation build, %d in "
      "its three adversarial hardening rounds, %d in the merge review." %
      (before, sum(len(v) for v in ROUNDS.values()), len(MERGE)))
    w("")

    # tests
    w("## 1. Unit and integration tests\n")
    w("Run with `python3 -m unittest discover -s tests`. Stdlib only.\n")
    w("CI (`.github/workflows/test.yml`): a matrix over Python %s with `fail-fast: false`. Steps: %s. The last step "
      "reruns `experiments/run_all.py` and `viewer/build.py`, then `git diff --exit-code` on `results/`, so a results "
      "table that no longer matches the code fails the build.\n" % (", ".join(versions), "; ".join('"%s"' % s for s in steps)))
    w("Last run: %d tests, %d passed, %d skipped, %d failed, on Python %s.\n" %
      (res["run"], res["passed"], res["skipped"], res["failed"], res["python"]))
    mods = {}
    for t in cases:
        mod, cls, meth = t.id().rsplit(".", 2)
        mods.setdefault(mod, {}).setdefault(cls, []).append(t)
    w("| file | tests |\n|---|---|")
    for mod in sorted(mods):
        w("| `tests/%s.py` | %d |" % (mod.split(".")[-1], sum(len(v) for v in mods[mod].values())))
    w("| total | %d |\n" % len(cases))
    for mod in sorted(mods):
        doc = (sys.modules.get(mod).__doc__ or "") if sys.modules.get(mod) else ""
        paras = [" ".join(l.strip() for l in p.splitlines()) for p in re.split(r"\n\s*\n", doc)]
        first = next((p for p in paras if p.strip() and not p.strip().startswith("python")), "").strip()
        w("### `tests/%s.py` (%d)\n" % (mod.split(".")[-1], sum(len(v) for v in mods[mod].values())))
        if first:
            w(words(first) + "\n")
        for cls in sorted(mods[mod]):
            w("**%s** (%d)\n" % (cls, len(mods[mod][cls])))
            for t in mods[mod][cls]:
                meth = getattr(t, t._testMethodName)
                d = (meth.__doc__ or "").strip().splitlines()
                w("- `%s`: %s" % (t._testMethodName, words(d[0]) if d else sentence(t._testMethodName)))
            w("")

    # experiments
    w("## 2. Experiments and live runs\n")
    w("Tables are copied from each results file; its check marks are written as words (held, VIOLATED, held, "
      "availability lost) and its middle-dot separators as `/`. Real Stripe ids are as they appear there.\n")
    for script, res_file, what, how, under in EXPERIMENTS:
        md = read(res_file)
        w("### %s\n" % script.split("/")[-1].split(" ")[0][:-3])
        w("- Script: `%s`" % script.split(" ")[0])
        w("- Tests: %s" % what)
        w("- Ran: %s" % how)
        for q in quotes(md, REAL):
            w("- Results file says: \"%s\"" % words(q))
        w("- Full results: [`%s`](../%s)\n" % (res_file, res_file))
        w(headline(md, under) + "\n")
        if res_file == "results/e2e_live.md":
            w("### e2e_audit\n")
            w("- Script: `experiments/e2e_audit.py`")
            w("- Tests: an independent check of `results/e2e_live.json` against Stripe itself, trusting nothing in the "
              "file and using none of the repo's code.")
            w("- Ran: real Stripe test-mode reads.")
            w("- Full results: [`results/e2e_audit.txt`](../results/e2e_audit.txt)\n")
            w("```\n" + "\n".join(audit) + "\n```\n")
    if os.path.exists(os.path.join(ROOT, "results/escalation_live.md")):
        md = read("results/escalation_live.md")
        w("### escalation_live\n")
        for q in quotes(md, REAL):
            w("- Results file says: \"%s\"" % words(q))
        w("- Full results: [`results/escalation_live.md`](../results/escalation_live.md)\n")
        w((headline(md) or "") + "\n")

    w("### Real-world scenario suite (`experiments/scenario_*.py`)\n")
    w("Each scenario runs one agent step against the standard setup, a fair hand-written check and Interlock, with a "
      "real SIGKILL and ground truth read back from the live service. Offline logic for each is in "
      "`tests/test_scenario_<key>.py`. Summary: [`results/scenarios/README.md`](../results/scenarios/README.md).\n")
    w(headline(scen_readme, "Results") + "\n")
    for key, what, under in SCENARIOS:
        rel = "results/scenarios/%s.md" % key
        md = read(rel)
        w("#### %s\n" % key)
        w("- Script: `experiments/scenario_%s.py`" % key)
        w("- Tests: %s" % what)
        for q in quotes(md, REAL + r"|BLOCKED"):
            w("- Results file says: \"%s\"" % words(q))
        w("- Full results: [`%s`](../%s)\n" % (rel, rel))
        t = headline(md, under)
        if t:
            w(t + "\n")

    # bugs
    w("## 3. Bugs found by testing\n")
    w("Every fix below has a test in `tests/` that failed before the fix.\n")
    w("### Before the escalation build (%d, from README.md)\n" % before)
    w("The first six were found writing the tests; the other nine by an adversarial review of the package.\n")
    for i, b in enumerate(BEFORE, 1):
        w("%d. %s" % (i, b))
    w("")
    w("### Escalation build, adversarial hardening rounds (%d)\n" % sum(len(v) for v in ROUNDS.values()))
    w("Each round, reviewers hunted for defects, each was reproduced, and the fixer reported it fixed. Regression "
      "tests: `tests/test_escalation_fixes.py`.\n")
    for k, v in ROUNDS.items():
        w("**Round %s (%d)**\n" % (k[-1], len(v)))
        for i, b in enumerate(v, 1):
            w("%d. %s" % (i, b))
        w("")
    w("### Merge review (%d reproduced, all fixed)\n" % len(MERGE))
    w("Found reviewing the merge of origin/main into the escalation build. Regression tests: "
      "`tests/test_merge_defects.py`.\n")
    for i, b in enumerate(MERGE, 1):
        w("%d. %s" % (i, b))
    w("")

    page = "\n".join(o)
    assert "\u2014" not in page
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("wrote %s: %d tests, %d passed" % (os.path.relpath(OUT, ROOT), res["run"], res["passed"]))
    return 0 if res["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
