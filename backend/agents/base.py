import time
from backend.tools.tool_registry import registry
from backend.security.permission_checker import check_permission


def run_tool(tool_name, log_func=None, query="", agent_name=None, **kwargs):

    tool = registry.get(tool_name)

    if not tool:
        return {"error": f"Tool {tool_name} not found"}

    if agent_name:
        if not check_permission(agent_name, tool_name):
            return {
                "error": f"Permission denied for {agent_name} to access {tool_name}"
            }

    start = time.time()

    try:
        result = tool["function"](**kwargs)

        latency = (time.time() - start) * 1000

        if log_func:
            log_func(
                user_query=query,
                tool_name=tool_name,
                input_data=kwargs,
                output_data=result,
                latency_ms=latency
            )

        return result

    except Exception as e:
        latency = (time.time() - start) * 1000

        if log_func:
            log_func(
                user_query=query,
                tool_name=tool_name,
                input_data=kwargs,
                output_data={"error": str(e)},
                latency_ms=latency
            )

        return {"error": str(e)}
