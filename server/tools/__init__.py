# server/tools/__init__.py
# Central re-export for all tool functions and the registry.
# Use `from server.tools import get_customer_profile` instead of
# digging into individual modules.

from server.tools.tool_registry import registry, init_tools
from server.tools.customer_tools import get_customer_profile, get_account_balance
from server.tools.loan_tools import check_loan_status, credit_score_tool
from server.tools.risk_tools import risk_score_tool, fraud_check_tool
from server.tools.trading_tools import get_portfolio, calculate_pnl, execute_trade

__all__ = [
    "registry",
    "init_tools",
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