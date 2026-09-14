# Interlock

[![test](https://github.com/az-said/Interlock/actions/workflows/test.yml/badge.svg)](https://github.com/az-said/Interlock/actions/workflows/test.yml) · MIT · Python 3.9+ · zero dependencies

**Interlock gives every action an AI agent takes a receipt: it happened once (or is marked unknown when the service can't be asked), it was authorized when it fired, and the facts it was decided on still held when it landed, even through a crash.**

Live demo: [interlock-demo.greenpond-c5ddc6af.westus2.azurecontainerapps.io](https://interlock-demo.greenpond-c5ddc6af.westus2.azurecontainerapps.io) · Landing page: [az-said.github.io/Interlock/site](https://az-said.github.io/Interlock/site/) · Offline: `python3 demo.py 2`

## Install

```
pip install git+https://github.com/az-said/Interlock
```

**1. Python, three lines.** Decorate the function with the side effect and recover on startup.

```python
from interlock import Interlock
gate = Interlock(".interlock")

@gate.effect(key=lambda order, amount: f"refund:{order}",
             premises=lambda order, amount, idempotency_key: {
                 "refunded_by_others": refunded_total(order, excluding=idempotency_key)},
             dedupes=True)
def refund(order, amount, idempotency_key):
    return stripe.Refund.create(charge=charge_for(order), amount=amount, idempotency_key=idempotency_key)

gate.recover()   # once, on startup
```

**2. No code: in front of an MCP server.** `python3 -m interlock.mcp_proxy --config interlock.mcp.json -- <server command>`

**3. Let your coding agent do it.** Paste [docs/install-with-ai.md](docs/install-with-ai.md) into Claude Code, Cursor, Codex or Copilot.

Temporal activities, OpenAI and Anthropic tool loops, LangChain and LangGraph, and Google ADK: [docs/integrations.md](docs/integrations.md).

## Proof

Seven runs, from simulated faults to real Stripe, real Temporal and a SIGKILLed Google ADK agent, with every id listed: [the proof table](docs/proof.md#seven-runs-one-claim). Tests: [tests/README.md](tests/README.md).

## Docs

- [How it works](docs/how-it-works.md): the problem, the five rules, the core in code, where it plugs in, the repo map
- [Proof](docs/proof.md): the results tables, what it costs, what is real and what is not, references
- [Integrations](docs/integrations.md): every integration, refusals and repair, receipts, escalations
- [The whole story](docs/00-the-whole-story.md) and the [visual walkthrough](https://az-said.github.io/Interlock/docs/interlock-explained.html)
- [Live demo, run locally](demo/README.md)

MIT licensed. Battle of the Coasts 2026, Cloud AI track, Boston.
