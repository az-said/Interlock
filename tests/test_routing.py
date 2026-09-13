"""
    python3 -m unittest discover -s tests

Routing, SLAs and a restart-safe inbox: an escalation goes to the group its route names, only
that group decides it, an unanswered item moves up the chain, a repair is a new decision, and a
fresh inbox rebuilds the same queue from the journal without losing or duplicating anything.
"""
import os, sys, tempfile, threading, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, SimulatedCrash, effect_id_for
from interlock.approvals import Authority, Inbox, Route, Rule
from interlock.targets import Payments

HOUR = 3600
POLICY = {"by": "policy", "rules": []}
CRASH = ("ambiguous", "stale_premise_at_recovery", "lease_at_recovery", "target_error")
RULES = [Rule("amount under $50", lambda r, facts: r["amount"] <= 50),
         Rule("customer not flagged", lambda r, facts: not r.get("flagged")),
         Rule("order eligible", lambda r, facts: facts["eligible"])]
ROUTES = [Route("risk", ["risk"], when=lambda i: i["request"].get("flagged")),
          Route("crash", ["payments-ops"], when=lambda i: i["reason"] in CRASH),
          Route("large", ["controller", "finance-manager"], when=lambda i: i["request"]["amount"] > 200, sla=4 * HOUR),
          Route("default", ["ap-leads", "finance-manager"], sla=4 * HOUR)]


def eid(rid):
    return effect_id_for({"request_id": rid})


def req(rid, order, amount, **extra):
    return {"id": rid, "order": order, "amount": amount, **extra}


def run_all(*fns):
    out = []
    ts = [threading.Thread(target=lambda f=f: out.append(f())) for f in fns]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


class Routing(unittest.TestCase):
    def setUp(self):
        self.use(".jsonl")

    def use(self, suffix, tier=2):
        self.now = [1000.0]
        self.api = Payments(tier)
        for order in ("1", "2", "3"):
            self.api.create_order(order, 400)
        self.groups = {"ap-leads": {"ana"}, "controller": {"cy"}, "finance-manager": {"fm"},
                       "payments-ops": {"ops"}, "risk": {"rita"}}
        self.auth = Authority(groups=self.groups, max_age=4 * HOUR, clock=lambda: self.now[0])
        self.path = tempfile.mktemp(suffix=suffix)
        self.ibx = self.inbox()

    def inbox(self, rules=None, routes=ROUTES):
        return Inbox(Gate(self.api, self.path, self.auth), capture=lambda r: self.api.capture(r["order"]),
                     effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                     rules=RULES if rules is None else rules, routes=routes, clock=lambda: self.now[0])

    def entries(self, rid=None, kind=None):
        es = self.ibx.gate.journal.entries(None if rid is None else eid(rid))
        return [x for x in es if kind is None or x["kind"] == kind]

    def hand(self, order, amount):
        self.api.refunds.append({"eid": "dashboard", "order": order, "amount": amount})

    def crash_sends(self):
        self.api.apply = lambda e, effect, crash=False: Payments.apply(self.api, e, effect, True)

    def stale_with_repair(self, total=100, by_hand=30, amount=100, routes=ROUTES):
        """A policy send refused because support refunded part by hand; the refusal suggests the rest (as L1 writes it)."""
        self.api.create_order("5", total)
        facts = self.api.capture("5")
        self.hand("5", by_hand)
        gate = self.ibx.gate
        self.assertEqual(gate.submit(self.ibx._proposal(req("r", "5", amount), POLICY, facts)), "REFUSED:stale_premise")
        left = total - by_hand
        gate.journal.append("REFUSED", eid("r"), code="stale_premise", reason=["refunded elsewhere since decision"],
                            changes=[{"field": "refunded", "was": 0, "now": by_hand}],
                            repairs=[{"code": "refund_remaining", "set": {"amount": left},
                                      "why": f"{left} is what is left to refund on this order"}])
        self.ibx = self.inbox(routes=routes)
        return self.ibx.queue["r"]["escalation"]

    # 20
    def test_route_by_amount_flag_and_reason(self):
        i = self.ibx
        for r in (req("big", "1", 250), req("flag", "2", 20, flagged=True), req("mid", "3", 80)):
            self.assertEqual(i.submit(r), "QUEUED")
        self.assertEqual({rid: it["group"] for rid, it in i.queue.items()},
                         {"big": "controller", "flag": "risk", "mid": "ap-leads"})
        self.assertEqual((i.queue["mid"]["routed_to"], i.queue["mid"]["level"], i.queue["mid"]["due"],
                          i.queue["mid"]["route"], i.queue["flag"]["due"]), (["ana"], 0, 1000 + 4 * HOUR, "default", None))

        self.use(".jsonl", tier=3)
        self.crash_sends()
        i = self.inbox(rules=[])
        with self.assertRaises(SimulatedCrash):
            i.submit(req("r9", "1", 20))
        i.reconcile(i.gate.recover())
        self.assertEqual((i.queue["r9"]["group"], i.queue["r9"]["reason"], i.queue["r9"]["detail"]),
                         ("payments-ops", "ambiguous", "AMBIGUOUS"))

    # 21
    def test_non_member_of_routed_group_cannot_decide(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        for act in (i.approve, i.reject, i.repair):
            self.assertEqual(act("r", "cy"), "REFUSED:lease")
        self.assertEqual(self.entries("r", "DECIDED"), [])
        self.assertIn("r", i.queue)
        self.assertEqual(self.api.refunded_total("1"), 0)

    # 22
    def test_decision_records_members_and_binds_the_lease(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        e = i.queue["r"]["escalation"]
        self.now[0] = 1500.0
        self.assertEqual(i.approve("r", "ana"), "COMMITTED")
        d = self.entries("r", "DECIDED")[0]
        self.assertEqual({k: d[k] for k in ("at", "by", "decision", "escalation", "group", "members", "repair")},
                         {"at": 1500.0, "by": "ana", "decision": "approve", "escalation": e, "group": "ap-leads",
                          "members": ["ana"], "repair": None})
        lease = {"by": "ana", "at": 1500.0, "group": "ap-leads", "escalation": e}
        sent = self.entries("r", "DISPATCHED")[0]
        self.assertEqual((sent["lease"], i.receipt("r")["authority"]), (lease, lease))
        self.assertEqual(sent["premises"], self.entries("r", "ESCALATED")[0]["facts"])

    # 23
    def test_member_removed_after_decision_is_refused_at_send_and_reescalated(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        i.approve("r", "ana", execute=False)
        self.groups["ap-leads"].discard("ana")
        self.hand("1", 10)
        self.assertEqual(i.execute("r"), "REFUSED:lease")
        item = i.queue["r"]
        self.assertEqual((item["reason"], item["facts"], item["breach"]), ("approver_removed", self.api.capture("1"), False))
        self.assertEqual(self.api.refunded_total("1"), 10)
        self.assertEqual(self.entries("r", "DISPATCHED"), [])

    # 24
    def test_expired_approval_reescalates_with_fresh_facts_and_diff(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        first = i.queue["r"]["escalation"]
        i.approve("r", "ana", execute=False)
        self.now[0] += 5 * HOUR
        self.hand("1", 30)
        self.assertEqual(i.execute("r"), "REFUSED:lease")
        item = i.queue["r"]
        self.assertEqual((item["reason"], item["changes"], item["facts"]["refunded"]),
                         ("approval_expired", [{"field": "refunded", "was": 0, "now": 30}], 30))
        self.assertEqual(i.approve("r", "ana", seen=first), "SUPERSEDED")
        self.assertEqual(i.approve("r", "ana", seen=item["escalation"]), "COMMITTED")
        self.assertEqual(self.api.refunded_total("1"), 110)
        self.assertEqual(self.entries("r", "DISPATCHED")[-1]["premises"]["refunded"], 30)

    # 25
    def test_unanswered_item_escalates_up_the_chain_after_sla(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        self.now[0] += 3 * HOUR
        self.assertEqual(i.tick(), {})
        self.now[0] += HOUR
        self.assertEqual(i.tick(), {"r": "finance-manager"})
        item = i.queue["r"]
        self.assertEqual((item["group"], item["level"], item["breach"], item["routed_to"], item["due"], item["reason"]),
                         ("finance-manager", 1, True, ["fm"], self.now[0] + 4 * HOUR, "needs_judgment"))
        self.assertEqual(i.approve("r", "ana"), "REFUSED:lease")
        self.assertEqual(i.approve("r", "fm"), "COMMITTED")

    # 26
    def test_top_of_chain_breach_recorded_once(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        self.now[0] += 4 * HOUR
        i.tick()
        self.now[0] += 4 * HOUR
        self.assertEqual(i.tick(), {"r": "BREACHED"})
        self.now[0] += 4 * HOUR
        self.assertEqual(i.tick(), {})
        es = self.entries("r", "ESCALATED")
        self.assertEqual((len(es), es[-1]["due"], es[-1]["group"], es[-1]["level"], es[-1]["breach"]),
                         (3, None, "finance-manager", 1, True))

    # 27
    def test_approval_racing_sla_is_superseded(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        old = i.queue["r"]["escalation"]
        self.now[0] += 4 * HOUR
        i.tick()
        n = len(self.entries())
        self.assertEqual(i.approve("r", "fm", seen=old), "SUPERSEDED")
        self.assertEqual(len(self.entries()), n)

    # 28
    def test_concurrent_approvals_decide_once(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(suffix):
                self.use(suffix)
                self.ibx.submit(req("r", "1", 80))
                a, b = self.inbox(), self.inbox()
                out = run_all(lambda: a.approve("r", "ana"), lambda: b.approve("r", "ana"))
                self.assertEqual(sorted(out), ["ALREADY_DECIDED", "COMMITTED"])
                self.assertEqual((len(self.entries("r", "DECIDED")), self.api.refunded_total("1")), (1, 80))

    # 29
    def test_resubmit_of_escalated_request_returns_queued(self):
        i = self.ibx
        i.submit(req("r", "1", 80))
        facts = self.api.capture("2")
        self.hand("2", 5)
        i._send(req("s", "2", 20), POLICY, facts)                  # stale: escalated by the gate's refusal
        n = len(self.entries())
        self.assertEqual((i.submit(req("r", "1", 80)), i.submit(req("s", "2", 20))), ("QUEUED", "QUEUED"))
        self.assertEqual(len(self.entries()), n)

    # 30
    def test_restart_rebuilds_queue_and_approved_without_duplicates(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(suffix):
                self.use(suffix)
                i = self.ibx
                i.submit(req("q", "1", 80))
                i.submit(req("a", "2", 90))
                i.approve("a", "ana", execute=False)
                i.submit(req("c", "3", 20))
                j = self.inbox()
                self.assertEqual((j.queue, j.approved, j.cleared), (i.queue, i.approved, i.cleared))
                self.assertEqual((sorted(j.queue), sorted(j.approved), j.cleared), (["q"], ["a"], ["c"]))
                n = len(self.entries())
                j.refresh()
                j.refresh()
                self.assertEqual(len(self.entries()), n)

    # 31
    def test_crash_between_refusal_and_escalation_escalates_once(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(suffix):
                self.use(suffix)
                facts = self.api.capture("1")
                self.hand("1", 30)
                self.assertEqual(self.ibx.gate.submit(self.ibx._proposal(req("r", "1", 20), POLICY, facts)),
                                 "REFUSED:stale_premise")
                made = run_all(self.inbox, self.inbox)
                self.assertEqual(len(self.entries("r", "ESCALATED")), 1)
                self.assertTrue(all("r" in m.queue for m in made))
                self.assertEqual(made[0].queue["r"]["changes"], [{"field": "refunded", "was": 0, "now": 30}])

    # 32
    def test_crash_after_proposed_before_escalation_resubmits(self):
        r = req("r", "1", 80)
        self.ibx.gate.journal.append("PROPOSED", eid("r"), agent="inbox", lease=None, premises=self.api.capture("1"),
                                     effect={"order": "1", "amount": 80}, request=r)
        j = self.inbox()
        self.assertEqual((len(self.entries("r", "ESCALATED")), len(self.entries("r", "PROPOSED"))), (1, 1))
        self.assertEqual(j.queue["r"]["detail"], ["amount under $50"])
        self.inbox()
        self.assertEqual(len(self.entries("r", "ESCALATED")), 1)

    # 33
    def test_restart_after_decision_sends_once(self):
        self.ibx.submit(req("r", "1", 80))
        self.assertEqual(self.ibx.approve("r", "ana", execute=False), "APPROVED")
        b = self.inbox()
        self.assertEqual(b.execute_approved(), {"r": "COMMITTED"})
        self.assertEqual((self.inbox().approved, self.api.refunded_total("1")), ({}, 80))

    # 34
    def test_reconcile_after_restart_uses_journal(self):
        self.crash_sends()
        with self.assertRaises(SimulatedCrash):
            self.ibx.submit(req("r", "1", 20))
        del self.api.apply
        b = self.inbox()
        self.assertEqual((b.sent, b.cleared), ({}, []))
        b.reconcile(b.gate.recover())
        self.assertEqual((b.cleared, b.queue, self.api.refunded_total("1")), (["r"], {}, 20))

    # 35
    def test_in_flight_status_is_not_escalated(self):
        r = req("r", "1", 20)
        with self.assertRaises(SimulatedCrash):
            self.ibx.gate.submit(self.ibx._proposal(r, POLICY, self.api.capture("1")), crash_before_effect=True)
        self.assertEqual(self.ibx.submit(r), "IN_FLIGHT")
        self.ibx.reconcile({eid("r"): "UNRESOLVED:RuntimeError"})
        self.inbox()
        self.assertEqual((self.entries("r", "ESCALATED"), self.ibx.queue), ([], {}))

    # 36
    def test_ambiguous_item_cannot_be_approved_but_can_be_closed(self):
        self.use(".jsonl", tier=3)
        self.crash_sends()
        i = self.inbox(rules=[])
        r = req("r", "1", 20)
        with self.assertRaises(SimulatedCrash):
            i.submit(r)
        del self.api.apply
        i.reconcile(i.gate.recover())
        self.assertEqual(i.approve("r", "ops"), "REFUSED:ambiguous")
        self.assertEqual(i.reject("r", "ops"), "REJECTED")
        self.assertEqual(i.gate.submit(i._proposal(r, POLICY, self.api.capture("1"))), "AMBIGUOUS")
        self.assertEqual((self.api.refunded_total("1"), len(self.entries("r", "DISPATCHED")), i.queue), (20, 1, {}))

    # 37
    def test_repair_with_new_amount_is_a_new_effect_never_the_refused_id(self):
        e = self.stale_with_repair()
        self.assertEqual(self.ibx.queue["r"]["repairs"][0]["set"], {"amount": 70})
        self.assertEqual(self.ibx.repair("r", "ana"), "COMMITTED")
        child = f"r:repair:{e[:8]}"
        self.assertEqual(self.entries(child, "PROPOSED")[0]["request"]["repair_of"], "r")
        self.assertEqual(self.entries(child, "DISPATCHED")[0]["effect"], {"order": "5", "amount": 70})
        self.assertEqual(self.entries("r", "DISPATCHED"), [])
        d = self.entries("r", "DECIDED")[0]
        self.assertEqual((d["decision"], d["repair"]), ("repair", {"code": "refund_remaining", "set": {"amount": 70},
                                                                   "request_id": child}))
        other = {"agent": "agent", "lease": POLICY, "request_id": "r", "premises": self.api.capture("5"),
                 "effect": {"order": "5", "amount": 70}}
        self.assertEqual(self.ibx.gate.submit(other), "REFUSED:conflicting_payload")
        self.assertEqual(self.api.refunded_total("5"), 100)

    # 38
    def test_repair_goes_back_through_rules_or_the_routed_person(self):
        routes = [Route("refused", ["ap-leads"], when=lambda i: i["reason"] != "needs_judgment"),
                  Route("judgment", ["controller"])]
        e = self.stale_with_repair(routes=routes)
        child = f"r:repair:{e[:8]}"
        self.assertEqual(self.ibx.repair("r", "ana"), "QUEUED")
        self.assertEqual((self.ibx.queue[child]["group"], self.ibx.queue[child]["reason"]), ("controller", "needs_judgment"))
        self.assertEqual(self.api.refunded_total("5"), 30)

        self.use(".jsonl")
        self.groups["controller"].add("ana")
        e = self.stale_with_repair(routes=routes)
        child = f"r:repair:{e[:8]}"
        self.assertEqual(self.ibx.repair("r", "ana"), "COMMITTED")
        d = self.entries(child, "DECIDED")
        self.assertEqual((len(d), d[0]["by"], d[0]["group"]), (1, "ana", "controller"))
        self.assertEqual(self.api.refunded_total("5"), 100)

    # 39
    def test_repair_on_changed_facts_is_superseded(self):
        e = self.stale_with_repair()
        self.hand("5", 10)
        self.assertEqual(self.ibx.repair("r", "ana"), "SUPERSEDED")
        es = self.entries("r", "ESCALATED")
        self.assertEqual((len(es), es[-1]["changes"], es[-1]["repairs"], es[-1]["reason"]),
                         (2, [{"field": "refunded", "was": 30, "now": 40}], [], "stale_premise"))
        self.assertEqual((self.entries(f"r:repair:{e[:8]}"), self.entries("r", "DECIDED")), ([], []))
        self.assertEqual(self.ibx.repair("r", "ana"), "REFUSED:no_repair")

    # 40
    def test_repair_accepted_twice_or_concurrently_is_one_effect(self):
        self.stale_with_repair()
        self.assertEqual(self.ibx.repair("r", "ana"), "COMMITTED")
        self.assertEqual(self.ibx.repair("r", "ana"), "ALREADY_DECIDED")
        self.assertEqual(self.api.refunded_total("5"), 100)
        for suffix in (".jsonl", ".db"):
            with self.subTest(suffix):
                self.use(suffix)
                e = self.stale_with_repair()
                a, b = self.inbox(), self.inbox()
                out = sorted(run_all(lambda: a.repair("r", "ana"), lambda: b.repair("r", "ana")))
                self.assertIn(out, (["ALREADY_DECIDED", "COMMITTED"], ["COMMITTED", "SUPERSEDED"]))
                self.assertEqual(len(self.entries("r", "DECIDED")), 1)
                self.assertEqual(len(self.entries(f"r:repair:{e[:8]}", "COMMITTED")), 1)
                self.assertEqual(self.api.refunded_total("5"), 100)

    # 41
    def test_repair_refused_while_original_in_flight_or_committed(self):
        e = self.stale_with_repair()
        self.crash_sends()
        with self.assertRaises(SimulatedCrash):
            self.ibx.approve("r", "ana")
        del self.api.apply
        self.assertEqual(self.ibx.repair("r", "ana"), "ALREADY_DECIDED")
        self.ibx.gate.recover()
        self.assertEqual(self.ibx.repair("r", "ana"), "ALREADY_DECIDED")
        self.assertEqual((self.entries(f"r:repair:{e[:8]}"), self.api.refunded_total("5")), ([], 130))

    # 42
    def test_crash_between_repair_decision_and_child_submit_submits_child_once(self):
        e = self.stale_with_repair()
        child = f"r:repair:{e[:8]}"

        def crash(*a):
            raise SimulatedCrash("inbox died")
        self.ibx._submit = crash
        with self.assertRaises(SimulatedCrash):
            self.ibx.repair("r", "ana")
        self.assertEqual(self.entries(child), [])
        j = self.inbox()
        self.assertEqual((j.queue[child]["detail"], j.queue[child]["facts"]["refunded"]), (["amount under $50"], 30))
        n = len(self.entries())
        self.inbox()
        self.assertEqual(len(self.entries()), n)
        self.assertEqual(j.approve(child, "ana"), "COMMITTED")
        self.assertEqual(self.api.refunded_total("5"), 100)

    # 43
    def test_accepted_repair_closes_original_against_direct_gate_submit(self):
        self.stale_with_repair()
        self.assertEqual(self.ibx.repair("r", "ana"), "COMMITTED")
        direct = {"agent": "agent", "lease": {"by": "policy", "rules": ["direct"]}, "request_id": "r",
                  "premises": self.api.capture("5"), "effect": {"order": "5", "amount": 100}}
        self.assertEqual(self.ibx.gate.submit(direct), "REFUSED:closed")
        self.assertEqual(self.api.refunded_total("5"), 100)
        self.assertFalse(any(x["eid"] == eid("r") for x in self.api.refunds))


if __name__ == "__main__":
    unittest.main()
