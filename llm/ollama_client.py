"""
llm/ollama_client.py — Local models via Ollama's native tool-calling API.

Use a model that supports tools (e.g. qwen2.5, llama3.1). Models without
tool support (such as phi3) cannot drive the agent loop and will fail fast.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx

from llm.types import LLMError, LLMResponse, ToolCall, ToolSpec, Usage

DEFAULT_MODEL = "qwen2.5:7b"


class OllamaClient:
    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        # A local GPU/CPU serves one request at a time. Queue requests here so the
        # timeout clock starts when a request actually runs, not while it waits.
        self._gate = asyncio.Semaphore(int(os.getenv("OLLAMA_MAX_CONCURRENCY", "1")))
        self._timeout = float(os.getenv("LLM_TIMEOUT", "300"))
        self._host = (host or os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")

    async def chat(self, system, messages, tools=None, *, max_tokens=1024, force_tool=None) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}] + _to_ollama_messages(messages),
            "options": {"temperature": 0, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = [
                {"type": "function",
                 "function": {"name": t.name, "description": t.description, "parameters": t.schema}}
                for t in tools
            ]
        try:
            async with self._gate, httpx.AsyncClient(timeout=self._timeout) as http:
                r = await http.post(f"{self._host}/api/chat", json=payload)
            if r.status_code == 400 and "tools" in r.text.lower():
                raise LLMError(f"Model '{self.model}' does not support tool calling. Try qwen2.5 or llama3.1.")
            r.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama timed out after {self._timeout:.0f}s (model slow or still loading). "
                           "Raise LLM_TIMEOUT or use a smaller model.") from exc
        except httpx.ConnectError as exc:
            raise LLMError("Ollama is not running. Start it with: ollama serve") from exc
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        data = r.json()
        msg = data.get("message", {})
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=fn.get("name", ""), args=args))
        return LLMResponse(
            text=msg.get("content", "") or "",
            tool_calls=calls,
            stop_reason="tool_use" if calls else "end_turn",
            usage=Usage(data.get("prompt_eval_count", 0), data.get("eval_count", 0)),
        )


def _to_ollama_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            entry = {"role": "assistant", "content": m.get("text", "")}
            if m.get("tool_calls"):
                entry["tool_calls"] = [
                    {"function": {"name": c.name, "arguments": c.args}} for c in m["tool_calls"]
                ]
            out.append(entry)
        elif m["role"] == "tool":
            for r in m["results"]:
                out.append({"role": "tool", "tool_name": r.name, "content": r.content})
    return out
