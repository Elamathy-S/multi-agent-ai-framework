"""
client/agents/loan_agent.py — Loan specialist agent.

Owns: loan status, credit scores, approval decisions.
Uses the ReAct reasoning loop — the LLM decides whether to check
just loans, just credit, or both based on the question.
"""

from client.mcp.client import MCPClient
from client.agents.react import react_loop

TOOLS = {
    "get_loan_status": "List all loans for a customer (amounts, interest rates, statuses)",
    "get_credit_score": "Calculate credit score 300-850, rating, risk factors, approval likelihood",
}

PERSONA = (
    "the Loan Agent at a finance company. "
    "You assess loans and creditworthiness. "
    "If asked about loans only, call get_loan_status. "
    "If asked about credit or approval, call get_credit_score. "
    "If asked for a full loan review, call both."
)


async def loan_agent(mcp: MCPClient, query: str, customer_id: int) -> dict:
    return await react_loop(
        mcp, query, customer_id,
        agent_name="loan_agent",
        persona=PERSONA,
        tools=TOOLS,
        rag_category="loan",
    )