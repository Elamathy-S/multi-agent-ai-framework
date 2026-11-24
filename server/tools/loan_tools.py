import time
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
    """Credit score 300-850 from balances, open debt, rejections and cash flow."""
    from server.tools.analytics import compute_credit
    from server.tools.customer_context_builder import build_customer_context

    start = time.time()
    try:
        result = {"customer_id": customer_id, **compute_credit(build_customer_context(customer_id))}
    except Exception as e:
        log_tool_usage(
            user_query=f"credit_score_tool:{customer_id}",
            tool_name="credit_score_tool",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2),
        )
        raise
    log_tool_usage(
        user_query=f"credit_score_tool:{customer_id}",
        tool_name="credit_score_tool",
        input_data={"customer_id": customer_id},
        output_data=result,
        latency_ms=round((time.time() - start) * 1000, 2),
    )
    return result
