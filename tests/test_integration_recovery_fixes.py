"""Failed tool reads stay unresolved, and ADK recovery keeps the recorded target."""
import tempfile
import unittest
from types import SimpleNamespace

from interlock import Leases, SimulatedCrash
from interlock.integrations.adk import Guard
from interlock.journal import effect_id_for, open_dispatch
from interlock.targets.stripe_api import StripeRefunds
from interlock.tools import protect


READ_ERROR = {"isError": True, "content": [{"type": "text", "text": "Database unavailable"}]}
BAD_READS = [READ_ERROR, {}, "not JSON", {"content": [{"type": "text", "text": "[]"}]}]


class ToolReadFailures(unittest.TestCase):
    def directory(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def test_failed_or_missing_premises_do_not_send_and_can_retry(self):
        for bad in BAD_READS:
            with self.subTest(result=bad):
                state, sent = {"facts": bad}, []
                tools = protect({"read": lambda **kw: state["facts"],
                                 "refund": lambda **kw: sent.append(kw)},
                                {"journal_dir": self.directory(), "tools": {"refund": {
                                    "key": ["order"], "premises": {"tool": "read", "arguments": {},
                                                                  "fields": ["refunded"]}}}})
                self.assertEqual(tools["refund"](order="A")["status"], "NOT_SENT")
                self.assertEqual(sent, [])
                state["facts"] = {"refunded": 0}
                self.assertEqual(tools["refund"](order="A")["status"], "COMMITTED")
                self.assertEqual(sent, [{"order": "A"}])

    def test_failure_at_dispatch_recheck_does_not_send(self):
        reads, sent = iter([{"refunded": 0}, READ_ERROR]), []
        tools = protect({"read": lambda: next(reads), "refund": lambda **kw: sent.append(kw)},
                        {"journal_dir": self.directory(), "tools": {"refund": {
                            "key": ["order"], "premises": {"tool": "read", "arguments": {},
                                                          "fields": ["refunded"]}}}})
        self.assertEqual(tools["refund"](order="A")["status"], "NOT_SENT")
        self.assertEqual(sent, [])

    def test_bad_recovery_lookup_never_resends_a_landed_action(self):
        for bad in BAD_READS + [{"found": "false"}, {"found": None}, {"found": 0}]:
            with self.subTest(result=bad):
                state, sent = {"lookup": bad}, []

                def refund(**arguments):
                    sent.append(arguments)
                    raise ConnectionError("response lost after the refund landed")

                tools = protect({"lookup": lambda **kw: state["lookup"], "refund": refund},
                                {"journal_dir": self.directory(), "claim_ttl": 0, "tools": {"refund": {
                                    "key": ["order"], "lookup": {"tool": "lookup", "arguments": {}}}}})
                self.assertEqual(tools["refund"](order="A")["status"], "IN_FLIGHT")
                recovered = next(iter(tools.recover().values()))
                self.assertTrue(next(iter(recovered.values())).startswith("UNRESOLVED:"))
                gate = next(iter(tools.interlock.gates.values()))
                self.assertTrue(open_dispatch(gate.journal.entries()))
                self.assertEqual(len(sent), 1)
                state["lookup"] = {"found": True}
                self.assertEqual(next(iter(next(iter(tools.recover().values())).values())), "COMMITTED_ON_QUERY")
                self.assertEqual(len(sent), 1)

    def test_explicit_negative_lookup_allows_recovery_send(self):
        sent = []

        def refund(**arguments):
            if not sent:
                sent.append("lost before arrival")
                raise ConnectionError("request did not arrive")
            sent.append(arguments)
            return {"ok": True}

        tools = protect({"lookup": lambda: {"found": False}, "refund": refund},
                        {"journal_dir": self.directory(), "claim_ttl": 0, "tools": {"refund": {
                            "key": ["order"], "lookup": {"tool": "lookup", "arguments": {}}}}})
        tools["refund"](order="A")
        self.assertEqual(next(iter(next(iter(tools.recover().values())).values())), "REAPPLIED_AFTER_QUERY")
        self.assertEqual(sent, ["lost before arrival", {"order": "A"}])


class AdkRecordedTarget(unittest.TestCase):
    def test_changed_payment_on_replay_recovers_only_the_recorded_payment(self):
        for incoming in ("pi_A", "pi_B"):
            with self.subTest(incoming=incoming), tempfile.TemporaryDirectory() as directory:
                class Client:
                    def __init__(self):
                        self.crash, self.sent = True, []

                    def request(self, method, path, params=None, idempotency_key=None):
                        if method == "GET":
                            return {"data": []}
                        if self.crash:
                            self.crash = False
                            raise SimulatedCrash("before sending")
                        self.sent.append(params)
                        return {"_replayed": False, "id": "re_1", "amount": params["amount"]}

                client, leases = Client(), Leases()
                leases.grant("L")
                guard = Guard(directory, leases, claim_ttl=0, poll=0)
                guard.gate("refund", target_for=lambda effect: StripeRefunds(client, effect["payment_intent"]),
                           proposal=lambda args, ctx: {"request_id": "case-1", "lease": "L", "effect": args,
                               "premises": {"payment_intent": args["payment_intent"], "refunded_by_others": 0}})
                ctx = SimpleNamespace(invocation_id="inv", function_call_id="call", agent_name="agent")
                with self.assertRaises(SimulatedCrash):
                    guard.run("refund", {"payment_intent": "pi_A", "amount": 20}, ctx)
                out = guard.run("refund", {"payment_intent": incoming, "amount": 20}, ctx)
                expected = "COMMITTED_BY_RETRY" if incoming == "pi_A" else "REFUSED:conflicting_payload"
                self.assertEqual(out["interlock"], expected)
                self.assertEqual([send["payment_intent"] for send in client.sent], ["pi_A"])
                entries = guard._gate("refund", {"payment_intent": "pi_A"}).journal.entries(
                    effect_id_for({"request_id": "case-1"}))
                self.assertFalse(open_dispatch(entries))
                self.assertEqual([e["effect"]["payment_intent"] for e in entries if e["kind"] == "DISPATCHED"], ["pi_A"])


if __name__ == "__main__":
    unittest.main()
