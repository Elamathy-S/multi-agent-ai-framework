"""
client/mcp/gateway.py — FastAPI router that queries the real MCP server.

Mounted at /mcp/* by main.py.
GET /mcp/tools now queries the MCP server via the MCP client so it returns
all 10 tools, 4 prompts, and 4 resources — not just the local registry.
"""

import asyncio
import os
import json
from fastapi import APIRouter
from client.mcp.executor import run_tool_by_name
from client.agents.orchestrator import orchestrator

router = APIRouter(prefix="/mcp", tags=["MCP"])

MCP_SERVER_SSE_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")


async def _query_mcp_server(action: str, **kwargs) -> dict:
    """
    Connect to the MCP server over SSE and run an action.
    action: 'list_tools' | 'list_prompts' | 'list_resources'
    Falls back gracefully if MCP server is not running.
    """
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    try:
        async with sse_client(MCP_SERVER_SSE_URL, timeout=5) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                if action == "list_tools":
                    result = await session.list_tools()
                    return {
                        "tools": [
                            {
                                "name": t.name,
                                "description": t.description or "",
                                "input_schema": t.inputSchema,
                            }
                            for t in result.tools
                        ]
                    }
                elif action == "list_prompts":
                    result = await session.list_prompts()
                    return {
                        "prompts": [
                            {
                                "name": p.name,
                                "description": p.description or "",
                                "arguments": [a.name for a in (p.arguments or [])],
                            }
                            for p in result.prompts
                        ]
                    }
                elif action == "list_resources":
                    result = await session.list_resources()
                    return {
                        "resources": [
                            {
                                "uri":         str(r.uri),
                                "name":        r.name or "",
                                "description": r.description or "",
                            }
                            for r in result.resources
                        ]
                    }

    except ExceptionGroup as eg:
        return {"error": "MCP server not running", "detail": str(eg.exceptions[0])}
    except Exception as exc:
        return {"error": "MCP server not running", "detail": str(exc)}


# ---------------------------------------------------------------------------
# 1. LIST TOOLS — reads from real MCP server
# ---------------------------------------------------------------------------
@router.get("/tools")
async def list_tools():
    """List all 10 tools registered on the MCP server."""
    return await _query_mcp_server("list_tools")


# ---------------------------------------------------------------------------
# 2. LIST PROMPTS — reads from real MCP server
# ---------------------------------------------------------------------------
@router.get("/prompts")
async def list_prompts():
    """List all 4 prompts registered on the MCP server."""
    return await _query_mcp_server("list_prompts")


# ---------------------------------------------------------------------------
# 3. LIST RESOURCES — reads from real MCP server
# ---------------------------------------------------------------------------
@router.get("/resources")
async def list_resources():
    """List all 4 resources registered on the MCP server."""
    return await _query_mcp_server("list_resources")


# ---------------------------------------------------------------------------
# 4. FULL SURFACE — tools + prompts + resources in one call
# ---------------------------------------------------------------------------
@router.get("/surface")
async def mcp_surface():
    """Return the complete MCP server surface: tools, prompts, and resources."""
    tools     = await _query_mcp_server("list_tools")
    prompts   = await _query_mcp_server("list_prompts")
    resources = await _query_mcp_server("list_resources")
    return {
        "mcp_server": MCP_SERVER_SSE_URL,
        "tools":      tools.get("tools", []),
        "prompts":    prompts.get("prompts", []),
        "resources":  resources.get("resources", []),
        "counts": {
            "tools":     len(tools.get("tools", [])),
            "prompts":   len(prompts.get("prompts", [])),
            "resources": len(resources.get("resources", [])),
        }
    }


# ---------------------------------------------------------------------------
# 5. EXECUTE TOOL — direct call via registry (no MCP round-trip needed)
# ---------------------------------------------------------------------------
@router.post("/tools/execute")
def execute_tool_endpoint(payload: dict):
    """
    Execute a tool by name directly.
    Body: { "tool": "get_customer", "arguments": { "customer_id": 3 } }
    """
    tool_name = payload.get("tool")
    args      = payload.get("arguments", {})

    if not tool_name:
        return {"error": "Missing 'tool' field in request body"}

    return {"tool": tool_name, "output": run_tool_by_name(tool_name, args)}


# ---------------------------------------------------------------------------
# 6. RUN AGENT
# ---------------------------------------------------------------------------
@router.post("/agents/run")
def run_agent(payload: dict):
    """Route a natural language query through the orchestrator."""
    query       = payload.get("query", "")
    customer_id = payload.get("customer_id", 1)

    if not query:
        return {"error": "Missing 'query' field"}

    return {"result": orchestrator(query, customer_id)}