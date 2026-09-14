"""
GitHub pull request merges: a small REST client, the Interlock EffectTarget, and the judge.

The effect is "merge PR #n at the head sha the reviewer read". GitHub has no idempotency key,
but a PR merges at most once and its state can be read back, so the target is tier 2:
recovery looks the merge up instead of guessing. The premise is the reviewed head sha.
apply() also passes that sha to the merge API, GitHub's own atomic precondition (409 when the
head moved), so a push landing between the premise check and the send cannot slip through.

Standard library only. The token is read at runtime and kept in memory.
"""
import json, os, signal, urllib.error, urllib.request
from interlock.gate import SimulatedCrash

API = "https://api.github.com"
MERGED_OUTCOMES = ("MERGED", "ALREADY_MERGED", "COMMITTED", "REAPPLIED")


class GitHubError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status = status


def die():
    """A real crash: the OS kills this process, nothing after this line runs."""
    os.kill(os.getpid(), signal.SIGKILL)


class GitHub:
    def __init__(self, repo, token, timeout=15):
        self.repo, self.timeout = repo, timeout
        self._auth = f"Bearer {token}"

    def call(self, method, path, body=None, accept="application/vnd.github+json"):
        req = urllib.request.Request(f"{API}/repos/{self.repo}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", self._auth)
        req.add_header("Accept", accept)
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise GitHubError(e.code, json.loads(e.read() or b"{}").get("message")) from None
        return raw.decode() if accept.endswith("diff") else json.loads(raw)

    def pr(self, n):
        return self.call("GET", f"/pulls/{n}")

    def diff(self, base, head_sha):
        """The diff pinned to the sha under review, so what was read and what is premised agree."""
        return self.call("GET", f"/compare/{base}...{head_sha}", accept="application/vnd.github.diff")

    def commit(self, sha):
        return self.call("GET", f"/commits/{sha}")

    def merge(self, n, sha=None, message=None, crash=None):
        """PUT /pulls/n/merge. sha, when given, is GitHub's precondition: 409 if the head is not that sha."""
        body = {"merge_method": "merge"}
        if sha:
            body["sha"] = sha
        if message:
            body["commit_message"] = message
        if crash == "before_send":
            die()
        result = self.call("PUT", f"/pulls/{n}/merge", body)
        if crash == "after_commit":
            die()                                   # GitHub merged; the response is never recorded
        return result


class GitHubMerge:
    """EffectTarget for gate.Gate. effect = {"pr": n, "sha": reviewed head}."""
    tier = 2
    queryable = True

    def __init__(self, client, crash=None):
        self.client, self.crash = client, crash

    def capture(self, pr, reviewed_sha):
        return {"pr": pr, "head_sha": reviewed_sha}

    def validate_premises(self, premises, eid=None):
        head = self.client.pr(premises["pr"])["head"]["sha"]
        return [] if head == premises["head_sha"] else [f"head moved: reviewed {premises['head_sha']}, now {head}"]

    def apply(self, eid, effect, crash_after_effect=False):
        crash, self.crash = self.crash, None        # one-shot
        r = self.client.merge(effect["pr"], sha=effect["sha"], crash=crash,
                              message=f"Merge PR #{effect['pr']} at reviewed head {effect['sha'][:12]}\n\ninterlock-effect: {eid}")
        if crash_after_effect:
            raise SimulatedCrash(eid)               # offline tests only; the live path SIGKILLs above
        return {"merge_commit": r["sha"]}

    def query(self, eid, effect):
        """The merge commit that merged the reviewed sha, or None."""
        pr = self.client.pr(effect["pr"])
        if not pr["merged"]:
            return None
        parents = [p["sha"] for p in self.client.commit(pr["merge_commit_sha"])["parents"]]
        return pr["merge_commit_sha"] if effect["sha"] in parents else None


def judge(fault, truth, outcome):
    """
    truth: what GitHub says after the run (merged, second_parent, unreviewed_on_main).
    before_send: a human pushed an unreviewed commit before anything merged, so the PR must stay unmerged.
    after_commit: the reviewed head merged before the crash, so it must be merged exactly at that head,
    with the later human commit not on main. GitHub merges a PR at most once, so "merged" is "merged once".
    """
    if fault == "before_send":
        held = not truth["merged"]
    else:
        held = truth["merged"] and truth["second_parent"] == truth["reviewed_sha"]
    held = held and not truth["unreviewed_on_main"]
    reports_merged = str(outcome).startswith(MERGED_OUTCOMES)
    return {"invariant_held": bool(held), "answer_matches": reports_merged == truth["merged"]}
