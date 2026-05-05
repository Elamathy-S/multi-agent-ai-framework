import time
import random
from sqlalchemy.orm import Session
from server.models.loans import Loan
from server.db import SessionLocal
from server.logger import log_tool_usage


def check_loan_status(customer_id: int):
    start = time.time()
    db: Session = SessionLocal()

    try:
        loans = db.query(Loan).filter(Loan.customer_id == customer_id).all()

        result = [
            {
                "loan_id": l.id,
                "amount": float(l.amount),
                "interest_rate": float(l.interest_rate),
                "status": l.status
            }
            for l in loans
        ]

        log_tool_usage(
            user_query=f"check_loan_status:{customer_id}",
            tool_name="check_loan_status",
            input_data={"customer_id": customer_id},
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        log_tool_usage(
            user_query=f"check_loan_status:{customer_id}",
            tool_name="check_loan_status",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise

    finally:
        db.close()

def credit_score_tool(customer_id: int):
    start = time.time()

    try:
        from server.llm.llm_engine import safe_json_llm
        from server.tools.customer_context_builder import build_customer_context
        import json

        context = build_customer_context(customer_id)

        system_prompt = """
You are a credit analyst. Analyse the customer financial data and return a credit assessment.
Return ONLY a JSON object with exactly these fields:
{
  "customer_id": <integer>,
  "credit_score": <integer 300-850>,
  "rating": "Excellent" | "Good" | "Fair" | "Poor",
  "loan_approval_likelihood": "HIGH" | "MEDIUM" | "LOW",
  "factors": [<list of 2-3 brief strings explaining the score>]
}
"""
        user_prompt = f"Customer financial data:\n{json.dumps(context, indent=2)}"
        result = safe_json_llm(system_prompt, user_prompt)

        # If LLM failed, use rule-based fallback
        if "error" in result or "credit_score" not in result:
            loans    = context.get("loans", [])
            accounts = context.get("accounts", [])
            balance  = sum(float(a.get("balance", 0)) for a in accounts)
            score    = min(850, max(300, 500 + int(balance / 100) - len(loans) * 20))
            result = {
                "customer_id":             customer_id,
                "credit_score":            score,
                "rating":                  "Excellent" if score > 750 else "Good" if score > 650 else "Fair" if score > 550 else "Poor",
                "loan_approval_likelihood": "HIGH" if score > 700 else "MEDIUM" if score > 600 else "LOW",
                "factors":                 ["Based on account balance and loan history"],
            }

        result["customer_id"] = customer_id

        log_tool_usage(
            user_query=f"credit_score_tool:{customer_id}",
            tool_name="credit_score_tool",
            input_data={"customer_id": customer_id},
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