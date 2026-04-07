import random
from faker import Faker
from datetime import datetime, timedelta
import psycopg2

fake = Faker()

# --- DB Connection ---
conn = psycopg2.connect(
    dbname="finance_sim",   
    user="elamathy",          
    password="elamathy",  
    host="localhost",
    port="5432"
)
cur = conn.cursor()

# --- Config ---
NUM_CUSTOMERS = 50
NUM_ACCOUNTS_PER_CUSTOMER = 2
NUM_TRADES_PER_CUSTOMER = 20
STOCK_SYMBOLS = ["AAPL", "TSLA", "MSFT", "GOOG", "AMZN"]

# --- 1. Customers ---
customers = []
for _ in range(NUM_CUSTOMERS):
    name = fake.name()
    email = fake.email()
    phone = fake.phone_number()
    cur.execute(
        "INSERT INTO customers (name, email, phone) VALUES (%s, %s, %s) RETURNING id",
        (name, email, phone)
    )
    customer_id = cur.fetchone()[0]
    customers.append(customer_id)

# --- 2. Accounts ---
accounts = []
for customer_id in customers:
    for _ in range(NUM_ACCOUNTS_PER_CUSTOMER):
        balance = round(random.uniform(1000, 100000), 2)
        account_type = random.choice(["checking", "savings"])
        status = "active"
        cur.execute(
            "INSERT INTO accounts (customer_id, balance, account_type, status) VALUES (%s, %s, %s, %s) RETURNING id",
            (customer_id, balance, account_type, status)
        )
        accounts.append(cur.fetchone()[0])

# --- 3. Transactions ---
for account_id in accounts:
    for _ in range(10):
        amount = round(random.uniform(50, 5000), 2)
        t_type = random.choice(["deposit", "withdrawal", "transfer"])
        description = fake.sentence()
        timestamp = fake.date_time_between(start_date="-1y", end_date="now")
        cur.execute(
            "INSERT INTO transactions (account_id, amount, type, description, timestamp) VALUES (%s, %s, %s, %s, %s)",
            (account_id, amount, t_type, description, timestamp)
        )

# --- 4. Loans ---
for customer_id in customers:
    if random.random() < 0.4:  # 40% of customers have loans
        amount = round(random.uniform(5000, 50000), 2)
        interest_rate = round(random.uniform(3, 12), 2)
        term_months = random.choice([12, 24, 36, 60])
        status = random.choice(["approved", "pending", "rejected"])
        cur.execute(
            "INSERT INTO loans (customer_id, amount, interest_rate, term_months, status) VALUES (%s, %s, %s, %s, %s)",
            (customer_id, amount, interest_rate, term_months, status)
        )

# --- 5. Market Prices ---
today = datetime.now()
for symbol in STOCK_SYMBOLS:
    for day in range(365):  # 1 year of daily prices
        date = today - timedelta(days=day)
        base = random.uniform(100, 1000)
        open_price = round(base, 2)
        close_price = round(base + random.uniform(-10, 10), 2)
        high_price = round(max(open_price, close_price) + random.uniform(0, 5), 2)
        low_price = round(min(open_price, close_price) - random.uniform(0, 5), 2)
        volume = random.randint(10000, 1000000)
        cur.execute(
            "INSERT INTO market_prices (symbol, price, timestamp) VALUES (%s, %s, %s)",
            (symbol, close_price, date)
        )

# --- 6. Trades & Portfolio ---
for customer_id in customers:
    portfolio = {}
    for _ in range(NUM_TRADES_PER_CUSTOMER):
        symbol = random.choice(STOCK_SYMBOLS)
        trade_type = random.choice(["BUY", "SELL"])
        quantity = random.randint(1, 100)
        price = round(random.uniform(50, 1000), 2)
        timestamp = fake.date_time_between(start_date="-1y", end_date="now")
        cur.execute(
            "INSERT INTO trades (customer_id, symbol, trade_type, quantity, price, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
            (customer_id, symbol, trade_type, quantity, price, timestamp)
        )
        # Update portfolio
        if trade_type == "BUY":
            portfolio[symbol] = portfolio.get(symbol, 0) + quantity
        else:
            portfolio[symbol] = max(0, portfolio.get(symbol, 0) - quantity)

    # Save portfolio
    for symbol, qty in portfolio.items():
        if qty > 0:
            avg_price = round(random.uniform(50, 1000), 2)
            cur.execute(
                "INSERT INTO portfolio (customer_id, symbol, quantity, avg_purchase_price) VALUES (%s, %s, %s, %s)",
                (customer_id, symbol, qty, avg_price)
            )

# Commit changes
conn.commit()
cur.close()
conn.close()

print("✅ Database seeded successfully!")
