"""
tests/conftest.py — Shared fixtures.

Unit tests are hermetic: a throwaway SQLite database, a scripted LLM and an
in-memory fake MCP session. No server, model or network is needed.
Integration tests (marked `integration`) need the MCP server on port 8001.
"""

import os
import tempfile

# Must be set before any `server.db` import so tests never touch the dev database.
_TMP = tempfile.mkdtemp(prefix="agent-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"

import pytest  # noqa: E402

from client.mcp.client import MCPClient, MCPConnectionError, MCPToolError  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _seed_roles():
    from client.security.rbac import seed_default_roles
    seed_default_roles()


class FakeMCP:
    """In-memory stand-in for MCPClient: same list_tools()/call() surface."""

    SCHEMAS = {
        "search_policies": {"type": "object", "properties": {"query": {"type": "string"}, "category": {"type": "string"}}, "required": ["query"]},
        "get_market_price": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        "list_customers": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    }
    CUSTOMER = {"type": "object", "properties": {"customer_id": {"type": "integer"}}, "required": ["customer_id"]}

    def __init__(self, handlers: dict):
        self.handlers = handlers
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self):
        return [{"name": n, "description": f"{n} tool", "schema": self.SCHEMAS.get(n, self.CUSTOMER)}
                for n in self.handlers]

    async def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        out = self.handlers[name](**kwargs)
        if isinstance(out, Exception):
            raise out
        return out


DEFAULT_HANDLERS = {
    "get_customer":     lambda customer_id: {"id": customer_id, "name": "Alice Example"},
    "get_loan_status":  lambda customer_id: [{"loan_id": 1, "amount": 10000.0, "status": "approved"}],
    "get_credit_score": lambda customer_id: {"credit_score": 640, "rating": "Fair"},
    "get_risk_score":   lambda customer_id: {"risk_score": 62, "level": "MEDIUM"},
    "check_fraud":      lambda customer_id: {"fraud_flag": True, "severity": "LOW", "suspicious_patterns": ["night txn"]},
    "get_trading_portfolio": lambda customer_id: [],
    "get_pnl":          lambda customer_id: {"total_pnl": 100.0},
    "get_market_price": lambda symbol: {"symbol": symbol, "price": 10.0},
    "list_customers":   lambda limit=10: [],
    "search_policies":  lambda query, category="", n=3: [
        {"id": "risk_policy_001#1", "title": "Risk bands", "score": 0.9, "text": "51-70 MEDIUM: monthly review"}],
}


@pytest.fixture
def fake_mcp():
    return FakeMCP(dict(DEFAULT_HANDLERS))


# ---------------------------------------------------------------------------
# Real MCP session — integration tests only
# ---------------------------------------------------------------------------
@pytest.fixture
async def mcp():
    """Open MCPClient session. Skips if the server is not running."""
    try:
        client = await MCPClient().__aenter__()
    except MCPConnectionError:
        pytest.skip("MCP server not running on port 8001")
    yield client
    await client.__aexit__(None, None, None)
