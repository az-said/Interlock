"""
Scenario: double booking on a real Google Calendar, three systems, real SIGKILLs. One command:

    env $(grep ^ANTHROPIC_API_KEY= /path/to/.env) python3 experiments/scenario_calendar.py [--only before_send/slot_busy] [--keep-events]

Needs gcloud logged in as a user holding roles/iam.serviceAccountTokenCreator on the sandbox service account
(CALENDAR_SA, default interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com) in a project with the
Calendar API enabled. No key file and no domain-wide delegation: per cell the harness mints a one-hour,
calendar-scoped token by impersonation and passes it to the worker in its environment. The calendar is the service
account's own primary calendar, with no attendees.

Each cell: a booking request ("30-minute call at <slot>") is written; for pre_busy a customer event is put on the
slot first; a worker process asks the model to book it (once; the decision is persisted) and sends it with one
system; the worker SIGKILLs itself right before the insert or right after it returns; during the outage the harness
does nothing, puts a customer event on the slot, or cancels the request; a new worker runs the same job; events.list
on the slot is the ground truth. Everything needed to re-check a cell afterwards (full event resources, the journal
bundle, worker logs, crash markers) goes into results/scenarios/calendar.json, because the events and the service
account are deleted after the run. Writes results/scenarios/calendar.json and .md.
"""
import argparse, datetime, json, os, signal, statistics, subprocess, sys, tempfile, time, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scenarios", "calendar"))
import booking   # noqa: E402

SA = os.environ.get("CALENDAR_SA", "interlock-sandbox-cal@gen-lang-client-0277439345.iam.gserviceaccount.com")
WORKER = os.path.join(ROOT, "scenarios", "calendar", "worker.py")
OUT = os.path.join(ROOT, "results", "scenarios")
SYSTEM_ORDER = ("no_check", "hand_check", "interlock", "interlock_change_only")
EMULATED = ("booking request system: a local JSON file per request (status live or cancelled) read by the worker "
            "and rewritten by the harness to cancel; there is no real booking service")


def token():
    return subprocess.run(["gcloud", "auth", "print-access-token", f"--impersonate-service-account={SA}",
                           "--scopes=https://www.googleapis.com/auth/calendar"],
                          capture_output=True, text=True, check=True).stdout.strip()


def wait(proc, seconds):
    try:
        return proc.wait(seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise


def read(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


def run_cell(data, i, base, crash, action, system):
    rid = f"{uuid.uuid4().hex[:10]}{i:02d}"
    start = base + datetime.timedelta(hours=i)
    slot = booking.rfc3339(start)
    end = booking.rfc3339(start + datetime.timedelta(minutes=booking.DURATION))
    booking.write_request(data, {"id": rid, "slot_start": slot, "status": "live", "text":
                                 f"Booking request {rid}: Dana, a customer, asked for a 30-minute call on "
                                 f"{start:%A %Y-%m-%d} at {start:%H:%M} UTC to go over her onboarding."})
    cal = booking.Calendar(token(), SA)
    env = {**os.environ, "CALENDAR_TOKEN": cal.token, "CALENDAR_ID": SA, "CAL_CRASH": crash,
           "CAL_CRASH_MARKER": os.path.join(data, f"crash-{rid}")}
    cmd = [sys.executable, WORKER, "--system", system, "--request", rid, "--data", data]
    label = f"[{crash}/{action}:{system}] {rid} {slot}"
    customer = {"summary": "Dana: busy (interlock-sandbox)", "start": {"dateTime": slot}, "end": {"dateTime": end}}

    def put_customer(when):
        # list the slot right before the insert: Calendar's `created` is whole seconds, too coarse to order events
        before = [e["id"] for e in cal.list(slot, end)]
        ev = cal.insert(customer)
        return {"customer_event": ev["id"], "created": ev["created"], "when": when, "events_on_slot_before": before}

    outage = None
    if action == "pre_busy":            # the customer's event is there before the job is decided
        outage = put_customer("before the first worker")
    with open(os.path.join(data, f"worker-{rid}.log"), "ab") as log:
        first = wait(subprocess.Popen(cmd, env=env, stdout=log, stderr=log), 180)
        crashed_at = time.time()
        if first != -signal.SIGKILL and not (action == "pre_busy" and first == 0):
            raise RuntimeError(f"{label}: worker exited {first}, expected SIGKILL at {crash}")
        print(f"{label} first worker exit {first}", flush=True)

        if action == "slot_busy":       # the customer takes the slot during the outage: a real event, same calendar
            outage = put_customer("during the outage")
        elif action == "request_cancelled":
            booking.write_request(data, {**booking.read_request(data, rid), "status": "cancelled"})
            outage = {"request_status": "cancelled", "at": time.time(), "when": "during the outage"}

        second = wait(subprocess.Popen(cmd, env=env, stdout=log, stderr=log), 300)
        settled_at = time.time()
    if second != 0:
        raise RuntimeError(f"{label}: restarted worker exited {second}; see {log.name}")
    with open(os.path.join(data, f"result-{rid}.json")) as f:
        result = json.load(f)
    with open(os.path.join(data, f"decision-{rid}.json")) as f:
        decision = json.load(f)

    events = cal.list(slot, end)                                # ground truth, read back from Calendar
    want = booking.WANT[(crash, action)]
    g = booking.grade(events, rid, want, result["answer"], (outage or {}).get("events_on_slot_before", ()))
    receipt = result.get("receipt")
    proof = bool(receipt and receipt["valid"])
    rechecked = receipt and receipt.get("rechecked_at_recovery")
    ids = [f"request {rid}", f"slot {slot}", f"calendar {SA}",
           "agent events " + (", ".join(g["agent_events"]) or "none"),
           "other events " + (", ".join(g["other_events"]) or "none")]
    if result.get("effect_id"):
        ids.append(f"interlock effect {result['effect_id']}")
    print(f"{label} {result['outcome']} agent_events={len(g['agent_events'])} want={want} "
          f"held={g['invariant_held']} {settled_at - crashed_at:.1f}s", flush=True)
    return {
        "system": system, "fault": f"{crash}/{action}", "crash_point": crash, "outage_action": action,
        "request_id": rid, "slot_start": slot, "slot_end": end,
        "outcome": result["outcome"], "answer": result["answer"],
        "ground_truth": {"events_list": events, "agent_events": g["agent_events"], "other_events": g["other_events"],
                         "double_booked": g["double_booked"], "want_agent_events": want},
        "invariant_held": g["invariant_held"], "answer_matches_calendar": g["answer_matches_calendar"],
        "can_prove_what_happened": proof,
        "conflict_recorded_at_recovery": bool(rechecked and (rechecked.get("violations") or not rechecked.get("lease_live"))),
        "ids": "; ".join(ids), "seconds_to_settle": round(settled_at - crashed_at, 1), "emulated": EMULATED,
        "worker_exit_codes": [first, second], "crash_fired": first == -signal.SIGKILL, "outage": outage,
        "decision": decision, "receipt": receipt, "journal": result.get("journal"),
        "evidence": {"receipt_bundle": result.get("receipt_bundle"), "worker_log": read(log.name),
                     "crash_marker": read(env["CAL_CRASH_MARKER"]), "result_file": result,
                     "request_file": booking.read_request(data, rid)},
    }


def cleanup(cells):
    """Delete every event the run saw, then read each one back (showDeleted: status cancelled) as a record."""
    cal = booking.Calendar(token(), SA)
    record = []
    for c in cells:
        for e in c["ground_truth"]["events_list"]:
            try:
                cal.delete(e["id"])
                after = cal.get(e["id"])
                record.append({"id": e["id"], "deleted": True, "status_after_delete": after and after.get("status")})
            except booking.CalendarError as err:
                record.append({"id": e["id"], "deleted": False, "error": str(err)})
                print(f"could not delete {e['id']}: {err}", flush=True)
    return record


def cell_text(c):
    g = c["ground_truth"]
    n = len(g["agent_events"])
    held = "**held**" if c["invariant_held"] else ("**VIOLATED, double booked**" if g["double_booked"]
                                                   else "**VIOLATED**")
    answer = {True: "answer matches", False: "answer CONTRADICTS calendar", None: "answer unknown"}[c["answer_matches_calendar"]]
    crashed = "" if c["crash_fired"] else "; no crash (refused before the send)"
    return (f"{c['outcome']}; {n} agent event{'s' if n != 1 else ''} (want {g['want_agent_events']}); {held}; {answer}; "
            f"{c['seconds_to_settle']}s; proof: {'receipt' if c['can_prove_what_happened'] else 'none'}{crashed}")


def markdown(out):
    cells = out["cells"]
    by = {(c["fault"], c["system"]): c for c in cells}
    faults = list(dict.fromkeys(c["fault"] for c in cells))
    systems = [s for s in SYSTEM_ORDER if any(c["system"] == s for c in cells)]
    rows = "\n".join(f"| `{f}` | " + " | ".join(cell_text(by[(f, s)]) if (f, s) in by else "n/a" for s in systems) + " |"
                     for f in faults)

    def tally(s):
        cs = [c for c in cells if c["system"] == s]
        return (f"- **{s}**: invariant held {sum(c['invariant_held'] for c in cs)}/{len(cs)}, answers matched the "
                f"calendar {sum(c['answer_matches_calendar'] is True for c in cs)}/{len(cs)}, double bookings "
                f"{sum(c['ground_truth']['double_booked'] for c in cs)}, provable record {sum(c['can_prove_what_happened'] for c in cs)}/{len(cs)}, "
                f"median {statistics.median(c['seconds_to_settle'] for c in cs):.1f}s crash to settled")

    def same(f, a, b):
        return (by[(f, a)]["invariant_held"], by[(f, a)]["answer_matches_calendar"]) == \
               (by[(f, b)]["invariant_held"], by[(f, b)]["answer_matches_calendar"])

    differ = [f for f in faults if (f, "hand_check") in by and (f, "interlock") in by and not same(f, "hand_check", "interlock")]
    bad_no_check = [f for f in faults if (f, "no_check") in by and not by[(f, "no_check")]["invariant_held"]]
    conflicts = [f for f in faults if (f, "interlock") in by and by[(f, "interlock")]["conflict_recorded_at_recovery"]
                 and by[(f, "interlock")]["answer"] == "booked"]
    change_only = by.get(("before_send/pre_busy", "interlock_change_only"))
    retry = by.get(("after_commit/none", "interlock"))
    retry_evidence = retry and retry["receipt"]["evidence"]
    decisions = "\n".join(f"- `{c['fault']}` / {c['system']}: pid {c['decision']['pid']}: {c['decision']['tool_input']}"
                          for c in cells)
    ids = "\n".join(f"- `{c['fault']}` / {c['system']}: {c['ids']}; worker exits {c['worker_exit_codes']}" +
                    (f"; receipt valid={c['receipt']['valid']} happened={c['receipt']['happened']} "
                     f"authorized_when_fired={c['receipt']['authorized_when_fired']} "
                     f"assumptions_held={c['receipt']['assumptions_held']} evidence={c['receipt']['evidence']} "
                     f"journal {' > '.join(e['kind'] + ('(' + e['via'] + ')' if e.get('via') else '') for e in c['journal'])}"
                     if c.get("receipt") else "") for c in cells)
    deleted = out["cleanup"]
    return f"""# Scenario: double booking on Google Calendar

Generated {out['generated']} by `experiments/scenario_calendar.py`. Model `{out['model']}`, Google Calendar API v3,
the sandbox service account's own primary calendar (`{SA}`), no attendees, no delegation.

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

| fault | {' | '.join(systems)} |
|---|{'---|' * len(systems)}
{rows}

{chr(10).join(tally(s) for s in systems)}

**Verdict.** hand_check and interlock differ on {', '.join(f'`{f}`' for f in differ) or 'no row'} in outcome or
answer. {'hand_check TIES interlock on every calendar outcome here, `pre_busy` included.' if not differ else ''} That
tie depends on configuring interlock's slot premise to require an empty slot, which `interlock.easy` cannot express
(see "The systems"). {f"Configured as easy.py ships it, where a premise only has to stay unchanged, interlock ({change_only['system']}) went `{change_only['outcome']}` on `before_send/pre_busy` with the invariant {'held' if change_only['invariant_held'] else 'VIOLATED' + (', double booked' if change_only['ground_truth']['double_booked'] else '')}: " + ('WORSE than hand_check and no_check there, both of which refused.' if not change_only['invariant_held'] else 'no worse.') if change_only else ''}
no_check violated the invariant on {', '.join(f'`{f}`' for f in bad_no_check) or 'no row'}: it checked the request
and freebusy when the job was enqueued, and the queued send replayed after the crash without looking again.
Beyond the calendar, interlock leaves a hash-chained receipt recording the request status and slot contents it
checked before each send and again at recovery; hand_check records nothing about its checks (the event itself shows
the creator and, through extendedProperties, the request and system, which is all no_check and hand_check can show
afterwards). {'When its booking had already landed and the world then changed (' + ', '.join(f'`{f}`' for f in conflicts) + '), interlock reports booked and its receipt also records the failed re-check at recovery (slot now taken, or request cancelled), which tells whoever handles it next; hand_check reports booked and notes nothing. ' if conflicts else ''}{f"What the receipt proves is that the booking committed once, not which HTTP attempt created it: in `after_commit/none` the outcome is `{retry['outcome']}` because recovery settled it by retrying, and the retry got Calendar's 409, recorded in the COMMITTED result as {retry_evidence}; the event was created by the SIGKILLed first worker. " if retry else ''}Interlock is slower to settle after a SIGKILL: a dead sender's claim blocks recovery for `CLAIM_TTL` = {booking.CLAIM_TTL}s.

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
  `already_existed` when the insert was a 409), where `easy.py` records `{{"status": "ok"}}` and `True`.
- **interlock_change_only**: `interlock` without change (1), that is `interlock.easy` as it ships. Run on
  `before_send/pre_busy` only.

Proposed core change (not made): let `gate.effect` declare an expected value for a premise (for example
`expect={{"other_events_in_slot": []}}`) that `validate_premises` enforces at dispatch and recovery alongside the
unchanged-since-decided check, and have `_FunctionTarget.apply` and `query` record the function's return value.

## What is real

- Calendar: every insert, get, list, freebusy and delete is a real Calendar API v3 call as the service account.
- LLM: every decision is a real Anthropic Messages API call (`{out['model']}`, temperature 0), made once per job and
  persisted; all decisions are listed below.
- Crashes: `os.kill(os.getpid(), SIGKILL)` inside the worker, one-shot via a marker file. Exit codes are recorded.
- The customer's busy event is a real event on the same calendar, inserted by the harness.

## What is emulated

- The booking request system: a JSON file per request in a temp directory, read by the worker (`allowed` for
  interlock, the live check for hand_check and at enqueue for no_check) and rewritten by the harness to cancel.
  Every cell's `emulated` field says so.

## Evidence kept, and what was deleted

After the run the harness deleted every event it saw ({sum(d['deleted'] for d in deleted)} of {len(deleted)} deleted;
each read back afterwards with status {sorted(set(str(d.get('status_after_delete')) for d in deleted))}), and the
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

{decisions}

## Ids

{ids}

## Re-run

    env $(grep ^ANTHROPIC_API_KEY= /path/to/.env) python3 experiments/scenario_calendar.py
    python3 -m unittest tests.test_scenario_calendar      # offline logic
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="crash/action, e.g. before_send/slot_busy (repeatable)")
    ap.add_argument("--systems", default=",".join(SYSTEM_ORDER))
    ap.add_argument("--keep-events", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")

    data = tempfile.mkdtemp(prefix="interlock-calendar-")
    now = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
    base = now + datetime.timedelta(days=30)
    print(f"data {data}", flush=True)
    cells, i, record = [], 0, []
    try:
        for crash, action in booking.FAULTS:
            if a.only and f"{crash}/{action}" not in a.only:
                continue
            for system in a.systems.split(","):
                if system == "interlock_change_only" and action != "pre_busy":
                    continue
                cells.append(run_cell(data, i, base, crash, action, system))
                i += 1
    finally:
        record = [] if a.keep_events or not cells else cleanup(cells)
    out = {"key": "calendar", "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "model": cells[0]["decision"]["model"], "calendar": SA, "claim_ttl": booking.CLAIM_TTL,
           "events_kept": a.keep_events, "cleanup": record, "cells": cells}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "calendar.json"), "w") as f:
        json.dump(out, f, indent=2)
    with open(os.path.join(OUT, "calendar.md"), "w") as f:
        f.write(markdown(out))
    print(f"wrote {OUT}/calendar.json and calendar.md", flush=True)


if __name__ == "__main__":
    main()
