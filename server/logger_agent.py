"""
server/logger_agent.py — Agent session logger.

Writes one AgentLog row per user query, capturing the full
orchestration trace: plan, agent steps, tools, RAG, permissions, answer.

If the DB write fails (e.g. locked, schema mismatch), falls back to
writing a JSON line to logs/agent_sessions.jsonl so nothing is silently lost.
"""

import json
import time
import uuid
import logging
import os
from pathlib import Path
from server.db import SessionLocal
from server.models.agent_log import AgentLog

# ---------------------------------------------------------------------------
# Fallback file logger — used when DB is unavailable
# ---------------------------------------------------------------------------
_LOG_DIR  = Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "agent_sessions.jsonl"

_file_logger = logging.getLogger("agent_session_fallback")
_file_logger.setLevel(logging.WARNING)


def _write_fallback(payload: dict) -> None:
    """Append a JSON line to logs/agent_sessions.jsonl as a last resort."""
    try:
        _LOG_DIR.mkdir(exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
        print(f"⚠️  Session written to fallback log: {_LOG_FILE}")
    except Exception as file_exc:
        # Nothing left to do — at least print so it shows in terminal output
        print(f"⚠️  Fallback log also failed: {file_exc}")
        print(f"    Session payload: {json.dumps(payload, default=str)[:300]}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def new_session_id() -> str:
    """Generate a unique session ID for one user query."""
    return str(uuid.uuid4())[:8]


def log_agent_session(
    session_id:         str,
    user_query:         str,
    customer_id:        int,
    agents_planned:     list,
    agent_results:      dict,
    rag_retrieved:      dict,
    permission_denials: list,
    final_answer:       str,
    total_latency_ms:   float,
    error:              str = None,
):
    """
    Write a full agent session to the agent_logs table.
    Falls back to a JSONL file if the DB write fails.

    Args:
        session_id:         Short ID grouping all steps for this query.
        user_query:         The original user message.
        customer_id:        Customer being queried.
        agents_planned:     List of agent names selected by orchestrator.
        agent_results:      {agent_name: {steps, observations, answer}}.
        rag_retrieved:      {agent_name: [policy_title, ...]}.
        permission_denials: [{agent, tool, reason}, ...].
        final_answer:       The synthesised answer shown to the user.
        total_latency_ms:   Total time from query to answer.
        error:              Error message if something failed.
    """
    # Summarise tools called per agent
    tools_called = {
        name: [s.get("action", "") for s in res.get("steps", [])]
        for name, res in agent_results.items()
    }

    total_tools = sum(len(t) for t in tools_called.values())

    # Summarise agent steps (thought + action; abbreviated)
    agent_steps_summary = {}
    for name, res in agent_results.items():
        agent_steps_summary[name] = [
            {
                "thought": s.get("thought", "")[:100],
                "action":  s.get("action", ""),
            }
            for s in res.get("steps", [])
        ]

    # Build a serialisable snapshot for the fallback writer
    fallback_payload = {
        "session_id":         session_id,
        "user_query":         user_query,
        "customer_id":        customer_id,
        "agents_planned":     agents_planned,
        "agent_steps":        agent_steps_summary,
        "tools_called":       tools_called,
        "rag_policies":       rag_retrieved,
        "permission_denials": permission_denials,
        "final_answer":       final_answer,
        "total_tools":        total_tools,
        "total_latency_ms":   round(total_latency_ms, 2),
        "had_error":          bool(error),
        "error_detail":       error,
    }

    db = SessionLocal()
    try:
        log = AgentLog(
            session_id         = session_id,
            user_query         = user_query,
            customer_id        = customer_id,
            agents_planned     = json.dumps(agents_planned),
            plan_reason        = f"keyword routing → {agents_planned}",
            agent_steps        = json.dumps(agent_steps_summary, default=str),
            tools_called       = json.dumps(tools_called),
            rag_policies       = json.dumps(rag_retrieved, default=str),
            permission_denials = json.dumps(permission_denials),
            final_answer       = final_answer,
            total_tools        = total_tools,
            total_latency_ms   = round(total_latency_ms, 2),
            had_error          = bool(error),
            error_detail       = error,
        )
        db.add(log)
        db.commit()
    except Exception as db_exc:
        db.rollback()
        print(f"⚠️  DB agent logging failed: {db_exc} — writing to fallback file.")
        _write_fallback(fallback_payload)
    finally:
        db.close()


def get_recent_logs(limit: int = 20) -> list:
    """Return the most recent agent session logs."""
    db = SessionLocal()
    try:
        logs = (
            db.query(AgentLog)
            .order_by(AgentLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id":                 log.id,
                "session_id":         log.session_id,
                "created_at":         str(log.created_at),
                "user_query":         log.user_query,
                "customer_id":        log.customer_id,
                "agents_planned":     json.loads(log.agents_planned or "[]"),
                "tools_called":       json.loads(log.tools_called or "{}"),
                "rag_policies":       json.loads(log.rag_policies or "{}"),
                "permission_denials": json.loads(log.permission_denials or "[]"),
                "total_tools":        log.total_tools,
                "total_latency_ms":   float(log.total_latency_ms or 0),
                "had_error":          log.had_error,
                "final_answer":       (log.final_answer or "")[:200],
            }
            for log in logs
        ]
    finally:
        db.close()