"""Scenario email_tier3, offline logic only: no network, no keys. The live run is experiments/scenario_email_tier3.py."""
import json, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock.journal import effect_id_for
from scenarios.email_tier3 import systems as S
from scenarios.email_tier3.resend import Resend, ResendError, key_used


class FakeResend:
    def __init__(self, used=False):
        self.used, self.sends, self.probes = used, [], []

    def send(self, email, key):
        self.sends.append(key)
        replayed, self.used = self.used, True
        return "em_1", replayed

    def probe(self, key):
        self.probes.append(key)
        return self.used


class FakeStripe:
    def __init__(self, status):
        self.status = status

    def request(self, method, path, params=None, idempotency_key=None):
        return {"status": self.status}


CASE = {"case_id": "case-1", "approved": True, "refund_id": "re_1",
        "email": {"to": ["delivered@resend.dev"], "subject": "Your refund is on the way", "text": "hi"}}


class Probe(unittest.TestCase):
    def test_reads_used_and_unused(self):
        self.assertTrue(key_used(409, "invalid_idempotent_request"))
        self.assertFalse(key_used(403, "validation_error", "The interlock-sandbox.invalid domain is not verified."))

    def test_anything_else_is_not_an_answer(self):
        for status, name, msg in [(401, "restricted_api_key", ""), (409, "concurrent_idempotent_requests", ""),
                                  (403, "validation_error", "You can only send testing emails to your own address")]:
            with self.assertRaises(ResendError):
                key_used(status, name, msg)

    def test_never_sends_to_a_real_inbox(self):
        with self.assertRaises(ValueError):
            Resend("re_offline").send({"to": ["someone@example.com"]}, "k")


class HandCheck(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()

    def test_used_key_reports_sent_without_reading_the_refund(self):
        r = FakeResend(used=True)
        out = S.hand_check(CASE, self.state, r, FakeStripe("failed"))
        self.assertEqual(out["outcome"], "ALREADY_SENT")

    def test_failed_refund_sends_nothing(self):
        r = FakeResend()
        out = S.hand_check(CASE, self.state, r, FakeStripe("failed"))
        self.assertEqual((out["outcome"], r.sends), ("SKIPPED:refund_failed", []))
        with open(os.path.join(self.state, "app.log")) as f:
            lines = [json.loads(l) for l in f]
        self.assertTrue(S.provable_from_log(lines, out["outcome"], None))

    def test_without_the_probe_a_sent_email_reads_as_skipped(self):
        r = FakeResend(used=True)                     # the crashed worker's email went out
        out = S.hand_check(CASE, self.state, r, FakeStripe("failed"), probe=False)
        self.assertEqual((out["outcome"], r.sends, r.probes), ("SKIPPED:refund_failed", [], []))


class RefundAlreadyFailedAtDecision(unittest.TestCase):
    """The premise is absolute: a refund that had failed before the agent captured it must not get an email."""
    def test_interlock_sends_nothing(self):
        d = tempfile.mkdtemp()
        case_path = os.path.join(d, "case.json")
        with open(case_path, "w") as f:
            json.dump(CASE, f)
        for lookup in (True, False):
            r = FakeResend()
            out = S.interlock(CASE, tempfile.mkdtemp(), r, FakeStripe("failed"), case_path, lookup=lookup)
            self.assertEqual((out["outcome"], r.sends), ("REFUSED:stale_premise", []))


class Recovery(unittest.TestCase):
    """An email left in flight by a crash, recovered by the gate."""
    def gate(self, resend, stripe, tier=1, lookup=True):
        d = tempfile.mkdtemp()
        case_path = os.path.join(d, "case.json")
        with open(case_path, "w") as f:
            json.dump(CASE, f)
        target = S.ResendEmail(resend, stripe, tier, lookup)
        g = S.KeyWindowGate(target, os.path.join(d, "journal.jsonl"), S.CaseApproval(case_path), claim_ttl=0)
        eid = effect_id_for({"request_id": "refund-email/case-1"})
        effect, premises = {"email": CASE["email"]}, {"refund_id": "re_1", "refund_status": "succeeded"}
        g.journal.append("PROPOSED", eid, agent="a", lease="case-1", premises=premises, effect=effect)
        g.journal.append("AUTHORIZED", eid, lease="case-1")
        g.journal.dispatch(eid, effect, "dead-worker", 0, lease="case-1", premises=premises,
                           checks={"lease_live": True, "lease": None, "violations": []})
        return g, eid

    def test_refund_failed_and_never_sent_is_refused(self):
        r = FakeResend()
        g, eid = self.gate(r, FakeStripe("failed"))
        self.assertEqual(g.recover(), {eid: "REFUSED:stale_premise_at_recovery"})
        self.assertEqual(r.sends, [])

    def test_refund_failed_but_already_sent_is_found(self):
        r = FakeResend(used=True)
        g, eid = self.gate(r, FakeStripe("failed"))
        self.assertEqual(g.recover(), {eid: "COMMITTED_ON_QUERY"})

    def test_without_the_probe_a_failed_refund_is_ambiguous(self):
        r = FakeResend(used=True)
        g, eid = self.gate(r, FakeStripe("failed"), lookup=False)
        self.assertEqual(g.recover(), {eid: "AMBIGUOUS"})
        self.assertEqual((r.sends, r.probes), ([], []))

    def test_after_the_key_window_nothing_is_asked_or_sent(self):
        r = FakeResend()
        g, eid = self.gate(r, FakeStripe("succeeded"))
        self.assertEqual(g.recover(now=time.time() + 25 * 3600), {eid: "AMBIGUOUS"})
        self.assertEqual((r.sends, r.probes), ([], []))
        self.assertTrue(g.target.queryable)           # restored for effects still inside the window

    def test_tier3_never_resends(self):
        r = FakeResend()
        g, eid = self.gate(r, FakeStripe("succeeded"), tier=3)
        self.assertEqual(g.recover(), {eid: "AMBIGUOUS"})
        self.assertEqual(r.sends, [])


class Scoring(unittest.TestCase):
    def test_claimed(self):
        self.assertEqual([S.claimed(o) for o in ("SENT_REPLAYED", "ALREADY_SENT", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY",
                                                 "SKIPPED:refund_failed", "REFUSED:stale_premise_at_recovery", "AMBIGUOUS")],
                         [1, 1, 1, 1, 0, 0, None])

    def test_a_log_without_checks_proves_nothing(self):
        self.assertFalse(S.provable_from_log([{"sent": "em_1"}], "SENT", "em_1"))
        self.assertTrue(S.provable_from_log([{"check": "refund_status"}, {"sent": "em_1"}], "SENT", "em_1"))


if __name__ == "__main__":
    unittest.main()
