from backend.db import SessionLocal
from backend.models.loans import Loan
from backend.models.transactions import Transaction
from backend.models.accounts import Account


def build_customer_context(customer_id: int):
    db = SessionLocal()

    try:
        loans = db.query(Loan).filter(Loan.customer_id == customer_id).all()
        accounts = db.query(Account).filter(Account.customer_id == customer_id).all()

        # example: transactions via accounts
        account_ids = [a.id for a in accounts]

        transactions = []
        if account_ids:
            transactions = db.query(Transaction).filter(
                Transaction.account_id.in_(account_ids)
            ).all()

        return {
            "loans": [
                {
                    "amount": float(l.amount),
                    "interest_rate": float(l.interest_rate),
                    "status": l.status
                }
                for l in loans
            ],
            "accounts": [
                {
                    "balance": float(a.balance),
                    "type": a.account_type,
                    "status": a.status
                }
                for a in accounts
            ],
            "transactions_sample": [
                {
                    "amount": float(t.amount),
                    "type": t.type,
                    "description": t.description
                }
                for t in transactions[:20]   # limit for token safety
            ]
        }

    finally:
        db.close()
