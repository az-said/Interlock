# Interlock: the whole story, from the root

*Written Sunday afternoon, Sept 13, for the team. This is the document to read before recording the video, before talking to a judge, and before pitching an investor. It explains what we did, why, what's under the surface, what we ruled out, and what's next.*

---

## 0. Where we are right now

The repo at `github.com/az-said/Interlock` is much bigger than what existed at noon. The core was about 400 lines: journal, leases, gate, two targets, two experiments, docs. Since then the team extended it: a durable-execution baseline column, three new faults (support refunds by hand during the outage, permission revoked during the outage, retry after Stripe's 24-hour key window), a live Stripe test-mode experiment with real PaymentIntent ids, a live Temporal experiment, an approval-inbox simulation, a three-line decorator API, an MCP proxy, hash-chained and HMAC-signed receipts, a SQLite journal for multiple workers, a journal viewer, 53 tests including a 2,000-case randomized sweep, and CI. The README also reports a fourth finding: the tests found a real bug in the gate's recovery path, and the fix is documented.

That last part matters more than any feature. The brief says: *"A result that fails under a difficult case is useful if you diagnose the failure and revise the claim."* Finding 4 is exactly that, in our own repo, about our own code.

**Before anyone shows this to a judge, five things must be verified by a human, not assumed:**

1. `python3 -m unittest discover -s tests` passes on a clean clone, and the count matches the README. *(Status: CI is green on Python 3.9, 3.12 and 3.13, and fails if `results/` drifts from the code. Still worth one clean-clone run.)*
2. `experiments/stripe_live.py` was actually run against Stripe test mode. The PaymentIntent ids in `results/stripe_live.md` (`pi_3UFG…`) look real. Open one in the Stripe test dashboard and confirm the refunds are there.
3. `experiments/temporal_live.py` was actually run against a local Temporal dev server. Check `results/temporal_live.md` has real output. *(It does: temporalio 1.32.0, full per-fault attempts.)*
4. The three 2026 papers cited (ATR arXiv 2609.08015, Cordon arXiv 2606.17573, WashU commit gates arXiv 2609.10969) exist and say what we say they say. *(Checked: all three exist, and the titles and claims match. A fabricated citation is the single fastest way to lose a research track; this one is clean.)*
5. The "See it work" block in the README shows what `demo.py` actually prints. *(Fixed: the README now carries the real output — `$100 paid, $20 approved`, `refunded on order #881: $20 (1 refund record(s))`.)*

Also: checkpoint 1 was submitted with `github.com/shawnzhu02/Interlock`. The repo was transferred, so that URL now redirects here automatically; the old link keeps working.

---

## 1. Day 0: what the challenge actually asked

The brief's title is "Verifiable execution for distributed AI systems." Every team read that and heard "multi-agent." We did too. Here is what it actually says, sentence by sentence, and what each sentence turned into.

| The brief says | What it means | What it became |
|---|---|---|
| "If a tool performs an action but its acknowledgment is lost, the runtime may not know whether retrying will duplicate the effect." | The ambiguous window. Sent, ack lost, indistinguishable from never sent. | The crash-before-ack row, and the whole tier model. |
| "Repeating a model call can produce a different decision." | The classic fix for a crash, re-run from the start, breaks at the one step that decides. | Effect id bound to the approved request, not the model output. The "$30 on retry" row. |
| "Permissions may change during execution." | Authority checked at planning time is stale by execution time. | Leases, checked at dispatch and again at recovery. The two revocation rows. |
| "The system must distinguish what an agent proposed, what was authorized, what was executed, and what was durably recorded." | Four separate facts that every framework collapses into one log line. | The receipt. Four booleans and a final state. |
| "A runtime cannot promise universal exactly-once behavior merely by retrying." | Two Generals, 1975. | Tier 3 is `AMBIGUOUS`, not a retry. |
| "Its guarantees depend on what the external systems support." | The answer is a function of the target, not the client. | The cooperation ladder: dedupes / queryable / neither. |
| "Include what the system is allowed to delay or refuse when it cannot establish the condition." | Refusing is a valid answer if you say when. | `REFUSED:*` and `AMBIGUOUS` as first-class states. |
| "A small workflow is sufficient if the failure case is difficult and the evidence is convincing." | Don't build a platform. | One $20 refund. Three lines of agent code. |
| "A polished interface alone does not establish the underlying claim." | Don't build a landing page. | We built one anyway. It's fine, but it earns no points. |
| "You may submit… an impossibility result paired with a useful weaker guarantee." | A negative result is a winning format. | Finding 1. |
| "Do we need multiple agents? No." | Agent count is not depth. | One agent, one service, the whole problem. |

On the word "model": the brief lists "a model, simulation, mathematical result, experiment, design, notebook, prototype" as valid formats. *Model* there means a formal or executable model of the system, a state machine with invariants. That is `gate.py`. Not a machine-learning model. We never touch the model.

---

## 2. The consequences we could have chased

Saturday's first whiteboard listed: security → sandboxed environments; prompt injection; data poisoning affecting downstream; duplicate tasks; and beneath them, "execution correctness, authorization, decision history, interruptions." Then an arrow to "security vs efficiency."

Each of those was a fork. Here's why we didn't take most of them.

**Sandboxed environments for agents.** Real, funded, and already built by people we know (Inner, YC S26, our own MEET alumni). Admission control on artifacts: is this package safe to install. Different layer from ours. Building a worse version of a friend's funded startup in 50 hours is not a plan.

**Prompt injection detection.** A model-quality claim. Needs a benchmark we didn't have time to build, and the brief explicitly says keep model quality separate from protocol guarantees. Twenty teams would build detectors. We kept injection only as *containment*: untrusted data cannot mint authority, because authority comes from leases the principal issues.

**Data poisoning, specification gaming.** Out of scope by the brief's own sentence: "Execution correctness does not establish the truth of the decision being executed." A faithfully executed bad refund is still a bad refund. We say that in the README.

**Security vs efficiency.** A product-positioning axis, not a research axis. The research axis is "which guarantee, under which failure model, with what evidence." We dropped the fork.

**Multi-agent communication.** The team's original instinct: agents in parallel break code because they can't talk. This was the most important fork, and it took a day to resolve. The resolution: no message between two agents prevents the failure, because every message either arrives too late or becomes a check at the commit point. So build the check at the commit point. "Multiplayer AI doesn't fail because agents can't talk. It fails because nothing validates what they assumed at the moment their work lands." That sentence turned a communication problem into a commit problem, and the coding-agent half of the repo exists to prove it.

---

## 3. How we narrowed: four decisions

**Decision 1: research, not product.** The rubric is 30% innovation, 25% technical, 25% business, 20% presentation. The track brief interprets "technical depth" as resolving a difficult uncertainty with evidence. That's a research artifact: a claim, a contract, a fault matrix. The product framing comes after, in the business quarter.

**Decision 2: effects, not the model.** Everything we care about happens after a proposal exists and before the world changes. That's a runtime layer. It doesn't need weights, prompts, or interpretability. That's what makes it tractable in a weekend.

**Decision 3: duplicate effects as the headline; everything else as supporting invariants.** Four properties were on the board. We picked the one that is provable and that the brief uses as its own example. Decision history is the *mechanism* (the journal), not a separate goal. Authority at dispatch is one `if`. Recovery is what `recover()` does. One sharp claim with a boundary beats four soft ones.

**Decision 4: refund as the instrument, coding agents as the generalization.** One narrow refund spec (one refund, at most once). One broad concurrency-control spec for parallel coding agents. They looked like two projects. Sunday morning we saw they were one mechanism aimed at two targets, built the core once, and ran both. The refund is what a judge understands in ten seconds. The coding experiment is what shows the root is general.

---

## 4. The root

Micro level, at the wire. Your process opens a connection to the payment service, sends a request, waits. The service commits the refund and sends back `200 OK`. That response is a packet. Packets drop. Or your process was killed while it was in flight. Either way, you experience a timeout.

| What actually happened | What you observe |
|---|---|
| Request never arrived | timeout |
| Service did it, response lost | timeout |
| Service still processing | timeout |
| Service crashed halfway | timeout |

Four realities, one observation. Provably impossible to close from the client side (Two Generals, 1975). You don't solve it; you design around it and say what's left.

Why more logging doesn't help: a log records what the logger saw. Perfect client-side logging of this crash reads `request bytes written` and then nothing. The fact you need lives on a machine you don't control, and it can only tell you by sending a message, which can also be lost. Logging is observation. Reconciliation is agreement between two parties, and needs both.

What AI adds, three things: re-running the program doesn't reproduce the decision; data the agent reads can change what the program does; permissions move while the agent runs.

**The root, one sentence:** an agent decides on premises that are true when it decides; its action lands later; and nothing in the system carries the premises along with the action to be re-checked when it lands.

Systems people call the shape time-of-check to time-of-use. It used to be microseconds inside one process. Now it's seconds across a model call, a network hop, and a service you don't own.

The consequence a buyer feels: because nobody can prove what an agent did, compliance mandates that a person approves every consequential action by hand. That person is the reconciliation layer.

---

## 5. What we read, and what each one gave us

| Paper / source | What it gave the project |
|---|---|
| Two Generals (Akkoyunlu et al., 1975) | Tier 3 is undecidable. `AMBIGUOUS` is a theorem, not a bug. |
| Stripe idempotency keys (Brandur Leach, 2017) | What the cooperating side looks like. Tier 1. The second baseline. And the 24-hour expiry that became a fault row. |
| Optimistic concurrency control (Kung & Robinson, 1981) | Record your read set, validate at commit. The premise check. |
| Sagas (Garcia-Molina & Salem, 1987) | Compensation when you can't roll back. The next step after this repo. |
| Temporal durable execution docs | Freeze model outputs as recorded steps. Solves resume. Stops at the tool call. Became the third baseline column and the integration story. |
| Pydantic AI durable execution docs | Confirmed the gap in the vendor's own words: a step that dies mid-call re-runs the tool. |
| Anthropic multi-agent research system (2025) | Agents are stateful, errors compound, resume from where the agent was. The easy half, solved for read-only agents. Also the 4×/15× token figures that make "retry is free" false. |
| CaMeL (Debenedetti et al., 2025) | The standard of "provable." Capabilities on values, policy at each tool call. No model of crashes or revocation. Closest prior work. |
| Greshake et al. (2023) | Indirect prompt injection. Why data can change control flow in an agent and not in a program. |
| Why Do Multi-Agent LLM Systems Fail? (Cemri et al., Berkeley 2025) | Step repetition is the top failure mode at 17.14%. All seven frameworks studied were conversational, not concurrent writers. The gap our coding experiment fills. The `duplicate_work` row. |
| Cognition, Don't Build Multi-Agents | "Keep writes single-threaded." Sufficient, not necessary. The benign-edit row answers it. |
| Mosaic, The Coordination Problem (2026) | Agents as ephemeral probes; "retry is close to free." True only until a probe touches the outside world. The thesis of the coding half disputes exactly this sentence. |
| Kore.ai Agent Productivity Index (2026) | 8 in 10 enterprises had an agent execute a consequential action and paid to correct it. Observability without attribution. |
| J.P. Morgan treasury survey; McKinsey; Levvel | 61% name reconciliation the most time-consuming manual process; 30% of finance time; 1.2% of payment volume is duplicates before agents. |
| ATR, Cordon, WashU commit gates (all 2026, cited in README) | Three groups converging on this layer in three months. All three links checked and real. |

---

## 6. The field

| Layer | Question | Who |
|---|---|---|
| Artifacts in | Is this package safe to install? | Inner |
| Policy and inventory | What may agents do? | Snyk Evo / Agent Guard |
| Orchestration | Who's assigned, what state? | Linear Agents, OpenAI Symphony |
| Durable execution | Resume after failure | Temporal, DBOS, Restate, Prefect; Pydantic AI first-party |
| Injection containment | Can data change control flow? | CaMeL |
| Dedup at the receiver | Don't do it twice | Stripe keys, Kafka EOS |
| Agent-native payment rails | Let agents hold and move money | Natural ($40M raised), Ralio, Paygentic |
| Parallel-agent workspaces | Run N agents, merge at end | Superconductor, Conductor, Superset, Augment Intent |
| Conflict heuristics | Catch semantic conflicts | moire, conflict-check, sol |
| **Effects** | **Did it happen, once, under live authority, on premises that still hold?** | **nobody** |

Crowded: injection detectors, sandboxes, observability dashboards, parallel-agent conflict heuristics. Empty: the effects row. It's empty for a structural reason: model providers sit on one side of the effect, API providers on the other, durable-execution vendors upstream. Nobody owns the seam. Seams are where Stripe, Twilio, and Plaid came from.

Natural is worth one sentence: they're building the cooperating side. In our terms, a tier-1 target with a ledger. They validate that the receiver side is being funded right now.

---

## 7. Approaches we ruled out, and why

| Approach | Why it doesn't work |
|---|---|
| Log more | Logs record what the logger saw. The fact is on the other machine. |
| A network proxy that records every request | It's a third party in the same problem. It has to terminate TLS to see inside payment traffic, which nobody allows. And a record of "response received" only helps if the client consults it on restart with a protocol for each state. The storage half is right; the protocol half is the work. |
| Idempotency keys alone | Handles crash and duplicates at the service. Cannot see the agent's authority or premises. Refunds under a revoked lease and on an ineligible order. Measured: column 2. |
| Durable execution alone | Checkpoints the step's result. A step that dies after the effect re-runs the tool. Replays the old decision instead of asking whether it still holds. Measured: column 3. |
| A detector for bad actions | Model-quality claim. Needs a benchmark. Brief says keep it separate. |
| A sandbox | Admission control on artifacts, not correctness of effects. Already built by Inner. |
| Agent-to-agent messaging | Every message arrives too late or becomes a check at commit. Non-terminating, non-durable, non-deterministic, and a model call per exchange. |
| Hash every file the agent read | Safe but refuses benign concurrent edits. Measured: the `gate/file` column. Over-fires. |

---

## 8. The approach, and what's under the surface

### The idea in five rules

1. Write the decision to disk before acting.
2. The effect's identity is fixed when the request is approved, never by the model.
3. Actions carry their premises; re-check at commit.
4. Authority is a lease, checked at dispatch.
5. Recovery never guesses: retry if the target dedupes, look up if it can be queried, otherwise say `AMBIGUOUS`.

### The state machine

```
                       ┌──────────────────────────────────────────────────────┐
                       │                       JOURNAL                        │
                       │        append-only · fsync'd · hash-chained          │
                       └──────────────────────────────────────────────────────┘
                              ▲            ▲            ▲             ▲
  agent decides ──▶ PROPOSED ──▶ AUTHORIZED ──▶ DISPATCHED ──▶ [effect] ──▶ COMMITTED
       (premises,      │              │              │ on disk BEFORE
        request id)    │              │              │ the call goes out
                       │              │              │
                       │              └─ lease dead ─┼──────────────────────▶ REFUSED:lease
                       └─ premise changed ───────────┼──────────────────────▶ REFUSED:stale_premise
                       └─ same id, different payload ┼──────────────────────▶ REFUSED:conflicting_payload
                       └─ symbol already defined/claimed ────────────────────▶ REFUSED:duplicate_symbol
                                                     │
                                          crash here ┴──▶ recover():
                                                             tier 1  retry (idempotent)   ──▶ COMMITTED
                                                             tier 2  query the target     ──▶ COMMITTED or reapply
                                                             tier 3  cannot know          ──▶ AMBIGUOUS
                                                          before any resend: re-check lease + premises
```

### One refund, traced through the code

`demo.py 2` does this:

1. `Payments(tier=2)` creates a simulated payment service with an order: $100 paid, eligible. `Leases().grant("L-refund")`.
2. The agent builds a **proposal**: `{"request_id": "case-4471", "lease": "L-refund", "premises": api.capture("881"), "effect": {"order": "881", "amount": 20}}`. `capture()` records what the agent saw: eligible=True, amount=100.
3. `gate.submit(proposal)`:
   - `effect_id_for(proposal)` hashes `request_id` → `8351811bed3d`. Not the model's output. Same case, same id, forever.
   - `journal.append("PROPOSED", ...)` writes the decision and premises to disk with `fsync`.
   - Payload binding (I5): if this id was proposed before with a different amount → `REFUSED:conflicting_payload`. This is the "$30 on retry" defense.
   - Dedup (I2): if this id is already `COMMITTED` → `DUPLICATE_IGNORED`.
   - Lease (I4): `leases.is_live("L-refund")` right now, not when the agent planned → else `REFUSED:lease`.
   - Premises (I3): `target.validate_premises(premises)` re-reads the order and compares → else `REFUSED:stale_premise`.
   - Intent (I1): `journal.append("DISPATCHED", ...)`. **Now** and only now, `target.apply(...)`.
   - The simulated crash fires after the refund is appended to the service ledger and before `COMMITTED` is written.
4. Process "restarts." `gate.recover()`:
   - `journal.in_flight()` finds the id whose last entry is `DISPATCHED`.
   - Tier 2: `target.query(eid)` asks the service "do you have a refund with this reference?" Yes → `journal.append("COMMITTED", via="recovery-query")`. Nothing re-sent.
   - (Per Finding 4, the gate re-checks lease and premises before any resend at tiers 1 and 2. That's the fix for "support refunded by hand during the outage.")
5. `gate.receipt(proposal)` reads the journal and returns the four facts: proposed, authorized, executed, recorded, all True, final `COMMITTED`.

Run `demo.py 3` and step 4 changes: tier 3 has no `query`, so recovery writes `AMBIGUOUS` and stops. One refund exists on the ledger. The receipt says `recorded: False, final: AMBIGUOUS`. That's the case that goes to a human.

### Why is the repo "that long"

The core is small. Everything else is either evidence or adapters:

| Part | Lines (approx.) | Why it exists |
|---|---|---|
| `journal.py`, `leases.py`, `gate.py` | ~250 | The protocol. The thing that's being claimed. |
| `targets/payments.py`, `targets/repo.py` | ~150 | Simulated targets with *honest* semantics per tier. The brief: "a mock that always behaves perfectly cannot substantiate recovery claims." |
| `targets/stripe_api.py` | — | A real target. The "is this just a simulation?" answer. |
| `experiments/*.py` | ~300 | The fault-injection harnesses. Each row of each table is one function here. |
| `easy.py`, `mcp_proxy.py`, `temporal.py` | — | Integration. Answers the judge's "how does this fit in other products?" |
| `receipts.py`, `approvals.py` | — | The receipt as a verifiable object, and the approval-queue model. The business half. |
| `tests/` | — | Every README claim as an assertion. Found fifteen bugs across two review passes. |
| `viewer/` | — | Replays real journals. Makes the guarantee *inspectable*, which is the brief's word. |

If you strip it to what's judged, it's the protocol (250 lines) and the two tables.

---

## 9. What the experiments showed

| # | Experiment | Setup | What it showed |
|---|---|---|---|
| 1 | Refund agent | 10 faults + control × 6 systems, simulated service at 3 tiers | Findings 1, 2, 4 |
| 2 | Parallel coding agents | 7 faults × 3 systems, local repo, 2 premise granularities | Finding 3 |
| 3 | Real Stripe | 3 faults × 3 systems, test mode, real PaymentIntents | Simulation matches the real service |
| 4 | Real Temporal | 4 faults × 2 systems, local dev server | Durable execution replays; gate inside the activity refuses |
| 5 | Approval inbox | 100 synthetic refunds × 3 policies (mix is an assumption) | Reviews 100 → 33, wrong payouts 8 → 0 |

**Finding 1.** Exactly-once is a property of the target, not the client. At tier 3 the crash cases are undecidable; the strongest honest guarantee is at-most-once with the ambiguity surfaced, and the measured cost is a refund that never happened staying blocked.

**Finding 2.** Idempotency keys are necessary and insufficient. They handle crash, duplicates, and the $30 re-decision at the service, and still refund under a revoked lease and on an ineligible order, because the service can't see the agent.

**Finding 3.** Premise granularity is a dial with a floor. File hashes never land broken code but refuse benign edits. Symbols land benign edits, catch the rename, catch duplicated work (MAST's #1 failure mode) with zero model calls, and cannot see a same-signature meaning change. That row is the boundary.

**Finding 4.** Recovery is when the world moves. Our own tests found that `recover()` re-sent at tiers 1 and 2 without re-checking premises or lease, so the gate itself refunded $40 when support refunded by hand during the outage. Fixed: a resend is a new dispatch. This is the brief's "diagnose the failure and revise the claim," done to ourselves.

---

## 10. The numbers

- 61% of corporate treasury executives name payment reconciliation their most time-consuming manual process, up from 44% in 2022 (J.P. Morgan).
- High-volume finance teams spend up to 30% of their time on manual reconciliation (McKinsey).
- AI payment matching catches about 1.2% of payment volume as duplicates that manual review missed. Before agents. (Levvel)
- 8 in 10 enterprises have had an agent execute a consequential action in production and paid real cost to correct it; they built observability without attribution (Kore.ai, 2026).
- Agents succeed 56.6% of tasks; reliability decays 60% → 25% over eight runs; failures cluster at handoffs and monitoring seams.
- IDC: 1000× growth in agent-related API calls. Gartner: 40% of agentic AI projects canceled by 2027 for cost, unclear ROI, governance failures.

There is no market for network crashes. There is a market for the consequences of not knowing what happened after one. It's called reconciliation, it's already the most expensive manual job in finance, and every agent that touches an API multiplies it.

---

## 11. Why it's a business

**The person.** In every finance team running agents, someone approves each refund, payment, or transfer by hand. Not because the agent is dumb. Because nobody can prove three things about what it did.

**The product.** A receipt per action. Most of what the approver checks is mechanical: is the order still eligible, was it already refunded, is this still allowed. Interlock checks exactly that at the moment of sending. The human sees only the cases that need judgment, plus the `AMBIGUOUS` ones. Experiment 5: reviews from 100 to 33, wrong payouts from 8 to 0, under a stated assumption.

**Nail it.** One action type (refunds), one team, one integration (three lines or the MCP proxy), one metric: approval rate and wrong-payout count before and after.

**Scale it.** More effect types (payments, provisioning, merges). More targets (adapters are four methods). Then the notary: a shared log both agent and service write to, which lifts tier-3 services to tier 2 without changing their API. That's the hosted product, and it's why the receipt format matters: the moat is being the thing everyone integrates against, not a patent.

**Why not the incumbents.** Model providers sell inference. API providers solve dedup for themselves. Durable-execution vendors stop at the tool call. Each sits on one side of the effect. The seam is nobody's product.

---

## 12. Honest limits

- The simulated targets are local and faults are injected, not observed. By design, per the brief. The Stripe and Temporal runs are the "not just a simulation" answer, and they cover a subset of faults.
- Premises are file hashes, function arity, and whatever the integrator writes in the decorator. The one thing no library can guess is which facts the decision depends on.
- Semantic conflicts (same signature, different meaning) are outside any mechanical premise check. Stated as Finding 3.
- Tier 3 blocks refunds that never happened. Stated as the cost of Finding 1.
- The approval-inbox mix is an assumption, not customer data.
- We don't judge whether the decision was right. A carefully executed bad refund is still a bad refund.
- Multiple gates over one target need a shared journal (SQLite is there) or the notary (not built).

---

## 13. Next steps

### Hackathon (Sunday 22:00 → Monday 12:00)

```
NOW ────────────────────────────────────────────────────────────────────────▶ Mon 12:00

 [verify]         [record]           [checkpoint 3]      [one real row]        [final]
 tests pass       3-min video        Sun 22:00 ET        Mon morning           Mon 10:00 cp4
 Stripe ids       face cam + slides  submit repo +       GitHub target,        Mon 12:00 submit
 Temporal md      + real terminal    video + doc         or coverage table     repo public, email,
 3 arXiv links    + cookie sketch    "what changed":     (pick one, not both)  screenshot saved
 fix demo text    upload to Drive    findings 4, live                          laptop closed 10:50
                                     Stripe/Temporal
```

Priority if time runs out: verify → record → submit. Everything else is optional.

### Startup (the next 90 days, if you continue)

```
 Week 1–2          Week 3–4            Month 2              Month 3
 ┌──────────┐      ┌──────────┐        ┌──────────┐         ┌──────────┐
 │ 10 user  │ ──▶  │ 1 design │  ──▶   │ pilot:   │  ──▶    │ notary   │
 │ interviews│      │ partner  │        │ refunds  │         │ v0 +     │
 │ (approvers│      │ (finance │        │ at one   │         │ 2nd      │
 │ + platform│      │ or fintech│        │ team,    │         │ effect   │
 │ eng)      │      │ ops)     │        │ measure  │         │ type     │
 └──────────┘      └──────────┘        │ approval │         └──────────┘
   Mom Test          intros to the      │ rate     │           YC app
   questions         payments-rail      └──────────┘
                     founders we know
```

The interviews come first because the approval-inbox mix is an assumption. The first thing a real finance-ops person tells you replaces it with a number. That number is the pitch.

---

## 14. The video

**Format: slides as backdrop, face cam for talking, real terminal for the three demos, cookie sketch live on camera.** Polished-but-voiceless scored 2.5 in this room; the judge asked for voice by name. Slides that *describe* a demo instead of *showing* it repeat the mistake with nicer fonts.

**The arc:** consequence (the approver) → why (three unanswerable questions) → root (premises go stale) → insight (carry them, re-check at commit, produce a receipt) → demo (naive / 2 / 3) → evidence (table 1 with the idempotency and durable columns) → where it fits (unnamed: retry engines, payment rails, guardrails) → limits and next.

**New since the last script, and worth ten seconds each:** the real Stripe run ("same result on the real service"), the Temporal run ("inside a Temporal activity, the same retry is refused"), and Finding 4 ("our own tests found a bug in our recovery path; here's the fix"). That last one is the most credible sentence in the video. Use it.

Three minutes. Say the dollar amounts. End on the two questions for the judges.
