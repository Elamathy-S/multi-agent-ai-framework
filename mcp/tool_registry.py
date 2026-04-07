from mcp.customer_tools import get_customer_profile
from mcp.trading_tools import get_portfolio, calculate_pnl
from mcp.loan_tools import check_loan_status, credit_score_tool
from mcp.risk_tools import risk_score_tool, fraud_check_tool

TOOLS = {
    "get_customer_profile": {
        "function": get_customer_profile,
        "description": "Retrieve customer profile information",
        "agent": "customer_agent",
        "parameters": {
            "customer_id": "int"
        }
    },

    "get_portfolio": {
        "function": get_portfolio,
        "description": "Get portfolio holdings for a customer",
        "agent": "trading_agent",
        "parameters": {
            "customer_id": "int"
        }
    },

    "calculate_pnl": {
        "function": calculate_pnl,
        "description": "Calculate profit and loss for portfolio",
        "agent": "trading_agent",
        "parameters": {
            "customer_id": "int"
        }
    },

    "check_loan_status": {
        "function": check_loan_status,
        "description": "Fetch loan status for customer",
        "agent": "loan_agent",
        "parameters": {
            "customer_id": "int"
        }
    },

    "credit_score_tool": {
        "function": credit_score_tool,
        "description": "Compute credit score for loan eligibility",
        "agent": "loan_agent",
        "parameters": {
            "customer_id": "int"
        }
    },

    "risk_score_tool": {
        "function": risk_score_tool,
        "description": "Compute risk score for a customer",
        "agent": "risk_agent",
        "parameters": {
            "customer_id": "int"
        }
    },

    "fraud_check_tool": {
        "function": fraud_check_tool,
        "description": "Detect suspicious transactions or fraud patterns",
        "agent": "risk_agent",
        "parameters": {
            "customer_id": "int"
        }
    }
}