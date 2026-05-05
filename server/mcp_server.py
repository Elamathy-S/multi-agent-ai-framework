"""
mcp_server.py — The real MCP server for the Finance AI system.

This replaces the fake /mcp REST routes in main.py with a proper
MCP server that speaks JSON-RPC 2.0 and can be connected to by
Claude Desktop, Claude Code, Cursor, or any MCP-compatible host.

Run in development (stdio transport — for Claude Desktop):
    python mcp_server.py

Run as HTTP server (SSE transport — for web clients):
    python mcp_server.py --http
"""

import json
import sys
import argparse
from mcp.server import FastMCP
from server.tools.customer_tools import get_customer_profile
from server.tools.loan_tools import check_loan_status, credit_score_tool
from server.tools.risk_tools import risk_score_tool, fraud_check_tool
from server.tools.trading_tools import get_portfolio, calculate_pnl
from server.tools.tool_registry import init_tools
from server.db import SessionLocal, engine, Base
from server.models.customer import Customer
from server.models.market import MarketPrice


# ---------------------------------------------------------------------------
# Bootstrap: create tables + register legacy tool registry (used by agents)
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)
init_tools()


# ---------------------------------------------------------------------------
# Parse args early so we can pass the port to FastMCP
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Finance MCP Server")
parser.add_argument("--http", action="store_true", help="Run with SSE/HTTP transport")
parser.add_argument("--port", type=int, default=8001, help="Port for HTTP transport (default: 8001)")
args = parser.parse_args()


# ---------------------------------------------------------------------------
# Create the MCP server — port is passed in so --port flag is respected
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="finance-mcp-server",
    port=args.port,
    instructions=(
        "You are connected to a simulated finance company's server. "
        "You can look up customer profiles, check loans, score credit risk, "
        "detect fraud, and analyse trading portfolios. "
        "Always ask for a customer_id before calling any tool that requires one."
    ),
)


# ---------------------------------------------------------------------------
# TOOL 1 — Customer Profile
# ---------------------------------------------------------------------------
@mcp.tool()
def get_customer(customer_id: int) -> str:
    """
    Retrieve a customer's profile from the finance database.

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON string with name, email, and account creation date.
    """
    result = get_customer_profile(customer_id)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# TOOL 2 — Loan Status
# ---------------------------------------------------------------------------
@mcp.tool()
def get_loan_status(customer_id: int) -> str:
    """
    List all loans for a customer, including amounts, interest rates, and statuses.

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON array of loan records (loan_id, amount, interest_rate, status).
    """
    result = check_loan_status(customer_id)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# TOOL 3 — Credit Score
# ---------------------------------------------------------------------------
@mcp.tool()
def get_credit_score(customer_id: int) -> str:
    """
    Calculate a credit score for a customer based on their financial history.

    Analyses loans, account balances, and transactions to produce a score
    between 300 (Poor) and 850 (Excellent), plus loan approval likelihood.

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON with credit_score, rating (Poor/Fair/Good/Excellent),
        risk_factors, positive_factors, and loan_approval_likelihood.
    """
    result = credit_score_tool(customer_id)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# TOOL 4 — Risk Score
# ---------------------------------------------------------------------------
@mcp.tool()
def get_risk_score(customer_id: int) -> str:
    """
    Compute an overall financial risk score for a customer (0–100 scale).

    A score under 30 = LOW risk, 30–70 = MEDIUM, above 70 = HIGH.

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON with risk_score and level (LOW / MEDIUM / HIGH).
    """
    result = risk_score_tool(customer_id)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# TOOL 5 — Fraud Check
# ---------------------------------------------------------------------------
@mcp.tool()
def check_fraud(customer_id: int) -> str:
    """
    Run a fraud detection check on a customer's recent transactions.

    Flags unusual patterns that may indicate fraudulent activity.

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON with fraud_flag (true/false) and a plain-English reason.
    """
    result = fraud_check_tool(customer_id)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# TOOL 6 — Portfolio
# ---------------------------------------------------------------------------
@mcp.tool()
def get_trading_portfolio(customer_id: int) -> str:
    """
    Retrieve a customer's current stock portfolio (holdings only, no PnL).

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON array of holdings with symbol, quantity, and average purchase price.
    """
    result = get_portfolio(customer_id)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# TOOL 7 — PnL Analysis
# ---------------------------------------------------------------------------
@mcp.tool()
def get_pnl(customer_id: int) -> str:
    """
    Calculate profit-and-loss for every holding in a customer's portfolio.

    Compares average purchase price against the latest market price for each
    stock symbol to compute unrealised gain or loss.

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON with total_pnl and a per-symbol breakdown (avg_price,
        current_price, pnl).
    """
    result = calculate_pnl(customer_id)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# TOOL 8 — Full Customer Analysis (composite tool)
# ---------------------------------------------------------------------------
@mcp.tool()
def full_customer_analysis(customer_id: int) -> str:
    """
    Run a complete financial analysis for a customer in one call.

    Combines profile, credit score, risk score, fraud check, and PnL into a
    single structured report. Useful for advisor dashboards or AI summaries.

    Args:
        customer_id: The unique integer ID of the customer.

    Returns:
        JSON report with all analysis sections bundled together.
    """
    profile  = get_customer_profile(customer_id)
    credit   = credit_score_tool(customer_id)
    risk     = risk_score_tool(customer_id)
    fraud    = fraud_check_tool(customer_id)
    loans    = check_loan_status(customer_id)
    pnl      = calculate_pnl(customer_id)

    report = {
        "customer_id": customer_id,
        "profile":     profile,
        "credit":      credit,
        "risk":        risk,
        "fraud":       fraud,
        "loans":       loans,
        "portfolio_pnl": pnl,
    }
    return json.dumps(report, indent=2)


# ---------------------------------------------------------------------------
# TOOL 9 — List all customers (discovery helper)
# ---------------------------------------------------------------------------
@mcp.tool()
def list_customers(limit: int = 10) -> str:
    """
    Return a list of customers in the database (id, name, email).

    Useful for discovering valid customer IDs to pass to other tools.

    Args:
        limit: Maximum number of customers to return (default 10, max 100).

    Returns:
        JSON array of customers.
    """
    limit = min(limit, 100)
    db = SessionLocal()
    try:
        customers = db.query(Customer).limit(limit).all()
        result = [
            {"id": c.id, "name": c.name, "email": c.email}
            for c in customers
        ]
        return json.dumps(result, indent=2)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# TOOL 10 — Market prices
# ---------------------------------------------------------------------------
@mcp.tool()
def get_market_price(symbol: str) -> str:
    """
    Get the most recent simulated market price for a stock symbol.

    Supported symbols: AAPL, TSLA, MSFT, GOOG, AMZN.

    Args:
        symbol: Stock ticker symbol (e.g. "AAPL").

    Returns:
        JSON with symbol, price, and timestamp of the latest data point.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(MarketPrice)
            .filter(MarketPrice.symbol == symbol.upper())
            .order_by(MarketPrice.timestamp.desc())
            .first()
        )
        if not row:
            return json.dumps({"error": f"No price data found for {symbol}"})
        return json.dumps({
            "symbol": row.symbol,
            "price": float(row.price),
            "timestamp": str(row.timestamp),
        }, indent=2)
    finally:
        db.close()


# ===========================================================================
# RESOURCES
# ===========================================================================
# Resources are read-only data sources the LLM can browse — like files or
# database views.  They are distinct from tools: tools *do* things,
# resources *expose* data.  The MCP host shows them in a resource picker.
#
# URI scheme used here:  finance://<topic>[/<id>]
# ===========================================================================


# ---------------------------------------------------------------------------
# RESOURCE 1 — Customer directory
# URI: finance://customers
# ---------------------------------------------------------------------------
@mcp.resource("finance://customers")
def resource_customers() -> str:
    """
    A browsable directory of all customers in the simulated finance database.
    Returns id, name, and email for every customer (up to 200 rows).
    Use this to discover customer IDs before calling any customer-specific tool.
    """
    db = SessionLocal()
    try:
        rows = db.query(Customer).limit(200).all()
        data = [{"id": c.id, "name": c.name, "email": c.email} for c in rows]
        return json.dumps(data, indent=2)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RESOURCE 2 — Live market snapshot
# URI: finance://market/snapshot
# ---------------------------------------------------------------------------
@mcp.resource("finance://market/snapshot")
def resource_market_snapshot() -> str:
    """
    Latest simulated market prices for all tracked symbols:
    AAPL, TSLA, MSFT, GOOG, AMZN.
    Refreshed on every read from the market_prices table.
    """
    db = SessionLocal()
    try:
        symbols = ["AAPL", "TSLA", "MSFT", "GOOG", "AMZN"]
        snapshot = {}
        for sym in symbols:
            row = (
                db.query(MarketPrice)
                .filter(MarketPrice.symbol == sym)
                .order_by(MarketPrice.timestamp.desc())
                .first()
            )
            if row:
                snapshot[sym] = {
                    "price": float(row.price),
                    "as_of": str(row.timestamp),
                }
        return json.dumps(snapshot, indent=2)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RESOURCE 3 — Individual customer financial summary
# URI: finance://customer/{customer_id}
# ---------------------------------------------------------------------------
@mcp.resource("finance://customer/{customer_id}")
def resource_customer_summary(customer_id: str) -> str:
    """
    A snapshot of one customer's financial data: profile, account balances,
    active loans, and current portfolio holdings.
    Replace {customer_id} in the URI with a numeric ID, e.g. finance://customer/3
    """
    cid = int(customer_id)
    db = SessionLocal()
    try:
        from server.models.accounts import Account
        from server.models.loans import Loan
        from server.models.portfolio import Portfolio

        customer = db.query(Customer).filter(Customer.id == cid).first()
        if not customer:
            return json.dumps({"error": f"Customer {cid} not found"})

        accounts = db.query(Account).filter(Account.customer_id == cid).all()
        loans    = db.query(Loan).filter(Loan.customer_id == cid).all()
        holdings = db.query(Portfolio).filter(Portfolio.customer_id == cid).all()

        summary = {
            "customer": {"id": customer.id, "name": customer.name, "email": customer.email},
            "accounts": [
                {"id": a.id, "type": a.account_type, "balance": float(a.balance), "status": a.status}
                for a in accounts
            ],
            "loans": [
                {"id": l.id, "amount": float(l.amount), "interest_rate": float(l.interest_rate),
                 "term_months": l.term_months, "status": l.status}
                for l in loans
            ],
            "portfolio": [
                {"symbol": h.symbol, "quantity": h.quantity, "avg_price": float(h.avg_purchase_price)}
                for h in holdings
            ],
        }
        return json.dumps(summary, indent=2)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RESOURCE 4 — High-risk customers report
# URI: finance://reports/high-risk
# ---------------------------------------------------------------------------
@mcp.resource("finance://reports/high-risk")
def resource_high_risk_report() -> str:
    """
    Lists customers who have at least one loan in 'rejected' status.
    Useful as a starting point for compliance review workflows.
    """
    db = SessionLocal()
    try:
        import datetime
        from server.models.loans import Loan

        rejected_cids = (
            db.query(Loan.customer_id)
            .filter(Loan.status == "rejected")
            .distinct()
            .all()
        )
        flagged_ids = {row[0] for row in rejected_cids}
        customers = db.query(Customer).filter(Customer.id.in_(flagged_ids)).all()

        report = {
            "generated_at": str(datetime.datetime.utcnow()),
            "flagged_count": len(customers),
            "criteria": "At least one loan with status=rejected",
            "customers": [{"id": c.id, "name": c.name, "email": c.email} for c in customers],
        }
        return json.dumps(report, indent=2)
    finally:
        db.close()


# ===========================================================================
# PROMPTS
# ===========================================================================
# Prompts are reusable message templates the LLM host injects into a
# conversation.  They pre-load context and step-by-step instructions so
# the user doesn't have to type them every time.
# Think of them as saved "missions" for the AI agent.
# ===========================================================================


# ---------------------------------------------------------------------------
# PROMPT 1 — Loan application review
# ---------------------------------------------------------------------------
@mcp.prompt()
def loan_application_review(customer_id: str) -> str:
    """
    Guides the AI through a full loan application review for one customer.
    Fetches credit score, existing loans, risk level, and fraud status,
    then produces a structured approve/reject recommendation.
    """
    return f"""
You are a senior loan officer at a finance company.
Review the loan application for customer ID {customer_id}.

Follow these steps IN ORDER:
1. Call `get_customer` to confirm the customer exists.
2. Call `get_loan_status` to see their existing loan history.
3. Call `get_credit_score` to assess creditworthiness.
4. Call `get_risk_score` to understand their overall risk profile.
5. Call `check_fraud` to ensure there are no fraud flags.

After all steps, produce this report:

LOAN DECISION REPORT
====================
Customer: <name>
Credit Score: <score> (<rating>)
Risk Level: <level>
Fraud Flag: <yes/no>
Existing Loans: <count and total amount>

DECISION: APPROVE / REJECT / REFER TO SENIOR OFFICER

JUSTIFICATION:
<2-3 sentences based on the data above>

CONDITIONS (if approved):
<Any conditions, e.g. maximum amount, required collateral>
""".strip()


# ---------------------------------------------------------------------------
# PROMPT 2 — Portfolio health check
# ---------------------------------------------------------------------------
@mcp.prompt()
def portfolio_health_check(customer_id: str) -> str:
    """
    Guides the AI through a complete trading portfolio review.
    Checks holdings, PnL, and risk before producing investment recommendations.
    """
    return f"""
You are a financial advisor conducting a portfolio health check for customer ID {customer_id}.

Steps:
1. Call `get_customer` to identify the client.
2. Call `get_trading_portfolio` to see their current holdings.
3. Call `get_pnl` to calculate unrealised profit/loss per position.
4. Call `get_market_price` for each symbol in their portfolio.
5. Call `get_risk_score` to understand their risk profile.

Produce this report:

PORTFOLIO HEALTH REPORT
=======================
Client: <name>
Total Unrealised PnL: <amount>

POSITION BREAKDOWN:
<symbol>: <qty> shares @ avg $<avg> | current $<current> | PnL: $<pnl>

RISK ASSESSMENT: <LOW / MEDIUM / HIGH>

RECOMMENDATIONS:
1. <recommendation based on PnL and risk>
2. <concentration risk observation if applicable>
3. <any rebalancing suggestion>
""".strip()


# ---------------------------------------------------------------------------
# PROMPT 3 — Fraud investigation
# ---------------------------------------------------------------------------
@mcp.prompt()
def fraud_investigation(customer_id: str) -> str:
    """
    Triggers a structured fraud investigation workflow for a customer.
    Produces a compliance-ready investigation summary.
    """
    return f"""
You are a fraud analyst at a finance company.
Investigate customer ID {customer_id}.

Steps:
1. Call `get_customer` to establish identity.
2. Call `check_fraud` to get the fraud detection result.
3. Call `get_risk_score` to see the overall risk level.
4. Call `get_loan_status` to check for unusual loan activity.
5. Call `get_pnl` to review trading activity for suspicious patterns.

Produce this report:

FRAUD INVESTIGATION REPORT
===========================
Customer: <name> (ID: {customer_id})

FRAUD DETECTION RESULT: <flagged / clear>
RISK LEVEL: <LOW / MEDIUM / HIGH>

FINDINGS:
- <finding from loans>
- <finding from trading activity>

CONCLUSION: <SUSPICIOUS / NO EVIDENCE OF FRAUD>

RECOMMENDED ACTION:
<freeze account / escalate to compliance / no action required>
""".strip()


# ---------------------------------------------------------------------------
# PROMPT 4 — New customer onboarding assessment
# ---------------------------------------------------------------------------
@mcp.prompt()
def onboarding_assessment(customer_id: str) -> str:
    """
    A quick onboarding check for a newly registered customer.
    Decides what products the customer should be offered at sign-up.
    """
    return f"""
You are an onboarding specialist at a finance company.
Complete the initial assessment for new customer ID {customer_id}.

Steps:
1. Call `get_customer` to verify their profile is complete.
2. Call `get_credit_score` to establish a baseline credit profile.
3. Call `check_fraud` to run an initial fraud screening.

Produce this summary:

ONBOARDING ASSESSMENT
=====================
Customer: <name>
Email: <email>

CREDIT BASELINE:
Score: <score> (<rating>)
Approval Likelihood: <LOW / MEDIUM / HIGH>

FRAUD SCREENING: <PASSED / FLAGGED>

RECOMMENDED PRODUCT TIER:
<Basic checking only / Full product suite / Refer to manager>

NEXT STEPS:
<list 2-3 concrete next steps for the onboarding team>
""".strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if args.http:
        print(f"🚀 Finance MCP Server running on http://localhost:{args.port}/sse")
        mcp.run(transport="sse")
    else:
        # stdio transport — used by Claude Desktop and Claude Code
        mcp.run(transport="stdio")