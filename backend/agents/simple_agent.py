from backend.tools.tool_registry import TOOLS
import time

def run_agent(user_query: str, customer_id: int = 1):
    query = user_query.lower()

    # Step 1: choose tool
    if "portfolio" in query:
        tool_name = "get_portfolio"

    elif "loan" in query:
        tool_name = "check_loan_status"

    elif "customer" in query or "profile" in query:
        tool_name = "get_customer_profile"

    else:
        return {"message": "Sorry, I don’t understand the request"}

    tool = TOOLS.get(tool_name)

    # Step 2: execute with timing
    start = time.time()
    result = tool["function"](customer_id=customer_id)
    end = time.time()

    response_time = (end - start) * 1000  # ms

    # Step 3: log
    log_tool_usage(
        user_query=user_query,
        tool_name=tool_name,
        input_params={"customer_id": customer_id},
        output=result,
        response_time=response_time
    )

    return {
        "tool_used": tool_name,
        "data": result,
        "response_time_ms": response_time
    }