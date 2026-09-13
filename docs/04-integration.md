# Integration

Interlock wraps the moment an agent calls a tool. It touches nothing else: not the model, not the prompt, not the planner.

## The adapter

```python
class EffectTarget:
    tier: int                                   # 1, 2, or 3

    def capture(self, ...) -> dict:             # premises, at decision time
    def validate_premises(self, premises) -> list[str]   # violations, at commit time
    def apply(self, effect_id, effect) -> None  # do the thing
    def query(self, effect_id, effect) -> bool  # tier 2 only: did it already happen?
```

Four methods. Two exist in the repo (`targets/payments.py`, `targets/repo.py`). Real ones:

| target | tier | `apply` | `query` |
|---|---|---|---|
| Stripe | 1 | `stripe.Refund.create(..., idempotency_key=effect_id)` | n/a; Stripe dedupes |
| GitHub merge | 2 | `gh pr merge` | `GET /repos/.../commits?sha=<branch>` and check for the merge commit |
| Postgres | 2 | `INSERT ... ON CONFLICT (effect_id) DO NOTHING` | `SELECT 1 WHERE effect_id = ?` |
| S3 put | 2 | `put_object` | `head_object` |
| SendGrid | 3 | `send` | none; `AMBIGUOUS` on crash |
| Slack post | 3 | `chat.postMessage` | search is eventual and unreliable; treat as 3 |

Declaring the tier is the integration. Everything else is the same gate.

## Where it goes in each framework

**LangGraph.** A tool node becomes `gate.submit(...)` instead of calling the tool directly. Premises come from the state the node read. The journal path is per-thread. On resume, call `gate.recover()` before the graph continues.

**MCP.** Interlock as a proxy server: it exposes the same tools as the upstream server, journals each call, and forwards. The MCP spec has no idempotency or transactional contract, so the proxy is where the tier gets declared per tool. This is the most general integration and the one we'd build next.

**OpenAI Agents SDK / Anthropic tool use.** Wrap the tool executor. Same pattern as LangGraph.

**Temporal / Pydantic AI durable execution.** Interlock inside the activity (Temporal) or step (DBOS/Prefect). The durable engine guarantees the step is retried until it completes; Interlock guarantees the retry doesn't duplicate the effect, and says `AMBIGUOUS` when it can't know. With Pydantic AI, this is a tool function whose body is `gate.submit(...)`; nothing else changes.

## The notary (not built)

Tier 3 services could be lifted to tier 2 without changing their API if both sides write to a shared log:

```
agent  ──"intend e"──▶  NOTARY  ◀──"performed e"──  service
```

On recovery either side asks the notary what it has for `e`. This is a two-phase-commit coordinator (Gray, 1978) aimed at agents. It requires the service to write one line per effect. That's the product.

## Cost

One fsync per effect before dispatch, one journal read on recovery. Tier 2 adds one query per in-flight effect after a crash. Tier 1 adds nothing. The precision dial (file vs symbol premises) is a validation-time cost, not a dispatch-time cost.
