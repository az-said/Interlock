# Checkpoint 2 — Sunday 10:00 ET

## What changed since checkpoint 1

At checkpoint 1 we had a problem statement, two competing specs, and an empty repo. Now we have one runtime, two experiments, and three findings.

**Two specs became one system.** The team wrote two documents on Saturday: a narrow refund-duplicate spec and a broad concurrency-control spec for parallel coding agents. They looked like different projects. They're the same mechanism: an agent decides on premises that are true when it decides and stale when its effect lands, and nothing re-checks them at commit. So we built the gate once and pointed it at two effect targets.

**Built.** Append-only journal; effect identity bound to the approved request (never to a model output); a gate enforcing six invariants; recovery by cooperation tier; a claims registry; two effect targets (payments API at three tiers, local repo at two premise granularities); two fault-injection harnesses with two baselines; a results generator.

**Measured.** 8 faults × 5 systems for the refund agent; 7 faults × 3 systems for parallel coding agents. Every cell regenerates from `python3 experiments/run_all.py`.

**Found.**
1. **Exactly-once effect is a property of the target, not the client.** Achievable when the target dedupes (tier 1) or is queryable (tier 2). When it does neither, crash-before-ack is undecidable; the strongest honest guarantee is at-most-once with the ambiguity surfaced. The cost is measurable: at tier 3 a refund that never happened stays blocked, because crash-before-send and crash-before-ack look identical from the client.
2. **Idempotency keys are necessary and insufficient.** The idempotency-only baseline handles crash, duplicates, and payload conflicts at the service. It refunds under a revoked lease and refunds an ineligible order, because the service cannot see the agent's authority or premises. That gap is the runtime's measured contribution.
3. **Premise granularity is a dial with a floor.** File-hash premises never land broken code but refuse benign edits. Symbol premises land benign edits, catch renames, and catch duplicated implementations with zero model calls, but cannot see a same-signature meaning change. That row is the boundary of any mechanical premise check.

## What changed in our understanding

We came in believing parallel agents fail because they can't communicate. They fail because nothing validates what they assumed at the moment their work lands. Every added message either arrives too late or becomes a check at the commit point. So we built the check at the commit point.

We also thought "decision history" and "no duplicates" were two features. They're one: the recorded decision is the effect's identity.

And we thought the effect id should be a hash of what the model decided. The refund spec corrected that: bind identity to the *approved request*, so a model that re-decides on retry produces the same id with a different payload, and the gate can reject it instead of refunding $50.

## Answers to checkpoint-1 feedback

See `checkpoint-1.md`. Landscape → `docs/03`. MVP → this repo. Integration → `docs/04`. Voice → demo recording.

## Where feedback would help

- Is the tier-3 `AMBIGUOUS` result, stated as an impossibility with a named weaker guarantee and a measured cost, the kind of negative result the track values? Or should we push into the notary design (`docs/04`) that lifts tier 3 to tier 2?
- Finding 3's boundary is where premises end and intent begins. The concurrency spec proposes measuring what fraction of real dependencies are statically resolvable vs coarse vs dark. Is that the right next experiment, or should semantics stay out per the brief's model-quality separation?

## Next

- Real `gh pr merge` target; measure `AMBIGUOUS` rate with and without merge-commit lookup.
- Early notification (spec §5.5): tell B mid-run when A's write set intersects B's read set.
- Coverage distribution on a real repo (spec §4).
- The notary.
