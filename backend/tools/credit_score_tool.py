import time
from backend.llm.llm_engine import safe_json_llm
from backend.logger import log_tool_usage
from backend.tools.customer_context_builder import build_customer_context


def credit_score_tool(customer_id: int):
    start = time.time()

    try:
        context = build_customer_context(customer_id)

        system_prompt = """
        You are a senior credit risk analyst.

        You MUST base your decision ONLY on provided data.

        Return ONLY JSON:
        {
            "customer_id": int,
            "credit_score": number (300-850),
            "rating": "Poor" | "Fair" | "Good" | "Excellent",
            "risk_factors": [string],
            "positive_factors": [string],
            "loan_approval_likelihood": "LOW" | "MEDIUM" | "HIGH"
        }
        """

        user_prompt = f"""
        Analyze this customer financial profile:

        {context}
        """

        result = safe_json_llm(system_prompt, user_prompt)
        result["customer_id"] = customer_id

        log_tool_usage(
            user_query=f"credit_score_tool:{customer_id}",
            tool_name="credit_score_tool",
            input_data=context,
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        log_tool_usage(
            user_query=f"credit_score_tool:{customer_id}",
            tool_name="credit_score_tool",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise
