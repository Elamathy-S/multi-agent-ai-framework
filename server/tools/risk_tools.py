"""
server/tools/risk_tools.py — Risk scoring and fraud screening tools.

Deterministic: see analytics.py. Interpretation against policy is the
agent's job, not the tool's.
"""

import time

from server.logger import log_tool_usage
from server.tools.analytics import compute_fraud, compute_risk
from server.tools.customer_context_builder import build_customer_context


def _run(tool: str, customer_id: int, fn) -> dict:
    start = time.time()
    try:
        result = {"customer_id": customer_id, **fn(build_customer_context(customer_id))}
    except Exception as exc:
        log_tool_usage(f"{tool}:{customer_id}", tool, {"customer_id": customer_id},
                       {"error": str(exc)}, round((time.time() - start) * 1000, 2))
        raise
    log_tool_usage(f"{tool}:{customer_id}", tool, {"customer_id": customer_id},
                   result, round((time.time() - start) * 1000, 2))
    return result


def risk_score_tool(customer_id: int) -> dict:
    """Risk score 0-100 with a per-component breakdown."""
    return _run("risk_score_tool", customer_id, compute_risk)


def fraud_check_tool(customer_id: int) -> dict:
    """Rule-based fraud screen over the customer's transactions."""
    return _run("fraud_check_tool", customer_id, compute_fraud)
