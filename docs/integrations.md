# Integrations

Every way to add Interlock, with the full options. Each snippet on the landing page is a short form of one below. Back to the [README](../README.md).

## Install

```
pip install git+https://github.com/az-said/Interlock      # no dependencies; Python 3.9+
pip install "interlock-gate[temporal] @ git+https://github.com/az-said/Interlock"   # plus temporalio
```

A journal path ending in `.db` uses SQLite, so several workers can share one journal: an action is dispatched by exactly one of them and recovered by exactly one of them (`tests/test_interlock.py`, eight workers racing).

## Add it in three lines

For your own functions, skip the adapter. Three statements: create the gate, decorate the function that has the side effect, recover on startup.

```python
from interlock import Interlock
gate = Interlock(".interlock")

@gate.effect(key=lambda order, amount: f"refund:{order}",
             premises=lambda order, amount, idempotency_key: {
                 "eligible": is_eligible(order),
                 "refunded_by_others": refunded_total(order, excluding=idempotency_key)},
             dedupes=True)
def refund(order, amount, idempotency_key):
    return stripe.Refund.create(charge=charge_for(order), amount=amount, idempotency_key=idempotency_key)

gate.recover()   # once, on startup
```

`refund("881", 20)` now journals the decision, re-reads the premises right before the call and again after any crash, passes a stable idempotency key, and returns `("COMMITTED", result)`, `("REFUSED:stale_premise", None)`, `("DUPLICATE_IGNORED", ...)`, and so on.

If startup happens before a crashed sender's claim expires, calling the decorated function again retries recovery of its recorded decision. Call `recover()` periodically for effects that will not be called again. An active claim still prevents a second send.

The one thing you still have to say is the thing no library can guess: which facts the decision depends on. Then say how the service cooperates: `dedupes=True` if it takes the key, `lookup=` a function that answers "did this already happen?", or neither. `allowed=` adds a permission check at dispatch and at recovery. A premise that would count the effect's own result takes `idempotency_key` and leaves it out, as above. The adapter is `interlock/easy.py`; `tests/test_interlock.py` runs it through a crash and a process restart.

## Zero lines: in front of an MCP server

The agent's code doesn't change. Point its MCP server command at the proxy and name the tools that have real effects:

```
python3 -m interlock.mcp_proxy --config interlock.mcp.json -- python3 payments_server.py
```

```json
{"tools": {"create_refund": {
  "key": ["order_id"],
  "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"}, "fields": ["refunded_total"]},
  "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
  "idempotency_argument": "reference"}}}
```

Every other message passes through untouched. `create_refund` is journaled before it goes out, its facts are read from `get_order` and read again before any resend, a crash is recovered on the next start, and the tool result carries the receipt in `_meta.interlock`. MCP itself has no idempotency or transactional contract; this is where a tool gets one. `tests/test_mcp_proxy.py` runs it against a real subprocess MCP server, kills the proxy mid-call, and checks the refund lands once, and that a refund issued by hand during the outage is refused even when the agent retries.

Premise tools must return every configured field, and lookup tools must return a JSON boolean in the configured `found` field. An error, missing field, or malformed lookup leaves the action unsent or unresolved; it never proves that the previous action was absent.

The same config drives in-process tool lists, for any loop that maps a tool name to a function:

```python
from interlock.tools import protect
tools = protect({"get_order": get_order, "create_refund": create_refund, "find_refund": find_refund}, config)
tools.recover()                                   # once, on startup
out = tools["create_refund"](order_id="881", amount=20)
# hand out["message"] back to the model as the tool result
```

For LangChain or LangGraph, `interlock.langchain_tools.protect_tools(tools, config)` takes and returns `BaseTool` objects, so the list drops into `create_agent` or a `ToolNode` unchanged (`tests/test_langchain.py`, run with `uv run --with langchain-core --with langgraph`).

When the agent reads the premises tool itself (`get_order`, through the proxy or the tool list), its call is proposed on the facts it read, not on a fresh read at call time. A refund issued by hand between the agent's read and its call is caught too.


## Temporal: the activity body

Temporal owns the retries; the gate decides whether a retry may send. `refund_money` is a function decorated with `@gate.effect` as above.

```python
from interlock.temporal import gated

@activity.defn
def refund(order: str, amount: int) -> str:
    # recovers this refund if a crash left it in flight, else submits
    return gated(refund_money.gate, refund_money.proposal(order, amount))
```

A refusal or `AMBIGUOUS` raises a non-retryable `ApplicationError`; an unsettled send raises a retryable one. `experiments/temporal_live.py` runs this on a real Temporal server; the module docstring in `interlock/temporal.py` has the full mapping.

## Google ADK: the Guard callback

```python
from interlock.integrations.adk import Guard
guard = Guard(".interlock/adk", leases)
guard.gate("issue_refund",
           target_for=lambda effect: refunds,           # an EffectTarget: capture, validate_premises, apply, query
           # ctx.state["premises"] is set when the agent decides (the tool that reads the order), not at send time
           proposal=lambda args, ctx: {"lease": "case-4471", "request_id": "case-4471",
                                       "premises": ctx.state["premises"],
                                       "effect": {"order": args["order_id"], "amount": args["amount"]}})
agent = LlmAgent(name="support", model="gemini-2.5-flash", tools=[issue_refund],
                 before_tool_callback=guard.before_tool_callback)
guard.recover()                                         # once, when the process starts
```

Take `request_id` from the business action, not the function call id, so a replayed call is the same effect. `App(..., plugins=[guard.plugin()])` covers every agent in an app. [results/adk_live.md](../results/adk_live.md) is the live run.

## Install with your AI

[install-with-ai.md](install-with-ai.md) is a prompt for Claude Code, Cursor, Codex, Copilot or any coding agent that finds your side effects and wraps them with the integration that fits.

## Refused, then repaired

A refusal says what changed, not just that something did: `Interlock did not send this action (REFUSED:stale_premise): ... refunded_total: was 0, now 5.` The same facts are in `out["repair"]` and in the MCP result's `_meta.interlock.repair`; the structured form is `_meta.interlock.escalation` (see [Escalations and receipts](#escalations-and-receipts)).

By default a refused request stays refused until a person decides again, because a model that re-decides on retry is how a $20 refund becomes $50. Add an `approval` to the tool's config and the agent may send a corrected call instead:

```json
"approval": {"tool": "get_approval", "arguments": {"order_id": "order_id"}, "attempts": 3}
```

The tool returns the approval from the system of record, never from the model: `{"id": "case-4471", "match": {"order_id": "881"}, "max": {"amount": 15}}`, where `max` is what is still left. Each distinct decision is its own attempt. A call that fits the approval is sent, and only one attempt per approval is ever sent, so a crash can't be routed around with a new amount. A call outside it is refused with the limit (`amount 30 is over the 15 approved`). `attempts` (optional) caps the distinct calls tried, so a model that keeps re-deciding is stopped by the gate. An expired, revoked, used-up or already-used approval says `may_retry: false`. The store is `approvals.Envelope`; the decorator takes `approval=` and `attempts=` too.

Repair means one thing in both places: a new effect id, never the refused one with a different payload. Here the agent picks the new payload and the approval bounds it; in the inbox (`Inbox.repair`) a person accepts a suggested one and it goes back through rules or a person.

On a synthetic day of 100 refunds ([results/repair_loop.md](../results/repair_loop.md), mix stated as an assumption, scripted agent rather than a model), the refunds that needed a person went from 17 to 3 and wrong payouts from 13 to 0. The 13 were $30 decisions on $20 cases, which premises alone don't bound. With no gate, 40 of 100 paid out wrong. A careful hand-written check for this one refund (a reference per case, a lookup, a read of what is left right before sending) ties Interlock with repair on that day, as it did in [docs/10-scenarios.md](10-scenarios.md). What Interlock adds there is no per-tool code and a record of which checks ran.

With a real model deciding ([results/repair_live_model.md](../results/repair_live_model.md): `gpt-5.4-mini` over Azure OpenAI, 40 cases per system, mix stated as an assumption), interlock+repair finished all 40 with no person and no wrong payout, and in all 10 refused cases the model read the refusal and sent the right corrected call. No gate paid out wrong 15 times ($233). The hand check paid nothing wrong, but in 4 of its 6 hand-refund cases the model read "Not sent: amount 20 is over the 11 left on this case. You may send a refund of up to 11." and replied DONE with the customer short, and 2 went to a person. A first run with a terser hand-check message did worse ([results/repair_live_model_terse_hand_check.md](../results/repair_live_model_terse_hand_check.md)). That gap is the refusal message, not the check: Interlock's tells the model what changed and what to do next, for every tool, and a hand check has to be written to do the same. The model never asked for more than the $20 approved, so the approval limit was exercised only by the scripted run. Six cases per kind is a small sample.

## Receipts you can check

A log you have to trust is not a receipt. Every journal entry is hash-chained to the previous entry for its action, every send records the lease and premise checks that passed immediately before it, and `verify()` re-derives the claims from those entries alone:

```
$ interlock-verify receipt.json --key $SHARED_KEY
{ "valid": true, "tamper_evident": true, "signed": true,
  "happened": true, "happened_once": true,
  "authorized_when_fired": true, "assumptions_held": true, "problems": [] }
```

`gate.receipt_bundle(proposal, key)` produces the file. With a key shared with the other side (the payment service, an auditor), the bundle is HMAC-signed, so both sides can confirm the same record of what happened; an edited amount, a removed entry, or a rewritten chain fails. After a crash nobody can resolve, the receipt says `happened: "unknown"` instead of guessing. Without a key, the chain proves internal consistency only, and `verify()` says `signed: null`.

## Escalations and receipts

The goal is to cut two thirds of the manual approvals finance teams do on agent actions. That only works if what still reaches a person is explained, routed, and on the record.

**Explained.** A refusal says exactly what changed and what would still be safe. A $50 refund on a $100 order, after support refunded $30 by hand, comes back as `changes: [{"field": "refunded", "was": 0, "now": 30}]`, read as `refunded: was 0, now 30`, with the repair `still_fits` (70 is left to refund). A $100 request after the same hand refund suggests `refund_remaining`, `{"amount": 70}`. Targets opt in with an optional `explain()` method; targets without it keep refusing with plain strings. The same structure rides on the MCP proxy refusal (`_meta.interlock.escalation`, next to the agent's guidance in `_meta.interlock.repair`), on `tools.protect()` results (`out["escalation"]`) and on the Temporal helper's error. A repair is a new decision: a new effect id, never the refused one with a different payload, back through the rules or a person, and superseded if the facts moved again.

**Routed, with an SLA.** `Route("large", ["controller", "finance-manager"], when=..., sla=4 * 3600)` sends an escalation to a group; only a member of that group, checked when deciding and again at the send, can approve it. Unanswered past its SLA, it moves up the chain. An approval that expires, or whose approver left the group, is refused at the send and re-escalated with freshly read facts. Time is injected (`clock=`), and the queue is a fold over the journal, so a restarted or second inbox rebuilds it without losing or duplicating an escalation.

**On the chain.** `ESCALATED` (reason, what changed, facts shown, the group and its members) and `DECIDED` (who, when, on which escalation) are appended to the effect's hash chain, atomically with the dispatch check. `verify()` checks that a person's send has that person's decision, on the latest escalation, on the facts they were shown, before the send, from someone it was routed to, and reports `approved_by`, `approval_verified` and the `escalations` history. Receipts from before this feature stay valid.

**Confirmed by the target.** `interlock.confirm.confirm_event()` takes a Stripe webhook, verifies its `Stripe-Signature` (HMAC-SHA256 over `t.payload`, a timestamp tolerance, constant-time compare), matches the refund to the effect by `metadata.interlock_effect_id`, and appends `CONFIRMED` with the event and refund ids. `confirm_by_lookup()` does the same from the refunds list for users without webhooks. Unsigned or mismatched events write nothing. `verify()` then reports `confirmed_by_target`.

**Exported.** Receipts export to Cloud Logging and BigQuery (both read back live in the tests), OpenTelemetry spans, and SIEM file formats (`interlock/export/`). Which receipt field answers which SOX, SOC 2, PCI DSS and NIST AI RMF question is mapped in [docs/08-compliance-mapping.md](08-compliance-mapping.md) — the mapping is evidence, not certification.

**Counted.** `interlock.scoreboard.scoreboard(journal)` derives the numbers from the journal alone: requests, cleared with no person (and how many of those receipts verify), escalations by reason, stale approvals caught, crash cases sent to a person, repairs suggested and accepted, SLA breaches, time to decision. Experiment 6 reports it on its synthetic day.
