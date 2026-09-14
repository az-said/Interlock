# Authority, receipts and premise events: what to use

Research date 2026-09-13. Every version, license and behavior below was checked against PyPI JSON, the GitHub API, repo
LICENSE/README files or the vendor docs on that date. Two items were run locally (marked MEASURED).

Where these plug in, in terms of the current gate (interlock/gate.py, read-only):

- Authority: `gate._lease_seen` calls `leases.allows(lease, effect)` and `leases.describe(lease)` at dispatch, and recovery
  calls the same thing again. Any engine below becomes that `allows`/`describe` pair. What `describe` returns is what the
  receipt stores as "the grant record read with it", so it has to carry a policy version.
- Premises: `target.validate_premises(decided_on, eid)` runs right before send and again on recovery. That pull check stays
  the source of truth. Push events can only make a violation show up sooner: they mark in-flight decisions stale so the
  workflow can re-plan before it reaches send. They never replace the send-time read.
- Receipts: `receipts.py` hash-chains entries per effect and signs the head with HMAC. This proves the chain is internally
  consistent. It does not stop the journal owner from rebuilding or truncating a chain. A transparency log closes that
  gap by publishing a signed tree head that covers every receipt head.

## 1. Authority engines

| | Cedar via cedarpy | OpenFGA | OPA |
|---|---|---|---|
| License | Apache-2.0 (cedar-policy/cedar and k9securityio/cedar-py) | Apache-2.0 (server and python-sdk) | Apache-2.0 |
| Latest | cedar v4.12.0 (2026-07-28); cedarpy 4.12.0 on PyPI (2026-09-12) | server v1.20.0 (2026-09-08); openfga-sdk 0.10.4 | v1.20.2 (2026-09-03) |
| Python | In-process Rust via PyO3 wheels. Linux x86_64/aarch64 3.10-3.14, macOS 3.11-3.14 | HTTP/gRPC client to a Go server | HTTP to a Go server (opa-python-client 2.1.0 is MIT and third party; plain HTTP is enough) |
| Extra infra | None | An OpenFGA server. Storage: PostgreSQL 14+, MySQL 8, SQLite beta. In-memory is dev only | An OPA server or sidecar, plus bundle distribution |
| Model | Policies over principal/action/resource with context and entity attributes. Default deny. | Relationship tuples (Zanzibar), with CEL conditions on tuples | Rego over arbitrary JSON input |

MEASURED (scratch script, uv, Python 3.14, macOS arm64): `cedarpy.is_authorized` with the policy
`permit(principal == Agent::"refund-bot", action == Action::"refund", resource) when { context.amount <= principal.limit && !principal.revoked }`
returned Allow for amount 30 and Deny for amount 80. Steady state was 0.092 ms per call; the first call was 4.1 ms.
`openfga-sdk` also installs and imports on 3.14 and exposes `ConsistencyPreference`.

How each plugs into dispatch-time and recovery-time checks:

- Cedar. `allows(lease, effect)` becomes `is_authorized({principal: agent, action: effect kind, resource: target object,
  context: {amount, ...}}, policies, entities)`. The trick is that policies and entities are plain text/JSON passed in on
  every call. So the runtime loads them from Postgres rows (a `policies` table versioned by hash, and grant/lease rows as
  entities) inside the same transaction that claims the dispatch. A revoke is an `UPDATE` that commits before the
  dispatch transaction reads, so the check sees it. There is no cache to go stale. `describe` returns the policy set hash,
  the entity rows and the `diagnostics.reasons` (the ids of the policies that fired). A verifier can re-run the exact
  decision offline, because the inputs are in the receipt. That is a real improvement on today's attestation-only lease
  check. `is_authorized_partial` can also tell an agent at plan time what would be allowed.
- OpenFGA. `allows` becomes `Check(user=agent, relation=can_refund, object=charge:..., context={amount})`, using a
  conditional tuple for the limit. Two caveats come straight from its docs. First, the default `MINIMIZE_LATENCY` can serve
  a cached answer that ignores a tuple you just wrote, so the gate must pass `HIGHER_CONSISTENCY`. (With the cache
  disabled, which is the default, everything is strongly consistent.) Second, the decision lives in another service's
  database, so it is not atomic with our dispatch row. A revoke can commit between the Check and the send. That window is
  the same one Temporal plus a pre-send check has, and it is smaller only if the check sits right next to the send.
  Condition context is limited to 32KB.
- OPA. `allows` becomes `POST /v1/data/interlock/allow` with `{"input": {...}}`. The response carries a `decision_id`,
  and `?provenance=true` returns the bundle `revision`, which goes in `describe`. Decision logs are buffered, and OPA
  drops events past `max_decisions_per_second`, so they cannot be the audit record. Our journal has to be. Policy data
  arrives by bundle polling, so a revoke has propagation lag unless it is sent as `input` on each call. At that point the
  runtime holds the data anyway, and Cedar does the same job in-process.

Verdict: Cedar through cedarpy. It needs no service, it reads authority from the same Postgres transaction as the dispatch
claim (no revoke race), and it makes the authority check re-derivable from the receipt. OpenFGA is worth adding only if a
deployment already runs it for relationship-heavy permissions. In that case, wrap it in the same `allows`/`describe`
interface with `HIGHER_CONSISTENCY`, and label the revoke window. OPA brings a server and best-effort logs for no gain here.

## 2. Verifiable receipts: transparency logs

| | License / status | Storage | Python |
|---|---|---|---|
| Sigstore Rekor v1 (sigstore/rekor) | Apache-2.0, v1.5.4 (2026-08-20) | Built on Trillian, so MySQL | Go server. `sigstore` 4.5.0 on PyPI (Apache-2.0) is a signing/verification client for artifacts, not a generic log API |
| Rekor v2 (sigstore/rekor-tiles) | Apache-2.0, v2.3.0 (2026-06-10) | Built on Tessera: GCP (Spanner or CloudSQL), AWS (Aurora/RDS MySQL), POSIX | Go server; entries are Sigstore types (signed artifacts, DSSE) |
| Trillian (google/trillian) | Apache-2.0, v1.7.3 (2026-03-30) | MySQL/MariaDB. README: "Trillian is in maintenance mode... We recommend that any new log operators first try Tessera." | gRPC only |
| Tessera (transparency-dev/tessera) | Apache-2.0; README calls it "generally available and production ready" | AWS, GCP, POSIX filesystem. No Postgres driver | Go library, not a service |
| pymerkle 6.1.0 | GPL-3.0 (GPLv3+ classifier); last release 2023-08-30 | Storage agnostic; RFC 9162 hashing; inclusion and consistency proofs | Pure Python |
| merkletools 1.0.3 (Tierion) | MIT; repo last pushed 2023-07-19 | In memory | Pure Python, Bitcoin-style tree, no consistency proofs |

What we actually need is much smaller than any of these. It comes down to three things. (1) An append-only list of
receipt heads (`sha256(effect_id || last_entry_hash)`). (2) A signed tree head at size N, so a holder can later check
that the log only grew. (3) An inclusion proof for one effect. RFC 9162 section 2 defines the hashing and both proofs in a
few dozen lines of `hashlib` (leaf = `H(0x00||d)`, node = `H(0x01||l||r)`). The C2SP tlog-checkpoint format
(origin line, tree size, base64 root hash, then a signed-note signature) is the interoperable way to publish the head.
With an Ed25519 note key, any Go tooling in the transparency-dev ecosystem can check it, and so can a witness.

How it plugs in:
- On each terminal journal entry (COMMITTED, REFUSED, AMBIGUOUS resolved), the runtime appends the receipt head as a leaf
  row in a Postgres `tlog_leaves(index bigserial, hash bytea)` table in the same transaction. A single writer then
  periodically computes the root and writes a checkpoint row.
- The receipt bundle gains `{leaf_index, checkpoint, inclusion_proof}`. `receipts.verify` recomputes the root from the
  leaf and proof and compares it with the checkpoint.
- Publishing the checkpoint outside our database is what upgrades "consistent" to "not rewritten". Options: hand it to the
  counterparty, post it to a witness, or, if the checkpoint is ever signed as a Sigstore artifact, log it to public Rekor.
  Without that, a journal owner can still rebuild both log and checkpoints.
- Signature: the checkpoint signature has to be asymmetric (Ed25519) for third parties to verify it. Python's stdlib has
  no Ed25519. `cryptography` (Apache-2.0/BSD) is the only dependency this adds. The existing HMAC mode can stay for
  shared-key counterparties.

Verdict: do not run Rekor, Trillian or Tessera. Each needs a Go server plus MySQL, cloud storage or a filesystem log, which
breaks the Postgres-only rule, and Trillian is in maintenance. Do not take pymerkle: GPL-3.0 is a licensing problem for a
library others embed, and it has had no release since 2023. Write RFC 9162 Merkle hashing and proofs directly (stdlib),
store leaves in Postgres, and emit C2SP checkpoints signed with `cryptography` Ed25519. Tessera's POSIX driver is the
upgrade path if volume ever needs a real log server.

## 3. Pushing premise changes

Stripe webhooks (docs.stripe.com/webhooks):
- Signed with the `Stripe-Signature` header (`t=` timestamp plus `v1=` HMAC-SHA256 of `t.body` using the `whsec_` secret).
  Libraries default to a 5 minute tolerance.
- Stripe "doesn't guarantee the delivery of events in the order that they're generated". Endpoints "might occasionally
  receive the same event more than once", and sometimes two separate Event objects are sent for one change.
- Retries last up to three days in live mode, but a sandbox only retries "three times over the course of a few hours".
- Snapshot events carry the object as of the event; thin events require fetching the current object.
- Python `stripe` 15.6.1 (MIT) verifies signatures (`construct_event`, `parse_event_notification`).
- The endpoint needs a public HTTPS URL. `stripe listen --forward-to localhost:...` covers local tests.

How it plugs in: the webhook handler verifies the signature, inserts `(event_id PRIMARY KEY, object_id, type)` into
Postgres (dedup on conflict), and then marks stale any open decision whose recorded premises reference `object_id`,
e.g. `charge.refunded` or `charge.dispute.created` against a pending refund. Because order and delivery are not
guaranteed, the event is only a hint. The handler, or the premise re-check, reads the current object from the API. The
send-time `validate_premises` remains the guarantee. This is where we can beat Temporal: a signal can cancel a waiting
workflow before it ever reaches send. Temporal plus a pre-send check matches us at send time.

Debezium (debezium/debezium and debezium/debezium-server, both Apache-2.0; newest tags v3.7.0.Beta1):
- The Postgres connector uses `pgoutput` and needs `wal_level=logical` plus a replication slot. The docs promise
  "_exactly once_" in normal operation but "_at least once_" after abnormal stops, and "consumers should always anticipate
  some duplicate events".
- It runs on the JVM: Kafka Connect, Debezium Server (sinks include http, redis, nats-jetstream, kafka, jdbc, ...), or the
  embedded Java engine. There is no Python engine.
- Use case: premises about *our own* Postgres tables (a customer's balance, an account freeze flag) changing under a
  pending decision.

Postgres LISTEN/NOTIFY (built in, zero deps):
- Transactional: events are delivered only on commit, in commit order, and identical payloads within one transaction are
  folded.
- Notifications are not stored. They go only to sessions listening at that moment. The payload must be under 8000 bytes,
  and a full 8GB queue makes `NOTIFY` fail at commit.

How the two plug in: a trigger on premise-bearing tables issues `pg_notify('premise', table||':'||key)` in the same
transaction as the change. The worker `LISTEN`s and marks matching open decisions stale. Since notifications are lost
while a worker is down, a worker also scans for changed rows on startup. That scan uses an `updated_at` or `xmin`
comparison against the decision's capture time, which gives the same at-least-once hint Debezium provides, with no JVM
and no replication slot to manage. Debezium becomes worth it only when premises live in a *different* database the
runtime does not own, or when a Kafka pipeline already exists.

## Recommended minimal set

1. Authority: **cedarpy** (Apache-2.0), in process. Load policies and grants from Postgres in the dispatch transaction.
   Record policy hash, entities and matched policy ids in the receipt so verifiers can re-run the decision.
2. Receipts: **no log server**. Build an RFC 9162 Merkle log over receipt heads in a Postgres table and publish C2SP
   checkpoints signed with Ed25519 via **cryptography**. Keep HMAC signing as it is.
3. Premise events: **Stripe webhooks** through the official `stripe` library, deduped by event id in Postgres, for
   external premises. **LISTEN/NOTIFY plus a startup scan** for premises in our own Postgres. Both only mark decisions
   stale; the send-time and recovery-time pull re-check remains the guarantee.

Not recommended now: OpenFGA and OPA (extra server; revoke race or bundle lag), Rekor/Trillian/Tessera (Go server and
non-Postgres storage; Trillian is in maintenance), pymerkle (GPL-3.0, stale), merkletools (no consistency proofs, stale),
and Debezium (JVM; only needed for foreign databases).

New dependencies in total: `cedarpy`, `cryptography`, `stripe` (optional, only for the Stripe target), plus `psycopg` (LGPL-3.0, already the Postgres driver).

## Sources

- https://github.com/cedar-policy/cedar , https://github.com/k9securityio/cedar-py , https://pypi.org/project/cedarpy/
- https://github.com/openfga/openfga (README storage list), https://openfga.dev/docs/interacting/consistency , https://openfga.dev/docs/modeling/conditions , https://pypi.org/project/openfga-sdk/
- https://github.com/open-policy-agent/opa , https://www.openpolicyagent.org/docs/rest-api , https://www.openpolicyagent.org/docs/management-decision-logs
- https://github.com/sigstore/rekor , https://github.com/sigstore/rekor-tiles , https://pypi.org/project/sigstore/
- https://github.com/google/trillian (README maintenance notice) , https://github.com/transparency-dev/tessera
- https://github.com/fmerg/pymerkle , https://pypi.org/project/pymerkle/ , https://github.com/Tierion/pymerkletools
- https://datatracker.ietf.org/doc/html/rfc9162 , https://c2sp.org/tlog-checkpoint , https://c2sp.org/signed-note
- https://docs.stripe.com/webhooks
- https://github.com/debezium/debezium (documentation/modules/ROOT/pages/connectors/postgresql.adoc) , https://github.com/debezium/debezium-server
- https://www.postgresql.org/docs/current/sql-notify.html
