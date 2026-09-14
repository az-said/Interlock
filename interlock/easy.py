"""
The short way in: gate any function that has a side effect.

    gate = Interlock(".interlock")

    @gate.effect(key=lambda order, amount: f"refund:{order}",
                 premises=lambda order, amount: {"refunded": refunded_total(order)},
                 dedupes=True)
    def refund(order, amount, idempotency_key):
        return stripe.Refund.create(charge=charge_for(order), amount=amount,
                                    idempotency_key=idempotency_key)

    gate.recover()                      # once, on startup

`key` names the approved request, so a retry or a re-decided amount maps to the same
effect. `premises` reads the facts the decision depends on: they are saved when the call
is made and read again right before the effect is sent, including after a crash.
Say how the service cooperates: `dedupes=True` if you pass `idempotency_key` through
(tier 1), `lookup=` a function answering "did this effect already happen?" (tier 2),
neither for tier 3. `allowed=` is checked at dispatch and again at recovery.

Any of these functions that declares an `idempotency_key` parameter receives the effect
id, so `premises` can leave the effect's own result out of its facts. Arguments and facts
must be JSON-serializable: they are written to the journal.
"""
import functools, inspect, json, os, re
from .approvals import Envelope
from .escalation import diff, render
from .gate import Gate, SimulatedCrash
from .journal import CLAIM_TTL, effect_id_for


def _call(f, args, eid):
    if "idempotency_key" in inspect.signature(f).parameters:
        return f(*args, idempotency_key=eid)
    return f(*args)


class _FunctionTarget:
    """One decorated function, adapted to the EffectTarget interface in targets/."""
    def __init__(self, fn, premises, lookup, dedupes, dedup_window):
        self.fn, self.premises, self.lookup = fn, premises, lookup
        self.tier = 1 if dedupes else 2 if lookup else 3
        self.queryable = lookup is not None
        self.dedup_window = dedup_window
        self.results = {}

    def facts(self, args, eid):
        raw = _call(self.premises, args, eid) if self.premises else {}
        return json.loads(json.dumps(raw, default=str))    # compare exactly what the journal stores

    def validate_premises(self, premises, eid=None):
        return [render(c) for c in diff(premises["facts"], self.facts(premises["args"], eid))]

    def explain(self, premises, eid=None, effect=None):
        """One read per check: violations are rendered from the same diff. A check patched onto the instance still runs."""
        if "validate_premises" in vars(self):
            return {"violations": self.validate_premises(premises, eid), "changes": [], "repairs": []}
        changes = diff(premises["facts"], self.facts(premises["args"], eid))
        return {"violations": [render(c) for c in changes], "changes": changes, "repairs": []}

    def apply(self, eid, effect, crash_after_effect=False):
        self.results[eid] = _call(self.fn, effect["args"], eid)
        if crash_after_effect:
            raise SimulatedCrash(eid)
        return {"status": "ok"}

    def query(self, eid, effect):
        return bool(_call(self.lookup, effect["args"], eid))


def _redecidable(entries):
    """
    Refused before anything was sent or reserved (a stale fact, or outside the approval). Under an approval
    the agent re-decides on current facts, so the same arguments get a new effect id instead of being
    checked forever against the refused attempt's premises.
    """
    return (bool(entries) and entries[-1]["kind"] == "REFUSED" and entries[-1].get("code") in ("stale_premise", "lease")
            and not any(e["kind"] == "DISPATCHED" for e in entries))


class _Allowed:
    """An `allowed(*args)` callable, in the shape of the lease store the gate checks."""
    def __init__(self, allowed):
        self.allowed = allowed

    def is_live(self, args):
        return True if self.allowed is None else bool(self.allowed(*args))


class Interlock:
    def __init__(self, directory=".interlock", claim_ttl=CLAIM_TTL):
        os.makedirs(directory, exist_ok=True)
        self.directory, self.claim_ttl = directory, claim_ttl
        self.gates = {}

    def effect(self, key, premises=None, lookup=None, dedupes=False, allowed=None, dedup_window=24 * 3600,
               approval=None, fields=None):
        """
        `approval(*args)` returns the approval this call runs under (see approvals.Envelope), read from
        the system of record. With it, the agent may re-decide after a refusal: each distinct set of
        arguments is its own attempt, only one that fits the approval is sent, and only once.
        `fields(args)` names the arguments for its match and max (default: by parameter name).
        """
        if approval and allowed:
            raise ValueError("approval= and allowed= both authorize the call; give one")

        def wrap(fn):
            name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{fn.__module__}.{fn.__qualname__}")
            if name in self.gates:                     # one journal per function: recovery must call the right one
                raise ValueError(f"an effect named {name} is already registered; give the function a distinct name")
            target = _FunctionTarget(fn, premises, lookup, dedupes, dedup_window)
            if approval:
                names = [p for p in inspect.signature(fn).parameters if p != "idempotency_key"]
                named = fields or (lambda args: dict(zip(names, args)))
                leases = Envelope(os.path.join(self.directory, f"{name}.approvals.db"), fields=lambda effect: named(effect["args"]))
            else:
                leases = _Allowed(allowed)
            gate = Gate(target, os.path.join(self.directory, f"{name}.jsonl"), leases, claim_ttl=self.claim_ttl)
            self.gates[name] = gate

            def request_id(*args):
                args = json.loads(json.dumps(list(args)))
                if not approval:
                    return key(*args)
                base = f"{key(*args)}:{json.dumps(args, sort_keys=True)}"   # one attempt per distinct decision
                rid, n = base, 1
                while _redecidable(gate.journal.entries(effect_id_for({"request_id": rid}))):
                    n += 1                             # the same arguments after a refusal are a new decision
                    rid = f"{base}:{n}"
                return rid

            def proposal(*args):
                args = json.loads(json.dumps(list(args)))
                request = request_id(*args)
                eid = effect_id_for({"request_id": request})
                return {"agent": name, "lease": json.loads(json.dumps(approval(*args))) if approval else args,
                        "request_id": request,
                        "premises": {"args": args, "facts": target.facts(args, eid)},
                        "effect": {"args": args}}

            @functools.wraps(fn)
            def call(*args):
                p = proposal(*args)
                status = gate.submit(p)
                return status, target.results.get(effect_id_for(p))

            call.gate, call.proposal, call.request_id = gate, proposal, request_id
            return call
        return wrap

    def recover(self, now=None):
        """Resolve every effect a crash left in flight. Call once on startup."""
        return {name: gate.recover(now=now) for name, gate in self.gates.items()}
