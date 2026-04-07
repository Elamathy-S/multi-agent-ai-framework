from agents.base import run_tool
from backend.logger import log_tool_usage

def loan_agent(query, customer_id):

    q = query.lower()

    # LOAN STATUS
    if "status" in q or "loan" in q:
        return run_tool(
            "check_loan_status",
            customer_id,
            log_tool_usage,
            query
        )

    # CREDIT SCORE
    if "credit" in q or "score" in q:
        return run_tool(
            "credit_score_tool",
            customer_id,
            log_tool_usage,
            query
        )

    return {
        "agent": "loan_agent",
        "message": "I can only handle loan status or credit score queries right now."
    }