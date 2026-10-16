"""
client/security/permissions.py — Agent-to-tool permission matrix + checker.

Keys are agent names, values are sets of MCP tool names each agent
is authorised to call. Any call not listed here is denied by
check_permission() before the MCP request is made.

Tool names match the MCP server registrations in mcp_server.py.
"""

ROLE_PERMISSIONS = {
    "customer_agent": {
        "get_customer",
        "list_customers",
    },

    "loan_agent": {
        "get_loan_status",
        "get_credit_score",
    },

    "risk_agent": {
        "get_risk_score",
        "check_fraud",
    },

    "trading_agent": {
        "get_trading_portfolio",
        "get_pnl",
        "get_market_price",
    },
}


def check_permission(agent_name: str, tool_name: str) -> bool:
    """Check whether an agent is authorised to call a tool."""
    allowed_tools = ROLE_PERMISSIONS.get(agent_name, set())
    return tool_name in allowed_tools