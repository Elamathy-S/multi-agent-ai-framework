"""
server/tools/risk_tools.py

Risk scoring and fraud detection tools.
Now powered by the real LLM engine instead of random numbers.
"""

import time
import json
from server.llm.llm_engine import safe_json_llm
from server.logger import log_tool_usage
from server.tools.customer_context_builder import build_customer_context


def risk_score_tool(customer_id: int) -> dict:
    """
    Analyse a customer's financial profile and return a risk score + level.
    Uses Claude to reason over real account/loan/transaction data.
    """
    start = time.time()

    try:
        context = build_customer_context(customer_id)

        system_prompt = """
You are a senior financial risk analyst at a bank.
Analyse the customer's financial profile and return a risk assessment.

Return ONLY a JSON object with exactly these fields:
{
  "customer_id": <integer>,
  "risk_score": <integer 0-100, where 0=no risk, 100=extreme risk>,
  "level": "LOW" | "MEDIUM" | "HIGH",
  "key_risk_factors": [<list of concise strings explaining the score>],
  "recommendation": <one sentence on what action the bank should take>
}
"""

        user_prompt = (
            f"Customer financial profile:\n{json.dumps(context, indent=2)}"
        )

        result = safe_json_llm(system_prompt, user_prompt)
        result["customer_id"] = customer_id

        log_tool_usage(
            user_query=f"risk_score_tool:{customer_id}",
            tool_name="risk_score_tool",
            input_data=context,
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2),
        )

        return result

    except Exception as exc:
        log_tool_usage(
            user_query=f"risk_score_tool:{customer_id}",
            tool_name="risk_score_tool",
            input_data={"customer_id": customer_id},
            output_data={"error": str(exc)},
            latency_ms=round((time.time() - start) * 1000, 2),
        )
        raise


def fraud_check_tool(customer_id: int) -> dict:
    """
    Run a fraud screening on a customer based on their transaction patterns.
    Uses Claude to reason over real data instead of random True/False.
    """
    start = time.time()

    try:
        context = build_customer_context(customer_id)

        system_prompt = """
You are a fraud detection specialist at a financial institution.
Review the customer's transaction history and account activity.

Return ONLY a JSON object with exactly these fields:
{
  "customer_id": <integer>,
  "fraud_flag": <true | false>,
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "suspicious_patterns": [<list of strings — empty list if none>],
  "reason": <one sentence summary of your conclusion>
}
"""

        user_prompt = (
            f"Customer profile and transaction history:\n{json.dumps(context, indent=2)}"
        )

        result = safe_json_llm(system_prompt, user_prompt)
        result["customer_id"] = customer_id

        log_tool_usage(
            user_query=f"fraud_check_tool:{customer_id}",
            tool_name="fraud_check_tool",
            input_data=context,
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2),
        )

        return result

    except Exception as exc:
        log_tool_usage(
            user_query=f"fraud_check_tool:{customer_id}",
            tool_name="fraud_check_tool",
            input_data={"customer_id": customer_id},
            output_data={"error": str(exc)},
            latency_ms=round((time.time() - start) * 1000, 2),
        )
        raise