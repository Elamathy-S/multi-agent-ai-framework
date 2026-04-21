from fastapi import APIRouter
from backend.mcp.schemas import TOOLS
from backend.mcp.executor import execute_tool
from backend.tools.tool_registry import registry
from backend.agents.orchestrator import orchestrator

router = APIRouter(prefix="/mcp")


# -----------------------------
# 1. LIST ALL TOOLS
# -----------------------------
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


# -----------------------------
# 2. TOOL SCHEMAS (LLM USES THIS)
# -----------------------------
@router.get("/tools/schema")
def tool_schema():
    return {"tools": TOOLS}


# -----------------------------
# 3. EXECUTE TOOL (CORE MCP)
# -----------------------------
@router.post("/tools/execute")
def run_tool(payload: dict):

    tool = payload.get("tool")
    args = payload.get("arguments", {})

    return {
        "tool": tool,
        "output": execute_tool(tool, args)
    }


# -----------------------------
# 4. RUN AGENT
# -----------------------------
@router.post("/agents/run")
def run_agent(payload: dict):

    query = payload.get("query")
    customer_id = payload.get("customer_id", 1)

    result = orchestrator(query, customer_id)

    return {
        "result": result
    }
