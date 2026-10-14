"""
client/agents/orchestrator.py — Async Multi-Agent Orchestrator (MCP-powered).

The orchestrator:
1. Opens a single MCP session (one SSE connection to the MCP server)
2. Decides which specialist agents to call (can call multiple)
3. Runs them concurrently via asyncio.gather — each agent calls its
   MCP tools through the shared session
4. Collects all results
5. Synthesises a final answer from all agent outputs

Every tool call in the system now goes through the MCP protocol.
"""

import asyncio
import json
import time

from client.llm.llm_engine import safe_json_llm
from client.mcp.client import MCPClient, MCPConnectionError
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

    if any(k in q for k in ["full", "complete", "everything", "all", "overview",
                              "analysis", "summary", "report"]):
        return list(AGENTS.keys())

    if any(k in q for k in ["customer", "profile", "who", "name", "email", "identity"]):
        agents.append("customer")
    if any(k in q for k in ["loan", "credit", "borrow", "approve", "approval",
                              "interest", "debt", "repay", "mortgage"]):
        agents.append("loan")
    if any(k in q for k in ["risk", "fraud", "suspicious", "safe", "scam",
                              "flag", "threat", "danger", "unusual", "detect"]):
        agents.append("risk")
    if any(k in q for k in ["portfolio", "trade", "pnl", "profit", "loss",
                              "stock", "holding", "position", "investment",
                              "market", "price", "return", "gain"]):
        agents.append("trading")

    return agents if agents else ["customer"]


# ---------------------------------------------------------------------------
# Step 2 — Run each agent concurrently via the shared MCP session
# ---------------------------------------------------------------------------
async def run_agents(
    mcp: MCPClient,
    agent_names: list[str],
    query: str,
    customer_id: int,
) -> dict:
    """
    Run each specialist agent concurrently through the shared MCP session.
    Each agent calls its own MCP tools independently.
    Returns: {agent_name: {answer, observations, steps, denials}}
    """

    async def _run_one(name: str) -> tuple[str, dict]:
        agent_fn = AGENTS[name]["fn"]
        try:
            result = await agent_fn(mcp, query, customer_id)
            return name, result
        except Exception as e:
            return name, {
                "answer":       f"Agent error: {e}",
                "observations": {},
                "steps":        [],
                "denials":      [],
            }

    # Run all agents concurrently — they share the MCP session
    # but each calls different tools so there's no conflict
    pairs = await asyncio.gather(*[_run_one(name) for name in agent_names])
    return dict(pairs)


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
    profile  = cust_obs.get("get_customer", {})
    if profile and "name" in profile:
        sections.append(
            f"👤 CUSTOMER\n"
            f"  Name:    {profile.get('name', '?')}\n"
            f"  Email:   {profile.get('email', '?')}\n"
            f"  Account: since {profile.get('created_at', '?')}"
        )

    # ── Loan / Credit section ─────────────────────────────────────────────
    loan_obs = loan_res.get("observations", {})
    credit   = loan_obs.get("get_credit_score", {})
    loans    = loan_obs.get("get_loan_status", [])

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
            loan_lines.append(
                f"  Active loans:  {len(loans)} totalling ${total:,.2f} "
                f"({', '.join(statuses)})"
            )
        else:
            loan_lines.append(f"  Active loans:  None on record")
        sections.append("\n".join(loan_lines))

    # ── Risk section ──────────────────────────────────────────────────────
    risk_obs = risk_res.get("observations", {})
    risk_d   = risk_obs.get("get_risk_score", {})
    fraud_d  = risk_obs.get("check_fraud", {})

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
            reason = fraud_d.get("reason", "")
            reason = reason.split(".")[0] + "." if reason else ""
            conf_str = f" ({conf} confidence)" if conf else ""
            risk_lines.append(f"  Fraud status:  {flag}{conf_str}")
            if reason:
                risk_lines.append(f"  Reason:        {reason[:100]}")
        sections.append("\n".join(risk_lines))

    # ── Trading section ───────────────────────────────────────────────────
    trading_obs = trading_res.get("observations", {})
    portfolio   = trading_obs.get("get_trading_portfolio", [])
    pnl         = trading_obs.get("get_pnl", {})

    if isinstance(portfolio, list) and portfolio or pnl:
        trading_lines = ["📈 PORTFOLIO"]
        if isinstance(portfolio, list) and portfolio:
            symbols = [p.get("symbol", "?") for p in portfolio]
            trading_lines.append(
                f"  Holdings:      {len(portfolio)} position(s) — {', '.join(symbols)}"
            )
            for p in portfolio[:3]:
                qty   = p.get("quantity", 0)
                sym   = p.get("symbol", "?")
                price = p.get("avg_price", 0)
                trading_lines.append(
                    f"                 {sym}: {qty} shares @ ${float(price):,.2f}"
                )
        if pnl and "total_pnl" in pnl:
            total     = float(pnl["total_pnl"])
            direction = "profit 🟢" if total >= 0 else "loss 🔴"
            trading_lines.append(f"  Unrealised:    ${abs(total):,.2f} {direction}")
        sections.append("\n".join(trading_lines))

    if not sections:
        return "Analysis complete — no data found."

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Main entry point — now async, opens one MCP session for the whole run
# ---------------------------------------------------------------------------
async def orchestrator(query: str, customer_id: int = 1) -> dict:
    """
    Full multi-agent orchestration (MCP-powered):
    1. Plan which agents to call
    2. Open a single MCP session
    3. Run each agent concurrently (each calls MCP tools through the session)
    4. Synthesise results into a final answer
    5. Log the full session
    """
    session_start = time.time()
    agent_names   = plan_agents(query)

    # One MCP connection for the entire orchestration run
    async with MCPClient() as mcp:
        agent_results = await run_agents(mcp, agent_names, query, customer_id)

        # The MCP client tracks every tool call made during the session
        mcp_calls = [
            {"tool": r.tool_name, "args": r.arguments, "ok": r.ok}
            for r in mcp.call_log
        ]

    final_answer  = synthesise(query, agent_results)
    total_tools   = sum(len(r.get("steps", [])) for r in agent_results.values())
    total_latency = (time.time() - session_start) * 1000

    # Collect RAG policies per agent
    rag_retrieved = {}
    for name, res in agent_results.items():
        policies = []
        for step in res.get("steps", []):
            if "rag_policies" in step:
                policies.extend(step["rag_policies"])
        rag_retrieved[name] = policies

    # Collect permission denials
    all_denials = []
    for name, res in agent_results.items():
        all_denials.extend(res.get("denials", []))

    # Log the session
    sid = _log_session(
        query, customer_id, agent_names, agent_results,
        rag_retrieved, all_denials, final_answer, total_latency,
    )

    return {
        "answer":        final_answer,
        "agents_called": agent_names,
        "agent_results": agent_results,
        "total_tools":   total_tools,
        "mcp_calls":     mcp_calls,
        "session_id":    sid,
        "denials":       all_denials,
    }


def _log_session(query, customer_id, agent_names, agent_results,
                 rag_retrieved, all_denials, final_answer, total_latency):
    """Log session — non-fatal if it fails."""
    try:
        from server.logger_agent import log_agent_session, new_session_id
        from server.db import Base, engine
        Base.metadata.create_all(bind=engine)
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
        return sid
    except Exception as e:
        print(f"⚠️  Session logging failed (non-fatal): {e}")
        return "unknown"


# ---------------------------------------------------------------------------
# Legacy helpers (kept for backward-compatible endpoints)
# ---------------------------------------------------------------------------
def route_agent(query: str) -> str:
    agents = plan_agents(query)
    return agents[0] if agents else "customer"


async def react_agent(query: str, customer_id: int = 1) -> dict:
    """Alias so existing /agent/react endpoint still works."""
    result = await orchestrator(query, customer_id)
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


AVAILABLE_TOOLS = {
    "get_customer":           "Fetch customer profile",
    "get_loan_status":        "Get loan records",
    "get_credit_score":       "Calculate credit score",
    "get_risk_score":         "Run risk assessment",
    "check_fraud":            "Run fraud detection",
    "get_trading_portfolio":  "Get portfolio holdings",
    "get_pnl":                "Calculate PnL",
    "get_market_price":       "Get market price",
    "full_customer_analysis": "Run all analyses",
}