"""
client/agents/loan_agent.py — Loan specialist agent.

Owns: loan status, credit scores, approval decisions.
Calls both tools directly — no LLM tool selection.
Retrieves relevant loan policies from RAG before running tools.
"""

from server.tools.tool_registry import registry


def loan_agent(query: str, customer_id: int) -> dict:
    from rag.retriever import get_policy_context
    from client.agents.base import run_tool
    history  = []
    _denials = []

    # Retrieve RAG policies and record titles
    policy_context = get_policy_context(query, category="loan")
    try:
        from rag.embedder import retrieve
        rag_titles = [d["title"] for d in retrieve(query, n_results=2, category="loan")]
    except Exception:
        rag_titles = []

    for tool_name in ["check_loan_status", "credit_score_tool"]:
        obs = run_tool(tool_name, agent_name="loan_agent",
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
    credit = obs.get("credit_score_tool", {})
    loans  = obs.get("check_loan_status", [])
    parts  = []
    if credit:
        parts.append(f"Credit score: {credit.get('credit_score','?')} ({credit.get('rating','?')}), approval: {credit.get('loan_approval_likelihood','?')}")
    if isinstance(loans, list) and loans:
        total = sum(float(l.get("amount", 0)) for l in loans)
        parts.append(f"{len(loans)} loan(s) totalling ${total:,.2f}")
    return " | ".join(parts) if parts else "Loan data retrieved."