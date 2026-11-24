# Multi-Agent Finance Assistant

![CI](https://github.com/Elamathy-S/multi-agent-ai-framework/actions/workflows/ci.yml/badge.svg)

A supervisor LLM and four specialist agents answer questions about a bank customer. The agents decide
for themselves which tools to call, read policy through retrieval, and are constrained by role-based
access control. Tools are served over the Model Context Protocol (MCP).

> Data is synthetic (Faker). This is a learning/portfolio project, not a production banking system.

## What makes this an agent system (and not a pipeline)

| Concern | How it works here |
|---|---|
| **Who decides which tools run?** | The model. Each specialist gets a task and a set of tools and chooses calls using native tool-use (Anthropic tool use / Ollama tools). There is no keyword router and no fixed call order. |
| **Who decides which specialists run?** | A supervisor LLM calls a `delegate` tool with a self-contained sub-task per specialist. Out-of-scope questions are declined without touching any tool. |
| **Where does reasoning happen?** | In the agents. Tools (`get_risk_score`, `check_fraud`, `get_credit_score`) are **deterministic** computations (`server/tools/analytics.py`), not hidden LLM calls. The agent interprets the numbers against policy. |
| **How is RAG used?** | `search_policies` is an MCP tool. The agent chooses when to retrieve, and must cite passage ids like `[risk_policy_002#1]`. Evals check the citations are real. |
| **What stops the model misbehaving?** | The harness, not the prompt: agents only *see* tools their RBAC role allows; every call is re-checked and audit-logged; `customer_id` is injected by the harness so the model cannot read another customer; tool output is size-capped. |
| **How do you know it works?** | Behavioural evals (`evals/`) grade real runs on tool selection, delegation, policy citation, numeric grounding, efficiency and scope. The graders themselves are unit-tested. |

## Architecture

```
Browser ──SSE──▶ FastAPI (:8080)
                   │
                   ▼
            Supervisor (LLM)  ── plan ──▶ delegate(tasks)
                   │
        ┌──────────┼───────────┬───────────┐   run concurrently
        ▼          ▼           ▼           ▼
    customer     loan        risk       trading        each = the same agent loop:
        └──────────┴─────┬─────┴───────────┘            model ⇄ tools until it answers
                         │  RBAC filter + audit
                         ▼
                 MCP server (:8001, JSON-RPC over SSE)
                   ├─ 10 tools: lookups, deterministic scoring, search_policies (RAG)
                   ├─ resources + prompts (usable from Claude Desktop)
                   └─ SQLite/Postgres, Chroma/TF-IDF
                         ▲
                         │
            Supervisor (LLM) synthesises the specialists' findings
```

Key files:

| Path | Role |
|---|---|
| `llm/` | Provider-neutral LLM interface: Anthropic (default), Ollama, scripted (tests) |
| `client/agents/loop.py` | The agent loop and the guarantees the harness enforces |
| `client/agents/specs.py` | Specialists as data (name, RBAC role, domain guidance) |
| `client/agents/orchestrator.py` | Plan → delegate → synthesise |
| `server/tools/analytics.py` | Deterministic risk, fraud and credit rules (mirrors the policy docs) |
| `rag/` | Section-level chunking, Chroma + Ollama embeddings, in-memory TF-IDF fallback |
| `client/security/` | Database-backed RBAC (read-only API) and audit log |
| `evals/` | Behavioural cases, graders, runner |

## Run it

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # choose a model provider (see below) and add its key

export PYTHONPATH=.
python data/seed_data.py                                  # synthetic data
python rag/build_index.py                                 # optional: semantic index (needs Ollama embeddings)
python -m server.mcp_server --http --port 8001            # terminal 1
uvicorn client.main:app --port 8080                       # terminal 2
open frontend/index.html
```

Docker: `docker compose up` (Anthropic) or `docker compose --profile local-llm up` (Ollama).

**Model providers** (`LLM_PROVIDER` in `.env`):

| Provider | Setting | Notes |
|---|---|---|
| Anthropic (default) | `anthropic` + `ANTHROPIC_API_KEY` | Native tool use |
| Google Gemini | `gemini` + `GEMINI_API_KEY` | Free tier available; uses Google's OpenAI-compatible endpoint, retries rate limits, round-trips Gemini 3 thought signatures |
| Any OpenAI-compatible API | `openai_compat` + `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | Groq, OpenRouter, Mistral, ... |
| Ollama (local) | `ollama` + `LLM_MODEL` | Free, runs on your machine |

**Local models:** use one with tool calling (e.g. `qwen2.5:7b`, `llama3.1`). Models without it, such as
phi3, cannot drive the agent loop and fail fast with a clear error.

Try: *"How risky is this customer and what does policy require?"*, *"Could they get a $30,000 loan?"*,
*"Give me a full review."*

## Testing and evals

```bash
pytest                          # 100+ tests; scripted model, no key or network needed
python evals/run_evals.py --trials 3 --min-pass 0.8     # real model + MCP server
```

* **Unit/integration tests** pin down harness behaviour with a scripted model: what the model is shown,
  RBAC blocking and audit, customer scoping, tool errors fed back, step budget, truncation, parallel
  calls, partial failure, SSE contract.
* **Behavioural evals** run the real model several times per case (agents are stochastic) and report a
  pass rate. Checks: right specialists, required/forbidden tools, tool budget, policy cited *and*
  citation exists in retrieved passages, every number in the answer traceable to tool output, and the
  customer scope was never escaped.
* CI runs the tests on every push. Live evals run on demand (`workflow_dispatch`) with a secret key.

## Design decisions

* **Deterministic tools, reasoning agents.** An earlier design had MCP tools that secretly prompted an
  LLM, so an agent called an LLM through a tool. Now tools compute facts and agents explain them.
* **No silent fallbacks.** The old "call every tool if the model fails" mode made weak models look
  fine and hid failures. Now a model failure is an error, and one failing specialist is reported as
  such in the answer rather than papered over.
* **The harness owns security.** Prompts are advice; scoping, permissions and audit are code.
* **RBAC controls visibility *and* execution.** Hiding a tool saves tokens and removes temptation;
  the call-time check is defence in depth.

## Known limitations

* Data is synthetic and the scoring rules are illustrative, not regulatory-grade.
* Retrieval corpus is small (9 policy documents, chunked by section); no reranking.
* Agents get one customer per run; cross-customer comparison is intentionally unsupported.
* Admin endpoints use a static token; a real deployment would use proper authentication.
* No conversation memory between requests.
* Eval pass rates depend on the model; none are published here until run on your setup.