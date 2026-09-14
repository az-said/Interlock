"""
    python3 -m unittest discover -s tests

Defects the escalation merge kept or introduced, each reproduced before its fix.
"""
import inspect, json, os, sys, tempfile, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from interlock import Interlock
from interlock.gate import Rejected
from interlock.receipts import verify
from interlock.tools import ToolError, protect


def refunder(approval=False):
    """A tier-3 refund that lands, then answers with an error on its first call."""
    refunds = []

    def create_refund(order_id, amount):
        refunds.append(amount)
        if len(refunds) == 1:
            raise ToolError("upstream MCP server exited")
        return {"refund": len(refunds)}

    def get_approval(order_id):
        return {"id": "case-" + order_id, "match": {"order_id": order_id}, "max": {"amount": 20}}
    spec = {"key": ["order_id"]}
    if approval:
        spec["approval"] = {"tool": "get_approval", "arguments": {"order_id": "order_id"}}
    tools = protect({"create_refund": create_refund, "get_approval": get_approval},
                    {"journal_dir": tempfile.mkdtemp(), "claim_ttl": 0, "tools": {"create_refund": spec}})
    return tools, refunds


class TargetErrorIsFinal(unittest.TestCase):
    def test_a_settled_target_error_is_never_sent_again(self):
        for approval in (False, True):
            with self.subTest(approval=approval):
                tools, refunds = refunder(approval)
                self.assertEqual(tools["create_refund"](order_id="881", amount=20)["status"], "REFUSED:target_error")
                tools.recover()
                out = tools["create_refund"](order_id="881", amount=20)
                self.assertEqual(out["status"], "REFUSED:target_error")
                self.assertFalse(out["repair"]["may_retry"])
                self.assertEqual(refunds, [20])

    def test_easy_rejected_is_never_sent_again(self):
        refunds, il = [], Interlock(tempfile.mkdtemp(), claim_ttl=0)

        @il.effect(key=lambda o, a: f"refund:{o}")
        def refund(o, a):
            refunds.append(a)
            raise Rejected("upstream gone")
        self.assertEqual(refund("881", 20)[0], "REFUSED:target_error")
        il.recover()
        self.assertEqual(refund("881", 20)[0], "REFUSED:target_error")
        self.assertEqual(refunds, [20])

    def test_receipt_flags_a_send_after_a_target_error(self):
        tools, _ = refunder()
        tools["create_refund"](order_id="881", amount=20)
        gate = next(iter(tools.interlock.gates.values()))
        eid = gate.journal.entries()[0]["effect_id"]
        d = next(e for e in gate.journal.entries(eid) if e["kind"] == "DISPATCHED")
        gate.journal.append("PROPOSED", eid, agent="a", lease=d.get("lease"), premises=d["premises"], effect=d["effect"])
        gate.journal.append("AUTHORIZED", eid, lease=d.get("lease"))
        gate.journal.append("DISPATCHED", eid, effect=d["effect"], lease=d.get("lease"), premises=d["premises"], checks=d["checks"])
        gate.journal.append("COMMITTED", eid, result={"status": "ok"})
        v = verify({"effect_id": eid, "entries": gate.journal.entries(eid)})
        self.assertFalse(v["valid"])
        self.assertFalse(v["happened_once"])


class ProxyUpstreamExit(unittest.TestCase):
    def test_upstream_exit_mid_send_is_unknown_not_refused(self):
        import test_mcp_proxy as t
        fake = os.path.join(tempfile.mkdtemp(), "fake.py")
        with open(t.FAKE) as f:
            src = f.read().replace("            save(state)\n",
                                   "            save(state)\n            if args.get(\"amount\") == 777:\n                os._exit(1)\n", 1)
        with open(fake, "w") as f:
            f.write(src)
        old, t.FAKE = t.FAKE, fake
        try:
            d = tempfile.mkdtemp()
            state = os.path.join(d, "state.json")
            with open(os.path.join(d, "config.json"), "w") as f:
                json.dump({"journal_dir": "journal", "claim_ttl": 1, "tools": {"create_refund": {"key": ["order_id"]}}}, f)
            s = t.Session(d, state)
            self.assertEqual(s.refund("881", 777)["_meta"]["interlock"]["status"], "IN_FLIGHT")
            s.close()
            time.sleep(1.5)                                   # past claim_ttl, so recovery takes the send over
            s = t.Session(d, state)
            self.assertEqual(s.refund("881", 777)["_meta"]["interlock"]["status"], "AMBIGUOUS")
            s.kill()
        finally:
            t.FAKE = old
        with open(state) as f:
            self.assertEqual([r["amount"] for r in json.load(f)["refunds"]], [777])


class SameArgsRedecision(unittest.TestCase):
    def test_same_arguments_after_a_stale_refusal_are_a_new_decision(self):
        state = {"refunds": [], "note": 0, "reads": 0}

        def get_order(order_id):
            state["reads"] += 1
            if state["reads"] == 2:
                state["note"] = 1
            return {"order_id": order_id, "refunded_total": sum(state["refunds"]), "notes": state["note"]}

        def get_approval(order_id):
            return {"id": "case-" + order_id, "match": {"order_id": order_id}, "max": {"amount": 20 - sum(state["refunds"])}}

        def create_refund(order_id, amount, reference=None):
            state["refunds"].append(amount)
            return {"refund": 1}
        spec = {"key": ["order_id"], "idempotency_argument": "reference",
                "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"}, "fields": ["refunded_total", "notes"]},
                "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
                "approval": {"tool": "get_approval", "arguments": {"order_id": "order_id"}}}
        tools = protect({"get_order": get_order, "get_approval": get_approval, "create_refund": create_refund,
                         "find_refund": lambda reference: {"found": False}},
                        {"journal_dir": tempfile.mkdtemp(), "claim_ttl": 0, "tools": {"create_refund": spec}})
        first = tools["create_refund"](order_id="881", amount=20)
        self.assertEqual(first["status"], "REFUSED:stale_premise")
        self.assertTrue(first["repair"]["may_retry"])
        second = tools["create_refund"](order_id="881", amount=20)
        self.assertEqual(second["status"], "COMMITTED")
        self.assertEqual(tools["create_refund"](order_id="881", amount=20)["status"], "DUPLICATE_IGNORED")
        self.assertEqual(state["refunds"], [20])


class EasyPremiseReads(unittest.TestCase):
    def test_one_read_per_check_and_the_change_is_recorded(self):
        seq, calls = [0, 5, 0], {"n": 0}

        def facts(order):
            v = seq[min(calls["n"], len(seq) - 1)]
            calls["n"] += 1
            return {"refunded": v}
        il = Interlock(tempfile.mkdtemp())

        @il.effect(key=lambda order: f"r:{order}", premises=facts, dedupes=True)
        def refund(order, idempotency_key):
            return "sent"
        self.assertEqual(refund("o1")[0], "REFUSED:stale_premise")
        self.assertEqual(calls["n"], 2)
        r = [e for e in refund.gate.journal.entries() if e["kind"] == "REFUSED"][-1]
        self.assertEqual(r["checks"]["violations"], ["refunded: was 0, now 5"])
        self.assertEqual(r["changes"], [{"field": "refunded", "was": 0, "now": 5}])

    def test_a_patched_validate_premises_still_runs(self):
        il = Interlock(tempfile.mkdtemp())

        @il.effect(key=lambda order: f"r:{order}", premises=lambda order: {"x": 1}, dedupes=True)
        def refund(order, idempotency_key):
            return "sent"
        refund.gate.target.validate_premises = lambda premises, eid=None: ["patched"]
        self.assertEqual(refund("o1")[0], "REFUSED:stale_premise")


class EnvelopeLeaseMessage(unittest.TestCase):
    def test_over_limit_says_no_approval_covers_it(self):
        tools = protect({"get_approval": lambda order_id: {"id": "case-1", "match": {"order_id": order_id}, "max": {"amount": 20}},
                         "create_refund": lambda order_id, amount: {"refund": 1}},
                        {"journal_dir": tempfile.mkdtemp(), "tools": {"create_refund": {
                            "key": ["order_id"], "approval": {"tool": "get_approval", "arguments": {"order_id": "order_id"}}}}})
        out = tools["create_refund"](order_id="881", amount=30)
        self.assertEqual(out["status"], "REFUSED:lease")
        self.assertIn("no live approval covers it", out["message"])
        self.assertNotIn("not live", out["message"])
        self.assertEqual(out["escalation"]["why"], "no live approval covers it")


class OldNames(unittest.TestCase):
    def test_names_callers_of_either_parent_import(self):
        import interlock.mcp_proxy as m
        import interlock.tools as tools
        for n in ("WHY", "code", "describe", "explain", "Rejected", "effect_id_for", "open_dispatch",
                  "RESOLVED", "ToolError", "structured", "fill"):
            self.assertTrue(hasattr(m, n), n)
        self.assertEqual(m.WHY["stale_premise"], "a fact this action depends on changed since it was decided")
        self.assertEqual(tools.WHY["REFUSED:stale_premise"], "a fact this action depends on changed since it was decided")
        self.assertEqual(tools.WHY["REFUSED:lease"], "no live approval covers it")
        self.assertEqual(list(inspect.signature(tools.repair).parameters)[:3], ["gate", "entries", "status"])
        tl, _ = refunder()
        tl["create_refund"](order_id="881", amount=20)
        call = tl.interlock.gates and next(iter(tl.interlock.gates.values()))
        eid = call.journal.entries()[0]["effect_id"]
        self.assertFalse(tools.repair(call, eid, "REFUSED:target_error")["may_retry"])
        gated = tools.gated(Interlock(tempfile.mkdtemp()), "create_refund", {"key": ["order_id"]}, lambda n, a: {})
        self.assertEqual(gated.key({"order_id": "881"}), 'create_refund:{"order_id": "881"}')


if __name__ == "__main__":
    unittest.main()
