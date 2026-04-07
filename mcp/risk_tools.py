import random
import time
from backend.logger import log_tool_usage


def risk_score_tool(customer_id: int):
    start = time.time()

    try:
        score = random.randint(0, 100)

        result = {
            "customer_id": customer_id,
            "risk_score": score,
            "level": (
                "LOW" if score < 30 else
                "MEDIUM" if score < 70 else
                "HIGH"
            )
        }

        log_tool_usage(
            user_query=f"risk_score_tool:{customer_id}",
            tool_name="risk_score_tool",
            input_data={"customer_id": customer_id},
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        log_tool_usage(
            user_query=f"risk_score_tool:{customer_id}",
            tool_name="risk_score_tool",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise

def fraud_check_tool(customer_id: int):
    start = time.time()

    try:
        flag = random.choice([True, False])

        result = {
            "customer_id": customer_id,
            "fraud_flag": flag,
            "reason": "Unusual transaction pattern" if flag else "No anomalies detected"
        }

        log_tool_usage(
            user_query=f"fraud_check_tool:{customer_id}",
            tool_name="fraud_check_tool",
            input_data={"customer_id": customer_id},
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        log_tool_usage(
            user_query=f"fraud_check_tool:{customer_id}",
            tool_name="fraud_check_tool",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise