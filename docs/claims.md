# Claims ledger

Every number and comparative claim this repo makes in public, and how to check it. Three statuses:

- **reproduced** — a script in this repo produces the number; run the command shown beside it.
- **source-checked** — the primary source was opened on 2026-09-13 and the quote held.
- **assumption** — stated as an assumption where it is used, with the conclusion's sensitivity to it.

Anything that failed this audit was removed on 2026-09-13, not softened. The full row-by-row audit (350 claims) is in [claims-full.md](claims-full.md).

## Numbers this repo produces

| claim | where it appears | status |
|---|---|---|
| Plain retry pays wrong in 9 of 10 injected refund faults; request IDs 5; durable workflows 5; the gate 0, flagging 5 for a person | README, site, results/refund_agent.md | reproduced — command beside the table in README |
| Live run: 22 of 22 outcome cells re-audited against Stripe test mode; invariants held 4/7 with Temporal alone, 6/7 with a hand-written check, 6/7 with the gate; medians 16s / 15s / 43s | results/e2e_live.md | reproduced — command at the top of that file (needs keys) |
| Across 7 real-service scenarios, a fair hand-written check ties the gate on outcomes; no_check breaks invariants in 6 of 7; the gate pays for its guarantee in time (25–43s claim-TTL waits) | docs/10-scenarios.md | reproduced — per-scenario commands in the doc |
| Repair loop: 17 candidate patches to 3 sends; 13 duplicate sends to 0. Scripted agent, not a model | README | reproduced — command beside the table |
| Approval inbox: reviews 100 to 36, wrong payouts 10 to 0 | docs/00-the-whole-story.md §11 | assumption — the inbox mix is assumed and says so |

## Numbers from outside sources

| claim | source (opened 2026-09-13) | status |
|---|---|---|
| Over 40% of agentic AI projects will be canceled by end of 2027 | gartner.com newsroom, press release of 2025-06-25 | source-checked |
| By 2027, G2000 agent use grows 10x; token and API call loads 1000x | IDC FutureScape 2026 (prUS53883425) | source-checked |
| "agents typically use about 4× more tokens than chat interactions, and multi-agent systems use about 15× more" | anthropic.com, *How we built our multi-agent research system* | source-checked |
| 63% of organizations require human validation of agent outputs, up from 22% in Q1 2025; 54% actively deploying agents | KPMG AI Pulse survey, Q1 2026 (kpmg.com) | source-checked |
| MAST: 1,600+ annotated traces across 7 frameworks, 14 failure modes; step repetition the top mode at 17.14% | arXiv 2503.13657 | source-checked (traces and modes in the abstract; the percentage is from the paper body) |
| Stripe idempotency keys are pruned after at least 24 hours; a reused key then creates a new request | docs.stripe.com/api/idempotent_requests | source-checked |
| Manual invoice processing runs $15 to $16 each; labor is 62% of AP cost (site, "By hand today") | IOFM and Levvel Research benchmarks, APQC labor share, as compiled by Resolve — resolvepay.com/blog/13-statistics-that-quantify-cost-per-invoice-in-manual-vs-automated-flows | source-checked (secondary compilation, opened 2026-09-13; cited as a compilation where used) |

## Comparative claims

| claim | basis | status |
|---|---|---|
| ATR (arXiv 2609.08015) excludes crashes, partial effects, and non-idempotent APIs | its abstract and stated scope | source-checked |
| Cordon (arXiv 2606.17573) stages effects; an unproven dispatch goes to an audit state; no public code found | abstract opened; code search on 2026-09-13 found none | source-checked |
| Commit gates (arXiv 2609.10969): after-check races defeat verifier-only gates, so guards must be atomic | abstract opened | source-checked |
| No shipping system re-checks an action's premises and authority on the recovery path | docs/03-landscape.md feature matrix; each cell traces to vendor docs or the paper named | reviewed 2026-09-12/13 |

A number that appears anywhere in this repo and not in this ledger is a bug. Open an issue.
