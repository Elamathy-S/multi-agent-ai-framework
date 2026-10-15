"""
tests/test_permissions.py — Unit tests for the agent → tool permission system.

Verifies that each agent can only call the tools it's authorised for,
and that cross-agent tool access is blocked.
"""

import pytest
from client.security.permission_checker import check_permission
from client.security.permissions import ROLE_PERMISSIONS


# ---------------------------------------------------------------------------
# Allowed calls — each agent can call its own tools
# ---------------------------------------------------------------------------
class TestAllowedPermissions:

    @pytest.mark.parametrize("agent, tool", [
        ("customer_agent", "get_customer"),
        ("customer_agent", "list_customers"),
        ("loan_agent",     "get_loan_status"),
        ("loan_agent",     "get_credit_score"),
        ("risk_agent",     "get_risk_score"),
        ("risk_agent",     "check_fraud"),
        ("trading_agent",  "get_trading_portfolio"),
        ("trading_agent",  "get_pnl"),
        ("trading_agent",  "get_market_price"),
    ])
    def test_agent_can_call_own_tools(self, agent, tool):
        assert check_permission(agent, tool) is True


# ---------------------------------------------------------------------------
# Denied calls — agents cannot call other agents' tools
# ---------------------------------------------------------------------------
class TestDeniedPermissions:

    @pytest.mark.parametrize("agent, tool", [
        ("customer_agent", "get_risk_score"),
        ("customer_agent", "check_fraud"),
        ("customer_agent", "get_pnl"),
        ("loan_agent",     "get_customer"),
        ("loan_agent",     "check_fraud"),
        ("risk_agent",     "get_loan_status"),
        ("risk_agent",     "get_trading_portfolio"),
        ("trading_agent",  "get_customer"),
        ("trading_agent",  "get_credit_score"),
    ])
    def test_agent_cannot_call_other_tools(self, agent, tool):
        assert check_permission(agent, tool) is False

    def test_unknown_agent_denied(self):
        assert check_permission("hacker_agent", "get_customer") is False

    def test_unknown_tool_denied(self):
        assert check_permission("risk_agent", "delete_database") is False


# ---------------------------------------------------------------------------
# Permission matrix completeness
# ---------------------------------------------------------------------------
class TestPermissionMatrix:

    def test_all_agents_have_permissions(self):
        expected_agents = {"customer_agent", "loan_agent", "risk_agent", "trading_agent"}
        assert set(ROLE_PERMISSIONS.keys()) == expected_agents

    def test_no_empty_permission_sets(self):
        for agent, tools in ROLE_PERMISSIONS.items():
            assert len(tools) >= 1, f"{agent} has no permitted tools"

    def test_all_permissions_are_strings(self):
        for agent, tools in ROLE_PERMISSIONS.items():
            for tool in tools:
                assert isinstance(tool, str), f"{agent} has non-string permission: {tool}"