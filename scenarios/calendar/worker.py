"""
One booking job as its own OS process, so a crash is a real SIGKILL.

    python3 scenarios/calendar/worker.py --system no_check|hand_check|interlock|interlock_change_only --request <id> --data <dir>

Env: CALENDAR_TOKEN (access token for the sandbox service account), CALENDAR_ID, ANTHROPIC_API_KEY, and
CAL_CRASH=before_send|after_commit with CAL_CRASH_MARKER=<file> for a one-shot SIGKILL at that point.
Reads <data>/request-<id>.json. The first run asks the model to book it and persists the decision to
<data>/decision-<id>.json; a restarted job reuses that decision (a job is decided once) and runs the same system.
Writes <data>/result-<id>.json.
"""
import argparse, json, os, signal, sys, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import booking  # noqa: E402

MODEL = "claude-haiku-4-5-20251001"
SYSTEM = ("You are a scheduling agent with access to one calendar. Book exactly what the booking request asks for "
          "by calling book_call once. Times are RFC3339 in UTC, for example 2026-09-28T15:00:00Z. Invite nobody.")
TOOLS = [{"name": "book_call", "description": "Put a call on the calendar.",
          "input_schema": {"type": "object", "required": ["start", "duration_minutes", "summary"], "properties": {
              "start": {"type": "string", "description": "RFC3339 start time in UTC"},
              "duration_minutes": {"type": "integer"},
              "summary": {"type": "string", "description": "short event title"}}}}]


def crash_once(point):
    if os.environ.get("CAL_CRASH") != point or os.path.exists(os.environ["CAL_CRASH_MARKER"]):
        return
    with open(os.environ["CAL_CRASH_MARKER"], "w") as f:
        f.write(point)
    print(f"crash injected: SIGKILL at {point} (pid {os.getpid()})", file=sys.stderr, flush=True)
    os.kill(os.getpid(), signal.SIGKILL)


def decide(request):
    body = {"model": MODEL, "max_tokens": 512, "temperature": 0, "system": SYSTEM, "tools": TOOLS,
            "tool_choice": {"type": "tool", "name": "book_call"},
            "messages": [{"role": "user", "content": request["text"]}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 529) or attempt == 3:
                raise RuntimeError(f"Anthropic API {e.code}") from None
            time.sleep(2 ** attempt)
    call = next(b for b in resp["content"] if b["type"] == "tool_use")
    return {**booking.validate_decision(call["input"], request), "model": resp["model"], "tool_input": call["input"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=sorted(booking.SYSTEMS), required=True)
    ap.add_argument("--request", required=True)
    ap.add_argument("--data", required=True)
    a = ap.parse_args()

    request = booking.read_request(a.data, a.request)
    cal = booking.Calendar(os.environ["CALENDAR_TOKEN"], os.environ["CALENDAR_ID"])
    decided = os.path.join(a.data, f"decision-{a.request}.json")
    if not os.path.exists(decided):
        booking.write_json(decided, {"pid": os.getpid(), "ts": time.time(), **decide(request)})
    with open(decided) as f:
        decision = json.load(f)
    extra = {"journal_dir": os.path.join(a.data, f"journal-{a.request}")} if a.system.startswith("interlock") else {}
    result = booking.SYSTEMS[a.system](cal, a.data, a.request, {k: decision[k] for k in ("start", "end", "summary")},
                                       crash_once, **extra)
    result.update(pid=os.getpid(), finished=time.time())
    booking.write_json(os.path.join(a.data, f"result-{a.request}.json"), result)


if __name__ == "__main__":
    main()
