"""llm/anthropic_client.py — Claude via the official Anthropic SDK (native tool use)."""

from __future__ import annotations

import os

from llm.types import LLMError, LLMResponse, ToolCall, ToolSpec, Usage

DEFAULT_MODEL = "claude-sonnet-5-5"


class AnthropicClient:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMError("Install the SDK: pip install anthropic") from exc
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not set (or use LLM_PROVIDER=ollama)")
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self._client = AsyncAnthropic(api_key=key, max_retries=3, timeout=60.0)

    async def chat(self, system, messages, tools=None, *, max_tokens=1024, force_tool=None) -> LLMResponse:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": _to_anthropic_messages(messages),
        }
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.schema}
                for t in tools
            ]
            if force_tool:
                kwargs["tool_choice"] = {"type": "tool", "name": force_tool}
        try:
            resp = await self._client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc

        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [
            ToolCall(id=b.id, name=b.name, args=dict(b.input))
            for b in resp.content if b.type == "tool_use"
        ]
        return LLMResponse(
            text=text,
            tool_calls=calls,
            stop_reason=resp.stop_reason or "end_turn",
            usage=Usage(resp.usage.input_tokens, resp.usage.output_tokens),
        )


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "content": m["content"]})
        elif role == "assistant":
            blocks: list[dict] = []
            if m.get("text"):
                blocks.append({"type": "text", "text": m["text"]})
            for c in m.get("tool_calls", []):
                blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.args})
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            out.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in m["results"]
                ],
            })
    return out
