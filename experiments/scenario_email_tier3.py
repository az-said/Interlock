"""
Scenario email_tier3: an email that cannot be undone, against live Resend and Stripe test mode, with real SIGKILLs.

    python3 experiments/scenario_email_tier3.py

Keys are read at runtime and never written: RESEND_API_KEY (else /Users/kiromoussa/Downloads/.env), ANTHROPIC_API_KEY
(else /Users/kiromoussa/CADAI/.env), STRIPE_SECRET_KEY (else test_mode_api_key from `stripe config --list`). Stripe
test mode only; email only to delivered@resend.dev. Writes results/scenarios/email_tier3.json and .md.

Each cell: a $100 Stripe test payment; the model reads the support case and decides the refund and the email text;
the refund is issued in Stripe; a worker process (scenarios/email_tier3/systems.py) sends "your refund is on the way"
and SIGKILLs itself at the fault's crash point; the harness waits out the outage, starts a new worker, and reads the
outcome back from Resend and Stripe.
"""
import datetime, json, os, re, shutil, signal, statistics, subprocess, sys, tempfile, time, urllib.error, urllib.request, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.targets.stripe_api import StripeClient
from scenarios.email_tier3.resend import SENDER, TEST_INBOXES, Resend
from scenarios.email_tier3.systems import CLAIM_TTL, SYSTEMS, WANT, claimed, provable_from_log

MODEL = "claude-haiku-4-5-20251001"
APPROVED_CENTS = 2000
FAULTS = {   # card, crash point, what happens
    "crash_after_send": ("pm_card_visa", "after_send",
                         "worker SIGKILLed right after Resend answered 200, before anything recorded it; restarted at once. "
                         "Want: exactly one email, reported as sent"),
    "refused_before_send": ("pm_card_refundFail", "before_send",
                            "worker SIGKILLed right before the send; during the outage Stripe fails the refund; restarted "
                            "once Stripe reports it failed. Want: no email"),
    "refused_after_send": ("pm_card_refundFail", "after_send",
                           "worker SIGKILLed right after Resend answered 200; during the outage Stripe fails the refund; "
                           "restarted once Stripe reports it failed. Want: the one email that already went, reported as sent"),
}
EMULATED = {"interlock_tier3": "Nothing about Resend is emulated; the gate is told Resend has no dedup and no lookup "
            "(ResendEmail tier=3, queryable=False), the README's assumption for most email and what a sending-only key "
            "leaves after Resend's 24h key window. The send still carries an Idempotency-Key only so the harness can read "
            "it back; the gate never resends at tier 3, so Resend's dedup is never exercised."}


def env_key(name, path):
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in open(path):
            m = re.match(rf"\s*(?:export\s+)?{name}\s*=\s*(.+)", line)
            if m:
                return m.group(1).strip().strip("'\"")
    except FileNotFoundError:
        return None


def stripe_key():
    if os.environ.get("STRIPE_SECRET_KEY"):
        return os.environ["STRIPE_SECRET_KEY"]
    out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True).stdout
    m = re.search(r"^test_mode_api_key\s*=\s*['\"]?([^'\"\s]+)", out, re.M)
    return m and m.group(1)


def decide(anthropic_key, case_id, pi):
    """The agent's decision: a real model call. Validated against the approved amount before use."""
    case = (f"Support case {case_id}. Order #881, payment {pi}, paid $100.00 for a blender. The glass jar arrived "
            f"cracked. Support approved a $20.00 partial refund; the customer keeps the blender. Issue the approved "
            f"refund and write the customer a short plain-text email (two or three sentences, no placeholders, no "
            f"signature line) saying their refund is on the way.")
    tool = {"name": "refund_and_notify", "description": "Issue a refund and email the customer.",
            "input_schema": {"type": "object", "required": ["refund_cents", "email_text"], "properties": {
                "refund_cents": {"type": "integer"}, "email_text": {"type": "string"}}}}
    body = {"model": MODEL, "max_tokens": 500, "tools": [tool], "tool_choice": {"type": "tool", "name": tool["name"]},
            "messages": [{"role": "user", "content": case}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 529) or attempt == 3:
                raise RuntimeError(f"Anthropic API {e.code}") from None
            time.sleep(2 ** attempt)
    choice = next(b for b in resp["content"] if b["type"] == "tool_use")["input"]
    if choice.get("refund_cents") != APPROVED_CENTS:
        raise RuntimeError(f"model decided {choice.get('refund_cents')!r} cents, support approved {APPROVED_CENTS}")
    text = str(choice.get("email_text", "")).replace("\u2014", "-").strip()[:1200]
    if not text:
        raise RuntimeError("model wrote no email text")
    return {"refund_cents": APPROVED_CENTS, "email_text": text, "model": resp["model"]}


def tier_evidence(resend):
    """What Resend offers, established by calls, not by reading docs. Sends two emails to delivered@resend.dev."""
    tag = uuid.uuid4().hex[:10]
    email = {"from": SENDER, "to": list(TEST_INBOXES), "subject": f"Interlock tier evidence {tag}",
             "text": "Tier evidence for scenario email_tier3.", "tags": [{"name": "case", "value": f"evidence-{tag}"}]}
    k1, k2 = f"interlock-sandbox-evidence/{tag}/a", f"interlock-sandbox-evidence/{tag}/b"
    id1, r1 = resend.send(email, k1)
    id2, r2 = resend.send(email, k1)
    s, b, _ = resend.request("POST", "/emails", {**email, "text": "A different body under the same key."}, k1)
    fresh = resend.probe(k2)
    id3, r3 = resend.send({**email, "subject": email["subject"] + " b"}, k2)
    ev = {
        "dedupes": {"key": k1, "first": {"id": id1, "replayed": r1}, "second_same_body": {"id": id2, "replayed": r2},
                    "holds": id1 == id2 and not r1 and r2},
        "payload_bound": {"key": k1, "status": s, "name": b.get("name"), "holds": s == 409 and b.get("name") == "invalid_idempotent_request"},
        "probe": {"used_key": resend.probe(k1), "fresh_key": fresh, "send_after_probe": {"key": k2, "id": id3, "replayed": r3},
                  "same_key_after_send": resend.probe(k2)},
        "read_api": {},
    }
    ev["probe"]["holds"] = (ev["probe"]["used_key"] is True and fresh is False and not r3 and ev["probe"]["same_key_after_send"] is True)
    for path in (f"/emails/{id1}", "/emails?limit=1"):
        s, b, _ = resend.request("GET", path)
        ev["read_api"][path] = {"status": s, "name": b.get("name"), "message": b.get("message")}
    return ev


def run_cell(system, fault, keys, stripe, resend):
    """Attempts that end without reaching the crash point are kept, with their own ground truth, not thrown away."""
    card, point, _ = FAULTS[fault]
    discarded = []
    for attempt in range(1, 4):
        cell = attempt_cell(system, fault, card, point, keys, stripe, resend)
        if not cell.get("discarded"):
            cell.update(attempts=attempt, discarded_attempts=discarded)
            return cell
        discarded.append(cell)
        print(f"  {system}/{fault}: worker finished without reaching the crash point: {cell}; new case", flush=True)
    raise RuntimeError(f"{system}/{fault}: the crash point was never reached in 3 attempts")


def refund_failed_at(stripe, refund_id):
    """When Stripe emitted refund.failed for this refund (whole seconds), or None."""
    for e in stripe.request("GET", "/events", {"type": "refund.failed", "limit": 100})["data"]:
        if e["data"]["object"]["id"] == refund_id:
            return e["created"]


def last_check_before_send(log, journal):
    """Time of the last refund read before the first send: hand_check's log line, or the gate's DISPATCHED entry."""
    ts = [l["ts"] for l in log if l.get("check") == "refund_status"][:1] + \
         [e["ts"] for e in journal or [] if e["kind"] == "DISPATCHED"][:1]
    return min(ts) if ts else None


def attempt_cell(system, fault, card, point, keys, stripe, resend):
    case_id = f"case-4471-{uuid.uuid4().hex[:10]}"
    state = tempfile.mkdtemp(prefix="interlock-sandbox-email-")
    try:
        pi = stripe.request("POST", "/payment_intents", {"amount": 10000, "currency": "usd", "payment_method": card,
                                                         "payment_method_types": ["card"], "confirm": "true"})["id"]
        decision = decide(keys["anthropic"], case_id, pi)
        refund = stripe.request("POST", "/refunds", {"payment_intent": pi, "amount": decision["refund_cents"],
                                                     "metadata": {"case": case_id}}, idempotency_key=f"refund/{case_id}")
        case = {"case_id": case_id, "approved": True, "payment_intent": pi, "refund_id": refund["id"],
                "email": {"from": SENDER, "to": list(TEST_INBOXES), "subject": f"Your refund is on the way ({case_id})",
                          "text": decision["email_text"], "tags": [{"name": "case", "value": case_id}]}}
        case_path = os.path.join(state, "case.json")
        with open(case_path, "w") as f:
            json.dump(case, f)
        env = {**os.environ, "PYTHONPATH": ROOT, "RESEND_API_KEY": keys["resend"], "STRIPE_SECRET_KEY": keys["stripe"],
               "EMAIL_CRASH": point, "EMAIL_CRASH_MARKER": os.path.join(state, "crashed")}
        cmd = [sys.executable, "-m", "scenarios.email_tier3.systems", system, case_path, state]
        first = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        t_crash = time.time()
        if first.returncode != -signal.SIGKILL:
            if first.returncode != 0 or not os.path.exists(os.path.join(state, "result.json")):
                raise RuntimeError(f"{system}/{fault} worker failed ({first.returncode}): {first.stderr[-800:]}")
            with open(os.path.join(state, "result.json")) as f:
                result = json.load(f)
            return {"discarded": True, "outcome": result["outcome"], "emails": 1 if resend.probe(result["key"]) else 0,
                    "refund_status": stripe.request("GET", f"/refunds/{refund['id']}")["status"],
                    "ids": f"case {case_id}; refund {refund['id']}; Idempotency-Key {result['key']}"}
        outage = 0.0
        if card == "pm_card_refundFail":                  # the outage: Stripe fails the refund
            while stripe.request("GET", f"/refunds/{refund['id']}")["status"] != "failed":
                if time.time() - t_crash > 90:
                    raise RuntimeError("Stripe did not fail the refund within 90s")
                time.sleep(0.5)
            outage = time.time() - t_crash
        second = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=400)
        t_settled = time.time()
        if second.returncode != 0:
            raise RuntimeError(f"{system}/{fault} restarted worker failed ({second.returncode}): {second.stderr[-800:]}")
        with open(os.path.join(state, "result.json")) as f:
            result = json.load(f)
        log_path = os.path.join(state, "app.log")
        log = [json.loads(l) for l in open(log_path)] if os.path.exists(log_path) else []

        # Ground truth, from Resend: was the key used? If so, replaying the same body under it returns the email id and
        # must come back replayed (nothing new sent). And from Stripe: the refund's final status.
        key = result["key"]
        used = resend.probe(key)
        truth_id, truth_replayed = resend.send(case["email"], key) if used else (None, None)
        if used and not truth_replayed:
            raise RuntimeError(f"ground-truth replay for {key} sent a new email; the probe was wrong")
        emails = 1 if used else 0
        refund_final = stripe.request("GET", f"/refunds/{refund['id']}")["status"]
        said = claimed(result["outcome"])
        want = WANT[fault]
        if system.startswith("interlock"):     # a record proves nothing when what it says contradicts Resend
            r = result["receipt"]
            prove = bool(r["valid"]) and r["happened"] is (emails == 1)
        else:
            prove = provable_from_log(log, result["outcome"], result.get("email_id")) and said == emails
        failed_at = refund_failed_at(stripe, refund["id"]) if refund_final == "failed" else None
        checked_at = last_check_before_send(log, result.get("journal"))
        return {
            "system": system, "fault": fault, "outcome": result["outcome"],
            "answer": "cannot know (said so)" if said is None else "matches Resend" if said == emails else "CONTRADICTS Resend",
            "ground_truth": (f"Resend: {emails} email under Idempotency-Key {key}" + (f" (id {truth_id}, replay confirmed)" if used else "")
                             + f"; Stripe refund {refund['id']} {refund_final}"),
            "emails": emails, "want": want, "invariant_held": emails == want,
            "can_prove_what_happened": prove,
            "ids": f"case {case_id}; PaymentIntent {pi}; refund {refund['id']}; Idempotency-Key {key}; email {truth_id or 'none'}",
            "seconds_to_settle": round(t_settled - t_crash, 1), "outage_seconds": round(outage, 1),
            # refund.failed is stamped in whole seconds, so the failure came between margin and margin + 1s after the check
            "refund_failed_event_at": failed_at, "last_refund_check_before_send_at": checked_at,
            "failure_margin_seconds": round(failed_at - checked_at, 2) if failed_at and checked_at else None,
            "emulated": EMULATED.get(system), "worker_exit_codes": [first.returncode, second.returncode],
            "decision": decision, "reported_email_id": result.get("email_id"), "submitted": result.get("submitted"),
            "receipt": result.get("receipt"), "journal": result.get("journal"), "app_log": log,
        }
    finally:
        shutil.rmtree(state, ignore_errors=True)


def cell_md(c):
    held = "**held**" if c["invariant_held"] else f"**VIOLATED** ({c['emails']} email, want {c['want']})"
    return (f"`{c['outcome']}`; {c['emails']} email (want {c['want']}); {held}; answer {c['answer']}; "
            f"record proves it: {'yes' if c['can_prove_what_happened'] else 'no'}; {c['seconds_to_settle']}s")


def render(data):
    cells, ev = data["cells"], data["tier_evidence"]
    at = {(c["fault"], c["system"]): c for c in cells}
    table = "| system | " + " | ".join(f"`{f}`" for f in FAULTS) + " |\n|---|" + "---|" * len(FAULTS) + "\n" + "\n".join(
        f"| {s} | " + " | ".join(cell_md(at[f, s]) for f in FAULTS) + " |" for s in SYSTEMS)
    timing = "\n".join(
        f"- `{c['fault']}` / {c['system']}: last refund read before the send at {c['last_refund_check_before_send_at']:.2f}, "
        f"refund.failed at {c['refund_failed_event_at']}: the refund failed {c['failure_margin_seconds']}s to "
        f"{c['failure_margin_seconds'] + 1:.2f}s later"
        for c in cells if c["failure_margin_seconds"] is not None)
    discarded = "\n".join(f"- `{c['fault']}` / {c['system']} attempt {i + 1}: `{d['outcome']}`, {d['emails']} email, refund "
                          f"{d['refund_status']}; {d['ids']}"
                          for c in cells for i, d in enumerate(c["discarded_attempts"])) or "- none in this run"
    tally = "\n".join(
        f"- {s}: {sum(at[f, s]['invariant_held'] for f in FAULTS)}/{len(FAULTS)} left Resend as wanted, "
        f"{sum(at[f, s]['answer'] == 'matches Resend' for f in FAULTS)}/{len(FAULTS)} answers matched Resend, "
        f"{sum(at[f, s]['can_prove_what_happened'] for f in FAULTS)}/{len(FAULTS)} left a record that proves the outcome, "
        f"median {statistics.median(at[f, s]['seconds_to_settle'] for f in FAULTS):.0f}s from crash to settled"
        for s in SYSTEMS)
    def differ(a, b):
        return ", ".join(f"`{f}`" for f in FAULTS if (at[f, a]["emails"], at[f, a]["answer"])
                         != (at[f, b]["emails"], at[f, b]["answer"])) or "none"
    read = ev["read_api"]
    ids = "\n".join(f"- `{c['fault']}` / {c['system']}: {c['ids']}; worker exits {c['worker_exit_codes']}"
                    + (f"; receipt valid={c['receipt']['valid']}, happened={c['receipt']['happened']}, "
                       f"authorized_when_fired={c['receipt']['authorized_when_fired']}, assumptions_held={c['receipt']['assumptions_held']}"
                       f", re-check at recovery: {c['receipt']['rechecked_at_recovery']}" if c["receipt"] else "")
                    for c in cells)
    return f"""# Scenario email_tier3: an email that cannot be undone (Resend, live)

Generated {data['generated']} by `experiments/scenario_email_tier3.py`. Model `{MODEL}`, Resend API, Stripe test mode.

Each cell is one support case: a new $100 Stripe test payment, a real model call that reads the case (support
approved a $20 partial refund) and decides the refund and the email text, the refund issued in Stripe, and a worker
process that emails "Your refund is on the way" to delivered@resend.dev through Resend. The worker SIGKILLs itself at
the fault's crash point (exit code -9 recorded per cell). The harness waits out the outage, starts a new worker
process, and reads the result back from Resend and Stripe. An email cannot be recalled once Resend accepts it.

## What Resend offers, from evidence

| question | how it was tested in this run | result |
|---|---|---|
| Does POST /emails dedupe on `Idempotency-Key`? | the same key and body sent twice | first `{ev['dedupes']['first']['id']}` replayed={ev['dedupes']['first']['replayed']}, second `{ev['dedupes']['second_same_body']['id']}` replayed={ev['dedupes']['second_same_body']['replayed']}: **{'yes' if ev['dedupes']['holds'] else 'NO'}** |
| Is the key bound to the body? | the same key with another body | {ev['payload_bound']['status']} `{ev['payload_bound']['name']}`: **{'yes' if ev['payload_bound']['holds'] else 'NO'}** |
| Can a sent email be read back by id or listed? | GET `/emails/{{id}}` and GET `/emails?limit=1` with the key provided | {read[next(iter(read))]['status']} `{read[next(iter(read))]['name']}` and {read['/emails?limit=1']['status']} `{read['/emails?limit=1']['name']}`: **not with this key**. Docs: list returns id, to, subject, created_at, last_event and has no tag or header filter; get by id returns tags. A full-access key was not available, so these were not exercised. |
| Can this key ask "did an email go out under key K" without sending? | POST a well-formed body from an unverifiable domain under K | used key: {ev['probe']['used_key']} (409); fresh key: {ev['probe']['fresh_key']} (403, nothing sent); a real send under the probed key was new (replayed={ev['probe']['send_after_probe']['replayed']}) and the key then probed used={ev['probe']['same_key_after_send']}: **{'yes, inside 24h' if ev['probe']['holds'] else 'NO'}** |

Docs checked 2026-09-13: resend.com/docs/dashboard/emails/idempotency-keys (24h, 409 `invalid_idempotent_request`,
409 `concurrent_idempotent_requests`), api-reference list-emails and retrieve-email, resend.com/pricing (30-day data
retention on the free plan). The probe is not a documented lookup; it follows from the documented 409 and from Resend
checking the key before the sender's domain, which this run confirms.

**Tier, from that evidence.** Inside 24h Resend is tier 1 (it dedupes on the key) with a lookup (the probe), the same
shape as the gate's Stripe target. The lookup is an observed behavior, not a contract: if Resend started checking the
sender's domain before the key, the probe would stop answering (it raises rather than guess), and Interlock would be
tier 1 without a lookup, which is interlock_noprobe below. After 24h, with a sending-only key, it is tier 3: nothing dedupes and nothing can be
asked. With a full-access key the docs describe a lookup past 24h (list, then get each email for its tags, within the
retention window), not verified here. The README's row "SendGrid / most email: tier 3" does not describe Resend inside
its key window.

## Results

{table}

{tally}

Faults where the two systems left a different number of emails or gave a different answer: hand_check vs interlock:
{differ('hand_check', 'interlock')}; hand_check_noprobe vs interlock_noprobe: {differ('hand_check_noprobe', 'interlock_noprobe')};
hand_check_noprobe vs interlock: {differ('hand_check_noprobe', 'interlock')}.

## Better, equal, worse

- **Emails: equal.** Every system with a refund re-read (both hand checks, all three gates) left Resend as wanted on
  all three faults. no_check is the one that sends "your refund is on the way" for a refund Stripe has failed
  (`refused_before_send`): the stable key stops a duplicate, not a wrong email.
- **Answers, against the strongest hand check: equal.** hand_check (probe plus refund re-read, about fifteen lines)
  gave the same answer as Interlock on every fault. It ties.
- **Answers, against the idiomatic hand check: Interlock better, but only with the probe.** hand_check_noprobe, in
  `refused_after_send`, re-read the failed refund on restart and logged `SKIPPED:refund_failed` while the crashed
  worker's email had already gone out: its answer and its log contradict Resend. Interlock answered
  `COMMITTED_ON_QUERY` there, and that answer comes from the same undocumented probe. With Resend's documented features
  alone, interlock_noprobe answered `AMBIGUOUS` in both refused rows: never wrong, but not an answer either, and a
  person has to reconcile it. So on documented features the difference is "wrong" against "cannot know", not "wrong"
  against "right".
- **Timing: no attempt was discarded in this run.** The refund failed 0.9s to 5.8s after the last refund read before a
  send (per cell below). The previous run's Interlock result in `refused_before_send` was a near miss that exposed a
  premise bug, now fixed (see Faults).
- **Record: better.** Interlock's receipt is hash-chained, records the approval and premise checks that passed
  immediately before the send, and `verify()` re-derives what happened from it. hand_check's log also names its checks
  and the email id in these runs, but it is plain lines written by the same process, not chained, and nothing checks it.
  The interlock_tier3 receipt says `happened: unknown` after a crash, which is honest and proves nothing about delivery.
- **Time: worse.** A SIGKILLed sender cannot release its claim, so Interlock waits out `CLAIM_TTL` ({CLAIM_TTL}s, longer
  than the 30s HTTP timeouts) before recovering. hand_check and no_check rely on Resend's key and retry at once.
- **After 24h (read from code, not run: nobody waited a day).** hand_check's probe then reads "never used", its refund
  re-read passes, and it sends a second email under a key Resend has forgotten. Interlock compares its clock with the
  DISPATCHED entry, treats Resend as tier 3 (KeyWindowGate also stops trusting the probe) and says AMBIGUOUS without
  sending. hand_check could add the same age check.
- **Tier 3 costs availability.** interlock_tier3 never sends twice and never sends after the refund failed, but it
  cannot say whether the crashed send went out, so every crash ends AMBIGUOUS for a person to reconcile, including
  `crash_after_send`, where the email did go.

## Systems

- **no_check**: `Idempotency-Key: refund-email/<case>`, send, retry on restart with the same key, no re-check.
- **hand_check**: the strongest check available with this key, not the idiomatic one. Probe the key (already sent:
  replay the same body under it for the id and stop); else re-read the Stripe refund and skip if it is not succeeded
  or pending; else send with the key. Each check is logged. The probe is undocumented (see above), so few engineers
  would write it.
- **hand_check_noprobe**: the idiomatic check: re-read the refund right before the send, skip if it is not succeeded or
  pending, send with the documented Idempotency-Key, log each step.
- **interlock**: `interlock.Gate` (KeyWindowGate in `scenarios/email_tier3/systems.py`) over `ResendEmail`: tier 1 with
  the effect id as the key, the probe as the lookup, the case approval as the lease, and one premise: the refund is
  succeeded or pending, checked before the send and again at recovery. On startup the worker runs `recover()` until
  nothing is in flight, then submits as usual.
- **interlock_noprobe**: the same gate without the probe (tier 1, `queryable=False`), what Interlock gets from Resend's
  documented features alone.
- **interlock_tier3**: the same gate, told Resend offers neither dedup nor lookup.

## Faults

""" + "\n".join(f"- `{f}`: {d}" for f, (_, _, d) in FAULTS.items()) + f"""

`pm_card_refundFail` is Stripe's test card whose refund starts `succeeded` and turns `failed` a few seconds later
(4 to 7s when measured). A worker that reads the refund after it failed skips (or is refused) before the send and
never reaches the crash point. Such an attempt is rerun with a new case, the same rule for every system, and kept in
the JSON (`discarded_attempts`) with its own ground truth:

{discarded}

**The previous run was a near miss, and a real bug.** In the run generated 2026-09-13 22:33 UTC, Interlock's premise
was "the refund's OK-ness is unchanged since capture". Its `refused_before_send` cell captured the refund at
1789338900.44; Stripe's `refund.failed` event for re_3UFLzB88KhIqqdFL1X8xhi2V is stamped 1789338901, so the refund
failed 0.56s to 1.56s later. Had it failed before the capture, the premise would have recorded "not OK", matched it,
and sent "your refund is on the way" for a failed refund; and because that worker still reaches the send and the
crash, the harness would have scored it rather than rerun it. The premise is now absolute (the refund is succeeded or
pending), `tests/test_scenario_email_tier3.py` covers a refund already failed at capture, and every system follows
the same rerun rule, with discarded attempts kept above.

How close each refused cell came to the other branch (the worker's last refund read before the send against Stripe's
`refund.failed` event):

{timing}

## Ground truth

Resend's GET endpoints refuse the key provided (above), so ground truth is read from Resend's key store: after the cell,
probe the cell's key; if it was used, replay the recorded body under it, which returns the email's id and must come
back `Idempotent-Replayed: true` (checked; the run aborts otherwise). Every system sends under one stable key per case,
so one used key is one email. An email under some other key would not be seen this way; with a full-access key,
GET /emails would show it. Stripe's refund status is read directly. "Answer" compares what the system itself reported
(sent, not sent, or cannot know) with that.

"Record proves it" means the system's own record, read alone, names the email sent (or the skip), the case, and the
checks that ran before it, and what it says agrees with Resend: for the gates, `interlock.receipts.verify()` is valid
and its `happened` equals the ground truth; for the hand checks and no_check, the app log has a check entry and the
email id or the skip, and that claim equals the ground truth. A log that records a skip while an email went out
proves nothing.

## What is emulated

""" + "\n".join(f"- {s}: {t}" for s, t in EMULATED.items()) + f"""

Everything else is live: Resend sends to delivered@resend.dev, Stripe test-mode payments and refunds, Anthropic model
calls, and SIGKILLs of separate worker processes. No mocks.

## Ids

Emails cannot be looked up in the Resend dashboard by key; the ids below are Resend's email ids returned by replay.

{ids}

## Re-run

    python3 experiments/scenario_email_tier3.py
    python3 -m unittest tests.test_scenario_email_tier3     # offline logic
"""


def main():
    out = os.path.join(ROOT, "results", "scenarios")
    if sys.argv[1:] == ["--render"]:      # rewrite the .md from the last real run's JSON
        with open(os.path.join(out, "email_tier3.json")) as f:
            data = json.load(f)
        with open(os.path.join(out, "email_tier3.md"), "w") as f:
            f.write(render(data))
        return
    keys = {"resend": env_key("RESEND_API_KEY", "/Users/kiromoussa/Downloads/.env"),
            "anthropic": env_key("ANTHROPIC_API_KEY", "/Users/kiromoussa/CADAI/.env"), "stripe": stripe_key()}
    missing = [k for k, v in keys.items() if not v]
    if missing:
        sys.exit(f"missing keys: {missing}")
    stripe, resend = StripeClient(keys["stripe"]), Resend(keys["resend"])
    print("tier evidence...", flush=True)
    data = {"key": "email_tier3", "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "model": MODEL, "tier_evidence": tier_evidence(resend), "cells": []}
    print(json.dumps(data["tier_evidence"], indent=1), flush=True)
    only = set(sys.argv[1:])              # optional: limit to some systems or faults while iterating
    for fault in FAULTS:
        for system in SYSTEMS:
            if only and not ({fault, system} & only):
                continue
            print(f"{fault} / {system}...", flush=True)
            cell = run_cell(system, fault, keys, stripe, resend)
            print("  " + cell_md(cell), flush=True)
            data["cells"].append(cell)
    if only:
        print(json.dumps(data["cells"], indent=1)[:4000])
        return
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "email_tier3.json"), "w") as f:
        json.dump(data, f, indent=1)
    with open(os.path.join(out, "email_tier3.md"), "w") as f:
        f.write(render(data))
    print(f"wrote {out}/email_tier3.json and .md")


if __name__ == "__main__":
    main()
