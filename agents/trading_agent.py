from agents.base import run_tool
from backend.logger import log_tool_usage

def trading_agent(query, customer_id):

    q = query.lower()

    if "portfolio" in q:
        return run_tool(
            "get_portfolio",
            customer_id,
            log_tool_usage,
            query
        )

    if "pnl" in q:
        return run_tool(
            "calculate_pnl",
            customer_id,
            log_tool_usage,
            query
        )

    return {"message": "Trading agent cannot handle this query"}