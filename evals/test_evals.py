"""
evals/test_evals.py — AI decision quality evaluations.

Unlike unit tests (deterministic, code correctness), evals measure
whether the AI makes good decisions:
  - Does the orchestrator pick the right agents?
  - Do agents call the right tools?
  - Does RAG retrieve relevant policies?
  - Does the permission system block cross-agent access?
  - Does the final answer contain the expected information?

Run offline evals (no servers needed):
    PYTHONPATH=. pytest evals/ -v

Run full evals (needs MCP server + Ollama):
    PYTHONPATH=. pytest evals/ -v --run-integration
"""

import pytest
from evals.eval_dataset import (
    ROUTING_EVALS,
    TOOL_SELECTION_EVALS,
    RAG_EVALS,
    PERMISSION_EVALS,
    END_TO_END_EVALS,
)


# ---------------------------------------------------------------------------
# 1. ROUTING EVALS — does plan_agents select the right agents?
# ---------------------------------------------------------------------------
class TestRoutingEvals:
    """Evaluate orchestrator agent selection accuracy."""

    @pytest.mark.parametrize(
        "case",
        ROUTING_EVALS,
        ids=[e["id"] for e in ROUTING_EVALS],
    )
    def test_agent_routing(self, case):
        from client.agents.orchestrator import plan_agents

        selected = plan_agents(case["query"])

        for agent in case["expected_agents"]:
            assert agent in selected, (
                f"[{case['id']}] Expected '{agent}' for query '{case['query']}', "
                f"got {selected}. {case['description']}"
            )

        for agent in case.get("not_expected_agents", []):
            assert agent not in selected, (
                f"[{case['id']}] '{agent}' should NOT be selected for '{case['query']}'. "
                f"{case['description']}"
            )


# ---------------------------------------------------------------------------
# 2. RAG RETRIEVAL EVALS — are the right policies retrieved?
# ---------------------------------------------------------------------------
class TestRAGEvals:
    """Evaluate RAG retrieval quality — correct policies at sufficient scores."""

    @pytest.mark.parametrize(
        "case",
        RAG_EVALS,
        ids=[e["id"] for e in RAG_EVALS],
    )
    def test_rag_retrieval(self, case):
        try:
            from rag.embedder import retrieve, index_count
        except ImportError:
            pytest.skip("RAG dependencies not installed")

        if index_count() == 0:
            pytest.skip("RAG index not built — run: PYTHONPATH=. python3 rag/build_index.py")

        results = retrieve(case["query"], n_results=3, category=case["category"])
        titles = [r["title"] for r in results]
        scores = [r["score"] for r in results]

        # Check that expected policies are retrieved
        for expected_title in case["expected_titles"]:
            assert any(expected_title in t for t in titles), (
                f"[{case['id']}] Expected policy '{expected_title}' not found. "
                f"Got: {titles}. {case['description']}"
            )

        # Check minimum relevance score
        if results:
            assert max(scores) >= case["min_score"], (
                f"[{case['id']}] Best score {max(scores):.3f} below threshold "
                f"{case['min_score']}. {case['description']}"
            )


# ---------------------------------------------------------------------------
# 3. PERMISSION ENFORCEMENT EVALS
# ---------------------------------------------------------------------------
class TestPermissionEvals:
    """Evaluate that the permission matrix correctly gates agent-tool access."""

    @pytest.mark.parametrize(
        "case",
        PERMISSION_EVALS,
        ids=[e["id"] for e in PERMISSION_EVALS],
    )
    def test_permission_enforcement(self, case):
        from client.security.permissions import check_permission

        result = check_permission(case["agent"], case["tool"])

        if case["should_allow"]:
            assert result is True, (
                f"[{case['id']}] {case['agent']} should be allowed to call {case['tool']}. "
                f"{case['description']}"
            )
        else:
            assert result is False, (
                f"[{case['id']}] {case['agent']} must NOT call {case['tool']}. "
                f"{case['description']}"
            )


# ---------------------------------------------------------------------------
# 4. TOOL SELECTION EVALS — do agents call the expected tools?
#    (Offline: checks the fallback path which calls all agent tools)
# ---------------------------------------------------------------------------
class TestToolSelectionEvals:
    """
    Evaluate that each agent's tool set covers what the query needs.
    Offline version: verifies the tool is in the agent's TOOLS dict.
    """

    @pytest.mark.parametrize(
        "case",
        TOOL_SELECTION_EVALS,
        ids=[e["id"] for e in TOOL_SELECTION_EVALS],
    )
    def test_tool_coverage(self, case):
        agent_tools = _get_agent_tools(case["agent"])

        for tool in case["expected_tools"]:
            assert tool in agent_tools, (
                f"[{case['id']}] Agent '{case['agent']}' needs tool '{tool}' "
                f"but only has {list(agent_tools.keys())}. {case['description']}"
            )

        for tool in case.get("not_expected_tools", []):
            assert tool not in agent_tools, (
                f"[{case['id']}] Agent '{case['agent']}' should NOT have tool '{tool}'. "
                f"{case['description']}"
            )


# ---------------------------------------------------------------------------
# 5. END-TO-END SYNTHESIS EVALS — does synthesise produce correct output?
# ---------------------------------------------------------------------------
class TestEndToEndEvals:
    """
    Evaluate that synthesise() output contains the expected information
    given mock agent results.
    """

    def test_customer_answer_content(self):
        """Customer query answer should contain profile fields."""
        from client.agents.orchestrator import synthesise

        result = synthesise("who is customer 1", {
            "customer": {
                "observations": {
                    "get_customer": {
                        "id": 1, "name": "Alice", "email": "alice@test.com",
                        "created_at": "2024-01-15"
                    }
                }
            }
        })
        result_lower = result.lower()
        assert "alice" in result_lower, "Answer should contain customer name"
        assert "alice@test.com" in result_lower, "Answer should contain email"

    def test_risk_answer_content(self):
        """Risk query answer should contain score and level."""
        from client.agents.orchestrator import synthesise

        result = synthesise("check risk", {
            "risk": {
                "observations": {
                    "get_risk_score": {
                        "risk_score": 72, "level": "HIGH",
                        "key_risk_factors": ["large transactions"],
                        "recommendation": "Enhanced due diligence required"
                    },
                    "check_fraud": {
                        "fraud_flag": False, "confidence": "HIGH",
                        "reason": "No suspicious patterns."
                    }
                }
            }
        })
        assert "72" in result, "Answer should contain risk score"
        assert "HIGH" in result, "Answer should contain risk level"
        assert "Clear" in result or "clear" in result.lower(), "Answer should show no fraud"

    def test_full_analysis_covers_all_domains(self):
        """Full analysis should have sections for every agent."""
        from client.agents.orchestrator import synthesise

        result = synthesise("full analysis", {
            "customer": {
                "observations": {
                    "get_customer": {"id": 1, "name": "Alice", "email": "a@b.com", "created_at": "2024-01-01"}
                }
            },
            "loan": {
                "observations": {
                    "get_credit_score": {"credit_score": 720, "rating": "Good",
                                         "loan_approval_likelihood": "High"},
                    "get_loan_status": [{"amount": 5000, "status": "active"}]
                }
            },
            "risk": {
                "observations": {
                    "get_risk_score": {"risk_score": 35, "level": "LOW",
                                       "key_risk_factors": [], "recommendation": "Monitor"},
                    "check_fraud": {"fraud_flag": False, "confidence": "HIGH", "reason": "Clean."}
                }
            },
            "trading": {
                "observations": {
                    "get_trading_portfolio": [{"symbol": "AAPL", "quantity": 10, "avg_price": 150}],
                    "get_pnl": {"total_pnl": 500.0}
                }
            },
        })

        result_lower = result.lower()
        assert "alice" in result_lower, "Should contain customer name"
        assert "720" in result, "Should contain credit score"
        assert "35" in result, "Should contain risk score"
        assert "aapl" in result_lower, "Should contain portfolio holdings"

    def test_error_handling_in_output(self):
        """Errors from tools should appear in output, not crash."""
        from client.agents.orchestrator import synthesise

        result = synthesise("check risk", {
            "risk": {
                "observations": {
                    "get_risk_score": {"error": "MCP server unreachable"},
                }
            }
        })
        assert "unreachable" in result.lower(), "Error should surface in the answer"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _get_agent_tools(agent_name: str) -> dict:
    """Import an agent's TOOLS dict by name."""
    if agent_name == "customer":
        from client.agents.customer_agent import TOOLS
    elif agent_name == "loan":
        from client.agents.loan_agent import TOOLS
    elif agent_name == "risk":
        from client.agents.risk_agent import TOOLS
    elif agent_name == "trading":
        from client.agents.trading_agent import TOOLS
    else:
        raise ValueError(f"Unknown agent: {agent_name}")
    return TOOLS