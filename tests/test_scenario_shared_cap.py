"""Offline logic of scenarios/shared_cap: the cap reservation, the headroom premise, the hand check, ground truth."""
import multiprocessing, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock.gate import SimulatedCrash
from scenarios.shared_cap.cap import (CAP, BOTS, CapGate, CapRefunds, CaseApproval, case_id, effect_id,
                                      ground_truth, hand_check_decision, race_mechanism, reserved_cents)


class Ledger:
    """A local tier-1 refunds target: dedupes on the effect id."""
    tier, queryable, dedup_window = 1, True, 24 * 3600

    def __init__(self):
        self.refunds = {}

    def validate_premises(self, premises, eid=None):
        return []

    def apply(self, eid, effect, crash_after_effect=False):
        self.refunds.setdefault(eid, effect["amount"])
        if crash_after_effect:
            raise SimulatedCrash(eid)
        return {"status": "ok"}

    def query(self, eid, effect):
        return eid in self.refunds


def proposal(case, bot, amount=2000):
    return {"agent": bot, "lease": case, "request_id": f"{case}/{bot}", "premises": {},
            "effect": {"case": case, "bot": bot, "amount": amount}}


def race(path, case, bot, go, out):
    time.sleep(max(0, go - time.time()))
    out.put(CapGate(Ledger(), path, CaseApproval(case, CAP), CAP).submit(proposal(case, bot)))


class SharedCap(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "journal.db")
        self.case = case_id("t")

    def gate(self, target, ttl=40):
        return CapGate(target, self.path, CaseApproval(self.case, CAP), CAP, claim_ttl=ttl)

    def test_in_flight_reservation_refuses_the_other_bot_and_recovery_lands_once(self):
        ledger = Ledger()
        with self.assertRaises(SimulatedCrash):
            self.gate(ledger, ttl=0.2).submit(proposal(self.case, "support-bot"), crash_after_effect=True)
        other = self.gate(ledger)
        self.assertEqual(other.submit(proposal(self.case, "billing-bot")), "REFUSED:over_cap")
        refusal = other.journal.entries(effect_id(self.case, "billing-bot"))[-1]
        self.assertEqual(refusal["reserved_by_others"], {effect_id(self.case, "support-bot"): 2000})
        time.sleep(0.3)
        self.assertEqual(self.gate(ledger).recover(), {effect_id(self.case, "support-bot"): "COMMITTED_BY_RETRY"})
        self.assertEqual(sum(ledger.refunds.values()), 2000)

    def test_headroom_left_lets_both_land(self):
        gate = self.gate(Ledger())
        self.assertEqual(gate.submit(proposal(self.case, "support-bot", 1000)), "COMMITTED")
        self.assertEqual(gate.submit(proposal(self.case, "billing-bot", 2000)), "COMMITTED")

    def test_refused_at_recovery_gives_the_reservation_back(self):
        j, eid = self.gate(Ledger()).journal, effect_id(self.case, "support-bot")
        j.dispatch(eid, {"case": self.case, "amount": 2000}, "w")
        self.assertEqual(reserved_cents(j.entries(), self.case, None)[0], 2000)
        j.append("REFUSED", eid, reason="stale at recovery", resolves=True)
        self.assertEqual(reserved_cents(j.entries(), self.case, None)[0], 0)

    def test_two_processes_racing_one_dispatches(self):
        ctx = multiprocessing.get_context("spawn")
        out, go = ctx.Queue(), time.time() + 1.5
        self.gate(Ledger())                                     # create the database before the race
        ps = [ctx.Process(target=race, args=(self.path, self.case, f"bot-{i}", go, out)) for i in range(6)]
        for p in ps:
            p.start()
        for p in ps:
            p.join(30)
        statuses = sorted(out.get(timeout=5) for _ in ps)
        self.assertEqual(statuses.count("COMMITTED"), 1, statuses)
        self.assertEqual(statuses.count("REFUSED:over_cap"), 5, statuses)

    def test_headroom_premise(self):
        class Client:
            def __init__(self, refunds):
                self.data = refunds

            def request(self, method, path, params=None, idempotency_key=None):
                return {"data": self.data}
        mine = effect_id(self.case, "support-bot")
        refund = lambda amount, eid: {"amount": amount, "status": "succeeded", "metadata": {"interlock_effect_id": eid}}
        premises = {"amount": 2000, "cap": CAP}
        self.assertEqual(CapRefunds(Client([refund(2000, mine)]), "pi").validate_premises(premises, mine), [])
        self.assertTrue(CapRefunds(Client([refund(2000, "other")]), "pi").validate_premises(premises, mine))

    def test_hand_check_decision(self):
        r = lambda amount, key: {"id": f"re_{key}", "amount": amount, "metadata": {"key": key}}
        self.assertEqual(hand_check_decision([], "k", 2000, CAP), ("SEND", 0))
        self.assertEqual(hand_check_decision([r(2000, "other")], "k", 2000, CAP), ("REFUSED:over_cap", 2000))
        self.assertEqual(hand_check_decision([r(2000, "k")], "k", 2000, CAP), ("FOUND_BY_LOOKUP", "re_k"))

    def test_race_mechanism(self):
        tl = {"billing-bot": {"check_start": 1.0, "check_read": 1.2, "sigkill": 1.1},
              "billing-bot (restart)": {"check_read": 1.4, "committed": 3.0},
              "support-bot": {"check_start": 1.05, "check_read": 1.3, "check_read_refunded": 0}}
        m = race_mechanism(tl, "billing-bot")
        self.assertEqual(m, {"saw_cents": 0, "read_started_before_crash": True, "read_done_before_crash": False,
                             "read_done_before_restart_reread": True, "read_in_restart_gap": False,
                             "read_done_before_rival_commit": True})
        self.assertIsNone(race_mechanism({"billing-bot": {"sigkill": 1}, "support-bot": {}}, "billing-bot"))

    def test_ground_truth(self):
        refunds = [{"id": "re_1", "amount": 2000, "status": "succeeded", "metadata": {"bot": "billing-bot"}},
                   {"id": "re_2", "amount": 2000, "status": "succeeded",
                    "metadata": {"interlock_effect_id": effect_id(self.case, BOTS[0])}},
                   {"id": "re_3", "amount": 2000, "status": "failed", "metadata": {}}]
        t = ground_truth(refunds, self.case)
        self.assertEqual((t["total_cents"], t["count"], t["invariant_held"]), (4000, 2, False))
        self.assertEqual([r["bot"] for r in t["refunds"]], ["billing-bot", "support-bot"])


if __name__ == "__main__":
    unittest.main()
