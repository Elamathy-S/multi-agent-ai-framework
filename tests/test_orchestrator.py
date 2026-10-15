"""
tests/test_orchestrator.py — Unit tests for the orchestrator.

Tests plan_agents (query routing) and synthesise (output formatting).
These run without Ollama or MCP — pure logic tests.
"""

import pytest
from client.agents.orchestrator import plan_agents, synthesise


# ---------------------------------------------------------------------------
# plan_agents — decides which agents handle a query
# ---------------------------------------------------------------------------
class TestPlanAgents:

    def test_full_analysis_calls_all_agents(self):
        agents = plan_agents("give me a full analysis of this customer")
        assert set(agents) == {"customer", "loan", "risk", "trading"}

    def test_overview_calls_all_agents(self):
        agents = plan_agents("complete overview please")
        assert set(agents) == {"customer", "loan", "risk", "trading"}

    def test_risk_query_includes_risk(self):
        agents = plan_agents("what is the risk level")
        assert "risk" in agents

    def test_fraud_query_includes_risk(self):
        agents = plan_agents("is there any fraud")
        assert "risk" in agents

    def test_loan_query_includes_loan(self):
        agents = plan_agents("check loan status")
        assert "loan" in agents

    def test_credit_query_includes_loan(self):
        agents = plan_agents("what is the credit score")
        assert "loan" in agents

    def test_portfolio_query_includes_trading(self):
        agents = plan_agents("show me the portfolio")
        assert "trading" in agents

    def test_profit_query_includes_trading(self):
        agents = plan_agents("how much profit has been made")
        assert "trading" in agents

    def test_customer_query_includes_customer(self):
        agents = plan_agents("who is this customer")
        assert "customer" in agents

    def test_multi_topic_query(self):
        agents = plan_agents("check the loan and risk for this customer")
        assert "loan" in agents
        assert "risk" in agents

    def test_unknown_query_defaults_to_customer(self):
        agents = plan_agents("xyzzy")
        assert "customer" in agents


# ---------------------------------------------------------------------------
# synthesise — formats agent results into readable output
# ---------------------------------------------------------------------------
class TestSynthesise:

    def test_empty_results(self):
        result = synthesise("test", {})
        assert "no data" in result.lower()

    def test_customer_section(self, sample_customer):
        agent_results = {
            "customer": {
                "observations": {"get_customer": sample_customer},
            }
        }
        result = synthesise("who is customer 1", agent_results)
        assert "Alice" in result
        assert "alice@example.com" in result

    def test_risk_section(self, sample_risk, sample_fraud_clear):
        agent_results = {
            "risk": {
                "observations": {
                    "get_risk_score": sample_risk,
                    "check_fraud":    sample_fraud_clear,
                },
            }
        }
        result = synthesise("check risk", agent_results)
        assert "35" in result           # risk score
        assert "LOW" in result          # risk level
        assert "Clear" in result        # no fraud

    def test_fraud_flagged_shows_warning(self, sample_risk, sample_fraud_flagged):
        agent_results = {
            "risk": {
                "observations": {
                    "get_risk_score": sample_risk,
                    "check_fraud":    sample_fraud_flagged,
                },
            }
        }
        result = synthesise("check fraud", agent_results)
        assert "FLAGGED" in result

    def test_loan_section(self, sample_credit, sample_loans):
        agent_results = {
            "loan": {
                "observations": {
                    "get_credit_score": sample_credit,
                    "get_loan_status":  sample_loans,
                },
            }
        }
        result = synthesise("loan check", agent_results)
        assert "720" in result          # credit score
        assert "Good" in result         # rating
        assert "2" in result            # number of loans
        assert "$15,000" in result      # total amount

    def test_trading_section(self, sample_portfolio, sample_pnl):
        agent_results = {
            "trading": {
                "observations": {
                    "get_trading_portfolio": sample_portfolio,
                    "get_pnl":              sample_pnl,
                },
            }
        }
        result = synthesise("portfolio check", agent_results)
        assert "AAPL" in result
        assert "TSLA" in result
        assert "1,250.50" in result     # total PnL

    def test_multi_agent_result(self, sample_customer, sample_risk, sample_fraud_clear):
        agent_results = {
            "customer": {
                "observations": {"get_customer": sample_customer},
            },
            "risk": {
                "observations": {
                    "get_risk_score": sample_risk,
                    "check_fraud":    sample_fraud_clear,
                },
            },
        }
        result = synthesise("full analysis", agent_results)
        assert "Alice" in result        # customer section
        assert "35" in result           # risk section
        assert "Clear" in result        # fraud section

    def test_handles_error_observations(self):
        agent_results = {
            "risk": {
                "observations": {
                    "get_risk_score": {"error": "Permission denied"},
                },
            }
        }
        result = synthesise("check risk", agent_results)
        assert "Permission denied" in result

    def test_handles_unknown_tool_gracefully(self):
        """New tools that don't have a formatter should not crash."""
        agent_results = {
            "customer": {
                "observations": {
                    "some_future_tool": {"foo": "bar", "count": 42},
                },
            }
        }
        result = synthesise("test", agent_results)
        assert "foo" in result
        assert "42" in result

    def test_empty_loans_shows_none_on_record(self):
        agent_results = {
            "loan": {
                "observations": {
                    "get_loan_status": [],
                },
            }
        }
        result = synthesise("loan check", agent_results)
        assert "None" in result or "No" in result.lower()