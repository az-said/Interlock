"""
    python3 -m unittest discover -s tests

Regressions for confirmed defects in escalation, routing, confirmation and scoreboard code.
Each test failed before its fix.
"""
import copy, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from interlock import Gate, Leases, SimulatedCrash, effect_id_for
from interlock.approvals import Authority, Inbox, Route, Rule
from interlock.confirm import confirm_event
from interlock.escalation import explain, record
from interlock.receipts import bundle, verify
from interlock.scoreboard import scoreboard
from interlock.targets import Payments
from interlock.targets.stripe_api import StripeRefunds
from interlock.temporal import Refused, gated
from test_confirmations import SECRET, T, Client, event, header

HOUR = 3600
SUFFIXES = (".jsonl", ".db")


def eid(rid):
    return effect_id_for({"request_id": rid})


class World:
    def __init__(self, suffix=".jsonl", tier=2, total=100, rules=None, routes=(), groups=None, approvers=()):
        self.now = [1000.0]
        self.api = Payments(tier)
        self.api.create_order("1", total)
        self.auth = Authority(approvers=approvers, groups=groups, max_age=4 * HOUR, clock=lambda: self.now[0])
        self.path = tempfile.mktemp(suffix=suffix)
        self.rules = [Rule("small", lambda r, f: r["amount"] <= 50)] if rules is None else rules
        self.routes = routes
        self.ibx = self.inbox()

    def inbox(self):
        return Inbox(Gate(self.api, self.path, self.auth), capture=lambda r: self.api.capture(r["order"]),
                     effect=lambda r: {"order": r["order"], "amount": r["amount"]}, rules=self.rules,
                     routes=self.routes, clock=lambda: self.now[0])

    def hand(self, amount, name="hand"):
        self.api.refunds.append({"eid": name, "order": "1", "amount": amount})

    def proposal(self, request, lease, facts):
        return self.ibx._proposal(request, lease, facts)


class PersonLeaseAtDispatch(unittest.TestCase):
    """Defects 1, 2, 10, 11: dispatch binds a person's lease to the escalation's facts and group (I7)."""

    def test_approval_lease_on_facts_the_approver_never_saw_is_not_sent(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, groups={"controllers": {"alice"}}, routes=[Route("big", ["controllers"])])
                r = {"id": "r1", "order": "1", "amount": 80}
                self.assertEqual(w.ibx.submit(r), "QUEUED")
                self.assertEqual(w.ibx.approve("r1", "alice", execute=False), "APPROVED")
                a = w.ibx.approved["r1"]
                w.hand(30)
                status = w.ibx.gate.submit(w.proposal(r, a["authority"], w.api.capture("1")))
                self.assertNotEqual(status, "COMMITTED")
                self.assertEqual(w.api.refunded_total("1"), 30)

    def test_lease_naming_another_group_is_not_sent(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, groups={"controllers": {"alice"}, "ops": {"alice"}},
                          routes=[Route("big", ["controllers"])])
                r = {"id": "r1", "order": "1", "amount": 80}
                w.ibx.submit(r)
                w.ibx.approve("r1", "alice", execute=False)
                a = w.ibx.approved["r1"]
                w.auth.groups["controllers"] = set()
                status = w.ibx.gate.submit(w.proposal(r, dict(a["authority"], group="ops"), a["facts"]))
                self.assertNotEqual(status, "COMMITTED")
                self.assertEqual(w.api.refunded_total("1"), 0)

    def test_honest_approval_still_sends(self):
        w = World(groups={"controllers": {"alice"}}, routes=[Route("big", ["controllers"])])
        w.ibx.submit({"id": "r1", "order": "1", "amount": 80})
        self.assertEqual(w.ibx.approve("r1", "alice"), "COMMITTED")
        self.assertTrue(verify(bundle(w.ibx.gate.journal, eid("r1")))["valid"])


class ExplainPicksTheOutcome(unittest.TestCase):
    """Defect 3: an AMBIGUOUS status is explained by the AMBIGUOUS entry, not a later refusal."""

    def test_ambiguous_after_conflicting_retry(self):
        class Live:
            def is_live(self, lease):
                return True
        api = Payments(3)
        api.create_order("1", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), Live())
        p = lambda amount: {"agent": "a", "lease": "L", "request_id": "r1", "premises": api.capture("1"),
                            "effect": {"order": "1", "amount": amount}}
        with self.assertRaises(SimulatedCrash):
            gate.submit(p(20), crash_after_effect=True)
        self.assertEqual(gate.recover(), {eid("r1"): "AMBIGUOUS"})
        self.assertEqual(gate.submit(p(30)), "REFUSED:conflicting_payload")
        with self.assertRaises(Refused) as ctx:
            gated(gate, p(20))
        self.assertEqual(ctx.exception.escalation["status"], "AMBIGUOUS")
        self.assertIn("unclear whether it happened", str(ctx.exception))
        self.assertEqual(explain(gate.journal.entries(eid("r1")), "AMBIGUOUS")["reason"], "ambiguous")


class ReescalationReason(unittest.TestCase):
    """Defect 4: an awaiting_decision refusal does not replace the stale premise it follows."""

    def test_restart_after_awaiting_decision_keeps_stale_reason_and_repair(self):
        w = World(approvers={"alice"})
        r = {"id": "r1", "order": "1", "amount": 60}
        w.ibx.submit(r)
        w.ibx.approve("r1", "alice", execute=False)
        a = w.ibx.approved["r1"]
        w.hand(30)
        gate = w.ibx.gate
        self.assertEqual(gate.submit(w.proposal(r, a["authority"], a["facts"])), "REFUSED:stale_premise")
        self.assertEqual(gate.submit(w.proposal(r, {"by": "policy", "rules": ["small"]}, w.api.capture("1"))),
                         "REFUSED:awaiting_decision")
        item = w.inbox().queue["r1"]
        self.assertEqual(item["reason"], "stale_premise")
        self.assertEqual([x["code"] for x in item["repairs"]], ["still_fits"])


class BoundRequest(unittest.TestCase):
    """Defects 5, 6: the queue shows and routes the request the journal bound, which is what gets sent."""
    ROUTES = [Route("large", ["controller"], when=lambda i: i["request"]["amount"] > 200),
              Route("default", ["ap-leads"])]
    GROUPS = {"controller": {"cy"}, "ap-leads": {"ana"}}

    def test_retry_with_other_amount_after_crash_routes_by_bound_amount(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, total=400, groups=self.GROUPS, routes=self.ROUTES)
                big = {"id": "r", "order": "1", "amount": 300}
                w.ibx.gate.journal.append("PROPOSED", eid("r"), agent="inbox", lease=None, premises=w.api.capture("1"),
                                          effect={"order": "1", "amount": 300}, request=big)   # crashed before ESCALATED
                self.assertEqual(w.ibx.submit({"id": "r", "order": "1", "amount": 30}), "REFUSED:conflicting_payload")
                item = w.ibx.queue["r"]
                self.assertEqual((item["group"], item["request"]["amount"]), ("controller", 300))
                self.assertEqual(w.ibx.approve("r", "ana"), "REFUSED:lease")
                self.assertEqual(w.api.refunds, [])

    def test_resubmit_with_other_amount_does_not_change_what_queue_shows(self):
        w = World(total=400, groups=self.GROUPS, routes=self.ROUTES)
        self.assertEqual(w.ibx.submit({"id": "r", "order": "1", "amount": 300}), "QUEUED")
        self.assertEqual(w.ibx.submit({"id": "r", "order": "1", "amount": 30}), "QUEUED")
        self.assertEqual(w.ibx.queue["r"]["request"]["amount"], 300)


class StaleRepairs(unittest.TestCase):
    """Defect 13: repairs computed before the world moved again are not shown."""

    def test_restart_after_second_hand_refund_drops_repair(self):
        w = World(approvers={"ana"}, rules=[Rule("under 100", lambda r, f: r["amount"] <= 100)])
        r = {"id": "r1", "order": "1", "amount": 80}
        facts = w.api.capture("1")
        w.hand(30, "hand1")
        self.assertEqual(w.ibx.gate.submit(w.proposal(r, {"by": "policy", "rules": ["under 100"]}, facts)),
                         "REFUSED:stale_premise")
        w.hand(40, "hand2")
        ibx = w.inbox()
        self.assertEqual(ibx.queue["r1"]["repairs"], [])
        self.assertEqual(ibx.repair("r1", "ana"), "REFUSED:no_repair")
        self.assertEqual(w.api.refunded_total("1"), 70)


class Confirmations(unittest.TestCase):
    """Defects 7, 9, 12, 14, 16: out-of-order, foreign or early confirmations."""

    def world(self):
        client = Client()
        target = StripeRefunds(client, "pi_1")
        leases = Leases()
        leases.grant("L")
        gate = Gate(target, tempfile.mktemp(suffix=".jsonl"), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "case-1", "premises": target.capture(), "effect": {"amount": 5000}}
        self.assertEqual(gate.submit(P), "COMMITTED")
        return client, target, gate, P

    def deliver(self, gate, target, refund, **kw):
        p = event(refund, **kw)
        return confirm_event(gate.journal, target, p, header(p), SECRET, now=T)

    def test_late_pending_does_not_downgrade_succeeded(self):
        client, target, gate, P = self.world()
        r = client.refunds[0]
        self.assertEqual(self.deliver(gate, target, {**r, "status": "succeeded"}, type="refund.updated", id="evt_2"),
                         "CONFIRMED")
        self.assertNotEqual(self.deliver(gate, target, {**r, "status": "pending"}, id="evt_1"), "CONFIRMED")
        v = verify(gate.receipt_bundle(P))
        self.assertEqual((v["valid"], v["confirmed_by_target"]), (True, True))
        self.assertEqual(scoreboard(gate.journal, name="bot")["confirmed_by_target"], 1)

    def test_late_succeeded_does_not_overwrite_failed(self):
        client, target, gate, P = self.world()
        r = client.refunds[0]
        self.assertEqual(self.deliver(gate, target, {**r, "status": "failed"}, type="refund.failed", id="evt_f"),
                         "CONFIRMED")
        self.assertNotEqual(self.deliver(gate, target, {**r, "status": "succeeded"}, id="evt_c"), "CONFIRMED")
        self.assertIs(verify(gate.receipt_bundle(P))["confirmed_by_target"], False)

    def test_receipt_reads_final_status_by_precedence(self):
        client, target, gate, P = self.world()
        for status in ("failed", "succeeded", "pending"):           # a journal written before the fix
            gate.journal.append("CONFIRMED", effect_id_for(P), **record(
                "CONFIRMED", via="webhook", event=f"evt_{status}", refund="re_1", status=status, amount=5000,
                payment_intent="pi_1", created=T))
        self.assertIs(verify(gate.receipt_bundle(P))["confirmed_by_target"], False)

    def test_confirmation_of_another_refund_id_is_refused_and_flagged(self):
        client, target, gate, P = self.world()
        other = {**client.refunds[0], "id": "re_hand_with_copied_metadata"}
        self.assertEqual(self.deliver(gate, target, other, id="evt_x"), "REFUSED:mismatch")
        gate.journal.append("CONFIRMED", effect_id_for(P), **record(
            "CONFIRMED", via="webhook", event="evt_x", refund=other["id"], status="succeeded", amount=5000,
            payment_intent="pi_1", created=T))
        v = verify(gate.receipt_bundle(P))
        self.assertFalse(v["valid"])
        self.assertIn("target confirmed a refund other than the one sent", v["problems"])

    def test_confirmed_resend_in_flight_after_resolved_refusal_verifies(self):
        api = Payments(2)
        api.create_order("o1", 100)
        auth = Authority(approvers={"ana"}, clock=lambda: 1000.0)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), auth)
        inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                      effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                      rules=[Rule("small", lambda r, f: r["amount"] <= 50)], clock=lambda: 1000.0)
        r = {"id": "req1", "order": "o1", "amount": 40}
        with self.assertRaises(SimulatedCrash):
            gate.submit(inbox._proposal(r, {"by": "policy", "rules": ["small"]}, api.capture("o1")), crash_before_effect=True)
        api.refunds.append({"eid": "hand", "order": "o1", "amount": 10})
        self.assertEqual(gate.recover(), {eid("req1"): "REFUSED:stale_premise_at_recovery"})
        inbox.refresh()
        self.assertEqual(inbox.approve("req1", "ana", execute=False), "APPROVED")
        a = inbox.approved.pop("req1")
        with self.assertRaises(SimulatedCrash):
            gate.submit(inbox._proposal(a["request"], a["authority"], a["facts"]), crash_after_effect=True)

        class Target:
            payment_intent = "pi_1"
        refund = {"id": "re_1", "status": "succeeded", "amount": 40, "payment_intent": "pi_1",
                  "metadata": {"interlock_effect_id": eid("req1")}}
        self.assertEqual(self.deliver(gate, Target(), refund), "CONFIRMED")
        v = verify(bundle(gate.journal, eid("req1")))
        self.assertEqual((v["valid"], v["problems"], v["confirmed_by_target"]), (True, [], True))


class ScoreboardCountsOnce(unittest.TestCase):
    """Defects 8, 15: a stale repair re-shows the same unanswered item; it is not a second escalation."""

    def test_superseded_repair_after_stale_approval(self):
        w = World(approvers={"ana"})
        w.ibx.submit({"id": "req1", "order": "1", "amount": 80})
        w.ibx.approve("req1", "ana", execute=False)
        w.hand(30, "hand1")
        self.assertEqual(w.ibx.execute("req1"), "REFUSED:stale_premise")
        w.hand(10, "hand2")
        self.assertEqual(w.ibx.repair("req1", "ana"), "SUPERSEDED")
        s = scoreboard(w.ibx.gate.journal)
        self.assertEqual((s["requests"], s["stale_approvals_caught"], s["escalated_by_reason"]),
                         (1, 1, {"needs_judgment": 1, "stale_premise": 1}))

    def test_superseded_repair_after_crash(self):
        groups = {"ap-leads": {"ana"}}
        w = World(total=100, groups=groups, rules=[Rule("small", lambda r, f: r["amount"] <= 50)],
                  routes=[Route("default", ["ap-leads"], sla=4 * HOUR)])
        r = {"id": "r", "order": "1", "amount": 40}
        with self.assertRaises(SimulatedCrash):
            w.ibx.gate.submit(w.proposal(r, {"by": "policy", "rules": []}, w.api.capture("1")), crash_before_effect=True)
        w.hand(80, "dash")
        ibx = w.inbox()
        ibx.reconcile(ibx.gate.recover())
        self.assertEqual([x["code"] for x in ibx.queue["r"]["repairs"]], ["refund_remaining"])
        w.hand(5, "dash2")
        self.assertEqual(ibx.repair("r", "ana"), "SUPERSEDED")
        s = scoreboard(ibx.gate.journal)
        self.assertEqual((s["requests"], s["crash_to_person"], s["escalated_by_reason"], s["repairs_suggested"]),
                         (1, 1, {"stale_premise_at_recovery": 1}, 1))


class TamperedReceipt(unittest.TestCase):
    """Defect 17: verify reports a tampered escalated receipt instead of raising."""

    def test_missing_hash_or_kind_is_a_problem(self):
        w = World(approvers={"ana"})
        w.ibx.submit({"id": "r1", "order": "1", "amount": 80})
        w.ibx.approve("r1", "ana")
        b = bundle(w.ibx.gate.journal, eid("r1"))
        for field in ("hash", "kind"):
            with self.subTest(field):
                t = copy.deepcopy(b)
                del next(e for e in t["entries"] if e["kind"] == "ESCALATED")[field]
                v = verify(t)
                self.assertFalse(v["valid"])
                self.assertTrue(any("was altered" in p for p in v["problems"]))


if __name__ == "__main__":
    unittest.main()
