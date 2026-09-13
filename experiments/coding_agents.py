"""
Experiment 2: parallel coding agents. Scenarios 1, 2 and 3 of the team's
concurrency-control spec (docs/team-notes/research-spec-concurrency-control.md),
plus the crash/dup/lease faults from experiment 1, plus the coverage boundary.

Two agents on one repo. Agent B decides FIRST (snapshots the repo), agent A
lands FIRST. That ordering is the bug every worktree-based product ships.

Systems compared:
    naive        apply the diff; git-style; no memory
    gate/file    premises = hashes of files the agent read   (coarse; a naive hash check)
    gate/symbol  premises = symbols the agent called + arity (fine; the spec's read set)

Invariant: nothing lands that fails at runtime; nothing lands twice; at most
one implementation of any symbol; nothing lands under a revoked lease.
"""
import os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock import Gate, Naive, Leases, SimulatedCrash
from interlock.targets import LocalRepo

BASE_AUTH  = "def validate_session(token):\n    return token == 'ok'\n"
BASE_API   = "import auth\n"
BASE_UTILS = ""
B_APPEND   = "\ndef require_auth(req):\n    return auth.validate_session(req['token'])\n"
FMT_A      = "\ndef format_currency(x):\n    return f'${x:.2f}'\n"
FMT_B      = "\ndef format_currency(x):\n    return '$' + str(round(x, 2))\n"

FAULTS = {
    "rename_break":        "spec §6.6-1: A renames the function B calls; different files; git clean; build breaks",
    "duplicate_work":      "spec §6.6-2: A and B both implement format_currency (MAST top failure mode, 17%)",
    "benign_reformat":     "spec §6.6-3: A edits the file B read in a way B does not depend on",
    "crash_before_commit": "process dies after B's change is applied, before COMMITTED is journaled",
    "duplicate_submit":    "B's identical proposal arrives twice",
    "lease_revoked":       "B's authority is revoked after it decided, before its change lands",
    "semantic_only":       "coverage boundary: A keeps name+arity of B's callee but inverts its meaning",
}

def _fresh():
    d = tempfile.mkdtemp()
    open(f"{d}/auth.py", "w").write(BASE_AUTH)
    open(f"{d}/api.py", "w").write(BASE_API)
    open(f"{d}/utils.py", "w").write(BASE_UTILS)
    return d

def _state(d):
    if "def require_auth" not in open(f"{d}/api.py").read():
        return "not_landed"
    r = subprocess.run([sys.executable, "-c",
        "import api; assert api.require_auth({'token':'ok'}) is True"],
        cwd=d, capture_output=True, text=True)
    return "landed_ok" if r.returncode == 0 else "landed_BROKEN"

def _A(kind, repo, mode):
    writes = {"rename":   "def check_session(token):\n    return token == 'ok'\n",
              "benign":   BASE_AUTH + "\ndef log_attempt(token):\n    pass\n",
              "behavior": "def validate_session(token):\n    return False\n"}[kind]
    return {"agent": "A", "lease": "L-A", "premises": repo.capture(["auth.py"], [], mode),
            "effect": {"writes": {"auth.py": writes}}}

def _B(repo, mode):
    return {"agent": "B", "lease": "L-B",
            "premises": repo.capture(["auth.py"], ["auth.validate_session"], mode),
            "effect": {"appends": {"api.py": B_APPEND}}}

def _fmt(agent, repo, mode, body):
    return {"agent": agent, "lease": f"L-{agent}", "premises": repo.capture(["utils.py"], [], mode),
            "defines": ["utils.format_currency"], "effect": {"appends": {"utils.py": body}}}

def run(system, mode, fault):
    d = _fresh(); repo = LocalRepo(d)
    leases = Leases(); leases.grant("L-A"); leases.grant("L-B")
    s = Naive(repo) if system == "naive" else Gate(repo, tempfile.mktemp(suffix=".jsonl"), leases)

    if fault == "duplicate_work":
        A, B = _fmt("A", repo, mode, FMT_A), _fmt("B", repo, mode, FMT_B)
        if system == "gate":
            s.claim("A", "utils.format_currency")
            held_by = s.claim("B", "utils.format_currency")          # B is told A holds it
        s.submit(A)
        out = s.submit(B) if system == "naive" or held_by is None else f"REFUSED:claimed_by_{held_by}"
        n = open(f"{d}/utils.py").read().count("def format_currency")
        shutil.rmtree(d)
        return {"outcome": out, "result": f"{n} impl", "duplicated": n > 1, "invariant_held": n == 1, "caveat": ""}

    B = _B(repo, mode)                                          # B snapshots first ...
    A = _A({"rename_break": "rename", "semantic_only": "behavior"}.get(fault, "benign"), repo, mode)

    if fault in ("rename_break", "benign_reformat", "semantic_only"):
        s.submit(A); out = s.submit(B)                          # ... A lands first
    elif fault == "crash_before_commit":
        try: s.submit(B, crash_after_effect=True)
        except SimulatedCrash: pass
        rec = s.recover()
        if not rec: s.submit(B); out = "RETRIED"
        else: out = list(rec.values())[0]
    elif fault == "duplicate_submit":
        s.submit(B); out = s.submit(B)
    elif fault == "lease_revoked":
        leases.revoke("L-B"); out = s.submit(B)

    state = _state(d)
    dup = open(f"{d}/api.py").read().count("def require_auth") > 1
    shutil.rmtree(d)
    held = state != "landed_BROKEN" and not dup and not (fault == "lease_revoked" and state != "not_landed")
    caveat = "false_refusal" if (fault == "benign_reformat" and state == "not_landed") else ""
    return {"outcome": str(out), "result": state, "duplicated": dup, "invariant_held": held, "caveat": caveat}

SYSTEMS = [("naive", "symbol", "naive"), ("gate", "file", "gate/file"), ("gate", "symbol", "gate/symbol")]

def results():
    return {fault: {name: run(sysk, mode, fault) for sysk, mode, name in SYSTEMS} for fault in FAULTS}
