"""
tests/test_orchestrator.py — Supervisor planning, delegation and synthesis.
"""

import pytest

from client.agents.orchestrator import plan, orchestrator
from llm import LLMError, LLMResponse, ToolCall
from llm.scripted import RoutedScriptedLLM, ScriptedLLM, say, tool_call


def delegate(*tasks, reasoning="because") -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall("p", "delegate", {"reasoning": reasoning, "tasks": [
            {"agent": a, "task": t} for a, t in tasks]})],
        stop_reason="tool_use",
    )


class TestPlanning:

    async def test_supervisor_delegates_with_task_per_specialist(self):
        llm = ScriptedLLM([delegate(("risk", "assess risk"), ("loan", "credit score"))])
        p = await plan(llm, "risk and credit?", 1)
        assert p.agents == ["risk", "loan"]
        assert p.tasks[0]["task"] == "assess risk"

    async def test_planner_is_given_the_roster_and_the_delegate_tool(self):
        llm = ScriptedLLM([delegate(("risk", "x"))])
        await plan(llm, "q", 3)
        req = llm.requests[0]
        assert req["tools"] == ["delegate"]
        assert all(name in req["system"] for name in ("customer", "loan", "risk", "trading"))
        assert "Customer ID: 3" in req["messages"][0]["content"]

    async def test_unknown_agents_and_duplicates_are_dropped(self):
        llm = ScriptedLLM([delegate(("risk", "a"), ("wizard", "b"), ("risk", "c"))])
        p = await plan(llm, "q", 1)
        assert p.agents == ["risk"]

    async def test_out_of_scope_question_gets_a_direct_reply(self):
        p = await plan(ScriptedLLM([say("I only help with customer finance.")]), "tell me a joke", 1)
        assert p.tasks == [] and p.direct_reply.startswith("I only help")

    async def test_no_plan_and_no_text_fails_loudly(self):
        with pytest.raises(LLMError):
            await plan(ScriptedLLM([LLMResponse()]), "q", 1)


class TestRun:

    def llm(self, **agents):
        return RoutedScriptedLLM(
            supervisor=[delegate(*[(a, f"{a} task") for a in agents])],
            agents=agents,
            synthesis=[say("Final combined answer.")],
        )

    async def test_runs_only_the_delegated_specialists(self, fake_mcp):
        llm = self.llm(risk=[tool_call("get_risk_score"), say("Risk MEDIUM 62")])
        out = await orchestrator("how risky?", 1, llm=llm, mcp=fake_mcp)
        assert out["agents_called"] == ["risk"]
        assert [c[0] for c in fake_mcp.calls] == ["get_risk_score"]
        assert out["answer"] == "Final combined answer."

    async def test_specialists_run_independently_with_their_own_tools(self, fake_mcp):
        llm = self.llm(
            risk=[tool_call("get_risk_score"), say("Risk MEDIUM")],
            loan=[tool_call("get_credit_score"), say("Credit 640")],
        )
        out = await orchestrator("full view", 1, llm=llm, mcp=fake_mcp)
        assert set(out["agent_results"]) == {"risk", "loan"}
        assert {c[0] for c in fake_mcp.calls} == {"get_risk_score", "get_credit_score"}

    async def test_synthesis_is_grounded_in_specialist_findings(self, fake_mcp):
        llm = self.llm(risk=[tool_call("get_risk_score"), say("Risk MEDIUM (62)")])
        await orchestrator("how risky?", 1, llm=llm, mcp=fake_mcp)
        synth_input = [r for r in llm.requests if r["who"] == "synthesis"][0]
        text = synth_input["messages"][0]["content"]
        assert "Risk MEDIUM (62)" in text and '"risk_score": 62' in text
        assert "ONLY the specialist reports" in synth_input["system"]

    async def test_one_failing_specialist_does_not_sink_the_run(self, fake_mcp):
        llm = RoutedScriptedLLM(
            supervisor=[delegate(("risk", "r"), ("loan", "l"))],
            agents={"loan": [say("Credit 640")]},       # risk has no script -> raises LLMError
            synthesis=[say("Partial answer.")],
        )
        out = await orchestrator("both", 1, llm=llm, mcp=fake_mcp)
        assert out["agent_results"]["risk"]["status"] == "error"
        assert out["agent_results"]["loan"]["status"] == "ok"
        synth = [r for r in llm.requests if r["who"] == "synthesis"][0]["messages"][0]["content"]
        assert "FAILED" in synth

    async def test_all_specialists_failing_skips_synthesis(self, fake_mcp):
        llm = RoutedScriptedLLM(supervisor=[delegate(("risk", "r"))], agents={})
        out = await orchestrator("q", 1, llm=llm, mcp=fake_mcp)
        assert out["answer"].startswith("I could not complete")
        assert not [r for r in llm.requests if r["who"] == "synthesis"]

    async def test_direct_reply_skips_all_agents(self, fake_mcp):
        out = await orchestrator("joke?", 1, llm=ScriptedLLM([say("Out of scope.")]), mcp=fake_mcp)
        assert out["answer"] == "Out of scope." and out["agents_called"] == [] and fake_mcp.calls == []

    async def test_permission_denials_are_surfaced(self, fake_mcp):
        llm = self.llm(risk=[tool_call("get_customer"), say("Could not read profile")])
        out = await orchestrator("who?", 1, llm=llm, mcp=fake_mcp)
        assert out["denials"][0]["tool"] == "get_customer"


class TestCitationGuard:
    """Regression: a weak model invented '[risk_policy_001#2]' that no agent had retrieved."""

    async def test_invented_citation_is_removed_and_flagged(self, fake_mcp):
        llm = RoutedScriptedLLM(
            supervisor=[delegate(("risk", "r"))],
            agents={"risk": [tool_call("search_policies", query="bands"), say("Medium risk [risk_policy_001#1]")]},
            synthesis=[say("Medium [risk_policy_001#1]. Must assess within 30 days [risk_policy_001#2].")],
        )
        out = await orchestrator("q", 1, llm=llm, mcp=fake_mcp)
        assert "[risk_policy_001#1]" in out["answer"]                 # really retrieved: kept
        assert "[risk_policy_001#2]" not in out["answer"]             # never retrieved: removed
        assert out["removed_citations"] == ["risk_policy_001#2"]

    async def test_failed_specialist_keeps_its_partial_trace_and_error(self, fake_mcp):
        llm = RoutedScriptedLLM(
            supervisor=[delegate(("risk", "r"))],
            agents={"risk": [tool_call("get_risk_score")]},           # then the model dies
            synthesis=[],
        )
        out = await orchestrator("q", 1, llm=llm, mcp=fake_mcp)
        risk = out["agent_results"]["risk"]
        assert risk["status"] == "error" and "No scripted response" in risk["error"]
        assert [s["action"] for s in risk["steps"]] == ["get_risk_score"]

    async def test_synthesis_is_told_which_passages_were_retrieved(self, fake_mcp):
        llm = RoutedScriptedLLM(
            supervisor=[delegate(("risk", "r"))],
            agents={"risk": [tool_call("search_policies", query="x"), say("ok")]},
            synthesis=[say("done")],
        )
        await orchestrator("q", 1, llm=llm, mcp=fake_mcp)
        synth = [r for r in llm.requests if r["who"] == "synthesis"][0]
        assert "Policy passages retrieved: risk_policy_001#1" in synth["messages"][0]["content"]
        assert "Never write a policy rule from memory" in synth["system"]
