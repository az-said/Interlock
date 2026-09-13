# Interlock

> *"The system must distinguish what an agent proposed, what was authorized, what was executed, and what was durably recorded."*
> — the Cloud AI track brief, one sentence in, describing a thing that does not exist yet.

A customer paid $100. A support case approves one $20 partial refund. An AI agent issues it. The service commits the refund; the process dies before the response comes back. On restart, nothing in the system can answer three questions: **did the refund happen? may I retry? was I still allowed to do it?**

Today's answer is a human with two logs and a spreadsheet. Or, worse, the workflow re-runs, the model says "$30" this time, and the customer gets $50. Interlock is a commit gate that answers all three questions mechanically, refuses the $30, and is honest about the one case where nobody can know.

```
python3 demo.py naive     # today: the refund lands twice
python3 demo.py 2         # Interlock: lands once, receipt says so
python3 demo.py 3         # Interlock against an API that can't help: refuses to guess
```

## What it is

Five rules, one append-only log, about 400 lines of Python with no dependencies.

1. **Write the decision to disk before acting.** Every effect gets a `DISPATCHED` entry, fsync'd, before the call goes out. After any crash, "things I started and never confirmed" is a query, not a guess.
2. **The effect's identity is fixed when the request is approved, never by the model.** One approved request → one effect id → at most one committed effect. A model that re-decides "$30" on retry produces the *same* id with a *different* payload, and the gate rejects it. This is why *preserving decision history* and *preventing duplicate effects* are one mechanism, not two.
3. **Actions carry their premises.** Whatever the agent read or assumed when it decided (order is eligible, this function takes one arg) is captured with the proposal and re-checked against the world at commit. If a premise went stale, the effect doesn't land. Optimistic concurrency control, Kung & Robinson 1981, pointed at agents.
4. **Authority is a lease, checked at dispatch.** Not at planning time. Permissions move while agents run.
5. **Recovery never guesses.** It acts by what the target can do: retry if the target dedupes, look up if it can be queried, and otherwise say `AMBIGUOUS` out loud. Before it sends anything a second time, it re-checks the lease and the premises, because the outage is exactly when the world moves.

```
agent decides ──▶ PROPOSED ──▶ AUTHORIZED ──▶ DISPATCHED ──▶ effect ──▶ COMMITTED
                     │             │              (on disk first)
                     │             └── lease dead ─────────────────────▶ REFUSED
                     └── premise changed ──────────────────────────────▶ REFUSED
                                                  crash in the gap ────▶ recovered / AMBIGUOUS
```

The output of every effect is a **receipt**: the four facts and a final state. `executed` is what the target confirmed, not what was attempted, so after a crash nobody can resolve it reads `unknown`.

```
    proposed    True
    authorized  True
    executed    True
    recorded    True
    final       COMMITTED
```

That is the object the brief asked for. An auditor reads receipts instead of reconciling logs.

## What nobody else combines

Pieces of this exist separately, in durable-execution engines and in papers published this summer. Interlock joins three steps into one system:

1. **Write down why.** Before acting, the premises are saved with the decision: order 881 is eligible, $100 paid, nothing refunded yet. ATR (Huawei, Sept 2026) records premises too, and explicitly leaves crashes out.
2. **Look again after a crash.** Recovery does not resume blindly. It re-reads the journal and re-checks the premises and the lease against the world. If support refunded the order by hand while the agent was down, "nothing refunded yet" is now false, and the retry is refused. Temporal, Restate, DBOS and LangGraph replay the old decision.
3. **Confirm the outcome the way this target allows.** Retry where the service dedupes, and only inside its dedup window. Look it up where it can be queried. Say `AMBIGUOUS` where neither is possible. Cordon (Tsinghua, EuroSys 27) parks unclear effects for a human; nobody states the guarantee per target.

The last three rows of the refund table below are steps 2 and 3, measured.

## See it work

```
$ python3 demo.py 2

  system: INTERLOCK, payments API at tier 2
  agent decides: refund order #881 for $80

  ── refund executes, then the process dies before the ack ──
  💥 crash

  ── process restarts ──
  journal says DISPATCHED with no COMMITTED → recovery: COMMITTED_ON_QUERY

  refunds on order #881: 1

  journal:
    PROPOSED    8351811bed3d
    AUTHORIZED  8351811bed3d
    DISPATCHED  8351811bed3d
    COMMITTED   8351811bed3d  recovery-query
```

Same crash, same agent, against an API that offers neither dedup nor lookup:

```
$ python3 demo.py 3
  ...
  journal says DISPATCHED with no COMMITTED → recovery: AMBIGUOUS
  refunds on order #881: 1
    final       AMBIGUOUS
```

It refused to retry, so there is no duplicate. It also refused to claim success, because it can't know. That is the whole design philosophy in one row: **never guess, and say exactly what you can't establish.**

### Watch the journal replay

Open `viewer/index.html`. It replays the gate's real journal for every fault as an animated trace: the proposal and its premises, the lease check, the intent written to disk, the crash, what changed during the outage, and how recovery resolved it, with the receipt filling in as it plays. Switch tiers to see the same fault against an API that dedupes, one that can be looked up, and one that can do neither. No server, no build. After changing the gate, regenerate the data with `python3 viewer/build.py`.

## Results

Two experiments, same gate, same journal, different worlds. Every cell is produced by `python3 experiments/run_all.py`; the tables below are copied from `results/`.

### 1. The refund agent (the brief's own example)

$100 paid, one $20 partial refund approved. Invariant: exactly $20 refunded, or $0 if the lease was revoked or the order became ineligible first. Three baselines: today's naive re-run, the conventional "just use idempotency keys" operation, and durable execution the way Temporal, DBOS and Restate recommend (recorded step results replay, a crashed step re-runs with a stable key, Stripe-grade target).

| fault | naive (today) | idempotency key only | durable execution (Temporal-style) | gate @ tier 1 | gate @ tier 2 | gate @ tier 3 |
|---|---|---|---|---|---|---|
| crash before send | $20 ✅ | $20 ✅ | $20 ✅ | $20 ✅ | $20 ✅ | **$0, `AMBIGUOUS`** ⚠️ |
| crash before ack | **$40** ❌ | $20 ✅ | $20 ✅ | $20 ✅ | $20 ✅ | $20, `AMBIGUOUS` ⚠️ |
| duplicate submit | **$40** ❌ | $20 ✅ | $20 ✅ | $20 ✅ | $20 ✅ | $20 ✅ |
| model re-decides $30 on retry | **$50** ❌ | $20 ✅ | $20, replayed ✅ | $20, refused ✅ | $20, refused ✅ | $20, refused ✅ |
| same request, different amount | **$50** ❌ | $20 ✅ | $20, replayed ✅ | refused ✅ | refused ✅ | refused ✅ |
| lease revoked mid-flight | refunded ❌ | **refunded** ❌ | **refunded** ❌ | refused ✅ | refused ✅ | refused ✅ |
| order became ineligible | refunded ❌ | **refunded** ❌ | **refunded** ❌ | refused ✅ | refused ✅ | refused ✅ |
| support refunds by hand during the outage | **$40** ❌ | **$40** ❌ | **$40** ❌ | $20, refused at recovery ✅ | $20, refused at recovery ✅ | $20, `AMBIGUOUS` ⚠️ |
| lease revoked during the outage | refunded ❌ | **refunded** ❌ | **refunded** ❌ | refused at recovery ✅ | refused at recovery ✅ | $0, `AMBIGUOUS` ⚠️ |
| recovery after the 24h idempotency window | **$40** ❌ | **$40** ❌ | **$40** ❌ | $20, found by lookup ✅ | $20, found by lookup ✅ | $20, `AMBIGUOUS` ⚠️ |

**Finding 1. Exactly-once is a property of the target, not the client.** Achievable when the API dedupes (tier 1) or can be queried (tier 2). When it does neither, the crash cases are undecidable from the client: "sent, ack lost" and "never sent" produce identical observations. The strongest honest guarantee at tier 3 is *at-most-once plus a surfaced ambiguity*, and the cost is on the table: a refund that **never happened** stays blocked after a crash-before-send. This is the Two Generals result (1975) written as a per-service contract with a measured price.

**Finding 2. Idempotency keys are necessary and not sufficient.** The idempotency-only column handles crashes, duplicates, and the $30 re-decision, all at the service. It still refunds under a revoked lease and refunds an ineligible order, because the service can't see the agent's authority or premises. The difference between that column and the gate columns is what the runtime adds, measured rather than claimed.

**Finding 4 (added after checkpoint 2). Recovery is when the world moves.** The last three rows found a bug in our own gate. Until this change, `recover()` re-sent at tiers 1 and 2 without re-checking premises or lease, so the gate refunded $40 when support refunded the order by hand during the outage, and refunded under a lease revoked during the outage. Tier 1 also trusted the provider's dedup forever, but Stripe prunes idempotency keys after 24 hours, and a retry after that is a new refund. The fix: a resend is a new dispatch, so I3 and I4 run again first, and after the dedup window tier 1 is treated as a lookup. The idempotency-only column still fails all three, because a key only matches the same request.

### 2. Parallel coding agents (the same root, wearing a different hat)

Two agents on one repo. Agent B decides first, agent A lands first. That ordering is what every worktree-based product ships. Invariant: nothing lands that fails at runtime; nothing lands twice; one implementation per symbol.

| fault | naive (today) | gate, file-hash premises | gate, symbol premises |
|---|---|---|---|
| A renames the function B calls | lands, **breaks at runtime** ❌ | refused ✅ | refused ✅ |
| A and B both implement `format_currency` | **2 implementations** ❌ | 1, B told A holds it ✅ | 1 ✅ |
| A edits the file in a way B doesn't depend on | lands ✅ | **refused** ⚠️ | lands ✅ |
| crash after apply, before commit | **duplicated** ❌ | recovered ✅ | recovered ✅ |
| duplicate submit | **duplicated** ❌ | ignored ✅ | ignored ✅ |
| lease revoked | lands ❌ | refused ✅ | refused ✅ |
| A keeps name+arity, inverts meaning | lands, **breaks** ❌ | refused ✅ | lands, **breaks** ❌ |

**Finding 3. Premise granularity is a dial with a floor.** File-hash premises never land a broken change but refuse benign concurrent edits: that's the naive "did the file change" check every worktree tool could add, and it over-fires. Symbol premises (what the agent actually *referenced*, not what it *opened*) land benign edits, catch the rename, and catch duplicated work with zero model calls. Duplicated work is the single most common multi-agent failure mode in the Berkeley MAST study (17% of 1,600 traces). But symbol premises cannot see a change that keeps the signature and inverts the meaning. No mechanically extractable premise catches that row. Catching it requires understanding intent, which is a model-quality question, and the brief is explicit that protocol guarantees and model quality stay separate. That row is the measured boundary.

The thesis behind this half, from the team's concurrency-control spec: **agent transactions need concurrency control, but not the classical kind.** Abort-and-retry assumes a cheap, deterministic redo. LLM agents cost 4–15× tokens per attempt and don't reproduce their plan on re-run. So the gate's response to a conflict is graded by what it can say mechanically, not "abort everything."

### 3. The same faults against real Stripe

Not a simulation: `experiments/stripe_live.py` makes a $100 test-mode card payment per run, approves one $20 partial refund, and injects the fault against Stripe's API. Every payment id is listed in [results/stripe_live.md](results/stripe_live.md) so the refunds can be checked in the Stripe test dashboard.

| fault | naive (today) | idempotency key only | gate (Stripe key + lookup) |
|---|---|---|---|
| crash before ack | **$40** ❌ | $20 ✅ | $20 ✅ |
| duplicate submit | **$40** ❌ | $20 ✅ | $20 ✅ |
| support refunds by hand during the outage | **$40** ❌ | **$40** ❌ | $20, refused at recovery ✅ |

Same result as the simulation, on the real service: the idempotency key handles the crash and the duplicate, and pays twice when a person refunds during the outage.

### 4. Durable execution on a real Temporal server

Not modeled: `experiments/temporal_live.py` runs the refund step as a Temporal activity on Temporal's local dev server, with Temporal's own retry policy doing every retry. A worker crash is a failed first attempt. Full output in [results/temporal_live.md](results/temporal_live.md).

| fault | Temporal, recommended idempotency key | Temporal with Interlock as the activity body |
|---|---|---|
| crash before ack | $20 ✅ | $20 ✅ |
| support refunds by hand during the outage | **$40** ❌ | $20, refused at recovery ✅ |
| permission revoked during the outage | **refunded** ❌ | refused at recovery ✅ |
| order became ineligible before the step ran | **refunded** ❌ | refused ✅ |

Temporal does exactly what it promises: the crashed step is retried and, with a stable key, lands once. When the facts behind the decision changed before the retry, it runs the same step again. Put the gate inside the activity and the same retry is refused. Interlock is not a Temporal replacement; it is the activity body.

## Why this and not the obvious things

**"Just use idempotency keys."** That's the second column in table 1, and it's the right answer whenever the target supports it. It refunds the ineligible order anyway. Keys live at the service; authority and premises live at the agent. Both are needed.

**"Just log more."** A log records what the logger saw. The thing you need to know happened on a machine you don't control, and it can only tell you by sending a message, which is subject to the same loss. Perfect client-side logging of the crash above reads `request bytes written` and then nothing. Logging is observation. What's missing is *attribution*: which decision, under whose authority, produced which effect, once. Enterprises report having the first without the second.

**"Temporal / Pydantic AI already does this."** Durable execution wraps every model and tool call as a checkpointed step and resumes from the last completed one. That solves resume and freezes model outputs. It checkpoints the step's *result*, which means a tool step that dies after the effect and before the result is saved re-runs the tool. Whether that duplicates the effect is the tool's problem. Their docs say as much: if the process crashes mid-request, the agent has no idea what already happened. Interlock is the body of that step. It journals intent *before* the call, checks premises and lease at dispatch, and recovers by the tool's tier. Complementary, and the cleanest place to ship it. Table 1's third column measures the difference instead of arguing it: durable execution used the way Temporal recommends, against a Stripe-grade target, ties the gate on every crash, duplicate, and re-decision row, and fails all five rows where the world changed after the decision. Experiment 4 repeats the key rows on a real Temporal server, with the same result.

**"Keep writes single-threaded" (Cognition).** Sufficient for coherence, not necessary. It's the rule a database would impose with no concurrency control, and databases abandoned it for throughput. The benign-edit row is a concurrent write landing safely.

**"CaMeL solves prompt injection with capabilities."** Yes, and it was the closest prior work until this summer. CaMeL controls whether untrusted data can influence control flow. It has no model of crashes, retries, duplicate delivery, or revocation. It answers "was this action allowed?" Interlock answers "did this allowed action happen, once, under authority that was live when it fired?"

**"Didn't a paper just do this?"** Three did, in pieces, between June and September 2026. ATR (Huawei) re-checks typed premises but excludes crashes and non-idempotent APIs. Cordon (Tsinghua, EuroSys 27) stages effects and parks an unproven dispatch in an audit state, which is our tier 3 from the security side. "Engineering Reliable Commit Gates for Agentic AI" (WashU) benchmarks verifiers and shows after-check races need atomic guards. None re-checks premises on the recovery path or states a guarantee per target, and none ships adapters for real services. Three groups converging on this layer in three months is the best evidence the layer is real. Details in [docs/03-landscape.md](docs/03-landscape.md#research-published-this-summer).

Full landscape, with the tools attacking parallel-agent conflicts today, in [docs/03-landscape.md](docs/03-landscape.md).

## Add it in three lines

For your own functions, skip the adapter. Three statements: create the gate, decorate the function that has the side effect, recover on startup.

```python
from interlock import Interlock
gate = Interlock(".interlock")

@gate.effect(key=lambda order, amount: f"refund:{order}",
             premises=lambda order, amount, idempotency_key: {
                 "eligible": is_eligible(order),
                 "refunded_by_others": refunded_total(order, excluding=idempotency_key)},
             dedupes=True)
def refund(order, amount, idempotency_key):
    return stripe.Refund.create(charge=charge_for(order), amount=amount, idempotency_key=idempotency_key)

gate.recover()   # once, on startup
```

`refund("881", 20)` now journals the decision, re-reads the premises right before the call and again after any crash, passes a stable idempotency key, and returns `("COMMITTED", result)`, `("REFUSED:stale_premise", None)`, `("DUPLICATE_IGNORED", ...)`, and so on.

The one thing you still have to say is the thing no library can guess: which facts the decision depends on. Then say how the service cooperates: `dedupes=True` if it takes the key, `lookup=` a function that answers "did this already happen?", or neither. `allowed=` adds a permission check at dispatch and at recovery. A premise that would count the effect's own result takes `idempotency_key` and leaves it out, as above. The adapter is `interlock/easy.py`; `tests/test_interlock.py` runs it through a crash and a process restart.

## Where it plugs in

Interlock is a wrapper around the point where an agent calls a tool. It does not touch the model, the prompt, or the agent framework's planning loop.

```python
gate = Gate(target=StripeTarget(client), journal_path="~/.interlock/journal.jsonl", leases=leases)
result = gate.submit({"agent": "refund-bot", "lease": lease_id,
                      "premises": target.capture(order_id),
                      "effect": {"order": order_id, "amount": amount}})
```

An `EffectTarget` is an adapter with four methods: `capture` premises, `validate_premises`, `apply`, and optionally `query`. It declares its tier. Writing one for a real service is an afternoon:

| target | tier | how |
|---|---|---|
| Stripe | 1 | `Idempotency-Key: <effect_id>` header; Stripe dedupes for 24h |
| GitHub merge | 2 | look up the merge commit by branch SHA on recovery |
| Postgres write | 2 | `INSERT ... ON CONFLICT` keyed on effect id, or a lookup |
| SendGrid / most email | 3 | no dedup, no lookup: `AMBIGUOUS` on crash, surfaced for reconciliation |
| Natural, agent-native rails | 1 | receipt-bearing ledger; the cooperating side, being built now |

Integration sketch for LangGraph, MCP, and the OpenAI Agents SDK in [docs/04-integration.md](docs/04-integration.md).

## Who this is for

The platform engineer who gets paged when an agent double-fires. The team running Claude Code or Codex in parallel and finding green builds that don't run. The finance team about to let an agent touch refunds and being told by compliance that "we have logs" is not an answer to "who authorized this."

Reconciliation is already the most expensive manual process in corporate finance. Agent-originated actions are about to multiply the volume that needs reconciling. A receipt per effect is cheaper than a human per incident.

## What's real, what's not

**Real.** The journal, the gate, both targets, both experiments, every number above. `python3 experiments/run_all.py` regenerates `results/` from scratch in under a second.

**Tested.** `python3 -m unittest discover -s tests` asserts every row above, where each baseline fails as well as where the gate holds, then runs 2,000 randomized interleavings of tier, crash point, events before the decision and during the outage, late recovery, and duplicate delivery, and finally the three-line integration through a simulated restart. CI runs it on every push and fails if `results/` drifts from the code.

**Simulated.** The payments API and the repo are local. Faults are injected, not observed. This is by design: the brief asks for targeted failures at meaningful boundaries, not random process kills.

**Real, against a live service.** `interlock/targets/stripe_api.py` is a Stripe refunds target (test-mode keys only, standard library only), and experiment 3 runs the refund faults against it.

**Not built yet.** A real GitHub target. A journal that isn't a local file. Premise extraction beyond file hashes and function arity. A notary that both sides write to, so tier 3 services can be lifted to tier 2 without changing their API.

**Out of scope, on purpose.** Whether the agent's decision was *right*. A faithfully executed bad refund is still a bad refund. Interlock controls effects, not judgment.

## Next test

Swap `LocalRepo` for a real `gh pr merge` target and measure how often the gate must return `AMBIGUOUS` when the merge API response is dropped, versus when GitHub's merge-commit lookup is used as the tier-2 query. The ratio is the availability cost of running without a cooperating target.

## Repo map

```
interlock/           the runtime
  journal.py         append-only, fsync'd; effect_id_for() binds identity to the approved request
  leases.py          authority that expires and is checked at dispatch
  gate.py            six invariants, recovery by tier, claims registry, three baselines
  easy.py            the three-line decorator: Interlock(dir), @gate.effect(...), gate.recover()
  targets/
    payments.py      simulated refund API at tiers 1 / 2 / 3, Stripe-style key semantics
    repo.py          local code repo with file-hash and symbol premises
experiments/         the fault-injection harnesses; run_all.py writes results/
results/             the tables above, as markdown and json
viewer/              index.html replays real journals as an animated trace; build.py writes traces.js
tests/               every README claim as an assertion, a 2,000-case fault sweep, the decorator through a restart
docs/
  01-problem.md      the root, from three lines of code to the four facts
  02-contract.md     invariants, failure model, cooperation ladder, baselines
  03-landscape.md    who owns which layer; the positions we disagree with
  04-integration.md  the EffectTarget adapter; LangGraph / MCP / Temporal; the notary
  05-reading.md      what we read and what each paper hands you
  checkpoints/       what was submitted, what was scored, what changed
  team-notes/        the raw planning doc, one file per tab, plus whiteboards
demo.py              one refund, one crash, one receipt
```

## How this came together

Saturday we wrote two specs that looked like different projects: one refund, at most once (`docs/team-notes/02`), and concurrency control for parallel coding agents (`docs/team-notes/05`). Sunday morning we noticed they were the same mechanism pointed at two targets, built the core once, and ran both. The whiteboards are in `docs/team-notes/whiteboards/`.

## References

The ones the results lean on. The full list with notes is in `docs/05-reading.md`; the concurrency spec's 18 references are in `docs/team-notes/05`.

- Akkoyunlu, Ekanadham & Huber (1975). Two Generals. Why tier 3 is undecidable.
- Kung & Robinson (1981). Optimistic concurrency control. The premise check.
- Garcia-Molina & Salem (1987). Sagas. The next step after this repo.
- Leach, Stripe (2017). Idempotency keys. The second baseline.
- Cemri et al. (2025). Why Do Multi-Agent LLM Systems Fail? arXiv 2503.13657. Step repetition at 17.14%.
- Debenedetti et al. (2025). CaMeL. arXiv 2503.18813. Closest prior work before this summer; no failure model.
- Lyu et al. (2026). ATR: selective revalidation for long-running AI agents. arXiv 2609.08015. Premises, without crashes.
- Chen et al. (2026). Cordon: semantic transactions for tool-using LLM agents. arXiv 2606.17573. Staged effects; tier 3 from the security side.
- Zheng et al. (2026). Engineering Reliable Commit Gates for Agentic AI. arXiv 2609.10969. Why the premise check sits immediately before dispatch.
- Cognition. Don't Build Multi-Agents. The position the benign-edit row answers.
- Mosaic (2026). The Coordination Problem. The "retry is free" assumption the coding half disputes.
- Anthropic (2025). How we built our multi-agent research system. The 4×/15× token figures.

Interlock — Battle of the Coasts 2026, Cloud AI track, Boston. MIT licensed. Fork it, break it, tell us which row is wrong.
