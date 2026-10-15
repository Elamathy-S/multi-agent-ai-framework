"""
tests/conftest.py — Shared fixtures for the test suite.

Unit tests run without any external service.
Integration tests (marked @pytest.mark.integration) need:
  - MCP server on port 8001
  - Database seeded with data/seed_data.py
"""

import pytest
from client.mcp.client import MCPClient, MCPConnectionError


# ---------------------------------------------------------------------------
# Sample data — mirrors what seed_data.py creates for customer 1
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_customer():
    return {"id": 1, "name": "Alice", "email": "alice@example.com", "created_at": "2024-01-15"}


@pytest.fixture
def sample_risk():
    return {"risk_score": 35, "level": "LOW", "key_risk_factors": ["low balance"], "recommendation": "Monitor"}


@pytest.fixture
def sample_fraud_clear():
    return {"fraud_flag": False, "confidence": "HIGH", "reason": "No suspicious patterns."}


@pytest.fixture
def sample_fraud_flagged():
    return {"fraud_flag": True, "confidence": "MEDIUM", "reason": "Unusual transaction volume."}


@pytest.fixture
def sample_credit():
    return {"credit_score": 720, "rating": "Good", "loan_approval_likelihood": "High", "factors": ["payment history"]}


@pytest.fixture
def sample_loans():
    return [
        {"id": 1, "amount": 10000, "status": "active", "interest_rate": 5.5},
        {"id": 2, "amount": 5000, "status": "paid", "interest_rate": 4.0},
    ]


@pytest.fixture
def sample_portfolio():
    return [
        {"symbol": "AAPL", "quantity": 10, "avg_price": 150.0},
        {"symbol": "TSLA", "quantity": 5, "avg_price": 200.0},
    ]


@pytest.fixture
def sample_pnl():
    return {"total_pnl": 1250.50, "positions": [{"symbol": "AAPL", "pnl": 800}, {"symbol": "TSLA", "pnl": 450.50}]}


# ---------------------------------------------------------------------------
# MCP client fixture — only used by integration tests
# ---------------------------------------------------------------------------
@pytest.fixture
async def mcp():
    """Provide an open MCPClient session. Skips if server is not running."""
    try:
        client = MCPClient()
        client = await client.__aenter__()
        yield client
        await client.__aexit__(None, None, None)
    except MCPConnectionError:
        pytest.skip("MCP server not running on port 8001")