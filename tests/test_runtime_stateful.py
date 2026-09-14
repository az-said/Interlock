"""
R6: a Hypothesis RuleBasedStateMachine against real Postgres, real worker subprocesses and a real HTTP target.

Rules start refund workflows, run workers (some armed with an instrumented SIGKILL), SIGKILL and SIGSTOP/SIGCONT them,
approve, revoke, refund by hand at the target, cancel, send stray signals, wait for timers and deploy a second version.
After every rule, every invariant that can be read from records mid-run is checked by name; at teardown a clean
worker drains the system and the rest (ReceiptTruthful, EffectCheckpointAtomic) are checked at quiescence.

Every example starts with one workflow and one unarmed worker, so no example is vacuous, and the test fails if the
whole run dispatched no effect or started no worker process.

EMULATED, in this test only: the workflow's sleep is 2s instead of 3600s and the approval timeout is 20s, and
advance_to_next_timer is a real sleep capped at 3s. SIGSTOPs last at most 0.5s, well inside send_timeout, so
assumption A1 holds (S13 measures what happens when it does not). The model is scripted (EMULATED model variance).
The seed is fixed and printed (ILR_HYPOTHESIS_SEED); the example count is ILR_HYPOTHESIS_EXAMPLES.
"""
import collections, os, signal, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "runtime"), ROOT]
DSN = os.environ.get("ILR_DSN")

try:
    from hypothesis import HealthCheck, seed, settings, strategies as st
    from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, precondition, rule
except ImportError:
    RuleBasedStateMachine = None

if DSN and RuleBasedStateMachine:
    from experiments import runtime_flows as flows
    from experiments.runtime_target import LocalRefunds, spawn_target
    from interlock_runtime import invariants

KILL_POINTS = [None, None, "claimed", "decide_after_response", "effect_before_dispatch", "effect_after_dispatch",
               "effect_after_send", "effect_after_commit", "resolve_after_commit", "resolve_after_send", "wait_after_suspend"]
ONLINE = ["StepResultUnique", "FencedWrites", "LeaseMutex", "TakeoverOnlyAfterExpiry", "AtMostOneCommit",
          "EffectAtMostOnceTier12", "Tier3NeverResends", "NoOverlappingSends", "CommittedImpliesApplied",
          "AmbiguousOnlyWhenUnknowable", "SendRequiresLiveClaim", "NoSendUnderRevokedGrant", "NoSendOnStalePremise",
          "RecoveryRechecks", "PayloadBound", "NoSendAfterCancel", "ReceiptChainLinear", "TimerNotEarly",
          "SignalExactlyOnceConsumed", "NoLostWakeup", "NonDeterminismLoud", "ForkNeverResends"]
TERMINAL = ("completed", "failed", "cancelled", "stuck", "continued")


if DSN and RuleBasedStateMachine:
    class RuntimeMachine(RuleBasedStateMachine):
        workflows = Bundle("workflows")
        counts = collections.Counter()

        def __init__(self):
            super().__init__()
            self.rt = flows.reset_db(DSN)
            self.tmp = tempfile.mkdtemp(prefix="ilr-stateful-")
            self.workers, self.approved, self.count = [], {}, 0

        def note(self, name):
            RuntimeMachine.counts[name] += 1

        @initialize(target=workflows, tier=st.sampled_from([1, 2, 3]))
        def setup(self, tier):
            self.tier = tier
            self.target_proc, url = spawn_target(tier, os.path.join(self.tmp, "ledger.sqlite"))
            self.target = LocalRefunds(url, tier)
            self.rt.register(flows.refund)
            self.note(f"tier{tier}")
            wf = self._start([2000])
            self._run_worker(None)
            return wf

        def world(self, quiescent=False):
            return {"ledger": self.target.ledger(), "access_log": [r for r in self.target.log() if r["path"] == "/refunds"],
                    "quiescent": quiescent}

        def alive(self):
            return [p for p in self.workers if p.poll() is None]

        def _start(self, amounts):
            self.count += 1
            wf = f"wf{self.count}"
            self.rt.start("refund", wf, {"id": wf, "url": self.target.url, "tier": self.tier, "amounts": amounts,
                                         "send_timeout": 3, "settle_margin": 1, "sleep_seconds": 2, "approval_timeout": 20})
            self.note("start")
            return wf

        def _run_worker(self, kill):
            env = {"ILR_KILL_AT": kill} if kill else {}
            self.workers.append(flows.spawn_worker(f"w{len(self.workers)}", self.tmp, lease_ttl=1.5, poll=0.2, env=env))
            self.note("run_worker")
            time.sleep(0.5)

        @rule(target=workflows, amounts=st.sampled_from([[2000], [2000, 3000]]))
        def start(self, amounts):
            return self._start(amounts)

        @precondition(lambda self: len(self.alive()) < 3)
        @rule(kill=st.sampled_from(KILL_POINTS))
        def run_worker(self, kill):
            self._run_worker(kill)

        @precondition(lambda self: self.alive())
        @rule(data=st.data())
        def sigkill_worker(self, data):
            data.draw(st.sampled_from(self.alive())).kill()
            self.note("sigkill")

        @precondition(lambda self: self.alive())
        @rule(data=st.data())
        def sigstop_and_sigcont(self, data):
            p = data.draw(st.sampled_from(self.alive()))
            p.send_signal(signal.SIGSTOP)
            time.sleep(0.5)
            p.send_signal(signal.SIGCONT)
            self.note("sigstop")

        @rule()
        def approve_waiting(self):
            """Approve every workflow that has decided and is not yet approved (a bundle draw usually came too early)."""
            for wf in [f"wf{i}" for i in range(1, self.count + 1) if f"wf{i}" not in self.approved]:
                d = self.rt.describe(wf)
                decide = next((s for s in d["steps"] if s["kind"] == "decide"), None)
                if decide and d["workflow"]["status"] not in TERMINAL:
                    self.approved[wf] = self.rt.approve(wf, {"amount": decide["output"]["response"]["amount"]},
                                                        decide["output"]["premises"], by="stateful-test")
                    self.note("approve")
            time.sleep(1.0)

        @precondition(lambda self: self.approved)
        @rule(data=st.data())
        def revoke(self, data):
            self.rt.revoke(self.approved[data.draw(st.sampled_from(sorted(self.approved)))], by="stateful-test")
            self.note("revoke")

        @rule(amount=st.sampled_from([1000, 2000]))
        def hand_refund(self, amount):
            self.target.hand_refund(amount)
            self.note("hand_refund")

        @rule(wf=workflows)
        def cancel(self, wf):
            self.rt.cancel(wf, by="stateful-test")
            self.note("cancel")

        @rule(wf=workflows)
        def stray_signal(self, wf):
            self.rt.signal(wf, "noise", {"at": time.time()})
            self.note("stray_signal")

        @rule()
        def advance_to_next_timer(self):
            row = self.rt.q("select extract(epoch from min(available_at) - now())::float8 as s from ilr.workflows "
                            "where status in ('pending', 'sleeping') and available_at < 'infinity'")[0]
            time.sleep(min(3.0, max(0.5, row["s"] or 0.0)))
            self.note("advance_timer")

        @rule()
        def deploy_v2(self):
            self.rt.register(flows.refund_v2)
            self.note("deploy_v2")

        @invariant()
        def records_hold_invariants(self):
            if hasattr(self, "target"):
                self.note("invariant_checks")
                failing = invariants.failing(invariants.check(self.rt.conn, self.world(), ONLINE))
                assert not failing, failing

        def teardown(self):
            try:
                for p in self.workers:
                    if p.poll() is None:
                        p.send_signal(signal.SIGCONT)
                        p.kill()
                        p.wait()
                if hasattr(self, "target"):
                    clean = flows.spawn_worker("clean", self.tmp, lease_ttl=1.5, poll=0.2)
                    self.workers.append(clean)
                    end = time.monotonic() + 60
                    while time.monotonic() < end and self.rt.q(
                            "select 1 from ilr.workflows where status in ('pending', 'running') or (status = 'sleeping' and available_at < 'infinity')"):
                        time.sleep(0.3)
                    clean.terminate()
                    clean.wait()
                    for r in self.rt.q("select state, count(*) as n from ilr.effects group by 1"):
                        RuntimeMachine.counts[f"effect_{r['state']}"] += r["n"]
                    RuntimeMachine.counts["sends"] += self.rt.q("select coalesce(sum(sends), 0) as n from ilr.effects")[0]["n"]
                    failing = invariants.failing(invariants.check(self.rt.conn, self.world(quiescent=True)))
                    assert not failing, failing
            finally:
                for p in self.workers:
                    if p.poll() is None:
                        p.kill()
                        p.wait()
                if hasattr(self, "target_proc"):
                    self.target_proc.kill()
                    self.target_proc.wait()
                self.rt.conn.close()


@unittest.skipUnless(DSN and RuleBasedStateMachine, "needs ILR_DSN and hypothesis (uv run --with hypothesis)")
class Stateful(unittest.TestCase):
    def test_runtime_state_machine(self):
        # derandomize=True was tried first and generated only zero-step examples: a vacuous pass. A fixed seed instead.
        chosen = int(os.environ.get("ILR_HYPOTHESIS_SEED", "20260913"))
        RuntimeMachine.counts.clear()
        case = seed(chosen)(RuntimeMachine.TestCase)
        case.settings = settings(max_examples=int(os.environ.get("ILR_HYPOTHESIS_EXAMPLES", "4")), stateful_step_count=15,
                                 deadline=None, database=None, print_blob=True, suppress_health_check=list(HealthCheck))
        result = unittest.TestResult()
        started = time.monotonic()
        case("runTest").run(result)
        print(f"hypothesis seed {chosen}, {time.monotonic() - started:.0f}s: {dict(sorted(RuntimeMachine.counts.items()))}",
              file=sys.stderr)
        self.assertEqual([str(e[1]) for e in result.errors + result.failures], [])
        self.assertGreater(RuntimeMachine.counts["run_worker"], 0, "no worker process ever ran")
        self.assertGreater(RuntimeMachine.counts["sends"], 0, "no effect was ever sent")


if __name__ == "__main__":
    unittest.main()
