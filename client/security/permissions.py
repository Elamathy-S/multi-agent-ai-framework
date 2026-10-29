"""
client/security/permissions.py — RBAC permission interface.

Delegates to the database-backed RBAC service (rbac.py).
This file is the import point for all agent code — agents import
check_permission from here, and the RBAC implementation can be
swapped without touching agent code.
"""

from client.security.rbac import check_permission, seed_default_roles

# Static fallback — kept for reference and for tests that don't need a DB
ROLE_PERMISSIONS = {
    "customer_agent": {"get_customer", "list_customers"},
    "loan_agent":     {"get_loan_status", "get_credit_score"},
    "risk_agent":     {"get_risk_score", "check_fraud"},
    "trading_agent":  {"get_trading_portfolio", "get_pnl", "get_market_price"},
}