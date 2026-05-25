---
marp: true
theme: default
paginate: true
size: 16:9
---

<!-- _class: lead -->

# Intelligent Strategic Enterprise Assistant

### Internship Presentation

<br>

**Intern:** [Your Name]

**University:** [University Name]

<br>

> 📷 *[ Photo Placeholder — replace with intern photo ]*

---

## Project Description

**General idea**
A multi-domain AI assistant for enterprise decision-making, combining
**HR / CRM / ERP** agents with a **real-time market intelligence** module
(Knowledge Graph + GNN + strategic recommendations).

**Intelligence & orchestration layer**
Built around a **LangGraph StateGraph** with an **orchestrator**, a
**world-model step**, domain agents (**HR / CRM / ERP / competitive intelligence**),
a **hybrid RAG agent**, and a **final response node**. The LLM layer relies on a
factory that supports **Groq, Gemini, and Mistral** with **retry and fallback**.
On the market-analysis side, the backend includes an **APScheduler pipeline**
for collection, LLM analysis, KG updates, **GNN inference**, alert/report generation,
an **LLM recommender** fed by **GNN + forecast outputs**, and **what-if simulation**
tools for both the knowledge graph and GNN scenarios.

**Execution plan**

1. **Infrastructure** — Docker stack: FastAPI · PostgreSQL · Neo4j · Redis · React
2. **Data pipeline** — ETL into 3 domain databases + Neo4j graph (22 nodes / 38 relations)
3. **Agentic core** — LangGraph orchestrator routing to HR / CRM / ERP / RAG agents
4. **Market intelligence** — Event ingestion → KG enrichment → GNN propagation → alerts
5. **Frontend** — React dashboard: chat, KG viewer, GNN predictions, recommendations
6. **Validation** — Live tests, UX trust signals, performance tuning

---

## Progress

**✅ Accomplished**
- Full Docker stack & ETL pipeline (HR / CRM / ERP + Neo4j)
- LangGraph multi-agent pipeline with ReAct loops and role-based permissions
- React frontend + chatbot (SSE streaming)
- Market analysis module: KG, GNN predictions, propagation paths, alerts feed
- Performance: GNN endpoint **105 s → 11 s**
- UX/trust quick wins: trust score badge, feedback buttons, propagation views

**🔧 Still to do**
- Finalize strategic recommendations synthesis & COMEX brief export
- Expand GNN training data and evaluation metrics
- End-to-end tests on the market intelligence flow
- Final report writing & demo polish

<br>

**📄 Report submission:** [Report Date]   ·   **🏁 Internship end:** [End Date]
