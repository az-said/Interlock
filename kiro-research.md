# Kiro research: Interlock context and findings

Compiled 2026-09-13 from Claude Code transcripts, workflow journals, repo docs and results (`~/Downloads/Interlock`, local `main` at `96bfbd0` plus uncommitted and untracked work; `origin/main` one commit ahead at `84787ec`), and memory notes. Secrets, email addresses and personal names of judges, mentors and contacts are left out on purpose.

Conventions:
- Times are US Eastern (EDT). Git gives them directly. Transcript timestamps are UTC and were converted (UTC minus 4h).
- "Unverified" means I could not confirm it from a repo file or a primary source quoted in the transcripts.
- Citations name the repo file each number comes from.

---

## 1. Timeline and key decisions

### Saturday, Sept 12 2026 (hackathon day 1)

- **Event.** Battle of the Coasts 2026 ("East v. West AllStar Hack"), Cloud AI track, Boston. Runs Sept 12 to 14 (memory note `interlock-project.md`). Track brief title: "Verifiable execution for distributed AI systems" (`docs/00-the-whole-story.md` section 1).
- **20:16.** Initial commit `4dd92cd`, "scaffold eastvwest workspace". The repo was otherwise empty through checkpoint 1.
- **Whiteboard forks** (`docs/00-the-whole-story.md` section 2): sandboxing, prompt injection, data poisoning, duplicate tasks, "security vs efficiency", and multi-agent communication.
- **Two team specs written.** A narrow refund-duplicate spec (`docs/team-notes/02`) and a broad concurrency-control spec for parallel coding agents (`docs/team-notes/05`). Neither was ever pushed to GitHub, so README links to them are broken (transcript, session 187016d4).
- **About 20:30 to 22:05. Remotion videos, in two parallel folders.**
  - `interlock-video`: a 135.5s cut, then a 60s cut, then an 89s "research story" cut with frosted-glass UI.
  - `interlock-video-b`: about 140s, technical terminal style.
  - All silent (transcripts c3b0c82e, 1224f7c5).
- **22:00. Checkpoint 1 submitted:** a one-page overview plus a silent video. The overview framed Interlock as "a safety checkpoint for AI agents", with a simulated refund-agent demo plan (`docs/checkpoints/checkpoint-1.md`).

### Sunday, Sept 13 2026 (day 2)

**Morning: the core mechanism**
- **Two specs become one mechanism.** Premises that are true at decision time go stale by commit time, and nothing re-checks them. So the gate was built once and aimed at two targets (`docs/checkpoints/checkpoint-2.md`).
- **Four narrowing decisions** (`docs/00-the-whole-story.md` section 3):
  1. Research, not product.
  2. Effects, not the model.
  3. Duplicate effects as the headline.
  4. Refund as the instrument, coding agents as the generalization.

**11:42 to 11:59: checkpoint 1 feedback and the story choice**
- Checkpoint 1 scorecard reviewed (section 5).
- Decision: tell only the Stripe refund crash story. Drop coding agents and treasury reconciliation as separate stories (transcript 187016d4).
- First competitor research pass.
- Video v2 (104.6s) rebuilt around a "human refunds during the outage" twist, with a competitor table and a 2x2 map. Benchmark grid labeled "predicted".

**12:17: checkpoint 2 core lands**
- `27a4fd7`: runtime, two fault-injection experiments, results, docs.
- `5a33379`: submission text. `bc46bdf`: plan for checkpoints 3 and 4.
- Three findings stated (section 4).

**12:30 to 12:55: first real bug, landing page, repo move**
- About 12:30: landing page `site/index.html` built by a separate session.
- 12:33: repo link updated to `az-said/Interlock`. `shawnzhu02/Interlock` redirects to the same repo id (memory note).
- About 12:37: a real gap found. `recover()` re-sent at tiers 1 and 2 without re-checking premises or lease, so a hand refund during the outage produced $40. The durable-execution baseline, `easy.py`, a 2,000-case randomized sweep and CI were added.
- 12:43: user pushback: a pitch built on an edge-case double refund is too narrow. The pitch was reframed as "agents act on stale facts": approval waits, parallel agents, revoked permissions, tools with no retry safety. Crashes become the bottom row.

**12:50 to 12:57: first real-service runs, new pitch direction**
- 12:50 and 13:37: first real-service runs. `experiments/stripe_live.py` ran in Stripe test mode (`results/stripe_live.md`). `experiments/temporal_live.py` ran on a Temporal dev server (`results/temporal_live.md`).
- 12:54: `6f6a872` pushed as PR #1 ("Recheck premises on recovery, measure against Temporal and Stripe, add three-line API"). CI passed.
- 12:57: user rule: feature sets go straight to `main`, no PRs (memory `interlock-push-to-main.md`).
- 12:57: new pitch direction from the user. Companies pay people to approve agent actions by hand. Interlock removes the mechanical half of approval. Goal: "cut two thirds of manual approvals", stated as a goal, not a result.

**13:04 to 13:38: approvals, receipts, integrations, hardening**
- 13:04: `3a11713`, shared journal: one dispatch and one recovery across concurrent workers.
- 13:13: `fe61e7b`, verifiable receipts plus an approval inbox (100 / 25 / 33 reviews).
- 13:17: `439a1ed`, zero-line MCP proxy, Temporal activity helper, pip packaging.
- 13:24: `888e688`, SQLite WAL fix; CI on Python 3.9 to 3.13.
- 13:31 to 13:38: an adversarial review found 9 defects, 1 critical (a recovery running during an in-flight send could send twice). Fixed in `f3d999f` with send claims. 53 tests.

**13:08 to 14:03: landing page iterations** (transcript ba946aff)
- 13:08: landing page deployed to `interlock-self.vercel.app` (Vercel, not connected to GitHub).
- User-driven changes:
  - Removed eyebrow labels and fine print.
  - Moved "We broke a $20 refund 10 ways" to the front.
  - Replaced the 100/25/33 review chart with an APQC duplicate-payment benchmark (2% / 0.8% / 0%).
  - Added a dollar-cost strip.

**13:45 to 14:13: checkpoint 2 document, verification, deck**
- 13:45 to 13:52: checkpoint 2 document rewritten as a .docx.
  - User direction: "six systems / tiers" reads badly; show one Interlock column against the alternatives.
  - A competitor comparison table was added.
- 13:46 to 13:49: five pre-judge checks run. All passed; the README demo block was fixed in `591c6d3`. Details in section 4.8.
- 13:12 to 13:38: Gamma deck prompts written and revised several times (15 slides). A draft of questions for a Google-affiliated mentor was prepared.
- 14:13: `96bfbd0`, `docs/00-the-whole-story.md` plus `docs/interlock-explained.html`.

**15:11 to 16:25: viewer and Cloud-Bean**
- Replay viewer reworked:
  - A toggle: no fix / retry with idempotency key / durable execution (Temporal) / Interlock.
  - Tier buttons removed at the user's request.
  - Interlock endings shown green.
- 15:12 to 15:15: viewer and explainer deployed to Vercel.

**16:27 to 18:01: live backend, the Temporal-replacement decision, and the hand-check tie**
- 16:27: user instruction: prove it end to end with no mock data and no terminal demo, as a real backend better than Temporal as pitched.
- 16:32: workflow launched.
  - Built: `backend/`, `experiments/e2e_live.py`, and an independent auditor `experiments/e2e_audit.py`.
  - Four adversarial verifiers (mock hunter, ground truth, fairness to Temporal, claims vs evidence), two fix rounds.
- 17:40 to 17:44: "replace Temporal" debated.
  - The assistant argued to sit inside Temporal, not replace it.
  - The user overrode: time and competitors are not the constraint. Recorded in memory as "decided, don't re-litigate".
- About 17:47: runtime workflow launched.
  - Research: 5 agents.
  - Design: 3 architectures (DBOS-based, SQL-first on Absurd, own journal-native core) scored by 3 judges. The own-core design won.
  - Output: build spec `docs/07-runtime.md`, TLA+ model in `spec/`, `runtime/` package.
- 17:57: `results/e2e_live.md` generated.
- 18:00: `84787ec` "Live backend: real LLM agent, Temporal, Stripe test mode, real SIGKILL" pushed. CI green.
- Key result: Interlock beats Temporal alone, but a hand-written re-check of about ten lines ties it on money in every row and recovers faster.

**18:05 to 18:22: mentor feedback, competitor searches, new build plans**
- 18:05: mentor feedback received (section 5). Pitch pivots to middleware alongside Temporal, ADK and AP2, with receipts exported into audit tooling and a one-click before/after demo.
- A workflow then produced:
  - `docs/08-pitch.md`, `docs/08-compliance-mapping.md`
  - `docs/09-research-adk.md`, `docs/09-research-ap2.md`, `docs/09-research-gcp-audit.md`
  - `interlock/integrations/adk.py`, `interlock/integrations/ap2.py`
  - exporters, and the `demo/` page
- 18:10: user rule: showcase pages must run live end to end with no mock data, plus a separate clearly labeled mock button (memory `interlock-demo-no-mock.md`).
- 18:09 to 18:16: competitor searches (LinkedIn phrases, GitHub, arXiv). Salus and "Notarized Agents" found (section 3).
- 18:16: real-world scenario suite launched: 8 scenarios, each run as no_check / hand_check / interlock (`docs/10-scenarios.md`).
- 18:18 to 18:22: escalation direction chosen: explained escalations with suggested repairs, routing and SLA, escalations in receipts, Stripe webhook confirmation, and a scoreboard.
  - Built by a workflow in a fresh clone, `~/Downloads/Interlock-build`, to avoid another session's uncommitted edits.

**18:22 to 19:11: Shopify, demo runs, restraint, UI, runtime live run**
- 18:22 to 18:58: Shopify scenario attempted and blocked (section 8).
- 18:33: demo page driven in headless Chromium against live services (`results/demo_live.md`, `results/demo_live_revoked.md`).
- 19:04: user rule: keep deliverables professional and restrained; no overbuilding or overclaiming (memory `interlock-professional-restraint.md`).
- 19:07 to 19:08: UI workflow started on branch `ui-escalations` in `~/Downloads/Interlock-ui`. It ports 21st.dev component designs into the dependency-free viewer and adds a reviewer inbox.
  - Separately, the user asked to replicate Temporal's landing-page "workflow failure preview" on the Interlock site.
- 19:10: `experiments/escalation_live.py` ran once against Stripe test mode (workflow journal wf_ed438274). **Unverified in this checkout:** that file is not in the local `experiments/`.
- 19:11: `experiments/runtime_live_agent.py` ran once (`results/runtime_live_agent.md`).

### Planned (from docs)

- Checkpoint 3: Sunday 22:00 ET. Checkpoint 4: Monday 10:00 ET. Final submission: Monday Sept 14, 12:00 (`docs/00-the-whole-story.md` section 13).
- One transcript says the scorecard is 1 of 6, with final placement = final round plus the average of 5 check-ins. **Unverified.**

---

## 2. Problem framing and pitch evolution

1. **Checkpoint 1: safety checkpoint** (`docs/checkpoints/checkpoint-1.md`). Check that an agent's permissions and assumptions are still valid before it acts, and record what happened so crashes and retries are safe. Demo plan: a simulated refund agent with three failures.

2. **Root framing** (`docs/01-problem.md`, `docs/00-the-whole-story.md` section 4).
   - The three-line refund function: decide with an LLM, call Stripe, update the DB. The process dies on the Stripe call.
   - A timeout hides four realities: never arrived, done with the response lost, still processing, crashed halfway. That is the Two Generals problem.
   - Root sentence: "an agent decides on premises that are true when it decides; its action lands later; and nothing in the system carries the premises along with the action to be re-checked when it lands." This is time-of-check to time-of-use across a model call, a network hop and a foreign service.
   - What AI adds: re-running does not reproduce the decision; data can change control flow; permissions move mid-run.
   - The brief's four facts become the receipt: proposed, authorized, executed, durably recorded.

3. **Checkpoint 2: commit gate, research framing** (`docs/checkpoints/checkpoint-2.md`). Three findings. "Multiplayer AI doesn't fail because agents can't talk. It fails because nothing validates what they assumed at the moment their work lands."

4. **Same day, narrowing to one story.** The judge was confused by three stories (refund crash, coding agents, treasury reconciliation), so the refund crash was chosen. The twist that idempotency keys miss is a human refunding during the outage.
   - Early video versions used two $240 charges (`ch_A`/`ch_B`), because Stripe rejects a second full refund (`charge_already_refunded`).
   - The repo uses a $20 partial refund on a $100 payment for the same reason (`docs/05-reading.md`).

5. **User pushback: "can't be our entire pitch if it's an edge problem."** Reframed as "agents act on stale facts", with the crash as the worst case.

6. **Receipts plus approvals** (README, from about 13:00).
   - Headline: "Every action an AI agent takes gets a receipt: it happened exactly once, it was authorized when it fired, and the facts it was decided on still held when it landed."
   - Goal line: "let finance teams cut two thirds of the manual approvals they do on agent actions".
   - Scoped claim: Interlock removes the mechanical checks (still valid? already happened? still allowed?). Judgment approvals stay with people.
   - Open weakness: no sourced number for how much approval work is mechanical (memory note; transcript 187016d4).

7. **"No tiers."** The user found the per-tier columns confusing ("it should just be one solution"). Docs and viewer switched to one Interlock column. One caveat sentence stays: against targets with neither dedup nor lookup, Interlock sends ambiguous cases to a person.

8. **"Crash duplicates are solved; stale actions are not"** (transcript 187016d4, 14:02). A plain crash or an exact duplicate is already handled by Stripe keys and Temporal. The unsolved part is the same action arriving as a different request, or facts and authority changing while the agent is down.
   - Temporal one-liner: "Temporal makes sure the agent finishes. Interlock makes sure what it finishes is still right."

9. **"Replace Temporal"** (user decision, about 17:43). Build an agent-native durable runtime on Postgres from OSS pieces, measured against Temporal and against Temporal plus a hand-written pre-send check (`docs/07-runtime.md`).

10. **After the live backend result and mentor feedback: middleware** (`docs/08-pitch.md`).
    - "Middleware for the moment an AI agent's action fires." It runs inside a Temporal activity, a Google ADK tool callback, an MCP proxy, or plain Python.
    - "AP2 proves what was authorized. Interlock proves it was still authorized, and its facts still held, when it fired, and that it happened once."
    - Three buyers: Risk and Compliance (policy), Platform Engineering (installs once per runtime), Finance or line of business (grants and revokes).
    - Differentiator: receipts land in the audit tools buyers already run (Cloud Logging, OTLP, SIEM).
    - `docs/08-pitch.md` states there is no "also runs without Temporal" line, because `runtime/` was not present when it was written. `runtime/` now exists; see section 6.

11. **Honest positioning after the scenario suite** (`docs/10-scenarios.md`). Across 7 real services, Interlock never beat the strongest hand-written check on the service's end state; it tied everywhere. Its consistent edge is the record: a structured, hash-chained receipt that `verify()` re-derives verdicts from, tamper-evident only when signed.

12. **Temporal is optional** (user rule, Sept 13). Users should never need Temporal to use Interlock. Lead with the standalone paths (the `interlock/easy.py` decorator, the MCP proxy, the Postgres runtime once it has results); Temporal is "already on Temporal? it runs as the activity body". As of this writing `backend/` and the live demo still require Temporal.

13. **Escalations** (from 18:18). Competitor Salus escalates at decision time. Interlock also escalates when the world changed between approval and send, and after a crash, with a structured "what changed" and a suggested repair.

---

## 3. Related work and competitors

Links and citations are reproduced as they appear in the sources.

### 3.1 Papers and classic references (`README.md` References, `docs/05-reading.md`, `docs/03-landscape.md`)

**Classics and foundations**
- Akkoyunlu, Ekanadham & Huber (1975). Two Generals. Why tier 3 is undecidable.
- Kung & Robinson (1981). On Optimistic Methods for Concurrency Control. Record the read set, validate at commit.
- Garcia-Molina & Salem (1987). Sagas. Compensation, named as the next step.
- Jim Gray (1981). The Transaction Concept: Virtues and Limitations. Gray (1978) is cited for two-phase commit in the notary sketch.
- Brandur Leach, Stripe (2017). Designing robust and predictable APIs with idempotency. Tier 1; the 24h key expiry.
- Birgisson et al. (2014). Macaroons.
- Jeff Hodges (2013). Notes on Distributed Systems for Young Bloods.

**Agent security and multi-agent systems**
- Debenedetti et al., Google DeepMind (2025). CaMeL, arXiv 2503.18813. Closest prior work before summer 2026; no failure model.
- Greshake et al. (2023). "Not what you've signed up for", indirect prompt injection.
- Cemri et al., Berkeley (2025). Why Do Multi-Agent LLM Systems Fail? arXiv 2503.13657. Step repetition 17.14% across 1,600+ traces. **The 17% figure was flagged in transcripts as not independently checked.**
- Open Challenges in Multi-Agent Security, arXiv 2505.02077 (2025).
- Anthropic (June 2025). How we built our multi-agent research system. Source of the 4x/15x token figures.
- Cognition. Don't Build Multi-Agents. "Keep writes single-threaded."
- Mosaic (June 2026). The Coordination Problem, mosaic.inc/blog/memo. "Retry is close to free."

**2026 papers on this layer**
- Lyu et al., Huawei (Sept 7 2026). ATR, "From Version Conflicts to Decision Conflicts: Selective Revalidation for Long-Running AI Agents", arXiv 2609.08015. Code: github.com/ezreal13/atr-decision-validation.
  - Typed premises, KEEP / REFRESH / REPLAN / BLOCK outcomes, a refund-agent example.
  - Explicitly excludes crashes, partial effects and non-idempotent APIs.
- Chen et al., Tsinghua (EuroSys 27). Cordon, "Semantic Transactions for Tool-Using LLM Agents", arXiv 2606.17573.
  - Effect outbox. "Dispatched effects are not resent unless the runtime has idempotency evidence"; unproven dispatches go to an audit or compensation state.
  - No code released.
- Zheng et al., WashU and SMU (Sept 10 2026). "Engineering Reliable Commit Gates for Agentic AI", arXiv 2609.10969.
  - Evidence-source diversity beats verifier-model diversity; "After-check races defeat verifier-only gates".
- SagaLLM (VLDB), arXiv 2503.11951.
- Agentic Transaction: Towards ACID-Compliant Agent Systems, arXiv 2608.13900.
- Khan (June 2026). Verified Detection and Prevention of Concurrency Anomalies in Multi-Agent LLM Systems, arXiv 2606.17182. TLA+ isolation levels, Rust runtime.
- Uchibeke, APort (March 2026). Before the Tool Call: Deterministic Pre-Action Authorization for Autonomous AI Agents, arXiv 2603.20953. Fail-closed policy; no state freshness.
- Notarized Agents, arXiv 2606.04193 (June 2026). The receiving service signs a receipt per action; after the fact, with no exactly-once and no fire-time re-check. https://arxiv.org/abs/2606.04193. Found in the 18:16 search; called "closest to our receipts idea, cite it".
- τ-bench, arXiv 2406.12045 (https://arxiv.org/abs/2406.12045). Considered for the landing page, not used.

**Citation verification (13:49).** ATR, Cordon and Commit Gates were checked against the full PDFs: titles, affiliations and quoted claims match. SagaLLM, Agentic Transaction, Khan, APort, CaMeL and Cemri were **not verified**.

### 3.2 Shipping systems and layer map (`docs/03-landscape.md`)

| layer | who |
|---|---|
| artifacts in | Inner (getinner.ai, YC S26 per whole story) |
| policy and inventory | Snyk Evo / Agent Guard |
| orchestration | Linear Agents, OpenAI Symphony |
| durable execution | Temporal, Restate, Inngest, DBOS, Prefect, AWS Lambda durable functions, Cloudflare Workflows, Vercel Workflow |
| agent frameworks with durability | Pydantic AI (first-party Temporal/DBOS/Prefect/Restate), LangGraph checkpoints |
| injection containment | CaMeL |
| dedup at receiver | Stripe idempotency keys, Kafka EOS |
| agent-native payment rails | Natural, Ralio, Paygentic |
| agent payment protocols | Google AP2, OpenAI/Stripe ACP |
| pre-action authorization | APort Open Agent Passport |
| parallel-agent workspaces | Superconductor, Conductor, Superset, Augment Intent |
| conflict heuristics | moire, conflict-check, sol |
| multi-agent runtimes | Claude Code Agent Teams, AutoGen |
| hackathon peer | Cloud-Bean (github.com/danielyangdev/Cloud-Bean): verifies the observer; its README notes it lacks "service receipts" |

### 3.3 Competitor search, 18:16 (transcript 187016d4; mostly search snippets)

**Salus** (YC W26, $4M; funding **unverified**)
- Sits between the agent and its tools. Lets actions through, rewrites them, or escalates, at decision time. Nothing seen on crashes or receipts.
- Called the most direct competitor for "fewer manual approvals".
- Links: https://www.ycombinator.com/companies/salus/jobs/S2nl2Hx-founding-gtm-bdr-ai-agent-infrastructure, https://www.startuphub.ai/ai-news/claudes-corner/2026/claudes-corner-salus-yc-w2026, https://x.com/salus_ai

**open-multi-agent** (TypeScript, 6.9k stars, MIT)
- Human approval with a hash of what the reviewer saw; hash-checked run record.
- Nothing on crashes or fire-time re-checks.
- https://github.com/open-multi-agent/open-multi-agent

**Other tools**
- **durable-agents** (PyPI): Postgres event log; cleans up cut-off tool calls on resume. Page did not load, so **unverified**. https://pypi.org/project/durable-agents/
- **APort**: https://aport.io (snippet only).
- **MCP gateways**: Maxim Bifrost, IBM ContextForge, LiteLLM PR #38241 (https://github.com/BerriAI/litellm/pull/38241). Rule-based gating; Bifrost keeps a signed audit log (snippets only).
- **Approval tooling**: HumanLayer (reportedly pivoted; https://orako.io/compare/humanlayer-alternative), Orako, Zapier human-in-the-loop (https://www.usecarly.com/blog/human-in-the-loop-automation-tools/), n8n, OpenAI Agents SDK `needs_approval`. Temporal human-in-the-loop: https://docs.temporal.io/ai-cookbook/human-in-the-loop-python, https://temporal.io/blog/human-in-the-loop-approvals
- **Funded agent-payment startups** (amounts from snippets, **unverified**): Natural ($9.8M seed, $30M Series A), Ralio ($2.5M pre-seed), Nekuda ($5M), Skyfire ($9.5M).
- **Durable-execution news** (unverified detail): Restate bring-your-own-cloud (July 2026); DBOS Go SDK and Databricks Lakebase partnership (April 2026).

**Evidence the problem is real, and why-now signals** (snippets)
- claude-code issue #64814 (https://github.com/anthropics/claude-code/issues/64814): double charge.
- An X API duplicate charge; a dev.to post on a support agent claiming a charge after failed lookups; Chargeflow on AI-agent chargebacks.
- IETF draft-sharif-agent-audit-trail.
- Posts titled "Exactly-Once Is a Lie for AI Agents" (postsyntax Substack) and "The Idempotency Key Your Agent Forgot to Send". Their authors and several LinkedIn posters were suggested as interview contacts; names omitted here.

### 3.4 Market and approval statistics used, with status

**Cited in repo docs (`docs/01-problem.md`, `docs/00-the-whole-story.md` section 10)**
- **J.P. Morgan 2025 Treasury Services Benchmarking.** 61% cite payment reconciliation as their most time-consuming manual process, up from 44% in 2022. Verified in transcript via https://ctmfile.com/story/10-must-know-payments-and-treasury-insights-from-2025-to-inform-2026; the "400 executives" detail was dropped as unconfirmed.
- **IDC.** 10x agent use and 1000x token/API call load by 2027 (https://www.idc.com/resource-center/blog/agent-adoption-the-it-industrys-next-great-inflection-point/, via https://blog.equinix.com/blog/2026/08/13/how-close-is-your-ai-infrastructure-to-the-agents-that-depend-on-it/). Corrected: 1000x is API call load, not agent use.
- **Gartner (June 2025).** Over 40% of agentic AI projects canceled by end of 2027, citing "inadequate risk controls" (corrected from "governance failures"). https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
- **Kore.ai Agent Productivity Index 2026, "8 in 10 enterprises".** Transcripts repeatedly say it has no source; removed from video v2. Still present in `docs/01-problem.md` and the whole story. **Unverified.**
- **McKinsey 30% of finance time; Levvel 1.2% duplicates; 56.6% task success; 60% to 25% decay over eight runs.** No source found in transcripts. **Unverified.**

**Added later**
- **KPMG Q1 2026 AI Pulse.** 63% of large US companies require humans to validate agent output, up from 22%. Verified. https://kpmg.com/us/en/media/blogs/2026/q1-ai-pulse-1.html
- **Anthropic, "How we built Claude Code auto mode".** People approve 93% of permission prompts (the transcript also mentions 93 to 97% and 13.6% of dangerous commands caught). 93% verified. https://www.anthropic.com/engineering/claude-code-auto-mode
- **EMA / Cequence (Aug 2026).** 65% of enterprises saw agents act outside scope; 29% had measurable impact; only 34% check authorization at action time. The press release headline says 33%. https://www.globenewswire.com/news-release/2026/08/31/3353329/0/en/new-cequence-ema-research-94-of-enterprises-trust-their-ai-agents-aren-t-over-provisioned-only-33-actually-enforce-it.html and https://www.infosecurity-magazine.com/news/65-percent-enterprises-ai-agents/
- **Clyro "88%" and "500 incidents".** Could not be verified; recommended to cut. https://clyro.dev/blog/the-5-ai-agent-failure-modes-why-they-fail-in-production/
- **APQC via CFO.com (March 2020).** Duplicate or erroneous disbursements: 2% bottom performers, 0.8% top performers. https://www.cfo.com/news/metric-of-the-month-detect-and-prevent-duplicate-or-erroneous-payments/656852/ and https://www.apqc.org/resources/benchmarking/open-standards-benchmarking/measures/percentage-total-annual-number
  - Used on the landing page next to Interlock "0%" from the 2,000-case test sweep.
  - The transcript itself flags that these are not the same kind of measurement.

---

## 4. Technical findings and measured results

### 4.1 Design (`README.md`, `docs/02-contract.md`)

**Five rules**
1. Journal the decision (DISPATCHED, fsync) before acting.
2. Effect id is bound to the approved request, never the model output.
3. Actions carry premises, re-checked at commit.
4. Authority is a lease checked at dispatch.
5. Recovery never guesses: retry if the target dedupes, look up if queryable, else AMBIGUOUS. Re-check lease and premises before any resend.

**Invariants.** I1 no effect without a journaled decision; I2 no duplicate commit; I3 no stale premise; I4 no dead lease; I5 payload binding; I6 no duplicate implementation.

**Cooperation ladder**
- Tier 1: dedup within a window (Stripe 24h, treated as expiring 10 minutes early).
- Tier 2: lookup.
- Tier 3: neither. At-most-once with AMBIGUOUS.

**Implementation details**
- Claims: `claim_ttl` defaults to 120s in `interlock/journal.py`. The backend uses 40s; the demo uses 15s.
- Effect id: SHA-256 truncated to 48 bits in the demo.
- Size: core about 400 lines of Python, zero dependencies (README). The protocol files are about 250 lines (`docs/00-the-whole-story.md` section 8).

### 4.2 Findings

- **1.** Exactly-once is a property of the target, not the client. Tier 3's honest guarantee is at-most-once with surfaced ambiguity. Measured cost: a refund that never happened stays blocked after crash-before-send (`results/refund_agent.md`).
- **2.** Idempotency keys are necessary but insufficient. They still refund under a revoked lease and on an ineligible order (`results/refund_agent.md`).
- **3.** Premise granularity is a dial with a floor.
  - File-hash premises over-refuse benign edits.
  - Symbol premises land benign edits and catch renames and duplicated work with zero model calls.
  - Neither catches a same-signature meaning inversion (`results/coding_agents.md`).
- **4.** Recovery is when the world moves. `recover()` had resent without re-checking; fixed so a resend is a new dispatch, and past the dedup window tier 1 becomes a lookup (README).

### 4.3 Simulated experiments (`python3 experiments/run_all.py`, under a second)

**Refund agent** (`results/refund_agent.md`, 2026-09-13 17:36 UTC): 11 fault rows including a happy-path control, 6 systems.
- Naive: $40 on crash-before-ack, duplicate submit, refund during outage and key expired. $50 on model re-decides and conflicting payload. Refunds under a revoked lease and a stale eligibility.
- idempotency@tier1 and durable@tier1 pass crash, duplicate and re-decision rows. They fail lease_revoked, stale_eligibility, refund_during_outage ($40), lease_revoked_during_outage and key_expired ($40).
- Gate at tiers 1 and 2: all held.
- Gate at tier 3: AMBIGUOUS on crash_before_send ($0), crash_before_ack, refund_during_outage, lease_revoked_during_outage and key_expired.
- Wrong outcomes out of 10 faults, summarized in transcripts and the checkpoint 2 docx: naive 9, idempotency key 5, durable execution 5, Interlock 0 (tiers 1 and 2). At tier 3, 5 of 10 are handed to a person.

**Parallel coding agents** (`results/coding_agents.md`): 7 faults, 3 systems.
- gate/file refuses `benign_reformat` (availability lost).
- gate/symbol lands `semantic_only` broken.
- `duplicate_work` is caught by the claims registry.

**Approval inbox** (`results/approval_inbox.md`, seed 4471). The mix is an assumption: 60 routine, 15 over limit, 5 flagged, 5 ineligible, 5 duplicate, 5 crash, 5 refunded by hand, plus 3 over-limit hand-refunded between approval and send.

| system | reviews | wrong refunds |
|---|---|---|
| everyone approves | 100 | 8 |
| rules only | 25 | 8 |
| rules + Interlock | 33 | 0 |

Of the 33, 25 need judgment and 8 could not be sent safely.

After the escalation build (in `Interlock-build`, per journal wf_f782b281; **not in this checkout, unverified here**): 65 of 95 unique requests cleared with no person, rules + Interlock reviews rose from 33 to 36, and baseline wrong orders rose from 8 to 10 with partial hand refunds added.

**Tests** (README)
- 53 tests: a 2,000-case randomized sweep, 8 workers racing on JSONL and SQLite, receipt tampering, MCP proxy killed mid-call.
- CI on Python 3.9, 3.12 and 3.13; fails if `results/` drifts.
- 15 real bugs found and fixed: 6 by our own tests, 9 by an adversarial review, including a critical double send during recovery.
- Later counts in transcripts: 54 after the viewer change, 57 to 61 after the live backend, 144 in `Interlock-build` after the escalation merge (**unverified in this checkout**).

### 4.4 Real services, first pass

**Stripe test mode** (`results/stripe_live.md`, 16:50 UTC; 3 faults x 3 systems)
- crash_before_ack: naive $40, key $20, gate $20.
- duplicate_submit: naive $40, key $20, gate $20.
- refund_during_outage: naive $40, key $40, gate $20 (`REFUSED:stale_premise_at_recovery`).
- All nine PaymentIntents re-checked with the Stripe CLI at 13:49 and matched.

**Temporal dev server** (`results/temporal_live.md`, temporalio 1.32.0; 4 faults)
- Temporal with its recommended key: crash_before_ack $20; refund_during_outage $40; lease_revoked_during_outage $20 (should be $0); stale_eligibility $20 (should be $0). So 3 of 4 wrong.
- Interlock as the activity body: all 4 correct.
- Re-run at 13:49 matched row for row.

### 4.5 End-to-end live backend (`results/e2e_live.md`, 21:57 UTC; `results/e2e_audit.txt`)

**Setup**
- Model `claude-haiku-4-5-20251001`, temporalio 1.32.0, Temporal dev server, Stripe test mode.
- Workers are separate OS processes killed with SIGKILL (exit -9 recorded).
- 8 scenarios x 3 columns, 22 cells. The independent auditor re-read every cell from Stripe: 22/22 (`docs/08-pitch.md`). A verifier reported 19/19 checks passing on a rerun (journal wf_21995490).

**Tally over the 7 rows all columns ran**

| column | left Stripe as wanted | answers matched Stripe | median crash to close |
|---|---|---|---|
| Temporal, key, no re-check | 4/7 | 6/7 | 16s |
| Temporal plus hand-written re-check (about 10 lines) | 6/7 | 7/7 | 15s |
| Temporal with Interlock as activity body | 6/7 | 7/7 | 43s |

**Per-row notes**
- Plain Temporal $40 on hand_refund_during_outage; refunded under a revoked approval.
- Hand-written check and Interlock identical on 7/7 rows. Both go SHORT by $20 on `unrelated_refund_during_outage`: an unrelated $5 goodwill refund changes the premise.
- `key_pruned_after_24h` and `no_lookup_after_24h` are EMULATED (a never-seen key, and Interlock's clock moved 25h). AMBIGUOUS end to end appears only in the emulated no-lookup row.
- Receipts are unsigned (`signed=None`).
- Latency cause: a SIGKILLed sender's claim blocks recovery until the TTL expires (40s backend default; `backend/config.py`).

**Verifier findings** (journal wf_21995490)
- "Better than Temporal" was overstated. What was proven is "idempotency key alone".
- The emulation was asymmetric.
- A fairness verifier added a 3-line "refund with my workflow_id exists?" lookup to the hand check and re-ran live. That column then matched Interlock on all 6 shared rows in 2 attempts instead of 8.

### 4.6 Demo page runs (`results/demo_live.md`, `results/demo_live_revoked.md`, 22:33 UTC)

Headless Chromium clicked "Run live" (with a double-click guard check) and then "Run mock". Claim TTL 15s, Stripe timeout 10s.

**Hand refund during the outage** (run `524b199586`, 23.1s from click to finished page)
- Standard setup: 2 refunds, $40, 16.8s crash to close.
- Interlock: 1 refund (the hand one), 16.2s, `REFUSED:stale_premise_at_recovery`.
- Page matched Stripe exactly: True. 0 MOCK badges on the live page.

**Approval revoked during the outage** (run `bf055e581b`, 23.1s)
- Plain Temporal refunded $20 (violated).
- Hand check: `REFUSED:lease`, 15.7s.
- Interlock: `REFUSED:lease_at_recovery`, 15.6s.

**Mock run.** Fully labeled MOCK. No processes left running.

### 4.7 Real-world scenario suite (`docs/10-scenarios.md`, `results/scenarios/*.md`)

Columns: held invariant / proof record / settle seconds.

| scenario | no_check | hand_check | interlock |
|---|---|---|---|
| stripe_dispute | 2/2, 0/2, 6.8 and 8.6 | 2/2, 2/2, 6.4 and 11.2 | 2/2, 2/2, 42.4 and 43.0 |
| shared_cap (20 reps x 2 crash points) | 0/40 | no shared state 4/40; hand_lock (flock) 40/40, 0/40 proof, median 0.5/1.4 | core 25/40 (40/40 proof); with CapJournal subclass 40/40, median 40.1/41.7 |
| billing_credit | 5/6 | 6/6, 6/6, median 17 | 6/6, 6/6, median 41 |
| github_merge (3 reps x 2) | 3/6 | 6/6, 6/6, median 7.7/2.5 | 6/6, 6/6, median 26.1/24.4 |
| calendar | 5/7 | 7/7, 0/7, median 0.6 | 7/7, 7/7, median 31.2 with an "empty slot" premise override; `easy.py` as shipped 0/1 (double booked) |
| email_tier3 (Resend) | 2/3 | with key probe 3/3, 3/3; idiomatic 3/3, 2/3 | with probe 3/3, 3/3; no probe 3/3, 1/3; tier 3 3/3, 0/3; median about 36 |
| gcp_resource | 0/3 | 3/3, 3/3, 0.5 to 2.1 | 3/3, 3/3, 30.6 to 30.9 |
| connect_payout | BLOCKED | BLOCKED | BLOCKED |

**Takeaways**
- Interlock tied the strongest hand check in all 7 scenarios that ran. In two it tied only with code outside the core; without that code it lost both.
- It settled slower in all 7.
- no_check violated its invariant in 6 of 7.
- In stripe_dispute, a chargeback landing minutes after a successful refund lost $120 on a $100 payment in test mode. No column catches it.
- In github_merge, unsigned receipt chains accepted 6/6 forgeries; keyed verify accepted 0/6. Proposal: rename `tamper_evident` to `chain_consistent` unless signed.

**Eight proposed core changes** (not made; `docs/10-scenarios.md`)
1. Cap reservation at dispatch.
2. Claim liveness (owner pid or heartbeat).
3. Premises with expected values.
4. Keep the target's return values.
5. Don't overclaim tamper evidence.
6. Post-commit settlement entries (for example `refund.failed`).
7. Surface blocked recovery as CLAIMED.
8. Optionally, write receipt bundles at recover.

### 4.8 Pre-judge verification (transcript 5a5dc3ca, 13:49)

- **Tests.** A clean clone ran 53 tests, all passing; the README count matched.
- **Stripe.** All nine PaymentIntents in `results/stripe_live.md` are real test-mode payments with matching refunds, checked via the Stripe CLI.
- **Temporal.** A re-run matched `results/temporal_live.md` row for row.
- **Papers.** ATR, Cordon and Commit Gates checked against full PDFs; claims match.
- **Demo block.** The README "See it work" block showed stale output; fixed in `591c6d3`. At 15:11 a later README edit had reintroduced the old journal id `8351811bed3d`, while the demo prints `6b6f07d3ceb0`. Left as an open question.
- **Receipt field fix.** The receipt's `executed` field meant "committed to sending". It was fixed to report target-confirmed true, false or unknown (transcript 187016d4, 12:52).

### 4.9 Google ADK, AP2 and GCP export research

**ADK** (`docs/09-research-adk.md`)
- `google-adk` 2.9.0, Apache 2.0.
- `before_tool_callback` returning a dict skips the tool body. After-callbacks also run when the tool was skipped.
- `ResumabilityConfig` is documented in source as at-least-once, leaving idempotency to the tool.
- Claude Haiku via LiteLlm smoke test: verified live.
- Gemini 2.5 Flash: 429 RESOURCE_EXHAUSTED (no prepayment credits).
- `temporalio` 1.32.0 ships `temporalio.contrib.google_adk_agents`. Under Temporal the gate must sit in the activity, not the callback. Design note only.

**AP2** (`docs/09-research-ap2.md`; repo `google-agentic-commerce/AP2` at `e1ea56d`, v0.2.0)
- Apache-2.0. Two mandate types (Checkout, Payment), each open or closed, as SD-JWT chains.
- No refund mandate, no revocation. Double-spend prevention is pushed to stateful parties.
- SDK tests: 186 passed, 2 failed (aud/nonce not enforced on intermediate hops).
- Probe results:
  - The same presentation was accepted twice.
  - A presentation 4 minutes past `exp` was accepted (300s default skew).
  - A stale usage context was accepted.
  - A JPY budget was mis-scaled (`int(max*100)`).
  - Recurrence mandates cannot be signed (Frequency enum serialization bug).

**GCP audit export** (`docs/09-research-gcp-audit.md`, `results/export_live.json`)

| destination | result |
|---|---|
| Cloud Logging | 40 entries sent and 40 returned per export; the hash chain rebuilt from Logging verified all 8 effects |
| Cloud Trace via OTLP JSON | 8 spans, HTTP 200. `gcp.project_id` is required (400 without it). A possible duplicate from re-export was not determined |
| SIEM files (JSONL, CEF) | local only |
| BigQuery | failed live: MERGE returned `400 Syntax error: Unexpected keyword AT` |

Other findings:
- BigQuery `insertAll` returns HTTP 200 with `insertErrors`; insertId dedup is best effort for one minute.
- The Logging `_Default` bucket keeps 30 days.
- `results/export_live.md`, referenced by `docs/08-compliance-mapping.md`, was never written.

**Compliance mapping** (`docs/08-compliance-mapping.md`)
- Receipt fields are mapped as evidence, not certification, to SOX ITGC (SEC 33-8810, PCAOB AS 2201 .47), SOC 2 CC6.1 to CC8.1, PCI DSS v4.0 Requirement 10, EU AI Act Articles 12, 14(4), 19 and 26(6), and NIST AI RMF.
- PCI 10.2.2 fields and 10.5.1 retention come from secondary sources and are marked NOT VERIFIED.

### 4.10 Durable runtime (`docs/07-runtime.md`, `runtime/`, `spec/`, `results/runtime_live_agent.md`)

**Spec**
- `interlock_runtime`: about 900 lines of Python on Postgres, one dependency (`psycopg`).
- Borrows from Absurd (SKIP LOCKED claims, DB clock, fencing), DBOS (steps by call order, fork), Temporal (retry defaults, `patched()`) and Restate (version pinning, design only). No code vendored.
- Mechanisms: one fenced transaction per write; `T_dispatch` / `T_commit` around each send with `send_deadline + settle_margin`; the journal entry format unchanged so `receipts.verify()` runs as-is; recovery ported row for row from `gate._recover_one`.

**Concessions stated in the spec**
- Worse than Temporal: scale, parallel steps, Updates and queries, UI, Python only, maturity.
- Equal at tier 2 under a pause beyond the configured bound or a slow target.

**Live run** (19:11 EDT)
- Real Stripe payment of 10000 cents; Claude decided 2000.
- w1 SIGKILLed after the model response. The workflow suspended for approval; approved via script, standing in for a human. w2 SIGKILLed after the send.
- w3 took over after the lease, waited 35s + 10s, re-checked, and resent under the same key.
- Result: `COMMITTED_BY_RETRY`, Stripe `already_processed`, exactly 1 refund. `verify()` valid, `signed: null`. The 3600s sleep was emulated as 5s.

**Build finding** (`docs/07-runtime.md` 13.4). On macOS, `os.kill(os.getpid(), SIGKILL)` is not synchronous; a "killed" worker still sent a refund. Any earlier instrumented-SIGKILL result that did not check the target access log should be treated as unverified.

**TLA+ model**
- `spec/Runtime.tla`, `Signals.cfg`, 2 assumption configs and 10 broken configs exist.
- `results/runtime_tlc.md` does **not** exist. The invariant table in `docs/07-runtime.md` 10.6 is a prediction, not a result.
- The Prove harness (100+ random kills, network faults vs Temporal and Temporal plus a check) is listed as not built (13.6). No `results/runtime_*` comparison files exist beyond the single live agent run.

**Design-judge scores** (journal wf_fdfc9d01). The journal-native own-core design was rated highest by all 3 judges: correctness 7 to 8, Temporal parity 6 to 8, agent-native edge 8 to 9, ops simplicity 8, buildable now 8.

### 4.11 Escalation build (journal wf_f782b281, wf_ed438274; in `~/Downloads/Interlock-build`; not verified in this checkout)

**Five lanes merged**
1. Explained refusals with repairs (`still_fits`, `refund_remaining`).
2. Routing groups with SLA escalation; restart-safe inbox; the gate refuses sends without approval of the latest escalation.
3. Escalations and decisions on the receipt chain; `verify()` reports `approved_by` and `approval_verified`.
4. Stripe webhook confirmation: signature and replay checks, CONFIRMED entries, lookup fallback.
5. A scoreboard.

**Stripe probe findings.** `refund.created`, `refund.updated` and `charge.refund.updated` carry `interlock_effect_id`; `charge.refunded` does not. There is a 5-minute signature tolerance. Duplicate events happen.

**Live run** (19:10). A $50 request escalated past a $10 auto limit and was approved. A $30 hand refund caused `REFUSED:stale_premise`. The repair "still_fits" was accepted and committed once, and a webhook CONFIRMED it. An SLA breach moved an item to finance-manager.

**Bug hunt.** Round 1 reproduced at least 17 findings. Final state and push to `main`: **unverified** (the workflow was still running at transcript end).

---

## 5. Judge and mentor feedback (paraphrased)

### Checkpoint 1 judge (`docs/checkpoints/checkpoint-1.md`; scorecard reviewed in transcript 187016d4)

**Scores**
- Innovation 6/10 (30%).
- Business value 5/10 (25%).
- Presentation 2.5/10 (20%).
- Technical implementation not scored directly (no code); filled in from the other categories. The transcript reads it as 3.55 and totals about 4.4/10. **Arithmetic unverified.**

**Comments, paraphrased**
- The video was hard to follow without the overview document; add voice narration.
- Explain the competitive landscape, existing solutions, and why Interlock is better or has a higher success rate.
- What is the technical implementation and intended MVP for the hackathon? The judge guessed a Stripe integration.
- How would integration into other products work?

**Team response** (checkpoint-1.md table): README as the presentation, `docs/03-landscape.md` with a feature matrix, built MVP plus experiments, Stripe as a tier-1 target, and LangGraph / MCP / SDK / Temporal integration sketches.

**Assistant's read of the silent video**
- Three stories at once confused the judge.
- The landscape slide compared coding-agent tools while the demo was about refunds.
- The integrations orbit implied six tools were done.
- The trace was mocked.

### Checkpoint 2

- Questions posed to judges (`docs/checkpoints/checkpoint-2-submission.txt`): is the tier-3 AMBIGUOUS impossibility result the kind of negative result the track values, or should the team build the notary? Is a coverage-distribution study the right next experiment?
- No checkpoint 2 scores or judge responses were found in any source.

### Google-affiliated mentor (written reply received about 18:05 ET, transcript 026b49e3)

**Paraphrase**
1. Pre-flight hooks such as `before_tool_callback` are useful. Enterprise systems rely on stateful orchestration like Temporal, not the LLM client, for idempotency and distributed state under crashes.
2. The best architecture should not depend on AP2 or future platform tooling adding execution-time checks. Treat Interlock as agnostic middleware that enforces pre-flight conditions and emits receipts alongside any mandate protocol. The mentor would not comment on unannounced roadmaps.
3. In Google Cloud enterprises: Risk and Compliance mandate approval policy, Platform Engineering builds the execution framework, and Finance or line of business holds operational authority. Receipts that plug into existing audit and compliance tooling would be a major differentiator.
4. Credibility comes from a clear, repeatable before/after failure demo: a standard setup double-charging after a simulated crash, then Interlock intercepting, validating state and preventing the duplicate.

**What the team did.** Middleware pitch (`docs/08-pitch.md`), ADK adapter and research, AP2 adapter and research, Cloud Logging / OTLP / SIEM / BigQuery exporters, compliance mapping with the three-buyer table, and the one-click live before/after demo page (`demo/`).

**Earlier questions for the same mentor** (drafted 13:34 ET; whether sent is unverified):
- ADK crash and retry semantics.
- AP2 execution-time re-checks.
- Spanner vs Firestore vs Cloud SQL for a shared journal.
- Exactly-once effects on Google Cloud.
- Cloud KMS for signing receipts.
- Approval fatigue among customers; who owns such a tool; evidence regulated customers need.

### User feedback that shaped the work (Kiro, paraphrased)

- The pitch cannot hinge on an edge-case double refund.
- Tiers are confusing; show one solution.
- No mock data or terminal-only demos on the live path; keep a separate labeled mock button.
- Push feature sets straight to `main`.
- Keep deliverables professional and restrained.
- Landing page: remove fine print and subtext labels; lead with "We broke a $20 refund 10 ways"; show Interlock lowest on the approvals chart. The assistant declined to show 0 reviews because the measured value was 33, and switched to wrong-refund and APQC error-rate charts instead.
- Earlier, the user said to stop editing the landing page and focus on program quality.

---

## 6. Rejected or deprioritized directions, and why

**Problem areas not pursued** (`docs/00-the-whole-story.md` sections 2 and 7)

| direction | why dropped |
|---|---|
| sandboxed environments | a different layer (artifact admission); already built by Inner, a funded startup |
| prompt-injection detection | a model-quality claim needing a benchmark; the brief separates model quality from protocol guarantees. Kept only as containment (untrusted data cannot mint authority) |
| data poisoning, specification gaming | out of scope: correct execution does not make a decision true |
| security vs efficiency | a positioning axis, not a research axis |
| multi-agent communication | every message arrives too late or becomes a check at commit, so build the check at commit |

**Mechanisms rejected**

| approach | why it fails |
|---|---|
| log more | a log records only what the logger saw |
| TLS-terminating network proxy | a third party in the same problem; nobody allows TLS termination on payment traffic |
| idempotency keys alone | refund under a revoked lease or an ineligible order |
| durable execution alone | replays the stale decision |
| a bad-action detector | a model-quality claim |
| hashing every file read | over-refuses benign edits |

**Storytelling and scope changes**
- **Coding-agent story as a headline.** Crowded (moire, sol, Augment Intent), off-brief, hard to demo a guarantee. Kept in the repo as generalization evidence only.
- **Treasury reconciliation as a product.** A cost, not a product; kept as one market stat.
- **Per-tier columns in pitch materials.** User found them confusing; replaced by one Interlock column plus a caveat sentence.
- **"That system did not exist. Now it does" and "nobody owns this layer".** Softened after the ATR, Cordon and Commit Gates papers were found.
- **Claim that Temporal double-refunds on a plain crash.** Shown false by measurement; removed.
- **"Replace Temporal" as the headline.**
  - The assistant advised against it: a multi-year engineering race, the hardest possible sale, and the evidence showed value inside Temporal.
  - The user overrode and the runtime was built.
  - After the mentor feedback and live results, the pitch moved to middleware, with the runtime at most a secondary note, and only if proven (memory `interlock-professional-restraint.md`, transcript 19:04).
- **"Better than Temporal" on money.** Withdrawn after a hand-written re-check tied on every live row (`results/e2e_live.md`) and in all 7 scenarios (`docs/10-scenarios.md`). The remaining claim is packaging, cross-worker claims, AMBIGUOUS, and receipts.

**OSS components rejected for the runtime** (`research/durable-cores.md`, `research/authority-receipts-events.md`, `research/proof-tools.md`)

| component | why rejected |
|---|---|
| Restate | server is BSL 1.1 and stores state in RocksDB, not Postgres |
| Inngest | SSPL server; needs Redis |
| DBOS | automatic takeover of a dead executor needs proprietary Conductor |
| Hatchet | separate Go engine plus API server |
| River | Go workers only; workflows are paid (Pro) |
| Procrastinate, pgmq | too low level (queue only) |
| Temporal | the baseline to measure against, not a base |
| OpenFGA | extra server; revoke race outside the dispatch transaction |
| OPA | extra server; bundle lag; best-effort decision logs |
| Rekor, Trillian, Tessera | Go servers and non-Postgres storage; Trillian is in maintenance mode |
| pymerkle | GPL-3.0; no release since 2023 |
| merkletools | no consistency proofs; stale |
| Debezium | JVM; only needed for foreign databases |
| P language | needs .NET; not clearly better than TLA+ |

**Smaller rejections**
- Plain-English policies interpreted by an LLM: fuzzy; code rules keep receipts checkable.
- A full gateway: the MCP proxy covers that entry point.
- Two-approver rules and business-hours SLAs: deferred until a customer asks.
- Seven-language code tabs like Temporal's site: would be fake, since only Python, the Temporal helper and the MCP proxy exist.
- The Clyro statistic: unverifiable. The McKinsey, Levvel 1.2% and "8 in 10" statistics were cut from videos for lack of sources.
- Notary service (lifts tier 3 to tier 2): designed in `docs/04-integration.md`, never built.

---

## 7. Open questions and known limits

**Evidence gaps**
- No sourced number for how much approval work is mechanical versus judgment. The approval-inbox mix is an assumption, and no customer interviews have happened: only a plan (10 interviews, Mom Test questions, `docs/00-the-whole-story.md` section 13).
- `results/runtime_tlc.md` missing: TLA+ outcomes are predictions. Prove harness not built. "Better than Temporal" for the runtime is unmeasured.
- ADK live cells not recorded (`results/adk_live.md` absent). ADK inside Temporal not built. Gemini not verified (429).
- Export gaps:
  - BigQuery export failed live; the BigQuery queries in `docs/08-compliance-mapping.md` have not run against the service.
  - A possible duplicate span in Cloud Trace is undetermined.
  - Nothing was sent to a real SIEM.
  - `results/export_live.md` was never written.
- The "Crash after Stripe answered" demo scenario has no recorded page run.

**Behavioral limits of the gate**
- Receipts in live runs are unsigned: gate attestation only, and whoever controls the journal can rebuild the chain. `verify()` reports `tamper_evident` for unsigned chains, which a forgery test showed is an overclaim.
- Interlock does not recognize "the same action as a different request". It refuses on any premise change, so an unrelated $5 refund blocks an approved $20 until re-approval.
- Latency: recovery waits out the claim TTL (43s median live vs 15 to 16s for Temporal columns; 25 to 40s TTLs in scenarios). A claim cannot tell a dead sender from a slow one.
- Tier 3 blocks refunds that never happened. AMBIGUOUS end to end was produced only in emulated rows on Stripe; in email_tier3 only on documented features.
- Semantic conflicts (same signature, different meaning) are outside any mechanical premise.
- The core alone failed shared_cap (25/40) and `easy.py` as shipped double booked in calendar; both need proposed core changes.
- Post-commit reversals (a chargeback after a successful refund) are not caught; the proposed post-commit watch is unbuilt.
- Interlock does not judge whether a decision was right. It records who granted a lease but does not enforce who may.

**Operational and repo-state issues**
- Demo API has no auth, binds to 127.0.0.1, and runs one run at a time (`demo/README.md`).
- Local checkout state:
  - Local `main` is one commit behind `origin/main`.
  - Many uncommitted or untracked paths: `backend`, `demo`, `runtime`, `scenarios`, `spec`, `docs/07` to `docs/10`, `research`, `site` edits.
  - Escalation and UI work lives in separate clones (`Interlock-build`, `Interlock-ui`). What has actually landed on GitHub `main` beyond `84787ec` is **unverified**.
- `docs/team-notes/` referenced in README and checkpoint docs is not in the repo.
- `docs/08-pitch.md` says no `runtime/` package exists; one now does, so the doc is stale.
- README still says "exactly once" in places that transcripts flagged as needing rewording after the hand-check tie.
- Landing page (`interlock-self.vercel.app`) is deployed by hand, not from GitHub, so it can drift from the repo. Fine print about simulation was removed at the user's request, so the page no longer states that most faults were simulated.

**Questions still open to judges and the team**
- Does the tier-3 impossibility plus weaker guarantee count as a valued negative result, or should the notary be built?
- Which, if any, of the 8 proposed core changes to adopt?
- Should the runtime be pitched at all?
- Blocked scenarios need account setup (section 8).

---

## 8. External resources and tools used

**Payments**
- **Stripe test mode**, via the Stripe CLI test key (`stripe config`). Used for PaymentIntents, refunds, idempotency keys, refund lookups, disputes (stripe_dispute), Billing with test clocks (billing_credit), and `stripe listen` webhook forwarding.
  - Auditor refuses keys that are not test or restricted-test keys.
  - Stripe Connect not enabled on the test platform: connect_payout BLOCKED (`results/scenarios/connect_payout.md`).
  - Python `stripe` 15.6.1 researched; the repo target uses the standard library only.

**Models**
- Anthropic API, model `claude-haiku-4-5-20251001`; the only working LLM key, in a local .env outside the repo (memory note).
- OpenAI keys on disk lacked model scope; the Azure OpenAI resource had no deployments.
- Gemini 2.5 Flash via AI Studio returned 429 (no credits).
- Anthropic SDK 1.5.0 researched; the runtime live path uses the official `anthropic` SDK.

**Durable execution and databases**
- Temporal: local dev server; `temporalio` 1.32.0 (server v1.32.0 released 2026-09-11), run with `uv run --no-project --with temporalio`.
- Postgres 17 (Homebrew `postgresql@17`) for `interlock_runtime`, driver `psycopg[binary]>=3.2,<4` (LGPL-3.0).
- SQLite (WAL) for the shared journal.

**Google Cloud** (one project, id omitted)
- Cloud Logging `entries.write`, Cloud Trace via OTLP/HTTP JSON at `telemetry.googleapis.com`, BigQuery `insertAll`/MERGE.
- gcloud user credentials; GCS for gcp_resource (`ifGenerationMatch`); Google Calendar API for the calendar scenario (service account's own calendar).

**Other services**
- GitHub: `gh` CLI, private sandbox repo `kiromoussa/interlock-sandbox` for github_merge (merge `sha` precondition); GitHub Actions CI; CodeRabbit present but did not review (manual review required).
- Resend test addresses for email_tier3.

**Agent frameworks and specs researched** (`research/agent-integrations.md`, `docs/09-*`)

| component | version | license |
|---|---|---|
| `google-adk` | 2.9.0 | Apache-2.0 |
| AP2 | v0.2.0 at `e1ea56d`; SDK tests with cryptography 46.0.5, jwcrypto 1.5.6, pydantic 2.12.5, sd-jwt 0.10.4, pytest 9.0.2 | Apache-2.0 |
| MCP Python SDK | 2.2.0, spec 2026-07-28 | MIT |
| LangGraph | 1.2.11 (checkpoint-postgres 3.1.2) | MIT |
| OpenAI Agents SDK | 0.22.2 | MIT |
| Pydantic AI | 2.43.0 | MIT |
| OTel GenAI semantic conventions | core semconv v1.44.0 | Apache-2.0 |
| LiteLLM | used for Claude in ADK | n/a |

**Durable cores researched** (`research/durable-cores.md`): Absurd 0.5.0; DBOS Transact py 2.31.1; Hatchet v0.106.5; Procrastinate 3.9.0; River v0.47.0; pgmq v1.13.0; Restate v1.7.9; Inngest v1.44.0.

**Authority and receipt tooling researched** (`research/authority-receipts-events.md`)
- cedarpy 4.12.0 / Cedar v4.12.0, measured 0.092 ms per call steady state.
- OpenFGA v1.20.0; OPA v1.20.2.
- Rekor v1.5.4 and v2.3.0; Trillian v1.7.3; Tessera; pymerkle 6.1.0; merkletools 1.0.3.
- RFC 9162, C2SP tlog-checkpoint.
- Debezium v3.7.0.Beta1; Postgres LISTEN/NOTIFY.

**Proof tools** (`research/proof-tools.md`)
- TLA+ TLC rolling jar (TLC2 2026.09.12, rev 867aefb); a 15-line spec was checked locally and found a counterexample.
- Apalache v0.62.2 (not run); P 3.1.0 (not installed).
- elle-cli 0.1.11 with Jepsen 0.3.11 (checked a duplicate-append history locally); Knossos; Porcupine v1.3.0.
- Toxiproxy 2.12.0; Hypothesis 6.168.0.
- Local environment: OpenJDK 26.0.2 and 17 not linked on PATH; Docker daemon not running.

**Demo and verification tooling**
- Headless Chromium (Playwright) for `experiments/demo_browser.py`; WebKit for Safari checks.
- Python 3.9 to 3.14 used across runs; `uv`.

**Presentation stack**
- Remotion (TypeScript/React, `@remotion/google-fonts`, Tailwind v4, hand-written shadcn-style components, BlurJS look reproduced).
- Gamma (deck built from a one-shot prompt; the exported deck had stale numbers).
- A Google Drive-hosted slide (link omitted).
- Vercel (`interlock-self.vercel.app`: landing page, `/viewer`, `/explainer`).
- GitHub Pages link in README (`az-said.github.io/Interlock/docs/interlock-explained.html`).
- 21st.dev CLI (login expired; re-auth attempted; components ported to plain HTML/CSS).
- Shopify AI Toolkit plugin v1.8.2 and Shopify CLI: blocked ("Cannot find a valid organization"); no dev store domain or Admin API token.
- Not attempted for lack of credentials: EasyPost or Shippo, HubSpot.
