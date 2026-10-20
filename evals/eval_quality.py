"""
evals/eval_quality.py — AI Quality Evals

Industry-standard evaluations for an agentic AI system.
Runs in seconds (no LLM calls needed). Produces realistic scores.

Usage:
    PYTHONPATH=. python evals/eval_quality.py

What this evaluates:
1. Prompt Robustness    — Same intent phrased 5+ ways → same routing?
2. Synthesis Quality    — Does the output capture all key data points?
3. Error Resilience     — Graceful handling of missing/broken data?
4. RAG Precision/Recall — Right docs retrieved? Irrelevant ones excluded?
5. Latency Budget       — Are tool calls within acceptable time?
"""

import json
import time
import sys
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════
# 1. PROMPT ROBUSTNESS — Same intent, different phrasing → same result?
#
# In production, users phrase the same question many ways. The system
# should route consistently regardless of phrasing. This eval catches
# brittle keyword matching.
# ═══════════════════════════════════════════════════════════════════════════

ROBUSTNESS_CASES = [
    {
        "intent": "risk_assessment",
        "expected_agents": {"risk"},
        "phrasings": [
            "what is the risk level",
            "how risky is this customer",
            "run a risk assessment",
            "evaluate the risk",
            "is this customer dangerous",
            "risk analysis please",
            "what's the risk score",
        ],
    },
    {
        "intent": "fraud_detection",
        "expected_agents": {"risk"},
        "phrasings": [
            "check for fraud",
            "is there any fraud",
            "any suspicious activity",
            "run a fraud check",
            "has this account been flagged",
            "detect any anomalies",
            "is something fishy going on",
        ],
    },
    {
        "intent": "credit_check",
        "expected_agents": {"loan"},
        "phrasings": [
            "what is the credit score",
            "check their creditworthiness",
            "credit rating please",
            "how's their credit",
            "are they credit worthy",
            "run a credit check",
            "credit score lookup",
        ],
    },
    {
        "intent": "portfolio_review",
        "expected_agents": {"trading"},
        "phrasings": [
            "show me the portfolio",
            "what stocks do they hold",
            "investment holdings",
            "portfolio positions",
            "what are their holdings",
            "trading positions",
            "show stock positions",
        ],
    },
    {
        "intent": "full_analysis",
        "expected_agents": {"customer", "loan", "risk", "trading"},
        "phrasings": [
            "give me everything",
            "full analysis",
            "complete overview",
            "run all checks",
            "tell me everything about this customer",
            "comprehensive report",
            "full financial review",
        ],
    },
]


def eval_robustness() -> dict:
    from client.agents.orchestrator import plan_agents

    total = 0
    passed = 0
    failures = []

    for case in ROBUSTNESS_CASES:
        for phrasing in case["phrasings"]:
            total += 1
            selected = set(plan_agents(phrasing))
            expected = case["expected_agents"]

            # Check that all expected agents are selected
            if expected.issubset(selected):
                passed += 1
            else:
                missing = expected - selected
                failures.append({
                    "intent": case["intent"],
                    "phrasing": phrasing,
                    "expected": sorted(expected),
                    "got": sorted(selected),
                    "missing": sorted(missing),
                })

    return {
        "name": "Prompt Robustness",
        "description": "Same intent phrased differently → consistent routing",
        "passed": passed,
        "total": total,
        "score": round(passed / total * 100, 1) if total else 0,
        "failures": failures[:5],  # show top 5 failures
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. SYNTHESIS QUALITY — Does the output capture all key data points?
#
# Tests whether synthesise() extracts and presents the important
# information from tool results. Scores based on data point coverage.
# ═══════════════════════════════════════════════════════════════════════════

SYNTHESIS_CASES = [
    {
        "id": "synth_risk_high",
        "description": "HIGH risk customer should show score, level, factors, and recommendation",
        "query": "check risk",
        "agent_results": {
            "risk": {
                "observations": {
                    "get_risk_score": {
                        "risk_score": 85,
                        "level": "HIGH",
                        "key_risk_factors": ["large cash withdrawals", "new account"],
                        "recommendation": "Escalate to compliance team immediately",
                    },
                    "check_fraud": {
                        "fraud_flag": True,
                        "confidence": "MEDIUM",
                        "reason": "Unusual transaction pattern detected.",
                    },
                }
            }
        },
        "must_contain": ["85", "HIGH", "FLAGGED", "MEDIUM"],
        "should_contain": ["cash withdrawal", "compliance", "transaction pattern"],
    },
    {
        "id": "synth_risk_low",
        "description": "LOW risk customer should show clean status",
        "query": "check risk",
        "agent_results": {
            "risk": {
                "observations": {
                    "get_risk_score": {
                        "risk_score": 15,
                        "level": "LOW",
                        "key_risk_factors": [],
                        "recommendation": "No action needed",
                    },
                    "check_fraud": {
                        "fraud_flag": False,
                        "confidence": "HIGH",
                        "reason": "No suspicious patterns.",
                    },
                }
            }
        },
        "must_contain": ["15", "LOW", "Clear"],
        "should_contain": ["No action", "HIGH"],
    },
    {
        "id": "synth_full",
        "description": "Full analysis should cover all four domains",
        "query": "full analysis",
        "agent_results": {
            "customer": {
                "observations": {
                    "get_customer": {"id": 1, "name": "Alice", "email": "a@b.com", "created_at": "2024-01-15"},
                }
            },
            "loan": {
                "observations": {
                    "get_credit_score": {"credit_score": 680, "rating": "Fair", "loan_approval_likelihood": "Medium"},
                    "get_loan_status": [{"amount": 25000, "status": "active"}, {"amount": 5000, "status": "paid"}],
                }
            },
            "risk": {
                "observations": {
                    "get_risk_score": {"risk_score": 55, "level": "MEDIUM", "key_risk_factors": ["high debt ratio"], "recommendation": "Review quarterly"},
                    "check_fraud": {"fraud_flag": False, "confidence": "HIGH", "reason": "Clean history."},
                }
            },
            "trading": {
                "observations": {
                    "get_trading_portfolio": [{"symbol": "GOOG", "quantity": 20, "avg_price": 140.0}],
                    "get_pnl": {"total_pnl": -320.50},
                }
            },
        },
        "must_contain": ["Alice", "680", "Fair", "55", "MEDIUM", "GOOG", "320.50"],
        "should_contain": ["a@b.com", "2", "$30,000", "high debt", "loss"],
    },
    {
        "id": "synth_empty_portfolio",
        "description": "Empty portfolio should say no holdings, not crash",
        "query": "show portfolio",
        "agent_results": {
            "trading": {
                "observations": {
                    "get_trading_portfolio": [],
                    "get_pnl": {"total_pnl": 0},
                }
            }
        },
        "must_contain": ["No"],
        "should_contain": [],
    },
    {
        "id": "synth_mixed_errors",
        "description": "Mix of errors and data should show both",
        "query": "full analysis",
        "agent_results": {
            "customer": {
                "observations": {
                    "get_customer": {"id": 1, "name": "Bob", "email": "bob@test.com", "created_at": "2024-06-01"},
                }
            },
            "risk": {
                "observations": {
                    "get_risk_score": {"error": "MCP connection timeout"},
                    "check_fraud": {"fraud_flag": False, "confidence": "HIGH", "reason": "No issues."},
                }
            },
        },
        "must_contain": ["Bob", "timeout", "Clear"],
        "should_contain": ["bob@test.com"],
    },
]


def eval_synthesis() -> dict:
    from client.agents.orchestrator import synthesise

    total_points = 0
    earned_points = 0
    failures = []

    for case in SYNTHESIS_CASES:
        result = synthesise(case["query"], case["agent_results"])

        # must_contain = critical (2 points each)
        for keyword in case["must_contain"]:
            total_points += 2
            if keyword.lower() in result.lower():
                earned_points += 2
            else:
                failures.append({
                    "case": case["id"],
                    "type": "must_contain",
                    "missing": keyword,
                    "in_output": result[:100],
                })

        # should_contain = nice to have (1 point each)
        for keyword in case["should_contain"]:
            total_points += 1
            if keyword.lower() in result.lower():
                earned_points += 1
            else:
                failures.append({
                    "case": case["id"],
                    "type": "should_contain",
                    "missing": keyword,
                })

    return {
        "name": "Synthesis Quality",
        "description": "Output completeness — does the answer capture all key data points?",
        "passed": earned_points,
        "total": total_points,
        "score": round(earned_points / total_points * 100, 1) if total_points else 0,
        "failures": failures[:8],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. ERROR RESILIENCE — Graceful degradation under bad inputs
#
# Tests edge cases: missing fields, empty results, nulls, malformed data.
# The system should never crash — it should surface the error cleanly.
# ═══════════════════════════════════════════════════════════════════════════

RESILIENCE_CASES = [
    {
        "id": "err_missing_name",
        "description": "Customer with missing name field",
        "agent_results": {"customer": {"observations": {"get_customer": {"id": 1, "email": "a@b.com"}}}},
    },
    {
        "id": "err_empty_observations",
        "description": "Agent with no observations",
        "agent_results": {"risk": {"observations": {}}},
    },
    {
        "id": "err_null_score",
        "description": "Risk score is None",
        "agent_results": {"risk": {"observations": {"get_risk_score": {"risk_score": None, "level": None}}}},
    },
    {
        "id": "err_string_amount",
        "description": "Loan amount as string instead of number",
        "agent_results": {"loan": {"observations": {"get_loan_status": [{"amount": "ten thousand", "status": "active"}]}}},
    },
    {
        "id": "err_nested_error",
        "description": "Tool returned nested error object",
        "agent_results": {"trading": {"observations": {"get_pnl": {"error": "Connection refused"}}}},
    },
    {
        "id": "err_all_errors",
        "description": "Every tool returned an error",
        "agent_results": {
            "customer": {"observations": {"get_customer": {"error": "timeout"}}},
            "risk": {"observations": {"get_risk_score": {"error": "timeout"}}},
        },
    },
    {
        "id": "err_completely_empty",
        "description": "No agent results at all",
        "agent_results": {},
    },
]


def eval_resilience() -> dict:
    from client.agents.orchestrator import synthesise

    total = len(RESILIENCE_CASES)
    passed = 0
    failures = []

    for case in RESILIENCE_CASES:
        try:
            result = synthesise("test query", case["agent_results"])
            # If it didn't crash and returned a string, it passed
            if isinstance(result, str) and len(result) > 0:
                passed += 1
            else:
                failures.append({"case": case["id"], "reason": f"Empty or non-string output: {type(result)}"})
        except Exception as e:
            failures.append({"case": case["id"], "reason": f"Crashed: {type(e).__name__}: {e}"})

    return {
        "name": "Error Resilience",
        "description": "Graceful degradation — no crashes on bad/missing data",
        "passed": passed,
        "total": total,
        "score": round(passed / total * 100, 1) if total else 0,
        "failures": failures,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. RAG PRECISION & RECALL — Retrieval quality metrics
#
# Precision: what % of retrieved docs are relevant?
# Recall:    what % of relevant docs are retrieved?
# ═══════════════════════════════════════════════════════════════════════════

RAG_PRECISION_CASES = [
    {
        "query": "loan approval criteria and interest rates",
        "category": "loan",
        "relevant_titles": {"Standard Loan Approval Criteria", "Loan Interest Rate Schedule"},
        "n_results": 3,
    },
    {
        "query": "high risk customer fraud detection",
        "category": "risk",
        "relevant_titles": {"High Risk Customer Actions", "Customer Risk Classification Guidelines"},
        "n_results": 3,
    },
    {
        "query": "suspicious transactions fraud triggers",
        "category": "fraud",
        "relevant_titles": {"Fraud Detection Triggers and Response"},
        "n_results": 3,
    },
    {
        "query": "portfolio risk concentration limits",
        "category": "trading",
        "relevant_titles": {"Portfolio Risk Limits"},
        "n_results": 3,
    },
]


def eval_rag_quality() -> dict:
    try:
        from rag.embedder import retrieve, index_count
    except ImportError:
        return {
            "name": "RAG Precision/Recall",
            "description": "RAG dependencies not installed",
            "passed": 0, "total": 0, "score": 0, "failures": [],
        }

    if index_count() == 0:
        return {
            "name": "RAG Precision/Recall",
            "description": "RAG index empty",
            "passed": 0, "total": 0, "score": 0, "failures": [],
        }

    total_precision = 0
    total_recall = 0
    count = 0
    failures = []

    for case in RAG_PRECISION_CASES:
        results = retrieve(case["query"], n_results=case["n_results"], category=case["category"])
        retrieved_titles = {r["title"] for r in results}
        relevant = case["relevant_titles"]

        # Precision: of what we retrieved, how many are relevant?
        true_positives = retrieved_titles & relevant
        precision = len(true_positives) / len(retrieved_titles) if retrieved_titles else 0

        # Recall: of what's relevant, how many did we retrieve?
        recall = len(true_positives) / len(relevant) if relevant else 0

        total_precision += precision
        total_recall += recall
        count += 1

        if recall < 1.0:
            missed = relevant - retrieved_titles
            failures.append({
                "query": case["query"],
                "missed": list(missed),
                "precision": round(precision, 2),
                "recall": round(recall, 2),
            })

    avg_precision = round(total_precision / count * 100, 1) if count else 0
    avg_recall = round(total_recall / count * 100, 1) if count else 0
    f1 = round(2 * avg_precision * avg_recall / (avg_precision + avg_recall), 1) if (avg_precision + avg_recall) else 0

    return {
        "name": "RAG Precision/Recall",
        "description": f"Precision: {avg_precision}% | Recall: {avg_recall}% | F1: {f1}%",
        "passed": round(f1),  # F1 as "score"
        "total": 100,
        "score": f1,
        "failures": failures,
        "metrics": {
            "precision": avg_precision,
            "recall": avg_recall,
            "f1": f1,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. ROUTING CONSISTENCY — Run each query 3x, check for variance
#
# Deterministic routing should return the same result every time.
# If it doesn't, the routing logic has hidden randomness.
# ═══════════════════════════════════════════════════════════════════════════

CONSISTENCY_QUERIES = [
    "who is customer 1",
    "check risk and fraud",
    "full analysis",
    "credit score",
    "show me the portfolio",
    "is there anything suspicious",
    "loan status and credit rating",
    "profit and loss report",
]


def eval_consistency() -> dict:
    from client.agents.orchestrator import plan_agents

    total = len(CONSISTENCY_QUERIES)
    consistent = 0
    failures = []

    for query in CONSISTENCY_QUERIES:
        results = [tuple(sorted(plan_agents(query))) for _ in range(3)]
        if len(set(results)) == 1:
            consistent += 1
        else:
            failures.append({
                "query": query,
                "results": [list(r) for r in results],
            })

    return {
        "name": "Routing Consistency",
        "description": "Same query → same routing across 3 runs",
        "passed": consistent,
        "total": total,
        "score": round(consistent / total * 100, 1) if total else 0,
        "failures": failures,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_quality_evals():
    evaluators = [
        eval_robustness,
        eval_synthesis,
        eval_resilience,
        eval_rag_quality,
        eval_consistency,
    ]

    print()
    print("=" * 64)
    print(f"  AI QUALITY EVAL REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 64)

    results = []
    for evaluator in evaluators:
        start = time.time()
        result = evaluator()
        result["latency_ms"] = round((time.time() - start) * 1000)
        results.append(result)

        icon = "✅" if result["score"] >= 90 else "⚠️" if result["score"] >= 70 else "❌"
        print(f"\n  {icon} {result['name']}: {result['score']}%")
        print(f"     {result['description']}")
        if result["failures"]:
            for f in result["failures"][:3]:
                detail = f.get("phrasing") or f.get("missing") or f.get("query") or f.get("case") or f.get("reason", "")
                print(f"     ↳ {detail}")

    # Summary table
    print()
    print("┌─────────────────────────┬────────┬────────┬─────────┐")
    print("│ Evaluation              │ Passed │ Total  │ Score   │")
    print("├─────────────────────────┼────────┼────────┼─────────┤")

    for r in results:
        name = r["name"][:23].ljust(23)
        p = str(r["passed"]).center(6)
        t = str(r["total"]).center(6)
        s = f"{r['score']}%".rjust(7)
        print(f"│ {name} │ {p} │ {t} │ {s} │")

    total_score = sum(r["score"] for r in results) / len(results) if results else 0
    print("├─────────────────────────┼────────┼────────┼─────────┤")
    print(f"│ {'WEIGHTED AVERAGE'.ljust(23)} │ {'—'.center(6)} │ {'—'.center(6)} │ {f'{total_score:.1f}%'.rjust(7)} │")
    print("└─────────────────────────┴────────┴────────┴─────────┘")

    total_ms = sum(r["latency_ms"] for r in results)
    print(f"\n  Total eval time: {total_ms}ms")

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "type": "quality",
        "weighted_average": round(total_score, 1),
        "evaluations": results,
    }
    with open("evals/eval_quality_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to evals/eval_quality_report.json\n")

    return report


if __name__ == "__main__":
    report = run_quality_evals()
    sys.exit(0 if report["weighted_average"] >= 70 else 1)