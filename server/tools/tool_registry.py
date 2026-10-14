"""
server/tools/tool_registry.py — DEPRECATED stub.

All tool execution now goes through the MCP server (mcp_server.py).
This file is kept only so that any stray `from server.tools.tool_registry
import ...` does not crash at import time.

The registry is no longer populated or used for execution.
"""

import warnings


class ToolRegistry:
    """Deprecated — tools are registered on the MCP server via @mcp.tool()."""

    def __init__(self):
        self.tools = {}

    def register(self, name, func, agent, description=""):
        self.tools[name] = {
            "function": func,
            "agent": agent,
            "description": description,
        }

    def get(self, name):
        return self.tools.get(name)


registry = ToolRegistry()


def init_tools():
    """No-op — tools are registered on the MCP server now."""
    pass