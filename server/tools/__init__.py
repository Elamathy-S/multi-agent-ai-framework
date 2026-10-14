# server/tools/__init__.py
# Re-exports for tool functions.
# Tools are registered on the MCP server via @mcp.tool() in mcp_server.py.
# These direct imports are only needed by mcp_server.py and health checks.

from server.tools.customer_tools import get_customer_profile, get_account_balance
from server.tools.loan_tools import check_loan_status, credit_score_tool
from server.tools.risk_tools import risk_score_tool, fraud_check_tool
from server.tools.trading_tools import get_portfolio, calculate_pnl, execute_trade

__all__ = [
    "get_customer_profile",
    "get_account_balance",
    "check_loan_status",
    "credit_score_tool",
    "risk_score_tool",
    "fraud_check_tool",
    "get_portfolio",
    "calculate_pnl",
    "execute_trade",
]