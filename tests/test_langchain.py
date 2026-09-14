"""
    uv run --no-project --with langchain-core --with langgraph python -m unittest tests.test_langchain

Interlock over LangChain tools, and the same tools inside a LangGraph ToolNode. Skipped when
langchain-core (or langgraph, for the ToolNode test) is not installed.
"""
import os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "experiments"))
from repair_loop import Shop

try:
    from langchain_core.tools import tool
except ImportError:
    tool = None
try:
    from langchain_core.messages import AIMessage
    from langgraph.prebuilt import ToolNode
except ImportError:
    ToolNode = None

CONFIG = {"claim_ttl": 0, "tools": {"create_refund": {
    "key": ["order_id"],
    "premises": {"tool": "get_order", "arguments": {"order_id": "order_id"}, "fields": ["refunded_total"]},
    "lookup": {"tool": "find_refund", "arguments": {"reference": "$effect_id"}, "found": "found"},
    "approval": {"tool": "get_approval", "arguments": {"order_id": "order_id"}},
    "idempotency_argument": "reference"}}}


@unittest.skipIf(tool is None, "langchain-core is not installed")
class LangChainTools(unittest.TestCase):
    def setUp(self):
        from interlock.langchain_tools import protect_tools
        shop = self.shop = Shop()

        @tool
        def get_order(order_id: str) -> dict:
            """Refund facts for an order."""
            return shop.get_order(order_id)

        @tool
        def get_approval(order_id: str) -> dict:
            """The support case approving a refund for an order."""
            return shop.get_approval(order_id)

        @tool
        def create_refund(order_id: str, amount: int, reference: str = "") -> dict:
            """Refund an order, in whole dollars."""
            return shop.create_refund(order_id, amount, reference)

        @tool
        def find_refund(reference: str) -> dict:
            """Whether a refund with this reference exists."""
            return shop.find_refund(reference)

        self.tools = protect_tools([get_order, get_approval, create_refund, find_refund],
                                   {**CONFIG, "journal_dir": tempfile.mkdtemp()})
        self.by_name = {t.name: t for t in self.tools}

    def test_refusal_is_the_tool_output_and_a_correction_is_sent_once(self):
        self.assertEqual(self.by_name["get_order"].invoke({"order_id": "881"}), {"order_id": "881", "refunded_total": 0})
        refused = self.by_name["create_refund"].invoke({"order_id": "881", "amount": 30})
        self.assertIn("amount 30 is over the 20 approved", refused)
        self.assertEqual(self.by_name["create_refund"].invoke({"order_id": "881", "amount": 20}), {"refund": 1})
        self.assertIn("already happened once", self.by_name["create_refund"].invoke({"order_id": "881", "amount": 20}))
        self.assertEqual(self.shop.total("881"), 20)

    @unittest.skipIf(ToolNode is None, "langgraph is not installed")
    def test_inside_a_langgraph_tool_node(self):
        from langgraph.graph import END, START, MessagesState, StateGraph
        graph = StateGraph(MessagesState)
        graph.add_node("tools", ToolNode(list(self.tools)))
        graph.add_edge(START, "tools")
        graph.add_edge("tools", END)
        app = graph.compile()
        call = lambda cid, amount: {"messages": [AIMessage(content="", tool_calls=[
            {"name": "create_refund", "args": {"order_id": "881", "amount": amount}, "id": cid, "type": "tool_call"}])]}
        self.assertIn("refund", app.invoke(call("c1", 20))["messages"][-1].content)
        self.assertIn("already happened once", app.invoke(call("c2", 20))["messages"][-1].content)
        self.assertEqual(self.shop.total("881"), 20)


if __name__ == "__main__":
    unittest.main()
