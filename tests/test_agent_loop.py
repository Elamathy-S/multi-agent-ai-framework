"""
tests/test_agent_loop.py — The agent loop's behaviour, with a scripted model.

These tests pin down what the harness guarantees regardless of which model
runs: what the model is shown, what it may do, and how tool results flow back.
"""

import pytest

from client.agents.loop import MAX_OBSERVATION_CHARS, run_agent
from client.agents.specs import SPECIALISTS
from client.mcp.client import MCPToolError
from llm import LLMResponse, ToolCall
from llm.scripted import ScriptedLLM, say, tool_call

RISK = SPECIALISTS["risk"]


def last_tool_results(llm: ScriptedLLM) -> list:
    """Tool results the model saw on its most recent request."""
    tool_msgs = [m for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    return tool_msgs[-1]["results"]


class TestToolUseLoop:

    async def test_model_can_answer_without_any_tool(self, fake_mcp):
        llm = ScriptedLLM([say("Nothing to look up.")])
        res = await run_agent(RISK, llm, fake_mcp, "hello", 1)
        assert res.status == "ok" and res.answer == "Nothing to look up."
        assert fake_mcp.calls == []

    async def test_tool_result_is_fed_back_to_the_model(self, fake_mcp):
        llm = ScriptedLLM([tool_call("get_risk_score"), say("Risk is MEDIUM (62).")])
        res = await run_agent(RISK, llm, fake_mcp, "assess risk", 1)
        assert res.answer == "Risk is MEDIUM (62)."
        assert '"risk_score": 62' in last_tool_results(llm)[0].content
        assert res.observations["get_risk_score"]["risk_score"] == 62

    async def test_model_chooses_follow_up_tool_from_observation(self, fake_mcp):
        """The second call depends on what the first returned: this is the 'agentic' part."""
        def decide(system, messages, tools):
            seen = str(messages[-1])
            return tool_call("check_fraud", call_id="c2") if "MEDIUM" in seen else say("Low risk, done.")
        llm = ScriptedLLM([tool_call("get_risk_score"), decide, say("Medium risk with fraud flag.")])
        res = await run_agent(RISK, llm, fake_mcp, "assess", 1)
        assert [c[0] for c in fake_mcp.calls] == ["get_risk_score", "check_fraud"]
        assert res.answer == "Medium risk with fraud flag."

    async def test_parallel_tool_calls_in_one_turn(self, fake_mcp):
        two = LLMResponse(tool_calls=[ToolCall("a", "get_risk_score", {}), ToolCall("b", "check_fraud", {})],
                          stop_reason="tool_use")
        llm = ScriptedLLM([two, say("both done")])
        await run_agent(RISK, llm, fake_mcp, "x", 1)
        assert {c[0] for c in fake_mcp.calls} == {"get_risk_score", "check_fraud"}
        assert len(last_tool_results(llm)) == 2

    async def test_retrieved_policies_are_recorded(self, fake_mcp):
        llm = ScriptedLLM([tool_call("search_policies", query="medium risk"), say("See [risk_policy_001#1]")])
        res = await run_agent(RISK, llm, fake_mcp, "actions?", 1)
        assert res.policies == ["risk_policy_001#1"]


class TestWhatTheModelSees:

    async def test_only_permitted_tools_are_offered(self, fake_mcp):
        llm = ScriptedLLM([say("ok")])
        await run_agent(RISK, llm, fake_mcp, "x", 1)
        assert set(llm.requests[0]["tools"]) == {"get_risk_score", "check_fraud", "search_policies"}

    async def test_customer_id_is_not_exposed_to_the_model(self, fake_mcp):
        seen = {}
        def capture(system, messages, tools):
            seen["schemas"] = {t.name: t.schema for t in tools}
            return say("ok")
        await run_agent(RISK, ScriptedLLM([capture]), fake_mcp, "x", 1)
        assert "customer_id" not in seen["schemas"]["get_risk_score"].get("properties", {})
        assert "customer_id" not in seen["schemas"]["get_risk_score"].get("required", [])

    async def test_system_prompt_states_the_customer_and_grounding_rules(self, fake_mcp):
        llm = ScriptedLLM([say("ok")])
        await run_agent(RISK, llm, fake_mcp, "x", 7)
        system = llm.requests[0]["system"]
        assert "customer 7" in system and "Never invent" in system


class TestHarnessEnforcement:

    async def test_customer_id_is_forced_by_the_harness(self, fake_mcp):
        llm = ScriptedLLM([tool_call("get_risk_score", customer_id=99), say("ok")])
        await run_agent(RISK, llm, fake_mcp, "x", 1)
        assert fake_mcp.calls == [("get_risk_score", {"customer_id": 1})]

    async def test_tool_outside_role_is_blocked_and_audited(self, fake_mcp):
        llm = ScriptedLLM([tool_call("get_customer"), say("could not")])
        res = await run_agent(RISK, llm, fake_mcp, "who is it", 1)
        assert fake_mcp.calls == []                              # never reached MCP
        assert res.denials and res.denials[0]["tool"] == "get_customer"
        assert last_tool_results(llm)[0].is_error

    async def test_hallucinated_tool_name_is_reported_and_loop_recovers(self, fake_mcp):
        llm = ScriptedLLM([tool_call("do_magic"), tool_call("get_risk_score", call_id="c2"), say("recovered")])
        res = await run_agent(RISK, llm, fake_mcp, "x", 1)
        assert res.answer == "recovered"
        assert [c[0] for c in fake_mcp.calls] == ["get_risk_score"]

    async def test_tool_failure_is_returned_to_the_model_not_raised(self, fake_mcp):
        fake_mcp.handlers["get_risk_score"] = lambda customer_id: MCPToolError("db down")
        llm = ScriptedLLM([tool_call("get_risk_score"), say("Risk data unavailable.")])
        res = await run_agent(RISK, llm, fake_mcp, "x", 1)
        assert res.status == "ok"
        assert last_tool_results(llm)[0].is_error and "db down" in last_tool_results(llm)[0].content

    async def test_huge_tool_output_is_truncated(self, fake_mcp):
        fake_mcp.handlers["get_risk_score"] = lambda customer_id: {"blob": "x" * 50_000}
        llm = ScriptedLLM([tool_call("get_risk_score"), say("ok")])
        await run_agent(RISK, llm, fake_mcp, "x", 1)
        content = last_tool_results(llm)[0].content
        assert len(content) < MAX_OBSERVATION_CHARS + 50 and content.endswith("[truncated]")


class TestTermination:

    async def test_step_budget_forces_a_final_answer_without_tools(self, fake_mcp):
        loop_forever = [tool_call("get_risk_score", call_id=f"c{i}") for i in range(3)]
        llm = ScriptedLLM(loop_forever + [say("Best effort answer.")])
        res = await run_agent(RISK, llm, fake_mcp, "x", 1, max_steps=3)
        assert res.status == "max_steps" and res.answer == "Best effort answer."
        assert llm.requests[-1]["tools"] == []

    async def test_empty_answer_is_an_error_not_silent_success(self, fake_mcp):
        res = await run_agent(RISK, ScriptedLLM([say("")]), fake_mcp, "x", 1)
        assert res.status == "error"

    async def test_events_stream_in_order(self, fake_mcp):
        events = []
        llm = ScriptedLLM([tool_call("get_risk_score"), say("done")])
        await run_agent(RISK, llm, fake_mcp, "x", 1, on_event=events.append)
        assert [e["type"] for e in events] == ["tool_call", "tool_result", "final"]


class TestFailureKeepsTheTrace:
    """Regression: a model crash mid-run used to lose every step already taken."""

    async def test_crash_after_tools_keeps_steps_and_reports_the_error(self, fake_mcp):
        # Two tool calls succeed, then the model backend dies (script runs out -> LLMError).
        llm = ScriptedLLM([tool_call("get_risk_score"), tool_call("check_fraud", call_id="c2")])
        events = []
        res = await run_agent(RISK, llm, fake_mcp, "x", 1, on_event=events.append)
        assert res.status == "error"
        assert "ran out of scripted responses" in res.error
        assert [s["action"] for s in res.steps] == ["get_risk_score", "check_fraud"]
        assert set(res.observations) == {"get_risk_score", "check_fraud"}
        assert events[-1]["type"] == "agent_error"
