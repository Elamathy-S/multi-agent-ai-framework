"""
server/models/rbac.py — RBAC database models.

Tables:
  - roles:            Agent roles (customer_agent, loan_agent, etc.)
  - role_permissions:  Which tools each role can access
  - access_audit_log:  Every permission check logged (allowed + denied)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from server.db import Base


class Role(Base):
    __tablename__ = "roles"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(100), unique=True, nullable=False)  # e.g. "risk_agent"
    description = Column(String(500), default="")
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Role {self.name}>"


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    role_id   = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(100), nullable=False)  # MCP tool name
    granted_at = Column(DateTime, default=datetime.utcnow)

    role = relationship("Role", back_populates="permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "tool_name", name="uq_role_tool"),
    )

    def __repr__(self):
        return f"<RolePermission {self.role_id}:{self.tool_name}>"


class AccessAuditLog(Base):
    __tablename__ = "access_audit_log"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    agent_name  = Column(String(100), nullable=False)
    tool_name   = Column(String(100), nullable=False)
    allowed     = Column(Boolean, nullable=False)
    reason      = Column(String(500), default="")
    session_id  = Column(String(100), default="")
    customer_id = Column(Integer, default=0)
    created_at  = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        status = "ALLOWED" if self.allowed else "DENIED"
        return f"<AuditLog {self.agent_name}→{self.tool_name}: {status}>"