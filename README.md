# Multi-Agent AI Framework

![CI](https://github.com/Elamathy-S/multi-agent-ai-framework/actions/workflows/ci.yml/badge.svg)

A multi-agent system where AI agents handle financial tasks — risk assessment, fraud detection, credit scoring, portfolio analysis — and talk to each other through the Model Context Protocol (MCP). Each agent reasons independently, decides which tools to use, and can only access data it's authorised for.

Built as a Masters project to explore how agentic AI systems work at the protocol level.

## What it does

You ask a question like "give me a full analysis of customer 3" and the system:

1. Figures out which agents need to run (customer, loan, risk, trading)
2. Runs them at the same time
3. Each agent thinks about what tools to call, calls them through MCP, looks at the results, and decides what to do next
4. Combines everything into a report
5. The frontend shows the whole reasoning process live as it happens

Every tool call goes through the MCP protocol (JSON-RPC 2.0 over SSE) — agents don't call Python functions directly. The same MCP server works with Claude Desktop.

## Architecture

```
Frontend (HTML/JS)
    │
    ▼ SSE stream
FastAPI Server (:8080)
    │
    ├── Orchestrator ── picks agents, runs them concurrently
    │       │
    │       ├── Customer Agent ── profiles
    │       ├── Loan Agent ────── loans, credit scores
    │       ├── Risk Agent ────── risk scoring, fraud detection
    │       └── Trading Agent ─── portfolio, PnL
    │               │
    │               ▼
    │       ReAct Loop (think → act → observe → repeat)
    │               │
    │               ▼ permission check (RBAC)
    │
    ▼ JSON-RPC 2.0 over SSE
MCP Server (:8001)
    │
    ├── 10 tools, 4 resources, 4 prompts
    │
    ├── SQLite (customer, loan, trade data)
    └── RAG (policy documents via ChromaDB + TF-IDF)
```

## Key features

**MCP protocol** — agents communicate through JSON-RPC 2.0, not function calls. Add a new tool with one `@mcp.tool()` decorator and every agent can discover it.

**ReAct reasoning** — agents use a think-act-observe loop where the LLM decides what to do next. If the LLM can't reason properly (happens ~67% of the time with phi3), it falls back to calling all its tools — so data is always correct.

**RBAC** — database-backed role-based access control. Each agent has a role with scoped permissions. The risk agent can't read customer profiles. Permissions can be changed at runtime through the API. Every access check is logged to an audit trail.

**RAG** — agents retrieve relevant policy documents (loan approval rules, risk thresholds) before reasoning, so decisions are grounded in domain knowledge.

**Live trace** — the frontend streams every step as it happens: which agents were selected, what each agent is thinking, which tools are being called, what data came back.

## Tech stack

Python, FastAPI, MCP v2, Ollama (phi3), SQLAlchemy, SQLite, ChromaDB, Docker, GitHub Actions, pytest

## Quick start

**With Docker:**
```bash
git clone https://github.com/Elamathy-S/multi-agent-ai-framework.git
cd multi-agent-ai-framework
docker-compose up
```

**Without Docker:**
```bash
git clone https://github.com/Elamathy-S/multi-agent-ai-framework.git
cd multi-agent-ai-framework
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

ollama serve && ollama pull phi3

# Terminal 1 — MCP server
PYTHONPATH=. python3 -m server.mcp_server --http --port 8001

# Terminal 2 — Client server
PYTHONPATH=. uvicorn client.main:app --reload --port 8080
```

Open `frontend/index.html` and try "full analysis of customer 3".

## API highlights

| Endpoint | What it does |
|----------|-------------|
| `GET /agent/react/stream` | Full multi-agent run with live SSE trace |
| `POST /chat` | Single tool call, keyword-routed |
| `GET /mcp/surface` | See all MCP tools, resources, prompts |
| `GET /security/roles` | View RBAC roles and permissions |
| `POST /security/roles/{name}/grant` | Grant a tool to a role at runtime |
| `GET /security/audit` | View access audit log |
| `GET /docs` | Swagger UI |

## RBAC

Roles and permissions are stored in the database, not hardcoded. You can manage them at runtime:

```bash
# See all roles
curl http://localhost:8080/security/roles

# Create a new role
curl -X POST http://localhost:8080/security/roles \
  -d '{"name": "audit_agent", "description": "Read-only", "permissions": ["get_customer"]}'

# Grant a permission
curl -X POST http://localhost:8080/security/roles/risk_agent/grant \
  -d '{"tool": "get_customer"}'

# Revoke it
curl -X POST http://localhost:8080/security/roles/risk_agent/revoke \
  -d '{"tool": "get_customer"}'

# View audit trail
curl http://localhost:8080/security/audit
```

Every permission check — allowed or denied — is logged with timestamp, agent, tool, and session ID.

## Testing and evaluation

```bash
# Unit tests (72 cases, ~1s)
PYTHONPATH=. pytest tests/ -v

# Validation checks (31 cases, ~10s)
PYTHONPATH=. python evals/run_evals.py

# AI quality metrics — robustness, precision/recall, resilience (~10s)
PYTHONPATH=. python evals/eval_quality.py

# Live AI evals — real LLM calls, measures ReAct success rate (~20min)
PYTHONPATH=. python evals/eval_live.py
```

Live eval results with phi3: 83% overall. ReAct reasoning succeeds 33% of the time — the rest falls back to sequential execution. A stronger model would improve this, and the eval framework measures that directly.

## Project structure

```
server/           MCP server, tools, database, LLM engine
client/           FastAPI app, agents, orchestrator, RBAC
rag/              RAG pipeline (ChromaDB + TF-IDF)
frontend/         Chat UI with live agent trace
tests/            72 unit + integration tests
evals/            Validation, quality metrics, live AI evals
```

## Design decisions

**Why MCP?** — One protocol for everything. Claude Desktop connects to the same server. Agents are decoupled from tool implementations.

**Why ReAct with fallback?** — Best case: the agent intelligently picks tools. Worst case: it calls everything. Data is always correct either way.

**Why fresh MCP connection per tool?** — The LLM takes 10-30s between tool calls. A long-lived SSE connection would timeout. One connection per tool call adds ~50ms but never fails.

**Why database RBAC?** — A hardcoded dict is a demo. Database-backed roles with runtime management and audit logging is production thinking.