# Results: parallel coding agents

Generated 2026-09-13 16:13 UTC by `experiments/run_all.py`. Cells: `outcome · result · invariant`. ✅ held · ❌ violated · ⚠️ held, but availability lost.

Invariant: nothing lands that fails at runtime; nothing lands twice; nothing lands
under a revoked lease. `result` executes the code B added, it does not just import it.

| fault | naive | gate/file | gate/symbol |
|---|---|---|---|
| `rename_break` | APPLIED landed_BROKEN ❌ | REFUSED:stale_premise not_landed ✅ | REFUSED:stale_premise not_landed ✅ |
| `duplicate_work` | APPLIED 2 impl ❌ | REFUSED:claimed_by_A 1 impl ✅ | REFUSED:claimed_by_A 1 impl ✅ |
| `benign_reformat` | APPLIED landed_ok ✅ | REFUSED:stale_premise not_landed ⚠️ | COMMITTED landed_ok ✅ |
| `crash_before_commit` | RETRIED landed_ok ❌ | COMMITTED_ON_QUERY landed_ok ✅ | COMMITTED_ON_QUERY landed_ok ✅ |
| `duplicate_submit` | APPLIED landed_ok ❌ | DUPLICATE_IGNORED landed_ok ✅ | DUPLICATE_IGNORED landed_ok ✅ |
| `lease_revoked` | APPLIED landed_ok ❌ | REFUSED:lease not_landed ✅ | REFUSED:lease not_landed ✅ |
| `semantic_only` | APPLIED landed_BROKEN ❌ | REFUSED:stale_premise not_landed ✅ | COMMITTED landed_BROKEN ❌ |

## Faults

- `rename_break` — spec §6.6-1: A renames the function B calls; different files; git clean; build breaks
- `duplicate_work` — spec §6.6-2: A and B both implement format_currency (MAST top failure mode, 17%)
- `benign_reformat` — spec §6.6-3: A edits the file B read in a way B does not depend on
- `crash_before_commit` — process dies after B's change is applied, before COMMITTED is journaled
- `duplicate_submit` — B's identical proposal arrives twice
- `lease_revoked` — B's authority is revoked after it decided, before its change lands
- `semantic_only` — coverage boundary: A keeps name+arity of B's callee but inverts its meaning

## Reading it

- **naive** lands the broken rename (green build, runtime failure), duplicates on crash
  and on double delivery, and lands under a dead lease. This is every parallel-agent
  tool today: git checks text, CI checks the branch alone, nobody checks premises.
- **duplicate_work** is MAST's single most common multi-agent failure mode (step
  repetition, 17.14%). The claims registry catches it with zero model calls: B is told
  A holds `format_currency` before B writes a second one.
- **gate/file** (premise = hash of every file the agent read) never lands anything
  broken, but it also refuses `benign_reformat`, where A edited `auth.py` in a way B
  does not depend on. That is lost availability: safe, but it says no too often. The
  spec's point exactly: the read set is not "files opened", it's symbols referenced.
- **gate/symbol** (premise = symbols the agent called, with arity) lands the benign
  edit, refuses the rename, handles crash/dup/lease, and **lands `semantic_only`**:
  A kept the name and arity of `validate_session` and inverted its meaning. No
  mechanically extractable premise sees that. That row is the boundary of what a
  premise check can guarantee. Catching it needs intent, which is a model-quality
  question, not a protocol one, and the brief says to keep those separate.

The two gate columns are the precision/availability trade-off, measured.
