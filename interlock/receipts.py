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
    approved_by          the person whose lease the landed send went out under (None for policy)
    approval_verified    once escalated, every decision answers the latest escalation, from someone it was
                         routed to, before a send citing it on the facts it showed (None: never escalated)
    escalations          who each escalation went to, why, what changed, and who decided it
    confirmed_by_target  the target's own last word, by status precedence since Stripe delivers out of order:
                         True, False, "pending" or None

A person lease with no escalation on a chain with no ESCALATED or DECIDED is a legacy approval and
is not checked against decisions. Without a signature, whoever controls the journal can strip the
escalations off a chain and make it look legacy.

With a key, the bundle is signed (HMAC-SHA256 over the effect id and the last hash). Anyone
else holding the key (the payment service, an auditor, a notary) can then confirm the log
was not rewritten wholesale. Without a key the chain proves internal consistency only: whoever
controls the journal could rebuild a consistent fake chain, or drop entries off the end, and
verify() says signed=None. The recorded checks are the gate's own attestations that it ran
them; a signature binds those attestations to the key holder, it does not re-run them.

    python3 -m interlock.receipts receipt.json [--key KEY]
"""
import hashlib, hmac, json, sys
from .escalation import final, sent_refund
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
        if e.get("kind") == "AUTHORIZED":
            authorized_seen = True
        if e.get("kind") == "REFUSED":
            refused = e.get("reason")
        if "rechecked" in e:
            at_recovery = e["rechecked"]
        if e.get("kind") == "DISPATCHED":
            if open_:
                once = False
                problems.append("sent again while an earlier send was unresolved")
            if not authorized_seen:
                problems.append("a send has no authorization before it")
            open_, effect = True, e.get("effect") or {}
            sends.append((e.get("checks") or {}, effect))
        elif e.get("kind") == "COMMITTED":
            if not open_:
                problems.append("a commit that closes no send")
            if e.get("via") in RESENDS:
                sends.append((e.get("rechecked") or {}, effect))
            evidence = e.get("result") or e.get("found")
        if e.get("kind") == "REFUSED" and e.get("resolves") and open_:
            sends.pop()         # closed by a refusal: that send never landed, so its checks attest to nothing that fired
        if e.get("kind") in ("COMMITTED", "AMBIGUOUS") or (e.get("kind") == "REFUSED" and e.get("resolves")):
            open_ = False

    kinds = [e.get("kind") for e in es]
    decisions, confirms = _people(es, problems), _confirmations(es, problems, open_)
    if confirms["refunds"] > 1:
        once = False
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
            "evidence": evidence, "rechecked_at_recovery": at_recovery, **decisions,
            "confirmed_by_target": confirms["confirmed_by_target"], "confirmation": confirms["confirmation"],
            "problems": problems}


def _people(es, problems):
    """
    Rules for escalated effects, in chain order: every decision answers the latest escalation, from
    someone it was routed to, once; every send after an escalation cites that person's approval of
    the latest one and carries the facts it showed; nothing is sent after a person closed it.
    """
    before = len(problems)
    history, answered, latest, closed, sent, landed = [], {}, None, False, None, None
    for e in es:
        kind, lease = e.get("kind"), e.get("lease")
        if kind == "ESCALATED":
            latest = e
            history.append({"at": e.get("at"), "reason": e.get("reason"), "group": e.get("group"),
                            "routed_to": e.get("routed_to"), "level": e.get("level"), "breach": e.get("breach"),
                            "changes": e.get("changes"), "repairs": len(e.get("repairs") or []), "decision": None,
                            "hash": e.get("hash")})
        elif kind == "DECIDED":
            if latest is None or e.get("escalation") != latest.get("hash"):
                problems.append("a decision answers an escalation that was superseded or missing")
            elif e.get("group") != latest.get("group") or e.get("by") not in (e.get("members") or []):
                problems.append("decided by someone the item was not routed to")
            if e.get("escalation") in answered:
                problems.append("decided twice")
            answered.setdefault(e.get("escalation"), e)
            for h in history:
                if h["hash"] == e.get("escalation") and h["decision"] is None:
                    h["decision"] = {"by": e.get("by"), "decision": e.get("decision"), "at": e.get("at")}
            closed = closed or e.get("decision") in ("reject", "repair")
        elif kind == "DISPATCHED":
            sent = lease
            person = isinstance(lease, dict)
            if closed:
                problems.append("sent after a person closed it")
            if latest is not None:
                d = answered.get(latest.get("hash"))
                if not (person and lease.get("escalation") == latest.get("hash")):
                    problems.append("sent without the decision its latest escalation asked for")
                elif not (d and d.get("decision") == "approve" and
                          (d.get("by"), d.get("at"), d.get("group")) == (lease.get("by"), lease.get("at"), lease.get("group"))):
                    problems.append("a person's send has no matching decision")
                if e.get("premises") != latest.get("facts"):
                    problems.append("sent on facts the approver never saw")
            elif person and "escalation" in lease:
                problems.append("a send cites an escalation that is not in the receipt")
        elif kind == "COMMITTED" and landed is None:
            landed = sent
    for h in history:
        del h["hash"]
    by = landed.get("by") if isinstance(landed, dict) else None
    verified = False if len(problems) > before else True if history else None
    return {"approved_by": None if by == "policy" else by, "approval_verified": verified, "escalations": history}


def _confirmations(es, problems, open_):
    """
    What the target itself said about the send: evidence only, never what decides whether it happened.
    `open_` is a send still unresolved at the end of the chain: it may have landed whatever came before it.
    """
    seen, sent, refunds, refund = [], None, set(), sent_refund(es)
    for e in es:
        if e.get("kind") == "DISPATCHED":
            sent = e.get("effect") or {}
        elif e.get("kind") == "CONFIRMED":
            if sent is None:
                problems.append("a confirmation matches no send")
            elif "amount" in sent and e.get("amount") != sent["amount"]:
                problems.append("target confirmed a different amount")
            if refund is not None and e.get("refund") != refund:
                problems.append("target confirmed a refund other than the one sent")
            refunds.add(e.get("refund"))
            seen.append({k: e.get(k) for k in ("via", "event", "refund", "status")})
    if len(refunds) > 1:
        problems.append("target confirmed more than one refund")
    kinds = [e.get("kind") for e in es]
    never_landed = not open_ and "COMMITTED" not in kinds and "AMBIGUOUS" not in kinds and any(
        e.get("kind") == "REFUSED" and e.get("resolves") for e in es)
    if never_landed and any(c["status"] == "succeeded" for c in seen):
        problems.append("target confirmed an effect the journal says never landed")
    last = final([c["status"] for c in seen])
    return {"refunds": len(refunds), "confirmation": seen,
            "confirmed_by_target": None if last is None else {"succeeded": True, "failed": False, "canceled": False}.get(last, "pending")}


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
