"""The payments service on the real mcp 2.x SDK, for the optional RealSdk test in tests/test_mcp_proxy.py."""
from mcp.server.mcpserver import MCPServer

app = MCPServer("payments")
refunds = []


@app.tool()
def get_order(order_id: str) -> dict:
    return {"order_id": order_id, "refunded_total": sum(r["amount"] for r in refunds if r["order_id"] == order_id)}


@app.tool()
def create_refund(order_id: str, amount: int, reference: str = "") -> dict:
    refunds.append({"order_id": order_id, "amount": amount, "reference": reference})
    return {"ok": True}


@app.tool()
def find_refund(reference: str) -> dict:
    return {"found": any(r["reference"] == reference for r in refunds)}


if __name__ == "__main__":
    app.run()
