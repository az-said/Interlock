"""
    python3 -m unittest discover -s tests

The escalation contract every lane builds on: atomic append_if, the gate refusing to send an
escalated effect without a person's decision on its latest escalation, and the shared shapes.
"""
import os, sys, tempfile, threading, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, SimulatedCrash, effect_id_for
from interlock.approvals import Authority
from interlock.escalation import WHY, describe, explain, record
from interlock.journal import entry_hash, open_journal
from interlock.targets import Payments

POLICY = {"by": "policy", "rules": []}


def esc(facts, reason="needs_judgment"):
    return record("ESCALATED", at=1, reason=reason, why=WHY[reason], detail=[], facts=facts, changes=[],
                  repairs=[], route="default", group=None, routed_to=["alice"], level=0, due=None, breach=False)


def dec(e, at, decision="approve"):
    return record("DECIDED", at=at, by="alice", decision=decision, escalation=e["hash"], group=None,
                  members=["alice"], repair=None)


class AppendIf(unittest.TestCase):
    def test_append_if_writes_once_under_threads(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(suffix):
                path = tempfile.mktemp(suffix=suffix)
                open_journal(path).append("PROPOSED", "e", effect={})
                none_yet = lambda es: "exists" if any(x["kind"] == "X" for x in es) else None
                threads = [threading.Thread(target=lambda: open_journal(path).append_if("X", "e", none_yet))
                           for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                es = open_journal(path).entries("e")
                self.assertEqual([x["kind"] for x in es], ["PROPOSED", "X"])
                self.assertEqual(es[1]["prev"], es[0]["hash"])
                self.assertTrue(all(entry_hash(x) == x["hash"] for x in es))

    def test_append_if_blocker_writes_nothing(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(suffix):
                j = open_journal(tempfile.mktemp(suffix=suffix))
                j.append("PROPOSED", "e", effect={})
                self.assertEqual(j.append_if("X", "e", lambda es: "no"), (None, "no"))
                self.assertEqual(len(j.entries("e")), 1)
                entry, blocker = j.append_if("X", "e", lambda es: None, n=1)
                self.assertEqual((entry["n"], blocker, len(j.entries("e"))), (1, None, 2))


class GateBlocker(unittest.TestCase):
    def setUp(self):
        self.api = Payments(2)
        self.api.create_order("1", 100)
        self.gate = Gate(self.api, tempfile.mktemp(suffix=".jsonl"), Authority(approvers={"alice"}))
        self.eid = effect_id_for({"request_id": "r1"})

    def proposal(self, lease, **extra):
        return {"agent": "inbox", "lease": lease, "request_id": "r1", "premises": self.api.capture("1"),
                "effect": {"order": "1", "amount": 50}, **extra}

    def escalate(self):
        self.assertEqual(self.gate.submit(self.proposal("dead")), "REFUSED:lease")
        return self.gate.journal.append("ESCALATED", self.eid, **esc(self.api.capture("1")))

    def kinds(self):
        return [x["kind"] for x in self.gate.journal.entries(self.eid)]

    def test_policy_send_over_open_escalation_is_awaiting_decision(self):
        self.escalate()
        self.assertEqual(self.gate.submit(self.proposal(POLICY)), "REFUSED:awaiting_decision")
        self.assertNotIn("DISPATCHED", self.kinds())
        self.assertEqual(self.gate.journal.entries(self.eid)[-1]["code"], "awaiting_decision")

    def test_person_lease_needs_decision_on_latest_escalation(self):
        e1 = self.escalate()
        self.gate.journal.append("DECIDED", self.eid, **dec(e1, at=2))
        e2 = self.gate.journal.append("ESCALATED", self.eid, **esc(self.api.capture("1"), "approval_expired"))
        stale = {"by": "alice", "at": 2, "group": None, "escalation": e1["hash"]}
        self.assertEqual(self.gate.submit(self.proposal(stale)), "REFUSED:awaiting_decision")
        self.gate.journal.append("DECIDED", self.eid, **dec(e2, at=3))
        live = {"by": "alice", "at": 3, "group": None, "escalation": e2["hash"]}
        self.assertEqual(self.gate.submit(self.proposal(live)), "COMMITTED")
        self.assertEqual(self.api.refunded_total("1"), 50)

    def test_closed_effect_is_never_dispatched(self):
        e = self.escalate()
        self.gate.journal.append("DECIDED", self.eid, **dec(e, at=2, decision="reject"))
        lease = {"by": "alice", "at": 2, "group": None, "escalation": e["hash"]}
        self.assertEqual(self.gate.submit(self.proposal(lease)), "REFUSED:closed")
        self.assertEqual(self.api.refunded_total("1"), 0)

    def test_gate_records_code_and_request(self):
        codes = lambda gate, eid: [x.get("code") for x in gate.journal.entries(eid) if x["kind"] in ("REFUSED", "AMBIGUOUS")]
        g = self.gate
        self.assertEqual(g.submit(self.proposal(POLICY, request={"id": "r1"})), "COMMITTED")
        self.assertEqual(g.journal.entries(self.eid)[0]["request"], {"id": "r1"})
        other = {**self.proposal(POLICY), "effect": {"order": "1", "amount": 60}}
        self.assertEqual(g.submit(other), "REFUSED:conflicting_payload")
        self.assertNotIn("request", g.journal.entries(self.eid)[-2])

        def fresh(tier, rid):
            api = Payments(tier)
            api.create_order("1", 100)
            p = {"agent": "a", "lease": POLICY, "request_id": rid, "premises": api.capture("1"),
                 "effect": {"order": "1", "amount": 10}}
            return api, Gate(api, tempfile.mktemp(suffix=".jsonl"), Authority(), claim_ttl=0), p, effect_id_for(p)

        api, g2, p, eid = fresh(2, "sym")
        g2.claim("other", "f")
        self.assertEqual(g2.submit({**p, "defines": ["f"]}), "REFUSED:duplicate_symbol")
        self.assertEqual(g2.submit({**p, "lease": "dead"}), "REFUSED:lease")
        api.refunds.append({"eid": "hand", "order": "1", "amount": 30})
        self.assertEqual(g2.submit(p), "REFUSED:stale_premise")
        self.assertEqual(codes(g2, eid), ["duplicate_symbol", "lease", "stale_premise"])

        api, g3, p, eid = fresh(2, "rec")
        with self.assertRaises(SimulatedCrash):
            g3.submit(p, crash_before_effect=True)
        api.refunds.append({"eid": "hand", "order": "1", "amount": 30})
        self.assertEqual(g3.recover(), {eid: "REFUSED:stale_premise_at_recovery"})

        api, g4, p, eid4 = fresh(2, "fail")
        with self.assertRaises(SimulatedCrash):
            g4.submit(p, crash_before_effect=True)
        self.assertEqual(g4.settle_failed(eid4, "boom"), "REFUSED:target_error")

        api, g5, p, eid5 = fresh(3, "amb")
        with self.assertRaises(SimulatedCrash):
            g5.submit(p, crash_after_effect=True)
        self.assertEqual(g5.recover(), {eid5: "AMBIGUOUS"})
        self.assertEqual([codes(g3, eid), codes(g4, eid4), codes(g5, eid5)],
                         [["stale_premise_at_recovery"], ["target_error"], ["ambiguous"]])


class Shapes(unittest.TestCase):
    def test_record_rejects_missing_or_unknown_fields(self):
        full = dict(via="webhook", event="evt_1", refund="re_1", status="succeeded", amount=50,
                    payment_intent="pi_1", created=1)
        self.assertEqual(record("CONFIRMED", **full), full)
        with self.assertRaises(ValueError):
            record("CONFIRMED", **{k: v for k, v in full.items() if k != "event"})
        with self.assertRaises(ValueError):
            record("CONFIRMED", secret="whsec", **full)

    def test_explain_and_describe_on_old_entries(self):
        old = [{"kind": "PROPOSED", "effect_id": "e"}, {"kind": "REFUSED", "effect_id": "e", "reason": ["x"]}]
        self.assertEqual((explain(old)["reason"], explain(old)["changes"], explain(old)["status"]),
                         ("refused", [], "REFUSED"))
        stale = old[:1] + [{"kind": "REFUSED", "effect_id": "e", "code": "stale_premise",
                            "changes": [{"field": "refunded", "was": 0, "now": 30}],
                            "repairs": [{"code": "remaining", "set": {"amount": 70}, "why": "refund the remaining $70"}]}]
        text = describe(explain(stale))
        self.assertIn("refunded was 0, now 30", text)
        self.assertIn("Suggested, needs rules or a person: refund the remaining $70", text)
        self.assertIsNone(explain(stale + [{"kind": "COMMITTED", "effect_id": "e"}]))


if __name__ == "__main__":
    unittest.main()
