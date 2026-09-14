------------------------------ MODULE Signals ------------------------------
(***************************************************************************)
(* Suspend, signal and timer for interlock_runtime (docs/07-runtime.md 5.6). *)
(* One workflow makes two consecutive wait_signal("approve") calls: wait 1 *)
(* has a timeout at absolute database time Until (3 or infinity), wait 2 has *)
(* none. Two signals may be sent at any time. One worker, which may crash   *)
(* (SIGKILL) and be claimed again after its lease (lease time abstracted).  *)
(*                                                                         *)
(* BROKEN = "wake_only_if_sleeping" splits the suspend transaction into a   *)
(* mailbox check and a later release, and makes rt.signal wake only a       *)
(* workflow that is already sleeping. That is the lost-wakeup design the    *)
(* spec rejects.                                                           *)
(*                                                                         *)
(* This is a model check for the stated constants, not a proof of the      *)
(* Python or SQL.                                                          *)
(***************************************************************************)
EXTENDS Integers, FiniteSets

CONSTANTS MaxClock, MaxCrashes, BROKEN

Inf     == MaxClock + 1          \* 'infinity': later than any reachable clock value
Sigs    == {1, 2}                \* signal ids (ilr.signals.id order)
Seqs    == {1, 2}                \* the two wait steps
Done    == 3                     \* seq after both waits are recorded
None    == 0
Timeout == -1
Split   == BROKEN = "wake_only_if_sleeping"

VARIABLES
  now,          \* database clock
  until1,       \* timeout of wait 1, chosen in Init: 3 or Inf
  status,       \* ilr.workflows.status: "pending" | "running" | "sleeping" | "completed"
  availableAt,  \* ilr.workflows.available_at
  mailbox,      \* unconsumed signal rows
  consumed,     \* signal id -> set of seqs that consumed it (should be at most one)
  recorded,     \* seq -> None (0) | Timeout (-1) | signal id  (ilr.steps output)
  recordedAt,   \* seq -> database time the step row was written
  seq,          \* next unrecorded wait seq (the replay frontier)
  pcS,          \* worker: "idle" | "check" | "release"
  sent,         \* signals already sent
  crashes

vars == <<now, until1, status, availableAt, mailbox, consumed, recorded, recordedAt, seq, pcS, sent, crashes>>

UntilOf(q) == IF q = 1 THEN until1 ELSE Inf

Init ==
  /\ now = 0
  /\ until1 \in {3, Inf}
  /\ status = "pending"
  /\ availableAt = 0
  /\ mailbox = {}
  /\ consumed = [s \in Sigs |-> {}]
  /\ recorded = [q \in Seqs |-> None]
  /\ recordedAt = [q \in Seqs |-> 0]
  /\ seq = 1
  /\ pcS = "idle"
  /\ sent = {}
  /\ crashes = 0

Tick == now < MaxClock /\ now' = now + 1
        /\ UNCHANGED <<until1, status, availableAt, mailbox, consumed, recorded, recordedAt, seq, pcS, sent, crashes>>

\* Claim: due pending/sleeping row, or a running row whose worker died (lease expiry abstracted).
Claim ==
  /\ pcS = "idle"
  /\ \/ status \in {"pending", "sleeping"} /\ availableAt <= now
     \/ status = "running"
  /\ status' = "running"
  /\ pcS' = "check"
  /\ UNCHANGED <<now, until1, availableAt, mailbox, consumed, recorded, recordedAt, seq, sent, crashes>>

Record(out) ==
  /\ recorded' = [recorded EXCEPT ![seq] = out]
  /\ recordedAt' = [recordedAt EXCEPT ![seq] = now]
  /\ seq' = seq + 1
  /\ IF seq + 1 = Done
       THEN status' = "completed" /\ pcS' = "idle"
       ELSE status' = status /\ pcS' = "check"

\* The suspend transaction of 5.6 (atomic), or its first half under the broken variant.
Suspend ==
  /\ pcS = "check" /\ seq # Done
  /\ IF mailbox # {}
       THEN LET s == CHOOSE x \in mailbox : \A y \in mailbox : x <= y IN
            /\ mailbox' = mailbox \ {s}
            /\ consumed' = [consumed EXCEPT ![s] = @ \cup {seq}]
            /\ Record(s)
            /\ UNCHANGED availableAt
       ELSE IF UntilOf(seq) # Inf /\ now >= UntilOf(seq)
       THEN /\ Record(Timeout)
            /\ UNCHANGED <<mailbox, consumed, availableAt>>
       ELSE IF Split
       THEN /\ pcS' = "release"
            /\ UNCHANGED <<status, availableAt, mailbox, consumed, recorded, recordedAt, seq>>
       ELSE /\ status' = "sleeping"
            /\ availableAt' = UntilOf(seq)
            /\ pcS' = "idle"
            /\ UNCHANGED <<mailbox, consumed, recorded, recordedAt, seq>>
  /\ UNCHANGED <<now, until1, sent, crashes>>

\* Broken variant only: the release commits separately, after the mailbox check.
SuspendRelease ==
  /\ pcS = "release"
  /\ status' = "sleeping"
  /\ availableAt' = UntilOf(seq)
  /\ pcS' = "idle"
  /\ UNCHANGED <<now, until1, mailbox, consumed, recorded, recordedAt, seq, sent, crashes>>

\* rt.signal: lock the row, insert the signal, wake. The broken variant wakes only a sleeping row.
SendSignal(s) ==
  /\ s \notin sent
  /\ sent' = sent \cup {s}
  /\ mailbox' = mailbox \cup {s}
  /\ IF status = "completed" \/ (Split /\ status # "sleeping")
       THEN UNCHANGED <<status, availableAt>>
       ELSE /\ availableAt' = now
            /\ status' = IF status = "sleeping" THEN "pending" ELSE status
  /\ UNCHANGED <<now, until1, consumed, recorded, recordedAt, seq, pcS, crashes>>

\* SIGKILL: an open transaction rolls back, local state is lost, the row stays 'running'.
Crash ==
  /\ pcS # "idle" /\ crashes < MaxCrashes
  /\ pcS' = "idle"
  /\ crashes' = crashes + 1
  /\ UNCHANGED <<now, until1, status, availableAt, mailbox, consumed, recorded, recordedAt, seq, sent>>

Next ==
  \/ Tick \/ Claim \/ Suspend \/ SuspendRelease \/ Crash
  \/ \E s \in Sigs : SendSignal(s)

Spec == Init /\ [][Next]_vars

\* ---- invariants (names as in docs/07-runtime.md 2.1) ----
NoLostWakeup == ~(status = "sleeping" /\ availableAt = Inf /\ mailbox # {})

SignalExactlyOnceConsumed ==
  \A s \in Sigs : Cardinality(consumed[s]) <= 1 /\ \A q \in consumed[s] : recorded[q] = s

TimerNotEarly == \A q \in Seqs : recorded[q] = Timeout => recordedAt[q] >= UntilOf(q)

TypeOK ==
  /\ status \in {"pending", "running", "sleeping", "completed"}
  /\ pcS \in {"idle", "check", "release"}
  /\ seq \in 1..Done
=============================================================================
