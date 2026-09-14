"""
Interlock for LangChain and LangGraph tools: the same gate and config as tools.protect(), over BaseTool objects.

    from interlock.langchain_tools import protect_tools
    tools = protect_tools([get_order, get_approval, create_refund, find_refund], config)
    tools.recover()                               # once, on startup
    agent = create_agent(model, tools)            # LangChain, or ToolNode(tools) / create_react_agent in LangGraph

Tools named in the config return the tool's own result when the call is sent, and Interlock's one-line
message otherwise (refused with what changed, already happened once, or not settled yet). Every other tool
passes through, and a read of the premises tool is remembered as what the agent decided on (see tools.py).
Sync tools only. Needs langchain-core; imported only when protect_tools() is called.
"""
from .tools import protect


class ToolList(list):
    """The wrapped tools, in the order given. recover() settles what a crash left in flight."""
    def __init__(self, tools, protected):
        super().__init__(tools)
        self.protected = protected

    def recover(self):
        return self.protected.recover()


def protect_tools(tools, config):
    from langchain_core.tools import StructuredTool

    by_name = {t.name: t for t in tools}
    protected = protect({name: (lambda _tool=t, **arguments: _tool.invoke(arguments)) for name, t in by_name.items()}, config)

    def wrap(name, original):
        def func(**arguments):
            out = protected[name](**arguments)
            if name not in config["tools"]:
                return out
            return out["result"] if out["status"] == "COMMITTED" and out["result"] is not None else out["message"]
        return StructuredTool.from_function(func=func, name=name, description=original.description,
                                            args_schema=original.args_schema)

    return ToolList([wrap(name, t) for name, t in by_name.items()], protected)
