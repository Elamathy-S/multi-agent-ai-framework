from backend.tools.customer_tools import get_customer_profile
from backend.tools.loan_tools import check_loan_status, credit_score_tool
from backend.tools.risk_tools import risk_score_tool, fraud_check_tool
from backend.tools.trading_tools import get_portfolio, calculate_pnl

class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, func, agent, description=""):
        self.tools[name] = {
            "function": func,
            "agent": agent,
            "description": description
        }

    def get(self, name):
        return self.tools.get(name)


# GLOBAL INSTANCE (IMPORTANT)
registry = ToolRegistry()


def init_tools():

    registry.register("get_customer_profile", get_customer_profile, "customer_agent")
    registry.register("check_loan_status", check_loan_status, "loan_agent")
    registry.register("credit_score_tool", credit_score_tool, "loan_agent")
    registry.register("risk_score_tool", risk_score_tool, "risk_agent")
    registry.register("fraud_check_tool", fraud_check_tool, "risk_agent")
    registry.register("get_portfolio", get_portfolio, "trading_agent")
    registry.register("calculate_pnl", calculate_pnl, "trading_agent")
