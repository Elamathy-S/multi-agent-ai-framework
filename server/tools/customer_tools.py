import time
from sqlalchemy.orm import Session
from server.models.customer import Customer
from server.models.accounts import Account
from server.db import SessionLocal
from server.logger import log_tool_usage


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

def get_account_balance(customer_id: int, account_type: str = None):
    """Get account balance for a customer"""
    start = time.time()
    db: Session = SessionLocal()

    try:
        query = db.query(Account).filter(Account.customer_id == customer_id)
        
        if account_type:
            query = query.filter(Account.account_type == account_type)
        
        accounts = query.all()

        if not accounts:
            result = {"error": "No accounts found"}
            log_tool_usage(
                user_query=f"get_account_balance:{customer_id}",
                tool_name="get_account_balance",
                input_data={"customer_id": customer_id, "account_type": account_type},
                output_data=result,
                latency_ms=round((time.time() - start) * 1000, 2)
            )
            return result

        result = {
            "customer_id": customer_id,
            "accounts": [
                {
                    "id": acc.id,
                    "type": acc.account_type,
                    "balance": float(acc.balance),
                    "status": acc.status
                }
                for acc in accounts
            ],
            "total_balance": sum(float(acc.balance) for acc in accounts)
        }

        log_tool_usage(
            user_query=f"get_account_balance:{customer_id}",
            tool_name="get_account_balance",
            input_data={"customer_id": customer_id, "account_type": account_type},
            output_data=result,
            latency_ms=round((time.time() - start) * 1000, 2)
        )

        return result

    except Exception as e:
        log_tool_usage(
            user_query=f"get_account_balance:{customer_id}",
            tool_name="get_account_balance",
            input_data={"customer_id": customer_id, "account_type": account_type},
            output_data={"error": str(e)},
            latency_ms=round((time.time() - start) * 1000, 2)
        )
        raise

    finally:
        db.close()