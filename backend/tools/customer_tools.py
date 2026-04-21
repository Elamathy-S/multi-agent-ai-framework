import time
from sqlalchemy.orm import Session
from backend.models.customer import Customer
from backend.db import SessionLocal
from backend.logger import log_tool_usage


def get_customer_profile(customer_id: int):
    start = time.time()
    db: Session = SessionLocal()

    try:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()

        if not customer:
            result = {"error": "Customer not found"}

            log_tool_usage(
                user_query=f"get_customer_profile:{customer_id}",
                tool_name="get_customer_profile",
                input_data={"customer_id": customer_id},
                output_data=result,
                latency_ms=round((time.time() - start) * 1000, 2)
            )

            return result

        result = {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "created_at": str(customer.created_at)
        }

        log_tool_usage(
            user_query=f"get_customer_profile:{customer_id}",
            tool_name="get_customer_profile",
            input_data={"customer_id": customer_id},
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        log_tool_usage(
            user_query=f"get_customer_profile:{customer_id}",
            tool_name="get_customer_profile",
            input_data={"customer_id": customer_id},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise

    finally:
        db.close()