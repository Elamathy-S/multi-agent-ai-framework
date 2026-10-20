"""
evals/run_evals.py — Eval runner with scored report.

Usage:
    PYTHONPATH=. python evals/run_evals.py

Runs all eval cases and prints a report like:

    ┌─────────────────────────────────────────────────┐
    │          EVAL REPORT — 2026-10-19               │
    ├──────────────────────┬────────┬────────┬────────┤
    │ Category             │ Passed │ Total  │ Score  │
    ├──────────────────────┼────────┼────────┼────────┤
    │ Routing              │   8    │   8    │ 100.0% │
    │ Tool Selection       │   8    │   8    │ 100.0% │
    │ RAG Retrieval        │   5    │   6    │  83.3% │
    │ Permissions          │   5    │   5    │ 100.0% │
    │ End-to-End           │   4    │   4    │ 100.0% │
    ├──────────────────────┼────────┼────────┼────────┤
    │ OVERALL              │  30    │  31    │  96.8% │
    └──────────────────────┴────────┴────────┴────────┘
"""

import json
import sys
from datetime import datetime

from evals.eval_dataset import (
    ROUTING_EVALS,
    TOOL_SELECTION_EVALS,
    RAG_EVALS,
    PERMISSION_EVALS,
    END_TO_END_EVALS,
)


# ---------------------------------------------------------------------------
# Eval runners — each returns (passed: bool, detail: str) per case
# ---------------------------------------------------------------------------

def eval_routing(case: dict) -> tuple[bool, str]:
    from client.agents.orchestrator import plan_agents
    selected = plan_agents(case["query"])

    for agent in case["expected_agents"]:
        if agent not in selected:
            return False, f"Missing agent '{agent}', got {selected}"

    for agent in case.get("not_expected_agents", []):
        if agent in selected:
            return False, f"Unexpected agent '{agent}' in {selected}"

    return True, f"Selected {selected}"


def eval_tool_selection(case: dict) -> tuple[bool, str]:
    agent_tools = _get_agent_tools(case["agent"])

    for tool in case["expected_tools"]:
        if tool not in agent_tools:
            return False, f"Agent '{case['agent']}' missing tool '{tool}'"

    for tool in case.get("not_expected_tools", []):
        if tool in agent_tools:
            return False, f"Agent '{case['agent']}' should not have '{tool}'"

    return True, f"Tools: {list(agent_tools.keys())}"


def eval_rag(case: dict) -> tuple[bool, str]:
    try:
        from rag.embedder import retrieve, index_count
    except ImportError:
        return False, "RAG dependencies not installed"

    if index_count() == 0:
        return False, "RAG index empty"

    results = retrieve(case["query"], n_results=3, category=case["category"])
    titles = [r["title"] for r in results]
    scores = [r["score"] for r in results]

    for expected_title in case["expected_titles"]:
        if not any(expected_title in t for t in titles):
            return False, f"Missing '{expected_title}', got {titles}"

    if results and max(scores) < case["min_score"]:
        return False, f"Best score {max(scores):.3f} < threshold {case['min_score']}"

    best = f"{max(scores):.3f}" if scores else "N/A"
    return True, f"Top: '{titles[0] if titles else 'none'}' (score={best})"


def eval_permissions(case: dict) -> tuple[bool, str]:
    from client.security.permissions import check_permission
    result = check_permission(case["agent"], case["tool"])

    if result == case["should_allow"]:
        action = "allowed" if result else "blocked"
        return True, f"{case['agent']} → {case['tool']}: {action}"
    else:
        expected = "allow" if case["should_allow"] else "block"
        return False, f"Expected {expected}, got {'allowed' if result else 'blocked'}"


def eval_end_to_end(case: dict) -> tuple[bool, str]:
    from client.agents.orchestrator import synthesise

    # Build mock agent results based on what the case needs
    mock_results = _build_mock_results(case)
    result = synthesise(case["query"], mock_results)
    result_lower = result.lower()

    for keyword in case.get("answer_must_contain", []):
        if keyword.lower() not in result_lower:
            return False, f"Missing '{keyword}' in answer"

    for keyword in case.get("answer_must_not_contain", []):
        if keyword.lower() in result_lower:
            return False, f"Unexpected '{keyword}' in answer"

    return True, f"Answer contains all expected keywords"


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_all_evals() -> dict:
    categories = [
        ("Routing",        ROUTING_EVALS,        eval_routing),
        ("Tool Selection", TOOL_SELECTION_EVALS,  eval_tool_selection),
        ("RAG Retrieval",  RAG_EVALS,             eval_rag),
        ("Permissions",    PERMISSION_EVALS,      eval_permissions),
        ("End-to-End",     END_TO_END_EVALS,      eval_end_to_end),
    ]

    report = {}
    total_passed = 0
    total_cases = 0

    print()
    print("=" * 60)
    print(f"  EVAL REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    for cat_name, cases, runner in categories:
        passed = 0
        failures = []

        print(f"\n  {cat_name}")
        print(f"  {'─' * 50}")

        for case in cases:
            try:
                ok, detail = runner(case)
            except Exception as e:
                ok, detail = False, f"Exception: {e}"

            status = "✅" if ok else "❌"
            print(f"    {status} {case['id']}: {case.get('description', '')}")
            if not ok:
                print(f"       → {detail}")
                failures.append({"id": case["id"], "detail": detail})
            if ok:
                passed += 1

        total = len(cases)
        pct = (passed / total * 100) if total else 0
        total_passed += passed
        total_cases += total

        report[cat_name] = {
            "passed": passed,
            "total": total,
            "score": round(pct, 1),
            "failures": failures,
        }

    # Summary table
    overall_pct = (total_passed / total_cases * 100) if total_cases else 0

    print()
    print("┌──────────────────────┬────────┬────────┬─────────┐")
    print("│ Category             │ Passed │ Total  │ Score   │")
    print("├──────────────────────┼────────┼────────┼─────────┤")

    for cat_name, data in report.items():
        name = cat_name.ljust(20)
        p = str(data["passed"]).center(6)
        t = str(data["total"]).center(6)
        s = f"{data['score']}%".rjust(7)
        print(f"│ {name} │ {p} │ {t} │ {s} │")

    print("├──────────────────────┼────────┼────────┼─────────┤")
    p = str(total_passed).center(6)
    t = str(total_cases).center(6)
    s = f"{overall_pct:.1f}%".rjust(7)
    print(f"│ {'OVERALL'.ljust(20)} │ {p} │ {t} │ {s} │")
    print("└──────────────────────┴────────┴────────┴─────────┘")
    print()

    # Save report to file
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "overall_score": round(overall_pct, 1),
        "total_passed": total_passed,
        "total_cases": total_cases,
        "categories": report,
    }

    with open("evals/eval_report.json", "w") as f:
        json.dump(report_data, f, indent=2)
    print(f"  Report saved to evals/eval_report.json")
    print()

    return report_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_agent_tools(agent_name: str) -> dict:
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


def _build_mock_results(case: dict) -> dict:
    """Build mock agent results for end-to-end synthesis eval."""
    mock = {}

    if any(k in case.get("answer_must_contain", []) for k in ["name", "email", "customer"]):
        mock["customer"] = {
            "observations": {
                "get_customer": {
                    "id": case.get("customer_id", 1),
                    "name": "Alice Test",
                    "email": "alice@test.com",
                    "created_at": "2024-01-15",
                }
            }
        }

    if any(k in case.get("answer_must_contain", []) for k in ["credit", "loan", "score"]):
        mock["loan"] = {
            "observations": {
                "get_credit_score": {
                    "credit_score": 720,
                    "rating": "Good",
                    "loan_approval_likelihood": "High",
                },
                "get_loan_status": [
                    {"amount": 10000, "status": "active", "interest_rate": 5.5}
                ],
            }
        }

    if any(k in case.get("answer_must_contain", []) for k in ["risk", "fraud"]):
        mock["risk"] = {
            "observations": {
                "get_risk_score": {
                    "risk_score": 42,
                    "level": "MEDIUM",
                    "key_risk_factors": ["transaction pattern"],
                    "recommendation": "Monitor closely",
                },
                "check_fraud": {
                    "fraud_flag": False,
                    "confidence": "HIGH",
                    "reason": "No suspicious patterns.",
                },
            }
        }

    if any(k in case.get("answer_must_contain", []) for k in ["portfolio", "trading", "pnl"]):
        mock["trading"] = {
            "observations": {
                "get_trading_portfolio": [
                    {"symbol": "AAPL", "quantity": 10, "avg_price": 150.0}
                ],
                "get_pnl": {"total_pnl": 500.0},
            }
        }

    return mock


if __name__ == "__main__":
    result = run_all_evals()
    sys.exit(0 if result["overall_score"] == 100.0 else 1)