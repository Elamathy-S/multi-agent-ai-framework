"""
client/agents/specs.py — The specialist agents.

Each specialist is data: a name, an RBAC role, and domain guidance. The tools
an agent can use are NOT listed here; they come from its RBAC role, so
changing a permission changes what the agent can do without touching code.
"""

from client.agents.loop import AgentSpec

SPECIALISTS: dict[str, AgentSpec] = {
    "customer": AgentSpec(
        name="customer", role="customer_agent", icon="👤",
        description="Who the customer is: profile, contact details, account age.",
        instructions="You look up customer identity and profile information.",
    ),
    "loan": AgentSpec(
        name="loan", role="loan_agent", icon="🏦",
        description="Loans, credit score and loan approval likelihood, judged against loan policy.",
        instructions=(
            "You assess a customer's loans and creditworthiness. Combine existing loan records "
            "with the credit score, and use loan policy to say whether review or escalation applies."
        ),
    ),
    "risk": AgentSpec(
        name="risk", role="risk_agent", icon="⚠️",
        description="Financial risk score and fraud screening, with the actions policy requires.",
        instructions=(
            "You assess financial risk and fraud. Start with the risk score. Run the fraud check when "
            "the question concerns fraud or when the risk score or its components give a reason to. "
            "Then retrieve the policy for the resulting risk band and state the required actions."
        ),
    ),
    "trading": AgentSpec(
        name="trading", role="trading_agent", icon="📈",
        description="Portfolio holdings, unrealised profit and loss, market prices, portfolio risk limits.",
        instructions=(
            "You analyse a customer's investment portfolio and profit and loss. Compare what you find "
            "with the portfolio risk limits in policy."
        ),
    ),
}
