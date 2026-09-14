"""
AP2 mandates as Interlock leases: the gate re-verifies the mandate when the effect is sent, and again after a crash.

AP2 (Agent Payments Protocol, v0.2) carries proof of what was authorized: an open Payment Mandate signed by a
trusted surface (amount range, allowed payees and instruments, expiry, and the agent's key in `cnf`), closed by
the agent with the exact payment. AP2 keeps no state. Its verifier accepts the same presentation twice, it has
no revocation, and it cannot know whether the payment already happened. This store and the gate add, at the
moment of the effect:

    - revocation of a closed or an open mandate (a row here)
    - the nonce is issued by this store (challenge()) and good for one register(), not chosen by the agent
    - one closed mandate pays one effect id, and the effects under one open mandate together stay within its
      AmountRange max (reserve(), called by the gate right before it sends). AP2 defines that range per payment;
      reading it as the open mandate's total is this adapter's policy. An open mandate with no AmountRange max
      has no total to count against, so it authorizes nothing here
    - authority(lease) is the open mandate, so an agent that re-closes the same mandate after a refusal is held
      to the facts of its first decision, and refused again. A new open mandate, from a person, is a new decision

    mandates = Mandates("mandates.db", trusted_keys={"finance-1": public_jwk_json}, audience="interlock",
                        observe=stripe_payment(client))  # reads the PaymentIntent the target will refund
    nonce = mandates.challenge()                     # hand to the agent; it closes the mandate with this nonce
    lease = mandates.register(chain, nonce)          # the closed-mandate reference, as AP2 receipts use it
    gate = Gate(target, "journal.db", mandates)      # proposal["lease"] = lease
    mandates.revoke(open_mandate_id(chain))          # whoever holds operational authority withdraws it

The effect must name what it pays: amount (integer minor units), currency, payee (id), instrument (id) and
transaction_id. allows(lease, effect) is True only if, when the gate asks:

    - the chain verifies against a trusted root key, looked up by `kid` in `trusted_keys` (policy config, never
      the agent): every hop's signature, the sd_hash binding between hops, aud and nonce on the closed hop, and
      exp and iat with zero clock skew (the SDK's default accepts 300 s past expiry)
    - AP2's own evaluator finds no violation of the open mandate's constraints and pre-set claims. No usage
      context is passed, so budget and recurrence constraints always fail: counting spend is not done here yet
    - the effect's fields equal the closed mandate's: amount, currency, payee, instrument, transaction_id
    - observe(effect) reads the payment the target will actually act on from the system of record (for Stripe,
      stripe_payment() reads the PaymentIntent in effect["payment_intent"]), and its transaction id, payee,
      instrument and currency are the mandate's too. Without observe nothing is allowed: the effect's fields are
      the caller's, and a refund sent to another customer's payment could otherwise match them
    - the open mandate has an AmountRange with a max
    - neither the closed mandate nor the open mandate it closes is revoked in this store

describe(lease) is recorded by the gate next to every check: the mandate reference and open-mandate id, the
root kid, cap, payee, instrument, expiry, revocation, and every problem found. So a receipt joins to an AP2
Payment Receipt on `reference`, and shows what was checked when the effect fired.

What is cryptographic and what is not. The signatures, hop binding, aud, nonce and expiry are verified by the
AP2 SDK against the trusted key. Revocation is a row in this store, trusted as far as the store is. That the
effect matches the mandate is a comparison, not a signature: with the effect's fields, and with what observe
reads from the payment provider. observe must read the same object the target sends to. AP2 v0.2 defines no
refund mandate; using a Payment Mandate to authorize a refund payout is this adapter's convention, not AP2's.

Needs the AP2 SDK (not the unrelated `ap2` package on PyPI):
    pip install "ap2 @ git+https://github.com/google-agentic-commerce/AP2@e1ea56d"
"""
import base64, contextlib, hashlib, secrets, sqlite3, time

SKEW = 0            # seconds past exp a mandate is still accepted


def _sha256_b64url(text):
    return base64.urlsafe_b64encode(hashlib.sha256(text.encode()).digest()).rstrip(b"=").decode()


def mandate_reference(chain):
    """SHA-256 (base64url) of the closed-mandate JWT: the `reference` an AP2 receipt binds to."""
    return _sha256_b64url(chain.rsplit("~~", 1)[-1].split("~", 1)[0])


def open_mandate_id(chain):
    """SHA-256 (base64url) of the open mandate's issuer-signed JWT. Stable across every closing of it."""
    return _sha256_b64url(chain.split("~~", 1)[0].split("~", 1)[0])


def verify_chain(chain, trusted_keys, audience, nonce, now):
    """
    The AP2 SDK's verification of an open-then-closed Payment Mandate chain. Returns (open, closed, violations)
    as plain dicts and a list of strings; raises if the chain does not verify at all.
    """
    try:
        from ap2.sdk.mandate import MandateClient
        from ap2.sdk.payment_mandate_chain import PaymentMandateChain
        from jwcrypto.jwk import JWK
    except ImportError as e:
        raise ImportError(f"{e}. Install the AP2 SDK: {__doc__.rsplit('pip install', 1)[1].strip()}") from None

    def root_key(token):
        kid = token.header.get("kid")
        if kid not in trusted_keys:
            raise ValueError(f"root key {kid!r} is not a trusted key")
        return JWK.from_json(trusted_keys[kid]) if isinstance(trusted_keys[kid], str) else JWK(**trusted_keys[kid])

    payloads = MandateClient().verify(chain, root_key, expected_aud=audience, expected_nonce=nonce,
                                      clock_skew_seconds=SKEW, current_time=int(now))
    parsed = PaymentMandateChain.parse(payloads)
    dump = lambda m: m.model_dump(mode="json", exclude_none=True)
    return dump(parsed.open_mandate), dump(parsed.closed_mandate), parsed.verify()


def open_payment_mandate(issuer_key, agent_public_jwk, cap, currency, payee, instrument, exp, iat=None):
    """
    Issuer side (the approver's trusted surface): an open Payment Mandate capped at `cap` minor units, for one
    payee ({id, name}) and one instrument ({id, type}), that only the holder of `agent_public_jwk` can close.
    """
    from ap2.sdk.generated.open_payment_mandate import AllowedPayees, AllowedPaymentInstruments, AmountRange, OpenPaymentMandate
    from ap2.sdk.mandate import MandateClient
    m = OpenPaymentMandate(constraints=[AmountRange(currency=currency, max=cap, min=1), AllowedPayees(allowed=[payee]),
                                        AllowedPaymentInstruments(allowed=[instrument])],
                           cnf={"jwk": agent_public_jwk}, iat=int(time.time() if iat is None else iat), exp=int(exp))
    return MandateClient().create([m], issuer_key)


def close_payment_mandate(agent_key, open_token, amount, currency, payee, instrument, transaction_id, nonce, audience):
    """Agent side: close the open mandate with the exact payment. Returns the `~~` chain a verifier checks."""
    from ap2.sdk.generated.payment_mandate import PaymentMandate
    from ap2.sdk.mandate import MandateClient
    closed = PaymentMandate(transaction_id=transaction_id, payee=payee, payment_instrument=instrument,
                            payment_amount={"amount": amount, "currency": currency})
    return MandateClient().present(holder_key=agent_key, mandate_token=open_token, payloads=[closed], nonce=nonce,
                                   aud=audience)


def stripe_payment(client, field="payment_intent"):
    """
    observe= for a Stripe target that sends to the PaymentIntent in effect[field]: that PaymentIntent as Stripe
    has it, so the payment actually refunded must be the mandate's transaction, customer and card.
    """
    def observe(effect):
        p = client.request("GET", f"/payment_intents/{effect[field]}")
        return {"transaction_id": p["id"], "payee": p.get("customer"), "instrument": p.get("payment_method"),
                "currency": p["currency"].upper()}
    return observe


def _mandated(closed):
    return {"amount": closed["payment_amount"]["amount"], "currency": closed["payment_amount"]["currency"].upper(),
            "payee": closed["payee"]["id"], "instrument": closed["payment_instrument"]["id"],
            "transaction_id": closed["transaction_id"]}


def _mismatches(closed, effect):
    want = _mandated(closed)
    got = {k: effect.get(k) for k in want}
    got["currency"] = str(got["currency"]).upper()
    out = [f"effect {k} is {got[k]!r}, the mandate says {want[k]!r}" for k in want if got[k] != want[k]]
    if type(effect.get("amount")) is not int:
        out.append(f"effect amount {effect.get('amount')!r} is not an integer number of minor units")
    return out


class Mandates:
    """A lease store for Gate whose leases are AP2 Payment Mandate chains."""

    def __init__(self, path, trusted_keys, audience, observe=None, clock=time.time, verify=verify_chain):
        self.path, self.trusted_keys, self.audience, self.clock, self.verify = path, trusted_keys, audience, clock, verify
        self.observe = observe
        self._seen = {}
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS mandates (lease_id TEXT PRIMARY KEY, chain TEXT NOT NULL, "
                       "nonce TEXT NOT NULL, open_id TEXT NOT NULL, registered REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS revocations (id TEXT PRIMARY KEY, at REAL NOT NULL, by TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, issued REAL NOT NULL, used REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS uses (lease_id TEXT NOT NULL, effect_id TEXT NOT NULL, open_id TEXT NOT NULL, "
                       "amount INTEGER NOT NULL, at REAL NOT NULL, PRIMARY KEY (lease_id, effect_id))")

    @contextlib.contextmanager
    def _db(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            yield db

    def challenge(self):
        """A fresh nonce from this verifier, for the agent to close the mandate with. Good for one register()."""
        nonce = secrets.token_urlsafe(18)
        with self._db() as db:
            db.execute("INSERT INTO nonces VALUES (?, ?, NULL)", (nonce, time.time()))
        return nonce

    def register(self, chain, nonce):
        """
        Store a presented chain closed with `nonce`, which must come from challenge() and not be used yet.
        Returns its reference, the lease id. Raises ValueError for any other nonce.
        """
        lease = mandate_reference(chain)
        with self._db() as db:
            if not db.execute("UPDATE nonces SET used = ? WHERE nonce = ? AND used IS NULL", (time.time(), nonce)).rowcount:
                raise ValueError("nonce was not issued by this verifier, or was already used")
            db.execute("INSERT OR IGNORE INTO mandates VALUES (?, ?, ?, ?, ?)",
                       (lease, chain, nonce, open_mandate_id(chain), time.time()))
        return lease

    def authority(self, lease_id):
        """The approval a lease stands for: the open mandate it closes. The gate binds premises to this."""
        with self._db() as db:
            row = db.execute("SELECT open_id FROM mandates WHERE lease_id = ?", (lease_id,)).fetchone()
        return row[0] if row else lease_id

    def reserve(self, lease_id, effect_id, effect):
        """
        Called by the gate right before it dispatches. Binds the closed mandate to this effect id and counts the
        amount against the open mandate's cap (its AmountRange max, the total it approves). Returns problems;
        empty means reserved. A reservation stays when the effect is later refused: a new approval is a new mandate.
        """
        cap = next((c.get("max") for c in self.check(lease_id).get("constraints") or []
                    if c.get("type") == "payment.amount_range"), None)
        if cap is None:                             # no range, no total to hold the closings to: fail closed
            return ["open mandate has no amount range with a max, so its closings have no cap to count against"]
        amount = effect.get("amount")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")           # one reserver at a time, across processes
            row = db.execute("SELECT open_id FROM mandates WHERE lease_id = ?", (lease_id,)).fetchone()
            if row is None:
                return ["mandate not registered"]
            other = db.execute("SELECT effect_id FROM uses WHERE lease_id = ? AND effect_id != ?", (lease_id, effect_id)).fetchone()
            if other:
                return [f"closed mandate already used by effect {other[0]}"]
            spent = db.execute("SELECT COALESCE(SUM(a), 0) FROM (SELECT MAX(amount) AS a FROM uses WHERE open_id = ? "
                               "AND effect_id != ? GROUP BY effect_id)", (row[0], effect_id)).fetchone()[0]
            if spent + amount > cap:
                return [f"open mandate cap {cap}: {spent} already reserved by other effects, {amount} more asked"]
            db.execute("INSERT OR IGNORE INTO uses VALUES (?, ?, ?, ?, ?)", (lease_id, effect_id, row[0], amount, time.time()))
        return []

    def revoke(self, mandate_id, by=None):
        """Revoke a closed mandate (its reference) or an open one (open_mandate_id), which ends every closing of it."""
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO revocations VALUES (?, ?, ?)", (mandate_id, time.time(), by))

    def check(self, lease_id, effect=None):
        """Every check, with what it read. `problems` empty means the mandate covers this effect right now."""
        with self._db() as db:
            row = db.execute("SELECT chain, nonce, open_id FROM mandates WHERE lease_id = ?", (lease_id,)).fetchone()
            if row is None:
                return {"lease_id": lease_id, "revoked": None, "max_cents": None, "problems": ["mandate not registered"]}
            chain, nonce, open_id = row
            revoked = db.execute("SELECT id, at, by FROM revocations WHERE id IN (?, ?) ORDER BY at LIMIT 1",
                                 (lease_id, open_id)).fetchone()
        now = self.clock()
        out = {"lease_id": lease_id, "mandate_reference": lease_id, "open_mandate_id": open_id, "checked_at": now,
               "clock_skew_seconds": SKEW, "revoked": revoked and {"id": revoked[0], "at": revoked[1], "by": revoked[2]},
               "max_cents": None, "problems": []}
        if revoked:
            out["problems"].append(f"{'open' if revoked[0] == open_id else 'closed'} mandate revoked")
        try:
            open_m, closed, violations = self.verify(chain, self.trusted_keys, self.audience, nonce, now)
        except Exception as e:                  # a chain that does not verify authorizes nothing
            out["problems"].append(f"mandate did not verify: {type(e).__name__}: {e}")
            return out
        out.update(verified=True, vct=[open_m.get("vct"), closed.get("vct")], exp=open_m.get("exp"),
                   constraints=open_m.get("constraints"), payee=closed["payee"], instrument=closed["payment_instrument"],
                   transaction_id=closed["transaction_id"], amount=closed["payment_amount"],
                   max_cents=closed["payment_amount"]["amount"])
        out["problems"] += violations
        if not any(c.get("type") == "payment.amount_range" and c.get("max") is not None for c in open_m.get("constraints") or []):
            out["problems"].append("open mandate has no amount range with a max, so its closings have no cap to count against")
        if effect is not None:
            out["problems"] += _mismatches(closed, effect) + self._observed(out, closed, effect)
        return out

    def _observed(self, out, closed, effect):
        """The payment the target will act on, read from the system of record, must be the mandated one."""
        if self.observe is None:
            return ["no observe(effect) configured: nothing binds the payment the target acts on to this mandate"]
        try:
            out["observed"] = seen = self.observe(effect)
        except Exception as e:
            return [f"could not read the payment from the system of record: {type(e).__name__}: {e}"]
        want = _mandated(closed)
        return [f"system of record: {k} is {seen[k]!r}, the mandate says {want[k]!r}" for k in seen if seen[k] != want.get(k)]

    def allows(self, lease_id, effect):
        seen = self._seen[lease_id] = self.check(lease_id, effect if isinstance(effect, dict) else {})
        return not seen["problems"]

    def describe(self, lease_id):
        """The check allows() just made (the gate calls the two together), else a fresh one without an effect."""
        return self._seen.pop(lease_id, None) or self.check(lease_id)

    def is_live(self, lease_id):
        return not self.check(lease_id)["problems"]
