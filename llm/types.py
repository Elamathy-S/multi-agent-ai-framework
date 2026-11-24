"""
llm/types.py — Provider-neutral message and response types.

The agent loop only ever speaks these types. Each provider adapter
(Anthropic, Ollama, scripted-for-tests) translates to and from them, so
swapping models never touches agent code.

Conversation format (list of dicts):
    {"role": "user",      "content": "text"}
    {"role": "assistant", "text": "...", "tool_calls": [ToolCall, ...]}
    {"role": "tool",      "results": [ToolResult, ...]}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolSpec:
    """A tool the model may call. `schema` is a JSON Schema for its arguments."""
    name: str
    description: str
    schema: dict


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ToolResult:
    call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __iadd__(self, other: "Usage") -> "Usage":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        return self


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"          # end_turn | tool_use | max_tokens
    usage: Usage = field(default_factory=Usage)


class LLMError(Exception):
    """Raised when the model backend is unreachable or returns an unusable reply."""


class LLMClient(Protocol):
    model: str

    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        *,
        max_tokens: int = 1024,
        force_tool: str | None = None,
    ) -> LLMResponse: ...
