"""
client/main.py — FastAPI companion server (MCP-powered).

All tool calls — whether via /chat, /chat/stream, or /agent/* — now go
through the MCP server using the MCP Python client (JSON-RPC 2.0 over SSE).

This server runs on port 8080.
The MCP server (mcp_server.py) runs on port 8001 (SSE transport).

Responsibilities:
  - /chat          → single MCP tool call (keyword-routed)
  - /chat/respond  → single MCP tool call + Ollama summary
  - /chat/stream   → full multi-agent orchestration via SSE (MCP-powered)
  - /agent/*       → call a specific agent directly (MCP-powered)
  - /mcp/*         → inspect MCP server surface (tools, prompts, resources)
  - /debug         → development helpers
"""

import asyncio
import json
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# DB bootstrap — import ALL models before create_all so every table is created
from server.db import engine, Base
from server.models.tool_log import ToolLog
from server.models.agent_log import AgentLog
Base.metadata.create_all(bind=engine)

# MCP client — the execution path for all tool calls
from client.mcp.client import MCPClient, MCPConnectionError

# Tool router — single source of query→tool mapping (replaces INTENT_TO_TOOL + ToolRegistry)
from client.tool_router import resolve_tool, extract_customer_id, discover_tools

# Agents — all async, all MCP-powered
from client.agents.orchestrator import (
    orchestrator, plan_agents, synthesise, react_agent, route_agent, AGENTS,
)
from client.agents.customer_agent import customer_agent
from client.agents.loan_agent     import loan_agent
from client.agents.trading_agent  import trading_agent
from client.agents.risk_agent     import risk_agent

# Gateway router for /mcp/* introspection endpoints
from client.mcp.gateway import router as mcp_router

# Direct tool import — only for health check (lightweight, no MCP round-trip)
from server.tools.customer_tools import get_customer_profile


# ---------------------------------------------------------------------------
# MCP server URL
# ---------------------------------------------------------------------------
MCP_SERVER_SSE_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")


# ---------------------------------------------------------------------------
# Single-tool MCP call helper (for /chat, /chat/respond, /chat/stream single)
# Opens its own short-lived MCP session for one tool call.
# ---------------------------------------------------------------------------
async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Call a single MCP tool via a short-lived session.
    Used by /chat and /chat/respond which only need one tool per request.
    """
    try:
        async with MCPClient(MCP_SERVER_SSE_URL) as mcp:
            return await mcp.call(tool_name, **arguments)
    except MCPConnectionError:
        raise HTTPException(
            status_code=503,
            detail="MCP server is not running. Start: python -m server.mcp_server --http --port 8001",
        )
    except Exception as exc:
        err = str(exc)
        if any(k in err.lower() for k in ["connect", "refused", "unreachable"]):
            raise HTTPException(
                status_code=503,
                detail="MCP server is not running. Start: python -m server.mcp_server --http --port 8001",
            )
        raise HTTPException(status_code=502, detail=f"MCP error: {err}")


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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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

    return {
        "status": "healthy" if (db_ok and mcp_ok) else "degraded",
        "database": "ok" if db_ok else "error",
        "mcp_server": "ok" if mcp_ok else "not running — start mcp_server.py --http --port 8001",
        "timestamp": str(datetime.now()),
    }


# ===========================================================================
# SINGLE-TOOL ENDPOINTS (keyword-routed, one MCP call)
# ===========================================================================

@app.post("/chat", tags=["Chat"])
async def chat(req: ChatRequest):
    """
    Send a natural language message. The server resolves the right MCP tool,
    calls the MCP server, and returns the result.
    """
    tool_name, param_names = resolve_tool(req.message)
    effective_cid = extract_customer_id(req.message, req.customer_id)

    arguments = {}
    if "customer_id" in param_names:
        arguments["customer_id"] = effective_cid
    if "symbol" in param_names:
        arguments["symbol"] = req.symbol

    mcp_result = await call_mcp_tool(tool_name, arguments)

    return {
        "timestamp":   str(datetime.now()),
        "customer_id": req.customer_id,
        "message":     req.message,
        "mcp_tool":    tool_name,
        "arguments":   arguments,
        "response":    mcp_result,
    }


# ===========================================================================
# MULTI-AGENT STREAMING (orchestrator-powered)
# ===========================================================================

@app.get("/agent/react/stream", tags=["ReAct Agent"])
async def react_agent_stream(message: str, customer_id: int = 1):
    """
    Run the full multi-agent orchestrator and stream each step as SSE.
    All tool calls go through the MCP server.
    """
    async def generate():
        def evt(status, label, detail=""):
            return f"data: {json.dumps({'status': status, 'label': label, 'detail': detail})}\n\n"

        yield evt("start", "ReAct Agent started", f"Question: {message}")
        await asyncio.sleep(0)

        # Step 1 — Plan
        yield evt("thinking", "🧠 Orchestrator planning", "Deciding which agents to call...")
        await asyncio.sleep(0)

        agent_names = plan_agents(message)
        yield evt("planned", f"📋 Plan: {', '.join(agent_names)}", f"{len(agent_names)} agent(s) selected")
        await asyncio.sleep(0)

        # Step 2 — Run agents through MCP
        agent_results = {}
        all_steps = []

        try:
            async with MCPClient() as mcp:
                for agent_name in agent_names:
                    icon = AGENTS[agent_name]["icon"]
                    yield evt("agent_start", f"{icon} {agent_name.title()} Agent starting", "")
                    await asyncio.sleep(0)

                    yield ": keepalive\n\n"
                    await asyncio.sleep(0)

                    agent_fn = AGENTS[agent_name]["fn"]
                    result = await agent_fn(mcp, message, customer_id)
                    agent_results[agent_name] = result

                    steps = result.get("steps", [])

                    # Show RAG policies if any were retrieved
                    rag_policies = []
                    for s in steps:
                        rag_policies.extend(s.get("rag_policies", []))
                    if rag_policies:
                        unique_policies = list(dict.fromkeys(rag_policies))  # deduplicate
                        yield evt("rag", f"  📚 RAG: {', '.join(unique_policies[:3])}", f"{len(unique_policies)} policy doc(s)")
                        await asyncio.sleep(0)

                    for s in steps:
                        yield evt("tool_call", f"  ⚡ {s.get('action','?')}", s.get("thought","")[:60])
                        await asyncio.sleep(0)
                        all_steps.append({**s, "agent": agent_name})

                    yield evt("agent_done", f"{icon} {agent_name.title()} Agent done", f"{len(steps)} tool call(s)")
                    await asyncio.sleep(0)

        except MCPConnectionError as e:
            yield evt("error", "MCP connection failed", str(e))
            yield evt("done", "done", json.dumps({"error": str(e)}))
            return

        # Step 3 — Synthesise structured report
        yield evt("thinking", "🔀 Synthesising results", "Combining all agent outputs...")
        await asyncio.sleep(0)

        structured_answer = synthesise(message, agent_results)
        all_raw = {name: r.get("observations", {}) for name, r in agent_results.items()}

        # Step 4 — Ollama summary (optional, falls back to structured report)
        final_answer = structured_answer
        try:
            from server.llm import safe_json_llm
            yield evt("llm", "🧠 Summarising with Ollama",
                       f"Asking {os.getenv('OLLAMA_MODEL', 'phi3')} to explain...")
            await asyncio.sleep(0)

            summary_system = (
                "You are a senior financial analyst. The user asked a question and "
                "multiple AI agents gathered data. Below is the structured report. "
                "Write a clear, conversational 3-5 sentence summary using the actual "
                "numbers and findings. Do not use bullet points or headers. "
                'Reply with JSON only: {"reply": "<your summary>"}'
            )
            summary_user = (
                f"User question: {message}\n\n"
                f"Agent report:\n{structured_answer}"
            )
            llm_result = safe_json_llm(summary_system, summary_user)

            if "error" not in llm_result:
                raw_reply = (
                    llm_result.get("reply")
                    or llm_result.get("response")
                    or llm_result.get("text")
                    or ""
                )
                if isinstance(raw_reply, dict):
                    raw_reply = raw_reply.get("text") or str(raw_reply)
                raw_reply = str(raw_reply).strip()
                if raw_reply and not raw_reply.startswith("{"):
                    final_answer = raw_reply
                    yield evt("llm_done", "✅ Summary ready", "")
                    await asyncio.sleep(0)
                else:
                    yield evt("llm_done", "Using structured report", "LLM returned invalid output")
                    await asyncio.sleep(0)
            else:
                yield evt("llm_done", "Using structured report", "Ollama unavailable")
                await asyncio.sleep(0)
        except Exception:
            yield evt("llm_done", "Using structured report", "Ollama not running")
            await asyncio.sleep(0)

        yield evt("done", "done", json.dumps({
            "reply":         final_answer,
            "mcp_tool":      f"multi_agent[{','.join(agent_names)}]",
            "steps":         all_steps,
            "tool_calls":    len(all_steps),
            "agents_called": agent_names,
            "raw":           all_raw,
        }))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/agent/react", tags=["ReAct Agent"])
async def react_agent_endpoint(req: ChatRequest):
    """Run the multi-agent orchestrator and return the full result."""
    result = await react_agent(req.message, req.customer_id)
    reply = result.get("answer", "")
    if not reply:
        reply = _format_fallback("react", result)
    return {
        "timestamp":   str(datetime.now()),
        "customer_id": req.customer_id,
        "message":     req.message,
        "mcp_tool":    "react_agent",
        "reply":       reply,
        "steps":       result.get("steps", []),
        "tool_calls":  result.get("tool_calls", 0),
        "raw":         {
            s["action"]: s.get("obs", s.get("observation", {}))
            for s in result.get("steps", [])
        },
    }


# ===========================================================================
# AGENT ENDPOINTS — call a specific agent directly (MCP-powered)
# ===========================================================================

@app.post("/agent/customer", tags=["Agents (direct)"])
async def agent_customer_endpoint(req: QueryRequest):
    """Call the customer agent directly (MCP-powered)."""
    async with MCPClient() as mcp:
        data = await customer_agent(mcp, req.query, req.customer_id)
    return {"agent": "customer_agent", "data": data}


@app.post("/agent/loan", tags=["Agents (direct)"])
async def agent_loan_endpoint(req: QueryRequest):
    """Call the loan agent directly (MCP-powered)."""
    async with MCPClient() as mcp:
        data = await loan_agent(mcp, req.query, req.customer_id)
    return {"agent": "loan_agent", "data": data}


@app.post("/agent/trading", tags=["Agents (direct)"])
async def agent_trading_endpoint(req: QueryRequest):
    """Call the trading agent directly (MCP-powered)."""
    async with MCPClient() as mcp:
        data = await trading_agent(mcp, req.query, req.customer_id)
    return {"agent": "trading_agent", "data": data}


@app.post("/agent/risk", tags=["Agents (direct)"])
async def agent_risk_endpoint(req: QueryRequest):
    """Call the risk agent directly (MCP-powered)."""
    async with MCPClient() as mcp:
        data = await risk_agent(mcp, req.query, req.customer_id)
    return {"agent": "risk_agent", "data": data}


# ===========================================================================
# FALLBACK FORMATTER
# ===========================================================================

def _format_fallback(tool_name: str, data: dict) -> str:
    """Plain-text summary — used when Ollama is not running or returns bad output."""
    if isinstance(data, dict) and "error" in data:
        return f"Sorry, I could not retrieve that data: {data['error']}"

    if tool_name == "get_customer":
        name  = data.get("name", "Unknown")
        email = data.get("email", "—")
        since = data.get("created_at", "—")
        return f"Customer {data.get('id','?')} is {name}. Email: {email}. Account opened: {since}."

    if tool_name == "get_loan_status":
        loans = data if isinstance(data, list) else []
        if not loans:
            return "No loans found for this customer."
        total = sum(l.get("amount", 0) for l in loans)
        return (
            f"Found {len(loans)} loan(s) totalling ${total:,.2f}. "
            f"Statuses: {', '.join(set(l.get('status','?') for l in loans))}."
        )

    if tool_name == "get_credit_score":
        score  = data.get("credit_score", "—")
        rating = data.get("rating", "—")
        likely = data.get("loan_approval_likelihood", "—")
        return f"Credit score: {score} ({rating}). Loan approval likelihood: {likely}."

    if tool_name == "get_risk_score":
        score = data.get("risk_score", "—")
        level = data.get("level", "—")
        rec   = data.get("recommendation", "")
        return f"Risk score: {score}/100 — {level} risk. {rec}"

    if tool_name == "check_fraud":
        flag   = data.get("fraud_flag", False)
        reason = data.get("reason", "—")
        conf   = data.get("confidence", "")
        status = "FLAGGED" if flag else "Clear"
        return f"Fraud check: {status}{' (' + conf + ' confidence)' if conf else ''}. {reason}"

    if tool_name in ("get_trading_portfolio", "get_pnl"):
        if isinstance(data, list):
            return f"Portfolio contains {len(data)} position(s)."
        total = data.get("total_pnl")
        if total is not None:
            direction = "profit" if float(total) >= 0 else "loss"
            return f"Total unrealised {direction}: ${abs(float(total)):,.2f}."

    if tool_name == "get_market_price":
        return f"{data.get('symbol','?')} is trading at ${data.get('price','—')}."

    if tool_name == "list_customers":
        customers = data if isinstance(data, list) else []
        return f"Found {len(customers)} customer(s) in the database."

    if tool_name == "full_customer_analysis":
        profile = data.get("profile", {})
        credit  = data.get("credit", {})
        risk    = data.get("risk", {})
        fraud   = data.get("fraud", {})
        name    = profile.get("name", "Customer")
        score   = credit.get("credit_score", "—")
        rating  = credit.get("rating", "—")
        rlevel  = risk.get("level", "—")
        fscore  = risk.get("risk_score", "—")
        fflag   = "No fraud detected" if not fraud.get("fraud_flag") else "FRAUD FLAGGED"
        return (
            f"{name} — Credit score: {score} ({rating}). "
            f"Risk: {fscore}/100 ({rlevel}). "
            f"Fraud status: {fflag}."
        )

    return f"Data retrieved successfully via {tool_name}."


# ===========================================================================
# RAG ENDPOINTS (unchanged — these don't touch MCP)
# ===========================================================================

@app.get("/rag/search", tags=["RAG"])
def rag_search(query: str, category: str = None, n: int = 3):
    """Search the policy knowledge base and return matching documents."""
    try:
        from rag.embedder import retrieve, index_count
        if index_count() == 0:
            return {
                "status":  "index_empty",
                "message": "Run: PYTHONPATH=. python3.12 rag/build_index.py",
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
        return {"status": "error", "message": "Run: pip install chromadb sentence-transformers"}


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
            "message":      "Index ready" if count > 0 else "Run: PYTHONPATH=. python3.12 rag/build_index.py",
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


@app.get("/security/permissions", tags=["Security"])
def list_permissions():
    """Show all agent-tool permission mappings."""
    from client.security.permissions import ROLE_PERMISSIONS
    return {
        "permissions": {agent: sorted(tools) for agent, tools in ROLE_PERMISSIONS.items()},
        "total_agents": len(ROLE_PERMISSIONS),
        "total_rules":  sum(len(t) for t in ROLE_PERMISSIONS.values()),
    }


@app.post("/security/check", tags=["Security"])
def check_permission_endpoint(payload: dict):
    """Test whether an agent is allowed to call a tool."""
    from client.security.permissions import check_permission
    agent   = payload.get("agent", "")
    tool    = payload.get("tool", "")
    allowed = check_permission(agent, tool)
    return {
        "agent":   agent,
        "tool":    tool,
        "allowed": allowed,
        "reason":  f"{agent} {'can' if allowed else 'cannot'} call {tool}",
    }


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