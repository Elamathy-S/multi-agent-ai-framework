"""
client/agents/orchestrator.py — Supervisor that plans, delegates, and synthesises.

    1. PLAN        the LLM reads the question and the specialist roster and
                   delegates self-contained sub-tasks via a `delegate` tool
                   call (or answers directly if the question is out of scope)
    2. DELEGATE    chosen specialists run concurrently, each in its own agent
                   loop over one shared MCP session
    3. SYNTHESISE  the LLM merges the specialists' findings into one answer,
                   grounded only in what they reported

There is no keyword routing and no template formatting: the supervisor and
the specialists reason with the model. If the model is unavailable the
request fails loudly instead of degrading into a different, fake behaviour.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from dataclasses import dataclass, field

from client.agents.loop import AgentResult, AgentSpec, EventSink, run_agent
from client.agents.specs import SPECIALISTS
from client.mcp.client import MCPClient
from llm import LLMClient, LLMError, ToolSpec, Usage, get_llm

AGENTS = SPECIALISTS

PLAN_SYSTEM = """\
You are the supervisor of a bank's multi-agent customer-analysis assistant.
The user asks about one customer. You delegate to specialists with the `delegate` tool.

Specialists:
{roster}

Guidelines:
- Give each specialist a self-contained task that states exactly what to find out.
- Delegate only to the specialists the question needs; use several for broad questions.
- If the question is unrelated to customer finance, answer briefly in plain text and do not delegate.\
"""

DELEGATE_TOOL = ToolSpec(
    name="delegate",
    description="Assign sub-tasks to specialist agents. They run in parallel.",
    schema={
        "type": "object",
        "properties": {
            "reasoning": {"type": "string", "description": "One sentence: why these specialists."},
            "tasks": {
                "type": "array", "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": list(SPECIALISTS)},
                        "task": {"type": "string", "description": "Self-contained instruction."},
                    },
                    "required": ["agent", "task"],
                },
            },
        },
        "required": ["tasks"],
    },
)

SYNTH_SYSTEM = """\
You are the lead analyst. Answer the user's question using ONLY the specialist reports provided.
- Do not add facts, figures or recommendations that are not in the reports.
- Keep policy citations such as [risk_policy_001#2] next to the claims they support.
- Cite only passage ids that appear in the reports under "Policy passages retrieved". Never write a policy rule from memory.
- If a specialist FAILED, say that its area could not be assessed. Say nothing else about that area: no guesses, no policy rules.
- If a specialist was denied a tool or reported missing data, say what is unknown.
- Be direct and concise (under 200 words); lead with the answer to the question.\
"""


@dataclass
class Plan:
    tasks: list[dict] = field(default_factory=list)      # [{"agent", "task"}]
    reasoning: str = ""
    direct_reply: str = ""
    usage: Usage = field(default_factory=Usage)

    @property
    def agents(self) -> list[str]:
        return [t["agent"] for t in self.tasks]


# ---------------------------------------------------------------------------
async def plan(llm: LLMClient, query: str, customer_id: int) -> Plan:
    roster = "\n".join(f"- {s.name}: {s.description}" for s in SPECIALISTS.values())
    resp = await llm.chat(
        PLAN_SYSTEM.format(roster=roster),
        [{"role": "user", "content": f"Customer ID: {customer_id}\nQuestion: {query}"}],
        [DELEGATE_TOOL],
        max_tokens=600,
    )
    out = Plan(usage=resp.usage)
    for call in resp.tool_calls:
        if call.name != "delegate":
            continue
        out.reasoning = str(call.args.get("reasoning", ""))
        seen = set()
        for t in call.args.get("tasks", []):
            agent, task = t.get("agent"), t.get("task", "")
            if agent in SPECIALISTS and agent not in seen and task:
                seen.add(agent)
                out.tasks.append({"agent": agent, "task": task})
    if not out.tasks:
        if resp.text.strip():
            out.direct_reply = resp.text.strip()
        else:
            raise LLMError("Supervisor produced neither a delegation nor an answer")
    return out


async def run_agents(
    llm: LLMClient, mcp: MCPClient, tasks: list[dict], customer_id: int,
    *, session_id: str = "", on_event: EventSink | None = None,
) -> dict[str, AgentResult]:
    """Run the delegated specialists concurrently. One failing agent never sinks the rest."""

    async def one(t: dict) -> AgentResult:
        spec: AgentSpec = SPECIALISTS[t["agent"]]
        try:
            return await run_agent(spec, llm, mcp, t["task"], customer_id,
                                   session_id=session_id, on_event=on_event)
        except Exception as exc:
            return AgentResult(agent=spec.name, status="error", error=f"{type(exc).__name__}: {exc}")

    results = await asyncio.gather(*[one(t) for t in tasks])
    return {r.agent: r for r in results}


async def synthesise(llm: LLMClient, query: str, results: dict[str, AgentResult]) -> tuple[str, Usage]:
    reports = []
    for name, r in results.items():
        if r.status == "error":
            reports.append(f"## {name} specialist\nFAILED: {r.error}")
            continue
        body = r.answer
        if r.denials:
            body += "\nDenied tools: " + ", ".join(d["tool"] for d in r.denials)
        data = json.dumps(
            {k: v for k, v in r.observations.items() if k != "search_policies"}, default=str,
        )[:2500]
        retrieved = ", ".join(r.policies) or "none"
        reports.append(f"## {name} specialist\n{body}\nPolicy passages retrieved: {retrieved}\nRaw tool data: {data}")

    if all(r.status == "error" for r in results.values()):
        return "I could not complete this analysis: " + "; ".join(
            f"{n}: {r.error}" for n, r in results.items()), Usage()

    resp = await llm.chat(
        SYNTH_SYSTEM,
        [{"role": "user", "content": f"Question: {query}\n\nSpecialist reports:\n\n" + "\n\n".join(reports)}],
        None,
        max_tokens=700,
    )
    return resp.text.strip(), resp.usage


# ---------------------------------------------------------------------------
async def orchestrator(
    query: str, customer_id: int = 1, *,
    llm: LLMClient | None = None, mcp: MCPClient | None = None,
    on_event: EventSink | None = None,
) -> dict:
    """
    Plan -> delegate -> synthesise, with the whole run logged as one session.
    `llm` and `mcp` can be injected (tests do); by default a real model is
    created and a fresh MCP session is opened for the run.
    """
    from server.logger_agent import new_session_id

    llm = llm or get_llm()
    sid = new_session_id()
    started = time.time()
    usage = Usage()

    async def emit(e: dict) -> None:
        if on_event:
            out = on_event(e)
            if asyncio.iscoroutine(out):
                await out

    await emit({"type": "plan_start"})
    the_plan = await plan(llm, query, customer_id)
    usage += the_plan.usage
    await emit({"type": "plan", "agents": the_plan.agents, "reasoning": the_plan.reasoning,
                "direct_reply": the_plan.direct_reply})

    if the_plan.direct_reply:
        return {"answer": the_plan.direct_reply, "agents_called": [], "agent_results": {},
                "total_tools": 0, "session_id": sid, "denials": [], "plan": the_plan.reasoning,
                "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}}

    async with _mcp_session(mcp) as session:
        results = await run_agents(llm, session, the_plan.tasks, customer_id, session_id=sid, on_event=on_event)
    for r in results.values():
        usage += r.usage

    await emit({"type": "synthesis_start"})
    answer, synth_usage = await synthesise(llm, query, results)
    usage += synth_usage
    answer, removed = strip_unverified_citations(answer, results)

    denials = [d for r in results.values() for d in r.denials]
    _log_session(sid, query, customer_id, the_plan, results, denials, answer, (time.time() - started) * 1000)

    return {
        "answer": answer,
        "agents_called": the_plan.agents,
        "agent_results": {n: r.to_dict() for n, r in results.items()},
        "total_tools": sum(len(r.steps) for r in results.values()),
        "session_id": sid,
        "denials": denials,
        "plan": the_plan.reasoning,
        "removed_citations": removed,
        "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
    }


CITATION = re.compile(r"\[([a-z_]+_\d+#\d+)\]")


def strip_unverified_citations(answer: str, results: dict[str, AgentResult]) -> tuple[str, list[str]]:
    """
    Code-level guard against invented citations: any [policy_id#n] that no
    specialist actually retrieved is removed and flagged. Prompts ask the model
    not to do this; this makes sure it cannot slip through if it does.
    """
    retrieved = {p for r in results.values() for p in r.policies}
    bad = [c for c in dict.fromkeys(CITATION.findall(answer)) if c not in retrieved]
    for c in bad:
        answer = answer.replace(f"[{c}]", "[unverified citation removed]")
    if bad:
        answer += "\n\n(Note: citation(s) removed because no specialist retrieved them: " + ", ".join(bad) + ")"
    return answer, bad


@contextlib.asynccontextmanager
async def _mcp_session(existing: MCPClient | None):
    if existing is not None:
        yield existing
    else:
        async with MCPClient() as opened:
            yield opened


def _log_session(sid, query, customer_id, the_plan, results, denials, answer, latency_ms) -> None:
    """Persist the session trace. Logging must never break a request."""
    try:
        from server.db import Base, engine
        from server.logger_agent import log_agent_session
        Base.metadata.create_all(bind=engine)
        log_agent_session(
            session_id=sid, user_query=query, customer_id=customer_id,
            agents_planned=the_plan.agents,
            agent_results={n: r.to_dict() for n, r in results.items()},
            rag_retrieved={n: r.policies for n, r in results.items()},
            permission_denials=denials, final_answer=answer, total_latency_ms=latency_ms,
            error="; ".join(f"{n}: {r.error}" for n, r in results.items() if r.error) or None,
            plan_reason=the_plan.reasoning,
        )
    except Exception as exc:
        print(f"⚠️  Session logging failed (non-fatal): {exc}")
