# Scenario billing_credit: goodwill credit vs a billing run

Generated 2026-09-13 22:40 UTC by `experiments/scenario_billing_credit.py`. Stripe Billing test mode with test clocks, model `claude-haiku-4-5-20251001`, every crash a real SIGKILL of the worker process.

| crash / outage | no_check | hand_check | interlock |
|---|---|---|---|
| `before_send` / `renewal` | CREDITED; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof no; 18.1s crash to settled (0.8s after restart) | CREDITED; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 23.7s crash to settled (1.5s after restart) | COMMITTED_BY_RETRY via `retry-idempotent`; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 41.8s crash to settled (14.0s after restart) |
| `before_send` / `billing_credit` | CREDITED; 1 case credit(s), $10 (want 0, $0); **VIOLATED**; answer matches Stripe; proof no; 19.1s crash to settled (0.4s after restart) | REFUSED:stale_premise; 0 case credit(s), $0 (want 0, $0); **held**; answer matches Stripe; proof yes; 21.4s crash to settled (1.2s after restart) | REFUSED:stale_premise_at_recovery; 0 case credit(s), $0 (want 0, $0); **held**; answer matches Stripe; proof yes; 41.5s crash to settled (27.5s after restart) |
| `before_send` / `proration` | CREDITED; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof no; 16.6s crash to settled (0.8s after restart) | CREDITED; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 17.0s crash to settled (1.4s after restart) | COMMITTED_BY_RETRY via `retry-idempotent`; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 41.0s crash to settled (24.1s after restart) |
| `after_send` / `renewal` | REPLAYED_BY_STRIPE; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof no; 15.5s crash to settled (0.4s after restart) | FOUND_BY_LOOKUP; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 15.3s crash to settled (0.3s after restart) | COMMITTED_BY_RETRY via `retry-idempotent`; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 41.1s crash to settled (20.3s after restart) |
| `after_send` / `proration` | REPLAYED_BY_STRIPE; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof no; 13.7s crash to settled (0.3s after restart) | FOUND_BY_LOOKUP; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 14.1s crash to settled (0.8s after restart) | COMMITTED_BY_RETRY via `retry-idempotent`; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 41.2s crash to settled (27.4s after restart) |
| `before_send` / `unrelated_credit` | CREDITED; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof no; 25.7s crash to settled (0.7s after restart) | CREDITED; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 16.5s crash to settled (1.2s after restart) | COMMITTED_BY_RETRY via `retry-idempotent`; 1 case credit(s), $10 (want 1, $10); **held**; answer matches Stripe; proof yes; 41.1s crash to settled (21.0s after restart) |

- **no_check**: invariant held 5/6, answer matched Stripe 6/6, can prove what happened 0/6, median 17s crash to settled (median 1s after restart)
- **hand_check**: invariant held 6/6, answer matched Stripe 6/6, can prove what happened 6/6, median 17s crash to settled (median 1s after restart)
- **interlock**: invariant held 6/6, answer matched Stripe 6/6, can prove what happened 6/6, median 41s crash to settled (median 23s after restart)

Rows where hand_check and interlock differ on the invariant: none.

## Verdict

- **Money: hand_check ties interlock on every row (6 of 6).** Both kept the customer at one $10 credit when nothing
  else credited this incident. Both refused when billing's SLA credit note for the same incident landed during the
  outage. Both still credited when billing credited a different incident. Neither was fooled by the renewal eating
  the credit or by a proration credit line. no_check held 5 of 6. It failed the row that matters here: it re-sent
  after billing had already credited the incident, so the customer got $20 for one incident. The Idempotency-Key
  cannot help, because nothing had been sent under it yet.
- **The premise is scoped to the incident, because the data is there.** Billing's SLA credit notes carry
  `metadata.incident`, and the case file holds the incident id, so both columns compare `incident_compensation`
  (about two lines in `compensation_by_others`). An earlier version of this page said that data was missing. It was
  not, and it compared a coarser premise instead. Both columns read the same `facts()`, so the change moves them
  together and the tie stands.
- **What the coarser premises would have done, from the table below.** `customer_balance` and
  `compensation_by_others` give the same result as `incident_compensation` on the first five rows. That includes
  `before_send`/`billing_credit`: the balance went 0 -> -1000 at restart and would have refused, so an earlier claim
  here that a balance premise would have caught nothing was wrong. All three differ on `unrelated_credit`: both
  coarse premises refuse a goodwill credit the invariant allows, and a person would have to re-approve it. The
  balance also moves on our own send: after `after_send` it read -1000 until the renewal consumed it, so a restart
  before the renewal would see a changed balance. That one is harmless for both careful columns (not run):
  hand_check looks its credit up before comparing premises, and the gate queries the target before it refuses
  (`COMMITTED_ON_QUERY`). A check that compared the balance before looking would refuse a credit that already landed.
- **Where interlock is better: the record, not the outcome.** Both hand_check and interlock leave a record that
  agrees with Stripe, and both are published in full in the JSON (`hand_check_log`; `receipt` and `decision` per
  interlock cell). Interlock's is hash-chained, and verify() re-derives who acted, under which approval, and the lease
  and premise checks before the send and again at recovery; the harness and the unit test re-run it on the published
  copy. hand_check's log is a plain file written by the same worker. It is just as informative here, but nothing can
  check it. Neither is signed in this run (no key), so the chain shows internal consistency, not who wrote it. The
  honest gap is packaging, not correctness: the hand-written lines have to be written again, correctly, for every
  effect.
- **Where interlock is worse: time.** A SIGKILLed Interlock sender keeps its claim until the claim expires (40s
  after DISPATCHED), so every interlock cell settled 41 to 42s after the crash. The other two took 14 to 26s, mostly
  the test clock advance. The wait is what stops two workers sending the same effect at once. The other two columns
  rely on Stripe's 24h idempotency window for that.
- **Recovery path.** Every interlock commit here was `retry-idempotent`: the premises still held at recovery, so
  the gate re-sent under the same key (a first send after before_send, a Stripe replay after after_send). The one
  refusal queried Stripe first and found nothing. AMBIGUOUS never came up, because Stripe dedupes and can be queried.
- **No core change needed.** CreditTarget, the premise and the approval lease store live in scenarios/billing_credit/.

## Premise candidates, from this run

Each cell read all three candidates from Stripe at decision time, right after the SIGKILL, and right before the restart. Values are cents (customer_balance is negative when the customer is owed). "Refuses" means the value differs from decision time in that many of the row's cells. The right answer at restart is to refuse exactly when the row wants no credit from this case; a refusal after `after_send` would contradict a credit that already landed.

| crash / outage | want | `customer_balance` decision -> crash -> restart | `compensation_by_others` decision -> crash -> restart | `incident_compensation` decision -> crash -> restart |
|---|---|---|---|---|
| `before_send` / `renewal` | 1 | 0 -> 0 -> 0; refuses at restart 0/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** |
| `before_send` / `billing_credit` | 0 | 0 -> 0 -> -1000; refuses at restart 3/3; **right** | 0 -> 0 -> 1000; refuses at restart 3/3; **right** | 0 -> 0 -> 1000; refuses at restart 3/3; **right** |
| `before_send` / `proration` | 1 | 0 -> 0 -> 0; refuses at restart 0/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** |
| `after_send` / `renewal` | 1 | 0 -> -1000 -> 0; refuses at restart 0/3, would refuse at crash 3/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** |
| `after_send` / `proration` | 1 | 0 -> -1000 -> 0; refuses at restart 0/3, would refuse at crash 3/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** | 0 -> 0 -> 0; refuses at restart 0/3; **right** |
| `before_send` / `unrelated_credit` | 1 | 0 -> 0 -> -1000; refuses at restart 3/3; **WRONG** | 0 -> 0 -> 1000; refuses at restart 3/3; **WRONG** | 0 -> 0 -> 0; refuses at restart 0/3; **right** |

## Setup

- **Decision.** Support approves ONE $10 goodwill credit for the case (approval cap 1000 cents). The worker reads the
  account from Stripe, and the model (tools `get_account`, `issue_credit`) decides the amount and description; the
  call is validated against the approval cap. The credit is `POST /v1/customers/{id}/balance_transactions`
  (amount -1000, metadata case_id), which Stripe applies to the next finalized invoice.
- **Premises**, captured when the worker reads the account, re-checked before any send: `subscription_status` is
  still `active`; `incident_compensation`, the cents credited to the customer for THIS incident by anyone other than
  this case (issued credit notes and negative balance adjustments whose `metadata.incident` is the case's incident),
  is unchanged. Billing's SLA automation tags its credit notes with the incident, so the data to scope the premise
  is in Stripe. A renewal consuming the balance, proration lines, and a credit for another incident do not move it.
- **Invariant**: this case's credits in Stripe are exactly what the premises allow: one $10 credit, or none when
  billing already credited this incident during the outage. Ground truth is Stripe's balance transactions, credit
  notes and invoices for the customer, re-read after the case settles.
- **no_check**: the decision is saved before the send, and the restart re-sends it with the same Idempotency-Key
  (`goodwill-credit-<case>`). The standard setup: Stripe dedupes, nothing re-reads the world.
- **hand_check**: the idiomatic careful version. Stripe offers no precondition on a balance transaction (no If-Match,
  no expected-balance parameter), so its native tools are the Idempotency-Key and listing the customer's balance
  transactions by metadata. Before every send, first run and restart alike: look this case's credit up and stop if
  it is there; check the approval is unrevoked and covers the amount; compare the premises with the ones saved in
  decision.json; append each step to a log file before and after the POST. About fifteen lines.
- **interlock**: `interlock.gate.Gate` over `scenarios/billing_credit/billing.py:CreditTarget` (tier 1, queryable),
  the approval as the lease store, a JSONL journal, claim TTL 40s; the restart loops `gate.recover()` until the
  effect is resolved, then writes the receipt bundle and `receipts.verify()`.
- **can_prove_what_happened**: the system's own record, without reading Stripe, says who acted, under which
  approval, which checks ran, and an outcome that agrees with Stripe. no_check: never. hand_check: its log does when
  it agrees with Stripe (it is a plain file from the same worker, not tamper-evident; published in full as
  `hand_check_log`). interlock: verify() is valid and its `happened` agrees with Stripe. The full receipt bundle is
  published per cell as `receipt` (with `decision`), and the harness re-runs verify() on that published copy;
  `python3 -m unittest tests.test_scenario_billing_credit` re-checks every published receipt offline.
- **Timing**: seconds from the harness seeing the worker exit -9 to the restart process exiting, which includes the
  outage (the test clock advance, about 10 to 20s); the part after the restart is in parentheses. A SIGKILLed
  Interlock sender cannot release its claim, so recovery waits until 40s after DISPATCHED.

## Rows

- `before_send` / `renewal`: worker SIGKILLed right before the balance-transaction POST; outage: test clock advanced through the renewal: Stripe invoices, applies any customer balance, charges the card. Want: 1 credit(s) from this case.
- `before_send` / `billing_credit`: worker SIGKILLed right before the balance-transaction POST; outage: renewal as above, then billing's SLA automation issues a $10 credit note on the renewal invoice for the same incident (credited to the customer balance). Want: 0 credit(s) from this case.
- `before_send` / `proration`: worker SIGKILLed right before the balance-transaction POST; outage: the customer downgrades $30 -> $20 with proration (credit line for unused time), then the renewal. Want: 1 credit(s) from this case.
- `after_send` / `renewal`: worker SIGKILLed after Stripe's response to the POST was parsed, before anything recorded it; outage: test clock advanced through the renewal: Stripe invoices, applies any customer balance, charges the card. Want: 1 credit(s) from this case.
- `after_send` / `proration`: worker SIGKILLed after Stripe's response to the POST was parsed, before anything recorded it; outage: the customer downgrades $30 -> $20 with proration (credit line for unused time), then the renewal. Want: 1 credit(s) from this case.
- `before_send` / `unrelated_credit`: worker SIGKILLed right before the balance-transaction POST; outage: renewal as above, then billing's SLA automation issues a $10 credit note on the renewal invoice for a DIFFERENT incident (metadata.incident is another INC id). Want: 1 credit(s) from this case.

## LLM decisions

- `before_send`/`renewal`/no_check: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-0efaf1"
- `before_send`/`renewal`/hand_check: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-e35dc8 (case-34ef553a02)"
- `before_send`/`renewal`/interlock: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-d86886 (case-fc36291434)"
- `before_send`/`billing_credit`/no_check: 1000 cents, "Goodwill credit for service outage during incident INC-9ea27f (3 days downtime) - case-7155d2cad6"
- `before_send`/`billing_credit`/hand_check: 1000 cents, "Goodwill credit for three-day service outage (INC-bc90ff). Case case-cdedf8479d."
- `before_send`/`billing_credit`/interlock: 1000 cents, "Goodwill credit for incident INC-383222 - 3-day service outage"
- `before_send`/`proration`/no_check: 1000 cents, "Goodwill credit for 3-day access loss during incident INC-4c56bb (case-a6abd356e7)"
- `before_send`/`proration`/hand_check: 1000 cents, "Goodwill credit for three-day service outage during incident INC-5a01db per case case-79e0c5b893"
- `before_send`/`proration`/interlock: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-5a6cfc (case-41f8e29f91)"
- `after_send`/`renewal`/no_check: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-a81802 (case-f65c3a6625)"
- `after_send`/`renewal`/hand_check: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-08e30e (case-bf572ac028)"
- `after_send`/`renewal`/interlock: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-52a14b (case-50065c673c)"
- `after_send`/`proration`/no_check: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-b9ec8a (case-8a2b73488a)"
- `after_send`/`proration`/hand_check: 1000 cents, "Goodwill credit for service outage during incident INC-7a54f3 (3 days downtime)"
- `after_send`/`proration`/interlock: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-4a24b6"
- `before_send`/`unrelated_credit`/no_check: 1000 cents, "Goodwill credit for 3-day service outage during incident INC-e189ba"
- `before_send`/`unrelated_credit`/hand_check: 1000 cents, "Goodwill credit for three-day service outage during incident INC-0ef01a"
- `before_send`/`unrelated_credit`/interlock: 1000 cents, "Goodwill credit for three-day service outage during incident INC-83bcb4"

## Ids, for checking in the Stripe test dashboard

- `before_send`/`renewal`/no_check: clock clock_1UFM2R88KhIqqdFLFX1wBeEf; customer cus_VFrlBdc4GY9vq1; subscription sub_1UFM2S88KhIqqdFLPR183wL7; renewal_invoice in_1UFM2g88KhIqqdFLnGUAMhBI; case credits cbtxn_1UFM2p88KhIqqdFLDy7epaqj; worker exit -9
- `before_send`/`renewal`/hand_check: clock clock_1UFM2R88KhIqqdFLMsZhnGhe; customer cus_VFrlDF5BP29dnu; subscription sub_1UFM2S88KhIqqdFLqX2MScYH; renewal_invoice in_1UFM2l88KhIqqdFLCsfxZfvp; case credits cbtxn_1UFM2w88KhIqqdFLA4qB1PrI; worker exit -9
- `before_send`/`renewal`/interlock: clock clock_1UFM2R88KhIqqdFLfSHqfr5z; customer cus_VFrlSqPG8t2Dnq; subscription sub_1UFM2S88KhIqqdFLJDrQWiZe; renewal_invoice in_1UFM2r88KhIqqdFLZ3RljPo7; case credits cbtxn_1UFM3F88KhIqqdFLXkeHAqTX; effect 6fdbedc91d21; worker exit -9; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True refused=None rechecked_at_recovery={'lease_live': True, 'lease': {'id': 'approval-case-fc36291434', 'approver': 'support-lead', 'max_cents': 1000, 'revoked': None}, 'violations': []}; journal PROPOSED AUTHORIZED DISPATCHED COMMITTED
- `before_send`/`billing_credit`/no_check: clock clock_1UFM2R88KhIqqdFLStUxOkQD; customer cus_VFrlzBcQz1DUPM; subscription sub_1UFM2S88KhIqqdFLiWGWMwye; renewal_invoice in_1UFM2g88KhIqqdFLjzuzCloD; credit_note cn_1UFM2p88KhIqqdFLyhaCCF7G; credit_note_incident INC-9ea27f; case credits cbtxn_1UFM2r88KhIqqdFLxE0HL2Ul; worker exit -9
- `before_send`/`billing_credit`/hand_check: clock clock_1UFM2R88KhIqqdFLdX8c6UVC; customer cus_VFrlr7iW9JSeTP; subscription sub_1UFM2S88KhIqqdFL7myrAloR; renewal_invoice in_1UFM2j88KhIqqdFLzSGO3Ttr; credit_note cn_1UFM2s88KhIqqdFLLzGeOrsR; credit_note_incident INC-bc90ff; case credits none; worker exit -9
- `before_send`/`billing_credit`/interlock: clock clock_1UFM2r88KhIqqdFLABV3zZAS; customer cus_VFrmE1SLlJEHn2; subscription sub_1UFM2s88KhIqqdFL1VBus6AB; renewal_invoice in_1UFM3288KhIqqdFLjWU223Sl; credit_note cn_1UFM3A88KhIqqdFLVm67iu01; credit_note_incident INC-383222; case credits none; effect 5af981a181de; worker exit -9; receipt valid=True happened=False authorized_when_fired=None assumptions_held=None refused='stale_premise at recovery' rechecked_at_recovery={'lease_live': True, 'lease': {'id': 'approval-case-0230701ef3', 'approver': 'support-lead', 'max_cents': 1000, 'revoked': None}, 'violations': ['incident_compensation: was 0, now 1000']}; journal PROPOSED AUTHORIZED DISPATCHED REFUSED
- `before_send`/`proration`/no_check: clock clock_1UFM2s88KhIqqdFL2K2zAh14; customer cus_VFrmxngRKsc8Ua; subscription sub_1UFM2t88KhIqqdFLOs4EVZRs; renewal_invoice in_1UFM3488KhIqqdFLauiOoyzU; case credits cbtxn_1UFM3F88KhIqqdFLZE58HbVZ; worker exit -9
- `before_send`/`proration`/hand_check: clock clock_1UFM2v88KhIqqdFL8PWExpdN; customer cus_VFrmNJXwuwp9nu; subscription sub_1UFM2w88KhIqqdFLdIzwhxIl; renewal_invoice in_1UFM3788KhIqqdFLhCXxQlaI; case credits cbtxn_1UFM3J88KhIqqdFLTuMMKRg6; worker exit -9
- `before_send`/`proration`/interlock: clock clock_1UFM2x88KhIqqdFLbQGEMVi5; customer cus_VFrmHkFIS1XfBZ; subscription sub_1UFM2y88KhIqqdFLXEYpGoG8; renewal_invoice in_1UFM3B88KhIqqdFLoDiEWp5N; case credits cbtxn_1UFM3j88KhIqqdFLB1eK5Hw5; effect 7d99306218e6; worker exit -9; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True refused=None rechecked_at_recovery={'lease_live': True, 'lease': {'id': 'approval-case-41f8e29f91', 'approver': 'support-lead', 'max_cents': 1000, 'revoked': None}, 'violations': []}; journal PROPOSED AUTHORIZED DISPATCHED COMMITTED
- `after_send`/`renewal`/no_check: clock clock_1UFM3G88KhIqqdFLQFt3AAzA; customer cus_VFrmNh91lKfK0t; subscription sub_1UFM3H88KhIqqdFLWOrF7FFk; renewal_invoice in_1UFM3R88KhIqqdFL18N1DbDS; case credits cbtxn_1UFM3M88KhIqqdFLXcyLHFTh; worker exit -9
- `after_send`/`renewal`/hand_check: clock clock_1UFM3G88KhIqqdFLxUHHpFDh; customer cus_VFrmd9kDZMWMtj; subscription sub_1UFM3H88KhIqqdFLrEaCeiF3; renewal_invoice in_1UFM3T88KhIqqdFL0TXBjJVS; case credits cbtxn_1UFM3O88KhIqqdFLqqS6C0Cx; worker exit -9
- `after_send`/`renewal`/interlock: clock clock_1UFM3K88KhIqqdFLkQLvIF5a; customer cus_VFrmfQkuLBftf0; subscription sub_1UFM3L88KhIqqdFLXwZwkWAE; renewal_invoice in_1UFM3c88KhIqqdFLBmyqAhoe; case credits cbtxn_1UFM3R88KhIqqdFLQ4OeudIT; effect 7f5b47689844; worker exit -9; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True refused=None rechecked_at_recovery={'lease_live': True, 'lease': {'id': 'approval-case-50065c673c', 'approver': 'support-lead', 'max_cents': 1000, 'revoked': None}, 'violations': []}; journal PROPOSED AUTHORIZED DISPATCHED COMMITTED
- `after_send`/`proration`/no_check: clock clock_1UFM3d88KhIqqdFLpxT8MdN3; customer cus_VFrnku4NbXnJiD; subscription sub_1UFM3e88KhIqqdFLyu6YDdze; renewal_invoice in_1UFM3p88KhIqqdFLlIfsNjrx; case credits cbtxn_1UFM3j88KhIqqdFLn1XL9psq; worker exit -9
- `after_send`/`proration`/hand_check: clock clock_1UFM3e88KhIqqdFLgtOfREQX; customer cus_VFrn3QvPBDPWKb; subscription sub_1UFM3f88KhIqqdFLTwBRkYPo; renewal_invoice in_1UFM3s88KhIqqdFL42fn4IGp; case credits cbtxn_1UFM3m88KhIqqdFL8pj9prKY; worker exit -9
- `after_send`/`proration`/interlock: clock clock_1UFM3e88KhIqqdFLNfJmVOz2; customer cus_VFrndYwPb7vZuY; subscription sub_1UFM3f88KhIqqdFLw83Fymtz; renewal_invoice in_1UFM3r88KhIqqdFLGev99edM; case credits cbtxn_1UFM3l88KhIqqdFLcXLqO4z3; effect 6144855b1017; worker exit -9; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True refused=None rechecked_at_recovery={'lease_live': True, 'lease': {'id': 'approval-case-dbb955bf4c', 'approver': 'support-lead', 'max_cents': 1000, 'revoked': None}, 'violations': []}; journal PROPOSED AUTHORIZED DISPATCHED COMMITTED
- `before_send`/`unrelated_credit`/no_check: clock clock_1UFM3k88KhIqqdFLZ1WrniAp; customer cus_VFrnsn5JW4LLM9; subscription sub_1UFM3l88KhIqqdFLS0bxZ1KX; renewal_invoice in_1UFM3y88KhIqqdFLZnl1osW3; credit_note cn_1UFM4E88KhIqqdFLY4pTxUxJ; credit_note_incident INC-10ef40; case credits cbtxn_1UFM4G88KhIqqdFLJIzKymD4; worker exit -9
- `before_send`/`unrelated_credit`/hand_check: clock clock_1UFM3y88KhIqqdFLHs3fz0Ys; customer cus_VFrn96c0keFQg3; subscription sub_1UFM3z88KhIqqdFLdF6BsbSL; renewal_invoice in_1UFM4988KhIqqdFLA31eu0z0; credit_note cn_1UFM4J88KhIqqdFLYKQZCoZE; credit_note_incident INC-d72b97; case credits cbtxn_1UFM4L88KhIqqdFLOc8DPzck; worker exit -9
- `before_send`/`unrelated_credit`/interlock: clock clock_1UFM4188KhIqqdFLoi1XyrAT; customer cus_VFrnUrnKZ3hsO0; subscription sub_1UFM4288KhIqqdFLUtBnvRGc; renewal_invoice in_1UFM4H88KhIqqdFLY5SDLXKh; credit_note cn_1UFM4R88KhIqqdFLo8dBXjrS; credit_note_incident INC-8ae15e; case credits cbtxn_1UFM4n88KhIqqdFLaQW69nSH; effect 883f135cfd91; worker exit -9; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True refused=None rechecked_at_recovery={'lease_live': True, 'lease': {'id': 'approval-case-1c6daca1cf', 'approver': 'support-lead', 'max_cents': 1000, 'revoked': None}, 'violations': []}; journal PROPOSED AUTHORIZED DISPATCHED COMMITTED

## Re-run

    ANTHROPIC_API_KEY=... python3 experiments/scenario_billing_credit.py
