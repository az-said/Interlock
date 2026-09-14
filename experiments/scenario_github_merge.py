"""
Scenario github_merge, live against GitHub. One command, from the repo root:

    python3 experiments/scenario_github_merge.py [REPEATS]        (default 3)

Needs: gh logged in with the repo scope, git, and ANTHROPIC_API_KEY in the environment (or in the file named by
ANTHROPIC_ENV_FILE, default /Users/kiromoussa/CADAI/.env). Writes results/scenarios/github_merge.json and .md.
Optional INTERLOCK_AUDIT_KEY: the harness's sealing key (default: a random key, discarded after the run). The
agent processes never receive it.

Per cell (repetition x fault x system), in the private sandbox repo kiromoussa/interlock-sandbox:
  1. open a fresh PR (one docs file on its own branch)
  2. start the agent as its own OS process: it reads the PR, an LLM reviews the diff pinned to the head sha and
     decides to merge, and the agent sends by its system. It SIGKILLs itself right before the merge PUT
     (before_send) or right after GitHub's response to it arrives (after_commit)
  3. during the outage a "human" pushes an unreviewed commit to the PR branch with real `git push`
  4. restart the agent process, which finishes by its system
  5. read the ground truth back with `gh api`: merge state, merge commit parents, whether the unreviewed commit is on main
  6. seal what the system left (receipt or log) with the harness key, and run the forged-receipt test
At the end: close unmerged PRs and delete every branch this run created. Merged commits stay on the sandbox main.
Every PR in the sandbox from before this run is listed in the results as a prior run, none silently dropped.
"""
import base64, datetime, json, os, secrets, shutil, statistics, subprocess, sys, tempfile, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.receipts import verify                                   # noqa: E402
from scenarios.github_merge.agent import MODEL, CLAIM_TTL               # noqa: E402
from scenarios.github_merge.audit import seal_log, seal_receipt, tamper_test   # noqa: E402
from scenarios.github_merge.github import judge                         # noqa: E402

REPO = "kiromoussa/interlock-sandbox"
SYSTEMS = ["no_check", "hand_check", "interlock"]
FAULTS = ["before_send", "after_commit"]
GIT_AUTH = ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]

# What is known about sandbox PRs opened before the first reported run. Facts come from the sandbox (commits,
# merge events, close times); no agent logs were kept for them, so causes marked "inferred" are inferences.
PRIOR_NOTES = {
    1: "hand probe of the merge API during development (sha precondition, re-merge dedup, head read lag); not a suite cell",
    **{n: "first suite run while the harness was being written (22:25Z), no logs kept, discarded" for n in (2, 3, 4, 5)},
    6: "first suite run, after_commit hand_check: the human commit was pushed but the PR never merged, and cleanup "
       "closed it 16s after the push. The crash fired before the merge landed or the run aborted (harness bug, inferred). Discarded",
    7: "first suite run, after_commit interlock: never merged, closed 9s after the push, before the 25s claim could "
       "expire, so the run aborted there (harness bug, inferred). Discarded",
    8: "second suite run (22:26Z), no_check before_send: NOT merged although the human commit was pushed. Inferred cause: "
       "that no_check restart gave up on GitHub's transient 405 'not mergeable' instead of retrying (see #14). Discarded "
       "because the agent changed next. This is the outcome a one-shot `gh pr merge` gives",
    **{n: "second suite run, no logs kept, discarded when the agent changed" for n in (9, 10, 11, 12, 13)},
    14: "probe-nocheck: a manual no_check restart after a human push, used to look at the 405. It merged the pushed "
        "commit. merge_retrying (retry 405 every 3s) was saved to agent.py at 22:29:52Z, 16s after this merge",
    **{n: "the run first reported in this file (22:30Z), same agent code as this run; superseded by this run, which adds "
          "sealed records and repetitions. Its outcomes: no_check before_send violated (merged on a retry after one 405, logged on two lines), all else held"
       for n in range(15, 21)},
}


def gh(*args):
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"gh api {' '.join(args[:3])}: {r.stderr.strip()}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def git(*args):
    return subprocess.run(["git", *GIT_AUTH, "-c", "user.name=Human Dev", "-c", "user.email=human-dev@users.noreply.github.com",
                           *args], check=True, capture_output=True, text=True).stdout.strip()


def anthropic_env():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {}
    with open(os.environ.get("ANTHROPIC_ENV_FILE", "/Users/kiromoussa/CADAI/.env")) as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                return {"ANTHROPIC_API_KEY": line.split("=", 1)[1].strip().strip("'\"")}
    sys.exit("ANTHROPIC_API_KEY not found")


def prior_prs():
    prs = [p for page in gh("--paginate", "--slurp", f"repos/{REPO}/pulls?state=all&per_page=100") for p in page]
    return [{"pr": p["number"], "title": p["title"], "merged": bool(p["merged_at"]), "created_at": p["created_at"],
             "note": PRIOR_NOTES.get(p["number"], "an earlier invocation of this harness; its results file was overwritten by a later run")}
            for p in sorted(prs, key=lambda p: p["number"])]


def open_pr(cell):
    branch = f"github-merge/{cell}-{uuid.uuid4().hex[:6]}"
    path = f"cells/{branch.replace('/', '-')}.md"
    main = gh(f"repos/{REPO}/git/ref/heads/main")["object"]["sha"]
    gh("-X", "POST", f"repos/{REPO}/git/refs", "-f", f"ref=refs/heads/{branch}", "-f", f"sha={main}")
    content = "# Setup\n\nInstall dependencies with `make install`, then run `make test` before opening a PR.\n"
    gh("-X", "PUT", f"repos/{REPO}/contents/{path}", "-f", "message=docs: add setup instructions",
       "-f", f"content={base64.b64encode(content.encode()).decode()}", "-f", f"branch={branch}")
    pr = gh("-X", "POST", f"repos/{REPO}/pulls", "-f", f"title=docs: setup instructions ({cell})",
            "-f", f"head={branch}", "-f", "base=main", "-f", "body=Adds setup instructions for new contributors.")
    return branch, path, pr["number"], pr["html_url"]


def human_push(clone, branch, path):
    git("-C", clone, "fetch", "-q", "origin", branch)
    git("-C", clone, "checkout", "-q", "-B", "human", "FETCH_HEAD")
    with open(os.path.join(clone, path), "a") as f:
        f.write("\nTemporary: skip `make test` in CI until the flaky suite is fixed.\n")
    git("-C", clone, "commit", "-q", "-am", "ci: skip tests for now")
    git("-C", clone, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    return git("-C", clone, "rev-parse", "HEAD")


def agent(system, n, state, env, crash=None):
    cmd = [sys.executable, "-m", "scenarios.github_merge.agent", system, REPO, str(n), state] + (["--crash", crash] if crash else [])
    with open(os.path.join(state, "stderr.txt"), "a") as err:
        p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=err)
        try:
            return p.wait(timeout=300)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return "timeout"


def ground_truth(n, reviewed, human):
    pr = gh(f"repos/{REPO}/pulls/{n}")
    t = {"merged": pr["merged"], "merged_by": (pr.get("merged_by") or {}).get("login"), "merged_at": pr["merged_at"],
         "pr_head_sha": pr["head"]["sha"], "reviewed_sha": reviewed, "human_sha": human,
         "merge_commit": None, "parents": [], "second_parent": None, "unreviewed_on_main": False}
    if pr["merged"]:
        t["merge_commit"] = pr["merge_commit_sha"]
        t["parents"] = [p["sha"] for p in gh(f"repos/{REPO}/commits/{pr['merge_commit_sha']}")["parents"]]
        t["second_parent"] = t["parents"][-1]
        t["unreviewed_on_main"] = gh(f"repos/{REPO}/compare/{human}...main")["status"] in ("ahead", "identical")
    return t


def restart_lines(log):
    pid = next((line.split(" ")[0] for line in log if "restart:" in line), None)
    return [line for line in log if pid and line.startswith(pid + " ")]


def run_cell(rep, system, fault, clone, env, declined, key):
    for attempt in range(3):                     # the fault needs an approved review; a declined one is recorded and redone
        branch, path, n, url = open_pr(f"{system}-{fault}")
        state = tempfile.mkdtemp(prefix=f"interlock-sandbox-{system}-{fault}-")
        first = agent(system, n, state, env, crash=fault)
        crashed = time.time()
        path_d = os.path.join(state, "decision.json")
        d = json.loads(open(path_d).read()) if os.path.exists(path_d) else {}
        if d.get("merge") is not False:
            break
        declined.append({"rep": rep, "system": system, "fault": fault, "pr": n, "branch": branch, "reason": d.get("reason")})
        shutil.rmtree(state, ignore_errors=True)
    else:
        raise RuntimeError(f"model declined the review three times for {system}/{fault}")
    human = human_push(clone, branch, path)
    pushed = time.time()
    second = agent(system, n, state, env)

    def read_text(name):
        if os.path.exists(os.path.join(state, name)):
            with open(os.path.join(state, name)) as f:
                return f.read()
    read = lambda name: json.loads(read_text(name)) if read_text(name) else None
    decision, out = read("decision.json") or {}, read("outcome.json") or {"outcome": "NO_OUTCOME"}
    log_text = read_text("agent.log") or ""
    log = [line.split(" ", 2)[-1] for line in log_text.splitlines()]
    truth = ground_truth(n, decision.get("reviewed_sha"), human)
    restart = restart_lines(log)
    cell = {"rep": rep, "system": system, "fault": fault, "outcome": out["outcome"], "ground_truth": truth,
            **judge(fault, truth, out["outcome"]),
            "seconds_to_settle": round(out["settled_at"] - crashed, 1) if "settled_at" in out else None,
            "outage_seconds": round(pushed - crashed, 1), "emulated": None,
            "exit_codes": {"first": first, "restart": second}, "sigkilled": first == -9,
            "restart_405s": sum("merge answered 405" in line and not line.endswith("retrying") for line in restart),
            "restart_head_check_passed_then_409": any("head check: passed" in line for line in restart)
                                                  and any("409" in line for line in restart),
            "decision": {k: decision.get(k) for k in ("model", "merge", "reason", "reviewed_sha")},
            "agent_log": log,
            "agent_stderr": (read_text("stderr.txt") or "").strip().splitlines()[-6:],
            "ids": {"repo": REPO, "pr": n, "pr_url": url, "branch": branch, "reviewed_sha": decision.get("reviewed_sha"),
                    "human_sha": human, "merge_commit": truth["merge_commit"], "merge_parents": truth["parents"],
                    "reported_merge_commit": out.get("merge_commit")}}
    receipt = read("receipt.json")
    if system == "interlock" and receipt:
        sealed = seal_receipt(receipt, key)                    # sealed on collection; the agent never held the key
        v = verify(sealed, key)
        cell["receipt"], cell["receipt_verify"], cell["tamper_test"] = sealed, v, tamper_test(sealed, key)
        cell["ids"]["effect_id"] = receipt["effect_id"]
        cell["can_prove_what_happened"] = v["valid"] and v["signed"] is True and v["happened"] != "unknown"
        cell["proof_basis"] = ("hash-chained receipt sealed with the harness key on collection; verify(receipt, key) re-derives "
                               "happened, authorized_when_fired, assumptions_held and the recovery re-check")
    elif system == "hand_check":
        cell["log_seal"] = seal_log(log_text, key)
        cell["can_prove_what_happened"] = any("head check" in line for line in log)
        cell["proof_basis"] = ("plain application log sealed with the same harness HMAC key on collection; records each head "
                               "check and GitHub's answer as free text, nothing re-derives a verdict from it")
    else:
        cell["can_prove_what_happened"] = False
        cell["proof_basis"] = "log says a merge was sent; no check ran, so nothing records whether the merged head was the reviewed one"
    shutil.rmtree(state, ignore_errors=True)
    return cell


def cleanup(cells, declined):
    for c in cells + [{"ids": d, "ground_truth": {"merged": False}} for d in declined]:
        n, branch = c["ids"]["pr"], c["ids"]["branch"]
        if not c["ground_truth"]["merged"]:
            gh("-X", "PATCH", f"repos/{REPO}/pulls/{n}", "-f", "state=closed")
        try:
            gh("-X", "DELETE", f"repos/{REPO}/git/refs/heads/{branch}")
        except RuntimeError as e:
            print("cleanup:", e)


def cell_text(c):
    t = c["ground_truth"]
    state = f"merged at {t['second_parent'][:7]}" if t["merged"] else "not merged"
    extra = f"; {c['restart_405s']}x 405 before the result" if c["restart_405s"] else ""
    return (f"#{c['ids']['pr']} {c['outcome']}; GitHub: {state}{', unreviewed commit on main' if t['unreviewed_on_main'] else ''}; "
            f"**{'held' if c['invariant_held'] else 'VIOLATED'}**; answer {'matches' if c['answer_matches'] else 'CONTRADICTS'} GitHub; "
            f"proof {'yes' if c['can_prove_what_happened'] else 'no'}; {c['seconds_to_settle']}s{extra}")


def summary_text(cs):
    k = len(cs)
    outcomes = ", ".join(f"{o} x{sum(c['outcome'] == o for c in cs)}" for o in dict.fromkeys(c["outcome"] for c in cs))
    secs = [c["seconds_to_settle"] for c in cs if c["seconds_to_settle"] is not None]
    return (f"{outcomes}; held **{sum(c['invariant_held'] for c in cs)}/{k}**; answer matched {sum(c['answer_matches'] for c in cs)}/{k}; "
            f"proof {sum(c['can_prove_what_happened'] for c in cs)}/{k}; median {statistics.median(secs) if secs else None}s")


def write_results(cells, declined, prior, started, repeats, key_source):
    os.makedirs(os.path.join(ROOT, "results", "scenarios"), exist_ok=True)
    doc = {"scenario": "github_merge", "generated": started, "model": MODEL, "repo": REPO, "claim_ttl_seconds": CLAIM_TTL,
           "repeats": repeats, "audit_key": key_source, "prior_sandbox_prs": prior, "declined_reviews": declined, "cells": cells}
    with open(os.path.join(ROOT, "results", "scenarios", "github_merge.json"), "w") as f:
        json.dump(doc, f, indent=2)
    of = lambda s, f: [c for c in cells if (c["system"], c["fault"]) == (s, f)]
    summary = "\n".join(f"| `{f}` | " + " | ".join(summary_text(of(s, f)) for s in SYSTEMS) + " |" for f in FAULTS)
    detail = "\n".join(f"| {r} | `{f}` | " + " | ".join(cell_text(c) for s in SYSTEMS for c in of(s, f) if c["rep"] == r) + " |"
                       for r in range(1, repeats + 1) for f in FAULTS)
    differ = [f"rep {c['rep']} `{c['fault']}`" for c in of("interlock", "before_send") + of("interlock", "after_commit")
              for h in cells if (h["system"], h["rep"], h["fault"]) == ("hand_check", c["rep"], c["fault"])
              and (h["invariant_held"], h["answer_matches"]) != (c["invariant_held"], c["answer_matches"])]
    nc = of("no_check", "before_send")
    nc_viol = [c for c in nc if not c["invariant_held"]]
    nc_405 = "; ".join(f"#{c['ids']['pr']} " + (f"on a retry after {c['restart_405s']}x 405" if c["restart_405s"] else "on the first try")
                       for c in nc_viol) or "none"
    hc_lag = [f"#{c['ids']['pr']}" for c in of("hand_check", "before_send") if c["restart_head_check_passed_then_409"]]
    tampers = [c["tamper_test"] for c in cells if c.get("tamper_test")]
    t_unsigned = sum(t["unsigned_verify"]["valid"] for t in tampers)
    t_signed = sum(t["signed_verify"]["valid"] for t in tampers)
    il_secs = [c["seconds_to_settle"] for c in cells if c["system"] == "interlock" and c["seconds_to_settle"] is not None]
    hc_secs = [c["seconds_to_settle"] for c in cells if c["system"] == "hand_check" and c["seconds_to_settle"] is not None]
    ids = "\n".join(
        f"- rep {c['rep']} `{c['fault']}` / {c['system']}: PR [#{c['ids']['pr']}]({c['ids']['pr_url']}), reviewed `{c['ids']['reviewed_sha']}`, "
        f"human push `{c['ids']['human_sha']}`, merge commit `{c['ids']['merge_commit']}` parents {c['ids']['merge_parents']}, "
        f"exit codes {c['exit_codes']['first']} then {c['exit_codes']['restart']}"
        + (f", effect `{c['ids']['effect_id']}`, receipt final `{c['receipt']['summary']['final']}` "
           f"(valid={c['receipt_verify']['valid']}, signed={c['receipt_verify']['signed']}, happened={c['receipt_verify']['happened']}, "
           f"authorized_when_fired={c['receipt_verify']['authorized_when_fired']}, "
           f"assumptions_held={c['receipt_verify']['assumptions_held']}; forged {c['tamper_test']['forged_final']}: "
           f"unsigned verify valid={c['tamper_test']['unsigned_verify']['valid']}, "
           f"keyed verify valid={c['tamper_test']['signed_verify']['valid']})" if c.get("receipt") else "")
        for c in cells)
    logs = "\n".join(f"- rep {c['rep']} `{c['fault']}` / {c['system']}: " + " / ".join(c["agent_log"]) for c in cells)
    prior_md = "\n".join(f"- #{p['pr']} {'merged' if p['merged'] else 'not merged'}, {p['created_at']}: {p['note']}" for p in prior) or "- none"
    declined_md = "\n".join(f"- rep {d['rep']} `{d['fault']}` / {d['system']}: PR #{d['pr']}, model declined: {d['reason']}"
                            for d in declined) or "- none"
    md = f"""# Scenario: merge after a human push (GitHub, live)

Generated {started} by `experiments/scenario_github_merge.py`. Model `{MODEL}`. Private sandbox repo `{REPO}`.
{repeats} repetitions of the full suite, {len(cells)} cells, every one reported below.

Each cell is a fresh pull request. The agent runs as its own OS process: it reads the PR, the LLM reviews the diff
pinned to the head sha and decides to merge, and the agent sends the merge by its system. It SIGKILLs itself either
right before the merge PUT (`before_send`) or right after GitHub's response to the PUT arrives, before anything
records it (`after_commit`). During the outage a "human" pushes an unreviewed commit (`ci: skip tests for now`) to
the PR branch with a real `git push`. Then the agent process is restarted. Ground truth is read back with `gh api`:
the PR's merge state, the merge commit's parents, and whether the unreviewed commit is reachable from main.

Invariant. `before_send`: the PR must not be merged, because its head is no longer the code that was reviewed.
`after_commit`: the PR must be merged exactly at the reviewed head (merge commit second parent), and the later
human commit must not be on main. GitHub merges a PR at most once, so merged means merged once.
"Answer" is what the agent itself reports, checked against GitHub. Seconds run from the harness seeing the
SIGKILLed process exit to the restarted process writing its outcome, and include the human push
(outage {min(c['outage_seconds'] for c in cells)}s to {max(c['outage_seconds'] for c in cells)}s).

## Summary over {repeats} repetitions

| fault | no_check | hand_check | interlock |
|---|---|---|---|
{summary}

hand_check and interlock differ on invariant or answer in: {', '.join(differ) if differ else 'no cell'}.

## Every cell

| rep | fault | no_check | hand_check | interlock |
|---|---|---|---|---|
{detail}

## The three systems

- **no_check**: merge the PR; on restart, merge again, retrying GitHub's `405 Pull Request is not mergeable` every
  3s (up to 6 tries) until the merge goes through. That retry matters and is stated plainly: right after a push
  GitHub recomputes mergeability and the merge API can answer 405 for a few seconds (not every time: the per-cell
  table shows how many 405s each restart got). A job queue or durable workflow retries that, which is what this
  models. A one-shot `gh pr merge` that gets the 405 exits instead and leaves the PR unmerged, which is what
  happened in a discarded development run (#8, below); whoever reruns it later then merges the unreviewed head. GitHub's native dedup is real and used: merging an already merged PR is answered
  from the PR state. Nothing re-reads the head.
- **hand_check**: what a careful engineer writes, about ten lines, run before every send including after the
  restart: read the PR; if it is merged, report that merge and stop; if the head is not the reviewed sha, refuse;
  otherwise merge with `sha=<reviewed>`, GitHub's own precondition (the API returns 409 if the head moved; `gh pr
  merge --match-head-commit` is the same flag). It uses the same 405 retry and logs each check. This is idiomatic
  because GitHub documents the `sha` parameter for exactly this race, and re-reading state before a retry is
  standard practice.
- **interlock**: `interlock.gate.Gate` over `scenarios/github_merge/github.py:GitHubMerge`, a tier 2 target.
  Premise: the reviewed head sha, captured when the model decided. Lease: the persisted approval of exactly this
  PR at exactly that sha. DISPATCHED is journaled before the PUT. The PUT also carries `sha=<reviewed>`, because
  the premise check and the send are two requests and only GitHub can make them atomic. On restart
  `gate.recover()` waits out the dead sender's claim ({CLAIM_TTL}s), re-checks lease and premise, and looks the
  merge up (merged, with the reviewed sha as a parent of the merge commit) before any resend.

## Records and what they prove

The harness plays auditor. It holds a key the agent processes never receive ({key_source}) and seals each record
when it collects it: Interlock's receipt with `receipts.sign` (HMAC over the effect id and the chain head), and
hand_check's log with an HMAC over the log text. A seal shows the record was not rewritten after collection by
anyone without the key. It does not show the agent process wrote honest entries: whoever runs the agent can write
a false journal before the seal, for either system.

Forged-receipt test, on every Interlock receipt in this run: flip the final entry (REFUSED to COMMITTED, or the
reverse), recompute its hash. `verify()` without the key called {t_unsigned}/{len(tampers)} forgeries valid, because an
unsigned hash chain only proves internal consistency. `verify()` with the key called {t_signed}/{len(tampers)} valid.
So the chain alone is not tamper-evident; the key held outside the writer is what makes it so, and the same key
makes hand_check's log just as tamper-evident.

What does differ is structure. The receipt records the lease check, the premise re-check before the send and at
recovery (with the head sha it read), and how it settled, and `verify()` re-derives happened, authorized when fired
and assumptions held from those entries. hand_check's log records the same checks as free text a person has to read.

## Findings

- no_check violated the invariant in {len(nc_viol)}/{len(nc)} `before_send` cells: the restart merged whatever the head
  was when it ran, which was the unreviewed commit. Whether the merge needed the 405 retry, per cell: {nc_405}.
  Without the retry, a cell that got a 405 would have ended unmerged with an error instead. It held after the
  commit, because GitHub merges a PR once.
- hand_check ties Interlock on GitHub's final state and on the agent's answer in every cell where the summary says
  so. Its protection is the head re-read plus GitHub's `sha` precondition, and Interlock's adapter sends the same
  precondition. This scenario does not separate them on outcome.
- The head re-read alone is not enough. GitHub's PR API is eventually consistent: a probe during development read
  the old head for about 0.5s after a push landed. hand_check restarts whose head check passed and whose merge
  GitHub then refused with 409 in this run: {', '.join(hc_lag) if hc_lag else 'none'}. In those, GitHub's `sha`
  precondition, not the check, refused the merge. Interlock's premise re-read has the same exposure; it reads the head
  only after waiting out the claim, and its send carries the same `sha`, so a lagging read would end in a 409.
- Interlock's extra is the structured, sealed receipt described above and one recovery path for every target instead
  of per-call checks, not a different merge.
- Interlock is slower after a crash: median {statistics.median(il_secs) if il_secs else None}s against hand_check's
  {statistics.median(hc_secs) if hc_secs else None}s. A SIGKILLed sender cannot release its claim, so recovery waits
  for it to expire ({CLAIM_TTL}s). That wait keeps two workers from sending the same merge at once; hand_check has no
  such wait and relies on GitHub's `sha` precondition and merge dedup instead, which is enough for this target.

## Prior runs in the sandbox

Every PR the sandbox held before this run, and why it is not in the tables. None of them is counted above.

{prior_md}

## Declined reviews (redone with a fresh PR)

{declined_md}

## Ids

{ids}

## Agent logs (both processes per cell)

{logs}

## What is real, what is not

- GitHub: every PR, read, merge, push and ground-truth read is a real call against a real private repo. No mock.
- LLM: every review is a real Anthropic Messages API call on the diff pinned to the reviewed sha. The restart
  reads the persisted decision and does not ask the model again.
- Crashes: `os.kill(os.getpid(), SIGKILL)` in the agent process; exit code -9 is recorded per cell.
- The human push is a real `git push` of a new commit to the PR branch, from a separate clone.
- `after_commit` kills the process after GitHub's full response was received, before anything durable recorded
  it. The connection is never cut mid-response; recovery sees the same state as a response lost in transit.
- Seals are applied by the harness after the agent exits, not by a separate service at write time.
- Emulated: nothing.

## Re-run

    python3 experiments/scenario_github_merge.py [REPEATS]
"""
    with open(os.path.join(ROOT, "results", "scenarios", "github_merge.md"), "w") as f:
        f.write(md)


def main():
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    key = os.environ.get("INTERLOCK_AUDIT_KEY")
    key_source = "from INTERLOCK_AUDIT_KEY" if key else "a random key generated for this run and discarded after it"
    key = key or secrets.token_hex(32)
    env = {k: v for k, v in {**os.environ, **anthropic_env(), "PYTHONPATH": ROOT}.items() if k != "INTERLOCK_AUDIT_KEY"}
    prior = prior_prs()
    clone = tempfile.mkdtemp(prefix="interlock-sandbox-clone-")
    cells, declined = [], []
    try:
        git("clone", "-q", f"https://github.com/{REPO}.git", clone)
        for rep in range(1, repeats + 1):
            for fault in FAULTS:
                for system in SYSTEMS:
                    cells.append(run_cell(rep, system, fault, clone, env, declined, key))
                    print(f"rep {rep} {fault:13} {system:11} {cell_text(cells[-1])}", flush=True)
        write_results(cells, declined, prior, started, repeats, key_source)
    finally:
        cleanup(cells, declined)
        shutil.rmtree(clone, ignore_errors=True)


if __name__ == "__main__":
    main()
