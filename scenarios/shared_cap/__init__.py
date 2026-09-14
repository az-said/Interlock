"""
Scenario shared_cap: two agents, two OS processes, one approval cap on one Stripe test payment.

cap.py  the Interlock pieces (a journal whose dispatch also reserves the shared cap) and pure helpers
bot.py  one bot process: an LLM decides the refund, then no_check, hand_check or interlock sends it

Run it with experiments/scenario_shared_cap.py.
"""
