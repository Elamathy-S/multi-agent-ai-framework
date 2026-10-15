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

from client.llm import safe_json_llm
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

    Works in two layers:
    1. Per-tool formatters (TOOL_FORMATTERS) handle known tools nicely.
    2. A generic fallback auto-formats any unknown tool result as key-value
       pairs, so adding a new tool never breaks the synthesiser.

    Each agent's observations are processed in the order they appear.
    """
    sections = []

    # Process agents in a consistent display order
    for agent_name in ("customer", "loan", "risk", "trading"):
        agent_res = agent_results.get(agent_name, {})
        obs = agent_res.get("observations", {})
        if not obs:
            continue

        icon = AGENTS.get(agent_name, {}).get("icon", "📌")
        title = AGENTS.get(agent_name, {}).get("description", agent_name.title())
        lines = [f"{icon} {title.upper()}"]

        for tool_name, data in obs.items():
            if isinstance(data, dict) and "error" in data:
                lines.append(f"  ⚠ {tool_name}: {data['error']}")
                continue

            formatter = TOOL_FORMATTERS.get(tool_name, _format_generic)
            tool_lines = formatter(data)
            lines.extend(f"  {line}" for line in tool_lines)

        if len(lines) > 1:  # more than just the header
            sections.append("\n".join(lines))

    if not sections:
        return "Analysis complete — no data found."

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Per-tool formatters — each returns a list of display lines.
# If a key is missing the .get() returns a safe default, so changing
# the tool's return shape never crashes — it just shows "?" for that field.
# ---------------------------------------------------------------------------

def _fmt_customer(d: dict) -> list[str]:
    return [
        f"Name:    {d.get('name', '?')}",
        f"Email:   {d.get('email', '?')}",
        f"Account: since {d.get('created_at', '?')}",
    ]


def _fmt_credit_score(d: dict) -> list[str]:
    lines = [f"Credit score:  {d.get('credit_score', '?')} ({d.get('rating', '?')})"]
    likely = d.get("loan_approval_likelihood", "")
    if likely:
        lines.append(f"Loan approval: {likely}")
    factors = d.get("factors", [])
    if factors:
        lines.append(f"Factors:       {', '.join(factors[:3])}")
    return lines


def _fmt_loan_status(d) -> list[str]:
    if not isinstance(d, list) or not d:
        return ["Active loans:  None on record"]
    total = sum(float(l.get("amount", 0)) for l in d)
    statuses = sorted(set(l.get("status", "?") for l in d))
    return [
        f"Active loans:  {len(d)} totalling ${total:,.2f} ({', '.join(statuses)})",
    ]


def _fmt_risk_score(d: dict) -> list[str]:
    lines = [f"Risk score:    {d.get('risk_score', '?')}/100 ({d.get('level', '?')})"]
    factors = d.get("key_risk_factors", [])
    if factors:
        lines.append(f"Key factors:   {'; '.join(factors[:3])}")
    rec = d.get("recommendation", "")
    if rec:
        lines.append(f"Action:        {rec[:120]}")
    return lines


def _fmt_fraud(d: dict) -> list[str]:
    flag = "🔴 FLAGGED" if d.get("fraud_flag") else "🟢 Clear"
    conf = d.get("confidence", "")
    conf_str = f" ({conf} confidence)" if conf else ""
    lines = [f"Fraud status:  {flag}{conf_str}"]
    reason = d.get("reason", "")
    if reason:
        lines.append(f"Reason:        {reason.split('.')[0]}.")
    return lines


def _fmt_portfolio(d) -> list[str]:
    if not isinstance(d, list) or not d:
        return ["No holdings found"]
    symbols = [p.get("symbol", "?") for p in d]
    lines = [f"Holdings:      {len(d)} position(s) — {', '.join(symbols)}"]
    for p in d[:5]:
        sym = p.get("symbol", "?")
        qty = p.get("quantity", 0)
        price = p.get("avg_price", 0)
        lines.append(f"               {sym}: {qty} shares @ ${float(price):,.2f}")
    return lines


def _fmt_pnl(d: dict) -> list[str]:
    total = d.get("total_pnl")
    if total is None:
        return ["PnL data unavailable"]
    total_f = float(total)
    direction = "profit 🟢" if total_f >= 0 else "loss 🔴"
    return [f"Unrealised:    ${abs(total_f):,.2f} {direction}"]


def _fmt_market_price(d: dict) -> list[str]:
    return [f"{d.get('symbol', '?')}: ${d.get('price', '?')}"]


def _fmt_list_customers(d) -> list[str]:
    if not isinstance(d, list):
        return ["No customer data"]
    return [f"Found {len(d)} customer(s)"] + [
        f"  #{c.get('id','?')} {c.get('name','?')} ({c.get('email','')})"
        for c in d[:5]
    ]


def _format_generic(d) -> list[str]:
    """
    Fallback formatter for any tool not in TOOL_FORMATTERS.
    Auto-formats dict keys or list items — so adding a new tool
    to mcp_server.py never breaks the synthesiser.
    """
    if isinstance(d, list):
        return [f"{len(d)} record(s) returned"]
    if isinstance(d, dict):
        lines = []
        for k, v in list(d.items())[:8]:
            if isinstance(v, (list, dict)):
                v = json.dumps(v, default=str)[:80]
            lines.append(f"{k}: {v}")
        return lines
    return [str(d)[:200]]


# Tool name → formatter function
TOOL_FORMATTERS = {
    "get_customer":           _fmt_customer,
    "list_customers":         _fmt_list_customers,
    "get_credit_score":       _fmt_credit_score,
    "get_loan_status":        _fmt_loan_status,
    "get_risk_score":         _fmt_risk_score,
    "check_fraud":            _fmt_fraud,
    "get_trading_portfolio":  _fmt_portfolio,
    "get_pnl":                _fmt_pnl,
    "get_market_price":       _fmt_market_price,
}


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