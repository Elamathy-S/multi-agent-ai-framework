"""
client/agents/base.py — Shared tool executor with MCP + permission enforcement.

All specialist agents use run_tool() to call tools.  Each call opens
a fresh MCP connection, executes the tool, and closes — this avoids
SSE timeout issues when slow LLM calls happen between tool calls
in the ReAct loop.

Permission checks happen here — if an agent tries to call a tool
it is not allowed to use, the call is blocked before the MCP
request is made.
"""

import time
from client.mcp.client import MCPClient, MCPToolError, MCPConnectionError
from client.security.permissions import check_permission


async def run_tool(
    mcp: MCPClient | None,
    tool_name: str,
    *,
    agent_name: str | None = None,
    denial_log: list | None = None,
    **kwargs,
) -> dict:
    """
    Execute a tool via the MCP server with:
    - Permission check (blocks unauthorised agent→tool calls)
    - Fresh MCP connection per call (avoids SSE timeout during ReAct)
    - Timing measurement
    - Error handling with graceful fallback

    Args:
        mcp:         Optional MCPClient (ignored — kept for API compat).
                     Each call opens its own short-lived connection.
        tool_name:   MCP tool name (e.g. "get_customer", "get_risk_score").
        agent_name:  Calling agent's name (for permission check).
        denial_log:  List to append permission denials to.
        **kwargs:    Arguments passed to the MCP tool.

    Returns:
        Tool result dict, or {"error": "..."} if blocked or failed.
    """
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

    # ── Call via MCP (fresh connection per call) ──────────────────────────
    start = time.time()
    try:
        async with MCPClient() as fresh_mcp:
            result = await fresh_mcp.call(tool_name, **kwargs)
        latency = (time.time() - start) * 1000
        print(f"  ⚡ {tool_name} → {latency:.0f}ms (via MCP)")
        return result

    except MCPToolError as e:
        latency = (time.time() - start) * 1000
        print(f"  ✕ {tool_name} → error after {latency:.0f}ms: {e}")
        return {"error": str(e)}

    except MCPConnectionError as e:
        return {"error": str(e)}

    except Exception as e:
        latency = (time.time() - start) * 1000
        print(f"  ✕ {tool_name} → unexpected error after {latency:.0f}ms: {e}")
        return {"error": str(e)}