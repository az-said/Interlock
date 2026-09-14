"""
Probe for the "receipt is the product" changes. interlock/ is imported, never edited: every proposed change is a
wrapper here, so its size and behavior can be measured before anyone touches the core.

Four mechanisms, each checked against forged copies of REAL receipts from live Stripe test-mode runs:

    seal       an Ed25519 checkpoint over (effect id, entry count, head hash, sealed_at, kid), made by a sealer whose
               private key the writer process never holds; a keyring with rotation (kid, retired_at)
    anchor     the DISPATCHED entry's hash sent to Stripe as refund metadata, so the service keeps a copy of the
               chain prefix (proposal, lease check, premise check) the writer cannot rewrite afterwards
    reconcile  a verifier with no key and none of the repo's code: re-hash the chain, list Stripe's refunds for the
               effect id, match the anchor (from the refund.created EVENT, and from the refund object) and the evidence
    settle     an evidence-only SETTLED entry after commit: refund status, charge disputed, disputes

Cells, every crash a real SIGKILL of a separate sender process, Interlock core claim_ttl (no liveness change):
    A crash_after_commit, B crash_before_send, C hand refund during outage (REFUSED at recovery)
    F refund then chargeback at once, G refund then chargeback after GAP seconds (the $120 gap)
    E metadata edit probe, I idempotency with a changed anchor, D key rotation (local)

    python3 experiments/competitor_receipt_proof.py            # writes results/competitors/receipt_proof.{json,txt}

Stripe test mode only (key from STRIPE_SECRET_KEY or `stripe config --list`). Requires `cryptography` for Ed25519.
"""
import copy, hashlib, hmac, inspect, json, os, shutil, signal, subprocess, sys, tempfile, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cryptography.exceptions import InvalidSignature                                   # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey         # noqa: E402
from interlock import receipts                                                          # noqa: E402
from interlock.gate import Gate                                                         # noqa: E402
from interlock.targets.stripe_api import StripeRefunds                                  # noqa: E402
from scenarios.stripe_dispute import dispute as sd                                      # noqa: E402

TTL = 35                          # above the Stripe client's 30s timeout, as the core requires
GAP = int(os.environ.get("GAP", "300"))
OUT = os.path.join(ROOT, "results", "competitors")


# ---------------------------------------------------------------- anchor (proposed: ~6 lines in the Stripe target)
class AnchoredRefunds(StripeRefunds):
    """StripeRefunds, plus the DISPATCHED hash in refund metadata. mode: before_send / after_commit SIGKILL self."""
    def __init__(self, client, payment_intent, mode=None):
        super().__init__(client, payment_intent)
        self.mode, self.journal = mode, None

    def apply(self, eid, effect, crash_after_effect=False):
        if self.mode == "before_send":
            os.kill(os.getpid(), signal.SIGKILL); time.sleep(5)
        anchor = next(e["hash"] for e in reversed(self.journal.entries(eid)) if e["kind"] == "DISPATCHED")
        refund = self.client.request("POST", "/refunds", {
            "payment_intent": self.payment_intent, "amount": effect["amount"],
            "metadata": {"interlock_effect_id": eid, "interlock_dispatch": anchor}}, idempotency_key=eid)
        if self.mode == "after_commit":
            os.kill(os.getpid(), signal.SIGKILL); time.sleep(5)
        return {"status": "already_processed" if refund["_replayed"] else "ok", "refund": refund["id"],
                "amount": refund["amount"]}


class Grant:
    def is_live(self, lease):
        return True

    def describe(self, lease):
        return {"id": lease, "granted_by": "finance-lead", "max_cents": 2000, "revoked": None}


def make_gate(d, pi, mode=None):
    t = AnchoredRefunds(sd.client(), pi, mode)
    g = Gate(t, os.path.join(d, "journal.jsonl"), Grant(), claim_ttl=TTL)
    t.journal = g.journal
    return g


def proposal(g, case):
    return {"agent": "refund-bot", "lease": f"L-{case}", "request_id": f"refund:{case}",
            "premises": g.target.capture(), "effect": {"amount": 2000}}


# ---------------------------------------------------------------- seal (proposed: receipts.seal / verify keyring)
def _msg(eid, size, head, sealed_at, kid):
    return f"interlock-receipt/v1\n{eid}\n{size}\n{head}\n{sealed_at}\n{kid}\n".encode()


def seal(bundle, kid, private_key, sealed_at=None):
    es = bundle["entries"]
    sealed_at = time.time() if sealed_at is None else sealed_at
    sig = private_key.sign(_msg(bundle["effect_id"], len(es), es[-1]["hash"], sealed_at, kid))
    return {**bundle, "seal": {"alg": "ed25519", "kid": kid, "size": len(es), "head": es[-1]["hash"],
                               "sealed_at": sealed_at, "sig": sig.hex()}}


def verify_sealed(receipt, keyring):
    """keyring: kid -> {"public": Ed25519PublicKey, "retired_at": ts or None}. Never trusts a key inside the receipt."""
    core, s, why = receipts.verify(receipt), receipt.get("seal"), None
    es = receipt["entries"]
    if not s:
        why = "unsealed"
    elif s["kid"] not in keyring:
        why = "unknown kid"
    elif keyring[s["kid"]]["retired_at"] is not None and s["sealed_at"] > keyring[s["kid"]]["retired_at"]:
        why = "sealed after its key was retired"
    elif not es or s["size"] != len(es) or s["head"] != es[-1]["hash"]:
        why = "entries differ from the sealed checkpoint"
    else:
        try:
            keyring[s["kid"]]["public"].verify(bytes.fromhex(s["sig"]),
                                                _msg(receipt["effect_id"], s["size"], s["head"], s["sealed_at"], s["kid"]))
        except InvalidSignature:
            why = "bad signature"
    return {"valid": core["valid"] and why is None, "chain_consistent": core["tamper_evident"],
            "tamper_evident": core["tamper_evident"] and why is None, "sealed_by": None if why else s["kid"], "why": why}


# ---------------------------------------------------------------- reconcile (proposed: interlock-verify --reconcile)
def _h(entry):        # the chain hash, reimplemented: this verifier uses none of the repo's code
    return hashlib.sha256(json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


def stripe_view(c, pi, eid, since):
    """Everything Stripe holds for this effect: refunds (all statuses), refund.created anchors, anchor edits."""
    rs = [r for r in c.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]
          if r["metadata"].get("interlock_effect_id") == eid]
    created, edited = {}, []
    for _ in range(30):
        created, edited = {}, []
        for ev in c.request("GET", "/events", {"type": "refund.created", "created": {"gte": since}, "limit": 100})["data"]:
            o = ev["data"]["object"]
            if o["metadata"].get("interlock_effect_id") == eid:
                created[o["id"]] = o["metadata"].get("interlock_dispatch")
        for ev in c.request("GET", "/events", {"type": "refund.updated", "created": {"gte": since}, "limit": 100})["data"]:
            prev = (ev["data"].get("previous_attributes") or {}).get("metadata") or {}
            if ev["data"]["object"]["id"] in {r["id"] for r in rs} and "interlock_dispatch" in prev:
                edited.append(ev["data"]["object"]["id"])
        if all(r["id"] in created for r in rs):
            break
        time.sleep(1)
    return {"refunds": rs, "created_anchor": created, "anchor_edited": edited}


def reconcile(receipt, view, source="event"):
    eid, es, problems, prev = receipt["effect_id"], receipt["entries"], [], None
    for i, e in enumerate(es):
        if e.get("hash") != _h(e) or e.get("prev") != prev:
            problems.append(f"chain broken at entry {i}")
        prev = e.get("hash")
    sent = {e["hash"]: e for e in es if e["kind"] == "DISPATCHED"}
    commits = [e for e in es if e["kind"] == "COMMITTED"]
    rs = view["refunds"]
    if commits:
        if len(rs) != 1:
            problems.append(f"receipt says committed; Stripe holds {len(rs)} refunds for this effect id")
        ev = commits[-1].get("result") or {}
        named = ev.get("refund") if isinstance(ev, dict) else None
        named = named or commits[-1].get("found")
        for r in rs:
            anchor = view["created_anchor"].get(r["id"]) if source == "event" else r["metadata"].get("interlock_dispatch")
            if anchor not in sent:
                problems.append("Stripe's anchor matches no DISPATCHED entry in this receipt")
            elif (sent[anchor].get("effect") or {}).get("amount") != r["amount"]:
                problems.append("anchored send amount differs from Stripe's refund")
            if named != r["id"]:
                problems.append("committed evidence names a refund Stripe does not hold for this effect")
            if source == "event" and r["id"] in view["anchor_edited"]:
                problems.append("anchor metadata was edited after the refund was created")
    elif rs and "AMBIGUOUS" not in [e["kind"] for e in es]:
        problems.append(f"receipt says not committed; Stripe holds {len(rs)} refund(s) for this effect id")
    return {"valid": not problems, "problems": problems}


# ---------------------------------------------------------------- settle (proposed: gate.settle, evidence only)
def settle(journal, c, pi, eid):
    p = c.request("GET", f"/payment_intents/{pi}")
    ch = c.request("GET", f"/charges/{p['latest_charge']}")
    rs = [r for r in c.request("GET", "/refunds", {"payment_intent": pi, "limit": 100})["data"]
          if r["metadata"].get("interlock_effect_id") == eid]
    ds = c.request("GET", "/disputes", {"payment_intent": pi, "limit": 100})["data"]
    return journal.append("SETTLED", eid, read_at=time.time(),
                          refunds=[{k: r.get(k) for k in ("id", "status", "failure_reason", "amount")} for r in rs],
                          charge={"amount_refunded": ch["amount_refunded"], "disputed": ch["disputed"]},
                          disputes=[{k: d.get(k) for k in ("id", "status", "amount")} for d in ds])


def settlement(receipt):
    s = next((e for e in reversed(receipt["entries"]) if e["kind"] == "SETTLED"), None)
    if s is None:
        return None
    ok = [r for r in s["refunds"] if r["status"] == "succeeded"]
    back = [d for d in s["disputes"] if d["status"] in sd.CHARGEBACK]
    if any(r["status"] == "failed" for r in s["refunds"]) and not ok:
        return {"state": "refund_failed", "reason": s["refunds"][0]["failure_reason"]}
    if ok and back:
        return {"state": "refunded_and_charged_back", "exposure_cents": sum(r["amount"] for r in ok) + sum(d["amount"] for d in back)}
    return {"state": "succeeded" if ok else "pending"}


# ---------------------------------------------------------------- forgeries on copies
def rechain(es, start=0):
    for i in range(start, len(es)):
        es[i]["prev"] = es[i - 1]["hash"] if i else None
        es[i]["hash"] = _h(es[i])
    return es


def forgeries(bundle):
    es = bundle["entries"]
    out = {}
    f = copy.deepcopy(bundle)                                       # F1: edit the send, no rehash
    next(e for e in f["entries"] if e["kind"] == "DISPATCHED")["effect"]["amount"] = 1500
    out["F1_edit_no_rehash"] = f
    f = copy.deepcopy(bundle)                                       # F2: flip the outcome, rehash
    last = f["entries"][-1]
    if last["kind"] == "COMMITTED":
        f["entries"][-1] = {k: v for k, v in last.items() if k not in ("result", "found", "via")}
        f["entries"][-1].update(kind="REFUSED", reason="stale_premise at recovery", resolves=True)
    else:
        f["entries"][-1] = {k: v for k, v in last.items() if k not in ("reason", "resolves")}
        f["entries"][-1].update(kind="COMMITTED", via="recovery-reapply", result={"status": "ok", "refund": "re_forged"})
    rechain(f["entries"], len(es) - 1)
    out["F2_flip_outcome_rehash"] = f
    f = copy.deepcopy(bundle)                                       # F3: drop the last entry
    f["entries"] = f["entries"][:-1]
    out["F3_truncate"] = f
    f = copy.deepcopy(bundle)                                       # F4: rebuild the whole chain with $15
    for e in f["entries"]:
        if isinstance(e.get("effect"), dict):
            e["effect"]["amount"] = 1500
    rechain(f["entries"])
    out["F4_rebuild_chain"] = f
    return out


def sign_writer(bundle, key):
    b = {k: v for k, v in bundle.items() if k != "signature"}
    return {**b, "signature": receipts.sign(b["effect_id"], b["entries"], key)}


# ---------------------------------------------------------------- live cells
def crash_cell(mode, hand_refund=False):
    c, d = sd.client(), tempfile.mkdtemp(prefix="rproof-", dir=tempfile.gettempdir())
    try:
        since = int(time.time()) - 5
        pi = c.test_payment(10000)
        case = uuid.uuid4().hex[:8]
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "child", d, pi, case, mode])
        p.wait()
        killed_at = time.time()
        if hand_refund:
            c.request("POST", "/refunds", {"payment_intent": pi, "amount": 2000})
        g = make_gate(d, pi)
        status = None
        while time.time() - killed_at < TTL + 30 and not status:
            status = next(iter(g.recover().values()), None)
            time.sleep(0.5)
        eid = next(iter({e["effect_id"] for e in g.journal.entries()}))
        return {"mode": mode, "hand_refund": hand_refund, "payment_intent": pi, "effect_id": eid,
                "sender": {"pid": p.pid, "name": "python3", "exit": p.returncode}, "status": status,
                "crash_to_settled_s": round(time.time() - killed_at, 1), "since": since,
                "bundle": receipts.bundle(g.journal, eid)}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def settle_cell(gap):
    c, d = sd.client(), tempfile.mkdtemp(prefix="rproof-", dir=tempfile.gettempdir())
    try:
        since = int(time.time()) - 5
        case = sd.create_case(c, f"interlock-sandbox-{uuid.uuid4().hex[:8]}")
        g = make_gate(d, case["payment_intent"])
        prop = proposal(g, case["id"])
        status = g.submit(prop)
        eid = next(iter({e["effect_id"] for e in g.journal.entries()}))
        settle(g.journal, c, case["payment_intent"], eid)
        at_commit = settlement(receipts.bundle(g.journal, eid))
        time.sleep(gap)
        esc = sd.escalate(c, case)
        time.sleep(15)
        settle(g.journal, c, case["payment_intent"], eid)
        b = receipts.bundle(g.journal, eid)
        return {"gap_s": gap, "payment_intent": case["payment_intent"], "dispute": case["dispute"], "effect_id": eid,
                "status": status, "escalation": esc, "settlement_at_commit": at_commit,
                "settlement_after_chargeback": settlement(b), "core_verify_with_settled": receipts.verify(b)["valid"],
                "since": since, "bundle": b}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def judge(cell, sealer_kid, sealer, keyring, writer_key, c):
    b, eid, pi = cell["bundle"], cell["effect_id"], cell["payment_intent"]
    view = stripe_view(c, pi, eid, cell["since"])
    sealed = seal(b, sealer_kid, sealer)
    rows = {"genuine": {"core_unsigned": receipts.verify(b)["valid"],
                        "core_writer_hmac": receipts.verify(sign_writer(b, writer_key), writer_key)["valid"],
                        "sealed": verify_sealed(sealed, keyring)["valid"],
                        "reconcile_event": reconcile(b, view)["valid"],
                        "reconcile_object": reconcile(b, view, "object")["valid"]}}
    for name, f in forgeries(b).items():
        after_seal = {**f, "seal": sealed["seal"]}                  # forged after collection: the old seal stays
        rows[name] = {"core_unsigned": receipts.verify(f)["valid"],
                      "core_writer_hmac": receipts.verify(sign_writer(f, writer_key), writer_key)["valid"],
                      "sealed": verify_sealed(after_seal, keyring)["valid"],
                      "sealed_if_forged_before_seal": verify_sealed(seal(f, sealer_kid, sealer), keyring)["valid"],
                      "reconcile_event": reconcile(f, view)["valid"],
                      "reconcile_event_problems": reconcile(f, view)["problems"],
                      "reconcile_object": reconcile(f, view, "object")["valid"]}
    anchors = {r["id"]: {"object": r["metadata"].get("interlock_dispatch"), "event": view["created_anchor"].get(r["id"])}
               for r in view["refunds"]}
    dispatched = [e["hash"] for e in b["entries"] if e["kind"] == "DISPATCHED"]
    return {"refunds_for_effect": [(r["id"], r["status"], r["amount"]) for r in view["refunds"]],
            "anchor_equals_dispatched_hash": all(a["event"] in dispatched and a["object"] in dispatched for a in anchors.values()),
            "verdicts": rows, "view": view}


def rotation_probe():
    """Local: seal with k1, retire k1 and add k2; old seals verify, new k1 seals and unknown kids do not."""
    k1, k2, rogue = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    b = {"effect_id": "e", "entries": rechain([{"ts": 1, "kind": "PROPOSED", "effect_id": "e", "effect": {"amount": 1}}])}
    t0 = time.time()
    old = seal(b, "k1", k1, sealed_at=t0)
    ring = {"k1": {"public": k1.public_key(), "retired_at": t0 + 10}, "k2": {"public": k2.public_key(), "retired_at": None}}
    return {"old_k1_seal_after_rotation": verify_sealed(old, ring)["valid"],
            "k2_seal": verify_sealed(seal(b, "k2", k2), ring)["valid"],
            "k1_seal_dated_after_retirement": verify_sealed(seal(b, "k1", k1, sealed_at=t0 + 60), ring)["why"],
            "rogue_key_claiming_k2": verify_sealed(seal(b, "k2", rogue), ring)["why"],
            "unknown_kid": verify_sealed(seal(b, "k9", rogue), ring)["why"],
            "caveat": "sealed_at is the sealer's own clock; retirement is only as trustworthy as an outside timestamp "
                      "(Cloud Logging receiveTimestamp, or a KMS key version's destroy time)"}


def loc(*fns):
    return sum(len([l for l in inspect.getsource(f).splitlines() if l.strip() and not l.strip().startswith("#")])
               for f in fns)


def main():
    c = sd.client()
    sealer, writer_key = Ed25519PrivateKey.generate(), os.urandom(32)   # the sealer key never reaches a child process
    keyring = {"sealer-2026-09": {"public": sealer.public_key(), "retired_at": None}}
    out = {"generated": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "claim_ttl": TTL, "cells": {}}

    for name, args in (("A_crash_after_commit", ("after_commit",)), ("B_crash_before_send", ("before_send",)),
                       ("C_hand_refund_during_outage", ("before_send", True))):
        cell = crash_cell(*args)
        cell["judged"] = judge(cell, "sealer-2026-09", sealer, keyring, writer_key, c)
        out["cells"][name] = cell
        print(name, cell["status"], cell["crash_to_settled_s"], json.dumps(cell["judged"]["refunds_for_effect"]), flush=True)

    a = out["cells"]["A_crash_after_commit"]
    try:                                                     # I: same key, changed anchor
        c.request("POST", "/refunds", {"payment_intent": a["payment_intent"], "amount": 2000,
                  "metadata": {"interlock_effect_id": a["effect_id"], "interlock_dispatch": "0" * 64}},
                  idempotency_key=a["effect_id"])
        out["I_idempotency_changed_anchor"] = "ACCEPTED (unexpected)"
    except Exception as e:
        out["I_idempotency_changed_anchor"] = str(e)[:160]

    forged = forgeries(a["bundle"])["F4_rebuild_chain"]      # E: forge the chain AND edit Stripe's metadata to match
    fake = next(e["hash"] for e in forged["entries"] if e["kind"] == "DISPATCHED")
    rid = a["judged"]["refunds_for_effect"][0][0]
    c.request("POST", f"/refunds/{rid}", {"metadata": {"interlock_dispatch": fake}})
    time.sleep(3)
    view = stripe_view(c, a["payment_intent"], a["effect_id"], a["since"])
    out["E_metadata_edit"] = {"refund": rid, "object_anchor_now_forged": view["refunds"][0]["metadata"]["interlock_dispatch"] == fake,
                              "event_anchor_still_original": view["created_anchor"].get(rid) != fake,
                              "reconcile_object_accepts_forgery": reconcile(forged, view, "object")["valid"],
                              "reconcile_event_accepts_forgery": reconcile(forged, view)["valid"],
                              "reconcile_event_problems": reconcile(forged, view)["problems"],
                              "reconcile_event_genuine_now": reconcile(a["bundle"], view)["problems"]}
    print("E", json.dumps(out["E_metadata_edit"]), flush=True)

    out["D_rotation"] = rotation_probe()
    for name, gap in (("F_chargeback_at_once", 0), ("G_chargeback_after_gap", GAP)):
        cell = settle_cell(gap)
        out["cells"][name] = cell
        print(name, cell["status"], json.dumps(cell["settlement_at_commit"]), json.dumps(cell["settlement_after_chargeback"]), flush=True)

    out["prototype_lines"] = {"anchor": loc(AnchoredRefunds.apply), "seal_and_keyring_verify": loc(_msg, seal, verify_sealed),
                              "reconcile": loc(_h, stripe_view, reconcile), "settle": loc(settle, settlement)}
    with open(os.path.join(OUT, "receipt_proof.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    with open(os.path.join(OUT, "receipt_proof.txt"), "w") as f:
        f.write(f"# receipt proof probe, {out['generated']}, Stripe test mode, claim_ttl={TTL}s, one trial per cell\n")
        for name, cell in out["cells"].items():
            f.write(f"\n## {name}: {cell['status']}, pi {cell['payment_intent']}, effect {cell['effect_id']}\n")
            if "judged" in cell:
                j = cell["judged"]
                f.write(f"refunds for effect: {j['refunds_for_effect']}; anchor == DISPATCHED hash: {j['anchor_equals_dispatched_hash']}; "
                        f"crash to settled {cell['crash_to_settled_s']}s; sender exit {cell['sender']['exit']}\n")
                cols = ("core_unsigned", "core_writer_hmac", "sealed", "sealed_if_forged_before_seal", "reconcile_event", "reconcile_object")
                f.write("receipt | " + " | ".join(cols) + "   (True = accepted as valid)\n")
                for row, v in j["verdicts"].items():
                    f.write(f"{row} | " + " | ".join(str(v.get(k, "-")) for k in cols) + "\n")
            else:
                f.write(f"settlement at commit: {cell['settlement_at_commit']}; after chargeback (gap {cell['gap_s']}s): "
                        f"{cell['settlement_after_chargeback']}; core verify() still valid with SETTLED: {cell['core_verify_with_settled']}\n")
        for k in ("I_idempotency_changed_anchor", "E_metadata_edit", "D_rotation", "prototype_lines"):
            f.write(f"\n## {k}\n{json.dumps(out[k], indent=1)}\n")
    print("done", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        _, _, d, pi, case, mode = sys.argv
        g = make_gate(d, pi, mode)
        g.submit(proposal(g, case))
        sys.exit(0)
    main()
