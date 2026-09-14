"""
Differential test: interlock.Gate against interlock_runtime, fault by fault, tier by tier.

NOT LIVE on the Gate side: interlock.Gate is the reference implementation and runs in-process with its file journal,
crashing by its own SimulatedCrash. The runtime side is live: a real worker subprocess SIGKILLed at an instrumented
kill point (effect_after_dispatch or effect_after_send), real Postgres, a real HTTP target process.

For each fault from experiments/refund_agent.py, both systems get the same pre-recovery state (one target process
each, same tier, same premises, one shared grant in ilr.grants read by both), the same world events, and then recover.
Asserted equal: every result status, every verify() field, the journal summary, and the target ledgers. verify()
output carries no ts or hashes. The runtime side is also checked against the code invariants.
"""
import os, signal, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "runtime"), ROOT]
DSN = os.environ.get("ILR_DSN")

if DSN:
    from experiments import runtime_flows as flows
    from experiments.runtime_target import LocalRefunds, spawn_target
    from interlock import Gate, SimulatedCrash
    from interlock.gate import DEDUP_MARGIN
    from interlock.journal import _seal, effect_id_for
    from interlock.receipts import verify
    from interlock_runtime import Worker, invariants
    from interlock_runtime.db import connect
    from interlock_runtime.effects import grant_checks

CRASH = {"crash_before_send": "effect_after_dispatch", "crash_before_ack": "effect_after_send",
         "refund_during_outage": "effect_after_dispatch", "lease_revoked_during_outage": "effect_after_dispatch",
         "key_expired": "effect_after_send", "model_redecides": "effect_after_send"}
CHECKED = ["AtMostOneCommit", "EffectAtMostOnceTier12", "Tier3NeverResends", "NoOverlappingSends", "CommittedImpliesApplied",
           "AmbiguousOnlyWhenUnknowable", "EffectCheckpointAtomic", "SendRequiresLiveClaim", "NoSendUnderRevokedGrant",
           "NoSendOnStalePremise", "RecoveryRechecks", "PayloadBound", "ReceiptChainLinear", "ReceiptTruthful",
           "FencedWrites", "TakeoverOnlyAfterExpiry"]


class PgGrants:
    """The lease store interlock.Gate reads: the same ilr.grants rows and snapshot the runtime records."""
    def __init__(self, dsn):
        self.conn = connect(dsn)

    def allows(self, lease, effect):
        return grant_checks(self.conn, lease, "refund", effect)["lease_live"]

    def describe(self, lease):
        return grant_checks(self.conn, lease, "refund", {})["lease"]

    def is_live(self, lease):
        return self.describe(lease) is not None


@unittest.skipUnless(DSN, "set ILR_DSN (python3 experiments/runtime_pg.py start) to run against real Postgres")
class GateParity(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.cleanup = []

    def tearDown(self):
        for fn in reversed(self.cleanup):
            fn()

    def proc(self, p):
        self.cleanup.append(lambda: (p.kill(), p.wait()))
        return p

    def settle(self, rt, wf_id):
        """Run the runtime until the workflow ends: an in-process worker (no crash happens on this path)."""
        w = Worker(rt, [flows.refund_local], worker_id="recoverer", lease_ttl=1, poll=0.1)
        end = time.monotonic() + 40
        while rt.describe(wf_id)["workflow"]["status"] not in ("completed", "failed", "stuck"):
            self.assertLess(time.monotonic(), end, rt.describe(wf_id))
            w.run(until_idle=True)
            time.sleep(0.1)
        self.assertEqual(w.errors, [])
        return next(s["output"]["status"] for s in rt.describe(wf_id)["steps"] if s["kind"] == "effect")

    def run_case(self, tier, fault):
        tmp = tempfile.mkdtemp(prefix=f"ilr-parity-{fault}-{tier}-")
        rt = flows.reset_db(DSN)
        self.cleanup.append(rt.conn.close)
        rt.register(flows.refund_local)
        key = f"{fault}-{tier}"
        eid = effect_id_for({"request_id": key})
        grant = rt.grant("refund-bot", "refund", max_cents=5000)
        opts = {"send_timeout": 1.5, "settle_margin": 0.5, "dedup_window": DEDUP_MARGIN + 3}
        targets = []
        for name in ("gate", "runtime"):
            p, url = spawn_target(tier, os.path.join(tmp, f"{name}.sqlite"))
            self.proc(p)
            targets.append(LocalRefunds(url, tier, **opts))
        gt, rtt = targets
        grants = PgGrants(DSN)
        self.cleanup.append(grants.conn.close)
        gate = Gate(gt, os.path.join(tmp, "journal.jsonl"), grants)
        premises = gt.capture()
        self.assertEqual(premises, rtt.capture())

        def proposal(amount=2000):
            return {"agent": "refund_local", "lease": grant, "request_id": key, "premises": premises, "effect": {"amount": amount}}

        def case(amount=2000):
            return {"url": rtt.url, "tier": tier, **opts, "key": key, "amount": amount, "grant": grant, "premises": premises}

        if fault == "lease_revoked":
            rt.revoke(grant, by="test")
        if fault == "stale_eligibility":
            gt.set_eligible(False)
            rtt.set_eligible(False)

        g, r = [], []
        crash = CRASH.get(fault)
        rt.start("refund_local", "wf1", case())
        if crash:
            try:
                gate.submit(proposal(), crash_before_effect=crash == "effect_after_dispatch",
                            crash_after_effect=crash == "effect_after_send")
                self.fail("the gate reference did not crash")
            except SimulatedCrash:
                pass
            w = self.proc(flows.spawn_worker("crasher", tmp, lease_ttl=1, poll=0.1, env={"ILR_KILL_AT": crash}))
            self.assertEqual(w.wait(timeout=30), -signal.SIGKILL)       # instrumented SIGKILL
            sends = [x for x in rtt.log() if (x["method"], x["path"]) == ("POST", "/refunds")]
            # Killed before the send means no request, killed after it means exactly one. This caught kill() to self
            # returning before the process died.
            self.assertEqual(len(sends), 0 if crash == "effect_after_dispatch" else 1, sends)
            if fault == "refund_during_outage":
                gt.hand_refund(2000)
                rtt.hand_refund(2000)
            if fault == "lease_revoked_during_outage":
                self.assertEqual(rt.revoke(grant, by="test"), [eid])     # the dispatched effect may still land
            if fault == "key_expired":
                gt.prune_keys()                                          # EMULATED key expiry, on both targets
                rtt.prune_keys()
                time.sleep(3.2)                                          # real age past dedup_window - DEDUP_MARGIN
            g.append(gate.recover()[eid])
        else:
            g.append(gate.submit(proposal()))
        r.append(self.settle(rt, "wf1"))

        if fault in ("duplicate_submit", "conflicting_payload", "model_redecides"):
            amount = 2000 if fault == "duplicate_submit" else 3000
            g.append(gate.submit(proposal(amount)))
            rt.start("refund_local", "wf2", case(amount))
            r.append(self.settle(rt, "wf2"))

        self.assertEqual(r, g, "result statuses")
        gb, rb = gate.receipt_bundle(proposal()), rt.receipt(eid)
        self.assertEqual(verify(rb), verify(gb), "verify() output")
        self.assertEqual(rb["summary"], gb["summary"], "journal summary")
        strip = lambda rows: [(x["id"], x["amount"], x["source"], x["effect_id"]) for x in rows if x["source"] == "agent"]
        self.assertEqual(strip(rtt.ledger()), strip(gt.ledger()), "target ledgers")

        world = {"ledger": rtt.ledger(), "access_log": [x for x in rtt.log() if x["path"] == "/refunds"], "quiescent": True}
        self.assertEqual(invariants.failing(invariants.check(rt.conn, world, CHECKED)), {})
        return g, verify(rb)

    def each_tier(self, fault, tiers=(1, 2, 3)):
        for tier in tiers:
            with self.subTest(tier=tier):
                self.run_case(tier, fault)

    def test_happy_path(self):
        self.each_tier("happy_path")

    def test_crash_before_send(self):
        self.each_tier("crash_before_send")

    def test_crash_before_ack(self):
        self.each_tier("crash_before_ack")

    def test_duplicate_submit(self):
        self.each_tier("duplicate_submit")

    def test_model_redecides(self):
        self.each_tier("model_redecides")

    def test_conflicting_payload(self):
        self.each_tier("conflicting_payload")

    def test_lease_revoked(self):
        self.each_tier("lease_revoked")

    def test_stale_eligibility(self):
        self.each_tier("stale_eligibility")

    def test_refund_during_outage(self):
        self.each_tier("refund_during_outage")

    def test_lease_revoked_during_outage(self):
        self.each_tier("lease_revoked_during_outage")

    def test_key_expired(self):
        self.each_tier("key_expired", tiers=(1,))

    def test_verify_reads_the_runtime_snapshot_shape(self):
        """A DISPATCHED whose recorded grant snapshot has `revoked` set must verify as not authorized."""
        _, v = self.run_case(1, "happy_path")
        self.assertIs(v["authorized_when_fired"], True)
        rt = flows.Runtime(DSN)
        self.cleanup.append(rt.conn.close)
        eid = effect_id_for({"request_id": "happy_path-1"})
        entries, resealed, prev = rt.receipt(eid)["entries"], [], None
        for e in entries:
            e = {k: v for k, v in e.items() if k not in ("hash", "prev")}
            if e["kind"] == "DISPATCHED":
                e["checks"]["lease"]["revoked"] = "2026-09-13T00:00:00+00:00"
            prev = _seal(e, prev)
            resealed.append(prev)
        out = verify({"effect_id": eid, "entries": resealed})
        self.assertTrue(out["tamper_evident"])
        self.assertIs(out["authorized_when_fired"], False)


if __name__ == "__main__":
    unittest.main()
