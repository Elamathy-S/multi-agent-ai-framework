"""
tests/test_api_stream.py — The SSE contract the frontend depends on.

Runs the real FastAPI app and real MCP server with a scripted model, so it
verifies the wiring (events, payload shape) without needing an API key.
"""

import json

import httpx
import pytest

from llm import LLMResponse, ToolCall
from llm.scripted import RoutedScriptedLLM, say, tool_call

pytestmark = pytest.mark.integration


def scripted():
    plan = LLMResponse(tool_calls=[ToolCall("p", "delegate", {"reasoning": "risk question", "tasks": [
        {"agent": "risk", "task": "assess risk"}]})], stop_reason="tool_use")
    return RoutedScriptedLLM(
        supervisor=[plan],
        agents={"risk": [tool_call("get_risk_score"), say("Risk assessed.")]},
        synthesis=[say("Customer 1 risk assessed.")],
    )


async def read_events(client, url):
    events = []
    async with client.stream("GET", url) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def test_stream_emits_trace_then_done_payload(mcp, monkeypatch):
    from client import main
    monkeypatch.setattr(main, "get_llm", scripted)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        events = await read_events(client, "/agent/react/stream?message=how risky&customer_id=1")

    statuses = [e["status"] for e in events]
    assert statuses[0] == "start" and statuses[-1] == "done"
    assert {"thinking", "planned", "tool_call", "agent_done"} <= set(statuses)

    done = json.loads(events[-1]["detail"])
    assert done["reply"] == "Customer 1 risk assessed."
    assert done["agents_called"] == ["risk"] and done["tool_calls"] == 1
    assert done["steps"][0]["action"] == "get_risk_score" and "obs" in done["steps"][0]
    assert "risk_score" in done["raw"]["risk"]["get_risk_score"]


async def test_stream_reports_missing_llm_key_as_error(monkeypatch):
    from client import main
    from llm import LLMError

    def no_key():
        raise LLMError("ANTHROPIC_API_KEY is not set")
    monkeypatch.setattr(main, "get_llm", no_key)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        events = await read_events(client, "/agent/react/stream?message=hi&customer_id=1")
    assert events[-2]["status"] == "error"
    assert "ANTHROPIC_API_KEY" in json.loads(events[-1]["detail"])["error"]
