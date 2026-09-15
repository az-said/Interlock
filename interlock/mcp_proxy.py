"""
Zero lines in the agent: Interlock as an MCP proxy.

    python3 -m interlock.mcp_proxy --config interlock.mcp.json -- python3 payments_server.py

Point the agent's MCP server command at this instead of the server. Every message passes
through untouched, except `tools/call` for the tools named in the config. Those go through
the gate: facts are read from another tool before the send and again before any resend,
the call is journaled before it goes out, a crash is recovered on the next start, and the
response carries the receipt in `_meta.interlock`. Recovery runs once per start: when a handshake client
sends notifications/initialized, or, for a client on the stateless 2026-07-28 spec (no handshake), before
the first gated call is sent.

    {
      "journal_dir": ".interlock/mcp",
      "tools": {
        "create_refund": {
          "key": ["order_id"],
          "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"},
                       "fields": ["refunded_total"]},
          "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
          "approval": {"tool": "get_approval", "arguments": {"order_id": "order_id"}},
          "idempotency_argument": "reference",
          "dedupes": false
        }
      }
    }

`key`       arguments that name the approved request; the same key is the same action
`premises`  a read tool, how to fill its arguments from the call's, and the fields that must not change
`lookup`    a tool that answers "did this effect already happen?" (tier 2); "$effect_id" fills in the id
`approval`  optional: a read tool returning the approval (approvals.Envelope), so the agent may send a
            corrected call after a refusal, within the approval, once
`idempotency_argument`  pass the effect id to the tool under this name
`dedupes`   true if the tool itself dedupes on that argument (tier 1)
A premise that counts the tool's own result (like refunded_total) needs a `lookup`, or
recovery after a crash can only say AMBIGUOUS. A refusal carries what changed in its text, as
structured changes in `_meta.interlock.escalation`, and as guidance for the agent in `_meta.interlock.repair`. The same config drives tools.protect() for in-process tool lists.
Standard library only.
"""
import itertools, json, queue, subprocess, sys, threading, uuid
from .easy import Interlock
from .escalation import WHY, code, describe, explain                   # re-exported for old imports
from .gate import Rejected
from .journal import CLAIM_TTL, effect_id_for, open_dispatch
from .tools import RESOLVED, ToolError, fill, gated, run, structured


class Upstream:
    """The real MCP server, as a child process. Our own requests use ids no client can guess."""
    def __init__(self, command, to_client):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.to_client, self.waiting, self.ids = to_client, {}, itertools.count(1)
        self.prefix = f"interlock-{uuid.uuid4().hex}-"
        self.write_lock, self.wait_lock = threading.Lock(), threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            if not line.strip():
                continue
            msg = json.loads(line)
            mid = msg.get("id")
            with self.wait_lock:
                waiter = self.waiting.pop(mid, None) if isinstance(mid, str) and mid.startswith(self.prefix) else None
            (waiter.put if waiter else self.to_client)(msg)
        with self.wait_lock:
            waiters, self.waiting = list(self.waiting.values()), {}
        for waiter in waiters:
            waiter.put({"exited": "upstream MCP server exited"})   # not an answer: the call may have landed

    def send(self, msg):
        with self.write_lock:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def call_tool(self, name, arguments, timeout=60):
        rid, waiter = f"{self.prefix}{next(self.ids)}", queue.Queue()
        with self.wait_lock:
            self.waiting[rid] = waiter
        self.send({"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        try:
            msg = waiter.get(timeout=timeout)
        except queue.Empty:
            with self.wait_lock:
                self.waiting.pop(rid, None)
            raise TimeoutError(f"{name} did not answer within {timeout}s") from None
        if "exited" in msg:
            raise ConnectionError(f"{name}: {msg['exited']}")      # outcome unknown, so recovery settles it
        if "error" in msg:
            raise ToolError(msg["error"].get("message"))
        return msg["result"]


class Proxy:
    def __init__(self, config, command):
        self.out = threading.Lock()
        self.upstream = Upstream(command, self.to_client)
        self.interlock = Interlock(config.get("journal_dir", ".interlock/mcp"), claim_ttl=config.get("claim_ttl", CLAIM_TTL))
        self.tools = {name: self._gated(name, spec) for name, spec in config["tools"].items()}
        self.recovered, self.recovering = False, threading.Lock()
        self.reads = {}                                   # client request id -> (tool, arguments) of a passthrough call

    def to_client(self, msg):
        read = self.reads.pop(msg.get("id"), None) if "result" in msg else None
        if read:                                          # the agent read a tool: its facts are what it decides on
            for call in self.tools.values():
                call.observe(*read, msg["result"])
        with self.out:
            sys.stdout.write(json.dumps(msg) + "\n")
            sys.stdout.flush()

    def _gated(self, name, spec):
        return gated(self.interlock, name, spec, self.upstream.call_tool, module=__name__)

    def handle_call(self, msg):
        """Every gated call gets exactly one answer, whatever happens inside."""
        try:
            self.recover()                                # a client with no handshake: settle a crash before the first send
            self._handle_call(msg)
        except Exception as e:
            sys.stderr.write(f"interlock: could not process call: {e!r}\n")
            self.to_client({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "isError": True, "content": [{"type": "text", "text": f"Interlock could not process this call ({type(e).__name__}); it will be settled before anything is sent again."}]}})

    def recover(self):
        """
        Resolve what a crash left in flight, once per proxy: on notifications/initialized (the handshake), or before
        the first gated call (a client on the stateless 2026-07-28 spec sends no handshake). Concurrent callers wait.
        """
        if self.recovered:
            return
        with self.recovering:
            if self.recovered:
                return
            try:
                for tool, outcomes in self.interlock.recover().items():
                    for eid, status in outcomes.items():
                        sys.stderr.write(f"interlock: recovered {tool} {eid}: {status}\n")
            finally:
                self.recovered = True                     # a failed recovery is not retried here; each call retries its own

    def _handle_call(self, msg):
        name, arguments = msg["params"]["name"], msg["params"].get("arguments") or {}
        out = run(self.tools[name], arguments)
        meta = {"interlock": {"status": out["status"], "receipt": out["receipt"], "repair": out["repair"],
                              "escalation": out["escalation"]}}
        if out["status"] == "COMMITTED" and isinstance(out["result"], dict):
            result = {**out["result"], "_meta": {**out["result"].get("_meta", {}), **meta}}
        else:
            result = {"content": [{"type": "text", "text": out["message"]}], "_meta": meta}
            if not out["ok"]:
                result["isError"] = True
        self.to_client({"jsonrpc": "2.0", "id": msg["id"], "result": result})

    def run(self):
        for line in sys.stdin:
            if not line.strip():
                continue
            msg = json.loads(line)
            if msg.get("method") == "tools/call" and (msg.get("params") or {}).get("name") in self.tools:
                threading.Thread(target=self.handle_call, args=(msg,), daemon=True).start()
                continue
            if msg.get("method") == "tools/call" and "id" in msg:
                params = msg.get("params") or {}
                self.reads[msg["id"]] = (params.get("name"), params.get("arguments") or {})
            self.upstream.send(msg)
            if msg.get("method") == "notifications/initialized":
                self.recover()                            # upstream is ready: resolve what a crash left in flight
        self.upstream.proc.stdin.close()
        self.upstream.proc.wait()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--" not in argv or "--config" not in argv:
        sys.exit("usage: python3 -m interlock.mcp_proxy --config interlock.mcp.json -- <server command>")
    with open(argv[argv.index("--config") + 1]) as f:
        config = json.load(f)
    Proxy(config, argv[argv.index("--") + 1:]).run()


if __name__ == "__main__":
    main()
