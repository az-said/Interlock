"""
The shared cap, made atomic in the journal both bot processes share.

The gate's premise check reads Stripe and then sends: two bots can both read "nothing refunded
yet" and both send. Each bot's refund is its own approved effect (its own effect id), so the
gate's per-effect rules do not stop the second one. What closes the race is making the cap part
of the dispatch decision: CapJournal.dispatch runs inside SQLite's BEGIN IMMEDIATE (one writer
at a time across processes) and refuses a DISPATCHED that would take the case over its cap,
counting every other effect of the case that is in flight, committed or AMBIGUOUS. An effect
refused at recovery never landed, so it gives its reservation back.

This is a scenario-level subclass because gate.py and journal.py are not edited here; the
proposed core change is a `reserve=` hook on dispatch (see results/scenarios/shared_cap.md).
"""
import contextlib, json, time
from interlock.gate import Gate
from interlock.journal import CLAIM_TTL, SqliteJournal, dispatch_blocker, effect_id_for, open_dispatch
from interlock.targets.stripe_api import StripeRefunds

PAID = 10000            # the customer's payment, cents
CAP = 3000              # the case approves at most $30 in refunds, across all bots
BOTS = ("support-bot", "billing-bot")
SETTLED_TTL = 40        # claim ttl: longer than the Stripe client's 30s timeout, as in e2e_live


def case_id(run_id):
    return f"case-4471-{run_id}"


def effect_id(case, bot):
    return effect_id_for({"request_id": f"{case}/{bot}"})


def reserved_cents(entries, case, exclude):
    """Cents other effects of `case` hold against the cap: dispatched and not refused at recovery."""
    by = {}
    for e in entries:
        by.setdefault(e["effect_id"], []).append(e)
    total, holders = 0, {}
    for eid, es in by.items():
        sent = [e for e in es if e["kind"] == "DISPATCHED"]
        if eid == exclude or not sent or sent[-1]["effect"].get("case") != case:
            continue
        if open_dispatch(es) or {"COMMITTED", "AMBIGUOUS"} & {e["kind"] for e in es}:
            total += sent[-1]["effect"]["amount"]
            holders[eid] = sent[-1]["effect"]["amount"]
    return total, holders


class CapJournal(SqliteJournal):
    def __init__(self, path, cap):
        super().__init__(path)
        self.cap = cap

    def dispatch(self, effect_id, effect, owner, ttl=CLAIM_TTL, **data):
        with contextlib.closing(self._connect()) as db:
            db.isolation_level = None
            db.execute("BEGIN IMMEDIATE")            # the cap read and the DISPATCHED write are one step
            entries = [json.loads(b) for (b,) in db.execute("SELECT body FROM entries ORDER BY seq")]
            blocker = dispatch_blocker([e for e in entries if e["effect_id"] == effect_id], effect)
            if blocker:
                db.execute("ROLLBACK")
                return blocker
            reserved, holders = reserved_cents(entries, effect["case"], effect_id)
            if reserved + effect["amount"] > self.cap:
                self._insert(db, "REFUSED", effect_id, {
                    "reason": f"shared cap: {reserved} reserved by other effects + {effect['amount']} > cap {self.cap}",
                    "over_cap": True, "reserved_by_others": holders, "checks": data.get("checks")})
                db.execute("COMMIT")
                return "over_cap"
            self._insert(db, "DISPATCHED", effect_id, {"effect": effect, **data})
            db.execute("INSERT OR REPLACE INTO claims (effect_id, owner, expires) VALUES (?, ?, ?)",
                       (effect_id, owner, time.time() + ttl))
            db.execute("COMMIT")
            return None


class CapGate(Gate):
    def __init__(self, target, journal_path, leases, cap, claim_ttl=SETTLED_TTL):
        super().__init__(target, journal_path, leases, claim_ttl=claim_ttl)
        self.journal = CapJournal(journal_path, cap)

    def submit(self, proposal, **kw):
        status = super().submit(proposal, **kw)
        if status == "IN_FLIGHT" and self.journal.entries(effect_id_for(proposal))[-1].get("over_cap"):
            return "REFUSED:over_cap"             # Gate maps an unknown dispatch blocker to IN_FLIGHT
        return status


class CaseApproval:
    """The case's approval as the gate's lease: live, covering amounts up to the cap."""
    def __init__(self, case, cap):
        self.case, self.cap = case, cap

    def is_live(self, lease):
        return lease == self.case

    def allows(self, lease, effect):
        return lease == self.case and effect.get("case") == self.case and 0 < effect.get("amount", 0) <= self.cap

    def describe(self, lease):
        return {"case": lease, "max_cents": self.cap, "revoked": None}


class CapRefunds(StripeRefunds):
    """Stripe refunds with a headroom premise, and the harness's crash points around the real POST."""
    def __init__(self, client, payment_intent, hook=lambda point: None, log=lambda ev, **kw: None):
        super().__init__(client, payment_intent)
        self.hook, self.log = hook, log

    def capture(self, amount, cap=CAP):
        total = self.refunded_total()
        self.log("capture", refunded=total)
        return {"payment_intent": self.payment_intent, "refunded_by_others": total, "amount": amount, "cap": cap}

    def validate_premises(self, premises, eid=None):
        self.log("check_start")
        others = self._by_others(eid)
        self.log("check_read", refunded_by_others=others)
        if others + premises["amount"] > premises["cap"]:
            return [f"cap headroom: refunded by others {others} + this {premises['amount']} > cap {premises['cap']}"]
        return []

    def apply(self, eid, effect, crash_after_effect=False):
        self.hook("before_send")
        self.log("send")
        out = super().apply(eid, effect)
        self.log("committed", refund=out["refund"], replayed=out["status"] == "already_processed")
        self.hook("after_commit")
        return out


def hand_check_decision(refunds, key, amount, cap):
    """The idiomatic pre-send check: my refund already there? else would this one exceed the cap?"""
    mine = next((r["id"] for r in refunds if r["metadata"].get("key") == key), None)
    if mine:
        return "FOUND_BY_LOOKUP", mine
    total = sum(r["amount"] for r in refunds)
    return ("REFUSED:over_cap", total) if total + amount > cap else ("SEND", total)


def race_mechanism(timeline, crashed, bots=BOTS):
    """
    Measured, for a crashed run of a check-then-send system: when the other bot's check read ran, relative to
    the SIGKILL, the restarted process's own re-read, and the commit of the crashed bot's refund (the one the
    read had to see). None when the other bot never read. Times are seconds after the start barrier.
    """
    other = next(b for b in bots if b != crashed)
    c, r, o = timeline.get(crashed, {}), timeline.get(crashed + " (restart)", {}), timeline.get(other, {})
    if "check_read" not in o or "sigkill" not in c:
        return None
    rival = c.get("committed", r.get("committed"))
    return {"saw_cents": o.get("check_read_refunded"),
            "read_started_before_crash": o["check_start"] < c["sigkill"],
            "read_done_before_crash": o["check_read"] < c["sigkill"],
            "read_done_before_restart_reread": "check_read" in r and o["check_read"] < r["check_read"],
            "read_in_restart_gap": "check_read" in r and r["check_read"] <= o["check_read"] < r.get("committed", 1e9),
            "read_done_before_rival_commit": rival is not None and o["check_read"] < rival}


def ground_truth(refunds, case, cap=CAP):
    """Stripe's refund list for the payment, attributed to bots, and the invariant."""
    eids = {effect_id(case, b): b for b in BOTS}
    live = [r for r in refunds if r["status"] != "failed"]
    rows = [{"id": r["id"], "amount": r["amount"], "status": r["status"],
             "bot": r["metadata"].get("bot") or eids.get(r["metadata"].get("interlock_effect_id"))} for r in live]
    total = sum(r["amount"] for r in rows)
    return {"refunds": rows, "total_cents": total, "count": len(rows), "invariant_held": total <= cap}
