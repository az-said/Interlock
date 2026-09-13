"""
Zero lines in the agent: Interlock as an MCP proxy.

    python3 -m interlock.mcp_proxy --config interlock.mcp.json -- python3 payments_server.py

Point the agent's MCP server command at this instead of the server. Every message passes
through untouched, except `tools/call` for the tools named in the config. Those go through
the gate: facts are read from another tool before the send and again before any resend,
the call is journaled before it goes out, a crash is recovered on the next start, and the
response carries the receipt in `_meta.interlock`.

    {
      "journal_dir": ".interlock/mcp",
      "tools": {
        "create_refund": {
          "key": ["order_id"],
          "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"},
                       "fields": ["refunded_total"]},
          "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
          "idempotency_argument": "reference",
          "dedupes": false
        }
      }
    }

`key`       arguments that name the approved request; the same key is the same action
`premises`  a read tool, how to fill its arguments from the call's, and the fields that must not change
`lookup`    a tool that answers "did this effect already happen?" (tier 2); "$effect_id" fills in the id
`idempotency_argument`  pass the effect id to the tool under this name
`dedupes`   true if the tool itself dedupes on that argument (tier 1)
A premise that counts the tool's own result (like refunded_total) needs a `lookup`, or
recovery after a crash can only say AMBIGUOUS. Standard library only.
"""
import itertools, json, queue, subprocess, sys, threading, uuid
from .easy import Interlock
from .journal import CLAIM_TTL, effect_id_for

RESOLVED = ("DUPLICATE_IGNORED", "COMMITTED_BY_RETRY", "COMMITTED_ON_QUERY", "REAPPLIED_AFTER_QUERY")
WHY = {
    "REFUSED:stale_premise": "a fact this action depends on changed since it was decided",
    "REFUSED:stale_premise_at_recovery": "a fact this action depends on changed while the agent was down",
    "REFUSED:conflicting_payload": "the same request was already decided with different arguments",
    "REFUSED:target_error": "the tool reported an error, and nothing was sent again",
    "AMBIGUOUS": "a crash left it unclear whether it happened, and the tool gives no way to check",
    "IN_FLIGHT": "its outcome is not known yet; Interlock will settle it before anything is sent again",
}


class ToolError(RuntimeError):
    pass


def structured(result):
    """A tool result's data: structuredContent, or JSON in its first text block."""
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                data = json.loads(block["text"])
                return data if isinstance(data, dict) else {}
            except ValueError:
                pass
    return {}


def fill(template, arguments, effect_id):
    return {k: effect_id if v == "$effect_id" else arguments.get(v) for k, v in template.items()}


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
            waiter.put({"error": {"message": "upstream MCP server exited"}})

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
        if "error" in msg:
            raise ToolError(msg["error"].get("message"))
        return msg["result"]


class Proxy:
    def __init__(self, config, command):
        self.out = threading.Lock()
        self.upstream = Upstream(command, self.to_client)
        self.interlock = Interlock(config.get("journal_dir", ".interlock/mcp"), claim_ttl=config.get("claim_ttl", CLAIM_TTL))
        self.tools = {name: self._gated(name, spec) for name, spec in config["tools"].items()}
        self.recovered = False

    def to_client(self, msg):
        with self.out:
            sys.stdout.write(json.dumps(msg) + "\n")
            sys.stdout.flush()

    def _gated(self, name, spec):
        up = self.upstream
        key = lambda arguments: f"{name}:" + json.dumps({k: arguments.get(k) for k in spec["key"]}, sort_keys=True)

        def send(arguments, idempotency_key):
            args = dict(arguments)
            if spec.get("idempotency_argument"):
                args[spec["idempotency_argument"]] = idempotency_key
            result = up.call_tool(name, args)
            if result.get("isError"):
                raise ToolError(json.dumps(result.get("content")))
            return result
        send.__name__ = send.__qualname__ = name

        premises = lookup = None
        if "premises" in spec:
            p = spec["premises"]
            def premises(arguments, idempotency_key):
                facts = structured(up.call_tool(p["tool"], fill(p["arguments"], arguments, idempotency_key)))
                return {field: facts.get(field) for field in p["fields"]}
        if "lookup" in spec:
            l = spec["lookup"]
            def lookup(arguments, idempotency_key):
                return bool(structured(up.call_tool(l["tool"], fill(l["arguments"], arguments, idempotency_key))).get(l.get("found", "found")))

        call = self.interlock.effect(key=key, premises=premises, lookup=lookup, dedupes=spec.get("dedupes", False))(send)
        call.key = key
        return call

    def handle_call(self, msg):
        """Every gated call gets exactly one answer, whatever happens inside."""
        try:
            self._handle_call(msg)
        except Exception as e:
            sys.stderr.write(f"interlock: could not process call: {e!r}\n")
            self.to_client({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "isError": True, "content": [{"type": "text", "text": f"Interlock could not process this call ({type(e).__name__}); it will be settled before anything is sent again."}]}})

    def _handle_call(self, msg):
        name, arguments = msg["params"]["name"], msg["params"].get("arguments") or {}
        call = self.tools[name]
        eid = effect_id_for({"request_id": call.key(arguments)})
        try:
            status, result = call(arguments)
        except ToolError as e:                            # the tool answered "failed": settle it, never resend
            status, result = call.gate.settle_failed(eid, str(e)) or "IN_FLIGHT", None
        except Exception as e:                            # no answer (timeout, upstream gone): outcome unknown.
            sys.stderr.write(f"interlock: {name} did not settle ({e!r}); left for recovery\n")
            status, result = "IN_FLIGHT", None            # recovery takes it over once the send's claim expires
        meta = {"interlock": {"status": status, "receipt": call.gate.journal.receipt(eid)}}
        if status == "COMMITTED" and result is not None:
            result = {**result, "_meta": {**result.get("_meta", {}), **meta}}
        elif status in RESOLVED or status == "COMMITTED":
            result = {"content": [{"type": "text", "text": f"Interlock: this action already happened once ({status}); it was not sent again."}], "_meta": meta}
        else:
            why = WHY.get(status, "the gate could not send it safely")
            result = {"isError": True, "_meta": meta,
                      "content": [{"type": "text", "text": f"Interlock did not send this action ({status}): {why}."}]}
        self.to_client({"jsonrpc": "2.0", "id": msg["id"], "result": result})

    def run(self):
        for line in sys.stdin:
            if not line.strip():
                continue
            msg = json.loads(line)
            if msg.get("method") == "tools/call" and (msg.get("params") or {}).get("name") in self.tools:
                threading.Thread(target=self.handle_call, args=(msg,), daemon=True).start()
                continue
            self.upstream.send(msg)
            if msg.get("method") == "notifications/initialized" and not self.recovered:
                self.recovered = True                     # upstream is ready: resolve what a crash left in flight
                for tool, outcomes in self.interlock.recover().items():
                    for eid, status in outcomes.items():
                        sys.stderr.write(f"interlock: recovered {tool} {eid}: {status}\n")
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
