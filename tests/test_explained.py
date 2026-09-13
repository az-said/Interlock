"""
    python3 -m unittest discover -s tests

Explained refusals: a stale or unverifiable outcome names what changed and, where nothing
landed, suggests safe repairs. Suggestions only: nothing here sends a repair.
"""
import json, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock import Gate, Interlock, Leases, SimulatedCrash
from interlock.escalation import explain
from interlock.journal import effect_id_for
from interlock.targets import Payments
from interlock.targets.stripe_api import StripeError, StripeRefunds
from interlock.temporal import InFlight, Refused, gated

try:
    import temporalio  # noqa: F401
    HAS_TEMPORAL = True
except ImportError:
    HAS_TEMPORAL = False


def last(gate, kind, eid):
    return [e for e in gate.journal.entries(eid) if e["kind"] == kind][-1]


class Explained(unittest.TestCase):
    def setup(self, tier=2, amount=50):
        self.api = Payments(tier)
        self.api.create_order("881", 100)
        self.leases = Leases()
        self.leases.grant("L")
        self.gate = Gate(self.api, tempfile.mktemp(suffix=".jsonl"), self.leases)
        self.P = {"agent": "bot", "lease": "L", "request_id": "case-4471",
                  "premises": self.api.capture("881"), "effect": {"order": "881", "amount": amount}}
        self.eid = effect_id_for(self.P)

    def hand_refund(self, amount):
        self.api.refunds.append({"eid": "by-hand", "order": "881", "amount": amount})

    def refused(self, amount):
        self.setup(amount=amount)
        self.hand_refund(30)
        self.assertEqual(self.gate.submit(self.P), "REFUSED:stale_premise")
        return last(self.gate, "REFUSED", self.eid)

    def test_stale_refusal_names_the_change(self):
        r = self.refused(50)
        self.assertEqual(r["changes"], [{"field": "refunded", "was": 0, "now": 30}])
        self.assertEqual(r["reason"], ["refunded elsewhere since decision"])
        self.assertEqual(r["checks"]["violations"], ["refunded elsewhere since decision"])
        self.assertEqual(r["code"], "stale_premise")

    def test_partial_hand_refund_suggests_same_amount_when_it_fits(self):
        r = self.refused(50)
        self.assertEqual([(x["code"], x["set"]) for x in r["repairs"]], [("still_fits", {})])
        self.assertIn("70", r["repairs"][0]["why"])

    def test_over_remaining_suggests_refund_remaining(self):
        r = self.refused(80)
        self.assertEqual([(x["code"], x["set"]) for x in r["repairs"]], [("refund_remaining", {"amount": 70})])

    def test_full_hand_refund_or_ineligible_suggests_nothing(self):
        self.setup()
        self.hand_refund(100)
        self.assertEqual(self.gate.submit(self.P), "REFUSED:stale_premise")
        r = last(self.gate, "REFUSED", self.eid)
        self.assertEqual(r["changes"], [{"field": "refunded", "was": 0, "now": 100}])
        self.assertNotIn("repairs", r)

        self.setup()
        self.api.set_eligible("881", False)
        self.assertEqual(self.gate.submit(self.P), "REFUSED:stale_premise")
        r = last(self.gate, "REFUSED", self.eid)
        self.assertEqual(r["changes"], [{"field": "eligible", "was": True, "now": False}])
        self.assertNotIn("repairs", r)

    def test_target_without_explain_still_refuses_with_strings(self):
        class Plain:
            tier = 2
            def validate_premises(self, premises, eid=None):
                return ["file changed"]
            def apply(self, eid, effect, crash_after_effect=False):
                raise AssertionError("never sent")
        leases = Leases()
        leases.grant("L")
        gate = Gate(Plain(), tempfile.mktemp(suffix=".jsonl"), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "w1", "premises": {}, "effect": {"path": "a.py"}}
        self.assertEqual(gate.submit(P), "REFUSED:stale_premise")
        r = last(gate, "REFUSED", effect_id_for(P))
        self.assertEqual(r["reason"], ["file changed"])
        self.assertNotIn("changes", r)
        self.assertNotIn("repairs", r)

    def test_refusal_at_recovery_carries_changes_and_repairs(self):
        self.setup(tier=2)
        with self.assertRaises(SimulatedCrash):
            self.gate.submit(self.P, crash_before_effect=True)
        self.hand_refund(30)
        self.assertEqual(self.gate.recover(), {self.eid: "REFUSED:stale_premise_at_recovery"})
        r = last(self.gate, "REFUSED", self.eid)
        self.assertTrue(r["resolves"])
        self.assertEqual(r["changes"], [{"field": "refunded", "was": 0, "now": 30}])
        self.assertEqual(r["repairs"][0]["code"], "still_fits")

    def test_ambiguous_never_carries_repairs(self):
        self.setup(tier=1)
        self.api.queryable = False                                   # stale at recovery, and no lookup
        with self.assertRaises(SimulatedCrash):
            self.gate.submit(self.P, crash_before_effect=True)
        self.hand_refund(30)
        self.assertEqual(self.gate.recover(), {self.eid: "AMBIGUOUS"})
        a = last(self.gate, "AMBIGUOUS", self.eid)
        self.assertEqual(a["code"], "ambiguous")
        self.assertEqual(a["changes"], [{"field": "refunded", "was": 0, "now": 30}])
        self.assertNotIn("repairs", a)

    def test_stripe_explain_with_fake_client(self):
        class Fake:
            def __init__(self):
                self.refunds, self.pi_fails = [], False
            def request(self, method, path, params=None, idempotency_key=None):
                if path == "/refunds" and method == "GET":
                    return {"data": self.refunds}
                if path == "/payment_intents/pi_test":
                    if self.pi_fails:
                        raise StripeError("500 GET /payment_intents/pi_test: down")
                    return {"id": "pi_test", "amount_received": 10000}
                raise AssertionError(f"unexpected {method} {path}")
        for fails in (False, True):
            with self.subTest(pi_fails=fails):
                client = Fake()
                client.pi_fails = fails
                api = StripeRefunds(client, "pi_test")
                leases = Leases()
                leases.grant("L")
                gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)
                P = {"agent": "bot", "lease": "L", "request_id": "case-1", "premises": api.capture(),
                     "effect": {"amount": 8000}}
                client.refunds.append({"id": "re_hand", "amount": 3000, "status": "succeeded", "metadata": {}})
                self.assertEqual(gate.submit(P), "REFUSED:stale_premise")
                r = last(gate, "REFUSED", effect_id_for(P))
                self.assertEqual(r["reason"], ["refunded by others: was 0, now 3000"])
                self.assertEqual(r["changes"], [{"field": "refunded_by_others", "was": 0, "now": 3000}])
                if fails:
                    self.assertNotIn("repairs", r)
                else:
                    self.assertEqual([(x["code"], x["set"]) for x in r["repairs"]],
                                     [("refund_remaining", {"amount": 7000})])

    def test_easy_function_target_reports_changes(self):
        state = {"refunded": 0}
        gate = Interlock(tempfile.mkdtemp())

        @gate.effect(key=lambda order: f"refund:{order}", premises=lambda order: dict(state), lookup=lambda order: False)
        def refund(order):
            raise AssertionError("never sent")

        p = refund.proposal("881")
        state["refunded"] = 30
        self.assertEqual(refund.gate.submit(p), "REFUSED:stale_premise")
        r = last(refund.gate, "REFUSED", effect_id_for(p))
        self.assertEqual(r["reason"], ["refunded: was 0, now 30"])
        self.assertEqual(r["changes"], [{"field": "refunded", "was": 0, "now": 30}])
        self.assertNotIn("repairs", r)

    def test_mcp_refusal_carries_structured_escalation(self):
        from test_mcp_proxy import CONFIG, Session
        d = tempfile.mkdtemp()
        state = os.path.join(d, "state.json")
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump(CONFIG, f)
        s = Session(d, state, slow=5)
        s.refund("881", 20, wait=False)
        deadline = time.time() + 10
        while True:
            if os.path.exists(state):
                with open(state) as f:
                    if json.load(f)["refunds"]:
                        break
            self.assertLess(time.time(), deadline, "upstream never wrote the refund")
            time.sleep(0.05)
        with open(state, "w") as f:
            json.dump({"refunds": []}, f)
        s.kill()
        with open(state, "w") as f:
            json.dump({"refunds": [{"order_id": "881", "amount": 20, "reference": None}]}, f)
        time.sleep(1.5)
        s = Session(d, state)
        try:
            retry = s.refund("881", 20)
            self.assertTrue(retry.get("isError"), retry)
            esc = retry["_meta"]["interlock"]["escalation"]
            self.assertEqual(esc["changes"][0]["field"], "refunded_total")
            self.assertEqual(esc["repairs"], [])
            self.assertIn("changed", retry["content"][0]["text"])
            self.assertIn("refunded_total was 0, now 20", retry["content"][0]["text"])
        finally:
            s.close()

    @unittest.skipIf(HAS_TEMPORAL, "checks the fallback exceptions")
    def test_temporal_refusal_message_names_the_change(self):
        self.setup(amount=50)
        self.hand_refund(30)
        with self.assertRaises(Refused) as cm:
            gated(self.gate, self.P)
        msg = str(cm.exception)
        self.assertTrue(msg.startswith("interlock: REFUSED:stale_premise"), msg)
        self.assertIn("refunded was 0, now 30", msg)
        self.assertTrue(cm.exception.escalation["repairs"])

        self.setup()
        self.gate.journal.append("PROPOSED", self.eid, agent="bot", lease="L", premises=self.P["premises"],
                                 effect=self.P["effect"])
        self.gate.journal.dispatch(self.eid, self.P["effect"], "another-worker", 3600, lease="L",
                                   premises=self.P["premises"])
        with self.assertRaises(InFlight) as cm:
            gated(self.gate, self.P)
        self.assertEqual(str(cm.exception), "interlock: IN_FLIGHT")
        self.assertIsNone(cm.exception.escalation)
        self.assertIsNone(explain([]))


if __name__ == "__main__":
    unittest.main()
