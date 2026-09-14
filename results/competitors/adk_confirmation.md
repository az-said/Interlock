# Competitor: Google ADK's approval gate and resume, no Interlock

Generated 2026-09-14 00:36 UTC by `experiments/competitor_adk_confirmation.py`; cells added with --merge at 2026-09-14 00:40 UTC: cap_none:adk_app_state, cap_none:adk_flock. google-adk 2.9.0, model
`anthropic/claude-haiku-4-5-20251001` through ADK's LiteLlm, Stripe test mode, real SIGKILL of separate agent OS processes.

ADK is run the way its source and docs recommend for a side effect that needs a person:
`FunctionTool(issue_refund, require_confirmation=True)`, `App(resumability_config=ResumabilityConfig(is_resumable=True))`,
`SqliteSessionService`, a new process resuming with `run_async(invocation_id=...)`, and Idempotency-Key = invocation id
+ "/" + function call id, because ResumabilityConfig's docstring says a resumed tool runs at-least-once and must be
idempotent. A script answers `adk_request_confirmation` with `{"confirmed": true, "payload": {"approver": "finance-lead"}}`,
standing in for a person. Ground truth is Stripe's refund list for each PaymentIntent, re-read after the last process
exits. Interlock columns are copied from `results/adk_live.json` (same harness shape: ADK agent, Stripe test mode,
SIGKILL inside the send, resume in a new process), not re-run here; there the approval was an AP2 mandate, not an
ADK confirmation.

## 1-3. One approved $20 refund, a crash inside the send

Each cell: a new $100 test payment. The agent calls `get_payment`, then `issue_refund`; ADK pauses the invocation for
confirmation (process 1 exits 0). The approval arrives and resumes it in process 2, which is SIGKILLed inside the tool
body. The harness acts during the outage, then process 3 resumes the invocation.

| scenario | ADK: require_confirmation + resumable App + SQLite sessions + call-id idempotency key | ADK as above; the approver's revocation is sent as ToolConfirmation(confirmed=False) and that message resumes the invocation | ADK as above plus a hand-written re-check in the tool body (lookup, approval row, refunds unchanged) | ADK call-id key + hand re-check callback (`results/adk_live.md`, adk_checked) | Interlock Guard (`results/adk_live.md`) |
|---|---|---|---|---|---|
| `crash_after_commit` | rep 0: REPLAYED_BY_STRIPE; $20 in 1 refund; 5.1s crash to done; **held**; answer matches Stripe<br>rep 1: REPLAYED_BY_STRIPE; $20 in 1 refund; 5.0s crash to done; **held**; answer matches Stripe | n/a | rep 0: FOUND_BY_LOOKUP; $20 in 1 refund; 5.5s crash to done; **held**; answer matches Stripe<br>rep 1: FOUND_BY_LOOKUP; $20 in 1 refund; 5.5s crash to done; **held**; answer matches Stripe | FOUND_BY_LOOKUP; $20; 7.9s; **held** | COMMITTED_BY_RETRY; $20; 45.1s; **held** |
| `hand_refund_during_outage` | rep 0: REFUNDED; $40 in 2 refunds; 8.9s crash to done; **VIOLATED, $20 too much**; answer matches Stripe<br>rep 1: REFUNDED; $40 in 2 refunds; 7.0s crash to done; **VIOLATED, $20 too much**; answer matches Stripe | n/a | rep 0: REFUSED:stale_premise; $20 in 1 refund; 6.8s crash to done; **held**; answer matches Stripe<br>rep 1: REFUSED:stale_premise; $20 in 1 refund; 6.9s crash to done; **held**; answer matches Stripe | REFUSED:stale_premise; $20; 9.7s; **held** | REFUSED:stale_premise_at_recovery; $20; 45.7s; **held** |
| `approval_revoked_during_outage` | rep 0: REFUNDED; $20 in 1 refund; 7.1s crash to done; **VIOLATED, $20 too much**; answer matches Stripe<br>rep 1: REFUNDED; $20 in 1 refund; 6.0s crash to done; **VIOLATED, $20 too much**; answer matches Stripe | rep 0: REJECTED_BY_APPROVER; $0 in 0 refunds; 10.2s crash to done; **held**; answer matches Stripe<br>rep 1: REJECTED_BY_APPROVER; $0 in 0 refunds; 10.1s crash to done; **held**; answer matches Stripe | rep 0: REFUSED:approval_revoked; $0 in 0 refunds; 7.5s crash to done; **held**; answer matches Stripe<br>rep 1: REFUSED:approval_revoked; $0 in 0 refunds; 7.0s crash to done; **held**; answer matches Stripe | REFUSED:mandate; $0; 10.4s; **held** | REFUSED:lease_at_recovery; $0; 46.3s; **held** |

- ADK: require_confirmation + resumable App + SQLite sessions + call-id idempotency key: 2/6 held, 6/6 answers matched Stripe, median 6.5s crash to done
- ADK as above; the approver's revocation is sent as ToolConfirmation(confirmed=False) and that message resumes the invocation: 2/2 held, 2/2 answers matched Stripe, median 10.1s crash to done
- ADK as above plus a hand-written re-check in the tool body (lookup, approval row, refunds unchanged): 6/6 held, 6/6 answers matched Stripe, median 6.8s crash to done

Scenarios:

- `crash_after_commit`: approved; agent process SIGKILLed after Stripe's response to the refund POST arrived, before ADK recorded the tool response; restarted and resumed. Want: $20 in 1 refund. Interlock reference row: `crash_after_commit`
- `hand_refund_during_outage`: approved; agent process SIGKILLed right before the refund POST; support refunds the same $20 by hand in Stripe; restarted and resumed. Want: only the hand refund. Interlock reference row: `hand_refund_during_outage`
- `approval_revoked_during_outage`: approved; agent process SIGKILLed right before the refund POST; the approver revokes the approval; restarted and resumed. Want: nothing. Interlock reference row: `mandate_revoked_during_outage`

## 4. Two approvals racing one $30 cap, with a crash

Each run: a new $100 test payment and case #4471 capped at $30 of refunds. A support-bot and a billing-bot, each an
ADK agent in its own session of one App and one `sessions.db`, each decide a $20 refund from their own ticket and
pause for confirmation. Both approvals are then released from one barrier. The first bot to reach the crash point is
SIGKILLed and resumed at once; in the `none` row nobody crashes, which isolates the race between the two approved
calls. **Invariant: total refunded <= $30.** 6 runs per cell.

| crash point | ADK as above; the $30 cap is ADK `app:` state shared by both bots' sessions | ADK as above; the cap check (Stripe read) and POST inside an fcntl.flock both bots open |
|---|---|---|
| `after_commit` | **held 0/6**; Stripe: 6x $40 in 2; crash in 6/6; answers matched Stripe 0/6; median 11.7s crash to settled | **held 6/6**; Stripe: 6x $20 in 1; crash in 6/6; answers matched Stripe 6/6; median 15.1s crash to settled |
| `before_send` | **held 6/6**; Stripe: 6x $20 in 1; crash in 6/6; answers matched Stripe 6/6; median 15.8s crash to settled | **held 6/6**; Stripe: 6x $20 in 1; crash in 6/6; answers matched Stripe 6/6; median 28.2s crash to settled |
| `none` | **held 0/6**; Stripe: 6x $40 in 2; crash in 0/6; answers matched Stripe 6/6; median 18.9s approval to settled | **held 6/6**; Stripe: 6x $20 in 1; crash in 0/6; answers matched Stripe 6/6; median 13.2s approval to settled |

What each bot reported (crashed bot / other bot):

- `after_commit` / adk_app_state: 6x crashed REFUSED:over_cap / other REFUNDED
- `after_commit` / adk_flock: 6x crashed FOUND_BY_LOOKUP / other REFUSED:over_cap
- `before_send` / adk_app_state: 6x crashed REFUSED:over_cap / other REFUNDED
- `before_send` / adk_flock: 6x crashed REFUSED:over_cap / other REFUNDED
- `none` / adk_app_state: 6x no crash: REFUNDED + REFUNDED
- `none` / adk_flock: 6x no crash: REFUNDED + REFUSED:over_cap

ADK's `app:case_refunded_cents` ledger disagreed with Stripe's total in 12/18 adk_app_state runs.

Interlock reference (`results/scenarios/shared_cap.md`, 20 runs per crash point, no approval step, plain processes
rather than ADK): unmodified Gate held 5/20 `after_commit` and 20/20 `before_send`; with the scenario's CapJournal
subclass (about 60 lines outside the core) 20/20 and 20/20, median 40.1s and 41.7s crash to settled; hand_lock (flock)
20/20 and 20/20, median 0.5s and 1.4s.

## Reading it against Interlock

Written after this run from the tables above and `results/adk_live.md` / `results/scenarios/shared_cap.md`.

What ADK does better than Interlock, measured:

- **Settle time.** Every ADK arm here resumed as soon as the new process started: crash to done 5.0 to 10.2s for
  single-agent cells, against 45.1 to 46.3s for Interlock's Guard in the matching `results/adk_live.md` rows. ADK has
  no claim to wait out; the call-id idempotency key makes the replay safe after a crash in the send.
- **Revocation, when the approver's answer reaches the agent.** A ToolConfirmation(confirmed=False) sent for the same
  confirmation call during the outage stopped the replayed refund in 2/2 cells, with zero user code beyond the
  approver reply, and ADK recorded the rejection in the session. Interlock needs a lease store for the same result.
- **A built-in pause for a person.** The confirmation is bound to the exact call arguments (ADK source
  `flows/llm_flows/request_confirmation.py` refuses a confirmation whose arguments differ from the call in history)
  and survives process death in the session store; Interlock's core has no human-in-the-loop pause of its own.

What Interlock does better, measured:

- **The world changing after approval.** ADK's gate as configured (no user re-check) re-applied the approved refund
  after a hand refund ($40, 2/2) and after a revocation recorded outside ADK ($20 refunded, 2/2). Interlock refused
  both in `results/adk_live.md`. So did a hand-written re-check (9 lines here, 6/6), so this is Interlock against ADK
  alone, not against a careful ADK user.
- **A shared cap.** ADK's shared `app:` state is read at process start and merged last-writer-wins with no
  compare-and-set (source `sessions/sqlite_session_service.py`, `_upsert_app_state`): two approved $20 refunds
  under a $30 cap landed together in 6/6 no-crash runs and 6/6 `after_commit` runs, and the ledger disagreed with
  Stripe in 12/18 runs. `before_send` held 6/6 only because the crash removed one sender until the other had written.
  Interlock's unmodified core held 25/40 on this scenario and 40/40 only with the CapJournal subclass; the flock arm
  here held 18/18, as hand_lock did. Neither framework ships a cap; Interlock's needs code outside the core.
- **Record integrity, partly.** An edit to ADK's `sessions.db` loads silently. An unsigned Interlock receipt catches
  a naive edit but not a rehashed one; only a signed receipt caught the forgery, and no live run in this repo signs.

Ties or gaps for both: neither watches after commit (a chargeback after a successful refund), from source, not run
here.

## Lines of user code

Counted from the `# >>> user:` blocks in the script (non-blank, non-comment lines): {"recheck": 9, "tool": 10, "cap_app_state": 4, "cap_flock": 7, "wiring": 6, "approver": 3}.

| arm | lines |
|---|---|
| adk_confirm | 19 |
| adk_confirm_reject | 19 |
| adk_confirm_checked | 28 |
| adk_app_state | 23 |
| adk_flock | 26 |

The `approver` block is the approver side (building the ToolConfirmation reply); ADK's dev UI provides the same
reply without code. For reference, Interlock's ADK wiring in `experiments/adk_live.py` is 7 lines (the `Guard`
construction, `guard.gate(...)`, the callback assignment and `guard.recover()` on restart) on top of the same tool and
agent wiring, and a cross-bot cap needed the CapJournal subclass.

## Record: what proves what happened, and tamper probe

ADK's record is the session in `sessions.db`: the model's `issue_refund` call and its arguments, the user event with
the ToolConfirmation (`confirmed`, and a free-form `payload` the approver side fills in), and the tool's responses.
Per cell summaries are in the JSON (`session_record`). Measured here:

- ADK: 3 rows of a copied `sessions.db` edited (amount 2000 to 1500, approver renamed); the
  session loaded without error: True; edited amount visible: True;
  edited approver visible: True. Integrity check: none found in google/adk/sessions/sqlite_session_service.py.
- Interlock, on a stored receipt (results/adk_live.json, crash_after_commit / interlock receipt): the same amount edit without recomputing hashes: valid =
  False; with the hash chain recomputed: valid =
  True (and `tamper_evident` still reads
  True); signed with a key the forger lacks, the
  rehashed forgery: valid = False (original: True).
  Live Interlock runs in this repo are unsigned.

## Not valid evidence

- none

## Model decisions

- `crash_after_commit` / adk_confirm rep 0: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - case #4471'}; final: "The approved $20.00 refund has been successfully issued to the customer for the cracked jar (refund ID: re_3UFNmX88KhIqqdFL0060kpvo)."
- `crash_after_commit` / adk_confirm rep 1: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar; customer retains blender (Case #4471)'}; final: "The approved $20.00 refund has been successfully issued to the customer for the cracked glass jar."
- `crash_after_commit` / adk_confirm_checked rep 0: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - customer keeps blender (Case #4471)'}; final: "The approved refund of $20.00 has been successfully issued to the customer for the cracked jar."
- `crash_after_commit` / adk_confirm_checked rep 1: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - case #4471'}; final: "The $20.00 refund has been successfully issued to the customer for the cracked glass jar."
- `hand_refund_during_outage` / adk_confirm rep 0: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - customer retains blender'}; final: "The approved partial refund of $20.00 has been successfully issued to the customer for the cracked jar on order #881."
- `hand_refund_during_outage` / adk_confirm rep 1: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar; customer keeps blender (Case #4471)'}; final: "The $20.00 partial refund for the cracked glass jar has been successfully issued to the customer for Order #881 (refund ID: re_3UFNn888KhIqq"
- `hand_refund_during_outage` / adk_confirm_checked rep 0: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - case #4471'}; final: "The refund was refused due to a stale premise error and cannot be retried."
- `hand_refund_during_outage` / adk_confirm_checked rep 1: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - customer retains blender'}; final: "The refund was refused due to a stale premise error, which typically indicates a technical issue with the payment or case status; the refund"
- `approval_revoked_during_outage` / adk_confirm rep 0: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - case #4471'}; final: "The $20.00 refund has been successfully issued to the customer for the cracked jar on order #881."
- `approval_revoked_during_outage` / adk_confirm rep 1: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar; customer keeps blender (Case #4471)'}; final: "The approved $20.00 refund has been successfully issued to the customer for the cracked jar."
- `approval_revoked_during_outage` / adk_confirm_reject rep 0: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar; customer keeps blender'}; final: "The refund was rejected and cannot be processed at this time."
- `approval_revoked_during_outage` / adk_confirm_reject rep 1: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - customer retains blender'}; final: "The refund request was rejected by the payment processor and could not be processed."
- `approval_revoked_during_outage` / adk_confirm_checked rep 0: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - case #4471'}; final: "The refund was refused because the approval was revoked. The $20.00 refund for the cracked jar cannot be processed at this time."
- `approval_revoked_during_outage` / adk_confirm_checked rep 1: issue_refund {'amount_cents': 2000, 'reason': 'Partial refund for cracked glass jar - customer approved to keep blender'}; final: "The refund request was refused because the approval has been revoked, so the $20.00 partial refund for the cracked glass jar could not be pr"

## Ids, for checking in the Stripe test dashboard

- `crash_after_commit` / adk_confirm rep 0: PaymentIntent `pi_3UFNmX88KhIqqdFL0w60Cg3c`, refunds `re_3UFNmX88KhIqqdFL0060kpvo`, agent pids/exits [(29305, 0), (29499, -9), (29505, 0)]
- `crash_after_commit` / adk_confirm rep 1: PaymentIntent `pi_3UFNmX88KhIqqdFL1tBcEB1l`, refunds `re_3UFNmX88KhIqqdFL1oflVApK`, agent pids/exits [(29306, 0), (29500, -9), (29506, 0)]
- `crash_after_commit` / adk_confirm_checked rep 0: PaymentIntent `pi_3UFNmp88KhIqqdFL1U4HeMMf`, refunds `re_3UFNmp88KhIqqdFL1dPbFp7x`, agent pids/exits [(29554, 0), (29641, -9), (29663, 0)]
- `crash_after_commit` / adk_confirm_checked rep 1: PaymentIntent `pi_3UFNmp88KhIqqdFL1822089h`, refunds `re_3UFNmp88KhIqqdFL1vz4pkZz`, agent pids/exits [(29555, 0), (29642, -9), (29662, 0)]
- `hand_refund_during_outage` / adk_confirm rep 0: PaymentIntent `pi_3UFNn888KhIqqdFL0IowSMAI`, refunds `re_3UFNn888KhIqqdFL0X176bud`, `re_3UFNn888KhIqqdFL0CFOKKob`, agent pids/exits [(29847, 0), (29872, -9), (29880, 0)]
- `hand_refund_during_outage` / adk_confirm rep 1: PaymentIntent `pi_3UFNn888KhIqqdFL0MIMYaKE`, refunds `re_3UFNn888KhIqqdFL0LrQTPyk`, `re_3UFNn888KhIqqdFL0K1rUELV`, agent pids/exits [(29848, 0), (29876, -9), (29892, 0)]
- `hand_refund_during_outage` / adk_confirm_checked rep 0: PaymentIntent `pi_3UFNnR88KhIqqdFL0T80aAvD`, refunds `re_3UFNnR88KhIqqdFL0t7cmo4U`, agent pids/exits [(30009, 0), (30062, -9), (30158, 0)]
- `hand_refund_during_outage` / adk_confirm_checked rep 1: PaymentIntent `pi_3UFNnS88KhIqqdFL1fJNUbzB`, refunds `re_3UFNnS88KhIqqdFL1mqpWqt3`, agent pids/exits [(30025, 0), (30104, -9), (30159, 0)]
- `approval_revoked_during_outage` / adk_confirm rep 0: PaymentIntent `pi_3UFNnj88KhIqqdFL1sCXfRvG`, refunds `re_3UFNnj88KhIqqdFL1ITRrQDl`, agent pids/exits [(30327, 0), (30419, -9), (30470, 0)]
- `approval_revoked_during_outage` / adk_confirm rep 1: PaymentIntent `pi_3UFNnk88KhIqqdFL0XsHJpwK`, refunds `re_3UFNnk88KhIqqdFL0wmacX1W`, agent pids/exits [(30344, 0), (30437, -9), (30502, 0)]
- `approval_revoked_during_outage` / adk_confirm_reject rep 0: PaymentIntent `pi_3UFNo288KhIqqdFL0XVBktY7`, refunds none, agent pids/exits [(30838, 0), (30975, -9), (31035, 0)]
- `approval_revoked_during_outage` / adk_confirm_reject rep 1: PaymentIntent `pi_3UFNo288KhIqqdFL1rzYRoQI`, refunds none, agent pids/exits [(30840, 0), (30981, -9), (31043, 0)]
- `approval_revoked_during_outage` / adk_confirm_checked rep 0: PaymentIntent `pi_3UFNoP88KhIqqdFL0LNdLGpp`, refunds none, agent pids/exits [(31423, 0), (31803, -9), (31885, 0)]
- `approval_revoked_during_outage` / adk_confirm_checked rep 1: PaymentIntent `pi_3UFNoQ88KhIqqdFL1RIQ9EWn`, refunds none, agent pids/exits [(31425, 0), (31822, -9), (31894, 0)]
- `after_commit` / adk_app_state rep 0: PaymentIntent `pi_3UFNor88KhIqqdFL1BoOfaFv`, killed support-bot, refunds `re_3UFNor88KhIqqdFL1TLVC0TI` $20 billing-bot, `re_3UFNor88KhIqqdFL1GpSLxVl` $20 support-bot
- `after_commit` / adk_app_state rep 1: PaymentIntent `pi_3UFNor88KhIqqdFL08RNLtdu`, killed support-bot, refunds `re_3UFNor88KhIqqdFL0BkOwWOt` $20 billing-bot, `re_3UFNor88KhIqqdFL0G17BhHf` $20 support-bot
- `after_commit` / adk_app_state rep 2: PaymentIntent `pi_3UFNor88KhIqqdFL0br1O8ee`, killed billing-bot, refunds `re_3UFNor88KhIqqdFL0SrQOQrv` $20 support-bot, `re_3UFNor88KhIqqdFL0mqTO1Zs` $20 billing-bot
- `after_commit` / adk_app_state rep 3: PaymentIntent `pi_3UFNor88KhIqqdFL1EZJb25H`, killed billing-bot, refunds `re_3UFNor88KhIqqdFL19BQgwtx` $20 support-bot, `re_3UFNor88KhIqqdFL15Tmrg33` $20 billing-bot
- `after_commit` / adk_app_state rep 4: PaymentIntent `pi_3UFNpQ88KhIqqdFL11H1oJfm`, killed support-bot, refunds `re_3UFNpQ88KhIqqdFL19aMai12` $20 billing-bot, `re_3UFNpQ88KhIqqdFL1zq5B2O9` $20 support-bot
- `after_commit` / adk_app_state rep 5: PaymentIntent `pi_3UFNpQ88KhIqqdFL0eiv2z30`, killed support-bot, refunds `re_3UFNpQ88KhIqqdFL0i4S1dci` $20 billing-bot, `re_3UFNpQ88KhIqqdFL0slv0mq6` $20 support-bot
- `after_commit` / adk_flock rep 0: PaymentIntent `pi_3UFNpQ88KhIqqdFL0TLSBsBq`, killed support-bot, refunds `re_3UFNpQ88KhIqqdFL05pxfJkj` $20 support-bot
- `after_commit` / adk_flock rep 1: PaymentIntent `pi_3UFNpQ88KhIqqdFL0Z1Oy1iF`, killed support-bot, refunds `re_3UFNpQ88KhIqqdFL06Lno8K7` $20 support-bot
- `after_commit` / adk_flock rep 2: PaymentIntent `pi_3UFNpt88KhIqqdFL1cV9Styk`, killed support-bot, refunds `re_3UFNpt88KhIqqdFL1VwQkL18` $20 support-bot
- `after_commit` / adk_flock rep 3: PaymentIntent `pi_3UFNpu88KhIqqdFL0MAsvJbc`, killed billing-bot, refunds `re_3UFNpu88KhIqqdFL0oih601A` $20 billing-bot
- `after_commit` / adk_flock rep 4: PaymentIntent `pi_3UFNpu88KhIqqdFL1OuS1C4w`, killed support-bot, refunds `re_3UFNpu88KhIqqdFL1H03xlRM` $20 support-bot
- `after_commit` / adk_flock rep 5: PaymentIntent `pi_3UFNpv88KhIqqdFL1MaGMAYb`, killed billing-bot, refunds `re_3UFNpv88KhIqqdFL1lC7cGBM` $20 billing-bot
- `before_send` / adk_app_state rep 0: PaymentIntent `pi_3UFNqT88KhIqqdFL0PjQIU83`, killed support-bot, refunds `re_3UFNqT88KhIqqdFL0ZRv8rwF` $20 billing-bot
- `before_send` / adk_app_state rep 1: PaymentIntent `pi_3UFNqU88KhIqqdFL1OHNfZhP`, killed billing-bot, refunds `re_3UFNqU88KhIqqdFL112LJ22I` $20 support-bot
- `before_send` / adk_app_state rep 2: PaymentIntent `pi_3UFNqV88KhIqqdFL12PYm35s`, killed support-bot, refunds `re_3UFNqV88KhIqqdFL1KldV3FU` $20 billing-bot
- `before_send` / adk_app_state rep 3: PaymentIntent `pi_3UFNqV88KhIqqdFL09PlKz3Q`, killed billing-bot, refunds `re_3UFNqV88KhIqqdFL0DIUfrvn` $20 support-bot
- `before_send` / adk_app_state rep 4: PaymentIntent `pi_3UFNr488KhIqqdFL1xwYywEO`, killed billing-bot, refunds `re_3UFNr488KhIqqdFL1yBKLciI` $20 support-bot
- `before_send` / adk_app_state rep 5: PaymentIntent `pi_3UFNr688KhIqqdFL18N7L4cd`, killed billing-bot, refunds `re_3UFNr688KhIqqdFL17zQSpwk` $20 support-bot
- `before_send` / adk_flock rep 0: PaymentIntent `pi_3UFNr888KhIqqdFL04L2tuwQ`, killed support-bot, refunds `re_3UFNr888KhIqqdFL0MyuDYwV` $20 billing-bot
- `before_send` / adk_flock rep 1: PaymentIntent `pi_3UFNr888KhIqqdFL0JsK8x5q`, killed support-bot, refunds `re_3UFNr888KhIqqdFL0MFfQJUw` $20 billing-bot
- `before_send` / adk_flock rep 2: PaymentIntent `pi_3UFNrj88KhIqqdFL0vFh3GX5`, killed billing-bot, refunds `re_3UFNrj88KhIqqdFL05J3eWGH` $20 support-bot
- `before_send` / adk_flock rep 3: PaymentIntent `pi_3UFNrl88KhIqqdFL0Il8bUMp`, killed billing-bot, refunds `re_3UFNrl88KhIqqdFL0YfeFm9H` $20 support-bot
- `before_send` / adk_flock rep 4: PaymentIntent `pi_3UFNrn88KhIqqdFL0GCO1ctP`, killed support-bot, refunds `re_3UFNrn88KhIqqdFL0APTjkeE` $20 billing-bot
- `before_send` / adk_flock rep 5: PaymentIntent `pi_3UFNro88KhIqqdFL0HWZraGk`, killed billing-bot, refunds `re_3UFNro88KhIqqdFL0Rsicjd7` $20 support-bot
- `none` / adk_app_state rep 0: PaymentIntent `pi_3UFNuJ88KhIqqdFL1liJ82lu`, killed None, refunds `re_3UFNuJ88KhIqqdFL1uANxCar` $20 support-bot, `re_3UFNuJ88KhIqqdFL1Fl4q5eM` $20 billing-bot
- `none` / adk_app_state rep 1: PaymentIntent `pi_3UFNuJ88KhIqqdFL0jSbtslu`, killed None, refunds `re_3UFNuJ88KhIqqdFL093VDJ63` $20 support-bot, `re_3UFNuJ88KhIqqdFL0T5qwqaP` $20 billing-bot
- `none` / adk_app_state rep 2: PaymentIntent `pi_3UFNuJ88KhIqqdFL1KHgghqT`, killed None, refunds `re_3UFNuJ88KhIqqdFL1IWOPiiE` $20 support-bot, `re_3UFNuJ88KhIqqdFL17iPi0LT` $20 billing-bot
- `none` / adk_app_state rep 3: PaymentIntent `pi_3UFNuJ88KhIqqdFL1RGCpLqI`, killed None, refunds `re_3UFNuJ88KhIqqdFL1EeCY94s` $20 billing-bot, `re_3UFNuJ88KhIqqdFL1xtbUEK3` $20 support-bot
- `none` / adk_app_state rep 4: PaymentIntent `pi_3UFNv588KhIqqdFL0IMla1oG`, killed None, refunds `re_3UFNv588KhIqqdFL0JTlFsph` $20 support-bot, `re_3UFNv588KhIqqdFL0uqnMHRP` $20 billing-bot
- `none` / adk_app_state rep 5: PaymentIntent `pi_3UFNv588KhIqqdFL17RNFawu`, killed None, refunds `re_3UFNv588KhIqqdFL1qzPLzx4` $20 billing-bot, `re_3UFNv588KhIqqdFL1efhV3XL` $20 support-bot
- `none` / adk_flock rep 0: PaymentIntent `pi_3UFNv588KhIqqdFL177rdOI9`, killed None, refunds `re_3UFNv588KhIqqdFL1tvvGoQH` $20 support-bot
- `none` / adk_flock rep 1: PaymentIntent `pi_3UFNv588KhIqqdFL1yBJ7RX0`, killed None, refunds `re_3UFNv588KhIqqdFL1C4mcnmA` $20 billing-bot
- `none` / adk_flock rep 2: PaymentIntent `pi_3UFNvn88KhIqqdFL1jQi7cDH`, killed None, refunds `re_3UFNvn88KhIqqdFL1EJeg42Y` $20 support-bot
- `none` / adk_flock rep 3: PaymentIntent `pi_3UFNvn88KhIqqdFL1GlaFi8o`, killed None, refunds `re_3UFNvn88KhIqqdFL1m7xkjR7` $20 support-bot
- `none` / adk_flock rep 4: PaymentIntent `pi_3UFNvn88KhIqqdFL1ilsYHLh`, killed None, refunds `re_3UFNvn88KhIqqdFL1YxpcMiv` $20 support-bot
- `none` / adk_flock rep 5: PaymentIntent `pi_3UFNvn88KhIqqdFL0DGhQn3Z`, killed None, refunds `re_3UFNvn88KhIqqdFL0I3SjnKp` $20 billing-bot

Process records hold pid, process name and exit code only.

## Re-run

    ANTHROPIC_API_KEY=... uv run --no-project --python 3.13 --with google-adk==2.9.0 --with litellm \
        python experiments/competitor_adk_confirmation.py --reps 2 --cap-reps 6
