"""
interlock_runtime against real Postgres and real worker subprocesses.

    python3 experiments/runtime_pg.py start
    ILR_DSN=postgresql://localhost:55432/ilr uv run --no-project --with 'psycopg[binary]' python -m unittest tests.test_runtime -v

Crashes are real SIGKILLs (external, or instrumented via ILR_KILL_AT) and real SIGSTOPs. The Postgres crash is
`pg_ctl stop -m immediate`. Tests that run a Worker in-process do so only where no crash is involved.
"""
import os, signal, subprocess, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "runtime"), ROOT]
DSN = os.environ.get("ILR_DSN")

if DSN:
    from experiments import runtime_flows as flows
    from interlock_runtime import Runtime, Worker, workflow, invariants
else:                                             # decorators below still need to exist
    def workflow(name, version):
        return lambda fn: fn


@unittest.skipUnless(DSN, "set ILR_DSN (python3 experiments/runtime_pg.py start) to run against real Postgres")
class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.rt = flows.reset_db(DSN)
        self.procs, self.tmp = [], tempfile.mkdtemp(prefix="ilr-test-")

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.send_signal(signal.SIGCONT)
                p.kill()
                p.wait()
        self.rt.conn.close()

    def worker(self, wid, **kw):
        p = flows.spawn_worker(wid, self.tmp, **kw)
        self.procs.append(p)
        return p

    def drain(self, fns, **kw):
        w = Worker(self.rt, fns, worker_id=kw.pop("worker_id", "inproc"), lease_ttl=kw.pop("lease_ttl", 5), poll=0.1, **kw)
        w.run(until_idle=True)
        self.assertEqual(w.errors, [])
        return w

    def invoked(self, wf_id, name):
        return sum(1 for i in flows.invocations(DSN) if (i["workflow_id"], i["name"]) == (wf_id, name))

    def status(self, wf_id):
        return self.rt.describe(wf_id)["workflow"]["status"]

    def assertInvariants(self, names, world=None):
        world = {"invocations": flows.invocations(DSN), **(world or {})}
        results = invariants.check(self.rt.conn, world, names)
        for name, violations in results.items():
            self.assertIsNotNone(violations, f"{name} was not checked")
            self.assertEqual(violations, [], name)


class FirstGate(RuntimeCase):
    def test_takeover_and_zombie_fence(self):
        rt = self.rt
        rt.register(flows.three_steps)

        # 1. SIGKILL the claim holder mid-step. The other worker may claim only after lease_expires_at.
        rt.start("three_steps", "wf-a", {"step_seconds": 1.5})
        w = {"w1": self.worker("w1"), "w2": self.worker("w2")}
        flows.wait_for(lambda: self.invoked("wf-a", "two"))
        owner = rt.describe("wf-a")["workflow"]["owner"]
        w[owner].kill()
        self.assertEqual(rt.result("wf-a", timeout=30)["status"], "completed")
        takeovers = [c for c in rt.describe("wf-a")["claims"] if c["prev_status"] == "running"]
        self.assertEqual(len(takeovers), 1)
        self.assertNotEqual(takeovers[0]["owner"], owner)
        self.assertGreaterEqual(takeovers[0]["claimed_at"], takeovers[0]["prev_lease_expires_at"])

        # 2. SIGSTOP a third worker past its lease; another claims; SIGCONT: its write is fenced and changes nothing.
        survivor = next(p for k, p in w.items() if k != owner)
        survivor.terminate()
        survivor.wait()
        rt.start("three_steps", "wf-b", {"step_seconds": 1.5})
        w3 = self.worker("w3")
        flows.wait_for(lambda: self.invoked("wf-b", "two"))
        zombie_epoch = rt.describe("wf-b")["workflow"]["epoch"]
        w3.send_signal(signal.SIGSTOP)
        self.worker("w4")
        flows.wait_for(lambda: rt.describe("wf-b")["workflow"]["epoch"] > zombie_epoch, timeout=20)
        w3.send_signal(signal.SIGCONT)
        self.assertEqual(rt.result("wf-b", timeout=30)["status"], "completed")
        flows.wait_for(lambda: any(e["event"] == "fenced" and e["wf"] == "wf-b" and e["epoch"] == zombie_epoch
                                   for e in flows.events(w3)), timeout=10)
        steps = rt.describe("wf-b")["steps"]
        self.assertEqual([s["name"] for s in steps], ["one", "two", "three"])
        self.assertTrue(all(s["epoch"] > zombie_epoch for s in steps if s["seq"] >= 2), steps)

        self.assertInvariants(["NoRerunAfterComplete", "LeaseMutex", "TakeoverOnlyAfterExpiry", "FencedWrites", "StepResultUnique"])


class Steps(RuntimeCase):
    def test_step_never_reruns_across_sigkill(self):
        self.rt.register(flows.three_steps)
        self.rt.start("three_steps", "wf", {})
        w1 = self.worker("w1", env={"ILR_KILL_AT": "step_after_record@1"})
        self.assertEqual(w1.wait(timeout=30), -signal.SIGKILL)
        self.worker("w2")
        self.assertEqual(self.rt.result("wf", timeout=30)["result"], ["one", "two", "three"])
        self.assertEqual([self.invoked("wf", n) for n in ("one", "two", "three")], [1, 1, 1])
        self.assertInvariants(["NoRerunAfterComplete", "FencedWrites", "TakeoverOnlyAfterExpiry"])

    def test_retry_backoff_on_database_clock(self):
        self.rt.register(flows.retrying)
        self.rt.start("retrying", "wf", {"fails": 2, "initial": 0.5})
        self.rt.start("retrying", "capped", {"fails": 5, "initial": 0.2, "max_attempts": 2})
        self.rt.start("retrying", "fatal", {"fails": 5, "error": "ValueError"})
        self.worker("w1")
        self.assertEqual(self.rt.result("wf", timeout=30)["result"], 3)
        starts = [i["started_at"] for i in flows.invocations(DSN) if i["workflow_id"] == "wf"]
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertGreaterEqual(gaps[0], 0.5)
        self.assertGreaterEqual(gaps[1], 1.0)
        self.assertLess(gaps[1], 1.0 + 1.5, gaps)          # within the poll interval plus scheduling slack
        capped = self.rt.result("capped", timeout=30)
        self.assertEqual((capped["status"], self.invoked("capped", "flaky")), ("failed", 2))
        fatal = self.rt.result("fatal", timeout=30)
        self.assertEqual((fatal["status"], self.invoked("fatal", "flaky")), ("failed", 1))

    def test_suspend_swallowed_goes_stuck(self):
        self.rt.register(swallower)
        self.rt.start("swallower", "wf", {})
        self.drain([swallower])
        wf = self.rt.describe("wf")["workflow"]
        self.assertEqual((wf["status"], wf["error"]), ("stuck", {"message": "Suspend swallowed"}))


class Timers(RuntimeCase):
    def test_timer_survives_worker_sigkill_and_postgres_crash(self):
        self.rt.register(flows.sleeper)
        self.rt.start("sleeper", "wf", {"seconds": 4})
        w1 = self.worker("w1", env={"ILR_KILL_AT": "wait_after_suspend"})
        self.assertEqual(w1.wait(timeout=30), -signal.SIGKILL)
        self.rt.conn.close()
        subprocess.run([sys.executable, os.path.join(ROOT, "experiments", "runtime_pg.py"), "restart-immediate"], check=True)
        self.rt = Runtime(DSN)
        self.assertEqual(self.status("wf"), "sleeping")
        self.worker("w2")
        self.assertEqual(self.rt.result("wf", timeout=30)["status"], "completed")
        sleep = next(s for s in self.rt.describe("wf")["steps"] if s["kind"] == "sleep")
        lateness = sleep["created_at"].timestamp() - sleep["output"]["until"]
        self.assertGreaterEqual(lateness, 0)
        self.assertLess(lateness, 2.0)
        self.assertEqual((self.invoked("wf", "before"), self.invoked("wf", "after")), (1, 1))
        self.assertInvariants(["TimerNotEarly", "NoRerunAfterComplete"])


class Signals(RuntimeCase):
    def test_two_signals_buffered_under_one_name(self):
        self.rt.register(flows.waiter)
        self.rt.start("waiter", "early", {"n": 2})
        self.rt.signal("early", "go", {"i": 1})
        self.rt.signal("early", "go", {"i": 2})
        self.rt.start("waiter", "late", {"n": 2})
        self.drain([flows.waiter])
        self.assertEqual(self.status("late"), "sleeping")
        self.rt.signal("late", "go", "a")
        self.drain([flows.waiter])
        self.assertInvariants(["NoLostWakeup"])
        self.rt.signal("late", "go", "b")
        self.drain([flows.waiter])
        self.assertEqual(self.rt.result("early", 5)["result"], [{"i": 1}, {"i": 2}])
        self.assertEqual(self.rt.result("late", 5)["result"], ["a", "b"])
        self.assertInvariants(["SignalExactlyOnceConsumed", "NoLostWakeup"])

    def test_wait_timeout_returns_none(self):
        self.rt.register(flows.waiter)
        self.rt.start("waiter", "wf", {"n": 1, "timeout": 0.5})
        self.worker("w1")
        self.assertEqual(self.rt.result("wf", timeout=15)["result"], [None])

    def test_cancel_mid_sleep(self):
        self.rt.register(flows.sleeper)
        self.rt.start("sleeper", "wf", {"seconds": 3600})
        self.drain([flows.sleeper])
        self.assertEqual(self.status("wf"), "sleeping")
        self.rt.cancel("wf", by="test")
        self.drain([flows.sleeper])
        self.assertEqual(self.status("wf"), "cancelled")
        self.assertEqual(self.invoked("wf", "after"), 0)


@workflow("versioned", "v1")
def versioned_v1(ctx, inp):
    return ctx.step("a", flows.step_body, ctx.wf_id, "a")


@workflow("versioned", "v2")
def versioned_v2(ctx, inp):
    return ctx.step("a2", flows.step_body, ctx.wf_id, "a2")


@workflow("nd", "1")
def nd_original(ctx, inp):
    ctx.step("a", flows.step_body, ctx.wf_id, "a")
    ctx.wait_signal("go")
    return ctx.step("b", flows.step_body, ctx.wf_id, "b")


@workflow("nd", "1")
def nd_renamed(ctx, inp):
    ctx.step("a_renamed", flows.step_body, ctx.wf_id, "a_renamed")
    ctx.wait_signal("go")
    return ctx.step("b", flows.step_body, ctx.wf_id, "b")


@workflow("nd", "1")
def nd_patched(ctx, inp):
    ctx.step("a", flows.step_body, ctx.wf_id, "a")
    ctx.wait_signal("go")
    if ctx.patched("extra-step"):
        ctx.step("extra", flows.step_body, ctx.wf_id, "extra")
    return ctx.step("b", flows.step_body, ctx.wf_id, "b")


@workflow("swallower", "1")
def swallower(ctx, inp):
    try:
        ctx.sleep(100)
    except BaseException:
        pass
    return "swallowed"


class Versioning(RuntimeCase):
    def test_v2_worker_never_claims_v1(self):
        self.rt.register(versioned_v1)
        self.rt.start("versioned", "old", {})
        self.rt.register(versioned_v2)
        self.rt.start("versioned", "new", {})
        self.assertEqual(self.rt.describe("new")["workflow"]["version"], "v2")
        self.drain([versioned_v2], worker_id="v2-only")
        self.assertEqual((self.status("old"), self.status("new")), ("pending", "completed"))
        self.drain([versioned_v1], worker_id="v1-only")
        self.assertEqual(self.status("old"), "completed")
        self.assertInvariants(["VersionPinned"], {"worker_versions": {"v2-only": [["versioned", "v2"]], "v1-only": [["versioned", "v1"]]}})

    def test_changed_step_name_goes_stuck_and_runs_nothing(self):
        self.rt.register(nd_original)
        self.rt.start("nd", "wf", {})
        self.drain([nd_original])
        self.rt.signal("wf", "go", 1)
        self.drain([nd_renamed], allow_code_change=True)
        wf = self.rt.describe("wf")
        self.assertEqual(wf["workflow"]["status"], "stuck")
        self.assertEqual(wf["workflow"]["error"]["seq"], 1)
        self.assertEqual(wf["workflow"]["error"]["called"]["name"], "a_renamed")
        self.assertEqual([s["name"] for s in wf["steps"]], ["a"])
        self.assertEqual((self.invoked("wf", "a_renamed"), self.invoked("wf", "b")), (0, 0))
        self.assertInvariants(["NonDeterminismLoud"])

    def test_patched_marker(self):
        self.rt.register(nd_original)
        self.rt.start("nd", "running-old", {})
        self.drain([nd_original])                        # waiting on go, recorded under the old code
        self.rt.signal("running-old", "go", 1)
        self.rt.start("nd", "new", {})
        self.rt.signal("new", "go", 1)
        self.drain([nd_patched], allow_code_change=True)
        self.assertEqual(self.status("running-old"), "completed")
        self.assertEqual(self.status("new"), "completed")
        new = [s["kind"] for s in self.rt.describe("new")["steps"]]
        self.assertEqual(new, ["step", "signal", "patch", "step", "step"])
        self.assertEqual(self.invoked("new", "extra"), 1)


class Decisions(RuntimeCase):
    def test_decision_recorded_once_across_sigkill(self):
        self.rt.register(flows.decider)
        self.rt.start("decider", "wf", {"case": "case-1", "amounts": [2000, 3000], "facts": {"refunded": 0}})
        w1 = self.worker("w1", env={"ILR_KILL_AT": "decide_after_response"})
        self.assertEqual(w1.wait(timeout=30), -signal.SIGKILL)
        self.worker("w2")
        wf = self.rt.result("wf", timeout=30)
        self.assertEqual(wf["result"], {"amount": 3000})     # the first response was discarded by the crash, never recorded
        decides = [s for s in self.rt.describe("wf")["steps"] if s["kind"] == "decide"]
        self.assertEqual(len(decides), 1)
        self.assertEqual(decides[0]["output"]["premises"], {"seen": {"refunded": 0}})
        calls = self.rt.q("select count(*) as n from ilr.llm_calls where workflow_id = 'wf'")[0]["n"]
        self.assertEqual(calls - len(decides), 1)             # discarded LLM calls
        self.assertEqual(self.invoked("wf", "after_decide"), 1)


class Composition(RuntimeCase):
    def test_child_workflow_result(self):
        for fn in (flows.parent_wf, flows.child_wf):
            self.rt.register(fn)
        self.rt.start("parent_wf", "p", {"x": 21})
        self.worker("w1")
        self.assertEqual(self.rt.result("p", timeout=30)["result"], {"status": "completed", "result": 42, "error": None})

    def test_continue_as_new(self):
        self.rt.register(flows.looper)
        self.rt.start("looper", "loop", {"n": 2})
        self.drain([flows.looper])
        rows = {r["id"]: r for r in self.rt.list(name="looper")}
        self.assertEqual({k: v["status"] for k, v in rows.items()}, {"loop": "continued", "loop#1": "continued", "loop#2": "completed"})
        self.assertEqual(rows["loop#2"]["continued_from"], "loop#1")

    def test_migrate_and_drain_report(self):
        self.rt.register(versioned_v1)
        self.rt.start("versioned", "wf", {})
        self.rt.register(versioned_v2)
        self.rt.migrate("wf", "v2")
        self.drain([versioned_v2])
        self.assertEqual([(r["version"], r["status"], r["n"]) for r in self.rt.drain_report()], [("v2", "completed", 1)])


class Effects(RuntimeCase):
    """Gated effects against a real HTTP target process. Crashes are real signals to worker subprocesses."""

    def setUp(self):
        super().setUp()
        from experiments.runtime_target import LocalRefunds, spawn_target
        self.LocalRefunds, self.spawn_target = LocalRefunds, spawn_target

    def target(self, tier, **kw):
        p, url = self.spawn_target(tier, os.path.join(self.tmp, f"t{tier}-{time.time_ns()}.sqlite"))
        self.addCleanup(lambda: (p.kill(), p.wait()))
        return self.LocalRefunds(url, tier, **kw)

    def world(self, t):
        return {"ledger": t.ledger(), "access_log": [x for x in t.log() if x["path"] == "/refunds"], "quiescent": True}

    def effect_step(self, wf_id):
        return next(s["output"] for s in self.rt.describe(wf_id)["steps"] if s["kind"] == "effect")

    def agent_case(self, t, wf_id, **kw):
        return {"id": wf_id, "url": t.url, "tier": t.tier, "amounts": [2000, 3000], "sleep_seconds": 0.2,
                "send_timeout": 3, "settle_margin": 1, **kw}

    def drain_until(self, fns, wf_id, timeout=30):
        w = Worker(self.rt, fns, worker_id="inproc", lease_ttl=5, poll=0.1)
        end = time.monotonic() + timeout
        while self.status(wf_id) not in ("completed", "failed", "cancelled", "stuck"):
            self.assertLess(time.monotonic(), end, self.rt.describe(wf_id))
            w.run(until_idle=True)
            time.sleep(0.1)
        self.assertEqual(w.errors, [])

    def approve_decision(self, wf_id, amount=None):
        decide = next(s for s in self.rt.describe(wf_id)["steps"] if s["kind"] == "decide")["output"]
        return self.rt.approve(wf_id, {"amount": amount or decide["response"]["amount"]}, decide["premises"], by="test")

    def test_agent_refund_commits_once_with_a_valid_receipt(self):
        from interlock.receipts import verify
        t = self.target(1)
        self.rt.register(flows.refund)
        self.rt.start("refund", "wf", self.agent_case(t, "wf"))
        self.drain([flows.refund])
        self.assertEqual(self.rt.describe("wf")["waiting"]["signal"], "approve")
        self.approve_decision("wf")
        self.drain_until([flows.refund], "wf")
        out = self.rt.result("wf", 5)["result"]
        self.assertEqual((out["status"], out["amount"]), ("COMMITTED", 2000))
        v = verify(self.rt.receipt(out["effect_id"], key="k"), key="k")
        self.assertEqual({k: v[k] for k in ("valid", "happened", "happened_once", "authorized_when_fired", "assumptions_held", "signed")},
                         {"valid": True, "happened": True, "happened_once": True, "authorized_when_fired": True,
                          "assumptions_held": True, "signed": True})
        self.assertEqual(len(t.ledger()), 1)
        self.assertInvariants(["AtMostOneCommit", "CommittedImpliesApplied", "ReceiptTruthful", "PayloadBound",
                               "SendRequiresLiveClaim", "EffectCheckpointAtomic", "TimerNotEarly"], self.world(t))

    def test_approval_is_bound_to_the_payload(self):
        t = self.target(1)
        self.rt.register(flows.refund)
        self.rt.start("refund", "wf", self.agent_case(t, "wf"))
        self.drain([flows.refund])
        self.approve_decision("wf", amount=1500)                  # the person approved $15; the decision says $20
        self.drain_until([flows.refund], "wf")
        self.assertEqual(self.rt.result("wf", 5)["result"]["status"], "REFUSED:lease")
        self.assertEqual(t.ledger(), [])

    def test_fork_never_resends(self):
        t = self.target(1)
        self.rt.register(flows.refund)
        self.rt.start("refund", "wf", self.agent_case(t, "wf"))
        self.drain([flows.refund])
        self.approve_decision("wf")
        self.drain_until([flows.refund], "wf")
        steps = self.rt.describe("wf")["steps"]
        decide_seq = next(s["seq"] for s in steps if s["kind"] == "decide")
        effect_seq = next(s["seq"] for s in steps if s["kind"] == "effect")

        self.rt.fork("wf", effect_seq, "fork-after-approval")      # replays decide and approval, re-runs the effect call
        self.drain_until([flows.refund], "fork-after-approval")
        self.assertEqual(self.rt.result("fork-after-approval", 5)["result"]["status"], "DUPLICATE_IGNORED")

        self.rt.fork("wf", decide_seq, "fork-redecide")            # the model now says $30 (EMULATED model variance)
        self.drain([flows.refund])
        self.approve_decision("fork-redecide")
        self.drain_until([flows.refund], "fork-redecide")
        out = self.rt.result("fork-redecide", 5)["result"]
        self.assertEqual((out["amount"], out["status"]), (3000, "REFUSED:conflicting_payload"))
        self.assertEqual([r["amount"] for r in t.ledger()], [2000])
        self.assertInvariants(["ForkNeverResends", "PayloadBound", "EffectAtMostOnceTier12"], self.world(t))

    def test_send_timeout_waits_out_the_deadline_before_lookup(self):
        """
        The target takes 3s and send_timeout is 2s. Either the socket timeout fires (the worker suspends until
        send_deadline + settle) or the watchdog does (os._exit(75), and another worker recovers). Both are allowed by
        5.4; in both, no lookup or resend may happen until the slow request has finished processing.
        """
        t = self.target(2)
        t.set_delay(3.0)
        self.rt.register(flows.refund_local)
        grant = self.rt.grant("refund-bot", "refund", max_cents=5000)
        self.rt.start("refund_local", "wf", {"url": t.url, "tier": 2, "key": "slow", "amount": 2000, "grant": grant,
                                             "send_timeout": 2, "settle_margin": 3})
        w1 = self.worker("w1", lease_ttl=1)
        refund_posts = lambda: [x for x in t.log() if (x["method"], x["path"]) == ("POST", "/refunds")]
        flows.wait_for(refund_posts, timeout=20)                  # logged when processing ends
        t.set_delay(0)
        if w1.poll() is not None:
            self.assertEqual(w1.returncode, 75)                   # the send watchdog
        self.worker("w2", lease_ttl=1)
        self.rt.result("wf", timeout=30)
        self.assertEqual(self.effect_step("wf")["status"], "COMMITTED_ON_QUERY")
        self.assertEqual(len(t.ledger()), 1)
        post = refund_posts()[0]
        after = [x for x in t.log() if x["path"] == "/refunds" and x["arrival"] > post["arrival"]]
        self.assertTrue(after and all(x["arrival"] > post["end"] for x in after), "a lookup or resend ran before the send settled")
        self.assertInvariants(["EffectAtMostOnceTier12", "NoOverlappingSends", "ReceiptTruthful"], self.world(t))

    def test_late_response_after_takeover_is_committed_by_compare_and_set(self):
        """
        SIGSTOP the sender while the target is processing, for longer than its lease but inside send_timeout (A1 holds).
        A successor claims and waits for send_deadline + settle; the sender resumes, gets the response, fails the fence,
        and the late-result transaction commits it because the dispatch pair is still its own.
        """
        t = self.target(2)
        t.set_delay(1.0)
        self.rt.register(flows.refund_local)
        grant = self.rt.grant("refund-bot", "refund", max_cents=5000)
        self.rt.start("refund_local", "wf", {"url": t.url, "tier": 2, "key": "late", "amount": 2000, "grant": grant,
                                             "send_timeout": 10, "settle_margin": 2})
        w1 = self.worker("w1", lease_ttl=1)
        # The request is in flight at the target: it arrived (access log rows are written when processing ends, so
        # watch the dispatch instead) and the target is sleeping through its 1s service delay.
        flows.wait_for(lambda: (self.rt.q("select sends from ilr.effects") or [{"sends": 0}])[0]["sends"] == 1, timeout=20)
        time.sleep(0.3)
        w1.send_signal(signal.SIGSTOP)
        self.worker("w2", lease_ttl=1)
        flows.wait_for(lambda: self.rt.describe("wf")["workflow"]["epoch"] >= 2, timeout=20)
        time.sleep(1.0)
        w1.send_signal(signal.SIGCONT)
        self.rt.result("wf", timeout=40)
        kinds = [e["kind"] for e in self.rt.receipt(self.effect_step("wf")["effect_id"])["entries"]]
        self.assertEqual(kinds.count("COMMITTED"), 1)
        self.assertEqual(self.effect_step("wf")["status"], "DUPLICATE_IGNORED")   # the successor replays the committed effect
        self.assertTrue(any(e["event"] == "fenced" for e in flows.events(w1)))
        self.assertEqual(len(t.ledger()), 1)
        self.assertInvariants(["AtMostOneCommit", "EffectAtMostOnceTier12", "FencedWrites", "ReceiptTruthful"], self.world(t))

    def test_recover_orphans(self):
        t = self.target(2)
        self.rt.register(flows.refund_local)
        grant = self.rt.grant("refund-bot", "refund", max_cents=5000)
        self.rt.start("refund_local", "wf", {"url": t.url, "tier": 2, "key": "orphan", "amount": 2000, "grant": grant,
                                             "send_timeout": 2, "settle_margin": 1})
        w1 = self.worker("w1", lease_ttl=1, env={"ILR_KILL_AT": "effect_after_dispatch"})
        self.assertEqual(w1.wait(timeout=30), -signal.SIGKILL)
        # Operator action standing in for a workflow that failed with its effect in flight.
        self.rt.conn.execute("update ilr.workflows set status = 'failed', owner = null where id = 'wf'")
        target_for = lambda eff: self.LocalRefunds(t.url, 2, send_timeout=2, settle_margin=1)
        self.assertEqual(list(self.rt.recover_orphans(target_for).values()), ["IN_FLIGHT"])   # not before deadline + settle
        time.sleep(3.2)
        self.assertEqual(list(self.rt.recover_orphans(target_for).values()), ["REAPPLIED_AFTER_QUERY"])
        self.assertEqual(self.status("wf"), "failed")
        self.assertEqual(len(t.ledger()), 1)
        self.assertInvariants(["RecoveryRechecks", "AtMostOneCommit", "ReceiptTruthful"], self.world(t))


if __name__ == "__main__":
    unittest.main()
