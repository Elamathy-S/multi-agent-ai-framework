from agents.base import run_tool
from backend.logger import log_tool_usage

def customer_agent(query, customer_id):

    q = query.lower()

    if "profile" in q or "customer" in q:
        return run_tool(
            "get_customer_profile",
            customer_id,
            log_tool_usage,
            query
        )

    return {"message": "Customer agent cannot handle this query"}