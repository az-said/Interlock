"""
Interleaved races on real Postgres, no subprocesses: two connections, one transaction held open while the other runs.

Where a transaction must stay open in the middle of the runtime's own code, the hold is real database work inside
that transaction: a registered SQL premise function that runs pg_sleep after the grant is locked FOR SHARE, or (for
the suspend transaction) a threading.Event wait placed after the fence took the workflow row lock. Blocking is
confirmed from pg_stat_activity (wait_event_type = 'Lock'), not inferred from timing.
"""
import os, sys, tempfile, threading, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "runtime"), ROOT]
DSN = os.environ.get("ILR_DSN")

if DSN:
    import psycopg
    from experiments import runtime_flows as flows
    from experiments.runtime_target import LocalRefunds, spawn_target
    from interlock.journal import effect_id_for
    from interlock_runtime import Worker, invariants
    from interlock_runtime.context import Suspend, WorkflowContext
    from interlock_runtime.db import connect
    from interlock_runtime.effects import append
    from interlock_runtime.runtime import cancel_in, revoke_in, signal_in


@unittest.skipUnless(DSN, "set ILR_DSN (python3 experiments/runtime_pg.py start) to run against real Postgres")
class Races(unittest.TestCase):
    def setUp(self):
        self.rt = flows.reset_db(DSN)
        self.mon = connect(DSN)
        self.mon.execute("create or replace function public.slow_ok(args jsonb, eid text) returns jsonb language sql as "
                         "$$ select '[]'::jsonb from pg_sleep((args->>'s')::float8) $$")
        self.tmp = tempfile.mkdtemp(prefix="ilr-race-")
        self.target_proc, url = spawn_target(1, os.path.join(self.tmp, "ledger.sqlite"))
        self.target = LocalRefunds(url, 1)
        self.grant = self.rt.grant("refund-bot", "refund", max_cents=5000)
        self.rt.register(flows.refund_local)

    def tearDown(self):
        self.target_proc.kill()
        self.target_proc.wait()
        self.mon.close()
        self.rt.conn.close()

    def case(self, key="case-1", amount=2000, **kw):
        return {"url": self.target.url, "tier": 1, "key": key, "amount": amount, "grant": self.grant,
                "premises": self.target.capture(), "send_timeout": 5, "settle_margin": 1, **kw}

    def run_workers(self, n=1):
        def loop():
            w = Worker(self.rt, [flows.refund_local], worker_id=f"t{threading.get_ident()}", lease_ttl=5, poll=0.1)
            end = time.monotonic() + 30
            while time.monotonic() < end and any(r["status"] not in ("completed", "failed", "cancelled", "stuck")
                                                 for r in self.rt.list()):
                w.run(until_idle=True)
                time.sleep(0.05)
            self.assertEqual(w.errors, [])
        threads = [threading.Thread(target=loop) for _ in range(n)]
        for t in threads:
            t.start()
        return threads

    def blocked(self, like):
        # A separate autocommit connection: inside a transaction, pg_stat_activity is a snapshot taken at first read.
        with connect(DSN) as watch:
            return watch.execute("select count(*) as n from pg_stat_activity where wait_event_type = 'Lock' and query like %s",
                                 (like,)).fetchone()["n"]

    def active(self, like):
        with connect(DSN) as watch:
            return watch.execute("select count(*) as n from pg_stat_activity where state = 'active' and query like %s",
                                 (like,)).fetchone()["n"]

    def effect_status(self, wf_id):
        return next(s["output"]["status"] for s in self.rt.describe(wf_id)["steps"] if s["kind"] == "effect")

    def world(self):
        return {"ledger": [{"effect_id": r["effect_id"], "amount": r["amount"]} for r in self.target.ledger()],
                "access_log": [r for r in self.target.log() if r["path"] == "/refunds"], "quiescent": True}

    # ---- revoke vs T_dispatch ----------------------------------------------------------------------
    def test_revoke_waits_for_dispatch_and_returns_the_effect(self):
        self.rt.start("refund_local", "wf", self.case(local=[["public.slow_ok", {"s": 1.5}]]))
        threads = self.run_workers()
        flows.wait_for(lambda: self.active("%slow_ok%"))           # T_dispatch holds the grant FOR SHARE
        out = {}
        revoker = threading.Thread(target=lambda: out.update(ids=self.rt.revoke(self.grant, by="test"), at=time.time()))
        revoker.start()
        flows.wait_for(lambda: self.blocked("update ilr.grants%"), timeout=5)
        revoker.join()
        for t in threads:
            t.join()
        eid = effect_id_for({"request_id": "case-1"})
        self.assertEqual(out["ids"], [eid])                       # the effect that could still land, and did
        self.assertEqual(self.effect_status("wf"), "COMMITTED")
        world = {**self.world(), "revokes": [{"grant_id": self.grant, "returned": out["ids"], "returned_at": out["at"]}]}
        self.assertEqual(invariants.failing(invariants.check(self.rt.conn, world, ["RevokeLinearizable", "NoSendUnderRevokedGrant"])), {})

    def test_dispatch_waits_for_revoke_and_refuses(self):
        self.rt.start("refund_local", "wf", self.case())
        with self.mon.transaction():
            returned = revoke_in(self.mon, self.grant)
            threads = self.run_workers()
            flows.wait_for(lambda: self.blocked("%from ilr.grants where id = % for share%"), timeout=10)
        for t in threads:
            t.join()
        self.assertEqual(returned, [])
        self.assertEqual(self.effect_status("wf"), "REFUSED:lease")
        self.assertEqual(self.target.ledger(), [])

    # ---- cancel vs T_dispatch --------------------------------------------------------------------
    def test_cancel_waits_for_dispatch(self):
        self.rt.start("refund_local", "wf", self.case(local=[["public.slow_ok", {"s": 1.5}]]))
        threads = self.run_workers()
        flows.wait_for(lambda: self.active("%slow_ok%"))
        canceller = threading.Thread(target=self.rt.cancel, args=("wf", "test"))
        canceller.start()
        flows.wait_for(lambda: self.blocked("select 1 from ilr.workflows where id = % for update%"), timeout=5)
        canceller.join()
        for t in threads:
            t.join()
        self.assertEqual(self.effect_status("wf"), "COMMITTED")   # dispatched before the cancel committed
        self.assertEqual(invariants.failing(invariants.check(self.rt.conn, self.world(), ["NoSendAfterCancel"])), {})

    def test_cancel_before_dispatch_refuses(self):
        self.rt.start("refund_local", "wf", self.case(pause=1.0))
        threads = self.run_workers()
        flows.wait_for(lambda: self.rt.describe("wf")["workflow"]["status"] == "running")
        with self.mon.transaction():
            cancel_in(self.mon, "wf")
        for t in threads:
            t.join()
        self.assertEqual(self.effect_status("wf"), "REFUSED:cancelled")
        self.assertEqual(self.target.ledger(), [])
        self.assertEqual(invariants.failing(invariants.check(self.rt.conn, self.world(), ["NoSendAfterCancel"])), {})

    # ---- signal vs the suspend transaction (NoLostWakeup) --------------------------------------------
    def claimed_waiter(self):
        self.rt.register(flows.waiter)
        self.rt.start("waiter", "wf", {"n": 1})
        worker = Worker(self.rt, [flows.waiter], worker_id="race", lease_ttl=10)
        conn = connect(DSN)
        claim = worker.claim(conn, 1)[0]
        return WorkflowContext(worker, conn, claim)

    def paused(self, ctx):
        entered, release, real = threading.Event(), threading.Event(), ctx.txn

        class Hold:
            def __enter__(s):
                s.cm = real()
                r = s.cm.__enter__()                  # the fence ran: this transaction holds the workflow row lock
                entered.set()
                release.wait(10)
                return r

            def __exit__(s, *exc):
                return s.cm.__exit__(*exc)
        ctx.txn = Hold
        return entered, release

    def test_signal_during_suspend_wakes_the_workflow(self):
        ctx = self.claimed_waiter()
        entered, release = self.paused(ctx)
        out = {}

        def wait():
            try:
                out["value"] = ctx.wait_signal("go")
            except Suspend:
                out["value"] = "suspended"
        waiter = threading.Thread(target=wait)
        waiter.start()
        entered.wait(5)
        signaller = threading.Thread(target=self.rt.signal, args=("wf", "go", {"ok": 1}))
        signaller.start()
        flows.wait_for(lambda: self.blocked("select 1 from ilr.workflows where id = % for update%"), timeout=5)
        release.set()
        waiter.join()
        signaller.join()
        self.assertEqual(out["value"], "suspended")                # the mailbox was empty when it looked
        wf = self.rt.describe("wf")["workflow"]
        self.assertEqual(wf["status"], "pending")                  # and the signal woke it after the release committed
        self.assertEqual(invariants.check(self.rt.conn, {}, ["NoLostWakeup"]), {"NoLostWakeup": []})
        ctx.conn.close()
        Worker(self.rt, [flows.waiter], worker_id="after").run(until_idle=True)
        self.assertEqual(self.rt.result("wf", 5)["result"], [{"ok": 1}])

    def test_suspend_after_signal_consumes_it(self):
        ctx = self.claimed_waiter()
        out = {}
        with self.mon.transaction():
            signal_in(self.mon, "wf", "go", {"ok": 2})

            def wait():
                out["value"] = ctx.wait_signal("go")
            waiter = threading.Thread(target=wait)
            waiter.start()
            flows.wait_for(lambda: self.blocked("update ilr.workflows set lease_expires_at%"), timeout=5)
        waiter.join()
        self.assertEqual(out["value"], {"ok": 2})
        self.assertEqual(invariants.failing(invariants.check(self.rt.conn, {}, ["SignalExactlyOnceConsumed", "NoLostWakeup"])), {})
        ctx.conn.close()

    # ---- concurrent submits, chains, commits -----------------------------------------------------
    def test_concurrent_submit_with_different_payloads(self):
        slow = [["public.slow_ok", {"s": 0.5}]]
        self.rt.start("refund_local", "a", self.case(amount=2000, local=slow))
        self.rt.start("refund_local", "b", self.case(amount=3000, local=slow))
        for t in self.run_workers(2):
            t.join()
        statuses = sorted([self.effect_status("a"), self.effect_status("b")])
        self.assertEqual(statuses, ["COMMITTED", "REFUSED:conflicting_payload"])
        self.assertEqual(len(self.target.ledger()), 1)
        self.assertEqual(invariants.failing(invariants.check(
            self.rt.conn, self.world(), ["PayloadBound", "AtMostOneCommit", "EffectAtMostOnceTier12", "ReceiptChainLinear"])), {})

    def seed_effect(self, eid="e1"):
        self.rt.start("refund_local", "wf", self.case())
        self.rt.conn.execute("insert into ilr.effects (effect_id, workflow_id, target, tier, payload, payload_hash) "
                             "values (%s, 'wf', 't', 1, '{\"amount\": 1}', 'h')", (eid,))
        append(self.rt.conn, "PROPOSED", eid, effect={"amount": 1})
        return eid

    def test_forked_chain_is_rejected(self):
        eid = self.seed_effect()
        a, b = connect(DSN), connect(DSN)
        errors = []
        with a.transaction():
            append(a, "AUTHORIZED", eid, lease="g")            # reads head, inserts, not yet committed

            def fork():
                try:
                    with b.transaction():
                        append(b, "AUTHORIZED", eid, lease="other")   # same head: blocks on the unique (effect_id, prev)
                except psycopg.errors.UniqueViolation as e:
                    errors.append(e)
            t = threading.Thread(target=fork)
            t.start()
            flows.wait_for(lambda: self.blocked("insert into ilr.journal%"), timeout=5)
        t.join()
        self.assertEqual(len(errors), 1)
        self.assertEqual([e["kind"] for e in self.rt.receipt(eid)["entries"]], ["PROPOSED", "AUTHORIZED"])
        a.close()
        b.close()

    def test_second_commit_and_mutations_are_rejected(self):
        eid = self.seed_effect()
        append(self.rt.conn, "COMMITTED", eid, result={"n": 1})
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.rt.conn.transaction():
                append(self.rt.conn, "COMMITTED", eid, result={"n": 2})
        with self.assertRaises(psycopg.errors.RaiseException):
            self.rt.conn.execute("update ilr.journal set body = body where effect_id = %s", (eid,))
        with self.assertRaises(psycopg.errors.RaiseException):
            self.rt.conn.execute("update ilr.effects set payload_hash = 'other' where effect_id = %s", (eid,))
        self.rt.conn.execute("update ilr.effects set state = 'committed' where effect_id = %s", (eid,))
        with self.assertRaises(psycopg.errors.RaiseException):
            self.rt.conn.execute("update ilr.effects set state = 'dispatched' where effect_id = %s", (eid,))


if __name__ == "__main__":
    unittest.main()
