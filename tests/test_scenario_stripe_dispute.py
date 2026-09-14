"""Offline logic for scenarios/stripe_dispute: an in-memory Stripe stands in; the live run uses real Stripe, a real model and SIGKILL."""
import importlib.util, json, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scenarios", "stripe_dispute")]
import dispute as sd                                # noqa: E402
from scenarios.stripe_dispute import worker         # noqa: E402  (not a bare `import worker`: other scenarios have one too)
from interlock.gate import SimulatedCrash   # noqa: E402
from interlock.receipts import verify       # noqa: E402

spec = importlib.util.spec_from_file_location("scenario_stripe_dispute", os.path.join(ROOT, "experiments", "scenario_stripe_dispute.py"))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)

CASE = {"id": "case-1", "payment_intent": "pi_1", "charge": "ch_1", "dispute": "du_1"}
RESULTS = os.path.join(ROOT, "results", "scenarios", "stripe_dispute.json")


class FakeStripe:
    """Just the calls the scenario makes, with Stripe's key replay and its refusal to refund a charged-back charge."""
    def __init__(self):
        self.status, self.refunds, self.keys = "warning_needs_response", [], {}

    def request(self, method, path, params=None, idempotency_key=None):
        if (method, path) == ("GET", "/disputes"):
            return {"data": [{"id": "du_1", "status": self.status}]}
        if (method, path) == ("GET", "/refunds"):
            return {"data": list(self.refunds)}
        if (method, path) == ("POST", "/refunds"):
            if idempotency_key in self.keys:
                return {**self.keys[idempotency_key], "_replayed": True}
            if self.status in sd.CHARGEBACK:
                raise sd.StripeError("400 POST /refunds: Charge ch_1 has been charged back; cannot issue a refund.")
            r = {"id": f"re_{len(self.refunds)}", "amount": params["amount"], "status": "succeeded",
                 "metadata": params["metadata"], "created": 100}
            self.refunds.append(r)
            self.keys[idempotency_key] = r
            return {**r, "_replayed": False}
        raise AssertionError(f"unexpected {method} {path}")


def crash_as_exception(where, crash):
    if crash == where:
        raise SimulatedCrash(where)       # offline only: the live run SIGKILLs the process here


def decide(case, facts):
    return {"amount": sd.APPROVED, "reason": "goodwill"}


def crash_then_chargeback(system, crash, decider=decide):
    c, state = FakeStripe(), tempfile.mkdtemp()
    with open(os.path.join(state, "approval.json"), "w") as f:
        json.dump({"max_cents": sd.APPROVED, "revoked": None, "by": "support"}, f)
    try:
        worker.SYSTEMS[system](c, CASE, state, crash, decider)
    except SimulatedCrash:
        pass
    else:
        raise AssertionError("the crash point was not reached")
    c.status = "needs_response"           # the bank escalates the inquiry during the outage
    for r in c.refunds:
        r["status"] = "failed"            # as Stripe did live once the chargeback posted
    extra = {"wait": 0} if system == "interlock" else {}
    return c, worker.SYSTEMS[system](c, CASE, state, None, decider, **extra), state


class StripeDisputeLogic(unittest.TestCase):
    def setUp(self):
        self.real_crash, worker.crash_point = worker.crash_point, crash_as_exception

    def tearDown(self):
        worker.crash_point = self.real_crash

    def test_hand_check_decision(self):
        snap = {"chargebacks": [], "refunded_by_others": 0}
        self.assertIsNone(worker.hand_check_decision(snap, snap, [], True))
        self.assertEqual(worker.hand_check_decision(snap, snap, [{"id": "re"}], True), "FOUND_BY_LOOKUP")
        self.assertEqual(worker.hand_check_decision(snap, snap, [], False), "REFUSED:approval")
        self.assertEqual(worker.hand_check_decision(snap, {**snap, "chargebacks": ["du_1"]}, [], True), "REFUSED:charged_back")
        self.assertEqual(worker.hand_check_decision(snap, {**snap, "refunded_by_others": 500}, [], True), "REFUSED:refunds_changed")

    def test_verdict_counts_failed_refunds_as_issued(self):
        rs = [{"id": "re_a", "amount": 2000, "status": "failed", "created": 10},
              {"id": "re_b", "amount": 2000, "status": "failed", "created": 50}]
        self.assertEqual(sd.verdict(rs, 40, 1), (2, ["re_b"], False))
        self.assertEqual(sd.verdict(rs[:1], 40, 1), (1, [], True))
        self.assertEqual(sd.verdict([], 40, 0), (0, [], True))
        self.assertFalse(sd.money_returned(rs))

    def test_inquiry_is_not_a_chargeback(self):
        c = FakeStripe()
        self.assertEqual(sd.facts(c, CASE)["chargebacks"], [])
        c.status = "needs_response"
        self.assertEqual(sd.facts(c, CASE)["chargebacks"], ["du_1"])

    def test_crash_before_send(self):
        with self.assertRaises(sd.StripeError):                        # only Stripe's own guard stops no_check
            crash_then_chargeback("no_check", "before")
        want = {"hand_check": "REFUSED:charged_back", "interlock": "REFUSED:stale_premise_at_recovery"}
        for system, status in want.items():
            c, out, _ = crash_then_chargeback(system, "before")
            self.assertEqual((out["status"], c.refunds), (status, []), system)

    def test_crash_after_send_lands_once_everywhere(self):
        want = {"no_check": "REPLAYED_BY_STRIPE", "hand_check": "FOUND_BY_LOOKUP", "interlock": "COMMITTED_ON_QUERY"}
        for system, status in want.items():
            c, out, _ = crash_then_chargeback(system, "after")
            self.assertEqual((out["status"], len(c.refunds)), (status, 1), system)

    def test_interlock_receipt_names_the_chargeback_and_the_refund(self):
        _, out, _ = crash_then_chargeback("interlock", "before")
        self.assertEqual(out["journal"], ["PROPOSED", "AUTHORIZED", "DISPATCHED", "REFUSED"])
        self.assertTrue(out["receipt"]["valid"])
        self.assertIs(out["receipt"]["happened"], False)
        self.assertIn("du_1", out["receipt"]["rechecked_at_recovery"]["violations"][0])
        c, out, _ = crash_then_chargeback("interlock", "after")
        self.assertEqual(out["receipt"]["evidence"], c.refunds[0]["id"])      # not True: the lookup keeps the id

    def test_proof_is_scored_from_records(self):
        for crash in ("before", "after"):
            got = {}
            for system in ("hand_check", "interlock"):
                c, _, state = crash_then_chargeback(system, crash)
                got[system] = sd.proof(system, harness.harvest(state), c.refunds)
            self.assertEqual({s: (p["checks_recorded"], p["outcome_matches"], p["tamper_evident"]) for s, p in got.items()},
                             {"hand_check": (True, True, False), "interlock": (True, True, True)}, crash)
        p = sd.proof("no_check", {"decision": {"reason": "x"}, "hand_check_log": None, "receipt": None}, [])
        self.assertEqual((p["decision_recorded"], p["checks_recorded"], p["outcome_matches"]), (True, False, False))
        c, _, state = crash_then_chargeback("hand_check", "after")
        record = harness.harvest(state)
        record["hand_check_log"][-1]["lookup"] = ["re_other"]                    # a record that disagrees with Stripe
        self.assertFalse(sd.proof("hand_check", record, c.refunds)["outcome_matches"])

    def test_model_asking_for_more_than_approved_sends_nothing(self):
        c, state = FakeStripe(), tempfile.mkdtemp()
        with open(os.path.join(state, "approval.json"), "w") as f:
            json.dump({"max_cents": sd.APPROVED, "revoked": None}, f)
        for system in worker.SYSTEMS:
            out = worker.SYSTEMS[system](c, CASE, state, None, lambda case, facts: {"amount": 3000, "reason": "x"})
            self.assertEqual(out["status"], "MODEL_DEVIATED", system)
        self.assertEqual(c.refunds, [])

    @unittest.skipUnless(os.path.exists(RESULTS), "no published run")
    def test_published_receipts_reverify(self):
        with open(RESULTS) as f:
            cells = json.load(f)["cells"]
        receipts = [x["record"]["receipt"] for x in cells if x["system"] == "interlock"]
        self.assertTrue(receipts)
        for r in receipts:
            self.assertTrue(verify(r)["valid"])
            r["entries"][-1]["kind"] = "COMMITTED" if r["entries"][-1]["kind"] == "REFUSED" else "REFUSED"
            self.assertFalse(verify(r)["valid"])


if __name__ == "__main__":
    unittest.main()
