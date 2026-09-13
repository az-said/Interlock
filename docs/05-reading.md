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

## Things to know, not read

- MCP has no idempotency or transactional contract. Tools can't declare their tier.
- Temporal activities are at-least-once by default.
- Stripe idempotency keys expire after 24 hours.
- LangGraph checkpoints state; it doesn't govern effects.
- `git merge` checks text. CI checks the branch alone. Nothing checks premises.
