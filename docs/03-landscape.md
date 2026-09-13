# Landscape

Who owns which piece, and which piece nobody owns. Reviewed from primary docs and papers, Sept 12–13 2026.

## The map

| layer | question it answers | who |
|---|---|---|
| artifacts in | is this package / MCP server safe to install? | Inner (getinner.ai) |
| policy and inventory | what agents exist, what may they do? | Snyk Evo / Agent Guard |
| orchestration | who is assigned, what state is the work in? | Linear Agents, OpenAI Symphony |
| crash recovery for deterministic workflows | resume after failure | Temporal, Restate, Inngest, DBOS, Prefect |
| agent frameworks with durable execution | wrap each model/tool call as a checkpointed step | Pydantic AI (first-party Temporal/DBOS/Prefect/Restate), LangGraph checkpoints |
| injection containment | can untrusted data change control flow? | CaMeL (DeepMind, 2025) |
| dedup at the receiver | don't do it twice | Stripe idempotency keys, Kafka EOS |
| agent-native payment rails | let agents hold and move money | Natural, Ralio, Paygentic |
| parallel-agent workspaces | run N agents in isolated worktrees, merge at end | Superconductor, Conductor, Superset, Augment Intent |
| multi-agent runtimes | let agents message each other | Claude Code Agent Teams, AutoGen |
| **effects** | **did it happen, once, under live authority, on premises that still hold?** | **nobody** |

## Feature matrix

| | keeps decision history | dedupes effects | derives dedup key from the decision | re-checks premises at commit | re-checks authority at dispatch | states a per-target guarantee |
|---|---|---|---|---|---|---|
| LangGraph checkpoints | yes | no | no | no | no | no |
| Temporal | yes (event history) | activities at-least-once by default | no | no | no | replay determinism only |
| Pydantic AI + Temporal/DBOS | yes (steps checkpointed) | no; a tool step that crashes mid-call re-runs the tool | no | no | no | resume-from-last-step |
| Stripe idempotency | no | yes, 24h window | no (client supplies key) | no | no | yes, for Stripe |
| CaMeL | no | no | no | data-flow capabilities, not world state | at tool call, no revocation model | provable non-interference |
| moire / conflict-check / sol | no | no | no | heuristic, unstated | no | no |
| Linear Agents | issue history | no | no | no | permissions fixed at install | no |
| Cloud-Bean (hackathon peer) | judgments | stable finding ids | no | no | no | reproducibility of *findings* |
| **Interlock** | **yes** | **yes** | **yes** | **yes** | **yes** | **yes, by tier** |

The third column is the one that matters. Every "yes" in the first two columns comes from a different mechanism. Interlock is the only row where the dedup key *is* the recorded decision, which is why history and dedup can't drift apart.

## Published positions we disagree with (from the team spec, §2)

- **Cemri et al., "Why Do Multi-Agent LLM Systems Fail?"** (Berkeley, 2025). 1,600+ traces, 14 failure modes. Step repetition is the top mode at 17.14%. But all seven frameworks studied are conversational orchestration, not concurrent writers to shared state. MAST measured agents *talking*; it didn't measure agents *committing*. Our `duplicate_work` row is the claims registry catching MAST's top mode with zero model calls.
- **Cognition, "Don't Build Multi-Agents."** Keep writes single-threaded. Sufficient for coherence, not necessary; it's the rule a database would impose with no concurrency control, and databases abandoned it for throughput. Our benign-edit row shows a concurrent write landing safely.
- **Anthropic, multi-agent research system.** Agents aren't good at real-time coordination, and coding parallelizes less than research. We agree with the first and treat it as a design reason: no agent-to-agent negotiation; a deterministic gate mediates. The second we think is an artifact of merge-time reconciliation being expensive.
- **Mosaic, "The Coordination Problem."** Retry is close to free. Not for LLM agents: 4–15× tokens, and re-running doesn't reproduce the plan. Discarding work is lossy and expensive. So agent transactions need concurrency control, but not classical abort-and-retry, because that assumes a cheap deterministic redo agents don't provide. **That sentence is the thesis of the coding-agent half of this repo.**

## Notes on the neighbours

**Pydantic AI's durable execution** (Temporal, DBOS, Prefect, Restate, all first-party) is the most likely thing a judge will name. It wraps every model and tool call as a durable step and checkpoints the *result*. That solves resume and freezes model outputs. It does not solve our problem, and their own docs say why: if the process crashes or a request times out, the agent has no idea what already happened. A tool step that dies *after* the effect and *before* its result is checkpointed re-runs the tool on recovery. Whether that duplicates the effect is left to the tool. Interlock is the body of that step: it journals intent *before* the call, binds the effect id to the approved request, checks premises and lease at dispatch, and recovers by the tool's declared tier. Complementary, and the cleanest integration story we have.

**Temporal** is the closest infrastructure and the most honest about the gap. Their own guidance for LLM agents is to record model outputs as activities so replay doesn't re-ask the model. That handles nondeterminism. It does not handle a frozen decision whose premises changed before its effect landed, or a grant revoked mid-flight. Interlock sits between a Temporal activity and the world.

**CaMeL** is the closest research. It attaches capabilities to values and enforces policy at each tool call, with a provable non-interference property. It has no notion of crash, retry, duplicate delivery, or revocation. Different question, same standard of evidence.

**moire, conflict-check, sol, Augment Intent** all attack parallel-coding-agent conflicts. All are heuristics. None states what class of conflict it provably catches or provably cannot. Finding 2 in this repo is the statement they're missing.

**Inner, Snyk** are admission control and governance. They decide whether the agent *may* act. Interlock establishes what it *did*.

**Natural** is building the cooperating side: agent-native payment rails with a ledger. In Interlock's terms they are a tier-1 target. They validate that the receiver side is being funded right now.

**Cloud-Bean** (another team in this track) is verifying the *observer*: their finding pipeline reproduces deterministically from recorded judgments. Interlock verifies the *actor*. Their README notes they lack "service receipts." That's this repo.

## The empty cell

It's empty for a structural reason. Model providers sit on one side of the effect and sell inference. API providers sit on the other side and solve dedup for themselves. Durable-execution vendors sit upstream and stop at the tool call. Nobody owns the agreement between an agent's recorded decision and the world's recorded effect. Seams like that are where Stripe (merchants ↔ banks), Twilio (apps ↔ carriers), and Plaid (apps ↔ banks) came from.
