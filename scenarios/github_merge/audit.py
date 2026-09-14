"""
The harness as auditor: it holds a key the agent process never sees and seals each system's record when it
collects it (Interlock's receipt with receipts.sign, hand_check's log with HMAC). A seal proves the record was not
rewritten after collection by anyone without the key. It does not prove the agent wrote honest entries.

forge_final() is the tamper test: flip the receipt's final entry (REFUSED <-> COMMITTED) and recompute its hash,
which is exactly what anyone who can edit an unsigned journal can do.
"""
import copy, hashlib, hmac
from interlock.journal import entry_hash
from interlock.receipts import sign, verify


def seal_receipt(receipt, key):
    return {**receipt, "signature": sign(receipt["effect_id"], receipt["entries"], key)}


def seal_log(text, key):
    return hmac.new(key.encode(), text.encode(), hashlib.sha256).hexdigest()


def forge_final(receipt):
    forged = copy.deepcopy(receipt)
    last = forged["entries"][-1]
    base = {k: last[k] for k in ("ts", "effect_id", "prev")}
    checks = {**(last.get("rechecked") or {}), "violations": []}
    if last["kind"] == "COMMITTED":
        new = {**base, "kind": "REFUSED", "reason": "stale_premise at recovery", "resolves": True,
               "rechecked": {**checks, "violations": ["forged"]}}
    else:
        new = {**base, "kind": "COMMITTED", "via": "recovery-query", "rechecked": checks, "found": "deadbeef" * 5}
    new["hash"] = entry_hash(new)
    forged["entries"][-1] = new
    return forged


def tamper_test(receipt, key):
    forged = forge_final(receipt)
    unsigned, signed = verify(forged), verify(forged, key)
    return {"forged_final": f"{receipt['entries'][-1]['kind']} -> {forged['entries'][-1]['kind']}",
            "unsigned_verify": {"valid": unsigned["valid"], "happened": unsigned["happened"], "problems": unsigned["problems"]},
            "signed_verify": {"valid": signed["valid"], "signed": signed["signed"], "problems": signed["problems"]}}
