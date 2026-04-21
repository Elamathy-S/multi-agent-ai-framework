from backend.agents.base import run_tool
from backend.logger import log_tool_usage

def trading_agent(query, customer_id):

    q = query.lower()

    if "portfolio" in q:
        return run_tool(
            "get_portfolio",
            log_func=log_tool_usage,
            query=query,
            agent_name = "trading_agent",
            customer_id=customer_id
        )

    if "pnl" in q:
        return run_tool(
            "calculate_pnl",
            log_func=log_tool_usage,
            query=query,
            agent_name = "trading_agent",
            customer_id=customer_id
        )

    return {"message": "Trading agent cannot handle this query"}