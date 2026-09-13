"""
    python3 -m unittest discover -s tests

Regression tests for the defects an adversarial review of the package found. Each one
reproduced the defect before its fix.
"""
import os, sys, tempfile, threading, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, Interlock, Leases, SimulatedCrash, open_journal
from interlock.approvals import Authority, Inbox, Rule
from interlock.journal import _seal
from interlock.receipts import verify
from interlock.targets import Payments
from interlock.temporal import gated


class SlowPayments(Payments):
    def apply(self, eid, effect, crash_after_effect=False):
        time.sleep(0.4)
        return super().apply(eid, effect, crash_after_effect)


def world(tier=2, api_cls=Payments, suffix=".jsonl", order="881", request="case-4471"):
    api = api_cls(tier)
    api.create_order(order, 100)
    leases = Leases()
    leases.grant("L")
    P = {"agent": "bot", "lease": "L", "request_id": request,
         "premises": api.capture(order), "effect": {"order": order, "amount": 20}}
    return api, leases, tempfile.mktemp(suffix=suffix), P


def wait_in_flight(path, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if open_journal(path).in_flight():
            return True
        time.sleep(0.01)
    return False


class ReviewFixes(unittest.TestCase):
    def test_recovery_never_resends_an_effect_that_is_still_being_applied(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                api, leases, path, P = world(api_cls=SlowPayments, suffix=suffix)
                sender = threading.Thread(target=lambda: Gate(api, path, leases).submit(P))
                sender.start()
                self.assertTrue(wait_in_flight(path))                 # the first send is mid-apply
                self.assertEqual(Gate(api, path, leases).recover(), {})
                sender.join()
                self.assertEqual(api.refunded_total("881"), 20)

    def test_recovery_rechecks_the_lease_the_send_actually_ran_under(self):
        api = Payments(2)
        api.create_order("881", 100)
        leases = Leases()
        leases.grant("L-old")
        leases.grant("L-new")
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)
        base = {"agent": "bot", "request_id": "case-4471", "premises": api.capture("881"),
                "effect": {"order": "881", "amount": 20}}
        api.set_eligible("881", False)
        self.assertEqual(gate.submit(dict(base, lease="L-old")), "REFUSED:stale_premise")
        api.set_eligible("881", True)
        with self.assertRaises(SimulatedCrash):
            gate.submit(dict(base, lease="L-new"), crash_before_effect=True)
        leases.revoke("L-new")                                        # L-old is still live
        self.assertEqual(list(gate.recover().values()), ["REFUSED:lease_at_recovery"])
        self.assertEqual(api.refunded_total("881"), 0)

    def test_a_different_payload_cannot_win_the_dispatch_race(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                journal = open_journal(tempfile.mktemp(suffix=suffix))
                journal.append("PROPOSED", "e1", effect={"amount": 20})    # worker 1 recorded $20 first
                self.assertEqual(journal.dispatch("e1", {"amount": 30}, "worker-2"), "conflicting_payload")
                self.assertIsNone(journal.dispatch("e1", {"amount": 20}, "worker-1"))

    def test_one_failing_effect_does_not_stop_recovery_of_the_others(self):
        api = Payments(2)
        for order in ("1", "2"):
            api.create_order(order, 100)
        leases = Leases()
        leases.grant("L")
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)
        for order in ("1", "2"):
            with self.assertRaises(SimulatedCrash):
                gate.submit({"agent": "bot", "lease": "L", "request_id": f"r{order}", "premises": api.capture(order),
                             "effect": {"order": order, "amount": 20}}, crash_before_effect=True)
        real_query = api.query

        def flaky_query(eid, effect):
            if effect["order"] == "1":
                raise ConnectionError("network down")
            return real_query(eid, effect)
        api.query = flaky_query
        self.assertEqual(sorted(gate.recover().values()), ["REAPPLIED_AFTER_QUERY", "UNRESOLVED:ConnectionError"])
        self.assertEqual((api.refunded_total("1"), api.refunded_total("2")), (0, 20))
        api.query = real_query                      # nothing was sent, so the next attempt need not wait out a claim
        self.assertEqual(list(Gate(api, gate.journal.path, leases).recover().values()), ["REAPPLIED_AFTER_QUERY"])
        self.assertEqual(api.refunded_total("1"), 20)

    def test_a_resend_that_raised_keeps_its_claim(self):
        api, leases, path, P = world(tier=1)
        with self.assertRaises(SimulatedCrash):
            Gate(api, path, leases).submit(P, crash_before_effect=True)
        real_apply = api.apply
        api.apply = lambda *a, **k: (_ for _ in ()).throw(TimeoutError("response lost"))
        self.assertEqual(list(Gate(api, path, leases).recover().values()), ["UNRESOLVED:TimeoutError"])
        api.apply = real_apply
        self.assertEqual(Gate(api, path, leases).recover(), {})      # the timed-out send may still land: wait

    def test_functions_with_the_same_name_get_separate_journals(self):
        gate = Interlock(tempfile.mkdtemp())

        class A:
            @staticmethod
            def act(x):
                return "A"

        class B:
            @staticmethod
            def act(x):
                return "B"
        a = gate.effect(key=lambda x: f"a:{x}")(A.act)
        b = gate.effect(key=lambda x: f"b:{x}")(B.act)
        self.assertNotEqual(a.gate.journal.path, b.gate.journal.path)
        with self.assertRaises(ValueError):
            gate.effect(key=lambda x: x)(A.act)

    def test_torn_final_journal_line_is_ignored_then_repaired(self):
        path = tempfile.mktemp(suffix=".jsonl")
        journal = open_journal(path)
        journal.append("PROPOSED", "e1", effect={})
        with open(path, "a") as f:
            f.write('{"kind": "DISPA')                                # power lost mid-write
        self.assertEqual([e["kind"] for e in journal.entries()], ["PROPOSED"])
        journal.append("REFUSED", "e1", reason="x")
        self.assertEqual([e["kind"] for e in journal.entries()], ["PROPOSED", "REFUSED"])

    def test_empty_claims_file_does_not_stop_recovery(self):
        api, leases, path, P = world()
        gate = Gate(api, path, leases)
        with self.assertRaises(SimulatedCrash):
            gate.submit(P, crash_before_effect=True)
        open(path + ".claims", "w").close()
        self.assertEqual(list(gate.recover().values()), ["REAPPLIED_AFTER_QUERY"])

    def test_temporal_helper_asks_for_a_retry_while_an_attempt_is_unsettled(self):
        api, leases, path, P = world(api_cls=SlowPayments)
        sender = threading.Thread(target=lambda: Gate(api, path, leases).submit(P))
        sender.start()
        self.assertTrue(wait_in_flight(path))
        with self.assertRaises(Exception) as caught:                  # InFlight, or a retryable ApplicationError
            gated(Gate(api, path, leases), P)
        sender.join()
        self.assertIn("IN_FLIGHT", str(caught.exception))
        self.assertFalse(getattr(caught.exception, "non_retryable", False))
        self.assertEqual(api.refunded_total("881"), 20)

    def test_verify_rejects_a_forged_lone_commit_and_an_empty_receipt(self):
        forged = {"effect_id": "e1", "entries": [_seal({"ts": 0, "kind": "COMMITTED", "effect_id": "e1"}, None)]}
        self.assertFalse(verify(forged)["valid"])
        self.assertFalse(verify({"effect_id": "e1", "entries": []})["valid"])

    def test_approval_after_a_stale_refusal_uses_the_facts_the_approver_saw(self):
        api = Payments(2)
        api.create_order("2", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), Authority(approvers={"alice"}))
        inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                      effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                      rules=[Rule("always ask", lambda r, facts: False)])
        inbox.submit({"id": "r2", "order": "2", "amount": 50})
        inbox.approve("r2", "alice", execute=False)
        api.refunds.append({"eid": "dashboard", "order": "2", "amount": 30})   # support refunds part of it by hand
        self.assertEqual(inbox.execute("r2"), "REFUSED:stale_premise")
        self.assertEqual(inbox.queue["r2"]["facts"]["refunded"], 30)
        self.assertEqual(inbox.approve("r2", "alice"), "COMMITTED")            # alice saw the $30 and approves again
        self.assertEqual(api.refunded_total("2"), 80)

    def test_nobody_can_approve_as_policy(self):
        api = Payments(2)
        api.create_order("2", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), Authority(approvers={"alice"}))
        inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                      effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                      rules=[Rule("always ask", lambda r, facts: False)])
        inbox.submit({"id": "r2", "order": "2", "amount": 50})
        with self.assertRaises(ValueError):
            inbox.approve("r2", "policy")
        self.assertEqual(api.refunded_total("2"), 0)


if __name__ == "__main__":
    unittest.main()
