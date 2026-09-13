"""
A minimal MCP server over stdio for tests/test_mcp_proxy.py: a payments service with no dedup.

State lives in the JSON file named by FAKE_STATE, so a test can inspect it and change it
(a support rep refunding by hand) while the proxy is down. FAKE_SLOW seconds of delay after
a refund is written simulates a response that never makes it back.
"""
import json, os, sys, time

STATE = os.environ["FAKE_STATE"]
TOOLS = [{"name": n, "description": n, "inputSchema": {"type": "object"}}
         for n in ("get_order", "create_refund", "find_refund")]


def load():
    if not os.path.exists(STATE):
        return {"refunds": []}
    with open(STATE) as f:
        return json.load(f)


def save(state):
    with open(STATE + ".tmp", "w") as f:
        json.dump(state, f)
    os.replace(STATE + ".tmp", STATE)


def reply(mid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
    sys.stdout.flush()


def data(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}], "structuredContent": obj}


for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method, mid = msg.get("method"), msg["id"]
    if method == "initialize":
        reply(mid, {"protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}}, "serverInfo": {"name": "fake-payments", "version": "1"}})
    elif method == "tools/list":
        reply(mid, {"tools": TOOLS})
    elif method == "tools/call":
        name, args, state = msg["params"]["name"], msg["params"].get("arguments", {}), load()
        if name == "get_order":
            reply(mid, data({"order_id": args["order_id"],
                             "refunded_total": sum(r["amount"] for r in state["refunds"] if r["order_id"] == args["order_id"])}))
        elif name == "create_refund":
            state["refunds"].append({"order_id": args["order_id"], "amount": args["amount"], "reference": args.get("reference")})
            save(state)
            time.sleep(float(os.environ.get("FAKE_SLOW", "0")))
            reply(mid, {"content": [{"type": "text", "text": "refund created"}]})
        elif name == "find_refund":
            reply(mid, data({"found": any(r.get("reference") == args["reference"] for r in state["refunds"])}))
