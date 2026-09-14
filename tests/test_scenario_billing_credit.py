"""Offline logic of scenarios/billing_credit: premises, judging, the target, and the hand check. No network."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock.receipts import verify  # noqa: E402
from scenarios.billing_credit.billing import Approval, CreditTarget, compensation_by_others, facts, judge  # noqa: E402
from scenarios.billing_credit.worker import hand_checked_send  # noqa: E402

CASE = {"case_id": "case-1", "incident": "INC-1", "customer": "cus_1", "subscription": "sub_1"}
RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "scenarios",
                       "billing_credit.json")


def note(amount, incident, status="issued"):
    return {"amount": amount, "status": status, "metadata": {"incident": incident}}


class FakeStripe:
    """Answers only the reads and the one write the scenario makes."""
    def __init__(self, txns=(), notes=(), status="active"):
        self.txns, self.notes, self.status, self.posts = list(txns), list(notes), status, []

    def request(self, method, path, params=None, idempotency_key=None):
        if path.endswith("/balance_transactions"):
            if method == "GET":
                return {"data": self.txns}
            txn = {"id": f"cbtxn_{len(self.posts)}", "type": "adjustment", "amount": params["amount"],
                   "metadata": params["metadata"], "_replayed": False}
            self.posts.append((params, idempotency_key))
            self.txns.append(txn)
            return txn
        if path == "/credit_notes":
            return {"data": self.notes}
        if path.startswith("/subscriptions/"):
            return {"status": self.status}
        raise AssertionError(path)


def adj(amount, case_id=None, **meta):
    return {"type": "adjustment", "amount": amount, "metadata": {**({"case_id": case_id} if case_id else {}), **meta}}


class Premises(unittest.TestCase):
    def test_counts_credit_notes_and_others_adjustments_only(self):
        txns = [adj(-1000, "case-1", incident="INC-1"),                 # this case's own credit
                {"type": "applied_to_invoice", "amount": 1000, "metadata": {}},   # renewal consumed a balance
                {"type": "credit_note", "amount": -1000, "metadata": {}},         # counted via the credit note itself
                adj(-500), adj(-300, incident="INC-1"), adj(700)]       # others' credits; a debit
        notes = [note(1000, "INC-1"), note(400, "INC-1", "void"), note(250, "INC-2")]
        self.assertEqual(compensation_by_others(txns, notes, "case-1"), 2050)
        self.assertEqual(compensation_by_others(txns, notes, "case-1", "INC-1"), 1300)   # only this incident

    def test_target_sees_a_billing_credit_and_finds_its_own_send(self):
        s = FakeStripe()
        t = CreditTarget(s, CASE)
        premises = facts(s, CASE)
        self.assertEqual(t.validate_premises(premises), [])
        self.assertIsNone(t.query("eid1", {}))
        t.apply("eid1", {"amount": 1000, "description": "goodwill"})
        self.assertEqual(t.validate_premises(premises), [])            # its own credit is not someone else's
        self.assertTrue(t.query("eid1", {}))
        s.notes.append(note(1000, "INC-2"))                             # another incident's credit: still fine
        self.assertEqual(t.validate_premises(premises), [])
        s.notes.append(note(1000, "INC-1"))
        self.assertEqual(len(t.validate_premises(premises)), 1)


class HandCheck(unittest.TestCase):
    APPROVAL = {"id": "a", "max_cents": 1000, "revoked": None}

    def run_check(self, s, premises, approval=APPROVAL):
        log = []
        decision = {"amount": 1000, "description": "goodwill", "premises": premises}
        return hand_checked_send(s, CASE, approval, decision, log.append), log

    def test_sends_once_then_finds_by_lookup(self):
        s = FakeStripe()
        premises = facts(s, CASE)
        self.assertEqual(self.run_check(s, premises)[0], "CREDITED")
        self.assertEqual(self.run_check(s, premises)[0], "FOUND_BY_LOOKUP")
        self.assertEqual(len(s.posts), 1)
        self.assertEqual(s.posts[0][1], "goodwill-credit-case-1")

    def test_refuses_on_billing_credit_or_revoked_approval(self):
        s = FakeStripe()
        premises = facts(s, CASE)
        self.assertEqual(self.run_check(s, premises, {**self.APPROVAL, "revoked": 1})[0], "REFUSED:approval")
        s.notes.append(note(1000, "INC-1"))
        status, log = self.run_check(s, premises)
        self.assertEqual(status, "REFUSED:stale_premise")
        self.assertEqual(log[-1]["step"], "premises")
        self.assertEqual(s.posts, [])


class Judge(unittest.TestCase):
    def test_want_comes_from_the_premises_not_the_system(self):
        one = {"case_credit_count": 1, "case_credit_cents": 1000}
        two = {"case_credit_count": 2, "case_credit_cents": 2000}
        none = {"case_credit_count": 0, "case_credit_cents": 0}
        self.assertEqual(judge("before_send", "renewal", one, "CREDITED"), (True, True))
        self.assertEqual(judge("before_send", "billing_credit", one, "CREDITED"), (False, True))
        self.assertEqual(judge("before_send", "billing_credit", none, "REFUSED:stale_premise_at_recovery"), (True, True))
        self.assertEqual(judge("after_send", "renewal", two, "CREDITED"), (False, True))
        self.assertEqual(judge("after_send", "renewal", one, "AMBIGUOUS"), (True, False))

    def test_approval_lease_store(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "case.json")
            with open(path, "w") as f:
                json.dump({"approval": {"id": "a", "max_cents": 1000, "revoked": None}}, f)
            a = Approval(path)
            self.assertTrue(a.allows("a", {"amount": 1000}))
            self.assertFalse(a.allows("a", {"amount": 1001}))
            self.assertFalse(a.allows("b", {"amount": 10}))


class PublishedReceipts(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(RESULTS), "no published run")
    def test_every_published_interlock_receipt_reverifies_offline(self):
        with open(RESULTS) as f:
            cells = [c for c in json.load(f)["cells"] if c["system"] == "interlock" and "ground_truth" in c]
        self.assertTrue(cells)
        for c in cells:
            v = verify(c["receipt"])
            self.assertTrue(v["valid"], v["problems"])
            self.assertEqual(v["happened"] is True, c["ground_truth"]["case_credit_count"] > 0)


if __name__ == "__main__":
    unittest.main()
