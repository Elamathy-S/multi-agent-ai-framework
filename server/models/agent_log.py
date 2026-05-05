"""
server/models/agent_log.py — Agent session log table.

Records every orchestrator decision and agent execution:
- which query came in
- which agents were selected and why
- which tools each agent called
- which RAG policies were retrieved
- latency at every step
- final synthesised answer

This gives full observability into the multi-agent system.
"""

from sqlalchemy import Column, Integer, Text, Numeric, DateTime, Boolean
from server.db import Base
from datetime import datetime


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id              = Column(Integer, primary_key=True, index=True)
    session_id      = Column(Text, index=True)   # groups all steps for one query
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Query
    user_query      = Column(Text)
    customer_id     = Column(Integer)

    # Orchestrator decision
    agents_planned  = Column(Text)   # JSON list e.g. ["loan", "risk"]
    plan_reason     = Column(Text)   # why these agents were chosen

    # Per-agent results (JSON)
    agent_steps     = Column(Text)   # JSON: {agent: [{action, thought, obs}]}
    tools_called    = Column(Text)   # JSON: {agent: [tool_name, ...]}
    rag_policies    = Column(Text)   # JSON: {agent: [policy_title, ...]}

    # Permission checks
    permission_denials = Column(Text)  # JSON: [{agent, tool, reason}]

    # Output
    final_answer    = Column(Text)
    total_tools     = Column(Integer)
    total_latency_ms = Column(Numeric)

    # Flags
    had_error       = Column(Boolean, default=False)
    error_detail    = Column(Text)