# Claims ledger, full audit

The row-by-row audit behind [claims.md](claims.md): 350 claims from the README, docs, site and test inventory, each with what proves it and a status. Line numbers refer to the files as they stood during the audit (2026-09-13, before the README was restructured); the claim text is what to search for.

Date: 2026-09-13. Branch `lock-in` at 63f962b plus the working tree of that day.

The rule (handoff/04-claims-discipline.md): every quantitative or comparative claim in a public file (README, docs, site, slides, video) has a row here with the claim, where it appears, what produces or proves it, and a status. A claim that is `unverified` is deleted from the public files and kept in `.team/UNVERIFIED.md` with what would verify it. Deletion is preferred over hedging.

Statuses: `verified-by-code` (a script in the repo, or the suite, was re-run this session and its output matched), `verified-by-url` (the source was opened and the number found), `assumption-labeled` (a simulation input, goal, plan or illustration, labeled where it appears), `verified-by-results-file (not re-run this session)` (the claim matches a committed results file whose producer was not re-run, usually because it creates live objects), `unverified`. Each row's last column says what this session did about it. Line numbers are from before this session's edits. The Stripe re-audit (read-only, test mode) and `experiments/e2e_audit.py` count as re-run producers.

## Counts

| status | rows |
|---|---|
| verified-by-code | 106 |
| verified-by-url | 77 |
| assumption-labeled | 37 |
| verified-by-results-file (not re-run this session) | 49 |
| unverified | 79 |
| total | 348 |

Of the 79 unverified rows, 56 were removed from the public files this session and 23 remain, listed with a reason in `.team/UNVERIFIED.md` (generated results, files outside the edit scope, or a decision the team has to make).

## README.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C001 | Python 3.9+, zero dependencies | README.md:3 | pyproject.toml `requires-python = ">=3.9"`, `dependencies = []`; temporalio and langchain_core are optional imports | verified-by-code | kept |
| C002 | gets a receipt: it happened exactly once, it was authorized when it fired, and the facts ... still held | README.md:5 | receipts.py:137-139; `test_committed_refund_proves_all_three_claims_on_both_backends` passes. At tier 3 `happened` is unknown (demo 3) | verified-by-code | reworded: "happened once (or is marked unknown when the service can't be asked)", the tier qualifier handoff/03 requires |
| C003 | A customer paid $100. A support case approves one $20 partial refund. | README.md:7 | Scenario input; `python3 demo.py 2` prints it back | assumption-labeled | label added: "The scenario every experiment below uses" |
| C004 | On restart, nothing in the system can answer three questions | README.md:7 | Narrative framing, no data | unverified | removed: now "the system has to answer three questions" |
| C005 | the model says "$30" this time, and the customer gets $50 | README.md:9 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; refund_agent.md `model_redecides` naive `APPLIED $50` | verified-by-code | kept |
| C006 | honest about the one case where nobody can know | README.md:9 | `python3 demo.py 3` prints `recovery: AMBIGUOUS` | verified-by-code | kept |
| C007 | demo.py naive: the refund lands twice | README.md:12 | `python3 demo.py naive`: `$40  (2 refund record(s))` | verified-by-code | kept |
| C008 | demo.py 2: lands once, receipt says so | README.md:13 | `python3 demo.py 2`: `$20  (1 refund record(s))`, `final COMMITTED` | verified-by-code | kept |
| C009 | every PaymentIntent id is listed in results/stripe_live.md | README.md:19 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C010 | Real Temporal: durable execution retries a stale refund to $40; with Interlock the same retry is refused | README.md:20 | results/temporal_live.md:11 | verified-by-results-file (not re-run this session) | kept |
| C011 | Ten faults and a control against six systems, regenerated in under a second. CI fails if the tables drift | README.md:21 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty in 0.618s; test.yml runs `git diff --exit-code` on results/ | verified-by-code | kept |
| C012 | 278 tests including a 2,000-case randomized fault sweep | README.md:22 | `python3 -m unittest discover -s tests`: `Ran 415 tests`, `OK (skipped=52)`. `RUNS = 2000` at tests/test_interlock.py:53 is correct; the count was stale | verified-by-code | count removed; sweep kept |
| C013 | Writing them found 15 real bugs in our own gate; each fix has a test that failed before it | README.md:22 | No test-to-bug mapping; tests/README.md lists 15 + 30 + 6 | unverified | removed |
| C014 | Three research groups (Huawei, Tsinghua, WashU) published pieces of this layer between June and September 2026 | README.md:23 | https://arxiv.org/abs/2609.08015, https://arxiv.org/abs/2606.17573, https://arxiv.org/abs/2609.10969 | verified-by-url | kept |
| C015 | None re-checks premises on the recovery path; none ships adapters for real services | README.md:23 | None-of-X claim; cannot be shown from a URL | unverified | removed |
| C016 | the Cloud AI track brief, one sentence in, describing a thing that did not exist. Now it does. | README.md:26 | Brief not in repo; novelty claim | unverified | novelty clause removed; attribution kept |
| C017 | The goal: let finance teams cut two thirds of the manual approvals | README.md:30 | Stated as a goal; approval_inbox gives 65 of 95 = 68.4% on a synthetic day | assumption-labeled | kept |
| C018 | synthetic day: reviews 100 to 36, zero wrong payouts, rules alone paid out wrong 10 times | README.md:30 | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged: `100/10`, `25/10`, `36/0`; "mix stated as an assumption" | assumption-labeled | kept |
| C019 | about 400 lines of Python | README.md:34 | `wc -l interlock/*.py` gives 2648 | unverified | removed |
| C020 | One approved request, one effect id, at most one committed effect | README.md:37 | journal.py:383-402 SHA-256 of request_id; test_contract passes | verified-by-code | kept |
| C021 | Optimistic concurrency control, Kung & Robinson 1981 | README.md:38 | https://dl.acm.org/doi/10.1145/319566.319567 | verified-by-url | kept |
| C022 | receipt: the four facts and a final state | README.md:50 | `python3 demo.py 2` prints proposed, authorized, executed, recorded, `final COMMITTED` | verified-by-code | kept |
| C023 | What nobody else combines (heading) | README.md:62 | None-of-X claim | unverified | removed: heading is now "What Interlock combines" |
| C024 | ATR (Huawei, Sept 2026) records premises too, and explicitly leaves crashes out | README.md:66 | https://arxiv.org/html/2609.08015: "does not solve crashes between an external effect and its acknowledgement" | verified-by-url | kept |
| C025 | Temporal, Restate, DBOS and LangGraph replay the old decision | README.md:67 | Only a Temporal search summary; no page for Restate, DBOS or LangGraph | unverified | removed |
| C026 | Cordon (Tsinghua, EuroSys 27) parks unclear effects for a human | README.md:68 | https://arxiv.org/html/2606.17573 | verified-by-url | kept |
| C027 | nobody states the guarantee per target | README.md:68 | None-of-X claim | unverified | removed |
| C028 | The last three rows of the refund table below are steps 2 and 3, measured | README.md:70 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C029 | demo 2 transcript: journal effect id 8351811bed3d | README.md:90-93 | `python3 demo.py 2` prints `6b6f07d3ceb0` | verified-by-code | replaced with 6b6f07d3ceb0 |
| C030 | demo 3 transcript: AMBIGUOUS, $20, 1 refund record | README.md:101-103 | `python3 demo.py 3` | verified-by-code | kept |
| C031 | Two experiments ... Every cell is produced by run_all | README.md:114 | The section presents 5 experiments; run_all regenerates only experiments 1 and 2 | verified-by-code | replaced: five experiments, run_all covers 1 and 2, 3 and 4 live, 5 is approval_inbox.py |
| C032 | $100 paid, one $20 refund; invariant; three baselines | README.md:118 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C033 | refund table cells (10 faults x 6 systems) | README.md:120-131 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; every cell matches refund_agent.md | verified-by-code | kept |
| C034 | Finding 1: exactly-once needs tier 1 or 2 | README.md:133 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; gate@tier1/2 all held, tier 3 has AMBIGUOUS cells | verified-by-code | kept |
| C035 | Two Generals result (1975) | README.md:133 | https://www.deepdyve.com/lp/association-for-computing-machinery/some-constraints-and-tradeoffs-in-the-design-of-network-communications-v0NJ3yAE2i | verified-by-url | kept |
| C036 | Finding 2: idempotency handles crash, duplicate, $30; still refunds under revoked lease and ineligible order | README.md:135 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C037 | Finding 4: before the fix, recover() refunded $40 | README.md:137 | History, not re-runnable; `test_human_refund_during_outage_is_refused_after_restart` passes and refund_agent.md shows `REFUSED:stale_premise_at_recovery $20` | verified-by-code | kept |
| C038 | Stripe prunes idempotency keys after 24 hours, and a retry after that is a new refund | README.md:137 | https://docs.stripe.com/api/idempotent_requests ("at least 24 hours old") | verified-by-url | kept |
| C039 | The idempotency-only column still fails all three | README.md:137 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty: `RETRIED $40`, `RETRIED $20`, `RETRIED $40` | verified-by-code | kept |
| C040 | That ordering is what every worktree-based product ships | README.md:141 | No source | unverified | removed |
| C041 | coding table (7 faults x 3 systems) | README.md:143-151 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; matches coding_agents.md | verified-by-code | kept |
| C042 | catch duplicated work with zero model calls | README.md:153 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty: `duplicate_work` `REFUSED:claimed_by_A` in both gate columns | verified-by-code | kept |
| C043 | Duplicated work is the single most common multi-agent failure mode in the Berkeley MAST study (17% of 1,600 traces) | README.md:153 | https://arxiv.org/html/2503.13657v3: FM-1.3 15.7% of 1,642 traces, still the largest; 17.14% is v2 on 200+ traces | verified-by-url | replaced with "15.7% of 1,642 traces, arXiv v3" |
| C044 | No mechanically extractable premise catches that row | README.md:153 | Argued, not measured; only file and symbol premises were tested | verified-by-code | replaced: "Neither premise we tested, file hash or symbol, catches that row" |
| C045 | LLM agents cost 4-15x tokens per attempt and don't reproduce their plan on re-run | README.md:155 | https://www.anthropic.com/engineering/multi-agent-research-system: about 4x chat, 15x for multi-agent, against chat; re-run clause unsourced | verified-by-url | replaced with the source's ratios; re-run clause removed |
| C046 | stripe_live.py makes a $100 payment, approves one $20 refund, injects the fault | README.md:159 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C047 | Stripe table: naive $40/$40/$40; key $20/$20/$40; gate $20/$20/$20 | README.md:161-165 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C048 | the idempotency key handles the crash and the duplicate, and pays twice when a person refunds during the outage | README.md:167 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C049 | Temporal table (4 faults x 2 systems) | README.md:173-178 | results/temporal_live.md:10-13 | verified-by-results-file (not re-run this session) | kept |
| C050 | approval inbox mix (60/15/5/5/5/5/5, 3 full, 2 partial) | README.md:184 | approval_inbox.py:33-43; label "The mix is an assumption" at README:184 | assumption-labeled | kept |
| C051 | inbox table 100/10, 25/10, 36/0 | README.md:188-190 | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged | assumption-labeled | kept |
| C052 | Of the 11 extra reviews, 10 closing or repairing, 1 deciding a new amount | README.md:192 | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged: `stale_premise: 10`, `of those, deciding the new amount of an accepted repair: 1` | assumption-labeled | kept |
| C053 | Their docs say as much: if the process crashes mid-request, the agent has no idea what already happened | README.md:200 | https://pydantic.dev/docs/ai/integrations/durable_execution/temporal/ has no such sentence; it says "if an activity fails part-way through it is restarted from the beginning" | verified-by-url | replaced with that quote |
| C054 | durable execution ties the gate on crash, duplicate and re-decision rows and fails all five changed-world rows | README.md:200 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; durable@tier1 fails 5 rows | verified-by-code | kept |
| C055 | Experiment 4 repeats the key rows on a real Temporal server, with the same result | README.md:200 | results/temporal_live.md (4 rows) | verified-by-results-file (not re-run this session) | kept |
| C056 | It's the rule a database would impose with no concurrency control, and databases abandoned it for throughput | README.md:202 | https://cognition.com/blog/dont-build-multi-agents does not discuss databases; the analogy has no source | unverified | removed |
| C057 | CaMeL ... has no model of crashes, retries, duplicate delivery, or revocation | README.md:204 | https://arxiv.org/html/2503.18813: "no means to enable atomicity ... or rollbacks" | verified-by-url | kept |
| C058 | None re-checks premises on the recovery path or states a guarantee per target, and none ships adapters for real services | README.md:206 | None-of-X claim | unverified | removed |
| C059 | Add it in three lines | README.md:210-212 | `Interlock(...)`, `@gate.effect(...)`, `gate.recover()`; ThreeLineIntegration tests pass | verified-by-code | kept |
| C060 | Zero lines: in front of an MCP server; proxy killed mid-call, refund lands once | README.md:235,253 | test_mcp_proxy.py passes against tests/fake_mcp_server.py | verified-by-code | kept |
| C061 | MCP itself has no idempotency or transactional contract | README.md:253 | https://modelcontextprotocol.io/specification/2026-07-28/server/tools | verified-by-url | kept |
| C062 | refused message: "refunded_total: was 0, now 5." | README.md:271 | escalation.py:118; test_repair passes | verified-by-code | kept |
| C063 | attempts 3, max 15, one attempt per approval sent, "amount 30 is over the 15 approved" | README.md:276-279 | tools.py:31, approvals.py:47 and :117; test_repair passes | verified-by-code | kept |
| C064 | repair_loop: person 17 to 3, wrong 13 to 0; no gate 40 wrong; hand check ties | README.md:283 | `python3 experiments/repair_loop.py` re-run, results/repair_loop.md unchanged; mix labeled | assumption-labeled | kept |
| C065 | gpt-5.4-mini, 40 per system; interlock+repair 40 no person, 10 refused then right; no gate 15 wrong ($233) | README.md:285 | results/repair_live_model.md:9-12 | verified-by-results-file (not re-run this session) | kept |
| C066 | hand check: 4 of 6 hand-refund cases said DONE short, 2 to a person; terser message did worse | README.md:285 | results/repair_live_model.md by-kind table; repair_live_model_terse_hand_check.md | verified-by-results-file (not re-run this session) | kept |
| C067 | Six cases per kind is a small sample | README.md:285 | repair_live_model.md:3: kinds have 16/6/4/6/4/4 cases | verified-by-results-file (not re-run this session) | replaced: "Each kind had 4 to 16 cases" |
| C068 | interlock-verify output keys | README.md:292-295 | receipts.py:137-139; test with key asserts valid, tamper_evident, signed | verified-by-code | kept |
| C069 | The goal is to cut two thirds of the manual approvals | README.md:302 | Goal, not measured | assumption-labeled | label added: "not a measured result" |
| C070 | $50 after $30 by hand: was 0 now 30, 70 left | README.md:304 | test_escalation_flow passes | verified-by-code | kept |
| C071 | Route("large", [...], sla=4 * 3600); restarted inbox rebuilds without loss or duplication | README.md:306 | approvals.py:157-160; test_approvals and test_escalation_flow pass | verified-by-code | kept |
| C072 | Stripe-Signature: HMAC-SHA256 over t.payload, tolerance, constant-time compare | README.md:310 | confirm.py:31, :54-57 | verified-by-code | kept |
| C073 | pip install: no dependencies; Python 3.9+ | README.md:317 | pyproject.toml | verified-by-code | kept |
| C074 | eight workers racing: one dispatch, one recovery, JSONL and SQLite | README.md:321 | test_interlock.py:187 `run_threads(fn, n=8)`; both race tests pass | verified-by-code | kept |
| C075 | Writing one for a real service is an afternoon | README.md:334 | Never measured | unverified | removed |
| C076 | target table: Stripe tier 1, dedupes for 24h | README.md:338 | https://docs.stripe.com/api/idempotent_requests | verified-by-url | kept |
| C077 | target table: GitHub merge tier 2 (look up the merge commit) | README.md:339 | results/scenarios/github_merge.md: `COMMITTED_ON_QUERY x3` | verified-by-results-file (not re-run this session) | kept |
| C078 | target table: Postgres write tier 2 | README.md:340 | Design mapping, not measured | assumption-labeled | kept |
| C079 | target table: SendGrid / most email tier 3, no dedup, no lookup | README.md:341 | Only a secondary blog; "most email" is a generalization | unverified | row removed |
| C080 | Reconciliation is already the most expensive manual process in corporate finance | README.md:350 | J.P. Morgan (secondary copies only) says most time-consuming; no cost source | unverified | removed |
| C081 | Real: both targets, both experiments, every number above; run_all regenerates results/ in under a second | README.md:354 | targets/ has 3 files; run_all regenerates only refund_agent.md and coding_agents.md (0.618s) | verified-by-code | replaced: "The journal and the gate. run_all regenerates the tables of experiments 1 and 2" |
| C082 | 278 tests, CI on Python 3.9, 3.12 and 3.13 | README.md:356 | `python3 -m unittest discover -s tests`: `Ran 415 tests`, `OK (skipped=52)`; test.yml matrix verified | verified-by-code | count removed; CI kept |
| C083 | found six bugs ... then found nine more ... All fifteen are fixed, and each has a test that failed before its fix | README.md:356 | No test-to-bug mapping; tests/README.md now lists 51 | unverified | counts and the "each has a test" sentence removed; bug descriptions kept |
| C084 | Not built yet: a real GitHub target | README.md:362 | experiments/scenario_github_merge.py and results/scenarios/github_merge.md exist | unverified | removed |
| C085 | gate.py: six invariants | README.md:376 | gate.py:21-37 lists I1 to I8 | verified-by-code | replaced: "eight invariants (I1 to I8)" |
| C086 | tests/: every README claim as an assertion, a 2,000-case fault sweep | README.md:393 | Several README numbers have no assertion; sweep verified | verified-by-code | replaced: "the fault rows as assertions" |
| C087 | Saturday two specs, Sunday same mechanism | README.md:408 | History under the heading "How this came together" | assumption-labeled | kept |
| C088 | Kung & Robinson 1981; Garcia-Molina & Salem 1987; Leach 2017 | README.md:414-417 | https://dl.acm.org/doi/10.1145/38713.38742, https://stripe.com/blog/idempotency | verified-by-url | kept |
| C089 | Cemri et al. ... Step repetition at 17.14% | README.md:418 | https://arxiv.org/html/2503.13657v3 | verified-by-url | replaced: "15.7% of 1,642 traces (v3)" |
| C090 | Debenedetti, Lyu, Chen, Zheng citations | README.md:419-422 | arXiv abs pages 2503.18813, 2609.08015, 2606.17573, 2609.10969 | verified-by-url | kept |
| C091 | Anthropic (2025) 4x/15x token figures; Mosaic retry is close to free | README.md:424-425 | https://www.anthropic.com/engineering/multi-agent-research-system; https://mosaic.inc/blog/memo | verified-by-url | kept |

## docs/00-the-whole-story.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C092 | Four separate facts that every framework collapses into one log line | docs/00-the-whole-story.md:16 | Contradicted in part by competitor runs (DBOS and Temporal keep step histories) | unverified | removed: "Four separate facts." |
| C093 | One $20 refund. Three lines of agent code. | docs/00-the-whole-story.md:20 | Same as README:210-212 | verified-by-code | kept |
| C094 | The rubric is 30% innovation, 25% technical, 25% business, 20% presentation | docs/00-the-whole-story.md:49 | External brief, not reachable | unverified | removed |
| C095 | It used to be microseconds inside one process. Now it's seconds | docs/00-the-whole-story.md:78 | No source | unverified | removed |
| C096 | Two Generals, 1975; Leach 2017; Kung & Robinson 1981; Sagas 1987 | docs/00-the-whole-story.md:17,70,88-91 | URLs as in README rows | verified-by-url | kept |
| C097 | Pydantic AI docs: a step that dies mid-call re-runs the tool | docs/00-the-whole-story.md:93 | https://pydantic.dev/docs/ai/integrations/durable_execution/temporal/ | verified-by-url | kept |
| C098 | Step repetition is the top failure mode at 17.14%; all seven frameworks conversational | docs/00-the-whole-story.md:97 | https://arxiv.org/html/2503.13657v3 | verified-by-url | replaced: "15.7% of 1,642 traces (arXiv v3)" |
| C099 | Mosaic, retry is close to free | docs/00-the-whole-story.md:99 | https://mosaic.inc/blog/memo | verified-by-url | kept |
| C100 | 8 in 10 enterprises had an agent execute a consequential action and paid to correct it (Kore.ai) | docs/00-the-whole-story.md:100,243 | https://www.kore.ai/research/agent-productivity-index-report | verified-by-url | kept |
| C101 | J.P. Morgan 61%; McKinsey 30% of finance time; Levvel 1.2% duplicates | docs/00-the-whole-story.md:101,240-242 | Secondary copies only, no primary found | unverified | row and three bullets removed |
| C102 | Natural ($40M raised) | docs/00-the-whole-story.md:116 | https://techcrunch.com/2026/07/20/natural-raises-30m-to-reinvent-payments-for-ai-agents-and-take-on-stripe/ | verified-by-url | kept |
| C103 | Effects row: nobody | docs/00-the-whole-story.md:119 | results/competitors/langgraph.md and dbos.md: hand-written re-checks held | verified-by-results-file (not re-run this session) | replaced: "hand-written checks; research prototypes cover pieces" |
| C104 | Empty: the effects row ... Nobody owns the seam. Seams are where Stripe, Twilio, and Plaid came from. | docs/00-the-whole-story.md:121 | No source; contradicted in part by the competitor runs | unverified | removed |
| C105 | effect_id_for hashes request_id to 8351811bed3d | docs/00-the-whole-story.md:183 | `python3 demo.py 2` prints `6b6f07d3ceb0` | verified-by-code | replaced with 6b6f07d3ceb0 |
| C106 | journal+leases+gate ~250 lines; targets ~150; experiments ~300 | docs/00-the-whole-story.md:205-208 | wc -l: 828, 250, 12,647 | unverified | line-count column removed |
| C107 | tests/: Found fifteen bugs across two review passes | docs/00-the-whole-story.md:211 | No record; tests/README.md now lists 51 | unverified | removed |
| C108 | the protocol (250 lines) and the two tables | docs/00-the-whole-story.md:214 | wc -l: 828 | unverified | line count removed |
| C109 | exp 1: 10 faults + control x 6 systems, 3 tiers; exp 2: 7 faults x 3 systems | docs/00-the-whole-story.md:222-223 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C110 | exp 3: 3 faults x 3 systems, real Stripe | docs/00-the-whole-story.md:224 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C111 | exp 4: 4 faults x 2 systems, real Temporal | docs/00-the-whole-story.md:225 | results/temporal_live.md | verified-by-results-file (not re-run this session) | kept |
| C112 | exp 5: reviews 100 to 33, wrong payouts 8 to 0 (mix is an assumption) | docs/00-the-whole-story.md:226,255 | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged: 36 reviews, wrong payouts 10 to 0 | assumption-labeled | replaced with 100 to 36, 10 to 0; label present |
| C113 | Finding 2, Finding 3 (symbols, zero model calls, MAST's #1 mode), Finding 4 | docs/00-the-whole-story.md:230-234 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; MAST v3 still largest mode | verified-by-code | kept |
| C114 | Agents succeed 56.6%; 60% to 25% over eight runs | docs/00-the-whole-story.md:244 | No source named or found | unverified | removed |
| C115 | IDC 1000x agent API calls | docs/00-the-whole-story.md:245 | https://www.idc.com/resource-center/blog/agent-adoption-the-it-industrys-next-great-inflection-point/ | verified-by-url | reworded to the source: token and API call loads rise 1000x by 2027 |
| C116 | Gartner: 40% of agentic AI projects canceled by 2027 | docs/00-the-whole-story.md:245 | Primary returned 403; secondary copies only | unverified | removed |
| C117 | reconciliation ... already the most expensive manual job in finance | docs/00-the-whole-story.md:247 | No cost source | unverified | removed |
| C118 | In every finance team running agents, someone approves each refund by hand | docs/00-the-whole-story.md:253 | No source for "every" | unverified | "every" removed: "In a finance team running agents" |
| C119 | One integration: three lines or the MCP proxy; adapters are four methods | docs/00-the-whole-story.md:257-259 | easy.py, mcp_proxy.py and their tests; EffectTarget capture, validate_premises, apply, query | verified-by-code | kept |
| C120 | Why not the incumbents ... The seam is nobody's product | docs/00-the-whole-story.md:261 | Market claim, no source | unverified | last sentence removed |

## docs/01-problem.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C121 | solved for deterministic programs between 1975 and 2015; roughly two years old | docs/01-problem.md:50 | No source | unverified | dates removed |
| C122 | Today's frameworks keep one log line | docs/01-problem.md:67 | Contradicted in part by competitor runs | unverified | removed |
| C123 | It used to be microseconds inside one process. Now it's seconds | docs/01-problem.md:85 | No source | unverified | removed |
| C124 | Eight in ten enterprises ... (Kore.ai) | docs/01-problem.md:89 | https://www.kore.ai/research/agent-productivity-index-report | verified-by-url | kept |
| C125 | 61% of treasury teams (J.P. Morgan); 1.2% duplicates (Levvel) | docs/01-problem.md:90-91 | Secondary copies only | unverified | removed |
| C126 | IDC: G2000 agent use 10x, token and API call loads 1000x by 2027 | docs/01-problem.md:92 | https://www.idc.com/resource-center/blog/agent-adoption-the-it-industrys-next-great-inflection-point/ | verified-by-url | kept |
| C127 | Gartner (June 2025): over 40% of agentic AI projects canceled by end of 2027 | docs/01-problem.md:93 | Primary returned 403; secondary copies agree | unverified | removed |

## docs/02-contract.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C128 | recover() waits for claim_ttl, 120s default | docs/02-contract.md:22 | journal.py:46 `CLAIM_TTL = 120` | verified-by-code | kept |
| C129 | Duplicated work, MAST | docs/02-contract.md:43 | https://arxiv.org/html/2503.13657v3 (largest mode in v3); no percentage at this line | verified-by-url | kept |
| C130 | Stripe 24h key pruning | docs/02-contract.md:57 | https://docs.stripe.com/api/idempotent_requests | verified-by-url | kept |
| C131 | three baselines | docs/02-contract.md:65 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C132 | SHA-256 truncated to 48 bits | docs/02-contract.md:76 | journal.py:402 `hexdigest()[:12]` | verified-by-code | kept |
| C133 | key treated as expired 10 minutes early | docs/02-contract.md:78 | gate.py:60 `DEDUP_MARGIN = 600` | verified-by-code | kept |
| C134 | Stripe 30s, MCP 60s, 120s default | docs/02-contract.md:79 | stripe_api.py:60; mcp_proxy.py:75; journal.py:46 | verified-by-code | kept |
| C135 | Two-phase commit / Leach citation | docs/02-contract.md:86 | https://stripe.com/blog/idempotency | verified-by-url | kept |

## docs/03-landscape.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C136 | which piece nobody owns. Reviewed from primary docs and papers, Sept 12-13 2026 | docs/03-landscape.md:3 | Process claim, no log | unverified | removed |
| C137 | effects: no shipping system; research covers pieces | docs/03-landscape.md:22 | results/competitors/langgraph.md: docs pattern plus a re-check tied 29/29 | verified-by-results-file (not re-run this session) | replaced: "hand-written checks; research prototypes cover pieces" |
| C138 | Temporal activities at-least-once by default | docs/03-landscape.md:29 | https://docs.temporal.io/encyclopedia/retry-policies | verified-by-url | kept |
| C139 | Pydantic AI + Temporal/DBOS: a tool step that crashes mid-call re-runs the tool | docs/03-landscape.md:30 | https://pydantic.dev/docs/ai/integrations/durable_execution/temporal/ | verified-by-url | kept |
| C140 | Restate / DBOS / AWS Lambda: a step is at-least-once if the process dies before the result is saved | docs/03-landscape.md:31 | DBOS: https://docs.dbos.dev/architecture. Restate and Lambda not checked | unverified | kept; DBOS verified, Restate and Lambda need a source (logged) |
| C141 | Stripe idempotency: 24h window | docs/03-landscape.md:34 | https://docs.stripe.com/api/idempotent_requests | verified-by-url | kept |
| C142 | Cordon (Tsinghua, EuroSys 27) | docs/03-landscape.md:37 | https://arxiv.org/html/2606.17573 | verified-by-url | kept |
| C143 | Interlock row all yes | docs/03-landscape.md:42 | Self-rated | assumption-labeled | label added: "The Interlock row is self-rated" |
| C144 | Interlock is the only row where the dedup key is the recorded decision | docs/03-landscape.md:44 | Comparative within this table only | assumption-labeled | scoped: "In this table" |
| C145 | Cemri et al.: 1,600+ traces, 14 failure modes, step repetition 17.14% | docs/03-landscape.md:48 | https://arxiv.org/html/2503.13657v3 | verified-by-url | replaced: 1,642 traces in arXiv v3, 15.7% |
| C146 | duplicate_work row, zero model calls | docs/03-landscape.md:48 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C147 | Cognition: the rule a database would impose ... databases abandoned it for throughput | docs/03-landscape.md:49 | The blog does not discuss databases; no source | unverified | removed |
| C148 | Mosaic: not for LLM agents: 4-15x tokens, and re-running doesn't reproduce the plan | docs/03-landscape.md:51 | https://www.anthropic.com/engineering/multi-agent-research-system | verified-by-url | replaced with about 4x chat, 15x multi-agent; re-run clause removed |
| C149 | their own docs say why: if the process crashes or a request times out, the agent has no idea what already happened | docs/03-landscape.md:55 | No such sentence at https://pydantic.dev/docs/ai/integrations/durable_execution/temporal/ | verified-by-url | replaced with the docs' restart quote |
| C150 | durable@tier1 ties crash/dup/re-decision, fails changed-world rows | docs/03-landscape.md:57 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C151 | ATR motivating example is a refund agent | docs/03-landscape.md:73 | https://arxiv.org/html/2609.08015 | verified-by-url | kept |
| C152 | Commit Gates: evidence-source diversity beats verifier-model diversity | docs/03-landscape.md:77 | https://arxiv.org/abs/2609.10969 | verified-by-url | kept |
| C153 | SagaLLM (VLDB, arXiv 2503.11951); Agentic Transaction; Khan; APort OAP | docs/03-landscape.md:79 | arXiv IDs and titles verified; VLDB venue not shown on arXiv | verified-by-url | "VLDB" removed |
| C154 | What none of them joins ... That join is this repo | docs/03-landscape.md:81 | None-of-X claim | unverified | removed |
| C155 | In shipping software it's empty for a structural reason | docs/03-landscape.md:85 | Our reading, no source | assumption-labeled | label added: "Our reading of why no vendor sells this cell" |
| C156 | Seams like that are where Stripe, Twilio, and Plaid came from | docs/03-landscape.md:85 | Analogy, no source | unverified | removed |

## docs/04-integration.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C157 | Two exist in the repo (targets/payments.py, targets/repo.py) | docs/04-integration.md:17 | interlock/targets/ holds payments.py, repo.py, stripe_api.py | verified-by-code | replaced: three, with stripe_api.py |
| C158 | GitHub merge tier 2; Postgres tier 2; S3 tier 2 | docs/04-integration.md:22-24 | GitHub: results/scenarios/github_merge.md; Postgres and S3 are design mappings | assumption-labeled | kept |
| C159 | SendGrid tier 3: no lookup | docs/04-integration.md:25 | Secondary blog only | unverified | row removed |
| C160 | Slack post: search is eventual and unreliable; treat as 3 | docs/04-integration.md:26 | Not checked | unverified | row removed |
| C161 | MCP spec has no idempotency or transactional contract | docs/04-integration.md:34 | https://modelcontextprotocol.io/specification/2026-07-28/server/tools | verified-by-url | kept |
| C162 | Two-phase commit (Gray, 1978) | docs/04-integration.md:48 | https://arxiv.org/pdf/2310.04601 | verified-by-url | kept |
| C163 | one fsync per effect; tier 2 one query; tier 1 nothing | docs/04-integration.md:52 | journal.py `os.fsync` on every append: a committed effect writes four fsync'd entries (PROPOSED, AUTHORIZED, DISPATCHED, COMMITTED), not one | unverified | corrected in docs/04-integration.md to four appends per committed effect |

## docs/05-reading.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C164 | OCC, Kung & Robinson 1981; CaMeL; Anthropic post June 2025 | docs/05-reading.md:9,14,17 | URLs as in README rows; Anthropic post dated June 13, 2025 | verified-by-url | kept |
| C165 | SagaLLM. VLDB. | docs/05-reading.md:33 | arXiv page gives no venue | unverified | "VLDB" removed |
| C166 | Temporal at-least-once; Stripe charge_already_refunded; 24h pruning | docs/05-reading.md:41,44,45 | https://docs.temporal.io/encyclopedia/retry-policies; https://docs.stripe.com/error-codes; https://docs.stripe.com/api/idempotent_requests | verified-by-url | kept |
| C167 | partial refunds unprotected by charge_already_refunded | docs/05-reading.md:44 | Partial clause not found on the error-codes page | unverified | kept; logged (needs a decision) |

## docs/07-runtime.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C168 | runtime ~900 lines, one dependency psycopg | docs/07-runtime.md:11 | runtime/interlock_runtime/*.py is 1575 lines; `psycopg[binary]>=3.2,<4` verified | verified-by-code | line count removed; dependency kept |
| C169 | NOTICE credits all four | docs/07-runtime.md:36 | runtime/NOTICE | verified-by-code | kept |
| C170 | killpoints.py about 15 lines | docs/07-runtime.md:93 | 29 lines | unverified | line count removed |
| C171 | poll default 1.0; code_sha256 mismatch exits 2; min_send_budget 1.0; send_timeout 35, settle_margin 10, premise_max_age 5; lease ttl 30 | docs/07-runtime.md:384-409 | worker.py:36, :146, :163; runtime.py:61-63; effects.py:26-27, :233; stripe_api.py:60 | verified-by-code | kept |
| C172 | max_interval None means 100x initial; max_attempts 0 means unlimited | docs/07-runtime.md:420 | https://docs.temporal.io/encyclopedia/retry-policies; temporalio/common.py@1.32.0 | verified-by-url | kept |
| C173 | Better only where Temporal documents no mechanism; Worse: scale and throughput | docs/07-runtime.md:627,639 | Design section; results/runtime_prove.md and runtime_bench.md do not exist | assumption-labeled | kept |
| C174 | TLA base constants MaxClock 12, DedupAge 6, MaxCrashes 2 | docs/07-runtime.md:721 | spec/Runtime.cfg comment calls them base values; configs run use 10/5/1 | assumption-labeled | kept |
| C175 | expected TLC outcome table; S01-S14 predictions | docs/07-runtime.md:846,984 | Labeled as predictions; results/runtime_tlc.md absent | assumption-labeled | kept |
| C176 | Every broken config must produce a counterexample on the named invariant | docs/07-runtime.md:871 | A stated requirement; spec/README.md: NoFencing prediction revised; no committed TLC output | assumption-labeled | kept; logged (needs a decision) |
| C177 | planned harness: 20 failing runs, pay_881 10000 cents, 3 workers, 3 seeds, 100 seeds, 2,000 sweep, 8 parallel, latency n=1,000, closed loop 60s x 3 | docs/07-runtime.md:897-1089 | Plan text; scripts not built | assumption-labeled | kept |
| C178 | dedup_window 612s, downgrade at 12s | docs/07-runtime.md:987 | 612 minus DEDUP_MARGIN 600 | verified-by-code | kept |
| C179 | Temporal Cloud pricing | docs/07-runtime.md:1093 | https://temporal.io/pricing | verified-by-url | kept |
| C180 | live run: 2 LLM calls, 1 decision; pi_3UFMX888KhIqqdFL0cZUF1Zw 10000 cents; COMMITTED_BY_RETRY; one refund 2000; 3600s sleep shortened to 5s | docs/07-runtime.md:1181 | results/runtime_live_agent.md | verified-by-results-file (not re-run this session) | kept |
| C181 | 42 runtime tests pass in about 120s; stateful test seed 20260913 stats; 3 errors in test_integrations.MandateChecks | docs/07-runtime.md:1185-1187 | Runtime suites skipped this session (no ILR_DSN); full run has 0 errors | unverified | removed; replaced by the skip fact |

## docs/08-compliance-mapping.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C182 | None of these frameworks mentions agent receipts | docs/08-compliance-mapping.md:5 | None-of-X claim; texts not full-text searched | unverified | removed |
| C183 | optionally signed with HMAC-SHA256 | docs/08-compliance-mapping.md:14 | receipts.py:51 | verified-by-code | kept |
| C184 | BigQuery merge adds no rows; SIEM files write no lines; no real SIEM | docs/08-compliance-mapping.md:20-21 | results/export_live.md: `[32, 0]`, "NOT VERIFIED LIVE" | verified-by-results-file (not re-run this session) | kept |
| C185 | BigQuery best-effort dedup about a minute | docs/08-compliance-mapping.md:23 | https://docs.cloud.google.com/bigquery/docs/streaming-data-into-bigquery | verified-by-url | kept |
| C186 | EU AI Act Chapter III deferred to 2 Dec 2027 / 2 Aug 2028 under Reg. (EU) 2026/1744; OJ 24 July, in force 27 July | docs/08-compliance-mapping.md:60,150 | EUR-Lex returned empty; https://www.hunton.com/privacy-and-cybersecurity-law-blog/eu-digital-omnibus-on-ai-enters-into-force states the same dates | verified-by-url | kept |
| C187 | Digital Omnibus adopted 8 July 2026 | docs/08-compliance-mapping.md:150 | Not confirmed by any source | unverified | removed |
| C188 | AMBIGUOUS CEF severity 9 | docs/08-compliance-mapping.md:71 | export/siem.py:13; cloud_logging.py:27 | verified-by-code | kept |
| C189 | PCI 10.5.1: 12 months, 3 immediately available; 10.2.2 fields | docs/08-compliance-mapping.md:65-73,131 | Secondary only (pcidssguide, Basis Theory); labeled NOT VERIFIED in place | unverified | kept with its NOT VERIFIED label; logged (needs a decision) |
| C190 | AI Act Art. 19(1) and 26(6): at least six months | docs/08-compliance-mapping.md:73 | https://artificialintelligenceact.eu/article/19/, /article/26/ | verified-by-url | kept |
| C191 | Cloud Logging _Default 30 days; _Required 400 days | docs/08-compliance-mapping.md:73 | https://docs.cloud.google.com/logging/quotas | verified-by-url | kept |
| C192 | SEC Release 33-8810 II.A.1.d | docs/08-compliance-mapping.md:79 | https://www.sec.gov/rules/interp/2007/33-8810.pdf | verified-by-url | kept |
| C193 | SOC 2: 2017 TSC, March 2020 revision | docs/08-compliance-mapping.md:88 | https://arpio.io/wp-content/uploads/2020/08/trust-services-criteria.pdf | verified-by-url | kept |
| C194 | PCI 10.4.1.1 and 10.7.2 best practice until 31 March 2025 | docs/08-compliance-mapping.md:129 | https://listings.pcisecuritystandards.org/documents/PCI-DSS-v3-2-1-to-v4-0-Summary-of-Changes-r1.pdf | verified-by-url | kept |
| C195 | NIST AI RMF 1.0, AI 100-1, January 2023 | docs/08-compliance-mapping.md:164 | https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf | verified-by-url | kept |
| C196 | AP2 v0.2 does not cover refunds or revocation | docs/08-compliance-mapping.md:201 | Refund: v0.2 spec has no "refund" (AP2 @ e1ea56d). Revocation not checked by URL | unverified | kept; logged (revocation half needs a source) |

## docs/08-positioning.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C197 | demo run 09b281c272 | docs/08-positioning.md:20,157 | results/demo_live.md holds run `c47aff8b49` | verified-by-results-file (not re-run this session) | replaced with c47aff8b49 |
| C198 | attempt 2, 2 refunds, $40; REFUSED:stale_premise_at_recovery, 1 refund $20 | docs/08-positioning.md:24-27 | results/demo_live.md:23,33 | verified-by-results-file (not re-run this session) | kept |
| C199 | 22 cells, 18 live, 4 emulated; all 22 matched Stripe; plain Temporal $40 in a passing cell | docs/08-positioning.md:41 | `python3 experiments/e2e_audit.py` re-run 2026-09-13: `22/22 cells verified against Stripe` | verified-by-code | kept |
| C200 | ADK 16 cells: Interlock 5/5 46s, key 2/5 8s, hand check 5/5 10s | docs/08-positioning.md:42 | results/adk_live.md:26-29 | verified-by-results-file (not re-run this session) | kept |
| C201 | hand refund during outage: $40 key only, $20 gate | docs/08-positioning.md:44 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C202 | temporalio 1.32.0 ships contrib.google_adk_agents | docs/08-positioning.md:49 | https://pypi.org/pypi/temporalio/1.32.0/json | verified-by-url | kept |
| C203 | one $20 mandate paid one refund where it had paid three; no-range mandate refused three times | docs/08-positioning.md:81-83 | results/adk_mandate_probes.md:41, :69-71 (before-fix state is prose) | verified-by-results-file (not re-run this session) | kept |
| C204 | 8 receipts exported twice; 40 sent, 40 returned, 40 insertIds, 8/8; merge 32 then 0; stream 64 raw, 32 dedup; Trace spans 8, 9, 10; SIEM 32 then 0 | docs/08-positioning.md:117-125 | results/export_live.md | verified-by-results-file (not re-run this session) | kept |
| C205 | Temporal key 4/7 16s; hand re-check (about ten lines) 6/7 15s; Interlock 6/7 43s | docs/08-positioning.md:143-145 | results/e2e_live.md:28-30; backend/workflows.py:71-80 is 10 non-blank lines | verified-by-results-file (not re-run this session) | kept |
| C206 | hand check same as Interlock on 7/7 rows; ADK callback 5/5 | docs/08-positioning.md:149 | results/e2e_live.md:32-33; results/adk_live.md | verified-by-results-file (not re-run this session) | kept |
| C207 | demo 15s TTL, 10s Stripe; backend 40s/30s | docs/08-positioning.md:162 | demo/serve.py:47-48; backend/config.py:13-14 | verified-by-code | kept |
| C208 | 90-second script event times t=1s, 4.6s, 5.1-6.2s, 19.6s, 21.8s, 22.1s, finished 23.6s | docs/08-positioning.md:170-177 | results/demo_live.json live_run.events for c47aff8b49: 1.4, 5.9, 6.1-8.9, 20.9, 24.2, 24.3; elapsed 26.3 | verified-by-results-file (not re-run this session) | replaced with the recorded times |
| C209 | card text Violated $40 / Held $20 | docs/08-positioning.md:177 | results/demo_live.md:23,33 | verified-by-results-file (not re-run this session) | kept |
| C210 | 25.1s click to page; page clock 23.6s | docs/08-positioning.md:184-185 | results/demo_live.md:9-10, :18: 28.2s from the click, finished in 26.3s | verified-by-results-file (not re-run this session) | replaced with 28.2s and 26.3s |
| C211 | Temporal's 15s activity timeout dominates | docs/08-positioning.md:187 | demo/README.md:91 | verified-by-code | kept |
| C212 | revoked run 49da4aa4cf: hand check REFUSED:lease, Interlock REFUSED:lease_at_recovery, 25.1s | docs/08-positioning.md:192-194 | results/demo_live_revoked.md: run e7c266e058, 2 columns, `REFUSED:lease_at_recovery`, 32.1s from the click | verified-by-results-file (not re-run this session) | replaced: run e7c266e058, no hand-check column, 32.1s |
| C213 | 7/7, 15s vs 43s; 5/5, 10s vs 46s | docs/08-positioning.md:218-220 | results/e2e_live.md; results/adk_live.md | verified-by-results-file (not re-run this session) | kept |
| C214 | demo TTL: Interlock 16.3s vs plain 16.7s | docs/08-positioning.md:222 | results/demo_live.md:23,33: 15.6s and 17.6s crash to close | verified-by-results-file (not re-run this session) | replaced with 15.6s against 17.6s |
| C215 | unsigned receipts, signed=None | docs/08-positioning.md:224-226 | results/e2e_live.md, results/demo_live.md:40 | verified-by-results-file (not re-run this session) | kept |
| C216 | unrelated $5 refund stopped the $20, short by $20 | docs/08-positioning.md:229-231 | results/e2e_live.md `unrelated_refund_during_outage` | verified-by-results-file (not re-run this session) | kept |
| C217 | The project's key returned 429 RESOURCE_EXHAUSTED | docs/08-positioning.md:241 | No results file; prose only in docs/09-research-adk.md:88 | unverified | removed; "Gemini is not verified live" kept |
| C218 | AI Act Chapter III moved to 2 Dec 2027 / 2 Aug 2028 | docs/08-positioning.md:247 | Hunton secondary; EUR-Lex empty | verified-by-url | kept |
| C219 | Cloud Logging _Default keeps 30 days | docs/08-positioning.md:252 | https://docs.cloud.google.com/logging/quotas | verified-by-url | kept |
| C220 | Python, zero dependencies | docs/08-positioning.md:271 | pyproject.toml | verified-by-code | kept |
| C221 | 22 cells, all matched Stripe; ADK 16 live cells | docs/08-positioning.md:293-296 | `python3 experiments/e2e_audit.py` re-run 2026-09-13: `22/22 cells verified against Stripe`; results/adk_live.md | verified-by-code | kept |
| C222 | ten-line re-check tied, 15s vs 43s, 2 scenarios / 4 cells emulated | docs/08-positioning.md:322-325 | results/e2e_live.md; e2e_audit re-run flags 4 EMULATED cells | verified-by-results-file (not re-run this session) | kept |

## docs/09-research-adk.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C223 | google-adk 2.9.0 latest, needs Python 3.10+ | docs/09-research-adk.md:7 | https://pypi.org/pypi/google-adk/json | verified-by-url | kept |
| C224 | ADK llm_agent.py lines 101-129 and 530-566 | docs/09-research-adk.md:14 | google-adk 2.9.0 wheel (llm_agent.py only) | verified-by-url | kept |
| C225 | ADK smoke output: fn_response lines, tool body ran once (verified live) | docs/09-research-adk.md:78-86 | experiments/adk_smoke.py exists; output not committed | unverified | kept; logged (research log, needs a decision) |
| C226 | Gemini: 429 RESOURCE_EXHAUSTED | docs/09-research-adk.md:88,119 | Prose only | unverified | kept in the research log; removed from docs/08-positioning.md; logged |
| C227 | temporalio 1.32.0 pins google-adk>=2.2.0,<3 and mcp>=1.24,<2 | docs/09-research-adk.md:99 | https://pypi.org/pypi/temporalio/1.32.0/json | verified-by-url | kept |

## docs/09-research-ap2.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C228 | AP2 repo at e1ea56d; tags v0.1.0, v0.2.0 b4587ac | docs/09-research-ap2.md:3 | https://github.com/google-agentic-commerce/AP2 | verified-by-url | kept |
| C229 | Two mandate types, four vct values | docs/09-research-ap2.md:17 | AP2 spec and SDK @ e1ea56d | verified-by-url | kept |
| C230 | The string "refund" does not appear in the v0.2 spec or the Python SDK | docs/09-research-ap2.md:21 | SDK has `refund_period` (models/payment_request.py:63) and `requires_refundability` (models/mandate.py:69) | verified-by-url | replaced: not in the spec; the SDK has those two fields |
| C231 | exp/iat with 300s default skew | docs/09-research-ap2.md:36 | code/sdk/python/ap2/sdk/mandate.py:182 | verified-by-url | kept |
| C232 | AP2 SDK test suite: 2 failed, 186 passed | docs/09-research-ap2.md:136 | External repo run; output not committed | unverified | kept; logged (research log, needs a decision) |
| C233 | AP2 probe table 1-15 | docs/09-research-ap2.md:151 | Probe script in the appendix; output not committed | unverified | kept; logged (research log, needs a decision) |

## docs/09-research-gcp-audit.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C234 | Future timestamp limit 1 day, else INVALID_ARGUMENT | docs/09-research-gcp-audit.md:26-27 | API doc mirror says entries over 24h ahead are not listed, not that they are rejected | verified-by-url | "else INVALID_ARGUMENT" removed; 1-day limit kept |
| C235 | LogEntry 256 KiB, write request 10 MB; labels 64, key 512 B, value 64 KB | docs/09-research-gcp-audit.md:36-37 | https://docs.cloud.google.com/logging/quotas; LogEntry reference | verified-by-url | kept |
| C236 | Logging dedup: returns once; batch with future timestamp HTTP 400 | docs/09-research-gcp-audit.md:44-45 | Probe not committed | unverified | kept; logged (research log, needs a decision) |
| C237 | Cloud Logging _Default 30 days; no BigQuery costs for linked dataset | docs/09-research-gcp-audit.md:56,65 | https://docs.cloud.google.com/logging/quotas; https://docs.cloud.google.com/logging/docs/log-analytics | verified-by-url | kept |
| C238 | BigQuery best-effort dedup one minute; sandbox no streaming or DML, 60-day expiry | docs/09-research-gcp-audit.md:76,81 | https://docs.cloud.google.com/bigquery/docs/streaming-data-into-bigquery; https://docs.cloud.google.com/bigquery/docs/sandbox | verified-by-url | kept |
| C239 | BigQuery insertAll twice gives 1 | docs/09-research-gcp-audit.md:91 | Probe not committed | unverified | kept; logged (research log, needs a decision) |
| C240 | Trace limits 512 B / 64 KiB / 1024 / 1024 B / 256 / 128 | docs/09-research-gcp-audit.md:112 | https://docs.cloud.google.com/stackdriver/quotas | verified-by-url | kept |
| C241 | Trace 404 then 200 after about 10s | docs/09-research-gcp-audit.md:121 | Probe not committed | unverified | kept; logged (research log, needs a decision) |
| C242 | Original Art. 113: 2 Aug 2026; Art. 6(1) from 2 Aug 2027 | docs/09-research-gcp-audit.md:232 | https://artificialintelligenceact.eu/article/113/ | verified-by-url | kept |
| C243 | Digital Omnibus adopted 8 July 2026 | docs/09-research-gcp-audit.md:233 | Not confirmed by any source | unverified | removed |

## docs/10-scenarios.md

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C244 | stripe_dispute, shared_cap, billing_credit, github_merge, calendar, email_tier3, gcp_resource rows | docs/10-scenarios.md:26-50 | results/scenarios/README.md:28-54; shared_cap.md:16-17 | verified-by-results-file (not re-run this session) | kept |
| C245 | gap probe lost $120 on $100 | docs/10-scenarios.md:67 | results/scenarios/stripe_dispute.md:30, :108 | verified-by-results-file (not re-run this session) | kept |
| C246 | hand_lock 40/40 at 0.5/1.4s; interlock_core 25/40 | docs/10-scenarios.md:70-72 | results/scenarios/shared_cap.md:16-17 | verified-by-results-file (not re-run this session) | kept |
| C247 | head re-read alone passed on a lagging read in 3/3 restarts; 6/6 vs 0/6 forgeries; about 25s vs 5s | docs/10-scenarios.md:79-81 | results/scenarios/github_merge.md Findings: restarts #22, #28, #34 passed the head check and GitHub refused with 409; :71 forgeries | verified-by-results-file (not re-run this session) | kept |
| C248 | calendar 7/7 vs 0/7, 31.2s vs 0.6s; email about 36s vs 3s, 24h window read from code; gcp about 31s vs 2s | docs/10-scenarios.md:87-98 | results/scenarios/README.md:42-54; email_tier3.md:78 label; gcp_resource.md:13 | verified-by-results-file (not re-run this session) | kept |
| C249 | tied on all seven; slower; TTLs 25 to 40s | docs/10-scenarios.md:103-107 | scenarios/github_merge/agent.py:27 `CLAIM_TTL = 25`; calendar 30, gcp 30, email 35, stripe_dispute 40, billing 40 | verified-by-code | kept |
| C250 | no_check violated in six of seven | docs/10-scenarios.md:110 | results/scenarios/*.md | verified-by-results-file (not re-run this session) | kept |
| C251 | GET /v1/accounts 0 connected accounts | docs/10-scenarios.md:117 | results/scenarios/connect_payout.json | verified-by-results-file (not re-run this session) | kept |
| C252 | core CLAIM_TTL 120s; rewritten final entry passed 6/6 | docs/10-scenarios.md:143,152 | journal.py:46; github_merge.md:71 | verified-by-code | kept |

## docs/interlock-explained.html

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C253 | Finance teams use it to stop hand-approving every agent action | docs/interlock-explained.html:104 | No customer data | unverified | removed |
| C254 | Plain retry (most agents today) | docs/interlock-explained.html:123 | No source | unverified | "most agents today" removed |
| C255 | The five stops are the five moments a real process can die | docs/interlock-explained.html:127 | A simplified model | assumption-labeled | label added: "a simplified model" |
| C256 | Two Generals problem (1975) | docs/interlock-explained.html:133 | URL as in README row | verified-by-url | kept |
| C257 | Every framework today collapses these into one log line | docs/interlock-explained.html:147 | Contradicted in part by competitor runs | unverified | removed |
| C258 | tier 1 exactly once; tier 2 exactly once plus a read; tier 3 at most once | docs/interlock-explained.html:183-185 | gate.py:282 downgrades tier 1 past `dedup_window - DEDUP_MARGIN` | verified-by-code | tier-1 guarantee scoped: "while the service still holds the key" |
| C259 | Two baselines | docs/interlock-explained.html:192 | refund_agent.md has 3 baselines; the page table shows 2 | verified-by-code | replaced: "two of the repo's three baselines" |
| C260 | hardcoded refund rows and coding rows | docs/interlock-explained.html:320,331 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C261 | key rows run on real Stripe and Temporal, with the same outcomes | docs/interlock-explained.html:205 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match; results/temporal_live.md | verified-by-results-file (not re-run this session) | kept |
| C262 | The protocol is about 250 lines | docs/interlock-explained.html:219 | wc -l: 828 | unverified | line count removed |
| C263 | Effects: Nobody; Nobody owns the seam; seams are where payment processors ... came from | docs/interlock-explained.html:232-234 | results/competitors: hand-written checks held; analogy has no source | verified-by-results-file (not re-run this session) | cell replaced with "Hand-written checks; research covers pieces"; seam sentences removed |
| C264 | checkpoint 1 scored 6 / 5 / 2.5 | docs/interlock-explained.html:242 | docs/checkpoints/checkpoint-1.md:21-24 | verified-by-results-file (not re-run this session) | kept |
| C265 | 41 tests | docs/interlock-explained.html:244 | `python3 -m unittest discover -s tests`: `Ran 405 tests`, `OK (skipped=52)` | unverified | removed |
| C266 | record the 90-second video; ten interviews in 90 days | docs/interlock-explained.html:265-267 | Plans under "What's next" | assumption-labeled | kept |

## site/index.html

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C267 | receipt: happened once, allowed when it fired, facts still held; Python or MCP, Temporal optional | site/index.html:7 | receipts.py verify; mcp_proxy.py; temporal.py. No tier qualifier in the meta description | verified-by-code | kept; logged (tier caveat needs a decision) |
| C268 | crash mid-refund: $40 without, $20 with | site/index.html:17 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty: crash_before_ack naive $40, gate $20 | verified-by-code | kept |
| C269 | Open source, Python, MIT | site/index.html:588 | LICENSE line 1 | verified-by-code | kept |
| C270 | case #4471, "customer · 2 min ago", $100/$20 | site/index.html:593,601-603 | Scenario inputs match refund_agent.md; "2 min ago" was illustrative | assumption-labeled | label added: ticket now "example case · timings not measured" |
| C271 | hero trace durations | site/index.html:618-643 | Hand-set values | assumption-labeled | covered by the ticket label above |
| C272 | Paid twice, $40 | site/index.html:613-614,1289 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty: naive crash_before_ack `RETRIED $40` | verified-by-code | kept |
| C273 | $20. Interlock found the refund already landed and sent nothing. | site/index.html:649,1291 | True at tier 2: `python3 demo.py 2` `COMMITTED_ON_QUERY`; tier 1 resends under the key | verified-by-code | reworded to the lookup path: "looked the refund up, found it already landed" |
| C274 | broke a $20 refund 10 ways; same faults for every approach | site/index.html:659-660 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C275 | Plain retry 9 wrong; Request IDs 5; Durable workflows 5; Interlock 0 | site/index.html:663-667 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty (tier 1 columns; durable is a simulation) | verified-by-code | kept |
| C276 | What most agents do today | site/index.html:664 | No source | unverified | removed: now "Re-run the step on restart" |
| C277 | all-10-faults table | site/index.html:676-685 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C278 | out-of-sync orders and refunds tables | site/index.html:702-723 | Illustrative | assumption-labeled | label added to both window titles: "example" |
| C279 | timeline 0:00 / 0:02 / 0:40 / 1:10 | site/index.html:754-771 | Illustrative; fault matches refund_during_outage | assumption-labeled | label added: "An example timeline" |
| C280 | $40 on a $20 refund | site/index.html:777 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C281 | That fact stopped being true 30 seconds before the retry | site/index.html:778 | Derived from illustrative times | unverified | removed |
| C282 | recovery trace durations, 5.20s clock | site/index.html:797-811 | Hand-set | assumption-labeled | label added to the section lede: "an illustration; its timings are not measurements" |
| C283 | Second refund blocked, $20 total | site/index.html:814 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty: `REFUSED:stale_premise_at_recovery $20` | verified-by-code | kept |
| C284 | four faults, journal entries from recorded run; demo totals and console lines | site/index.html:826-833,1355-1392 | viewer/traces.js from refund_agent.py; totals match refund_agent.md | verified-by-code | kept |
| C285 | Temporal snippet: 30s timeout, max 5 attempts | site/index.html:890-892 | Example configuration in a code sample | assumption-labeled | kept; logged (no visible label; needs a decision) |
| C286 | without: $40, 2 refunds; with: $20, 1 refund | site/index.html:958-972 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C287 | Happened once: one $20 refund, never sent twice | site/index.html:991 | gate@tier1 column; verify() `happened_once` | verified-by-code | kept |
| C288 | Signed with a key the payment service also holds | site/index.html:995 | receipts.py:51 supports it; every live receipt reports `signed=None` | verified-by-code | reworded: "Can be signed" |
| C289 | Change $20 to $2,000 and the check fails, naming the step that was changed | site/index.html:1000 | `test_edited_amount_is_detected` passes; naming the step is not asserted | verified-by-code | "naming the step" removed |
| C290 | 3 faults on Stripe, 4 on Temporal, same results | site/index.html:1001 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match; results/temporal_live.md | verified-by-results-file (not re-run this session) | kept |
| C291 | Fewer approvals. Zero wrong refunds. (heading) | site/index.html:1013 | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged; mix is an assumption | assumption-labeled | label added to the lede: synthetic day, mix is an assumption, 100 to 36 |
| C292 | Finance teams put a person on every action their agents take | site/index.html:1014 | No source | unverified | removed: now "When a person approves every agent action" |
| C293 | 0.8% to 2% of payments go out duplicated or wrong, from the best finance teams to the worst (APQC) | site/index.html:1019 | https://trustmi.ai/resource/the-duplicate-payment-dilemma/ quotes APQC: "duplicate payments represent .8%-2% of total spend or disbursements"; no best-to-worst framing | verified-by-url | removed from the site: only secondary vendor-blog sources |
| C294 | 0.1% to 0.5% paid twice, even at careful organizations (IOFM) | site/index.html:1020 | https://transparentglobal.com/blog/what-percentage-of-ap-spend-is-lost-to-duplicate-payments-industry-benchmarks/: "Between 0.1% and 0.5% of total AP spend is affected by duplicate payments or overpayments", not attributed to IOFM | verified-by-url | removed from the site: only secondary vendor-blog sources |
| C295 | $15 to $16 per invoice; IOFM and Levvel; 62% labor from APQC; compiled by Resolve | site/index.html:1021 | https://resolvepay.com/blog/13-statistics-that-quantify-cost-per-invoice-in-manual-vs-automated-flows: Levvel and APQC; IOFM not cited for this | verified-by-url | IOFM removed from the attribution |
| C296 | Under 15% of finance leaders let AI act on its own in six of seven processes (Avalara, 1,500+) | site/index.html:1025 | https://www.journalofaccountancy.com/news/2026/jul/are-finance-leaders-moving-too-fast-on-agentic-ai/ says organizations | verified-by-url | "finance leaders" replaced with "organizations" |
| C297 | 23% say accountability for a serious AI error would be unclear | site/index.html:1026 | same Journal of Accountancy URL | verified-by-url | kept |
| C298 | 95.5% added a safeguard, most often human-in-the-loop; 750 IT leaders | site/index.html:1027 | https://www.avepoint.com/blog/strategy-blog/human-in-the-loop-ai; https://www.avepoint.com/blog/manage/state-of-ai-2026-report | verified-by-url | kept |
| C299 | calculator defaults: 2,000 actions/day, 5 min, $50/hr, 250 workdays | site/index.html:1037-1043 | experiments/approval_cost.py defaults; labeled under Assumptions | assumption-labeled | kept |
| C300 | Still reviewed with Interlock 33%; the 33% comes from the synthetic day | site/index.html:1044,1046,1059 | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged: rules + Interlock 36 of 100 | assumption-labeled | replaced with 36 (site and experiments/approval_cost.py default) |
| C301 | full-time reviewer = 8 hours | site/index.html:1046,1525 | Stated at :1046 | assumption-labeled | kept |
| C302 | save $1,395,833 a year; 14 reviewers; with Interlock $687,500; about 6.9 reviewers | site/index.html:1051-1061 | `python3 experiments/approval_cost.py` at 0.36: saved $1,333,333.33, with $750,000.00; 20.83 x 0.64 = 13.3, 20.83 x 0.36 = 7.5 | verified-by-code | replaced with $1,333,333, 13, $750,000, about 7.5 |
| C303 | every action approved $2,083,333; about 21 reviewers; one approval $4.17 | site/index.html:1054-1063 | `python3 experiments/approval_cost.py` | verified-by-code | kept |
| C304 | stale approval timeline 9:00/11:40/15:00 | site/index.html:1070-1088 | Illustrative; behavior matches approval_inbox "stale approvals caught" | assumption-labeled | kept; logged (no visible label; needs a decision) |
| C305 | Others stop repeats. None checks if the action should still happen. None of them asks whether the reason is still true. | site/index.html:1100-1101 | results/competitors/langgraph.md (checked 29/29) and dbos.md (dbos_checked 3/3): the re-check is user-written | verified-by-results-file (not re-run this session) | replaced: the check "is left to you" / "a check you write yourself" |
| C306 | Request IDs: Stripe and most payment services | site/index.html:1107 | No source for "most" | unverified | "and most payment services" removed |
| C307 | Interlock: chained and signed | site/index.html:1113 | Signing optional; every live receipt unsigned | verified-by-code | replaced: "chained, optionally signed" |
| C308 | durable workflows replay the old decision; Interlock needs none of these, fits inside them | site/index.html:1107-1112 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty; easy.py, temporal.py, mcp_proxy.py | verified-by-code | kept |
| C309 | runs inside plain Python, Temporal, MCP, a LangGraph tool | site/index.html:1156 | langchain_tools.py exists; `test_inside_a_langgraph_tool_node` passes locally with langchain-core, skipped in CI | verified-by-code | kept; README says passes locally, skipped in CI |
| C310 | IDs help on crash and double click, not on change during outage | site/index.html:1175 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C311 | real Temporal: $40 alone, $20 with Interlock | site/index.html:1179 | results/temporal_live.md:11 | verified-by-results-file (not re-run this session) | kept |
| C312 | $400 refund for a flagged customer stays with a person | site/index.html:1183 | Example amount in a hypothetical | assumption-labeled | kept |
| C313 | hand-written check tied on money in every live case; median 43s vs 15 to 16s | site/index.html:1187-1191 | results/e2e_live.md:28-33 | verified-by-results-file (not re-run this session) | kept |
| C314 | ordinary send adds a journal write and one read | site/index.html:1191 | journal.py fsync on dispatch; no benchmark | verified-by-code | kept |
| C315 | crash demo in one command; demo.py 2, no dependencies, MIT | site/index.html:1207-1210 | `python3 demo.py 2`; pyproject; LICENSE | verified-by-code | kept |

## tests/README.md (generated by tests/report.py)

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C316 | 338 tests, 329 passed, 9 skipped | tests/README.md:7,16 | `python3 -m unittest discover -s tests`: `Ran 405 tests`, `OK (skipped=52)`. report.py reads the count from a live run; the page is stale, not the source | verified-by-code | kept; regenerate with `python3 tests/report.py` (writes tests/README.md) |
| C317 | CI 3.9/3.12/3.13, fails on results drift | tests/README.md:8 | .github/workflows/test.yml | verified-by-code | kept |
| C318 | 282 Stripe payments and subscriptions across 6 results files | tests/README.md:9 | Scratch re-run of report.py's regex over results/stripe_live.md 9, e2e_live.md 22, stripe_dispute.md 15, shared_cap.md 200, billing_credit.md 18, email_tier3.md 18 = 282 | verified-by-code | kept |
| C319 | e2e audit 22/22 | tests/README.md:9 | `python3 experiments/e2e_audit.py` re-run 2026-09-13: `22/22 cells verified against Stripe` | verified-by-code | kept |
| C320 | 8 scenarios written, 7 ran, 1 blocked; held sums 17/67, 67/67, 98/114 | tests/README.md:10 | results/scenarios/README.md:28-54 | verified-by-results-file (not re-run this session) | kept |
| C321 | 65 of 95 (68.4%) cleared, 65 verify | tests/README.md:11 | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged | assumption-labeled | kept |
| C322 | bugs 15 / 30 (33 fixes) / 6, each with a test | tests/README.md:12 | Counts of the lists in report.py; no test-to-bug mapping (regression tests 12 / 37 / 9) | unverified | kept (generated; the listed counts are not wrong); logged. report.py no longer reads the count from README.md |

## results/ (generated; not edited)

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C323 | refund matrix 11 x 6; durable@tier1 fails every changed-world row | results/refund_agent.md | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C324 | coding matrix 7 x 3 | results/coding_agents.md:8-16 | `python3 experiments/run_all.py` re-run; `git diff -I '^Generated' -- results/` empty | verified-by-code | kept |
| C325 | every parallel-agent tool today: git checks text... | results/coding_agents.md:31-32 | No source; generated file | unverified | not edited (generated); logged |
| C326 | MAST 17% of 1,600 traces | results/coding_agents.md:21,33-34 | arXiv v3: 15.7% of 1,642 | unverified | not edited (generated); logged |
| C327 | inbox table and scoreboard | results/approval_inbox.md | `python3 experiments/approval_inbox.py` re-run; results/approval_inbox.md unchanged | assumption-labeled | kept |
| C328 | repair_loop table | results/repair_loop.md | `python3 experiments/repair_loop.py` re-run, unchanged | assumption-labeled | kept |
| C329 | repair_live_model table; no API failures | results/repair_live_model.md:3-12 | file as quoted | verified-by-results-file (not re-run this session) | kept |
| C330 | Stripe live rows and 9 PaymentIntents | results/stripe_live.md:9-31 | Stripe re-audit 2026-09-13: read-only GET /v1/refunds per PaymentIntent, 9/9 match | verified-by-code | kept |
| C331 | escalation live: 9500 cents from 3 refunds ($30 hand, $50 agent, $15 after SLA) | results/escalation_live.md:29-30 | Stripe re-audit: pi_3UFOFi88KhIqqdFL1ueAaUx9 holds exactly re_...Qpt3qv8 3000, re_...ebviQSB 5000, re_...obdhASH 1500 | verified-by-code | kept |
| C332 | Temporal live rows | results/temporal_live.md:10-13 | `experiments/temporal_live.py` re-run on a local Temporal dev server at de39e1e: identical tables, timestamp only | verified-by-code | kept |
| C333 | e2e tallies 4/7, 6/7, 6/7 and medians; AMBIGUOUS only in emulated row | results/e2e_live.md:28-36,104 | `python3 experiments/e2e_audit.py` re-run 2026-09-13: `22/22 cells verified against Stripe` (cents only; timings not re-checked) | verified-by-results-file (not re-run this session) | kept |
| C334 | ADK, mandate probes, demo pages, export, runtime live agent | results/adk_live.md, adk_mandate_probes.md, demo_*.md, export_live.md, runtime_live_agent.md | files as quoted in the code verification | verified-by-results-file (not re-run this session) | kept |
| C335 | scenario rows, gap probe $120, forgeries 6/6, 25 of 25 calendar events deleted | results/scenarios/*.md | files as quoted | verified-by-results-file (not re-run this session) | kept |
| C336 | hand_check about fifteen lines | results/scenarios/email_tier3.md:60 | scenarios/email_tier3/systems.py:57-80: 18 lines without def and docstring | unverified | not edited (generated); logged |
| C337 | competitor results (ADK confirmation, DBOS, LangGraph, open-multi-agent, OpenAI Agents SDK, closed and protocols) | results/competitors/*.md | files as quoted; competitor scripts not run per the hard rules | verified-by-results-file (not re-run this session) | kept |
| C338 | 70/70 quotes found | results/competitors/closed_and_protocols.md:3 | Script not run | unverified | not edited (generated); logged |

## spec/ and research/ (outside this session's edit scope)

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C339 | spec base constants; constants actually run | spec/README.md:53-64 | spec/Runtime.cfg | verified-by-code | kept |
| C340 | State spaces: @@STATES@@ | spec/README.md:77 | Placeholder unfilled | unverified | not edited; logged |
| C341 | MaxClock 8: 6.6M states; NoFencing 3.35M / 12.4M / 3.8M; FencedWrites in 239 states; TLC finds first two | spec/README.md:54-55,142-153 | No committed TLC output | unverified | not edited; logged |
| C342 | TLC 2026.09.12.025210 (rev 867aefb) from v1.8.0 | spec/README.md:26 | https://github.com/tlaplus/tlaplus/releases/tag/v1.8.0 (rev and asset date; build string not seen) | verified-by-url | kept |
| C343 | Last tagged stable is 1.7.4 (2020) | research/proof-tools.md:20-21 | https://github.com/tlaplus/tlaplus/releases: v1.7.4 published 2024-08-05 | unverified | not edited; logged |
| C344 | 30-line wrapper; about 40-line loop | research/agent-integrations.md:41,97 | Estimate, no code | unverified | not edited; logged |
| C345 | cedarpy Allow 30 / Deny 80, 0.092 ms | research/authority-receipts-events.md:28-30 | Scratch script not committed | unverified | not edited; logged |
| C346 | java 26.0.2 and 17.0.20; 15-line TLC spec verified locally | research/proof-tools.md:9,25 | Local checks, not committed | unverified | not edited; logged |
| C347 | Apalache Java 21+; OpenFGA Postgres 14+ / MySQL 8 | research/proof-tools.md:42; research/authority-receipts-events.md:25 | Not stated on the install or configure pages | unverified | not edited; logged |
| C348 | package versions, licenses, dates, Temporal limits and defaults, RFC 9162 sections, Stripe webhook retries, NOTIFY 8000 bytes, Absurd line counts | research/*.md | PyPI JSON, GitHub API, docs.temporal.io, datatracker.ietf.org, docs.stripe.com/webhooks, postgresql.org (per the URL verification) | verified-by-url | kept |

## Lock-in follow-ups

| id | claim | where | what proves it | status | this session |
|---|---|---|---|---|---|
| C900 | Agent checkpoints (LangGraph): won't repeat the same request: No | site/index.html (comparison table) | results/competitors/langgraph.md: the docs pattern re-runs the node and relies on Stripe's idempotency key to avoid a second refund | verified-by-results-file (not re-run this session) | reworded: "Only through the tool's own key" |
| C901 | Gives a receipt both sides can check: Yes, chained, optionally signed | site/index.html (comparison table) | results/competitors/langgraph.md: unsigned verify() misses a consistently rewritten chain; keyed verify() detects it | verified-by-results-file (not re-run this session) | kept: "optionally signed" already states the key is needed |
