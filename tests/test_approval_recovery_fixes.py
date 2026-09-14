"""Regressions for approval audit records and retries after a fast restart."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from interlock import Interlock, SimulatedCrash, effect_id_for
from interlock.receipts import verify


class ApprovalRecoveryFixes(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def test_last_allowed_attempt_has_a_valid_receipt(self):
        for limit in (1, 2):
            with self.subTest(attempts=limit):
                gate = Interlock(os.path.join(self.directory.name, str(limit)))

                @gate.effect(key=lambda amount: "request", attempts=limit,
                             approval=lambda amount: {"id": "approval", "max": {"amount": 20}})
                def send(amount):
                    return amount

                if limit == 2:
                    self.assertEqual(send(30)[0], "REFUSED:lease")
                self.assertEqual(send(10), ("COMMITTED", 10))
                receipt = verify(send.gate.receipt_bundle(send.proposal(10)))
                self.assertTrue(receipt["valid"], receipt["problems"])
                self.assertTrue(receipt["authorized_when_fired"])
                self.assertFalse(send.gate.leases.is_live({"id": "approval"}))

    def test_last_allowed_attempt_remains_valid_during_recovery(self):
        gate = Interlock(self.directory.name)

        @gate.effect(key=lambda amount: "request", dedupes=True, attempts=1,
                     approval=lambda amount: {"id": "approval", "max": {"amount": 20}})
        def send(amount, idempotency_key):
            return amount

        proposal = send.proposal(10)
        with self.assertRaises(SimulatedCrash):
            send.gate.submit(proposal, crash_before_effect=True)
        self.assertEqual(send(10), ("COMMITTED_BY_RETRY", 10))
        receipt = verify(send.gate.receipt_bundle(proposal))
        self.assertTrue(receipt["valid"], receipt["problems"])

    def test_nonfinite_amounts_never_reach_the_function(self):
        sent = []
        gate = Interlock(self.directory.name)

        @gate.effect(key=lambda amount: "request",
                     approval=lambda amount: {"id": "approval", "max": {"amount": 20}})
        def send(amount):
            sent.append(amount)

        for value in (float("nan"), float("inf"), float("-inf"), True):
            with self.subTest(value=value):
                self.assertEqual(send(value)[0], "REFUSED:lease")
        self.assertEqual(sent, [])

    def test_invalid_maximum_fails_closed(self):
        sent = []
        maximum = [20]
        gate = Interlock(self.directory.name)

        @gate.effect(key=lambda amount: "request",
                     approval=lambda amount: {"id": "approval", "max": {"amount": maximum[0]}})
        def send(amount):
            sent.append(amount)

        for value in (float("nan"), float("inf"), float("-inf"), True, "20", None):
            with self.subTest(maximum=value):
                maximum[0] = value
                self.assertEqual(send(10)[0], "REFUSED:lease")
        self.assertEqual(sent, [])

    def test_retry_recovers_after_startup_skipped_a_live_claim(self):
        sent = []

        def install():
            gate = Interlock(self.directory.name, claim_ttl=60)

            @gate.effect(key=lambda request: request,
                         lookup=lambda request, idempotency_key: idempotency_key in sent)
            def send(request, idempotency_key):
                sent.append(idempotency_key)
                raise TimeoutError("response lost")

            return gate, send

        _, send = install()
        with self.assertRaises(TimeoutError):
            send("request")
        restarted, retry = install()
        self.assertEqual(list(restarted.recover().values()), [{}])
        self.assertEqual(retry("request"), ("IN_FLIGHT", None))
        with patch("interlock.journal.time.time", return_value=time.time() + 61):
            self.assertEqual(retry("request"), ("COMMITTED_ON_QUERY", None))
        self.assertEqual(len(sent), 1)
        self.assertEqual(retry.gate.journal.in_flight(), [])

    def test_retry_rechecks_original_facts_without_requesting_new_approval(self):
        facts = {"version": 1}
        approval_reads = []
        sent = []

        def approval(amount):
            approval_reads.append(amount)
            if len(approval_reads) > 1:
                raise AssertionError("recovery must use the recorded approval")
            return {"id": "approval", "max": {"amount": 20}}

        gate = Interlock(self.directory.name)

        @gate.effect(key=lambda amount: "request", approval=approval,
                     premises=lambda amount: dict(facts), lookup=lambda amount: False)
        def send(amount):
            sent.append(amount)

        proposal = send.proposal(10)
        with self.assertRaises(SimulatedCrash):
            send.gate.submit(proposal, crash_before_effect=True)
        facts["version"] = 2
        self.assertEqual(send(10), ("REFUSED:stale_premise_at_recovery", None))
        self.assertEqual(approval_reads, [10])
        self.assertEqual(sent, [])
        entries = send.gate.journal.entries(effect_id_for(proposal))
        self.assertEqual(sum(e["kind"] == "PROPOSED" for e in entries), 1)

    def test_recovery_refuses_retry_with_a_different_payload(self):
        for crash_after in (False, True):
            with self.subTest(crash_after=crash_after):
                gate = Interlock(os.path.join(self.directory.name, str(crash_after)))
                sent = []

                @gate.effect(key=lambda order, amount: order,
                             lookup=lambda order, amount, idempotency_key: bool(sent))
                def send(order, amount):
                    sent.append(amount)
                    return amount

                proposal = send.proposal("order", 20)
                with self.assertRaises(SimulatedCrash):
                    send.gate.submit(proposal, crash_before_effect=not crash_after,
                                     crash_after_effect=crash_after)
                # This call's recovery settled the recorded $20: it reports that, not "refused, nothing happened".
                self.assertEqual(send("order", 30),
                                 ("COMMITTED_ON_QUERY" if crash_after else "REAPPLIED_AFTER_QUERY", 20))
                self.assertEqual(sent, [20])
                self.assertEqual(send.gate.journal.in_flight(), [])
                entries = send.gate.journal.entries(effect_id_for(proposal))
                self.assertEqual(entries[-1]["code"], "conflicting_payload")
                self.assertEqual(send("order", 20)[0], "DUPLICATE_IGNORED")


if __name__ == "__main__":
    unittest.main()
