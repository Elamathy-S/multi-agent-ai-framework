"""
llm/scripted.py — Deterministic LLM stand-in for tests and CI.

Feed it a list of LLMResponse objects (or callables that build one from the
request). It records every request, so tests can assert on what the agent
actually sent: system prompt, tools offered, and tool results fed back.
"""

from __future__ import annotations

from typing import Callable, Union

from llm.types import LLMError, LLMResponse, ToolCall, ToolSpec

Step = Union[LLMResponse, Callable[[str, list[dict], list[ToolSpec]], LLMResponse]]


def tool_call(name: str, call_id: str = "c1", text: str = "", **args) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=[ToolCall(call_id, name, args)], stop_reason="tool_use")


def say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


class ScriptedLLM:
    model = "scripted"

    def __init__(self, steps: list[Step]):
        self._steps = list(steps)
        self.requests: list[dict] = []

    async def chat(self, system, messages, tools=None, *, max_tokens=1024, force_tool=None) -> LLMResponse:
        self.requests.append({
            "system": system, "messages": list(messages),
            "tools": [t.name for t in (tools or [])], "force_tool": force_tool,
        })
        if not self._steps:
            raise LLMError("ScriptedLLM ran out of scripted responses")
        step = self._steps.pop(0)
        return step(system, messages, tools or []) if callable(step) else step


class RoutedScriptedLLM:
    """
    Scripted LLM for multi-agent runs. Specialists execute concurrently, so a
    single FIFO queue would interleave unpredictably. This routes each request
    to its own queue by looking at who is asking:

        supervisor -> planning call      agents[name] -> that specialist's loop
        synthesis  -> final summary call
    """
    model = "scripted-routed"

    def __init__(self, supervisor: list[Step], agents: dict[str, list[Step]], synthesis: list[Step] | None = None):
        self._queues: dict[str, list[Step]] = {
            "supervisor": list(supervisor), "synthesis": list(synthesis or []),
            **{f"agent:{k}": list(v) for k, v in agents.items()},
        }
        self.requests: list[dict] = []

    @staticmethod
    def _who(system: str) -> str:
        if "supervisor of a bank" in system:
            return "supervisor"
        if "lead analyst" in system:
            return "synthesis"
        import re
        m = re.search(r"You are the (\w+) specialist", system)
        return f"agent:{m.group(1)}" if m else "unknown"

    async def chat(self, system, messages, tools=None, *, max_tokens=1024, force_tool=None) -> LLMResponse:
        who = self._who(system)
        self.requests.append({
            "who": who, "system": system, "messages": list(messages),
            "tools": [t.name for t in (tools or [])],
        })
        queue = self._queues.get(who)
        if not queue:
            raise LLMError(f"No scripted response left for {who}")
        step = queue.pop(0)
        return step(system, messages, tools or []) if callable(step) else step
