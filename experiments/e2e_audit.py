"""
Independent audit of results/e2e_live.json against Stripe itself. Trusts nothing in the file.

    python3 experiments/e2e_audit.py [results/e2e_live.json]

Key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list`. Test keys only.
Optional: TEMPORAL_HTTP=http://127.0.0.1:7243 also reads each workflow's status over
Temporal's HTTP API (informational, never required).

Stdlib only, and deliberately none of the repo's code: its own Stripe client, its own
receipt hash-chain check. Exit 1 on any mismatch.

Per cell:
  payment    the PaymentIntent is test mode (livemode false), $100 (10000 usd cents), succeeded,
             and its charge's amount_refunded equals the sum of refund objects
  refunds    every non-failed refund on the PaymentIntent, listed live, has exactly the ids in
             refund_ids and sums to refunded_cents
  invariant  expected_cents and expected_refunds match this file's own table per scenario (from the
             approved $20, never from the model), and invariant_held == (live total and count match)
  decision   decision_matches_approval == (the LLM's amount == the approved 2000)
  workflow   workflow_ok is true (the workflow completed with a known outcome, not an error)
  answer     answer_matches_stripe re-derived: an outcome that says sent needs exactly one refund
             carrying this case's workflow id or effect id, a refusal needs none, AMBIGUOUS is honest
  who        no Interlock effect id appears on two refunds; a refund with no metadata is a hand
             refund, and the count per scenario matches the table; any workflow id in metadata is
             this cell's
  receipt    (interlock) the entry hash chain is intact; the journal's committed-or-not agrees with
             the refunds tagged with that effect id (AMBIGUOUS may have 0 or 1); a receipt for an
             effect that did not happen (refused, not AMBIGUOUS) must not claim authorized_when_fired or
             assumptions_held; every COMMITTED entry names, as its evidence, a refund id Stripe lists with
             that effect id
  emulated   exactly the emulated scenarios say so (unset is an overstatement, set elsewhere a mislabel)
"""
import base64, hashlib, json, os, subprocess, sys, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAID, APPROVED = 10000, 2000
# What each scenario must leave in Stripe, kept here independently of e2e_live.py:
# (cents refunded, refund objects, hand refunds among them)
WANT = {"crash_after_commit": (2000, 1, 0), "hand_refund_before_decision": (2500, 2, 1),
        "hand_refund_during_outage": (2000, 1, 1),
        "unrelated_refund_during_outage": (2500, 2, 1), "approval_revoked_during_outage": (0, 0, 0),
        "approval_revoked_after_commit": (2000, 1, 0), "key_pruned_after_24h": (2000, 1, 0),
        "no_lookup_after_24h": (2000, 1, 0)}
EMULATED = {"key_pruned_after_24h", "no_lookup_after_24h"}
SENT = {"REFUNDED", "REPLAYED_BY_STRIPE", "FOUND_BY_LOOKUP", "COMMITTED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY",
        "REAPPLIED_AFTER_QUERY", "DUPLICATE_IGNORED"}


def stripe_key():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        try:
            out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True, timeout=10).stdout
            key = next((l.split("=", 1)[1].strip().strip("'\"") for l in out.splitlines()
                        if l.strip().startswith("test_mode_api_key")), None)
        except (OSError, subprocess.SubprocessError):
            pass
    if not key or not key.startswith(("sk_test_", "rk_test_")):
        sys.exit("audit needs a test-mode Stripe key (sk_test_/rk_test_) in STRIPE_SECRET_KEY")
    return key


def stripe_get(key, path, params=()):
    url = "https://api.stripe.com/v1" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def all_refunds(key, pi):
    out, after = [], None
    while True:
        page = stripe_get(key, "/refunds", [("payment_intent", pi), ("limit", 100)] + ([("starting_after", after)] if after else []))
        out += page["data"]
        if not page.get("has_more"):
            return out
        after = page["data"][-1]["id"]


def chain_intact(entries):
    prev = None
    for e in entries:
        body = json.dumps({k: v for k, v in e.items() if k != "hash"}, sort_keys=True, separators=(",", ":"), default=str)
        if e.get("prev") != prev or e.get("hash") != hashlib.sha256(body.encode()).hexdigest():
            return False
        prev = e.get("hash")
    return True


def audit_cell(key, c, temporal_http):
    fails, notes = [], []
    pi_id = c.get("payment_intent")
    try:
        pi = stripe_get(key, f"/payment_intents/{pi_id}", [("expand[]", "latest_charge")])
    except urllib.error.HTTPError as e:
        return [f"PaymentIntent {pi_id} not readable ({e.code})"], notes
    if pi.get("livemode") is not False: fails.append("PaymentIntent is not test mode")
    if pi.get("amount") != PAID or pi.get("currency") != "usd": fails.append(f"paid {pi.get('amount')} {pi.get('currency')}, want {PAID} usd")
    if pi.get("status") != "succeeded": fails.append(f"PaymentIntent status {pi.get('status')}")

    live = [r for r in all_refunds(key, pi_id) if r["status"] != "failed"]
    total = sum(r["amount"] for r in live)
    charge = pi.get("latest_charge") or {}
    if isinstance(charge, dict) and charge.get("amount_refunded") != total:
        fails.append(f"charge amount_refunded {charge.get('amount_refunded')} != refund objects {total}")
    if any(r.get("livemode") for r in live): fails.append("a refund is live mode")
    if sorted(r["id"] for r in live) != sorted(c.get("refund_ids") or []):
        fails.append(f"refund ids: Stripe {sorted(r['id'] for r in live)}, JSON {sorted(c.get('refund_ids') or [])}")
    if c.get("refunded_cents") != total: fails.append(f"refunded_cents JSON {c.get('refunded_cents')}, Stripe {total}")

    if c.get("scenario") not in WANT:
        return fails + [f"unknown scenario {c.get('scenario')}"], notes
    want_cents, want_refunds, want_hand = WANT[c["scenario"]]
    if (c.get("expected_cents"), c.get("expected_refunds")) != (want_cents, want_refunds):
        fails.append(f"expected {c.get('expected_cents')} in {c.get('expected_refunds')}, audit table says {want_cents} in {want_refunds}")
    held = total == want_cents and len(live) == want_refunds
    if c.get("invariant_held") is not held:
        fails.append(f"invariant_held {c.get('invariant_held')} but Stripe has {total} in {len(live)}, want {want_cents} in {want_refunds}")
    decided = (c.get("llm_decision") or {}).get("amount_cents")
    if c.get("decision_matches_approval") is not (decided == APPROVED):
        fails.append(f"decision_matches_approval {c.get('decision_matches_approval')} but LLM decided {decided}")
    if c.get("workflow_ok") is not True:
        fails.append(f"workflow did not complete with a known outcome: {c.get('workflow_status')} {c.get('outcome')}")

    # who created each refund
    eids = [r["metadata"].get("interlock_effect_id") for r in live if r["metadata"].get("interlock_effect_id")]
    if len(eids) != len(set(eids)): fails.append("one Interlock effect id on two refunds")
    manual = [r["id"] for r in live if not r.get("metadata")]
    if len(manual) != want_hand: fails.append(f"{len(manual)} refunds without metadata (hand refunds), want {want_hand}")
    wf = c.get("workflow_id")
    rec = c.get("receipt")
    b = (rec or {}).get("bundle", rec) or {}
    eid = b.get("effect_id")
    own = [r for r in live if r["metadata"].get("workflow_id") == wf or (eid and r["metadata"].get("interlock_effect_id") == eid)]
    outcome = str(c.get("outcome"))
    answer = len(own) == 1 if outcome in SENT else len(own) == 0 if outcome.startswith("REFUSED") else outcome == "AMBIGUOUS"
    if c.get("answer_matches_stripe") is not answer:
        fails.append(f"answer_matches_stripe {c.get('answer_matches_stripe')}, but outcome {outcome} with {len(own)} own refunds")
    for r in live:
        for k, v in r["metadata"].items():
            if "workflow" in k and wf and v != wf and not str(v).startswith(wf + "/"):
                fails.append(f"refund {r['id']} metadata {k}={v} is not this cell's workflow {wf}")

    if c.get("mode") == "interlock":
        entries = b.get("entries")
        if not entries or not eid:
            fails.append("interlock cell without a receipt bundle (effect_id + entries)")
        else:
            if not chain_intact(entries): fails.append("receipt hash chain broken")
            committed = any(e.get("kind") == "COMMITTED" for e in entries)
            tagged = eids.count(eid)
            if committed and tagged != 1: fails.append(f"receipt says COMMITTED, Stripe has {tagged} refunds for {eid}")
            tagged_ids = {r["id"] for r in live if r["metadata"].get("interlock_effect_id") == eid}
            for e in entries:
                if e.get("kind") == "COMMITTED":
                    rid = (e.get("result") or {}).get("refund") or e.get("found")
                    if rid not in tagged_ids:
                        fails.append(f"receipt's commit evidence {rid!r} is not a Stripe refund tagged {eid}")
            ambiguous = any(e.get("kind") == "AMBIGUOUS" for e in entries)
            if ambiguous and not committed:
                notes.append(f"receipt AMBIGUOUS, Stripe has {tagged} refund(s) for {eid}")
                if tagged > 1: fails.append(f"receipt AMBIGUOUS, Stripe has {tagged} refunds for {eid}")
            elif not committed and tagged: fails.append(f"receipt not committed, Stripe has {tagged} refunds for {eid}")
            v = (rec or {}).get("verification") or {}
            if not committed and not ambiguous and (v.get("authorized_when_fired") is True or v.get("assumptions_held") is True):
                fails.append("receipt for an effect that did not happen claims authorized_when_fired or assumptions_held")

    if bool(c.get("emulated")) != (c["scenario"] in EMULATED):
        fails.append("emulated label is wrong: " + ("missing" if c["scenario"] in EMULATED else "set on a real cell"))

    if temporal_http and wf:
        try:
            with urllib.request.urlopen(f"{temporal_http}/api/v1/namespaces/default/workflows/{urllib.parse.quote(wf, safe='')}", timeout=5) as r:
                notes.append("temporal " + str(json.loads(r.read()).get("workflowExecutionInfo", {}).get("status")))
        except (OSError, ValueError) as e:
            notes.append(f"temporal unchecked ({type(e).__name__})")
    return fails, notes


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "results", "e2e_live.json")
    with open(path) as f:
        data = json.load(f)
    key, temporal_http = stripe_key(), os.environ.get("TEMPORAL_HTTP")
    rows, bad = [], 0
    for c in data.get("cells") or []:
        try:
            fails, notes = audit_cell(key, c, temporal_http)
        except (OSError, ValueError, KeyError) as e:
            fails, notes = [f"audit error: {type(e).__name__}: {e}"], []
        bad += bool(fails)
        flag = "EMULATED" if c.get("emulated") else ""
        rows.append((c.get("scenario"), c.get("mode"), c.get("refunded_cents"), c.get("expected_cents"),
                     "PASS" if not fails else "FAIL", flag, "; ".join(fails + notes)))
    if not rows:
        sys.exit(f"{path}: no cells to audit")
    w = [max(len(str(r[i])) for r in rows + [("scenario", "mode", "cents", "want", "audit", "flag", "")]) for i in range(6)]
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(("scenario", "mode", "cents", "want", "audit", "flag"))), " detail")
    for r in rows:
        print("  ".join(str(r[i]).ljust(w[i]) for i in range(6)), "", r[6])
    print(f"\n{len(rows) - bad}/{len(rows)} cells verified against Stripe" + (f", {bad} FAILED" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
