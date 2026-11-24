"""
client/agents/loop.py — The agent loop.

One generic loop drives every specialist. The model is given a role, a task
and the tools its RBAC role permits, then decides for itself which tools to
call, in what order, and when it has enough to answer. There is no keyword
routing, no scripted tool order, and no "call everything" fallback.

    messages = [task]
    repeat up to max_steps:
        response = llm(system, messages, tools)       # native tool use
        if no tool calls: return response.text        # model decided it is done
        run the tool calls through MCP (RBAC-checked) # act
        append results to messages                    # observe

Safety properties enforced here, not left to the prompt:
  * the model only SEES tools its role is permitted to use
  * every call is re-checked and audit-logged at execution time
  * `customer_id` is injected by the harness; the model cannot change it
  * tool output is size-capped before going back into the context
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Union

from client.mcp.client import MCPClient, MCPToolError
from client.security.permissions import check_permission, permitted_tools
from llm import LLMClient, ToolCall, ToolResult, ToolSpec, Usage

MAX_OBSERVATION_CHARS = 6000
Event = dict
EventSink = Callable[[Event], Union[None, Awaitable[None]]]


@dataclass
class AgentSpec:
    """Declarative agent definition. Behaviour lives in the loop, not here."""
    name: str            # short name used by the orchestrator, e.g. "risk"
    role: str            # RBAC role, e.g. "risk_agent"
    icon: str
    description: str     # shown to the orchestrator when it plans
    instructions: str    # domain guidance for this specialist


@dataclass
class AgentResult:
    agent: str
    answer: str = ""
    steps: list[dict] = field(default_factory=list)
    observations: dict = field(default_factory=dict)
    denials: list[dict] = field(default_factory=list)
    policies: list[str] = field(default_factory=list)   # RAG passage ids the agent retrieved
    usage: Usage = field(default_factory=Usage)
    status: str = "ok"                                   # ok | max_steps | error
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "agent": self.agent, "answer": self.answer, "steps": self.steps,
            "observations": self.observations, "denials": self.denials,
            "policies": self.policies, "status": self.status, "error": self.error,
            "usage": {"input_tokens": self.usage.input_tokens, "output_tokens": self.usage.output_tokens},
        }


SYSTEM_TEMPLATE = """\
You are the {name} specialist in a bank's multi-agent assistant.
{instructions}

Rules:
- You are working on customer {customer_id}. Your tools are already scoped to this customer; never ask for an ID.
- Every number or claim in your answer must come from a tool result. Never invent or estimate data.
- If a tool fails or returns nothing, say so plainly instead of guessing.
- Call only the tools you need, then stop and answer. Do not repeat a call you already made.
- Before stating a required action, threshold or escalation, look it up with search_policies (if you have it) and cite the passage id in [brackets].
- Final answer: concise findings with the key figures, no more than about 120 words.\
"""


async def run_agent(
    spec: AgentSpec,
    llm: LLMClient,
    mcp: MCPClient,
    task: str,
    customer_id: int,
    *,
    session_id: str = "",
    max_steps: int = 6,
    on_event: EventSink | None = None,
) -> AgentResult:
    result = AgentResult(agent=spec.name)
    emit = _emitter(on_event, spec.name)
    try:
        await _drive(spec, llm, mcp, task, customer_id, session_id, max_steps, result, emit)
    except Exception as exc:
        # Keep every step taken so far and say why we stopped; never lose the trace.
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
        await emit({"type": "agent_error", "error": result.error})
    return _finish(result)


async def _drive(spec, llm, mcp, task, customer_id, session_id, max_steps, result, emit) -> None:
    tools, scoped = await _tools_for(spec, mcp)
    tool_names = {t.name for t in tools}
    system = SYSTEM_TEMPLATE.format(
        name=spec.name, instructions=spec.instructions, customer_id=customer_id,
    )
    messages: list[dict] = [{"role": "user", "content": task}]

    for _ in range(max_steps):
        resp = await llm.chat(system, messages, tools, max_tokens=1024)
        result.usage += resp.usage

        if not resp.tool_calls:                       # the model decided it is done
            result.answer = resp.text.strip()
            await emit({"type": "final", "answer": result.answer})
            return

        messages.append({"role": "assistant", "text": resp.text, "tool_calls": resp.tool_calls})
        outcomes = await asyncio.gather(*[
            _execute(c, spec, mcp, tool_names, scoped, customer_id, session_id, result, resp.text, emit)
            for c in resp.tool_calls
        ])
        messages.append({"role": "tool", "results": list(outcomes)})

    # Step budget exhausted: force a final answer from what has been gathered.
    messages.append({"role": "user", "content": "Tool budget used up. Answer now using only the results above."})
    resp = await llm.chat(system, messages, None, max_tokens=1024)
    result.usage += resp.usage
    result.answer = resp.text.strip()
    result.status = "max_steps"
    await emit({"type": "final", "answer": result.answer})


# ---------------------------------------------------------------------------
async def _tools_for(spec: AgentSpec, mcp: MCPClient) -> tuple[list[ToolSpec], set[str]]:
    """
    Tools the MCP server offers, filtered to what this role may use.
    Also returns the names of tools that take a customer_id (the harness fills it in).
    """
    allowed = permitted_tools(spec.role)
    out: list[ToolSpec] = []
    scoped: set[str] = set()
    for t in await mcp.list_tools():
        if t["name"] not in allowed:
            continue
        if "customer_id" in (t["schema"] or {}).get("properties", {}):
            scoped.add(t["name"])
        out.append(ToolSpec(t["name"], t["description"], _hide_customer_id(t["schema"])))
    return out, scoped


def _hide_customer_id(schema: dict) -> dict:
    """The harness injects customer_id, so the model never sees or sets it."""
    schema = json.loads(json.dumps(schema or {"type": "object", "properties": {}}))
    schema.get("properties", {}).pop("customer_id", None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r != "customer_id"]
    return schema


async def _execute(
    call: ToolCall, spec: AgentSpec, mcp: MCPClient, tool_names: set[str], scoped: set[str],
    customer_id: int, session_id: str, result: AgentResult, thought: str, emit,
) -> ToolResult:
    start = time.time()
    args = dict(call.args)
    await emit({"type": "tool_call", "tool": call.name, "args": args, "thought": thought})

    obs: object
    ok = True
    if not check_permission(spec.role, call.name, session_id, customer_id):   # audited
        denial = {"agent": spec.role, "tool": call.name,
                  "reason": f"{spec.role} is not authorised to call {call.name}"}
        result.denials.append(denial)
        ok, obs = False, {"error": denial["reason"]}
    elif call.name not in tool_names:
        ok, obs = False, {"error": f"Unknown tool '{call.name}'. Available: {', '.join(sorted(tool_names))}"}
    else:
        try:
            scope = {"customer_id": customer_id} if call.name in scoped else {}
            obs = await mcp.call(call.name, **{**args, **scope})
        except MCPToolError as exc:
            ok, obs = False, {"error": str(exc)}
        except Exception as exc:                      # connection drop, bad args, ...
            ok, obs = False, {"error": f"{type(exc).__name__}: {exc}"}

    latency = round((time.time() - start) * 1000)
    result.steps.append({
        "agent": spec.name, "thought": thought.strip(), "action": call.name,
        "args": args, "obs": obs, "ok": ok, "latency_ms": latency,
    })
    if ok:
        result.observations[call.name] = obs
        if call.name == "search_policies" and isinstance(obs, list):
            result.policies.extend(p.get("id", "") for p in obs)
    await emit({"type": "tool_result", "tool": call.name, "ok": ok, "latency_ms": latency})

    content = json.dumps(obs, default=str)
    if len(content) > MAX_OBSERVATION_CHARS:
        content = content[:MAX_OBSERVATION_CHARS] + '... [truncated]'
    return ToolResult(call.id, call.name, content, is_error=not ok)


def _finish(result: AgentResult) -> AgentResult:
    if not result.answer:
        result.status = "error"
        result.error = result.error or "model returned an empty answer"
    result.policies = list(dict.fromkeys(p for p in result.policies if p))
    return result


def _emitter(sink: EventSink | None, agent: str):
    async def emit(event: Event) -> None:
        if sink is None:
            return
        out = sink({"agent": agent, **event})
        if asyncio.iscoroutine(out):
            await out
    return emit
