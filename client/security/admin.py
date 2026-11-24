"""
client/security/admin.py — Guard for endpoints that change security state.

Granting a role a tool, or executing a tool directly, bypasses the agents'
normal RBAC path, so those endpoints need their own protection. Set
ADMIN_TOKEN and send it as the `X-Admin-Token` header. With no token
configured the admin API is disabled rather than left open.
"""

import hmac
import os

from fastapi import Header, HTTPException


def require_admin(x_admin_token: str = Header(default="")) -> None:
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=403, detail="Admin API disabled: set ADMIN_TOKEN to enable it.")
    if not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin token.")
