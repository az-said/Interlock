"""Regressions for the lock-in review of the recovery, approval, export and repository fixes."""
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from interlock import Gate, Interlock, Leases, SimulatedCrash, effect_id_for, open_journal
from interlock.approvals import Envelope
from interlock.export import _common
from interlock.targets import Payments, repo
from interlock.tools import protect


class LockinReviewFixes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = self.temp.name

    def test_slow_lookup_does_not_resend_what_a_later_recovery_sent(self):
        """1 and 7: our claim and then another recoverer's claim expire during our lookup."""
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                api = Payments(2)
                api.create_order("order", 100)
                leases = Leases()
                leases.grant("L")
                gate = Gate(api, os.path.join(self.dir, "slow" + suffix), leases)
                p = dict(agent="bot", lease="L", request_id="req", premises=api.capture("order"),
                         effect=dict(order="order", amount=20))
                with self.assertRaises(SimulatedCrash):
                    gate.submit(p, crash_before_effect=True)
                claim, real_query, calls = gate.journal.claim, api.query, []

                def expire_first_claim(eid, owner, ttl):
                    calls.append(owner)
                    return claim(eid, owner, -1 if len(calls) == 1 else ttl)

                def query(eid, effect):
                    if len(calls) > 1:
                        return real_query(eid, effect)
                    absent = real_query(eid, effect)                 # read before the other recoverer's send
                    self.assertTrue(claim(eid, "other-recovery", -1))  # it takes over; its claim later expires
                    api.apply(eid, effect)                          # its send lands, the response is lost
                    return absent

                with mock.patch.object(gate.journal, "claim", side_effect=expire_first_claim), \
                        mock.patch.object(api, "query", side_effect=query):
                    self.assertEqual(list(gate.recover().values()), ["COMMITTED_ON_QUERY"])
                self.assertEqual([r["amount"] for r in api.refunds], [20])

    def test_different_payload_reports_what_recovery_did(self):
        """2: tier 2 resend, and tier 3 AMBIGUOUS, are reported by the call that caused them."""
        gate, sent = Interlock(os.path.join(self.dir, "t2")), []

        @gate.effect(key=lambda order, amount: order, lookup=lambda order, amount, idempotency_key: bool(sent))
        def refund(order, amount):
            sent.append(amount)
            return {"amount": amount}

        p = refund.proposal("A", 20)
        with self.assertRaises(SimulatedCrash):
            refund.gate.submit(p, crash_before_effect=True)
        self.assertEqual(refund("A", 30), ("REAPPLIED_AFTER_QUERY", {"amount": 20}))
        self.assertEqual(sent, [20])
        self.assertEqual(refund.gate.journal.entries(effect_id_for(p))[-1]["code"], "conflicting_payload")

        gate3 = Interlock(os.path.join(self.dir, "t3"))

        @gate3.effect(key=lambda order, amount: order)
        def refund3(order, amount):
            return amount

        p = refund3.proposal("A", 20)
        with self.assertRaises(SimulatedCrash):
            refund3.gate.submit(p, crash_after_effect=True)
        self.assertEqual(refund3("A", 30)[0], "AMBIGUOUS")

    def test_call_reports_an_effect_another_worker_committed_meanwhile(self):
        """3: recovery finds nothing to do because the other worker committed; the status comes from the journal."""
        gate = Interlock(self.dir)

        @gate.effect(key=lambda order: order)
        def send(order):
            return "sent"

        p = send.proposal("A")
        eid = effect_id_for(p)
        journal = send.gate.journal
        journal.append("PROPOSED", eid, agent="other", lease=p["lease"], premises=p["premises"], effect=p["effect"])
        self.assertIsNone(journal.dispatch(eid, p["effect"], "other-worker", 120, lease=p["lease"], premises=p["premises"]))
        real_recover = send.gate.recover

        def commit_then_recover(**kw):
            journal.append("COMMITTED", eid, result={"status": "ok"})
            journal.release(eid, "other-worker")
            return real_recover(**kw)

        with mock.patch.object(send.gate, "recover", side_effect=commit_then_recover):
            self.assertEqual(send("A")[0], "DUPLICATE_IGNORED")

    def test_backends_agree_a_claim_is_expired_at_its_expiry_instant(self):
        """4"""
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                j = open_journal(os.path.join(self.dir, "boundary" + suffix))
                with mock.patch("interlock.journal.time.time", return_value=1000.0):
                    self.assertIsNone(j.dispatch("e", {"a": 1}, "sender", ttl=0))
                    self.assertTrue(j.claim("e", "recover", 120))

    def test_lookup_error_while_settling_a_rejected_send_never_resends(self):
        """5"""
        sent, lookups = [], []

        def refund(**kw):
            sent.append(kw)
            if len(sent) == 1:
                return {"isError": True, "content": [{"type": "text", "text": "card_declined"}]}
            return {"ok": True}

        def find_refund(**kw):
            lookups.append(kw)
            return {"isError": True, "content": []} if len(lookups) == 1 else {"found": False}

        tools = protect({"refund": refund, "find_refund": find_refund},
                        {"journal_dir": self.dir, "claim_ttl": 0, "tools": {"refund": {
                            "key": ["order"],
                            "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"}}}})
        self.assertEqual(tools["refund"](order="A")["status"], "REFUSED:target_error")
        self.assertEqual(tools.recover(), {"interlock.tools.refund": {}})
        self.assertEqual(len(sent), 1)

    def test_nan_expiry_never_approves(self):
        """6"""
        env = Envelope(os.path.join(self.dir, "a.db"), clock=lambda: 1000.0)
        for expires in (float("nan"), json.loads('{"e": NaN}')["e"], float("inf")):
            with self.subTest(expires=expires):                             # inf is not finite either
                self.assertTrue(env.problems({"id": "case-1", "max": {"amount": 20}, "expires": expires}, {"amount": 10}))
        self.assertEqual(env.problems({"id": "case-1", "max": {"amount": 20}, "expires": 2000}, {"amount": 10}), [])

    def test_match_does_not_equate_bool_and_int(self):
        """8"""
        env = Envelope(os.path.join(self.dir, "m.db"))
        self.assertTrue(env.problems({"id": "c", "match": {"quantity": 1}}, {"quantity": True}))
        self.assertTrue(env.problems({"id": "c", "match": {"quantity": False}}, {"quantity": 0}))
        self.assertEqual(env.problems({"id": "c", "match": {"quantity": 1, "gift": True}}, {"quantity": 1, "gift": True}), [])

    def test_unresolved_send_is_attributed_to_its_dispatcher_not_a_later_refused_proposer(self):
        """9"""
        class Tier3:
            tier = 3

            def validate_premises(self, premises, eid=None):
                return []

            def apply(self, eid, effect, crash_after_effect=False):
                raise SimulatedCrash(eid)

        leases = Leases()
        leases.grant("alice-approval")
        leases.grant("mallory-lease")
        path = os.path.join(self.dir, "j.jsonl")
        g = Gate(Tier3(), path, leases, claim_ttl=0)
        a = dict(agent="agent-A", lease="alice-approval", request_id="refund-881", premises={}, effect={"amount": 20})
        with self.assertRaises(SimulatedCrash):
            g.submit(a)
        self.assertEqual(list(Gate(Tier3(), path, leases, claim_ttl=0).recover().values()), ["AMBIGUOUS"])
        b = dict(agent="agent-B", lease="mallory-lease", request_id="refund-881", premises={}, effect={"amount": 999})
        self.assertEqual(g.submit(b), "REFUSED:conflicting_payload")
        self.assertEqual(_common.who(g.journal.entries(effect_id_for(a))), ("agent-A", "alice-approval"))

    def test_reapproved_repo_retry_runs_after_a_refusal_proved_nothing_landed(self):
        """10"""
        root = os.path.join(self.dir, "repo")
        os.makedirs(root)

        def write(name, text):
            with open(os.path.join(root, name), "w") as f:
                f.write(text)

        write("a.txt", "v1\n")
        write("read.txt", "facts\n")
        leases = Leases()
        leases.grant("L1")
        journal = os.path.join(self.dir, "gate.jsonl")
        gate = lambda: Gate(repo.LocalRepo(root), journal, leases, claim_ttl=0)
        t = repo.LocalRepo(root)
        p1 = dict(agent="A", lease="L1", request_id="r", effect={"appends": {"a.txt": "x\n"}},
                  premises=t.capture(["read.txt"], [], mode="file"))
        with mock.patch.object(repo, "_write", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                gate().submit(p1)
        leases.revoke("L1")
        self.assertEqual(list(gate().recover().values()), ["REFUSED:lease_at_recovery"])
        write("a.txt", "v2\n")
        leases.grant("L2")
        p2 = dict(p1, lease="L2", premises=t.capture(["read.txt"], [], mode="file"))
        self.assertEqual(gate().submit(p2), "COMMITTED")
        with open(os.path.join(root, "a.txt")) as f:
            self.assertEqual(f.read(), "v2\nx\n")

    @unittest.skipIf(os.name == "nt", "POSIX modes and symlinks")
    def test_repo_write_honors_umask_and_writes_through_symlinks(self):
        """11"""
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        os.makedirs(os.path.join(self.dir, "shared"))
        with open(os.path.join(self.dir, "shared", "real.py"), "w") as f:
            f.write("x = 1\n")
        os.symlink(os.path.join("shared", "real.py"), os.path.join(self.dir, "link.py"))
        repo.LocalRepo(self.dir).apply("e1", {"writes": {"new.py": "def f(): pass\n"}, "appends": {"link.py": "y = 2\n"}})
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.dir, "new.py")).st_mode), 0o644)
        self.assertTrue(os.path.islink(os.path.join(self.dir, "link.py")))
        with open(os.path.join(self.dir, "shared", "real.py")) as f:
            self.assertEqual(f.read(), "x = 1\ny = 2\n")


if __name__ == "__main__":
    unittest.main()
