"""
client/tool_router.py — MCP tool discovery.

The MCP server is the single source of truth for which tools exist. Agents
receive their tools from it at run time (filtered by RBAC); nothing here maps
words to tools.
"""

from client.mcp.client import MCPClient, MCPConnectionError


# ---------------------------------------------------------------------------
# Live tool discovery — queries the MCP server for its actual tool list
# ---------------------------------------------------------------------------
_cached_tools: list[dict] | None = None


async def discover_tools(force: bool = False) -> list[dict]:
    """
    Fetch the tool list from the MCP server.  Cached after first call.
    Returns a list of {name, description, input_schema} dicts.
    """
    global _cached_tools
    if _cached_tools is not None and not force:
        return _cached_tools

    try:
        async with MCPClient() as mcp:
            _cached_tools = await mcp.list_tools()
        return _cached_tools
    except MCPConnectionError:
        return []


async def get_tool_names() -> list[str]:
    """Return just the tool names from the MCP server."""
    tools = await discover_tools()
    return [t["name"] for t in tools]