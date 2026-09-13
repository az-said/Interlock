"""
Run every experiment, print the tables, and write results/ (json + markdown).
This file's output is the deliverable. Everything else exists to produce it.
"""
import json, os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refund_agent, coding_agents

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(os.path.dirname(HERE), "results")
os.makedirs(OUT, exist_ok=True)

def mark(cell, key):
    if cell.get("caveat"): return "⚠️"
    return "✅" if cell.get(key) else "❌"

def table(rows, systems, cols):
    head = "| fault | " + " | ".join(f"{s}" for s in systems) + " |"
    sep  = "|---|" + "---|" * len(systems)
    lines = [head, sep]
    for fault, cells in rows.items():
        parts = []
        for s in systems:
            c = cells[s]
            parts.append(" ".join(str(c[k]) if k != "invariant_held" else mark(c, k) for k in cols))
        lines.append(f"| `{fault}` | " + " | ".join(parts) + " |")
    return "\n".join(lines)

stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ---- experiment 1 ----------------------------------------------------------
r1 = refund_agent.results()
sys1 = [n for _, _, n in refund_agent.SYSTEMS]
md1 = f"""# Results: refund agent

Generated {stamp} by `experiments/run_all.py`. Cells: `outcome · refunds · invariant`. ✅ held · ❌ violated · ⚠️ held, but availability lost.

Customer paid $100. Case #4471 approves one $20 partial refund. Invariant: exactly $20
refunded (or $0 if the lease was revoked or the order became ineligible first).

{table(r1, sys1, ["outcome", "refunded", "invariant_held"])}

## Faults

""" + "\n".join(f"- `{k}` — {v}" for k, v in refund_agent.FAULTS.items()) + """

## Reading it

- **naive** double-refunds on crash and duplicate delivery, refunds $50 when the re-run
  model says $30, and refunds under a revoked lease and an ineligible order. This is an
  agent framework with no gate.
- **idempotency@tier1** is the conventional durable operation: a stable key at a Stripe-
  like service, no agent runtime. It handles crash, duplicates, and the $30 re-decision
  (the service rejects a reused key with different params). It does **not** handle a
  revoked lease or a changed order, because the service can't see the agent's authority
  or premises. That gap is exactly what the runtime adds.
- **gate@tier1** (API dedupes on the effect id): every fault handled, including crash,
  by a safe retry. Exactly-once effect.
- **gate@tier2** (API has a lookup): every fault handled; the crash is resolved by
  asking the API what it has, then committing without re-sending.
- **gate@tier3** (API has neither): both crash cases end `AMBIGUOUS`. The gate refuses
  to retry, so there is no duplicate, but it cannot confirm the refund happened. Note
  `crash_before_send`: the refund never happened, and tier 3 still blocks it, because
  from the client the two crashes are indistinguishable. A refund that never happened
  may stay blocked. That is the stated cost.
  **That row is an impossibility, not a bug.** From the client side, "sent and ack
  lost" is indistinguishable from "never arrived". No protocol closes it without
  the target's cooperation. What the gate can still promise at tier 3 is at-most-once
  plus a surfaced ambiguity for a human or a later reconciliation job.
"""
json.dump(r1, open(f"{OUT}/refund_agent.json", "w"), indent=2)
open(f"{OUT}/refund_agent.md", "w").write(md1)

# ---- experiment 2 ----------------------------------------------------------
r2 = coding_agents.results()
sys2 = [n for _, _, n in coding_agents.SYSTEMS]
md2 = f"""# Results: parallel coding agents

Generated {stamp} by `experiments/run_all.py`. Cells: `outcome · result · invariant`. ✅ held · ❌ violated · ⚠️ held, but availability lost.

Invariant: nothing lands that fails at runtime; nothing lands twice; nothing lands
under a revoked lease. `result` executes the code B added, it does not just import it.

{table(r2, sys2, ["outcome", "result", "invariant_held"])}

## Faults

""" + "\n".join(f"- `{k}` — {v}" for k, v in coding_agents.FAULTS.items()) + """

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
"""
json.dump(r2, open(f"{OUT}/coding_agents.json", "w"), indent=2)
open(f"{OUT}/coding_agents.md", "w").write(md2)

print(md1); print(); print(md2)
