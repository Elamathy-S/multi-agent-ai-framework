"""
client/security/rbac.py — Database-backed RBAC service.

Provides:
  - check_permission()  — queries DB for role→tool access, logs to audit trail
  - manage roles/permissions at runtime via CRUD functions
  - seed_default_roles() — initialises DB with default permissions on first run
  - Falls back to static ROLE_PERMISSIONS if DB is unavailable

This replaces the static dict lookup with a real RBAC system:
  Users (agents) → Roles → Permissions (tools)
"""

from datetime import datetime
from server.db import SessionLocal, Base, engine
from server.models.rbac import Role, RolePermission, AccessAuditLog

# Static fallback — used if DB hasn't been seeded or is unavailable
_STATIC_PERMISSIONS = {
    "customer_agent": {"get_customer", "list_customers"},
    "loan_agent":     {"get_loan_status", "get_credit_score"},
    "risk_agent":     {"get_risk_score", "check_fraud"},
    "trading_agent":  {"get_trading_portfolio", "get_pnl", "get_market_price"},
}


# ---------------------------------------------------------------------------
# Permission check — the core RBAC function
# ---------------------------------------------------------------------------

def check_permission(agent_name: str, tool_name: str, session_id: str = "", customer_id: int = 0) -> bool:
    """
    Check if an agent is authorised to call a tool.

    1. Queries the roles + role_permissions tables
    2. Logs the check to access_audit_log (allowed or denied)
    3. Falls back to static dict if DB query fails

    Args:
        agent_name:  The agent's role name (e.g. "risk_agent")
        tool_name:   The MCP tool being called (e.g. "get_risk_score")
        session_id:  Current orchestration session (for audit trail)
        customer_id: Target customer (for audit trail)

    Returns:
        True if allowed, False if denied.
    """
    try:
        db = SessionLocal()
        try:
            # Query: does this role have this permission?
            role = db.query(Role).filter(
                Role.name == agent_name,
                Role.is_active == True,
            ).first()

            if role:
                permission = db.query(RolePermission).filter(
                    RolePermission.role_id == role.id,
                    RolePermission.tool_name == tool_name,
                ).first()
                allowed = permission is not None
            else:
                # Role not in DB — fall back to static
                allowed = tool_name in _STATIC_PERMISSIONS.get(agent_name, set())

            # Log to audit trail
            audit = AccessAuditLog(
                agent_name=agent_name,
                tool_name=tool_name,
                allowed=allowed,
                reason=f"{'Allowed' if allowed else 'Denied'} by {'DB role' if role else 'static fallback'}",
                session_id=session_id,
                customer_id=customer_id,
            )
            db.add(audit)
            db.commit()

            return allowed

        finally:
            db.close()

    except Exception:
        # DB unavailable — fall back to static permissions
        return tool_name in _STATIC_PERMISSIONS.get(agent_name, set())


# ---------------------------------------------------------------------------
# Role management — CRUD for runtime changes
# ---------------------------------------------------------------------------

def get_all_roles() -> list[dict]:
    """List all roles with their permissions."""
    db = SessionLocal()
    try:
        roles = db.query(Role).all()
        return [
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "is_active": role.is_active,
                "permissions": sorted([p.tool_name for p in role.permissions]),
                "created_at": str(role.created_at),
            }
            for role in roles
        ]
    finally:
        db.close()


def get_role(role_name: str) -> dict | None:
    """Get a single role by name."""
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            return None
        return {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "is_active": role.is_active,
            "permissions": sorted([p.tool_name for p in role.permissions]),
        }
    finally:
        db.close()


def create_role(name: str, description: str = "", permissions: list[str] = None) -> dict:
    """Create a new role with optional permissions."""
    db = SessionLocal()
    try:
        existing = db.query(Role).filter(Role.name == name).first()
        if existing:
            return {"error": f"Role '{name}' already exists"}

        role = Role(name=name, description=description)
        db.add(role)
        db.flush()

        for tool in (permissions or []):
            db.add(RolePermission(role_id=role.id, tool_name=tool))

        db.commit()
        return {"created": name, "permissions": permissions or []}
    finally:
        db.close()


def add_permission(role_name: str, tool_name: str) -> dict:
    """Grant a tool permission to a role."""
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            return {"error": f"Role '{role_name}' not found"}

        existing = db.query(RolePermission).filter(
            RolePermission.role_id == role.id,
            RolePermission.tool_name == tool_name,
        ).first()
        if existing:
            return {"error": f"'{role_name}' already has '{tool_name}'"}

        db.add(RolePermission(role_id=role.id, tool_name=tool_name))
        db.commit()
        return {"granted": tool_name, "to": role_name}
    finally:
        db.close()


def revoke_permission(role_name: str, tool_name: str) -> dict:
    """Revoke a tool permission from a role."""
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            return {"error": f"Role '{role_name}' not found"}

        perm = db.query(RolePermission).filter(
            RolePermission.role_id == role.id,
            RolePermission.tool_name == tool_name,
        ).first()
        if not perm:
            return {"error": f"'{role_name}' does not have '{tool_name}'"}

        db.delete(perm)
        db.commit()
        return {"revoked": tool_name, "from": role_name}
    finally:
        db.close()


def toggle_role(role_name: str, active: bool) -> dict:
    """Enable or disable a role."""
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            return {"error": f"Role '{role_name}' not found"}

        role.is_active = active
        db.commit()
        return {"role": role_name, "is_active": active}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Audit log queries
# ---------------------------------------------------------------------------

def get_audit_log(limit: int = 50, denied_only: bool = False) -> list[dict]:
    """Retrieve recent access audit entries."""
    db = SessionLocal()
    try:
        query = db.query(AccessAuditLog).order_by(AccessAuditLog.created_at.desc())
        if denied_only:
            query = query.filter(AccessAuditLog.allowed == False)
        logs = query.limit(limit).all()
        return [
            {
                "agent": log.agent_name,
                "tool": log.tool_name,
                "allowed": log.allowed,
                "reason": log.reason,
                "session_id": log.session_id,
                "customer_id": log.customer_id,
                "timestamp": str(log.created_at),
            }
            for log in logs
        ]
    finally:
        db.close()


def get_audit_stats() -> dict:
    """Summary stats of access audit log."""
    db = SessionLocal()
    try:
        total = db.query(AccessAuditLog).count()
        denied = db.query(AccessAuditLog).filter(AccessAuditLog.allowed == False).count()
        allowed = total - denied
        return {
            "total_checks": total,
            "allowed": allowed,
            "denied": denied,
            "denial_rate": f"{(denied / total * 100):.1f}%" if total else "0%",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Seed default roles — call on startup
# ---------------------------------------------------------------------------

def seed_default_roles():
    """
    Initialise the DB with default roles and permissions.
    Idempotent — skips roles that already exist.
    """
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        defaults = {
            "customer_agent": {
                "description": "Handles customer profile lookups and identity verification",
                "tools": ["get_customer", "list_customers"],
            },
            "loan_agent": {
                "description": "Assesses loans, credit scores, and approval decisions",
                "tools": ["get_loan_status", "get_credit_score"],
            },
            "risk_agent": {
                "description": "Evaluates financial risk and detects fraud",
                "tools": ["get_risk_score", "check_fraud"],
            },
            "trading_agent": {
                "description": "Analyses portfolio holdings, PnL, and market data",
                "tools": ["get_trading_portfolio", "get_pnl", "get_market_price"],
            },
        }

        for role_name, config in defaults.items():
            existing = db.query(Role).filter(Role.name == role_name).first()
            if existing:
                continue

            role = Role(name=role_name, description=config["description"])
            db.add(role)
            db.flush()

            for tool in config["tools"]:
                db.add(RolePermission(role_id=role.id, tool_name=tool))

        db.commit()
        print("  ✅ RBAC roles seeded")
    except Exception as e:
        db.rollback()
        print(f"  ⚠️  RBAC seed failed (non-fatal): {e}")
    finally:
        db.close()