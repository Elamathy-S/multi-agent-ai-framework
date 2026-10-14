"""
client/agents/risk_agent.py — Risk specialist agent.

Owns: risk scoring, fraud detection.
Uses the ReAct reasoning loop — if risk is HIGH, the LLM should
decide to also run a fraud check. If risk is LOW, it may skip it.
"""

from client.mcp.client import MCPClient
from client.agents.react import react_loop

TOOLS = {
    "get_risk_score": "Compute risk score 0-100 (LOW/MEDIUM/HIGH) with key risk factors",
    "check_fraud":    "Run fraud detection on recent transactions, returns flag + confidence",
}

PERSONA = (
    "the Risk Agent at a finance company. "
    "You assess financial risk and detect fraud. "
    "Start with get_risk_score. If the risk level is MEDIUM or HIGH, "
    "also run check_fraud to be thorough. "
    "If risk is LOW, you may finish without a fraud check unless "
    "the user specifically asked about fraud."
)


async def risk_agent(mcp: MCPClient, query: str, customer_id: int) -> dict:
    return await react_loop(
        mcp, query, customer_id,
        agent_name="risk_agent",
        persona=PERSONA,
        tools=TOOLS,
        rag_category="risk",
    )