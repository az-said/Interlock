# Competitor: OpenAI Agents SDK human-in-the-loop, Stripe test mode, real SIGKILL

Generated 2026-09-14 00:50 UTC by `experiments/competitor_openai_agents.py`. openai-agents 0.22.2 (MIT), litellm 1.83.0, model `anthropic/claude-haiku-4-5-20251001` through the SDK's `LitellmModel`, Stripe test mode, Interlock claim TTL 40s. Invalid cells (crash window missed, model did not pause for approval) are listed and excluded from tallies.

## How the SDK was run

As its human-in-the-loop guide describes: `@function_tool(needs_approval=True)` on `issue_refund`; `Runner.run` pauses with `result.interruptions`; the app stores `result.to_state().to_string()`; later `RunState.from_string(agent, s)`, `state.approve(item)` or `state.reject(item)`, and `Runner.run(agent, state, session=session)` with a `SQLiteSession`. The person's decision lives in an approvals table (approved by finance-lead, cap, revoked time) and is applied to the state each time the app resumes, which is the documented reload-approve-run sequence. Each phase is a separate OS process: decide (the model reads the payment and asks to refund), run (approval applied, tool executes, SIGKILL in the send), resume (a new process repeats reload, approve, run). The guide's caveat, "structure tools for idempotency", is followed with `Idempotency-Key = case/tool_call_id`.

## Results

### `crash_after_commit`

SIGKILL after Stripe's response to the refund POST arrived, before the SDK recorded the tool output; restarted and resumed. Want $20 in 1 refund.

| column | cells |
|---|---|
| SDK needs_approval + RunState resume, tool sends with no idempotency key | REFUNDED; $40 in 2 (want $20 in 1); **VIOLATED, $20 too much**; answer CONTRADICTS Stripe; 8.8s<br>REFUNDED; $40 in 2 (want $20 in 1); **VIOLATED, $20 too much**; answer CONTRADICTS Stripe; 8.5s<br>REFUNDED; $40 in 2 (want $20 in 1); **VIOLATED, $20 too much**; answer CONTRADICTS Stripe; 8.7s |
| SDK needs_approval + RunState resume, Idempotency-Key = case / tool_call_id (docs: make tools idempotent) | REPLAYED_BY_STRIPE; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 10.0s<br>REPLAYED_BY_STRIPE; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 10.9s<br>REPLAYED_BY_STRIPE; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 10.5s |
| as sdk, plus a hand-written re-check at the top of the tool (lookup, approval, refunds unchanged) | FOUND_BY_LOOKUP; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 6.9s<br>FOUND_BY_LOOKUP; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 7.9s<br>FOUND_BY_LOOKUP; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 8.6s |
| as sdk, with the tool body sent through Interlock's Gate (CapGate for the race) | DUPLICATE_IGNORED; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 42.8s<br>DUPLICATE_IGNORED; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 43.3s<br>DUPLICATE_IGNORED; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 43.4s |

### `hand_refund_during_outage`

SIGKILL right before the refund POST; support refunds the same $20 by hand (no key, no metadata); restarted and resumed. Want only the hand refund.

| column | cells |
|---|---|
| SDK needs_approval + RunState resume, Idempotency-Key = case / tool_call_id (docs: make tools idempotent) | REFUNDED; $40 in 2 (want $20 in 1); **VIOLATED, $20 too much**; answer matches Stripe; 14.8s<br>REFUNDED; $40 in 2 (want $20 in 1); **VIOLATED, $20 too much**; answer matches Stripe; 15.6s<br>REFUNDED; $40 in 2 (want $20 in 1); **VIOLATED, $20 too much**; answer matches Stripe; 14.3s |
| as sdk, plus a hand-written re-check at the top of the tool (lookup, approval, refunds unchanged) | REFUSED:stale_premise; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 14.9s<br>REFUSED:stale_premise; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 17.9s<br>REFUSED:stale_premise; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 18.0s |
| as sdk, with the tool body sent through Interlock's Gate (CapGate for the race) | REFUSED:stale_premise; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 44.2s<br>REFUSED:stale_premise; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 44.1s<br>REFUSED:stale_premise; $20 in 1 (want $20 in 1); **held**; answer matches Stripe; 44.5s |

### `approval_revoked_during_outage`

SIGKILL right before the refund POST; Finance revokes the approval in the approvals table; restarted and resumed. Want nothing.

| column | cells |
|---|---|
| SDK needs_approval + RunState resume, Idempotency-Key = case / tool_call_id (docs: make tools idempotent) | REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 12.6s<br>REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 13.0s<br>REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 13.1s |
| as sdk, but the approved RunState is saved and resumed as is (sticky approval, no re-decision) | REFUNDED; $20 in 1 (want $0 in 0); **VIOLATED, $20 too much**; answer matches Stripe; 18.7s<br>REFUNDED; $20 in 1 (want $0 in 0); **VIOLATED, $20 too much**; answer matches Stripe; 19.5s<br>REFUNDED; $20 in 1 (want $0 in 0); **VIOLATED, $20 too much**; answer matches Stripe; 21.5s |
| as sdk, plus a hand-written re-check at the top of the tool (lookup, approval, refunds unchanged) | REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 12.7s<br>REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 10.8s<br>REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 10.8s |
| as sdk, with the tool body sent through Interlock's Gate (CapGate for the race) | REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 43.0s<br>REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 43.3s<br>REJECTED_BY_APPROVER_ON_RESUME; $0 in 0 (want $0 in 0); **held**; answer matches Stripe; 43.0s |

### `shared_cap_race`

Two agent processes (support-bot, billing-bot), each a separate SDK run and session on one $100 payment. Each asks for $20; each approval request shows only its own $20 and is approved (case cap $30). Both resume from one barrier 15s after spawn; the first to reach the crash point is SIGKILLed and restarted at once. Invariant: total refunded <= $30.

| column | crash | held | totals | median settle (s) | what each bot reported (killed / other) |
|---|---|---|---|---|---|
| SDK needs_approval + RunState resume, Idempotency-Key = case / tool_call_id (docs: make tools idempotent) | `after_commit` | 0/5 | $40, $40, $40, $40, $40 | 6.7 | REPLAYED_BY_STRIPE / REFUNDED; REPLAYED_BY_STRIPE / REFUNDED; REPLAYED_BY_STRIPE / REFUNDED; REPLAYED_BY_STRIPE / REFUNDED; REPLAYED_BY_STRIPE / REFUNDED |
| SDK needs_approval + RunState resume, Idempotency-Key = case / tool_call_id (docs: make tools idempotent) | `before_send` | 0/5 | $40, $40, $40, $40, $40 | 5.5 | REFUNDED / REFUNDED; REFUNDED / REFUNDED; REFUNDED / REFUNDED; REFUNDED / REFUNDED; REFUNDED / REFUNDED |
| as sdk, plus the re-check inside an flock on the shared run dir (strongest hand-written arm) | `after_commit` | 4/4 (1 invalid) | $20, $20, $20, $20 | 10.3 | FOUND_BY_LOOKUP / REFUSED:over_cap; FOUND_BY_LOOKUP / REFUSED:over_cap; FOUND_BY_LOOKUP / REFUSED:over_cap; FOUND_BY_LOOKUP / REFUSED:over_cap |
| as sdk, plus the re-check inside an flock on the shared run dir (strongest hand-written arm) | `before_send` | 5/5 | $20, $20, $20, $20, $20 | 7.0 | REFUSED:over_cap / REFUNDED; REFUSED:over_cap / REFUNDED; REFUSED:over_cap / REFUNDED; REFUSED:over_cap / REFUNDED; REFUSED:over_cap / REFUNDED |
| as sdk, with the tool body sent through Interlock's Gate (CapGate for the race) | `after_commit` | 4/4 (1 invalid) | $20, $20, $20, $20 | 45.8 | DUPLICATE_IGNORED / REFUSED:over_cap; DUPLICATE_IGNORED / REFUSED:over_cap; DUPLICATE_IGNORED / REFUSED:over_cap; DUPLICATE_IGNORED / REFUSED:over_cap |
| as sdk, with the tool body sent through Interlock's Gate (CapGate for the race) | `before_send` | 4/4 (1 invalid) | $20, $20, $20, $20 | 43.8 | DUPLICATE_IGNORED / REFUSED:over_cap; DUPLICATE_IGNORED / REFUSED:over_cap; DUPLICATE_IGNORED / REFUSED:over_cap; DUPLICATE_IGNORED / REFUSED:over_cap |

## Tally (valid cells)

| scenario | column | held | answers match Stripe | median settle (s) |
|---|---|---|---|---|
| `crash_after_commit` | sdk_nokey | 0/3 | 0/3 | 8.7 |
| `crash_after_commit` | sdk | 3/3 | 3/3 | 10.5 |
| `crash_after_commit` | sdk_checked | 3/3 | 3/3 | 7.9 |
| `crash_after_commit` | sdk_interlock | 3/3 | 3/3 | 43.3 |
| `hand_refund_during_outage` | sdk | 0/3 | 3/3 | 14.8 |
| `hand_refund_during_outage` | sdk_checked | 3/3 | 3/3 | 17.9 |
| `hand_refund_during_outage` | sdk_interlock | 3/3 | 3/3 | 44.2 |
| `approval_revoked_during_outage` | sdk | 3/3 | 3/3 | 13.0 |
| `approval_revoked_during_outage` | sdk_sticky | 0/3 | 3/3 | 19.5 |
| `approval_revoked_during_outage` | sdk_checked | 3/3 | 3/3 | 10.8 |
| `approval_revoked_during_outage` | sdk_interlock | 3/3 | 3/3 | 43.0 |
| `shared_cap_race/after_commit` | sdk | 0/5 | - | 6.7 |
| `shared_cap_race/before_send` | sdk | 0/5 | - | 5.5 |
| `shared_cap_race/after_commit` | sdk_lock | 4/4 | - | 10.3 |
| `shared_cap_race/before_send` | sdk_lock | 5/5 | - | 7.0 |
| `shared_cap_race/after_commit` | sdk_interlock | 4/4 | - | 45.8 |
| `shared_cap_race/before_send` | sdk_interlock | 4/4 | - | 43.8 |

## Lines of user code

Counted by the harness from `# user:<tag>` regions of the script (non-blank, non-comment; crash hooks and logging excluded). `common` is the agent, both tools' signatures, the approval pause, storing state, and the reload-approve-run resume every SDK column needs.

| column | lines |
|---|---|
| sdk_nokey | 32 |
| sdk | 32 |
| sdk_sticky | 37 |
| sdk_checked | 44 |
| sdk_lock | 43 |
| sdk_interlock | 46 |
| sdk_interlock (race, + scenarios/shared_cap/cap.py reserve code) | 93 |

Regions: {"common": 27, "send": 5, "checked": 12, "lock": 11, "interlock": 19, "sticky": 5, "interlock_cap_scenario_code": 47}. Interlock itself (`interlock/`) is a library and is not counted; the race's cap reservation is scenario code (`scenarios/shared_cap/cap.py`, `reserved_cents`, `CapJournal`, `CapGate`) and is.

## Records

Scored per cell from the artifacts each system leaves, by the harness after the run (JSON `sdk_record`, `interlock_record`).

- `crash_after_commit` / sdk_nokey / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome does NOT match Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk_nokey / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome does NOT match Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk_nokey / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome does NOT match Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk_checked / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk_checked / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk_checked / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `crash_after_commit` / sdk_interlock / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/COMMITTED: valid=True, happened=True, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `crash_after_commit` / sdk_interlock / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/COMMITTED: valid=True, happened=True, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `crash_after_commit` / sdk_interlock / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/COMMITTED: valid=True, happened=True, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `hand_refund_during_outage` / sdk / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `hand_refund_during_outage` / sdk / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `hand_refund_during_outage` / sdk / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `hand_refund_during_outage` / sdk_checked / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `hand_refund_during_outage` / sdk_checked / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `hand_refund_during_outage` / sdk_checked / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `hand_refund_during_outage` / sdk_interlock / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/REFUSED/PROPOSED/AUTHORIZED/REFUSED: valid=True, happened=False, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `hand_refund_during_outage` / sdk_interlock / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/REFUSED/PROPOSED/AUTHORIZED/REFUSED: valid=True, happened=False, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `hand_refund_during_outage` / sdk_interlock / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/REFUSED/PROPOSED/AUTHORIZED/REFUSED: valid=True, happened=False, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `approval_revoked_during_outage` / sdk / rep 0: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk / rep 1: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk / rep 2: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk_sticky / rep 0: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk_sticky / rep 1: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk_sticky / rep 2: SDK RunState+session: approval approved by call id only (fields ['approved', 'rejected']); tool outputs 1 for 2 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk_checked / rep 0: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk_checked / rep 1: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk_checked / rep 2: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned
- `approval_revoked_during_outage` / sdk_interlock / rep 0: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/REFUSED: valid=True, happened=False, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `approval_revoked_during_outage` / sdk_interlock / rep 1: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/REFUSED: valid=True, happened=False, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None
- `approval_revoked_during_outage` / sdk_interlock / rep 2: SDK RunState+session: approval rejected by call id only (fields ['approved', 'rejected', 'rejection_messages']); tool outputs 1 for 1 real attempts; no checks recorded; outcome matches Stripe; edited copy loads (not tamper-evident); unsigned; Interlock receipt PROPOSED/AUTHORIZED/DISPATCHED/REFUSED: valid=True, happened=False, killed attempt visible=True, approver=finance-lead, edited entry rejected=True, rebuilt chain accepted=True, signed=None

## Reading

Every number here is copied from the tables above (valid cells only). Three race runs were excluded for network
faults, listed at the end of this section.

### What the SDK gives you out of the box, measured

- **The approval pause survives a process death.** `RunState.to_string()` held the pending `issue_refund` call; a new
  process reloaded it and the model's `tool_call_id` was the same (probe before the run, and every cell here). An
  `Idempotency-Key` built from that id made the resumed send a Stripe replay: `crash_after_commit` / sdk held 3/3,
  `REPLAYED_BY_STRIPE`, median 10.5s from crash to settled. Without a key (the docs leave idempotency to the tool)
  the same resume paid twice: `sdk_nokey` 0/3, $40 each, and the agent's answer named one refund while Stripe held two.
- **Revocation is honored for free if the app re-applies the person's decision on every resume.** The documented
  sequence is reload, approve or reject, run. With the decision read from the approvals table each time,
  `approval_revoked_during_outage` / sdk held 3/3 at 13.0s with 32 lines of user code, and the model's final message
  explained the refusal. If the app instead saves the approved state and resumes it as is (approvals are sticky and
  survive serialization, per the docs), the revoked approval was used: `sdk_sticky` 0/3, $20 refunded each time.
- **What the SDK cannot see:** the world changing under an approved call. `hand_refund_during_outage` / sdk 0/3, $40
  each: the approval was still live, so the resume re-ran the approved call, and the call-id key only matches the
  same request. With two agents under one $30 cap, each approval request shows only its own $20 and the SDK has no
  state shared between runs or sessions: `shared_cap_race` / sdk 0/10, $40 in every run.

### Against Interlock inside the same SDK tool

- **Outcomes: a tie with a fair hand-written check, as in every earlier scenario.** The SDK tool with about a dozen
  hand-written lines (`sdk_checked`: lookup by metadata, approval still live, refunds unchanged since the decision)
  held 9/9 single-agent cells; Interlock as the tool body held 9/9. For the race, the same check inside an flock
  (`sdk_lock`) held 9/9; Interlock with the scenario's cap reservation (`CapGate`) held 8/8. Interlock never held a
  cell the strongest hand-written arm lost.
- **Settle time: the SDK arms are 3 to 6 times faster.** Median crash to settled: sdk_checked 7.9s, 17.9s and 10.8s
  against Interlock 43.3s, 44.2s and 43.0s; race sdk_lock 10.3s and 7.0s against Interlock 45.8s and 43.8s. The
  whole gap is Interlock's 40s claim TTL: a SIGKILLed sender's claim cannot be told from a slow one, so recovery
  waits it out. The flock is dropped by the kernel the instant its holder dies.
- **Lines of user code** (counted from the script's regions): sdk 32, sdk_sticky 37, sdk_lock 43, sdk_checked 44,
  sdk_interlock 46, and 93 for the race once the cap reservation in `scenarios/shared_cap/cap.py` (47 lines) is
  counted. For these scenarios Interlock does not save code over the hand-written arms; the shared cap costs more.
- **Records: Interlock's is the only one that shows the crash.** In 60 of 60 crashed-agent SDK records (RunState JSON
  plus the SQLiteSession) the killed send is absent: the session holds one tool output for two real executions of the
  tool, and the invocation ledger the SDK keeps in memory (`executed`/`completed`) is only saved when the app calls
  `to_state()`, which it cannot do from inside a killed send. The SDK stores approvals as lists of call ids, with no
  approver and no time (0/87 records). An edited copy (decision flipped, Stripe refund ids replaced) loaded without
  error 87/87. Interlock's receipts showed the DISPATCHED entry written before the kill for 17/17 sent effects, the
  approver read at dispatch (`finance-lead`), and rejected an edited entry 25/25. They are unsigned: a chain rebuilt
  with fresh hashes was accepted 25/25, so neither record is proof against whoever holds the files. Stripe's refund
  list is the evidence in both.
- **An Interlock observation that is not a win:** in `approval_revoked_during_outage` Interlock's recover on start
  refused with `REFUSED:lease_at_recovery` in 3/3 before the SDK's approver rejected the call, and the receipt records
  that. Interlock under a sticky resume was not run, so this run does not show Interlock catching what `sdk_sticky` missed.

### Seen once, not measured

- When a tool raised (a Stripe TLS handshake timeout, excluded run below), the SDK returned the error to the model and
  the model asked for a new `issue_refund` call with a new call id, so a new approval request. Had a person approved
  it under the call-id key, it would have been a new Stripe key. Nothing was approved or sent in that run.

### Excluded runs

- `shared_cap_race` / sdk_lock / after_commit rep 1: DNS failure in the restarted bot's Stripe call, exit 1 (Stripe held $20).
- `shared_cap_race` / sdk_interlock / after_commit rep 3: Anthropic disconnected on the resumed bot's final model call
  after the tool had answered `DUPLICATE_IGNORED`, exit 1 (Stripe held $20).
- `shared_cap_race` / sdk_interlock / before_send rep 0: both bots' premise reads timed out on the TLS handshake before
  anything was dispatched; no bot reached the crash point and nothing was refunded.

### Limits

- One host, one Stripe test account, Claude Haiku 4.5 through LiteLLM (the SDK's default OpenAI models were not run:
  no working OpenAI key). OpenAI tracing was disabled, so the SDK's hosted trace record was not evaluated.
- The approver is a function applying the approvals table, standing in for a person clicking approve; it approved
  every live, in-cap request. A person who looked at the payment might have caught the hand refund.
- Race runs start both bots from one barrier, the worst case for check-then-send. 3 reps per single-agent cell, 5 per
  race crash point (fewer where excluded).
- The SDK was not run inside a durable-execution engine (such as Temporal); that combination is not measured here.


## Ids, for checking in the Stripe test dashboard

- `crash_after_commit` / sdk_nokey / rep 0: PaymentIntent `pi_3UFNoG88KhIqqdFL1OtdLgqY`, refunds `re_3UFNoG88KhIqqdFL1HLG67Jq` $20 succeeded, `re_3UFNoG88KhIqqdFL1WKFks5Y` $20 succeeded, processes [(31295, 'python'), (31591, 'python'), (31777, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_nokey / rep 1: PaymentIntent `pi_3UFNoG88KhIqqdFL1HjSDTJW`, refunds `re_3UFNoG88KhIqqdFL1WGgsAZg` $20 succeeded, `re_3UFNoG88KhIqqdFL1caFD1Pe` $20 succeeded, processes [(31294, 'python'), (31610, 'python'), (31804, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_nokey / rep 2: PaymentIntent `pi_3UFNoH88KhIqqdFL0OlCvD4i`, refunds `re_3UFNoH88KhIqqdFL0IeW5UmB` $20 succeeded, `re_3UFNoH88KhIqqdFL0KW0mJIT` $20 succeeded, processes [(31297, 'python'), (31600, 'python'), (31808, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk / rep 0: PaymentIntent `pi_3UFNos88KhIqqdFL1T49xjrt`, refunds `re_3UFNos88KhIqqdFL1iQfJHPS` $20 succeeded, processes [(32127, 'python'), (32694, 'python'), (32927, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk / rep 1: PaymentIntent `pi_3UFNos88KhIqqdFL1Gd8uwoq`, refunds `re_3UFNos88KhIqqdFL1uQYRSiE` $20 succeeded, processes [(32121, 'python'), (32690, 'python'), (32858, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk / rep 2: PaymentIntent `pi_3UFNos88KhIqqdFL0YsoYxoI`, refunds `re_3UFNos88KhIqqdFL0CvJgT7s` $20 succeeded, processes [(32122, 'python'), (32682, 'python'), (32837, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_checked / rep 0: PaymentIntent `pi_3UFNpP88KhIqqdFL043L4jVZ`, refunds `re_3UFNpP88KhIqqdFL0zRRRcli` $20 succeeded, processes [(33201, 'python'), (33421, 'python'), (33536, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_checked / rep 1: PaymentIntent `pi_3UFNpQ88KhIqqdFL1H78lyhf`, refunds `re_3UFNpQ88KhIqqdFL19WlADfz` $20 succeeded, processes [(33229, 'python'), (33449, 'python'), (33608, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_checked / rep 2: PaymentIntent `pi_3UFNpQ88KhIqqdFL0f6Zg4la`, refunds `re_3UFNpQ88KhIqqdFL0RbbiYRL` $20 succeeded, processes [(33235, 'python'), (33466, 'python'), (33637, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_interlock / rep 0: PaymentIntent `pi_3UFNpo88KhIqqdFL0gC8HnGR`, refunds `re_3UFNpo88KhIqqdFL0sHS2ysT` $20 succeeded, processes [(33756, 'python'), (33960, 'python'), (34039, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_interlock / rep 1: PaymentIntent `pi_3UFNpr88KhIqqdFL1bFnW2N4`, refunds `re_3UFNpr88KhIqqdFL1frDJA6C` $20 succeeded, processes [(33879, 'python'), (33991, 'python'), (34193, 'python')], exits [0, -9, 0]
- `crash_after_commit` / sdk_interlock / rep 2: PaymentIntent `pi_3UFNpt88KhIqqdFL0DWHvACi`, refunds `re_3UFNpt88KhIqqdFL010WHwRc` $20 succeeded, processes [(33906, 'python'), (34018, 'python'), (34259, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk / rep 0: PaymentIntent `pi_3UFNqp88KhIqqdFL0DuK2E6Z`, refunds `re_3UFNqp88KhIqqdFL0KP0CdoZ` $20 succeeded, `re_3UFNqp88KhIqqdFL0lQqbN7F` $20 succeeded, processes [(34926, 'python'), (35237, 'python'), (35425, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk / rep 1: PaymentIntent `pi_3UFNqs88KhIqqdFL0ehj55cv`, refunds `re_3UFNqs88KhIqqdFL04qGA1ZS` $20 succeeded, `re_3UFNqs88KhIqqdFL03yCAW8k` $20 succeeded, processes [(34969, 'python'), (35323, 'python'), (35520, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk / rep 2: PaymentIntent `pi_3UFNqv88KhIqqdFL1QVPdZjj`, refunds `re_3UFNqv88KhIqqdFL1NG1yK5O` $20 succeeded, `re_3UFNqv88KhIqqdFL1eBUImRY` $20 succeeded, processes [(35037, 'python'), (35362, 'python'), (35673, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk_checked / rep 0: PaymentIntent `pi_3UFNrV88KhIqqdFL0qVUfDcK`, refunds `re_3UFNrV88KhIqqdFL01J60fiB` $20 succeeded, processes [(36294, 'python'), (37173, 'python'), (37502, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk_checked / rep 1: PaymentIntent `pi_3UFNra88KhIqqdFL07EYtVch`, refunds `re_3UFNra88KhIqqdFL0VC8tu9W` $20 succeeded, processes [(36900, 'python'), (37339, 'python'), (37625, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk_checked / rep 2: PaymentIntent `pi_3UFNrc88KhIqqdFL0sNNusax`, refunds `re_3UFNrc88KhIqqdFL0oprWWgS` $20 succeeded, processes [(37045, 'python'), (37410, 'python'), (37640, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk_interlock / rep 0: PaymentIntent `pi_3UFNs988KhIqqdFL149TEJjn`, refunds `re_3UFNs988KhIqqdFL1OgsBHSg` $20 succeeded, processes [(37902, 'python'), (38974, 'python'), (39412, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk_interlock / rep 1: PaymentIntent `pi_3UFNsH88KhIqqdFL16SfLrrN`, refunds `re_3UFNsH88KhIqqdFL1G1y5lFJ` $20 succeeded, processes [(38270, 'python'), (39146, 'python'), (39708, 'python')], exits [0, -9, 0]
- `hand_refund_during_outage` / sdk_interlock / rep 2: PaymentIntent `pi_3UFNsJ88KhIqqdFL03neCopv`, refunds `re_3UFNsJ88KhIqqdFL0Q0W5mRs` $20 succeeded, processes [(38400, 'python'), (39162, 'python'), (39702, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk / rep 0: PaymentIntent `pi_3UFNtW88KhIqqdFL0CEnKUTU`, refunds none, processes [(41024, 'python'), (41627, 'python'), (41752, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk / rep 1: PaymentIntent `pi_3UFNtc88KhIqqdFL0KaFwm1h`, refunds none, processes [(41350, 'python'), (41740, 'python'), (41819, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk / rep 2: PaymentIntent `pi_3UFNtc88KhIqqdFL1DAXYQIO`, refunds none, processes [(41372, 'python'), (41741, 'python'), (41818, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_sticky / rep 0: PaymentIntent `pi_3UFNuA88KhIqqdFL1EUyvp29`, refunds `re_3UFNuA88KhIqqdFL12qACDTh` $20 succeeded, processes [(41956, 'python'), (42304, 'python'), (42582, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_sticky / rep 1: PaymentIntent `pi_3UFNuI88KhIqqdFL1cS8f76R`, refunds `re_3UFNuI88KhIqqdFL1IyMjjyh` $20 succeeded, processes [(42182, 'python'), (42522, 'python'), (42914, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_sticky / rep 2: PaymentIntent `pi_3UFNuI88KhIqqdFL1i2PBdY0`, refunds `re_3UFNuI88KhIqqdFL1TfH6HqR` $20 succeeded, processes [(42183, 'python'), (42535, 'python'), (42925, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_checked / rep 0: PaymentIntent `pi_3UFNuy88KhIqqdFL0Dukes7r`, refunds none, processes [(43223, 'python'), (43583, 'python'), (43924, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_checked / rep 1: PaymentIntent `pi_3UFNv788KhIqqdFL0SyNlHaM`, refunds none, processes [(43399, 'python'), (43907, 'python'), (44147, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_checked / rep 2: PaymentIntent `pi_3UFNvA88KhIqqdFL1FE11JmS`, refunds none, processes [(43451, 'python'), (43958, 'python'), (44293, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_interlock / rep 0: PaymentIntent `pi_3UFNvk88KhIqqdFL0wRqkr40`, refunds none, processes [(44431, 'python'), (44902, 'python'), (45169, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_interlock / rep 1: PaymentIntent `pi_3UFNvq88KhIqqdFL0q0SAzGQ`, refunds none, processes [(44653, 'python'), (45129, 'python'), (45375, 'python')], exits [0, -9, 0]
- `approval_revoked_during_outage` / sdk_interlock / rep 2: PaymentIntent `pi_3UFNvt88KhIqqdFL0VWm0TuD`, refunds none, processes [(44784, 'python'), (45157, 'python'), (45470, 'python')], exits [0, -9, 0]
- race / sdk / after_commit / rep 0: PaymentIntent `pi_3UFNws88KhIqqdFL0Hk8xQua`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNws88KhIqqdFL0bZg6zZE` $20 support-bot, `re_3UFNws88KhIqqdFL0bolDS2J` $20 billing-bot
- race / sdk / after_commit / rep 1: PaymentIntent `pi_3UFNx088KhIqqdFL033BVgOj`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNx088KhIqqdFL0FVxGvwA` $20 support-bot, `re_3UFNx088KhIqqdFL0ZJccOgr` $20 billing-bot
- race / sdk / after_commit / rep 2: PaymentIntent `pi_3UFNx288KhIqqdFL1OzDXxt6`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNx288KhIqqdFL1HpCrq3b` $20 support-bot, `re_3UFNx288KhIqqdFL1Wfnh6KI` $20 billing-bot
- race / sdk / after_commit / rep 3: PaymentIntent `pi_3UFNxR88KhIqqdFL1zAfKcka`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFNxR88KhIqqdFL1fpAuKqU` $20 billing-bot, `re_3UFNxR88KhIqqdFL1FbgE8HK` $20 support-bot
- race / sdk / after_commit / rep 4: PaymentIntent `pi_3UFNxZ88KhIqqdFL1el6dwXS`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNxZ88KhIqqdFL1HESFJfy` $20 support-bot, `re_3UFNxZ88KhIqqdFL1MsEqqnx` $20 billing-bot
- race / sdk / before_send / rep 0: PaymentIntent `pi_3UFNxb88KhIqqdFL11dJ3HXw`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFNxb88KhIqqdFL1cijxAOx` $20 support-bot, `re_3UFNxb88KhIqqdFL1abblRN1` $20 billing-bot
- race / sdk / before_send / rep 1: PaymentIntent `pi_3UFNxx88KhIqqdFL10et0rQ9`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFNxx88KhIqqdFL1zDIX0hL` $20 support-bot, `re_3UFNxx88KhIqqdFL1wPuR3Mz` $20 billing-bot
- race / sdk / before_send / rep 2: PaymentIntent `pi_3UFNy588KhIqqdFL1olNyCjh`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNy588KhIqqdFL1VLciZsO` $20 billing-bot, `re_3UFNy588KhIqqdFL1IpDuqvZ` $20 support-bot
- race / sdk / before_send / rep 3: PaymentIntent `pi_3UFNy688KhIqqdFL0Rilx07F`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNy688KhIqqdFL0SFhiQth` $20 billing-bot, `re_3UFNy688KhIqqdFL0T8p4tDk` $20 support-bot
- race / sdk / before_send / rep 4: PaymentIntent `pi_3UFNyS88KhIqqdFL0n8LFQbc`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFNyS88KhIqqdFL0b2OtY3p` $20 support-bot, `re_3UFNyS88KhIqqdFL087zBSbR` $20 billing-bot
- race / sdk_lock / after_commit / rep 0: PaymentIntent `pi_3UFNya88KhIqqdFL0XLNGLnS`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNya88KhIqqdFL0HWhVt9D` $20 billing-bot
- race / sdk_lock / after_commit / rep 1: PaymentIntent `pi_3UFNyb88KhIqqdFL01LSw1dy`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 1]}, refunds `re_3UFNyb88KhIqqdFL0zWAWbtt` $20 billing-bot
- race / sdk_lock / after_commit / rep 2: PaymentIntent `pi_3UFNyx88KhIqqdFL1Rg0HJzD`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFNyx88KhIqqdFL1mqc95IF` $20 billing-bot
- race / sdk_lock / after_commit / rep 3: PaymentIntent `pi_3UFNz888KhIqqdFL0GWNuxxf`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFNz888KhIqqdFL0EdRVZ3A` $20 support-bot
- race / sdk_lock / after_commit / rep 4: PaymentIntent `pi_3UFNze88KhIqqdFL1MQc339w`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFNze88KhIqqdFL16ASTyjn` $20 support-bot
- race / sdk_lock / before_send / rep 0: PaymentIntent `pi_3UFNzn88KhIqqdFL0SRpjdcx`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFNzn88KhIqqdFL0THep3Oo` $20 billing-bot
- race / sdk_lock / before_send / rep 1: PaymentIntent `pi_3UFO0Q88KhIqqdFL16jDxMJ4`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFO0Q88KhIqqdFL1VVbFXWP` $20 billing-bot
- race / sdk_lock / before_send / rep 2: PaymentIntent `pi_3UFO0V88KhIqqdFL1Oqb4jBV`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFO0V88KhIqqdFL1jBuUFo7` $20 support-bot
- race / sdk_lock / before_send / rep 3: PaymentIntent `pi_3UFO0f88KhIqqdFL0vInYTOc`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFO0f88KhIqqdFL0NjdFBte` $20 support-bot
- race / sdk_lock / before_send / rep 4: PaymentIntent `pi_3UFO0y88KhIqqdFL0XMOrZEw`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFO0y88KhIqqdFL0z8v7jm8` $20 support-bot
- race / sdk_interlock / after_commit / rep 0: PaymentIntent `pi_3UFO1188KhIqqdFL0LluhKxH`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFO1188KhIqqdFL0PtyJrqS` $20 5934fd40187a
- race / sdk_interlock / after_commit / rep 1: PaymentIntent `pi_3UFO1E88KhIqqdFL004Bzne4`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFO1E88KhIqqdFL0KPn65tg` $20 2f47c9025748
- race / sdk_interlock / after_commit / rep 2: PaymentIntent `pi_3UFO1b88KhIqqdFL1V3wZ5EL`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFO1b88KhIqqdFL1KpwrMXl` $20 2cc66f3c01bb
- race / sdk_interlock / after_commit / rep 3: PaymentIntent `pi_3UFO2B88KhIqqdFL1sMbaTmB`, killed support-bot, exits {'support-bot': [-9, 1], 'billing-bot': [0]}, refunds `re_3UFO2B88KhIqqdFL1VA8zQE6` $20 868a00bf0d4f
- race / sdk_interlock / after_commit / rep 4: PaymentIntent `pi_3UFO2S88KhIqqdFL05gD9Gdt`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFO2S88KhIqqdFL0zzxoaus` $20 ce8616e48478
- race / sdk_interlock / before_send / rep 0: PaymentIntent `pi_3UFO2v88KhIqqdFL0qJdwyNU`, killed None, exits {'support-bot': [0], 'billing-bot': [0]}, refunds none
- race / sdk_interlock / before_send / rep 1: PaymentIntent `pi_3UFO3k88KhIqqdFL0TLF8GCv`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFO3k88KhIqqdFL0UC9zEyi` $20 6535a867c028
- race / sdk_interlock / before_send / rep 2: PaymentIntent `pi_3UFO3k88KhIqqdFL1OUgH2vZ`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFO3k88KhIqqdFL1PjtgG4K` $20 840a7e97194e
- race / sdk_interlock / before_send / rep 3: PaymentIntent `pi_3UFO3v88KhIqqdFL065vJUNl`, killed support-bot, exits {'support-bot': [-9, 0], 'billing-bot': [0]}, refunds `re_3UFO3v88KhIqqdFL0AQRMaF8` $20 83720164d304
- race / sdk_interlock / before_send / rep 4: PaymentIntent `pi_3UFO5288KhIqqdFL0XENpqKg`, killed billing-bot, exits {'support-bot': [0], 'billing-bot': [-9, 0]}, refunds `re_3UFO5288KhIqqdFL0d0BV2yW` $20 9f24bd3deb98

## Re-run

    uv run --no-project --python 3.12 --with openai-agents==0.22.2 --with litellm \
        python experiments/competitor_openai_agents.py --reps 3 --race-reps 5
