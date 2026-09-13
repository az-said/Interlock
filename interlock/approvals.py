"""
Approvals that shrink.

Today a person approves every agent refund. Much of what that person checks is
mechanical: is the order still eligible, was it already refunded, is this still allowed.
The gate checks those at the moment of sending. So the work splits three ways:

    rules      decide which requests need a person at all (amount limit, flagged customer)
    the gate   re-checks the facts and the authority right before the effect, and after a crash
    the queue  holds only what needs judgment, or what nobody could verify

A human approval is recorded as the authority the effect runs under, and the facts the
approver saw become its premises. If those facts change before the refund goes out
(support already refunded it, the order was cancelled), the gate refuses and the item
comes back to the queue saying so. Approvals can expire (`max_age`) and approvers can be
removed; both are checked when the effect is sent, not when the button was clicked.

Escalations and decisions live on the effect's journal chain, not in this object. Routes
send an escalation to a group, only that group decides it, and an unanswered one moves up
the route's chain after its SLA. `queue` and `approved` are a cache of the journal, so a
restarted inbox (or a second one) rebuilds them and never loses or duplicates an escalation.

    inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                  effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                  rules=[Rule("under $50", lambda r, facts: r["amount"] <= 50)],
                  routes=[Route("large", ["controller", "finance-manager"], lambda i: i["request"]["amount"] > 200, sla=4 * 3600)])
    inbox.submit(request)             # runs now, or waits for a person
    inbox.approve(request_id, "alice")
"""
import time
from .escalation import WHY, closed, diff, explain, latest, record
from .journal import _plain, effect_id_for, open_dispatch

DONE = ("COMMITTED", "DUPLICATE_IGNORED")
ITEM = ("why", "detail", "facts", "reason", "changes", "repairs", "route", "group", "routed_to", "level", "due", "breach")


class Rule:
    """A named check over the request and the facts read for it. False sends it to a person."""
    def __init__(self, name, check):
        self.name, self.check = name, check


class Route:
    """Where an escalation goes. First match wins; chain[0] gets it, and after sla unanswered the next group."""
    def __init__(self, name, chain, when=None, sla=None):
        self.name, self.chain, self.when, self.sla = name, list(chain), when, sla


DEFAULT = Route("default", [None])


class Authority:
    """The lease store the gate consults for approvals: is this authority good right now?"""
    def __init__(self, approvers=(), max_age=None, groups=None, clock=time.time):
        self.approvers, self.max_age, self.groups, self.clock = set(approvers), max_age, groups, clock

    def members(self, group):
        """None is the approvers. An unknown group has nobody, so a bad route fails closed. Read live."""
        return set(self.approvers) if group is None else set((self.groups or {}).get(group, ()))

    def is_live(self, authority):
        if not isinstance(authority, dict):
            return False
        if authority.get("by") == "policy":
            return True
        fresh = self.max_age is None or self.clock() - authority.get("at", 0) <= self.max_age
        return authority.get("by") in self.members(authority.get("group")) and fresh


def _state(es):
    """Where one inbox chain stands, read from the journal alone."""
    if open_dispatch(es):
        return "SENDING"
    if any(x["kind"] == "COMMITTED" for x in es):
        return "DONE"
    if closed(es):
        return "CLOSED"
    e, d = latest(es)
    if e and not d:
        return "ESCALATED"
    since = es[es.index(d) + 1:] if e else es
    if any(x["kind"] in ("REFUSED", "AMBIGUOUS") and x.get("code") not in ("awaiting_decision", "closed") for x in since):
        return "NEEDS_ESCALATION"
    return "APPROVED" if e else "NEW"


def _by_policy(es):
    sent = [x for x in es if x["kind"] == "DISPATCHED"]
    lease = sent[-1].get("lease") if sent else None
    return isinstance(lease, dict) and lease.get("by") == "policy" and not any(x["kind"] == "ESCALATED" for x in es)


def _unanswered(e, landed=False):
    """A check that e is still the latest escalation and nobody has answered or sent it."""
    def check(es):
        now, d = latest(es)
        if now is None or now["hash"] != e["hash"]:
            return "SUPERSEDED"
        if d or open_dispatch(es) or closed(es) or (landed and any(x["kind"] in ("COMMITTED", "AMBIGUOUS") for x in es)):
            return "ALREADY_DECIDED"
        return None
    return check


class Inbox:
    def __init__(self, gate, capture, effect, rules, routes=(), clock=time.time, name="inbox"):
        self.gate, self.capture, self.effect, self.rules = gate, capture, effect, rules
        self.routes, self.clock, self.name = list(routes) or [DEFAULT], clock, name
        self.queue = {}        # request id -> item waiting for a person
        self.approved = {}     # request id -> approval recorded but not yet executed
        self.cleared = []      # request ids executed with no person involved
        self.sent = {}         # effect id -> (request, sent under policy?); kept for callers, reconcile reads the journal
        self.log = []          # (request id, event) in order, for the viewer
        self.refresh()

    def receipt(self, request_id):
        return self.gate.journal.receipt(effect_id_for({"request_id": request_id}))

    def _proposal(self, request, authority, facts):
        return {"agent": self.name, "lease": authority, "request_id": request["id"],
                "premises": facts, "effect": self.effect(request), "request": request}

    def _chain(self, request_id):
        return self.gate.journal.entries(effect_id_for({"request_id": request_id}))

    def _request(self, es):
        """The request behind a chain this inbox owns, or None."""
        first = next((x for x in es if x["kind"] == "PROPOSED"), None)
        if first is None or first.get("agent") != self.name:
            return None
        return next((x["request"] for x in es if x["kind"] == "PROPOSED" and "request" in x), None)

    def _chains(self):
        by_effect = {}
        for e in self.gate.journal.entries():
            by_effect.setdefault(e["effect_id"], []).append(e)
        for es in by_effect.values():
            request = self._request(es)
            if request is not None:
                yield request, es

    def _cache(self, request, es):
        request = self._request(es) or request               # show what the journal bound, which is what gets sent
        rid, state = request["id"], _state(es)
        self.queue.pop(rid, None)
        self.approved.pop(rid, None)
        e, d = latest(es)
        if state == "ESCALATED":
            self.queue[rid] = {"request": request, **{k: e[k] for k in ITEM}, "escalation": e["hash"]}
        elif state == "APPROVED":
            self.approved[rid] = {"request": request, "facts": e["facts"],
                                  "authority": {"by": d["by"], "at": d["at"], "group": e["group"], "escalation": e["hash"]}}
        return state

    def _route(self, item):
        return next((r for r in self.routes if r.when is None or r.when(item)), DEFAULT)

    def _write(self, request, check, fields):
        """Append an escalation if check allows, then re-read so the cache matches the journal either way."""
        entry, _ = self.gate.journal.append_if("ESCALATED", effect_id_for({"request_id": request["id"]}), check, **fields)
        self._cache(request, self._chain(request["id"]))
        if entry:
            self.log.append((request["id"], f"queued: {fields['why']}"))
        return entry

    def _refine(self, reason, es):
        """A gate lease refusal of a person's approval says which way it lapsed."""
        lease = next((x.get("lease") for x in reversed(es) if x["kind"] == "PROPOSED"), None)
        if reason != "lease" or not isinstance(lease, dict) or lease.get("by") == "policy":
            return reason
        max_age = self.gate.leases.max_age
        if max_age is not None and self.clock() - lease.get("at", 0) > max_age:
            return "approval_expired"
        if lease.get("by") not in self.gate.leases.members(lease.get("group")):
            return "approver_removed"
        return reason

    def _escalate(self, request, es, facts=None, failed=None):
        """
        Open the one escalation this chain is owed: a rule failed, or the gate refused or could not verify it.
        Routed and captured for the bound request, not a retry's. A refusal's repairs are kept only while the
        facts read now are the world they were computed on.
        """
        bound = self._request(es)
        if bound is not None and bound != _plain(request):
            request, facts = bound, None
        facts = _plain(self.capture(request) if facts is None else facts)
        if failed:
            want, reason, detail, changes, repairs = "NEW", "needs_judgment", failed, [], []
        else:
            esc, e = explain(es), latest(es)[0]
            want, reason, detail = "NEEDS_ESCALATION", self._refine(esc["reason"], es), esc["status"]
            shown = (e["facts"] if e else next(x.get("premises") for x in es if x["kind"] == "PROPOSED")) or {}
            then = {**shown, **{c["field"]: c["now"] for c in esc["changes"]}}
            changes, repairs = esc["changes"] or diff(shown, facts), esc["repairs"] if facts == then else []
        route = self._route({"request": request, "facts": facts, "reason": reason, "detail": detail})
        at, group = self.clock(), route.chain[0]
        fields = record("ESCALATED", at=at, reason=reason, why=WHY.get(reason, WHY["refused"]), detail=detail,
                        facts=facts, changes=changes, repairs=repairs, route=route.name, group=group,
                        routed_to=sorted(self.gate.leases.members(group)), level=0,
                        due=None if route.sla is None else at + route.sla, breach=False)
        return self._write(request, lambda es: None if _state(es) == want else "moved", fields)

    def _send(self, request, authority, facts):
        self.sent[effect_id_for({"request_id": request["id"]})] = (request, authority.get("by") == "policy")
        status = self.gate.submit(self._proposal(request, authority, facts))
        self.log.append((request["id"], status))
        if status not in DONE and status != "IN_FLIGHT" and not status.startswith("UNRESOLVED"):   # recovery owns those
            es = self._chain(request["id"])
            if self._cache(request, es) == "NEEDS_ESCALATION":
                self._escalate(request, es)
        return status

    def submit(self, request):
        """Send it if every rule passes; otherwise it waits for a person. A request already in the journal is not decided again."""
        return self._submit(request)

    def _submit(self, request, facts=None):
        """submit, on the given facts when a repair was computed from them, so the gate checks exactly those."""
        rid, es = request["id"], self._chain(request["id"])
        state = self._cache(request, es)
        if state == "NEEDS_ESCALATION":
            self._escalate(request, es)
        if state in ("NEEDS_ESCALATION", "ESCALATED"):
            return "QUEUED"
        if state != "NEW":
            return {"APPROVED": "APPROVED", "CLOSED": "CLOSED", "DONE": "DUPLICATE_IGNORED", "SENDING": "IN_FLIGHT"}[state]
        bound = next((x["premises"] for x in es if x["kind"] == "PROPOSED" and x.get("lease") is None), None)
        if facts is None:                                     # a crash after binding: decide on the facts it was bound
            facts = self.capture(request) if bound is None else bound   # with, as it would have been without the crash
        failed = [r.name for r in self.rules if not r.check(request, facts)]
        if not failed:
            status = self._send(request, {"by": "policy", "rules": [r.name for r in self.rules]}, facts)
            if status == "COMMITTED" and rid not in self.cleared:
                self.cleared.append(rid)
            return status
        eid = effect_id_for({"request_id": rid})
        if not es:                                            # bind the payload before a person sees it (I5)
            _, moved = self.gate.journal.append_if("PROPOSED", eid, lambda es: "moved" if es else None, agent=self.name,
                                                   lease=None, premises=facts, effect=self.effect(request), request=request)
            if moved:
                return self._submit(request, facts)
        if not self._escalate(request, self.gate.journal.entries(eid), facts, failed):
            return self._submit(request, facts)
        return "QUEUED"

    def _pending(self, request_id, by, seen, ambiguous=True):
        """(entries, open escalation, its group's members, refusal) for a person about to answer it."""
        if by == "policy":
            raise ValueError('"policy" is reserved for sends made by the rules; approvals need a person\'s name')
        es = self._chain(request_id)
        e = latest(es)[0]
        if not es or _state(es) != "ESCALATED":
            return es, e, None, "ALREADY_DECIDED"
        if seen is not None and seen != e["hash"]:
            return es, e, None, "SUPERSEDED"
        if not ambiguous and e["reason"] == "ambiguous":
            return es, e, None, "REFUSED:ambiguous"
        members = self.gate.leases.members(e["group"])
        return es, e, members, None if by in members else "REFUSED:lease"

    def _decide(self, request_id, e, by, decision, members, repair=None):
        return self.gate.journal.append_if(
            "DECIDED", effect_id_for({"request_id": request_id}), _unanswered(e, landed=decision == "repair"),
            **record("DECIDED", at=self.clock(), by=by, decision=decision, escalation=e["hash"], group=e["group"],
                     members=sorted(members), repair=repair))

    def approve(self, request_id, by, execute=True, seen=None, _repair=None):
        """Record a person's approval against the facts they saw. execute=False sends it later."""
        es, e, members, refusal = self._pending(request_id, by, seen, ambiguous=False)
        if refusal:
            return refusal
        d, blocker = self._decide(request_id, e, by, "approve", members, _repair)
        if blocker:
            return blocker
        self.queue.pop(request_id, None)
        self.approved[request_id] = {"request": self._request(es), "facts": e["facts"],
                                     "authority": {"by": by, "at": d["at"], "group": e["group"], "escalation": e["hash"]}}
        self.log.append((request_id, f"approved by {by}"))
        return self.execute(request_id) if execute else "APPROVED"

    def execute(self, request_id):
        a = self.approved.pop(request_id)
        return self._send(a["request"], a["authority"], a["facts"])

    def execute_approved(self):
        return {rid: self.execute(rid) for rid in list(self.approved)}

    def reject(self, request_id, by, seen=None):
        _, e, members, refusal = self._pending(request_id, by, seen)
        if refusal:
            return refusal
        _, blocker = self._decide(request_id, e, by, "reject", members)
        if blocker:
            return blocker
        self.queue.pop(request_id, None)
        self.log.append((request_id, f"rejected by {by}"))
        return "REJECTED"

    def repair(self, request_id, by, index=0, seen=None, execute=True):
        """
        Accept a suggested repair. A different payload is a new request with its own effect id, sent only if
        the rules or a person of its routed group pass it, and only on the facts the repair was computed from.
        """
        es, e, members, refusal = self._pending(request_id, by, seen)
        if refusal:
            return refusal
        if not 0 <= index < len(e["repairs"]):
            return "REFUSED:no_repair"
        r = e["repairs"][index]
        if not r["set"]:                                      # same payload: an approval, recorded as the accepted repair
            return self.approve(request_id, by, execute, seen=e["hash"],
                                _repair={"code": r["code"], "set": {}, "request_id": request_id})
        request = self._request(es)
        child = {**request, **r["set"], "id": f"{request_id}:repair:{e['hash'][:8]}", "repair_of": request_id}
        if _plain(self.effect(child)) != _plain({**self.effect(request), **r["set"]}):
            return "REFUSED:repair_not_expressible"
        facts = _plain(self.capture(child))
        if facts != e["facts"]:                               # the suggestion is stale: show the change, suggest nothing
            self._write(request, _unanswered(e), record(
                "ESCALATED", at=self.clock(), reason=e["reason"], why=e["why"], detail=e["detail"], facts=facts,
                changes=diff(e["facts"], facts), repairs=[], route=e["route"], group=e["group"],
                routed_to=sorted(members), level=e["level"], due=e["due"], breach=False))
            return "SUPERSEDED"
        _, blocker = self._decide(request_id, e, by, "repair", members,
                                  {"code": r["code"], "set": r["set"], "request_id": child["id"]})
        if blocker:
            return blocker
        self.queue.pop(request_id, None)
        self.log.append((request_id, f"repaired by {by}: {r['code']}"))
        status = self._submit(child, facts)
        if status == "QUEUED" and by in self.gate.leases.members(latest(self._chain(child["id"]))[0]["group"]):
            return self.approve(child["id"], by, execute)
        return status

    def _each(self, request, step):
        """One request's step. If it raises (say its order cannot be read), log it and go on, as gate.recover() does."""
        try:
            return step()
        except Exception as e:
            self.log.append((request["id"], f"UNRESOLVED:{type(e).__name__}"))
            return None

    def tick(self):
        """Move each escalation unanswered past its SLA to the next group of its route; at the top, record the breach once."""
        out, now = {}, self.clock()
        for request, es in self._chains():
            moved = self._each(request, lambda: self._tick(request, es, now))
            if moved:
                out[request["id"]] = moved
        return out

    def _tick(self, request, es, now):
        e = latest(es)[0]
        if _state(es) != "ESCALATED" or e["due"] is None or e["due"] > now:
            return None
        route = next((r for r in self.routes if r.name == e["route"]), None)
        chain = route.chain if route else [e["group"]]
        up = e["level"] + 1 < len(chain)
        group, level = (chain[e["level"] + 1], e["level"] + 1) if up else (e["group"], e["level"])
        facts = _plain(self.capture(request))
        fields = record("ESCALATED", at=now, reason=e["reason"], why=e["why"], detail=e["detail"], facts=facts,
                        changes=diff(e["facts"], facts) or e["changes"],
                        repairs=e["repairs"] if facts == e["facts"] else [], route=e["route"], group=group,
                        routed_to=sorted(self.gate.leases.members(group)), level=level,
                        due=now + route.sla if up and route.sla is not None else None, breach=True)
        if self._write(request, _unanswered(e), fields):
            return group if up else "BREACHED"
        return None

    def refresh(self):
        """Rebuild queue, approvals and cleared from the journal, and finish whatever a crash left half done."""
        self.queue, self.approved, self.cleared = {}, {}, []
        for request, es in self._chains():
            self._each(request, lambda: self._refresh(request, es))

    def _refresh(self, request, es):
        state = self._cache(request, es)
        if state == "NEEDS_ESCALATION":
            self._escalate(request, es)
        elif state == "NEW":
            self._submit(request)
        elif state == "CLOSED":
            c = closed(es)
            if c["decision"] == "repair" and not self._chain(c["repair"]["request_id"]):
                child = {**request, **c["repair"]["set"], "id": c["repair"]["request_id"], "repair_of": request["id"]}
                self._submit(child, next(x["facts"] for x in es if x.get("hash") == c["escalation"]))
        elif state == "DONE" and _by_policy(es):
            self.cleared.append(request["id"])

    def reconcile(self, recovered):
        """After gate.recover(): confirmed policy sends are cleared; anything recovery could not confirm goes to a person, once."""
        for eid, status in recovered.items():
            es = self.gate.journal.entries(eid)
            request = self._request(es)
            if request is None:
                continue                                   # not ours (another inbox on the same journal)
            self.log.append((request["id"], status))
            if status.startswith("COMMITTED") or status == "REAPPLIED_AFTER_QUERY":
                if _by_policy(es) and request["id"] not in self.cleared:
                    self.cleared.append(request["id"])
            elif status != "IN_FLIGHT" and not status.startswith("UNRESOLVED"):
                if self._cache(request, es) == "NEEDS_ESCALATION":
                    self._each(request, lambda: self._escalate(request, es))
