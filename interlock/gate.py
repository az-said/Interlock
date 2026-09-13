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
    I2  no duplicate effect (an effect id reaches COMMITTED at most once)
    I3  no stale premise lands (premises re-validated against the target at commit)
    I4  no effect under a dead lease (lease checked at dispatch, not just proposal)
    I5  payload binding: once a decision is recorded for an effect id, a later proposal
        with the same id and a different payload is rejected, never silently applied.
        (A model that re-decides "$30" on retry cannot replace the recorded "$20".)
    I6  no duplicate implementation: an effect that defines a symbol already defined,
        or claimed by another live agent, is refused (MAST's top failure mode, step
        repetition, caught with zero model calls)
    P   progress: valid proposals commit; recovery resolves every in-flight effect
        to COMMITTED or AMBIGUOUS, and never re-applies blindly
"""
from .journal import Journal, effect_id_for


class SimulatedCrash(Exception):
    """Raised by a target AFTER the effect exists but BEFORE the ack returns."""


class Gate:
    def __init__(self, target, journal_path, leases):
        self.target = target
        self.journal = Journal(journal_path)
        self.leases = leases
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

    def submit(self, proposal, crash_after_effect=False, crash_before_effect=False):
        eid = effect_id_for(proposal)
        recorded = self.journal.recorded_effect(eid)
        self.journal.append("PROPOSED", eid, agent=proposal["agent"],
                            premises=proposal["premises"], effect=proposal["effect"])

        if recorded is not None and recorded != proposal["effect"]:    # I5
            self.journal.append("REFUSED", eid, reason="payload differs from recorded decision",
                                recorded=recorded, offered=proposal["effect"])
            return "REFUSED:conflicting_payload"

        if self.journal.has("COMMITTED", eid):                          # I2
            return "DUPLICATE_IGNORED"

        for sym in proposal.get("defines", []):                         # I6
            holder = self.claims.get(sym)
            if (holder and holder != proposal["agent"]) or sym in getattr(self.target, "symbol_table", lambda: {})():
                self.journal.append("REFUSED", eid, reason=f"{sym} already defined or claimed by {holder}")
                return "REFUSED:duplicate_symbol"

        if not self.leases.is_live(proposal["lease"]):                  # I4
            self.journal.append("REFUSED", eid, reason="lease not live")
            return "REFUSED:lease"
        self.journal.append("AUTHORIZED", eid, lease=proposal["lease"])

        violated = self.target.validate_premises(proposal["premises"])  # I3
        if violated:
            self.journal.append("REFUSED", eid, reason=violated)
            return "REFUSED:stale_premise"

        self.journal.append("DISPATCHED", eid, effect=proposal["effect"])   # I1
        if crash_before_effect:
            raise SimulatedCrash(eid)          # in-flight marker written, request never sent
        self.target.apply(eid, proposal["effect"], crash_after_effect)  # may raise SimulatedCrash
        self.journal.append("COMMITTED", eid)
        self._release(proposal["agent"])
        return "COMMITTED"

    def recover(self):
        """
        After a crash. For each DISPATCHED-without-COMMITTED, act by tier.
        This is where the guarantee either holds or is honestly lost.
        """
        out = {}
        for eid in self.journal.in_flight():
            effect = [e for e in self.journal.entries(eid) if e["kind"] == "DISPATCHED"][-1]["effect"]
            tier = self.target.tier
            if tier == 1:
                self.target.apply(eid, effect)                  # idempotent: safe to retry
                self.journal.append("COMMITTED", eid, via="retry-idempotent")
                out[eid] = "COMMITTED_BY_RETRY"
            elif tier == 2:
                if self.target.query(eid, effect):              # ask the target what it has
                    self.journal.append("COMMITTED", eid, via="recovery-query")
                    out[eid] = "COMMITTED_ON_QUERY"
                else:
                    self.target.apply(eid, effect)
                    self.journal.append("COMMITTED", eid, via="recovery-reapply")
                    out[eid] = "REAPPLIED_AFTER_QUERY"
            else:
                self.journal.append("AMBIGUOUS", eid)           # cannot know; refuse to guess
                out[eid] = "AMBIGUOUS"
        return out

    def receipt(self, proposal):
        return self.journal.receipt(effect_id_for(proposal))


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

    def recover(self):
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

    def recover(self):
        return {}      # no journal; the caller retries with the same key
