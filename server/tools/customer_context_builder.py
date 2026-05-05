"""
server/tools/customer_context_builder.py

Pulls a customer's loans, accounts, and recent transactions from the DB
and returns a structured dict that gets passed to the LLM as context.
"""

from server.db import SessionLocal
from server.models.loans import Loan
from server.models.transactions import Transaction
from server.models.accounts import Account


def build_customer_context(customer_id: int) -> dict:
    """
    Build a financial context dict for a customer.
    Used by credit_score_tool and any other tool that needs real data
    before calling the LLM.
    """
    db = SessionLocal()

    try:
        loans    = db.query(Loan).filter(Loan.customer_id == customer_id).all()
        accounts = db.query(Account).filter(Account.customer_id == customer_id).all()

        account_ids  = [a.id for a in accounts]
        transactions = []
        if account_ids:
            transactions = (
                db.query(Transaction)
                .filter(Transaction.account_id.in_(account_ids))
                .limit(20)   # cap for token safety
                .all()
            )

        return {
            "customer_id": customer_id,
            "loans": [
                {
                    "amount":        float(l.amount),
                    "interest_rate": float(l.interest_rate),
                    "status":        l.status,
                }
                for l in loans
            ],
            "accounts": [
                {
                    "balance":      float(a.balance),
                    "type":         a.account_type,
                    "status":       a.status,
                }
                for a in accounts
            ],
            "transactions_sample": [
                {
                    "amount":      float(t.amount),
                    "type":        t.type,
                    "description": t.description,
                }
                for t in transactions
            ],
        }

    finally:
        db.close()