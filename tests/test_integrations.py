"""
    python3 -m unittest discover -s tests
    uv run --no-project --with google-adk --with "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56d" \
        python -m unittest tests.test_integrations

Offline checks for interlock/integrations. Without google-adk or the AP2 SDK installed, the tests that need them
skip; the ADK callback logic and the mandate checks around the SDK still run, against fakes.
"""
import asyncio, os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock import Gate, Leases, SimulatedCrash
from interlock.integrations.adk import Guard
from interlock.integrations.ap2 import Mandates, mandate_reference, open_mandate_id
from interlock.journal import effect_id_for
from interlock.receipts import _lease_held, verify
from interlock.targets import Payments


def installed(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


class Tool:
    def __init__(self, name):
        self.name = name


class Context:                   # the ToolContext fields the guard reads
    def __init__(self, state, call="call-1"):
        self.state, self.invocation_id, self.function_call_id, self.agent_name = state, "inv-1", call, "support"


class CrashOnce(Payments):
    """An in-memory payments API whose first send dies, before or after the refund exists."""
    def __init__(self, tier, when):
        super().__init__(tier)
        self.when = when

    def apply(self, eid, effect, crash_after_effect=False):
        when, self.when = self.when, None
        if when == "before":
            raise SimulatedCrash(eid)
        return super().apply(eid, effect, crash_after_effect=when == "after")


class AdkGuard(unittest.TestCase):
    def setUp(self):
        self.leases = Leases()
        self.leases.grant("L")
        self.api = None

    def guard(self, api):
        self.api = api
        api.create_order("881", 100)
        guard = Guard(tempfile.mkdtemp(), self.leases, claim_ttl=0, poll=0)
        guard.gate("issue_refund", target_for=lambda effect: api,
                   proposal=lambda args, ctx: {"lease": "L", "request_id": "case-4471", "premises": ctx.state["premises"],
                                               "effect": {"order": "881", "amount": args["amount"]}})
        return guard

    def call(self, guard, amount=20, tool="issue_refund", call="call-1"):
        ctx = Context({"premises": self.api.capture("881")} if not hasattr(self, "premises") else {"premises": self.premises}, call)
        return asyncio.run(guard.before_tool_callback(Tool(tool), {"amount": amount}, ctx))

    def test_ungated_tool_runs_normally(self):
        self.assertIsNone(self.call(self.guard(Payments(1)), tool="get_payment"))

    def test_sends_once_and_reports_the_recorded_result_on_replay(self):
        guard = self.guard(Payments(1))
        first = self.call(guard)
        self.assertEqual((first["interlock"], first["sent"], first["result"]), ("COMMITTED", True, {"status": "ok"}))
        again = self.call(guard, call="call-2")             # a replayed or re-issued call for the same case
        self.assertEqual((again["interlock"], again["sent"]), ("DUPLICATE_IGNORED", True))
        self.assertEqual(self.api.refunded_total("881"), 20)
        receipt = guard._gate("issue_refund", {}).journal.entries(first["effect_id"])[0]
        self.assertEqual(receipt["agent"], "adk:support/inv-1/call-1")

    def test_a_re_decided_amount_is_refused(self):
        guard = self.guard(Payments(1))
        self.call(guard)
        self.assertEqual(self.call(guard, amount=30)["interlock"], "REFUSED:conflicting_payload")
        self.assertEqual(self.api.refunded_total("881"), 20)

    def test_crash_after_the_refund_then_restart(self):
        guard = self.guard(CrashOnce(2, "after"))
        self.premises = self.api.capture("881")
        with self.assertRaises(SimulatedCrash):
            self.call(guard)
        eid = effect_id_for({"request_id": "case-4471"})
        self.assertEqual(guard.recover(), {eid: "COMMITTED_ON_QUERY"})          # on process start
        replay = self.call(guard)                                                # ADK resume replays the call
        self.assertEqual((replay["interlock"], replay["sent"]), ("DUPLICATE_IGNORED", True))
        self.assertEqual(len(self.api.refunds), 1)

    def test_replayed_call_recovers_before_it_submits(self):
        guard = self.guard(CrashOnce(1, "after"))
        self.premises = self.api.capture("881")
        with self.assertRaises(SimulatedCrash):
            self.call(guard)
        self.assertEqual(self.call(guard)["interlock"], "COMMITTED_BY_RETRY")      # no recover() at start
        self.assertEqual(len(self.api.refunds), 1)

    def test_hand_refund_during_the_outage_is_not_repeated(self):
        guard = self.guard(CrashOnce(1, "before"))
        self.premises = self.api.capture("881")
        with self.assertRaises(SimulatedCrash):
            self.call(guard)
        self.api.refunds.append({"eid": "by-hand", "order": "881", "amount": 20})
        out = self.call(guard)
        self.assertEqual((out["interlock"], out["sent"]), ("REFUSED:stale_premise_at_recovery", False))
        self.assertIn("stale_premise", out["refused"])
        self.assertEqual(self.api.refunded_total("881"), 20)

    def test_approval_revoked_during_the_outage(self):
        guard = self.guard(CrashOnce(1, "before"))
        self.premises = self.api.capture("881")
        with self.assertRaises(SimulatedCrash):
            self.call(guard)
        self.leases.revoke("L")
        self.assertEqual(self.call(guard)["interlock"], "REFUSED:lease_at_recovery")
        self.assertEqual(self.api.refunds, [])

    @unittest.skipUnless(installed("google.adk"), "google-adk not installed")
    def test_plugin_wraps_the_same_callback(self):
        from google.adk.plugins.base_plugin import BasePlugin
        guard = self.guard(Payments(1))
        plugin = guard.plugin()
        self.assertIsInstance(plugin, BasePlugin)
        ctx = Context({"premises": self.api.capture("881")})
        out = asyncio.run(plugin.before_tool_callback(tool=Tool("issue_refund"), tool_args={"amount": 20}, tool_context=ctx))
        self.assertEqual(out["interlock"], "COMMITTED")


CLOSED = {"vct": "mandate.payment.1", "transaction_id": "pi_1", "payee": {"id": "cus_1", "name": "Customer"},
          "payment_instrument": {"id": "pm_1", "type": "card"}, "payment_amount": {"amount": 2000, "currency": "USD"}}
EFFECT = {"amount": 2000, "currency": "usd", "payee": "cus_1", "instrument": "pm_1", "transaction_id": "pi_1"}
PAYMENT = {"transaction_id": "pi_1", "payee": "cus_1", "instrument": "pm_1", "currency": "USD"}   # what observe() reads
CHAIN = "openjwt.x.y~d1~~closedjwt.a.b~"
RECLOSED = "openjwt.x.y~d1~~closedjwt.c.d~"            # the same open mandate, closed again by the agent
NEW_APPROVAL = "openjwt.p.q~d1~~closedjwt.e.f~"        # a new open mandate: a person approved again
OPEN = {"vct": "mandate.payment.open.1", "exp": 99,
        "constraints": [{"type": "payment.amount_range", "currency": "USD", "max": 2000, "min": 1}]}


class MandateChecks(unittest.TestCase):
    """The checks around the SDK, with the SDK's verification replaced by a fake."""
    def store(self, violations=(), error=None, open_mandate=OPEN, observe=lambda effect: dict(PAYMENT)):
        def fake_verify(chain, keys, aud, nonce, now):
            if error:
                raise error
            return dict(open_mandate), dict(CLOSED), list(violations)
        return Mandates(tempfile.mktemp(suffix=".db"), {}, "interlock", observe=observe, verify=fake_verify)

    def register(self, m, chain=CHAIN):
        return m.register(chain, m.challenge())

    def proposal(self, api, lease, request_id="refund:case-4471"):
        return {"agent": "a", "lease": lease, "request_id": request_id, "premises": api.capture("881"),
                "effect": {**EFFECT, "order": "881"}}

    def test_references(self):
        self.assertNotEqual(mandate_reference(CHAIN), open_mandate_id(CHAIN))
        self.assertEqual(mandate_reference(CHAIN), mandate_reference("other~~closedjwt.a.b~"))

    def test_nonce_comes_from_the_verifier_and_is_single_use(self):
        m = self.store()
        with self.assertRaises(ValueError):
            m.register(CHAIN, "case-4471")                      # picked by the agent
        nonce = m.challenge()
        m.register(CHAIN, nonce)
        with self.assertRaises(ValueError):
            m.register(RECLOSED, nonce)

    def test_re_closing_the_same_mandate_after_a_refusal_is_refused_too(self):
        m, api = self.store(), CrashOnce(1, "before")
        api.create_order("881", 10000)
        gate = Gate(api, tempfile.mktemp(suffix=".db"), m, claim_ttl=0)
        p = self.proposal(api, self.register(m))
        with self.assertRaises(SimulatedCrash):
            gate.submit(p)
        api.refunds.append({"eid": "by-hand", "order": "881", "amount": 2000})
        self.assertEqual(gate.recover(), {effect_id_for(p): "REFUSED:stale_premise_at_recovery"})
        again = self.proposal(api, self.register(m, RECLOSED))  # a new lease, fresh premises that include the hand refund
        self.assertNotEqual(again["lease"], p["lease"])
        self.assertEqual(gate.submit(again), "REFUSED:stale_premise")
        self.assertEqual(api.refunded_total("881"), 2000)
        self.assertIs(verify(gate.receipt_bundle(p))["happened"], False)
        self.assertEqual(gate.submit(self.proposal(api, self.register(m, NEW_APPROVAL))), "COMMITTED")  # a person re-approved

    def test_one_closed_mandate_pays_once_and_an_open_mandate_its_cap_in_total(self):
        m, api = self.store(), Payments(1)
        api.create_order("881", 10000)
        gate, lease = Gate(api, tempfile.mktemp(suffix=".db"), m), self.register(m)
        self.assertEqual(gate.submit(self.proposal(api, lease)), "COMMITTED")
        self.assertEqual(gate.submit(self.proposal(api, lease)), "DUPLICATE_IGNORED")
        self.assertEqual(gate.submit(self.proposal(api, lease, "refund:case-4471-retry")), "REFUSED:lease_used")
        self.assertEqual(gate.submit(self.proposal(api, self.register(m, RECLOSED), "refund:case-2")), "REFUSED:lease_used")
        self.assertEqual(api.refunded_total("881"), 2000)
        refused = gate.journal.entries(effect_id_for({"request_id": "refund:case-2"}))[-1]
        self.assertIn("open mandate cap 2000", refused["reason"])

    def test_covers_exactly_the_mandated_payment(self):
        m = self.store()
        lease = self.register(m)
        self.assertTrue(m.allows(lease, EFFECT))
        self.assertTrue(_lease_held({"lease_live": True, "lease": m.describe(lease)}, EFFECT))
        for k, v in (("amount", 2500), ("amount", 1000), ("amount", 2000.0), ("payee", "cus_2"), ("instrument", "pm_2"),
                     ("transaction_id", "pi_2"), ("currency", "eur")):
            self.assertFalse(m.allows(lease, {**EFFECT, k: v}), (k, v))

    def test_the_payment_the_target_acts_on_must_be_the_mandated_one(self):
        other_customer = {"transaction_id": "pi_2", "payee": "cus_2", "instrument": "pm_2", "currency": "USD"}
        for observe, why in ((lambda effect: other_customer, "system of record: transaction_id is 'pi_2'"),
                             (None, "no observe(effect) configured"),
                             (lambda effect: 1 / 0, "could not read the payment")):
            m = self.store(observe=observe)
            lease = self.register(m)
            self.assertFalse(m.allows(lease, EFFECT))
            self.assertIn(why, " ".join(m.describe(lease)["problems"]))

    def test_an_open_mandate_without_an_amount_cap_authorizes_nothing(self):
        m, api = self.store(open_mandate={**OPEN, "constraints": []}), Payments(1)
        api.create_order("881", 10000)
        gate = Gate(api, tempfile.mktemp(suffix=".db"), m)
        for i in range(3):              # three closings of the same open mandate
            self.assertEqual(gate.submit(self.proposal(api, self.register(m, f"openjwt.x.y~d1~~closedjwt.{i}.b~"), f"r{i}")),
                             "REFUSED:lease")
        self.assertEqual(m.reserve(self.register(m, RECLOSED), "e", EFFECT)[0][:32], "open mandate has no amount range")
        self.assertEqual(api.refunded_total("881"), 0)

    def test_revoking_the_open_mandate_ends_its_closings(self):
        m = self.store()
        lease = self.register(m)
        m.revoke(open_mandate_id(CHAIN), by="finance")
        self.assertFalse(m.allows(lease, EFFECT))
        record = m.describe(lease)
        self.assertEqual(record["revoked"]["by"], "finance")
        self.assertFalse(_lease_held({"lease_live": True, "lease": record}, EFFECT))

    def test_fails_closed(self):
        m = self.store(violations=["Missing mandate context"])
        self.assertFalse(m.allows(self.register(m), EFFECT))
        m = self.store(error=ValueError("Token 0 expired at 99"))
        lease = self.register(m)
        self.assertFalse(m.allows(lease, EFFECT))
        self.assertIn("expired", m.describe(lease)["problems"][0])
        self.assertFalse(m.allows("never-registered", EFFECT))


@unittest.skipUnless(installed("ap2.sdk.mandate"), "AP2 SDK not installed")
class RealMandates(unittest.TestCase):
    """Signed and verified with the AP2 SDK. No network."""
    def setUp(self):
        from jwcrypto.jwk import JWK
        from interlock.integrations.ap2 import close_payment_mandate, open_payment_mandate
        self.finance = JWK.generate(kty="EC", crv="P-256", kid="finance-1")
        self.agent = JWK.generate(kty="EC", crv="P-256", kid="agent-1")
        self.payee, self.card = {"id": "cus_1", "name": "Customer"}, {"id": "pm_1", "type": "card"}
        self.exp = int(time.time()) + 600
        self.open = open_payment_mandate(self.finance, self.agent.export_public(as_dict=True), 2000, "USD",
                                         self.payee, self.card, self.exp)
        self.now = time.time()
        self.mandates = Mandates(tempfile.mktemp(suffix=".db"), {"finance-1": self.finance.export_public()}, "interlock",
                                 observe=lambda effect: dict(PAYMENT), clock=lambda: self.now)

    def close(self, amount, key=None, store=None, nonce=None):
        """Close the open mandate with a nonce the store issued. Returns (chain, the issued nonce) for register()."""
        from interlock.integrations.ap2 import close_payment_mandate
        issued = (store or self.mandates).challenge()
        return close_payment_mandate(key or self.agent, self.open, amount, "USD", self.payee, self.card, "pi_1",
                                     nonce or issued, "interlock"), issued

    def test_verified_chain_covers_the_payment(self):
        lease = self.mandates.register(*self.close(2000))
        self.assertTrue(self.mandates.allows(lease, EFFECT), self.mandates.describe(lease))
        record = self.mandates.describe(lease)
        self.assertEqual((record["max_cents"], record["exp"], record["vct"]), (2000, self.exp, ["mandate.payment.open.1", "mandate.payment.1"]))

    def test_over_the_cap(self):
        lease = self.mandates.register(*self.close(2500))
        self.assertFalse(self.mandates.allows(lease, {**EFFECT, "amount": 2500}))
        self.assertIn("exceeds maximum", " ".join(self.mandates.describe(lease)["problems"]))

    def test_expired_with_no_skew(self):
        lease = self.mandates.register(*self.close(2000))
        self.now = self.exp + 1
        self.assertFalse(self.mandates.allows(lease, EFFECT))
        self.assertIn("expired", " ".join(self.mandates.describe(lease)["problems"]))

    def test_untrusted_issuer_or_wrong_agent_key_or_nonce(self):
        from jwcrypto.jwk import JWK
        other = Mandates(tempfile.mktemp(suffix=".db"), {"finance-1": JWK.generate(kty="EC", crv="P-256").export_public()},
                         "interlock", observe=lambda effect: dict(PAYMENT))
        self.assertFalse(other.allows(other.register(*self.close(2000, store=other)), EFFECT))
        stranger = JWK.generate(kty="EC", crv="P-256", kid="agent-2")
        self.assertFalse(self.mandates.allows(self.mandates.register(*self.close(2000, key=stranger)), EFFECT))
        self.assertFalse(self.mandates.allows(self.mandates.register(*self.close(2000, nonce="not-the-issued-one")), EFFECT))

    def test_re_closings_share_one_authority_and_one_cap(self):
        a, b = self.mandates.register(*self.close(2000)), self.mandates.register(*self.close(2000))
        self.assertNotEqual(a, b)
        self.assertEqual(self.mandates.authority(a), self.mandates.authority(b))
        self.assertEqual(self.mandates.reserve(a, "effect-1", EFFECT), [])
        self.assertIn("already reserved", self.mandates.reserve(b, "effect-2", EFFECT)[0])

    def test_gate_refuses_at_recovery_after_revocation_and_records_the_mandate(self):
        api = CrashOnce(1, "before")
        api.create_order("881", 100)
        lease = self.mandates.register(*self.close(2000))
        gate = Gate(api, tempfile.mktemp(suffix=".db"), self.mandates, claim_ttl=0)
        p = {"agent": "a", "lease": lease, "request_id": "case-4471", "premises": api.capture("881"),
             "effect": {**EFFECT, "order": "881"}}
        with self.assertRaises(SimulatedCrash):
            gate.submit(p)
        dispatched = [e for e in gate.journal.entries(effect_id_for(p)) if e["kind"] == "DISPATCHED"][0]
        self.assertEqual(dispatched["checks"]["lease"]["mandate_reference"], lease)
        self.mandates.revoke(open_mandate_id(self.open), by="finance")
        self.assertEqual(gate.recover(), {effect_id_for(p): "REFUSED:lease_at_recovery"})
        v = verify(gate.receipt_bundle(p))
        self.assertEqual((v["valid"], v["happened"]), (True, False))
        self.assertEqual(api.refunds, [])


if __name__ == "__main__":
    unittest.main()
