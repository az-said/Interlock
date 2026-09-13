"""Offline logic for scenarios/github_merge. The live run is experiments/scenario_github_merge.py."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock.gate import SimulatedCrash
from interlock.receipts import verify
from scenarios.github_merge import agent, audit
from scenarios.github_merge.github import GitHubError, judge


class FakeGitHub:
    """GitHub's merge semantics as probed live: sha precondition 409, re-merge returns the same commit,
    a merged PR's head stays put. A crash point raises instead of SIGKILL."""
    repo = "o/r"

    def __init__(self, head):
        self.head, self.merged, self.merges, self.push_during_send = head, False, 0, None

    def pr(self, n):
        return {"merged": self.merged, "merge_commit_sha": "m1" if self.merged else None,
                "head": {"sha": self.head}, "base": {"ref": "main"}}

    def commit(self, sha):
        return {"parents": [{"sha": "base"}, {"sha": self.merged_head}]}

    def push(self, sha):
        if not self.merged:
            self.head = sha

    def merge(self, n, sha=None, message=None, crash=None):
        if crash == "before_send":
            raise SimulatedCrash("before_send")
        if self.push_during_send:
            self.push(self.push_during_send)
        if not self.merged:
            if sha and sha != self.head:
                raise GitHubError(409, "Head branch was modified")
            self.merged, self.merged_head, self.merges = True, self.head, self.merges + 1
        if crash == "after_commit":
            raise SimulatedCrash("after_commit")
        return {"sha": "m1"}


def decision(state):
    d = {"pr": 7, "reviewed_sha": "r1", "model": agent.MODEL, "merge": True, "reason": "docs only"}
    agent.write_json(os.path.join(state, "decision.json"), d)
    return d


class Decision(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(agent.parse_decision('```json\n{"merge": true, "reason": "ok"}\n```'), {"merge": True, "reason": "ok"})
        with self.assertRaises(ValueError):
            agent.parse_decision('{"merge": "yes"}')


class Judge(unittest.TestCase):
    base = {"reviewed_sha": "r1", "unreviewed_on_main": False}

    def test_before_send(self):
        self.assertEqual(judge("before_send", {**self.base, "merged": False, "second_parent": None}, "REFUSED:head_moved"),
                         {"invariant_held": True, "answer_matches": True})
        self.assertFalse(judge("before_send", {**self.base, "merged": True, "second_parent": "h2",
                                               "unreviewed_on_main": True}, "MERGED")["invariant_held"])

    def test_after_commit(self):
        truth = {**self.base, "merged": True, "second_parent": "r1"}
        self.assertEqual(judge("after_commit", truth, "COMMITTED_ON_QUERY"), {"invariant_held": True, "answer_matches": True})
        self.assertFalse(judge("after_commit", truth, "REFUSED:stale_premise_at_recovery")["answer_matches"])


class Systems(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = tmp.name
        self.d = decision(self.state)
        self.gh = FakeGitHub("r1")

    def test_no_check_merges_the_push(self):
        with self.assertRaises(SimulatedCrash):
            agent.send_no_check(self.gh, self.d, "before_send")
        self.gh.push("h2")
        self.assertEqual(agent.send_no_check(self.gh, self.d, None), ("MERGED", "m1"))
        self.assertEqual(self.gh.merged_head, "h2")

    def test_hand_check(self):
        with self.assertRaises(SimulatedCrash):
            agent.send_hand_check(self.gh, self.d, "before_send")
        self.gh.push("h2")
        self.assertEqual(agent.send_hand_check(self.gh, self.d, None), ("REFUSED:head_moved", None))
        self.assertEqual(self.gh.merges, 0)

    def test_hand_check_push_between_check_and_send(self):
        self.gh.push_during_send = "h2"
        self.assertEqual(agent.send_hand_check(self.gh, self.d, None), ("REFUSED:head_modified", None))

    def test_hand_check_after_commit(self):
        with self.assertRaises(SimulatedCrash):
            agent.send_hand_check(self.gh, self.d, "after_commit")
        self.assertEqual(agent.send_hand_check(self.gh, self.d, None), ("ALREADY_MERGED", "m1"))

    def test_interlock_before_send(self):
        with self.assertRaises(SimulatedCrash):
            agent.run_interlock(self.gh, self.d, self.state, "before_send")
        self.gh.push("h2")
        status, merge = agent.run_interlock(self.gh, self.d, self.state, None)
        self.assertEqual((status, merge, self.gh.merges), ("REFUSED:stale_premise_at_recovery", None, 0))
        v = verify(agent.read_json(os.path.join(self.state, "receipt.json")))
        self.assertTrue(v["valid"])
        self.assertIs(v["happened"], False)

    def test_interlock_after_commit(self):
        with self.assertRaises(SimulatedCrash):
            agent.run_interlock(self.gh, self.d, self.state, "after_commit")
        self.gh.push("h2")
        status, merge = agent.run_interlock(self.gh, self.d, self.state, None)
        self.assertEqual((status, merge, self.gh.merges), ("COMMITTED_ON_QUERY", "m1", 1))
        v = verify(agent.read_json(os.path.join(self.state, "receipt.json")))
        self.assertTrue(v["valid"] and v["happened"] is True and v["authorized_when_fired"] and v["assumptions_held"])

    def test_forged_receipt_passes_unsigned_fails_signed(self):
        with self.assertRaises(SimulatedCrash):
            agent.run_interlock(self.gh, self.d, self.state, "before_send")
        self.gh.push("h2")
        agent.run_interlock(self.gh, self.d, self.state, None)
        sealed = audit.seal_receipt(agent.read_json(os.path.join(self.state, "receipt.json")), "k")
        self.assertTrue(verify(sealed, "k")["signed"])
        t = audit.tamper_test(sealed, "k")
        self.assertEqual(t["forged_final"], "REFUSED -> COMMITTED")
        self.assertTrue(t["unsigned_verify"]["valid"])          # the chain alone cannot catch a rewrite
        self.assertFalse(t["signed_verify"]["valid"])


if __name__ == "__main__":
    unittest.main()
