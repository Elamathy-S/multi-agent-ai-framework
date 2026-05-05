# client/mcp/__init__.py
from client.mcp.executor import run_tool_by_name
from client.mcp.gateway import router as mcp_router

__all__ = ["run_tool_by_name", "mcp_router"]