"""
    python3 -m unittest discover -s tests

The MCP proxy against a real subprocess MCP server: passthrough, one refund per request,
recovery after the proxy is killed mid-call, and refusal when support refunded by hand
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
    def __init__(self, cwd, state, slow=0):
        env = {**os.environ, "FAKE_STATE": state, "FAKE_SLOW": str(slow), "PYTHONPATH": ROOT}
        self.proc = subprocess.Popen([sys.executable, "-m", "interlock.mcp_proxy", "--config", "config.json", "--", sys.executable, FAKE],
                                     cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1, start_new_session=True)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.ids = 0
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
        for pipe in (self.proc.stdin, self.proc.stdout):
            try:
                pipe.close()
            except (ValueError, OSError):
                pass

    def write(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params, wait=True):
        self.ids += 1
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


if __name__ == "__main__":
    unittest.main()
