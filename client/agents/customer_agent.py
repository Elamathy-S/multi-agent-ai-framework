"""
client/agents/customer_agent.py — Customer specialist agent.

Owns: customer profiles and account details.
"""

from server.tools.tool_registry import registry


def customer_agent(query: str, customer_id: int) -> dict:
    from client.agents.base import run_tool
    _denials = []

    obs = run_tool("get_customer_profile", agent_name="customer_agent",
                   denial_log=_denials, customer_id=customer_id)
    history = [{
        "thought": f"Fetching profile for customer {customer_id}",
        "action":  "get_customer_profile",
        "args":    {"customer_id": customer_id},
        "obs":     obs,
    }]

    return {
        "answer":       _fallback({"get_customer_profile": obs}),
        "observations": {"get_customer_profile": obs},
        "steps":        history,
        "denials":      _denials,
    }


def _fallback(obs):
    d = obs.get("get_customer_profile", {})
    if d and "name" in d:
        return f"{d['name']} ({d.get('email','')}) — account since {d.get('created_at','?')}"
    return "Customer data retrieved."