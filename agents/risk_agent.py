from agents.base import run_tool
from backend.logger import log_tool_usage

def risk_agent(query, customer_id):

    q = query.lower()

    if "risk" in q:
        return run_tool(
            "risk_score_tool",
            customer_id,
            log_tool_usage,
            query
        )

    if "fraud" in q:
        return run_tool(
            "fraud_check_tool",
            customer_id,
            log_tool_usage,
            query
        )

    return {"message": "Risk agent cannot handle this query"}