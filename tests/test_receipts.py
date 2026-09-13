"""
    python3 -m unittest discover -s tests

Receipts as proof: verify() re-derives "happened once, authorized when it fired,
assumptions held" from the hash-chained entries, and notices when they were tampered with.
"""
import copy, os, sys, tempfile, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, Leases, SimulatedCrash
from interlock.receipts import verify
from interlock.targets import Payments

KEY = "shared-with-the-payment-service"


class Receipts(unittest.TestCase):
    def world(self, tier=2, journal=".jsonl"):
        api = Payments(tier)
        api.create_order("881", 100)
        leases = Leases()
        leases.grant("L")
        gate = Gate(api, tempfile.mktemp(suffix=journal), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "case-4471",
             "premises": api.capture("881"), "effect": {"order": "881", "amount": 20}}
        return api, leases, gate, P

    def test_committed_refund_proves_all_three_claims_on_both_backends(self):
        for journal in (".jsonl", ".db"):
            with self.subTest(journal=journal):
                _, _, gate, P = self.world(journal=journal)
                gate.submit(P)
                r = verify(gate.receipt_bundle(P, KEY), KEY)
                self.assertEqual((r["valid"], r["tamper_evident"], r["signed"]), (True, True, True), r)
                self.assertEqual((r["happened"], r["happened_once"], r["authorized_when_fired"], r["assumptions_held"]),
                                 (True, True, True, True))

    def test_edited_amount_is_detected(self):
        _, _, gate, P = self.world()
        gate.submit(P)
        b = gate.receipt_bundle(P)
        next(e for e in b["entries"] if e["kind"] == "DISPATCHED")["effect"]["amount"] = 2000
        r = verify(b)
        self.assertFalse(r["valid"])
        self.assertIn("was altered", " ".join(r["problems"]))

    def test_removed_entry_is_detected(self):
        _, _, gate, P = self.world()
        gate.submit(P)
        b = gate.receipt_bundle(P)
        b["entries"] = [e for e in b["entries"] if e["kind"] != "AUTHORIZED"]
        self.assertIn("out of order", " ".join(verify(b)["problems"]))

    def test_rewritten_chain_fails_the_signature(self):
        _, _, gate, P = self.world()
        gate.submit(P)
        b = gate.receipt_bundle(P, KEY)
        forged = copy.deepcopy(b)
        forged["signature"] = "0" * 64
        self.assertFalse(verify(forged, KEY)["signed"])
        self.assertFalse(verify(b, "someone-else's-key")["valid"])

    def test_crash_recovered_by_retry_still_proves_the_recheck(self):
        _, _, gate, P = self.world(tier=1)
        with self.assertRaises(SimulatedCrash):
            gate.submit(P, crash_after_effect=True)
        gate.recover()
        r = verify(gate.receipt_bundle(P))
        self.assertEqual((r["valid"], r["happened"], r["authorized_when_fired"], r["assumptions_held"]),
                         (True, True, True, True), r)

    def test_refused_at_recovery_proves_nothing_was_sent(self):
        api, leases, gate, P = self.world(tier=2)
        with self.assertRaises(SimulatedCrash):
            gate.submit(P, crash_before_effect=True)
        api.refunds.append({"eid": "dashboard", "order": "881", "amount": 20})
        gate.recover()
        r = verify(gate.receipt_bundle(P))
        self.assertEqual((r["valid"], r["happened"], r["happened_once"]), (True, False, True), r)
        # the pre-crash dispatch passed its checks, but it never landed: nothing fired, so nothing is attested
        self.assertEqual((r["authorized_when_fired"], r["assumptions_held"], r["refused"]),
                         (None, None, "stale_premise at recovery"), r)

    def test_revoked_at_recovery_does_not_claim_it_was_authorized(self):
        _, leases, gate, P = self.world(tier=2)
        with self.assertRaises(SimulatedCrash):
            gate.submit(P, crash_before_effect=True)
        leases.revoke("L")
        gate.recover()
        r = verify(gate.receipt_bundle(P))
        self.assertEqual((r["valid"], r["happened"], r["authorized_when_fired"], r["assumptions_held"], r["refused"]),
                         (True, False, None, None, "lease at recovery"), r)

    def test_ambiguous_is_reported_as_unknown(self):
        _, _, gate, P = self.world(tier=3)
        with self.assertRaises(SimulatedCrash):
            gate.submit(P, crash_after_effect=True)
        gate.recover()
        self.assertEqual(verify(gate.receipt_bundle(P))["happened"], "unknown")


if __name__ == "__main__":
    unittest.main()
