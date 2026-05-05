"""
client/agents/orchestrator.py — Multi-Agent Orchestrator.

The orchestrator:
1. Reads the user query
2. Decides which specialist agents to call (can call multiple)
3. Runs them 
4. Collects all results
5. Synthesises a final answer from all agent outputs

Each specialist agent has its own ReAct loop and tool permissions.
This is genuine multi-agent collaboration.
"""

import json
from client.llm.llm_engine import safe_json_llm
from client.agents.customer_agent import customer_agent
from client.agents.loan_agent     import loan_agent
from client.agents.risk_agent     import risk_agent
from client.agents.trading_agent  import trading_agent

# ---------------------------------------------------------------------------
# Agent registry — what each agent is responsible for
# ---------------------------------------------------------------------------
AGENTS = {
    "customer": {
        "fn":          customer_agent,
        "description": "Customer identity, profile, account details",
        "icon":        "👤",
    },
    "loan": {
        "fn":          loan_agent,
        "description": "Loans, credit scores, approval decisions",
        "icon":        "🏦",
    },
    "risk": {
        "fn":          risk_agent,
        "description": "Risk scoring, fraud detection",
        "icon":        "⚠️",
    },
    "trading": {
        "fn":          trading_agent,
        "description": "Portfolio holdings, PnL, market prices",
        "icon":        "📈",
    },
}

# ---------------------------------------------------------------------------
# Step 1 — Orchestrator decides which agents to call
# ---------------------------------------------------------------------------
PLAN_SYSTEM = (
    "You are the Orchestrator of a multi-agent finance system. "
    "Decide which specialist agents to call to answer the user's question. "
    "You can call one or several agents. "
    "For broad questions like 'full analysis' or 'is this customer safe', call all agents. "
    "For specific questions, call only the relevant agents. "
    'Reply with JSON only: {"agents": ["agent1", "agent2", ...], "reason": "why"} '
    "Available agents: customer, loan, risk, trading"
)


def plan_agents(query: str) -> list[str]:
    """
    Select agents for a query.
    Uses keyword matching as primary router (fast, reliable with phi3).
    Falls back to LLM only for ambiguous queries with no keyword matches.
    """
    # Keyword routing first — much faster and more reliable than phi3
    keyword_result = _keyword_plan(query)

    # If keywords gave a clear answer, use it
    if keyword_result and keyword_result != ["customer"]:
        return keyword_result

    # Ambiguous query — try LLM
    result = safe_json_llm(PLAN_SYSTEM, f'User question: "{query}"')
    if "error" not in result:
        agents = result.get("agents", [])
        valid  = [a for a in agents if a in AGENTS]
        if valid:
            return valid

    return keyword_result


def _keyword_plan(query: str) -> list[str]:
    """Keyword-based agent selection — fast and reliable."""
    q      = query.lower()
    agents = []

    # Full analysis — all agents
    if any(k in q for k in ["full", "complete", "everything", "all", "overview",
                              "analysis", "summary", "report"]):
        return list(AGENTS.keys())

    # Customer agent
    if any(k in q for k in ["customer", "profile", "who", "name", "email",
                              "identity"]):
        agents.append("customer")

    # Loan agent
    if any(k in q for k in ["loan", "credit", "borrow", "approve", "approval",
                              "interest", "debt", "repay", "mortgage"]):
        agents.append("loan")

    # Risk agent — fraud keywords get risk agent, NOT customer
    if any(k in q for k in ["risk", "fraud", "suspicious", "safe", "scam",
                              "flag", "threat", "danger", "unusual", "check fraud",
                              "fraud check", "detect"]):
        agents.append("risk")

    # Trading agent
    if any(k in q for k in ["portfolio", "trade", "pnl", "profit", "loss",
                              "stock", "holding", "position", "investment",
                              "market", "price", "return", "gain"]):
        agents.append("trading")

    return agents if agents else ["customer"]


# ---------------------------------------------------------------------------
# Step 2 — Run each agent and collect results
# ---------------------------------------------------------------------------
def run_agents(agent_names: list[str], query: str, customer_id: int) -> dict:
    """
    Run each specialist agent and collect their results.
    Each agent runs its own ReAct loop independently.
    Returns: {agent_name: {answer, observations, steps}}
    """
    results = {}
    for name in agent_names:
        agent_fn = AGENTS[name]["fn"]
        try:
            results[name] = agent_fn(query, customer_id)
        except Exception as e:
            results[name] = {
                "answer":       f"Agent error: {e}",
                "observations": {},
                "steps":        [],
            }
    return results


# ---------------------------------------------------------------------------
# Step 3 — Synthesise all agent results into a final answer
# ---------------------------------------------------------------------------
def synthesise(query: str, agent_results: dict) -> str:
    """
    Build a structured, readable final answer from all agent outputs.
    Each section has a clear header and concise content.
    """
    sections = []

    customer_res = agent_results.get("customer", {})
    loan_res     = agent_results.get("loan", {})
    risk_res     = agent_results.get("risk", {})
    trading_res  = agent_results.get("trading", {})

    # ── Customer section ──────────────────────────────────────────────────
    cust_obs = customer_res.get("observations", {})
    profile  = cust_obs.get("get_customer_profile", {})
    if profile and "name" in profile:
        sections.append(
            f"👤 CUSTOMER\n"
            f"  Name:    {profile.get('name', '?')}\n"
            f"  Email:   {profile.get('email', '?')}\n"
            f"  Account: since {profile.get('created_at', '?')}"
        )

    # ── Loan / Credit section ─────────────────────────────────────────────
    loan_obs = loan_res.get("observations", {})
    credit   = loan_obs.get("credit_score_tool", {})
    loans    = loan_obs.get("check_loan_status", [])

    if credit or "loan" in agent_results:
        loan_lines = ["🏦 CREDIT & LOANS"]
        if credit:
            score    = credit.get("credit_score", "?")
            rating   = credit.get("rating", "?")
            likely   = credit.get("loan_approval_likelihood", "")
            loan_lines.append(f"  Credit score:  {score} ({rating})")
            if likely and likely != "?":
                loan_lines.append(f"  Loan approval: {likely}")
        if isinstance(loans, list) and loans:
            total    = sum(float(l.get("amount", 0)) for l in loans)
            statuses = list(set(l.get("status", "?") for l in loans))
            loan_lines.append(f"  Active loans:  {len(loans)} totalling ${total:,.2f} ({', '.join(statuses)})")
        else:
            loan_lines.append(f"  Active loans:  None on record")
        sections.append("\n".join(loan_lines))

    # ── Risk section ──────────────────────────────────────────────────────
    risk_obs = risk_res.get("observations", {})
    risk_d   = risk_obs.get("risk_score_tool", {})
    fraud_d  = risk_obs.get("fraud_check_tool", {})

    if risk_d or fraud_d:
        risk_lines = ["⚠️  RISK & FRAUD"]
        if risk_d:
            score   = risk_d.get("risk_score", "?")
            level   = risk_d.get("level", "?")
            rec     = risk_d.get("recommendation", "")
            factors = risk_d.get("key_risk_factors", [])
            risk_lines.append(f"  Risk score:    {score}/100 ({level})")
            if factors:
                risk_lines.append(f"  Key factors:   {factors[0]}")
                if len(factors) > 1:
                    risk_lines.append(f"                 {factors[1]}")
            if rec:
                risk_lines.append(f"  Action:        {rec[:120]}")
        if fraud_d:
            flag  = "🔴 FLAGGED" if fraud_d.get("fraud_flag") else "🟢 Clear"
            conf  = fraud_d.get("confidence", "")
            # Keep fraud reason short — first sentence only
            reason = fraud_d.get("reason", "")
            reason = reason.split(".")[0] + "." if reason else ""
            conf_str = f" ({conf} confidence)" if conf else ""
            risk_lines.append(f"  Fraud status:  {flag}{conf_str}")
            if reason:
                risk_lines.append(f"  Reason:        {reason[:100]}")
        sections.append("\n".join(risk_lines))

    # ── Trading section ───────────────────────────────────────────────────
    trading_obs = trading_res.get("observations", {})
    portfolio   = trading_obs.get("get_portfolio", [])
    pnl         = trading_obs.get("calculate_pnl", {})

    if isinstance(portfolio, list) and portfolio or pnl:
        trading_lines = ["📈 PORTFOLIO"]
        if isinstance(portfolio, list) and portfolio:
            symbols = [p.get("symbol", "?") for p in portfolio]
            trading_lines.append(f"  Holdings:      {len(portfolio)} position(s) — {', '.join(symbols)}")
            for p in portfolio[:3]:
                qty   = p.get("quantity", 0)
                sym   = p.get("symbol", "?")
                price = p.get("avg_price", 0)
                trading_lines.append(f"                 {sym}: {qty} shares @ ${float(price):,.2f}")
        if pnl and "total_pnl" in pnl:
            total     = float(pnl["total_pnl"])
            direction = "profit 🟢" if total >= 0 else "loss 🔴"
            trading_lines.append(f"  Unrealised:    ${abs(total):,.2f} {direction}")
        sections.append("\n".join(trading_lines))

    if not sections:
        return "Analysis complete — no data found."

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def orchestrator(query: str, customer_id: int = 1) -> dict:
    """
    Full multi-agent orchestration:
    1. Plan which agents to call
    2. Run each agent (each has its own ReAct loop + permission checks)
    3. Synthesise results into a final answer
    4. Log the full session to agent_logs table
    """
    import time
    from server.models.agent_log import AgentLog
    from server.db import Base, engine
    # Ensure agent_logs table exists
    Base.metadata.create_all(bind=engine)

    session_start = time.time()
    agent_names   = plan_agents(query)
    agent_results = run_agents(agent_names, query, customer_id)
    final_answer  = synthesise(query, agent_results)

    total_tools = sum(len(r.get("steps", [])) for r in agent_results.values())
    total_latency = (time.time() - session_start) * 1000

    # Collect RAG policies retrieved per agent
    rag_retrieved = {}
    for name, res in agent_results.items():
        policies = []
        for step in res.get("steps", []):
            if "rag_policies" in step:
                policies.extend(step["rag_policies"])
        rag_retrieved[name] = policies

    # Collect permission denials from all agents
    all_denials = []
    for name, res in agent_results.items():
        all_denials.extend(res.get("denials", []))

    # Log the full session
    try:
        from server.logger_agent import log_agent_session, new_session_id
        sid = new_session_id()
        log_agent_session(
            session_id         = sid,
            user_query         = query,
            customer_id        = customer_id,
            agents_planned     = agent_names,
            agent_results      = agent_results,
            rag_retrieved      = rag_retrieved,
            permission_denials = all_denials,
            final_answer       = final_answer,
            total_latency_ms   = total_latency,
        )
    except Exception as e:
        print(f"⚠️  Session logging failed (non-fatal): {e}")
        sid = "unknown"

    return {
        "answer":        final_answer,
        "agents_called": agent_names,
        "agent_results": agent_results,
        "total_tools":   total_tools,
        "session_id":    sid,
        "denials":       all_denials,
    }


# ---------------------------------------------------------------------------
# Legacy helpers (used by /agent/* endpoints and stream)
# ---------------------------------------------------------------------------
def route_agent(query: str) -> str:
    agents = plan_agents(query)
    return agents[0] if agents else "customer"


def _keyword_fallback(query: str) -> str:
    return _keyword_plan(query)[0]


def react_agent(query: str, customer_id: int = 1) -> dict:
    """Alias so existing /agent/react endpoint still works."""
    result = orchestrator(query, customer_id)
    steps  = []
    for name, r in result.get("agent_results", {}).items():
        for s in r.get("steps", []):
            s["agent"] = name
            steps.append(s)
    return {
        "answer":     result["answer"],
        "steps":      steps,
        "tool_calls": result["total_tools"],
    }


def build_react_prompt(query, customer_id, history):
    """Legacy stub."""
    return ""


def execute_tool(tool_name, args):
    """Legacy stub."""
    from server.tools.tool_registry import registry
    tool = registry.get(tool_name)
    return tool["function"](**args) if tool else {"error": "not found"}


def _summarise_observations(query, obs):
    return synthesise(query, {"customer": {"observations": obs, "steps": []}})


def build_rich_response_from_steps(steps):
    return ""


AVAILABLE_TOOLS = {
    "get_customer":          "Fetch customer profile",
    "get_loan_status":       "Get loan records",
    "get_credit_score":      "Calculate credit score",
    "get_risk_score":        "Run risk assessment",
    "check_fraud":           "Run fraud detection",
    "get_trading_portfolio": "Get portfolio holdings",
    "get_pnl":               "Calculate PnL",
    "get_market_price":      "Get market price",
    "full_customer_analysis":"Run all analyses",
}