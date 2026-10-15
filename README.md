# Multi-Agent AI Framework

A modular multi-agent system for financial operations, built on the **Model Context Protocol (MCP)**. Specialist AI agents handle risk assessment, fraud detection, credit scoring, loan analysis, and portfolio management — each reasoning independently through a ReAct loop and communicating exclusively via the MCP protocol.

Built as a Masters project to explore agentic AI architectures with real protocol-level communication, not just function calls.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS)                     │
│              Chat UI with live agent trace                │
└──────────────────────┬──────────────────────────────────┘
                       │ SSE stream
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Client Server (:8080)                │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │                  Orchestrator                        │ │
│  │   Plans which agents to call, runs them              │ │
│  │   concurrently, synthesises final answer             │ │
│  │                                                      │ │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ │ │
│  │  │ Customer │ │   Loan   │ │  Risk  │ │ Trading  │ │ │
│  │  │  Agent   │ │  Agent   │ │ Agent  │ │  Agent   │ │ │
│  │  └────┬─────┘ └────┬─────┘ └───┬────┘ └────┬─────┘ │ │
│  │       │             │           │            │       │ │
│  │       └─────────────┴─────┬─────┴────────────┘       │ │
│  │                   ReAct Loop                         │ │
│  │            think → act → observe → repeat            │ │
│  └───────────────────────┬─────────────────────────────┘ │
│                          │ Permission check               │
└──────────────────────────┼──────────────────────────────┘
                           │ JSON-RPC 2.0 over SSE
┌──────────────────────────▼──────────────────────────────┐
│                MCP Server (:8001)                         │
│                                                          │
│   10 Tools         4 Resources        4 Prompts          │
│   @mcp.tool()      finance://...      workflow templates  │
│                                                          │
│   get_customer          get_risk_score    check_fraud     │
│   get_loan_status       get_credit_score  get_pnl         │
│   get_trading_portfolio get_market_price  list_customers  │
│   full_customer_analysis                                  │
└──────────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
        ┌─────▼─────┐           ┌──────▼──────┐
        │  SQLite    │           │  RAG Index   │
        │  Database  │           │  ChromaDB +  │
        │            │           │  TF-IDF      │
        └────────────┘           └─────────────┘
```

### How a query flows through the system

1. **User sends a question** — "Give me a full analysis of customer 3"
2. **Orchestrator plans** — keyword + LLM routing selects which agents to activate
3. **Agents run concurrently** — each enters a ReAct reasoning loop
4. **ReAct loop** — the LLM decides which tool to call based on prior observations, or finishes when it has enough data
5. **Every tool call goes through MCP** — permission check → JSON-RPC 2.0 request → MCP server executes → result returned
6. **Synthesise** — per-tool formatters build a structured report, then Ollama writes a conversational summary
7. **Live trace** — the frontend streams every step (planning, agent start, tool calls, reasoning) via SSE

### Why MCP?

The MCP server is the **single source of truth** for all tools. Agents don't import Python functions — they discover and call tools through the protocol. This means:

- **Claude Desktop** can connect to the same MCP server and use all 10 tools
- Adding a new tool = one `@mcp.tool()` decorator in `mcp_server.py`
- Agents are isolated from tool implementations — they only know tool names and descriptions
- The permission system gates access before any MCP call is made

---

## Features

- **MCP-powered execution** — all tool calls use JSON-RPC 2.0 over SSE, not direct function imports
- **ReAct reasoning** — agents think before acting, with graceful fallback when the LLM can't reason
- **4 specialist agents** — Customer, Loan, Risk, Trading — each with scoped permissions
- **Permission enforcement** — agents can only call tools they're authorised for; cross-agent access is blocked and logged
- **RAG integration** — agents retrieve relevant policy documents (loan rules, risk thresholds) from ChromaDB/TF-IDF before reasoning
- **Live agent trace** — the frontend streams every step: orchestrator planning, agent start/done, tool calls with thoughts, data summaries
- **Concurrent execution** — independent agents run in parallel via `asyncio.gather`
- **Ollama summarisation** — structured data is passed through a local LLM for conversational summaries
- **Session logging** — every orchestration run is logged with agent results, tool calls, RAG retrievals, and permission denials
- **62 test cases** — unit tests for routing, permissions, and formatting; integration tests for the full MCP pipeline

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Protocol | MCP (Model Context Protocol) v2.x — JSON-RPC 2.0 over SSE |
| Backend | Python, FastAPI, async/await |
| LLM | Ollama (phi3 / phi3:mini) — runs locally, no API keys needed |
| Database | SQLite (dev) — swappable to PostgreSQL via `DATABASE_URL` |
| RAG | ChromaDB for vector search, TF-IDF fallback |
| Frontend | HTML, CSS, vanilla JS — SSE streaming |
| Testing | pytest, pytest-asyncio |

---

## Project Structure

```
├── server/                     # MCP server + tools + database
│   ├── mcp_server.py           # MCP server — 10 tools, 4 resources, 4 prompts
│   ├── db.py                   # SQLAlchemy engine + session
│   ├── tools/                  # Tool implementations (customer, loan, risk, trading)
│   ├── llm/                    # Ollama integration (safe_json_llm)
│   ├── models/                 # SQLAlchemy models (ToolLog, AgentLog)
│   └── logger_agent.py         # Session logging
│
├── client/                     # FastAPI client server + agents
│   ├── main.py                 # FastAPI app — all endpoints
│   ├── tool_router.py          # Query → MCP tool routing (single source)
│   ├── mcp/
│   │   ├── client.py           # MCPClient — async MCP v2 client wrapper
│   │   └── gateway.py          # /mcp/* introspection endpoints
│   ├── agents/
│   │   ├── orchestrator.py     # Plans agents, runs concurrently, synthesises
│   │   ├── react.py            # ReAct reasoning engine (think→act→observe)
│   │   ├── base.py             # run_tool() — permission check + MCP call
│   │   ├── customer_agent.py   # Profile lookups
│   │   ├── loan_agent.py       # Loans + credit scoring
│   │   ├── risk_agent.py       # Risk scoring + fraud detection
│   │   └── trading_agent.py    # Portfolio + PnL
│   └── security/
│       ├── permissions.py      # Agent → tool permission matrix
│       └── permission_checker.py
│
├── rag/                        # Retrieval-Augmented Generation
│   ├── embedder.py             # ChromaDB + TF-IDF indexing
│   ├── retriever.py            # Policy document retrieval
│   ├── documents.py            # Policy document definitions
│   └── build_index.py          # Index builder script
│
├── frontend/                   # Chat UI
│   ├── index.html
│   ├── style.css
│   └── app.js                  # SSE streaming + agent trace rendering
│
├── data/
│   └── seed_data.py            # Database seeder (10 customers, loans, trades)
│
├── tests/                      # Test suite (62 cases)
│   ├── test_tool_router.py     # Query routing tests
│   ├── test_permissions.py     # Permission matrix tests
│   ├── test_orchestrator.py    # Planning + synthesis tests
│   └── test_mcp_integration.py # End-to-end MCP pipeline tests
│
├── claude_desktop_config.json  # Claude Desktop MCP configuration
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com) installed

### 1. Clone and install

```bash
git clone https://github.com/Elamathy-S/multi-agent-ai-framework.git
cd multi-agent-ai-framework
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start Ollama

```bash
ollama serve
ollama pull phi3          # main model
```

### 3. Seed the database (first time only)

```bash
PYTHONPATH=. python3 data/seed_data.py
```

### 4. Build RAG index (optional, first time only)

```bash
PYTHONPATH=. python3 rag/build_index.py
```

### 5. Start the MCP server

```bash
PYTHONPATH=. python3 -m server.mcp_server --http --port 8001
```

### 6. Start the client server (new terminal)

```bash
source venv/bin/activate
PYTHONPATH=. uvicorn client.main:app --reload --port 8080
```

### 7. Open the frontend

Open `frontend/index.html` in your browser. Try:
- "Who is customer 3?" — single agent, one tool call
- "What is the risk level for customer 1?" — risk agent with ReAct reasoning
- "Give me a full financial analysis" — all 4 agents run concurrently

### API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Single MCP tool call (keyword-routed) |
| `/chat/stream` | GET | Single tool with SSE streaming |
| `/agent/react/stream` | GET | Full multi-agent orchestration with live trace |
| `/agent/react` | POST | Multi-agent orchestration (JSON response) |
| `/agent/{type}` | POST | Call a specific agent directly |
| `/mcp/tools` | GET | List MCP server tools |
| `/mcp/surface` | GET | Full MCP surface (tools + prompts + resources) |
| `/mcp/tools/execute` | POST | Execute any MCP tool directly |
| `/health` | GET | Server + MCP + database status |
| `/docs` | GET | Swagger UI |

### Run tests

```bash
# Unit tests (no servers needed)
PYTHONPATH=. pytest tests/test_tool_router.py tests/test_permissions.py tests/test_orchestrator.py -v

# Full suite (needs MCP server running)
PYTHONPATH=. pytest -v
```

---

## Claude Desktop Integration

The MCP server works with Claude Desktop. Add this to your Claude Desktop config:

```json
{
  "mcpServers": {
    "finance-mcp-server": {
      "command": "python3",
      "args": ["-m", "server.mcp_server"],
      "cwd": "/path/to/multi-agent-ai-framework",
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

Claude can then use all 10 finance tools directly through the MCP protocol.

---

## Environment Variables

See `.env.example` for all options:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_URL` | `http://localhost:8001/sse` | MCP server SSE endpoint |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `phi3` | LLM model (`phi3:mini` for lower RAM) |
| `DATABASE_URL` | `sqlite:///finance_sim.db` | Database connection string |

---

## Key Design Decisions

**MCP as the single source of truth** — Tools are registered once on the MCP server. No duplicate registries. Adding a tool means one `@mcp.tool()` decorator.

**ReAct with fallback** — Agents use LLM reasoning to decide which tools to call. When the LLM can't produce valid JSON (common with phi3), the agent falls back to calling all its permitted tools. Worst case = same as hardcoded; best case = intelligent, selective tool use.

**Fresh MCP connection per tool call** — The ReAct loop has slow LLM calls (10-30s) between tool calls. A long-lived SSE connection would timeout during these pauses. Each tool call opens its own short-lived MCP session (~50ms overhead, never times out).

**Permission enforcement before MCP** — The permission check runs locally in `base.py` before the MCP request is made. Unauthorised calls never hit the wire. Every denial is logged.

**Structured synthesis + LLM summary** — `synthesise()` formats raw data into a readable report using per-tool formatters. Then Ollama writes a conversational summary. If Ollama is down, the structured report is shown as-is.