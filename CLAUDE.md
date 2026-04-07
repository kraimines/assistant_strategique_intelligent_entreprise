# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Talan Intelligent Enterprise Assistant — a multi-domain AI assistant (HR/CRM/ERP) built with FastAPI, LangGraph, and PostgreSQL. It routes user questions to specialized agents that call SQL tools and synthesize Markdown responses in French.

## Commands

### Start the full stack
```bash
cd infra && docker-compose up --build
```
Services: PostgreSQL (5432), Neo4j (7687), Redis (6379), FastAPI (8000), Frontend (5173), Adminer (8080).

### Run the backend only (without Docker)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Interactive CLI to test agents manually
```bash
cd backend
python chat_cli.py
```

### Check LLM quota and connectivity
```bash
cd backend
PYTHONIOENCODING=utf-8 python check_llm_quota.py
```

### Run tests
```bash
cd backend

# Fast tests only (mocked LLM, no Docker required)
python -m pytest tests/ -v -m "not live"

# All tests (requires Docker + Groq API key)
python -m pytest tests/ -v -m live

# A single test file
python -m pytest tests/test_agent_crm.py -v -m live

# A single test
python -m pytest tests/test_agent_crm.py::test_crm_list_opportunities -v -m live
```

### Run ETL (populate databases from Excel files)
```bash
cd backend
python -m backend.etl.run_all_etl
```

## Architecture

### LangGraph Pipeline
```
User message
    └─ orchestrator_node          (classifies domain + confidence)
           ├─ hr_agent_node       (HR tools → SQL queries)
           ├─ crm_agent_node      (CRM tools → SQL queries)
           ├─ erp_agent_node      (ERP tools → SQL queries)
           └─ rag_agent_node      (ChromaDB retrieval)
                 │
           [route_after_domain_agent: adds RAG if documentary keywords found]
                 │
           final_response_node    (synthesizes Markdown French response)
```

All nodes share `AgentState` (TypedDict in `backend/app/agents/state.py`). The graph is compiled in `backend/app/agents/graph.py` with `MemorySaver` for conversation persistence.

### Domain Agents (HR / CRM / ERP)
Each agent implements a **ReAct loop** (max 3 iterations):
1. Bind LLM to domain tools via `get_llm_with_tools()`
2. LLM decides which tool(s) to call
3. Execute tools (SQL via SQLAlchemy synchronous sessions)
4. Feed results back to LLM for next iteration or final answer
5. Store `tool_results` and final `AIMessage` in state

Tool results are truncated to 1500 chars via `truncate_tool_result()` before being sent back to the LLM to stay within token limits.

### Three PostgreSQL Databases
Each domain has its own DB and schema:
- `talan_hr` → schema `hr` (hr_employees, hr_leave_requests, hr_skills, etc.)
- `talan_crm` → schema `crm` (crm_accounts, crm_opportunities, crm_contacts, etc.)
- `talan_erp` → schema `erp` (erp_invoices, erp_sales_orders, erp_customers, etc.)

Tools use **module-level SQLAlchemy engines** (synchronous, shared connection pool). Schema is always explicit in SQL (e.g., `FROM crm.crm_opportunities`).

### LLM Factory (`backend/app/core/llm.py`)
- `get_llm()` — main LLM (streaming disabled for stability with tool calling)
- `get_json_llm()` — JSON-mode LLM used by the orchestrator for classification
- `get_llm_with_tools(tools)` — LLM with bound LangChain tools
- `invoke_with_retry(llm, messages)` — auto-retry on HTTP 429 with backoff
- `truncate_tool_result(result_str)` — caps tool output at 1500 chars

All functions use `@lru_cache`. **Restart required after changing `GROQ_MODEL` in `.env`** — the cache persists in-process.

### Orchestrator Classification
- Uses `get_json_llm()` for JSON-structured output
- Classifies into: `hr | crm | erp | rag | multi`
- Threshold: `domain_confidence >= 0.7`; retries once if below; falls back to `rag`
- Enforces write permissions by role:
  - `employee`: write to hr only
  - `manager`: write to hr, crm
  - `admin`: write to hr, crm, erp

### Configuration (`backend/app/core/config.py`)
Pydantic `BaseSettings` loaded from `backend/.env`. Access via `settings` singleton (`@lru_cache`). Key helper: `settings.database_url(domain)` returns the psycopg2 connection string for a given domain (`hr`, `crm`, `erp`).

### API Structure
FastAPI app at `backend/app/main.py`. Routers under `/api/v1/`:
- `auth` — JWT register/login
- `chat` — SSE streaming (`/chat/stream`) and non-streaming (`/chat`) endpoints
- `hr`, `crm`, `erp` — domain CRUD
- `stats` — KPI aggregation (role-gated)
- `simulate` — strategic simulation stubs

## Database Column Values (Critical)

All enum values in the database are in **English**. Prompts must use these exact values:

| Table | Column | Valid values |
|---|---|---|
| `erp_invoices` | `payment_status` | `Unpaid`, `Partially Paid`, `Paid`, `Overdue` |
| `erp_sales_orders` | `status` | `Pending`, `Confirmed`, `Shipped`, `Delivered`, `Cancelled` |
| `erp_purchase_orders` | `status` | `Draft`, `Submitted`, `Approved`, `Received`, `Cancelled` |
| `crm_opportunities` | `stage` | `Prospecting`, `Qualification`, `Proposal`, `Negotiation`, `Closed Won`, `Closed Lost` |
| `hr_leave_requests` | `leave_type` | `Annual Leave`, `Sick Leave`, `Maternity Leave`, `Paternity Leave`, `Unpaid Leave`, `Training Leave` |
| `hr_leave_requests` | `status` | `Pending`, `Approved`, `Rejected` |
| `hr_skills` | `level` | `Beginner`, `Intermediate`, `Advanced`, `Expert` |
| `hr_skills` | `certified` | `Yes`, `No`, `In Progress` |
| `hr_employees` | `contract_type` | `Permanent`, `Fixed-Term`, `Contractor` |
| `hr_projects` | `status` | `Planning`, `Active`, `Completed`, `On Hold`, `Cancelled` |

## LLM Quotas (Groq Free Tier)

| Model | TPM | TPD | Notes |
|---|---|---|---|
| `llama-3.3-70b-versatile` | 12 000 | 100 000 | **Preferred** — best tool calling |
| `qwen/qwen3-32b` | 6 000 | 100 000 | Fallback — set smaller result limits |
| `meta-llama/llama-4-scout-17b-16e-instruct` | 30 000 | 500 000 | Fallback for high TPM |
| `moonshotai/kimi-k2-instruct` | 10 000 | — | Avoid — fails on tool calling |

Each pipeline request consumes ~2 000 tokens → ~50 requests/day on free tier. When the daily quota is exhausted, switch the `GROQ_MODEL` in `backend/.env` and **restart the process**.

## Test Strategy

- Tests marked `@pytest.mark.live` require Docker + PostgreSQL + a valid Groq API key
- The live tests call real agents with real DB data — expected to pass ~16/18 (2 may fail on quota exhaustion)
- IDs used in tests: `EMP0001`–`EMP0010` (HR), `ACC0001`–`ACC0010` (CRM), `CUS0001`–`CUS0157` (ERP)
