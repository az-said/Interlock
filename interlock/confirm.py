"""
Target-confirmed receipts: the target itself says the refund exists, on the effect's own chain.

Two ways in, one record (CONFIRMED):
    confirm_event      a Stripe webhook, trusted only once its Stripe-Signature verifies
    confirm_by_lookup  the refunds list, for users without a webhook endpoint

The signature is HMAC-SHA256 over "t.raw_body" keyed by the endpoint's whsec_ secret. Every v1 is
tried (secret rotation sends one per secret), other schemes are ignored so nobody can downgrade to
v0, and the timestamp must sit inside the tolerance, so an old signed event can't be replayed.

A refund is matched to its effect by metadata interlock_effect_id, then must name the payment the send recorded,
the amount that was sent and, once committed, the refund id the commit recorded. Stripe does not
deliver in order, so a status behind the one recorded (pending after succeeded, succeeded after
failed) is ignored. Anything unsigned or mismatched writes nothing. CONFIRMED is
evidence only: it never closes a dispatch, and the gate and inbox never read it. It stores ids,
status and amount, never the payload or the signature header, so auditors re-fetch the event.

Test mode only: live-mode events are refused.
"""
import hashlib, hmac, json, time
from .escalation import RANK, final, record, sent_refund

TYPES = ("refund.created", "refund.updated", "refund.failed")   # charge.refunded carries no refund metadata


class WebhookError(ValueError):
    pass


def verify_webhook(payload, header, secret, now=None, tolerance=300):
    """The event, once the signature over the raw bytes verifies. Errors never quote the inputs."""
    if not isinstance(secret, str) or not secret.startswith("whsec_"):
        raise ValueError("webhook secret must be a whsec_ test endpoint secret")
    if not tolerance > 0:                                          # 0 would disable the replay check
        raise ValueError("tolerance must be positive")
    if not isinstance(payload, bytes):
        raise WebhookError("payload must be the raw request bytes")
    if not header or not isinstance(header, str):
        raise WebhookError("unsigned webhook")
    t, v1s = None, []
    for part in header.split(","):
        k, _, v = part.strip().partition("=")
        if k == "t":
            t = v
        elif k == "v1":
            v1s.append(v)
    try:
        t = int(t)
    except (TypeError, ValueError):
        raise WebhookError("unsigned webhook") from None
    if not v1s:
        raise WebhookError("unsigned webhook")
    if abs((time.time() if now is None else now) - t) > tolerance:
        raise WebhookError("timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest().encode()
    if not any(hmac.compare_digest(expected, v.encode()) for v in v1s):
        raise WebhookError("signature does not match")
    event = json.loads(payload)
    if not isinstance(event, dict) or event.get("livemode") is not False:
        raise WebhookError("live mode events are refused")
    return event


def confirm_event(journal, target, payload, header, secret, now=None):
    """CONFIRMED, DUPLICATE_IGNORED, REFUSED:mismatch, IGNORED:type, IGNORED:unknown_effect or IGNORED:out_of_order."""
    event = verify_webhook(payload, header, secret, now)
    if event.get("type") not in TYPES:
        return "IGNORED:type"
    obj = event["data"]["object"]
    eid = (obj.get("metadata") or {}).get("interlock_effect_id")
    if not eid or not journal.entries(eid):
        return "IGNORED:unknown_effect"
    return _record(journal, target, eid, obj, "webhook", event["id"], event.get("created"))


def confirm_by_lookup(journal, target, eid):
    """Ask Stripe for this effect's refunds, failed ones included. NOT_FOUND when there are none."""
    # ponytail: first 100 refunds on the payment only, page with starting_after if a payment ever has more
    data = target.client.request("GET", "/refunds", {"payment_intent": target.payment_intent, "limit": 100})["data"]
    found = [r for r in data if (r.get("metadata") or {}).get("interlock_effect_id") == eid]
    if not found:
        return "NOT_FOUND"
    results = [_record(journal, target, eid, r, "lookup", None, r.get("created")) for r in found]
    return "CONFIRMED" if "CONFIRMED" in results else results[-1]


def _record(journal, target, eid, obj, via, event, created):
    def check(entries):
        sent = [e for e in entries if e["kind"] == "DISPATCHED"]
        if not sent or obj.get("amount") != (sent[-1].get("effect") or {}).get("amount"):
            return "mismatch"
        paid = (sent[-1].get("premises") or {}).get("payment_intent", target.payment_intent)   # a handler's target
        if obj.get("payment_intent") != paid:                                                 # may come from the event
            return "mismatch"
        refund = sent_refund(entries)
        if refund is not None and obj.get("id") != refund:
            return "mismatch"
        seen = [e for e in entries if e["kind"] == "CONFIRMED"]
        if event is not None and any(e["event"] == event for e in seen):
            return "duplicate"
        statuses = [e["status"] for e in seen if e["refund"] == obj.get("id")]
        if statuses and RANK.get(obj.get("status"), 0) < RANK.get(final(statuses), 0):
            return "out_of_order"
        if statuses and statuses[-1] == obj.get("status"):
            return "duplicate"
        return None

    entry, blocker = journal.append_if("CONFIRMED", eid, check, **record(
        "CONFIRMED", via=via, event=event, refund=obj.get("id"), status=obj.get("status"),
        amount=obj.get("amount"), payment_intent=obj.get("payment_intent"), created=created))
    return ("CONFIRMED" if entry else "DUPLICATE_IGNORED" if blocker == "duplicate"
            else "IGNORED:out_of_order" if blocker == "out_of_order" else "REFUSED:mismatch")
