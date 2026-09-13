"""
Receipts anyone can check, without trusting whoever hands them over.

A receipt bundle is every journal entry for one effect. Each entry carries the hash of
the entry before it, so an edited, removed or reordered entry breaks the chain. verify()
re-derives the claims from the entries themselves rather than reading a summary:

    happened             committed (True), refused or never sent (False), or nobody can know ("unknown")
    happened_once        committed at most once, never sent while an earlier send was unresolved
    authorized_when_fired  the lease check recorded immediately before every send passed, and the grant
                         record read with it (if any) shows it unrevoked and covering the amount
    assumptions_held     the premises were re-checked immediately before every send, with no violations
                         (none means the target read the recorded premises back unchanged)
                         (both None when nothing fired: a send later refused at recovery never landed)
    refused              the last refusal's reason, when the effect did not happen
    evidence             what the target returned for the commit (e.g. Stripe's refund id), or what a lookup found
    rechecked_at_recovery  the last re-check recovery recorded, including a failed one before a lookup
                         found the effect had already landed

With a key, the bundle is signed (HMAC-SHA256 over the effect id and the last hash). Anyone
else holding the key (the payment service, an auditor, a notary) can then confirm the log
was not rewritten wholesale. Without a key the chain proves internal consistency only: whoever
controls the journal could rebuild a consistent fake chain, or drop entries off the end, and
verify() says signed=None. The recorded checks are the gate's own attestations that it ran
them; a signature binds those attestations to the key holder, it does not re-run them.

    python3 -m interlock.receipts receipt.json [--key KEY]
"""
import hashlib, hmac, json, sys
from .journal import entry_hash

RESENDS = ("retry-idempotent", "recovery-reapply")


def sign(effect_id, entries, key):
    head = entries[-1].get("hash", "") if entries else ""
    key = key.encode() if isinstance(key, str) else key
    return hmac.new(key, f"{effect_id}:{head}".encode(), hashlib.sha256).hexdigest()


def bundle(journal, effect_id, key=None):
    entries = journal.entries(effect_id)
    out = {"effect_id": effect_id, "entries": entries, "summary": journal.receipt(effect_id)}
    if key is not None:
        out["signature"] = sign(effect_id, entries, key)
    return out


def verify(receipt, key=None):
    effect_id, es, problems = receipt["effect_id"], receipt["entries"], []

    prev = None
    for i, e in enumerate(es):
        if e.get("effect_id") != effect_id:
            problems.append(f"entry {i} belongs to another effect")
        if e.get("hash") != entry_hash(e):
            problems.append(f"entry {i} ({e.get('kind')}) was altered")
        if e.get("prev") != prev:
            problems.append(f"entry {i} ({e.get('kind')}) is out of order, or an entry before it is missing")
        prev = e.get("hash")
    chained = not problems

    signed = None
    if key is not None:
        signed = hmac.compare_digest(str(receipt.get("signature", "")), sign(effect_id, es, key))
        if not signed:
            problems.append("signature does not match this key")

    if not es:
        problems.append("the receipt has no entries")
    elif es[0].get("kind") != "PROPOSED":
        problems.append("the receipt does not start with a proposal")

    sends, once, open_, authorized_seen, refused, effect, evidence, at_recovery = [], True, False, False, None, {}, None, None
    for e in es:
        if e["kind"] == "AUTHORIZED":
            authorized_seen = True
        if e["kind"] == "REFUSED":
            refused = e.get("reason")
        if "rechecked" in e:
            at_recovery = e["rechecked"]
        if e["kind"] == "DISPATCHED":
            if open_:
                once = False
                problems.append("sent again while an earlier send was unresolved")
            if not authorized_seen:
                problems.append("a send has no authorization before it")
            open_, effect = True, e.get("effect") or {}
            sends.append((e.get("checks") or {}, effect))
        elif e["kind"] == "COMMITTED":
            if not open_:
                problems.append("a commit that closes no send")
            if e.get("via") in RESENDS:
                sends.append((e.get("rechecked") or {}, effect))
            evidence = e.get("result") or e.get("found")
        if e["kind"] == "REFUSED" and e.get("resolves") and open_:
            sends.pop()         # closed by a refusal: that send never landed, so its checks attest to nothing that fired
        if e["kind"] in ("COMMITTED", "AMBIGUOUS") or (e["kind"] == "REFUSED" and e.get("resolves")):
            open_ = False

    kinds = [e["kind"] for e in es]
    commits = kinds.count("COMMITTED")
    if commits > 1:
        once = False
        problems.append("committed more than once")
    happened = True if commits else "unknown" if ("AMBIGUOUS" in kinds or open_) else False
    authorized = all(_lease_held(s, eff) for s, eff in sends) if sends else None
    held = all(s.get("violations") == [] for s, _ in sends) if sends else None
    if authorized is False:
        problems.append("a send has no record of a live lease")
    if held is False:
        problems.append("a send has no record of premises holding")

    return {"effect_id": effect_id, "valid": not problems, "tamper_evident": chained, "signed": signed,
            "happened": happened, "happened_once": once, "authorized_when_fired": authorized,
            "assumptions_held": held, "refused": None if happened is True else refused,
            "evidence": evidence, "rechecked_at_recovery": at_recovery, "problems": problems}


def _lease_held(checks, effect):
    """The recorded lease check passed, and the grant record read with it (when there is one) agrees."""
    grant, amount = checks.get("lease"), effect.get("amount")
    if checks.get("lease_live") is not True:
        return False
    if isinstance(grant, dict):
        if grant.get("revoked") is not None:
            return False
        if grant.get("max_cents") is not None and not (type(amount) is int and amount <= grant["max_cents"]):
            return False
    return True


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        sys.exit("usage: interlock-verify receipt.json [--key KEY]")
    key = args[args.index("--key") + 1] if "--key" in args else None
    with open(args[0]) as f:
        result = verify(json.load(f), key)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
