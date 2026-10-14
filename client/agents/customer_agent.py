# """
# client/agents/customer_agent.py — Customer specialist agent.

# Owns: customer profiles and account details.
# Calls get_customer via the MCP server.
# """

# from client.mcp.client import MCPClient
# from client.agents.base import run_tool


# async def customer_agent(mcp: MCPClient, query: str, customer_id: int) -> dict:
#     """Run the customer agent — fetches profile via MCP."""
#     _denials = []

#     obs = await run_tool(
#         mcp, "get_customer",
#         agent_name="customer_agent",
#         denial_log=_denials,
#         customer_id=customer_id,
#     )

#     history = [{
#         "thought": f"Fetching profile for customer {customer_id}",
#         "action":  "get_customer",
#         "args":    {"customer_id": customer_id},
#         "obs":     obs,
#     }]

#     return {
#         "answer":       _summarise({"get_customer": obs}),
#         "observations": {"get_customer": obs},
#         "steps":        history,
#         "denials":      _denials,
#     }


# def _summarise(obs: dict) -> str:
#     d = obs.get("get_customer", {})
#     if d and "name" in d:
#         return f"{d['name']} ({d.get('email','')}) — account since {d.get('created_at','?')}"
#     return "Customer data retrieved."

"""
client/agents/customer_agent.py — Customer specialist agent.

Owns: customer profiles and account details.
Uses the ReAct reasoning loop to decide what to do.
"""

from client.mcp.client import MCPClient
from client.agents.react import react_loop

TOOLS = {
    "get_customer":   "Retrieve customer profile (name, email, account creation date)",
    "list_customers": "List customers in the database (id, name, email)",
}

PERSONA = (
    "the Customer Agent at a finance company. "
    "You look up customer profiles and identity information. "
    "For a simple 'who is customer X' question, one tool call is enough."
)


async def customer_agent(mcp: MCPClient, query: str, customer_id: int) -> dict:
    return await react_loop(
        mcp, query, customer_id,
        agent_name="customer_agent",
        persona=PERSONA,
        tools=TOOLS,
    )