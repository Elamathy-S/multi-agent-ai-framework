from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime

# Orchestrator
from backend.agents import orchestrator

# Tools (for health check)
from backend.tools.customer_tools import get_customer_profile
from backend.tools.credit_score_tool import credit_score_tool
from backend.tools.tool_registry import init_tools

from backend.agents.customer_agent import customer_agent


app = FastAPI(title="MCP Financial Multi-Agent System")

@app.on_event("startup")
def startup_event():
    init_tools()


# -----------------------------
# Request Model
# -----------------------------
class QueryRequest(BaseModel):
    query: str
    customer_id: int


# -----------------------------
# ROOT / HEALTH
# -----------------------------
@app.get("/")
def root():
    return {
        "message": "🚀 MCP Financial Multi-Agent System Running",
        "timestamp": str(datetime.now())
    }


@app.get("/health")
def health_check():
    try:
        # simple DB + tool check
        get_customer_profile(1)
        return {
            "status": "healthy",
            "timestamp": str(datetime.now())
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# -----------------------------
# 🔥 ORCHESTRATOR ENDPOINT (MAIN ENTRY)
# -----------------------------
@app.post("/query")
def handle_query(req: QueryRequest):
    result = orchestrator.orchestrator(req.query, req.customer_id)

    return {
        "timestamp": str(datetime.now()),
        "response": result
    }


# -----------------------------
# AGENT ENDPOINTS (OPTIONAL)
# -----------------------------
@app.post("/agent/customer")
def customer(req: QueryRequest):
    return {
        "agent": "customer_agent",
        "data": customer_agent(req.query, req.customer_id)
    }


@app.post("/agent/loan")
def loan(req: QueryRequest):
    return {
        "agent": "loan_agent",
        "data": loan_agent(req.query, req.customer_id)
    }


@app.post("/agent/trading")
def trading(req: QueryRequest):
    return {
        "agent": "trading_agent",
        "data": trading_agent(req.query, req.customer_id)
    }


@app.post("/agent/risk")
def risk(req: QueryRequest):
    return {
        "agent": "risk_agent",
        "data": risk_agent(req.query, req.customer_id)
    }


@app.post("/credit-score")
def get_credit_score(req: QueryRequest):
    result = credit_score_tool(req.customer_id)

    return {
        "timestamp": str(datetime.now()),
        "customer_id": req.customer_id,
        "credit_score": result
    }

# -----------------------------
# DEBUG ENDPOINT (VERY USEFUL)
# -----------------------------
@app.get("/debug/tools")
def debug_tools():
    from mcp.tool_registry import TOOLS
    return {
        "total_tools": len(TOOLS),
        "tools": list(TOOLS.keys())
    }
    
from fastapi import APIRouter
from backend.tools.tool_registry import registry
from backend.agents.orchestrator import orchestrator

router = APIRouter(prefix="/mcp")


# -----------------------
# LIST TOOLS
# -----------------------
@router.get("/tools")
def list_tools():
    return {
        "tools": [
            {
                "name": name,
                "agent": t["agent"],
                "description": t.get("description", "")
            }
            for name, t in registry.tools.items()
        ]
    }


# -----------------------
# EXECUTE TOOL DIRECTLY
# -----------------------
@router.post("/tools/execute")
def execute_tool(payload: dict):

    tool = registry.get(payload["tool"])

    if not tool:
        return {"error": "Tool not found"}

    result = tool["function"](**payload.get("args", {}))

    return {
        "tool": payload["tool"],
        "result": result
    }


# -----------------------
# RUN AGENT
# -----------------------
@router.post("/agents/run")
def run_agent(payload: dict):

    result = orchestrator(
        payload["query"],
        payload.get("customer_id", 1)
    )

    return {
        "agent": payload["agent"],
        "result": result
    }


from backend.llm.ollama_llm import ollama_tool_call
from backend.mcp.executor import execute_tool
from backend.mcp.schemas import TOOLS


@app.post("/mcp/chat")
def mcp_chat(req: QueryRequest):

    # 🔥 REAL LLM DECISION
    decision = ollama_tool_call(req.query, TOOLS)

    if not decision.get("tool"):
        return {"response": "No tool selected"}

    result = execute_tool(
        decision["tool"],
        decision.get("arguments", {})
    )

    return {
        "tool_used": decision["tool"],
        "tool_result": result
    }

from backend.mcp.gateway import router as mcp_router

app.include_router(mcp_router)
