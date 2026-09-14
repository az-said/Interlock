"""Settings shared by the API, the worker and the harness. Standard library only."""
import json, os, signal, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.targets.stripe_api import API, StripeClient, StripeError, _form

DATA = os.environ.get("INTERLOCK_DATA") or os.path.join(ROOT, ".interlock", "backend")
TEMPORAL = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE = os.environ.get("INTERLOCK_TASK_QUEUE", "interlock-refunds")     # the demo gives each column its own
# The gate requires every send to finish inside the claim, so the Stripe request timeout stays well under CLAIM_TTL.
# Defaults 30s and 40s; demo/serve.py lowers both (10s and 15s) so a run fits on a projector.
STRIPE_TIMEOUT = int(os.environ.get("INTERLOCK_STRIPE_TIMEOUT", 30))
CLAIM_TTL = int(os.environ.get("INTERLOCK_CLAIM_TTL", 40))
if not 0 < STRIPE_TIMEOUT <= CLAIM_TTL - 5:
    raise ValueError(f"INTERLOCK_STRIPE_TIMEOUT ({STRIPE_TIMEOUT}s) must be at least 5s under INTERLOCK_CLAIM_TTL ({CLAIM_TTL}s)")
REFUND_ATTEMPTS = 3 * CLAIM_TTL // 5    # retries 5s apart can wait out a dead worker's claim three times over
# EMULATED, for the key-window cells only (Stripe cannot be made to forget a key, and nobody waits a day):
#   INTERLOCK_EMULATE_24H=1  every refund POST from this worker uses '<key>/emulated-pruned', a key Stripe never
#                            saw, and Interlock's recovery runs with its clock 25h ahead
#   INTERLOCK_NO_LOOKUP=1    the Interlock target declares it cannot list refunds (Stripe can)
EMULATE_24H = os.environ.get("INTERLOCK_EMULATE_24H") == "1"
NO_LOOKUP = os.environ.get("INTERLOCK_NO_LOOKUP") == "1"


def path(name):
    os.makedirs(DATA, exist_ok=True)
    return os.path.join(DATA, name)


def stripe_key():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        try:
            out = subprocess.run(["stripe", "config", "--list"], capture_output=True, text=True, timeout=10).stdout
            key = next((l.split("=", 1)[1].strip().strip("'\"") for l in out.splitlines()
                        if l.strip().startswith("test_mode_api_key")), None)
        except (OSError, subprocess.SubprocessError):
            pass
    return key


class TimedStripeClient(StripeClient):
    """StripeClient.request with STRIPE_TIMEOUT in place of its fixed 30s. Otherwise the same request."""
    def request(self, method, path, params=None, idempotency_key=None):
        query = urllib.parse.urlencode(_form(params or {}))
        req = urllib.request.Request(f"{API}{path}" + (f"?{query}" if method == "GET" and query else ""),
                                     data=query.encode() if method == "POST" else None, method=method)
        req.add_header("Authorization", self._auth)
        if idempotency_key:
            req.add_header("Idempotency-Key", idempotency_key)
        try:
            with urllib.request.urlopen(req, timeout=STRIPE_TIMEOUT) as r:
                obj = json.loads(r.read())
                obj["_replayed"] = r.headers.get("Idempotent-Replayed") == "true"
                return obj
        except urllib.error.HTTPError as e:
            message = json.loads(e.read() or b"{}").get("error", {}).get("message")
            raise StripeError(f"{e.code} {method} {path}: {message}") from None


def stripe():
    return TimedStripeClient(stripe_key())       # refuses anything but a test-mode key


def crash_once(point):
    """
    SIGKILL this process at `point` when INTERLOCK_CRASH names it. One-shot: the marker file
    INTERLOCK_CRASH_MARKER is created first, so a restarted worker with the same env runs clean.
    """
    if os.environ.get("INTERLOCK_CRASH") != point:
        return
    try:
        os.close(os.open(os.environ["INTERLOCK_CRASH_MARKER"], os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return
    print(f"crash injected: SIGKILL at {point} (pid {os.getpid()})", file=sys.stderr, flush=True)
    os.kill(os.getpid(), signal.SIGKILL)
    # The kill is not synchronous for the thread that sends it (on macOS a gate running in asyncio.to_thread
    # went on to write COMMITTED before the process died). Never run past the crash point.
    while True:
        time.sleep(1)
