"""Recovery ownership and file locks must hold across calls, threads and processes."""
import concurrent.futures
import multiprocessing
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from interlock import Gate, Leases, SimulatedCrash, open_journal
from interlock.targets import Payments


def _dispatch_process(path, ready, start, results):
    """Top-level target so this regression also runs with Windows spawn."""
    try:
        journal = open_journal(path)
        ready.put(True)
        if not start.wait(10):
            raise TimeoutError("workers were not started")
        results.put(("ok", journal.dispatch("effect", {"amount": 20}, str(os.getpid()))))
    except Exception as exc:
        results.put(("error", repr(exc)))


class BlockingPayments(Payments):
    def __init__(self):
        super().__init__(2)
        self.entered = threading.Event()
        self.finish = threading.Event()

    def apply(self, eid, effect, crash_after_effect=False):
        if not self.entered.is_set():
            self.entered.set()
            if not self.finish.wait(10):
                raise TimeoutError("test did not release the first send")
        return super().apply(eid, effect, crash_after_effect)


class RecoveryLocking(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def world(self, suffix, target=None):
        api = target or Payments(2)
        api.create_order("order", 100)
        leases = Leases()
        leases.grant("L")
        gate = Gate(api, os.path.join(self.temp.name, "journal" + suffix), leases)
        proposal = dict(agent="bot", lease="L", request_id="request",
                        premises=api.capture("order"), effect=dict(order="order", amount=20))
        with self.assertRaises(SimulatedCrash):
            gate.submit(proposal, crash_before_effect=True)
        return gate, api

    def test_concurrent_recovery_on_same_gate_has_one_sender(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                gate, api = self.world(suffix, BlockingPayments())
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    running = pool.submit(gate.recover)
                    try:
                        self.assertTrue(api.entered.wait(5))
                        self.assertEqual(gate.recover(), {})
                    finally:
                        api.finish.set()
                    self.assertEqual(list(running.result(timeout=5).values()), ["REAPPLIED_AFTER_QUERY"])
                self.assertEqual(api.refunded_total("order"), 20)
                self.assertEqual(sum(e["kind"] == "COMMITTED" for e in gate.journal.entries()), 1)

    def test_same_gate_waits_out_a_timed_out_recovery(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                gate, api = self.world(suffix)
                with patch.object(api, "apply", side_effect=TimeoutError("send may still be processing")):
                    self.assertEqual(list(gate.recover().values()), ["UNRESOLVED:TimeoutError"])
                self.assertEqual(gate.recover(), {})
                self.assertEqual(api.refunds, [])

    def test_slow_lookup_cannot_resend_after_another_recovery_takes_over(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                gate, api = self.world(suffix)
                claim = gate.journal.claim
                calls = []

                def expire_first_claim(eid, owner, ttl):
                    calls.append(owner)
                    return claim(eid, owner, -1 if len(calls) == 1 else ttl)

                def lookup(eid, effect):
                    self.assertTrue(claim(eid, "other-recovery", 120))
                    return False

                with patch.object(gate.journal, "claim", side_effect=expire_first_claim), patch.object(api, "query", side_effect=lookup):
                    self.assertEqual(list(gate.recover().values()), ["IN_FLIGHT"])
                self.assertEqual(api.refunds, [])

    def test_slow_lookup_cannot_resend_after_another_recovery_finishes(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(journal=suffix):
                gate, api = self.world(suffix)
                claim = gate.journal.claim
                calls = []

                def expire_first_claim(eid, owner, ttl):
                    calls.append(owner)
                    return claim(eid, owner, -1 if len(calls) == 1 else ttl)

                def lookup(eid, effect):
                    self.assertTrue(claim(eid, "other-recovery", 120))
                    result = api.apply(eid, effect)
                    gate.journal.append("COMMITTED", eid, result=result)
                    gate.journal.release(eid, "other-recovery")
                    return False  # our lookup read absence before the other worker's send

                with patch.object(gate.journal, "claim", side_effect=expire_first_claim), patch.object(api, "query", side_effect=lookup):
                    self.assertEqual(gate.recover(), {})
                self.assertEqual(api.refunded_total("order"), 20)
                self.assertEqual(sum(e["kind"] == "COMMITTED" for e in gate.journal.entries()), 1)

    def test_jsonl_dispatch_is_exclusive_across_spawned_processes(self):
        path = os.path.join(self.temp.name, "processes.jsonl")
        journal = open_journal(path)
        journal.append("PROPOSED", "effect", effect={"amount": 20})
        ctx = multiprocessing.get_context("spawn")
        ready, results, start = ctx.Queue(), ctx.Queue(), ctx.Event()
        processes = [ctx.Process(target=_dispatch_process, args=(path, ready, start, results)) for _ in range(4)]
        try:
            for process in processes:
                process.start()
            for _ in processes:
                self.assertTrue(ready.get(timeout=10))
            start.set()
            outcomes = [results.get(timeout=10) for _ in processes]
            self.assertEqual(outcomes.count(("ok", None)), 1, outcomes)
            self.assertEqual(outcomes.count(("ok", "in_flight")), 3, outcomes)
            self.assertEqual(sum(e["kind"] == "DISPATCHED" for e in journal.entries()), 1)
        finally:
            start.set()
            for process in processes:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            ready.close()
            results.close()


if __name__ == "__main__":
    unittest.main()
