"""
evals/eval_dataset.py — Evaluation dataset for the multi-agent framework.

Each entry defines:
  - A query (natural language input)
  - Expected behaviour (which agents, tools, data keys should appear)
  - Category (routing, agent_behaviour, rag, end_to_end)

These are not unit tests — they evaluate AI decision quality.
"""

# ---------------------------------------------------------------------------
# 1. ROUTING EVALS — does the orchestrator pick the right agents?
# ---------------------------------------------------------------------------
ROUTING_EVALS = [
    {
        "id": "route_01",
        "query": "who is customer 3",
        "expected_agents": ["customer"],
        "not_expected_agents": ["trading", "risk"],
        "description": "Simple identity query should only call customer agent",
    },
    {
        "id": "route_02",
        "query": "what is the credit score and loan status",
        "expected_agents": ["loan"],
        "description": "Credit + loan query should route to loan agent",
    },
    {
        "id": "route_03",
        "query": "is this customer risky or fraudulent",
        "expected_agents": ["risk"],
        "description": "Risk/fraud query should route to risk agent",
    },
    {
        "id": "route_04",
        "query": "show me the portfolio and profit loss",
        "expected_agents": ["trading"],
        "description": "Portfolio/PnL query should route to trading agent",
    },
    {
        "id": "route_05",
        "query": "give me a full financial analysis of customer 1",
        "expected_agents": ["customer", "loan", "risk", "trading"],
        "description": "Full analysis should activate all four agents",
    },
    {
        "id": "route_06",
        "query": "check risk and credit score",
        "expected_agents": ["risk", "loan"],
        "description": "Multi-domain query should activate both relevant agents",
    },
    {
        "id": "route_07",
        "query": "hello how are you",
        "expected_agents": ["customer"],
        "description": "Ambiguous query should default to customer agent",
    },
    {
        "id": "route_08",
        "query": "is there any suspicious activity on this account",
        "expected_agents": ["risk"],
        "description": "Suspicious activity implies fraud detection",
    },
]

# ---------------------------------------------------------------------------
# 2. TOOL SELECTION EVALS — do agents call the right MCP tools?
# ---------------------------------------------------------------------------
TOOL_SELECTION_EVALS = [
    {
        "id": "tool_01",
        "query": "who is customer 1",
        "agent": "customer",
        "expected_tools": ["get_customer"],
        "not_expected_tools": ["list_customers"],
        "description": "Profile query should call get_customer, not list_customers",
    },
    {
        "id": "tool_02",
        "query": "check loan status",
        "agent": "loan",
        "expected_tools": ["get_loan_status"],
        "description": "Loan query should call get_loan_status",
    },
    {
        "id": "tool_03",
        "query": "what is the credit score",
        "agent": "loan",
        "expected_tools": ["get_credit_score"],
        "description": "Credit query should call get_credit_score",
    },
    {
        "id": "tool_04",
        "query": "full loan review",
        "agent": "loan",
        "expected_tools": ["get_loan_status", "get_credit_score"],
        "description": "Full loan review should call both loan tools",
    },
    {
        "id": "tool_05",
        "query": "check for fraud",
        "agent": "risk",
        "expected_tools": ["check_fraud"],
        "description": "Fraud query should call check_fraud",
    },
    {
        "id": "tool_06",
        "query": "risk assessment",
        "agent": "risk",
        "expected_tools": ["get_risk_score"],
        "description": "Risk query should call get_risk_score",
    },
    {
        "id": "tool_07",
        "query": "show portfolio",
        "agent": "trading",
        "expected_tools": ["get_trading_portfolio"],
        "description": "Portfolio query should call get_trading_portfolio",
    },
    {
        "id": "tool_08",
        "query": "how much profit or loss",
        "agent": "trading",
        "expected_tools": ["get_pnl"],
        "description": "PnL query should call get_pnl",
    },
]

# ---------------------------------------------------------------------------
# 3. RAG RETRIEVAL EVALS — are the right policies retrieved?
# ---------------------------------------------------------------------------
RAG_EVALS = [
    {
        "id": "rag_01",
        "query": "should we approve this loan",
        "category": "loan",
        "expected_titles": ["Standard Loan Approval Criteria"],
        "min_score": 0.15,
        "description": "Loan approval query should retrieve loan approval policy",
    },
    {
        "id": "rag_02",
        "query": "high risk customer what to do",
        "category": "risk",
        "expected_titles": ["High Risk Customer Actions"],
        "min_score": 0.2,
        "description": "High risk query should retrieve risk action policy",
    },
    {
        "id": "rag_03",
        "query": "suspicious transactions fraud",
        "category": "fraud",
        "expected_titles": ["Fraud Detection Triggers and Response"],
        "min_score": 0.1,
        "description": "Fraud query should retrieve fraud detection policy",
    },
    {
        "id": "rag_04",
        "query": "portfolio concentration limits",
        "category": "trading",
        "expected_titles": ["Portfolio Risk Limits"],
        "min_score": 0.15,
        "description": "Portfolio limits query should retrieve trading policy",
    },
    {
        "id": "rag_05",
        "query": "interest rate for loan",
        "category": "loan",
        "expected_titles": ["Loan Interest Rate Schedule"],
        "min_score": 0.1,
        "description": "Interest rate query should retrieve rate schedule",
    },
    {
        "id": "rag_06",
        "query": "customer risk classification levels",
        "category": "risk",
        "expected_titles": ["Customer Risk Classification Guidelines"],
        "min_score": 0.1,
        "description": "Risk classification query should retrieve risk guidelines",
    },
]

# ---------------------------------------------------------------------------
# 4. PERMISSION ENFORCEMENT EVALS — are cross-agent calls blocked?
# ---------------------------------------------------------------------------
PERMISSION_EVALS = [
    {
        "id": "perm_01",
        "agent": "risk_agent",
        "tool": "get_customer",
        "should_allow": False,
        "description": "Risk agent must not access customer profiles",
    },
    {
        "id": "perm_02",
        "agent": "customer_agent",
        "tool": "check_fraud",
        "should_allow": False,
        "description": "Customer agent must not run fraud checks",
    },
    {
        "id": "perm_03",
        "agent": "trading_agent",
        "tool": "get_credit_score",
        "should_allow": False,
        "description": "Trading agent must not access credit scores",
    },
    {
        "id": "perm_04",
        "agent": "loan_agent",
        "tool": "get_trading_portfolio",
        "should_allow": False,
        "description": "Loan agent must not access trading data",
    },
    {
        "id": "perm_05",
        "agent": "risk_agent",
        "tool": "get_risk_score",
        "should_allow": True,
        "description": "Risk agent should access its own tools",
    },
]

# ---------------------------------------------------------------------------
# 5. END-TO-END EVALS — does the final answer contain the right data?
# ---------------------------------------------------------------------------
END_TO_END_EVALS = [
    {
        "id": "e2e_01",
        "query": "who is customer 1",
        "customer_id": 1,
        "answer_must_contain": ["name", "email"],
        "answer_must_not_contain": ["risk_score", "fraud"],
        "description": "Customer query should return profile data only",
    },
    {
        "id": "e2e_02",
        "query": "check risk for customer 1",
        "customer_id": 1,
        "answer_must_contain": ["risk", "score"],
        "description": "Risk query answer should mention risk and score",
    },
    {
        "id": "e2e_03",
        "query": "full analysis of customer 1",
        "customer_id": 1,
        "answer_must_contain": ["customer", "credit", "risk", "portfolio"],
        "min_agents": 4,
        "description": "Full analysis should cover all domains",
    },
]