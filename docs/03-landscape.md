# Landscape

Who owns which piece, and which piece nobody owns. Reviewed from primary docs and papers, Sept 12–13 2026.

## The map

| layer | question it answers | who |
|---|---|---|
| artifacts in | is this package / MCP server safe to install? | Inner (getinner.ai) |
| policy and inventory | what agents exist, what may they do? | Snyk Evo / Agent Guard |
| orchestration | who is assigned, what state is the work in? | Linear Agents, OpenAI Symphony |
| crash recovery for deterministic workflows | resume after failure | Temporal, Restate, Inngest, DBOS, Prefect, AWS Lambda durable functions, Cloudflare Workflows, Vercel Workflow |
| agent frameworks with durable execution | wrap each model/tool call as a checkpointed step | Pydantic AI (first-party Temporal/DBOS/Prefect/Restate), LangGraph checkpoints |
| injection containment | can untrusted data change control flow? | CaMeL (DeepMind, 2025) |
| dedup at the receiver | don't do it twice | Stripe idempotency keys, Kafka EOS |
| agent-native payment rails | let agents hold and move money | Natural, Ralio, Paygentic |
| agent payment protocols | may this agent pay, under which signed mandate? | Google AP2, OpenAI/Stripe ACP |
| pre-action authorization | does this tool call match policy right now? | APort Open Agent Passport |
| research prototypes (2026) | premise revalidation, staged effects, commit gates | ATR (Huawei), Cordon (Tsinghua), commit gates (WashU) |
| parallel-agent workspaces | run N agents in isolated worktrees, merge at end | Superconductor, Conductor, Superset, Augment Intent |
| multi-agent runtimes | let agents message each other | Claude Code Agent Teams, AutoGen |
| **effects** | **did it happen, once, under live authority, on premises that still hold?** | **no shipping system; research covers pieces (below)** |

## Feature matrix

| | keeps decision history | dedupes effects | derives dedup key from the decision | re-checks premises at commit | re-checks authority at dispatch | states a per-target guarantee |
|---|---|---|---|---|---|---|
| LangGraph checkpoints | yes | no | no | no | no | no |
| Temporal | yes (event history) | activities at-least-once by default | no | no | no | replay determinism only |
| Pydantic AI + Temporal/DBOS | yes (steps checkpointed) | no; a tool step that crashes mid-call re-runs the tool | no | no | no | resume-from-last-step |
| Restate / DBOS / AWS Lambda durable functions | yes (journal or checkpoints) | no; a step is at-least-once if the process dies after the call and before the result is saved | no | no | no | resume-from-last-step |
| Google AP2 / OpenAI-Stripe ACP | signed mandates | no | no | no | mandate at payment time; no crash or retry model | no |
| APort Open Agent Passport | signed audit records | no | no | no; static policy only | yes, fail-closed | no |
| Stripe idempotency | no | yes, 24h window | no (client supplies key) | no | no | yes, for Stripe |
| CaMeL | no | no | no | data-flow capabilities, not world state | at tool call, no revocation model | provable non-interference |
| ATR (Huawei, Sept 2026) | decision dependency graph | no | no | **yes, typed premises, selective** | only via target-side tokens | no; excludes crashes and non-idempotent APIs |
| Cordon (Tsinghua, EuroSys 27) | transaction log | effect outbox; no resend without idempotency evidence | no | flow and authority, not live target state | yes | no; an unclear dispatch goes to an audit state |
| Commit gates (WashU, Sept 2026) | frozen records | idempotent request ids | no | yes, atomic guards | no | no; a benchmark study, not a runtime |
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

**Temporal** is the closest infrastructure and the most honest about the gap. Their own guidance for LLM agents is to record model outputs as activities so replay doesn't re-ask the model. That handles nondeterminism. It does not handle a frozen decision whose premises changed before its effect landed, or a grant revoked mid-flight. Interlock sits between a Temporal activity and the world. Measured, not argued: experiment 1's `durable@tier1` column is durable execution used as Temporal recommends. It ties the gate on every crash, duplicate, and re-decision row and fails every row where the world changed after the decision. Experiment 4 (`experiments/temporal_live.py`) reproduces this on a real Temporal server with Temporal's own retry policy, and shows the fix: the same activity with the gate as its body refuses.

**CaMeL** was the closest research until this summer (see below). It attaches capabilities to values and enforces policy at each tool call, with a provable non-interference property. It has no notion of crash, retry, duplicate delivery, or revocation. Different question, same standard of evidence.

**moire, conflict-check, sol, Augment Intent** all attack parallel-coding-agent conflicts. All are heuristics. None states what class of conflict it provably catches or provably cannot. Finding 2 in this repo is the statement they're missing.

**Inner, Snyk** are admission control and governance. They decide whether the agent *may* act. Interlock establishes what it *did*.

**Natural** is building the cooperating side: agent-native payment rails with a ledger. In Interlock's terms they are a tier-1 target. They validate that the receiver side is being funded right now.

**Cloud-Bean** (another team in this track) is verifying the *observer*: their finding pipeline reproduces deterministically from recorded judgments. Interlock verifies the *actor*. Their README notes they lack "service receipts." That's this repo.

## Research published this summer

Three papers landed between June and September 2026 that each build one of Interlock's pieces. We read them after checkpoint 2. None of them changes the design; each sharpens a claim, and one exposed a gap in our recovery path that is now fixed and measured.

**ATR, "From Version Conflicts to Decision Conflicts" (Huawei, arXiv 2609.08015, Sept 7).** Records typed premises with each decision and re-checks only the ones a change touches, with a KEEP / REFRESH / REPLAN / BLOCK outcome. Its motivating example is a refund agent. This is rule 3 done more selectively than ours. It explicitly excludes crashes, partial effects, and non-idempotent APIs, and its guarantee covers only premises the target checks atomically. Research prototype, no real targets. **What we take:** premise re-checks are a recognized open problem, not our invention. **Where we differ:** we run the re-check on the recovery path, which ATR leaves out.

**Cordon, "Semantic Transactions for Tool-Using LLM Agents" (Tsinghua, arXiv 2606.17573, EuroSys 27).** Stages outward effects in an outbox and validates the composed flow before release. On a crash, "dispatched effects are not resent unless the runtime has idempotency evidence," and an unproven dispatch goes to an audit or compensation state. That is our tier 3 `AMBIGUOUS`, arrived at independently. Security-first; no per-target guarantee, no check of live target state, no code released.

**"Engineering Reliable Commit Gates for Agentic AI" (WashU and SMU, arXiv 2609.10969, Sept 10).** Uses our name for our layer. A benchmark of verifier portfolios: evidence-source diversity beats verifier-model diversity, and after-check races defeat verifier-only gates, so atomic guards are needed. That last finding is why our premise check runs immediately before `DISPATCHED`.

Also relevant: **SagaLLM** (VLDB, arXiv 2503.11951), sagas and validation agents for multi-agent planning; **Agentic Transaction** (arXiv 2608.13900), semantic ACID for agents; **Khan, "Verified Detection and Prevention of Concurrency Anomalies in Multi-Agent LLM Systems"** (arXiv 2606.17182), TLA+-verified isolation levels with a Rust runtime, the formal cousin of our coding-agent half; **APort OAP** (arXiv 2603.20953), fail-closed pre-action authorization.

**What the convergence means.** Three groups building pieces of the same layer within three months says the layer is real. What none of them joins: crash recovery that re-checks premises and authority, a guarantee stated per target, and adapters for real services. That join is this repo.

## The empty cell

In shipping software it's empty for a structural reason. Model providers sit on one side of the effect and sell inference. API providers sit on the other side and solve dedup for themselves. Durable-execution vendors sit upstream and stop at the tool call. Nobody owns the agreement between an agent's recorded decision and the world's recorded effect. Seams like that are where Stripe (merchants ↔ banks), Twilio (apps ↔ carriers), and Plaid (apps ↔ banks) came from.
