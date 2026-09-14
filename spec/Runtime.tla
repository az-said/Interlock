------------------------------ MODULE Runtime ------------------------------
(***************************************************************************)
(* interlock_runtime claims, step journal, gated effect, recovery by tier   *)
(* (docs/07-runtime.md sections 5 and 10), and the two Temporal baselines.  *)
(*                                                                         *)
(* One workflow: a plain step, then one gated refund effect (payload 20),   *)
(* then completion. Two workers. World events: revoke, a full or partial    *)
(* hand refund, cancel, key pruning (tier 1) and a re-decision to 30.       *)
(*                                                                         *)
(* MODE "interlock"         the runtime as specified, plus the fixes found  *)
(*                          by this model (spec/COUNTEREXAMPLES.md).        *)
(* MODE "temporal_idem"     Temporal activity, key = run id + activity id.  *)
(* MODE "temporal_precheck" the same activity with the pre-send check of    *)
(*                          docs/07-runtime.md 11.1 (b), key = workflow id. *)
(*                                                                         *)
(* Modeling choices (each is stated again next to the action):             *)
(*  - Postgres now() is the transaction start time. T_dispatch is two       *)
(*    steps (begin takes the fence and row lock, commit does the checks),   *)
(*    so a slow commit is visible. Other transactions are atomic.           *)
(*  - A crash and the restart of that worker are one step (local state      *)
(*    lost). A down worker is an idle worker that does not act.             *)
(*  - The target processes a request at most SettleMargin ticks after it    *)
(*    leaves (A2), or at any time up to MaxClock under SERVER_SLOW.         *)
(*  - The response reaches the sender when processed, if the sender still   *)
(*    waits for it; a lost response is a sender that never acts on it.      *)
(*  - Temporal: the plain step is not modeled (pre-completed), attempts are *)
(*    retried only after the start-to-close timeout, and an attempt sends   *)
(*    only before its own timeout unless paused (the baseline's best case). *)
(*                                                                         *)
(* A model check for the stated constants, not a proof of the Python or SQL.*)
(***************************************************************************)
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
  Workers, None,
  Tier, Queryable, MODE, BROKEN,
  PAUSE, SERVER_SLOW, URGENT,
  Events,
  MaxClock, LeaseTTL, SendTimeout, SettleMargin, DedupAge, MaxCrashes

ASSUME MODE \in {"interlock", "temporal_idem", "temporal_precheck"}
ASSUME Tier \in {1, 2, 3} /\ (Tier = 2 => Queryable) /\ (Tier = 3 => ~Queryable)
ASSUME BROKEN \in {"none", "naive_recovery", "no_fencing", "grant_check_outside_txn",
                   "commit_without_checkpoint", "recover_before_deadline",
                   "stopwatch_after_dispatch", "late_ack_dropped",
                   "no_local_lease_check", "thin_dedup_margin"}

Interlock == MODE = "interlock"
Terminal  == {"completed", "cancelled", "failed"}
Approved  == 20

VARIABLES
  now,      \* database clock
  wf,       \* ilr.workflows row plus its step rows
  eff,      \* ilr.effects row plus journal counters
  world,    \* grant, premise world, target ledger and dedup store
  lw,       \* per-worker local (lost on crash)
  paused,   \* per-worker SIGSTOP
  wire,     \* requests sent and not yet processed
  sendLog,  \* every request put on the wire, with what was true when it was authorized
  hist,     \* history flags and counters for invariants
  tmp       \* Temporal server state for the refund activity

vars == <<now, wf, eff, world, lw, paused, wire, sendLog, hist, tmp>>

Sym == Permutations(Workers)

NoAuth == [liveClaim |-> FALSE, grantOk |-> FALSE, premiseOk |-> FALSE, resend |-> FALSE,
           recheckOk |-> FALSE, authAfterRevoke |-> FALSE, afterCancel |-> FALSE, pastWindow |-> FALSE]

L0 == [pc |-> "idle", epoch |-> 0, lease |-> 0, deadline |-> 0, txnStart |-> 0, fenceOk |-> FALSE,
       readOk |-> FALSE, readGrant |-> FALSE, seenW |-> None, seenE |-> 0, recPrem |-> FALSE,
       found |-> FALSE, auth |-> NoAuth, lateSend |-> FALSE, sentId |-> 0, ackOk |-> FALSE, run |-> 0]

Init ==
  /\ now = 0
  /\ wf = [status |-> IF Interlock THEN "pending" ELSE "running", avail |-> 0, epoch |-> 0,
           owner |-> None, lease |-> 0, lock |-> None, cancelAt |-> -1,
           stepPlain |-> ~Interlock, stepEffect |-> FALSE]
  /\ eff = [state |-> "none", bound |-> 0, dispW |-> None, dispE |-> 0, first |-> -1, deadline |-> 0,
            nDisp |-> 0, nCommit |-> 0, nRes |-> 0, ambig |-> "none", late |-> 0, acksAfterRes |-> 0]
  /\ world = [revoked |-> FALSE, revokeReturned |-> FALSE, offer |-> Approved, hand |-> 0, done |-> {},
              pruned |-> FALSE, keyStore |-> {}, appliedKeys |-> {}, ourApps |-> 0, landedUnlisted |-> FALSE]
  /\ lw = [w \in Workers |-> L0]
  /\ paused = [w \in Workers |-> FALSE]
  /\ wire = {}
  /\ sendLog = <<>>
  /\ hist = [plainAfter |-> 0, effRows |-> 0, unfenced |-> FALSE, earlyTakeover |-> FALSE,
             crashes |-> 0, pauses |-> 0]
  /\ tmp = [act |-> "scheduled", w |-> None, start |-> 0, attempt |-> 0, run |-> 1]

\* ---------------------------------------------------------------- helpers
RealFence(w) == lw[w].epoch = wf.epoch /\ wf.owner = w /\ wf.status = "running" /\ wf.lease > now
Fence(w)     == RealFence(w) \/ BROKEN = "no_fencing"
Mine(w)      == eff.dispW = w /\ eff.dispE = lw[w].epoch
Age          == now - eff.first
PastWindow   == Tier = 1 /\ eff.first >= 0 /\ Age > DedupAge
EffTier      == IF PastWindow THEN (IF Queryable THEN 2 ELSE 3) ELSE Tier
PruneOK      == eff.first >= 0 /\
                IF BROKEN = "thin_dedup_margin" THEN Age > DedupAge
                ELSE Age > DedupAge + SendTimeout + SettleMargin
RunPayload(r) == IF r = 1 THEN Approved ELSE 30
Idle(w)      == lw' = [lw EXCEPT ![w] = L0]
SetPc(w, p)  == lw' = [lw EXCEPT ![w].pc = p]
Renew        == [wf EXCEPT !.lease = now + LeaseTTL]

LogEntry(a, p) ==
  [liveClaim |-> a.liveClaim, grantOk |-> a.grantOk, premiseOk |-> a.premiseOk, resend |-> a.resend,
   recheckOk |-> a.recheckOk, authAfterRevoke |-> a.authAfterRevoke, afterCancel |-> a.afterCancel,
   pastWindow |-> a.pastWindow, payload |-> p, prevSendSettled |-> wire = {},
   premTrueAtSend |-> world.hand = 0]

PutOnWire(w, key, p, a) ==
  /\ wire' = wire \cup {[id |-> Len(sendLog) + 1, w |-> w, key |-> key, payload |-> p,
                         authAfterRevoke |-> a.authAfterRevoke,
                         processBy |-> IF SERVER_SLOW THEN MaxClock ELSE now + SettleMargin]}
  /\ sendLog' = Append(sendLog, LogEntry(a, p))

\* ================================================================ interlock
\* 5.3 claim: a due pending row, or a running row whose lease expired.
Claim(w) ==
  /\ Interlock /\ lw[w].pc = "idle" /\ ~paused[w] /\ wf.lock = None
  /\ \/ wf.status = "pending" /\ wf.avail <= now
     \/ wf.status = "running" /\ wf.lease <= now
  /\ wf' = [wf EXCEPT !.status = "running", !.epoch = @ + 1, !.owner = w, !.lease = now + LeaseTTL]
  /\ lw' = [lw EXCEPT ![w] = [L0 EXCEPT !.pc = "replay", !.epoch = wf.epoch + 1, !.lease = now + LeaseTTL]]
  /\ hist' = [hist EXCEPT !.earlyTakeover = @ \/ (wf.status = "running" /\ wf.lease > now)]
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, tmp>>

\* Renews only when the lease is within one tick of expiry (the ttl/3 thread, coarsened to cut
\* states). Whether it runs at all stays nondeterministic: a skipped heartbeat is a partition.
Heartbeat(w) ==
  /\ Interlock /\ lw[w].pc # "idle" /\ ~paused[w] /\ wf.lock \in {None, w} /\ Fence(w)
  /\ wf.lease <= now + 1
  /\ wf' = Renew
  /\ lw' = [lw EXCEPT ![w].lease = now + LeaseTTL]
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, hist, tmp>>

\* A fenced write matched zero rows: roll back and abandon the run.
Abandon(w) ==
  /\ Interlock /\ ~paused[w] /\ ~Fence(w)
  /\ lw[w].pc \in {"replay", "plainDone", "tdisp", "recov", "tresolve", "tcommitStep"}
  /\ Idle(w)
  /\ UNCHANGED <<now, wf, eff, world, paused, wire, sendLog, hist, tmp>>

\* 5.1 replay from the top: route to the frontier call.
Replay(w) ==
  /\ Interlock /\ lw[w].pc = "replay" /\ ~paused[w]
  /\ CASE ~wf.stepPlain /\ wf.cancelAt < 0 ->
            SetPc(w, "plain") /\ UNCHANGED <<wf, hist>>
       [] ~wf.stepPlain \/ wf.stepEffect ->                  \* Cancelled raised, or the workflow returns
            /\ Fence(w) /\ wf.lock = None
            /\ wf' = [wf EXCEPT !.status = IF wf.cancelAt >= 0 THEN "cancelled" ELSE "completed",
                                !.owner = None]
            /\ hist' = [hist EXCEPT !.unfenced = @ \/ ~RealFence(w)]
            /\ Idle(w)
       [] eff.state = "dispatched" /\ ~Mine(w) ->
            SetPc(w, "recov") /\ UNCHANGED <<wf, hist>>
       [] OTHER ->
            SetPc(w, "premise") /\ UNCHANGED <<wf, hist>>
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, tmp>>

\* A plain step body starts. Fix C1: not after the worker's local lease deadline.
RunPlain(w) ==
  /\ Interlock /\ lw[w].pc = "plain" /\ ~paused[w]
  /\ BROKEN = "no_local_lease_check" \/ now < lw[w].lease
  /\ hist' = [hist EXCEPT !.plainAfter = @ + (IF wf.stepPlain THEN 1 ELSE 0)]
  /\ SetPc(w, "plainDone")
  /\ UNCHANGED <<now, wf, eff, world, paused, wire, sendLog, tmp>>

RecordPlain(w) ==
  /\ Interlock /\ lw[w].pc = "plainDone" /\ ~paused[w] /\ wf.lock = None /\ Fence(w)
  /\ IF wf.stepPlain
       THEN Idle(w) /\ UNCHANGED wf                          \* primary key rejects a second row
       ELSE /\ wf' = [Renew EXCEPT !.stepPlain = TRUE]
            /\ lw' = [lw EXCEPT ![w].pc = "replay", ![w].lease = now + LeaseTTL]
  /\ hist' = [hist EXCEPT !.unfenced = @ \/ ~RealFence(w)]
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, tmp>>

\* 5.7 submit (a): external premises read outside any transaction (A3).
ReadPremise(w) ==
  /\ Interlock /\ lw[w].pc = "premise" /\ ~paused[w]
  /\ lw' = [lw EXCEPT ![w].pc = "tdisp", ![w].readOk = (world.hand = 0), ![w].readGrant = ~world.revoked]
  /\ UNCHANGED <<now, wf, eff, world, paused, wire, sendLog, hist, tmp>>

\* T_dispatch begins: the fence UPDATE takes the workflow row lock; now() is fixed here.
TDispatchBegin(w) ==
  /\ Interlock /\ lw[w].pc = "tdisp" /\ ~paused[w] /\ wf.lock = None /\ Fence(w)
  /\ wf' = [Renew EXCEPT !.lock = w]
  /\ lw' = [lw EXCEPT ![w].pc = "tdispC", ![w].txnStart = now, ![w].fenceOk = RealFence(w),
                      ![w].lease = now + LeaseTTL]
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, hist, tmp>>

RecordEffectStep(w) ==       \* insert the step row in this transaction, release the lock, replay
  /\ wf' = [wf EXCEPT !.lock = None, !.stepEffect = TRUE]
  /\ hist' = [hist EXCEPT !.effRows = @ + 1, !.unfenced = @ \/ ~lw[w].fenceOk]
  /\ SetPc(w, "replay")

\* T_dispatch commits, steps 1 to 13 of 5.7 (c), atomically at commit time.
TDispatchCommit(w) ==
  /\ Interlock /\ lw[w].pc = "tdispC" /\ ~paused[w]
  /\ LET offered == world.offer
         bound   == IF eff.bound = 0 THEN offered ELSE eff.bound
         grantOk == IF BROKEN = "grant_check_outside_txn" THEN lw[w].readGrant ELSE ~world.revoked
         a       == [NoAuth EXCEPT !.liveClaim = lw[w].fenceOk, !.grantOk = ~world.revoked,
                                   !.premiseOk = lw[w].readOk, !.recheckOk = TRUE,
                                   !.authAfterRevoke = world.revoked, !.afterCancel = wf.cancelAt >= 0]
     IN CASE eff.state = "dispatched" ->                     \* open dispatch by another claim: re-enter
               /\ wf' = [wf EXCEPT !.lock = None] /\ SetPc(w, "replay")
               /\ UNCHANGED <<eff, hist>>
          [] wf.stepEffect ->                                \* primary key: roll back
               /\ wf' = [wf EXCEPT !.lock = None] /\ Idle(w) /\ UNCHANGED <<eff, hist>>
          [] eff.bound \notin {0, offered}                   \* REFUSED:conflicting_payload
             \/ eff.state \in {"committed", "ambiguous"}     \* DUPLICATE_IGNORED / AMBIGUOUS
             \/ wf.cancelAt >= 0                             \* REFUSED:cancelled
             \/ ~grantOk                                     \* REFUSED:lease
             \/ ~lw[w].readOk ->                             \* REFUSED:stale_premise
               /\ eff' = [eff EXCEPT !.bound = bound]
               /\ RecordEffectStep(w)
          [] OTHER ->                                        \* DISPATCHED
               /\ eff' = [eff EXCEPT !.state = "dispatched", !.bound = bound, !.dispW = w,
                                     !.dispE = lw[w].epoch, !.first = IF @ < 0 THEN now ELSE @,
                                     !.deadline = lw[w].txnStart + SendTimeout, !.nDisp = @ + 1]
               /\ wf' = [wf EXCEPT !.lock = None]
               /\ lw' = [lw EXCEPT ![w].pc = "send", ![w].auth = a,
                         ![w].deadline = IF BROKEN = "stopwatch_after_dispatch"
                                         THEN now + SendTimeout            \* stopwatch started after commit
                                         ELSE lw[w].txnStart + SendTimeout] \* stopwatch before T_dispatch
               /\ hist' = [hist EXCEPT !.unfenced = @ \/ ~lw[w].fenceOk]
  /\ UNCHANGED <<now, world, paused, wire, sendLog, tmp>>

\* Bytes leave. Only before the local deadline (the watchdog), unless resumed from a pause (A1).
Send(w) ==
  /\ Interlock /\ lw[w].pc = "send" /\ ~paused[w]
  /\ now < lw[w].deadline \/ lw[w].lateSend
  /\ PutOnWire(w, "E", eff.bound, lw[w].auth)
  /\ lw' = [lw EXCEPT ![w].pc = "await", ![w].sentId = Len(sendLog) + 1]
  /\ UNCHANGED <<now, wf, eff, world, paused, hist, tmp>>

\* 5.4 watchdog: os._exit at the local deadline while the send is unfinished.
Watchdog(w) ==
  /\ Interlock /\ lw[w].pc \in {"send", "await"} /\ ~paused[w] /\ now >= lw[w].deadline
  /\ Idle(w)
  /\ UNCHANGED <<now, wf, eff, world, paused, wire, sendLog, hist, tmp>>

\* T_commit: fenced, the dispatch pair must still be this claim.
TCommit(w) ==
  /\ Interlock /\ lw[w].pc = "acked" /\ ~paused[w] /\ wf.lock = None /\ Fence(w)
  /\ eff.state = "dispatched" /\ Mine(w)
  /\ eff' = [eff EXCEPT !.state = "committed", !.nCommit = @ + 1, !.nRes = @ + 1]
  /\ hist' = [hist EXCEPT !.unfenced = @ \/ ~RealFence(w),
                          !.effRows = @ + (IF BROKEN = "commit_without_checkpoint" THEN 0 ELSE 1)]
  /\ IF BROKEN = "commit_without_checkpoint"
       THEN wf' = Renew /\ SetPc(w, "tcommitStep")
       ELSE wf' = [Renew EXCEPT !.stepEffect = TRUE] /\ SetPc(w, "replay")
  /\ UNCHANGED <<now, world, paused, wire, sendLog, tmp>>

\* Broken variant only: the step row commits in a second transaction.
TCommitStep(w) ==
  /\ Interlock /\ lw[w].pc = "tcommitStep" /\ ~paused[w] /\ wf.lock = None /\ Fence(w)
  /\ wf' = [Renew EXCEPT !.stepEffect = TRUE]
  /\ hist' = [hist EXCEPT !.effRows = @ + 1]
  /\ SetPc(w, "replay")
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, tmp>>

\* 5.7 (f) late-result transaction: unfenced, locks only the effect row.
LateAck(w) ==
  /\ Interlock /\ lw[w].pc = "acked" /\ ~paused[w]
  /\ ~Fence(w) \/ ~(eff.state = "dispatched" /\ Mine(w))
  /\ IF eff.state = "dispatched" /\ Mine(w)
       THEN eff' = [eff EXCEPT !.state = "committed", !.nCommit = @ + 1, !.nRes = @ + 1]
       ELSE eff' = [eff EXCEPT !.acksAfterRes = @ + 1,
                               !.late = @ + (IF BROKEN = "late_ack_dropped" THEN 0 ELSE 1)]
  /\ Idle(w)
  /\ UNCHANGED <<now, wf, world, paused, wire, sendLog, hist, tmp>>

\* 5.7 recovery (a): nothing before send_deadline + settle_margin.
BeginRecovery(w) ==
  /\ Interlock /\ lw[w].pc = "recov" /\ ~paused[w]
  /\ CASE eff.state # "dispatched" \/ Mine(w) ->
            SetPc(w, "replay") /\ UNCHANGED wf
       [] now > eff.deadline + SettleMargin \/ BROKEN = "recover_before_deadline" ->
            /\ lw' = [lw EXCEPT ![w].pc = "recheck", ![w].seenW = eff.dispW, ![w].seenE = eff.dispE]
            /\ UNCHANGED wf
       [] OTHER ->                                           \* suspend until the deadline
            /\ Fence(w) /\ wf.lock = None
            /\ wf' = [wf EXCEPT !.status = "pending", !.owner = None,
                                !.avail = eff.deadline + SettleMargin + 1]
            /\ Idle(w)
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, hist, tmp>>

\* 5.7 recovery (c): premise re-check and lookup, outside any transaction.
Recheck(w) ==
  /\ Interlock /\ lw[w].pc = "recheck" /\ ~paused[w]
  /\ lw' = [lw EXCEPT ![w].pc = "tresolve",
                      ![w].recPrem = (BROKEN = "naive_recovery" \/ world.hand = 0),
                      ![w].found = (Queryable /\ "E" \in world.appliedKeys)]
  /\ UNCHANGED <<now, wf, eff, world, paused, wire, sendLog, hist, tmp>>

\* 5.7 recovery (d): T_resolve, gate._recover_one's table. Atomic (now() = commit time).
TResolve(w) ==
  /\ Interlock /\ lw[w].pc = "tresolve" /\ ~paused[w] /\ wf.lock = None /\ Fence(w)
  /\ LET naive  == BROKEN = "naive_recovery"
         stale  == ~(naive \/ ~world.revoked) \/ ~lw[w].recPrem
         a      == [NoAuth EXCEPT !.liveClaim = RealFence(w), !.grantOk = ~world.revoked,
                                  !.premiseOk = IF naive THEN world.hand = 0 ELSE lw[w].recPrem,
                                  !.resend = TRUE, !.recheckOk = ~naive,
                                  !.authAfterRevoke = world.revoked, !.pastWindow = PastWindow]
         still  == /\ eff.state = "dispatched" /\ eff.dispW = lw[w].seenW /\ eff.dispE = lw[w].seenE
                   /\ (now > eff.deadline + SettleMargin \/ BROKEN = "recover_before_deadline")
         Resolve(st, why) ==
           /\ eff' = [eff EXCEPT !.state = st, !.nRes = @ + 1, !.ambig = why,
                                 !.nCommit = @ + (IF st = "committed" THEN 1 ELSE 0),
                                 !.dispW = IF st = "proposed" THEN None ELSE @]
           /\ wf' = [Renew EXCEPT !.stepEffect = TRUE]
           /\ hist' = [hist EXCEPT !.effRows = @ + 1, !.unfenced = @ \/ ~RealFence(w)]
           /\ SetPc(w, "replay")
         Resend ==
           /\ eff' = [eff EXCEPT !.dispW = w, !.dispE = lw[w].epoch, !.deadline = now + SendTimeout]
           /\ wf' = Renew
           /\ lw' = [lw EXCEPT ![w].pc = "send", ![w].auth = a, ![w].deadline = now + SendTimeout]
           /\ hist' = [hist EXCEPT !.unfenced = @ \/ ~RealFence(w)]
     IN IF ~still THEN SetPc(w, "replay") /\ UNCHANGED <<wf, eff, hist>>
        ELSE CASE EffTier = 3               -> Resolve("ambiguous", "tier3")
               [] EffTier = 1 /\ ~stale     -> Resend                           \* COMMITTED_BY_RETRY
               [] stale /\ ~Queryable       -> Resolve("ambiguous", "stale_no_lookup")
               [] lw[w].found               -> Resolve("committed", "none")     \* COMMITTED_ON_QUERY
               [] stale                     -> Resolve("proposed", "none")      \* REFUSED:*_at_recovery
               [] OTHER                     -> Resend                           \* REAPPLIED_AFTER_QUERY
  /\ UNCHANGED <<now, world, paused, wire, sendLog, tmp>>

\* ================================================================ target
\* The target applies a request. Tier 1 dedupes on the key with Stripe semantics:
\* same params replay, different params error, neither applies again.
Process(m) ==
  /\ m \in wire
  /\ LET hit  == Tier = 1 /\ \E kv \in world.keyStore : kv[1] = m.key
         same == <<m.key, m.payload>> \in world.keyStore
         app  == ~hit
         s    == m.w
     IN /\ world' = [world EXCEPT
                       !.ourApps = @ + (IF app THEN 1 ELSE 0),
                       !.keyStore = IF app /\ Tier = 1 THEN @ \cup {<<m.key, m.payload>>} ELSE @,
                       !.appliedKeys = IF app THEN @ \cup {m.key} ELSE @,
                       !.landedUnlisted = @ \/ (app /\ world.revoked /\ ~m.authAfterRevoke
                                                    /\ ~world.revokeReturned)]
        /\ lw' = IF lw[s].pc = "await" /\ lw[s].sentId = m.id
                   THEN [lw EXCEPT ![s].pc = "acked", ![s].ackOk = (~hit \/ same)]
                   ELSE lw
  /\ wire' = wire \ {m}
  /\ UNCHANGED <<now, wf, eff, paused, sendLog, hist, tmp>>

\* ================================================================ temporal
CurrentAttempt(w) == tmp.act = "started" /\ tmp.w = w /\ tmp.attempt = lw[w].epoch /\ tmp.run = lw[w].run

\* The server hands out an attempt: the first, or a retry after the start-to-close timeout.
TStart(w) ==
  /\ ~Interlock /\ lw[w].pc = "idle" /\ ~paused[w] /\ wf.status = "running"
  /\ \/ tmp.act = "scheduled"
     \/ tmp.act = "started" /\ now >= tmp.start + SendTimeout
  /\ tmp' = [tmp EXCEPT !.act = "started", !.w = w, !.start = now, !.attempt = @ + 1]
  /\ lw' = [lw EXCEPT ![w] = [L0 EXCEPT !.pc = IF MODE = "temporal_precheck" THEN "tcheck" ELSE "tsend",
                                       !.epoch = tmp.attempt + 1, !.run = tmp.run, !.txnStart = now]]
  /\ UNCHANGED <<now, wf, eff, world, paused, wire, sendLog, hist>>

\* (b)'s reads: lookup, grant, amount vs approval, eligibility. One step, separate from the send.
TCheck(w) ==
  /\ MODE = "temporal_precheck" /\ lw[w].pc = "tcheck" /\ ~paused[w]
  /\ CASE Queryable /\ "wf" \in world.appliedKeys ->
            lw' = [lw EXCEPT ![w].pc = "acked", ![w].ackOk = TRUE]      \* "already happened"
       [] world.revoked \/ RunPayload(lw[w].run) # Approved ->
            SetPc(w, "tfail")                                          \* non-retryable
       [] OTHER ->
            SetPc(w, "tsend")        \* eligibility: hand refund + 20 <= 100 always passes here
  /\ UNCHANGED <<now, wf, eff, world, paused, wire, sendLog, hist, tmp>>

TSend(w) ==
  /\ ~Interlock /\ lw[w].pc = "tsend" /\ ~paused[w]
  /\ now < lw[w].txnStart + SendTimeout \/ lw[w].lateSend
  /\ LET r   == lw[w].run
         key == IF MODE = "temporal_idem" THEN (IF r = 1 THEN "run1" ELSE "run2") ELSE "wf"
         a   == [NoAuth EXCEPT !.liveClaim = CurrentAttempt(w) /\ now < lw[w].txnStart + SendTimeout,
                               !.grantOk = ~world.revoked, !.premiseOk = (world.hand = 0),
                               !.resend = Len(sendLog) > 0, !.recheckOk = FALSE,
                               !.authAfterRevoke = world.revoked, !.afterCancel = wf.cancelAt >= 0,
                               !.pastWindow = PastWindow]
     IN PutOnWire(w, key, RunPayload(r), a)
  /\ eff' = [eff EXCEPT !.first = IF @ < 0 THEN now ELSE @]
  /\ lw' = [lw EXCEPT ![w].pc = "await", ![w].sentId = Len(sendLog) + 1]
  /\ UNCHANGED <<now, wf, world, paused, hist, tmp>>

\* Completion is recorded only for the current attempt inside its timeout.
TComplete(w) ==
  /\ ~Interlock /\ lw[w].pc = "acked" /\ ~paused[w]
  /\ IF CurrentAttempt(w) /\ now < lw[w].txnStart + SendTimeout
       THEN IF lw[w].ackOk
              THEN /\ tmp' = [tmp EXCEPT !.act = "completed"]
                   /\ eff' = [eff EXCEPT !.state = "committed", !.nCommit = @ + 1]
                   /\ wf' = [wf EXCEPT !.stepEffect = TRUE,
                                       !.status = IF @ = "running" THEN "completed" ELSE @]
                   /\ hist' = [hist EXCEPT !.effRows = @ + 1]
              ELSE /\ tmp' = [tmp EXCEPT !.act = "scheduled"]   \* retryable target error
                   /\ UNCHANGED <<eff, wf, hist>>
       ELSE UNCHANGED <<tmp, eff, wf, hist>>
  /\ Idle(w)
  /\ UNCHANGED <<now, world, paused, wire, sendLog>>

TFail(w) ==
  /\ MODE = "temporal_precheck" /\ lw[w].pc = "tfail" /\ ~paused[w]
  /\ IF CurrentAttempt(w)
       THEN /\ tmp' = [tmp EXCEPT !.act = "failed"]
            /\ wf' = [wf EXCEPT !.status = IF @ = "running" THEN "failed" ELSE @]
       ELSE UNCHANGED <<tmp, wf>>
  /\ Idle(w)
  /\ UNCHANGED <<now, eff, world, paused, wire, sendLog, hist>>

\* ================================================================ world
Once(e) == e \in Events /\ e \notin world.done

Revoke ==
  /\ Once("revoke")
  /\ world' = [world EXCEPT !.revoked = TRUE, !.done = @ \cup {"revoke"},
                            !.revokeReturned = Interlock /\ eff.state = "dispatched"]
  /\ UNCHANGED <<now, wf, eff, lw, paused, wire, sendLog, hist, tmp>>

HandRefund(e, amt) ==
  /\ Once(e) /\ world.hand = 0
  /\ world' = [world EXCEPT !.hand = amt, !.done = @ \cup {e}]
  /\ UNCHANGED <<now, wf, eff, lw, paused, wire, sendLog, hist, tmp>>

Cancel ==     \* rt.cancel locks the workflow row; Temporal: cancellation request, no new attempts
  /\ Once("cancel") /\ wf.lock = None /\ wf.status \notin Terminal
  /\ wf' = [wf EXCEPT !.cancelAt = now,
                      !.avail = IF wf.status = "pending" THEN now ELSE @,
                      !.status = IF Interlock THEN @ ELSE "cancelled"]
  /\ world' = [world EXCEPT !.done = @ \cup {"cancel"}]
  /\ UNCHANGED <<now, eff, lw, paused, wire, sendLog, hist, tmp>>

Prune ==      \* EMULATED key expiry at the target; see C4 for the age condition
  /\ Once("prune_keys") /\ Tier = 1 /\ PruneOK
  /\ world' = [world EXCEPT !.keyStore = {}, !.pruned = TRUE, !.done = @ \cup {"prune_keys"}]
  /\ UNCHANGED <<now, wf, eff, lw, paused, wire, sendLog, hist, tmp>>

\* The next offer is 30. Interlock: a fork or re-run offers it at T_dispatch.
\* Temporal: a reset to before the decision, a new run with a new run id.
Redecide ==
  /\ Once("redecide")
  /\ world' = [world EXCEPT !.offer = 30, !.done = @ \cup {"redecide"}]
  /\ IF Interlock
       THEN UNCHANGED <<wf, eff, tmp, hist>>
       ELSE /\ tmp' = [tmp EXCEPT !.act = "scheduled", !.run = 2]
            /\ wf' = [wf EXCEPT !.status = IF @ = "cancelled" THEN @ ELSE "running", !.stepEffect = FALSE]
            /\ eff' = [eff EXCEPT !.state = "none", !.nCommit = 0]
            /\ hist' = [hist EXCEPT !.effRows = 0]
  /\ UNCHANGED <<now, lw, paused, wire, sendLog>>

WorldStep ==
  \/ Revoke \/ Cancel \/ Prune \/ Redecide
  \/ HandRefund("hand_refund_full", 20) \/ HandRefund("hand_refund_partial", 10)

\* SIGKILL and restart in one step: local state lost, an open transaction rolls back.
Crash(w) ==
  /\ hist.crashes < MaxCrashes /\ lw[w].pc # "idle"
  /\ Idle(w)
  /\ paused' = [paused EXCEPT ![w] = FALSE]
  /\ wf' = [wf EXCEPT !.lock = IF @ = w THEN None ELSE @]
  /\ hist' = [hist EXCEPT !.crashes = @ + 1]
  /\ UNCHANGED <<now, eff, world, wire, sendLog, tmp>>

Pause(w) ==
  /\ PAUSE /\ ~paused[w] /\ lw[w].pc # "idle" /\ hist.pauses < 1
  /\ paused' = [paused EXCEPT ![w] = TRUE]
  /\ hist' = [hist EXCEPT !.pauses = @ + 1]
  /\ UNCHANGED <<now, wf, eff, world, lw, wire, sendLog, tmp>>

\* On SIGCONT a sender may emit its bytes after its deadline: the A1 violation.
Resume(w) ==
  /\ paused[w]
  /\ paused' = [paused EXCEPT ![w] = FALSE]
  /\ lw' = [lw EXCEPT ![w].lateSend = lw[w].pc \in {"send", "tsend"}]
  /\ UNCHANGED <<now, wf, eff, world, wire, sendLog, hist, tmp>>

WorkerStep(w) ==
  \/ Claim(w) \/ Abandon(w) \/ Replay(w) \/ RunPlain(w) \/ RecordPlain(w) \/ ReadPremise(w)
  \/ TDispatchBegin(w) \/ TDispatchCommit(w) \/ Send(w) \/ Watchdog(w) \/ TCommit(w) \/ TCommitStep(w)
  \/ LateAck(w) \/ BeginRecovery(w) \/ Recheck(w) \/ TResolve(w)
  \/ TStart(w) \/ TCheck(w) \/ TSend(w) \/ TComplete(w) \/ TFail(w)

ProgressEnabled == \/ \E w \in Workers : ENABLED WorkerStep(w)
                   \/ ENABLED (\E m \in wire : Process(m))

\* Time cannot pass a request's processing bound. URGENT (liveness configs only): time
\* passes only when nothing else can progress, so a bounded clock does not starve the run.
Tick ==
  /\ now < MaxClock
  /\ \A m \in wire : now < m.processBy
  /\ URGENT => ~ProgressEnabled
  /\ now' = now + 1
  /\ UNCHANGED <<wf, eff, world, lw, paused, wire, sendLog, hist, tmp>>

Next ==
  \/ Tick \/ WorldStep
  \/ \E m \in wire : Process(m)
  \/ \E w \in Workers : WorkerStep(w) \/ Heartbeat(w) \/ Crash(w) \/ Pause(w) \/ Resume(w)

Spec == Init /\ [][Next]_vars

LiveSpec == Spec /\ WF_vars(Tick) /\ WF_vars(\E m \in wire : Process(m))
                 /\ \A w \in Workers : WF_vars(WorkerStep(w))

\* ================================================================ invariants (2.1 names)
Sends == DOMAIN sendLog
FirstBoundPayload == IF Interlock THEN eff.bound ELSE Approved
DispatcherClaimCurrent ==
  eff.dispW # None /\ wf.epoch = eff.dispE /\ wf.owner = eff.dispW /\ wf.status = "running" /\ wf.lease > now

NoRerunAfterComplete        == hist.plainAfter = 0
StepResultUnique            == hist.effRows <= 1
FencedWrites                == ~hist.unfenced
LeaseMutex                  == Cardinality({w \in Workers : Interlock /\ RealFence(w)}) <= 1
TakeoverOnlyAfterExpiry     == ~hist.earlyTakeover
AtMostOneCommit             == eff.nCommit <= 1
EffectAtMostOnceTier12      == (Tier = 2 \/ (Tier = 1 /\ ~(~Queryable /\ world.pruned))) => world.ourApps <= 1
Tier3NeverResends           == IF Tier = 3 THEN Len(sendLog) <= 1
                               ELSE (Tier = 1 /\ ~Queryable) => \A i \in Sends : sendLog[i].resend => ~sendLog[i].pastWindow
NoOverlappingSends          == \A i \in Sends : sendLog[i].prevSendSettled
CommittedImpliesApplied     == eff.state = "committed" => world.ourApps >= 1
AmbiguousOnlyWhenUnknowable == eff.state = "ambiguous" =>
                                 (eff.ambig = "tier3" \/ (Tier = 1 /\ ~Queryable /\ eff.ambig = "stale_no_lookup"))
EffectCheckpointAtomic      == (Interlock /\ eff.state = "committed" /\ ~wf.stepEffect) =>
                                 ((\E w \in Workers : lw[w].pc = "tcommitStep") \/ ~DispatcherClaimCurrent)
SendRequiresLiveClaim       == \A i \in Sends : sendLog[i].liveClaim
NoSendUnderRevokedGrant     == \A i \in Sends : sendLog[i].grantOk
RevokeLinearizable          == (\A i \in Sends : ~sendLog[i].authAfterRevoke) /\ ~world.landedUnlisted
NoSendOnStalePremise        == \A i \in Sends : sendLog[i].premiseOk
RecoveryRechecks            == \A i \in Sends : sendLog[i].resend => sendLog[i].recheckOk
PayloadBound                == \A i \in Sends : sendLog[i].payload = FirstBoundPayload
NoSendAfterCancel           == \A i \in Sends : ~sendLog[i].afterCancel
LateResultPreserved         == eff.late = eff.acksAfterRes
ReceiptChainLinear          == eff.nCommit <= 1 /\ eff.nDisp <= eff.nRes + 1

\* Not in 2.1: the premise judged at the moment the bytes leave, not at the read. Shows the A3 window.
PremiseTrueAtSend           == \A i \in Sends : sendLog[i].premTrueAtSend

\* Reachability witnesses: each must be VIOLATED, or the model is vacuous for that path.
Reach_Committed        == eff.state # "committed"
Reach_Completed        == wf.status # "completed"
Reach_Ambiguous        == eff.state # "ambiguous"
Reach_RecoveryResend   == ~\E i \in Sends : sendLog[i].resend
Reach_CommitByQuery    == ~(eff.state = "committed" /\ wf.stepEffect /\ world.ourApps = 1 /\ eff.dispW # None
                            /\ ~\E i \in Sends : sendLog[i].resend /\ \A w \in Workers : lw[w].pc # "acked")
Reach_RefusedAtRecovery == ~(eff.state = "proposed" /\ eff.nRes > 0)
Reach_LateResult       == eff.late = 0
Reach_Takeover         == wf.epoch < 2
Reach_Cancelled        == wf.status # "cancelled"
Reach_TwoSends         == Len(sendLog) < 2
Reach_Pruned           == ~world.pruned
Reach_SendAfterPrune   == ~(world.pruned /\ Len(sendLog) >= 1 /\ eff.state \in {"committed", "ambiguous"})

Termination    == <>(wf.status \in Terminal)
EffectResolved == (eff.state = "dispatched") ~> (eff.state \in {"committed", "ambiguous", "proposed"})
=============================================================================
