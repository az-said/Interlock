"""
    python3 -m unittest discover -s tests

The approvals scoreboard is derived from the journal alone, so it survives restarts and can be
recomputed by anyone holding the entries.
"""
import json, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, effect_id_for
from interlock import approvals
from interlock.approvals import Authority
from interlock.escalation import WHY, record
from interlock.journal import open_journal
from interlock.scoreboard import scoreboard
from interlock.targets import Payments

POLICY = {"by": "policy", "rules": []}
STILL_FITS = {"code": "still_fits", "set": {}, "why": "still fits"}
REMAINING = {"code": "refund_remaining", "set": {"amount": 70}, "why": "70 is left"}


class Day:
    """Hand-built inbox chains: real gate sends, escalations and decisions written with record()."""
    def __init__(self, suffix=".jsonl"):
        self.api = Payments(2)
        self.gate = Gate(self.api, tempfile.mktemp(suffix=suffix), Authority(approvers={"ana", "fm"}))
        self.j = self.gate.journal

    def request(self, rid, amount=20, **extra):
        self.api.create_order(rid, 100)
        r = {"id": rid, "order": rid, "amount": amount, **extra}
        return r, effect_id_for({"request_id": rid})

    def proposal(self, r, lease):
        return {"agent": "inbox", "lease": lease, "request_id": r["id"], "request": r,
                "premises": self.api.capture(r["order"]), "effect": {"order": r["order"], "amount": r["amount"]}}

    def propose(self, r, eid):
        self.j.append("PROPOSED", eid, agent="inbox", lease=None, premises=self.api.capture(r["order"]),
                      effect={"order": r["order"], "amount": r["amount"]}, request=r)

    def escalate(self, r, eid, at, reason="needs_judgment", group="ap-leads", repairs=(), breach=False, level=0):
        return self.j.append("ESCALATED", eid, **record(
            "ESCALATED", at=at, reason=reason, why=WHY[reason], detail=[], facts=self.api.capture(r["order"]),
            changes=[], repairs=list(repairs), route="default", group=group, routed_to=["ana"], level=level,
            due=None, breach=breach))

    def decide(self, eid, e, at, decision="approve", by="ana", repair=None):
        return self.j.append("DECIDED", eid, **record(
            "DECIDED", at=at, by=by, decision=decision, escalation=e["hash"], group=e["group"],
            members=[by], repair=repair))

    def send_as(self, r, e, d):
        lease = {"by": d["by"], "at": d["at"], "group": e["group"], "escalation": e["hash"]}
        return self.gate.submit(self.proposal(r, lease))


def scripted():
    day = Day()
    j = day.j

    r, eid = day.request("routine")                                   # cleared by rules, confirmed by Stripe
    assert day.gate.submit(day.proposal(r, POLICY)) == "COMMITTED"
    j.append("CONFIRMED", eid, **record("CONFIRMED", via="webhook", event="evt_1", refund="re_1",
                                        status="succeeded", amount=20, payment_intent="pi_1", created=1))

    r, eid = day.request("judgment", 80)                              # needs judgment, a person approves
    day.propose(r, eid)
    e = day.escalate(r, eid, 10)
    assert day.send_as(r, e, day.decide(eid, e, 40)) == "COMMITTED"

    r, eid = day.request("stale", 80)                                 # approved, then facts moved: back to a person
    day.propose(r, eid)
    e = day.escalate(r, eid, 100)
    day.decide(eid, e, 130)
    day.escalate(r, eid, 200, reason="stale_premise", repairs=[STILL_FITS])

    r, eid = day.request("crash")                                     # crash nobody can check: a person closes it
    day.propose(r, eid)
    j.append("AUTHORIZED", eid, lease=POLICY)
    j.append("DISPATCHED", eid, effect={"order": "crash", "amount": 20}, lease=POLICY, premises={}, checks={})
    j.append("AMBIGUOUS", eid, code="ambiguous")
    day.decide(eid, day.escalate(r, eid, 300, reason="ambiguous", group="payments-ops"), 400, "reject", by="ops")

    r, eid = day.request("sla", 250)                                  # unanswered past the SLA, moves up the chain
    day.propose(r, eid)
    day.escalate(r, eid, 500, group="controller")
    e = day.escalate(r, eid, 600, group="finance-manager", breach=True, level=1)
    day.decide(eid, e, 700, by="fm")

    r, eid = day.request("repair", 100)                               # refused stale, a person accepts a repair
    day.propose(r, eid)
    j.append("REFUSED", eid, code="stale_premise", reason=["refunded elsewhere since decision"], repairs=[REMAINING])
    e = day.escalate(r, eid, 800, reason="stale_premise", repairs=[REMAINING])
    child = dict(r, id="repair:repair:abcd1234", amount=70, repair_of="repair")
    day.decide(eid, e, 850, "repair", repair={"code": "refund_remaining", "set": {"amount": 70},
                                               "request_id": child["id"]})
    assert day.gate.submit(day.proposal(child, POLICY)) == "COMMITTED"

    r, eid = day.request("rejected", 30, flagged=True)                # a person rejects
    day.propose(r, eid)
    day.decide(eid, day.escalate(r, eid, 900), 910, "reject")

    day.gate.submit({"agent": "coder", "lease": POLICY, "request_id": "not-ours", "premises": day.api.capture("routine"),
                     "effect": {"order": "routine", "amount": 1}})    # another agent's chain is not counted
    return day


class Scoreboard(unittest.TestCase):
    def test_scoreboard_counts_a_scripted_journal(self):
        self.assertEqual(scoreboard(scripted().j), {
            "requests": 7, "cleared_no_person": 1, "cleared_verified": 1, "no_person_share": 0.143,
            "sent_after_person": 1, "rejected": 2, "closed_by_repair": 1, "open": 1, "escalated": 6,
            "escalated_by_reason": {"needs_judgment": 4, "stale_premise": 2, "ambiguous": 1},
            "stale_approvals_caught": 1, "crash_to_person": 1, "repairs_suggested": 2, "repairs_accepted": 1,
            "sla_breaches": 1, "confirmed_by_target": 1,
            "time_to_decision": {"n": 6, "median": 40, "p90": 200, "max": 200}})

    def test_cleared_verified_counts_only_valid_receipts(self):
        day = Day()
        for rid in ("a", "b", "c"):
            r, _ = day.request(rid)
            day.gate.submit(day.proposal(r, POLICY))
        tampered = effect_id_for({"request_id": "b"})
        with open(day.j.path) as f:
            lines = [json.loads(line) for line in f]
        for e in lines:
            if e["effect_id"] == tampered and e["kind"] == "DISPATCHED":
                e["effect"]["amount"] = 99                            # edited after the fact: the hash no longer matches
        with open(day.j.path, "w") as f:
            f.writelines(json.dumps(e) + "\n" for e in lines)
        s = scoreboard(day.j)
        self.assertEqual((s["cleared_no_person"], s["cleared_verified"]), (3, 2))

    def test_time_to_decision_uses_at_not_ts(self):
        day = Day(".db")
        r, eid = day.request("x", 80)
        day.propose(r, eid)
        e = day.escalate(r, eid, 1000)
        day.decide(eid, e, 1005)
        day.escalate(r, eid, 5000, reason="stale_premise")            # clock time, far from the wall clock in ts
        e = day.escalate(r, eid, 5100, group="finance-manager", breach=True, level=1)
        day.decide(eid, e, 5300, by="fm")
        self.assertEqual(scoreboard(day.j)["time_to_decision"], {"n": 2, "median": 152.5, "p90": 300, "max": 300})

    def test_empty_and_pre_feature_journals(self):
        empty = scoreboard(open_journal(tempfile.mktemp(suffix=".jsonl")))
        self.assertEqual((empty["requests"], empty["no_person_share"], empty["escalated_by_reason"]), (0, 0, {}))
        self.assertEqual(empty["time_to_decision"], {"n": 0, "median": None, "p90": None, "max": None})
        self.assertTrue(all(v == 0 for k, v in empty.items() if k not in ("escalated_by_reason", "time_to_decision")))

        day = Day()
        r, _ = day.request("old")
        p = day.proposal(r, POLICY)
        del p["request"]                                              # written before PROPOSED carried the request
        day.gate.submit(p)
        s = scoreboard(day.j)
        self.assertEqual((s["requests"], s["cleared_no_person"], s["cleared_verified"]), (1, 1, 1))


@unittest.skipUnless(hasattr(approvals, "Route") and hasattr(Payments, "explain"),
                     "phase B: needs the routed inbox (L2) and Payments.explain (L1)")
class SyntheticDay(unittest.TestCase):
    def test_synthetic_day_scoreboard_is_consistent(self):
        sys.path.insert(0, os.path.join(ROOT, "experiments"))
        import approval_inbox as x
        reqs = x.day()
        result = x.with_gate(reqs)
        s = result["scoreboard"]
        self.assertEqual(result["wrong_orders"], [])
        self.assertEqual(s["repairs_accepted"], x.PARTIAL_BY_HAND)
        self.assertEqual(s["requests"], len({r["id"] for r in reqs}))
        self.assertGreater(s["sla_breaches"], 0)


if __name__ == "__main__":
    unittest.main()
