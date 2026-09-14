"""
The systems for scenario email_tier3, and the worker process that runs one of them.

    python -m scenarios.email_tier3.systems <system> <case.json> <state_dir>

A refund was issued in Stripe (test mode); the agent now emails "your refund is on the way" to
delivered@resend.dev through Resend. Once Resend accepts an email it cannot be recalled.

    no_check            stable Idempotency-Key, retry on restart, no re-check
    hand_check          the strongest check this key allows: was the key already used (probe), is the refund still
                        good, send with the key
    hand_check_noprobe  the check most engineers write: is the refund still good, send with the key
    interlock           the send gated by interlock.Gate: tier 1 (Resend dedupes), lookup by probing the key
    interlock_noprobe   the same gate without the probe: tier 1, no lookup
    interlock_tier3     the same gate told Resend offers neither dedup nor lookup

EMAIL_CRASH=before_send|after_send with EMAIL_CRASH_MARKER=<file> SIGKILLs this process once, at that point.
The outcome goes to <state_dir>/result.json; a killed process writes nothing.
"""
import json, os, signal, sys, time
from interlock.gate import DEDUP_MARGIN, Gate
from interlock.receipts import verify
from interlock.targets.stripe_api import StripeClient
from .resend import Resend

REFUND_OK = ("succeeded", "pending")
CLAIM_TTL = 35          # seconds: longer than the 30s HTTP timeouts, so recovery never overlaps a live send
SYSTEMS = ("no_check", "hand_check", "hand_check_noprobe", "interlock", "interlock_noprobe", "interlock_tier3")
WANT = {"crash_after_send": 1, "refused_before_send": 0, "refused_after_send": 1}    # emails that should exist


def crash_once(point):
    marker = os.environ.get("EMAIL_CRASH_MARKER")
    if os.environ.get("EMAIL_CRASH") == point and marker and not os.path.exists(marker):
        open(marker, "w").close()
        os.kill(os.getpid(), signal.SIGKILL)


def refund_status(stripe, refund_id):
    return stripe.request("GET", f"/refunds/{refund_id}")["status"]


def app_log(state, **fields):
    with open(os.path.join(state, "app.log"), "a") as f:
        f.write(json.dumps({"ts": time.time(), **fields}) + "\n")


def no_check(case, state, resend, stripe):
    key = f"refund-email/{case['case_id']}"
    crash_once("before_send")
    email_id, replayed = resend.send(case["email"], key)
    crash_once("after_send")
    app_log(state, case=case["case_id"], sent=email_id, replayed=replayed)
    return {"outcome": "SENT_REPLAYED" if replayed else "SENT", "email_id": email_id, "key": key}


def hand_check(case, state, resend, stripe, probe=True):
    """
    The documented Idempotency-Key and a re-read of the refund immediately before sending, each logged. With probe=True
    it first asks whether the key was already used (the probe, an observed but undocumented behavior: Resend's list
    and get endpoints refuse a sending-only key). Without it, this is the check most engineers write.
    """
    key, cid = f"refund-email/{case['case_id']}", case["case_id"]
    used = probe and resend.probe(key)
    if probe:
        app_log(state, case=cid, check="idempotency_key_used", result=used)
    if used:
        email_id, replayed = resend.send(case["email"], key)       # used key, same body: Resend replays, sends nothing
        app_log(state, case=cid, already_sent=email_id, replayed=replayed)
        return {"outcome": "ALREADY_SENT", "email_id": email_id, "key": key}
    status = refund_status(stripe, case["refund_id"])
    app_log(state, case=cid, check="refund_status", result=status)
    if status not in REFUND_OK:
        app_log(state, case=cid, skipped=f"refund {status}")
        return {"outcome": f"SKIPPED:refund_{status}", "email_id": None, "key": key}
    crash_once("before_send")
    email_id, replayed = resend.send(case["email"], key)
    crash_once("after_send")
    app_log(state, case=cid, sent=email_id, replayed=replayed)
    return {"outcome": "SENT_REPLAYED" if replayed else "SENT", "email_id": email_id, "key": key}


class ResendEmail:
    """
    EffectTarget: one email through Resend. Tier 1 (Resend dedupes on Idempotency-Key for 24h), and a lookup: probe
    the key, then replay the recorded body under it to learn the email id. Both only answer inside the 24h key
    window; KeyWindowGate stops trusting the lookup after it. At tier 3 the send still carries the key, only so the
    harness can read the send back; the gate never resends at tier 3.
    """
    dedup_window = 24 * 3600

    def __init__(self, resend, stripe, tier=1, lookup=True):
        self.resend, self.stripe, self.tier, self.queryable = resend, stripe, tier, tier == 1 and lookup

    def capture(self, refund_id):
        return {"refund_id": refund_id, "refund_status": refund_status(self.stripe, refund_id)}

    def validate_premises(self, premises, eid=None):
        """
        Absolute: the refund is good now. Not "unchanged since capture": a refund that had already failed when the
        agent decided would pass that comparison, and the email would say a failed refund is on the way.
        """
        status = refund_status(self.stripe, premises["refund_id"])
        return [] if status in REFUND_OK else [f"refund {premises['refund_id']} is {status}"]

    def apply(self, eid, effect, crash_after_effect=False):
        crash_once("before_send")
        email_id, replayed = self.resend.send(effect["email"], eid)
        crash_once("after_send")
        return {"status": "already_processed" if replayed else "ok", "email_id": email_id}

    def query(self, eid, effect):
        if not self.resend.probe(eid):
            return None
        return self.resend.send(effect["email"], eid)[0]           # used key, same body: a replay, never a send


class KeyWindowGate(Gate):
    """
    The key probe answers only inside Resend's 24h key window. Gate already stops trusting dedup after the window;
    this also stops trusting the lookup, so a late recovery says AMBIGUOUS instead of reading "never sent".
    """
    def _recover_one(self, eid, now):
        sends = [e for e in self.journal.entries(eid) if e["kind"] == "DISPATCHED"]
        late = bool(sends) and now - sends[-1]["ts"] > self.target.dedup_window - DEDUP_MARGIN
        queryable = self.target.queryable
        self.target.queryable = queryable and not late
        try:
            return super()._recover_one(eid, now)
        finally:
            self.target.queryable = queryable


class CaseApproval:
    """The authority: the support case's approval, re-read from the case file at every check."""
    def __init__(self, path):
        self.path = path

    def is_live(self, case_id):
        with open(self.path) as f:
            case = json.load(f)
        return case["case_id"] == case_id and case.get("approved") is True


def interlock(case, state, resend, stripe, case_path, tier=1, lookup=True, settle_timeout=180):
    target = ResendEmail(resend, stripe, tier, lookup)
    gate = KeyWindowGate(target, os.path.join(state, "journal.jsonl"), CaseApproval(case_path), claim_ttl=CLAIM_TTL)
    recovered, deadline = {}, time.time() + settle_timeout
    while True:                                     # on startup: settle whatever a crash left in flight
        recovered.update(gate.recover())
        if not gate.journal.in_flight() or time.time() > deadline:
            break
        time.sleep(1)                               # a dead sender's claim has not expired yet
    proposal = {"agent": "refund-email-agent", "lease": case["case_id"], "request_id": f"refund-email/{case['case_id']}",
                "premises": target.capture(case["refund_id"]), "effect": {"email": case["email"]}}
    submitted = gate.submit(proposal)               # the agent's normal path; after a recovery it sends nothing
    bundle = gate.receipt_bundle(proposal)
    v = verify(bundle)
    evidence = v["evidence"]
    return {"outcome": next(iter(recovered.values()), submitted), "submitted": submitted, "key": bundle["effect_id"],
            "email_id": evidence.get("email_id") if isinstance(evidence, dict) else evidence,
            "receipt": {k: v[k] for k in ("valid", "tamper_evident", "signed", "happened", "happened_once",
                                          "authorized_when_fired", "assumptions_held", "refused", "evidence",
                                          "rechecked_at_recovery", "problems")},
            "journal": bundle["entries"]}


def claimed(outcome):
    """How many emails a system's own answer says went out: 1, 0, or None when it says it cannot know."""
    if outcome.startswith(("SENT", "ALREADY_SENT", "COMMITTED", "REAPPLIED")):
        return 1
    if outcome.startswith(("SKIPPED", "REFUSED")):
        return 0
    return None


def provable_from_log(lines, outcome, email_id):
    """An app log proves the outcome when it records the checks that ran and names the email sent, or the skip."""
    checks = any("check" in line for line in lines)
    if claimed(outcome) == 1:
        return checks and any(email_id is not None and email_id in (l.get("sent"), l.get("already_sent")) for l in lines)
    return checks and claimed(outcome) == 0 and any("skipped" in line for line in lines)


def main(argv):
    system, case_path, state = argv
    with open(case_path) as f:
        case = json.load(f)
    resend, stripe = Resend(os.environ.get("RESEND_API_KEY")), StripeClient(os.environ.get("STRIPE_SECRET_KEY"))
    if system.startswith("interlock"):
        result = interlock(case, state, resend, stripe, case_path, tier=3 if system == "interlock_tier3" else 1,
                           lookup=system != "interlock_noprobe")
    elif system == "no_check":
        result = no_check(case, state, resend, stripe)
    else:
        result = hand_check(case, state, resend, stripe, probe=system == "hand_check")
    tmp = os.path.join(state, "result.json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f)
    os.replace(tmp, os.path.join(state, "result.json"))


if __name__ == "__main__":
    main(sys.argv[1:])
