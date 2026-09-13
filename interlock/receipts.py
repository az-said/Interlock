"""
Receipts anyone can check, without trusting whoever hands them over.

A receipt bundle is every journal entry for one effect. Each entry carries the hash of
the entry before it, so an edited, removed or reordered entry breaks the chain. verify()
re-derives the claims from the entries themselves rather than reading a summary:

    happened             committed (True), refused or never sent (False), or nobody can know ("unknown")
    happened_once        committed at most once, never sent while an earlier send was unresolved
    authorized_when_fired  the lease was re-checked immediately before every send
    assumptions_held     the premises were re-checked immediately before every send, with no violations

With a key, the bundle is signed (HMAC-SHA256 over the effect id and the last hash). Anyone
else holding the key (the payment service, an auditor, a notary) can then confirm the log
was not rewritten wholesale. Without a key the chain proves internal consistency only: whoever
controls the journal could rebuild a consistent fake chain, and verify() says signed=None.

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

    sends, once, open_ = [], True, False
    for e in es:
        if e["kind"] == "DISPATCHED":
            if open_:
                once = False
                problems.append("sent again while an earlier send was unresolved")
            open_ = True
            sends.append(e.get("checks") or {})
        elif e["kind"] == "COMMITTED" and e.get("via") in RESENDS:
            sends.append(e.get("rechecked") or {})
        if e["kind"] in ("COMMITTED", "AMBIGUOUS") or (e["kind"] == "REFUSED" and e.get("resolves")):
            open_ = False

    kinds = [e["kind"] for e in es]
    commits = kinds.count("COMMITTED")
    if commits > 1:
        once = False
        problems.append("committed more than once")
    happened = True if commits else "unknown" if ("AMBIGUOUS" in kinds or open_) else False
    authorized = all(s.get("lease_live") is True for s in sends) if sends else None
    held = all(s.get("violations") == [] for s in sends) if sends else None
    if authorized is False:
        problems.append("a send has no record of a live lease")
    if held is False:
        problems.append("a send has no record of premises holding")

    return {"effect_id": effect_id, "valid": not problems, "tamper_evident": chained, "signed": signed,
            "happened": happened, "happened_once": once, "authorized_when_fired": authorized,
            "assumptions_held": held, "problems": problems}


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit("usage: python3 -m interlock.receipts receipt.json [--key KEY]")
    key = args[args.index("--key") + 1] if "--key" in args else None
    with open(args[0]) as f:
        result = verify(json.load(f), key)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
