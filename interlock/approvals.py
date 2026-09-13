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

    inbox = Inbox(gate, capture=lambda r: api.capture(r["order"]),
                  effect=lambda r: {"order": r["order"], "amount": r["amount"]},
                  rules=[Rule("under $50", lambda r, facts: r["amount"] <= 50)])
    inbox.submit(request)             # runs now, or waits for a person
    inbox.approve(request_id, "alice")
"""
import time
from .journal import effect_id_for

DONE = ("COMMITTED", "DUPLICATE_IGNORED")


class Rule:
    """A named check over the request and the facts read for it. False sends it to a person."""
    def __init__(self, name, check):
        self.name, self.check = name, check


class Authority:
    """The lease store the gate consults for approvals: is this authority good right now?"""
    def __init__(self, approvers=(), max_age=None):
        self.approvers, self.max_age = set(approvers), max_age

    def is_live(self, authority):
        if not isinstance(authority, dict):
            return False
        if authority.get("by") == "policy":
            return True
        fresh = self.max_age is None or time.time() - authority.get("at", 0) <= self.max_age
        return authority.get("by") in self.approvers and fresh


class Inbox:
    def __init__(self, gate, capture, effect, rules):
        self.gate, self.capture, self.effect, self.rules = gate, capture, effect, rules
        self.queue = {}        # request id -> item waiting for a person
        self.approved = {}     # request id -> approval recorded but not yet executed
        self.cleared = []      # request ids executed with no person involved
        self.sent = {}         # effect id -> (request, sent under policy?), for reconcile()
        self.log = []          # (request id, event) in order, for the viewer

    def receipt(self, request_id):
        return self.gate.journal.receipt(effect_id_for({"request_id": request_id}))

    def _proposal(self, request, authority, facts):
        return {"agent": "inbox", "lease": authority, "request_id": request["id"],
                "premises": facts, "effect": self.effect(request)}

    def _enqueue(self, request, why, detail):
        self.queue[request["id"]] = {"request": request, "why": why, "detail": detail,
                                     "facts": self.capture(request)}   # what the approver will see
        self.log.append((request["id"], f"queued: {why}"))

    def _send(self, request, authority, facts):
        self.sent[effect_id_for({"request_id": request["id"]})] = (request, authority.get("by") == "policy")
        status = self.gate.submit(self._proposal(request, authority, facts))
        self.log.append((request["id"], status))
        if status not in DONE:
            self._enqueue(request, "could not be sent safely", status)
        return status

    def submit(self, request):
        """Send it if every rule passes; otherwise it waits for a person."""
        facts = self.capture(request)
        failed = [r.name for r in self.rules if not r.check(request, facts)]
        if failed:
            self._enqueue(request, "needs judgment", failed)
            return "QUEUED"
        status = self._send(request, {"by": "policy", "rules": [r.name for r in self.rules]}, facts)
        if status == "COMMITTED":
            self.cleared.append(request["id"])
        return status

    def approve(self, request_id, by, execute=True):
        """Record a person's approval against the facts they saw. execute=False sends it later."""
        item = self.queue.pop(request_id)
        self.approved[request_id] = {"request": item["request"], "facts": item["facts"],
                                     "authority": {"by": by, "at": time.time()}}
        self.log.append((request_id, f"approved by {by}"))
        return self.execute(request_id) if execute else "APPROVED"

    def execute(self, request_id):
        a = self.approved.pop(request_id)
        return self._send(a["request"], a["authority"], a["facts"])

    def execute_approved(self):
        return {rid: self.execute(rid) for rid in list(self.approved)}

    def reject(self, request_id, by):
        self.queue.pop(request_id)
        self.log.append((request_id, f"rejected by {by}"))
        return "REJECTED"

    def reconcile(self, recovered):
        """After gate.recover(): confirmed sends are done; anything recovery could not confirm goes to a person."""
        for eid, status in recovered.items():
            if eid not in self.sent:
                continue                                   # not ours (another inbox on the same journal)
            request, by_policy = self.sent[eid]
            self.log.append((request["id"], status))
            if status.startswith("COMMITTED") or status == "REAPPLIED_AFTER_QUERY":
                if by_policy and request["id"] not in self.cleared:
                    self.cleared.append(request["id"])
            else:
                self._enqueue(request, "could not be verified after a crash", status)
