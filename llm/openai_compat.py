"""
llm/openai_compat.py — Any provider that speaks the OpenAI Chat Completions format.

Covers Gemini (via Google's OpenAI-compatible endpoint), Groq, OpenRouter,
Mistral, Cerebras and others. Written with plain httpx so no extra SDK is needed.

Things this adapter handles because free hosted tiers make them matter:
  * rate limits (HTTP 429) and transient 5xx: retried with backoff, honouring Retry-After
  * a concurrency cap, so parallel specialists do not trip requests-per-minute limits
  * Gemini 3 "thought signatures": returned on tool calls and REQUIRED on the next
    request, otherwise the API answers 400. Kept in ToolCall.extra and echoed back
  * thinking models spend output tokens on reasoning, so a floor is applied to max_tokens
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx

from llm.types import LLMError, LLMResponse, ToolCall, ToolSpec, Usage

RETRY_STATUS = {429, 500, 502, 503, 504}
SKIP_SIGNATURE = "skip_thought_signature_validator"   # Google's documented last-resort value


class OpenAICompatClient:
    def __init__(
        self, *, base_url: str, api_key: str, model: str, name: str = "openai_compat",
        reasoning_effort: str | None = None, min_output_tokens: int = 0,
        gemini_signatures: bool = False, max_retries: int = 4, retry_base: float = 1.5,
    ):
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._name = name
        self._effort = reasoning_effort
        self._min_out = min_output_tokens
        # Some providers/models reject large max_tokens (e.g. 512); LLM_MAX_OUTPUT_TOKENS caps it.
        self._cap = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "0")) or None
        self._gemini = gemini_signatures
        self._max_retries = max_retries
        self._retry_base = retry_base
        self._timeout = float(os.getenv("LLM_TIMEOUT", "120"))
        self._gate = asyncio.Semaphore(int(os.getenv("LLM_MAX_CONCURRENCY", "2")))

    # ------------------------------------------------------------------
    def _limit(self, n: int) -> int:
        return min(n, self._cap) if self._cap else n

    async def chat(self, system, messages, tools=None, *, max_tokens=1024, force_tool=None) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + _to_openai_messages(messages, self._gemini),
            "max_tokens": self._limit(max(max_tokens, self._min_out)),
        }
        if self._effort:
            payload["reasoning_effort"] = self._effort
        if tools:
            payload["tools"] = [_tool_json(t) for t in tools]
            payload["tool_choice"] = (
                {"type": "function", "function": {"name": force_tool}} if force_tool else "auto")

        data = await self._post(payload)
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self._name} returned an unexpected reply: {str(data)[:300]}") from exc

        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                name=fn.get("name", ""), args=args if isinstance(args, dict) else {},
                extra=tc.get("extra_content"),
            ))

        finish = choice.get("finish_reason")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=msg.get("content") or "",
            tool_calls=calls,
            stop_reason="tool_use" if calls else "max_tokens" if finish == "length" else "end_turn",
            usage=Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
        )

    # ------------------------------------------------------------------
    async def _post(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        last = ""
        for attempt in range(self._max_retries + 1):
            try:
                async with self._gate, httpx.AsyncClient(timeout=self._timeout) as http:
                    r = await http.post(self._url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                raise LLMError(f"{self._name} timed out after {self._timeout:.0f}s (raise LLM_TIMEOUT)") from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"{self._name} request failed: {exc}") from exc

            if r.status_code == 200:
                return r.json()
            last = r.text[:400]
            if r.status_code in RETRY_STATUS and attempt < self._max_retries:
                await asyncio.sleep(_backoff(r, attempt, self._retry_base))
                continue
            break

        if r.status_code == 429:
            raise LLMError(f"{self._name} rate limit hit (free tier?). Wait a minute, lower "
                           f"LLM_MAX_CONCURRENCY, or use a model with a higher limit. Detail: {last}")
        if r.status_code in (401, 403):
            raise LLMError(f"{self._name} rejected the API key ({r.status_code}). Check your key in .env.")
        raise LLMError(f"{self._name} error {r.status_code}: {last}")


def _backoff(r: httpx.Response, attempt: int, base: float) -> float:
    try:
        return min(float(r.headers["retry-after"]), 60.0)
    except (KeyError, ValueError):
        return min(base * (2 ** attempt), 30.0)


def _clean_schema(node):
    """Drop 'title' noise that MCP/pydantic adds; some providers are strict about schemas."""
    if isinstance(node, dict):
        return {k: _clean_schema(v) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_clean_schema(v) for v in node]
    return node


def _tool_json(t: ToolSpec) -> dict:
    fn: dict = {"name": t.name, "description": t.description}
    schema = _clean_schema(t.schema or {})
    if schema.get("properties"):          # empty-parameter tools: omit 'parameters' entirely
        fn["parameters"] = schema
    return {"type": "function", "function": fn}


def _to_openai_messages(messages: list[dict], gemini: bool) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            entry: dict = {"role": "assistant", "content": m.get("text") or None}
            calls = []
            for i, c in enumerate(m.get("tool_calls", [])):
                call = {"id": c.id, "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.args)}}
                if c.extra:
                    call["extra_content"] = c.extra
                elif gemini and i == 0:
                    call["extra_content"] = {"google": {"thought_signature": SKIP_SIGNATURE}}
                calls.append(call)
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
        elif m["role"] == "tool":
            for r in m["results"]:
                out.append({"role": "tool", "tool_call_id": r.call_id, "name": r.name, "content": r.content})
    return out