"""tests/test_api_surface.py — The API exposes no way to change roles or run tools directly."""

import httpx
import pytest


@pytest.fixture
async def client():
    from client import main
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        yield c


@pytest.mark.parametrize("path", [
    "/security/roles",
    "/security/roles/risk_agent/grant",
    "/security/roles/risk_agent/revoke",
    "/security/roles/risk_agent/toggle",
    "/mcp/tools/execute",
])
async def test_no_mutating_security_or_direct_tool_endpoints(client, path):
    r = await client.post(path, json={"tool": "get_customer"})
    assert r.status_code in (404, 405)


async def test_read_only_audit_and_roles_stay_open(client):
    assert (await client.get("/security/audit")).status_code == 200
    assert (await client.get("/security/roles")).status_code == 200