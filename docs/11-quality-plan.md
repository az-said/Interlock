# 11. Quality plan: what the competition does, what to build, what we may say

Written 2026-09-13 from the live competitor runs in `results/competitors/`, the public-source review in
`results/competitors/closed_and_protocols.md`, the weakness audit in `docs/11-weakness-audit.md`, three
design proposals and three independent judgments of them. It changes no code. Every number below names
where it was measured; anything not measured says so.

The starting point, stated plainly. On live services, a fair hand-written check (an idempotency key, a
lookup, and a premise re-read, 6 to 10 lines) ties Interlock on every outcome it was run against, and
settles faster after every crash. Interlock wins only against each framework's idiomatic pattern, and on
parts of the record. The plan below is aimed at removing the measured losses and at the one lead on record
quality that could be measured next. It does not aim at an outcome win over a careful engineer, because
none of the proposed changes produce one.

## 1. Competitor table

### 1.1 Run live in this project

All rows: Stripe test mode, one $20 refund approved on a $100 payment, real SIGKILL of a separate OS
process, ground truth from Stripe's refund list re-read after the last process exited. "Settle" is crash
to settled, median. Interlock arms used claim_ttl 40s and unsigned receipts.

| System | What it checks, and when | Record | Where it beats Interlock (measured) | Where Interlock beat it (measured) |
|---|---|---|---|---|
| **DBOS Transact 2.31.1** (MIT), Postgres 17 | Nothing about the world by default. Replays recorded steps when a process with the same executor_id restarts. `cancel_workflow` stops a workflow. Datasource transactions run exactly once. | `workflow_status` plus one row per completed step. No row for the killed attempt. No hash or signature: forged step outputs returned by its own API 21/21. The $40 double refund was recorded as SUCCESS. | Settle 2.9 to 5.6s against 41.2 to 42.2s. Shared $30 cap held natively 20/20 + 20/20 in 35 lines, where Interlock's core held 25/40. Revocation by `cancel_workflow` held 3/3 at 2.9s with no re-check code. DBOS plus a 10-line re-check tied Interlock 9/9. | Idiomatic DBOS: hand refund during the outage gave $40 in 2 refunds 3/3; a revocation recorded only in the approval row still refunded 3/3. A process with a different executor_id left the workflow PENDING 3/3 until someone called `resume_workflow` (Conductor waits 60s by default, per docs, not run). |
| **LangGraph 1.2.11** (MIT), PostgresSaver | Re-runs the node on resume. `interrupt` plus `Command(resume)` for the approval, idempotency key from thread id. Revocation by `graph.update_state`. | Checkpoint history holds the interrupt payload, the resume value (approver), the revocation as its own checkpoint, and the refund id. No trace of the killed attempt in 0 of 87 histories. Edited plaintext checkpoints read back silently; EncryptedSerializer caught a flipped byte only in encrypted blobs. | Settle 1.6 to 5.6s against 40.8 to 42.4s. Revocation via `update_state` held 3/3 with no gate. LangGraph Store held the cap 20/20 (Store `put` is an unconditional upsert, race window not timed). A 19-line checked node tied Interlock 29/29 on Stripe end state. | Idiomatic LangGraph: hand refund during the outage gave $40 3/3. All 49 Interlock receipts matched Stripe, and the 29 recovered effects record the re-check values. Noted, a loss for neither: the docs' `Command(goto)` routing plus `update_state` silently dropped the pending node; the measured graph used a static edge. |
| **Google ADK 2.9.0** (Apache-2.0), `require_confirmation`, SqliteSessionService | Confirmation bound to the exact call arguments (source: `request_confirmation.py`); the pause survives process death. Call-id idempotency key. | Session rows with confirmation, arguments and one tool response. No entry for the killed attempt. An edited `sessions.db` loaded without error. | Settle 5.0 to 10.2s against 45.1 to 46.3s. `ToolConfirmation(confirmed=False)` as the resume message stopped the refund 2/2 natively. | Hand refund during the outage: $40 2/2. Revocation recorded outside ADK: refunded 2/2. `app:` state for a shared cap: 0/6 held with no crash, 0/6 after_commit, ledger disagreed with Stripe 12/18. A 9-line hand re-check held 6/6 and an flock arm held 18/18, both faster than Interlock. |
| **OpenAI Agents SDK 0.22.2** (MIT), via LiteLLM to Claude | `needs_approval` pause, serializable RunState, `tool_call_id` stable across reloads. Idempotency is left to the tool. | Approvals stored as call-id lists with no approver or time (0/87). The killed send is missing in 0/60 crashed-agent records. Edited RunState copies loaded 87/87. | Settle 5.5 to 19.5s against 43.0 to 45.8s. The reload, approve, run cycle honored a revocation 3/3 in 32 lines. An flock cap inside the tool held 9/9 in 43 lines, where the Interlock arm needed 93. | Without a key the SDK paid twice 3/3. Hand refund during the outage: $40 3/3. A sticky approved RunState refunded under a revoked approval 3/3 (Interlock combined with sticky resume was not run). No state shared between runs: cap 0/10. |
| **open-multi-agent 1.19.0** (MIT, TypeScript) | Durable tool approval with a SHA-256 requestHash over tool name, input, agent, task and call id. Optional run store with a heartbeat lease (default 60s). `RunLedger.cancel`. | Approval row with reviewer and hash. Journal shows every attempt of a tool call. Not chained or signed: tail drop, a deleted tool result and edits with recomputed hashes all passed `verifyRun`. | Settle 1.4 and 1.5s without the run store, 5.4 and 5.5s with a 5s heartbeat lease, against 44.0s (with the default 60s lease OMA took 60.7 and 60.9s). Cancel during the outage settled in 1.6 and 1.8s against 43.6s. Heartbeat leases tell a slow sender from a dead one (read from code, not run). | Hand refund during the outage: $40 2/2 (OMA plus 9 lines tied). No revocation of a recorded decision without the run store: refunded 2/2. FileStore cap with compareAndSet: 2/5, no crash. |
| **A fair hand-written check** (per harness) | Premise re-read and lookup inside the tool, at send and on retry. | User-written status strings. No record of the killed attempt, no chain. | Tied Interlock on outcomes everywhere it ran; settled faster in every harness (e2e: 15s median against 43s). | Nothing on outcomes. Interlock's record holds DISPATCHED before the kill and the re-check values; the hand check's does not. |
| **Interlock (main)** for reference | Lease and premises at submit; lease and premises again at recovery before any resend; tiered resolution (retry under the provider key, lookup, or AMBIGUOUS). | Hash chain per effect with DISPATCHED written before the send. Unsigned in every live run; a rebuilt chain passed verify 6/6 (github_merge), 9/9 (DBOS harness), 25/25 (SDK harness); only an outside key rejected it. | | |

### 1.2 Public sources only, not run

| System | What it checks, and when | Record | Ahead of Interlock (read, not measured) | Interlock ahead (read, not measured) |
|---|---|---|---|---|
| **Salus** (salus-ai 0.3.7, MIT SDK, hosted control plane) | Policy decision before the call, including whether arguments are grounded in fresh evidence. Brokered execution with a single-use grant. | `decision_events` in hosted Postgres; SDK source says no hash chain; no source says signed. | Argument grounding, brokered credentials, repair hints, shadow mode, Slack approvals, Rewind compensation after commit, multi-host state. | After a crash the SDK raises on an ambiguous replay instead of resolving it; the default key uses a random per-instance run_id, so it does not survive a restart; `CumulativeLimit` is session-scoped only. A real Stripe run looks possible and has not been done. |
| **Bifrost** (Apache-2.0; audit logs Enterprise) | Gateway; tool calls are suggestions and the app owns approval and recovery. | HMAC-signed audit of administrative activity, not tool effects. | Signed audit events with archival; enterprise governance. | No documented fire-time premise re-check, durable intent, or crash recovery for tool effects. |
| **IBM ContextForge 1.0.10** (Apache-2.0) | Plugins at `tool_pre_invoke`; a retry policy can re-send. | `audit_trails` for CRUD, no hash or signature fields. | RBAC, OIDC, OTel, SIEM export, clustering. | No idempotency or lookup for tool effects; no shared cap. |
| **LiteLLM PR #38241** (open) | Agent 365 / Defender allow or block before an MCP call. Not an approval PR (corrects kiro-research.md 3.3). | Spend log with guardrail status; Microsoft audit attributes the call to the user. | Per-user Entra attribution, threat detection on arguments. | No idempotency, premise, revocation window or cap. |
| **HumanLayer 0.7.9** (deprecated) | A person approves each call; a re-run creates a new call id. | Approval records in the vendor cloud. | None beyond human review. | Duplicates, revocations and changed facts resolved mechanically without a second review. |
| **AP2 v0.2.0** (Apache-2.0) | Signed mandates; stateless verifier (this project's probe accepted one presentation twice). | Signed SD-JWT mandate, ES256 receipt if issued. | Cryptographic signatures. | No refund mandate, no revocation, no replay protection in v0.2. |
| **ACP and Stripe Shared Payment Tokens** | Enforced by the receiving service; idempotent POSTs, 409 in-flight, 422 conflict; SPT revocation with a webhook. | Service-side objects; order `adjustments[]` show refunds and disputes. | Enforcement a crashed client cannot bypass; post-commit data a chargeback watch needs. | Refunds are out of scope of `delegate_payment`; no premise re-check; per-token allowance only. |

### 1.3 What the table says

Interlock's measured advantages are narrow and real: it held the hand-refund-during-outage and
revoked-outside-the-framework cells that every idiomatic arm violated, and its record shows the killed
attempt and the re-check values. Its measured disadvantages are also real: 8 to 10 times slower to settle
after a crash, a shared cap that needed scenario code, and a record that is not tamper-evident without a
key held outside the writer. Nothing in the compared set watches the money after commit, except Salus
Rewind and ACP adjustments, neither run here.

## 2. Core changes, in build order

Selection rule: keep a change if it removes a measured loss, closes a measured correctness hole, or makes
the one record lead measurable; cut it otherwise (section 4). Invariants ship as assert-based tests next to
each change, not as a model-checking gate.

### 2.0 Step 0: harness-only work that decides the rules (no core edit, can start now)

Writable today under `experiments/competitor_*.py` and `results/competitors/`.

1. **Finish `competitor_receipt_proof.py`.** No `receipt_proof.{json,txt}` exists; the earlier run wrote no
   cell output. Every anchor and reconcile claim waits on it.
2. **Quiesce cell (new `competitor_quiesce.py`).** The flock probe (`flock_claim.txt`) used a synchronous
   in-process file target, so it cannot show the gap a judge found: a lock freed by the kernel proves the
   process is dead, not that its request has stopped. The kernel still flushes the socket, and the server
   may still be processing. Target: a local HTTP server that accepts a request, waits 2s, then applies.
   SIGKILL the sender right after the request bytes are written. Arms: flock with zero-wait takeover, and
   flock plus the quiesce rule (2.1). Prediction, not measured: 2 effects for the first, 1 for the second.
   Add a fork cell: a child forked while the lock is held keeps the effect pinned as live.
3. **Live Stripe mid-POST kill** with the `FlockClaims` mixin from `competitor_flock_claim.py` wrapping the
   journal, recovery started under 1s. Question: what does a concurrent same-key POST return, and does
   recovery treat it as not final? Today `StripeClient.request` raises `StripeError("409 ...")`, `_resend`
   marks it `interlock_sent`, and `recover()` reports `UNRESOLVED` and keeps the claim. That is safe if it
   holds live; it has not been observed.

### 2.1 Interfaces agreed before parallel work

Builders work on disjoint files against this contract, written down first:

- `journal.dispatch(eid, effect, owner, ttl, budget=None, **data)` returns `None`, `"in_flight"`,
  `"committed"`, `"ambiguous"`, `"conflicting_payload"`, or new `"over_limit"`. On `over_limit` the journal
  has already appended `REFUSED{code: "over_limit", held_by: {eid: amount}}` in the same lock.
  `budget` is `(key, amount, cap)`.
- `journal.holder(eid)` returns `{"live": bool, "owner": str, "sent_at": float}` or `None`. `sent_at` is
  the start of the latest send (DISPATCHED time, or the claim refresh a resend writes).
- `journal.claim(eid, owner, ttl)` keeps its signature and boolean result.
- A target that declares `anchors = True` receives `apply(eid, effect, crash_after_effect=False, anchor=None)`.
  `anchor` is the hash of the **first** DISPATCHED entry for that effect id, so the provider request stays
  byte-identical for the life of the effect id.
- A target may declare `send_timeout` (seconds, below `claim_ttl`); the request must be abandoned by then.
- `receipts.verify()` adds `chain_consistent` and `proof` (`"none"`, `"signed"`, `"reconciled"`).

### 2.2 Step 1: parallel builds (disjoint files)

| Builder | Owns | Change |
|---|---|---|
| A | `interlock/journal.py` | C1 kernel-lock claims, C2 budget inside dispatch, `holder()` |
| B | `interlock/gate.py` | C1 quiesce rule, C3 inline recover on submit, `over_limit` mapping, anchor pass-through, IN_FLIGHT detail |
| C | `interlock/receipts.py`, new `interlock/reconcile_stripe.py` | C5 honest field names, C6 keyless reconcile |
| D | `interlock/targets/stripe_api.py` | C6 anchor metadata, `send_timeout`, distinct in-progress error |
| E | `interlock/easy.py` | C4 `expect=`, kept return values, `budget=` / `send_timeout=` / anchor pass-through |
| F | `interlock/integrations/adk.py`, `interlock/mcp_proxy.py`, new `interlock/why.py` | C7 refusal sentence |
| G | `experiments/competitor_*.py`, `results/competitors/**` | Every live measurement in 2.3 |

These edits touch `interlock/`, which other work owns and this session may not edit. Each lands only with
the owners' approval. Readers outside `interlock/` that C5 changes are listed under C5 for their owners.

#### C1. Kernel-lock claims with a quiesce rule (builders A and B, about 30 lines)

- **Change.** The sender takes `fcntl.flock(LOCK_EX | LOCK_NB)` on `<journal>.locks/<eid>` **before**
  writing DISPATCHED and holds it through apply and COMMITTED; `release()` drops it. `claim()` probes the
  same lock: if held, refuse whatever expiry says; if free and the owner host is this host, take over
  without waiting for expiry. Lock rules: `flock` only (never `lockf` or `fcntl` record locks, which drop
  when any descriptor on the file closes); open with `O_CLOEXEC`; never unlink lock files (unlink races make
  two holders); document that a forked child inherits the lock. Lock order everywhere: per-effect lock, then
  the journal-wide lock (`_exclusive()` sidecar flock, or `BEGIN IMMEDIATE`). A remote owner keeps today's
  TTL rule.
- **Quiesce rule (gate).** Zero-wait takeover is allowed to **resend under the provider's key** at once.
  A lookup that returns "not found" is trusted only when `now - holder.sent_at >= target.send_timeout`;
  before that, recovery returns `IN_FLIGHT` with `retry_after`. This covers tier 2 targets and the tier 1
  stale branch, which also goes through `query` (`gate.py`, `_recover_one`). A provider in-progress answer
  (Stripe 409 on a reused key) maps to UNRESOLVED with the claim kept, never to REFUSED.
- **Fixes.** L1 recovery latency in every harness (40.8 to 46.3s against 1.6 to 17.9s for the fair checked
  arms; 8 Temporal attempts against 2). Also the hung-sender hole measured locally: with the TTL rule a
  sender still inside apply after `claim_ttl` was taken over and the effect applied twice, 6/6 (JSONL and
  SQLite); the flock form never took over, 6/6.
- **Invariant (tests).** At most one process sends an effect id at a time. A live lock holder on this host is
  never taken over. No "not found" lookup is acted on before the latest send's `send_timeout` has passed.
- **Backward compatibility.** Journal files and entries are unchanged; the `.locks/` directory is new.
  `recover()` returns the same statuses. Behavior change: a hung live sender now blocks its effect until it
  exits or is killed, and recovery reports the holder instead of skipping silently. flock is local
  filesystem only (not NFS or SMB; some macOS Docker bind mounts unverified); a journal on such a mount
  keeps the TTL rule. Ceiling: one empty lock file per effect id, removed only offline.
- **Cost to state up front.** The stale branch (hand refund or revocation during the outage) must wait out
  `send_timeout` after the DISPATCHED time before trusting the lookup. With Stripe's current 30s urlopen
  timeout those cells are predicted near 30s, still slower than the hand check's 16s, which does not guard
  this race. `send_timeout` is a calibration knob; report runs at 30s and 10s.
- **Live experiment.** (1) Step 0 cells 2 and 3. (2) Wrap the journal with the mixin in the Interlock arms
  of `experiments/e2e_live.py`, `experiments/adk_live.py`, `competitor_dbos.py` s1 to s3,
  `competitor_langgraph.py` s1 to s4 and `competitor_openai_agents.py`, same model, reps and Stripe setup.
  Pass: Stripe end state identical to the earlier Interlock cells; non-stale cells settle within the fair
  checked arm's spread; stale cells settle within `send_timeout` plus 2s; Temporal attempts 2 per cell;
  zero takeovers of a live sender. (3) Live hung sender, sleeping 45s before the POST with `claim_ttl` 40s.
  With the Idempotency-Key both arms should leave 1 refund, because Stripe dedupes; that result must be
  reported as it lands. The double apply needs a lookup-only variant (key header off, match by metadata):
  predicted 2 refunds on the TTL rule and 1 with the lock. Nothing live is measured yet.

#### C2. Shared budget reserved inside dispatch (builders A, B, E; about 20 lines)

- **Change.** `dispatch(..., budget=(key, amount, cap))` sums amounts of effects under the same key whose
  last DISPATCHED is open, COMMITTED or AMBIGUOUS, under the **journal-wide** lock (never the per-effect lock,
  which two effects under one key do not share). Over the cap it appends `REFUSED{code: over_limit, held_by}`
  and returns `over_limit`; `gate.py` maps it to `REFUSED:over_limit` instead of `IN_FLIGHT` (today's
  `.get(blocker, "IN_FLIGHT")`). The reservation is the DISPATCHED entry, so a `REFUSED{resolves: true}` at
  recovery frees it with no side table. The pre-dispatch `leases.reserve()` hook stays as is for lease
  counting.
- **Fixes.** shared_cap: core alone held 25/40; 40/40 needed the 34-line CapJournal subclass. DBOS held
  natively, ADK `app:` state 0/6, SDK 0/10, OMA FileStore 2/5.
- **Invariant (tests).** Per key, the sum of held amounts never exceeds the cap, checked in the same step
  that writes DISPATCHED. Two processes dispatching two effects under one key at once: at most one proceeds
  when both would exceed. A refused-at-recovery holder frees its amount.
- **Backward compatibility.** Opt-in; no `budget` means today's behavior. Callers that treat every blocker
  as IN_FLIGHT see a new status only when they pass a budget. Ceilings: refunds made outside the journal are
  not counted; AMBIGUOUS holds its amount until a person resolves it; dispatch scans the effect's key in
  O(n) (add a SQLite index when throughput matters).
- **Live experiment.** New `interlock_core_budget` arm in a `competitor_shared_cap` harness: 20 reps each at
  after_commit and before_send, live Stripe, SIGKILL, with C1. Pass: 40/40 with Stripe total at most $30,
  exactly one $20 refund per PaymentIntent, the refused bot answers `REFUSED:over_limit` 40/40, receipts
  name the holder 40/40. Report beside hand_lock (40/40, 0.5 and 1.4s) and DBOS (40/40, different harness).

#### C3. Recover inline on submit (builder B, about 10 lines)

- **Change.** In `Gate.submit`, when the blocker is `in_flight` and `journal.claim()` succeeds (holder dead
  per C1, or remote claim expired), run `_recover_one` and return its status. When the claim is held, return
  `IN_FLIGHT` with the holder and `retry_after`.
- **Fixes.** Recover-then-submit polling loops in every worker (`scenarios/stripe_dispute/worker.py:161-163`,
  `scenarios/connect_payout/worker.py:84-86`) and `backend/config.py` sizing `REFUND_ATTEMPTS = 3 * CLAIM_TTL // 5`
  to outlast a claim.
- **Invariant (tests).** Recovery semantics are unchanged: the same `_recover_one` re-checks lease and
  premises before any resend, and the atomic claim still admits one recoverer.
- **Backward compatibility.** Status strings unchanged; startup `recover()` still works and still returns its
  dict, so `connect_payout/worker.py` keeps working. `submit` may now do premise and lookup I/O on behalf of a
  dead sender.
- **Live experiment.** Copies of the stripe_dispute and connect_payout workers without the polling loop, in a
  competitor harness, plus the e2e Temporal arm with attempts sized to 2. Pass: identical service end state
  and answers per cell; 2 Temporal attempts per cell; the existing randomized fault sweep stays green.

#### C4. Expected-value premises and kept return values in `easy.py` (builder E, about 6 lines)

- **Change.** `effect(..., expect={...})` or `expect=callable` is checked on the facts at decision (refuse
  `REFUSED:premise_false_at_decision` before AUTHORIZED), at dispatch, and at recovery, alongside
  "unchanged". `apply` records the function's return value instead of `{"status": "ok"}`; `query` returns the
  lookup's value and treats `None` as not found (today `bool(...)`, which reads id 0 or `{}` as not found).
- **Fixes.** calendar: `easy.py` as shipped double booked 0/1, reaching 7/7 needed a 21-line override.
  stripe_dispute needed a query override because the lookup was reduced to a bool.
- **Invariant (tests).** Nothing is sent unless `expect` holds on the facts at decision and at the last check
  before the send. Receipt evidence equals the target's result, never a constant.
- **Backward compatibility.** `expect=` is opt-in. Kept return values change receipt `result` contents for
  existing `easy` users (a larger, truthful value); the `is not None` rule changes behavior only for lookups
  that return falsy real values.
- **Live experiment.** Calendar harness arm with `easy.py` plus `expect=` and no override, all 7 fault cells
  including before_send/pre_busy, live Google Calendar. Pass: 7/7 no double booking, pre_busy refused at
  decision, event id in receipt evidence 7/7. stripe_dispute crash_after_send without the query override:
  evidence is the Stripe refund id.

#### C5. Honest receipt fields (builder C, 2 lines in `receipts.py`, plus readers by their owners)

- **Change.** `verify()` returns `chain_consistent` (what `tamper_evident` means today) and `proof`.
  `tamper_evident` becomes true only when `proof` is `"signed"` with a key the verifier supplies or
  `"reconciled"` (C6).
- **Fixes.** `receipts.py:116` reports `tamper_evident: true` on unsigned chains that accepted rebuilt
  forgeries 6/6, 9/9 and 25/25; the README (line 257) and pitch (line 101) repeat it.
- **Invariant (tests).** A chain rebuilt with fresh hashes and no key returns `chain_consistent: true,
  tamper_evident: false`.
- **Backward compatibility.** The key stays; its meaning narrows, which is the point. Readers that meant
  "chain intact" must move to `chain_consistent` in the same release: `tests/test_runtime_gate_parity.py:213`
  (asserts true on an unsigned resealed chain, will fail), `tests/test_demo.py:48`, `demo/index.html:262`
  (labels it "chain intact"), `interlock/export/otlp.py:44`, `backend/demo.py:377`,
  `runtime/interlock_runtime/invariants.py:214`, `scenarios/gcp_resource/systems.py:190`,
  `scenarios/email_tier3/systems.py:162`, `scenarios/stripe_dispute/dispute.py`,
  `experiments/scenario_stripe_dispute.py`. `tests/test_receipts.py:34` checks a signed receipt and stays true.
- **Experiment.** Offline: re-run the forgery suites from `competitor_dbos.py`, `competitor_openai_agents.py`
  and the github_merge scenario. Pass: 100% of rebuilt forgeries report `tamper_evident: false`. No live run
  is needed; this removes an overclaim and wins nothing.

#### C6. Service-anchored receipts and keyless reconcile (builders B, C, D; about 50 lines)

- **Change.** For a target with `anchors = True`, the gate passes the hash of the effect's first DISPATCHED
  entry, which chains PROPOSED, AUTHORIZED, the premises and the checks. The Stripe target writes it as
  refund metadata `interlock_dispatch` next to `interlock_effect_id`. `python -m interlock.reconcile_stripe
  receipt.json` needs no key and no repo writer code: it re-hashes the chain, lists every refund carrying the
  effect id (paginated past 100), reads the anchor from the **`refund.created` event** (a snapshot the key
  holder cannot edit, unlike the refund object), and fails on: a committed receipt with a refund count other
  than 1; an anchor that matches no DISPATCHED entry; an anchored amount or evidence id that differs from
  Stripe's; a `refund.updated` event that changed the anchor; or a receipt that is not committed while Stripe
  holds a refund for the effect.
- **Fixes.** No record in the compared set can be checked against the service without trusting its writer:
  DBOS forged outputs 21/21, ADK and SDK edits 87/87, LangGraph and OMA edits undetected, Interlock rebuilt
  chains accepted. The only independent check today is a harness script (`experiments/e2e_audit.py`).
- **Invariant (tests).** A resend carries the same anchor as the first send, so Stripe's idempotent replay
  still matches. A receipt whose outcome or DISPATCHED content differs from what Stripe holds for its effect
  id fails reconcile, whoever rebuilt the chain.
- **Backward compatibility.** Opt-in per target; targets without `anchors` are called exactly as today.
  Refunds gain one metadata key. Anchoring the first DISPATCHED (not the latest) avoids the case one design
  found: after `settle_failed` a new DISPATCHED under the same key would change the body and Stripe would
  return 400. Ceilings: Stripe keeps events 30 days, so reconcile must run or be exported before then;
  truncating a REFUSED receipt back to an open DISPATCHED passes (it lowers the claim to unknown); the anchor
  witnesses what the gate recorded before sending, not that its checks were honest; Stripe only.
- **Live experiment.** `competitor_receipt_proof.py` cells A (crash_after_commit), B (crash_before_send) and
  C (refused), live Stripe, real SIGKILL. Probe I: resend the same key with a changed anchor, expect Stripe's
  idempotency 400, which proves anchor stability is load-bearing. Probe E: rewrite refund metadata to a
  forged anchor via the API; expect the refund object to show it, `refund.created` to keep the original, and
  a `refund.updated` event to reveal the edit. Forgeries on copies: F1 edit one entry, F2 flip outcome and
  rehash, F3 truncate, F4 rebuild the chain at $15. Pass: reconcile accepts every genuine receipt, rejects
  F1 to F4 (F3 only when it truncates a COMMITTED), and today's `verify()` accepts F2 and F4.

#### C7. One refusal sentence for the model (builder F, about 20 lines)

- **Change.** Port the `WHY` table from `Interlock-build/interlock/escalation.py` into `interlock/why.py`.
  Where a model reads the result (`integrations/adk.py`, `mcp_proxy.py`), return the status plus one sentence
  rendered from journal entries (for example, "Not sent: a fact this action depends on changed while the
  agent was down; a person decides"). No new fields beyond the sentence.
- **Fixes.** The ADK model read `stale_premise_at_recovery` as "a business logic issue" and misread
  `lease at recovery` (`results/adk_live.md`).
- **Invariant (tests).** Status strings are unchanged; the sentence is rendered only from journal entries,
  so it cannot disagree with the receipt; it never quotes payload values.
- **Backward compatibility.** Callers comparing status strings are unaffected.
- **Live experiment.** `adk_live.py` and the sdk_interlock column, hand_refund_during_outage and
  approval_revoked_during_outage, 10 reps per cell. A script scores each final message against Stripe truth
  (says not sent, says why, says a person decides) and counts refund-tool re-calls. Pass: at least 9/10
  correct per cell and 0 re-calls, reported per rep.

### 2.3 Step 2: measure step 1

Builder G runs every experiment above against the merged code, same models, reps and Stripe test mode, and
writes `results/competitors/*.md` with raw per-cell rows. No claim in section 3.2 moves to 3.1 before its row
exists.

### 2.4 Step 3: settlement, evidence only (after C6's run lands)

- **Change.** New `interlock/settle.py`, a port of `Interlock-build/interlock/confirm.py` (signature-verified
  webhook and lookup, rank-monotone status, test mode only), extended to paginate past 100 refunds and to read
  `charge.dispute.created` and `charge.dispute.closed`. It appends `SETTLED{status, refund, amount}` and, when
  a dispute opens on a charge with a succeeded gated refund, `SETTLED{status: at_risk, dispute, exposure_cents}`.
  Builder C adds `final_money` to `verify()`.
- **Invariant (test).** Removing every SETTLED entry changes no gate decision: `submit`, `dispatch` and
  `recover` never read them.
- **Fixes.** stripe_dispute: "answer vs final money" was 1/2 for every column; the 300s gap probe left the
  merchant out $120 on a $100 payment and no column saw it.
- **Backward compatibility.** New entry kind ignored by send accounting; opt-in watcher.
- **Live experiment.** stripe_dispute harness with a watcher arm, and the hand_check arm given the same
  webhook (fair). Pass: `final_money` matches Stripe in crash_after_send_chargeback_during_outage; `at_risk`
  with exposure 12000 appears within 60s of dispute creation in the gap probe. Expected: a tie with the hand
  check on detection. Detection does not return the $120.

### 2.5 Step 4, optional: attributed "done by someone else"

In the Stripe target only: a refund on the payment whose metadata names this case refuses the agent's refund
as `REFUSED:done_by_others` with that refund id. It can only narrow sends. It needs support tooling to stamp
the case id; the harnesses' hand refunds carried none, so it changes nothing measured until that exists, and
it does not fix the `unrelated_refund_during_outage` SHORT row.

## 3. Claim matrix

### 3.1 Claims we can make today

Each is measured, with its source.

- Against each framework's documented or idiomatic pattern, a person refunding the same $20 by hand during
  the outage produced a double refund ($40) in DBOS 3/3, LangGraph 3/3, ADK 2/2, OpenAI Agents SDK 3/3 and
  open-multi-agent 2/2. Interlock held in every harness it ran in.
- A revocation recorded outside the framework still refunded in ADK 2/2, OMA without its run store 2/2, DBOS
  when nobody called `cancel_workflow` 3/3, and an SDK sticky RunState 3/3. Interlock refused at recovery
  (Interlock with a sticky SDK resume was not run).
- A fair hand-written check, 6 to 10 lines, tied Interlock on every outcome in every harness where both ran.
- Interlock is slower after a crash: 40.8 to 46.3s median against 1.6 to 17.9s for the fair checked arms, and
  43s against 15s end to end on Temporal. The whole gap is the claim TTL.
- Interlock's record shows the killed send (DISPATCHED before the kill, 17/17 in the SDK harness) and the
  re-check values at recovery. DBOS, LangGraph (0/87), ADK and the SDK (0/60) kept no trace of the killed
  attempt. OMA's journal does show every attempt.
- Editing one entry of an Interlock receipt fails verify (9/9, 25/25). Rebuilding the chain with fresh hashes
  passes unless a key held outside the writer is used (6/6, 9/9, 25/25 accepted unsigned). No live run signed.
- Interlock's core alone held a shared cap 25/40; 40/40 needed scenario code.
- Locally only (file target, 3 trials per cell, JSONL and SQLite): a per-effect kernel lock cut recovery from
  5.01 to 5.06s to 0.00 to 0.01s with exactly one effect in 12/12 cells; the core TTL rule applied an effect
  twice while its sender was alive and still inside apply, 6/6, and the lock arm did not, 6/6.
- Nobody in the compared set, Interlock included, detected the $120 refund-plus-chargeback loss.

### 3.2 Claims we can make only after the named run passes

| Claim | Needs |
|---|---|
| After a SIGKILL on the same host, Interlock settles non-stale cells within the fair checked arm's spread (a tie on time, not a win). | C1 runs in e2e, ADK, DBOS, LangGraph and SDK harnesses. |
| Stale cells settle within `send_timeout` plus 2s, and no "not found" lookup is trusted while a request may still land. | C1 quiesce cell and live runs at 30s and 10s. |
| Zero-wait takeover never double-applies a request still in flight at the server. | Step 0 quiesce cell (local) plus live mid-POST kill. |
| A live but hung sender is never taken over, where the TTL rule double-applies on a no-dedup target. Parity with OMA's heartbeat lease, a lead over Interlock's current core. | C1 hung-sender cell on a lookup-only live target. |
| The core holds a shared cap 40/40 under SIGKILL with no subclass and names the holder. A tie with hand_lock and DBOS on money. | C2 run. |
| Workers need no polling loop; Temporal uses 2 attempts per cell. | C3 run. |
| `easy.py` as shipped holds the calendar matrix 7/7. A tie with hand_check. | C4 run. |
| Unsigned receipts no longer report tamper evidence. | C5 merged with its readers. |
| Anyone can check an Interlock refund receipt against Stripe without trusting the writer, and a rebuilt chain is rejected. Among DBOS, LangGraph, ADK, the OpenAI Agents SDK and OMA as run here, no other record can be checked this way. A lead on record quality, not on outcomes, Stripe only, within 30 days. | C6 `receipt_proof` run including probes I and E. |
| The model explains refusals correctly at least 9 times in 10 and does not retry. | C7 run. |
| The receipt reflects final money after a failed refund or a chargeback. A tie with a hand check given the same webhook. | Step 3 run. |
| Interlock answers AMBIGUOUS where the idiomatic hand check sends a second email after the 25-hour key window. | A real 25-hour run; today it is read from code. |

### 3.3 Claims we should never make

- "Exactly once." Tier 3 answers AMBIGUOUS, and the email case matched 1/3 answers against 2/3 for the hand
  check.
- Better outcomes than a fair hand-written check. Every change here is something a hand check can also write.
- Faster recovery than DBOS, LangGraph, the SDK, ADK or OMA. The best case is a tie on one host.
- Tamper-evident or tamper-proof receipts without an outside key or a passing reconcile; and never protection
  against a Stripe key holder beyond Stripe's 30-day event retention.
- Cross-host coordination. The SQLite journal is one host and flock is one kernel; DBOS and LangGraph keep
  state in Postgres.
- Prevents chargeback losses. Settlement detects after the fact.
- "Cuts two thirds of approvals" (that came from the rules; Interlock added 8 reviews), "no per-tool code"
  (the Interlock arm was as long or longer than the hand check in 7 of 8 scenarios), or "about 400 lines" (843).
- Compliance or certification. Mapping rows are evidence an assessor may weigh.
- Any Salus, Bifrost, ContextForge, HumanLayer, AP2 or ACP outcome. None was run.
- Any number from a design proposal presented as a result.

## 4. What to cut

- **Fencing epoch, `force_hung_after_s`, LATE_RESULT.** They matter only for cross-host or forced takeover,
  which is unsupported. Adding the epoch to resends would also change the anchored request body.
- **Overlap-aware premises (`still_ok` "holds despite change") and the `same_action="amount"` heuristic.**
  Both widen what gets sent with unmodeled money-moving logic (an unattributed partial duplicate passes,
  bounded only by the charge) to fix one SHORT row a hand check ties anyway. Only the attributed refusal in
  2.5 survives, because it can only narrow.
- **Refusing refunds during an open dispute inquiry as a default.** Merchant policy, not a gate invariant.
- **Model checking as a release gate.** Invariants ship as assert tests.
- **Ed25519 and Cloud KMS signers, keyrings with retirement.** The KMS API is disabled on the project and
  signing adds dependencies; the existing HMAC path plus reconcile covers the record claim.
- **Locked Cloud Logging retention and new compliance rows.** Locking is irreversible, 400 days does not meet
  SOX retention, and a mapping row without a run behind it is the overclaim C5 removes.
- **New GitHub, Calendar and GCS adapters, LangGraph and OpenAI Agents shims, and the LLM-written adoption
  benchmark.** Too much surface to build and measure honestly now; the benchmark measures a model, not
  developers. Revisit adapters only if the Stripe path measurably beats the hand check on lines with an
  identical end state.
- **Outcome objects with `.next`, `.repair` and `.changed`.** One sentence is what the measured misread
  needs.
- **32-hex effect ids and dual widths.** Hygiene with no measured failure (about 0.18% collision odds at 1M
  effects in one journal); note it and revisit at volume.
- **Duplicate witness designs.** Three proposals each had one; C6 is the single implementation.
