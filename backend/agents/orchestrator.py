from backend.agents.customer_agent import customer_agent
from backend.agents.loan_agent import loan_agent
from backend.agents.trading_agent import trading_agent
from backend.agents.risk_agent import risk_agent


def route_agent(query: str):

    q = query.lower()

    if any(k in q for k in ["loan", "credit", "approve"]):
        return "loan"

    if any(k in q for k in ["portfolio", "trade", "pnl"]):
        return "trading"

    if any(k in q for k in ["risk", "fraud"]):
        return "risk"

    if any(k in q for k in ["customer", "profile"]):
        return "customer"

    return "unknown"


def orchestrator(query: str, customer_id: int = 1):

    agent_type = route_agent(query)

    if agent_type == "loan":
        return loan_agent(query, customer_id)

    if agent_type == "trading":
        return trading_agent(query, customer_id)

    if agent_type == "risk":
        return risk_agent(query, customer_id)

    if agent_type == "customer":
        return customer_agent(query, customer_id)

    return {
        "message": "No agent found for query",
        "suggestion": "Try: loan, customer, trading, or risk queries"
    }