from backend.agents.base import run_tool
from backend.logger import log_tool_usage

def risk_agent(query, customer_id):

    q = query.lower()

    if "risk" in q:
        return run_tool(
            "risk_score_tool",
            log_func=log_tool_usage,
            query=query,
            agent_name = "risk_agent",
            customer_id=customer_id
        )
        

    if "fraud" in q:
        return run_tool(
            "fraud_check_tool",
            log_func=log_tool_usage,
            query=query,
            agent_name = "risk_agent",
            customer_id=customer_id
        )

    return {"message": "Risk agent cannot handle this query"}