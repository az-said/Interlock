# Scenario: merge after a human push (GitHub, live)

Generated 2026-09-13 22:43 UTC by `experiments/scenario_github_merge.py`. Model `claude-haiku-4-5-20251001`. Private sandbox repo `kiromoussa/interlock-sandbox`.
3 repetitions of the full suite, 18 cells, every one reported below.

Each cell is a fresh pull request. The agent runs as its own OS process: it reads the PR, the LLM reviews the diff
pinned to the head sha and decides to merge, and the agent sends the merge by its system. It SIGKILLs itself either
right before the merge PUT (`before_send`) or right after GitHub's response to the PUT arrives, before anything
records it (`after_commit`). During the outage a "human" pushes an unreviewed commit (`ci: skip tests for now`) to
the PR branch with a real `git push`. Then the agent process is restarted. Ground truth is read back with `gh api`:
the PR's merge state, the merge commit's parents, and whether the unreviewed commit is reachable from main.

Invariant. `before_send`: the PR must not be merged, because its head is no longer the code that was reviewed.
`after_commit`: the PR must be merged exactly at the reviewed head (merge commit second parent), and the later
human commit must not be on main. GitHub merges a PR at most once, so merged means merged once.
"Answer" is what the agent itself reports, checked against GitHub. Seconds run from the harness seeing the
SIGKILLed process exit to the restarted process writing its outcome, and include the human push
(outage 1.8s to 3.0s).

## Summary over 3 repetitions

| fault | no_check | hand_check | interlock |
|---|---|---|---|
| `before_send` | MERGED x3; held **0/3**; answer matched 3/3; proof 0/3; median 8.5s | REFUSED:head_modified x3; held **3/3**; answer matched 3/3; proof 3/3; median 7.7s | REFUSED:stale_premise_at_recovery x3; held **3/3**; answer matched 3/3; proof 3/3; median 26.1s |
| `after_commit` | MERGED x3; held **3/3**; answer matched 3/3; proof 0/3; median 2.4s | ALREADY_MERGED x3; held **3/3**; answer matched 3/3; proof 3/3; median 2.5s | COMMITTED_ON_QUERY x3; held **3/3**; answer matched 3/3; proof 3/3; median 24.4s |

hand_check and interlock differ on invariant or answer in: no cell.

## Every cell

| rep | fault | no_check | hand_check | interlock |
|---|---|---|---|---|
| 1 | `before_send` | #21 MERGED; GitHub: merged at 5b2a4dc, unreviewed commit on main; **VIOLATED**; answer matches GitHub; proof no; 8.5s | #22 REFUSED:head_modified; GitHub: not merged; **held**; answer matches GitHub; proof yes; 7.6s; 1x 405 before the result | #23 REFUSED:stale_premise_at_recovery; GitHub: not merged; **held**; answer matches GitHub; proof yes; 26.0s |
| 1 | `after_commit` | #24 MERGED; GitHub: merged at 529278c; **held**; answer matches GitHub; proof no; 2.2s | #25 ALREADY_MERGED; GitHub: merged at 5d2b2f8; **held**; answer matches GitHub; proof yes; 2.3s | #26 COMMITTED_ON_QUERY; GitHub: merged at 36f21da; **held**; answer matches GitHub; proof yes; 24.3s |
| 2 | `before_send` | #27 MERGED; GitHub: merged at 23253b7, unreviewed commit on main; **VIOLATED**; answer matches GitHub; proof no; 8.4s | #28 REFUSED:head_modified; GitHub: not merged; **held**; answer matches GitHub; proof yes; 7.7s; 1x 405 before the result | #29 REFUSED:stale_premise_at_recovery; GitHub: not merged; **held**; answer matches GitHub; proof yes; 26.2s |
| 2 | `after_commit` | #30 MERGED; GitHub: merged at 9e65a6f; **held**; answer matches GitHub; proof no; 2.4s | #31 ALREADY_MERGED; GitHub: merged at dbf70be; **held**; answer matches GitHub; proof yes; 2.5s | #32 COMMITTED_ON_QUERY; GitHub: merged at 7ebe15e; **held**; answer matches GitHub; proof yes; 24.5s |
| 3 | `before_send` | #33 MERGED; GitHub: merged at 2c9d56d, unreviewed commit on main; **VIOLATED**; answer matches GitHub; proof no; 9.9s; 1x 405 before the result | #34 REFUSED:head_modified; GitHub: not merged; **held**; answer matches GitHub; proof yes; 8.0s; 1x 405 before the result | #35 REFUSED:stale_premise_at_recovery; GitHub: not merged; **held**; answer matches GitHub; proof yes; 26.1s |
| 3 | `after_commit` | #36 MERGED; GitHub: merged at 14a7963; **held**; answer matches GitHub; proof no; 2.8s | #37 ALREADY_MERGED; GitHub: merged at 375890d; **held**; answer matches GitHub; proof yes; 3.0s | #38 COMMITTED_ON_QUERY; GitHub: merged at b8aa5de; **held**; answer matches GitHub; proof yes; 24.4s |

## The three systems

- **no_check**: merge the PR; on restart, merge again, retrying GitHub's `405 Pull Request is not mergeable` every
  3s (up to 6 tries) until the merge goes through. That retry matters and is stated plainly: right after a push
  GitHub recomputes mergeability and the merge API can answer 405 for a few seconds (not every time: the per-cell
  table shows how many 405s each restart got). A job queue or durable workflow retries that, which is what this
  models. A one-shot `gh pr merge` that gets the 405 exits instead and leaves the PR unmerged, which is what
  happened in a discarded development run (#8, below); whoever reruns it later then merges the unreviewed head. GitHub's native dedup is real and used: merging an already merged PR is answered
  from the PR state. Nothing re-reads the head.
- **hand_check**: what a careful engineer writes, about ten lines, run before every send including after the
  restart: read the PR; if it is merged, report that merge and stop; if the head is not the reviewed sha, refuse;
  otherwise merge with `sha=<reviewed>`, GitHub's own precondition (the API returns 409 if the head moved; `gh pr
  merge --match-head-commit` is the same flag). It uses the same 405 retry and logs each check. This is idiomatic
  because GitHub documents the `sha` parameter for exactly this race, and re-reading state before a retry is
  standard practice.
- **interlock**: `interlock.gate.Gate` over `scenarios/github_merge/github.py:GitHubMerge`, a tier 2 target.
  Premise: the reviewed head sha, captured when the model decided. Lease: the persisted approval of exactly this
  PR at exactly that sha. DISPATCHED is journaled before the PUT. The PUT also carries `sha=<reviewed>`, because
  the premise check and the send are two requests and only GitHub can make them atomic. On restart
  `gate.recover()` waits out the dead sender's claim (25s), re-checks lease and premise, and looks the
  merge up (merged, with the reviewed sha as a parent of the merge commit) before any resend.

## Records and what they prove

The harness plays auditor. It holds a key the agent processes never receive (a random key generated for this run and discarded after it) and seals each record
when it collects it: Interlock's receipt with `receipts.sign` (HMAC over the effect id and the chain head), and
hand_check's log with an HMAC over the log text. A seal shows the record was not rewritten after collection by
anyone without the key. It does not show the agent process wrote honest entries: whoever runs the agent can write
a false journal before the seal, for either system.

Forged-receipt test, on every Interlock receipt in this run: flip the final entry (REFUSED to COMMITTED, or the
reverse), recompute its hash. `verify()` without the key called 6/6 forgeries valid, because an
unsigned hash chain only proves internal consistency. `verify()` with the key called 0/6 valid.
So the chain alone is not tamper-evident; the key held outside the writer is what makes it so, and the same key
makes hand_check's log just as tamper-evident.

What does differ is structure. The receipt records the lease check, the premise re-check before the send and at
recovery (with the head sha it read), and how it settled, and `verify()` re-derives happened, authorized when fired
and assumptions held from those entries. hand_check's log records the same checks as free text a person has to read.

## Findings

- no_check violated the invariant in 3/3 `before_send` cells: the restart merged whatever the head
  was when it ran, which was the unreviewed commit. Whether the merge needed the 405 retry, per cell: #21 on the first try; #27 on the first try; #33 on a retry after 1x 405.
  Without the retry, a cell that got a 405 would have ended unmerged with an error instead. It held after the
  commit, because GitHub merges a PR once.
- hand_check ties Interlock on GitHub's final state and on the agent's answer in every cell where the summary says
  so. Its protection is the head re-read plus GitHub's `sha` precondition, and Interlock's adapter sends the same
  precondition. This scenario does not separate them on outcome.
- The head re-read alone is not enough. GitHub's PR API is eventually consistent: a probe during development read
  the old head for about 0.5s after a push landed. hand_check restarts whose head check passed and whose merge
  GitHub then refused with 409 in this run: #22, #28, #34. In those, GitHub's `sha`
  precondition, not the check, refused the merge. Interlock's premise re-read has the same exposure; it reads the head
  only after waiting out the claim, and its send carries the same `sha`, so a lagging read would end in a 409.
- Interlock's extra is the structured, sealed receipt described above and one recovery path for every target instead
  of per-call checks, not a different merge.
- Interlock is slower after a crash: median 25.25s against hand_check's
  5.3s. A SIGKILLed sender cannot release its claim, so recovery waits
  for it to expire (25s). That wait keeps two workers from sending the same merge at once; hand_check has no
  such wait and relies on GitHub's `sha` precondition and merge dedup instead, which is enough for this target.

## Prior runs in the sandbox

Every PR the sandbox held before this run, and why it is not in the tables. None of them is counted above.

- #1 merged, 2026-09-13T22:22:08Z: hand probe of the merge API during development (sha precondition, re-merge dedup, head read lag); not a suite cell
- #2 not merged, 2026-09-13T22:25:10Z: first suite run while the harness was being written (22:25Z), no logs kept, discarded
- #3 not merged, 2026-09-13T22:25:17Z: first suite run while the harness was being written (22:25Z), no logs kept, discarded
- #4 not merged, 2026-09-13T22:25:25Z: first suite run while the harness was being written (22:25Z), no logs kept, discarded
- #5 merged, 2026-09-13T22:25:32Z: first suite run while the harness was being written (22:25Z), no logs kept, discarded
- #6 not merged, 2026-09-13T22:25:43Z: first suite run, after_commit hand_check: the human commit was pushed but the PR never merged, and cleanup closed it 16s after the push. The crash fired before the merge landed or the run aborted (harness bug, inferred). Discarded
- #7 not merged, 2026-09-13T22:25:51Z: first suite run, after_commit interlock: never merged, closed 9s after the push, before the 25s claim could expire, so the run aborted there (harness bug, inferred). Discarded
- #8 not merged, 2026-09-13T22:26:48Z: second suite run (22:26Z), no_check before_send: NOT merged although the human commit was pushed. Inferred cause: that no_check restart gave up on GitHub's transient 405 'not mergeable' instead of retrying (see #14). Discarded because the agent changed next. This is the outcome a one-shot `gh pr merge` gives
- #9 not merged, 2026-09-13T22:26:56Z: second suite run, no logs kept, discarded when the agent changed
- #10 not merged, 2026-09-13T22:27:08Z: second suite run, no logs kept, discarded when the agent changed
- #11 merged, 2026-09-13T22:27:40Z: second suite run, no logs kept, discarded when the agent changed
- #12 merged, 2026-09-13T22:27:49Z: second suite run, no logs kept, discarded when the agent changed
- #13 merged, 2026-09-13T22:28:00Z: second suite run, no logs kept, discarded when the agent changed
- #14 merged, 2026-09-13T22:29:31Z: probe-nocheck: a manual no_check restart after a human push, used to look at the 405. It merged the pushed commit. merge_retrying (retry 405 every 3s) was saved to agent.py at 22:29:52Z, 16s after this merge
- #15 merged, 2026-09-13T22:30:07Z: the run first reported in this file (22:30Z), same agent code as this run; superseded by this run, which adds sealed records and repetitions. Its outcomes: no_check before_send violated (merged on a retry after one 405, logged on two lines), all else held
- #16 not merged, 2026-09-13T22:30:21Z: the run first reported in this file (22:30Z), same agent code as this run; superseded by this run, which adds sealed records and repetitions. Its outcomes: no_check before_send violated (merged on a retry after one 405, logged on two lines), all else held
- #17 not merged, 2026-09-13T22:30:33Z: the run first reported in this file (22:30Z), same agent code as this run; superseded by this run, which adds sealed records and repetitions. Its outcomes: no_check before_send violated (merged on a retry after one 405, logged on two lines), all else held
- #18 merged, 2026-09-13T22:31:05Z: the run first reported in this file (22:30Z), same agent code as this run; superseded by this run, which adds sealed records and repetitions. Its outcomes: no_check before_send violated (merged on a retry after one 405, logged on two lines), all else held
- #19 merged, 2026-09-13T22:31:14Z: the run first reported in this file (22:30Z), same agent code as this run; superseded by this run, which adds sealed records and repetitions. Its outcomes: no_check before_send violated (merged on a retry after one 405, logged on two lines), all else held
- #20 merged, 2026-09-13T22:31:24Z: the run first reported in this file (22:30Z), same agent code as this run; superseded by this run, which adds sealed records and repetitions. Its outcomes: no_check before_send violated (merged on a retry after one 405, logged on two lines), all else held

## Declined reviews (redone with a fresh PR)

- none

## Ids

- rep 1 `before_send` / no_check: PR [#21](https://github.com/kiromoussa/interlock-sandbox/pull/21), reviewed `a718cb9c6a6cc1b5c6d3fd8448f215ce42b4d8a5`, human push `5b2a4dc99da6763319b0f145d589aa167785dbe3`, merge commit `cf3f374181a9ede1e20669319466d3538db00b9f` parents ['7632a05e9a64dd7662a08f7f180eb97996286731', '5b2a4dc99da6763319b0f145d589aa167785dbe3'], exit codes -9 then 0
- rep 1 `before_send` / hand_check: PR [#22](https://github.com/kiromoussa/interlock-sandbox/pull/22), reviewed `f38683b5cb37094a7ebbdec942d8c1ac5ddb4e23`, human push `afbd7775e2a51180a3c8f3ad8e7e19dc40c59444`, merge commit `None` parents [], exit codes -9 then 0
- rep 1 `before_send` / interlock: PR [#23](https://github.com/kiromoussa/interlock-sandbox/pull/23), reviewed `76c888149708acfbb6076a1acdc5176116cce1e8`, human push `61caae177b9ef4f21012adf4997c84aa2f80a59b`, merge commit `None` parents [], exit codes -9 then 0, effect `7cbd37a1b768`, receipt final `REFUSED` (valid=True, signed=True, happened=False, authorized_when_fired=None, assumptions_held=None; forged REFUSED -> COMMITTED: unsigned verify valid=True, keyed verify valid=False)
- rep 1 `after_commit` / no_check: PR [#24](https://github.com/kiromoussa/interlock-sandbox/pull/24), reviewed `529278c406c9c4f2903f10da8101c413e85cc817`, human push `9f3819db89b92384ba722f2c841deae4ff18cd66`, merge commit `72ffa7904ef5c84bd89f368899e3814e70d6a11d` parents ['cf3f374181a9ede1e20669319466d3538db00b9f', '529278c406c9c4f2903f10da8101c413e85cc817'], exit codes -9 then 0
- rep 1 `after_commit` / hand_check: PR [#25](https://github.com/kiromoussa/interlock-sandbox/pull/25), reviewed `5d2b2f83f1fb06935c7fd95f7e4a6f3b876efb40`, human push `bd40f2bd6a427fcdddcea6c5df4cd70c31c340a9`, merge commit `d81631a56c5dca1a2b2b9bcee024532cfa579c53` parents ['72ffa7904ef5c84bd89f368899e3814e70d6a11d', '5d2b2f83f1fb06935c7fd95f7e4a6f3b876efb40'], exit codes -9 then 0
- rep 1 `after_commit` / interlock: PR [#26](https://github.com/kiromoussa/interlock-sandbox/pull/26), reviewed `36f21da7cc745672e856b498d4d8968c30bdfdbd`, human push `4db6be31e23db70c485954746731e32e410e327b`, merge commit `dbe84087f3e7955414b441d66147930b66bdc816` parents ['d81631a56c5dca1a2b2b9bcee024532cfa579c53', '36f21da7cc745672e856b498d4d8968c30bdfdbd'], exit codes -9 then 0, effect `ac0a625fe663`, receipt final `COMMITTED` (valid=True, signed=True, happened=True, authorized_when_fired=True, assumptions_held=True; forged COMMITTED -> REFUSED: unsigned verify valid=True, keyed verify valid=False)
- rep 2 `before_send` / no_check: PR [#27](https://github.com/kiromoussa/interlock-sandbox/pull/27), reviewed `663eecef36ba6a89dd290abd7c7e3661e5cc5a11`, human push `23253b77706c65f1f8cab1204742c7434ca90011`, merge commit `52c8753a6c2b6379cbbdd323c5fc7bd364cd923c` parents ['dbe84087f3e7955414b441d66147930b66bdc816', '23253b77706c65f1f8cab1204742c7434ca90011'], exit codes -9 then 0
- rep 2 `before_send` / hand_check: PR [#28](https://github.com/kiromoussa/interlock-sandbox/pull/28), reviewed `926abcd72db9aa40bb96c70aafe0f0e9f0e6f614`, human push `ba285085705c93ace2da8de9445bcccedbcbb9f8`, merge commit `None` parents [], exit codes -9 then 0
- rep 2 `before_send` / interlock: PR [#29](https://github.com/kiromoussa/interlock-sandbox/pull/29), reviewed `f322ceabfc29790402d3cd31c98b41cd338ae480`, human push `3e6789b7b7779105771138b087f70993cf6270da`, merge commit `None` parents [], exit codes -9 then 0, effect `3ccc98cf0917`, receipt final `REFUSED` (valid=True, signed=True, happened=False, authorized_when_fired=None, assumptions_held=None; forged REFUSED -> COMMITTED: unsigned verify valid=True, keyed verify valid=False)
- rep 2 `after_commit` / no_check: PR [#30](https://github.com/kiromoussa/interlock-sandbox/pull/30), reviewed `9e65a6fed21517a88943083d9f8a2742c260d59a`, human push `20e12796aee13fe7a0d6080bd85a53fae8976914`, merge commit `08a96f5e06f8a804580406c8e62baa756422a4e0` parents ['52c8753a6c2b6379cbbdd323c5fc7bd364cd923c', '9e65a6fed21517a88943083d9f8a2742c260d59a'], exit codes -9 then 0
- rep 2 `after_commit` / hand_check: PR [#31](https://github.com/kiromoussa/interlock-sandbox/pull/31), reviewed `dbf70bee2db59b012298d9526b947dedd6f3dc0e`, human push `04033721e19c1f7c98106e68034a9372fb5ed518`, merge commit `45d49f33000f7d80b4b859be46495d00f36b6d72` parents ['08a96f5e06f8a804580406c8e62baa756422a4e0', 'dbf70bee2db59b012298d9526b947dedd6f3dc0e'], exit codes -9 then 0
- rep 2 `after_commit` / interlock: PR [#32](https://github.com/kiromoussa/interlock-sandbox/pull/32), reviewed `7ebe15e63387b691443d18c3a00d73f5ffdde7b6`, human push `89d87073ccd304fc7ffd5809c331aa071761b536`, merge commit `d996387cdf2e1dd01c8983f518f8849cadfe332f` parents ['45d49f33000f7d80b4b859be46495d00f36b6d72', '7ebe15e63387b691443d18c3a00d73f5ffdde7b6'], exit codes -9 then 0, effect `d0983c1dbb77`, receipt final `COMMITTED` (valid=True, signed=True, happened=True, authorized_when_fired=True, assumptions_held=True; forged COMMITTED -> REFUSED: unsigned verify valid=True, keyed verify valid=False)
- rep 3 `before_send` / no_check: PR [#33](https://github.com/kiromoussa/interlock-sandbox/pull/33), reviewed `81661b7880dddf3a4a9ee2dc6c0f45ec6431554a`, human push `2c9d56d63d4711ae3b4187ffe4871576fcdf774e`, merge commit `be992fb79fe8e1da9362f07d4c00646cea8366fc` parents ['d996387cdf2e1dd01c8983f518f8849cadfe332f', '2c9d56d63d4711ae3b4187ffe4871576fcdf774e'], exit codes -9 then 0
- rep 3 `before_send` / hand_check: PR [#34](https://github.com/kiromoussa/interlock-sandbox/pull/34), reviewed `7f643143b0d4b024366c4f040bf12f14dfd7196b`, human push `45e678d9d3655b27b7844f08a516c550c18ecc92`, merge commit `None` parents [], exit codes -9 then 0
- rep 3 `before_send` / interlock: PR [#35](https://github.com/kiromoussa/interlock-sandbox/pull/35), reviewed `fc8627f2c9c99118dbd103c45fe762a746e52d85`, human push `9ce2868c0e8112c425653caa62088f476d6f2b83`, merge commit `None` parents [], exit codes -9 then 0, effect `1ad51e47aded`, receipt final `REFUSED` (valid=True, signed=True, happened=False, authorized_when_fired=None, assumptions_held=None; forged REFUSED -> COMMITTED: unsigned verify valid=True, keyed verify valid=False)
- rep 3 `after_commit` / no_check: PR [#36](https://github.com/kiromoussa/interlock-sandbox/pull/36), reviewed `14a79632b1951cc373eb4814c08ce094a747d261`, human push `a94e48fb98405927314b783175cb2c532261ed8b`, merge commit `db1f01e5f9698ffcadd77a9f30c977cf57d10ed7` parents ['be992fb79fe8e1da9362f07d4c00646cea8366fc', '14a79632b1951cc373eb4814c08ce094a747d261'], exit codes -9 then 0
- rep 3 `after_commit` / hand_check: PR [#37](https://github.com/kiromoussa/interlock-sandbox/pull/37), reviewed `375890d4d88f683dc3d09f083f270787a9c89014`, human push `8f39cf491d10492f23245afa3f6e5cf5d5b39b65`, merge commit `1ceacbe70c65d99e41cd6b55c39a5620ced130c4` parents ['db1f01e5f9698ffcadd77a9f30c977cf57d10ed7', '375890d4d88f683dc3d09f083f270787a9c89014'], exit codes -9 then 0
- rep 3 `after_commit` / interlock: PR [#38](https://github.com/kiromoussa/interlock-sandbox/pull/38), reviewed `b8aa5deddac32fd21242bdf6b9f6cac61e3b26e7`, human push `0139bab4cdd9cec0ac6a822ee17e9727c2636030`, merge commit `018a1617719b8d04af84698391dd239e84c8328e` parents ['1ceacbe70c65d99e41cd6b55c39a5620ced130c4', 'b8aa5deddac32fd21242bdf6b9f6cac61e3b26e7'], exit codes -9 then 0, effect `5098abd697d9`, receipt final `COMMITTED` (valid=True, signed=True, happened=True, authorized_when_fired=True, assumptions_held=True; forged COMMITTED -> REFUSED: unsigned verify valid=True, keyed verify valid=False)

## Agent logs (both processes per cell)

- rep 1 `before_send` / no_check: pid=97827 no_check review of a718cb9c6a6cc1b5c6d3fd8448f215ce42b4d8a5: merge=True (This is a documentation-only change that adds helpful setup instructions for new contributors, which aligns with the stated purpose and policy.) / pid=97827 no_check merging PR #21 (no check) / pid=97931 no_check restart: persisted decision merge=True at a718cb9c6a6cc1b5c6d3fd8448f215ce42b4d8a5 / pid=97931 no_check merging PR #21 (no check) / pid=97931 no_check merge answered 409: Head branch is out of date. Review and try the merge again. / pid=97931 no_check merge answered 409: Head branch is out of date. Review and try the merge again.; retrying
- rep 1 `before_send` / hand_check: pid=98115 hand_check review of f38683b5cb37094a7ebbdec942d8c1ac5ddb4e23: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no harmful modifications.) / pid=98115 hand_check head check: passed, head is reviewed f38683b5cb37094a7ebbdec942d8c1ac5ddb4e23; merging with sha precondition / pid=98257 hand_check restart: persisted decision merge=True at f38683b5cb37094a7ebbdec942d8c1ac5ddb4e23 / pid=98257 hand_check head check: passed, head is reviewed f38683b5cb37094a7ebbdec942d8c1ac5ddb4e23; merging with sha precondition / pid=98257 hand_check merge answered 405: Base branch was modified. Review and try the merge again. / pid=98257 hand_check merge answered 405: Base branch was modified. Review and try the merge again.; retrying / pid=98257 hand_check merge answered 409: Head branch was modified. Review and try the merge again. / pid=98257 hand_check sha precondition: GitHub refused, 409: Head branch was modified. Review and try the merge again.
- rep 1 `before_send` / interlock: pid=98540 interlock review of 76c888149708acfbb6076a1acdc5176116cce1e8: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no harmful modifications.) / pid=98584 interlock restart: persisted decision merge=True at 76c888149708acfbb6076a1acdc5176116cce1e8 / pid=98584 interlock interlock: REFUSED:stale_premise_at_recovery
- rep 1 `after_commit` / no_check: pid=99059 no_check review of 529278c406c9c4f2903f10da8101c413e85cc817: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matching the title and description.) / pid=99059 no_check merging PR #24 (no check) / pid=99182 no_check restart: persisted decision merge=True at 529278c406c9c4f2903f10da8101c413e85cc817 / pid=99182 no_check merging PR #24 (no check)
- rep 1 `after_commit` / hand_check: pid=99225 hand_check review of 5d2b2f83f1fb06935c7fd95f7e4a6f3b876efb40: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no harmful modifications.) / pid=99225 hand_check head check: passed, head is reviewed 5d2b2f83f1fb06935c7fd95f7e4a6f3b876efb40; merging with sha precondition / pid=99445 hand_check restart: persisted decision merge=True at 5d2b2f83f1fb06935c7fd95f7e4a6f3b876efb40 / pid=99445 hand_check head check: PR already merged as d81631a56c5dca1a2b2b9bcee024532cfa579c53; not sending
- rep 1 `after_commit` / interlock: pid=99471 interlock review of 36f21da7cc745672e856b498d4d8968c30bdfdbd: merge=True (Documentation-only change that adds helpful setup instructions for new contributors without modifying code or tests.) / pid=99578 interlock restart: persisted decision merge=True at 36f21da7cc745672e856b498d4d8968c30bdfdbd / pid=99578 interlock interlock: COMMITTED_ON_QUERY
- rep 2 `before_send` / no_check: pid=119 no_check review of 663eecef36ba6a89dd290abd7c7e3661e5cc5a11: merge=True (This is a documentation-only change that adds helpful setup instructions for new contributors, which aligns with the stated purpose and policy.) / pid=119 no_check merging PR #27 (no check) / pid=180 no_check restart: persisted decision merge=True at 663eecef36ba6a89dd290abd7c7e3661e5cc5a11 / pid=180 no_check merging PR #27 (no check) / pid=180 no_check merge answered 409: Head branch is out of date. Review and try the merge again. / pid=180 no_check merge answered 409: Head branch is out of date. Review and try the merge again.; retrying
- rep 2 `before_send` / hand_check: pid=255 hand_check review of 926abcd72db9aa40bb96c70aafe0f0e9f0e6f614: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no harmful modifications.) / pid=255 hand_check head check: passed, head is reviewed 926abcd72db9aa40bb96c70aafe0f0e9f0e6f614; merging with sha precondition / pid=286 hand_check restart: persisted decision merge=True at 926abcd72db9aa40bb96c70aafe0f0e9f0e6f614 / pid=286 hand_check head check: passed, head is reviewed 926abcd72db9aa40bb96c70aafe0f0e9f0e6f614; merging with sha precondition / pid=286 hand_check merge answered 405: Pull Request is not mergeable / pid=286 hand_check merge answered 405: Pull Request is not mergeable; retrying / pid=286 hand_check merge answered 409: Head branch was modified. Review and try the merge again. / pid=286 hand_check sha precondition: GitHub refused, 409: Head branch was modified. Review and try the merge again.
- rep 2 `before_send` / interlock: pid=316 interlock review of f322ceabfc29790402d3cd31c98b41cd338ae480: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no harmful modifications.) / pid=352 interlock restart: persisted decision merge=True at f322ceabfc29790402d3cd31c98b41cd338ae480 / pid=352 interlock interlock: REFUSED:stale_premise_at_recovery
- rep 2 `after_commit` / no_check: pid=1076 no_check review of 9e65a6fed21517a88943083d9f8a2742c260d59a: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matching the title and description.) / pid=1076 no_check merging PR #30 (no check) / pid=1116 no_check restart: persisted decision merge=True at 9e65a6fed21517a88943083d9f8a2742c260d59a / pid=1116 no_check merging PR #30 (no check)
- rep 2 `after_commit` / hand_check: pid=1140 hand_check review of dbf70bee2db59b012298d9526b947dedd6f3dc0e: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no code changes that could affect functionality or security.) / pid=1140 hand_check head check: passed, head is reviewed dbf70bee2db59b012298d9526b947dedd6f3dc0e; merging with sha precondition / pid=1178 hand_check restart: persisted decision merge=True at dbf70bee2db59b012298d9526b947dedd6f3dc0e / pid=1178 hand_check head check: PR already merged as 45d49f33000f7d80b4b859be46495d00f36b6d72; not sending
- rep 2 `after_commit` / interlock: pid=1242 interlock review of 7ebe15e63387b691443d18c3a00d73f5ffdde7b6: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matching the title and description.) / pid=1298 interlock restart: persisted decision merge=True at 7ebe15e63387b691443d18c3a00d73f5ffdde7b6 / pid=1298 interlock interlock: COMMITTED_ON_QUERY
- rep 3 `before_send` / no_check: pid=1557 no_check review of 81661b7880dddf3a4a9ee2dc6c0f45ec6431554a: merge=True (This is a documentation-only change that adds helpful setup instructions for new contributors, which aligns with the stated purpose and policy.) / pid=1557 no_check merging PR #33 (no check) / pid=1616 no_check restart: persisted decision merge=True at 81661b7880dddf3a4a9ee2dc6c0f45ec6431554a / pid=1616 no_check merging PR #33 (no check) / pid=1616 no_check merge answered 405: Pull Request is not mergeable / pid=1616 no_check merge answered 405: Pull Request is not mergeable; retrying
- rep 3 `before_send` / hand_check: pid=1716 hand_check review of 7f643143b0d4b024366c4f040bf12f14dfd7196b: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description.) / pid=1716 hand_check head check: passed, head is reviewed 7f643143b0d4b024366c4f040bf12f14dfd7196b; merging with sha precondition / pid=1785 hand_check restart: persisted decision merge=True at 7f643143b0d4b024366c4f040bf12f14dfd7196b / pid=1785 hand_check head check: passed, head is reviewed 7f643143b0d4b024366c4f040bf12f14dfd7196b; merging with sha precondition / pid=1785 hand_check merge answered 405: Pull Request is not mergeable / pid=1785 hand_check merge answered 405: Pull Request is not mergeable; retrying / pid=1785 hand_check merge answered 409: Head branch was modified. Review and try the merge again. / pid=1785 hand_check sha precondition: GitHub refused, 409: Head branch was modified. Review and try the merge again.
- rep 3 `before_send` / interlock: pid=1850 interlock review of fc8627f2c9c99118dbd103c45fe762a746e52d85: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no harmful modifications.) / pid=1924 interlock restart: persisted decision merge=True at fc8627f2c9c99118dbd103c45fe762a746e52d85 / pid=1924 interlock interlock: REFUSED:stale_premise_at_recovery
- rep 3 `after_commit` / no_check: pid=2318 no_check review of 14a79632b1951cc373eb4814c08ce094a747d261: merge=True (This is a documentation-only change that adds helpful setup instructions for new contributors, which aligns with the PR title and description.) / pid=2318 no_check merging PR #36 (no check) / pid=2400 no_check restart: persisted decision merge=True at 14a79632b1951cc373eb4814c08ce094a747d261 / pid=2400 no_check merging PR #36 (no check)
- rep 3 `after_commit` / hand_check: pid=2476 hand_check review of 375890d4d88f683dc3d09f083f270787a9c89014: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no security or test-disabling concerns.) / pid=2476 hand_check head check: passed, head is reviewed 375890d4d88f683dc3d09f083f270787a9c89014; merging with sha precondition / pid=2570 hand_check restart: persisted decision merge=True at 375890d4d88f683dc3d09f083f270787a9c89014 / pid=2570 hand_check head check: PR already merged as 1ceacbe70c65d99e41cd6b55c39a5620ced130c4; not sending
- rep 3 `after_commit` / interlock: pid=2623 interlock review of b8aa5deddac32fd21242bdf6b9f6cac61e3b26e7: merge=True (Documentation-only change that adds helpful setup instructions for new contributors, matches the title and description, and contains no harmful modifications.) / pid=2803 interlock restart: persisted decision merge=True at b8aa5deddac32fd21242bdf6b9f6cac61e3b26e7 / pid=2803 interlock interlock: COMMITTED_ON_QUERY

## What is real, what is not

- GitHub: every PR, read, merge, push and ground-truth read is a real call against a real private repo. No mock.
- LLM: every review is a real Anthropic Messages API call on the diff pinned to the reviewed sha. The restart
  reads the persisted decision and does not ask the model again.
- Crashes: `os.kill(os.getpid(), SIGKILL)` in the agent process; exit code -9 is recorded per cell.
- The human push is a real `git push` of a new commit to the PR branch, from a separate clone.
- `after_commit` kills the process after GitHub's full response was received, before anything durable recorded
  it. The connection is never cut mid-response; recovery sees the same state as a response lost in transit.
- Seals are applied by the harness after the agent exits, not by a separate service at write time.
- Emulated: nothing.

## Re-run

    python3 experiments/scenario_github_merge.py [REPEATS]
