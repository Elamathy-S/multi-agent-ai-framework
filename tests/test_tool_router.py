"""
tests/test_tool_router.py — Unit tests for query → tool routing.

These run without any external service.
"""

import pytest
from client.tool_router import resolve_tool, extract_customer_id


# ---------------------------------------------------------------------------
# resolve_tool — maps natural language to the right MCP tool
# ---------------------------------------------------------------------------
class TestResolveTool:

    @pytest.mark.parametrize("query, expected_tool", [
        ("who is customer 3",              "get_customer"),
        ("show me the profile",            "get_customer"),
        ("check the loan status",          "get_loan_status"),
        ("what is their credit score",     "get_credit_score"),
        ("check the credit rating",          "get_credit_score"),
        ("run a risk assessment",          "get_risk_score"),
        ("check for fraud",               "check_fraud"),
        ("is anything suspicious",         "check_fraud"),
        ("show portfolio holdings",        "get_trading_portfolio"),
        ("what is the pnl",               "get_pnl"),
        ("how much profit",               "get_pnl"),
        ("get market price for AAPL",      "get_market_price"),
        ("stock price",                    "get_market_price"),
        ("full customer analysis",         "full_customer_analysis"),
        ("give me everything on customer", "full_customer_analysis"),
        ("complete overview",              "full_customer_analysis"),
    ])
    def test_routes_to_correct_tool(self, query, expected_tool):
        tool_name, _ = resolve_tool(query)
        assert tool_name == expected_tool

    def test_unknown_query_defaults_to_customer(self):
        tool_name, params = resolve_tool("asdfghjkl random gibberish")
        assert tool_name == "get_customer"
        assert "customer_id" in params

    def test_returns_correct_param_names(self):
        _, params = resolve_tool("market price AAPL")
        assert "symbol" in params

        _, params = resolve_tool("who is customer 5")
        assert "customer_id" in params

    def test_case_insensitive(self):
        tool, _ = resolve_tool("FRAUD CHECK")
        assert tool == "check_fraud"

        tool, _ = resolve_tool("Portfolio Holdings")
        assert tool == "get_trading_portfolio"


# ---------------------------------------------------------------------------
# extract_customer_id — parses customer IDs from natural language
# ---------------------------------------------------------------------------
class TestExtractCustomerId:

    @pytest.mark.parametrize("message, expected_id", [
        ("who is customer 3",      3),
        ("check customer id 42",   42),
        ("customer #7",            7),
        ("lookup cust 12",         12),
        ("data for 5",             5),
        ("id: 99",                 99),
        ("customer number 15",     15),
    ])
    def test_extracts_id(self, message, expected_id):
        assert extract_customer_id(message, fallback=1) == expected_id

    def test_returns_fallback_when_no_id(self):
        assert extract_customer_id("hello world", fallback=1) == 1
        assert extract_customer_id("no numbers here", fallback=42) == 42

    def test_picks_first_plausible_id(self):
        # "customer 3" pattern should match before bare "5"
        result = extract_customer_id("customer 3 has 5 loans", fallback=1)
        assert result == 3