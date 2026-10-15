"""
client/agents/customer_agent.py — Customer specialist agent.

Owns: customer profiles and account details.
Uses the ReAct reasoning loop to decide what to do.
"""

from client.mcp.client import MCPClient
from client.agents.react import react_loop

TOOLS = {
    "get_customer": "Retrieve customer profile (name, email, account creation date)",
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