import time
import random
from sqlalchemy.orm import Session
from backend.models.loans import Loan
from backend.db import SessionLocal
from backend.logger import log_tool_usage


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
        score = random.randint(300, 850)

        result = {
            "customer_id": customer_id,
            "credit_score": score,
            "rating": (
                "Excellent" if score > 750 else
                "Good" if score > 650 else
                "Fair" if score > 550 else
                "Poor"
            )
        }

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