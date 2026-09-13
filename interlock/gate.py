"""
The commit gate: the only path by which an effect reaches the world.

A proposal:

    {"agent": "B",
     "lease": "L-B",
     "premises": {...},   # what the agent assumed, captured at decision time
     "effect": {...}}     # what it wants done (target-specific payload)

The gate is generic over an EffectTarget (see targets/). A target declares
how much it cooperates:

    tier 1  dedupes on the effect id             -> safe retry, exactly-once effect
    tier 2  no dedup, but queryable by effect id  -> exactly-once with a recovery read
    tier 3  neither                               -> crash-before-ack is undecidable;
                                                     the gate can only refuse to guess

Invariants (the correctness contract):

    I1  no effect without a journaled decision (DISPATCHED on disk before apply)
    I2  no duplicate effect (an effect id reaches COMMITTED at most once, and is never sent
        while an earlier send of it is unresolved, by this worker or any other)
    I3  no stale premise lands (premises re-validated against the target at commit)
    I4  no effect under a dead lease (lease checked at dispatch, not just proposal)
    I5  payload binding: once a decision is recorded for an effect id, a later proposal
        with the same id and a different payload is rejected, never silently applied.
        (A model that re-decides "$30" on retry cannot replace the recorded "$20".)
    I6  no duplicate implementation: an effect that defines a symbol already defined,
        or claimed by another live agent, is refused (MAST's top failure mode, step
        repetition, caught with zero model calls)
    I7  decision binding: once an effect has been escalated it is dispatched only under a person's
        recorded approval of its LATEST escalation, by a member of that escalation's group (checked
        when deciding and again at dispatch), with that escalation's facts as premises. Policy never
        sends it again.
    I8  repairs are new decisions: a repair with a different payload is a new effect id, accepted only
        while the original never landed, and accepting it closes the original. A closed effect is never
        dispatched.
    P'  every refused or unverifiable outcome of an inbox-owned effect ends in exactly one open
        escalation, derived from the journal, so a crash or a second inbox can neither lose nor
        duplicate it.
    P   progress: valid proposals commit; recovery resolves every in-flight effect
        to COMMITTED, REFUSED or AMBIGUOUS, re-checks lease and premises before any
        resend (the outage is when the world moves), and never re-applies blindly

Premises are bound to a decision under an authority. A retry under the same lease is
checked against the premises the decision was first recorded with; a new authority (a
person approving after a refusal) is a new decision and brings the facts that person saw.
Recovery re-checks exactly the lease and premises the send was dispatched under.

Every send holds a claim on its effect until it is resolved. Recovery takes an effect
over only after that claim expires (claim_ttl), so an effect still being applied is
never sent a second time. Targets must time out well inside claim_ttl.
"""
import os, socket, time, uuid
from .escalation import WHY
from .journal import CLAIM_TTL, _plain, effect_id_for, open_dispatch, open_journal

DEDUP_MARGIN = 600      # seconds of clock skew allowed for: a dedup key this close to expiry counts as expired


def _nonempty(**fields):
    """Old receipts stay byte-identical: a refusal only gains changes/repairs keys when there are some."""
    return {k: v for k, v in fields.items() if v}


class SimulatedCrash(Exception):
    """Raised by a target AFTER the effect exists but BEFORE the ack returns."""


class Gate:
    """
    `journal_path` ending in .db / .sqlite shares one SQLite journal across workers:
    an effect is dispatched by exactly one of them and recovered by exactly one of them.
    Any other path is a JSONL file, safe across processes on one machine.
    """
    def __init__(self, target, journal_path, leases, claim_ttl=CLAIM_TTL):
        self.target = target
        self.journal = open_journal(journal_path)
        self.leases = leases
        self.claim_ttl = claim_ttl
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.sender = self.owner + "/send"     # a separate owner, so even this gate's recover() waits out its own sends
        self.claims = {}                       # symbol -> agent holding an unreleased claim

    def claim(self, agent, symbol):
        """Declare intent to write a symbol. Returns the other claimant, or None."""
        holder = self.claims.get(symbol)
        if holder and holder != agent:
            return holder
        self.claims[symbol] = agent
        return None

    def _release(self, agent):
        for s in [s for s, a in self.claims.items() if a == agent]:
            del self.claims[s]

    @property
    def _queryable(self):
        return getattr(self.target, "queryable", self.target.tier == 2)

    def submit(self, proposal, crash_after_effect=False, crash_before_effect=False):
        eid = effect_id_for(proposal)
        effect, lease = _plain(proposal["effect"]), _plain(proposal["lease"])
        prior = self.journal.entries(eid)
        kinds = [e["kind"] for e in prior]
        request = {"request": proposal["request"]} if "request" in proposal else {}
        if open_dispatch(prior):                                        # being sent, or crashed mid-effect:
            return "IN_FLIGHT"                                          # recover() decides, a resend doesn't

        recorded = next((e.get("effect") for e in prior if e["kind"] == "PROPOSED"), None)
        if recorded is not None and recorded != effect:                 # I5
            self.journal.append("PROPOSED", eid, agent=proposal["agent"], lease=lease,
                                premises=proposal["premises"], effect=effect, **request)
            self.journal.append("REFUSED", eid, code="conflicting_payload", reason="payload differs from recorded decision",
                                recorded=recorded, offered=effect)
            return "REFUSED:conflicting_payload"

        if "AMBIGUOUS" in kinds:                                        # P: never resend what nobody can confirm
            return "AMBIGUOUS"
        if "COMMITTED" in kinds:                                        # I2
            return "DUPLICATE_IGNORED"

        # A retry under the same authority is checked against the premises it was decided on;
        # re-reading the world at retry time would bless a change the decision never saw.
        decided_on = next((e["premises"] for e in prior if e["kind"] == "PROPOSED" and e.get("lease") == lease),
                          proposal["premises"])
        self.journal.append("PROPOSED", eid, agent=proposal["agent"], lease=lease,
                            premises=proposal["premises"], effect=effect, **request)

        for sym in proposal.get("defines", []):                         # I6
            holder = self.claims.get(sym)
            if (holder and holder != proposal["agent"]) or sym in getattr(self.target, "symbol_table", lambda: {})():
                self.journal.append("REFUSED", eid, code="duplicate_symbol", reason=f"{sym} already defined or claimed by {holder}")
                return "REFUSED:duplicate_symbol"

        checks = self._lease_seen(lease, effect)                        # I4
        if not checks["lease_live"]:
            self.journal.append("REFUSED", eid, code="lease", reason="lease not live, or it does not cover this effect", checks=checks)
            return "REFUSED:lease"
        self.journal.append("AUTHORIZED", eid, lease=lease)

        checks["violations"], changes, repairs = self._premises(decided_on, eid, effect)     # I3
        if checks["violations"]:
            self.journal.append("REFUSED", eid, code="stale_premise", reason=checks["violations"], checks=checks,
                                **_nonempty(changes=changes, repairs=repairs))
            return "REFUSED:stale_premise"

        blocker = self.journal.dispatch(eid, effect, self.sender, self.claim_ttl, lease=lease, premises=decided_on,
                                        checks=checks)                  # I1, I7, I8: atomic across workers
        if blocker == "conflicting_payload":                            # another worker recorded a different decision first
            self.journal.append("REFUSED", eid, code="conflicting_payload", reason="payload differs from a decision recorded concurrently")
            return "REFUSED:conflicting_payload"
        if blocker in ("closed", "awaiting_decision"):                  # a person owns this effect now
            self.journal.append("REFUSED", eid, code=blocker, reason=WHY[blocker])
            return f"REFUSED:{blocker}"
        if blocker:
            return {"committed": "DUPLICATE_IGNORED", "ambiguous": "AMBIGUOUS"}.get(blocker, "IN_FLIGHT")

        try:
            if crash_before_effect:
                raise SimulatedCrash(eid)          # in-flight marker written, request never sent
            result = self.target.apply(eid, effect, crash_after_effect)  # may raise SimulatedCrash
        except SimulatedCrash:
            self.journal.release(eid, self.sender)  # a simulated death ends the process's claim; a real one waits out claim_ttl
            raise
        self.journal.append("COMMITTED", eid, result=result)
        self.journal.release(eid, self.sender)
        self._release(proposal["agent"])
        return "COMMITTED"

    def _lease_seen(self, lease, effect):
        """
        The lease check as observed: live (and, for a store with allows(lease, effect), covering this
        effect), plus the store's own record of the grant when it has describe(lease).
        """
        allows, describe = getattr(self.leases, "allows", None), getattr(self.leases, "describe", None)
        return {"lease_live": bool(allows(lease, effect) if allows else self.leases.is_live(lease)),
                "lease": describe(lease) if describe else None}

    def _resend(self, eid, effect):
        self.journal.claim(eid, self.owner, self.claim_ttl)   # refresh: the resend must finish inside the claim
        try:
            return self.target.apply(eid, effect)
        except Exception as e:
            e.interlock_sent = True     # the request may have reached the target: recover() keeps the claim
            raise

    def _premises(self, premises, eid, effect):
        """(violations, changes, repairs) from one read: target.explain when it has one, else validate_premises."""
        explain = getattr(self.target, "explain", None)
        if explain is None:
            return self.target.validate_premises(premises, eid), [], []
        out = explain(premises, eid, effect)
        return out["violations"], out["changes"], out["repairs"]

    def _recheck(self, dispatched):
        """
        I4 and I3 again, against the lease and premises this send was dispatched under. Returns the
        observed checks (recorded on whatever recovery writes next), what failed ("lease",
        "stale_premise" or None), and the target's changes and repairs. violations are only read
        when the lease holds.
        """
        checks = self._lease_seen(dispatched.get("lease"), dispatched["effect"])
        if not checks["lease_live"]:
            return checks, "lease", [], []
        checks["violations"], changes, repairs = self._premises(dispatched.get("premises"), dispatched["effect_id"],
                                                                dispatched["effect"])
        return checks, "stale_premise" if checks["violations"] else None, changes, repairs

    def recover(self, now=None, only=None):
        """
        After a crash. For each DISPATCHED-without-COMMITTED, act by tier.
        This is where the guarantee either holds or is honestly lost.

        Before sending anything again, re-check lease and premises: while the agent was
        down a human may have refunded the order by hand, or the grant may be gone.
        Tier 1 is only tier 1 inside the provider's dedup window (Stripe: 24h); after
        it, a retry is a new request, so fall back to a lookup or to AMBIGUOUS.

        An effect is recovered only by whoever claims it, and only once any earlier claim
        (a send still in progress, or another recoverer) has expired. An effect whose
        recovery raises is reported UNRESOLVED and left for a later attempt; the rest go on.
        `only` limits recovery to the given effect ids.
        """
        now = time.time() if now is None else now
        out = {}
        for eid in self.journal.in_flight():
            if only is not None and eid not in only:
                continue
            if not self.journal.claim(eid, self.owner, self.claim_ttl):
                continue                                        # being sent or recovered by someone else
            try:
                status = self._recover_one(eid, now)
            except Exception as e:                              # one bad effect must not strand the others
                status = f"UNRESOLVED:{type(e).__name__}"
                if not getattr(e, "interlock_sent", False):     # nothing was sent: the next attempt may go now
                    self.journal.release(eid, self.owner)
            else:
                self.journal.release(eid, self.owner)
            if status:
                out[eid] = status
        return out

    def _recover_one(self, eid, now):
        es = self.journal.entries(eid)
        if not open_dispatch(es):
            return None                                         # resolved while we were claiming
        d = [e for e in es if e["kind"] == "DISPATCHED"][-1]
        effect, tier, queryable = d["effect"], self.target.tier, self._queryable
        if tier == 1 and now - d["ts"] > getattr(self.target, "dedup_window", float("inf")) - DEDUP_MARGIN:
            tier = 2 if queryable else 3                        # provider forgot (or may have forgotten) the key
        if tier == 3:
            self.journal.append("AMBIGUOUS", eid, code="ambiguous")   # cannot know; refuse to guess
            return "AMBIGUOUS"
        checks, stale, changes, repairs = self._recheck(d)
        if tier == 1 and not stale:
            result = self._resend(eid, effect)                  # idempotent: safe to retry
            self.journal.append("COMMITTED", eid, via="retry-idempotent", rechecked=checks, result=result)
            return "COMMITTED_BY_RETRY"
        if not queryable:                                       # stale, and no way to see what landed: no repairs
            self.journal.append("AMBIGUOUS", eid, code="ambiguous", reason=f"{stale} at recovery, no lookup", rechecked=checks,
                                **_nonempty(changes=changes))
            return "AMBIGUOUS"
        found = self.target.query(eid, effect)                  # ask the target what it has
        if found:                                               # the earlier send landed; a failed re-check does not undo it
            self.journal.append("COMMITTED", eid, via="recovery-query", rechecked=checks, found=found)
            return "COMMITTED_ON_QUERY"
        if stale:
            self.journal.append("REFUSED", eid, code=f"{stale}_at_recovery", reason=f"{stale} at recovery", resolves=True, rechecked=checks,
                                **_nonempty(changes=changes, repairs=repairs))   # the lookup found nothing landed
            return f"REFUSED:{stale}_at_recovery"
        result = self._resend(eid, effect)
        self.journal.append("COMMITTED", eid, via="recovery-reapply", rechecked=checks, result=result)
        return "REAPPLIED_AFTER_QUERY"

    def settle_failed(self, eid, reason):
        """
        The target answered that the send failed (for example an MCP tool returned isError).
        Settle it without resending: confirm by lookup when possible, otherwise take the
        target at its word. Returns the new status, or None if the effect was not in flight.
        """
        es = self.journal.entries(eid)
        if not open_dispatch(es):
            return None
        d = [e for e in es if e["kind"] == "DISPATCHED"][-1]
        if self._queryable and self.target.query(eid, d["effect"]):
            self.journal.append("COMMITTED", eid, via="failed-but-landed")
            status = "COMMITTED_ON_QUERY"
        else:
            self.journal.append("REFUSED", eid, code="target_error", reason=f"target reported failure: {reason}", resolves=True)
            status = "REFUSED:target_error"
        self.journal.release(eid, self.sender)
        return status

    def receipt(self, proposal):
        return self.journal.receipt(effect_id_for(proposal))

    def receipt_bundle(self, proposal, key=None):
        """Every journal entry for this effect, hash-chained and optionally signed. See receipts.verify()."""
        from .receipts import bundle
        return bundle(self.journal, effect_id_for(proposal), key)


class Naive:
    """
    Baseline 1: what every agent framework does today.
    No journal, no premises, no lease re-check. A retry is "do it again",
    and a re-run re-asks the model, so the retry may carry a different payload.
    """
    def __init__(self, target):
        self.target = target

    def submit(self, proposal, crash_after_effect=False, crash_before_effect=False):
        import uuid
        if crash_before_effect:
            raise SimulatedCrash("naive")
        self.target.apply(uuid.uuid4().hex[:12], proposal["effect"], crash_after_effect)  # fresh id per attempt
        return "APPLIED"

    def recover(self, now=None):
        return {}      # no memory; the caller just retries


class IdempotencyOnly:
    """
    Baseline 2: the conventional durable operation. A stable idempotency key
    (the approved request id) sent to a cooperating service, no agent runtime.
    This is "just use Stripe idempotency keys". It establishes what the service
    alone gives you, so the agent runtime's additions are measured, not assumed.
    """
    def __init__(self, target):
        self.target = target

    def submit(self, proposal, crash_after_effect=False, crash_before_effect=False):
        if crash_before_effect:
            raise SimulatedCrash("idem")
        return "APPLIED:" + str(self.target.apply(effect_id_for(proposal), proposal["effect"],
                                                  crash_after_effect).get("status"))

    def recover(self, now=None):
        return {}      # no journal; the caller retries with the same key


class DurableExecution:
    """
    Baseline 3: Temporal, DBOS, Restate, used the way their docs recommend for a step
    with a side effect. A completed step's result is recorded and replayed, so a re-run
    model or a duplicate delivery gets the recorded result, not a second effect. A step
    that dies before its result is recorded is re-run (at-least-once) with a stable
    idempotency key. No lease or premise check: the engine replays the decision it
    already made. Run it against a tier-1 target, its best case.
    """
    def __init__(self, target):
        self.target = target
        self.completed = {}    # effect id -> recorded result (the event history)
        self.started = {}      # effect id -> effect, for steps with no recorded result

    def submit(self, proposal, crash_after_effect=False, crash_before_effect=False):
        eid = effect_id_for(proposal)
        if eid in self.completed:
            return "REPLAYED:" + self.completed[eid]
        self.started[eid] = proposal["effect"]
        if crash_before_effect:
            raise SimulatedCrash(eid)
        status = str(self.target.apply(eid, proposal["effect"], crash_after_effect).get("status"))
        self.completed[eid] = status
        del self.started[eid]
        return "COMPLETED:" + status

    def recover(self, now=None):
        out = {}
        for eid, effect in list(self.started.items()):     # at-least-once: re-run the step
            out[eid] = "RERUN:" + str(self.target.apply(eid, effect).get("status"))
            self.completed[eid] = out[eid]
            del self.started[eid]
        return out
