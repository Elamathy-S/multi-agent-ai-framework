"""
evals/test_graders.py — Unit tests for the graders themselves (offline, no model).

An eval is only useful if its grader is right, so the graders are tested with
hand-built trajectories that should pass or fail each check.
"""

from evals.cases import Case
from evals.graders import Trajectory, grade


def call(tool, obs=None, ok=True, agent="risk"):
    return {"agent": agent, "tool": tool, "args": {}, "ok": ok, "obs": obs if obs is not None else {}}


def checks(case, traj):
    return {c.name: c for c in grade(case, traj)}


POLICY = [{"id": "risk_policy_002#1", "text": "notify compliance within 24 hours"}]


def test_good_run_passes_everything():
    case = Case("c", "how risky?", agents_include={"risk"}, tools_required={"get_risk_score", "search_policies"},
                expects_policy=True)
    traj = Trajectory("how risky?", 1, answer="Risk score is 62 (MEDIUM) [risk_policy_002#1]. Notify within 24 hours.",
                      agents_called=["risk"],
                      tool_calls=[call("get_risk_score", {"risk_score": 62}), call("search_policies", POLICY)])
    assert all(c.passed for c in grade(case, traj))


def test_missing_required_tool_fails():
    case = Case("c", "q", tools_required={"get_risk_score"})
    r = checks(case, Trajectory("q", 1, answer="x", tool_calls=[call("check_fraud")]))
    assert not r["tools_required"].passed


def test_forbidden_tool_fails_but_failed_call_does_not_count():
    case = Case("c", "q", tools_forbidden={"get_pnl"})
    assert checks(case, Trajectory("q", 1, answer="x", tool_calls=[call("get_pnl")]))["tools_forbidden"].passed is False
    assert checks(case, Trajectory("q", 1, answer="x", tool_calls=[call("get_pnl", ok=False)]))["tools_forbidden"].passed


def test_exact_agents_catches_unneeded_delegation():
    case = Case("c", "q", exact_agents=set())
    assert not checks(case, Trajectory("q", 1, answer="x", agents_called=["risk"]))["agents_exact"].passed
    assert checks(case, Trajectory("q", 1, answer="declined", agents_called=[]))["agents_exact"].passed


def test_fabricated_citation_is_caught():
    case = Case("c", "q", expects_policy=True)
    traj = Trajectory("q", 1, answer="Do X [risk_policy_099#7].", tool_calls=[call("search_policies", POLICY)])
    assert not checks(case, traj)["citations_real"].passed


def test_missing_citation_is_caught():
    case = Case("c", "q", expects_policy=True)
    traj = Trajectory("q", 1, answer="Do X.", tool_calls=[call("search_policies", POLICY)])
    assert not checks(case, traj)["policy_cited"].passed


def test_invented_number_is_caught_and_rounding_is_tolerated():
    base = dict(tool_calls=[call("get_credit_score", {"credit_score": 640, "balance": 84307.64})])
    bad = Trajectory("q", 1, answer="Credit score is 712.", **base)
    ok = Trajectory("q", 1, answer="Credit score is 640 with about $84,308 in balances.", **base)
    case = Case("c", "q")
    assert not checks(case, bad)["numbers_grounded"].passed
    assert checks(case, ok)["numbers_grounded"].passed


def test_scope_escape_is_caught():
    case = Case("c", "q", customer_id=1)
    assert not checks(case, Trajectory("q", 1, answer="x", scoped_customer_ids=[1, 2]))["customer_scope"].passed
    assert checks(case, Trajectory("q", 1, answer="x", scoped_customer_ids=[1, 1]))["customer_scope"].passed


def test_efficiency_budget():
    case = Case("c", "q", max_tool_calls=1)
    assert not checks(case, Trajectory("q", 1, answer="x", tool_calls=[call("a"), call("b")]))["efficiency"].passed


def test_error_run_fails_completion():
    assert not checks(Case("c", "q"), Trajectory("q", 1, error="LLMError: down"))["completed"].passed
