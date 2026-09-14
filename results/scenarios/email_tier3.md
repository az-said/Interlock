# Scenario email_tier3: an email that cannot be undone (Resend, live)

Generated 2026-09-13 22:47 UTC by `experiments/scenario_email_tier3.py`. Model `claude-haiku-4-5-20251001`, Resend API, Stripe test mode.

Each cell is one support case: a new $100 Stripe test payment, a real model call that reads the case (support
approved a $20 partial refund) and decides the refund and the email text, the refund issued in Stripe, and a worker
process that emails "Your refund is on the way" to delivered@resend.dev through Resend. The worker SIGKILLs itself at
the fault's crash point (exit code -9 recorded per cell). The harness waits out the outage, starts a new worker
process, and reads the result back from Resend and Stripe. An email cannot be recalled once Resend accepts it.

## What Resend offers, from evidence

| question | how it was tested in this run | result |
|---|---|---|
| Does POST /emails dedupe on `Idempotency-Key`? | the same key and body sent twice | first `bc81630f-fd70-4ecc-bb88-d90ef650ab94` replayed=False, second `bc81630f-fd70-4ecc-bb88-d90ef650ab94` replayed=True: **yes** |
| Is the key bound to the body? | the same key with another body | 409 `invalid_idempotent_request`: **yes** |
| Can a sent email be read back by id or listed? | GET `/emails/{id}` and GET `/emails?limit=1` with the key provided | 401 `restricted_api_key` and 401 `restricted_api_key`: **not with this key**. Docs: list returns id, to, subject, created_at, last_event and has no tag or header filter; get by id returns tags. A full-access key was not available, so these were not exercised. |
| Can this key ask "did an email go out under key K" without sending? | POST a well-formed body from an unverifiable domain under K | used key: True (409); fresh key: False (403, nothing sent); a real send under the probed key was new (replayed=False) and the key then probed used=True: **yes, inside 24h** |

Docs checked 2026-09-13: resend.com/docs/dashboard/emails/idempotency-keys (24h, 409 `invalid_idempotent_request`,
409 `concurrent_idempotent_requests`), api-reference list-emails and retrieve-email, resend.com/pricing (30-day data
retention on the free plan). The probe is not a documented lookup; it follows from the documented 409 and from Resend
checking the key before the sender's domain, which this run confirms.

**Tier, from that evidence.** Inside 24h Resend is tier 1 (it dedupes on the key) with a lookup (the probe), the same
shape as the gate's Stripe target. The lookup is an observed behavior, not a contract: if Resend started checking the
sender's domain before the key, the probe would stop answering (it raises rather than guess), and Interlock would be
tier 1 without a lookup, which is interlock_noprobe below. After 24h, with a sending-only key, it is tier 3: nothing dedupes and nothing can be
asked. With a full-access key the docs describe a lookup past 24h (list, then get each email for its tags, within the
retention window), not verified here. The README's row "SendGrid / most email: tier 3" does not describe Resend inside
its key window.

## Results

| system | `crash_after_send` | `refused_before_send` | `refused_after_send` |
|---|---|---|---|
| no_check | `SENT_REPLAYED`; 1 email (want 1); **held**; answer matches Resend; record proves it: no; 0.2s | `SENT`; 1 email (want 0); **VIOLATED** (1 email, want 0); answer matches Resend; record proves it: no; 2.0s | `SENT_REPLAYED`; 1 email (want 1); **held**; answer matches Resend; record proves it: no; 2.5s |
| hand_check | `ALREADY_SENT`; 1 email (want 1); **held**; answer matches Resend; record proves it: yes; 0.8s | `SKIPPED:refund_failed`; 0 email (want 0); **held**; answer matches Resend; record proves it: yes; 4.6s | `ALREADY_SENT`; 1 email (want 1); **held**; answer matches Resend; record proves it: yes; 2.6s |
| hand_check_noprobe | `SENT_REPLAYED`; 1 email (want 1); **held**; answer matches Resend; record proves it: yes; 0.5s | `SKIPPED:refund_failed`; 0 email (want 0); **held**; answer matches Resend; record proves it: yes; 1.6s | `SKIPPED:refund_failed`; 1 email (want 1); **held**; answer CONTRADICTS Resend; record proves it: no; 6.1s |
| interlock | `COMMITTED_BY_RETRY`; 1 email (want 1); **held**; answer matches Resend; record proves it: yes; 35.9s | `REFUSED:stale_premise_at_recovery`; 0 email (want 0); **held**; answer matches Resend; record proves it: yes; 36.7s | `COMMITTED_ON_QUERY`; 1 email (want 1); **held**; answer matches Resend; record proves it: yes; 36.8s |
| interlock_noprobe | `COMMITTED_BY_RETRY`; 1 email (want 1); **held**; answer matches Resend; record proves it: yes; 35.8s | `AMBIGUOUS`; 0 email (want 0); **held**; answer cannot know (said so); record proves it: no; 36.0s | `AMBIGUOUS`; 1 email (want 1); **held**; answer cannot know (said so); record proves it: no; 35.8s |
| interlock_tier3 | `AMBIGUOUS`; 1 email (want 1); **held**; answer cannot know (said so); record proves it: no; 35.4s | `AMBIGUOUS`; 0 email (want 0); **held**; answer cannot know (said so); record proves it: no; 35.9s | `AMBIGUOUS`; 1 email (want 1); **held**; answer cannot know (said so); record proves it: no; 35.9s |

- no_check: 2/3 left Resend as wanted, 3/3 answers matched Resend, 0/3 left a record that proves the outcome, median 2s from crash to settled
- hand_check: 3/3 left Resend as wanted, 3/3 answers matched Resend, 3/3 left a record that proves the outcome, median 3s from crash to settled
- hand_check_noprobe: 3/3 left Resend as wanted, 2/3 answers matched Resend, 2/3 left a record that proves the outcome, median 2s from crash to settled
- interlock: 3/3 left Resend as wanted, 3/3 answers matched Resend, 3/3 left a record that proves the outcome, median 37s from crash to settled
- interlock_noprobe: 3/3 left Resend as wanted, 1/3 answers matched Resend, 1/3 left a record that proves the outcome, median 36s from crash to settled
- interlock_tier3: 3/3 left Resend as wanted, 0/3 answers matched Resend, 0/3 left a record that proves the outcome, median 36s from crash to settled

Faults where the two systems left a different number of emails or gave a different answer: hand_check vs interlock:
none; hand_check_noprobe vs interlock_noprobe: `refused_before_send`, `refused_after_send`;
hand_check_noprobe vs interlock: `refused_after_send`.

## Better, equal, worse

- **Emails: equal.** Every system with a refund re-read (both hand checks, all three gates) left Resend as wanted on
  all three faults. no_check is the one that sends "your refund is on the way" for a refund Stripe has failed
  (`refused_before_send`): the stable key stops a duplicate, not a wrong email.
- **Answers, against the strongest hand check: equal.** hand_check (probe plus refund re-read, about fifteen lines)
  gave the same answer as Interlock on every fault. It ties.
- **Answers, against the idiomatic hand check: Interlock better, but only with the probe.** hand_check_noprobe, in
  `refused_after_send`, re-read the failed refund on restart and logged `SKIPPED:refund_failed` while the crashed
  worker's email had already gone out: its answer and its log contradict Resend. Interlock answered
  `COMMITTED_ON_QUERY` there, and that answer comes from the same undocumented probe. With Resend's documented features
  alone, interlock_noprobe answered `AMBIGUOUS` in both refused rows: never wrong, but not an answer either, and a
  person has to reconcile it. So on documented features the difference is "wrong" against "cannot know", not "wrong"
  against "right".
- **Timing: no attempt was discarded in this run.** The refund failed 0.9s to 5.8s after the last refund read before a
  send (per cell below). The previous run's Interlock result in `refused_before_send` was a near miss that exposed a
  premise bug, now fixed (see Faults).
- **Record: better.** Interlock's receipt is hash-chained, records the approval and premise checks that passed
  immediately before the send, and `verify()` re-derives what happened from it. hand_check's log also names its checks
  and the email id in these runs, but it is plain lines written by the same process, not chained, and nothing checks it.
  The interlock_tier3 receipt says `happened: unknown` after a crash, which is honest and proves nothing about delivery.
- **Time: worse.** A SIGKILLed sender cannot release its claim, so Interlock waits out `CLAIM_TTL` (35s, longer
  than the 30s HTTP timeouts) before recovering. hand_check and no_check rely on Resend's key and retry at once.
- **After 24h (read from code, not run: nobody waited a day).** hand_check's probe then reads "never used", its refund
  re-read passes, and it sends a second email under a key Resend has forgotten. Interlock compares its clock with the
  DISPATCHED entry, treats Resend as tier 3 (KeyWindowGate also stops trusting the probe) and says AMBIGUOUS without
  sending. hand_check could add the same age check.
- **Tier 3 costs availability.** interlock_tier3 never sends twice and never sends after the refund failed, but it
  cannot say whether the crashed send went out, so every crash ends AMBIGUOUS for a person to reconcile, including
  `crash_after_send`, where the email did go.

## Systems

- **no_check**: `Idempotency-Key: refund-email/<case>`, send, retry on restart with the same key, no re-check.
- **hand_check**: the strongest check available with this key, not the idiomatic one. Probe the key (already sent:
  replay the same body under it for the id and stop); else re-read the Stripe refund and skip if it is not succeeded
  or pending; else send with the key. Each check is logged. The probe is undocumented (see above), so few engineers
  would write it.
- **hand_check_noprobe**: the idiomatic check: re-read the refund right before the send, skip if it is not succeeded or
  pending, send with the documented Idempotency-Key, log each step.
- **interlock**: `interlock.Gate` (KeyWindowGate in `scenarios/email_tier3/systems.py`) over `ResendEmail`: tier 1 with
  the effect id as the key, the probe as the lookup, the case approval as the lease, and one premise: the refund is
  succeeded or pending, checked before the send and again at recovery. On startup the worker runs `recover()` until
  nothing is in flight, then submits as usual.
- **interlock_noprobe**: the same gate without the probe (tier 1, `queryable=False`), what Interlock gets from Resend's
  documented features alone.
- **interlock_tier3**: the same gate, told Resend offers neither dedup nor lookup.

## Faults

- `crash_after_send`: worker SIGKILLed right after Resend answered 200, before anything recorded it; restarted at once. Want: exactly one email, reported as sent
- `refused_before_send`: worker SIGKILLed right before the send; during the outage Stripe fails the refund; restarted once Stripe reports it failed. Want: no email
- `refused_after_send`: worker SIGKILLed right after Resend answered 200; during the outage Stripe fails the refund; restarted once Stripe reports it failed. Want: the one email that already went, reported as sent

`pm_card_refundFail` is Stripe's test card whose refund starts `succeeded` and turns `failed` a few seconds later
(4 to 7s when measured). A worker that reads the refund after it failed skips (or is refused) before the send and
never reaches the crash point. Such an attempt is rerun with a new case, the same rule for every system, and kept in
the JSON (`discarded_attempts`) with its own ground truth:

- none in this run

**The previous run was a near miss, and a real bug.** In the run generated 2026-09-13 22:33 UTC, Interlock's premise
was "the refund's OK-ness is unchanged since capture". Its `refused_before_send` cell captured the refund at
1789338900.44; Stripe's `refund.failed` event for re_3UFLzB88KhIqqdFL1X8xhi2V is stamped 1789338901, so the refund
failed 0.56s to 1.56s later. Had it failed before the capture, the premise would have recorded "not OK", matched it,
and sent "your refund is on the way" for a failed refund; and because that worker still reaches the send and the
crash, the harness would have scored it rather than rerun it. The premise is now absolute (the refund is succeeded or
pending), `tests/test_scenario_email_tier3.py` covers a refund already failed at capture, and every system follows
the same rerun rule, with discarded attempts kept above.

How close each refused cell came to the other branch (the worker's last refund read before the send against Stripe's
`refund.failed` event):

- `refused_before_send` / hand_check: last refund read before the send at 1789339801.55, refund.failed at 1789339805: the refund failed 3.45s to 4.45s later
- `refused_before_send` / hand_check_noprobe: last refund read before the send at 1789339810.21, refund.failed at 1789339812: the refund failed 1.79s to 2.79s later
- `refused_before_send` / interlock: last refund read before the send at 1789339816.41, refund.failed at 1789339819: the refund failed 2.59s to 3.59s later
- `refused_before_send` / interlock_noprobe: last refund read before the send at 1789339857.65, refund.failed at 1789339860: the refund failed 2.35s to 3.35s later
- `refused_before_send` / interlock_tier3: last refund read before the send at 1789339897.58, refund.failed at 1789339901: the refund failed 3.42s to 4.42s later
- `refused_after_send` / hand_check: last refund read before the send at 1789339945.49, refund.failed at 1789339947: the refund failed 1.51s to 2.51s later
- `refused_after_send` / hand_check_noprobe: last refund read before the send at 1789339953.17, refund.failed at 1789339959: the refund failed 5.83s to 6.83s later
- `refused_after_send` / interlock: last refund read before the send at 1789339964.17, refund.failed at 1789339966: the refund failed 1.83s to 2.83s later
- `refused_after_send` / interlock_noprobe: last refund read before the send at 1789340006.10, refund.failed at 1789340007: the refund failed 0.9s to 1.90s later
- `refused_after_send` / interlock_tier3: last refund read before the send at 1789340047.20, refund.failed at 1789340049: the refund failed 1.8s to 2.80s later

## Ground truth

Resend's GET endpoints refuse the key provided (above), so ground truth is read from Resend's key store: after the cell,
probe the cell's key; if it was used, replay the recorded body under it, which returns the email's id and must come
back `Idempotent-Replayed: true` (checked; the run aborts otherwise). Every system sends under one stable key per case,
so one used key is one email. An email under some other key would not be seen this way; with a full-access key,
GET /emails would show it. Stripe's refund status is read directly. "Answer" compares what the system itself reported
(sent, not sent, or cannot know) with that.

"Record proves it" means the system's own record, read alone, names the email sent (or the skip), the case, and the
checks that ran before it, and what it says agrees with Resend: for the gates, `interlock.receipts.verify()` is valid
and its `happened` equals the ground truth; for the hand checks and no_check, the app log has a check entry and the
email id or the skip, and that claim equals the ground truth. A log that records a skip while an email went out
proves nothing.

## What is emulated

- interlock_tier3: Nothing about Resend is emulated; the gate is told Resend has no dedup and no lookup (ResendEmail tier=3, queryable=False), the README's assumption for most email and what a sending-only key leaves after Resend's 24h key window. The send still carries an Idempotency-Key only so the harness can read it back; the gate never resends at tier 3, so Resend's dedup is never exercised.

Everything else is live: Resend sends to delivered@resend.dev, Stripe test-mode payments and refunds, Anthropic model
calls, and SIGKILLs of separate worker processes. No mocks.

## Ids

Emails cannot be looked up in the Resend dashboard by key; the ids below are Resend's email ids returned by replay.

- `crash_after_send` / no_check: case case-4471-98a18f707d; PaymentIntent pi_3UFMBM88KhIqqdFL1DuFAEnN; refund re_3UFMBM88KhIqqdFL1u2k3TsE; Idempotency-Key refund-email/case-4471-98a18f707d; email 16ee9986-2227-4ce5-b062-9c255c8773e6; worker exits [-9, 0]
- `crash_after_send` / hand_check: case case-4471-3bef6db623; PaymentIntent pi_3UFMBQ88KhIqqdFL1dGYD1bu; refund re_3UFMBQ88KhIqqdFL1oxm2fMC; Idempotency-Key refund-email/case-4471-3bef6db623; email cf6e4589-a7ba-4d11-9230-14e541439211; worker exits [-9, 0]
- `crash_after_send` / hand_check_noprobe: case case-4471-f7868f875b; PaymentIntent pi_3UFMBW88KhIqqdFL15YQ8PdV; refund re_3UFMBW88KhIqqdFL1SV99qmE; Idempotency-Key refund-email/case-4471-f7868f875b; email c4b18d85-4a48-487f-a273-a9946694b260; worker exits [-9, 0]
- `crash_after_send` / interlock: case case-4471-6cb17b3724; PaymentIntent pi_3UFMBb88KhIqqdFL0edGHCFD; refund re_3UFMBb88KhIqqdFL00Zhw85i; Idempotency-Key 7ee564943fe5; email bec0e2e9-b3ae-46b1-b084-56c8ac686676; worker exits [-9, 0]; receipt valid=True, happened=True, authorized_when_fired=True, assumptions_held=True, re-check at recovery: {'lease_live': True, 'lease': None, 'violations': []}
- `crash_after_send` / interlock_noprobe: case case-4471-6a08f4fd87; PaymentIntent pi_3UFMCG88KhIqqdFL0xNWqtVx; refund re_3UFMCG88KhIqqdFL0K1MeewA; Idempotency-Key c263f4c70222; email 4d2aba90-a641-437c-b1e8-59eae2caacc2; worker exits [-9, 0]; receipt valid=True, happened=True, authorized_when_fired=True, assumptions_held=True, re-check at recovery: {'lease_live': True, 'lease': None, 'violations': []}
- `crash_after_send` / interlock_tier3: case case-4471-2e140620c9; PaymentIntent pi_3UFMCv88KhIqqdFL0Y7QstEs; refund re_3UFMCv88KhIqqdFL0Euck9a4; Idempotency-Key 8f2890ae41fc; email 213e5f20-8942-417f-b92f-697e129b47b8; worker exits [-9, 0]; receipt valid=True, happened=unknown, authorized_when_fired=True, assumptions_held=True, re-check at recovery: None
- `refused_before_send` / no_check: case case-4471-8c0a8d2ee3; PaymentIntent pi_3UFMDa88KhIqqdFL1pSpO6ZB; refund re_3UFMDa88KhIqqdFL1t15Orcy; Idempotency-Key refund-email/case-4471-8c0a8d2ee3; email 975b92da-a61f-4c9e-a385-656d26f89411; worker exits [-9, 0]
- `refused_before_send` / hand_check: case case-4471-da5bd8cb43; PaymentIntent pi_3UFMDh88KhIqqdFL1V7bCcdi; refund re_3UFMDh88KhIqqdFL1wM9F5Gt; Idempotency-Key refund-email/case-4471-da5bd8cb43; email none; worker exits [-9, 0]
- `refused_before_send` / hand_check_noprobe: case case-4471-22eec7418a; PaymentIntent pi_3UFMDr88KhIqqdFL0fr6h9aQ; refund re_3UFMDr88KhIqqdFL0AWNccdD; Idempotency-Key refund-email/case-4471-22eec7418a; email none; worker exits [-9, 0]
- `refused_before_send` / interlock: case case-4471-8cc19e775b; PaymentIntent pi_3UFMDw88KhIqqdFL0qNynx37; refund re_3UFMDw88KhIqqdFL0of52L5x; Idempotency-Key 4592c0d7a73d; email none; worker exits [-9, 0]; receipt valid=True, happened=False, authorized_when_fired=None, assumptions_held=None, re-check at recovery: {'lease_live': True, 'lease': None, 'violations': ['refund re_3UFMDw88KhIqqdFL0of52L5x is failed']}
- `refused_before_send` / interlock_noprobe: case case-4471-f091eda2bd; PaymentIntent pi_3UFMEc88KhIqqdFL0n9DWEGS; refund re_3UFMEc88KhIqqdFL0LDRVi9m; Idempotency-Key d47fa11ee2cd; email none; worker exits [-9, 0]; receipt valid=True, happened=unknown, authorized_when_fired=True, assumptions_held=True, re-check at recovery: {'lease_live': True, 'lease': None, 'violations': ['refund re_3UFMEc88KhIqqdFL0LDRVi9m is failed']}
- `refused_before_send` / interlock_tier3: case case-4471-3461cc4603; PaymentIntent pi_3UFMFG88KhIqqdFL1zZJFi7k; refund re_3UFMFG88KhIqqdFL1MWvaBlJ; Idempotency-Key 860631a9e0f8; email none; worker exits [-9, 0]; receipt valid=True, happened=unknown, authorized_when_fired=True, assumptions_held=True, re-check at recovery: None
- `refused_after_send` / no_check: case case-4471-a3b2caddf1; PaymentIntent pi_3UFMFu88KhIqqdFL1rZHwnR8; refund re_3UFMFu88KhIqqdFL1awhldRi; Idempotency-Key refund-email/case-4471-a3b2caddf1; email f0a3e930-f598-4b76-a6fa-23e8ee08e3e4; worker exits [-9, 0]
- `refused_after_send` / hand_check: case case-4471-3c4eabc10d; PaymentIntent pi_3UFMG188KhIqqdFL00SyZCUl; refund re_3UFMG188KhIqqdFL0DKdSJHA; Idempotency-Key refund-email/case-4471-3c4eabc10d; email 89eb8c8f-1742-4e4a-902a-fda721a1384d; worker exits [-9, 0]
- `refused_after_send` / hand_check_noprobe: case case-4471-b74bb6205f; PaymentIntent pi_3UFMG988KhIqqdFL1ICG2C1N; refund re_3UFMG988KhIqqdFL13cD4271; Idempotency-Key refund-email/case-4471-b74bb6205f; email 83da934e-696e-4c21-a566-92a166120518; worker exits [-9, 0]
- `refused_after_send` / interlock: case case-4471-0d354c4e51; PaymentIntent pi_3UFMGK88KhIqqdFL1py2wPzS; refund re_3UFMGK88KhIqqdFL1M9yVSZL; Idempotency-Key 5a7cbf44d786; email bfed89f9-a943-41c1-81cf-071d67222ef4; worker exits [-9, 0]; receipt valid=True, happened=True, authorized_when_fired=True, assumptions_held=True, re-check at recovery: {'lease_live': True, 'lease': None, 'violations': ['refund re_3UFMGK88KhIqqdFL1M9yVSZL is failed']}
- `refused_after_send` / interlock_noprobe: case case-4471-b92372710b; PaymentIntent pi_3UFMH088KhIqqdFL0t8EmrsK; refund re_3UFMH088KhIqqdFL0QMja2z4; Idempotency-Key c50d768c0526; email 56ca5ec0-fe0d-45ea-afbe-cc90e023fe5d; worker exits [-9, 0]; receipt valid=True, happened=unknown, authorized_when_fired=True, assumptions_held=True, re-check at recovery: {'lease_live': True, 'lease': None, 'violations': ['refund re_3UFMH088KhIqqdFL0QMja2z4 is failed']}
- `refused_after_send` / interlock_tier3: case case-4471-254aaeb33d; PaymentIntent pi_3UFMHf88KhIqqdFL17E3R3ub; refund re_3UFMHf88KhIqqdFL194OHZXu; Idempotency-Key f344da1cd554; email 60891138-ae49-4913-b8d1-de02b1ca3aee; worker exits [-9, 0]; receipt valid=True, happened=unknown, authorized_when_fired=True, assumptions_held=True, re-check at recovery: None

## Re-run

    python3 experiments/scenario_email_tier3.py
    python3 -m unittest tests.test_scenario_email_tier3     # offline logic
