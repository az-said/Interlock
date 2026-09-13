"""
    python3 -m unittest discover -s tests

Escalations in receipts: verify() checks that a send a person authorized has that person's
decision, on the facts they saw, before the send, from someone the item was routed to, and
reports what the target itself confirmed.
"""
import os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, SimulatedCrash, effect_id_for
from interlock.approvals import Authority
from interlock.escalation import WHY, record
from interlock.journal import _seal
from interlock.receipts import bundle, verify
from interlock.targets import Payments

KEY = "shared-with-the-payment-service"
POLICY = {"by": "policy", "rules": []}


def esc(facts, reason="stale_premise", group=None):
    return record("ESCALATED", at=10, reason=reason, why=WHY[reason], detail="REFUSED:stale_premise", facts=facts,
                  changes=[{"field": "refunded", "was": 0, "now": 30}], repairs=[], route="default", group=group,
                  routed_to=["alice"], level=0, due=None, breach=False)


def dec(e, at=20, by="alice", decision="approve", group=None, members=("alice",)):
    return record("DECIDED", at=at, by=by, decision=decision, escalation=e["hash"], group=group,
                  members=sorted(members), repair=None)


def confirmed(status="succeeded", amount=50, refund="re_1", event="evt_1"):
    return record("CONFIRMED", via="webhook", event=event, refund=refund, status=status, amount=amount,
                  payment_intent="pi_1", created=1)


def reseal(entries):
    out, prev = [], None
    for e in entries:
        prev = _seal({k: v for k, v in e.items() if k not in ("prev", "hash")}, prev)
        out.append(prev)
    return out


def problems(r):
    return " ".join(r["problems"])


class EscalationReceipts(unittest.TestCase):
    def setUp(self):
        self.api = Payments(2)
        self.api.create_order("1", 100)
        self.gate = Gate(self.api, tempfile.mktemp(suffix=".jsonl"), Authority(approvers={"alice"}))
        self.eid = effect_id_for({"request_id": "r1"})

    def proposal(self, lease, premises=None):
        return {"agent": "inbox", "lease": lease, "request_id": "r1",
                "premises": premises or self.api.capture("1"), "effect": {"order": "1", "amount": 50}}

    def approved(self, **decided):
        """A $50 policy send refused after a $30 hand refund, escalated, approved by alice, sent on her facts."""
        stale = self.api.capture("1")
        self.api.refunds.append({"eid": "hand", "order": "1", "amount": 30})
        self.assertEqual(self.gate.submit(self.proposal(POLICY, stale)), "REFUSED:stale_premise")
        facts = self.api.capture("1")
        e = self.gate.journal.append("ESCALATED", self.eid, **esc(facts))
        d = self.gate.journal.append("DECIDED", self.eid, **dec(e, **decided))
        lease = {"by": d["by"], "at": d["at"], "group": d["group"], "escalation": e["hash"]}
        self.assertEqual(self.gate.submit(self.proposal(lease, facts)), "COMMITTED")
        return self.gate.journal.entries(self.eid)

    def check(self, entries, key=None):
        b = {"effect_id": self.eid, "entries": entries}
        return verify(b, key)

    def test_person_approved_send_verifies(self):
        self.approved()
        r = verify(bundle(self.gate.journal, self.eid, KEY), KEY)
        self.assertEqual((r["valid"], r["signed"], r["happened"], r["authorized_when_fired"]), (True, True, True, True), r)
        self.assertEqual((r["approved_by"], r["approval_verified"]), ("alice", True))
        self.assertEqual(len(r["escalations"]), 1)
        h = r["escalations"][0]
        self.assertEqual((h["reason"], h["group"], h["routed_to"], h["level"], h["breach"], h["repairs"]),
                         ("stale_premise", None, ["alice"], 0, False, 0))
        self.assertEqual(h["changes"], [{"field": "refunded", "was": 0, "now": 30}])
        self.assertEqual(h["decision"], {"by": "alice", "decision": "approve", "at": 20})
        self.assertEqual((r["confirmed_by_target"], r["confirmation"]), (None, []))

    def test_decision_by_someone_not_routed_is_a_problem(self):
        for decided in ({"members": ("bob",)}, {"group": "ops", "members": ("alice",)}):
            with self.subTest(**decided):
                self.setUp()
                r = self.check(self.approved(**decided))
                self.assertFalse(r["valid"])
                self.assertIs(r["approval_verified"], False)
                self.assertIn("decided by someone the item was not routed to", problems(r))

    def test_send_citing_superseded_escalation_is_a_problem(self):
        es = self.approved()
        k = [e["kind"] for e in es]
        e2 = {**es[k.index("ESCALATED")], "at": 30, "reason": "approval_expired"}
        at = k.index("DECIDED") + 1
        r = self.check(reseal(es[:at] + [e2] + es[at:]))
        self.assertFalse(r["valid"])
        self.assertIn("sent without the decision its latest escalation asked for", problems(r))
        self.assertEqual(len(r["escalations"]), 2)

        at = k.index("ESCALATED") + 1
        r = self.check(reseal(es[:at] + [e2] + es[at:]))     # the decision answers an escalation already replaced
        self.assertIn("a decision answers an escalation that was superseded or missing", problems(r))

    def test_send_on_facts_the_approver_never_saw_is_a_problem(self):
        es = self.approved()
        d = next(x for x in es if x["kind"] == "DISPATCHED")
        d["premises"] = {**d["premises"], "refunded": 0}
        r = self.check(reseal(es))
        self.assertEqual(problems(r), "sent on facts the approver never saw")

    def test_decision_after_the_send_is_a_problem(self):
        es = self.approved()
        signature = bundle(self.gate.journal, self.eid, KEY)["signature"]
        d = next(x for x in es if x["kind"] == "DECIDED")
        moved = [x for x in es if x is not d]
        at = [x["kind"] for x in moved].index("COMMITTED")
        forged = {"effect_id": self.eid, "entries": reseal(moved[:at] + [d] + moved[at:]), "signature": signature}
        self.assertEqual(forged["entries"][-2]["kind"], "DECIDED")
        r = verify(forged)
        self.assertFalse(r["valid"])
        self.assertIn("a person's send has no matching decision", problems(r))
        self.assertIs(verify(forged, KEY)["signed"], False)

    def test_policy_send_after_escalation_is_a_problem(self):
        self.assertEqual(self.gate.submit(self.proposal(POLICY)), "COMMITTED")
        es = self.gate.journal.entries(self.eid)
        at = [x["kind"] for x in es].index("DISPATCHED")
        r = self.check(reseal(es[:at] + [{"ts": es[0]["ts"], "kind": "ESCALATED", "effect_id": self.eid, **esc(self.api.capture("1"))}] + es[at:]))
        self.assertFalse(r["valid"])
        self.assertIn("sent without the decision its latest escalation asked for", problems(r))
        self.assertIsNone(r["approved_by"])

    def test_send_after_close_is_a_problem(self):
        es = self.approved()
        next(x for x in es if x["kind"] == "DECIDED")["decision"] = "reject"
        r = self.check(reseal(es))
        self.assertIn("sent after a person closed it", problems(r))
        self.assertEqual(r["escalations"][0]["decision"]["decision"], "reject")

    def test_two_decisions_on_one_escalation_is_a_problem(self):
        stale = self.api.capture("1")
        self.api.refunds.append({"eid": "hand", "order": "1", "amount": 30})
        self.gate.submit(self.proposal(POLICY, stale))
        facts = self.api.capture("1")
        e = self.gate.journal.append("ESCALATED", self.eid, **esc(facts))
        self.gate.journal.append("DECIDED", self.eid, **dec(e))
        self.gate.journal.append("DECIDED", self.eid, **dec(e, at=21, decision="reject"))
        r = self.check(self.gate.journal.entries(self.eid))
        self.assertIn("decided twice", problems(r))
        self.assertIs(r["approval_verified"], False)

    def test_legacy_person_lease_stays_valid(self):
        lease = {"by": "alice", "at": 5}
        self.assertEqual(self.gate.submit(self.proposal(lease)), "COMMITTED")
        r = self.check(self.gate.journal.entries(self.eid))
        self.assertEqual((r["valid"], r["approved_by"], r["approval_verified"], r["escalations"]), (True, "alice", None, []))

        self.setUp()
        self.assertEqual(self.gate.submit(self.proposal(POLICY)), "COMMITTED")
        r = self.check(self.gate.journal.entries(self.eid))
        self.assertEqual((r["valid"], r["approved_by"], r["approval_verified"]), (True, None, None))

    def test_send_citing_an_escalation_not_in_the_receipt_is_a_problem(self):
        es = self.approved()
        r = self.check(reseal([x for x in es if x["kind"] not in ("ESCALATED", "DECIDED")]))
        self.assertIn("a send cites an escalation that is not in the receipt", problems(r))
        self.assertIs(r["approval_verified"], False)

    def test_confirmed_by_target_follows_last_status(self):
        self.approved()
        j = self.gate.journal
        j.append("CONFIRMED", self.eid, **confirmed())
        r = self.check(j.entries(self.eid))
        self.assertEqual((r["valid"], r["confirmed_by_target"]), (True, True), r)
        j.append("CONFIRMED", self.eid, **confirmed("failed", event="evt_2"))
        self.assertIs(self.check(j.entries(self.eid))["confirmed_by_target"], False)
        j.append("CONFIRMED", self.eid, **confirmed("pending", event="evt_3"))
        r = self.check(j.entries(self.eid))
        self.assertEqual(r["confirmed_by_target"], "pending")
        self.assertEqual(r["confirmation"], [{"via": "webhook", "event": e, "refund": "re_1", "status": s}
                                             for e, s in (("evt_1", "succeeded"), ("evt_2", "failed"), ("evt_3", "pending"))])

    def test_confirmation_without_send_or_wrong_amount_is_a_problem(self):
        self.api.set_eligible("1", False)
        self.gate.submit(self.proposal(POLICY, {**self.api.capture("1"), "eligible": True}))
        self.gate.journal.append("CONFIRMED", self.eid, **confirmed())
        self.assertIn("a confirmation matches no send", problems(self.check(self.gate.journal.entries(self.eid))))

        self.setUp()
        self.gate.submit(self.proposal(POLICY))
        self.gate.journal.append("CONFIRMED", self.eid, **confirmed(amount=5000))
        r = self.check(self.gate.journal.entries(self.eid))
        self.assertIn("target confirmed a different amount", problems(r))

    def test_two_refund_ids_break_happened_once(self):
        self.gate.submit(self.proposal(POLICY))
        self.gate.journal.append("CONFIRMED", self.eid, **confirmed())
        self.gate.journal.append("CONFIRMED", self.eid, **confirmed(refund="re_2", event="evt_2"))
        r = self.check(self.gate.journal.entries(self.eid))
        self.assertEqual((r["valid"], r["happened_once"]), (False, False))
        self.assertIn("target confirmed more than one refund", problems(r))

    def test_confirmation_of_never_landed_effect_is_a_problem(self):
        with self.assertRaises(SimulatedCrash):
            self.gate.submit(self.proposal(POLICY), crash_before_effect=True)
        self.api.refunds.append({"eid": "hand", "order": "1", "amount": 30})
        self.gate.recover()
        self.gate.journal.append("CONFIRMED", self.eid, **confirmed())
        r = self.check(self.gate.journal.entries(self.eid))
        self.assertIn("target confirmed an effect the journal says never landed", problems(r))
        self.assertIs(r["happened"], False)


if __name__ == "__main__":
    unittest.main()
