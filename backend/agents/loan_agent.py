from backend.agents.base import run_tool
from backend.logger import log_tool_usage

def loan_agent(query, customer_id):

    q = query.lower()

    # LOAN STATUS
    if "status" in q or "loan" in q:
        return run_tool(
            "check_loan_status",
            log_func=log_tool_usage,
            query=query,
            agent_name = "loan_agent",
            customer_id=customer_id
        )

    # CREDIT SCORE
    if "credit" in q or "score" in q:
        return run_tool(
            "credit_score_tool",
            log_func=log_tool_usage,
            query=query,
            agent_name = "loan_agent",
            customer_id=customer_id
        )

    return {
        "agent": "loan_agent",
        "message": "I can only handle loan status or credit score queries right now."
    }