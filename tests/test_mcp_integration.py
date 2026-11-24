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
        """Risk score returns a score, a policy band and the component breakdown."""
        result = await mcp.call("get_risk_score", customer_id=1)
        assert isinstance(result, dict)
        assert "risk_score" in result
        assert "level" in result
        assert result["level"] in ("LOW", "LOW-MEDIUM", "MEDIUM", "HIGH", "CRITICAL")

    async def test_call_check_fraud(self, mcp):
        """Fraud check returns a boolean flag and the matched rule patterns."""
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
# RAG as a tool, and a full agent run over the real MCP server
# ---------------------------------------------------------------------------
class TestPolicySearchTool:

    async def test_search_policies_returns_cited_passages(self, mcp):
        hits = await mcp.call("search_policies", query="actions for high risk customers", category="risk", n=2)
        assert hits and {"id", "title", "score", "text"} <= set(hits[0])
        assert hits[0]["id"].startswith("risk_policy")


class TestAgentOverRealMCP:

    async def test_risk_specialist_end_to_end(self, mcp):
        from client.agents.loop import run_agent
        from client.agents.specs import SPECIALISTS
        from llm.scripted import ScriptedLLM, say, tool_call

        llm = ScriptedLLM([tool_call("get_risk_score"),
                           tool_call("search_policies", call_id="c2", query="risk band actions", category="risk"),
                           say("done")])
        res = await run_agent(SPECIALISTS["risk"], llm, mcp, "assess", 1)
        assert res.status == "ok"
        assert "risk_score" in res.observations["get_risk_score"]
        assert res.policies

    async def test_rbac_blocks_out_of_role_tool_on_real_server(self, mcp):
        from client.agents.loop import run_agent
        from client.agents.specs import SPECIALISTS
        from llm.scripted import ScriptedLLM, say, tool_call

        llm = ScriptedLLM([tool_call("get_customer"), say("blocked")])
        res = await run_agent(SPECIALISTS["risk"], llm, mcp, "who?", 1)
        assert res.denials and "get_customer" not in res.observations
