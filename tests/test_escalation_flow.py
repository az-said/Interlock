"""
    python3 -m unittest discover -s tests

The lanes together: a real gate refusal becomes a routed escalation, a person's decision
becomes the send's authority, verify() checks it, a signed webhook confirms it, and the
scoreboard reads it all back from the journal, before and after a restart.
"""
import os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, SimulatedCrash, effect_id_for
from interlock.approvals import Authority, Inbox, Route, Rule
from interlock.confirm import confirm_event
from interlock.escalation import explain
from interlock.receipts import bundle, verify
from interlock.scoreboard import CRASH, scoreboard
from interlock.targets import Payments
from interlock.targets.stripe_api import StripeRefunds
from interlock.temporal import gated
from test_confirmations import SECRET, T, Client, event, header


def eid(rid):
    return effect_id_for({"request_id": rid})


class HandRefundAfterCapture(Payments):
    """Support refunds part of the order by hand once, right after the agent reads the facts."""
    def __init__(self, hand):
        super().__init__(2)
        self.hand = hand

    def capture(self, order_id):
        facts = super().capture(order_id)
        if self.hand:
            self.refunds.append({"eid": "dashboard", "order": order_id, "amount": self.hand})
            self.hand = 0
        return facts


class Flow(unittest.TestCase):
    def inbox(self, api, limit, path=None, groups=None, routes=(), capture=None, effect=None):
        self.path = path or getattr(self, "path", None) or tempfile.mktemp(suffix=".jsonl")
        auth = Authority(approvers={"alice"}, groups=groups, clock=lambda: 1000.0)
        return Inbox(Gate(api, self.path, auth),
                     capture=capture or (lambda r: api.capture(r["order"])),
                     effect=effect or (lambda r: {"order": r["order"], "amount": r["amount"]}),
                     rules=[Rule(f"amount under {limit}", lambda r, facts: r["amount"] <= limit)],
                     routes=routes, clock=lambda: 1000.0)

    def test_partial_hand_refund_end_to_end(self):
        api = HandRefundAfterCapture(30)
        api.create_order("1", 100)
        ibx = self.inbox(api, 50)
        self.assertEqual(ibx.submit({"id": "r1", "order": "1", "amount": 50}), "REFUSED:stale_premise")
        item = ibx.queue["r1"]
        self.assertEqual((item["reason"], item["changes"]), ("stale_premise", [{"field": "refunded", "was": 0, "now": 30}]))
        self.assertEqual([x["code"] for x in item["repairs"]], ["still_fits"])
        self.assertEqual(item["facts"]["refunded"], 30)

        self.assertEqual(ibx.approve("r1", "alice", seen=item["escalation"]), "COMMITTED")
        r = verify(bundle(ibx.gate.journal, eid("r1")))
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual((r["approved_by"], r["approval_verified"]), ("alice", True))
        self.assertEqual(api.refunded_total("1"), 80)
        s = scoreboard(ibx.gate.journal)
        self.assertEqual((s["escalated_by_reason"], s["sent_after_person"], s["cleared_no_person"]),
                         ({"stale_premise": 1}, 1, 0))

    def test_accepting_still_fits_counts_as_an_accepted_repair(self):
        api = HandRefundAfterCapture(30)
        api.create_order("1", 100)
        ibx = self.inbox(api, 50)
        ibx.submit({"id": "r1", "order": "1", "amount": 50})
        self.assertEqual(ibx.repair("r1", "alice", seen=ibx.queue["r1"]["escalation"]), "COMMITTED")
        r = verify(bundle(ibx.gate.journal, eid("r1")))
        self.assertTrue(r["valid"], r["problems"])
        s = scoreboard(ibx.gate.journal)
        self.assertEqual((s["repairs_accepted"], s["closed_by_repair"], api.refunded_total("1")), (1, 0, 80))

    def test_refund_remaining_repair_end_to_end(self):
        api = HandRefundAfterCapture(30)
        api.create_order("1", 100)
        ibx = self.inbox(api, 100)
        self.assertEqual(ibx.submit({"id": "r1", "order": "1", "amount": 100}), "REFUSED:stale_premise")
        e = ibx.queue["r1"]
        self.assertEqual([(x["code"], x["set"]) for x in e["repairs"]], [("refund_remaining", {"amount": 70})])

        self.assertEqual(ibx.repair("r1", "alice", seen=e["escalation"]), "COMMITTED")    # $70 passes the rules
        child = f"r1:repair:{e['escalation'][:8]}"
        self.assertEqual(api.refunded_total("1"), 100)
        self.assertEqual(ibx.gate.submit(ibx._proposal({"id": "r1", "order": "1", "amount": 100}, {"by": "policy", "rules": []},
                                                       api.capture("1"))), "REFUSED:closed")
        for rid in ("r1", child):
            r = verify(bundle(ibx.gate.journal, eid(rid)))
            self.assertTrue(r["valid"], (rid, r["problems"]))
        self.assertEqual(api.refunded_total("1"), 100)
        s = scoreboard(ibx.gate.journal)
        self.assertEqual((s["requests"], s["repairs_accepted"], s["closed_by_repair"], s["repairs_suggested"]), (1, 1, 1, 1))

    def test_crash_to_person_then_webhook_confirmation(self):
        class PI(Client):
            def request(self, method, path, params=None, idempotency_key=None):
                if method == "GET" and path == "/payment_intents/pi_1":
                    return {"id": "pi_1", "amount_received": 10000}
                return super().request(method, path, params, idempotency_key)

        class CrashOnce(StripeRefunds):
            crash = True
            def apply(self, eid, effect, crash_after_effect=False):
                if self.crash:
                    self.crash = False
                    raise SimulatedCrash(eid)         # dies before the request leaves
                return super().apply(eid, effect, crash_after_effect)

        client = PI()
        target = CrashOnce(client, "pi_1")
        ibx = self.inbox(target, 5000, groups={"payments-ops": {"ops"}},
                         routes=[Route("crash", ["payments-ops"], when=lambda i: i["reason"] in CRASH)],
                         capture=lambda r: target.capture(), effect=lambda r: {"amount": r["amount"]})
        with self.assertRaises(SimulatedCrash):
            ibx.submit({"id": "r1", "amount": 5000})
        client.refunds.append({"id": "re_hand", "object": "refund", "amount": 3000, "status": "succeeded",
                               "payment_intent": "pi_1", "metadata": {}, "created": T})
        ibx.reconcile(ibx.gate.recover())
        item = ibx.queue["r1"]
        self.assertEqual((item["reason"], item["group"], [x["code"] for x in item["repairs"]]),
                         ("stale_premise_at_recovery", "payments-ops", ["still_fits"]))
        self.assertEqual(ibx.approve("r1", "alice"), "REFUSED:lease")            # not routed to her
        self.assertEqual(ibx.repair("r1", "ops"), "COMMITTED")                    # still_fits: same payload, re-decided

        refund = client.refunds[-1]
        p = event(refund)
        self.assertEqual(confirm_event(ibx.gate.journal, target, p, header(p), SECRET, now=T), "CONFIRMED")
        r = verify(bundle(ibx.gate.journal, eid("r1")))
        self.assertTrue(r["valid"], r["problems"])
        self.assertEqual((r["confirmed_by_target"], r["approved_by"], r["approval_verified"]), (True, "ops", True))
        self.assertEqual(len([x for x in client.refunds if x["metadata"]]), 1)
        s = scoreboard(ibx.gate.journal)
        self.assertEqual((s["confirmed_by_target"], s["crash_to_person"]), (1, 1))

    def test_restart_mid_day_scoreboard_identical(self):
        api = HandRefundAfterCapture(30)
        for order in ("1", "2", "3", "4"):
            api.create_order(order, 100)
        ibx = self.inbox(api, 50)
        ibx.submit({"id": "stale", "order": "1", "amount": 50})               # escalated with a change
        ibx.submit({"id": "routine", "order": "2", "amount": 20})             # cleared
        ibx.submit({"id": "big", "order": "3", "amount": 90})                 # needs judgment
        ibx.approve("big", "alice", execute=False)                             # approved, not yet sent
        ibx.submit({"id": "other", "order": "4", "amount": 80})
        ibx.reject("other", "alice")
        before, n = scoreboard(ibx.gate.journal), len(ibx.gate.journal.entries())

        again = self.inbox(api, 50)
        self.assertEqual(scoreboard(again.gate.journal), before)
        self.assertEqual(len(again.gate.journal.entries()), n)
        self.assertEqual((again.queue, again.approved, again.cleared), (ibx.queue, ibx.approved, ibx.cleared))
        self.assertEqual(again.execute_approved(), {"big": "COMMITTED"})
        self.assertEqual(self.inbox(api, 50).approved, {})

    def test_mcp_and_temporal_describe_match_inbox_changes(self):
        api = Payments(2)
        api.create_order("1", 100)
        ibx = self.inbox(api, 100)
        r = {"id": "r1", "order": "1", "amount": 80}
        stale = api.capture("1")
        api.refunds.append({"eid": "dashboard", "order": "1", "amount": 30})
        with self.assertRaises(Exception) as cm:                               # a Temporal activity hits the refusal
            gated(ibx.gate, ibx._proposal(r, {"by": "policy", "rules": []}, stale))
        self.assertTrue(str(cm.exception).startswith("interlock: REFUSED:stale_premise"))
        temporal = getattr(cm.exception, "escalation", None) or cm.exception.details[0]
        proxy = explain(ibx.gate.journal.entries(eid("r1")))                   # what the MCP proxy puts in _meta
        restarted = self.inbox(api, 100)                                       # the inbox picks it up from the journal
        item = restarted.queue["r1"]
        want = [{"field": "refunded", "was": 0, "now": 30}]
        self.assertEqual((temporal["changes"], proxy["changes"], item["changes"]), (want, want, want))
        self.assertEqual(temporal["repairs"], item["repairs"])
        self.assertEqual(len([x for x in restarted.gate.journal.entries() if x["kind"] == "ESCALATED"]), 1)


if __name__ == "__main__":
    unittest.main()
