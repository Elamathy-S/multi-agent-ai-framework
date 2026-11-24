"""tests/test_analytics.py — Deterministic risk / fraud / credit rules."""

from datetime import datetime, timedelta

import pytest

from server.tools.analytics import compute_credit, compute_fraud, compute_risk

T0 = datetime(2025, 6, 1, 12, 0)


def txn(amount, kind="withdrawal", when=T0, account=1):
    return {"account_id": account, "amount": amount, "type": kind, "description": "", "timestamp": when}


def ctx(balance=50_000, loans=(), txns=()):
    return {"accounts": [{"balance": balance, "type": "checking", "status": "active"}],
            "loans": list(loans), "transactions": list(txns)}


class TestFraudRules:

    def test_clean_history_is_clear(self):
        r = compute_fraud(ctx(txns=[txn(100, when=T0 + timedelta(days=i)) for i in range(5)]))
        assert r["fraud_flag"] is False and r["severity"] == "NONE"

    def test_burst_of_more_than_five_in_an_hour(self):
        r = compute_fraud(ctx(txns=[txn(50, when=T0 + timedelta(minutes=5 * i)) for i in range(6)]))
        assert any("in one hour" in p for p in r["suspicious_patterns"])

    def test_five_in_an_hour_is_not_a_burst(self):
        r = compute_fraud(ctx(txns=[txn(50, when=T0 + timedelta(minutes=5 * i)) for i in range(5)]))
        assert not any("in one hour" in p for p in r["suspicious_patterns"])

    def test_amount_over_three_times_average(self):
        r = compute_fraud(ctx(txns=[txn(100, when=T0 + timedelta(days=i)) for i in range(9)] + [txn(5000, when=T0 + timedelta(days=20))]))
        assert any("3x average" in p for p in r["suspicious_patterns"])

    def test_night_transaction_over_1000(self):
        r = compute_fraud(ctx(txns=[txn(1500, when=datetime(2025, 6, 1, 3, 30))]))
        assert r["fraud_flag"] and "02:00 and 05:00" in r["suspicious_patterns"][0]

    def test_night_transaction_under_threshold_is_ignored(self):
        assert not compute_fraud(ctx(txns=[txn(900, when=datetime(2025, 6, 1, 3, 30))]))["fraud_flag"]

    def test_two_patterns_is_high_severity(self):
        night = [txn(1500, when=datetime(2025, 6, 1, 3, 0, i)) for i in range(6)]   # night + burst
        assert compute_fraud(ctx(txns=night))["severity"] == "HIGH"


class TestRisk:

    def test_is_deterministic(self):
        c = ctx(balance=3000, loans=[{"amount": 9000, "status": "approved"}], txns=[txn(500), txn(200, "deposit")])
        assert compute_risk(c) == compute_risk(c)

    def test_components_sum_to_score(self):
        r = compute_risk(ctx(balance=3000, loans=[{"amount": 9000, "status": "approved"}]))
        assert r["risk_score"] == min(100, sum(r["components"].values()))

    def test_heavy_debt_and_thin_balance_is_riskier_than_healthy_customer(self):
        healthy = compute_risk(ctx(balance=90_000, txns=[txn(1000, "deposit"), txn(200)]))
        stressed = compute_risk(ctx(balance=2_000, loans=[{"amount": 20_000, "status": "approved"}] ,
                                    txns=[txn(5000)]))
        assert stressed["risk_score"] > healthy["risk_score"] + 40

    @pytest.mark.parametrize("score,band", [(0, "LOW"), (25, "LOW"), (26, "LOW-MEDIUM"), (51, "MEDIUM"),
                                            (71, "HIGH"), (86, "CRITICAL")])
    def test_bands_match_policy(self, score, band):
        from server.tools.analytics import _risk_band
        assert _risk_band(score) == band

    def test_rejected_loans_do_not_count_as_debt(self):
        r = compute_risk(ctx(loans=[{"amount": 50_000, "status": "rejected"}]))
        assert r["components"]["leverage"] == 0 and r["components"]["rejected_loans"] == 5


class TestCredit:

    def test_score_stays_in_range_and_extremes_are_reachable(self):
        worst = compute_credit(ctx(balance=0, loans=[{"amount": 1e7, "status": "approved"}] + [{"amount": 1, "status": "rejected"}] * 9,
                                   txns=[txn(1, "deposit"), txn(1e6)]))
        best = compute_credit(ctx(balance=1e9, txns=[txn(1e6, "deposit")]))
        assert worst["credit_score"] == 300 and worst["rating"] == "Poor"
        assert 750 <= best["credit_score"] <= 850 and best["rating"] == "Excellent"

    def test_more_debt_lowers_the_score(self):
        base = compute_credit(ctx())["credit_score"]
        assert compute_credit(ctx(loans=[{"amount": 30_000, "status": "approved"}]))["credit_score"] < base

    def test_rating_and_likelihood_are_consistent(self):
        r = compute_credit(ctx(balance=100_000, txns=[txn(5000, "deposit")]))
        assert r["rating"] in {"Excellent", "Good"} and r["loan_approval_likelihood"] in {"HIGH", "MEDIUM"}
