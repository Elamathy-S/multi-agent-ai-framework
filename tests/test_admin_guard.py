"""tests/test_admin_guard.py — Mutating security endpoints must not be open."""

import httpx
import pytest


@pytest.fixture
async def client():
    from client import main
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        yield c


async def test_admin_api_is_disabled_without_a_configured_token(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    r = await client.post("/security/roles/risk_agent/grant", json={"tool": "get_customer"})
    assert r.status_code == 403


async def test_wrong_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    r = await client.post("/security/roles/risk_agent/grant", json={"tool": "get_customer"},
                          headers={"X-Admin-Token": "nope"})
    assert r.status_code == 401


async def test_direct_tool_execution_needs_admin_too(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    r = await client.post("/mcp/tools/execute", json={"tool": "get_customer", "arguments": {"customer_id": 1}})
    assert r.status_code == 403


async def test_correct_token_passes_the_guard(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    r = await client.post("/security/roles/risk_agent/toggle", json={"active": True},
                          headers={"X-Admin-Token": "s3cret"})
    assert r.status_code not in (401, 403)


async def test_read_only_audit_endpoints_stay_open(client):
    assert (await client.get("/security/audit")).status_code == 200
