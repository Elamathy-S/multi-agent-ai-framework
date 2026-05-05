"""
clinet/main.py — FastAPI companion server.

Responsibilities:
  - REST endpoints for the frontend / API consumers
  - /chat      → real MCP client → MCP server (SSE/JSON-RPC 2.0) → tool
  - /mcp/chat  → same + full MCP protocol trace
  - /mcp/*     → inspect MCP tool surface
  - /debug     → development helpers

This server runs on port 8080.
The MCP server (mcp_server.py) runs on port 8001 (SSE transport).
/chat uses the real MCP Python client — speaks JSON-RPC 2.0 over SSE.
"""

import asyncio
import json
import os
import httpx
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mcp.client.sse import sse_client
from mcp import ClientSession
from fastapi.responses import StreamingResponse

# DB bootstrap — import ALL models before create_all so every table is created
from server.db import engine, Base
from server.models.tool_log import ToolLog        # tool call logs
from server.models.agent_log import AgentLog      # agent session logs
Base.metadata.create_all(bind=engine)

# Tool registry — kept for /agent/* direct endpoints and /debug
from server.tools.tool_registry import init_tools, registry

# Agents — kept for /agent/* direct-call endpoints
from client.agents.orchestrator import orchestrator, route_agent, react_agent
from client.agents.customer_agent import customer_agent
from client.agents.loan_agent import loan_agent
from client.agents.trading_agent import trading_agent
from client.agents.risk_agent import risk_agent

# Direct tool imports
from server.tools.customer_tools import get_customer_profile
from client.mcp.gateway import router as mcp_router


# ---------------------------------------------------------------------------
# MCP client — connects to mcp_server.py over SSE (real MCP protocol)
# ---------------------------------------------------------------------------
MCP_SERVER_SSE_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")

# Map of user intent keywords → (MCP tool name, required arg names)
INTENT_TO_TOOL = {
    # Full analysis — must be first so "full" matches before other keywords
    ("full", "complete", "overall", "everything", "summary", "overview", "all"):
                                                ("full_customer_analysis", ["customer_id"]),
    ("loan", "borrow", "repay"):                ("get_loan_status",        ["customer_id"]),
    ("risk",):                                  ("get_risk_score",          ["customer_id"]),
    ("credit", "score", "approve", "rating"):   ("get_credit_score",       ["customer_id"]),
    ("fraud", "suspicious", "flag"):            ("check_fraud",             ["customer_id"]),
    ("portfolio", "holdings", "position"):      ("get_trading_portfolio",   ["customer_id"]),
    ("pnl", "profit", "loss", "return"):        ("get_pnl",                ["customer_id"]),
    ("market", "price", "stock", "symbol"):     ("get_market_price",       ["symbol"]),
    ("customer", "profile", "account", "who"):  ("get_customer",           ["customer_id"]),
}


def resolve_tool(message: str) -> tuple:
    """Pick the best MCP tool name for a natural-language message."""
    lowered = message.lower()
    for keywords, (tool_name, params) in INTENT_TO_TOOL.items():
        if any(k in lowered for k in keywords):
            return tool_name, params
    return "get_customer", ["customer_id"]  # safe default


def extract_customer_id(message: str, fallback: int) -> int:
    """Parse a customer ID from the message, e.g. "who is customer 3" -> 3."""
    import re
    msg = message.lower()
    patterns = [
        (r"customer\s+(?:id\s*)?#?\s*(\d+)"),
        (r"cust(?:omer)?\s*#?\s*(\d+)"),
        (r"\bid\s*[:#]?\s*(\d+)"),
        (r"\bfor\s+(\d+)\b"),
        (r"\bnumber\s+(\d+)\b"),
        (r"\b(\d+)\b"),
    ]
    for pat in patterns:
        m = re.search(pat, msg)
        if m:
            return int(m.group(1))
    return fallback



async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Real MCP client — connects over SSE, does JSON-RPC 2.0 handshake,
    calls the tool, returns parsed result.

    Must be called with await from an async FastAPI endpoint.
    ExceptionGroup is unwrapped to expose the real underlying error.
    """
    try:
        async with sse_client(MCP_SERVER_SSE_URL, timeout=10, sse_read_timeout=600) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()              # MCP handshake
                result = await session.call_tool(tool_name, arguments)

                if result.isError:
                    return {"error": str(result.content)}

                text = result.content[0].text if result.content else "{}"
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text}

    except ExceptionGroup as eg:
        # Unwrap anyio TaskGroup exceptions to find the real cause
        for exc in eg.exceptions:
            if "connect" in str(exc).lower() or "connection" in str(type(exc).__name__).lower():
                raise HTTPException(
                    status_code=503,
                    detail="MCP server is not running. Start: python3 -m server.mcp_server --http --port 8001",
                )
        raise HTTPException(status_code=502, detail=f"MCP error: {eg.exceptions[0]}")
    except Exception as exc:
        err = str(exc)
        if any(k in err.lower() for k in ["connect", "refused", "unreachable"]):
            raise HTTPException(
                status_code=503,
                detail="MCP server is not running. Start: python3 -m server.mcp_server --http --port 8001",
            )
        raise HTTPException(status_code=502, detail=f"MCP error: {err}")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Finance MCP System — REST API",
    description=(
        "REST API for the Finance MCP server. "
        "POST /chat for natural language queries routed through the MCP protocol. "
        "POST /mcp/chat for the same with a full MCP trace. "
        "GET /mcp/tools to inspect available tools."
    ),
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_tools()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    customer_id: int
    symbol: str = "AAPL"  # optional, used when market price tool is selected

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
        "version": "3.0.0",
        "timestamp": str(datetime.now()),
        "how_it_works": (
            "POST /chat sends your message to the MCP client, which calls "
            "the MCP server (port 8001) using the MCP protocol. "
            "The MCP server picks the right finance tool and returns the result."
        ),
        "endpoints": {
            "chat":        "POST /chat          — natural language -> MCP -> tool",
            "mcp_chat":    "POST /mcp/chat      — same + full MCP trace",
            "mcp_tools":   "GET  /mcp/tools     — list all MCP tools",
            "mcp_execute": "POST /mcp/tools/execute — call a tool directly",
            "agents":      "POST /agent/{type}  — bypass MCP, call agent directly",
            "debug_tools": "GET  /debug/tools   — registry snapshot",
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


# ---------------------------------------------------------------------------
# /chat  — PRIMARY USER ENDPOINT (now MCP-powered)
#
# Flow:
#   1. Parse the user message to pick the best MCP tool
#   2. Call that tool on the MCP server via HTTP (MCP protocol)
#   3. Return the result in a clean response envelope
# ---------------------------------------------------------------------------
@app.post("/chat", tags=["Chat"])
async def chat(req: ChatRequest):
    """
    Send a natural language message. The server resolves the right MCP tool,
    calls the MCP server (port 8001), and returns the result.

    This endpoint IS the MCP client — it demonstrates MCP in action.
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


# ---------------------------------------------------------------------------
# /mcp/chat — full MCP interaction trace for debugging / demos
# ---------------------------------------------------------------------------
@app.post("/mcp/chat", tags=["Chat"])
async def mcp_chat(req: ChatRequest):
    """
    Full MCP trace: shows tool selection, arguments, the MCP server URL called,
    and the raw response. Use this to inspect MCP in action step by step.
    """
    tool_name, param_names = resolve_tool(req.message)
    effective_cid = extract_customer_id(req.message, req.customer_id)

    arguments = {}
    if "customer_id" in param_names:
        arguments["customer_id"] = effective_cid
    if "symbol" in param_names:
        arguments["symbol"] = req.symbol

    mcp_endpoint = MCP_SERVER_SSE_URL
    mcp_result = await call_mcp_tool(tool_name, arguments)

    return {
        "timestamp":    str(datetime.now()),
        "user_message": req.message,
        "customer_id":  req.customer_id,
        "mcp_trace": {
            "step_1_tool_resolved": tool_name,
            "step_2_arguments":     arguments,
            "step_3_mcp_endpoint":  mcp_endpoint,
            "step_4_mcp_response":  mcp_result,
        },
    }




# ---------------------------------------------------------------------------
# Context-aware summariser prompt
# ---------------------------------------------------------------------------
SIMPLE_TOOLS = {"get_customer", "get_loan_status", "get_market_price", "list_customers"}
DETAILED_TOOLS = {"full_customer_analysis", "get_risk_score", "check_fraud", "get_credit_score", "get_pnl", "get_trading_portfolio"}


def build_rich_response(tool_name: str, data: dict) -> str | None:
    """
    Build a detailed response directly from data for complex tools.
    Returns None for simple tools — those still go through Ollama.
    This bypasses phi3 for multi-section responses it cannot handle.
    """

    if tool_name == "full_customer_analysis":
        profile  = data.get("profile",  {})
        credit   = data.get("credit",   {})
        risk     = data.get("risk",     {})
        fraud    = data.get("fraud",    {})
        loans    = data.get("loans",    [])
        pnl_data = data.get("pnl",      {})

        name    = profile.get("name", "This customer")
        email   = profile.get("email", "—")
        since   = profile.get("created_at", "—")

        c_score  = credit.get("credit_score", "—")
        c_rating = credit.get("rating", "—")
        c_likely = credit.get("loan_approval_likelihood", "—")

        r_score  = risk.get("risk_score", "—")
        r_level  = risk.get("level", "—")
        r_rec    = risk.get("recommendation", "")
        r_factors= risk.get("key_risk_factors", [])

        f_flag   = fraud.get("fraud_flag", False)
        f_conf   = fraud.get("confidence", "")
        f_reason = fraud.get("reason", "")

        loan_summary = ""
        if isinstance(loans, list) and loans:
            total = sum(float(l.get("amount", 0)) for l in loans)
            statuses = list(set(l.get("status", "?") for l in loans))
            loan_summary = f"{name} has {len(loans)} loan(s) totalling ${total:,.2f} with status: {', '.join(statuses)}."
        else:
            loan_summary = f"{name} has no active loans on record."

        pnl_summary = ""
        if isinstance(pnl_data, dict) and "total_pnl" in pnl_data:
            total_pnl = float(pnl_data.get("total_pnl", 0))
            direction = "profit" if total_pnl >= 0 else "loss"
            pnl_summary = f" The portfolio shows an unrealised {direction} of ${abs(total_pnl):,.2f}."

        factors_summary = ""
        if r_factors:
            factors_summary = f" Key risk factors include: {'; '.join(r_factors[:3])}."

        fraud_summary = (
            f"No fraud detected ({f_conf.lower()} confidence). {f_reason}"
            if not f_flag
            else f"FRAUD FLAGGED ({f_conf.lower()} confidence). {f_reason}"
        )

        return (
            f"{name} (account since {since}, {email}) has a credit score of "
            f"{c_score} rated {c_rating}, with a {c_likely.lower()} likelihood of loan approval. "
            f"{loan_summary}"
            f" The overall risk score is {r_score}/100 — {r_level} risk.{factors_summary} "
            f"{r_rec} "
            f"Fraud check: {fraud_summary}."
            f"{pnl_summary}"
        )

    if tool_name == "get_risk_score":
        score   = data.get("risk_score", "—")
        level   = data.get("level", "—")
        factors = data.get("key_risk_factors", [])
        rec     = data.get("recommendation", "")
        factor_text = " The main risk factors are: " + "; ".join(factors[:3]) + "." if factors else ""
        return (
            f"This customer has a risk score of {score}/100, placing them in the "
            f"{level} risk category.{factor_text} {rec}"
        )

    if tool_name == "check_fraud":
        flag    = data.get("fraud_flag", False)
        conf    = data.get("confidence", "")
        reason  = data.get("reason", "")
        patterns= data.get("suspicious_patterns", [])
        status  = "flagged for potential fraud" if flag else "cleared — no fraud detected"
        pattern_text = ""
        if flag and patterns:
            pattern_text = f" Suspicious patterns identified: {'; '.join(patterns[:3])}."
        return (
            f"This customer has been {status} ({conf.lower()} confidence). "
            f"{reason}{pattern_text}"
        )

    if tool_name == "get_credit_score":
        score   = data.get("credit_score", "—")
        rating  = data.get("rating", "—")
        likely  = data.get("loan_approval_likelihood", "—")
        factors = data.get("factors", [])
        factor_text = " Factors considered: " + ", ".join(factors[:3]) + "." if factors else ""
        return (
            f"Credit score is {score} ({rating} rating), with a {likely.lower()} "
            f"likelihood of loan approval.{factor_text}"
        )

    if tool_name == "get_pnl":
        total   = data.get("total_pnl")
        positions = data.get("positions", [])
        if total is None:
            return None
        direction = "profit" if float(total) >= 0 else "loss"
        pos_text = ""
        if isinstance(positions, list) and positions:
            gainers = [p for p in positions if float(p.get("pnl", 0)) > 0]
            losers  = [p for p in positions if float(p.get("pnl", 0)) < 0]
            pos_text = f" {len(gainers)} position(s) are profitable and {len(losers)} are at a loss."
        return (
            f"The portfolio has a total unrealised {direction} of ${abs(float(total)):,.2f}.{pos_text}"
        )

    if tool_name == "get_trading_portfolio":
        if not isinstance(data, list):
            return None
        if not data:
            return "No portfolio holdings found for this customer."
        total_value = sum(
            float(p.get("quantity", 0)) * float(p.get("avg_price", 0))
            for p in data
        )
        symbols = [p.get("symbol", "?") for p in data]
        return (
            f"The portfolio holds {len(data)} position(s) across {', '.join(symbols)}, "
            f"with a total book value of approximately ${total_value:,.2f}."
        )

    return None  # simple tools — let Ollama handle it

def build_summary_prompt(tool_name: str) -> str:
    """Return a system prompt appropriate for the tool complexity."""
    if tool_name == "full_customer_analysis":
        return (
            "You are a senior financial analyst writing a client briefing. "
            "Write a detailed 4-6 sentence summary covering: "
            "1) customer identity, "
            "2) credit standing and loan situation, "
            "3) risk level and key risk factors, "
            "4) fraud status, "
            "5) portfolio performance if available, "
            "6) an overall recommendation. "
            "Be specific — use the actual numbers and values from the data. "
            "Do not use bullet points. Write in flowing prose. "
            'Reply with JSON only: {"reply": "<your detailed summary>"}'
        )
    elif tool_name in ("get_risk_score", "check_fraud"):
        return (
            "You are a risk analyst explaining findings to a bank manager. "
            "Write 2-3 sentences: explain the score or flag, the key reasons, "
            "and what action the bank should take. Use the actual values. "
            'Reply with JSON only: {"reply": "<your explanation>"}'
        )
    elif tool_name in ("get_credit_score", "get_pnl", "get_trading_portfolio"):
        return (
            "You are a financial advisor explaining results to a client. "
            "Write 2-3 sentences using the actual data values. "
            "Explain what the numbers mean in plain English. "
            'Reply with JSON only: {"reply": "<your explanation>"}'
        )
    else:
        return 'Reply with JSON only: {"reply": "<one sentence summary of the data>"}'

# ---------------------------------------------------------------------------
# /chat/respond — conversational endpoint
#
# Flow:
#   1. Resolve + call the MCP tool (same as /chat)
#   2. Pass the raw tool result to Ollama
#   3. Ollama writes a plain-English reply the user can read
#   4. Returns { reply, tool, raw } so the frontend can show both
# ---------------------------------------------------------------------------
@app.post("/chat/respond", tags=["Chat"])
async def chat_respond(req: ChatRequest):
    """
    Natural language chat endpoint.
    Calls the right MCP tool then asks Ollama to explain the result
    in plain English. Returns a conversational reply alongside the raw data.
    """
    import time as _time
    from client.llm.llm_engine import safe_json_llm
    _start = _time.time()

    tool_name, param_names = resolve_tool(req.message)
    effective_cid = extract_customer_id(req.message, req.customer_id)

    arguments = {}
    if "customer_id" in param_names:
        arguments["customer_id"] = effective_cid
    if "symbol" in param_names:
        arguments["symbol"] = req.symbol

    raw = await call_mcp_tool(tool_name, arguments)

    # Try rich response first (complex tools) — bypasses phi3 limitations
    reply = build_rich_response(tool_name, raw)

    if reply is None:
        # Simple tool — ask Ollama for a one-sentence summary
        system = build_summary_prompt(tool_name)
        display = dict(raw) if isinstance(raw, dict) else raw
        if isinstance(display, dict):
            if not display.get("fraud_flag", True):
                display.pop("suspicious_patterns", None)
            display.pop("customer_id", None)
        if isinstance(display, list):
            data_str = "\n".join(str(i) for i in display)
        elif isinstance(display, dict):
            data_str = "\n".join(f"{k}: {v}" for k, v in display.items())
        else:
            data_str = str(display)
        user = f"User asked: {req.message}\n\nDatabase record:\n{data_str}"
        llm_result = safe_json_llm(system, user)
        if "error" in llm_result:
            reply = _format_fallback(tool_name, raw)
        else:
            raw_reply = llm_result.get("reply") or llm_result.get("response") or llm_result.get("text") or ""
            if isinstance(raw_reply, dict):
                raw_reply = raw_reply.get("text") or str(raw_reply)
            raw_reply = str(raw_reply).strip()
            if raw_reply.startswith("{") or not raw_reply:
                reply = _format_fallback(tool_name, raw)
            else:
                reply = raw_reply

    # Log the session
    try:
        from server.logger_agent import log_agent_session, new_session_id
        log_agent_session(
            session_id         = new_session_id(),
            user_query         = req.message,
            customer_id        = effective_cid,
            agents_planned     = [tool_name],
            agent_results      = {tool_name: {"steps": [], "observations": {tool_name: raw}}},
            rag_retrieved      = {},
            permission_denials = [],
            final_answer       = reply,
            total_latency_ms   = (_time.time() - _start) * 1000,
        )
    except Exception as e:
        print(f"⚠️  chat_respond logging failed: {e}")

    return {
        "timestamp":   str(datetime.now()),
        "customer_id": req.customer_id,
        "message":     req.message,
        "mcp_tool":    tool_name,
        "reply":       reply,
        "raw":         raw,
    }



# ---------------------------------------------------------------------------
# /chat/stream — SSE streaming endpoint with live progress steps
#
# Streams progress events as the request moves through the pipeline:
#   step: routing → mcp_call → llm_summarise → done
# Frontend listens and shows a live activity feed like Claude does.
# ---------------------------------------------------------------------------
TOOL_LABELS = {
    "get_customer":           ("👤", "Fetching customer profile"),
    "get_loan_status":        ("🏦", "Checking loan records"),
    "get_credit_score":       ("📊", "Calculating credit score"),
    "get_risk_score":         ("⚠️",  "Running risk assessment"),
    "check_fraud":            ("🔍", "Running fraud detection"),
    "get_trading_portfolio":  ("📈", "Loading portfolio data"),
    "get_pnl":                ("💰", "Calculating profit & loss"),
    "get_market_price":       ("📉", "Fetching market prices"),
    "full_customer_analysis": ("📋", "Running full financial analysis"),
    "list_customers":         ("📁", "Listing customers"),
}

AGENT_LABELS = {
    "get_customer":           "Customer Agent",
    "get_loan_status":        "Loan Agent",
    "get_credit_score":       "Loan Agent",
    "get_risk_score":         "Risk Agent",
    "check_fraud":            "Risk Agent",
    "get_trading_portfolio":  "Trading Agent",
    "get_pnl":                "Trading Agent",
    "get_market_price":       "Trading Agent",
    "full_customer_analysis": "Orchestrator",
    "list_customers":         "Customer Agent",
}


@app.get("/chat/stream", tags=["Chat"])
async def chat_stream(message: str, customer_id: int = 1, symbol: str = "AAPL"):
    """
    SSE streaming endpoint. Sends progress events then the final result.
    Frontend connects via EventSource and displays live steps.
    """
    from client.llm.llm_engine import safe_json_llm

    async def event_generator():
        def step(status: str, label: str, detail: str = ""):
            data = json.dumps({"status": status, "label": label, "detail": detail})
            return f"data: {data}\n\n"

        try:
            # Step 1 — routing
            yield step("routing", "Routing query", "Analysing your message...")
            await asyncio.sleep(0)

            tool_name, param_names = resolve_tool(message)
            effective_cid = extract_customer_id(message, customer_id)
            icon, tool_label = TOOL_LABELS.get(tool_name, ("⚙️", tool_name))
            agent = AGENT_LABELS.get(tool_name, "Agent")

            yield step("routed", f"Routed to {agent}", f"Selected tool: {tool_name}")
            await asyncio.sleep(0)

            # Step 2 — MCP tool call
            arguments = {}
            if "customer_id" in param_names:
                arguments["customer_id"] = effective_cid
            if "symbol" in param_names:
                arguments["symbol"] = symbol

            yield step("mcp_call", f"{icon} {tool_label}", f"Calling MCP server via SSE...")
            await asyncio.sleep(0)

            raw = await call_mcp_tool(tool_name, arguments)

            if "error" in raw:
                yield step("error", "Tool error", raw["error"])
                yield step("done", "done", json.dumps({"error": raw["error"], "raw": raw}))
                return

            yield step("mcp_done", f"{icon} Data received", f"MCP tool returned {len(str(raw))} bytes")
            await asyncio.sleep(0)

            # Step 3 — build response
            reply = build_rich_response(tool_name, raw)

            if reply is not None:
                # Complex tool — rich response built directly, no Ollama needed
                yield step("llm_done", "Analysis complete", "Rich response generated")
                await asyncio.sleep(0)
            else:
                # Simple tool — ask Ollama for a short summary
                yield step("llm", "Summarising with Ollama", f"Asking {os.getenv('OLLAMA_MODEL', 'phi3')} to explain...")
                await asyncio.sleep(0)

                system = build_summary_prompt(tool_name)
                display = dict(raw) if isinstance(raw, dict) else raw
                if isinstance(display, dict):
                    if not display.get("fraud_flag", True):
                        display.pop("suspicious_patterns", None)
                    display.pop("customer_id", None)
                if isinstance(display, list):
                    data_str = "\n".join(str(i) for i in display)
                elif isinstance(display, dict):
                    data_str = "\n".join(f"{k}: {v}" for k, v in display.items())
                else:
                    data_str = str(display)

                user = f"User asked: {message}\n\nDatabase record:\n{data_str}"
                llm_result = safe_json_llm(system, user)

                if "error" in llm_result:
                    reply = _format_fallback(tool_name, raw)
                    yield step("llm_done", "Using fallback summary", "Ollama unavailable")
                else:
                    raw_reply = llm_result.get("reply") or llm_result.get("response") or llm_result.get("text") or ""
                    if isinstance(raw_reply, dict):
                        raw_reply = raw_reply.get("text") or str(raw_reply)
                    raw_reply = str(raw_reply).strip()
                    if raw_reply.startswith("{") or not raw_reply:
                        reply = _format_fallback(tool_name, raw)
                    else:
                        reply = raw_reply
                    yield step("llm_done", "Response ready", "")
                await asyncio.sleep(0)

            # Final result
            result = {
                "timestamp":   str(datetime.now()),
                "customer_id": customer_id,
                "message":     message,
                "mcp_tool":    tool_name,
                "reply":       reply,
                "raw":         raw,
            }
            yield step("done", "done", json.dumps(result))

        except Exception as exc:
            yield step("error", "Unexpected error", str(exc))
            yield step("done", "done", json.dumps({"error": str(exc)}))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
        return f"Found {len(loans)} loan(s) totalling ${total:,.2f}. Statuses: {', '.join(set(l.get('status','?') for l in loans))}."

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


# ---------------------------------------------------------------------------
# /agent/react — ReAct agent endpoint (streaming)
# Shows the full think→act→observe loop live via SSE
# ---------------------------------------------------------------------------
@app.get("/agent/react/stream", tags=["ReAct Agent"])
async def react_agent_stream(message: str, customer_id: int = 1):
    """
    Run the ReAct agent and stream each step as an SSE event.
    Shows thought, action, and observation for each loop iteration.
    """
    async def generate():
        def evt(status, label, detail=""):
            return f"data: {json.dumps({'status': status, 'label': label, 'detail': detail})}\n\n"

        yield evt("start", "ReAct Agent started", f"Question: {message}")
        await asyncio.sleep(0)

        from server.tools.tool_registry import registry
        from client.agents.orchestrator import (
            build_react_prompt, execute_tool, AVAILABLE_TOOLS,
            _summarise_observations, build_rich_response_from_steps,
        )
        from client.llm.llm_engine import safe_json_llm

        history = []
        MAX_STEPS = 5

        from client.agents.orchestrator import plan_agents, run_agents, synthesise, AGENTS

        # Step 1 — Plan which agents to call
        yield evt("thinking", "🧠 Orchestrator planning", "Deciding which agents to call...")
        await asyncio.sleep(0)

        agent_names = plan_agents(message)
        yield evt("planned", f"📋 Plan: {', '.join(agent_names)}", f"{len(agent_names)} agent(s) selected")
        await asyncio.sleep(0)

        # Step 2 — Run each agent
        agent_results = {}
        all_steps = []

        for agent_name in agent_names:
            icon = AGENTS[agent_name]["icon"]
            yield evt("agent_start", f"{icon} {agent_name.title()} Agent starting", "")
            await asyncio.sleep(0)

            # Send keepalive comment to prevent browser SSE timeout (default 30s)
            yield ": keepalive\n\n"
            await asyncio.sleep(0)

            agent_fn = AGENTS[agent_name]["fn"]
            result   = agent_fn(message, customer_id)
            agent_results[agent_name] = result

            steps = result.get("steps", [])
            for s in steps:
                yield evt("tool_call", f"  ⚡ {s.get('action','?')}", s.get("thought","")[:60])
                await asyncio.sleep(0)
                all_steps.append({**s, "agent": agent_name})

            yield evt("agent_done", f"{icon} {agent_name.title()} Agent done", f"{len(steps)} tool call(s)")
            await asyncio.sleep(0)

        # Step 3 — Synthesise
        yield evt("thinking", "🔀 Synthesising results", "Combining all agent outputs...")
        await asyncio.sleep(0)

        final_answer = synthesise(message, agent_results)
        all_raw      = {name: r.get("observations", {}) for name, r in agent_results.items()}

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
    """Run the ReAct agent and return the full result."""
    result = react_agent(req.message, req.customer_id)
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
        "raw":         {s["action"]: s.get("obs", s.get("observation", {})) for s in result.get("steps", [])},
    }


# ---------------------------------------------------------------------------
# /rag — Query the policy knowledge base directly
# ---------------------------------------------------------------------------
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
        from rag.embedder import index_count, INDEX_FILE, BASE_DIR
        count = index_count()
        return {
            "status":    "ready" if count > 0 else "empty",
            "documents": count,
            "index_file": str(INDEX_FILE),
            "index_exists": INDEX_FILE.exists(),
            "message":   "Index ready" if count > 0 else "Run: PYTHONPATH=. python3.12 rag/build_index.py",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/rag/test", tags=["RAG"])
def rag_test():
    """Test RAG retrieval with sample queries to verify it is working."""
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
            results[category] = [
                {"title": d["title"], "score": d["score"]}
                for d in docs
            ]
        return {
            "status":  "working",
            "results": results,
            "message": "RAG is retrieving policies correctly" if any(results.values()) else "No results found",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# /logs — Query agent session logs and security audit
# ---------------------------------------------------------------------------
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
                    "session_id": log["session_id"],
                    "query":      log["user_query"],
                    "customer_id":log["customer_id"],
                    "timestamp":  log["created_at"],
                    **d,
                })
        return {
            "total_denials": len(denials),
            "denials":       denials,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/logs/tools", tags=["Logs"])
def get_tool_usage_log(limit: int = 50):
    """Return recent tool call logs from the server tools."""
    from server.db import SessionLocal
    from server.models.tool_log import ToolLog
    db = SessionLocal()
    try:
        logs = db.query(ToolLog).order_by(ToolLog.created_at.desc()).limit(limit).all()
        return {
            "total": len(logs),
            "logs": [
                {
                    "id":             log.id,
                    "tool_name":      log.tool_name,
                    "response_ms":    float(log.response_time_ms or 0),
                    "created_at":     str(log.created_at),
                    "query":          log.user_query,
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
        "permissions": {
            agent: list(tools)
            for agent, tools in ROLE_PERMISSIONS.items()
        },
        "total_agents": len(ROLE_PERMISSIONS),
        "total_rules":  sum(len(t) for t in ROLE_PERMISSIONS.values()),
    }


@app.post("/security/check", tags=["Security"])
def check_permission_endpoint(payload: dict):
    """
    Test whether an agent is allowed to call a tool.
    Body: { "agent": "loan_agent", "tool": "risk_score_tool" }
    """
    from client.security.permission_checker import check_permission
    agent = payload.get("agent", "")
    tool  = payload.get("tool", "")
    allowed = check_permission(agent, tool)
    return {
        "agent":   agent,
        "tool":    tool,
        "allowed": allowed,
        "reason":  f"{agent} {'can' if allowed else 'cannot'} call {tool}",
    }

# ---------------------------------------------------------------------------
# AGENT ENDPOINTS — bypass MCP, call a specific agent directly
# ---------------------------------------------------------------------------
@app.post("/agent/customer", tags=["Agents (direct)"])
def agent_customer(req: QueryRequest):
    """Call the customer agent directly (bypasses MCP)."""
    return {"agent": "customer_agent", "data": customer_agent(req.query, req.customer_id)}


@app.post("/agent/loan", tags=["Agents (direct)"])
def agent_loan(req: QueryRequest):
    """Call the loan agent directly (bypasses MCP)."""
    return {"agent": "loan_agent", "data": loan_agent(req.query, req.customer_id)}


@app.post("/agent/trading", tags=["Agents (direct)"])
def agent_trading(req: QueryRequest):
    """Call the trading agent directly (bypasses MCP)."""
    return {"agent": "trading_agent", "data": trading_agent(req.query, req.customer_id)}


@app.post("/agent/risk", tags=["Agents (direct)"])
def agent_risk(req: QueryRequest):
    """Call the risk agent directly (bypasses MCP)."""
    return {"agent": "risk_agent", "data": risk_agent(req.query, req.customer_id)}


# ---------------------------------------------------------------------------
# DEBUG
# ---------------------------------------------------------------------------
@app.get("/debug/tools", tags=["Debug"])
def debug_tools():
    """Show every tool currently registered in the local tool registry."""
    return {
        "total_tools": len(registry.tools),
        "tools": [
            {"name": name, "agent": t["agent"], "description": t.get("description", "")}
            for name, t in registry.tools.items()
        ],
    }


@app.get("/debug/routes", tags=["Debug"])
def debug_routes():
    """Show all registered API routes."""
    return {
        "routes": [
            {"path": route.path, "methods": list(route.methods)}
            for route in app.routes
            if hasattr(route, "methods")
        ]
    }


# ---------------------------------------------------------------------------
# MCP gateway — mounts /mcp/tools, /mcp/tools/schema, /mcp/tools/execute
# ---------------------------------------------------------------------------
app.include_router(mcp_router)