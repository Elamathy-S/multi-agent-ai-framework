"""
server/tools/analytics.py — Deterministic risk, fraud and credit computations.

These are pure functions over a customer context dict (see
customer_context_builder). They contain NO LLM calls: the same input always
gives the same output, so results are testable and auditable.

Division of labour in this system:
    tools  -> compute facts (scores, metrics, rule hits) from data
    agents -> decide which facts to fetch, interpret them against policy
              (retrieved via RAG), and explain the conclusion

Thresholds mirror the policy documents in rag/documents.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

OUTFLOW_TYPES = {"withdrawal", "transfer"}
OPEN_LOAN_STATUSES = {"approved", "pending"}


# ---------------------------------------------------------------------------
# Shared metrics
# ---------------------------------------------------------------------------
def _metrics(ctx: dict) -> dict:
    accounts = ctx.get("accounts", [])
    loans = ctx.get("loans", [])
    txns = ctx.get("transactions", [])

    balance = sum(a["balance"] for a in accounts)
    open_debt = sum(l["amount"] for l in loans if l["status"] in OPEN_LOAN_STATUSES)
    rejected = sum(1 for l in loans if l["status"] == "rejected")
    inflow = sum(t["amount"] for t in txns if t["type"] == "deposit")
    outflow = sum(t["amount"] for t in txns if t["type"] in OUTFLOW_TYPES)
    avg_txn = (sum(t["amount"] for t in txns) / len(txns)) if txns else 0.0

    return {
        "total_balance": round(balance, 2),
        "open_loan_debt": round(open_debt, 2),
        "debt_to_balance": round(open_debt / balance, 3) if balance > 0 else None,
        "rejected_loans": rejected,
        "inflow": round(inflow, 2),
        "outflow": round(outflow, 2),
        "net_flow_ratio": round((inflow - outflow) / inflow, 3) if inflow > 0 else None,
        "avg_transaction": round(avg_txn, 2),
        "transaction_count": len(txns),
    }


# ---------------------------------------------------------------------------
# Risk score (0–100) — additive, every point is accounted for in `components`
# ---------------------------------------------------------------------------
def compute_risk(ctx: dict) -> dict:
    m = _metrics(ctx)
    c: dict[str, int] = {}

    # Leverage: open loans relative to deposits (max 30)
    if m["debt_to_balance"] is None:
        c["leverage"] = 30 if m["open_loan_debt"] > 0 else 0
    else:
        c["leverage"] = min(30, round(m["debt_to_balance"] * 30))

    # Liquidity: thin balances (max 20)
    c["low_liquidity"] = 20 if m["total_balance"] < 5_000 else 10 if m["total_balance"] < 20_000 else 0

    # Cash burn: money going out faster than it comes in (max 20)
    if m["inflow"] == 0 and m["outflow"] > 0:
        c["cash_burn"] = 20
    elif m["net_flow_ratio"] is not None and m["net_flow_ratio"] < 0:
        c["cash_burn"] = min(20, round(-m["net_flow_ratio"] * 20))
    else:
        c["cash_burn"] = 0

    # Credit history: rejected applications (max 15)
    c["rejected_loans"] = min(15, m["rejected_loans"] * 5)

    # Fraud signals feed risk (max 15)
    fraud = compute_fraud(ctx)
    c["fraud_signals"] = min(15, len(fraud["suspicious_patterns"]) * 5)

    score = min(100, sum(c.values()))
    return {
        "risk_score": score,
        "level": _risk_band(score),
        "components": c,
        "key_risk_factors": [f"{k}: +{v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]) if v > 0],
        "metrics": m,
    }


def _risk_band(score: int) -> str:
    """Bands from policy risk_policy_001."""
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "LOW-MEDIUM"
    if score <= 70:
        return "MEDIUM"
    if score <= 85:
        return "HIGH"
    return "CRITICAL"


# ---------------------------------------------------------------------------
# Fraud rules — triggers from policy fraud_policy_001
# ---------------------------------------------------------------------------
def compute_fraud(ctx: dict) -> dict:
    txns = ctx.get("transactions", [])
    m = _metrics(ctx)
    patterns: list[str] = []

    # Rule 1: amount more than 3x the customer's average transaction value
    outliers = [t for t in txns if m["avg_transaction"] and t["amount"] > 3 * m["avg_transaction"]]
    if outliers:
        patterns.append(f"{len(outliers)} transaction(s) above 3x average (${m['avg_transaction']:,.2f})")

    # Rule 2: more than 5 transactions inside a 1-hour window (per account)
    burst = 0
    by_account: dict[int, list[datetime]] = {}
    for t in txns:
        if t.get("timestamp"):
            by_account.setdefault(t["account_id"], []).append(t["timestamp"])
    for times in by_account.values():
        times.sort()
        lo = 0
        for hi in range(len(times)):
            while times[hi] - times[lo] > timedelta(hours=1):
                lo += 1
            if hi - lo + 1 > 5:
                burst += 1
                break
    if burst:
        patterns.append(f"{burst} account(s) with >5 transactions in one hour")

    # Rule 3: unusual hour (02:00–05:00) and over $1,000
    night = [t for t in txns if t.get("timestamp") and 2 <= t["timestamp"].hour < 5 and t["amount"] > 1000]
    if night:
        patterns.append(f"{len(night)} transaction(s) over $1,000 between 02:00 and 05:00")

    severity = "NONE" if not patterns else "LOW" if len(patterns) == 1 else "HIGH"
    return {
        "fraud_flag": bool(patterns),
        "severity": severity,
        "suspicious_patterns": patterns,
        "transactions_reviewed": len(txns),
        "rules_checked": ["amount_over_3x_average", "burst_over_5_per_hour", "night_over_1000"],
    }


# ---------------------------------------------------------------------------
# Credit score (300–850)
# ---------------------------------------------------------------------------
def compute_credit(ctx: dict) -> dict:
    m = _metrics(ctx)
    factors: list[str] = []
    score = 550

    liquidity = min(150, int(m["total_balance"] / 1000 * 2))
    score += liquidity
    factors.append(f"liquidity +{liquidity} (balance ${m['total_balance']:,.0f})")

    debt = min(120, int(m["open_loan_debt"] / 1000 * 3))
    score -= debt
    if debt:
        factors.append(f"open loan debt -{debt} (${m['open_loan_debt']:,.0f})")

    rej = min(75, m["rejected_loans"] * 25)
    score -= rej
    if rej:
        factors.append(f"rejected applications -{rej}")

    if m["net_flow_ratio"] is not None:
        flow = round(60 * max(-1.0, min(1.0, m["net_flow_ratio"])))
        score += flow
        factors.append(f"cash flow {flow:+d} (net flow ratio {m['net_flow_ratio']})")

    score = max(300, min(850, score))
    return {
        "credit_score": score,
        "rating": "Excellent" if score >= 750 else "Good" if score >= 670 else "Fair" if score >= 580 else "Poor",
        "loan_approval_likelihood": "HIGH" if score >= 700 else "MEDIUM" if score >= 600 else "LOW",
        "factors": factors,
        "metrics": m,
    }
