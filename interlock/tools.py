"""
Interlock around a tool list, and what every tool integration shares: a gated tool built from a config,
and what the agent is told when a call is not sent.

    tools = protect({"get_order": get_order, "create_refund": create_refund, "find_refund": find_refund},
                    config)                  # the same config as interlock.mcp.json (see mcp_proxy.py)
    tools.recover()                          # once, on startup
    out = tools["create_refund"](order_id="881", amount=20)

That covers OpenAI and Anthropic tool calling, or any loop that maps a tool name to a function: call
tools[name](**arguments) and hand `out["message"]` back to the model as the tool result. Tools not
named in the config pass through untouched. `out` is:

    ok        True if the action happened, on this call or an earlier one (never twice)
    status    the gate's status
    result    what the tool returned, when it ran on this call
    message   one line for the model
    repair    when not sent: {"changed": [...], "may_retry": bool, "next": "..."}
    receipt   the four facts (journal.receipt)

A tool function returns normally when it worked, raises ToolError when the service said no (settled,
never resent), and any other exception means the outcome is unknown: recovery settles it.

`approval` in a tool's config, {"tool": "get_approval", "arguments": {"order_id": "order_id"}}, names a
read tool that returns the approval (approvals.Envelope) from the system of record. With it, a refused
call says what changed and whether a corrected call may go: one that fits the approval is sent, once.
Without it, a refused request stays refused until a person decides again.
"""
import json, sys
from .approvals import Envelope
from .easy import Interlock
from .journal import CLAIM_TTL, effect_id_for

RESOLVED = ("DUPLICATE_IGNORED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY", "REAPPLIED_AFTER_QUERY")
WHY = {
    "REFUSED:stale_premise": "a fact this action depends on changed since it was decided",
    "REFUSED:stale_premise_at_recovery": "a fact this action depends on changed while the agent was down",
    "REFUSED:conflicting_payload": "the same request was already decided with different arguments",
    "REFUSED:lease": "no live approval covers it",
    "REFUSED:lease_used": "its approval was already used by another attempt",
    "REFUSED:target_error": "the tool reported an error, and nothing was sent again",
    "AMBIGUOUS": "a crash left it unclear whether it happened, and the tool gives no way to check",
    "IN_FLIGHT": "its outcome is not known yet; Interlock will settle it before anything is sent again",
}
RETRYABLE = ("REFUSED:stale_premise", "REFUSED:lease")     # refused before anything was sent or reserved


class ToolError(RuntimeError):
    """The service answered that the call failed."""


def structured(result):
    """A tool result's data: a plain function's own dict, structuredContent, or JSON in the first text block."""
    if not isinstance(result, dict):
        return {}
    if "content" not in result and "structuredContent" not in result:
        return result
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                data = json.loads(block["text"])
                return data if isinstance(data, dict) else {}
            except ValueError:
                pass
    return {}


def fill(template, arguments, effect_id):
    return {k: effect_id if v == "$effect_id" else arguments.get(v) for k, v in template.items()}


def gated(interlock, name, spec, call_tool, module=__name__):
    """
    One config entry as a gated function of the call's arguments. call_tool(name, arguments) runs any tool.
    `module` names the journal file, so an existing deployment keeps finding its journal.
    """
    def read(source, arguments, effect_id):
        return structured(call_tool(source["tool"], fill(source["arguments"], arguments, effect_id)))

    def send(arguments, idempotency_key):
        args = dict(arguments)
        if spec.get("idempotency_argument"):
            args[spec["idempotency_argument"]] = idempotency_key
        result = call_tool(name, args)
        if isinstance(result, dict) and result.get("isError"):
            raise ToolError(json.dumps(result.get("content")))
        return result
    send.__name__ = send.__qualname__ = name
    send.__module__ = module

    premises = lookup = approval = None
    if "premises" in spec:
        p = spec["premises"]
        def premises(arguments, idempotency_key):
            facts = read(p, arguments, idempotency_key)
            return {field: facts.get(field) for field in p["fields"]}
    if "lookup" in spec:
        l = spec["lookup"]
        def lookup(arguments, idempotency_key):
            return bool(read(l, arguments, idempotency_key).get(l.get("found", "found")))
    if "approval" in spec:
        def approval(arguments):
            return read(spec["approval"], arguments, None) or None

    key = lambda arguments: f"{name}:" + json.dumps({k: arguments.get(k) for k in spec["key"]}, sort_keys=True)
    return interlock.effect(key=key, premises=premises, lookup=lookup, dedupes=spec.get("dedupes", False),
                            approval=approval, fields=lambda args: args[0])(send)


def repair(gate, eid, status):
    """What the agent is told when a call was not sent: what changed, and whether a corrected call may go."""
    es = gate.journal.entries(eid)
    refused = next((e for e in reversed(es) if e["kind"] == "REFUSED"), {})
    proposed = next((e for e in reversed(es) if e["kind"] == "PROPOSED"), {})
    envelope = isinstance(gate.leases, Envelope)
    if status == "REFUSED:lease" and envelope:
        changed = gate.leases.problems(proposed.get("lease"), proposed.get("effect"))
    elif status.startswith("REFUSED") and refused:
        checks = refused.get("checks") or refused.get("rechecked") or {}
        reason = checks.get("violations") or refused.get("reason") or []      # the facts that moved, when known
        changed = [str(r) for r in reason] if isinstance(reason, list) else [str(reason)]
    else:
        changed = []
    lease = proposed.get("lease")
    may_retry = (envelope and status in RETRYABLE and not gate.leases.problems(lease)
                 and gate.leases.describe(lease)["used_by"] is None)                # nothing sent under it yet
    if may_retry:
        step = "Read the facts and the approval again, then send a corrected call; one that fits the approval is sent once."
    elif status == "IN_FLIGHT":
        step = "Do not decide again; Interlock settles this call first."
    else:
        step = "Do not retry this; a person has to decide."
    return {"changed": changed, "may_retry": bool(may_retry), "next": step}


def run(call, arguments):
    """Send one call through its gate. Always returns an outcome (see the module docstring)."""
    eid = effect_id_for({"request_id": call.request_id(arguments)})
    try:
        status, result = call(arguments)
    except ToolError as e:                            # the tool answered "failed": settle it, never resend
        status, result = call.gate.settle_failed(eid, str(e)) or "IN_FLIGHT", None
    except Exception as e:                            # no answer (timeout, crash, upstream gone): outcome unknown
        sys.stderr.write(f"interlock: {call.__name__} did not settle ({e!r}); left for recovery\n")
        status, result = "IN_FLIGHT", None            # recovery takes it over once the send's claim expires
    out = {"ok": status == "COMMITTED" or status in RESOLVED, "status": status, "result": result,
           "repair": None, "receipt": call.gate.journal.receipt(eid)}
    if status == "COMMITTED":
        out["message"] = "Done: the action happened once."
    elif out["ok"]:
        out["message"] = f"Interlock: this action already happened once ({status}); it was not sent again."
    else:
        fix = out["repair"] = repair(call.gate, eid, status)
        changed = f" {'; '.join(fix['changed'])}." if fix["changed"] else ""
        out["message"] = f"Interlock did not send this action ({status}): {WHY.get(status, 'the gate could not send it safely')}.{changed} {fix['next']}"
    return out


class Tools(dict):
    """The tool list with its gated tools wrapped. Call recover() once on startup."""
    def __init__(self, tools, interlock):
        super().__init__(tools)
        self.interlock = interlock

    def recover(self):
        return self.interlock.recover()


def protect(tools, config):
    interlock = Interlock(config.get("journal_dir", ".interlock/tools"), claim_ttl=config.get("claim_ttl", CLAIM_TTL))
    out = Tools(tools, interlock)
    for name, spec in config["tools"].items():
        call = gated(interlock, name, spec, lambda tool, arguments: tools[tool](**arguments))
        out[name] = lambda _call=call, **arguments: run(_call, arguments)
    return out
