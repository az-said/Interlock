"""
The three systems for the gcp_resource scenario, and the worker process that runs one of them.

    python3 -m scenarios.gcp_resource.systems SYSTEM PHASE CASE_DIR

SYSTEM is no_check, hand_check or interlock. PHASE is `decide` (the first worker: the model reads the live
config and decides, then the write is attempted and gcs.write may SIGKILL the process) or `restart` (a new
worker process after the crash). Each phase that finishes writes outcome_<phase>.json into CASE_DIR.

no_check    the decision is a queue message (job.json) redelivered until marked done; the worker re-sends
            the same upload. GCS offers no idempotency key for uploads, so a plain retry is the standard.
hand_check  the same queue, and the upload carries ifGenerationMatch=<the generation the model read>: GCS's
            own atomic precondition, plus the job id in custom metadata. On 412 it lists the object's
            versions and reports ALREADY_APPLIED if a generation carries its job id (landed, maybe since
            replaced), else PRECONDITION_FAILED and stops. Sends and results go to a structured log.
interlock   Gate over GcsObjectTarget (below): decision and premise journaled, DISPATCHED before the
            upload (which also carries ifGenerationMatch), recovery by tier 2 on restart.
"""
import json, os, sys, time, uuid
from interlock.gate import Gate
from interlock.journal import effect_id_for
from interlock.receipts import bundle, verify
from . import agent, gcs

CLAIM_TTL = 30          # longer than the GCS client's 10s timeout, so recovery never overlaps a send in progress


def _load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _save(path, obj):
    with open(path + ".tmp", "w") as f:
        json.dump(obj, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(path + ".tmp", path)


def log(case_dir, **event):
    with open(os.path.join(case_dir, "log.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.time(), **event}) + "\n")
        f.flush()
        os.fsync(f.fileno())


# ---- baselines ---------------------------------------------------------------------------------------------

def no_check_send(client, job):
    obj = gcs.write(client, job["bucket"], job["object"], job["body"], job["metadata"])
    return "WRITTEN", {"generation": obj["generation"]}


def hand_check_send(client, job):
    try:
        obj = gcs.write(client, job["bucket"], job["object"], job["body"], job["metadata"],
                        if_generation_match=job["generation"])
        return "WRITTEN", {"generation": obj["generation"]}
    except gcs.GcsError as e:
        if e.code != 412:
            raise
    # 412: the object moved. Did our own earlier send land (maybe since replaced), or did someone else move it?
    # List every generation and look for this job's id: it covers every earlier send of this job.
    found = [v["generation"] for v in client.versions(job["bucket"], job["object"])
             if v.get("metadata", {}).get("job_id") == job["job_id"]]
    live = client.get(job["bucket"], job["object"]) or {}
    ids = {"writes_found": found, "live_generation": live.get("generation"),
           "live_writer": live.get("metadata", {}).get("writer")}
    return ("ALREADY_APPLIED" if found else "PRECONDITION_FAILED"), ids


def run_baseline(system, phase, case, client):
    send, job_path = {"no_check": no_check_send, "hand_check": hand_check_send}[system], os.path.join(case["dir"], "job.json")
    if phase == "decide":
        d = agent.decide(client, case["bucket"], case["object"], case["incident"])
        _save(os.path.join(case["dir"], "decision.json"), d)
        job_id = uuid.uuid4().hex          # the queue message id, fixed when the job is enqueued
        _save(job_path, {"bucket": case["bucket"], "object": case["object"], "body": agent.CONFIGS[d["to_version"]],
                         "metadata": {"writer": "agent", "incident": case["incident_id"], "job_id": job_id},
                         "generation": d["generation"], "job_id": job_id})
    job = _load(job_path)
    if job.get("done"):
        return job["done"]
    check = (f"ifGenerationMatch={job['generation']}; on 412 list versions for job_id={job['job_id']}"
             if system == "hand_check" else None)
    log(case["dir"], agent="sre-agent", system=system, phase=phase, event="send", object=job["object"], check=check)
    outcome, ids = send(client, job)
    log(case["dir"], agent="sre-agent", system=system, phase=phase, event="result", outcome=outcome, ids=ids)
    job["done"] = [outcome, ids]
    _save(job_path, job)
    return outcome, ids


# ---- interlock ---------------------------------------------------------------------------------------------

class IncidentLeases:
    """Authority: the incident the rollback was approved under must still be open. A file the harness owns."""
    def __init__(self, path):
        self.path = path

    def _status(self, lease):
        return _load(self.path, {}).get(lease)

    def is_live(self, lease):
        return self._status(lease) == "open"

    def describe(self, lease):
        status = self._status(lease)
        return {"incident": lease, "status": status, "revoked": None if status == "open" else status}


class GcsObjectTarget:
    """
    EffectTarget: overwrite one GCS object. Tier 2: GCS has no idempotency key for uploads, but the bucket keeps
    object versions and every write carries metadata interlock_effect_id, so recovery can look up whether this
    effect's write exists, even after someone overwrote it.

    Premise: the live generation the decision was made on, unless the live object is this effect's own write.
    apply() also sends ifGenerationMatch, so the check and the write are atomic at GCS (the gate's own
    re-check alone leaves a window between reading and sending).
    """
    tier, queryable = 2, True

    def __init__(self, client):
        self.client = client

    def validate_premises(self, premises, eid=None):
        live = self.client.get(premises["bucket"], premises["object"])
        meta = (live or {}).get("metadata", {})
        if live and eid and meta.get("interlock_effect_id") == eid:
            return []
        now = live and live["generation"]
        return [] if now == premises["generation"] else [
            f"generation: was {premises['generation']}, now {now} (deployed by {meta.get('writer')})"]

    def apply(self, eid, effect, crash_after_effect=False):
        obj = gcs.write(self.client, effect["bucket"], effect["object"], effect["body"],
                        {"writer": "agent", "interlock_effect_id": eid}, if_generation_match=effect["if_generation_match"])
        return {"status": "ok", "generation": obj["generation"], "md5Hash": obj["md5Hash"]}

    def query(self, eid, effect):
        """The generation this effect wrote, or None."""
        return next((v["generation"] for v in self.client.versions(effect["bucket"], effect["object"])
                     if v.get("metadata", {}).get("interlock_effect_id") == eid), None)


def request_id(case):
    return f"rollback:{case['bucket']}/{case['object']}:{case['incident_id']}"


def proposal_for(case, d):
    where = {"bucket": case["bucket"], "object": case["object"]}
    return {"agent": "sre-agent", "lease": case["incident_id"], "request_id": request_id(case),
            "premises": {**where, "generation": d["generation"]},
            "effect": {**where, "to_version": d["to_version"], "body": agent.CONFIGS[d["to_version"]],
                       "if_generation_match": d["generation"]}}


def run_interlock(phase, case, client):
    gate = Gate(GcsObjectTarget(client), os.path.join(case["dir"], "journal.jsonl"),
                IncidentLeases(os.path.join(case["dir"], "incident.json")), claim_ttl=CLAIM_TTL)
    eid = effect_id_for({"request_id": request_id(case)})
    if phase == "decide":
        d = agent.decide(client, case["bucket"], case["object"], case["incident"])
        _save(os.path.join(case["dir"], "decision.json"), d)
        try:
            status = gate.submit(proposal_for(case, d))
        except gcs.GcsError as e:
            if e.code != 412:
                raise
            status = gate.settle_failed(eid, str(e))
    else:
        status, deadline = None, time.time() + 300
        while eid in gate.journal.in_flight():      # a SIGKILLed sender holds its claim until CLAIM_TTL runs out
            if time.time() > deadline:
                raise RuntimeError("recovery did not settle in 300s")
            got = gate.recover(only=[eid]).get(eid) or ""
            if got and not got.startswith("UNRESOLVED"):
                status = got
            else:
                time.sleep(1)
        status = status or gate.journal.receipt(eid)["final"]
    v = verify(bundle(gate.journal, eid))
    return status, {"effect_id": eid,
                    "journal": [e["kind"] + (f" via {e['via']}" if e.get("via") else "") for e in gate.journal.entries(eid)],
                    "receipt": {k: v[k] for k in ("valid", "tamper_evident", "signed", "happened", "happened_once",
                                                  "authorized_when_fired", "assumptions_held", "refused", "evidence",
                                                  "rechecked_at_recovery", "problems")}}


# ---- judging -----------------------------------------------------------------------------------------------

def claims_landed(outcome):
    """What the system itself says about whether its write landed: True, False, or None (it cannot say)."""
    if outcome in ("WRITTEN", "ALREADY_APPLIED") or outcome.startswith(("COMMITTED", "DUPLICATE")):
        return True
    if outcome.startswith("AMBIGUOUS") or outcome == "IN_FLIGHT":
        return None
    return False


def record_says(system, artifacts):
    """
    What the system's own saved record states, read from the record lines alone (not from the outcome string or GCS):
    who acted, which checks it records, and which agent writes landed (None when the record cannot say, e.g. a send
    logged with no result and nothing later that resolves it). can_prove compares `agent_writes` with GCS.
    """
    if system == "interlock":
        es = artifacts["journal.jsonl"]
        eid = es[0]["effect_id"] if es else None
        v = verify({"effect_id": eid, "entries": [e for e in es if e["effect_id"] == eid]})
        ev = v["evidence"]
        writes = ([ev["generation"] if isinstance(ev, dict) else ev] if v["happened"] is True
                  else [] if v["happened"] is False else None)
        checks = [f"{e['kind']}: {e.get('checks') or e.get('rechecked')}" for e in es if e.get("checks") or e.get("rechecked")]
        return {"actor": next((e.get("agent") for e in es if e["kind"] == "PROPOSED"), None), "checks": checks,
                "agent_writes": writes if v["valid"] else None, "chain_valid": v["valid"]}
    events, writes, unresolved, checks = artifacts["log.jsonl"], [], 0, []
    for e in events:
        if e["event"] == "send":
            unresolved += 1
            checks.append(e.get("check"))
        elif e["event"] == "result":
            unresolved -= 1
            if "writes_found" in e["ids"]:      # a version lookup covers every earlier send of this job
                writes, unresolved = list(e["ids"]["writes_found"]), 0
            elif e["outcome"] == "WRITTEN":
                writes.append(e["ids"]["generation"])
    return {"actor": next((e.get("agent") for e in events), None), "checks": checks,
            "agent_writes": None if unresolved else writes, "unresolved_sends": unresolved}


def can_prove(said, truth_writes):
    """The record names the actor, records the check (or its absence) for every send, and its writes equal GCS's."""
    return bool(said["actor"] and said["checks"] and said["agent_writes"] is not None
                and sorted(said["agent_writes"]) == sorted(truth_writes))


def judge(versions, live_generation, want_agent_writes, want_live_writer):
    """Ground truth from GCS's own version list: how many agent writes exist, and who deployed the live object."""
    writers = {v["generation"]: v.get("metadata", {}).get("writer") for v in versions}
    agent_writes = [g for g, w in writers.items() if w == "agent"]
    live_writer = writers.get(live_generation)
    return {"agent_writes": agent_writes, "live_generation": live_generation, "live_writer": live_writer,
            "held": len(agent_writes) == want_agent_writes and live_writer == want_live_writer}


def main(system, phase, case_dir):
    os.environ["INTERLOCK_CASE_DIR"] = case_dir
    case = {**_load(os.path.join(case_dir, "case.json")), "dir": case_dir}
    client = gcs.Gcs()
    if system == "interlock":
        outcome, ids = run_interlock(phase, case, client)
    else:
        outcome, ids = run_baseline(system, phase, case, client)
    _save(os.path.join(case_dir, f"outcome_{phase}.json"), {"outcome": outcome, "ids": ids, "settled_at": time.time()})
    print(outcome)


if __name__ == "__main__":
    main(*sys.argv[1:4])
