# Scenario: double booking on Google Calendar

Generated 2026-09-13 22:58 UTC by `experiments/scenario_calendar.py`. Model `claude-haiku-4-5-20251001`, Google Calendar API v3,
the sandbox service account's own primary calendar (`interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com`), no attendees, no delegation.

Each cell is one booking request: "a 30-minute call at <slot>". A worker process (its own OS process) reads the
request, asks the model to book it (the model calls `book_call`; its start and duration are checked against the
request; the decision is persisted and a restarted job reuses it, so a job is decided once), and sends the insert
with one of the systems. The worker SIGKILLs itself right before the insert (`before_send`) or right after
Calendar's response arrives (`after_commit`). During the outage the harness does nothing, puts a real customer
event on the slot (`slot_busy`), or cancels the booking request (`request_cancelled`). In `pre_busy` the customer
event is on the slot before the job is decided; the crash is armed at `before_send`, but a system that refuses
never gets there, so its first worker exits 0 instead (marked "no crash" below). A new worker process then runs
the same job. Ground truth is `events.list` on the slot, read after the second worker exits.

Invariant: the request's agent events on the calendar equal "want", and no agent event was put on top of an event
that was already there. Want is 1 after a commit (the booking landed while the slot was free and the request live;
what to do about a later conflict or cancellation is a separate step), 1 before a send with no outage change, and
0 when the slot was taken (before the decision, or during the outage before the send) or the request cancelled.

| fault | no_check | hand_check | interlock | interlock_change_only |
|---|---|---|---|---|
| `after_commit/none` | ALREADY_EXISTS_409; 1 agent event (want 1); **held**; answer matches; 0.6s; proof: none | FOUND_BY_LOOKUP; 1 agent event (want 1); **held**; answer matches; 0.4s; proof: none | COMMITTED_BY_RETRY; 1 agent event (want 1); **held**; answer matches; 31.5s; proof: receipt | n/a |
| `after_commit/slot_busy` | ALREADY_EXISTS_409; 1 agent event (want 1); **held**; answer matches; 1.2s; proof: none | FOUND_BY_LOOKUP; 1 agent event (want 1); **held**; answer matches; 1.0s; proof: none | COMMITTED_ON_QUERY; 1 agent event (want 1); **held**; answer matches; 30.7s; proof: receipt | n/a |
| `after_commit/request_cancelled` | ALREADY_EXISTS_409; 1 agent event (want 1); **held**; answer matches; 0.6s; proof: none | FOUND_BY_LOOKUP; 1 agent event (want 1); **held**; answer matches; 0.3s; proof: none | COMMITTED_ON_QUERY; 1 agent event (want 1); **held**; answer matches; 31.1s; proof: receipt | n/a |
| `before_send/none` | BOOKED; 1 agent event (want 1); **held**; answer matches; 0.5s; proof: none | BOOKED; 1 agent event (want 1); **held**; answer matches; 0.8s; proof: none | COMMITTED_BY_RETRY; 1 agent event (want 1); **held**; answer matches; 31.2s; proof: receipt | n/a |
| `before_send/slot_busy` | BOOKED; 1 agent event (want 0); **VIOLATED, double booked**; answer matches; 1.0s; proof: none | REFUSED:slot_busy; 0 agent events (want 0); **held**; answer matches; 1.2s; proof: none | REFUSED:stale_premise_at_recovery; 0 agent events (want 0); **held**; answer matches; 32.1s; proof: receipt | n/a |
| `before_send/request_cancelled` | BOOKED; 1 agent event (want 0); **VIOLATED**; answer matches; 0.5s; proof: none | REFUSED:request_cancelled; 0 agent events (want 0); **held**; answer matches; 0.4s; proof: none | REFUSED:lease_at_recovery; 0 agent events (want 0); **held**; answer matches; 31.2s; proof: receipt | n/a |
| `before_send/pre_busy` | REFUSED:slot_busy; 0 agent events (want 0); **held**; answer matches; 0.3s; proof: none; no crash (refused before the send) | REFUSED:slot_busy; 0 agent events (want 0); **held**; answer matches; 0.6s; proof: none; no crash (refused before the send) | REFUSED:stale_premise; 0 agent events (want 0); **held**; answer matches; 0.8s; proof: receipt; no crash (refused before the send) | COMMITTED_BY_RETRY; 1 agent event (want 0); **VIOLATED, double booked**; answer matches; 31.5s; proof: receipt |

- **no_check**: invariant held 5/7, answers matched the calendar 7/7, double bookings 1, provable record 0/7, median 0.6s crash to settled
- **hand_check**: invariant held 7/7, answers matched the calendar 7/7, double bookings 0, provable record 0/7, median 0.6s crash to settled
- **interlock**: invariant held 7/7, answers matched the calendar 7/7, double bookings 0, provable record 7/7, median 31.2s crash to settled
- **interlock_change_only**: invariant held 0/1, answers matched the calendar 1/1, double bookings 1, provable record 1/1, median 31.5s crash to settled

**Verdict.** hand_check and interlock differ on no row in outcome or
answer. hand_check TIES interlock on every calendar outcome here, `pre_busy` included. That
tie depends on configuring interlock's slot premise to require an empty slot, which `interlock.easy` cannot express
(see "The systems"). Configured as easy.py ships it, where a premise only has to stay unchanged, interlock (interlock_change_only) went `COMMITTED_BY_RETRY` on `before_send/pre_busy` with the invariant VIOLATED, double booked: WORSE than hand_check and no_check there, both of which refused.
no_check violated the invariant on `before_send/slot_busy`, `before_send/request_cancelled`: it checked the request
and freebusy when the job was enqueued, and the queued send replayed after the crash without looking again.
Beyond the calendar, interlock leaves a hash-chained receipt recording the request status and slot contents it
checked before each send and again at recovery; hand_check records nothing about its checks (the event itself shows
the creator and, through extendedProperties, the request and system, which is all no_check and hand_check can show
afterwards). When its booking had already landed and the world then changed (`after_commit/slot_busy`, `after_commit/request_cancelled`), interlock reports booked and its receipt also records the failed re-check at recovery (slot now taken, or request cancelled), which tells whoever handles it next; hand_check reports booked and notes nothing. What the receipt proves is that the booking committed once, not which HTTP attempt created it: in `after_commit/none` the outcome is `COMMITTED_BY_RETRY` because recovery settled it by retrying, and the retry got Calendar's 409, recorded in the COMMITTED result as {'status': 'confirmed', 'event': '6a91e74b2c24', 'created': '2026-09-13T22:53:45.000Z', 'already_existed': True}; the event was created by the SIGKILLed first worker. Interlock is slower to settle after a SIGKILL: a dead sender's claim blocks recovery for `CLAIM_TTL` = 30s.

## The systems

- **no_check**: the standard setup, a durable job queue. When the job is enqueued it checks that the request is
  live and that `freeBusy` on the slot is empty, then queues the send with an event id fixed from the request
  (`bk` + sha256(request)[:26]), which is Calendar's native dedup: a second insert with that id is a 409, read as
  "already booked". A restart replays the queued send; nothing is re-read.
- **hand_check**: what a competent engineer writes for this step, using both native tools Calendar offers. The
  same client-supplied id, and on every attempt (restarts included): `events.get` on that id first (if it exists,
  report booked and stop, so a restart after the insert does not refuse because of its own event), then the
  request must still be live, then `freeBusy` on the slot must be empty. A 409 on the insert still reads as booked.
  About ten lines. It is idiomatic because a client-supplied id is Google's documented way to make inserts
  retry-safe, and a freebusy query is the documented availability check; the lookup-first order is the one fix a
  careful author adds after the first restart refuses its own booking.
- **interlock**: the same insert behind `interlock.easy`: key = the booking request, `allowed` = the request is
  live (checked at dispatch and at recovery), premise = the ids of other events on the slot, excluding this
  effect's own event, `dedupes=True` (the effect id is the event id, and a 409 is a replay), `lookup` =
  `events.get` on the effect id. On startup the worker runs `recover()` until nothing is in flight, then submits.
  Two changes are made on the gate's target instance in `scenarios/calendar/booking.py` (`_gate_target`), because
  `interlock/` is not edited here: (1) the premise must be `[]` when decided, not only unchanged. `easy.py`'s
  `validate_premises` compares the saved value with the current one, so on its own it detects a change, not a
  conflict. (2) The COMMITTED result and the lookup keep Calendar's answer (event id, created, and
  `already_existed` when the insert was a 409), where `easy.py` records `{"status": "ok"}` and `True`.
- **interlock_change_only**: `interlock` without change (1), that is `interlock.easy` as it ships. Run on
  `before_send/pre_busy` only.

Proposed core change (not made): let `gate.effect` declare an expected value for a premise (for example
`expect={"other_events_in_slot": []}`) that `validate_premises` enforces at dispatch and recovery alongside the
unchanged-since-decided check, and have `_FunctionTarget.apply` and `query` record the function's return value.

## What is real

- Calendar: every insert, get, list, freebusy and delete is a real Calendar API v3 call as the service account.
- LLM: every decision is a real Anthropic Messages API call (`claude-haiku-4-5-20251001`, temperature 0), made once per job and
  persisted; all decisions are listed below.
- Crashes: `os.kill(os.getpid(), SIGKILL)` inside the worker, one-shot via a marker file. Exit codes are recorded.
- The customer's busy event is a real event on the same calendar, inserted by the harness.

## What is emulated

- The booking request system: a JSON file per request in a temp directory, read by the worker (`allowed` for
  interlock, the live check for hand_check and at enqueue for no_check) and rewritten by the harness to cancel.
  Every cell's `emulated` field says so.

## Evidence kept, and what was deleted

After the run the harness deleted every event it saw (25 of 25 deleted;
each read back afterwards with status ['cancelled']), and the
sandbox service account, with its calendar, is deleted after that (`gcloud iam service-accounts delete`). The
events can no longer be read from Calendar. Ground truth for each cell therefore rests on what `calendar.json`
stores, read during the run: the full `events.list` resources on the slot, the full hash-chained journal bundle
for interlock cells (re-verify with `python3 -m interlock.receipts` on a cell's `evidence.receipt_bundle`), the
worker log, the crash marker, the result and request files, and the cleanup read-back under `cleanup`.

## Limits

- The interlock premise is "the ids of other events on the slot, which must be [] when decided and must not change
  before the send". It also refuses when an unrelated event lands on the slot, which is the point for a calendar.
  Both hand_check and interlock read the slot right before the send; neither closes the gap between that read and
  the insert (Calendar has no conditional insert on free/busy).
- Calendar's native dedup never expires (a deleted event keeps its id, and a re-insert is still a 409), so the
  key-window row from the Stripe run has no analogue here.
- The `after_commit` crash is after Calendar's full response arrived, before anything recorded it.
- "Double booked" is graded from the harness's own `events.list` of the slot taken right before it inserts the
  customer event (`outage.events_on_slot_before`): an agent event overlapping the customer event and not already
  on the slot then is a double booking. Calendar's `created` is whole seconds, so a customer insert and a replayed
  agent insert in the same second cannot be ordered from the events alone (an earlier run of this suite graded by
  `created` and missed one).
- Receipts are unsigned (verify reports signed=None) and written by the same worker that sends.

## Timing

Seconds are from the harness seeing the first worker exit to the second worker exiting, including the outage
action. Interlock adds the claim wait: the SIGKILLed sender cannot release its claim, so `recover()` retries until
`CLAIM_TTL` passes.

## LLM decisions

- `after_commit/none` / no_check: pid 7197: {'start': '2026-10-13T22:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/none` / hand_check: pid 7339: {'start': '2026-10-13T23:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/none` / interlock: pid 7420: {'start': '2026-10-14T00:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/slot_busy` / no_check: pid 7856: {'start': '2026-10-14T01:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/slot_busy` / hand_check: pid 7892: {'start': '2026-10-14T02:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/slot_busy` / interlock: pid 7959: {'start': '2026-10-14T03:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/request_cancelled` / no_check: pid 8881: {'start': '2026-10-14T04:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/request_cancelled` / hand_check: pid 8959: {'start': '2026-10-14T05:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `after_commit/request_cancelled` / interlock: pid 9067: {'start': '2026-10-14T06:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/none` / no_check: pid 10585: {'start': '2026-10-14T07:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/none` / hand_check: pid 10701: {'start': '2026-10-14T08:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/none` / interlock: pid 10765: {'start': '2026-10-14T09:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/slot_busy` / no_check: pid 11424: {'start': '2026-10-14T10:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/slot_busy` / hand_check: pid 11549: {'start': '2026-10-14T11:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/slot_busy` / interlock: pid 11576: {'start': '2026-10-14T12:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/request_cancelled` / no_check: pid 11839: {'start': '2026-10-14T13:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/request_cancelled` / hand_check: pid 11864: {'start': '2026-10-14T14:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/request_cancelled` / interlock: pid 11887: {'start': '2026-10-14T15:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/pre_busy` / no_check: pid 12603: {'start': '2026-10-14T16:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/pre_busy` / hand_check: pid 12889: {'start': '2026-10-14T17:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/pre_busy` / interlock: pid 13367: {'start': '2026-10-14T18:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}
- `before_send/pre_busy` / interlock_change_only: pid 13562: {'start': '2026-10-14T19:53:00Z', 'duration_minutes': 30, 'summary': 'Dana - Onboarding Call'}

## Ids

- `after_commit/none` / no_check: request 168303c48700; slot 2026-10-13T22:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bk1a1707f280f13bb8edd342df99; other events none; worker exits [-9, 0]
- `after_commit/none` / hand_check: request 6a41dc853b01; slot 2026-10-13T23:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bka2e99d487f0354c5f0d6c948c9; other events none; worker exits [-9, 0]
- `after_commit/none` / interlock: request 7e2eef77c802; slot 2026-10-14T00:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events 6a91e74b2c24; other events none; interlock effect 6a91e74b2c24; worker exits [-9, 0]; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True evidence={'status': 'confirmed', 'event': '6a91e74b2c24', 'created': '2026-09-13T22:53:45.000Z', 'already_existed': True} journal PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED(retry-idempotent)
- `after_commit/slot_busy` / no_check: request 6deb8bfae403; slot 2026-10-14T01:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bke21d72486174c43df8f5767dd2; other events cd3lno460i8fodc110r7ebq5pg; worker exits [-9, 0]
- `after_commit/slot_busy` / hand_check: request ac7a0d95ae04; slot 2026-10-14T02:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bkbd29aee587a8ab3853565d4a47; other events 090rfjq2j3mvfbmbpngel0g58k; worker exits [-9, 0]
- `after_commit/slot_busy` / interlock: request 55be767f3205; slot 2026-10-14T03:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events b8ff198374b5; other events iik18v2h013s6a0nke93qftmr8; interlock effect b8ff198374b5; worker exits [-9, 0]; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True evidence={'event': 'b8ff198374b5', 'created': '2026-09-13T22:54:28.000Z', 'status': 'confirmed'} journal PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED(recovery-query)
- `after_commit/request_cancelled` / no_check: request a5bbd34be706; slot 2026-10-14T04:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bka6296d2bea54152b3daea472ad; other events none; worker exits [-9, 0]
- `after_commit/request_cancelled` / hand_check: request 7b39425a8607; slot 2026-10-14T05:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bk075ad536b5587fcb1069e00b94; other events none; worker exits [-9, 0]
- `after_commit/request_cancelled` / interlock: request 028e027bba08; slot 2026-10-14T06:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events ca13e1751704; other events none; interlock effect ca13e1751704; worker exits [-9, 0]; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True evidence={'event': 'ca13e1751704', 'created': '2026-09-13T22:55:09.000Z', 'status': 'confirmed'} journal PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED(recovery-query)
- `before_send/none` / no_check: request f3b64983f309; slot 2026-10-14T07:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bkc7268938ca0c1a229eb2b23396; other events none; worker exits [-9, 0]
- `before_send/none` / hand_check: request 53b47b16d310; slot 2026-10-14T08:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bkd1a3765efacd1a4bf669450932; other events none; worker exits [-9, 0]
- `before_send/none` / interlock: request b4b5834eb511; slot 2026-10-14T09:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events 5b0bb1116c8d; other events none; interlock effect 5b0bb1116c8d; worker exits [-9, 0]; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True evidence={'status': 'confirmed', 'event': '5b0bb1116c8d', 'created': '2026-09-13T22:56:20.000Z', 'already_existed': False} journal PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED(retry-idempotent)
- `before_send/slot_busy` / no_check: request 448776679412; slot 2026-10-14T10:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bk1b4b1f68098c62f7a51a872592; other events dr1059kljak4snul0vv46o2j98; worker exits [-9, 0]
- `before_send/slot_busy` / hand_check: request cf23657fd213; slot 2026-10-14T11:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events none; other events 1hpdegi6bbeg7i0e5ou8timhf4; worker exits [-9, 0]
- `before_send/slot_busy` / interlock: request 99b4a49dc614; slot 2026-10-14T12:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events none; other events ivkl8v8kgc86m49lpgpecft3us; interlock effect 4183cab28f05; worker exits [-9, 0]; receipt valid=True happened=False authorized_when_fired=None assumptions_held=None evidence=None journal PROPOSED > AUTHORIZED > DISPATCHED > REFUSED > PROPOSED > AUTHORIZED > REFUSED
- `before_send/request_cancelled` / no_check: request ce9faeefa515; slot 2026-10-14T13:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events bke7a4e0f92fbd77c346c594906a; other events none; worker exits [-9, 0]
- `before_send/request_cancelled` / hand_check: request b3c3f9c59816; slot 2026-10-14T14:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events none; other events none; worker exits [-9, 0]
- `before_send/request_cancelled` / interlock: request c4df61b9ae17; slot 2026-10-14T15:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events none; other events none; interlock effect 8d970ab3a0c8; worker exits [-9, 0]; receipt valid=True happened=False authorized_when_fired=None assumptions_held=None evidence=None journal PROPOSED > AUTHORIZED > DISPATCHED > REFUSED > PROPOSED > REFUSED
- `before_send/pre_busy` / no_check: request ec9d90190018; slot 2026-10-14T16:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events none; other events 3u8rlq9ke713lr2c78oveupv68; worker exits [0, 0]
- `before_send/pre_busy` / hand_check: request 105b1ad7b419; slot 2026-10-14T17:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events none; other events kt6pej3h8ftdd8g4kl7kgmga8s; worker exits [0, 0]
- `before_send/pre_busy` / interlock: request 28ab9df8a720; slot 2026-10-14T18:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events none; other events r7op381bl9pmrcqh85d1k6ul3c; interlock effect 06abe9231126; worker exits [0, 0]; receipt valid=True happened=False authorized_when_fired=None assumptions_held=None evidence=None journal PROPOSED > AUTHORIZED > REFUSED > PROPOSED > AUTHORIZED > REFUSED
- `before_send/pre_busy` / interlock_change_only: request 9e070e993121; slot 2026-10-14T19:53:00Z; calendar interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com; agent events 62bd157889df; other events 0ir1g0lopgvi0dvpbv4pr8l510; interlock effect 62bd157889df; worker exits [-9, 0]; receipt valid=True happened=True authorized_when_fired=True assumptions_held=True evidence={'status': 'confirmed', 'event': '62bd157889df', 'created': '2026-09-13T22:58:29.000Z', 'already_existed': False} journal PROPOSED > AUTHORIZED > DISPATCHED > COMMITTED(retry-idempotent)

## Re-run

    env $(grep ^ANTHROPIC_API_KEY= /path/to/.env) python3 experiments/scenario_calendar.py
    python3 -m unittest tests.test_scenario_calendar      # offline logic
