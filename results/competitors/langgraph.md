# Competitor: LangGraph with PostgresSaver, live, against Interlock in the same harness

Generated 2026-09-14 00:39 UTC by `experiments/competitor_langgraph.py`. Raw data: `results/competitors/langgraph.json`
(every cell, run, PaymentIntent, timeline and probe). Tables only: `results/competitors/langgraph_tables.md`.

## Verdict

- **On Stripe's end state, LangGraph plus the docs' "verify existing results" check (19-line refund node) tied
  Interlock in every scenario: 29/29 against 29/29.** The plain docs pattern (13-line refund node, idempotency key
  only) held 26/29; it failed only the hand refund during the outage, 3/3 times ($40 in 2 refunds).
- **LangGraph settled about 37s faster after every SIGKILL**: a median of 1.6 to 5.6s from the kill to settled,
  against 40.8 to 42.4s for Interlock inside the same graph. Interlock waits out the dead sender's 40s claim;
  LangGraph just re-runs the node, relying on Stripe's idempotency key and a lookup.
- **Interlock's measured edge is the record, and only when signed.** All 49 Interlock receipts verified and matched
  Stripe, and the 29 that went through recovery record the re-check they ran. LangGraph's history has no trace of the
  killed attempt (0 of 87 histories). Neither record is tamper-evident by default: an edited LangGraph checkpoint was
  read back with no error, and an unsigned Interlock receipt accepted a forged commit and a truncation. Only
  Interlock with an HMAC key the writer does not hold rejected both.

## Results

"held" is the invariant read from Stripe's refund list. "answers" means the thread's final outcome agrees with
Stripe: sent means exactly one refund of its own, refused means none. "settle" runs from the harness seeing the
SIGKILLed process exit to the resumed process exiting. It includes the outage action and a fresh Python process
start. The time from restart alone is in parentheses.

| scenario | langgraph (docs pattern) | langgraph_checked (docs pattern + verify) | langgraph_interlock (Gate as the refund node) |
|---|---|---|---|
| s1 crash after Stripe commits (3 reps) | held 3/3, answers 3/3, `REPLAYED_BY_STRIPE`, $20 in 1, settle 1.62s | held 3/3, answers 3/3, `FOUND_BY_LOOKUP`, $20 in 1, settle 1.75s | held 3/3, answers 3/3, `COMMITTED_BY_RETRY`, $20 in 1, settle 40.76s |
| s2 crash before send, same $20 refunded by hand (3 reps) | **held 0/3**, answers 3/3, `REFUNDED`, **$40 in 2**, settle 3.75s (2.82s) | held 3/3, answers 3/3, `REFUSED:stale_premise`, $20 in 1, settle 3.55s (2.55s) | held 3/3, answers 3/3, `REFUSED:stale_premise_at_recovery`, $20 in 1, settle 41.93s (41.08s) |
| s3 crash before send, approval revoked (3 reps) | held 3/3, answers 3/3, `REFUSED:not_approved`, $0, settle 4.0s (1.64s) | held 3/3, answers 3/3, `REFUSED:not_approved`, $0, settle 3.8s (2.22s) | held 3/3, answers 3/3, `REFUSED:lease_at_recovery`, $0, settle 41.28s (38.4s) |
| s4 two approvals, one $30 cap, crash `after_commit` (10 runs) | held 10/10, answers 10/10, $20 in 1, settle 4.60s | held 10/10, answers 10/10, $20 in 1, settle 5.21s | held 10/10, answers 10/10, $20 in 1, settle 40.93s |
| s4 two approvals, one $30 cap, crash `before_send` (10 runs) | held 10/10, answers 10/10, $20 in 1, settle 5.56s | held 10/10, answers 10/10, $20 in 1, settle 4.54s | held 10/10, answers 10/10, $20 in 1, settle 42.45s |

Every crash was a real SIGKILL of a separate worker process (exit -9 in all 87 cells and runs). Every model decision
was 2000 cents (27 of 27 in s1 to s3, 120 of 120 in s4). No cell errored or timed out.

Outcomes in s4, crashed bot / other bot:
- `after_commit`: langgraph 10x `REPLAYED_BY_STRIPE` / `REFUSED:over_cap`; langgraph_checked 10x `FOUND_BY_LOOKUP` / `REFUSED:over_cap`; langgraph_interlock 10x `COMMITTED_BY_RETRY` / `REFUSED:over_cap`.
- `before_send`: langgraph 9x `REFUNDED` / `REFUSED:over_cap` and 1x the reverse; langgraph_checked 10x `REFUSED:over_cap` / `REFUNDED` (the other bot took the lock Postgres released and sent); langgraph_interlock 10x `COMMITTED_BY_RETRY` / `REFUSED:over_cap`.

## Lines of user code

Counted by the harness from `# >>> user:` markers (non-blank, non-comment). The Stripe POST helper with the
harness's crash points is counted as one line in each node.

| part | lines |
|---|---|
| graph shared by all columns: state, `get_payment` and `issue_refund` tools, agent, route, propose (validates the model's call), approve (`interrupt()`), `build()` | 52 |
| `langgraph` refund node: approval from state, Store cap, idempotency key | 13 |
| `langgraph_checked` refund node: the same plus own-refund lookup, premise re-read, Postgres advisory lock for the cap | 19 |
| `langgraph_interlock` refund node plus a 9-line `StateApproval` lease adapter; s4 also imports `CapGate` from `scenarios/shared_cap/cap.py` (about 60 lines of scenario code, not core) | 34 |

## What LangGraph does better than Interlock (measured here)

1. **Recovery latency, about 37s better per crash.** Medians of 1.6 to 5.6s against 40.8 to 42.4s, same graph,
   same Stripe account, same model, same kill points. After an `after_commit` crash, Stripe's idempotency key
   (`langgraph`) or a lookup (`langgraph_checked`) settles it immediately. In s4 `before_send`, Postgres released the
   killed holder's session advisory lock right away, so the other bot proceeded within the same few seconds.
   Interlock's claim cannot tell a dead sender from a slow one, so it waits the full `claim_ttl` (40s here).
2. **Revocation with no extra mechanism.** `graph.update_state` wrote the revocation into the thread (a checkpoint
   with source `update`). The resumed refund node read it and refused, 3/3, in the 13-line docs-pattern column, with
   no gate. Interlock needed a 9-line adapter to read the same approval as a lease.
3. **A shared cap without framework surgery.** LangGraph's own cross-thread Store (search, then put a reservation
   before sending) held the $30 cap 20/20. So did an advisory lock in `langgraph_checked`. Interlock held 20/20 only
   through the `CapGate` scenario subclass; the unmodified core held 25/40 in `results/scenarios/shared_cap.md`.
   Caveat: `BaseStore.put` is an unconditional upsert, so search-then-put is still a race. The two bots' resumes
   began a median of 0.16s apart, and the search-to-put window was not timed. 20/20 is not evidence that the race
   is closed.
4. **Checkpoints can hold state on a shared Postgres.** The lock and the Store sit in a database processes reach over
   the network. Interlock's SQLite journal coordinates one host only. Not run across machines here.
5. **The human steps are in the record.** Each history holds the interrupt payload, the resume value (the approver
   and cap), the revocation as its own `update` checkpoint, and the final outcome with the refund id. Interlock's
   journal holds only the lease as the gate read it.
6. **Encrypted blobs detect byte-level edits.** With `EncryptedSerializer.from_pycryptodome_aes` (AES-EAX), flipping
   a byte in an encrypted blob made the reader raise `ValueError('MAC check failed')`. An unsigned Interlock
   receipt has no equivalent; see the probes below for the limits.

## Where Interlock beats it (measured here)

1. **Against the docs pattern alone, on money.** s2: `langgraph` refunded $40 in 2 refunds 3/3; Interlock held 3/3.
   The idempotency key cannot see a refund made by hand under no key. Against `langgraph_checked` this is a tie: 6
   more lines closed it.
2. **The record of what recovery did.** All 49 Interlock receipts verified with happened matching Stripe. The 29
   effects that went through recovery each record the re-check at recovery: the approval read, with `revoked` set in
   s3, and `refunded by others: was 0, now 2000` in s2. A DISPATCHED entry is durable before every send. LangGraph
   recorded nothing of the SIGKILLed attempt: 0 of 87 histories hold a task error, a checkpoint or a pending write
   from it. s1 shows only a normal completion whose outcome says Stripe replayed the key. `langgraph_checked`'s
   refusal reason is whatever string the user wrote.
3. **Tamper evidence, only when keyed.** Interlock's `verify()` with an HMAC key held by the harness rejected a
   forged commit and a truncated receipt. No LangGraph configuration tested detected an edited plaintext value or a
   deleted latest checkpoint.

## Record integrity probes

The forger edits the store directly, then each system's own reader is asked for the state.

| probe | result |
|---|---|
| LangGraph, default serializer, real s1 thread: `jsonb_set` outcome to `REFUSED:not_approved`, remove `refund_id` | read back as edited, no error: **not detected** |
| LangGraph, `EncryptedSerializer` (AES-EAX), fresh thread: edit an inline value | primitives such as `outcome` are stored inline in plaintext JSONB; edit read back with no error: **not detected** |
| same, flip one byte in an encrypted blob | `ValueError('MAC check failed')`: **detected** |
| same, delete the latest checkpoint | state silently rolls back (`refund_id` `re_probe_2` becomes `re_probe`): **not detected** |
| Interlock receipt, real s1 journal, commit rewritten with a recomputed hash | unsigned `verify()` valid=True: **not detected**; keyed `verify()` valid=False: **detected** |
| Interlock receipt, last entry dropped | unsigned valid=True (happened becomes `unknown`): **not detected**; keyed valid=False: **detected** |

LangGraph's checkpointer docs describe encryption as confidentiality. They make no integrity, signing or audit
claim, and the probes agree. The first run of the encrypted probe reused one thread across probes, so its
"delete" row was contaminated by the byte flip. It was re-run with a fresh thread per probe
(`scratchpad/lg/rerun_encrypted_probe.py`); both versions are in the JSON.

## A LangGraph pitfall found on the way

The docs' approve/reject pattern routes with `Command(goto=...)`. In the first smoke run (1 cell per column, not
kept), revoking with `update_state` after a SIGKILL left `next` empty. The refund node never ran, the thread ended
with no outcome, and the Interlock column's journal was left with an open DISPATCHED. `routing_probe` in the JSON
reproduces it without Stripe, using an exception instead of a SIGKILL. With `Command(goto)`, `next` after
`update_state` is `[]`, the final outcome is `null`, and the failed step ran once. With a static edge, `next` stays
`["act"]` and the step re-runs and refuses. The measured graph therefore uses a static edge approve -> refund and
checks the approval in the refund node. That money stayed at $0 in that smoke run was an accident of routing,
not a refusal anyone recorded.

## The columns

- **langgraph**: the docs pattern. `PostgresSaver` (the docs: "Ideal for using in production"), `durability="sync"`,
  `interrupt()` then `Command(resume=...)` for approval, side effects after the interrupt in their own node, the
  Stripe refund with `Idempotency-Key = <thread_id>/refund`, and `invoke(None, same thread_id)` to resume after a
  failure. The refund node honours the approval in state (rejected or revoked means refuse). For s4 it reserves the
  cap in LangGraph's Store before sending.
- **langgraph_checked**: the same plus what the Functional API docs name as the alternative to keys alone, "verify
  existing results". Before sending it looks up a refund carrying this thread id and reports it; otherwise it
  refuses if the payment's refunds changed since the decision. For s4 it wraps the read and the send in a Postgres
  session advisory lock instead of the Store.
- **langgraph_interlock**: the same graph with `interlock.gate.Gate` as the refund node body (`CapGate` for s4),
  `claim_ttl` 40s as in `backend/config.py`, a SQLite journal per run, and the thread's approval as the lease.

## What is real, what is scripted

- Stripe test mode: every payment, refund, lookup and idempotent replay is a real API call. Ground truth is
  Stripe's refund list, re-read after the last process exits.
- Model: every decision is a real `claude-haiku-4-5-20251001` call through `ChatAnthropic`. The model calls
  `get_payment` (a real Stripe read), then `issue_refund`, and its arguments are validated before use.
- Processes: `start`, `resume`, `revoke` and `recover` are separate OS processes sharing only Postgres, Stripe and
  (Interlock) the journal file. At a crash point the worker blocks and the harness SIGKILLs it from outside. On
  macOS, `os.kill(getpid, SIGKILL)` is not synchronous (docs/07-runtime.md 13.4), so the kill comes from outside.
  `after_commit` means Stripe's full response arrived and the node had not returned.
- Scripted, standing in for people: the approver's resume, the revocation (`update_state`, "finance (scripted)"),
  and the hand refund (a Stripe refund with no idempotency key and no metadata, as from the dashboard).
- Postgres 17.11 is a throwaway local cluster the harness starts and stops. LangGraph 1.2.11,
  langgraph-checkpoint 4.2.0, langgraph-checkpoint-postgres 3.1.2, langgraph-prebuilt 1.1.0, langchain-anthropic
  1.7.2, langchain-core 1.6.3, psycopg 3.3.5, Python 3.12.13. Five cells ran at a time.

## Limits

- Small samples: 3 reps for s1 to s3, 10 per crash point for s4. The s4 bots started from one barrier; the Store's
  race window was not timed.
- Not run: an unrelated refund during the outage. `langgraph_checked` uses the same "refunds unchanged" premise as
  Interlock, so it should refuse the approved $20 exactly as Interlock did in `results/e2e_live.md` (read from
  code). Also not run: a Store reservation stranded by a send that never retries, which would hold the cap forever
  (read from `refund_langgraph`), and a chargeback after a successful refund, which no column watches.
- Interlock's 40s wait is its configured `claim_ttl`. The proposed claim-liveness change in `docs/10-scenarios.md`
  is not built, so no faster Interlock number exists.
- LangGraph's settle time includes a fresh Python process importing langchain and langgraph, about 1.5s of the
  totals above.

## Re-run

    uv run --no-project --python 3.12 --with langgraph==1.2.11 --with langgraph-checkpoint-postgres==3.1.2 \
        --with "psycopg[binary,pool]" --with langchain-anthropic==1.7.2 --with pycryptodome \
        python experiments/competitor_langgraph.py --reps 3 --cap-reps 10 --parallel 5
