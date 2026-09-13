"""
    python3 -m unittest discover -s tests

The approval inbox: routine requests never reach a person, judgment calls do, and a
person's approval is re-checked against the world when the refund is actually sent.
"""
import os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, SimulatedCrash, effect_id_for
from interlock.approvals import Authority, Inbox, Rule
from interlock.targets import Payments


class ApprovalInbox(unittest.TestCase):
    def setUp(self):
        self.api = Payments(2)
        for order in ("1", "2", "3"):
            self.api.create_order(order, 100)
        self.authority = Authority(approvers={"alice"}, max_age=3600)
        self.gate = Gate(self.api, tempfile.mktemp(suffix=".jsonl"), self.authority)
        self.inbox = Inbox(self.gate,
                           capture=lambda r: self.api.capture(r["order"]),
                           effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                           rules=[Rule("amount under $50", lambda r, facts: r["amount"] <= 50),
                                  Rule("order eligible", lambda r, facts: facts["eligible"])])

    def req(self, rid, order, amount):
        return {"id": rid, "order": order, "amount": amount}

    def test_routine_request_runs_with_no_person(self):
        self.assertEqual(self.inbox.submit(self.req("r1", "1", 20)), "COMMITTED")
        self.assertEqual((self.inbox.queue, self.inbox.cleared), ({}, ["r1"]))
        self.assertEqual(self.inbox.receipt("r1")["authority"]["by"], "policy")

    def test_duplicate_request_is_ignored_not_queued(self):
        self.inbox.submit(self.req("r1", "1", 20))
        self.assertEqual(self.inbox.submit(self.req("r1", "1", 20)), "DUPLICATE_IGNORED")
        self.assertEqual((self.api.refunded_total("1"), self.inbox.queue), (20, {}))

    def test_judgment_call_waits_then_runs_under_the_approver(self):
        self.assertEqual(self.inbox.submit(self.req("r2", "2", 80)), "QUEUED")
        self.assertEqual(self.inbox.queue["r2"]["detail"], ["amount under $50"])
        self.assertEqual(self.inbox.approve("r2", "alice"), "COMMITTED")
        self.assertEqual(self.api.refunded_total("2"), 80)
        self.assertEqual(self.inbox.receipt("r2")["authority"]["by"], "alice")

    def test_stale_approval_is_refused_and_comes_back_explained(self):
        self.inbox.submit(self.req("r2", "2", 80))
        self.inbox.approve("r2", "alice", execute=False)                         # 9am: approved
        self.api.refunds.append({"eid": "dashboard", "order": "2", "amount": 80})  # support refunds by hand
        self.assertEqual(self.inbox.execute_approved(), {"r2": "REFUSED:stale_premise"})  # 3pm: sent
        self.assertEqual(self.api.refunded_total("2"), 80)
        self.assertEqual(self.inbox.queue["r2"]["facts"]["refunded"], 80)       # approver now sees the change

    def test_expired_approval_is_refused(self):
        self.inbox.submit(self.req("r2", "2", 80))
        self.inbox.approve("r2", "alice", execute=False)
        self.inbox.approved["r2"]["authority"]["at"] -= 7200                     # approved two hours ago
        self.assertEqual(self.inbox.execute("r2"), "REFUSED:lease")
        self.assertEqual(self.api.refunded_total("2"), 0)

    def test_approval_from_someone_without_authority_is_refused(self):
        self.inbox.submit(self.req("r2", "2", 80))
        self.assertEqual(self.inbox.approve("r2", "mallory"), "REFUSED:lease")
        self.assertIn("r2", self.inbox.queue)
        self.assertEqual(self.api.refunded_total("2"), 0)

    def test_crash_mid_send_is_recovered_once_with_no_person(self):
        with self.assertRaises(SimulatedCrash):
            self.gate.submit(self.inbox._proposal(self.req("r1", "1", 20), {"by": "policy"}, self.api.capture("1")),
                             crash_after_effect=True)
        self.inbox.sent[effect_id_for({"request_id": "r1"})] = (self.req("r1", "1", 20), True)
        self.inbox.reconcile(self.gate.recover())
        self.assertEqual((self.api.refunded_total("1"), self.inbox.queue, self.inbox.cleared), (20, {}, ["r1"]))

    def test_crash_nobody_can_verify_goes_to_a_person(self):
        api = Payments(3)
        api.create_order("9", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), self.authority)
        inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                      effect=lambda r: {"order": r["order"], "amount": r["amount"]}, rules=[])
        crashing = lambda *a, **k: Payments.apply(api, a[0], a[1], True)
        api.apply = crashing
        with self.assertRaises(SimulatedCrash):
            inbox.submit(self.req("r9", "9", 20))
        inbox.reconcile(gate.recover())
        self.assertEqual(inbox.queue["r9"]["detail"], "AMBIGUOUS")
        self.assertEqual(api.refunded_total("9"), 20)

    def test_ineligible_order_needs_a_person_even_under_the_limit(self):
        self.api.set_eligible("3", False)
        self.assertEqual(self.inbox.submit(self.req("r3", "3", 10)), "QUEUED")
        self.assertEqual(self.inbox.reject("r3", "alice"), "REJECTED")
        self.assertEqual(self.api.refunded_total("3"), 0)


if __name__ == "__main__":
    unittest.main()
