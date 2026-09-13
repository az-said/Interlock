"""Offline logic for scenarios/connect_payout: an in-memory Stripe stands in; the live run uses real Stripe and SIGKILL."""
import os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scenarios", "connect_payout"))
import stripe_connect as sc   # noqa: E402
import worker                 # noqa: E402
from interlock.gate import SimulatedCrash   # noqa: E402

ORDER = {"id": "order-1", "seller": "acct_seller", "payment_intent": "pi_1", "charge": "ch_1"}


class FakeStripe:
    """Just the calls the scenario makes, with Stripe's key replay and its refusal to pay an inactive account."""
    def __init__(self):
        self.refunded, self.transfers_cap, self.transfers, self.keys = 0, "active", [], {}

    def request(self, method, path, params=None, idempotency_key=None):
        if path == "/charges/ch_1":
            return {"amount_refunded": self.refunded}
        if path == "/accounts/acct_seller":
            return {"capabilities": {"transfers": self.transfers_cap}}
        if (method, path) == ("GET", "/transfers"):
            return {"data": list(self.transfers)}
        if (method, path) == ("POST", "/transfers"):
            if idempotency_key in self.keys:
                return {**self.keys[idempotency_key], "_replayed": True}
            if self.transfers_cap != "active":
                raise sc.StripeError("400 POST /transfers: destination lacks the transfers capability")
            t = {"id": f"tr_{len(self.transfers)}", "amount": params["amount"], "amount_reversed": 0,
                 "metadata": params["metadata"]}
            self.transfers.append(t)
            self.keys[idempotency_key] = t
            return {**t, "_replayed": False}
        raise AssertionError(f"unexpected {method} {path}")


def crash_as_exception(where, crash):
    if crash == where:
        raise SimulatedCrash(where)       # offline only: the live run SIGKILLs the process here


def crash_then_restart(system, crash, during=None):
    """A fresh Stripe and journal, a crash at `crash`, `during(stripe)` in the outage, then a restart."""
    c, state = FakeStripe(), tempfile.mkdtemp()
    try:
        worker.SYSTEMS[system](c, ORDER, state, crash)
    except SimulatedCrash:
        pass
    else:
        raise AssertionError("the crash point was not reached")
    if during:
        during(c)
    extra = {"wait": 0} if system == "interlock" else {}
    return c, worker.SYSTEMS[system](c, ORDER, state, None, **extra)


def reverse(c):
    c.refunded = sc.PAID


def restrict(c):
    c.transfers_cap = "inactive"


class ConnectPayoutLogic(unittest.TestCase):
    def setUp(self):
        self.real_crash, worker.crash_point = worker.crash_point, crash_as_exception

    def tearDown(self):
        worker.crash_point = self.real_crash

    def test_hand_check_decision(self):
        ok = {"order_refunded_cents": 0, "seller_transfers": "active"}
        self.assertIsNone(worker.hand_check_decision(ok, []))
        self.assertEqual(worker.hand_check_decision(ok, [{"id": "tr"}]), "FOUND_BY_LOOKUP")
        self.assertEqual(worker.hand_check_decision({**ok, "order_refunded_cents": 1}, []), "REFUSED:order_reversed")
        self.assertEqual(worker.hand_check_decision({**ok, "seller_transfers": "inactive"}, []), "REFUSED:seller_restricted")

    def test_paid_out_ignores_reversed(self):
        ts = [{"amount": 2000, "amount_reversed": 0}, {"amount": 2000, "amount_reversed": 2000}]
        self.assertEqual(sc.paid_out(ts), (2000, 1))

    def test_crash_after_commit_lands_once_everywhere(self):
        want = {"no_check": "REPLAYED_BY_STRIPE", "hand_check": "FOUND_BY_LOOKUP", "interlock": "COMMITTED_BY_RETRY"}
        for system, status in want.items():
            c, out = crash_then_restart(system, "after")
            self.assertEqual((out["status"], sc.paid_out(c.transfers)), (status, (sc.PAYOUT, 1)), system)

    def test_order_reversed_during_outage(self):
        want = {"no_check": ("TRANSFERRED", (sc.PAYOUT, 1)),            # pays out a reversed order
                "hand_check": ("REFUSED:order_reversed", (0, 0)),
                "interlock": ("REFUSED:stale_premise_at_recovery", (0, 0))}
        for system, expected in want.items():
            c, out = crash_then_restart(system, "before", reverse)
            self.assertEqual((out["status"], sc.paid_out(c.transfers)), expected, system)

    def test_seller_restricted_during_outage(self):
        with self.assertRaises(sc.StripeError):                          # the fake, like Stripe, refuses the send
            crash_then_restart("no_check", "before", restrict)
        c, out = crash_then_restart("interlock", "before", restrict)
        self.assertEqual((out["status"], c.transfers), ("REFUSED:stale_premise_at_recovery", []))

    def test_interlock_receipt_records_the_refusal(self):
        _, out = crash_then_restart("interlock", "before", reverse)
        self.assertEqual(out["journal"], ["PROPOSED", "AUTHORIZED", "DISPATCHED", "REFUSED"])
        self.assertTrue(out["receipt"]["valid"])
        self.assertIs(out["receipt"]["happened"], False)
        self.assertIn("order_refunded_cents", out["receipt"]["rechecked_at_recovery"]["violations"][0])


if __name__ == "__main__":
    unittest.main()
