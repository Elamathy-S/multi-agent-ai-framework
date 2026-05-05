"""
client/agents/trading_agent.py — Trading specialist agent.

Owns: portfolio holdings, PnL, market prices.
Calls both portfolio tools directly — no LLM tool selection.
"""

from server.tools.tool_registry import registry


def trading_agent(query: str, customer_id: int) -> dict:
    from client.agents.base import run_tool
    _denials = []
    history  = []

    # Retrieve RAG policies and record titles
    from rag.retriever import get_policy_context
    policy_context = get_policy_context(query, category="trading")
    try:
        from rag.embedder import retrieve as _retrieve
        rag_titles = [d["title"] for d in _retrieve(query, n_results=2, category="trading")]
    except Exception:
        rag_titles = []

    for tool_name in ["get_portfolio", "calculate_pnl"]:
        obs = run_tool(tool_name, agent_name="trading_agent",
                       denial_log=_denials, customer_id=customer_id)
        history.append({
            "thought":      f"Running {tool_name} for customer {customer_id}",
            "action":       tool_name,
            "args":         {"customer_id": customer_id},
            "obs":          obs,
            "rag_policies": rag_titles,
        })

    obs_all = {s["action"]: s["obs"] for s in history}
    return {"answer": _fallback(obs_all), "observations": obs_all,
            "steps": history, "denials": _denials}


def _fallback(obs):
    portfolio = obs.get("get_portfolio", [])
    pnl       = obs.get("calculate_pnl", {})
    parts     = []
    if isinstance(portfolio, list) and portfolio:
        symbols = [p.get("symbol", "?") for p in portfolio]
        parts.append(f"Holdings: {', '.join(symbols)}")
    if pnl and "total_pnl" in pnl:
        direction = "profit" if float(pnl["total_pnl"]) >= 0 else "loss"
        parts.append(f"PnL: ${abs(float(pnl['total_pnl'])):,.2f} {direction}")
    return " | ".join(parts) if parts else "Trading data retrieved."