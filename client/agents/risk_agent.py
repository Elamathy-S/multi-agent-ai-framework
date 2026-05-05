"""
client/agents/risk_agent.py — Risk specialist agent.

Owns: risk scoring, fraud detection.
Has its own ReAct loop — may call both tools if risk is high.
"""

import json
from client.llm.llm_engine import safe_json_llm
from server.tools.tool_registry import registry

TOOLS = {
    "risk_score_tool":  "Calculate risk score 0-100, level LOW/MEDIUM/HIGH, key factors",
    "fraud_check_tool": "Run fraud detection on transaction patterns",
}

SYSTEM = (
    "You are the Risk Agent at a bank. "
    "You handle risk scoring and fraud detection. "
    "Use the bank risk policies to interpret scores and recommend actions. "
    "If risk is HIGH, also run fraud_check_tool to be thorough. "
    "Decide which tool to call, or finish if you have enough. "
    'Reply JSON: {"thought":"...","action":"tool_name","args":{"customer_id":N}} '
    'or {"thought":"...","action":"finish","answer":"..."}'
)


def risk_agent(query: str, customer_id: int) -> dict:
    """
    Risk agent — always calls both risk_score_tool and fraud_check_tool.
    Uses run_tool for permission enforcement on both calls.
    """
    from rag.retriever import get_policy_context
    from client.agents.base import run_tool
    history  = []
    _denials = []

    # Retrieve RAG policies and record titles
    from rag.retriever import get_policy_context
    policy_context = get_policy_context(query, category="risk")
    try:
        from rag.embedder import retrieve as _retrieve
        rag_titles = [d["title"] for d in _retrieve(query, n_results=2, category="risk")]
    except Exception:
        rag_titles = []

    for tool_name in ["risk_score_tool", "fraud_check_tool"]:
        obs = run_tool(tool_name, agent_name="risk_agent",
                       denial_log=_denials, customer_id=customer_id)
        history.append({
            "thought":      f"Running {tool_name} for customer {customer_id}",
            "action":       tool_name,
            "args":         {"customer_id": customer_id},
            "obs":          obs,
            "rag_policies": rag_titles,
        })

    obs_all = {s["action"]: s["obs"] for s in history}
    return {"answer": _fallback(obs_all), "observations": obs_all, "steps": history, "denials": _denials}


def _format_history(history):
    if not history: return " None"
    return "".join(f"\n  Called {s['action']} → {json.dumps(s['obs'])[:200]}" for s in history)


def _fallback(obs):
    risk  = obs.get("risk_score_tool", {})
    fraud = obs.get("fraud_check_tool", {})
    parts = []
    if risk:
        parts.append(f"Risk: {risk.get('risk_score','?')}/100 ({risk.get('level','?')})")
    if fraud:
        flag = "FRAUD FLAGGED" if fraud.get("fraud_flag") else "No fraud"
        parts.append(f"Fraud: {flag} ({fraud.get('confidence','?')} confidence)")
    return " | ".join(parts) if parts else "Risk data retrieved."