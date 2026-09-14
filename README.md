# Interlock

[![test](https://github.com/az-said/Interlock/actions/workflows/test.yml/badge.svg)](https://github.com/az-said/Interlock/actions/workflows/test.yml) · MIT · Python 3.9+ · zero dependencies

**Interlock gives every action an AI agent takes a receipt: it happened once (or is marked unknown when the service can't be asked), it was authorized when it fired, and the facts it was decided on still held when it landed, even through a crash.**

Live demo: [interlock-demo.greenpond-c5ddc6af.westus2.azurecontainerapps.io](https://interlock-demo.greenpond-c5ddc6af.westus2.azurecontainerapps.io) · Landing page: [az-said.github.io/Interlock/site](https://az-said.github.io/Interlock/site/) · Offline: `python3 demo.py 2`

## Why the obvious fix isn't enough

Why the obvious fix isn't enough, in one picture. Both columns write to disk before sending and read it back after the crash; the difference is what the entry carries, because **recovery can only re-check what was written down**:

```mermaid
flowchart LR
    subgraph L["The obvious fix: journal the INTENT"]
        direction TB
        L1["agent decides:<br/>refund $20"] --> L2["disk, fsync'd:<br/>&quot;I am sending $20&quot;"]
        L2 --> L3["send: 💥 crash"]
        L3 --> L4["restart: my send never landed,<br/>my permission is still live<br/>→ resend $20"]
        L4 --> L5["$40 refunded ❌<br/>its books balance: nothing alerts"]
    end
    MID["⏱️ mid-outage, off camera:<br/>support refunds the $20 by hand.<br/>No ID, no journal entry ,<br/>invisible to every log"]
    subgraph R["Interlock: journal the REASONS"]
        direction TB
        R1["agent decides:<br/>refund $20"] --> R2["disk, fsync'd: &quot;$20 BECAUSE<br/>refunded_total=0, case 4471<br/>allows it, lease live&quot;"]
        R2 --> R3["send: 💥 crash"]
        R3 --> R4["restart: re-read the world first ,<br/>refunded_total is now 20:<br/>premise stale"]
        R4 --> R5["REFUSED, receipt names the change<br/>$20 total ✅ measured on real Stripe"]
    end
    MID -.-> L4
    MID -.-> R4
    style L5 fill:#7f1d1d,stroke:#f87171,color:#fff
    style R5 fill:#14532d,stroke:#34d399,color:#fff
    style MID fill:#78350f,stroke:#f5a524,color:#fff
```

The journal records what *you* did. It cannot record what the *world* did while you were down. So the entry has to carry the facts the decision stood on, and recovery has to re-read the world before anything is sent a second time. That one line is the difference between the columns of every results table in [the proof](docs/proof.md).

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

## Who built it

| | |
|---|---|
| **Said Azaizah** | [said-azaizah.vercel.app](https://said-azaizah.vercel.app) · [github.com/az-said](https://github.com/az-said) |
| **Kiro Moussa** | [kiro.city](https://kiro.city) · [https://github.com/kiromoussa](https://github.com/kiromoussa) |

MIT licensed. Battle of the Coasts 2026, Cloud AI track, Boston.
