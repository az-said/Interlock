"""Settings shared by the API, the worker and the harness. Standard library only."""
import os, signal, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from interlock.targets.stripe_api import StripeClient

DATA = os.environ.get("INTERLOCK_DATA") or os.path.join(ROOT, ".interlock", "backend")
TEMPORAL = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE = "interlock-refunds"
CLAIM_TTL = 40      # seconds: longer than the Stripe client's 30s request timeout, as the gate requires
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


def stripe():
    return StripeClient(stripe_key())       # refuses anything but a test-mode key


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
