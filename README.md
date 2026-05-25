# Multi-Agent AI Framework

> A modular, production-style multi-agent AI system for simulating complex financial operations — including risk management, trading workflows, and customer interactions — powered by LLMs, RAG pipelines, and a FastAPI backend.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [RAG Pipeline](#rag-pipeline)
- [API Reference](#api-reference)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

---

## Overview

This project is a **modular multi-agent AI framework** built in Python, designed to simulate and prototype complex decision-making workflows in financial domains. It brings together LLM-powered reasoning, Retrieval-Augmented Generation (RAG) for grounding responses in real data, and a scalable FastAPI backend that exposes agent capabilities as APIs.

The framework serves two purposes:

1. **Production-style simulation** of financial operations (risk management, trading, customer workflows)
2. **Testbed for agentic architectures** — experimenting with multi-agent orchestration patterns, prompt engineering, and LLM integrations

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (UI)                       │
│              HTML / CSS / JavaScript                     │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│                  FastAPI Backend (server/)               │
│         REST APIs · Agent Endpoints · MCP Protocol      │
└──────┬──────────────────────┬───────────────────────────┘
       │                      │
┌──────▼──────┐     ┌─────────▼────────┐
│  Multi-Agent│     │   RAG Pipeline   │
│ Orchestrator│     │  (rag/ + ChromaDB)│
│  (client/)  │     │  TF-IDF fallback │
└──────┬──────┘     └─────────┬────────┘
       │                      │
┌──────▼──────────────────────▼────────┐
│         LLM Layer (Ollama — phi3)     │
│    Local inference · no API key req  │
└──────────────────────────────────────┘
       │
┌──────▼──────────────────────────────┐
│       Database (SQLite / PostgreSQL) │
│        finance_sim.db (dev)          │
└──────────────────────────────────────┘
```

**Agent roles** are delegated across the framework — each agent handles a specific domain (e.g. risk assessment, trade execution, customer query resolution) and communicates via the orchestrator.

---

## Features

- **Multi-agent orchestration** — Intelligent task delegation and reasoning across specialized agents
- **LLM-driven pipelines** — Context-aware responses using locally-run models via Ollama (phi3)
- **RAG support** — Retrieval-Augmented Generation for both structured (SQL) and unstructured (document) data, with ChromaDB for vector storage and a TF-IDF fallback
- **FastAPI backend** — Clean REST API exposing agent capabilities with async support
- **MCP Protocol integration** — Standardized model context protocol for agent communication
- **Financial domain simulation** — Simulated data for trading, risk, and customer workflows via Faker
- **Modular design** — Each component (agents, RAG, server, frontend) is independently extensible
- **Dev-friendly setup** — SQLite by default; PostgreSQL-ready for production

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Web Framework | FastAPI + Uvicorn |
| LLM Backend | Ollama (phi3 model) |
| Vector Store | ChromaDB |
| Embeddings | Ollama (`nomic-embed-text`) / TF-IDF fallback |
| Database | SQLite (dev) / PostgreSQL (prod) |
| ORM | SQLAlchemy 2.0 |
| Agent Protocol | MCP (Model Context Protocol) |
| Data Validation | Pydantic v2 |
| Frontend | HTML / CSS / JavaScript |
| Testing | pytest + pytest-asyncio |
| Data Generation | Faker |

---

## Project Structure

```
multi-agent-ai-framework/
├── client/                  # Agent client logic and orchestration
├── data/                    # Seed data, fixtures, and data generation scripts
├── frontend/                # UI (HTML/CSS/JS) for interacting with agents
├── rag/                     # RAG pipeline — retrieval, embeddings, ChromaDB integration
├── server/                  # FastAPI server — routes, endpoints, agent APIs
├── finance_sim.db           # SQLite database for development
├── claude_desktop_config.json  # Claude Desktop MCP configuration
├── requirements.txt         # Python dependencies
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally

### 1. Clone the repository

```bash
git clone https://github.com/Elamathy-S/multi-agent-ai-framework.git
cd multi-agent-ai-framework
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Pull the required Ollama models

```bash
ollama serve                          # Start Ollama if not already running
ollama pull phi3                      # LLM for agent reasoning
ollama pull nomic-embed-text          # Embeddings for RAG (optional — TF-IDF used as fallback)
```

---

## Configuration

Create a `.env` file in the project root:

```env
# Database
# Development: leave blank to use SQLite (finance_sim.db)
# Production: uncomment and set PostgreSQL URL
# DATABASE_URL=postgresql://user:password@localhost:5432/finance_sim

# Ollama
OLLAMA_HOST=http://localhost:11434
```

For Claude Desktop MCP integration, the `claude_desktop_config.json` at the root contains the server configuration. Point Claude Desktop to this file to connect agents as MCP tools.

---

## Running the Application

### Start the FastAPI server

```bash
uvicorn server.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs (Swagger UI) at `http://localhost:8000/docs`.

### Seed the database (optional)

```bash
python data/seed.py
```

### Run tests

```bash
pytest
```

---

## RAG Pipeline

The RAG module (`rag/`) supports retrieval over both structured and unstructured financial data.

**How it works:**

1. Documents or structured records are ingested and chunked
2. Embeddings are generated via `nomic-embed-text` (Ollama) or TF-IDF if Ollama embeddings are unavailable
3. Vectors are stored in ChromaDB
4. At query time, the most relevant chunks are retrieved and injected into the LLM prompt as context

**Embedding strategy:**

- Primary: `ollama pull nomic-embed-text` → semantic similarity search
- Fallback: TF-IDF (no additional setup required)

---

## API Reference

Once the server is running, full interactive documentation is available at:

```
http://localhost:8000/docs       # Swagger UI
http://localhost:8000/redoc      # ReDoc
```

Key endpoint groups (subject to change as development progresses):

| Prefix | Description |
|---|---|
| `/agents` | Agent orchestration and task delegation |
| `/rag` | RAG query endpoints |
| `/finance` | Financial simulation data (trades, risk, customers) |
| `/health` | Server health check |

---

## Contributing

Contributions, issues, and feature requests are welcome. Please open an issue first to discuss what you'd like to change.

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add some feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

*Built by [Elamathy-S](https://github.com/Elamathy-S)*
