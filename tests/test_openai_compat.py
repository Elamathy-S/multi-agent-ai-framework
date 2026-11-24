"""
tests/test_openai_compat.py — The OpenAI-compatible adapter (used for Gemini, Groq, OpenRouter...).

Mocked HTTP only. The Gemini-specific cases come from documented behaviour:
Gemini 3 returns a thought signature on tool calls and answers 400 if it is not echoed back.
"""

import asyncio
import json

import httpx
import pytest

from llm import LLMError, ToolCall, ToolResult, ToolSpec, get_llm
from llm.openai_compat import SKIP_SIGNATURE, OpenAICompatClient

SIG = {"google": {"thought_signature": "abc123=="}}
SPEC = ToolSpec("get_risk_score", "Risk score",
                {"type": "object", "title": "Args", "properties": {"x": {"type": "integer", "title": "X"}}})
NO_ARGS = ToolSpec("list_things", "No args", {"type": "object", "properties": {}})


def client(handler, monkeypatch, **kw):
    real = httpx.AsyncClient
    monkeypatch.setattr("llm.openai_compat.httpx.AsyncClient",
                        lambda **k: real(transport=httpx.MockTransport(handler)))
    return OpenAICompatClient(base_url="https://x/v1/", api_key="K", model="m", retry_base=0, **kw)


def ok(message=None, **extra):
    return httpx.Response(200, json={
        "choices": [{"message": message or {"content": "hi"}, "finish_reason": extra.pop("finish", "stop")}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2}})


async def test_request_shape_and_schema_cleanup(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=json.loads(request.content))
        return ok()

    c = client(handler, monkeypatch, reasoning_effort="low", min_output_tokens=4096)
    await c.chat("sys", [{"role": "user", "content": "q"}], [SPEC, NO_ARGS], max_tokens=1024)

    assert seen["url"] == "https://x/v1/chat/completions" and seen["auth"] == "Bearer K"
    body = seen["body"]
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["max_tokens"] == 4096                       # floor for thinking models
    assert body["reasoning_effort"] == "low" and body["tool_choice"] == "auto"
    with_args, without = [t["function"] for t in body["tools"]]
    assert "title" not in json.dumps(with_args["parameters"])
    assert "parameters" not in without                      # empty-parameter tool omits the key


async def test_parses_tool_calls_arguments_usage_and_signature(monkeypatch):
    msg = {"content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "get_risk_score", "arguments": '{"x": 3}'}, "extra_content": SIG},
        {"id": "c2", "type": "function", "function": {"name": "check_fraud", "arguments": "not json"}}]}
    resp = await client(lambda r: ok(msg), monkeypatch).chat("s", [{"role": "user", "content": "q"}], [SPEC])
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls[0].args == {"x": 3} and resp.tool_calls[0].extra == SIG
    assert resp.tool_calls[1].args == {} and resp.tool_calls[1].extra is None   # bad JSON args don't crash
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (4, 2)


async def test_thought_signature_is_echoed_back_exactly(monkeypatch):
    seen = {}
    c = client(lambda r: (seen.update(body=json.loads(r.content)) or ok()), monkeypatch, gemini_signatures=True)
    convo = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "text": "", "tool_calls": [ToolCall("c1", "get_risk_score", {"x": 1}, extra=SIG),
                                                           ToolCall("c2", "check_fraud", {})]},
        {"role": "tool", "results": [ToolResult("c1", "get_risk_score", "{}"), ToolResult("c2", "check_fraud", "{}")]},
    ]
    await c.chat("s", convo, [SPEC])
    a, t1, t2 = seen["body"]["messages"][2:5]
    assert a["tool_calls"][0]["extra_content"] == SIG                 # echoed verbatim
    assert "extra_content" not in a["tool_calls"][1]                  # parallel calls: only the first carries one
    assert a["tool_calls"][0]["function"]["arguments"] == '{"x": 1}'
    assert t1["tool_call_id"] == "c1" and t2["tool_call_id"] == "c2" and t1["role"] == "tool"


async def test_missing_signature_falls_back_to_documented_skip_value_for_gemini(monkeypatch):
    seen = {}
    c = client(lambda r: (seen.update(body=json.loads(r.content)) or ok()), monkeypatch, gemini_signatures=True)
    convo = [{"role": "user", "content": "q"},
             {"role": "assistant", "text": "", "tool_calls": [ToolCall("c1", "get_risk_score", {})]},
             {"role": "tool", "results": [ToolResult("c1", "get_risk_score", "{}")]}]
    await c.chat("s", convo, [SPEC])
    assert seen["body"]["messages"][2]["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == SKIP_SIGNATURE


async def test_non_gemini_never_gets_extra_content(monkeypatch):
    seen = {}
    c = client(lambda r: (seen.update(body=json.loads(r.content)) or ok()), monkeypatch)
    convo = [{"role": "user", "content": "q"},
             {"role": "assistant", "text": "", "tool_calls": [ToolCall("c1", "get_risk_score", {})]},
             {"role": "tool", "results": [ToolResult("c1", "get_risk_score", "{}")]}]
    await c.chat("s", convo, [SPEC])
    assert "extra_content" not in seen["body"]["messages"][2]["tool_calls"][0]


async def test_rate_limit_is_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": "slow down"}) if calls["n"] < 3 else ok()

    resp = await client(handler, monkeypatch).chat("s", [{"role": "user", "content": "q"}])
    assert resp.text == "hi" and calls["n"] == 3


async def test_rate_limit_gives_up_with_actionable_message(monkeypatch):
    c = client(lambda r: httpx.Response(429, text="quota exceeded"), monkeypatch)
    with pytest.raises(LLMError, match="rate limit.*LLM_MAX_CONCURRENCY"):
        await c.chat("s", [{"role": "user", "content": "q"}])


async def test_retry_after_header_is_honoured(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("llm.openai_compat.asyncio.sleep", fake_sleep)
    n = {"i": 0}

    def handler(request):
        n["i"] += 1
        return httpx.Response(429, headers={"retry-after": "7"}) if n["i"] == 1 else ok()

    await client(handler, monkeypatch).chat("s", [{"role": "user", "content": "q"}])
    assert slept == [7.0]


@pytest.mark.parametrize("status,match", [(401, "rejected the API key"), (403, "rejected the API key"),
                                          (400, "Function call is missing a thought_signature")])
async def test_client_errors_are_not_retried_and_explain_themselves(monkeypatch, status, match):
    n = {"i": 0}

    def handler(request):
        n["i"] += 1
        return httpx.Response(status, text="Function call is missing a thought_signature")

    with pytest.raises(LLMError, match=match):
        await client(handler, monkeypatch).chat("s", [{"role": "user", "content": "q"}])
    assert n["i"] == 1


async def test_truncated_reply_is_reported(monkeypatch):
    resp = await client(lambda r: ok({"content": ""}, finish="length"), monkeypatch).chat("s", [{"role": "user", "content": "q"}])
    assert resp.stop_reason == "max_tokens"


async def test_concurrency_cap(monkeypatch):
    state = {"active": 0, "peak": 0}

    async def handler(request):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.03)
        state["active"] -= 1
        return ok()

    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "2")
    c = client(handler, monkeypatch)
    await asyncio.gather(*[c.chat("s", [{"role": "user", "content": "q"}]) for _ in range(6)])
    assert state["peak"] == 2


class TestFactory:

    def test_gemini_needs_a_key_and_says_where_to_get_one(self, monkeypatch):
        for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        with pytest.raises(LLMError, match="aistudio.google.com"):
            get_llm()

    def test_gemini_defaults(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        llm = get_llm()
        assert llm.model == "gemini-3.8-flash"
        assert llm._url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert llm._effort == "low" and llm._min_out == 4096 and llm._gemini is True

    def test_model_can_be_overridden(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setenv("LLM_MODEL", "gemini-3.1-flash-lite")
        assert get_llm().model == "gemini-3.1-flash-lite"

    def test_generic_provider_lists_missing_settings(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
        for v in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
            monkeypatch.delenv(v, raising=False)
        with pytest.raises(LLMError, match="LLM_BASE_URL, LLM_API_KEY, LLM_MODEL"):
            get_llm()