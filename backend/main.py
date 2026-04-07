from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime

# Agents (optional direct access endpoints)
from agents.customer_agent import customer_agent
from agents.loan_agent import loan_agent
from agents.trading_agent import trading_agent
from agents.risk_agent import risk_agent

# Orchestrator (your separate file)
from agents import orchestrator

# Tools (for health check)
from mcp.customer_tools import get_customer_profile


app = FastAPI(title="MCP Financial Multi-Agent System")


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