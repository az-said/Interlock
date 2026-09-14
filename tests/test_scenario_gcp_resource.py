"""Offline logic of the gcp_resource scenario: no network. The live run is experiments/scenario_gcp_resource.py."""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock.gate import Gate
from scenarios.gcp_resource import agent, gcs, systems


class FakeGcs:
    """GCS object versions in a list, with ifGenerationMatch semantics. Offline tests only.
    versioned=False lists only the live object, like a bucket without object versioning."""
    def __init__(self, versioned=True):
        self.versions_, self.versioned = [], versioned

    def upload(self, bucket, name, body, metadata, if_generation_match=None):
        live = self.get(bucket, name)
        if if_generation_match is not None and (live or {}).get("generation") != if_generation_match:
            raise gcs.GcsError(412, "conditionNotMet")
        obj = {"name": name, "generation": str(len(self.versions_) + 1), "md5Hash": gcs.md5_b64(body), "metadata": metadata}
        self.versions_.append(obj)
        return obj

    def get(self, bucket, name):
        return self.versions_[-1] if self.versions_ else None

    def versions(self, bucket, name):
        return list(self.versions_) if self.versioned else self.versions_[-1:]


def job(client, generation):
    return {"bucket": "b", "object": "o", "body": agent.CONFIGS["v41"], "metadata": {"writer": "agent", "job_id": "j1"},
            "generation": generation, "job_id": "j1"}


class HandCheck(unittest.TestCase):
    def test_redeploy_since_decision_is_not_overwritten(self):
        c = FakeGcs()
        g0 = c.upload("b", "o", agent.CONFIGS["v42"], {"writer": "human-deploy"})["generation"]
        c.upload("b", "o", agent.CONFIGS["v43"], {"writer": "human-redeploy"})
        self.assertEqual(systems.hand_check_send(c, job(c, g0))[0], "PRECONDITION_FAILED")
        self.assertEqual(c.get("b", "o")["metadata"]["writer"], "human-redeploy")

    def test_own_write_already_there_reads_as_applied(self):
        c = FakeGcs()
        g0 = c.upload("b", "o", agent.CONFIGS["v42"], {"writer": "human-deploy"})["generation"]
        self.assertEqual(systems.hand_check_send(c, job(c, g0))[0], "WRITTEN")
        self.assertEqual(systems.hand_check_send(c, job(c, g0))[0], "ALREADY_APPLIED")
        self.assertEqual(len(c.versions_), 2)

    def test_lookup_finds_own_write_after_a_redeploy_only_with_versioning(self):
        for versioned, want in ((True, ("ALREADY_APPLIED", ["2"])), (False, ("PRECONDITION_FAILED", []))):
            c = FakeGcs(versioned)
            g0 = c.upload("b", "o", agent.CONFIGS["v42"], {"writer": "human-deploy"})["generation"]
            systems.hand_check_send(c, job(c, g0))
            c.upload("b", "o", agent.CONFIGS["v43"], {"writer": "human-redeploy"})
            outcome, ids = systems.hand_check_send(c, job(c, g0))
            self.assertEqual((outcome, ids["writes_found"]), want)


class Target(unittest.TestCase):
    def setUp(self):
        self.c = FakeGcs()
        self.g0 = self.c.upload("b", "o", agent.CONFIGS["v42"], {"writer": "human-deploy"})["generation"]
        self.t = systems.GcsObjectTarget(self.c)
        self.premises = {"bucket": "b", "object": "o", "generation": self.g0}
        self.effect = {"bucket": "b", "object": "o", "to_version": "v41", "body": agent.CONFIGS["v41"],
                       "if_generation_match": self.g0}

    def test_own_write_is_not_a_stale_premise(self):
        self.t.apply("e1", self.effect)
        self.assertEqual(self.t.validate_premises(self.premises, "e1"), [])
        self.assertEqual(self.t.query("e1", self.effect), "2")

    def test_redeploy_is_stale_and_lookup_still_finds_the_earlier_write(self):
        self.t.apply("e1", self.effect)
        self.c.upload("b", "o", agent.CONFIGS["v43"], {"writer": "human-redeploy"})
        self.assertIn("was 1, now 3", self.t.validate_premises(self.premises, "e1")[0])
        self.assertEqual(self.t.query("e1", self.effect), "2")

    def test_gate_recovery_refuses_after_redeploy_before_send(self):
        with tempfile.TemporaryDirectory() as d:
            case = {"bucket": "b", "object": "o", "incident_id": "INC-1", "dir": d}
            systems._save(os.path.join(d, "incident.json"), {"INC-1": "open"})
            gate = Gate(self.t, os.path.join(d, "j.jsonl"), systems.IncidentLeases(os.path.join(d, "incident.json")), claim_ttl=0)
            p = systems.proposal_for(case, {"generation": self.g0, "to_version": "v41"})
            eid = systems.effect_id_for(p)
            gate.journal.dispatch(eid, p["effect"], "dead-worker", 0, lease="INC-1", premises=p["premises"])
            self.c.upload("b", "o", agent.CONFIGS["v43"], {"writer": "human-redeploy"})
            self.assertEqual(gate.recover(only=[eid]), {eid: "REFUSED:stale_premise_at_recovery"})
            self.assertEqual([v["metadata"]["writer"] for v in self.c.versions_], ["human-deploy", "human-redeploy"])


class Record(unittest.TestCase):
    def send(self, check="c"):
        return {"agent": "sre-agent", "event": "send", "check": check}

    def test_unfinished_send_then_412_without_lookup_cannot_say(self):
        log = [self.send(), self.send(), {"event": "result", "outcome": "PRECONDITION_FAILED", "ids": {"live_generation": "3"}}]
        said = systems.record_says("hand_check", {"log.jsonl": log})
        self.assertIsNone(said["agent_writes"])
        self.assertFalse(systems.can_prove(said, ["2"]))

    def test_lookup_resolves_the_unfinished_send(self):
        log = [self.send(), self.send(), {"event": "result", "outcome": "ALREADY_APPLIED", "ids": {"writes_found": ["2"]}}]
        self.assertTrue(systems.can_prove(systems.record_says("hand_check", {"log.jsonl": log}), ["2"]))

    def test_no_check_retry_leaves_the_first_send_unresolved(self):
        log = [self.send(None), self.send(None), {"event": "result", "outcome": "WRITTEN", "ids": {"generation": "3"}}]
        self.assertIsNone(systems.record_says("no_check", {"log.jsonl": log})["agent_writes"])

    def test_interlock_without_versioning_misses_its_replaced_write(self):
        with tempfile.TemporaryDirectory() as d:
            c = FakeGcs(versioned=False)
            g0 = c.upload("b", "o", agent.CONFIGS["v42"], {"writer": "human-deploy"})["generation"]
            t = systems.GcsObjectTarget(c)
            case = {"bucket": "b", "object": "o", "incident_id": "INC-1", "dir": d}
            systems._save(os.path.join(d, "incident.json"), {"INC-1": "open"})
            gate = Gate(t, os.path.join(d, "j.jsonl"), systems.IncidentLeases(os.path.join(d, "incident.json")), claim_ttl=0)
            p = systems.proposal_for(case, {"generation": g0, "to_version": "v41"})
            eid = systems.effect_id_for(p)
            gate.journal.append("PROPOSED", eid, agent="sre-agent", lease="INC-1", premises=p["premises"], effect=p["effect"])
            gate.journal.append("AUTHORIZED", eid, lease="INC-1")
            gate.journal.dispatch(eid, p["effect"], "dead-worker", 0, lease="INC-1", premises=p["premises"])
            t.apply(eid, p["effect"])                                 # landed, then the worker died
            c.upload("b", "o", agent.CONFIGS["v43"], {"writer": "human-redeploy"})
            self.assertEqual(gate.recover(only=[eid]), {eid: "REFUSED:stale_premise_at_recovery"})   # wrong: it landed
            with open(os.path.join(d, "j.jsonl")) as f:
                said = systems.record_says("interlock", {"journal.jsonl": [json.loads(l) for l in f]})
            self.assertEqual(said["agent_writes"], [])


class Judging(unittest.TestCase):
    def test_judge_and_claims(self):
        vs = [{"generation": "1", "metadata": {"writer": "human-deploy"}}, {"generation": "2", "metadata": {"writer": "agent"}},
              {"generation": "3", "metadata": {"writer": "human-redeploy"}}]
        self.assertTrue(systems.judge(vs, "3", 1, "human-redeploy")["held"])
        self.assertFalse(systems.judge(vs, "3", 0, "human-redeploy")["held"])
        self.assertIs(systems.claims_landed("COMMITTED_ON_QUERY"), True)
        self.assertIs(systems.claims_landed("REFUSED:stale_premise_at_recovery"), False)
        self.assertIs(systems.claims_landed("PRECONDITION_FAILED"), False)
        self.assertIsNone(systems.claims_landed("AMBIGUOUS"))

    def test_model_may_only_pick_the_approved_version(self):
        with self.assertRaises(agent.AgentError):
            agent.validate({"to_version": "v40", "reason": "older"})

    def test_client_refuses_resources_outside_the_sandbox(self):
        with self.assertRaises(ValueError):
            gcs.Gcs(bearer="x").request("GET", f"{gcs.API}/b/prod-configs/o/app.json")


if __name__ == "__main__":
    unittest.main()
