"""
client/mcp/client.py — Async MCP client for agent-to-server communication.

Provides MCPClient, an async context manager that holds a single MCP
session open so an agent can call multiple tools without reconnecting
each time.

Usage:
    async with MCPClient() as mcp:
        profile = await mcp.call("get_customer", customer_id=3)
        risk    = await mcp.call("get_risk_score", customer_id=3)
"""

import json
import os
from dataclasses import dataclass, field

from mcp.client.sse import sse_client
from mcp import ClientSession


MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")


class MCPConnectionError(Exception):
    """Raised when the MCP server is unreachable."""


class MCPToolError(Exception):
    """Raised when an MCP tool returns an error."""


@dataclass
class ToolResult:
    """Parsed result from a single MCP tool call."""
    tool_name: str
    arguments: dict
    data: dict | list
    raw_text: str = ""

    @property
    def ok(self) -> bool:
        return not (isinstance(self.data, dict) and "error" in self.data)


class MCPClient:
    """
    Async context manager wrapping one MCP SSE session.

    Opens a single connection to the MCP server on __aenter__ and
    closes it on __aexit__.  All tool calls within the block share
    the same session — no reconnect overhead per call.

    Tracks every tool call made during the session for observability.
    """

    def __init__(self, server_url: str = MCP_SERVER_URL):
        self._url = server_url
        self._session: ClientSession | None = None
        self._read = None
        self._write = None
        self._cm = None           # sse_client context manager
        self._session_cm = None   # ClientSession context manager
        self.call_log: list[ToolResult] = []

    async def __aenter__(self) -> "MCPClient":
        try:
            self._cm = sse_client(self._url, timeout=10, sse_read_timeout=600)
            self._read, self._write = await self._cm.__aenter__()
            self._session_cm = ClientSession(self._read, self._write)
            self._session = await self._session_cm.__aenter__()
            await self._session.initialize()
            return self
        except Exception as exc:
            # Clean up partial state
            await self._cleanup()
            raise MCPConnectionError(
                f"Cannot connect to MCP server at {self._url}. "
                f"Start it with: python -m server.mcp_server --http --port 8001"
            ) from exc

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cleanup()
        return False

    async def _cleanup(self):
        if self._session_cm:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
        if self._cm:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None

    async def call(self, tool_name: str, **kwargs) -> dict | list:
        """
        Call a single MCP tool and return the parsed result.

        Args:
            tool_name: Name of the tool as registered on the MCP server.
            **kwargs:  Arguments to pass (e.g. customer_id=3).

        Returns:
            Parsed JSON result (dict or list).

        Raises:
            MCPToolError: If the tool returns an error.
            MCPConnectionError: If the session is not open.
        """
        if not self._session:
            raise MCPConnectionError("MCPClient session is not open. Use 'async with MCPClient() as mcp:'")

        result = await self._session.call_tool(tool_name, kwargs)

        raw_text = result.content[0].text if result.content else "{}"

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            data = {"raw": raw_text}

        tool_result = ToolResult(
            tool_name=tool_name,
            arguments=kwargs,
            data=data,
            raw_text=raw_text,
        )
        self.call_log.append(tool_result)

        if result.is_error:
            raise MCPToolError(f"Tool {tool_name} returned error: {raw_text}")

        return data

    async def list_tools(self) -> list[dict]:
        """Return the tools available on the MCP server."""
        if not self._session:
            raise MCPConnectionError("Session not open")
        result = await self._session.list_tools()
        return [
            {"name": t.name, "description": t.description or "", "schema": t.input_schema}
            for t in result.tools
        ]