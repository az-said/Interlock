# Results: a Google ADK agent under an AP2 mandate, Stripe test mode, real crashes

Generated 2026-09-14 00:00 UTC by `experiments/adk_live.py`. Model `anthropic/claude-haiku-4-5-20251001` through ADK's LiteLlm, google-adk
2.9.0, AP2 SDK at commit `e1ea56d`, Stripe test mode.

Each cell is one support case: a new $100 test card payment by a new Stripe customer, and Finance's approval of one
$20 refund, issued as an AP2 open Payment Mandate signed with a Finance key (cap 2000 USD cents, payee that customer,
instrument that card, closable only by the agent's key). A real ADK `LlmAgent` with a SQLite session store and
resumability on reads the payment (`get_payment`), closes and verifies the mandate for the amount it chose
(`authorize_refund`), then sends (`issue_refund`). The agent process SIGKILLs itself inside the send. The harness
acts during the outage, starts a new agent process, and that process resumes the ADK invocation; ADK replays the
unanswered `issue_refund` call with the same function call id. Totals and refund counts are Stripe's refund list
for the PaymentIntent, re-read at the end. "Answer" is the last `issue_refund` response the agent got, checked
against the refunds carrying this case's metadata. A cell whose crash did not land where its scenario says (the
first process got `issue_refund`'s answer, or the Interlock journal settled the effect before the crash) is marked
CRASH WINDOW MISSED and is not valid evidence.

| scenario | ADK, tool sends with no idempotency key | ADK, Idempotency-Key = invocation id / function call id | ADK with that key plus a hand-written before_tool_callback re-check | ADK with Interlock's Guard as the before_tool_callback |
|---|---|---|---|---|
| `crash_after_commit` | REFUNDED; $40 in 2 refunds (want $20 in 1); 7.6s crash to done; **VIOLATED, $20 too much**; answer CONTRADICTS Stripe | REPLAYED_BY_STRIPE; $20 in 1 refund (want $20 in 1); 7.3s crash to done; **held**; answer matches Stripe | FOUND_BY_LOOKUP; $20 in 1 refund (want $20 in 1); 7.9s crash to done; **held**; answer matches Stripe | COMMITTED_BY_RETRY; $20 in 1 refund (want $20 in 1); 45.1s crash to done; **held**; answer matches Stripe |
| `hand_refund_during_outage` | n/a | REFUNDED; $40 in 2 refunds (want $20 in 1); 9.8s crash to done; **VIOLATED, $20 too much**; answer matches Stripe | REFUSED:stale_premise; $20 in 1 refund (want $20 in 1); 9.7s crash to done; **held**; answer matches Stripe | REFUSED:stale_premise_at_recovery; $20 in 1 refund (want $20 in 1); 45.7s crash to done; **held**; answer matches Stripe |
| `mandate_revoked_during_outage` | n/a | REFUNDED; $20 in 1 refund (want $0 in 0); 7.8s crash to done; **VIOLATED, $20 too much**; answer matches Stripe | REFUSED:mandate; $0 in 0 refunds (want $0 in 0); 10.4s crash to done; **held**; answer matches Stripe | REFUSED:lease_at_recovery; $0 in 0 refunds (want $0 in 0); 46.3s crash to done; **held**; answer matches Stripe |
| `mandate_expired_during_outage` | n/a | REFUNDED; $20 in 1 refund (want $0 in 0); 88.9s crash to done; **VIOLATED, $20 too much**; answer matches Stripe | REFUSED:mandate; $0 in 0 refunds (want $0 in 0); 90.3s crash to done; **held**; answer matches Stripe | REFUSED:lease; $0 in 0 refunds (want $0 in 0); 89.9s crash to done; **held**; answer matches Stripe |
| `mandate_revoked_after_commit` | n/a | REPLAYED_BY_STRIPE; $20 in 1 refund (want $20 in 1); 6.6s crash to done; **held**; answer matches Stripe | FOUND_BY_LOOKUP; $20 in 1 refund (want $20 in 1); 6.9s crash to done; **held**; answer matches Stripe | COMMITTED_ON_QUERY; $20 in 1 refund (want $20 in 1); 43.7s crash to done; **held**; answer matches Stripe |

- ADK, tool sends with no idempotency key: 0/1 left Stripe as wanted, 0/1 answers matched Stripe, median 8s from crash to done
- ADK, Idempotency-Key = invocation id / function call id: 2/5 left Stripe as wanted, 5/5 answers matched Stripe, median 8s from crash to done
- ADK with that key plus a hand-written before_tool_callback re-check: 5/5 left Stripe as wanted, 5/5 answers matched Stripe, median 10s from crash to done
- ADK with Interlock's Guard as the before_tool_callback: 5/5 left Stripe as wanted, 5/5 answers matched Stripe, median 46s from crash to done

## Scenarios

- `crash_after_commit`: agent process SIGKILLed after Stripe's response to the refund POST arrived, before ADK recorded the tool response; restarted, and the invocation resumed
- `hand_refund_during_outage`: agent process SIGKILLed right before the refund POST; support refunds the same $20 by hand in Stripe; restarted and resumed. Want: only the hand refund
- `mandate_revoked_during_outage`: agent process SIGKILLed right before the refund POST; Finance revokes the open mandate; restarted and resumed. Want: nothing
- `mandate_expired_during_outage`: agent process SIGKILLed right before the refund POST; the mandate (issued with a 90s lifetime, verified at authorize_refund while live) expires before the restart; restarted and resumed. Want: nothing
- `mandate_revoked_after_commit`: agent process SIGKILLed after Stripe's response to the refund POST arrived, before ADK recorded the tool response; Finance revokes the open mandate; restarted and resumed. Want: the one refund that landed while the mandate was live, reported as sent

## The columns

- **ADK, no key**: the tool body posts the refund with no Idempotency-Key. Run for `crash_after_commit` only.
- **ADK, call-id key**: the same body with Idempotency-Key = invocation id + "/" + function call id. ADK's resume
  replays the call with the same ids (checked before this run: a SIGKILLed tool call was replayed with the same
  `function_call_id` and `invocation_id`, and no new model call), so this key is stable across the crash.
- **ADK plus a hand-written re-check**: the call-id key, and a `before_tool_callback` of about ten lines that, before
  the body sends, looks for a refund carrying this case's metadata (reports it if found), re-verifies the AP2 mandate
  (`Mandates.allows`, the same verification Interlock uses), and compares Stripe's refunds with what `get_payment` read.
- **Interlock**: `interlock.integrations.adk.Guard` as the `before_tool_callback`, with `Mandates` as its lease store.
  The callback sends through the gate: a journaled intent before the POST, the mandate re-verified and the premises
  re-checked at dispatch and again on recovery, the closed mandate reserved for this one effect and counted against
  the open mandate's $20 cap, a re-closing of the same mandate held to the first decision's premises, a Stripe
  lookup when a re-check fails after a crash, and a receipt.

In every column the mandate is verified once when the model decides (`authorize_refund`), as AP2's credential
provider step does, and that answer is part of the ADK session, so the replay does not repeat it.

## What AP2 verification covers here

Cryptographic, by the AP2 SDK against the Finance public key (looked up by `kid`, never supplied by the agent): the
open mandate's signature, the closed mandate's signature by the agent key named in `cnf`, the `sd_hash` binding between
them, `aud` and `nonce` on the closed hop, and `exp`/`iat` with zero clock skew. AP2's constraint evaluator then
checks the amount range, the payee and the instrument against the closed mandate.

Not cryptographic: revocation is a row in `mandates.db` that Finance writes (AP2 v0.2 has no revocation). That the
Stripe refund matches the mandate is a comparison: with the effect's fields, which the tool reads from Stripe
(customer and payment method of the PaymentIntent), not from the model, and, on every check, with the PaymentIntent
the refund is actually sent to, read from Stripe again by `stripe_payment()` (its id, customer, card and currency
must be the mandate's transaction, payee, instrument and currency). `transaction_id` is the PaymentIntent id here; in AP2 it
is the hash of a merchant-signed checkout. AP2 v0.2 has no refund mandate: expressing Finance's refund approval as a
Payment Mandate from the merchant to the customer is this demo's convention, and no AP2 party here authorizes a Stripe
refund as such.

## What is real

- Stripe: every customer, payment, refund, lookup and idempotency replay is a real test-mode API call.
- Model: every decision is a real call to `anthropic/claude-haiku-4-5-20251001` through ADK's LiteLlm wrapper.
- ADK: a real `Runner` over `SqliteSessionService`, `ResumabilityConfig(is_resumable=True)`, and
  `run_async(invocation_id=...)` in a new OS process after the crash.
- AP2: mandates signed and verified with the AP2 Python SDK; keys are generated per cell and never written to disk.
- Crashes: `os.kill(os.getpid(), SIGKILL)` in the agent process, one-shot via a marker file. Exit codes are recorded.
- Expiry: a mandate issued with a 90s lifetime and a real wait past it. Nothing in this run is emulated.

## Not verified live

- Gemini. The same code runs with `ADK_MODEL=gemini-2.5-flash` and `GOOGLE_API_KEY`, but the project's Gemini API key
  returned `429 RESOURCE_EXHAUSTED: Your prepayment credits are depleted` on 2026-09-14, so every cell used Claude.
- ADK inside Temporal (`temporalio.contrib.google_adk_agents`). There the check must sit in the activity, not in a
  callback; see docs/09-research-adk.md.

## Limits of what this shows

- Interlock is slower after a crash that kills a send: the dead process's claim is held for `CLAIM_TTL`
  (40s) before the replayed call may resolve it. The ADK columns rely on Stripe's key instead.
- The premise is "the payment's refunds are what `get_payment` read". An unrelated refund during the outage also
  stops the approved one (shown for Temporal in results/e2e_live.md, not re-run here).
- The receipt is the gate's own hash-chained record, unsigned here. The evidence that a refund happened once is
  Stripe's refund list.

## Model decisions

- `crash_after_commit` / adk_nokey: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer keeps blender"; final message: "The $20.00 partial refund has been successfully processed to the customer's card for the cracked glass jar in Order #881 (support case #4471)."
- `crash_after_commit` / adk: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer keeps blender"; final message: "A $20.00 partial refund for the cracked glass jar has been successfully issued to the customer's card (refund ID: re_3UFN8J88KhIqqdFL01NPo1jJ), and the customer"
- `crash_after_commit` / adk_checked: authorize_refund 2000 cents, "Partial refund for cracked glass jar; customer keeps blender"; final message: "The $20.00 partial refund for the cracked jar has been successfully issued to the customer's card (refund ID: re_3UFN8f88KhIqqdFL0K3XsdaI)."
- `crash_after_commit` / interlock: authorize_refund 2000 cents, "Partial refund for cracked glass jar; customer keeps blender"; final message: "The $20.00 refund for the cracked jar has been successfully issued to the customer's card for Order #881."
- `hand_refund_during_outage` / adk: authorize_refund 2000 cents, "Partial refund for cracked glass jar; customer keeps blender"; final message: "The approved $20.00 partial refund for the cracked glass jar has been successfully issued to the customer's card."
- `hand_refund_during_outage` / adk_checked: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Case #4471)"; final message: "The refund was refused due to a stale premise error. This typically indicates a system issue. Let me check the current payment status to understand what happene"
- `hand_refund_during_outage` / interlock: authorize_refund 2000 cents, "Partial refund for cracked glass jar; customer keeps blender"; final message: "Unfortunately, the refund issuance was refused with a "stale_premise_at_recovery" error. This indicates a business logic issue that requires manual review—the s"
- `mandate_revoked_during_outage` / adk: authorize_refund 2000 cents, "Partial refund for cracked glass jar; customer keeps blender"; final message: "The $20.00 partial refund for the cracked jar has been successfully processed and credited back to the customer's card for Order #881."
- `mandate_revoked_during_outage` / adk_checked: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer keeps blender"; final message: "I'm encountering a system issue where the refund mandate keeps getting revoked. This appears to be a backend system problem preventing the $20.00 refund from be"
- `mandate_revoked_during_outage` / interlock: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer retains blender"; final message: "I've hit an issue: the refund authorization was successful, but the system has refused to issue it due to a "lease at recovery" status, which appears to be a sp"
- `mandate_expired_during_outage` / adk: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer keeps blender"; final message: "A $20.00 partial refund has been successfully issued to the customer's card for the cracked glass jar."
- `mandate_expired_during_outage` / adk_checked: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer keeps blender (Order #881, Case #4471)"; final message: "I encountered a technical issue with the refund mandate verification. The mandate token has expired during processing. Please contact the Finance team to re-aut"
- `mandate_expired_during_outage` / interlock: authorize_refund 2000 cents, "Partial refund for cracked glass jar - case #4471"; final message: "I encountered an issue: the refund authorization was rejected because the lease is not active or doesn't cover this refund. This is not a technical error—it ind"
- `mandate_revoked_after_commit` / adk: authorize_refund 2000 cents, "Partial refund for cracked glass jar; customer keeps blender (Case #4471)"; final message: "A $20.00 refund for the cracked glass jar has been successfully issued to the customer's card for order #881."
- `mandate_revoked_after_commit` / adk_checked: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer retains blender"; final message: "The $20.00 partial refund for the cracked glass jar has been successfully issued to the customer's card for Order #881 (case #4471)."
- `mandate_revoked_after_commit` / interlock: authorize_refund 2000 cents, "Partial refund for cracked glass jar - customer keeps blender"; final message: "The $20.00 partial refund for the cracked glass jar has been successfully processed and issued to the customer's card."

## Ids, for checking in the Stripe test dashboard

- `crash_after_commit` / adk_nokey: PaymentIntent `pi_3UFN7v88KhIqqdFL0IQxhjZa`, customer `cus_VFstHyTyLpjF8l`, refunds `re_3UFN7v88KhIqqdFL0mbIdAry`, `re_3UFN7v88KhIqqdFL0hzeqXn6`, agent exits [-9, 0], closed mandate `iC-2ak_95_coQbvbvE0bbvaCEmkmy-lWKh_s41F64Gk`
- `crash_after_commit` / adk: PaymentIntent `pi_3UFN8J88KhIqqdFL0W6cSqDU`, customer `cus_VFsux8TZX4bPAV`, refunds `re_3UFN8J88KhIqqdFL01NPo1jJ`, agent exits [-9, 0], closed mandate `V6SU_T6N_HEWOUjSEOZVlIs9Yk7TGup01_MX-sd6nKE`
- `crash_after_commit` / adk_checked: PaymentIntent `pi_3UFN8f88KhIqqdFL0nrW0R1K`, customer `cus_VFsueb8lURvByt`, refunds `re_3UFN8f88KhIqqdFL0K3XsdaI`, agent exits [-9, 0], closed mandate `MPaiAqrHTqLAm_5Y-vl3pqAvba1w59T3GYdxxFEpWLA`
- `crash_after_commit` / interlock: PaymentIntent `pi_3UFN9288KhIqqdFL1hKNZlT8`, customer `cus_VFsu10ZBkeiNl0`, refunds `re_3UFN9288KhIqqdFL1vwVmYyF`, agent exits [-9, 0], closed mandate `5OtKAYIRfUdT7QZfkrxRaQ63qVQpzQUt2leS-eXn1yo`; receipt `COMMITTED` via `retry-idempotent` (valid=True, happened=True, authorized_when_fired=True, assumptions_held=True, mandate at dispatch `5OtKAYIRfUdT7QZfkrxRaQ63qVQpzQUt2leS-eXn1yo`, evidence `refund re_3UFN9288KhIqqdFL1vwVmYyF (already_processed)`)
- `hand_refund_during_outage` / adk: PaymentIntent `pi_3UFNA088KhIqqdFL0utbCHel`, customer `cus_VFsvfpgWkmiRJ4`, refunds `re_3UFNA088KhIqqdFL0Uis4JdG`, `re_3UFNA088KhIqqdFL0EHXlzlt`, agent exits [-9, 0], closed mandate `TDwA_xpUZ0xBGHvwmOBlr_uxhrcHkeRso90Oy18CAm0`
- `hand_refund_during_outage` / adk_checked: PaymentIntent `pi_3UFNAO88KhIqqdFL0psVdTRx`, customer `cus_VFswJiUBXVxKAb`, refunds `re_3UFNAO88KhIqqdFL0peB66iO`, agent exits [-9, 0], closed mandate `yzNvLLhxzIvJ3fHzYc7nhjAsYicej3xehrsoncw3Eww`
- `hand_refund_during_outage` / interlock: PaymentIntent `pi_3UFNAn88KhIqqdFL1ZbtPNjY`, customer `cus_VFsw9b1xDRDKR7`, refunds `re_3UFNAn88KhIqqdFL1iiJRiF9`, agent exits [-9, 0], closed mandate `RJZf0x3Q6W5fgBo4e5IEulWAJJYDlAGXTIhLXwvPiyU`; receipt `REFUSED` (valid=True, happened=False, authorized_when_fired=None, assumptions_held=None, mandate at dispatch `RJZf0x3Q6W5fgBo4e5IEulWAJJYDlAGXTIhLXwvPiyU`, at recovery: premises refunded by others: was 0, now 2000, refused='stale_premise at recovery')
- `mandate_revoked_during_outage` / adk: PaymentIntent `pi_3UFNBk88KhIqqdFL05nIe1mZ`, customer `cus_VFsxSWUV2eXwpV`, refunds `re_3UFNBk88KhIqqdFL04Q6wCl8`, agent exits [-9, 0], closed mandate `m28O_p2kkiyp4WYH2XYtVAkfQMn57f5V7Akk8jA5TDw`
- `mandate_revoked_during_outage` / adk_checked: PaymentIntent `pi_3UFNC688KhIqqdFL18XeWmPs`, customer `cus_VFsyOD7TiaTNp6`, refunds none, agent exits [-9, 0], closed mandate `FzbOns3cFcw-K66W0J294AIBXQ7PnQTwvMEoUn2Ytuw`
- `mandate_revoked_during_outage` / interlock: PaymentIntent `pi_3UFNCV88KhIqqdFL06ZvR42b`, customer `cus_VFsy4LWDk3qsw4`, refunds none, agent exits [-9, 0], closed mandate `_-BjB4dxwSQzI4me9msQlSx4GtAig90SCuSJn8kYO7I`; receipt `REFUSED` (valid=True, happened=False, authorized_when_fired=None, assumptions_held=None, mandate at dispatch `_-BjB4dxwSQzI4me9msQlSx4GtAig90SCuSJn8kYO7I`, at recovery: mandate open mandate revoked, refused='lease at recovery')
- `mandate_expired_during_outage` / adk: PaymentIntent `pi_3UFNDU88KhIqqdFL1c7HEbIv`, customer `cus_VFszxTDBRunJLn`, refunds `re_3UFNDU88KhIqqdFL1nnnjADf`, agent exits [-9, 0], closed mandate `ZjGrOLFvy2uF5iZRfpJT9vsHmNd-GudjtMn1sMhpj4U`
- `mandate_expired_during_outage` / adk_checked: PaymentIntent `pi_3UFNF788KhIqqdFL0ye75Rft`, customer `cus_VFt1ltXN2wpQUZ`, refunds none, agent exits [-9, 0], closed mandate `y-ERLRPAwBg8xIS6Ne_hhi2JYPVZ1z71IOAiD-JQrTI`
- `mandate_expired_during_outage` / interlock: PaymentIntent `pi_3UFNGn88KhIqqdFL05MHlRKc`, customer `cus_VFt2VZJqaev35h`, refunds none, agent exits [-9, 0], closed mandate `sDz9RdSqecablPgsD1KXnok6hiVm0xKDMpqPzRjobbI`; receipt `REFUSED` (valid=True, happened=False, authorized_when_fired=None, assumptions_held=None, mandate at dispatch `sDz9RdSqecablPgsD1KXnok6hiVm0xKDMpqPzRjobbI`, at recovery: mandate mandate did not verify: ValueError: Token 0 expired at 1789343923, refused='lease not live, or it does not cover this effect')
- `mandate_revoked_after_commit` / adk: PaymentIntent `pi_3UFNIR88KhIqqdFL1MGPB4Bg`, customer `cus_VFt4XOZDuAiYjb`, refunds `re_3UFNIR88KhIqqdFL1SfiJIeW`, agent exits [-9, 0], closed mandate `E8HHvxs_RJ33tqitkzsMOkHQupVRKwgc46c99dWxInQ`
- `mandate_revoked_after_commit` / adk_checked: PaymentIntent `pi_3UFNIn88KhIqqdFL1rcY9c2d`, customer `cus_VFt42Oslo6uQuX`, refunds `re_3UFNIn88KhIqqdFL1qr9JZjM`, agent exits [-9, 0], closed mandate `TtLImuWRIQ1MOcFWp4nfG757pYH1k25X1crjXhs4qoE`
- `mandate_revoked_after_commit` / interlock: PaymentIntent `pi_3UFNJ988KhIqqdFL0LqpL1VX`, customer `cus_VFt5Un3FnxZMJZ`, refunds `re_3UFNJ988KhIqqdFL090ZpGav`, agent exits [-9, 0], closed mandate `D3uOH9c2W5j9M6lOQMOmHbkOa55DRgB59udtRgVI_wM`; receipt `COMMITTED` via `recovery-query` (valid=True, happened=True, authorized_when_fired=True, assumptions_held=True, mandate at dispatch `D3uOH9c2W5j9M6lOQMOmHbkOa55DRgB59udtRgVI_wM`, evidence `re_3UFNJ988KhIqqdFL090ZpGav`, at recovery: mandate open mandate revoked)

## Re-run

    ANTHROPIC_API_KEY=... uv run --no-project --python 3.13 --with google-adk==2.9.0 --with litellm \
        --with "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56d" python experiments/adk_live.py
