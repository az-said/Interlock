"""
    python3 -m unittest discover -s tests

Regressions for confirmed defects in escalation, routing, confirmation and scoreboard code.
Each test failed before its fix.
"""
import copy, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from interlock import Gate, Leases, SimulatedCrash, effect_id_for
from interlock.approvals import Authority, Inbox, Route, Rule
from interlock.confirm import confirm_event
from interlock.escalation import explain, record
from interlock.receipts import bundle, verify
from interlock.scoreboard import scoreboard
from interlock.targets import Payments
from interlock.targets.stripe_api import StripeRefunds
from interlock.mcp_proxy import Proxy, ToolError
from interlock.easy import Interlock
from interlock.temporal import Refused, gated
from test_confirmations import SECRET, T, Client, event, header

HOUR = 3600
SUFFIXES = (".jsonl", ".db")


def eid(rid):
    return effect_id_for({"request_id": rid})


class World:
    def __init__(self, suffix=".jsonl", tier=2, total=100, rules=None, routes=(), groups=None, approvers=()):
        self.now = [1000.0]
        self.api = Payments(tier)
        self.api.create_order("1", total)
        self.auth = Authority(approvers=approvers, groups=groups, max_age=4 * HOUR, clock=lambda: self.now[0])
        self.path = tempfile.mktemp(suffix=suffix)
        self.rules = [Rule("small", lambda r, f: r["amount"] <= 50)] if rules is None else rules
        self.routes = routes
        self.ibx = self.inbox()

    def inbox(self):
        return Inbox(Gate(self.api, self.path, self.auth), capture=lambda r: self.api.capture(r["order"]),
                     effect=lambda r: {"order": r["order"], "amount": r["amount"]}, rules=self.rules,
                     routes=self.routes, clock=lambda: self.now[0])

    def hand(self, amount, name="hand"):
        self.api.refunds.append({"eid": name, "order": "1", "amount": amount})

    def proposal(self, request, lease, facts):
        return self.ibx._proposal(request, lease, facts)


class PersonLeaseAtDispatch(unittest.TestCase):
    """Defects 1, 2, 10, 11: dispatch binds a person's lease to the escalation's facts and group (I7)."""

    def test_approval_lease_on_facts_the_approver_never_saw_is_not_sent(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, groups={"controllers": {"alice"}}, routes=[Route("big", ["controllers"])])
                r = {"id": "r1", "order": "1", "amount": 80}
                self.assertEqual(w.ibx.submit(r), "QUEUED")
                self.assertEqual(w.ibx.approve("r1", "alice", execute=False), "APPROVED")
                a = w.ibx.approved["r1"]
                w.hand(30)
                status = w.ibx.gate.submit(w.proposal(r, a["authority"], w.api.capture("1")))
                self.assertNotEqual(status, "COMMITTED")
                self.assertEqual(w.api.refunded_total("1"), 30)

    def test_lease_naming_another_group_is_not_sent(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, groups={"controllers": {"alice"}, "ops": {"alice"}},
                          routes=[Route("big", ["controllers"])])
                r = {"id": "r1", "order": "1", "amount": 80}
                w.ibx.submit(r)
                w.ibx.approve("r1", "alice", execute=False)
                a = w.ibx.approved["r1"]
                w.auth.groups["controllers"] = set()
                status = w.ibx.gate.submit(w.proposal(r, dict(a["authority"], group="ops"), a["facts"]))
                self.assertNotEqual(status, "COMMITTED")
                self.assertEqual(w.api.refunded_total("1"), 0)

    def test_honest_approval_still_sends(self):
        w = World(groups={"controllers": {"alice"}}, routes=[Route("big", ["controllers"])])
        w.ibx.submit({"id": "r1", "order": "1", "amount": 80})
        self.assertEqual(w.ibx.approve("r1", "alice"), "COMMITTED")
        self.assertTrue(verify(bundle(w.ibx.gate.journal, eid("r1")))["valid"])


class ExplainPicksTheOutcome(unittest.TestCase):
    """Defect 3: an AMBIGUOUS status is explained by the AMBIGUOUS entry, not a later refusal."""

    def test_ambiguous_after_conflicting_retry(self):
        class Live:
            def is_live(self, lease):
                return True
        api = Payments(3)
        api.create_order("1", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), Live())
        p = lambda amount: {"agent": "a", "lease": "L", "request_id": "r1", "premises": api.capture("1"),
                            "effect": {"order": "1", "amount": amount}}
        with self.assertRaises(SimulatedCrash):
            gate.submit(p(20), crash_after_effect=True)
        self.assertEqual(gate.recover(), {eid("r1"): "AMBIGUOUS"})
        self.assertEqual(gate.submit(p(30)), "REFUSED:conflicting_payload")
        with self.assertRaises(Refused) as ctx:
            gated(gate, p(20))
        self.assertEqual(ctx.exception.escalation["status"], "AMBIGUOUS")
        self.assertIn("unclear whether it happened", str(ctx.exception))
        self.assertEqual(explain(gate.journal.entries(eid("r1")), "AMBIGUOUS")["reason"], "ambiguous")


class ReescalationReason(unittest.TestCase):
    """Defect 4: an awaiting_decision refusal does not replace the stale premise it follows."""

    def test_restart_after_awaiting_decision_keeps_stale_reason_and_repair(self):
        w = World(approvers={"alice"})
        r = {"id": "r1", "order": "1", "amount": 60}
        w.ibx.submit(r)
        w.ibx.approve("r1", "alice", execute=False)
        a = w.ibx.approved["r1"]
        w.hand(30)
        gate = w.ibx.gate
        self.assertEqual(gate.submit(w.proposal(r, a["authority"], a["facts"])), "REFUSED:stale_premise")
        self.assertEqual(gate.submit(w.proposal(r, {"by": "policy", "rules": ["small"]}, w.api.capture("1"))),
                         "REFUSED:awaiting_decision")
        item = w.inbox().queue["r1"]
        self.assertEqual(item["reason"], "stale_premise")
        self.assertEqual([x["code"] for x in item["repairs"]], ["still_fits"])


class BoundRequest(unittest.TestCase):
    """Defects 5, 6: the queue shows and routes the request the journal bound, which is what gets sent."""
    ROUTES = [Route("large", ["controller"], when=lambda i: i["request"]["amount"] > 200),
              Route("default", ["ap-leads"])]
    GROUPS = {"controller": {"cy"}, "ap-leads": {"ana"}}

    def test_retry_with_other_amount_after_crash_routes_by_bound_amount(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, total=400, groups=self.GROUPS, routes=self.ROUTES)
                big = {"id": "r", "order": "1", "amount": 300}
                w.ibx.gate.journal.append("PROPOSED", eid("r"), agent="inbox", lease=None, premises=w.api.capture("1"),
                                          effect={"order": "1", "amount": 300}, request=big)   # crashed before ESCALATED
                self.assertEqual(w.ibx.submit({"id": "r", "order": "1", "amount": 30}), "REFUSED:conflicting_payload")
                item = w.ibx.queue["r"]
                self.assertEqual((item["group"], item["request"]["amount"]), ("controller", 300))
                self.assertEqual(w.ibx.approve("r", "ana"), "REFUSED:lease")
                self.assertEqual(w.api.refunds, [])

    def test_resubmit_with_other_amount_does_not_change_what_queue_shows(self):
        w = World(total=400, groups=self.GROUPS, routes=self.ROUTES)
        self.assertEqual(w.ibx.submit({"id": "r", "order": "1", "amount": 300}), "QUEUED")
        self.assertEqual(w.ibx.submit({"id": "r", "order": "1", "amount": 30}), "QUEUED")
        self.assertEqual(w.ibx.queue["r"]["request"]["amount"], 300)


class StaleRepairs(unittest.TestCase):
    """Defect 13: repairs computed before the world moved again are not shown."""

    def test_restart_after_second_hand_refund_drops_repair(self):
        w = World(approvers={"ana"}, rules=[Rule("under 100", lambda r, f: r["amount"] <= 100)])
        r = {"id": "r1", "order": "1", "amount": 80}
        facts = w.api.capture("1")
        w.hand(30, "hand1")
        self.assertEqual(w.ibx.gate.submit(w.proposal(r, {"by": "policy", "rules": ["under 100"]}, facts)),
                         "REFUSED:stale_premise")
        w.hand(40, "hand2")
        ibx = w.inbox()
        self.assertEqual(ibx.queue["r1"]["repairs"], [])
        self.assertEqual(ibx.repair("r1", "ana"), "REFUSED:no_repair")
        self.assertEqual(w.api.refunded_total("1"), 70)


class Confirmations(unittest.TestCase):
    """Defects 7, 9, 12, 14, 16: out-of-order, foreign or early confirmations."""

    def world(self):
        client = Client()
        target = StripeRefunds(client, "pi_1")
        leases = Leases()
        leases.grant("L")
        gate = Gate(target, tempfile.mktemp(suffix=".jsonl"), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "case-1", "premises": target.capture(), "effect": {"amount": 5000}}
        self.assertEqual(gate.submit(P), "COMMITTED")
        return client, target, gate, P

    def deliver(self, gate, target, refund, **kw):
        p = event(refund, **kw)
        return confirm_event(gate.journal, target, p, header(p), SECRET, now=T)

    def test_late_pending_does_not_downgrade_succeeded(self):
        client, target, gate, P = self.world()
        r = client.refunds[0]
        self.assertEqual(self.deliver(gate, target, {**r, "status": "succeeded"}, type="refund.updated", id="evt_2"),
                         "CONFIRMED")
        self.assertNotEqual(self.deliver(gate, target, {**r, "status": "pending"}, id="evt_1"), "CONFIRMED")
        v = verify(gate.receipt_bundle(P))
        self.assertEqual((v["valid"], v["confirmed_by_target"]), (True, True))
        self.assertEqual(scoreboard(gate.journal, name="bot")["confirmed_by_target"], 1)

    def test_late_succeeded_does_not_overwrite_failed(self):
        client, target, gate, P = self.world()
        r = client.refunds[0]
        self.assertEqual(self.deliver(gate, target, {**r, "status": "failed"}, type="refund.failed", id="evt_f"),
                         "CONFIRMED")
        self.assertNotEqual(self.deliver(gate, target, {**r, "status": "succeeded"}, id="evt_c"), "CONFIRMED")
        self.assertIs(verify(gate.receipt_bundle(P))["confirmed_by_target"], False)

    def test_receipt_reads_final_status_by_precedence(self):
        client, target, gate, P = self.world()
        for status in ("failed", "succeeded", "pending"):           # a journal written before the fix
            gate.journal.append("CONFIRMED", effect_id_for(P), **record(
                "CONFIRMED", via="webhook", event=f"evt_{status}", refund="re_1", status=status, amount=5000,
                payment_intent="pi_1", created=T))
        self.assertIs(verify(gate.receipt_bundle(P))["confirmed_by_target"], False)

    def test_confirmation_of_another_refund_id_is_refused_and_flagged(self):
        client, target, gate, P = self.world()
        other = {**client.refunds[0], "id": "re_hand_with_copied_metadata"}
        self.assertEqual(self.deliver(gate, target, other, id="evt_x"), "REFUSED:mismatch")
        gate.journal.append("CONFIRMED", effect_id_for(P), **record(
            "CONFIRMED", via="webhook", event="evt_x", refund=other["id"], status="succeeded", amount=5000,
            payment_intent="pi_1", created=T))
        v = verify(gate.receipt_bundle(P))
        self.assertFalse(v["valid"])
        self.assertIn("target confirmed a refund other than the one sent", v["problems"])

    def test_confirmed_resend_in_flight_after_resolved_refusal_verifies(self):
        api = Payments(2)
        api.create_order("o1", 100)
        auth = Authority(approvers={"ana"}, clock=lambda: 1000.0)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), auth)
        inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                      effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                      rules=[Rule("small", lambda r, f: r["amount"] <= 50)], clock=lambda: 1000.0)
        r = {"id": "req1", "order": "o1", "amount": 40}
        with self.assertRaises(SimulatedCrash):
            gate.submit(inbox._proposal(r, {"by": "policy", "rules": ["small"]}, api.capture("o1")), crash_before_effect=True)
        api.refunds.append({"eid": "hand", "order": "o1", "amount": 10})
        self.assertEqual(gate.recover(), {eid("req1"): "REFUSED:stale_premise_at_recovery"})
        inbox.refresh()
        self.assertEqual(inbox.approve("req1", "ana", execute=False), "APPROVED")
        a = inbox.approved.pop("req1")
        with self.assertRaises(SimulatedCrash):
            gate.submit(inbox._proposal(a["request"], a["authority"], a["facts"]), crash_after_effect=True)

        class Target:
            payment_intent = "pi_1"
        refund = {"id": "re_1", "status": "succeeded", "amount": 40, "payment_intent": "pi_1",
                  "metadata": {"interlock_effect_id": eid("req1")}}
        self.assertEqual(self.deliver(gate, Target(), refund), "CONFIRMED")
        v = verify(bundle(gate.journal, eid("req1")))
        self.assertEqual((v["valid"], v["problems"], v["confirmed_by_target"]), (True, [], True))


class ScoreboardCountsOnce(unittest.TestCase):
    """Defects 8, 15: a stale repair re-shows the same unanswered item; it is not a second escalation."""

    def test_superseded_repair_after_stale_approval(self):
        w = World(approvers={"ana"})
        w.ibx.submit({"id": "req1", "order": "1", "amount": 80})
        w.ibx.approve("req1", "ana", execute=False)
        w.hand(30, "hand1")
        self.assertEqual(w.ibx.execute("req1"), "REFUSED:stale_premise")
        w.hand(10, "hand2")
        self.assertEqual(w.ibx.repair("req1", "ana"), "SUPERSEDED")
        s = scoreboard(w.ibx.gate.journal)
        self.assertEqual((s["requests"], s["stale_approvals_caught"], s["escalated_by_reason"]),
                         (1, 1, {"needs_judgment": 1, "stale_premise": 1}))

    def test_superseded_repair_after_crash(self):
        groups = {"ap-leads": {"ana"}}
        w = World(total=100, groups=groups, rules=[Rule("small", lambda r, f: r["amount"] <= 50)],
                  routes=[Route("default", ["ap-leads"], sla=4 * HOUR)])
        r = {"id": "r", "order": "1", "amount": 40}
        with self.assertRaises(SimulatedCrash):
            w.ibx.gate.submit(w.proposal(r, {"by": "policy", "rules": []}, w.api.capture("1")), crash_before_effect=True)
        w.hand(80, "dash")
        ibx = w.inbox()
        ibx.reconcile(ibx.gate.recover())
        self.assertEqual([x["code"] for x in ibx.queue["r"]["repairs"]], ["refund_remaining"])
        w.hand(5, "dash2")
        self.assertEqual(ibx.repair("r", "ana"), "SUPERSEDED")
        s = scoreboard(ibx.gate.journal)
        self.assertEqual((s["requests"], s["crash_to_person"], s["escalated_by_reason"], s["repairs_suggested"]),
                         (1, 1, {"stale_premise_at_recovery": 1}, 1))


class TamperedReceipt(unittest.TestCase):
    """Defect 17: verify reports a tampered escalated receipt instead of raising."""

    def test_missing_hash_or_kind_is_a_problem(self):
        w = World(approvers={"ana"})
        w.ibx.submit({"id": "r1", "order": "1", "amount": 80})
        w.ibx.approve("r1", "ana")
        b = bundle(w.ibx.gate.journal, eid("r1"))
        for field in ("hash", "kind"):
            with self.subTest(field):
                t = copy.deepcopy(b)
                del next(e for e in t["entries"] if e["kind"] == "ESCALATED")[field]
                v = verify(t)
                self.assertFalse(v["valid"])
                self.assertTrue(any("was altered" in p for p in v["problems"]))


class ProxySettlesOnlyItsOwnSend(unittest.TestCase):
    """A failed premise read never settles another call's send, so a retry never sends it twice (I2)."""
    TOOLS = {"create_refund": {"key": ["order_id"],
             "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"}, "fields": ["refunded_total"]},
             "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
             "idempotency_argument": "reference"}}

    class Up:
        def __init__(self):
            self.landed, self.pending, self.fail_read, self.decline = [], [], False, False

        def call_tool(self, name, args, timeout=60):
            if name == "get_order":
                if self.fail_read:
                    raise ToolError("upstream busy")
                return {"structuredContent": {"refunded_total": sum(r["amount"] for r in self.landed)}}
            if name == "find_refund":
                return {"structuredContent": {"found": any(r["reference"] == args["reference"] for r in self.landed)}}
            if self.decline:
                return {"isError": True, "content": [{"type": "text", "text": "card declined"}]}
            self.pending.append(args)                                  # accepted, but the answer never comes
            raise TimeoutError("create_refund did not answer")

    def proxy(self):
        p = object.__new__(Proxy)
        p.upstream, p.interlock, out = self.Up(), Interlock(tempfile.mkdtemp()), []
        p.tools = {n: p._gated(n, spec) for n, spec in self.TOOLS.items()}
        p.to_client = out.append
        call = lambda: (p._handle_call({"id": 1, "params": {"name": "create_refund",
                                                            "arguments": {"order_id": "881", "amount": 20}}}),
                        out[-1]["result"])[1]
        return p, call

    def test_failed_read_while_in_flight_does_not_settle_the_send(self):
        p, call = self.proxy()
        self.assertEqual(call()["_meta"]["interlock"]["status"], "IN_FLIGHT")
        p.upstream.fail_read = True
        self.assertEqual(call()["_meta"]["interlock"]["status"], "IN_FLIGHT")
        p.upstream.fail_read = False
        call()
        self.assertEqual(len(p.upstream.pending), 1)
        kinds = [e["kind"] for e in p.tools["create_refund"].gate.journal.entries()]
        self.assertEqual(kinds.count("DISPATCHED"), 1)
        self.assertNotIn("REFUSED", kinds)

    def test_failed_read_with_nothing_in_flight_says_nothing_was_sent(self):
        p, call = self.proxy()
        p.upstream.fail_read = True
        result = call()
        self.assertTrue(result["isError"])
        self.assertEqual(result["_meta"]["interlock"]["status"], "NOT_SENT")
        self.assertIn("could not be read", result["content"][0]["text"])
        self.assertEqual(p.tools["create_refund"].gate.journal.entries(), [])

    def test_declined_send_is_still_settled(self):
        p, call = self.proxy()
        p.upstream.decline = True
        self.assertEqual(call()["_meta"]["interlock"]["status"], "REFUSED:target_error")


class TemporalOutcome(unittest.TestCase):
    """The backend reads the status token, not the explanation that follows it."""

    def test_ambiguous_outcome_is_the_status(self):
        from interlock.temporal import outcome
        class Live:
            def is_live(self, lease):
                return True
        api = Payments(3)
        api.create_order("1", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), Live())
        P = {"agent": "a", "lease": "L", "request_id": "r1", "premises": api.capture("1"),
             "effect": {"order": "1", "amount": 20}}
        with self.assertRaises(SimulatedCrash):
            gated(gate, P, crash_after_effect=True)
        with self.assertRaises(Refused) as ctx:
            gated(gate, P)
        self.assertIn("unclear whether it happened", str(ctx.exception))
        self.assertEqual(outcome(str(ctx.exception)), "AMBIGUOUS")
        self.assertEqual(outcome("precheck: REFUSED:lease"), "REFUSED:lease")


class RepairChildCrash(unittest.TestCase):
    """A repair child that crashed before its escalation is escalated on the facts the repair was computed from."""

    def test_restart_does_not_overpay(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, approvers={"ana"})
                self.assertEqual(w.ibx.submit({"id": "r", "order": "1", "amount": 80}), "QUEUED")
                w.ibx.approve("r", "ana", execute=False)
                w.hand(30, "hand1")
                self.assertEqual(w.ibx.execute("r"), "REFUSED:stale_premise")
                real = Inbox._escalate

                def crash(self, request, *a, **kw):
                    if ":repair:" in request["id"]:
                        raise SimulatedCrash("died")
                    return real(self, request, *a, **kw)
                Inbox._escalate = crash
                try:
                    with self.assertRaises(SimulatedCrash):
                        w.ibx.repair("r", "ana")
                finally:
                    Inbox._escalate = real
                w.hand(40, "hand2")
                ibx = w.inbox()
                child = next(k for k in ibx.queue if ":repair:" in k)
                self.assertEqual(ibx.queue[child]["facts"]["refunded"], 30)
                self.assertNotEqual(ibx.approve(child, "ana"), "COMMITTED")
                self.assertEqual(w.api.refunded_total("1"), 70)


class OneBadCapture(unittest.TestCase):
    """A capture that raises for one request does not strand the others."""

    def broken(self, w, order):
        real = w.api.capture
        w.api.capture = lambda o: (_ for _ in ()).throw(KeyError(o)) if o == order else real(o)

    def test_restart_escalates_the_rest(self):
        w = World()
        w.api.create_order("2", 100)
        for rid, order in (("ra", "1"), ("rb", "2")):
            w.ibx.gate.journal.append("PROPOSED", eid(rid), agent="inbox", lease=None, premises=None,
                                      effect={"order": order, "amount": 80},
                                      request={"id": rid, "order": order, "amount": 80})
        self.broken(w, "1")
        ibx = w.inbox()
        self.assertEqual(list(ibx.queue), ["rb"])

    def test_reconcile_escalates_the_rest(self):
        w = World(tier=3, rules=[Rule("any", lambda r, f: True)])
        w.api.create_order("2", 100)
        for rid, order in (("r1", "1"), ("r2", "2")):
            r = {"id": rid, "order": order, "amount": 20}
            with self.assertRaises(SimulatedCrash):
                w.ibx.gate.submit(w.proposal(r, {"by": "policy", "rules": ["any"]}, w.api.capture(order)),
                                  crash_after_effect=True)
        self.broken(w, "1")
        w.ibx.reconcile(w.ibx.gate.recover())
        self.assertEqual(list(w.ibx.queue), ["r2"])

    def test_tick_moves_the_rest(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, groups={"a": {"ana"}, "b": {"bo"}}, routes=[Route("d", ["a", "b"], sla=HOUR)])
                for n in ("1", "2", "3"):
                    if n != "1":
                        w.api.create_order(n, 100)
                    w.ibx.submit({"id": "r" + n, "order": n, "amount": 80})
                self.broken(w, "1")
                w.now[0] += 2 * HOUR
                out = w.ibx.tick()
                self.assertEqual((out.get("r2"), out.get("r3")), ("b", "b"))
                self.assertEqual({k: v["group"] for k, v in w.ibx.queue.items()}, {"r1": "a", "r2": "b", "r3": "b"})


class RouteLostItsSla(unittest.TestCase):
    def test_tick_after_sla_removed_from_config(self):
        w = World(groups={"a": {"ana"}, "b": {"bo"}}, routes=[Route("d", ["a", "b"], sla=HOUR)])
        w.ibx.submit({"id": "r1", "order": "1", "amount": 80})
        w.routes = [Route("d", ["a", "b"])]
        ibx = w.inbox()
        w.now[0] += 2 * HOUR
        self.assertEqual(ibx.tick(), {"r1": "b"})
        self.assertIsNone(ibx.queue["r1"]["due"])


class StripeSubclassPremises(unittest.TestCase):
    """StripeRefunds.explain runs a subclass's validate_premises, like Payments.explain (I3)."""

    def test_override_still_refuses(self):
        class NoDisputed(StripeRefunds):
            def validate_premises(self, premises, eid=None):
                return ["payment disputed"]
        client = Client()
        target = NoDisputed(client, "pi_1")
        leases = Leases()
        leases.grant("L")
        gate = Gate(target, tempfile.mktemp(suffix=".jsonl"), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "c", "premises": target.capture(), "effect": {"amount": 500}}
        self.assertEqual(gate.submit(P), "REFUSED:stale_premise")
        self.assertEqual(client.refunds, [])


class AmbiguousKeepsItsGuard(unittest.TestCase):
    """An AMBIGUOUS crash case stays ambiguous when a retry with another payload lands before reconcile (P')."""

    def test_conflicting_retry_before_reconcile(self):
        w = World(tier=3, approvers={"alice"})
        r = {"id": "r1", "order": "1", "amount": 40}
        with self.assertRaises(SimulatedCrash):
            w.ibx.gate.submit(w.proposal(r, {"by": "policy", "rules": ["small"]}, w.api.capture("1")),
                              crash_after_effect=True)
        rec = w.ibx.gate.recover()
        retry = {**r, "amount": 45}
        self.assertEqual(w.ibx.gate.submit(w.proposal(retry, {"by": "policy", "rules": ["small"]}, w.api.capture("1"))),
                         "REFUSED:conflicting_payload")
        w.ibx.reconcile(rec)
        self.assertEqual(w.ibx.queue["r1"]["reason"], "ambiguous")
        self.assertEqual(w.ibx.approve("r1", "alice"), "REFUSED:ambiguous")
        again = w.inbox()
        self.assertEqual((list(again.queue), list(again.approved)), (["r1"], []))
        self.assertEqual(scoreboard(w.ibx.gate.journal)["crash_to_person"], 1)
        self.assertEqual(w.api.refunded_total("1"), 40)


class TargetRejection(unittest.TestCase):
    """A send the target answers 'not done' (a Stripe 400) is settled and escalated, never resent."""

    def rejecting(self, tier=1):
        from interlock.gate import Rejected

        class Rejecting(Payments):
            calls = 0

            def apply(self, eid, effect, crash_after_effect=False):
                Rejecting.calls += 1
                raise Rejected("400 amount exceeds unrefunded")
        return Rejecting

    def test_rejected_send_goes_to_a_person(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, tier=1, approvers={"alice"})
                w.api = api = self.rejecting()(1)
                api.create_order("1", 100)
                w.ibx = w.inbox()
                self.assertEqual(w.ibx.submit({"id": "r1", "order": "1", "amount": 40}), "REFUSED:target_error")
                for _ in range(3):
                    w.ibx.reconcile(w.ibx.gate.recover())
                self.assertEqual(type(api).calls, 1)
                self.assertEqual(w.inbox().queue["r1"]["reason"], "target_error")

    def test_rejected_resend_at_recovery_is_settled(self):
        api = self.rejecting()(1)
        api.create_order("1", 100)
        gate = Gate(api, tempfile.mktemp(suffix=".jsonl"), Authority(approvers={"alice"}))
        p = {"agent": "a", "lease": {"by": "policy"}, "request_id": "r1", "premises": api.capture("1"),
             "effect": {"order": "1", "amount": 40}}
        with self.assertRaises(SimulatedCrash):
            gate.submit(p, crash_before_effect=True)
        self.assertEqual(gate.recover(), {eid("r1"): "REFUSED:target_error"})
        self.assertEqual(gate.recover(), {})
        self.assertEqual(type(api).calls, 1)
        with self.assertRaises(Refused):
            gated(gate, p)

    def test_stripe_4xx_is_a_rejection_and_5xx_is_not(self):
        import io, urllib.error
        from unittest import mock
        from interlock.gate import Rejected
        from interlock.targets.stripe_api import StripeClient, StripeError
        client = StripeClient("sk_test_x")
        for code, rejected in ((400, True), (402, True), (409, False), (429, False), (500, False)):
            err = urllib.error.HTTPError("u", code, "m", {}, io.BytesIO(b'{"error": {"message": "no"}}'))
            with self.subTest(code), mock.patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaises(StripeError) as ctx:
                    client.request("POST", "/refunds", {})
                self.assertIs(isinstance(ctx.exception, Rejected), rejected)
            err.close()


class StaleCachedApproval(unittest.TestCase):
    """A second inbox's cached approval of an older escalation is not sent and does not supersede a newer one."""

    def test_second_inbox_does_not_discard_newer_approval(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix):
                w = World(suffix, approvers={"ana"})
                a = w.ibx
                self.assertEqual(a.submit({"id": "r", "order": "1", "amount": 80}), "QUEUED")
                a.approve("r", "ana", execute=False)
                b = w.inbox()
                self.assertEqual(list(b.approved), ["r"])
                w.hand(10)
                self.assertEqual(a.execute("r"), "REFUSED:stale_premise")
                self.assertEqual(a.approve("r", "ana", execute=False), "APPROVED")
                self.assertNotEqual(b.execute_approved().get("r"), "REFUSED:stale_premise")
                a.refresh()
                self.assertEqual((list(a.queue), a.execute_approved()), ([], {"r": "COMMITTED"}))
                self.assertEqual(w.api.refunded_total("1"), 90)
                self.assertEqual(scoreboard(a.gate.journal)["stale_approvals_caught"], 1)


class TickAfterOutage(unittest.TestCase):
    """An inbox down past several SLAs moves the item all the way in one tick, on the chain's own deadlines."""

    def world(self):
        return World(groups={"a": {"ana"}, "b": {"bo"}}, routes=[Route("d", ["a", "b"], sla=4 * HOUR)])

    def test_outage_past_every_deadline(self):
        w = self.world()
        w.ibx.submit({"id": "r", "order": "1", "amount": 80})
        t0 = w.now[0]
        w.now[0] = t0 + 12 * HOUR
        ibx = w.inbox()
        self.assertEqual(ibx.tick(), {"r": "b"})
        self.assertEqual(ibx.tick(), {})
        es = [x for x in ibx.gate.journal.entries(eid("r")) if x["kind"] == "ESCALATED"]
        self.assertEqual([(x["level"], x["due"], x["breach"]) for x in es],
                         [(0, t0 + 4 * HOUR, False), (1, t0 + 8 * HOUR, True), (1, None, True)])
        self.assertEqual(ibx.queue["r"]["group"], "b")

    def test_late_tick_keeps_the_next_deadline(self):
        w = self.world()
        w.ibx.submit({"id": "r", "order": "1", "amount": 80})
        t0 = w.now[0]
        w.now[0] = t0 + 5 * HOUR
        self.assertEqual(w.ibx.tick(), {"r": "b"})
        self.assertEqual(w.ibx.queue["r"]["due"], t0 + 8 * HOUR)


class ConfirmationPayment(unittest.TestCase):
    """A refund on another payment is never recorded as confirming this effect, whatever target the caller built."""

    def test_refund_on_other_payment_is_refused(self):
        client = Client()
        target = StripeRefunds(client, "pi_A")
        leases = Leases()
        leases.grant("L")
        gate = Gate(target, tempfile.mktemp(suffix=".jsonl"), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "case-1", "premises": target.capture(), "effect": {"amount": 5000}}
        with self.assertRaises(SimulatedCrash):
            gate.submit(P, crash_before_effect=True)
        foreign = {"id": "re_other", "object": "refund", "amount": 5000, "status": "succeeded", "payment_intent": "pi_B",
                   "metadata": {"interlock_effect_id": effect_id_for(P)}, "created": T}
        p = event(foreign)
        self.assertEqual(confirm_event(gate.journal, StripeRefunds(client, "pi_B"), p, header(p), SECRET, now=T),
                         "REFUSED:mismatch")
        gate.recover()
        self.assertTrue(verify(gate.receipt_bundle(P))["valid"])


class RepairChildIsNotCleared(unittest.TestCase):
    """A repair a person accepted is not 'cleared with no person', live or after a restart."""

    def test_cleared_matches_scoreboard(self):
        w = World(tier=1, approvers={"ann"})
        w.ibx.submit({"id": "r1", "order": "1", "amount": 60})
        w.ibx.approve("r1", "ann", execute=False)
        w.hand(60)
        self.assertEqual(w.ibx.execute("r1"), "REFUSED:stale_premise")
        self.assertEqual(w.ibx.repair("r1", "ann"), "COMMITTED")
        self.assertEqual((w.ibx.cleared, w.inbox().cleared), ([], []))
        self.assertEqual(scoreboard(w.ibx.gate.journal)["cleared_no_person"], 0)


class RepairAutoApprovalWait(unittest.TestCase):
    """A repair child approved at once by the person who accepted the repair is not a wait for a decision."""

    def test_time_to_decision_skips_it(self):
        w = World(approvers={"ana"})
        w.ibx.submit({"id": "r1", "order": "1", "amount": 80})
        w.now[0] += 100
        w.ibx.approve("r1", "ana", execute=False)
        w.hand(30)
        self.assertEqual(w.ibx.execute("r1"), "REFUSED:stale_premise")
        w.now[0] += 200
        self.assertEqual(w.ibx.repair("r1", "ana"), "COMMITTED")
        t = scoreboard(w.ibx.gate.journal)["time_to_decision"]
        self.assertEqual((t["n"], t["median"], t["max"]), (2, 150, 200))


class ReadmeMatchesResults(unittest.TestCase):
    """README's approval numbers are the ones results/approval_inbox.md reports."""

    def test_table_and_headline(self):
        import re
        rows = lambda text: {m[0].split(" (")[0]: (int(m[1]), int(m[2])) for m in
                             re.findall(r"^\| ([A-Za-z+ ]+(?: \(.*?\))?) \| (\d+) \| \**(\d+)\** \|$", text, re.M)}
        with open(os.path.join(ROOT, "results", "approval_inbox.md")) as f:
            md = f.read()
        results = rows(md)
        with open(os.path.join(ROOT, "README.md")) as f:
            readme = f.read()
        self.assertEqual(len(results), 3)
        self.assertEqual({k: v for k, v in rows(readme).items() if k in results}, results)
        reviews, _ = results["rules + Interlock"]
        self.assertIn(f"from 100 to {reviews} with zero wrong payouts, where rules alone paid out wrong "
                      f"{results['rules only'][1]} times", readme)
        extra = reviews - results["rules only"][0]
        why = md.split("## Why rules + Interlock")[1].split("Escalations by reason")[0]
        stopped = sum(int(v) for k, v in re.findall(r"^- (\w+): (\d+)$", why, re.M) if k != "needs_judgment")
        repairs = int(re.search(r"^- of those, deciding the new amount of an accepted repair: (\d+)$", why, re.M)[1])
        self.assertEqual(stopped + repairs, extra)          # every extra judgment review is a repair's new amount
        self.assertIn(f"Of the {extra} extra reviews, {stopped} are people closing or repairing refunds the gate "
                      f"stopped, not re-deciding them, and {repairs} is a person deciding the new, smaller amount "
                      f"of an accepted repair.", readme)


if __name__ == "__main__":
    unittest.main()
