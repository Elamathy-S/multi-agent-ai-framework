"""
tests/test_mcp_integration.py — Integration tests for the MCP pipeline.

These tests call the real MCP server and verify end-to-end behaviour.
Run with: PYTHONPATH=. pytest tests/test_mcp_integration.py -v

Requires:
  - MCP server running: PYTHONPATH=. python3 -m server.mcp_server --http --port 8001
  - Database seeded:    PYTHONPATH=. python3 data/seed_data.py
"""

import pytest
from client.mcp.client import MCPClient, MCPConnectionError, MCPToolError
from client.agents.base import run_tool


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# MCPClient — connection and tool discovery
# ---------------------------------------------------------------------------
class TestMCPClient:

    async def test_connects_to_server(self, mcp):
        """MCPClient should connect and initialise successfully."""
        assert mcp is not None

    async def test_list_tools_returns_tools(self, mcp):
        """MCP server should expose at least 8 registered tools."""
        tools = await mcp.list_tools()
        tool_names = [t["name"] for t in tools]
        assert len(tools) >= 8
        assert "get_customer" in tool_names
        assert "get_risk_score" in tool_names
        assert "check_fraud" in tool_names

    async def test_call_get_customer(self, mcp):
        """Calling get_customer should return a dict with name and email."""
        result = await mcp.call("get_customer", customer_id=1)
        assert isinstance(result, dict)
        assert "name" in result
        assert "email" in result

    async def test_call_get_risk_score(self, mcp):
        """Risk score should return score, level, and recommendation."""
        result = await mcp.call("get_risk_score", customer_id=1)
        assert isinstance(result, dict)
        assert "risk_score" in result
        assert "level" in result
        assert result["level"] in ("LOW", "MEDIUM", "HIGH")

    async def test_call_check_fraud(self, mcp):
        """Fraud check should return fraud_flag boolean and confidence."""
        result = await mcp.call("check_fraud", customer_id=1)
        assert isinstance(result, dict)
        assert "fraud_flag" in result
        assert isinstance(result["fraud_flag"], bool)

    async def test_call_get_credit_score(self, mcp):
        """Credit score should be between 300 and 850."""
        result = await mcp.call("get_credit_score", customer_id=1)
        assert isinstance(result, dict)
        assert 300 <= result.get("credit_score", 0) <= 850

    async def test_call_get_trading_portfolio(self, mcp):
        """Portfolio should return a list of holdings."""
        result = await mcp.call("get_trading_portfolio", customer_id=1)
        assert isinstance(result, list)
        if result:
            assert "symbol" in result[0]
            assert "quantity" in result[0]

    async def test_call_get_pnl(self, mcp):
        """PnL should return total_pnl as a number."""
        result = await mcp.call("get_pnl", customer_id=1)
        assert isinstance(result, dict)
        assert "total_pnl" in result

    async def test_call_log_tracks_calls(self, mcp):
        """Every tool call should be recorded in the call log."""
        initial_count = len(mcp.call_log)
        await mcp.call("get_customer", customer_id=1)
        await mcp.call("get_risk_score", customer_id=1)
        assert len(mcp.call_log) == initial_count + 2
        assert mcp.call_log[-2].tool_name == "get_customer"
        assert mcp.call_log[-1].tool_name == "get_risk_score"

    async def test_connection_error_on_bad_url(self):
        """MCPClient should raise MCPConnectionError for unreachable server."""
        with pytest.raises(MCPConnectionError):
            async with MCPClient("http://localhost:99999/sse"):
                pass


# ---------------------------------------------------------------------------
# Permission enforcement via run_tool
# ---------------------------------------------------------------------------
class TestPermissionEnforcement:

    async def test_allowed_call_succeeds(self, mcp):
        """Authorised agent-tool pairs should return data."""
        result = await run_tool(
            mcp, "get_risk_score",
            agent_name="risk_agent",
            customer_id=1,
        )
        assert "risk_score" in result

    async def test_denied_call_returns_error(self, mcp):
        """Unauthorised agent-tool pairs should be blocked."""
        denials = []
        result = await run_tool(
            mcp, "get_risk_score",
            agent_name="customer_agent",
            denial_log=denials,
            customer_id=1,
        )
        assert "error" in result
        assert len(denials) == 1
        assert denials[0]["agent"] == "customer_agent"
        assert denials[0]["tool"] == "get_risk_score"

    async def test_no_agent_name_skips_permission_check(self, mcp):
        """Calls without an agent_name should bypass permission checks."""
        result = await run_tool(mcp, "get_customer", customer_id=1)
        assert "name" in result


# ---------------------------------------------------------------------------
# Full agent execution
# ---------------------------------------------------------------------------
class TestAgentExecution:

    async def test_customer_agent(self, mcp):
        from client.agents.customer_agent import customer_agent
        result = await customer_agent(mcp, "who is customer 1", 1)
        assert "answer" in result
        assert "observations" in result
        assert "steps" in result

    async def test_risk_agent(self, mcp):
        from client.agents.risk_agent import risk_agent
        result = await risk_agent(mcp, "check risk", 1)
        assert "answer" in result
        assert len(result["steps"]) >= 1

    async def test_loan_agent(self, mcp):
        from client.agents.loan_agent import loan_agent
        result = await loan_agent(mcp, "check loans", 1)
        assert "answer" in result

    async def test_trading_agent(self, mcp):
        from client.agents.trading_agent import trading_agent
        result = await trading_agent(mcp, "show portfolio", 1)
        assert "answer" in result