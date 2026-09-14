# Proof tools for the Interlock runtime

Researched 2026-09-13 from primary sources (GitHub repos, release APIs, LICENSE files, official docs).
Local checks were run on this machine; each one is marked "verified locally".

## Environment facts that change the plan

- `java` on PATH fails ("Unable to locate a Java Runtime"). Homebrew JDKs are installed but not linked:
  `/opt/homebrew/opt/openjdk/bin/java` is 26.0.2 and `/opt/homebrew/opt/openjdk@17/bin/java` is 17.0.20.
  Scripts should set `JAVA=/opt/homebrew/opt/openjdk/bin/java`. Verified locally.
- The Docker CLI is installed but the daemon is not running (no socket). Plan for no containers.
- No dotnet. No Postgres binaries on PATH (`brew install postgresql@17` still needed).
- No Leiningen or Clojure. Not needed: elle-cli ships a prebuilt standalone jar.

## Tools

### TLA+ / TLC (tla2tools.jar)

- License: MIT (tlaplus/tlaplus LICENSE).
- Version: last tagged stable is 1.7.4 (2020). The `v1.8.0` pre-release tag carries a rolling
  `tla2tools.jar`; the asset was updated 2026-09-12 and reports `TLC2 Version 2026.09.12.025210 (rev: 867aefb)`.
  Pin by recording the jar's sha256 at download.
- Install: `curl -L -o tla2tools.jar https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar`, then
  `$JAVA -XX:+UseParallelGC -cp tla2tools.jar tlc2.TLC -deadlock Spec`.
- Verified locally: a 15-line spec of "journal DISPATCHED, crash, naive re-send on recovery against a tier-3 target"
  was checked in under a second and TLC printed the counterexample trace `sent = 0, 0, 1, 2` violating `AtMostOnce`.
- What it proves: exhaustive checking of safety invariants and liveness under fairness for a design, for bounded constants
  (for example 2 workers, 2 steps, 1 crash budget, 3 target tiers). It proves the protocol, not the Python code.
- Properties it fits:
  - A completed step is never re-executed (journal monotonicity).
  - At most one external effect per effect id on tier 1 inside the dedup window, and on tier 2 via lookup.
  - On tier 3, no re-send after DISPATCHED with an unknown outcome; the state becomes AMBIGUOUS.
  - No send without a current lease (fencing token equals the claim epoch), including after takeover by a second worker.
  - No send, and no recovery re-send, when a captured premise is false or authority was revoked.
  - Payload binding: the sent payload equals the approved payload.
  - Signals: a revoke or cancel committed before DISPATCHED means the effect is never sent.
  - Liveness under weak fairness: every workflow reaches a terminal state (DONE, REFUSED, AMBIGUOUS, CANCELLED).
  - The same spec with Temporal-style actions yields the formal comparison (see plan, step 1).

### Apalache

- License: Apache-2.0 (GitHub API). Latest v0.62.2, 2026-08-26. Requires Java 21+ (openjdk 26 is present).
- Install: download the release archive from github.com/apalache-mc/apalache/releases and run its `bin/apalache-mc`
  with `JAVA_HOME=/opt/homebrew/opt/openjdk`. Not run locally.
- What it proves: SMT-based bounded model checking, and inductive invariant checking (`check --init=IndInv --inv=IndInv`
  then `--init=Init --inv=IndInv`), which proves an invariant for executions of any length for the chosen constants.
  Needs type annotations on the spec. Use it after TLC, on the core safety invariants only.

### P language

- License: MIT. NuGet package `P` latest 3.1.0.
- Install: requires .NET SDK 8.0 (`brew tap isen-ng/dotnet-sdk-versions; brew install --cask dotnet-sdk8-0-200`),
  Java 11+, then `dotnet tool install --global P`. The docs offer a Docker image, but the daemon is down.
- What it proves: systematic exploration of message interleavings and failures in a state-machine model that reads
  closer to code; PEx adds model checking, PObserve checks production logs against the spec.
- Verdict: not clearly better than TLA+ for this job and it needs a new SDK. Defer. Revisit only if log conformance
  checking (PObserve) is wanted later.

### Jepsen Elle (via elle-cli)

- License: Elle is EPL-2.0 (or GPL-2.0 with classpath exception). elle-cli is EPL-1.0+.
- Version: elle-cli 0.1.11, released 2026-09-01, bundles Jepsen 0.3.11, needs Java 21+.
- Install: `curl -L -o elle.zip https://github.com/ligurio/elle-cli/releases/download/0.1.11/elle-cli-bin-0.1.11.zip && unzip elle.zip`,
  then `$JAVA -jar target/elle-cli-0.1.11-standalone.jar --model list-append history.json`.
- Verified locally: a JSON history where two processes each appended value 1 to key 1 was rejected with
  `:type :duplicate-appends ... "value 1 appended to key 1 multiple times!"` (reported as an exception carrying
  `:valid? :unknown`, not a clean `false`; the harness must treat that as a failure).
- Models: Elle rw-register and list-append (G0, G1a, G1b, G1c, G-single, G2, duplicate writes, garbage reads);
  Jepsen bank, counter, set, set-full, long-fork; Knossos cas-register and mutex.
- What it proves: nothing universally. It checks a recorded history from a real fault run and finds violations in it.
- Properties it fits: record each external effect as an append of the effect id to a per-target key; a duplicate
  effect shows up as a duplicate append. Journal step results fit rw-register (no lost or dirty step result under
  concurrent workers against Postgres).

### Knossos

- License: Eclipse Public License (README; the GitHub API reports no SPDX id). Last push 2026-07-17.
- Use through elle-cli (`--model mutex` or `cas-register`), no Clojure toolchain needed.
- What it proves: linearizability of an observed history against a sequential model. Search is exponential in history
  size and can return `unknown`.
- Properties it fits: lease claims as a mutex (two workers never both hold the same task lease in a linearizable
  order), including across SIGKILL and takeover. Keep histories short per task.

### Porcupine (Go)

- License: MIT. Latest tag v1.3.0, last push 2026-08-06. Go is installed.
- What it proves: linearizability of a history against a custom Go `Model` (`Init`, `Step`, optional `Partition`),
  and writes an HTML visualization of the failing partial linearization.
- When to prefer it over Knossos: when the model is custom, for example "effect ledger with AMBIGUOUS outcomes",
  and partitioning by effect id keeps checking fast.

### Toxiproxy

- License: MIT. Latest v2.12.0, 2025-03-18 (GitHub API). Homebrew core formula `toxiproxy` is 2.12.0.
- Install: `brew install toxiproxy`, run `toxiproxy-server` (HTTP API on port 8474). The Python client
  `toxiproxy-python` is 0.1.1 and old; drive the HTTP API with `urllib` from the stdlib instead.
- Real network faults (TCP level, not emulated):
  - `limit_data`: closes the connection after N bytes. Set N just past the request size and the server receives and
    commits the request but the response never arrives. That is the ack-lost-after-commit case.
  - `timeout`, `reset_peer`, `down`, `latency`, `slicer`, `bandwidth`, `slow_close`.
- Place one proxy between workers and Postgres (journal write and lease renewal faults) and one between workers and
  the effect target.
- Risk: it is a plain TCP proxy. Pointing a TLS client (Stripe) at it needs the client to connect to 127.0.0.1 while
  keeping SNI and certificate host `api.stripe.com`. Use a local HTTP target process for the fault matrix and Stripe
  test mode for a smaller tier-1 confirmation run.

### Hypothesis stateful testing

- License: MPL-2.0. Latest 6.168.0 (PyPI).
- Install: `uv run --no-project --with hypothesis --with psycopg[binary] python -m pytest ...` (or unittest).
- API: `RuleBasedStateMachine`, `@rule`, `@initialize`, `@precondition`, `@invariant`, `Bundle` and `consumes()`;
  failures shrink to a minimal step sequence printed as Python; `stateful_step_count` and `max_examples` bound cost.
- What it proves: nothing exhaustive. It searches random operation sequences and shrinks failures. Its value is running
  the TLA+ invariants against the real runtime code and real Postgres.
- Properties it fits: every spec invariant, asserted in `@invariant` by querying Postgres and the target ledger after
  each step; rules are start workflow, claim, complete step, signal approve/revoke/cancel, flip premise, deliver
  timer, and SIGKILL a worker subprocess.

### Deterministic simulation testing from Python

- No mature Python DST library was found. The one search hit (parag-labs/deterministic-sim-testing) is Java, MIT,
  created 2026-09-07 with 0 stars; not a dependency to take.
- Temporal's own Python SDK runs workflow code on a custom deterministic asyncio event loop (temporal.io blog), which
  is the same idea applied to workflow replay, not to the server.
- Practical approach: keep the runtime core a pure transition function (state plus event gives new state plus
  commands), inject clock, RNG and I/O, and let Hypothesis drive seeded schedules of crashes, message drops and timer
  firings over that core. Everything in that harness is EMULATED (virtual time, simulated crashes) and must be labeled
  so. It is for fast exploration and reproducible seeds; live claims still come from SIGKILL and Toxiproxy runs.

## Recommended proof plan (runnable today)

Order is cheapest proof first. Each step has a pass criterion.

1. **Model the protocol in TLA+ (spec/Runtime.tla), check with TLC.**
   - Constants: 2 workers, 1 workflow of 2 steps, 1 effect, tiers {1,2,3}, crash budget 2, 1 revoke signal, 1 premise flip.
   - Actions: Claim (epoch+1), Heartbeat, LeaseExpire, Takeover, JournalStep, Decide (captures premises),
     Dispatch, Send, AckLost, Ack, Crash, Recover, Signal(revoke|cancel|approve), TimerFire, PremiseFlip.
   - Invariants from the Tools section above, plus `NoDoubleCompletion` and `ReceiptChainLinear`.
   - Add a `MODE` constant with three values: `interlock`, `temporal_idem_key` (retry with the same key, no premise or
     lease re-check), `temporal_precheck` (check once before send, no re-check at recovery). TLC output per mode is the
     formal better/equal/worse table: which invariants hold in all three (equal), which fail only in the Temporal modes
     (better), and any that fail only in `interlock` (worse, report them).
   - Also keep deliberately broken variants (naive recovery, lease without fencing) and require TLC to find their
     counterexamples, so the checker is shown to have teeth.
   - Pass: `interlock` mode has no violations and the liveness property holds under fairness.
2. **Apalache inductive invariant** for the safety core (at-most-once, fencing, stale-premise). Pass: both
   `IndInv` checks succeed. Optional if time is short.
3. **Hypothesis stateful test (tests/test_runtime_stateful.py)** against the real runtime and real Postgres
   (brew postgresql@17 on a non-default port, data dir in .runtime-data/). Invariants mirror the spec by name.
   Worker crashes are SIGKILLs of worker subprocesses. Pass: no failure over a fixed budget, seed and budget recorded.
4. **Live fault run with history (experiments/runtime_jepsen.py)**: 3 worker processes, a local HTTP target per tier,
   Toxiproxy in front of Postgres and the target, a nemesis that SIGKILLs workers and applies `limit_data`, `timeout`,
   `reset_peer` on a schedule. Record a Jepsen-format JSON history (invoke/ok/info). Check with elle-cli
   (`list-append` on the target ledger, `rw-register` on step results) and Knossos `mutex` on lease claims. Run the same
   nemesis against Temporal (temporalio dev server) with its idempotency key and with the pre-send check.
   Pass: Interlock history valid; any Temporal violations are reported with the history file.
5. **Stripe test mode confirmation** (tier 1) for the ack-lost case, small N, real PaymentIntent ids in results.

Cross-cutting rules: TLC and Apalache results are proofs about the model for stated constants; Elle, Knossos and
Hypothesis results are evidence from finite runs. Say which is which in results/runtime_*.

## Sources

- https://github.com/tlaplus/tlaplus (LICENSE, releases, tag v1.8.0)
- https://github.com/apalache-mc/apalache (releases, license via GitHub API)
- https://github.com/p-org/P and https://p-org.github.io/P/getstarted/install/ and https://www.nuget.org/packages/P/
- https://github.com/jepsen-io/elle
- https://github.com/ligurio/elle-cli (README, release 0.1.11)
- https://github.com/jepsen-io/knossos
- https://github.com/anishathalye/porcupine
- https://github.com/Shopify/toxiproxy (license and latest release via GitHub API)
- https://hypothesis.readthedocs.io/en/latest/stateful.html and https://pypi.org/project/hypothesis/
- https://temporal.io/blog/durable-distributed-asyncio-event-loop
- https://github.com/parag-labs/deterministic-sim-testing
