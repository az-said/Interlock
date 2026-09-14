"""
    python3 -m unittest discover -s tests

The repair loop through tools.protect(): a refused call says what changed, a corrected call inside
its approval is sent once, and nothing outside the approval, or after it was used, is sent at all.
"""
import json, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "experiments"))
from interlock.tools import protect
from repair_loop import MIX, Shop, results


class RepairLoop(unittest.TestCase):
    def tools(self, shop, approval=True, attempts=None):
        spec = {"key": ["order_id"],
                "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"}, "fields": ["refunded_total"]},
                "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
                "idempotency_argument": "reference"}
        if approval:
            spec["approval"] = {"tool": "get_approval", "arguments": {"order_id": "order_id"}, "attempts": attempts}
        fns = {n: getattr(shop, n) for n in ("get_order", "get_approval", "create_refund", "find_refund")}
        return protect(fns, {"journal_dir": tempfile.mkdtemp(), "claim_ttl": 0, "tools": {"create_refund": spec}})

    def test_stale_fact_is_named_and_a_corrected_call_goes_once(self):
        shop = Shop()
        shop.by_hand["881"] = 5
        tools = self.tools(shop)
        out = tools["create_refund"](order_id="881", amount=20)
        self.assertEqual(out["status"], "REFUSED:stale_premise")
        self.assertEqual(out["repair"]["changed"], ["refunded_total: was 0, now 5"])
        self.assertTrue(out["repair"]["may_retry"])
        self.assertIn("refunded_total: was 0, now 5", out["message"])
        left = tools["get_approval"](order_id="881")["max"]["amount"]  # the agent reads again, decides again
        fixed = tools["create_refund"](order_id="881", amount=left)
        self.assertEqual((fixed["status"], shop.total("881")), ("COMMITTED", 20))

    def test_a_change_between_the_agents_read_and_its_call_is_caught(self):
        shop = Shop()
        tools = self.tools(shop, approval=False)
        tools["get_order"](order_id="881")                              # the agent reads $0 refunded, and decides
        shop.refunds.append({"order_id": "881", "amount": 5, "reference": None})   # support refunds $5 meanwhile
        out = tools["create_refund"](order_id="881", amount=20)
        self.assertEqual(out["status"], "REFUSED:stale_premise")
        self.assertEqual(out["repair"]["changed"], ["refunded_total: was 0, now 5"])
        self.assertEqual(shop.total("881"), 5)

    def test_overshoot_is_refused_with_the_limit_then_corrected(self):
        shop = Shop()
        tools = self.tools(shop)
        out = tools["create_refund"](order_id="881", amount=30)
        self.assertEqual((out["status"], out["repair"]["changed"]), ("REFUSED:lease", ["amount 30 is over the 20 approved"]))
        self.assertTrue(out["repair"]["may_retry"])
        self.assertTrue(tools["create_refund"](order_id="881", amount=20)["ok"])
        self.assertEqual(shop.total("881"), 20)

    def test_attempts_cap_stops_a_model_that_keeps_re_deciding(self):
        shop = Shop()
        tools = self.tools(shop, attempts=2)
        self.assertTrue(tools["create_refund"](order_id="881", amount=30)["repair"]["may_retry"])
        second = tools["create_refund"](order_id="881", amount=25)
        self.assertEqual(second["status"], "REFUSED:lease")
        self.assertFalse(second["repair"]["may_retry"])                  # that was the last attempt
        third = tools["create_refund"](order_id="881", amount=20)       # fits, but comes too late
        self.assertEqual(third["status"], "REFUSED:lease")
        self.assertIn("approval case-881 has had its 2 attempts", third["repair"]["changed"])
        self.assertEqual(shop.refunds, [])

    def test_attempts_cap_counts_the_same_arguments_sent_again(self):
        shop = Shop()
        tools = self.tools(shop, attempts=2)
        first = tools["create_refund"](order_id="881", amount=30)
        self.assertTrue(first["repair"]["may_retry"])
        second = tools["create_refund"](order_id="881", amount=30)      # the same call again gets base:2, a new attempt
        self.assertFalse(second["repair"]["may_retry"])
        third = tools["create_refund"](order_id="881", amount=30)
        self.assertEqual(third["status"], "REFUSED:lease")
        self.assertIn("approval case-881 has had its 2 attempts", third["repair"]["changed"])
        self.assertFalse(third["repair"]["may_retry"])
        self.assertEqual(shop.refunds, [])

    def test_duplicate_is_ignored_and_a_second_decision_cannot_use_the_approval(self):
        shop = Shop()
        tools = self.tools(shop)
        self.assertEqual(tools["create_refund"](order_id="881", amount=10)["status"], "COMMITTED")
        self.assertEqual(tools["create_refund"](order_id="881", amount=10)["status"], "DUPLICATE_IGNORED")
        second = tools["create_refund"](order_id="881", amount=5)     # fits what is left, but the approval is spent
        self.assertEqual(second["status"], "REFUSED:lease_used")
        self.assertFalse(second["repair"]["may_retry"])
        self.assertEqual(shop.total("881"), 10)

    def test_crash_holds_the_approval_until_recovery_settles_it(self):
        shop = Shop()
        shop.crash.add("881")
        tools = self.tools(shop)
        out = tools["create_refund"](order_id="881", amount=20)
        self.assertEqual(out["status"], "IN_FLIGHT")
        self.assertFalse(out["repair"]["may_retry"])
        around = tools["create_refund"](order_id="881", amount=15)    # an agent that tries to route around the crash
        self.assertFalse(around["ok"])
        self.assertFalse(around["repair"]["may_retry"])
        self.assertEqual(list(tools.recover().values())[0], {out["receipt"]["effect_id"]: "COMMITTED_ON_QUERY"})
        self.assertEqual(tools["create_refund"](order_id="881", amount=20)["status"], "DUPLICATE_IGNORED")
        self.assertEqual(shop.total("881"), 20)

    def test_revoked_approval_is_not_retryable(self):
        shop = Shop()
        tools = self.tools(shop)
        next(iter(tools.interlock.gates.values())).leases.revoke("case-881", by="alice")
        out = tools["create_refund"](order_id="881", amount=20)
        self.assertEqual(out["status"], "REFUSED:lease")
        self.assertIn("approval case-881 was revoked", out["repair"]["changed"])
        self.assertFalse(out["repair"]["may_retry"])
        self.assertEqual(shop.refunds, [])

    def test_without_an_approval_a_refusal_names_the_fact_but_stays_refused(self):
        shop = Shop()
        shop.by_hand["881"] = 5
        tools = self.tools(shop, approval=False)
        out = tools["create_refund"](order_id="881", amount=20)
        self.assertEqual(out["repair"]["changed"], ["refunded_total: was 0, now 5"])
        self.assertFalse(out["repair"]["may_retry"])
        self.assertEqual(tools["create_refund"](order_id="881", amount=15)["status"], "REFUSED:conflicting_payload")
        self.assertEqual(shop.total("881"), 5)

    def test_experiment_claims(self):
        r = results()
        self.assertEqual(r["interlock+repair"]["total"], {"no person": 97, "person": 3, "wrong payout": 0, "overpaid": 0})
        self.assertEqual(r["interlock"]["total"]["wrong payout"], MIX["overshoot"] + MIX["stubborn"])   # no amount bound
        self.assertEqual(r["hand check"]["total"], r["interlock+repair"]["total"])                      # a fair check ties here
        with open(os.path.join(ROOT, "results", "repair_loop.json")) as f:
            self.assertEqual(json.load(f), r)                                   # results/ matches the code

    def test_tools_not_in_the_config_pass_through(self):
        shop = Shop()
        self.assertEqual(self.tools(shop)["get_order"](order_id="881"), {"order_id": "881", "refunded_total": 0})


if __name__ == "__main__":
    unittest.main()
