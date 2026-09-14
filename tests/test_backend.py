"""
    python3 -m unittest discover -s tests

Offline checks for backend/: approval leases shared across connections and capped at the
approved amount, the one-shot crash marker (a real SIGKILL of a child process), and validation of the model's
refund call.
"""
import os, signal, subprocess, sys, tempfile, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.agent import AgentError, validate_refund
from backend.leases import DurableLeases
from interlock import Gate, SimulatedCrash
from interlock.receipts import _lease_held, verify
from interlock.targets import Payments
from interlock.targets.stripe_api import StripeRefunds


class Backend(unittest.TestCase):
    def test_leases_are_shared_across_connections(self):
        path = tempfile.mktemp(suffix=".db")
        api, worker = DurableLeases(path), DurableLeases(path)
        self.assertFalse(worker.is_live("approval/1"))
        api.grant("approval/1")
        self.assertTrue(worker.is_live("approval/1"))
        api.revoke("approval/1")
        self.assertFalse(worker.is_live("approval/1"))

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "backend crash injection requires POSIX signals")
    def test_crash_marker_kills_once(self):
        env = {**os.environ, "INTERLOCK_CRASH": "after_commit", "INTERLOCK_CRASH_MARKER": tempfile.mktemp()}
        code = f"import sys; sys.path.insert(0, {ROOT!r}); from backend.config import crash_once; crash_once('after_commit'); print('alive')"
        first = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual(first.returncode, -signal.SIGKILL)
        second = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual((second.returncode, second.stdout.strip()), (0, "alive"))

    def test_model_refund_call_is_validated(self):
        self.assertEqual(validate_refund({"amount_cents": 2000, "reason": " jar cracked "}, 10000, 0),
                         {"amount_cents": 2000, "reason": "jar cracked"})
        for bad in ({"amount_cents": "2000", "reason": "x"}, {"amount_cents": 20.0, "reason": "x"},
                    {"amount_cents": True, "reason": "x"}, {"amount_cents": 0, "reason": "x"},
                    {"amount_cents": 10001, "reason": "x"}, {"amount_cents": 2000, "reason": " "}):
            with self.assertRaises(AgentError):
                validate_refund(bad, 10000, 0)
        with self.assertRaises(AgentError):
            validate_refund({"amount_cents": 2000, "reason": "x"}, 10000, 9000)     # only $10 left to refund
        with self.assertRaises(AgentError):
            validate_refund({"amount_cents": 5000, "reason": "x"}, 10000, 0, approved_cents=2000)
        self.assertEqual(validate_refund({"amount_cents": 2000, "reason": "x"}, 10000, 0, 2000)["amount_cents"], 2000)

    def test_a_hand_refund_before_the_decision_is_part_of_the_premise(self):
        class Client:        # Stripe's refund list, offline: one $5 hand refund (no metadata) made before deciding
            def request(self, method, path, params=None, idempotency_key=None):
                return {"data": [{"id": "re_hand", "amount": 500, "status": "succeeded", "metadata": {}}]}
        target = StripeRefunds(Client(), "pi_1")
        premises = target.capture()
        self.assertEqual(premises["refunded_by_others"], 500)
        self.assertEqual(target.validate_premises(premises, "eid123"), [])

    def test_receipt_records_what_recovery_observed(self):
        path = tempfile.mktemp(suffix=".db")
        leases = DurableLeases(path)
        leases.grant("approval/1", max_cents=20)
        self.assertEqual(leases.describe("approval/1")["max_cents"], 20)
        api = Payments(1)
        api.create_order("881", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".db"), leases)
        P = {"agent": "bot", "lease": "approval/1", "request_id": "case-1", "premises": api.capture("881"),
             "effect": {"order": "881", "amount": 20}}
        with self.assertRaises(SimulatedCrash):
            gate.submit(P, crash_after_effect=True)
        leases.revoke("approval/1")
        # past the dedup window, so recovery re-checks (the lease fails) and then looks the refund up
        self.assertEqual(list(gate.recover(now=time.time() + api.dedup_window + 1).values()), ["COMMITTED_ON_QUERY"])
        r = verify(gate.receipt_bundle(P))
        dispatched = next(e for e in gate.receipt_bundle(P)["entries"] if e["kind"] == "DISPATCHED")
        self.assertEqual((dispatched["checks"]["lease"]["max_cents"], dispatched["checks"]["lease"]["revoked"]), (20, None))
        self.assertEqual((r["valid"], r["happened"], r["authorized_when_fired"], r["evidence"]), (True, True, True, True))
        self.assertIs(r["rechecked_at_recovery"]["lease_live"], False)
        self.assertIsNotNone(r["rechecked_at_recovery"]["lease"]["revoked"])
        # verify() reads the recorded grant, not only the lease_live flag
        self.assertFalse(_lease_held({"lease_live": True, "lease": {"revoked": 1.0}}, {"amount": 20}))
        self.assertFalse(_lease_held({"lease_live": True, "lease": {"revoked": None, "max_cents": 10}}, {"amount": 20}))

    def test_approval_caps_what_the_gate_sends(self):
        leases = DurableLeases(tempfile.mktemp(suffix=".db"))
        leases.grant("approval/1", max_cents=20)
        self.assertEqual((leases.allows("approval/1", {"amount": 20}), leases.allows("approval/1", {"amount": 21}),
                          leases.allows("approval/1", {}), leases.allows("approval/2", {"amount": 1})),
                         (True, False, False, False))
        api = Payments(1)
        api.create_order("881", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".db"), leases)
        P = {"agent": "bot", "lease": "approval/1", "request_id": "case-1", "premises": api.capture("881"),
             "effect": {"order": "881", "amount": 50}}
        self.assertEqual(gate.submit(P), "REFUSED:lease")
        self.assertEqual(gate.submit(dict(P, request_id="case-2", effect={"order": "881", "amount": 20})), "COMMITTED")
        self.assertEqual(api.refunded_total("881"), 20)


if __name__ == "__main__":
    unittest.main()
