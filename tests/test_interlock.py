"""
    python3 -m unittest discover -s tests

Every claim in the README, as an assertion, plus a randomized fault sweep and the
three-line integration. If a table in results/ and these tests disagree, the table is wrong.
"""
import os, random, sys, tempfile, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "experiments")]
from interlock import Gate, Interlock, Leases, SimulatedCrash
from interlock.targets import Payments
import coding_agents, refund_agent

OUTAGE = {"refund_during_outage", "lease_revoked_during_outage", "key_expired"}


class ExperimentClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refund = refund_agent.results()
        cls.coding = coding_agents.results()

    def failing(self, system):
        return {f for f, cells in self.refund.items() if not cells[system]["invariant_held"]}

    def test_gate_holds_every_refund_fault_at_every_tier(self):
        for tier in (1, 2, 3):
            self.assertEqual(self.failing(f"gate@tier{tier}"), set(), f"tier {tier}")

    def test_only_tier3_gives_up_liveness(self):
        for fault, cells in self.refund.items():
            for tier in (1, 2):
                self.assertEqual(cells[f"gate@tier{tier}"]["caveat"], "", f"tier {tier} {fault}")

    def test_each_baseline_fails_exactly_where_the_readme_says(self):
        self.assertEqual(self.failing("naive"), {"crash_before_ack", "duplicate_submit", "model_redecides",
                                                 "conflicting_payload", "lease_revoked", "stale_eligibility"} | OUTAGE)
        self.assertEqual(self.failing("idempotency@tier1"), {"lease_revoked", "stale_eligibility"} | OUTAGE)
        self.assertEqual(self.failing("durable@tier1"), {"lease_revoked", "stale_eligibility"} | OUTAGE)

    def test_coding_agent_boundary_is_exactly_one_row(self):
        self.assertEqual({f for f, c in self.coding.items() if not c["gate/symbol"]["invariant_held"]}, {"semantic_only"})
        self.assertTrue(all(c["gate/file"]["invariant_held"] for c in self.coding.values()))


class RandomFaultSweep(unittest.TestCase):
    """Random tier, crash point, events before the decision and during the outage, late recovery, duplicates."""
    RUNS = 2000

    def test_invariants_hold_on_random_interleavings(self):
        for seed in range(self.RUNS):
            rng = random.Random(seed)
            case = dict(tier=rng.choice((1, 2, 3)),
                        crash=rng.choice(("none", "before_send", "after_effect")),
                        before={e for e in ("revoke", "ineligible") if rng.random() < 0.15},
                        during={e for e in ("human_refund", "revoke", "ineligible") if rng.random() < 0.3},
                        late=rng.random() < 0.4,
                        dup=rng.random() < 0.4)
            with self.subTest(seed=seed, **case):
                self.run_case(**case)

    def run_case(self, tier, crash, before, during, late, dup):
        api = Payments(tier)
        api.create_order("881", 100)
        leases = Leases()
        leases.grant("L")
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "case-4471",
             "premises": api.capture("881"), "effect": {"order": "881", "amount": 20}}
        if "revoke" in before: leases.revoke("L")
        if "ineligible" in before: api.set_eligible("881", False)

        crashed = False
        try:
            gate.submit(P, crash_before_effect=crash == "before_send", crash_after_effect=crash == "after_effect")
        except SimulatedCrash:
            crashed = True
        if crashed and dup:
            self.assertIn(gate.submit(P), ("IN_FLIGHT",), "resent an effect a crash left unresolved")
        if crashed:
            if "human_refund" in during: api.refunds.append({"eid": "dashboard", "order": "881", "amount": 20})
            if "revoke" in during: leases.revoke("L")
            if "ineligible" in during: api.set_eligible("881", False)
            if late: api.prune_keys()
            gate.recover(now=time.time() + (api.dedup_window + 1 if late else 0))
        if dup:
            gate.submit(P)

        mine = [r for r in api.refunds if r["eid"] != "dashboard"]
        final = gate.receipt(P)["final"]
        self.assertLessEqual(len(mine), 1, "agent refunded twice")
        if before:
            self.assertEqual(mine, [], "refunded on a premise or lease that was already dead")
        if crashed and crash == "before_send" and during:
            self.assertEqual(mine, [], "sent after the world changed during the outage")
        if final == "COMMITTED":
            self.assertEqual(len(mine), 1, "receipt says committed, nothing landed")
        if final in ("REFUSED", "AMBIGUOUS") and crash == "before_send":
            self.assertEqual(mine, [], "receipt says it did not land, but it did")


class Receipts(unittest.TestCase):
    """`executed` reports what the target confirmed, never what was merely attempted."""

    def receipt_after(self, tier, crash, during=None):
        api = Payments(tier)
        api.create_order("881", 100)
        leases = Leases()
        leases.grant("L")
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "case-4471",
             "premises": api.capture("881"), "effect": {"order": "881", "amount": 20}}
        try:
            gate.submit(P, crash_before_effect=crash == "before_send", crash_after_effect=crash == "after_effect")
        except SimulatedCrash:
            if during:
                during(api, leases)
            gate.recover()
        return gate.receipt(P)

    def test_committed_is_executed(self):
        r = self.receipt_after(2, "none")
        self.assertEqual((r["executed"], r["recorded"], r["final"]), (True, True, "COMMITTED"))

    def test_ambiguous_is_unknown_not_executed(self):
        r = self.receipt_after(3, "after_effect")
        self.assertEqual((r["executed"], r["final"]), ("unknown", "AMBIGUOUS"))

    def test_refused_at_recovery_was_not_executed(self):
        r = self.receipt_after(2, "before_send", during=lambda api, leases: leases.revoke("L"))
        self.assertEqual((r["executed"], r["final"]), (False, "REFUSED"))

    def test_stripe_target_refuses_live_keys(self):
        from interlock.targets.stripe_api import StripeClient
        for key in ("sk_live_abc", "rk_live_abc", "", None):
            with self.assertRaises(ValueError):
                StripeClient(key)
        StripeClient("sk_test_abc")


class ThreeLineIntegration(unittest.TestCase):
    """The decorator in interlock/easy.py, including a simulated process restart."""

    def setUp(self):
        self.world = {"refunds": [], "eligible": True, "allowed": True}
        self.dir = tempfile.mkdtemp()

    def start(self, dedupes=False, lookup=False):
        """A fresh process: new Interlock over the same journal directory."""
        w = self.world
        gate = Interlock(self.dir)

        @gate.effect(key=lambda order, amount: f"refund:{order}",
                     premises=lambda order, amount, idempotency_key: {
                         "eligible": w["eligible"],
                         "refunded_by_others": sum(r["amount"] for r in w["refunds"] if r["key"] != idempotency_key)},
                     allowed=lambda order, amount: w["allowed"],
                     dedupes=dedupes,
                     lookup=(lambda order, amount, idempotency_key: any(r["key"] == idempotency_key for r in w["refunds"]))
                            if lookup else None)
        def refund(order, amount, idempotency_key):
            if dedupes and any(r["key"] == idempotency_key for r in w["refunds"]):
                return "deduped"
            w["refunds"].append({"key": idempotency_key, "amount": amount})
            return "re_123"

        return gate, refund

    def crash(self, refund, *args, when):
        with self.assertRaises(SimulatedCrash):
            refund.gate.submit(refund.proposal(*args), **{f"crash_{when}": True})

    def test_happy_path_then_duplicate(self):
        _, refund = self.start(dedupes=True)
        self.assertEqual(refund("881", 20), ("COMMITTED", "re_123"))
        self.assertEqual(refund("881", 20)[0], "DUPLICATE_IGNORED")
        self.assertEqual(len(self.world["refunds"]), 1)

    def test_redecided_amount_is_refused(self):
        _, refund = self.start(dedupes=True)
        refund("881", 20)
        self.assertEqual(refund("881", 30)[0], "REFUSED:conflicting_payload")
        self.assertEqual([r["amount"] for r in self.world["refunds"]], [20])

    def test_premise_change_before_dispatch_is_refused(self):
        _, refund = self.start(dedupes=True)
        p = refund.proposal("881", 20)
        self.world["eligible"] = False
        self.assertEqual(refund.gate.submit(p), "REFUSED:stale_premise")
        self.assertEqual(self.world["refunds"], [])

    def test_crash_after_effect_recovers_once_after_restart(self):
        _, refund = self.start(dedupes=True)
        self.crash(refund, "881", 20, when="after_effect")
        gate, _ = self.start(dedupes=True)
        self.assertEqual(list(gate.recover()["test_interlock.refund"].values()), ["COMMITTED_BY_RETRY"])
        self.assertEqual(len(self.world["refunds"]), 1)

    def test_human_refund_during_outage_is_refused_after_restart(self):
        _, refund = self.start(lookup=True)
        self.crash(refund, "881", 20, when="before_effect")
        self.world["refunds"].append({"key": "dashboard", "amount": 20})
        gate, _ = self.start(lookup=True)
        self.assertEqual(list(gate.recover()["test_interlock.refund"].values()), ["REFUSED:stale_premise_at_recovery"])
        self.assertEqual([r["key"] for r in self.world["refunds"]], ["dashboard"])

    def test_permission_revoked_during_outage_is_refused_after_restart(self):
        _, refund = self.start(lookup=True)
        self.crash(refund, "881", 20, when="before_effect")
        self.world["allowed"] = False
        gate, _ = self.start(lookup=True)
        self.assertEqual(list(gate.recover()["test_interlock.refund"].values()), ["REFUSED:lease_at_recovery"])
        self.assertEqual(self.world["refunds"], [])

    def test_no_dedup_no_lookup_is_ambiguous_and_never_resent(self):
        _, refund = self.start()
        self.crash(refund, "881", 20, when="after_effect")
        gate, refund = self.start()
        self.assertEqual(list(gate.recover()["test_interlock.refund"].values()), ["AMBIGUOUS"])
        self.assertEqual(refund("881", 20)[0], "AMBIGUOUS")
        self.assertEqual(len(self.world["refunds"]), 1)


if __name__ == "__main__":
    unittest.main()
