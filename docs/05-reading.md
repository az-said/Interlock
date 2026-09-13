# Reading list

What we read, in the order that made it make sense, and what each one hands you.

## Tier 1: the ground floor

1. **Two Generals Problem.** Akkoyunlu, Ekanadham & Huber, 1975. *Wikipedia is enough.* No finite number of messages lets two parties be certain they agree. This is why retrying can't close the ambiguous window. You design around it.
2. **Designing robust and predictable APIs with idempotency.** Brandur Leach, Stripe, 2017. What the cooperating side looks like. Client generates a key before sending; server remembers keys it has seen. Works because Stripe cooperates. Our tier 1.
3. **Defeating Prompt Injections by Design (CaMeL).** Debenedetti et al., Google DeepMind, 2025. arXiv 2503.18813. Capabilities on values, policy at each tool call, provable non-interference. The standard of "provable" we're held to, and the paper that has no model of failure.
4. **The Coordination Problem.** Mosaic, June 2026. mosaic.inc/blog/memo. Agents as ephemeral probes against a central store; "retry is close to free." True only until a probe touches the outside world. The world we're building for, and the blind spot we're standing in.

## Tier 2: the mechanisms

5. **On Optimistic Methods for Concurrency Control.** Kung & Robinson, 1981. Record your read set, validate at commit, abort if anything changed. Our premise check, 45 years old.
6. **Sagas.** Garcia-Molina & Salem, 1987. When you can't roll back an external step, run a compensating step. The next piece after this repo: what to do about a committed effect whose authority is revoked afterward.
7. **Of course you can build dynamic AI agents with Temporal.** Temporal blog. Freeze model outputs as activities so replay doesn't re-ask. The upstream layer; stops at the tool call.
8. **How we built our multi-agent research system.** Anthropic, June 2025. The production-reliability section: agents are stateful, errors compound, resume from where the agent was. The easy half of the problem, solved for read-only agents.
9. **Not what you've signed up for.** Greshake et al., 2023. Named indirect prompt injection. Why data can change control flow in an agent and not in a program.
10. **Notes on Distributed Systems for Young Bloods.** Jeff Hodges, 2013. The one-page version of everything above.

## Tier 3: context

11. **Open Challenges in Multi-Agent Security.** arXiv 2505.02077, 2025. Delegation and provenance across agents. Read after the others; multi-agent is a layer on top, not the foundation.
12. **Macaroons.** Birgisson et al., 2014. Scoped, attenuable, expiring bearer tokens. The lease, done properly.
13. **The Transaction Concept: Virtues and Limitations.** Jim Gray, 1981. Where "commit" comes from.
14. **How to Talk to Users.** Eric Migicovsky, YC. Not a paper. Watch before interviewing anyone.

## Tier 4: published this summer, closest to us

15. **From Version Conflicts to Decision Conflicts: Selective Revalidation for Long-Running AI Agents (ATR).** Lyu et al., Huawei, Sept 2026. arXiv 2609.08015. Typed premises and selective re-checks, with a refund agent as the example. Excludes crashes. Code: github.com/ezreal13/atr-decision-validation.
16. **Cordon: Semantic Transactions for Tool-Using LLM Agents.** Chen et al., Tsinghua, EuroSys 27. arXiv 2606.17573. Effect outbox; unproven dispatches go to an audit state. Our tier 3, from the security side.
17. **Engineering Reliable Commit Gates for Agentic AI.** Zheng et al., WashU and SMU, Sept 2026. arXiv 2609.10969. Verifier portfolios; after-check races need atomic guards.
18. **SagaLLM.** VLDB. arXiv 2503.11951. Sagas plus independent validation agents for multi-agent planning.
19. **Agentic Transaction: Towards ACID-Compliant Agent Systems.** arXiv 2608.13900. Semantic atomicity, consistency, isolation, durability.
20. **Verified Detection and Prevention of Concurrency Anomalies in Multi-Agent LLM Systems.** Khan, June 2026. arXiv 2606.17182. TLA+ isolation levels for agents; the formal cousin of the coding-agent experiment.
21. **Before the Tool Call: Deterministic Pre-Action Authorization for Autonomous AI Agents.** Uchibeke, APort, March 2026. arXiv 2603.20953. Fail-closed policy checks; no state freshness.

## Things to know, not read

- MCP has no idempotency or transactional contract. Tools can't declare their tier.
- Temporal activities are at-least-once by default.
- DBOS steps and Restate `ctx.run` are at-least-once if the process dies after the call and before the result is saved. Their docs hand idempotency back to you.
- LangGraph resume re-runs the whole node, not the next line.
- Stripe rejects a refund on a fully refunded charge (`charge_already_refunded`). Partial refunds get no such protection, which is why experiment 1 uses one.
- Stripe idempotency keys expire after 24 hours.
- LangGraph checkpoints state; it doesn't govern effects.
- `git merge` checks text. CI checks the branch alone. Nothing checks premises.
