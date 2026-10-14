"""
client/agents/base.py — Shared tool executor with MCP + permission enforcement.

All specialist agents use run_tool() to call tools.  It now goes through
the MCP server (via an open MCPClient session) instead of importing
Python functions directly from the tool registry.

Permission checks still happen here — if an agent tries to call a tool
it is not allowed to use, the call is blocked and logged before the
MCP request is made.
"""

import time
from client.mcp.client import MCPClient, MCPToolError, MCPConnectionError
from client.security.permission_checker import check_permission


async def run_tool(
    mcp: MCPClient,
    tool_name: str,
    *,
    agent_name: str | None = None,
    denial_log: list | None = None,
    **kwargs,
) -> dict:
    """
    Execute a tool via the MCP server with:
    - Permission check (blocks unauthorised agent→tool calls)
    - Timing measurement
    - Error handling with graceful fallback

    Args:
        mcp:         An open MCPClient session to call tools through.
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

    # ── Call via MCP ──────────────────────────────────────────────────────
    start = time.time()
    try:
        result = await mcp.call(tool_name, **kwargs)
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