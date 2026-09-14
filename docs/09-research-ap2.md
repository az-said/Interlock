# 09. Research: AP2 (Agent Payments Protocol) and Interlock

Sources: primary only. Repo `github.com/google-agentic-commerce/AP2`, cloned 2026-09-13 at
`e1ea56d` (2026-04-29). Tags: `v0.1.0` (2025-09-16), `v0.2.0` (`b4587ac`, 2026-04-28). Remote HEAD is
`e1ea56d`, so this is the latest published state. Files read: `docs/ap2/specification.md`,
`payment_mandate.md`, `checkout_mandate.md`, `agent_authorization.md`, `flows.md`,
`implementation_considerations.md`, `security_and_privacy_considerations.md`, the Python SDK under
`code/sdk/python/ap2/`, and the credential provider and payment processor samples. Everything marked
"ran" was executed on this machine. Anything else is from reading the code or the spec.

## 1. Short answer

- **License:** Apache-2.0 (`LICENSE`, `pyproject.toml`).
- **IntentMandate, CartMandate and PaymentMandate(contents, user_authorization) are v0.1 names.**
  v0.2 replaced them. The v0.2 spec never mentions IntentMandate or CartMandate. They survive only in
  `code/sdk/python/ap2/models/mandate.py` and the legacy samples.
- **v0.2 has two mandate types, Checkout and Payment, each open or closed.** Four `vct` values:
  `mandate.checkout.1`, `mandate.checkout.open.1`, `mandate.payment.1`, `mandate.payment.open.1`.
  Each one is an SD-JWT with Key Binding, chained with `~~` ("Delegate SD-JWT", an individual draft).
- **Refunds are not covered.** v0.2 has no refund mandate, refund constraint or refund receipt. The
  string "refund" does not appear in the v0.2 spec or the Python SDK. v0.1 had one related field,
  `IntentMandate.requires_refundability` ("items must be refundable"), which is not an authorization
  to refund.
- **Revocation is not covered.** There is no status claim, no status list and no revocation
  endpoint. The spec calls "Mandate Management" out of scope and gives it only a SHOULD for the
  Shopping Agent.
- **Double spend and replay are pushed onto stateful parties.** The spec says the Shopping Agent
  "MUST NOT" sign overlapping closed mandates until it holds a rejection receipt, and that Credential
  Providers, networks and processors "MAY" reject overlapping mandates. The SDK verifier is stateless:
  the same presentation verifies twice (ran, check 2).
- **What you can verify cryptographically today with the SDK (ran):**
  - the signature chain (provider key, then the agent `cnf` key)
  - the `sd_hash` binding between hops
  - `aud` and `nonce` on the terminal hop
  - `exp` and `iat`, with 300 s of default skew
  - deterministic constraint checks: amount range, payee, currency, instrument, PISP, execution
    date, reference
  - recurrence and budget, but only against a usage context the caller supplies
  - ES256 signatures on receipts

That gap is where Interlock fits. AP2 proves an agent was authorized, within limits, when the mandate
was signed. It keeps no state about whether the authority still holds or whether the effect already
happened. Interlock checks that at dispatch and again at recovery, and records it in a receipt.

## 2. v0.2 data model (from the generated pydantic types and JSON schemas)

Amounts are `{amount: int (ISO 4217 minor units), currency: str}`.
Merchants are `{id, name, website?}`.
Payment instruments are `{id, type, description?}`.

### Closed Payment Mandate, `vct = mandate.payment.1`

| field | type | notes |
|---|---|---|
| `transaction_id` | str, required | base64url hash of the merchant-signed `checkout_jwt`; binds payment to checkout |
| `payee` | Merchant, required | |
| `payment_amount` | Amount, required | "Final value confirmed by the user" |
| `payment_instrument` | PaymentInstrument, required | |
| `pisp` | PISP, optional | payment initiation service provider |
| `execution_date` | ISO 8601 str, optional | absent means immediate |
| `risk_data` | object, optional | signals from the trusted surface |
| `iat`, `exp` | int epoch, optional | |

### Open Payment Mandate, `vct = mandate.payment.open.1`

This mandate has `constraints` (required), `cnf` (required, RFC 7800: the agent's public key that may
close it) and `iat`/`exp`. It may also carry any closed-mandate field as a pre-set value, which must
match exactly. Payment constraint types:

| type | fields | evaluation (SDK `constraints.py`) |
|---|---|---|
| `payment.amount_range` | `currency`, `max` int, `min` int? | closed amount within range, same currency |
| `payment.allowed_payees` | `allowed: [Merchant]` (selectively disclosable) | match by `id`, else `name`+`website` |
| `payment.allowed_payment_instruments` | `allowed: [PaymentInstrument]` | match by `id` |
| `payment.allowed_pisps` | `allowed: [PISP]` | match on legal, brand and domain name |
| `payment.execution_date` | `not_before?`, `not_after?` | string comparison of ISO dates |
| `payment.reference` | `conditional_transaction_id` | equals hash of the open Checkout Mandate |
| `payment.agent_recurrence` | `frequency` enum, `max_occurrences?` | needs caller-supplied `MandateContext.total_uses` |
| `payment.budget` | `max` (float, major units), `currency` | needs caller-supplied `MandateContext.total_amount` |

Spec rule: "Any unknown Constraints MUST be treated as failing evaluation."

### Checkout Mandates

- **Closed, `mandate.checkout.1`:** `checkout_jwt` is the merchant-signed checkout (a UCP Checkout
  object when used with UCP). `checkout_hash` is the hash of `checkout_jwt`. Optional `iat`/`exp`.
- **Open, `mandate.checkout.open.1`:** `constraints`, `cnf`, `iat`/`exp`. Constraint types:
  - `checkout.allowed_merchants`
  - `checkout.line_items`: SKU sets and quantities, evaluated as max flow

### Receipts (verifier-signed JWT)

- **All receipts:** `status` (`Success` or `Error`), `iss`, `iat`, `reference` (hash of the closed
  mandate received), and `error`/`error_description` on Error.
- **Payment receipt adds:** `payment_id`, `psp_confirmation_id`, `network_confirmation_id`.
- **Checkout receipt adds:** `order_id`.
- **Error codes:** `invalid_credential`, `unresolved_constraint`, `invalid_mandate`,
  `mandates_not_supported`.
- **Signing and verification:** the SDK signs receipts with ES256 and verifies them with
  `ReceiptClient.verify_receipt`.

### Signatures and who signs

- **Human present:** the user, through a Trusted Surface, signs the closed mandates directly. Trust
  comes from a User Credential via OpenID4VP `transaction_data` of type `delegate`, or from a trusted
  Agent Provider key.
- **Human not present:**
  1. The Trusted Surface signs open mandates carrying the agent key in `cnf`.
  2. The agent closes them with a KB-SD-JWT signed by that key, using `aud`, `nonce`, and `sd_hash`
     over the previous hop.
  3. The verifier receives both hops.
- **Root key resolution:** the SDK resolves it by `kid` lookup, or by an `x5c` chain checked against
  trusted roots.

### v0.1, for reference only (`ap2/models/mandate.py`)

- **IntentMandate:** `user_cart_confirmation_required`, `natural_language_description`, `merchants?`,
  `skus?`, `requires_refundability?`, `intent_expiry` (ISO).
- **CartMandate:** `contents` (`id`, `user_cart_confirmation_required`, W3C `payment_request`,
  `cart_expiry`, `merchant_name`), plus `merchant_authorization` (a JWT over a `cart_hash`).
- **PaymentMandate:** `payment_mandate_contents` (`payment_mandate_id`, `payment_details_id`,
  `payment_details_total`, `payment_response`, `merchant_agent`, `timestamp`), plus
  `user_authorization` (an SD-JWT-VC presentation whose KB-JWT `transaction_data` holds hashes of the
  cart and payment contents).

Do not build on v0.1. The v0.2 spec and SDK no longer use these types.

## 3. What ran

**SDK test suite:**

```
PYTHONPATH=code/sdk/python uv run --no-project --python 3.13 --with cryptography==46.0.5 \
  --with jwcrypto==1.5.6 --with pydantic==2.12.5 --with sd-jwt==0.10.4 --with pytest==9.0.2 \
  python -m pytest -q -o python_files='*_tests.py' code/sdk/python/ap2/tests
2 failed, 186 passed
```

- **The 2 failures:** `kb_sd_jwt_intermediate_tests.py::test_verify_rejects_aud_mismatch` and
  `test_verify_rejects_nonce_mismatch`.
- **Cause:** `kb_sd_jwt.verify` only enforces `aud`/`nonce` on terminal hops (`typ in TYP_TERMINAL`),
  so an intermediate hop with the wrong `aud` or `nonce` is accepted.
- **Impact:** none on the two-hop open-to-closed flow below, where the checked hop is terminal.

**Probe script (Appendix A):** it signs an open Payment Mandate with a provider key, closes it with an
agent key, and verifies it the way the sample Credential Provider does (`MandateClient.verify`, then
`PaymentMandateChain.verify`). Output:

| # | case | result |
|---|---|---|
| 1 | valid chain, $15.00 under a $20.00 cap | ACCEPTED |
| 2 | the same presentation verified a second time | **ACCEPTED** (no replay protection in the verifier) |
| 3 | $25.00 over the cap | violation `Amount 2500 exceeds maximum 2000` |
| 4 | payee not allowed | violation `Payee Other not in allowed list` |
| 5 | EUR against a USD range | violation `Currency mismatch` |
| 6 | verified 2 h later, open mandate `exp` +1 h | rejected `Token 0 expired` |
| 7 | verified 4 min after `exp` | **ACCEPTED** (default `clock_skew_seconds=300`) |
| 8 | wrong nonce | rejected `KB-SD-JWT nonce mismatch` |
| 9 | root key not the trusted one | rejected `InvalidJWSSignature` |
| 10 | one byte of the closed hop changed | rejected (here at JSON parse; the signature check sits behind it) |
| 11 | recurrence + budget, no usage context passed | violations `Missing mandate context` (fails closed) |
| 12 | recurrence `max_occurrences=1`, context "0 prior uses" | ACCEPTED |
| 13 | same, context "1 prior use, 1500 spent" | violations: occurrences exceeded, budget exceeded |
| 14 | same chain, stale context "0 prior uses" passed again | **ACCEPTED** (the caller is the source of truth) |
| 15 | JPY budget `max=1000`, spend 50,000 yen | **ACCEPTED**: `BudgetEvaluator` does `int(max * 100)`, which is wrong for zero-decimal currencies |

Other SDK defects found:

- **Recurrence mandates cannot be signed as written.** `MandateClient.create` raises
  `TypeError: Object of type Frequency is not JSON serializable` on a mandate with
  `AgentRecurrence(frequency=Frequency.X)`. The cause is that `common.delegate_claims_from_model`
  calls `model_dump()` without `mode="json"`. The recurrence tests never sign, and no sample uses
  recurrence. The probe works around it with `model_construct(frequency="ON_DEMAND")`.
- **The docs and the schema disagree on amount units.** The docs example for `payment.amount_range`
  shows `"max": 100.50`, while the schema and SDK use integer minor units. `payment.budget` uses float
  major units. A mapping must normalize both.

Not verified live, with reasons:

- **The ADK and Gemini sample scenarios:** they need a Gemini key and the A2A servers. The protocol
  logic they call is the SDK code exercised above.
- **The User Credential and OpenID4VP path, and the Android and Go samples:** they need a wallet or
  Digital Credentials API.
- **The `x5c` root path:** read, not run.

## 4. Deriving an Interlock lease from an AP2 mandate

Interlock's gate asks a lease store two questions: `is_live(lease)`, and `allows(lease, effect)` when
the store has it. It asks at dispatch and again in `recover()`, and it records `describe(lease)` next
to each check (`interlock/gate.py` `_lease_seen`, `backend/leases.py`). An AP2 mandate fits that
interface. The proposal would be an optional-dependency adapter at `interlock/integrations/ap2.py`
that imports `ap2` lazily.

**Lease id.** The receipt `reference` of the closed mandate:
`sha256_b64url(MandateClient().get_closed_mandate_jwt(chain))`. It is the same value AP2 receipts
bind to, so an Interlock receipt and an AP2 Payment Receipt can be joined on it. Store the full
`~~` chain in the lease row, because verification needs it again at dispatch.

**`allows(lease, effect)` re-runs the checks at dispatch time, not at decision time:**

| Interlock check | derived from | notes |
|---|---|---|
| signature chain valid | `MandateClient.verify(chain, provider_key_lookup, expected_aud, expected_nonce, current_time=now)` | the trusted root key comes from policy config (Risk and Compliance), never from the agent |
| not expired | open (and closed, if set) `exp` | pass `clock_skew_seconds=0`, or record the skew used; the default accepts 5 min past expiry (check 7) |
| amount cap | `payment.amount_range.max` + `currency`, and any pre-set `payment_amount` | the effect's integer cents must be `<= max` and in the same currency; fail closed on a missing or non-int amount, as `DurableLeases.allows` already does |
| merchant | `payment.allowed_payees`, pre-set `payee`, `checkout.allowed_merchants` | compare against the payee the effect actually targets (for Stripe, the account), not against what the agent says |
| bound to this purchase | closed `transaction_id` == hash of the merchant `checkout_jwt` the effect is for | `PaymentMandateChain.verify(expected_transaction_id=...)` |
| budget and occurrences | `payment.budget`, `payment.agent_recurrence` | build `MandateContext` from Interlock's own journal: committed effects under this open-mandate hash, **plus DISPATCHED and AMBIGUOUS ones counted as spent** (fail closed). Convert `budget.max` by the currency's exponent, not `* 100` (check 15) |
| revoked | not in AP2 | a local revocation row keyed by open-mandate hash and closed reference, as in `DurableLeases.revoke`, written by whoever holds operational authority. Revoking the open mandate kills every closed mandate derived from it |
| unknown constraint | spec MUST | any constraint type the adapter does not evaluate means `allows` returns False |

**`describe(lease)`** records exactly what was checked, so the Interlock receipt stands on its own as
audit evidence:
- `vct`
- root `kid` or cert subject
- open-mandate hash and closed reference
- cap and currency
- allowed payee ids
- `exp`
- the `MandateContext` totals used
- the revocation state at check time

**Premises** stay Interlock's: live facts read from the system of record (for Stripe, the
PaymentIntent status and amount already refunded). AP2 constraints say what was allowed. Premises say
whether the world still matches what the agent decided on.

**Exactly once.** Key the effect on the closed-mandate reference. A crash between Stripe accepting the
call and the journal recording it then resolves through Interlock's recovery (idempotency key, or a
lookup) instead of a second presentation. AP2 deliberately leaves this job to stateful parties (checks
2 and 14).

### Refunds specifically

AP2 v0.2 cannot authorize a refund. Three honest options:

1. **Original mandate as evidence, not authority.** Verify the original closed Payment Mandate and the
   processor-signed Payment Receipt. Use them as premises and caps: the refund is for this
   `payment_id` and payee, and cumulative refunds must stay `<= payment_amount`. The authority to
   refund comes from an Interlock approval under Finance's policy. This is accurate today and needs
   nothing AP2 lacks.
2. **Custom mandate type.** The spec allows new mandate and constraint types with a collision-resistant
   name (for example `vct: "dev.interlock.mandate.refund.1"`). Interlock's own verifier could check
   it, but no AP2 verifier would recognize it: unknown constraints fail by spec rule. Label it clearly
   as an extension, not AP2.
3. **Gate the charge, not the refund.** The refund demo stays as it is. A separate AP2 path puts the
   agent's payment effect under a lease derived from an open Payment Mandate.

Recommendation: option 1 for the refund demo, with option 3 as the direct AP2 story. Do not describe
refunds as "AP2-authorized".

## 5. Positioning that the sources support

- **Division of labor, in AP2's own terms.** AP2 carries the proof of what the user authorized:
  signed, bound to one checkout, constrained, and hash-joined for disputes. Its spec assigns
  double-spend prevention, usage tracking for budgets and recurrence, and mandate management to
  stateful parties, and leaves out revocation and refunds entirely. Interlock can be one such stateful
  party at the moment of the effect, for the checks listed next and no others.
- **What is supported (as built in `interlock/integrations/ap2.py`, 2026-09-13).** "Interlock re-verifies
  the AP2 mandate at dispatch and after a crash, honors revocation that AP2 lacks, issues the nonce the
  agent closes with, reserves each closed mandate for one effect and keeps the effects under one open
  mandate within its amount cap (a row in its own store, not cryptographic; an open mandate with no amount
  range authorizes nothing), checks with `observe` that the payment the target acts on is the mandated
  transaction, payee and instrument as the processor reports them, and lets each effect id land at most
  once (after a crash it resends only under the same idempotency key inside the provider's key window,
  otherwise it looks the effect up or reports AMBIGUOUS). Its receipt carries the same `reference` hash as
  the AP2 receipt." Live checks:
  `results/adk_mandate_probes.md`. Budget and recurrence constraints are still not evaluated (no
  MandateContext is passed), so they fail closed.
- **Claims to avoid:**
  - that AP2 has revocation
  - that AP2 covers refunds
  - that the AP2 SDK prevents replay
  - that the User Credential / OpenID4VP path was exercised

## Appendix A: probe script

Run from the AP2 checkout root with the command in the docstring. Keys are generated per run, and
nothing touches the network.

```python
import json, time
from jwcrypto.jwk import JWK
from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.constraints import MandateContext
from ap2.sdk.generated.open_payment_mandate import OpenPaymentMandate, AmountRange, AllowedPayees, AgentRecurrence, Budget
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument

client = MandateClient()
provider = JWK.generate(kty="EC", crv="P-256", kid="agent-provider-key-1")
provider_pub = JWK.from_json(provider.export_public())
agent = JWK.generate(kty="EC", crv="P-256", kid="agent-key-1")
merchant = Merchant(id="merchant_1", name="Demo Merchant", website="https://demo-merchant.example")
card = PaymentInstrument(id="pm_card_visa", type="card", description="Card 4242")
now = int(time.time())

def open_token(constraints, exp):
    m = OpenPaymentMandate(constraints=constraints, cnf={"jwk": json.loads(agent.export_public())}, iat=now, exp=exp)
    return client.create([m], provider)

def close(tok, amount, currency="USD", nonce="n-1", payee=merchant):
    closed = PaymentMandate(transaction_id="checkout-hash-abc", payee=payee,
                            payment_amount=Amount(amount=amount, currency=currency), payment_instrument=card)
    return client.present(holder_key=agent, mandate_token=tok, payloads=[closed], nonce=nonce, aud="credential-provider")

def verify(chain, nonce="n-1", at=None, ctx=None, key=provider_pub):
    try:
        payloads = client.verify(chain, lambda _t: key, expected_aud="credential-provider", expected_nonce=nonce, current_time=at)
    except Exception as e:
        return f"REJECTED: {type(e).__name__}: {e}"
    v = PaymentMandateChain.parse(payloads).verify(expected_transaction_id="checkout-hash-abc", mandate_context=ctx)
    return f"VIOLATIONS: {v}" if v else "ACCEPTED"

def rec_c(n):   # workaround: create() cannot serialize the Frequency enum
    return AgentRecurrence.model_construct(type="payment.agent_recurrence", frequency="ON_DEMAND", max_occurrences=n)

tok = open_token([AmountRange(currency="USD", max=2000, min=0), AllowedPayees(allowed=[merchant])], exp=now + 3600)
good = close(tok, 1500)
print(1, verify(good)); print(2, verify(good))
print(3, verify(close(tok, 2500))); print(4, verify(close(tok, 1500, payee=Merchant(id="m2", name="Other"))))
print(5, verify(close(tok, 1500, currency="EUR"))); print(6, verify(good, at=now + 7200))
print(7, verify(good, at=now + 3840)); print(8, verify(good, nonce="other"))
print(9, verify(good, key=JWK.from_json(JWK.generate(kty="EC", crv="P-256").export_public())))
rtok = open_token([AmountRange(currency="USD", max=2000), rec_c(1), Budget(max=20.00, currency="USD")], exp=now + 3600)
rchain = close(rtok, 1500)
print(11, verify(rchain)); print(12, verify(rchain, ctx=MandateContext(total_uses=0, total_amount=0)))
print(13, verify(rchain, ctx=MandateContext(total_uses=1, total_amount=1500)))
print(14, verify(rchain, ctx=MandateContext(total_uses=0, total_amount=0)))
jtok = open_token([AmountRange(currency="JPY", max=100000), rec_c(None), Budget(max=1000, currency="JPY")], exp=now + 3600)
print(15, verify(close(jtok, 50000, currency="JPY"), ctx=MandateContext()))
```
