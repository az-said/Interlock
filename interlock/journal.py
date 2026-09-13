"""
The append-only decision log. The one idea everything rests on:

    write what you are about to do, to disk, BEFORE you do it.

Entry kinds (the four facts from the brief, plus the failure states):

    PROPOSED    an agent produced an effect + the premises it relied on
    AUTHORIZED  the lease it holds was live at this instant
    DISPATCHED  we are about to apply the effect  (fsync'd BEFORE applying)
    COMMITTED   the effect is applied and confirmed
    REFUSED     a premise, lease, claim, or payload-binding check failed; nothing applied
    AMBIGUOUS   we crashed mid-effect and cannot determine what happened

Mapping to the team spec's state names (docs/team-notes/refund-spec-shawn.md):
    Prepared = PROPOSED+AUTHORIZED · In flight = DISPATCHED · Confirmed = COMMITTED
    Needs reconciliation = AMBIGUOUS · Rejected = REFUSED

Because DISPATCHED is durable before the effect exists, recovery can always
find "things we started and never confirmed". Nothing else in the system
needs to remember anything.
"""
import hashlib, json, os, time


class Journal:
    def __init__(self, path):
        self.path = path
        open(path, "a").close()

    def append(self, kind, effect_id, **data):
        entry = {"ts": time.time(), "kind": kind, "effect_id": effect_id, **data}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())            # durable before we return
        return entry

    def entries(self, effect_id=None):
        with open(self.path) as f:
            es = [json.loads(l) for l in f if l.strip()]
        return [e for e in es if effect_id is None or e["effect_id"] == effect_id]

    def has(self, kind, effect_id):
        return any(e["kind"] == kind for e in self.entries(effect_id))

    def recorded_effect(self, effect_id):
        """The payload bound to this effect id at first proposal, if any."""
        for e in self.entries(effect_id):
            if e["kind"] == "PROPOSED":
                return e.get("effect")
        return None

    def in_flight(self):
        """effect ids whose latest entry is DISPATCHED: crashed between effect and ack."""
        last = {}
        for e in self.entries():
            last[e["effect_id"]] = e["kind"]
        return [eid for eid, k in last.items() if k == "DISPATCHED"]

    def receipt(self, effect_id):
        """The four facts, as one inspectable object."""
        kinds = [e["kind"] for e in self.entries(effect_id)]
        return {
            "effect_id": effect_id,
            "proposed":   "PROPOSED"   in kinds,
            "authorized": "AUTHORIZED" in kinds,
            "executed":   "DISPATCHED" in kinds,
            "recorded":   "COMMITTED"  in kinds,
            "final":      kinds[-1] if kinds else None,
        }


def effect_id_for(proposal):
    """
    The identity of an effect is fixed at the moment it is approved, and never
    derived from a model output or a retry.

    Two cases:
      - the proposal carries a request_id (an approved request supplied by the
        application, e.g. a support case authorising one $20 refund): the effect
        id is derived from that. A model that re-decides "$30" on retry produces
        the SAME effect id with a DIFFERENT payload, which the gate rejects.
      - no request_id (e.g. an agent's diff): the effect id is the hash of the
        decision content, so the same decision from any agent or retry is one effect.

    Either way: one approved decision -> one effect id -> at most one committed
    effect. This is why "preserve decision history" and "prevent duplicate
    effects" are one mechanism and not two.
    """
    key = proposal.get("request_id")
    canonical = json.dumps(key if key is not None else proposal["effect"], sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
