"""
Interlock inside Google ADK (Agent Development Kit): the gate runs a tool's effect from a tool callback.

    guard = Guard(".interlock/adk", leases)
    guard.gate("issue_refund",
               target_for=lambda effect: StripeRefunds(client, effect["payment_intent"]),
               proposal=lambda args, tool_context: {"lease": ..., "request_id": ..., "premises": ..., "effect": ...})
    agent = LlmAgent(..., tools=[issue_refund], before_tool_callback=guard.before_tool_callback)
    # or once for every agent in the app:  App(..., plugins=[guard.plugin()])
    guard.recover()                     # once, when the agent process starts

For a gated tool the callback does the send itself, through the gate, and returns the outcome as the tool
response. ADK skips the tool body whenever a before callback returns a dict, so the function in `tools=[...]`
only gives the model its schema. The effect is `target.apply`, the same EffectTarget interface as targets/.
The outcome is recorded in the journal by the gate, not inferred in an after callback: ADK runs after
callbacks even when a before callback skipped the tool, so they cannot tell whether anything was sent.

`proposal(args, tool_context)` is called at the tool call, the moment the model decided. It returns the
proposal the gate expects (see gate.py). Take `premises` from what the model read (for example facts a lookup
tool saved in `tool_context.state`), and `request_id` from the business action rather than
`function_call_id`, so the same approved action is one effect however the call is replayed. `agent` defaults
to the ADK agent, invocation and function call, so the receipt records which call proposed it.

Crashes. ADK's own resume (`ResumabilityConfig(is_resumable=True)` and `run_async(invocation_id=...)`) replays
a tool call that never answered, and its docs say the replayed tool must be idempotent. Replayed here, the
callback first recovers the effect if an earlier send is unresolved, and only otherwise submits: premises and
lease are re-checked, and a send that already landed is reported, not repeated. A send whose process died
holds its claim for claim_ttl; the callback waits that out rather than risk a second send.

google.adk is imported only by plugin(); the rest is standard library.
"""
import asyncio, os, re, time
from ..gate import Gate
from ..journal import CLAIM_TTL, effect_id_for, open_journal

UNSETTLED = ("IN_FLIGHT", "UNRESOLVED")


class _Gated:
    def __init__(self, target_for, proposal):
        self.target_for, self.proposal = target_for, proposal


class Guard:
    def __init__(self, directory, leases, claim_ttl=CLAIM_TTL, poll=1.0):
        os.makedirs(directory, exist_ok=True)
        self.directory, self.leases, self.claim_ttl, self.poll = directory, leases, claim_ttl, poll
        self.gates = {}

    def gate(self, tool_name, target_for, proposal):
        """Gate the ADK tool named `tool_name`. `target_for(effect)` returns the EffectTarget that sends it."""
        self.gates[tool_name] = _Gated(target_for, proposal)

    def _journal(self, tool_name):
        return os.path.join(self.directory, re.sub(r"[^A-Za-z0-9_.-]", "_", tool_name) + ".db")

    def _gate(self, tool_name, effect):
        return Gate(self.gates[tool_name].target_for(effect), self._journal(tool_name), self.leases, self.claim_ttl)

    async def before_tool_callback(self, tool, args, tool_context):
        """Agent-level callback: None for tools that are not gated, else the gated outcome as the tool response."""
        if tool.name not in self.gates:
            return None
        return await asyncio.to_thread(self.run, tool.name, dict(args), tool_context)

    def run(self, tool_name, args, tool_context):
        p = dict(self.gates[tool_name].proposal(args, tool_context))
        p.setdefault("agent", f"adk:{getattr(tool_context, 'agent_name', '?')}/{tool_context.invocation_id}/"
                              f"{tool_context.function_call_id}")
        eid, deadline = effect_id_for(p), time.time() + 2 * self.claim_ttl + 10
        gate = self._gate(tool_name, p["effect"])
        while True:
            status = gate.recover(only=[eid]).get(eid) or gate.submit(p)
            if not status.startswith(UNSETTLED) or time.time() > deadline:
                return response(gate.journal, eid, status)
            time.sleep(self.poll)

    def recover(self):
        """Resolve every effect a crash left in flight whose claim has expired. Call when the process starts."""
        out = {}
        for name in self.gates:
            journal = open_journal(self._journal(name))
            for eid in journal.in_flight():
                effect = [e for e in journal.entries(eid) if e["kind"] == "DISPATCHED"][-1]["effect"]
                out.update(self._gate(name, effect).recover(only=[eid]))
        return out

    def plugin(self, name="interlock"):
        """The same gate as an ADK plugin, so it covers every agent and tool in the app."""
        from google.adk.plugins.base_plugin import BasePlugin
        guard = self

        class InterlockPlugin(BasePlugin):
            async def before_tool_callback(self, *, tool, tool_args, tool_context):
                return await guard.before_tool_callback(tool, tool_args, tool_context)

        return InterlockPlugin(name=name)


def response(journal, eid, status):
    """What the model is told: the gate's status, what the target returned if it was sent, and why not if refused."""
    es = journal.entries(eid)
    committed = next((e for e in es if e["kind"] == "COMMITTED"), None)
    refused = next((e.get("reason") for e in reversed(es) if e["kind"] == "REFUSED"), None)
    out = {"interlock": status, "effect_id": eid, "sent": True if committed else "unknown" if status == "AMBIGUOUS"
           or status.startswith(UNSETTLED) else False}
    if committed:
        out["result"] = committed.get("result") or {"found": committed.get("found")}
    elif refused:
        out["refused"] = refused if isinstance(refused, str) else "; ".join(map(str, refused))
        out["final"] = ("Not a technical error. Do not retry: re-authorizing under the same approval is refused too. "
                        "A person has to review the case and issue a new approval.")
    return out
