from mcp.tool_registry import TOOLS
import time

def run_tool(tool_name, customer_id, log_func, query=""):

    tool = TOOLS.get(tool_name)

    if not tool:
        return {"error": "Tool not found"}

    start = time.time()
    result = tool["function"](customer_id=customer_id)
    latency = (time.time() - start) * 1000

    log_func(
        user_query=query,
        tool_name=tool_name,
        input_data={"customer_id": customer_id},
        output_data=result,
        latency_ms=latency
    )

    return result