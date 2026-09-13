"""
    python3 -m unittest discover -s tests

interlock.temporal.gated() without a Temporal server: each attempt recovers before it
submits, and refusals stop the retries. experiments/temporal_live.py covers a real server.
"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock import Gate, Leases, SimulatedCrash
from interlock.targets import Payments
from interlock.temporal import Refused, gated


class GatedActivity(unittest.TestCase):
    def setUp(self):
        self.api = Payments(2)
        self.api.create_order("881", 100)
        self.leases = Leases()
        self.leases.grant("L")
        self.gate = Gate(self.api, tempfile.mktemp(suffix=".jsonl"), self.leases)
        self.P = {"agent": "bot", "lease": "L", "request_id": "case-4471",
                  "premises": self.api.capture("881"), "effect": {"order": "881", "amount": 20}}

    def test_second_attempt_recovers_instead_of_resending(self):
        with self.assertRaises(SimulatedCrash):
            gated(self.gate, self.P, crash_after_effect=True)                 # attempt 1 dies
        self.assertEqual(gated(self.gate, self.P), "COMMITTED_ON_QUERY")     # attempt 2
        self.assertEqual(self.api.refunded_total("881"), 20)

    def test_refusal_stops_the_retries(self):
        with self.assertRaises(SimulatedCrash):
            gated(self.gate, self.P, crash_before_effect=True)
        self.leases.revoke("L")
        try:
            import temporalio  # noqa: F401
            expected = Exception
        except ImportError:
            expected = Refused
        with self.assertRaises(expected):
            gated(self.gate, self.P)
        self.assertEqual(gated(self.gate, self.P, raise_on_refusal=False), "REFUSED:lease")
        self.assertEqual(self.api.refunded_total("881"), 0)


if __name__ == "__main__":
    unittest.main()
