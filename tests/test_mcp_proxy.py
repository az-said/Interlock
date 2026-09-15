"""
    python3 -m unittest discover -s tests

The MCP proxy against a real subprocess MCP server: passthrough, one refund per request,
recovery after the proxy is killed mid-call (with and without the initialize handshake), and refusal when support refunded by hand
while it was down.
"""
import json, os, queue, signal, subprocess, sys, tempfile, threading, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(ROOT, "tests", "fake_mcp_server.py")
CONFIG = {
    "journal_dir": "journal",
    "claim_ttl": 1,                 # a killed proxy's claim expires quickly, so the restart can recover it
    "tools": {"create_refund": {
        "key": ["order_id"],
        "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"}, "fields": ["refunded_total"]},
        "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
        "idempotency_argument": "reference",
    }},
}


class Session:
    """One proxy process (and its upstream child) in its own process group, with a line reader."""
    def __init__(self, cwd, state, slow=0, slow_before=0, modern=False, stderr=None):
        """modern: no handshake; every request carries the 2026-07-28 protocol envelope in _meta, as the spec says."""
        env = {**os.environ, "FAKE_STATE": state, "FAKE_SLOW": str(slow), "FAKE_SLOW_BEFORE": str(slow_before), "PYTHONPATH": ROOT,
               "FAKE_LOG": os.path.join(cwd, "calls.jsonl")}
        self.stderr = open(stderr, "a") if stderr else subprocess.DEVNULL
        self.proc = subprocess.Popen([sys.executable, "-m", "interlock.mcp_proxy", "--config", "config.json", "--", sys.executable, FAKE],
                                     cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                     text=True, bufsize=1, start_new_session=True)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.ids, self.modern = 0, modern
        if not modern:
            self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
            self.write({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _read(self):
        try:
            for line in self.proc.stdout:
                if line.strip():
                    self.lines.put(json.loads(line))
        except (ValueError, OSError):
            pass

    def _release(self):
        self.reader.join(timeout=5)
        for pipe in (self.proc.stdin, self.proc.stdout, None if self.stderr == subprocess.DEVNULL else self.stderr):
            if pipe is None:
                continue
            try:
                pipe.close()
            except (ValueError, OSError):
                pass

    def write(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params, wait=True):
        self.ids += 1
        if self.modern:
            params = {**params, "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                          "io.modelcontextprotocol/clientCapabilities": {},
                                          "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"}}}
        self.write({"jsonrpc": "2.0", "id": self.ids, "method": method, "params": params})
        if not wait:
            return None
        while True:
            msg = self.lines.get(timeout=20)
            if msg.get("id") == self.ids:
                return msg["result"]

    def refund(self, order_id, amount, wait=True):
        return self.request("tools/call", {"name": "create_refund", "arguments": {"order_id": order_id, "amount": amount}}, wait)

    def kill(self):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        else:
            os.killpg(self.proc.pid, signal.SIGKILL)
        self.proc.wait()
        self._release()

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=20)
        self._release()


class McpProxy(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = os.path.join(self.dir, "state.json")
        with open(os.path.join(self.dir, "config.json"), "w") as f:
            json.dump(CONFIG, f)

    def refunds(self):
        with open(self.state) as f:
            return json.load(f)["refunds"]

    def wait_for_refund(self):
        deadline = time.time() + 10
        while time.time() < deadline:
            if os.path.exists(self.state) and self.refunds():
                return
            time.sleep(0.05)
        self.fail("upstream never wrote the refund")

    def test_passthrough_and_one_refund_per_request(self):
        s = Session(self.dir, self.state)
        try:
            self.assertEqual(len(s.request("tools/list", {})["tools"]), 4)
            first = s.refund("881", 20)
            self.assertNotIn("isError", first)
            self.assertEqual(first["_meta"]["interlock"]["receipt"]["final"], "COMMITTED")
            again = s.refund("881", 20)
            self.assertIn("already happened once", again["content"][0]["text"])
            self.assertEqual(len(self.refunds()), 1)
        finally:
            s.close()

    def test_tool_error_gets_an_answer_and_is_not_resent(self):
        s = Session(self.dir, self.state)
        try:
            declined = s.refund("881", 999)
            self.assertTrue(declined.get("isError"), declined)
            self.assertIn("reported an error", declined["content"][0]["text"])
            self.assertFalse(os.path.exists(self.state))           # nothing was written, and nothing sent twice
            fine = s.refund("882", 20)                               # the proxy is still answering
            self.assertNotIn("isError", fine)
            self.assertEqual(len(self.refunds()), 1)
        finally:
            s.close()

    def test_killed_mid_call_is_recovered_once_on_restart(self):
        s = Session(self.dir, self.state, slow=5)
        s.refund("881", 20, wait=False)
        self.wait_for_refund()                                   # the service did it; the response never comes
        s.kill()
        time.sleep(1.5)                                          # the dead proxy's send claim expires
        s = Session(self.dir, self.state)                        # restart: recovery looks it up
        try:
            again = s.refund("881", 20)                          # the agent retries
            self.assertIn("already happened once", again["content"][0]["text"])
            self.assertEqual(len(self.refunds()), 1)
        finally:
            s.close()

    def test_refund_by_hand_during_outage_is_refused_even_when_the_agent_retries(self):
        s = Session(self.dir, self.state, slow=5)
        s.refund("881", 20, wait=False)
        self.wait_for_refund()
        with open(self.state, "w") as f:                         # roll back: model "never arrived" ...
            json.dump({"refunds": []}, f)
        s.kill()
        with open(self.state, "w") as f:                         # ... and support refunds it by hand meanwhile
            json.dump({"refunds": [{"order_id": "881", "amount": 20, "reference": None}]}, f)
        time.sleep(1.5)
        s = Session(self.dir, self.state)
        try:
            retry = s.refund("881", 20)
            self.assertTrue(retry.get("isError"), retry)
            self.assertIn("changed", retry["content"][0]["text"])
            self.assertIn("refunded_total: was 0, now 20", retry["content"][0]["text"])   # the fact, not just "something"
            self.assertFalse(retry["_meta"]["interlock"]["repair"]["may_retry"])         # no approval config: a person decides
            self.assertEqual(len(self.refunds()), 1)
        finally:
            s.close()

    def test_a_change_after_the_agents_own_read_is_caught(self):
        s = Session(self.dir, self.state)
        try:
            read = s.request("tools/call", {"name": "get_order", "arguments": {"order_id": "881"}})   # the agent reads: $0 refunded
            self.assertEqual(read["structuredContent"]["refunded_total"], 0)
            with open(self.state, "w") as f:                     # support refunds $5 before the agent's call arrives
                json.dump({"refunds": [{"order_id": "881", "amount": 5, "reference": None}]}, f)
            late = s.refund("881", 20)
            self.assertTrue(late.get("isError"), late)
            self.assertIn("refunded_total: was 0, now 5", late["content"][0]["text"])
            self.assertEqual(len(self.refunds()), 1)
        finally:
            s.close()

    def test_agent_repairs_a_refused_call_within_its_approval(self):
        config = json.loads(json.dumps(CONFIG))
        config["tools"]["create_refund"]["approval"] = {"tool": "get_approval", "arguments": {"order_id": "order_id"}}
        with open(os.path.join(self.dir, "config.json"), "w") as f:
            json.dump(config, f)
        s = Session(self.dir, self.state)
        try:
            over = s.refund("881", 30)                                   # the model overshoots the $20 case
            self.assertTrue(over.get("isError"), over)
            self.assertIn("amount 30 is over the 20 approved", over["content"][0]["text"])
            self.assertTrue(over["_meta"]["interlock"]["repair"]["may_retry"])
            self.assertNotIn("isError", s.refund("881", 20))             # corrected, sent once
            again = s.refund("881", 5)                                   # a second decision under a used approval
            self.assertTrue(again.get("isError"), again)
            self.assertEqual([r["amount"] for r in self.refunds()], [20])
        finally:
            s.close()


class StartupRecovery(unittest.TestCase):
    """A proxy killed after dispatching leaves an effect in flight; the restarted proxy resolves it once, handshake or not."""
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = os.path.join(self.dir, "state.json")
        self.stderr = os.path.join(self.dir, "stderr.log")
        with open(os.path.join(self.dir, "config.json"), "w") as f:
            json.dump(CONFIG, f)

    def read(self, path):
        with open(path) as f:
            return f.read()

    def crash_after_dispatch(self, modern):
        journal = os.path.join(self.dir, "journal", "__main__.create_refund.jsonl")    # the proxy runs as -m
        s = Session(self.dir, self.state, slow_before=30, modern=modern)             # the first send never lands
        s.refund("881", 20, wait=False)
        deadline = time.time() + 10
        while not (os.path.exists(journal) and '"DISPATCHED"' in self.read(journal)):
            self.assertLess(time.time(), deadline, "the proxy never dispatched")
            time.sleep(0.05)
        s.kill()
        time.sleep(1.5)                                              # the dead proxy's claim expires
        self.assertFalse(os.path.exists(self.state))                 # nothing landed: the effect is in flight

    def refunds(self):
        return [r["order_id"] for r in json.loads(self.read(self.state))["refunds"]]

    def recovered_lines(self):
        return [line for line in self.read(self.stderr).splitlines() if line.startswith("interlock: recovered")]

    def test_a_client_on_the_stateless_spec_gets_recovery_before_its_first_gated_call_is_sent(self):
        self.crash_after_dispatch(modern=True)
        s = Session(self.dir, self.state, modern=True, stderr=self.stderr)   # no initialize, no notifications/initialized
        try:
            other = s.refund("882", 20)                              # a different order: its own call does not settle 881
            self.assertEqual(other["_meta"]["interlock"]["status"], "COMMITTED", other)
            self.assertEqual(self.refunds(), ["881", "882"])         # 881 was resolved (resent once) before 882 went out
            sends = [c["arguments"]["order_id"] for c in map(json.loads, self.read(os.path.join(self.dir, "calls.jsonl")).splitlines())
                     if c["name"] == "create_refund"]
            self.assertEqual(sends, ["881", "881", "882"])           # the crashed send, recovery's resend, the new call
            s.refund("883", 20)
            self.assertEqual(len(self.recovered_lines()), 1)         # a later gated call does not recover again
        finally:
            s.close()

    def test_the_handshake_still_triggers_recovery_once(self):
        self.crash_after_dispatch(modern=False)
        s = Session(self.dir, self.state, stderr=self.stderr)
        try:
            deadline = time.time() + 10
            while not os.path.exists(self.state):                   # recovered on notifications/initialized, no call needed
                self.assertLess(time.time(), deadline, "recovery never ran after the handshake")
                time.sleep(0.05)
            self.assertEqual(s.refund("882", 20)["_meta"]["interlock"]["status"], "COMMITTED")
            self.assertEqual(self.refunds(), ["881", "882"])
            self.assertEqual(len(self.recovered_lines()), 1)         # the gated call did not run it again
        finally:
            s.close()

    def test_concurrent_triggers_run_recover_once_and_never_at_the_same_time(self):
        from interlock.mcp_proxy import Proxy
        with tempfile.TemporaryDirectory() as d:
            p = Proxy({**CONFIG, "journal_dir": os.path.join(d, "journal")}, [sys.executable, "-c", "pass"])
            p.upstream.proc.wait()
            runs, inside, most = [], [0], [0]
            def slow_recover():
                inside[0] += 1
                most[0] = max(most[0], inside[0])
                time.sleep(0.2)
                runs.append(1)
                inside[0] -= 1
                return {}
            p.interlock.recover = slow_recover
            threads = [threading.Thread(target=p.recover) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            p.upstream.proc.stdin.close()
            p.upstream.proc.stdout.close()
            self.assertEqual((len(runs), most[0]), (1, 1))


if __name__ == "__main__":
    unittest.main()
