# Checkpoint 1 — Saturday 22:00 ET

## What we submitted

A one-page overview and a video. The overview, verbatim from our submission:

> **Interlock: a safety checkpoint for AI agents.** We check that an AI agent's permissions and assumptions are still valid before it acts, then record what happened so crashes and retries can be handled safely.
>
> Between an agent's decision and execution, permissions can be revoked, shared data can change, or a crash can hide whether an action succeeded. This can cause duplicate payments, unauthorized changes, and broken code. Humans must then reconstruct what happened.
>
> Every action carries the assumptions that justified it. Records the decision before execution. Checks permissions and relevant assumptions before the action takes effect. Uses a stable operation ID to prevent duplicates when the receiving service supports it. Tracks what was proposed, authorized, executed, and recorded. Blocks stale actions and requests a fresh plan.
>
> Demo plan: a simulated refund agent with three failures — crash after payment, revoke permission, change order eligibility — compared against an unprotected baseline.

The repo was empty. We said so: day one went to understanding the problem, not code.

## Score

| category | weight | score |
|---|---|---|
| Innovation & Creativity | 30% | 6 / 10 |
| Technical Implementation | 25% | (no code; averaged from others) |
| Business Value & Impact | 25% | 5 / 10 |
| Presentation & Communication | 20% | 2.5 / 10 |


## Feedback, verbatim

- Video presentation is hard to follow without the overview document and still a bit confusing → please add voice explanation.
- What is the competing landscape? What are the existing solutions and why is Interlock better / higher success rate?
- What is the technical implementation idea for the hackathon? What is the intended MVP (Stripe integration?)
- How should the integration in other products work?

## What we did about each

| feedback | answer | where |
|---|---|---|
| hard to follow | the README is now the presentation; runnable in 10 seconds | `README.md`, `demo.py` |
| competing landscape | a layer map and a feature matrix against nine named systems | `docs/03-landscape.md` |
| why better | the only system whose dedup key *is* the recorded decision; a stated per-tier guarantee instead of heuristics | `README.md` → "Why this and not the obvious things" |
| intended MVP | built: gate + journal + two targets + two fault-injection experiments + results | `interlock/`, `experiments/`, `results/` |
| Stripe integration | Stripe is a tier-1 target via `Idempotency-Key`; adapter is four methods | `docs/04-integration.md` |
| integration in other products | LangGraph node, MCP proxy, SDK tool wrapper, Temporal activity | `docs/04-integration.md` |
