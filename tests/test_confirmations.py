"""
    python3 -m unittest discover -s tests

Target-confirmed receipts: a signed Stripe webhook (or a refunds lookup) appends CONFIRMED to the
effect's chain. Unsigned, replayed, live-mode or mismatched events are never recorded. Offline:
signed locally with a test endpoint secret, against a fake Stripe client.
"""
import hashlib, hmac, json, os, sys, tempfile, threading, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock import Gate, Leases, SimulatedCrash, effect_id_for
from interlock.confirm import WebhookError, confirm_by_lookup, confirm_event, verify_webhook
from interlock.journal import open_dispatch
from interlock.receipts import verify
from interlock.targets.stripe_api import StripeRefunds

SECRET = "whsec_test_local"
T = 1_800_000_000


def sign(payload, t=T, secret=SECRET):
    return hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()


def header(payload, t=T, secret=SECRET):
    return f"t={t},v1={sign(payload, t, secret)}"


def event(refund, type="refund.created", id="evt_1", livemode=False):
    return json.dumps({"id": id, "object": "event", "type": type, "created": T, "livemode": livemode,
                       "data": {"object": refund}}).encode()


class Client:
    """Stripe's refunds endpoints, offline: idempotent POST, unfiltered GET."""
    def __init__(self):
        self.refunds, self.keys = [], {}

    def request(self, method, path, params=None, idempotency_key=None):
        if method == "POST" and path == "/refunds":
            if idempotency_key in self.keys:
                return {**self.keys[idempotency_key], "_replayed": True}
            r = {"id": f"re_{len(self.refunds) + 1}", "object": "refund", "amount": params["amount"],
                 "status": "succeeded", "payment_intent": params["payment_intent"],
                 "metadata": dict(params["metadata"]), "created": T}
            self.refunds.append(r)
            self.keys[idempotency_key] = r
            return {**r, "_replayed": False}
        if method == "GET" and path == "/refunds":
            return {"data": [dict(r) for r in self.refunds if r["payment_intent"] == params["payment_intent"]]}
        raise AssertionError(f"unexpected {method} {path}")


class Signature(unittest.TestCase):
    payload = event({"id": "re_1"})

    def test_valid_signature_returns_event(self):
        e = verify_webhook(self.payload, header(self.payload), SECRET, now=T)
        self.assertEqual((e["id"], e["type"]), ("evt_1", "refund.created"))

    def test_bad_signature_missing_header_or_v1_rejected(self):
        p = self.payload
        for h, msg in ((f"t={T},v1={'0' * 64}", "signature does not match"),
                       (header(p, secret="whsec_other"), "signature does not match"),
                       (None, "unsigned webhook"), ("", "unsigned webhook"),
                       (f"t={T}", "unsigned webhook"), (f"v1={sign(p)}", "unsigned webhook"),
                       (f"t=abc,v1={sign(p)}", "unsigned webhook"),
                       (f"t={T},v0={sign(p)}", "unsigned webhook"),
                       (f"t={T},v1=é", "signature does not match")):
            with self.subTest(h), self.assertRaises(WebhookError) as ctx:
                verify_webhook(p, h, SECRET, now=T)
            self.assertEqual(str(ctx.exception), msg)

    def test_old_and_future_timestamps_rejected(self):
        p = self.payload
        for now in (T + 301, T - 301):
            with self.subTest(now), self.assertRaises(WebhookError) as ctx:
                verify_webhook(p, header(p), SECRET, now=now)
            self.assertEqual(str(ctx.exception), "timestamp outside tolerance")
        self.assertEqual(verify_webhook(p, header(p), SECRET, now=T + 300)["id"], "evt_1")
        with self.assertRaises(WebhookError):
            verify_webhook(p, header(p), SECRET, now=T + 11, tolerance=10)

    def test_rotated_secret_any_v1_accepted_and_v0_ignored(self):
        p = self.payload
        h = f"t={T}, v1={sign(p, secret='whsec_old')}, v1={sign(p)}, v0={'f' * 64}"
        self.assertEqual(verify_webhook(p, h, SECRET, now=T)["id"], "evt_1")
        with self.assertRaises(WebhookError):          # a matching v0 alone is not a signature
            verify_webhook(p, f"t={T},v0={sign(p)},v1={'0' * 64}", SECRET, now=T)

    def test_non_whsec_secret_and_non_positive_tolerance_refused(self):
        p = self.payload
        for secret in ("sk_test_123", "", None, b"whsec_test_local"):
            with self.subTest(secret), self.assertRaises(ValueError) as ctx:
                verify_webhook(p, header(p), secret, now=T)
            self.assertNotIsInstance(ctx.exception, WebhookError)
        for tol in (0, -1):
            with self.subTest(tol), self.assertRaises(ValueError):
                verify_webhook(p, header(p), SECRET, now=T, tolerance=tol)

    def test_reserialized_body_fails(self):
        p = self.payload
        again = json.dumps(json.loads(p), indent=2).encode()
        with self.assertRaises(WebhookError) as ctx:
            verify_webhook(again, header(p), SECRET, now=T)
        self.assertEqual(str(ctx.exception), "signature does not match")
        with self.assertRaises(WebhookError) as ctx:
            verify_webhook(p.decode(), header(p), SECRET, now=T)
        self.assertEqual(str(ctx.exception), "payload must be the raw request bytes")

    def test_livemode_event_rejected(self):
        for live in (True, None):
            p = event({"id": "re_1"}, livemode=live)
            with self.subTest(live), self.assertRaises(WebhookError) as ctx:
                verify_webhook(p, header(p), SECRET, now=T)
            self.assertEqual(str(ctx.exception), "live mode events are refused")

    def test_secret_header_and_payload_never_in_error_text(self):
        p = self.payload
        good = header(p)
        cases = [(p, f"t={T},v1={'0' * 64}", SECRET, T), (p, None, SECRET, T), (p, good, SECRET, T + 999),
                 (json.dumps(json.loads(p), indent=2).encode(), good, SECRET, T), (p.decode(), good, SECRET, T),
                 (p, good, "sk_test_secretvalue", T), (p, header(p, secret="whsec_other"), SECRET, T)]
        live = event({"id": "re_1"}, livemode=True)
        cases.append((live, header(live), SECRET, T))
        for payload, h, secret, now in cases:
            with self.subTest(h), self.assertRaises(ValueError) as ctx:
                verify_webhook(payload, h, secret, now=now)
            text = str(ctx.exception)
            body = payload.decode() if isinstance(payload, bytes) else payload
            for leak in (SECRET, "sk_test_secretvalue", "whsec_other", good, sign(p), body, "re_1", str(T)):
                self.assertNotIn(leak, text)


class Recording(unittest.TestCase):
    def world(self, suffix=".jsonl", amount=5000, crash=False):
        client = Client()
        target = StripeRefunds(client, "pi_1")
        leases = Leases()
        leases.grant("L")
        gate = Gate(target, tempfile.mktemp(suffix=suffix), leases)
        P = {"agent": "bot", "lease": "L", "request_id": "case-1", "premises": target.capture(),
             "effect": {"amount": amount}}
        if crash:
            with self.assertRaises(SimulatedCrash):
                gate.submit(P, crash_after_effect=True)
        else:
            self.assertEqual(gate.submit(P), "COMMITTED")
        return client, target, gate, P, effect_id_for(P)

    def deliver(self, gate, target, refund, **kw):
        p = event(refund, **kw)
        return confirm_event(gate.journal, target, p, header(p), SECRET, now=T)

    def confirmed(self, gate, eid):
        return [e for e in gate.journal.entries(eid) if e["kind"] == "CONFIRMED"]

    def test_webhook_appends_confirmed(self):
        client, target, gate, P, eid = self.world()
        self.assertEqual(self.deliver(gate, target, client.refunds[0]), "CONFIRMED")
        (c,) = self.confirmed(gate, eid)
        fields = {k: v for k, v in c.items() if k not in ("ts", "kind", "effect_id", "prev", "hash")}
        self.assertEqual(fields, {"via": "webhook", "event": "evt_1", "refund": "re_1", "status": "succeeded",
                                  "amount": 5000, "payment_intent": "pi_1", "created": T})
        self.assertTrue(verify(gate.receipt_bundle(P))["valid"])

    def test_replayed_event_and_same_status_are_duplicates(self):
        client, target, gate, P, eid = self.world()
        refund = client.refunds[0]
        self.assertEqual(self.deliver(gate, target, refund), "CONFIRMED")
        self.assertEqual(self.deliver(gate, target, refund), "DUPLICATE_IGNORED")
        self.assertEqual(self.deliver(gate, target, refund, type="refund.updated", id="evt_2"), "DUPLICATE_IGNORED")
        self.assertEqual(len(self.confirmed(gate, eid)), 1)

    def test_status_change_is_recorded(self):
        client, target, gate, P, eid = self.world()
        refund = client.refunds[0]
        self.assertEqual(self.deliver(gate, target, refund), "CONFIRMED")
        failed = {**refund, "status": "failed"}
        self.assertEqual(self.deliver(gate, target, failed, type="refund.failed", id="evt_2"), "CONFIRMED")
        self.assertEqual([c["status"] for c in self.confirmed(gate, eid)], ["succeeded", "failed"])
        self.assertEqual(self.deliver(gate, target, failed, type="refund.updated", id="evt_3"), "DUPLICATE_IGNORED")

    def test_unknown_effect_other_payment_intent_or_amount_never_recorded(self):
        client, target, gate, P, eid = self.world()
        refund = client.refunds[0]
        self.assertEqual(self.deliver(gate, target, {**refund, "metadata": {"interlock_effect_id": "nope"}}),
                         "IGNORED:unknown_effect")
        self.assertEqual(self.deliver(gate, target, {**refund, "metadata": {}}), "IGNORED:unknown_effect")
        self.assertEqual(self.deliver(gate, target, {**refund, "payment_intent": "pi_other"}), "REFUSED:mismatch")
        self.assertEqual(self.deliver(gate, target, {**refund, "amount": 4999}), "REFUSED:mismatch")
        self.assertEqual(self.confirmed(gate, eid), [])
        self.assertEqual(gate.journal.entries("nope"), [])
        # a refusal before any send: nothing was dispatched, so nothing can be confirmed
        refused = {"agent": "bot", "lease": "dead", "request_id": "case-2", "premises": target.capture(),
                   "effect": {"amount": 5000}}
        self.assertEqual(gate.submit(refused), "REFUSED:lease")
        rid = effect_id_for(refused)
        self.assertEqual(self.deliver(gate, target, {**refund, "metadata": {"interlock_effect_id": rid}}),
                         "REFUSED:mismatch")
        self.assertEqual(self.confirmed(gate, rid), [])

    def test_non_refund_event_ignored(self):
        client, target, gate, P, eid = self.world()
        charge = {"id": "ch_1", "object": "charge", "metadata": {"interlock_effect_id": eid}}
        self.assertEqual(self.deliver(gate, target, charge, type="charge.refunded"), "IGNORED:type")
        self.assertEqual(self.confirmed(gate, eid), [])
        p = event(client.refunds[0])
        with self.assertRaises(WebhookError):            # verified before anything else is read
            confirm_event(gate.journal, target, p, "t=1,v1=00", SECRET, now=T)

    def test_webhook_before_ack_does_not_close_dispatch(self):
        client, target, gate, P, eid = self.world(crash=True)
        self.assertEqual(self.deliver(gate, target, client.refunds[0]), "CONFIRMED")
        self.assertTrue(open_dispatch(gate.journal.entries(eid)))
        self.assertEqual(gate.recover(), {eid: "COMMITTED_BY_RETRY"})
        self.assertFalse(open_dispatch(gate.journal.entries(eid)))
        self.assertEqual(len(client.refunds), 1)

    def test_pull_confirmation_by_lookup(self):
        client, target, gate, P, eid = self.world()
        client.refunds.append({"id": "re_hand", "object": "refund", "amount": 700, "status": "succeeded",
                               "payment_intent": "pi_1", "metadata": {}, "created": T})
        self.assertEqual(confirm_by_lookup(gate.journal, target, eid), "CONFIRMED")
        self.assertEqual(confirm_by_lookup(gate.journal, target, eid), "DUPLICATE_IGNORED")
        client.refunds[0]["status"] = "failed"           # failed refunds are part of the lookup
        self.assertEqual(confirm_by_lookup(gate.journal, target, eid), "CONFIRMED")
        cs = self.confirmed(gate, eid)
        self.assertEqual([(c["via"], c["event"], c["refund"], c["status"]) for c in cs],
                         [("lookup", None, "re_1", "succeeded"), ("lookup", None, "re_1", "failed")])
        self.assertEqual(confirm_by_lookup(gate.journal, target, "other"), "NOT_FOUND")

    def test_concurrent_deliveries_record_once(self):
        for suffix in (".jsonl", ".db"):
            with self.subTest(suffix):
                client, target, gate, P, eid = self.world(suffix)
                p = event(client.refunds[0])
                h, results = header(p), []
                def deliver():
                    j = type(gate.journal)(gate.journal.path)
                    results.append(confirm_event(j, target, p, h, SECRET, now=T))
                threads = [threading.Thread(target=deliver) for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                self.assertEqual(sorted(results), ["CONFIRMED"] + ["DUPLICATE_IGNORED"] * 7)
                self.assertEqual(len(self.confirmed(gate, eid)), 1)
                self.assertTrue(verify(gate.receipt_bundle(P))["valid"])


if __name__ == "__main__":
    unittest.main()
