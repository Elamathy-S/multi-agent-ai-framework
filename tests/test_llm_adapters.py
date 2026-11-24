"""tests/test_llm_adapters.py — Message translation for each provider (no network)."""

from llm import ToolCall, ToolResult
from llm.anthropic_client import _to_anthropic_messages
from llm.ollama_client import _to_ollama_messages

CONVO = [
    {"role": "user", "content": "assess risk"},
    {"role": "assistant", "text": "checking", "tool_calls": [ToolCall("t1", "get_risk_score", {})]},
    {"role": "tool", "results": [ToolResult("t1", "get_risk_score", '{"risk_score": 5}')]},
]


def test_anthropic_tool_round_trip_shape():
    msgs = _to_anthropic_messages(CONVO)
    assert msgs[1]["content"][-1] == {"type": "tool_use", "id": "t1", "name": "get_risk_score", "input": {}}
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"][0]["type"] == "tool_result" and msgs[2]["content"][0]["tool_use_id"] == "t1"


def test_ollama_tool_round_trip_shape():
    msgs = _to_ollama_messages(CONVO)
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "get_risk_score"
    assert msgs[2] == {"role": "tool", "tool_name": "get_risk_score", "content": '{"risk_score": 5}'}


def test_anthropic_client_requires_a_key(monkeypatch):
    import pytest
    from llm import LLMError, get_llm
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        get_llm()


# ---------------------------------------------------------------------------
# Wire-level checks against mocked HTTP (what we send, how we parse the reply)
# ---------------------------------------------------------------------------
import json

import httpx

from llm import ToolSpec
from llm.anthropic_client import AnthropicClient
from llm.ollama_client import OllamaClient

SPEC = ToolSpec("get_risk_score", "Risk score", {"type": "object", "properties": {}})


async def test_anthropic_request_and_tool_use_parsing():
    from anthropic.types import Message
    seen = {}

    async def fake_create(**kwargs):
        seen.update(kwargs)
        return Message.model_validate({
            "id": "msg_1", "type": "message", "role": "assistant", "model": "m", "stop_reason": "tool_use",
            "content": [{"type": "text", "text": "Checking."},
                        {"type": "tool_use", "id": "toolu_1", "name": "get_risk_score", "input": {"x": 1}}],
            "usage": {"input_tokens": 11, "output_tokens": 7},
        })

    client = AnthropicClient(model="m", api_key="k")
    client._client.messages.create = fake_create
    resp = await client.chat("sys", CONVO, [SPEC], force_tool="get_risk_score")

    assert seen["system"] == "sys" and seen["tools"][0]["input_schema"] == SPEC.schema
    assert seen["tool_choice"] == {"type": "tool", "name": "get_risk_score"}
    assert seen["messages"][2]["content"][0]["type"] == "tool_result"
    assert resp.text == "Checking." and resp.stop_reason == "tool_use"
    assert resp.tool_calls[0].name == "get_risk_score" and resp.tool_calls[0].args == {"x": 1}
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (11, 7)


async def test_anthropic_errors_become_llm_errors():
    import pytest
    from llm import LLMError

    async def boom(**kwargs):
        raise RuntimeError("401 bad key")

    client = AnthropicClient(model="m", api_key="k")
    client._client.messages.create = boom
    with pytest.raises(LLMError, match="Anthropic request failed"):
        await client.chat("sys", [{"role": "user", "content": "hi"}])


async def test_ollama_request_and_tool_call_parsing(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "message": {"content": "", "tool_calls": [{"function": {"name": "get_risk_score", "arguments": {"a": 2}}}]},
            "prompt_eval_count": 5, "eval_count": 3})

    real = httpx.AsyncClient
    monkeypatch.setattr("llm.ollama_client.httpx.AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler)))
    resp = await OllamaClient(model="qwen2.5:7b", host="http://x").chat("sys", CONVO, [SPEC])

    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["tools"][0]["function"]["name"] == "get_risk_score"
    assert resp.tool_calls[0].args == {"a": 2} and resp.stop_reason == "tool_use"


async def test_ollama_model_without_tool_support_fails_clearly(monkeypatch):
    import pytest
    from llm import LLMError

    real = httpx.AsyncClient
    monkeypatch.setattr("llm.ollama_client.httpx.AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "registry.ollama.ai/library/phi3 does not support tools"}))))
    with pytest.raises(LLMError, match="does not support tool calling"):
        await OllamaClient(model="phi3", host="http://x").chat("sys", CONVO, [SPEC])


async def test_ollama_runs_one_request_at_a_time_by_default(monkeypatch):
    import asyncio
    state = {"active": 0, "peak": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.05)
        state["active"] -= 1
        return httpx.Response(200, json={"message": {"content": "ok"}})

    real = httpx.AsyncClient
    monkeypatch.setattr("llm.ollama_client.httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    monkeypatch.delenv("OLLAMA_MAX_CONCURRENCY", raising=False)
    client = OllamaClient(model="m", host="http://x")
    await asyncio.gather(*[client.chat("s", [{"role": "user", "content": "hi"}]) for _ in range(3)])
    assert state["peak"] == 1


async def test_ollama_timeout_gives_an_actionable_message(monkeypatch):
    import pytest
    from llm import LLMError

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    real = httpx.AsyncClient
    monkeypatch.setattr("llm.ollama_client.httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(slow)))
    with pytest.raises(LLMError, match="LLM_TIMEOUT"):
        await OllamaClient(model="m", host="http://x").chat("s", [{"role": "user", "content": "hi"}])
