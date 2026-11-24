"""
client/main.py — FastAPI server for the multi-agent finance assistant.

Port 8080. The MCP server (server/mcp_server.py) runs separately on 8001.

  GET  /agent/react/stream  → full multi-agent run, live trace over SSE
  POST /agent/run           → same run, one JSON response
  POST /agent/{name}        → call a single specialist directly
  /mcp/*                    → inspect the MCP server (tools, prompts, resources)
  /rag/*, /security/*, /logs/*  → policy search, RBAC admin, audit/session logs
"""

import asyncio
import json
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# DB bootstrap — import ALL models before create_all so every table is created
from server.db import engine, Base
from server.models.tool_log import ToolLog
from server.models.agent_log import AgentLog
from server.models.rbac import Role, RolePermission, AccessAuditLog
Base.metadata.create_all(bind=engine)

# RBAC — seed default roles on startup
from client.security.rbac import (
    seed_default_roles, get_all_roles, get_role, create_role,
    add_permission, revoke_permission, toggle_role,
    get_audit_log, get_audit_stats,
)
seed_default_roles()

# MCP client — the execution path for all tool calls
from client.mcp.client import MCPClient, MCPConnectionError

from client.security.admin import require_admin
from client.tool_router import discover_tools

# Agents
from client.agents.loop import run_agent
from client.agents.orchestrator import orchestrator, AGENTS
from llm import LLMError, get_llm

# Gateway router for /mcp/* introspection endpoints
from client.mcp.gateway import router as mcp_router

# Direct tool import — only for health check (lightweight, no MCP round-trip)
from server.tools.customer_tools import get_customer_profile


# ---------------------------------------------------------------------------
# MCP server URL
# ---------------------------------------------------------------------------
MCP_SERVER_SSE_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Finance MCP System — REST API",
    description=(
        "REST API for the Finance MCP server. "
        "All tool calls go through the MCP protocol (JSON-RPC 2.0 over SSE). "
        "POST /chat for single-tool queries. "
        "GET /chat/stream for full multi-agent orchestration with live progress."
    ),
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:8080,http://localhost:3000,null").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    customer_id: int
    symbol: str = "AAPL"

class QueryRequest(BaseModel):
    query: str
    customer_id: int


# ---------------------------------------------------------------------------
# ROOT / HEALTH
# ---------------------------------------------------------------------------
@app.get("/", tags=["System"])
def root():
    return {
        "service": "Finance MCP REST API",
        "version": "4.0.0",
        "timestamp": str(datetime.now()),
        "how_it_works": (
            "Every tool call goes through the MCP server (port 8001) via "
            "the MCP protocol (JSON-RPC 2.0 over SSE). The multi-agent "
            "orchestrator opens one MCP session and runs agents concurrently."
        ),
        "endpoints": {
            "chat":        "POST /chat          — single MCP tool call",
            "chat_stream": "GET  /chat/stream   — multi-agent orchestration (SSE)",
            "mcp_tools":   "GET  /mcp/tools     — list MCP server tools",
            "agents":      "POST /agent/{type}  — call one agent (MCP-powered)",
            "docs":        "GET  /docs          — Swagger UI",
        },
    }


@app.get("/health", tags=["System"])
def health_check():
    db_ok = True
    mcp_ok = True

    try:
        get_customer_profile(1)
    except Exception:
        db_ok = False

    try:
        r = httpx.get(MCP_SERVER_SSE_URL, timeout=2.0)
        mcp_ok = r.status_code < 500
    except Exception:
        mcp_ok = False

    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    llm_ok = bool(os.getenv("ANTHROPIC_API_KEY")) if provider == "anthropic" else True

    return {
        "status": "healthy" if (db_ok and mcp_ok and llm_ok) else "degraded",
        "database": "ok" if db_ok else "error",
        "llm": {"provider": provider, "configured": llm_ok},
        "mcp_server": "ok" if mcp_ok else "not running — start mcp_server.py --http --port 8001",
        "timestamp": str(datetime.now()),
    }


# ===========================================================================
# MULTI-AGENT RUN
# ===========================================================================

def _sse(status: str, label: str, detail: str = "") -> str:
    return f"data: {json.dumps({'status': status, 'label': label, 'detail': detail})}\n\n"


def _flatten_steps(result: dict) -> list[dict]:
    return [s for r in result["agent_results"].values() for s in r["steps"]]


def _payload(result: dict) -> dict:
    steps = _flatten_steps(result)
    return {
        "reply":         result["answer"],
        "mcp_tool":      f"multi_agent[{','.join(result['agents_called'])}]",
        "steps":         steps,
        "tool_calls":    len(steps),
        "agents_called": result["agents_called"],
        "raw":           {n: r["observations"] for n, r in result["agent_results"].items()},
        "plan":          result["plan"],
        "agent_errors":  {n: r["error"] for n, r in result["agent_results"].items() if r["error"]},
        "removed_citations": result.get("removed_citations", []),
        "session_id":    result["session_id"],
        "usage":         result["usage"],
    }


@app.get("/agent/react/stream", tags=["Agents"])
async def agent_stream(message: str, customer_id: int = 1):
    """Run the supervisor + specialists and stream each step as Server-Sent Events."""

    async def generate():
        yield _sse("start", "Agent run started", f"Question: {message}")
        try:
            llm = get_llm()
        except LLMError as exc:
            yield _sse("error", "LLM not available", str(exc))
            yield _sse("done", "done", json.dumps({"error": str(exc)}))
            return

        queue: asyncio.Queue = asyncio.Queue()
        run = asyncio.create_task(orchestrator(message, customer_id, llm=llm, on_event=queue.put))

        while not (run.done() and queue.empty()):
            try:
                e = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            kind, agent = e["type"], e.get("agent", "")
            icon = AGENTS[agent].icon if agent in AGENTS else ""
            if kind == "plan_start":
                yield _sse("thinking", "🧠 Supervisor planning", "Deciding which specialists to involve...")
            elif kind == "plan":
                if e["agents"]:
                    yield _sse("planned", f"📋 Delegating to: {', '.join(e['agents'])}", e["reasoning"])
                else:
                    yield _sse("planned", "📋 No delegation needed", "")
            elif kind == "tool_call":
                yield _sse("tool_call", f"  ⚡ {icon} {agent} → {e['tool']}", (e.get("thought") or "")[:120])
            elif kind == "tool_result" and not e["ok"]:
                yield _sse("tool_call", f"  ✕ {agent} → {e['tool']} failed", f"{e['latency_ms']}ms")
            elif kind == "agent_error":
                yield _sse("tool_call", f"  ✕ {icon} {agent} specialist failed", e["error"][:300])
            elif kind == "final":
                yield _sse("agent_done", f"{icon} {agent.title()} specialist done", "")
            elif kind == "synthesis_start":
                yield _sse("thinking", "🔀 Synthesising", "Combining specialist findings...")

        try:
            result = run.result()
        except Exception as exc:
            yield _sse("error", "Agent run failed", str(exc))
            yield _sse("done", "done", json.dumps({"error": str(exc)}))
            return
        yield _sse("done", "done", json.dumps(_payload(result), default=str))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/agent/run", tags=["Agents"])
async def agent_run(req: ChatRequest):
    """Run the supervisor + specialists and return the complete result as JSON."""
    try:
        result = await orchestrator(req.message, req.customer_id)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except MCPConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"timestamp": str(datetime.now()), "customer_id": req.customer_id,
            "message": req.message, **_payload(result)}


@app.post("/agent/{name}", tags=["Agents"])
async def agent_direct(name: str, req: QueryRequest):
    """Call one specialist directly (customer, loan, risk or trading)."""
    if name not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent. Choose from: {', '.join(AGENTS)}")
    try:
        llm = get_llm()
        async with MCPClient() as mcp:
            res = await run_agent(AGENTS[name], llm, mcp, req.query, req.customer_id)
    except (LLMError, MCPConnectionError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"agent": name, "data": res.to_dict()}


# ===========================================================================
# RAG ENDPOINTS (inspection; agents reach RAG through the search_policies MCP tool)
# ===========================================================================

@app.get("/rag/search", tags=["RAG"])
def rag_search(query: str, category: str = None, n: int = 3):
    """Search the policy knowledge base and return matching documents."""
    try:
        from rag.embedder import retrieve, index_count
        if index_count() == 0:
            return {
                "status":  "index_empty",
                "message": "Run: PYTHONPATH=. python3 rag/build_index.py",
                "results": [],
            }
        docs = retrieve(query, n_results=n, category=category)
        return {
            "query":    query,
            "category": category,
            "count":    len(docs),
            "results":  [
                {"id": d["id"], "title": d["title"], "score": d["score"],
                 "category": d["category"], "excerpt": d["content"][:300] + "..."}
                for d in docs
            ],
        }
    except ImportError:
        return {"status": "error", "message": "Run: pip install chromadb"}


@app.get("/rag/status", tags=["RAG"])
def rag_status():
    """Check if the RAG index is built and ready."""
    try:
        from rag.embedder import index_count, INDEX_FILE
        count = index_count()
        return {
            "status":       "ready" if count > 0 else "empty",
            "documents":    count,
            "index_file":   str(INDEX_FILE),
            "index_exists": INDEX_FILE.exists(),
            "message":      "Index ready" if count > 0 else "Run: PYTHONPATH=. python3 rag/build_index.py",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/rag/test", tags=["RAG"])
def rag_test():
    """Test RAG retrieval with sample queries."""
    try:
        from rag.embedder import retrieve, index_count
        if index_count() == 0:
            return {"status": "empty", "message": "Run rag/build_index.py first"}

        tests = [
            ("credit score loan approval", "loan"),
            ("fraud suspicious transactions", "fraud"),
            ("risk score high risk customer", "risk"),
            ("portfolio concentration limit", "trading"),
        ]
        results = {}
        for query, category in tests:
            docs = retrieve(query, n_results=2, category=category)
            results[category] = [{"title": d["title"], "score": d["score"]} for d in docs]
        return {
            "status":  "working",
            "results": results,
            "message": "RAG is retrieving policies correctly" if any(results.values()) else "No results found",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ===========================================================================
# LOGS & SECURITY (unchanged)
# ===========================================================================

@app.get("/logs/sessions", tags=["Logs"])
def get_session_logs(limit: int = 20):
    """Return the most recent agent session logs."""
    try:
        from server.logger_agent import get_recent_logs
        return {"logs": get_recent_logs(limit=limit)}
    except Exception as e:
        return {"error": str(e), "logs": []}


@app.get("/logs/security", tags=["Logs"])
def get_security_log(limit: int = 50):
    """Return all permission denial events."""
    try:
        from server.logger_agent import get_recent_logs
        logs = get_recent_logs(limit=limit)
        denials = []
        for log in logs:
            for d in log.get("permission_denials", []):
                denials.append({
                    "session_id":  log["session_id"],
                    "query":       log["user_query"],
                    "customer_id": log["customer_id"],
                    "timestamp":   log["created_at"],
                    **d,
                })
        return {"total_denials": len(denials), "denials": denials}
    except Exception as e:
        return {"error": str(e)}


@app.get("/logs/tools", tags=["Logs"])
def get_tool_usage_log(limit: int = 50):
    """Return recent tool call logs."""
    from server.db import SessionLocal
    db = SessionLocal()
    try:
        logs = db.query(ToolLog).order_by(ToolLog.created_at.desc()).limit(limit).all()
        return {
            "total": len(logs),
            "logs": [
                {
                    "id":          log.id,
                    "tool_name":   log.tool_name,
                    "response_ms": float(log.response_time_ms or 0),
                    "created_at":  str(log.created_at),
                    "query":       log.user_query,
                }
                for log in logs
            ],
        }
    finally:
        db.close()


# ===========================================================================
# RBAC — Role-Based Access Control management
# ===========================================================================

@app.get("/security/roles", tags=["RBAC"])
def list_roles():
    """List all roles with their permissions."""
    roles = get_all_roles()
    return {
        "total_roles": len(roles),
        "roles": roles,
    }


@app.get("/security/roles/{role_name}", tags=["RBAC"])
def get_role_endpoint(role_name: str):
    """Get a single role and its permissions."""
    role = get_role(role_name)
    if not role:
        raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found")
    return role


@app.post("/security/roles", tags=["RBAC"], dependencies=[Depends(require_admin)])
def create_role_endpoint(payload: dict):
    """
    Create a new role.
    Body: {"name": "audit_agent", "description": "Read-only auditor", "permissions": ["get_customer"]}
    """
    name = payload.get("name", "")
    if not name:
        return {"error": "Missing 'name' field"}
    result = create_role(
        name=name,
        description=payload.get("description", ""),
        permissions=payload.get("permissions", []),
    )
    return result


@app.post("/security/roles/{role_name}/grant", tags=["RBAC"], dependencies=[Depends(require_admin)])
def grant_permission_endpoint(role_name: str, payload: dict):
    """
    Grant a tool permission to a role.
    Body: {"tool": "get_customer"}
    """
    tool = payload.get("tool", "")
    if not tool:
        return {"error": "Missing 'tool' field"}
    return add_permission(role_name, tool)


@app.post("/security/roles/{role_name}/revoke", tags=["RBAC"], dependencies=[Depends(require_admin)])
def revoke_permission_endpoint(role_name: str, payload: dict):
    """
    Revoke a tool permission from a role.
    Body: {"tool": "get_customer"}
    """
    tool = payload.get("tool", "")
    if not tool:
        return {"error": "Missing 'tool' field"}
    return revoke_permission(role_name, tool)


@app.post("/security/roles/{role_name}/toggle", tags=["RBAC"], dependencies=[Depends(require_admin)])
def toggle_role_endpoint(role_name: str, payload: dict):
    """
    Enable or disable a role.
    Body: {"active": false}
    """
    active = payload.get("active", True)
    return toggle_role(role_name, active)


@app.post("/security/check", tags=["RBAC"], dependencies=[Depends(require_admin)])
def check_permission_endpoint(payload: dict):
    """
    Test whether an agent is allowed to call a tool (queries the DB).
    Body: {"agent": "risk_agent", "tool": "get_customer"}
    """
    from client.security.permissions import check_permission
    agent = payload.get("agent", "")
    tool  = payload.get("tool", "")
    allowed = check_permission(agent, tool)
    return {
        "agent":   agent,
        "tool":    tool,
        "allowed": allowed,
        "source":  "database",
    }


@app.get("/security/audit", tags=["RBAC"])
def audit_log_endpoint(limit: int = 50, denied_only: bool = False):
    """View the access audit log — every permission check recorded."""
    return {
        "stats": get_audit_stats(),
        "log": get_audit_log(limit=limit, denied_only=denied_only),
    }


@app.get("/security/audit/stats", tags=["RBAC"])
def audit_stats_endpoint():
    """Summary: total checks, allowed, denied, denial rate."""
    return get_audit_stats()


# ===========================================================================
# DEBUG
# ===========================================================================

@app.get("/debug/tools", tags=["Debug"])
async def debug_tools():
    """List tools from the MCP server (the single source of truth)."""
    tools = await discover_tools()
    return {
        "source":      "MCP server",
        "mcp_url":     MCP_SERVER_SSE_URL,
        "total_tools": len(tools),
        "tools": [
            {"name": t["name"], "description": t["description"]}
            for t in tools
        ],
    }


# ---------------------------------------------------------------------------
# MCP gateway — mounts /mcp/tools, /mcp/prompts, /mcp/resources, etc.
# ---------------------------------------------------------------------------
app.include_router(mcp_router)