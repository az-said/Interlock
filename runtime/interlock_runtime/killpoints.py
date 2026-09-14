"""
Instrumented kill points (section 2.2). ILR_KILL_AT="name,name@n" sends this process a real SIGKILL the nth
time `name` is hit (first time when @n is omitted). ILR_STOP_AT does the same with SIGSTOP; the harness sends SIGCONT.
Results label these "instrumented SIGKILL". Nothing here raises an exception or fakes a crash.
"""
import os, signal, threading, time

_hits, _lock = {}, threading.Lock()


def _armed(var, point, n):
    for item in filter(None, os.environ.get(var, "").split(",")):
        name, _, at = item.strip().partition("@")
        if name == point and n == int(at or 1):
            return True
    return False


def hit(point):
    with _lock:
        n = _hits[point] = _hits.get(point, 0) + 1
    # kill() to our own pid can return before the signal takes effect (observed on macOS: a worker "killed" at
    # effect_after_dispatch went on to send and commit). Block this thread so nothing runs past the point.
    if _armed("ILR_STOP_AT", point, n):
        os.kill(os.getpid(), signal.SIGSTOP)
        time.sleep(0.2)                    # the stop lands during this sleep; after SIGCONT the thread continues
    if _armed("ILR_KILL_AT", point, n):
        os.kill(os.getpid(), signal.SIGKILL)
        threading.Event().wait()
