"""
client/agents/react.py — ReAct reasoning engine.

Provides a generic think→act→observe loop that any specialist agent
can use.  The LLM decides which tool to call next based on what it
has already observed, and stops when it has enough data to answer.

Falls back to calling all permitted tools sequentially if the LLM
cannot produce valid reasoning (handles phi3 unreliability).
"""

import json
from client.llm import safe_json_llm
from client.mcp.client import MCPClient
from client.agents.base import run_tool


# ---------------------------------------------------------------------------
# Prompt template — kept minimal for phi3 compatibility
# ---------------------------------------------------------------------------
_REACT_SYSTEM = """\
You are {persona}.
You have these tools:
{tool_list}

Decide what to do. Call ONE tool at a time, observe the result, then decide again.

Respond with JSON only. Either:
{{"thought":"why you are calling this tool","action":"tool_name","args":{{"customer_id":N}}}}

Or when you have enough data:
{{"thought":"what you concluded","action":"finish","answer":"your final answer"}}"""


_REACT_USER = """\
Question: {query}
Customer ID: {customer_id}
{rag_context}
{history_block}
What is your next step? Reply with JSON only."""


# ---------------------------------------------------------------------------
# ReAct loop
# ---------------------------------------------------------------------------
async def react_loop(
    mcp: MCPClient,
    query: str,
    customer_id: int,
    *,
    agent_name: str,
    persona: str,
    tools: dict[str, str],
    rag_category: str | None = None,
    max_steps: int = 5,
) -> dict:
    """
    Run a ReAct (Reason + Act) loop.

    Each iteration the LLM sees the query, available tools, and all
    previous observations, then decides which tool to call next or
    whether to finish.

    Args:
        mcp:           Open MCPClient session.
        query:         User's natural-language question.
        customer_id:   Target customer.
        agent_name:    For permission checks (e.g. "risk_agent").
        persona:       One-line role description for the system prompt.
        tools:         {mcp_tool_name: description} — what this agent can call.
        rag_category:  Optional RAG category to retrieve policies from.
        max_steps:     Safety cap on iterations.

    Returns:
        Standard agent result dict:
        {answer, observations, steps, denials, reasoning_mode}
    """
    history: list[dict] = []
    denials: list[dict] = []

    # RAG context
    rag_context = _get_rag_context(query, rag_category)
    rag_titles  = _get_rag_titles(query, rag_category)

    # Build system prompt
    tool_list = "\n".join(f"  - {name}: {desc}" for name, desc in tools.items())
    system = _REACT_SYSTEM.format(persona=persona, tool_list=tool_list)

    for step_num in range(max_steps):
        # Build user prompt with history
        history_block = _format_history(history)
        user = _REACT_USER.format(
            query=query,
            customer_id=customer_id,
            rag_context=rag_context,
            history_block=history_block,
        )

        # Ask the LLM
        decision = safe_json_llm(system, user)

        # If LLM failed to produce valid JSON, fall back
        if "error" in decision:
            print(f"  ⚠️  {agent_name} LLM failed at step {step_num + 1}, falling back")
            return await _fallback_run(
                mcp, query, customer_id,
                agent_name=agent_name,
                tools=tools,
                rag_titles=rag_titles,
                denials=denials,
                prior_steps=history,
            )

        thought = decision.get("thought", "")
        action  = decision.get("action", "")
        args    = decision.get("args", {})
        answer  = decision.get("answer", "")

        # ── Finish ────────────────────────────────────────────────────
        if action == "finish":
            history.append({
                "thought": thought,
                "action":  "finish",
                "args":    {},
                "obs":     answer,
                "rag_policies": rag_titles,
            })
            obs_all = {s["action"]: s["obs"] for s in history if s["action"] != "finish"}
            return {
                "answer":         answer or _build_fallback_answer(obs_all, tools),
                "observations":   obs_all,
                "steps":          history,
                "denials":        denials,
                "reasoning_mode": "react",
            }

        # ── Validate action ───────────────────────────────────────────
        if action not in tools:
            # LLM hallucinated a tool name — nudge it
            history.append({
                "thought": thought,
                "action":  action,
                "args":    args,
                "obs":     {"error": f"Unknown tool '{action}'. Available: {', '.join(tools.keys())}"},
                "rag_policies": rag_titles,
            })
            continue

        # ── Call tool via MCP ─────────────────────────────────────────
        # Ensure customer_id is in args
        if "customer_id" not in args:
            args["customer_id"] = customer_id

        obs = await run_tool(
            mcp, action,
            agent_name=agent_name,
            denial_log=denials,
            **args,
        )

        history.append({
            "thought": thought,
            "action":  action,
            "args":    args,
            "obs":     obs,
            "rag_policies": rag_titles,
        })

    # Hit max steps — synthesise what we have
    obs_all = {s["action"]: s["obs"] for s in history if s["action"] != "finish"}
    return {
        "answer":         _build_fallback_answer(obs_all, tools),
        "observations":   obs_all,
        "steps":          history,
        "denials":        denials,
        "reasoning_mode": "react_max_steps",
    }


# ---------------------------------------------------------------------------
# Fallback — call all tools sequentially (current behaviour)
# ---------------------------------------------------------------------------
async def _fallback_run(
    mcp: MCPClient,
    query: str,
    customer_id: int,
    *,
    agent_name: str,
    tools: dict[str, str],
    rag_titles: list[str],
    denials: list[dict],
    prior_steps: list[dict],
) -> dict:
    """
    When the LLM can't reason, call every tool in the agent's
    permission set and return all results.  This is the original
    behaviour — reliable even with weak models.
    """
    history = list(prior_steps)  # keep any steps already taken
    already_called = {s["action"] for s in history}

    for tool_name in tools:
        if tool_name in already_called:
            continue  # don't repeat a tool the LLM already called

        obs = await run_tool(
            mcp, tool_name,
            agent_name=agent_name,
            denial_log=denials,
            customer_id=customer_id,
        )
        history.append({
            "thought":      f"Fallback: calling {tool_name}",
            "action":       tool_name,
            "args":         {"customer_id": customer_id},
            "obs":          obs,
            "rag_policies": rag_titles,
        })

    obs_all = {s["action"]: s["obs"] for s in history if s["action"] != "finish"}
    return {
        "answer":         _build_fallback_answer(obs_all, tools),
        "observations":   obs_all,
        "steps":          history,
        "denials":        denials,
        "reasoning_mode": "fallback",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _format_history(history: list[dict]) -> str:
    if not history:
        return "No steps taken yet."

    lines = ["Previous steps:"]
    for i, step in enumerate(history, 1):
        obs_str = json.dumps(step["obs"], default=str)
        if len(obs_str) > 300:
            obs_str = obs_str[:300] + "..."
        lines.append(
            f"  Step {i}: Called {step['action']} → {obs_str}"
        )
    return "\n".join(lines)


def _build_fallback_answer(obs_all: dict, tools: dict) -> str:
    """Build a simple text summary from raw observations."""
    parts = []
    for tool_name, obs in obs_all.items():
        if isinstance(obs, dict) and "error" in obs:
            continue
        # Take the first few key-value pairs as a summary
        if isinstance(obs, dict):
            highlights = []
            for k, v in list(obs.items())[:4]:
                if isinstance(v, (str, int, float, bool)):
                    highlights.append(f"{k}: {v}")
            if highlights:
                parts.append(f"{tool_name} → {', '.join(highlights)}")
        elif isinstance(obs, list):
            parts.append(f"{tool_name} → {len(obs)} record(s)")
    return " | ".join(parts) if parts else "Data retrieved."


def _get_rag_context(query: str, category: str | None) -> str:
    if not category:
        return ""
    try:
        from rag.retriever import get_policy_context
        ctx = get_policy_context(query, category=category)
        return ctx if ctx else ""
    except Exception:
        return ""


def _get_rag_titles(query: str, category: str | None) -> list[str]:
    if not category:
        return []
    try:
        from rag.embedder import retrieve
        return [d["title"] for d in retrieve(query, n_results=2, category=category)]
    except Exception:
        return []