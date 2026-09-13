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
import functools, inspect, json, os
from .gate import Gate, SimulatedCrash
from .journal import effect_id_for


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
        was, now = premises["facts"], self.facts(premises["args"], eid)
        return [f"{k}: was {was.get(k)!r}, now {now.get(k)!r}" for k in sorted(set(was) | set(now))
                if was.get(k) != now.get(k)]

    def apply(self, eid, effect, crash_after_effect=False):
        self.results[eid] = _call(self.fn, effect["args"], eid)
        if crash_after_effect:
            raise SimulatedCrash(eid)
        return {"status": "ok"}

    def query(self, eid, effect):
        return bool(_call(self.lookup, effect["args"], eid))


class _Allowed:
    """An `allowed(*args)` callable, in the shape of the lease store the gate checks."""
    def __init__(self, allowed):
        self.allowed = allowed

    def is_live(self, args):
        return True if self.allowed is None else bool(self.allowed(*args))


class Interlock:
    def __init__(self, directory=".interlock"):
        os.makedirs(directory, exist_ok=True)
        self.directory = directory
        self.gates = {}

    def effect(self, key, premises=None, lookup=None, dedupes=False, allowed=None, dedup_window=24 * 3600):
        def wrap(fn):
            name = f"{fn.__module__}.{fn.__name__}"
            target = _FunctionTarget(fn, premises, lookup, dedupes, dedup_window)
            gate = Gate(target, os.path.join(self.directory, f"{name}.jsonl"), _Allowed(allowed))
            self.gates[name] = gate

            def proposal(*args):
                args = json.loads(json.dumps(list(args)))
                request = key(*args)
                eid = effect_id_for({"request_id": request})
                return {"agent": name, "lease": args, "request_id": request,
                        "premises": {"args": args, "facts": target.facts(args, eid)},
                        "effect": {"args": args}}

            @functools.wraps(fn)
            def call(*args):
                p = proposal(*args)
                status = gate.submit(p)
                return status, target.results.get(effect_id_for(p))

            call.gate, call.proposal = gate, proposal
            return call
        return wrap

    def recover(self, now=None):
        """Resolve every effect a crash left in flight. Call once on startup."""
        return {name: gate.recover(now=now) for name, gate in self.gates.items()}
