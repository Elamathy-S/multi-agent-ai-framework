"""
seed_data.py — populates finance_sim.db (SQLite) with realistic fake data.
Run once from the project root:  python data/seed_data.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from faker import Faker
from datetime import datetime, timedelta

from server.db import engine, SessionLocal, Base
from server.models.customer import Customer
from server.models.accounts import Account
from server.models.transactions import Transaction
from server.models.loans import Loan
from server.models.market import MarketPrice
from server.models.trade import Trade
from server.models.portfolio import Portfolio

fake = Faker()

# --- Config ---
NUM_CUSTOMERS = 50
NUM_ACCOUNTS_PER_CUSTOMER = 2
NUM_TRADES_PER_CUSTOMER = 20
STOCK_SYMBOLS = ["AAPL", "TSLA", "MSFT", "GOOG", "AMZN"]


def seed():
    # Create all tables (safe to run multiple times)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Guard: don't re-seed if data already exists
    if db.query(Customer).count() > 0:
        print("⚠️  Database already seeded. Delete finance_sim.db to re-seed.")
        db.close()
        return

    print("🌱 Seeding database...")

    # --- 1. Customers ---
    customer_ids = []
    for _ in range(NUM_CUSTOMERS):
        c = Customer(
            name=fake.name(),
            email=fake.email(),
            created_at=fake.date_this_decade()
        )
        db.add(c)
        db.flush()  # get auto-generated id
        customer_ids.append(c.id)

    # --- 2. Accounts ---
    account_ids = []
    for cid in customer_ids:
        for _ in range(NUM_ACCOUNTS_PER_CUSTOMER):
            a = Account(
                customer_id=cid,
                balance=round(random.uniform(1000, 100000), 2),
                account_type=random.choice(["checking", "savings"]),
                status="active"
            )
            db.add(a)
            db.flush()
            account_ids.append(a.id)

    # --- 3. Transactions ---
    TRANSACTION_DESCRIPTIONS = {
        "deposit": [
            "Salary deposit", "Freelance payment received", "Bank transfer in",
            "Direct deposit payroll", "Investment dividend received",
            "Tax refund deposit", "Insurance reimbursement", "Rental income",
        ],
        "withdrawal": [
            "ATM cash withdrawal", "Grocery store purchase", "Online shopping",
            "Utility bill payment", "Restaurant dining", "Fuel station",
            "Pharmacy purchase", "Subscription service charge",
            "Medical bill payment", "Rent payment",
        ],
        "transfer": [
            "Transfer to savings account", "Transfer to checking account",
            "Wire transfer sent", "Inter-bank transfer",
            "Loan repayment transfer", "Bill pay transfer",
        ],
    }
    for aid in account_ids:
        for _ in range(10):
            txn_type = random.choice(["deposit", "withdrawal", "transfer"])
            db.add(Transaction(
                account_id=aid,
                amount=round(random.uniform(50, 5000), 2),
                type=txn_type,
                description=random.choice(TRANSACTION_DESCRIPTIONS[txn_type]),
                timestamp=fake.date_time_between(start_date="-1y", end_date="now")
            ))

    # --- 4. Loans ---
    for cid in customer_ids:
        if random.random() < 0.4:
            db.add(Loan(
                customer_id=cid,
                amount=round(random.uniform(5000, 50000), 2),
                interest_rate=round(random.uniform(3, 12), 2),
                status=random.choice(["approved", "pending", "rejected"])
            ))

    # --- 5. Market Prices (90 days to keep DB small) ---
    today = datetime.now()
    for symbol in STOCK_SYMBOLS:
        base_price = random.uniform(100, 1000)
        for day in range(90):
            base_price += random.uniform(-15, 15)
            base_price = max(10, base_price)
            db.add(MarketPrice(
                symbol=symbol,
                price=round(base_price, 2),
                timestamp=today - timedelta(days=day)
            ))

    # --- 6. Trades & Portfolio ---
    for cid in customer_ids:
        holdings: dict[str, int] = {}
        for _ in range(NUM_TRADES_PER_CUSTOMER):
            symbol = random.choice(STOCK_SYMBOLS)
            trade_type = random.choice(["BUY", "SELL"])
            quantity = random.randint(1, 100)
            price = round(random.uniform(50, 1000), 2)
            db.add(Trade(
                customer_id=cid,
                symbol=symbol,
                quantity=quantity,
                price=price,
                trade_time=fake.date_time_between(start_date="-1y", end_date="now")
            ))
            if trade_type == "BUY":
                holdings[symbol] = holdings.get(symbol, 0) + quantity
            else:
                holdings[symbol] = max(0, holdings.get(symbol, 0) - quantity)

        for symbol, qty in holdings.items():
            if qty > 0:
                db.add(Portfolio(
                    customer_id=cid,
                    symbol=symbol,
                    quantity=qty,
                    avg_purchase_price=round(random.uniform(50, 1000), 2)
                ))

    db.commit()
    db.close()
    print(f"✅ Seeded {NUM_CUSTOMERS} customers, accounts, loans, trades, market prices.")


if __name__ == "__main__":
    seed()