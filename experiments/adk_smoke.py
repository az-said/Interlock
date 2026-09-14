"""ADK tool-callback smoke test. Proves the hook points Interlock would use.

Claude:  ANTHROPIC_API_KEY=... uv run --no-project --with google-adk --with litellm \
           python experiments/adk_smoke.py anthropic/claude-haiku-4-5-20251001
Gemini:  GOOGLE_API_KEY=... uv run --no-project --with google-adk --with litellm \
           python experiments/adk_smoke.py gemini-2.5-flash
"""
import asyncio
import sys

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

calls = []  # proves whether the tool body ran


def refund(payment_intent: str, amount_cents: int) -> dict:
    """Refund a payment intent."""
    calls.append(payment_intent)
    return {"status": "refunded", "id": "re_fake"}


def before(tool, args, tool_context):
    tool_context.state["gate_seen"] = args
    if args.get("amount_cents", 0) > 1000:
        return {"status": "blocked", "reason": "over limit"}  # dict: tool body skipped
    return None  # None: tool runs


def after(tool, args, tool_context, tool_response):
    return {**tool_response, "receipt": "r1"}  # dict: replaces the response


async def main(model):
    agent = LlmAgent(
        name="refunder", model=model, tools=[refund],
        instruction="Call refund exactly once with the given args, then report the tool result verbatim.",
        before_tool_callback=before, after_tool_callback=after)
    svc = InMemorySessionService()
    s = await svc.create_session(app_name="smoke", user_id="u")
    runner = Runner(agent=agent, app_name="smoke", session_service=svc)
    for amt in (500, 5000):
        msg = types.Content(role="user", parts=[types.Part(text=f"refund pi_123 amount_cents={amt}")])
        async for ev in runner.run_async(user_id="u", session_id=s.id, new_message=msg):
            for p in ev.content.parts if ev.content else []:
                if p.function_response:
                    print(amt, "fn_response:", p.function_response.response)
    s = await svc.get_session(app_name="smoke", user_id="u", session_id=s.id)
    print("tool body calls:", calls, "state:", s.state)
    assert calls == ["pi_123"], "blocked call must not run the tool body"


if __name__ == "__main__":
    m = sys.argv[1]
    if m.startswith("anthropic/"):
        from google.adk.models.lite_llm import LiteLlm
        m = LiteLlm(model=m)
    asyncio.run(main(m))
