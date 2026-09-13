# Plan — checkpoints 3 and 4

In order. Each item: file touched + acceptance test.

- [ ] **1. Demo recording (voice).** `demo.py naive` → `2` → `3`, one terminal, narrated, under 90 seconds. Judge asked for voice by name. Touches: README.md ("See it work" gains the link). Acceptance: link in README plays; total runtime < 90s.
- [ ] **2. Early notification (team spec §5.5).** When A's write set intersects B's live read set, notify B mid-run with a template message, zero model calls. Touches: `interlock/gate.py`. Acceptance: new `early_notification` row in `results/coding_agents.md`.
- [ ] **3. Real GitHub target.** `gh pr merge` as apply, merge-commit lookup as query (tier 2). Touches: `interlock/targets/github.py`. Acceptance: `demo.py --target github` runs against a scratch repo.
- [ ] **4. Coverage distribution (spec §4).** Run the symbol extractor over a real OSS Python repo; report statically-resolvable / coarse / dark fractions. Touches: `experiments/coverage.py`. Acceptance: `results/coverage.md` exists with the three fractions.
- [ ] **5. Notary sketch (docs/04).** Tiny HTTP service both agent and payments target write to, lifting tier 3 to tier 2. Touches: `interlock/notary.py`. Acceptance: `gate@tier3+notary` column where `crash_before_send` is no longer AMBIGUOUS.
