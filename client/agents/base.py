"""
client/agents/base.py — Shared tool executor with permission enforcement.

All specialist agents use run_tool() to call tools.
Permission checks happen here — if an agent tries to call a tool
it is not allowed to use, the call is blocked and logged.
"""

import time
from server.tools.tool_registry import registry
from client.security.permission_checker import check_permission


def run_tool(tool_name: str, log_func=None, query: str = "",
             agent_name: str = None, denial_log: list = None, **kwargs) -> dict:
    """
    Execute a tool with:
    - Permission check (blocks unauthorised agent→tool calls)
    - Timing measurement
    - Optional logging via log_func

    Args:
        tool_name:   Name of the tool to call.
        log_func:    Optional logging function (server logger).
        query:       Original user query (for logging).
        agent_name:  Name of calling agent (for permission check).
        denial_log:  List to append permission denials to (for agent logger).
        **kwargs:    Arguments passed to the tool function.

    Returns:
        Tool result dict, or {"error": "..."} if blocked or failed.
    """
    tool = registry.get(tool_name)
    if not tool:
        return {"error": f"Tool {tool_name} not found in registry"}

    # ── Permission check ──────────────────────────────────────────────────
    if agent_name:
        if not check_permission(agent_name, tool_name):
            denial = {
                "agent":  agent_name,
                "tool":   tool_name,
                "reason": f"{agent_name} is not authorised to call {tool_name}",
            }
            print(f"🚫 PERMISSION DENIED: {denial['reason']}")
            if denial_log is not None:
                denial_log.append(denial)
            return {"error": denial["reason"]}

    # ── Execute ───────────────────────────────────────────────────────────
    start = time.time()
    try:
        result  = tool["function"](**kwargs)
        latency = (time.time() - start) * 1000
        if log_func:
            log_func(user_query=query, tool_name=tool_name,
                     input_data=kwargs, output_data=result, latency_ms=latency)
        return result

    except Exception as e:
        latency = (time.time() - start) * 1000
        err = {"error": str(e)}
        if log_func:
            log_func(user_query=query, tool_name=tool_name,
                     input_data=kwargs, output_data=err, latency_ms=latency)
        return err