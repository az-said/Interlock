# 11. Weakness audit: where Interlock loses, ties, needs scenario code, or overclaims

Status: 2026-09-13. Sources read in full: `kiro-research.md`, `README.md`, `interlock/gate.py`, `journal.py`,
`receipts.py`, `easy.py`, `docs/10-scenarios.md`, every `results/scenarios/*.md`, `results/e2e_live.md`,
`results/adk_live.md`, `docs/08-pitch.md`, and the escalation build in `~/Downloads/Interlock-build` (read only).
Code citations are `file:line` in `~/Downloads/Interlock` unless marked **build**. `gate.py`, `journal.py` and
`docs/10-scenarios.md` are identical in this worktree (HEAD `f6ed9ee`); `easy.py` here already has `approval=`,
so `easy.py` line numbers below are from `~/Downloads/Interlock`.

Every statement is tagged as one of:

- **measured**: copied from a results file, with its number;
- **read from code**: follows from the cited lines, not run;
- **predicted**: what a change should do, not yet run against a live service.

The honesty rule holds throughout: a fair hand-written check ties Interlock on outcomes in every live row so far.
Nothing below claims a win that is not measured.

---

## 1. The scoreboard in one table

| where | Interlock vs strongest fair hand check | number | source |
|---|---|---|---|
| e2e refund, Temporal | tie on money and answers, **loses on time** | 6/7 vs 6/7 wanted, 7/7 same refunds; median 43s vs 15s | `results/e2e_live.md:28-32` |
| ADK + AP2 | tie on money, **loses on time** | 5/5 vs 5/5; median 46s vs 10s | `results/adk_live.md:28-29` |
| stripe_dispute | tie, **loses on time**; nobody catches a later chargeback | 2/2 vs 2/2; 42.4, 43.0s vs 6.4, 11.2s; gap probe out $120 on $100 | `results/scenarios/stripe_dispute.md:17-19, 30-34` |
| shared_cap | core **loses on money**; with scenario subclass ties hand_lock, **loses on time** | core 25/40, CapJournal 40/40, hand_lock 40/40; 40.1/41.7s vs 0.5/1.4s | `results/scenarios/shared_cap.md:29-33` |
| billing_credit | tie, **loses on time** | 6/6 vs 6/6; median 41s vs 17s | `results/scenarios/billing_credit.md:14-16` |
| github_merge | tie, **loses on time** | 6/6 vs 6/6; median 26.1/24.4s vs 7.7/2.5s | `results/scenarios/github_merge.md:24-25` |
| calendar | `easy.py` as shipped **loses on money**; with a scenario override ties, **loses on time** | change_only 0/1 (double booked) vs hand_check 7/7; override 7/7; 31.2s vs 0.6s | `results/scenarios/calendar.md:31-34` |
| email_tier3 | tie with probe; on documented features **scores lower on answers**; **loses on time** | interlock_noprobe answers 1/3 vs hand_check_noprobe 2/3; 36s vs 2s | `results/scenarios/email_tier3.md:44-49` |
| gcp_resource | tie, **loses on time** | 3/3 vs 3/3; 30.6 to 30.9s vs 0.5 to 2.1s | `results/scenarios/gcp_resource.md:11-13` |
| connect_payout | no verdict | BLOCKED | `results/scenarios/connect_payout.md` |
| record ("proof") | **Interlock ahead** where the hand check keeps no structured record; tie where it logs | calendar 7/7 vs 0/7; shared_cap 40/40 vs 0/40; billing 6/6 vs 6/6 | per-scenario md |

Where Interlock is ahead on outcome in any live row: **nowhere**. Its only measured lead is the record, and that
lead shrinks to structure alone once the hand check keeps a log and both are sealed by an outside key holder
(`results/scenarios/github_merge.md:64-78`).

---

## 2. Losses (measured), root cause, smallest core change

### L1. Recovery latency after a SIGKILL, in every live run

- **Numbers.** e2e median 43s vs 15s hand check (`results/e2e_live.md:28-30`); ADK 46s vs 10s
  (`results/adk_live.md:28-29`); scenarios 25 to 43s vs 0.4 to 17s (section 1 table).
- **Side cost, measured.** Temporal ran 8 activity attempts per Interlock cell against 2 for the other columns,
  because each attempt before claim expiry returned `IN_FLIGHT` (`results/e2e_live.md:17-24`;
  `backend/config.py:17` sizes `REFUND_ATTEMPTS = 3 * CLAIM_TTL // 5` just to outlast the claim).
- **Evidence the wait is the TTL and nothing else.** With a 15s TTL the demo measured Interlock 16.3s against
  16.7s for plain Temporal (`docs/08-pitch.md:222-223`).
- **Root cause.** A claim only expires by time. `journal.py:222-231` (`Journal.claim`) and `journal.py:302-310`
  (`SqliteJournal.claim`) grant a claim only when `expires < now`; `gate.py:211-212` then skips the effect. The
  owner string already names the process, `f"{hostname}:{pid}:{uuid}"` (`gate.py:66`), but nothing reads it.
- **Smallest change.** In both `claim()` methods, treat a held claim as released when its owner is on this host
  and `os.kill(pid, 0)` raises `ProcessLookupError`. About 8 lines per backend, stdlib only. A live or remote owner
  keeps today's TTL rule, so the change never takes over earlier from a sender that might still be sending.
- **Measured, locally.** `experiments/competitor_claim_liveness.py` subclasses both journals with exactly that
  check. It uses a local tier-1 file target and a real SIGKILL of a separate sender process, with TTL 10s and one
  trial per cell (`results/competitors/claim_liveness.txt`):

  | journal | crash point | core TTL: crash to recovered | with liveness | effects at target | live sender taken over |
  |---|---|---|---|---|---|
  | JSONL | after_commit | 10.03s | 0.01s | 1 / 1 | |
  | JSONL | before_send | 10.04s | 0.00s | 1 / 1 | |
  | JSONL | slow (alive 3s) | | | | no / no |
  | SQLite | after_commit | 10.08s | 0.01s | 1 / 1 | |
  | SQLite | before_send | 10.00s | 0.01s | 1 / 1 | |
  | SQLite | slow (alive 3s) | | | | no / no |

- **Predicted, not run live.** Interlock settle time drops to the hand check's in every same-host scenario.
  Money is unchanged, so the result would be a tie on time, not a win.
- **Limits.**
  - Remote owners still wait the TTL. The SQLite journal is one host anyway (`docs/08-pitch.md:209-212`).
  - A sender that is alive but hung still waits the TTL, as today.
  - Containers that share a hostname but not a pid namespace would read a live sender as dead. The robust form of
    the same idea is a per-effect `fcntl.flock` held for the length of `apply` and probed with `LOCK_NB`; the
    kernel drops it on death, which is hand_lock's measured 0.5s mechanism (`shared_cap.md:47`). That form is not
    measured here.
- **To measure the tie live.** Re-run `experiments/e2e_live.py` and the scenario workers with the liveness journal.

### L2. shared_cap: the core alone let two agents exceed one cap

- **Number.** interlock_core held 25/40 (5/20 `after_commit`) against hand_lock 40/40 (`shared_cap.md:31-32`).
- **Root cause.** `journal.py:124-136` (`dispatch_blocker`) looks only at the entries of the effect being
  dispatched, so two effect ids never see each other. `gate.py:147-148` maps any unknown blocker to `IN_FLIGHT`,
  which is why `CapGate.submit` had to translate it back (`scenarios/shared_cap/cap.py:83-87`).
- **Missed detail.** The core has since gained `leases.reserve()` (`gate.py:135-140`, commit `53df68a` at 19:34
  EDT). The shared_cap run was generated at 23:06 UTC, which is 19:06 EDT, before that hook existed. The hook still
  does not close the gap:
  1. it runs before `journal.dispatch`, outside the dispatch lock;
  2. it is never released when the effect is refused at recovery (`docs/08-pitch.md:237-238` says so for the AP2
     store);
  3. it leaks if `dispatch` then returns a blocker.
- **Smallest change.** Give `dispatch` an optional `check(all_entries, effect)` evaluated inside the same lock or
  `BEGIN IMMEDIATE`, and return `REFUSED:<code>` for its blocker. The build's `append_if` (**build**
  `journal.py:207-215`, `308-323`) is already this shape, per effect. About 15 lines; `CapJournal`
  (`cap.py:50-75`, 25 lines) is the measured proof of the mechanism.
- **What it wins.** 25/40 becomes 40/40, which is measured with CapJournal. Against hand_lock that is a tie on
  money and a lead on record (40/40 vs 0/40). Time is still a loss unless L1 lands too.
- **Ceiling.** The check reads the whole journal per dispatch. It never sees refunds made outside the journal
  (`shared_cap.md:117-119`).

### L3. calendar: `easy.py` as shipped double booked

- **Number.** interlock_change_only 0/1, `before_send/pre_busy`, double booked, where hand_check and no_check both
  refused (`calendar.md:29, 34, 39`).
- **Root cause.** `easy.py:50-53`: a premise can only fail by changing. A fact that was already wrong at decision
  time passes every check.
- **Smallest change.** `gate.effect(..., expect={"other_events_in_slot": []})`, enforced in `validate_premises`
  at submit and at recovery, alongside "unchanged". About 4 lines. It replaces the 21-line `_gate_target` override
  (`scenarios/calendar/booking.py:196-220`).
- **What it wins.** It removes a loss. Against hand_check the result is a tie on money and a lead on record
  (7/7 vs 0/7), which is measured with the override.

### L4. email_tier3: on documented Resend features, fewer correct answers than the idiomatic check

- **Number.** interlock_noprobe answers matched 1/3 vs hand_check_noprobe 2/3 (`email_tier3.md:46-48`).
  Interlock said AMBIGUOUS in both refused rows. The hand check said "not sent" twice and was wrong once
  (`refused_after_send`).
- **Root cause.** `gate.py:241-243`: stale at recovery with no lookup gives AMBIGUOUS, because DISPATCHED is
  written before the send and a `before_send` crash looks the same as an `after_send` crash.
- **Smallest change.** None that is honest. A second marker written just before the socket write narrows the
  window but cannot remove it. This row is the Two Generals cost, and it should be reported as a cost, not a loss
  to fix.
- **What could be a real, runnable win.**
  - Past Resend's 24h key window, the hand check would send a second email while `KeyWindowGate` says AMBIGUOUS
    (`email_tier3.md:78-81`, read from code).
  - That is runnable without emulation by waiting 25h before the restart.
  - It is also the only row where the hand check's own logic, not a missing line, predicts a duplicate.

### L5. Tier 3 availability

- **Numbers.**
  - Simulated: gate at tier 3 left $0 AMBIGUOUS on `crash_before_send` where every other system paid the $20
    (`README.md:122`).
  - Live: interlock_tier3 answers matched 0/3 (`email_tier3.md:49`).
- **Root cause.** `gate.py:233-235`, by design.
- **Change.** None proposed; this is the stated guarantee. It should stay out of any "wins" claim.

---

## 3. Ties: what made each a tie, and whether a win is reachable

| tie | why the hand check tied | reachable measured win? |
|---|---|---|
| e2e 7/7 (`e2e_live.md:32-37`) | 10-line re-check plus lookup by workflow id (`backend/workflows.py:71-80`) | time only, via L1. Money: no |
| `unrelated_refund_during_outage`, both SHORT $20 (`e2e_live.md:20`) | both compare "refunds unchanged" | **no, mechanically.** A $5 goodwill refund and a $20 hand duplicate differ only in intent. The build's `still_fits` repair (**build** `targets/payments.py:18-26`) hands the choice to rules or a person; unmeasured against a hand check |
| stripe_dispute (`stripe_dispute.md:23-41`) | Stripe's own guards | no on money. A refund that later failed (`answer vs final money` 1/2 for every column) needs a post-commit read: change 6 |
| $120 loss, chargeback 300s after a succeeded refund (`stripe_dispute.md:30-34, 108`) | no column catches it | not by any premise. A post-commit watch on `charge.dispute.created` could flag it; the build's `confirm.py:24` does not subscribe to dispute events |
| billing_credit 6/6 | incident-scoped premise in both columns | time only |
| github_merge 6/6 | GitHub `sha` precondition; the head re-read alone passed a lagging read 3/3 (`github_merge.md:89-93`) | time only |
| gcp_resource 3/3 | `ifGenerationMatch` plus a version lookup, about 10 lines (`gcp_resource.md:21-25`) | time only |
| ADK 5/5 | 13-line `precheck` (`experiments/adk_live.py:143`) | time only |

---

## 4. Code that lived outside the core to reach a tie

| scenario | override | lines (non-blank) | what it papers over | core change that removes it |
|---|---|---|---|---|
| shared_cap | `CapJournal`, `CapGate` (`cap.py:50-87`) | 25 + 9 | cross-effect cap; unknown blocker reads as IN_FLIGHT | 1 |
| calendar | `_gate_target` (`booking.py:196-220`) | 21 | premise must equal a value; easy drops return values | 3, 4 |
| email_tier3 | `KeyWindowGate` (`email_tier3/systems.py:118-131`) | 14 | stop trusting a lookup past the dedup window | small: `gate.py:231-232` should also clear `queryable` when the target declares `lookup_window` |
| stripe_dispute | `refund.gate.target.query = ...` (`stripe_dispute/worker.py:150`) | 1 | `easy.py:62` reduces a lookup to `bool` | 4 |
| every worker | recover-then-submit polling loops (`stripe_dispute/worker.py:159-165`, `connect_payout/worker.py:83-88`, `github_merge/agent.py:142-151`) | 7 to 10 each | recovery silently skips a live claim | 2, then 7 |
| backend e2e | `EmulatedClockGate` (`backend/workflows.py:45-51`) | 7 | emulation only; legitimate | none |

---

## 5. Overclaims and stale statements

| where | claim | what the evidence says | fix |
|---|---|---|---|
| `README.md:5` | "it happened exactly once" | `happened_once` is per effect id and does not see hand refunds or other ids (`receipts.py:9-11`); exactly once holds only at tiers 1 and 2 | "at most once per approved request, and exactly once where the service dedupes or can be looked up" |
| `README.md:26` | "describing a thing that did not exist. Now it does." | softened after ATR, Cordon and Commit Gates (`kiro-research.md:618`) | delete the sentence |
| `README.md:30` | "cut two thirds of the manual approvals" | the cut from 100 to 25 is rules; Interlock **adds** 8 reviews, 25 to 33, while wrong refunds go 8 to 0, on an assumed mix (`results/approval_inbox.md:9-10`) | say Interlock trades 8 extra reviews for 8 fewer wrong refunds, synthetic mix |
| `README.md:34` | "about 400 lines of Python" | gate 355 + journal 341 + receipts 147 = 843; with easy 952; the build's gate, journal, receipts, escalation and confirm total 1,270 | state the real count |
| `README.md:22, 306` | "53 tests" | 223 `def test_` in `tests/` today, 264 in the build | understated; update |
| `README.md:257` and `receipts.py:116` | `"tamper_evident": true` | unsigned chains accepted 6/6 forged final entries (`github_merge.md:70-74`) | change 5 |
| `README.md:194-206` | "Why this and not the obvious things" has no "write the check yourself" | ties in every live row (`e2e_live.md:32`, `docs/10-scenarios.md:103-110`) | add the row; the pitch already drafted it (`docs/08-pitch.md:320-326`) |
| `README.md:312` | "Not built yet. A real GitHub target." | `scenarios/github_merge/github.py` exists and ran live | update |
| `docs/08-pitch.md:101` | Platform Engineering gets "`valid` and `tamper_evident` on every chain" | same as change 5 | reword to chain consistency |
| `docs/08-pitch.md:151-153` | the case is "no per-tool code" | section 7: in the scenario suite the Interlock arm is as long or longer than the hand check; only the Temporal backend was shorter | say "one recovery path", not "no code" |
| `docs/08-pitch.md:54` | runtime "has no results file" | `results/runtime_live_agent.md` exists (`kiro-research.md:125`) | update |
| `results/scenarios/stripe_dispute.md:14-19`, `docs/10-scenarios.md:65-66, 75-76` | Interlock "tamper-evident yes" or "better on tamper evidence", unsigned | the probe altered one entry without recomputing hashes; a recomputed chain passes (`github_merge.md:70-74`) | "chain-consistent", or score as tied until sealed |
| `kiro-research.md:483, 665` | `results/export_live.md` "was never written"; BigQuery "failed live" | the file exists; the pitch cites a later successful BigQuery run (`docs/08-pitch.md:123`) | refresh the research file |
| **build** `results/repair_loop.md` | interlock+repair: 97 no person, 0 wrong | scripted agent, assumed mix, no hand-check arm | do not cite as a win against a careful engineer |
| **build** `receipts.py:26-28` | `approval_verified` | "whoever controls the journal can strip the escalations off a chain and make it look legacy" | unsigned `approval_verified` is an attestation only |

---

## 6. The eight proposed core changes, judged

Zero-dependency and existing semantics were checked for each.

| # | change | verdict | size | semantics risk | what it turns into | status |
|---|---|---|---|---|---|---|
| 2 | claim liveness | **adopt first** | ~8 lines per journal | none for live or remote owners; container caveat in L1 | time loss becomes a tie in every same-host scenario; removes wasted Temporal attempts | measured locally (L1 table); live predicted |
| 1 | cap reservation at dispatch | **adopt, reshaped** | ~15 lines | additive; unknown blocker becomes `REFUSED:<code>` instead of `IN_FLIGHT`, a visible change for callers that treat any blocker as in flight | core 25/40 becomes 40/40, the tie with hand_lock plus record | measured via CapJournal |
| 3 | premises with expected values | **adopt** | ~4 lines in `easy.py` | additive | calendar loss becomes a tie; removes a 21-line override | measured via override |
| 4 | keep target return values | **adopt** | 2 lines (`easy.py:59, 62`) | receipt `evidence` changes from `true` to the value; `if found` truthiness unchanged (`gate.py:245`); a lookup returning a falsy real value (id `0`) must be documented. The build did not fix it (**build** `easy.py:64`) | receipts carry the refund or event id without overrides | read from code |
| 5 | do not overclaim tamper evidence | **adopt** | 2 lines (`receipts.py:116`) | renames a field the demo and exporters read; keep the old key one release | removes an overclaim; not a win | measured need (6/6 forgeries) |
| 6 | post-commit settlement entries | **adopt partially** | port the build's lookup path (**build** `confirm.py:77-85`) without the Stripe coupling: `gate.settle(eid)` re-queries and appends an evidence-only entry | evidence only, never control flow, as the build already enforces | answers that match final money (1/2 today for every column); the hand check can add the same webhook, so it is packaging | the build ran once live (`kiro-research.md:526`), no result file in either checkout |
| 7 | surface blocked recovery | **adopt as opt-in, after 2** | ~10 lines | changing `recover()`'s return dict would break `connect_payout/worker.py:84-86`, which treats any non-`IN_FLIGHT` value as final; use `recover(wait=True)` or a separate `claimed()` query | fewer polling loops; mostly moot once 2 lands | read from code |
| 8 | write bundles at `recover()` | **defer** | 3 lines in `easy.py` | none | harness convenience, no outcome | no need measured |

---

## 7. Weaknesses not in the eight

1. **48-bit effect ids.** `journal.py:341` keeps 12 hex chars.
   - The birthday bound is about 0.18% collision odds at 1M effects in one journal or idempotency-key namespace,
     and about 50% near 20M.
   - A collision refuses a real refund as `conflicting_payload`, or sends Stripe a key it already used for
     another body.
   - Fix: 32 hex for new journals only. Changing the id of an in-flight effect across an upgrade would let a
     resubmit dispatch it again. Read from code.
2. **Every append reads the whole JSONL file.** `journal.py:177-186` calls `_drop_torn_tail` (reads the file) and
   `entries(effect_id)` (reads the file); `in_flight()` reads it again. Cost grows with journal age. No run
   measured throughput.
3. **Renaming a decorated function orphans its in-flight effects.** `easy.py:82-86` names the journal after
   `module.qualname`, so after a rename `recover()` never opens the old file. Read from code.
4. **`easy` passes the call's arguments as the lease** (`easy.py:93`), so receipts show arguments where an
   approval should be. `approval=` in this worktree fixes that for approvals only.
5. **Signing does not stop the writer.** `receipts.py:37-40` is an HMAC with a key the gate holds when it signs.
   Tamper evidence against the operator needs a key held elsewhere (the harness seal in `github_merge.md:64-68`)
   or a witness. **Unmeasured idea:** put the DISPATCHED entry's hash in the request metadata the target stores
   (Stripe refund metadata already carries `interlock_effect_id`), so the service holds a copy of the chain that
   the journal writer cannot rewrite afterwards. Zero dependencies.
6. **The escalation build weakens two invariants by design.**
   - I7 is not enforced on a journal override that calls `dispatch_blocker` with two arguments, which is exactly
     CapJournal (**build** `journal.py:128-136`).
   - `easy(approval=)` gives each distinct argument set its own effect id (**build** `easy.py`, `request_id`), so
     a model re-deciding $30 becomes a new attempt bounded by the Envelope, instead of the I5
     `conflicting_payload` refusal the README table measures (`README.md:125`).
7. **The build's confirmation is Stripe-shaped and test-only.** It refuses live-mode events (**build**
   `confirm.py:19`), reads only the first 100 refunds (`confirm.py:79`) and ignores dispute events (`confirm.py:24`).
8. **Core size growth in the build.** gate 355 to 399, journal 341 to 385, receipts 147 to 246, plus escalation
   127 and confirm 113; approvals 124 to 509. That is still zero-dependency, but further from the "small gate"
   pitch.

---

## 8. Developer experience against a hand-written check

### Lines to adopt, from the code that produced the results

Counts are non-blank, non-comment lines of each arm's functions (Python AST spans). They include each arm's own
logging, receipt writing and polling, and exclude shared target adapters unless named. They are approximate but
from the same code on both sides.

| scenario | hand check | Interlock arm | notes |
|---|---|---|---|
| e2e (Temporal) | 10 (`backend/workflows.py:71-80`) | 5 (`workflows.py:87-91`) plus `temporal.gated()` | the one place Interlock is shorter |
| ADK + AP2 | 13 (`experiments/adk_live.py:143`) | Guard setup, not counted | |
| stripe_dispute | 31 (`hand_check` 14, `hand_check_decision` 11, `log` 6) | 27 (`interlock_refund` 10, `interlock` 17 with polling) | about equal |
| billing_credit | 17 (`worker.py:74`) | `CreditTarget` in `billing.py`, not counted | |
| github_merge | 17 (`agent.py:93`) | 29 + `ReviewApproval` 13 + `github.py` 118 | longer |
| calendar | 13 (`booking.py:176`) | 35 + `_gate_target` 21 | longer |
| email_tier3 | 24 (`systems.py:57`) | 21 + `KeyWindowGate` 14 + target | longer |
| gcp_resource | 14 (`systems.py:58`) | 30 + `GcsObjectTarget` | longer |
| shared_cap | 14 + flock about 5 | `CapJournal` 25 + `CapGate` 9 + `CapRefunds` 23 | longer |
| connect_payout (offline) | 16 | 22 | longer |

**Reading.** "No per-tool code" is not supported by what was built. What drives the length:

- the target adapter (an `EffectTarget` is a class, not a function);
- a recovery polling loop, because a dead claim blocks (L1);
- overrides for missing `expect=` and return values (changes 3 and 4).

Changes 2, 3 and 4 delete most of that. The MCP proxy is the one zero-line path, and it has no live-server result
(`docs/08-pitch.md:43`).

### Error messages

- **Jargon.** `REFUSED:lease`, "lease not live, or it does not cover this effect" (`gate.py:126`). The ADK model
  read `stale_premise_at_recovery` as "a business logic issue" and `lease at recovery` as "a sp..."
  (`results/adk_live.md:107, 110`). `adk.py:111` now appends "Not a technical error. Do not retry", and the build
  maps every code to a plain sentence (**build** `escalation.py:16-35`). Main's `gate.py` and `easy.py` still
  return bare codes.
- **`IN_FLIGHT` does not say what to do.** It gives no expiry and no "call `recover()`" (`gate.py:91-92`), so
  every worker grew a sleep loop (section 4).
- **Status strings.** `easy` returns `(status_string, result)` (`easy.py:98-101`), so callers string-match
  `startswith("REFUSED")`. Hand-written checks return whatever the author chose.
- **Silent failure when `recover()` is forgotten.** If `recover()` is never called on startup, every later call
  returns `IN_FLIGHT` forever. A hand check has no such state.

### Docs

- There is no "when a hand-written check is enough" section. A reader cannot tell from the README that a ten-line
  check ties on outcomes.
- Premise design is the hard part, and it is only shown in scenario code. billing_credit's candidate table (three
  premises, one wrong on `unrelated_credit`, `billing_credit.md:59-70`) is the best guide in the repo, and it is
  not linked from the README.
- The TTL rule ("targets must time out well inside `claim_ttl`", `gate.py:41-43`) has no helper. Each integration
  re-derives it (`backend/config.py:15-16`).
- The 24h dedup margin is hard-coded (`gate.py:48`) and not documented per target.

### Operations a hand check does not need

- A journal file per function, and a claims sidecar.
- Choosing a TTL.
- Knowing that SQLite coordinates one host only (`docs/08-pitch.md:209-212`).

---

## 9. Order of work, and the measured result each should produce

| order | change | files | run that decides it | honest expected claim |
|---|---|---|---|---|
| 1 | claim liveness (2) | `journal.py` claim x2 | e2e_live, adk_live, the 7 scenarios with the liveness journal | "recovers as fast as the hand check" (tie), if the live medians match |
| 2 | expect= and return values (3, 4) | `easy.py` | calendar `pre_busy` with `easy.py` unmodified; stripe_dispute receipt evidence | "`easy.py` as shipped no longer double books" |
| 3 | dispatch check hook (1) | `journal.py`, `gate.py:147-148` | shared_cap with core only | "the core holds a shared cap 40/40 and records who held it" (tie on money with hand_lock, lead on record) |
| 4 | chain_consistent (5) | `receipts.py:116` | existing forgery test | removes an overclaim |
| 5 | evidence-only settlement (6) | port from build `confirm.py` | stripe_dispute `crash_after_send`: does the receipt's final status match Stripe's `failed`? | "the receipt reflects the final money state" (the hand check can add the same read) |
| 6 | the one row the hand check's logic loses | none | email_tier3 with a real 25h wait before restart | if measured: "after the key window Interlock says AMBIGUOUS where the idiomatic check sent a second email" |

Until those runs exist, the defensible claim is the one `docs/10-scenarios.md:103-110` makes:

- tied on every service outcome;
- slower after a crash;
- ahead only on a structured record, which is tamper-evident only when sealed by someone other than the writer.
