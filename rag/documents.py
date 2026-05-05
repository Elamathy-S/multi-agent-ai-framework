"""
rag/documents.py — Finance company policy documents.

These are the knowledge base documents indexed into ChromaDB.
Each document has an id, category, title, and content.
Add new documents here and re-run rag/build_index.py to index them.
"""

DOCUMENTS = [

    # ── LOAN POLICIES ────────────────────────────────────────────────────────
    {
        "id":       "loan_policy_001",
        "category": "loan",
        "title":    "Standard Loan Approval Criteria",
        "content":  """
Loan Approval Policy v2.1 — Standard Criteria

Credit Score Thresholds:
- 750 and above: Auto-approve up to $50,000. No collateral required.
- 700–749: Approve up to $30,000. Standard interest rate applies.
- 650–699: Approve up to $15,000 with enhanced monitoring. Rate +1.5%.
- 600–649: Conditional approval only. Collateral required. Maximum $8,000.
- Below 600: Decline. Customer must wait 6 months before reapplying.

Debt-to-Income Ratio:
- Below 30%: Preferred. Full loan amount available.
- 30–40%: Acceptable. Reduce loan amount by 20%.
- Above 40%: Decline or require co-signer.

Employment Requirements:
- Minimum 12 months continuous employment with current employer.
- Self-employed customers require 2 years of tax returns.
- Unemployed customers are not eligible for standard loans.
        """,
    },
    {
        "id":       "loan_policy_002",
        "category": "loan",
        "title":    "Loan Interest Rate Schedule",
        "content":  """
Loan Interest Rate Schedule — Effective Q1 2024

Personal Loans:
- Excellent credit (750+): Base rate 5.9% APR
- Good credit (700–749): Base rate 8.5% APR
- Fair credit (650–699): Base rate 12.0% APR
- Poor credit (600–649): Base rate 18.0% APR

Business Loans:
- Standard business loan: 7.5% APR base rate
- Startup business (<2 years): 11.0% APR base rate
- Secured business loan: 6.0% APR base rate

Loan Origination Fee: 1% of loan amount for all categories.
Early repayment penalty: None for loans under $25,000.
Late payment fee: $35 per missed payment, after 5-day grace period.
        """,
    },
    {
        "id":       "loan_policy_003",
        "category": "loan",
        "title":    "Loan Review and Escalation Procedure",
        "content":  """
Loan Review and Escalation Procedure

Automatic Review Triggers:
- Loan amount above $25,000 regardless of credit score.
- Customer has more than 2 active loans simultaneously.
- Credit score changed by more than 50 points in last 90 days.
- Customer has a missed payment in the last 12 months.

Escalation Path:
1. Branch manager review for loans $25,000–$75,000.
2. Credit committee review for loans above $75,000.
3. Chief Credit Officer sign-off required for loans above $150,000.

Review Timeline:
- Standard review: 3–5 business days.
- Expedited review: 24 hours (additional fee of $75 applies).
- Emergency review: Same day (requires branch manager authorisation).
        """,
    },

    # ── RISK POLICIES ─────────────────────────────────────────────────────────
    {
        "id":       "risk_policy_001",
        "category": "risk",
        "title":    "Customer Risk Classification Guidelines",
        "content":  """
Customer Risk Classification Guidelines v3.0

Risk Score Bands:
- 0–25:  LOW RISK. Standard account monitoring. Annual review.
- 26–50: LOW-MEDIUM RISK. Quarterly transaction review.
- 51–70: MEDIUM RISK. Monthly review. Alert compliance team.
- 71–85: HIGH RISK. Weekly monitoring. Restrict high-value transactions.
- 86–100: CRITICAL RISK. Immediate escalation. Account may be frozen.

Factors That Increase Risk Score:
- Multiple large cash withdrawals in short period (+15 points)
- International transfers to high-risk jurisdictions (+20 points)
- Rapid account balance depletion (+10 points)
- Multiple failed payment attempts (+8 points)
- Unusual login times or locations (+5 points)

Factors That Decrease Risk Score:
- Long-standing account with no issues (-10 points)
- Regular salary deposits (-8 points)
- Consistent spending patterns (-5 points)
        """,
    },
    {
        "id":       "risk_policy_002",
        "category": "risk",
        "title":    "High Risk Customer Actions",
        "content":  """
High Risk Customer Action Protocol

For customers scoring 71–85 (HIGH RISK):
1. Notify compliance officer within 24 hours.
2. Place soft flag on account — additional verification for transactions > $5,000.
3. Customer relationship manager must contact customer within 48 hours.
4. Restrict international wire transfers pending review.
5. Document all contact attempts in customer file.

For customers scoring 86–100 (CRITICAL RISK):
1. Immediate freeze on outgoing wire transfers.
2. Notify compliance officer and branch manager within 1 hour.
3. File Suspicious Activity Report (SAR) if warranted.
4. Legal team notification if fraud is suspected.
5. Account may be suspended pending full investigation.

Review and Removal from Watch List:
- Customer must maintain score below 50 for 90 consecutive days.
- Written approval from compliance officer required to remove flags.
        """,
    },

    # ── FRAUD POLICIES ────────────────────────────────────────────────────────
    {
        "id":       "fraud_policy_001",
        "category": "fraud",
        "title":    "Fraud Detection Triggers and Response",
        "content":  """
Fraud Detection Policy v4.2

Automatic Fraud Flag Triggers:
- Transaction amount 3x above customer's average transaction value.
- More than 5 transactions in a 1-hour window.
- Card used in two different countries within 6 hours.
- Multiple small transactions followed by one large transaction (structuring).
- Transaction at unusual hour (2am–5am local time) over $1,000.
- New payee receiving transfer over $10,000 within 24 hours of being added.

Immediate Actions on Fraud Flag:
1. Temporarily block the suspicious transaction.
2. Send SMS/email alert to customer immediately.
3. Require re-authentication for next 3 transactions.
4. Log incident in fraud monitoring system.
5. Assign fraud analyst within 2 hours during business hours.

False Positive Resolution:
- Customer can verify transaction via app or phone.
- Verified transactions are unblocked within 15 minutes.
- Three false positives in 30 days triggers policy review for that customer.
        """,
    },
    {
        "id":       "fraud_policy_002",
        "category": "fraud",
        "title":    "Know Your Customer (KYC) Requirements",
        "content":  """
Know Your Customer (KYC) Policy

Initial Customer Onboarding:
- Government-issued photo ID required (passport or driving licence).
- Proof of address dated within 3 months.
- Source of funds declaration for initial deposits over $10,000.
- Enhanced due diligence for Politically Exposed Persons (PEPs).

Annual KYC Review:
- Standard customers: Documents refreshed every 3 years.
- Medium/High risk customers: Annual document refresh required.
- Any change of address requires new proof of address within 30 days.

Suspicious Activity Reporting:
- Any transaction over $10,000 in cash must be reported.
- Structuring (multiple transactions to avoid $10,000 threshold) must be reported.
- Customer refusal to provide KYC documents is a reportable event.
        """,
    },

    # ── TRADING POLICIES ──────────────────────────────────────────────────────
    {
        "id":       "trading_policy_001",
        "category": "trading",
        "title":    "Portfolio Risk Limits",
        "content":  """
Portfolio Risk Management Policy

Concentration Limits:
- No single stock should exceed 25% of total portfolio value.
- No single sector should exceed 40% of total portfolio value.
- Minimum 5 different holdings recommended for diversification.

Loss Thresholds — Automatic Review:
- Portfolio down 15% from peak: Notify customer, review risk tolerance.
- Portfolio down 25% from peak: Mandatory review with financial advisor.
- Portfolio down 40% from peak: Automatic defensive rebalancing offered.

Margin Trading Limits:
- Maximum leverage: 2:1 for standard accounts.
- Margin call triggered at 30% equity ratio.
- Forced liquidation at 20% equity ratio.

Prohibited Investments:
- No investment in sanctioned entities or countries.
- No investment in companies under active SEC investigation.
- Penny stocks (under $1) limited to 5% of portfolio.
        """,
    },

    # ── GENERAL COMPLIANCE ────────────────────────────────────────────────────
    {
        "id":       "compliance_001",
        "category": "compliance",
        "title":    "Data Privacy and Customer Rights",
        "content":  """
Customer Data Privacy Policy

Customer Rights:
- Right to access all personal data held by the bank within 30 days of request.
- Right to correct inaccurate information within 15 business days.
- Right to data portability — customer data exportable in standard format.
- Right to deletion — subject to legal retention requirements (7 years minimum).

Data Retention:
- Transaction records: 7 years minimum (regulatory requirement).
- Customer communications: 5 years.
- Loan applications (including declined): 3 years.
- Identity documents: Duration of relationship + 5 years.

Breach Notification:
- Customers must be notified within 72 hours of any data breach.
- Regulatory notification required for breaches affecting 500+ customers.
        """,
    },
]