"""
The merge agent. One OS process per run.

    python3 -m scenarios.github_merge.agent SYSTEM REPO PR STATE_DIR [--crash before_send|after_commit]

With --crash (the first run): read the PR, have the LLM review the diff pinned to the head sha,
persist the decision, and send by SYSTEM. The send SIGKILLs this process at the crash point.
Without --crash (the restart): read the persisted decision (the model is not asked again, as in
any job queue or durable workflow) and finish by SYSTEM. Writes STATE_DIR/outcome.json when settled.

SYSTEM
  no_check    `gh pr merge` semantics: merge the PR, retry on restart, GitHub's "a PR merges once"
              as the only dedup. No re-check.
  hand_check  what a careful engineer writes: before every send read the PR; stop if it is already
              merged; refuse if the head is not the reviewed sha; then merge with sha=<reviewed>,
              GitHub's native precondition (`gh pr merge --match-head-commit`). Checks are logged.
  interlock   gate.Gate over GitHubMerge: the reviewed sha is the premise, the review is the lease,
              recovery on restart by tier 2 (look the merge up, re-check before any resend).
"""
import json, logging, os, re, subprocess, sys, time, urllib.request
from interlock.gate import Gate
from interlock.journal import effect_id_for
from interlock.receipts import bundle, verify
from .github import GitHub, GitHubError, GitHubMerge

MODEL = "claude-haiku-4-5-20251001"
CLAIM_TTL = 25          # longer than the client's 15s timeout, so recovery never overlaps a live send
log = logging.getLogger("merge-agent")


def parse_decision(text):
    m = re.search(r"\{.*\}", text, re.S)
    d = json.loads(m.group(0)) if m else {}
    if not isinstance(d.get("merge"), bool):
        raise ValueError(f"model reply is not a merge decision: {text[:200]!r}")
    return {"merge": d["merge"], "reason": str(d.get("reason", ""))}


def review(title, description, diff):
    body = {"model": MODEL, "max_tokens": 300, "temperature": 0,
            "system": "You are the merge bot for a small repository. Policy: merge a pull request when its diff is "
                      "correct, safe, and does what its title and description say. Documentation-only changes are "
                      "welcome. Do not merge changes that disable tests, weaken security, or do not match the description.",
            "messages": [{"role": "user", "content":
            f"Title: {title}\nDescription: {description}\n\nDiff:\n{diff}\n\n"
            'Reply with only JSON: {"merge": true or false, "reason": "one sentence"}.'}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST")
    req.add_header("x-api-key", os.environ["ANTHROPIC_API_KEY"])
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return parse_decision(json.loads(r.read())["content"][0]["text"])


def write_json(path, obj):
    with open(path + ".tmp", "w") as f:
        json.dump(obj, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(path + ".tmp", path)


def read_json(path):
    with open(path) as f:
        return json.load(f)


def merge_retrying(c, n, **kw):
    """Merge, retrying GitHub's transient 405 while mergeability is recomputed. Returns (outcome, merge sha)."""
    for attempt in range(6):
        try:
            return "MERGED", c.merge(n, **kw)["sha"]
        except GitHubError as e:
            log.info("merge answered %s", e)
            if e.status == 409 and kw.get("sha"):                # the sha precondition failed: final, not transient
                raise
            pr = c.pr(n)
            if pr["merged"]:                                    # a PR merges once: GitHub's native dedup
                log.info("PR already merged as %s", pr["merge_commit_sha"])
                return "ALREADY_MERGED", pr["merge_commit_sha"]
            if e.status not in (405, 409) or attempt == 5:     # 405/409 without sha: mergeability still recomputing
                raise
            log.info("merge answered %s; retrying", e)
            kw.pop("crash", None)
            time.sleep(3)


def send_no_check(c, d, crash):
    log.info("merging PR #%s (no check)", d["pr"])
    return merge_retrying(c, d["pr"], message=f"Merge PR #{d['pr']} (merge-bot)", crash=crash)


def send_hand_check(c, d, crash):
    pr = c.pr(d["pr"])
    if pr["merged"]:
        log.info("head check: PR already merged as %s; not sending", pr["merge_commit_sha"])
        return "ALREADY_MERGED", pr["merge_commit_sha"]
    if pr["head"]["sha"] != d["reviewed_sha"]:
        log.info("head check: FAILED, head %s is not reviewed %s; refusing", pr["head"]["sha"], d["reviewed_sha"])
        return "REFUSED:head_moved", None
    log.info("head check: passed, head is reviewed %s; merging with sha precondition", d["reviewed_sha"])
    try:
        return merge_retrying(c, d["pr"], sha=d["reviewed_sha"], crash=crash,
                              message=f"Merge PR #{d['pr']} at reviewed head {d['reviewed_sha'][:12]} (merge-bot)")
    except GitHubError as e:
        if e.status != 409:
            raise
        log.info("sha precondition: GitHub refused, %s", e)
        return "REFUSED:head_modified", None


class ReviewApproval:
    """The lease store: authority is the persisted LLM approval of exactly this PR at exactly this sha."""
    def __init__(self, state):
        self.path = os.path.join(state, "decision.json")

    def _decision(self):
        return read_json(self.path) if os.path.exists(self.path) else {}

    def is_live(self, lease):
        d = self._decision()
        return d.get("merge") is True and lease == f"review:{d['pr']}:{d['reviewed_sha']}"

    def describe(self, lease):
        d = self._decision()
        return {"reviewer": d.get("model"), "reviewed_sha": d.get("reviewed_sha"), "reason": d.get("reason")}


def run_interlock(c, d, state, crash):
    target = GitHubMerge(c, crash)
    gate = Gate(target, os.path.join(state, "journal.jsonl"), ReviewApproval(state), claim_ttl=CLAIM_TTL)
    proposal = {"agent": "merge-bot", "lease": f"review:{d['pr']}:{d['reviewed_sha']}",
                "request_id": f"merge {c.repo}#{d['pr']}", "premises": target.capture(d["pr"], d["reviewed_sha"]),
                "effect": {"pr": d["pr"], "sha": d["reviewed_sha"]}}
    eid = effect_id_for(proposal)
    if crash:
        try:
            status = gate.submit(proposal)
        except GitHubError as e:
            status = gate.settle_failed(eid, str(e))
    else:
        deadline, status = time.time() + 180, "UNSETTLED"
        while time.time() < deadline:                       # a SIGKILLed sender's claim holds until it expires
            got = gate.recover(only=[eid]).get(eid)
            if got and not got.startswith("UNRESOLVED"):
                status = got
                break
            if eid not in gate.journal.in_flight():
                status = gate.journal.receipt(eid)["final"]
                break
            time.sleep(1)
    log.info("interlock: %s", status)
    receipt = bundle(gate.journal, eid)
    write_json(os.path.join(state, "receipt.json"), receipt)
    merge = next((e.get("result", {}).get("merge_commit") or e.get("found") for e in receipt["entries"]
                  if e["kind"] == "COMMITTED"), None)
    return status, merge


def main(argv):
    system, repo, n, state = argv[:4]
    crash = argv[argv.index("--crash") + 1] if "--crash" in argv else None
    logging.basicConfig(filename=os.path.join(state, "agent.log"), level=logging.INFO,
                        format=f"%(asctime)s pid={os.getpid()} {system} %(message)s")
    token = os.environ.get("GITHUB_TOKEN") or subprocess.run(["gh", "auth", "token"], capture_output=True,
                                                             text=True, check=True).stdout.strip()
    c = GitHub(repo, token)
    decision_path = os.path.join(state, "decision.json")
    if crash:
        pr = c.pr(int(n))
        sha = pr["head"]["sha"]
        d = {"pr": int(n), "reviewed_sha": sha, "model": MODEL, **review(pr["title"], pr["body"] or "", c.diff(pr["base"]["ref"], sha))}
        write_json(decision_path, d)
        log.info("review of %s: merge=%s (%s)", sha, d["merge"], d["reason"])
        if not d["merge"]:
            outcome, merge = "NOT_APPROVED", None
        else:
            outcome, merge = None, None
    else:
        d = read_json(decision_path)
        log.info("restart: persisted decision merge=%s at %s", d["merge"], d["reviewed_sha"])
        outcome, merge = ("NOT_APPROVED", None) if not d["merge"] else (None, None)
    if outcome is None:
        send = {"no_check": send_no_check, "hand_check": send_hand_check}.get(system)
        outcome, merge = send(c, d, crash) if send else run_interlock(c, d, state, crash)
    write_json(os.path.join(state, "outcome.json"),
               {"system": system, "outcome": outcome, "merge_commit": merge, "settled_at": time.time(),
                "run": "first" if crash else "restart"})


if __name__ == "__main__":
    main(sys.argv[1:])
