"""
AP2 mandate misuse against real Stripe test mode, through the gate and the AP2 SDK. Checks the fixes for two
review findings: re-authorizing after a refusal, and paying more than one refund with one mandate.

    uv run --no-project --python 3.13 --with "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56d" \
        python experiments/adk_mandate_probes.py

Stripe key: STRIPE_SECRET_KEY, else test_mode_api_key from `stripe config --list`. Real: every customer, payment,
refund and refund list is a Stripe test-mode call, and every mandate is signed and verified by the AP2 SDK.
In-process: the crash before the send (SimulatedCrash). The SIGKILL version of that crash is the
hand_refund_during_outage cell of experiments/adk_live.py. No model: the probes play the agent's tool calls.
Writes results/adk_mandate_probes.json and .md.
"""
import datetime, json, os, sys, tempfile, time, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from jwcrypto.jwk import JWK
from backend import config
from interlock import Gate, SimulatedCrash
from interlock.integrations.ap2 import Mandates, close_payment_mandate, open_payment_mandate, stripe_payment
from interlock.journal import effect_id_for
from interlock.receipts import bundle, verify
from interlock.targets.stripe_api import StripeRefunds

AUD = "interlock-refund-gate"
RUN = uuid.uuid4().hex[:8]     # request ids differ per run: Stripe keeps an idempotency key 24h, account-wide


class CrashBeforeSendOnce(StripeRefunds):
    armed = True

    def apply(self, eid, effect, crash_after_effect=False):
        if CrashBeforeSendOnce.armed:
            CrashBeforeSendOnce.armed = False
            raise SimulatedCrash(eid)
        return super().apply(eid, effect, crash_after_effect)


def case(client, name):
    """A $100 test payment, Finance's open mandate for one $20 refund, and a store that verifies it."""
    cus = client.request("POST", "/customers", {"name": name, "description": "Interlock experiments/adk_mandate_probes.py"})
    pi = client.request("POST", "/payment_intents", {"amount": 10000, "currency": "usd", "customer": cus["id"],
                        "payment_method": "pm_card_visa", "payment_method_types": ["card"], "confirm": "true"})
    finance, agent = JWK.generate(kty="EC", crv="P-256", kid="finance-1"), JWK.generate(kty="EC", crv="P-256", kid="agent-1")
    payee, card = {"id": cus["id"], "name": name}, {"id": pi["payment_method"], "type": "card"}
    store = Mandates(os.path.join(tempfile.mkdtemp(prefix="interlock-probe-"), "mandates.db"),
                     {"finance-1": finance.export_public()}, AUD, observe=stripe_payment(client))

    def open_mandate(cap=2000):
        if cap is not None:
            return open_payment_mandate(finance, agent.export_public(as_dict=True), cap, "USD", payee, card, int(time.time()) + 600)
        from ap2.sdk.generated.open_payment_mandate import AllowedPayees, AllowedPaymentInstruments, OpenPaymentMandate
        from ap2.sdk.mandate import MandateClient       # payee and card constraints, no AmountRange
        return MandateClient().create([OpenPaymentMandate(
            constraints=[AllowedPayees(allowed=[payee]), AllowedPaymentInstruments(allowed=[card])],
            cnf={"jwk": agent.export_public(as_dict=True)}, iat=int(time.time()), exp=int(time.time()) + 600)], finance)

    def authorize(open_token, transaction=None):    # what adk_live.py's authorize_refund tool does on every call
        nonce = store.challenge()
        return store.register(close_payment_mandate(agent, open_token, 2000, "USD", payee, card, transaction or pi["id"],
                                                    nonce, AUD), nonce)
    effect = {"payment_intent": pi["id"], "amount": 2000, "currency": "USD", "payee": cus["id"], "instrument": card["id"],
              "transaction_id": pi["id"]}
    return pi["id"], store, open_mandate, authorize, effect


def stripe_state(client, pi):
    time.sleep(2)
    rs = StripeRefunds(client, pi).refunds()
    return {"refunds": [{"id": r["id"], "amount": r["amount"], "interlock_effect_id": r["metadata"].get("interlock_effect_id")}
                        for r in sorted(rs, key=lambda r: r["created"])], "total_cents": sum(r["amount"] for r in rs)}


def rerun_after_refusal(client):
    pi, store, open_mandate, authorize, effect = case(client, "probe: re-authorize after refusal")
    journal, target, rid, steps = os.path.join(os.path.dirname(store.path), "journal.db"), CrashBeforeSendOnce(client, pi), f"refund:case-4471-{RUN}", []
    finance_open = open_mandate()
    lease1 = authorize(finance_open)
    p = {"agent": "adk:inv-1/call-1", "lease": lease1, "request_id": rid, "premises": target.capture(), "effect": effect}
    try:
        Gate(target, journal, store, claim_ttl=40).submit(p)
    except SimulatedCrash:
        steps.append("agent dies right before the refund POST (DISPATCHED is on disk)")
    hand = client.request("POST", "/refunds", {"payment_intent": pi, "amount": 2000})["id"]
    steps.append(f"support refunds $20 by hand: {hand}")
    gate = Gate(target, journal, store, claim_ttl=40)
    steps.append(f"restart, recover(): {gate.recover()}")
    lease2 = authorize(finance_open)
    steps.append(f"agent calls authorize_refund again: a new closed mandate {lease2} (differs: {lease2 != lease1}), same open mandate")
    again = gate.submit({**p, "agent": "adk:inv-1/call-4", "lease": lease2, "premises": target.capture()})
    steps.append(f"agent calls issue_refund again, same request id: {again}")
    b = bundle(gate.journal, effect_id_for(p))
    v = verify(b)
    before_new_approval = stripe_state(client, pi)
    lease3 = authorize(open_mandate())
    approved = gate.submit({**p, "agent": "adk:inv-2/call-1", "lease": lease3, "premises": target.capture()})
    steps.append(f"Finance reviews the case and issues a NEW open mandate; issue_refund under it: {approved}")
    return {"payment_intent": pi, "steps": steps, "resubmit_status": again, "entries_before_new_approval": [e["kind"] for e in b["entries"]],
            "verify_before_new_approval": {k: v[k] for k in ("valid", "happened", "happened_once", "refused")},
            "stripe_before_new_approval": before_new_approval, "new_approval_status": approved,
            "stripe_after_new_approval": stripe_state(client, pi),
            "held": again.startswith("REFUSED") and before_new_approval["total_cents"] == 2000}


def reuse(client):
    pi, store, open_mandate, authorize, effect = case(client, "probe: one mandate, many refunds")
    journal, target, finance_open = os.path.join(os.path.dirname(store.path), "journal.db"), StripeRefunds(client, pi), open_mandate()
    lease = authorize(finance_open)
    out = []
    for rid, l in ((f"refund:case-1-{RUN}", lease), (f"refund:case-1-{RUN}-retry-by-new-invocation", lease)):
        out.append((rid, "same closed mandate", Gate(target, journal, store).submit(
            {"agent": "a", "lease": l, "request_id": rid, "premises": target.capture(), "effect": effect})))
    out.append((f"refund:case-2-{RUN}", "second closing of the same open mandate", Gate(target, journal, store).submit(
        {"agent": "a", "lease": authorize(finance_open), "request_id": f"refund:case-2-{RUN}", "premises": target.capture(), "effect": effect})))
    nonce_checks = {}
    for label, nonce in (("agent-picked nonce", "case-4471"),):
        try:
            store.register(close_payment_mandate(JWK.generate(kty="EC", crv="P-256"), finance_open, 2000, "USD",
                                                 {"id": "x", "name": "x"}, {"id": "y", "type": "card"}, pi, nonce, AUD), nonce)
            nonce_checks[label] = "accepted"
        except ValueError as e:
            nonce_checks[label] = f"refused: {e}"
    s = stripe_state(client, pi)
    return {"payment_intent": pi, "submits": out, "nonce": nonce_checks, "stripe": s,
            "held": [o[2] for o in out] == ["COMMITTED", "REFUSED:lease_used", "REFUSED:lease_used"] and s["total_cents"] == 2000}


def other_customers_payment(client):
    """Finance's mandate is for customer A's payment. The refund is aimed at customer B's PaymentIntent."""
    piA, store, open_mandate, authorize, effect = case(client, "probe: customer A")
    cusB = client.request("POST", "/customers", {"name": "probe: customer B", "description": "Interlock experiments/adk_mandate_probes.py"})
    piB = client.request("POST", "/payment_intents", {"amount": 10000, "currency": "usd", "customer": cusB["id"],
                         "payment_method": "pm_card_visa", "payment_method_types": ["card"], "confirm": "true"})["id"]
    journal, target, finance_open, out = os.path.join(os.path.dirname(store.path), "journal.db"), StripeRefunds(client, piB), open_mandate(), []
    for how, lease, eff in (
            ("effect names B's PaymentIntent; its transaction_id, payee and card are A's", authorize(finance_open),
             {**effect, "payment_intent": piB}),
            ("the agent closes the mandate with B's PaymentIntent as the transaction; payee and card are A's",
             authorize(finance_open, piB), {**effect, "payment_intent": piB, "transaction_id": piB})):
        rid = f"refund:other-customer-{RUN}-{len(out)}"
        status = Gate(target, journal, store).submit({"agent": "a", "lease": lease, "request_id": rid, "premises": target.capture(), "effect": eff})
        out.append({"how": how, "gate": status, "problems": store.check(lease, eff)["problems"]})
    a, b = stripe_state(client, piA), stripe_state(client, piB)
    return {"payment_intent_a": piA, "payment_intent_b": piB, "customer_b": cusB["id"], "attempts": out, "stripe_a": a, "stripe_b": b,
            "held": all(o["gate"].startswith("REFUSED") for o in out) and a["total_cents"] == b["total_cents"] == 0}


def no_amount_cap(client):
    """An open mandate with allowed payee and card but no AmountRange, closed three times."""
    pi, store, open_mandate, authorize, effect = case(client, "probe: open mandate without an amount range")
    journal, target, finance_open, out = os.path.join(os.path.dirname(store.path), "journal.db"), StripeRefunds(client, pi), open_mandate(None), []
    for i in range(3):
        lease, rid = authorize(finance_open), f"refund:no-cap-{RUN}-{i}"
        out.append((rid, Gate(target, journal, store).submit({"agent": "a", "lease": lease, "request_id": rid,
                                                               "premises": target.capture(), "effect": effect})))
    s = stripe_state(client, pi)
    return {"payment_intent": pi, "submits": out, "problems": store.check(lease, effect)["problems"], "stripe": s,
            "held": all(st.startswith("REFUSED") for _, st in out) and s["total_cents"] == 0}


def markdown(r):
    a, b = r["rerun_after_refusal"], r["one_mandate_many_refunds"]
    c, d = r["other_customers_payment"], r["no_amount_cap"]
    refunds = lambda s: ", ".join(f"`{x['id']}` {x['amount']}" + (" (Interlock)" if x["interlock_effect_id"] else " (hand)") for x in s["refunds"])
    return f"""# Results: AP2 mandate misuse, real Stripe test mode

Generated {r['generated']} by `experiments/adk_mandate_probes.py`. AP2 SDK at `e1ea56d` signs and verifies every
mandate; every payment, refund and refund list is a Stripe test-mode call. The crash before the send is in-process
(`SimulatedCrash`); the SIGKILL version is `hand_refund_during_outage` in `results/adk_live.md`. No model: the probe
makes the tool calls a model could make. Finance's open mandate caps one refund at $20 on a $100 payment.

## 1. Re-authorizing after a refusal: {'held' if a['held'] else 'NOT HELD'}

PaymentIntent `{a['payment_intent']}`.

{chr(10).join(f'{i + 1}. {s}' for i, s in enumerate(a['steps']))}

Before the new approval: Stripe {refunds(a['stripe_before_new_approval'])}, total {a['stripe_before_new_approval']['total_cents']} cents.
Journal {', '.join(a['entries_before_new_approval'])}; verify {a['verify_before_new_approval']}.
After Finance's new mandate: Stripe {refunds(a['stripe_after_new_approval'])}, total {a['stripe_after_new_approval']['total_cents']} cents
(the second $20 is what the new approval allowed).

Before the fix the same steps gave `COMMITTED` on the resubmit, two $20 refunds, and a receipt saying
`happened_once=True`: the gate took the new closed mandate for a new approval and read fresh premises that already
included the hand refund. Now `Mandates.authority()` names the open mandate, and the gate holds a re-closing of it to
the premises of the first decision.

## 2. One mandate, many refunds: {'held' if b['held'] else 'NOT HELD'}

PaymentIntent `{b['payment_intent']}`.

| request id | lease | gate |
|---|---|---|
""" + "\n".join(f"| `{rid}` | {how} | `{st}` |" for rid, how, st in b["submits"]) + f"""

Stripe: {refunds(b['stripe'])}, total {b['stripe']['total_cents']} cents. Nonce: {b['nonce']}.

Before the fix all three submits were `COMMITTED` and Stripe held three $20 refunds on one $20 mandate. Now the gate
calls `Mandates.reserve()` right before it sends: one effect id per closed mandate, and the effects under one open
mandate stay within its AmountRange max. That reading of the range as a total is the adapter's policy; AP2 v0.2
defines it per payment.

## 3. A refund aimed at another customer's payment: {'held' if c['held'] else 'NOT HELD'}

Finance's mandate: customer A, A's card, transaction A's PaymentIntent `{c['payment_intent_a']}`. Customer B
(`{c['customer_b']}`) has PaymentIntent `{c['payment_intent_b']}`. The Stripe target sends to `effect["payment_intent"]`.

| attempt | gate | problems found |
|---|---|---|
""" + "\n".join(f"| {o['how']} | `{o['gate']}` | {'; '.join(o['problems'])} |" for o in c["attempts"]) + f"""

Stripe after both: A {c['stripe_a']['total_cents']} cents, B {c['stripe_b']['total_cents']} cents.

Before the fix the adapter compared only the effect's own fields with the mandate, never the PaymentIntent the target
sends to. The review's probe of the first attempt got `COMMITTED`, and Stripe held refund `re_3UFMw888KhIqqdFL0Mo2fCNz`
(2000 cents) on customer B's PaymentIntent `pi_3UFMw888KhIqqdFL0mLfVBSW`. Now `Mandates(observe=stripe_payment(client))`
reads that PaymentIntent from Stripe on every check, and its id, customer, card and currency must be the mandate's.

## 4. An open mandate with no amount range: {'held' if d['held'] else 'NOT HELD'}

PaymentIntent `{d['payment_intent']}`. The open mandate allows this customer and card and has no AmountRange.

| request id | gate |
|---|---|
""" + "\n".join(f"| `{rid}` | `{st}` |" for rid, st in d["submits"]) + f"""

Problems found: {'; '.join(d['problems'])}. Stripe: {d['stripe']['total_cents']} cents refunded.

Before the fix a missing range meant no cap: the review's probe closed such a mandate three times and got `COMMITTED`
three times, three $20 refunds (6000 cents) on one PaymentIntent. Now an open mandate without an AmountRange max
authorizes nothing through the gate.

## Limits

- A reservation is not released when its effect is refused, so a refused refund still counts against the open
  mandate. A person issues a new mandate.
- The store is one SQLite file. Reservations are atomic across processes on one machine, not across machines.
- Revocation and reservations are rows in that store, trusted as far as the store is; they are not cryptographic.
"""


def main():
    client = config.stripe()
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "rerun_after_refusal": rerun_after_refusal(client), "one_mandate_many_refunds": reuse(client),
           "other_customers_payment": other_customers_payment(client), "no_amount_cap": no_amount_cap(client)}
    with open(os.path.join(ROOT, "results", "adk_mandate_probes.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    with open(os.path.join(ROOT, "results", "adk_mandate_probes.md"), "w") as f:
        f.write(markdown(out))
    print(markdown(out))


if __name__ == "__main__":
    main()
