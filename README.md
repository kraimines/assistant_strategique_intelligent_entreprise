# Assistant Stratégique Intelligent d'Entreprise

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-FF6B35)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-5.18-008CC1?logo=neo4j&logoColor=white)

Plateforme d'entreprise intelligente développée dans le cadre d'un PFE chez **Talan Tunisie**. Elle unifie les données RH, CRM et ERP au sein d'un assistant IA conversationnel multi-agents, de tableaux de bord personnalisés par rôle, d'une analyse de marché pilotée par des réseaux de neurones sur graphe (GNN), d'une veille concurrentielle automatisée et d'un moteur de simulation stratégique.

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [Stack technique](#2-stack-technique)
3. [Architecture](#3-architecture)
   - [Pipeline LangGraph](#31-pipeline-langgraph)
   - [Couches de données](#32-couches-de-données)
   - [Pipeline d'analyse de marché](#33-pipeline-danalyse-de-marché)
   - [Sécurité et rôles](#34-sécurité-et-rôles)
4. [Prérequis](#4-prérequis)
5. [Installation et démarrage](#5-installation-et-démarrage)
   - [Démarrage complet (Docker)](#51-démarrage-complet-docker)
   - [Backend seul (hors Docker)](#52-backend-seul-hors-docker)
   - [Frontend seul (hors Docker)](#53-frontend-seul-hors-docker)
6. [Variables d'environnement](#6-variables-denvironnement)
7. [ETL — Chargement des données](#7-etl--chargement-des-données)
8. [Structure du projet](#8-structure-du-projet)
9. [Backend — détail des modules](#9-backend--détail-des-modules)
   - [Agents IA (LangGraph)](#91-agents-ia-langgraph)
   - [Outils SQL (LangChain Tools)](#92-outils-sql-langchain-tools)
   - [API REST](#93-api-rest)
   - [Modèles de données](#94-modèles-de-données)
   - [Services métier](#95-services-métier)
   - [Analyse de marché et GNN](#96-analyse-de-marché-et-gnn)
   - [LLM Factory](#97-llm-factory)
10. [Frontend — détail des modules](#10-frontend--détail-des-modules)
11. [Tests](#11-tests)
12. [Valeurs d'énumération (base de données)](#12-valeurs-dénumération-base-de-données)
13. [Quotas LLM (Groq Free Tier)](#13-quotas-llm-groq-free-tier)
14. [Outils de développement](#14-outils-de-développement)
15. [Auteur](#15-auteur)

---

## 1. Vue d'ensemble

L'Assistant Stratégique Intelligent est une plateforme full-stack qui permet à des utilisateurs d'entreprise (employés, managers, direction) d'interagir en langage naturel avec leurs données opérationnelles et d'obtenir des analyses stratégiques en temps réel.

**Fonctionnalités principales :**

| Module | Description |
|--------|-------------|
| **Chat IA multi-agents** | Assistant conversationnel en français, routage automatique vers les agents RH / CRM / ERP / RAG |
| **Tableau de bord** | KPIs personnalisés selon le rôle (employé / manager / admin), visualisations Recharts |
| **Analyse de marché** | Pipeline automatisé de collecte, analyse LLM, prédictions GNN, alertes |
| **Veille concurrentielle** | Scanning RSS, job boards, actualités concurrentes, radar de menaces |
| **World Model / Digital Twin** | Graphe de connaissances Neo4j avec visualisation 3D des entités et relations |
| **Simulation stratégique** | Modélisation de scénarios d'impact (embauches, projets, budgets) |
| **Gestion CRUD** | Interfaces complètes pour RH, CRM et ERP |

---

## 2. Stack technique

### Backend
| Technologie | Version | Rôle |
|-------------|---------|------|
| Python | 3.11 | Langage principal |
| FastAPI | 0.111 | Framework API REST + SSE |
| LangGraph | 0.2 | Orchestration des agents IA |
| LangChain | 0.2 | Outils LLM et intégrations |
| Groq API | — | Inférence LLM (llama-3.3-70b) |
| SQLAlchemy | 2.0 | ORM synchrone (agents) + async (API) |
| Alembic | — | Migrations base de données |
| ChromaDB | — | Vectorstore pour le RAG |
| PyTorch Geometric | — | GNN (GAT, TGN, HGT) |
| APScheduler | — | Planification du pipeline marché |
| Pydantic | v2 | Validation et configuration |
| bcrypt / jose | — | Sécurité (hash + JWT) |

### Frontend
| Technologie | Version | Rôle |
|-------------|---------|------|
| React | 18 | Framework UI |
| TypeScript | 5 | Typage statique |
| Vite | 5 | Bundler & dev server |
| Tailwind CSS | 3 | Styles utilitaires |
| Zustand | — | State management global |
| TanStack Query | — | Fetching & cache async |
| Recharts | — | Graphiques et KPIs |
| React Force Graph | — | Visualisation 3D des graphes |
| Framer Motion | — | Animations |
| Axios | — | Client HTTP |

### Infrastructure
| Service | Image | Port |
|---------|-------|------|
| PostgreSQL | postgres:16-alpine | 5432 |
| Neo4j | neo4j:5.18-community | 7474 / 7687 |
| Redis | redis:7.2-alpine | 6379 |
| FastAPI | (build local) | 8000 |
| Frontend | (build local) | 5173 |
| Adminer | adminer:4.8.1 | 8080 |

---

## 3. Architecture

### 3.1 Pipeline LangGraph

Chaque message utilisateur traverse un graphe d'états LangGraph compilé avec `MemorySaver` (persistance de la conversation) :

```
Message utilisateur
        │
        ▼
┌─────────────────────┐
│  orchestrator_node  │  ← classification domaine + confiance (JSON LLM)
│  (hr|crm|erp|rag|   │  ← garde les permissions d'écriture par rôle
│   multi)            │
└─────────────────────┘
        │
   [routage conditionnel]
        │
   ┌────┼────┬────────────┐
   ▼    ▼    ▼            ▼
  HR   CRM  ERP          RAG
agent agent agent       agent
  │    │    │             │
  └────┴────┴─────────────┘
        │
        ▼  [route_after_domain_agent : RAG optionnel si mots-clés documentaires]
        │
┌──────────────────────┐
│  final_response_node │  ← synthèse Markdown en français
└──────────────────────┘
        │
       END
```

Chaque agent de domaine implémente une boucle **ReAct** (max 3 itérations) :
1. Le LLM choisit l'outil SQL à appeler
2. L'outil exécute la requête via SQLAlchemy (synchrone, pool partagé)
3. Le résultat (tronqué à 1 500 caractères) est renvoyé au LLM
4. Le LLM produit une réponse finale ou lance une nouvelle itération

### 3.2 Couches de données

```
┌─────────────────────────────────────────────────────────┐
│                      PostgreSQL                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  talan_hr    │  │  talan_crm   │  │  talan_erp   │  │
│  │  schema: hr  │  │  schema: crm │  │  schema: erp │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
┌──────────────────────────┐   ┌───────────────────────┐
│  Neo4j (Knowledge Graph) │   │  Redis (cache/session)│
│  22 nœuds, 38 relations  │   │  conversation state   │
└──────────────────────────┘   └───────────────────────┘
┌──────────────────────────┐
│  ChromaDB (Vectorstore)  │
│  documents RH/politique  │
└──────────────────────────┘
```

### 3.3 Pipeline d'analyse de marché

Pipeline automatisé planifié par APScheduler, stocké dans PostgreSQL, enrichi dans Neo4j :

```
Collecte ──────────────────────────────────────────────────────┐
  Yahoo Finance | NewsAPI | GNews | Reddit | X/Twitter          │
        │                                                       │
        ▼                                                       │
  Analyse LLM ─── extraction causale, scores d'impact          │
        │                                                       │
        ▼                                                       │
  Mise à jour KG ── upsert nœuds/arêtes dans Neo4j             │
        │                                                       │
        ▼                                                       │
  Inférence GNN ── GAT / TGN / HGT / HTGN sur le graphe        │
        │                                                       │
        ▼                                                       │
  Rapport + Alertes ── seuils, recommandations stratégiques ────┘
```

### 3.4 Sécurité et rôles

Authentification par JWT (HS256, expiry 30 min). Permissions d'écriture par rôle :

| Rôle | Lecture | Écriture HR | Écriture CRM | Écriture ERP |
|------|---------|-------------|--------------|--------------|
| `employee` | Tout | Oui | Non | Non |
| `manager` | Tout | Oui | Oui | Non |
| `admin` | Tout | Oui | Oui | Oui |

---

## 4. Prérequis

| Outil | Version minimale |
|-------|-----------------|
| Python | 3.11 |
| Node.js | 18 |
| Docker | 24 |
| Docker Compose | 2.20 |
| Groq API key | — |

---

## 5. Installation et démarrage

### 5.1 Démarrage complet (Docker)

```bash
# 1. Cloner le dépôt
git clone https://github.com/<org>/assistant_strategique_intelligent_entreprise.git
cd assistant_strategique_intelligent_entreprise

# 2. Copier le fichier d'environnement et renseigner les variables
cp .env.example .env
# Éditer .env : GROQ_API_KEY, mots de passe DB, JWT_SECRET, ...

# 3. Lancer tous les services
cd infra
docker-compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API Swagger | http://localhost:8000/docs |
| Adminer (DB) | http://localhost:8080 |
| Neo4j Browser | http://localhost:7474 |

### 5.2 Backend seul (hors Docker)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

> PostgreSQL, Neo4j et Redis doivent être démarrés séparément (ou via Docker).

### 5.3 Frontend seul (hors Docker)

```bash
cd frontend
npm install
npm run dev
```

### CLI de test des agents

```bash
cd backend
python chat_cli.py
# Commandes spéciales : quit, role <employee|manager|admin>, clear
```

### Vérification du quota LLM

```bash
cd backend
PYTHONIOENCODING=utf-8 python check_llm_quota.py
```

---

## 6. Variables d'environnement

Créer `backend/.env` (copier depuis `.env.example`) :

```dotenv
# ── LLM ──────────────────────────────────────────────
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# ── PostgreSQL ────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=talan
POSTGRES_PASSWORD=talan_password

POSTGRES_DB_HR=talan_hr
POSTGRES_DB_CRM=talan_crm
POSTGRES_DB_ERP=talan_erp

# ── Neo4j ─────────────────────────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password

# ── Redis ─────────────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── Sécurité ──────────────────────────────────────────
JWT_SECRET=changeme_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ── CORS ──────────────────────────────────────────────
CORS_ORIGINS=["http://localhost:5173"]

# ── APIs externes (optionnel) ─────────────────────────
NEWS_API_KEY=...
GNEWS_API_KEY=...
```

---

## 7. ETL — Chargement des données

Les fichiers Excel (`data/`) sont chargés dans PostgreSQL et Neo4j via le pipeline ETL :

```bash
cd backend
python -m backend.db.etl.run_all_etl
```

Étapes exécutées dans l'ordre :
1. **`etl_hr.py`** — Charge `RH_Talan_Tunisie.xlsx` → schéma `hr` (PostgreSQL)
2. **`etl_crm.py`** — Charge `CRM_Talan_Tunisie.xlsx` → schéma `crm` (PostgreSQL)
3. **`etl_erp.py`** — Charge `ERP_Talan_Tunisie.xlsx` → schéma `erp` (PostgreSQL)
4. **`etl_neo4j.py`** — Synchronise PostgreSQL → Neo4j (22 types de nœuds, 38 relations)

---

## 8. Structure du projet

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py                   # Entrée FastAPI (CORS, routes, lifespan)
│   │   ├── agents/
│   │   │   ├── graph.py              # Compilation du StateGraph LangGraph
│   │   │   ├── state.py              # AgentState (TypedDict partagé)
│   │   │   ├── orchestrator.py       # Classification domaine + routage
│   │   │   ├── hr_agent.py           # Agent RH (boucle ReAct)
│   │   │   ├── crm_agent.py          # Agent CRM (boucle ReAct)
│   │   │   ├── erp_agent.py          # Agent ERP (boucle ReAct)
│   │   │   ├── rag_agent.py          # Agent RAG (ChromaDB)
│   │   │   ├── market_analysis_agent.py
│   │   │   ├── competitive_intel_agent.py
│   │   │   ├── email_agent.py
│   │   │   └── simulator_agent.py
│   │   ├── api/
│   │   │   ├── deps.py               # Injection de dépendances (auth, DB)
│   │   │   └── routes/
│   │   │       ├── auth.py           # Register / Login / Profil
│   │   │       ├── chat.py           # SSE streaming + historique
│   │   │       ├── hr.py             # CRUD RH
│   │   │       ├── crm.py            # CRUD CRM
│   │   │       ├── erp.py            # CRUD ERP
│   │   │       ├── stats.py          # KPIs agrégés (role-gated)
│   │   │       ├── simulate.py       # Simulation stratégique
│   │   │       ├── graph.py          # Exploration Neo4j
│   │   │       ├── competitive_intel.py
│   │   │       └── market_analysis.py
│   │   ├── core/
│   │   │   ├── config.py             # Pydantic BaseSettings
│   │   │   ├── database.py           # Moteurs SQLAlchemy (async + sync)
│   │   │   ├── llm.py                # LLM factory (get_llm, retry, truncate)
│   │   │   ├── security.py           # JWT + bcrypt
│   │   │   └── redis_client.py       # Pool Redis async
│   │   ├── models/                   # ORM SQLAlchemy
│   │   │   ├── user_models.py
│   │   │   ├── hr_models.py
│   │   │   ├── crm_models.py
│   │   │   ├── erp_models.py
│   │   │   ├── conversation_models.py
│   │   │   ├── market_analysis_models.py
│   │   │   └── competitive_intel_models.py
│   │   ├── schemas/                  # Pydantic schemas (request/response)
│   │   ├── prompts/                  # Templates de prompts LLM
│   │   ├── tools/                    # LangChain tools (SQL + web)
│   │   │   ├── hr_tools.py
│   │   │   ├── crm_tools.py
│   │   │   ├── erp_tools.py
│   │   │   ├── competitive_intel_tools.py
│   │   │   └── email_tools.py
│   │   └── services/
│   │       ├── conversation_service.py
│   │       ├── neo4j_sync.py
│   │       ├── world_model_service.py
│   │       ├── email_service.py
│   │       ├── competitive_intel/
│   │       │   └── scanner.py        # Scraping RSS/job boards/news
│   │       └── market_analysis/
│   │           ├── orchestrator.py   # Pipeline planifié (APScheduler)
│   │           ├── collector.py      # Collecte Yahoo Finance, NewsAPI...
│   │           ├── analyst.py        # Analyse causale LLM
│   │           ├── gnn_predictor.py  # Inférence GNN
│   │           ├── world_model.py    # Synthèse world model
│   │           ├── recommender.py    # Recommandations stratégiques
│   │           ├── forecaster.py     # Prévisions temporelles
│   │           ├── gnn_data_adapter.py
│   │           ├── gnn_dataset_builder.py
│   │           ├── train_tgn.py      # Temporal Graph Network
│   │           ├── train_hgt.py      # Heterogeneous Graph Transformer
│   │           ├── train_htgn.py     # Hybrid TGN+HGT
│   │           └── compare_models.py
│   ├── db/
│   │   ├── postgres/
│   │   │   └── init.sql              # Init PostgreSQL (bases talan_crm, talan_erp)
│   │   ├── neo4j/
│   │   └── etl/
│   │       ├── run_all_etl.py        # Point d'entrée ETL
│   │       ├── etl_hr.py
│   │       ├── etl_crm.py
│   │       ├── etl_erp.py
│   │       └── etl_neo4j.py
│   ├── rag/                          # Ingest + retriever ChromaDB
│   ├── simulation/                   # Métamodèle + propagation scénarios
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_agents.py
│   │   ├── test_agent_hr.py
│   │   ├── test_agent_crm.py
│   │   ├── test_agent_erp.py
│   │   ├── test_agent_rag.py
│   │   ├── test_auth.py
│   │   ├── test_hr_api.py
│   │   ├── test_crm_api.py
│   │   └── test_erp_api.py
│   ├── chat_cli.py
│   ├── check_llm_quota.py
│   ├── build_gnn_dataset.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Signup.tsx
│   │   │   ├── Landing.tsx
│   │   │   ├── Chat.tsx              # Chat SSE streaming
│   │   │   ├── Dashboard.tsx         # KPIs par rôle
│   │   │   ├── MarketAnalysis.tsx
│   │   │   ├── CompetitiveIntel.tsx
│   │   │   ├── DigitalTwin.tsx
│   │   │   ├── WorldModelExplorer.tsx
│   │   │   └── Simulation.tsx
│   │   ├── components/
│   │   │   ├── Chat/                 # MessageBubble, MeetingCard
│   │   │   ├── Dashboard/            # KPICard
│   │   │   ├── MarketAnalysis/       # GNNPredictions, KGExplorer, AlertsFeed...
│   │   │   ├── CompetitiveIntel/     # ThreatRadar, JobSignalsChart...
│   │   │   ├── WorldModel/           # GraphViewer 3D, LeftSidebar...
│   │   │   ├── layout/               # AppShell, Sidebar, TopBar
│   │   │   └── ui/                   # Button, Badge, GlassCard, Spinner...
│   │   ├── api/                      # Clients Axios (market, graph, intel...)
│   │   ├── hooks/                    # useAuth, useChat
│   │   ├── stores/                   # Zustand (authStore)
│   │   ├── contexts/                 # ThemeContext
│   │   ├── types/                    # Types TypeScript globaux
│   │   └── utils/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── nginx/
├── data/
│   ├── RH_Talan_Tunisie.xlsx
│   ├── CRM_Talan_Tunisie.xlsx
│   └── ERP_Talan_Tunisie.xlsx
├── docs/
│   ├── architecture.md
│   └── api_guide.md
├── .env.example
├── .gitignore
├── CLAUDE.md
└── README.md
```

---

## 9. Backend — détail des modules

### 9.1 Agents IA (LangGraph)

#### Orchestrateur (`orchestrator.py`)
- Utilise `get_json_llm()` pour classifier la requête en JSON structuré
- Domaines : `hr | crm | erp | rag | multi`
- Seuil de confiance : `≥ 0.7` (sinon retry, puis fallback vers `rag`)
- Interdit les opérations d'écriture selon le rôle de l'utilisateur

#### Agents de domaine (`hr_agent.py`, `crm_agent.py`, `erp_agent.py`)
- Boucle ReAct (max 3 itérations)
- Lie le LLM aux outils SQL du domaine via `get_llm_with_tools()`
- Tronque les résultats d'outils à 1 500 caractères (`truncate_tool_result`)
- Stocke `tool_results` et `AIMessage` finale dans `AgentState`

#### Agent RAG (`rag_agent.py`)
- Interroge ChromaDB avec la question reformulée
- Synthétise les passages récupérés en réponse Markdown

#### Nœud de réponse finale (`final_response_node`)
- Reçoit l'ensemble des résultats d'agents
- Synthétise une réponse cohérente en Markdown français

### 9.2 Outils SQL (LangChain Tools)

Chaque outil est une fonction Python décorée `@tool` qui exécute une requête SQL synchrone via SQLAlchemy :

**HR Tools** — `hr_tools.py`
- `list_employees`, `get_employee`, `list_departments`, `list_skills`
- `create_leave_request`, `list_leave_requests`, `update_leave_request`
- `list_projects`, `list_performance_reviews`

**CRM Tools** — `crm_tools.py`
- `list_accounts`, `get_account`, `create_account`
- `list_opportunities`, `create_opportunity`, `update_opportunity`
- `list_contacts`, `list_activities`, `list_leads`

**ERP Tools** — `erp_tools.py`
- `list_customers`, `list_suppliers`, `list_products`
- `list_invoices`, `get_invoice`, `create_invoice`
- `list_sales_orders`, `create_sales_order`
- `list_purchase_orders`, `create_purchase_order`

**Competitive Intel Tools** — `competitive_intel_tools.py`
- Parsing de flux RSS, scanning de job boards, monitoring d'actualités

### 9.3 API REST

Toutes les routes sont sous le préfixe `/api/v1/` :

| Préfixe | Routes principales |
|---------|-------------------|
| `/auth` | `POST /register`, `POST /login`, `GET /me` |
| `/chat` | `POST /stream` (SSE), `POST /` (sync), `GET /conversations`, `GET /conversations/{id}` |
| `/hr` | CRUD employees, departments, skills, leave_requests, projects, performance_reviews |
| `/crm` | CRUD accounts, contacts, opportunities, activities, leads |
| `/erp` | CRUD customers, suppliers, products, invoices, sales_orders, purchase_orders |
| `/stats` | `GET /kpis` (role-gated), `POST /neo4j-sync` |
| `/simulate` | `POST /scenario`, `GET /scenarios/{id}` |
| `/graph` | `GET /nodes`, `GET /relations`, `GET /search` |
| `/competitive-intel` | `POST /scan`, `GET /threats`, `GET /job-signals` |
| `/market-analysis` | `POST /pipeline/run`, `GET /pipeline/status`, `GET /predictions`, `GET /alerts`, `GET /news` |

### 9.4 Modèles de données

#### Schéma `hr` (PostgreSQL `talan_hr`)
| Table | Colonnes principales |
|-------|---------------------|
| `hr_employees` | id, name, email, department_id, contract_type, hire_date, salary |
| `hr_departments` | id, name, manager_id, budget |
| `hr_skills` | id, employee_id, skill_name, level, certified |
| `hr_leave_requests` | id, employee_id, leave_type, status, start_date, end_date |
| `hr_projects` | id, name, status, start_date, end_date, team_ids |
| `hr_performance_reviews` | id, employee_id, reviewer_id, score, period |

#### Schéma `crm` (PostgreSQL `talan_crm`)
| Table | Colonnes principales |
|-------|---------------------|
| `crm_accounts` | id, name, industry, country, revenue, employee_count |
| `crm_contacts` | id, account_id, name, email, phone, role |
| `crm_opportunities` | id, account_id, name, stage, amount, close_date, probability |
| `crm_activities` | id, opportunity_id, type, date, description |
| `crm_leads` | id, name, email, source, status, assigned_to |

#### Schéma `erp` (PostgreSQL `talan_erp`)
| Table | Colonnes principales |
|-------|---------------------|
| `erp_customers` | id, name, email, country, credit_limit |
| `erp_suppliers` | id, name, country, payment_terms |
| `erp_products` | id, name, category, unit_price, stock_quantity |
| `erp_sales_orders` | id, customer_id, status, total_amount, order_date |
| `erp_invoices` | id, sales_order_id, payment_status, due_date, amount |
| `erp_purchase_orders` | id, supplier_id, status, total_amount, expected_delivery |

#### Tables `market_analysis` (PostgreSQL)
- `market_raw_articles`, `market_news_analyses`, `market_alerts`
- `market_reports`, `market_gnn_scores`, `market_recommendations`, `market_pipeline_runs`

#### Tables `competitive_intel` (PostgreSQL)
- `competitive_intelligence`, `threat_signals`, `job_postings`

### 9.5 Services métier

| Service | Rôle |
|---------|------|
| `conversation_service.py` | Persistance des conversations, historique paginé, résumés |
| `neo4j_sync.py` | ETL PostgreSQL → Neo4j (synchronisation nocturne + manuelle) |
| `world_model_service.py` | Snapshot du digital twin (entités + relations) |
| `email_service.py` | Envoi d'emails via SMTP |
| `competitive_intel/scanner.py` | Scraping RSS, job boards, NewsAPI, GNews |

### 9.6 Analyse de marché et GNN

Le pipeline est planifié via APScheduler et peut aussi être déclenché manuellement via l'API :

**Collecte (`collector.py`)**
- Sources : Yahoo Finance, NewsAPI, GNews, Reddit, X/Twitter
- Stockage des articles bruts dans `market_raw_articles`

**Analyse LLM (`analyst.py`)**
- Extraction de relations causales entre entités (entreprises, marchés, événements)
- Scores d'impact et de sentiment

**Mise à jour du graphe de connaissances**
- Upsert des nœuds et arêtes dans Neo4j
- Propagation temporelle des événements

**Entraînement et inférence GNN**
- Modèles disponibles : GAT, TGN (Temporal Graph Network), HGT (Heterogeneous Graph Transformer), HTGN (Hybrid)
- `gnn_predictor.py` : inférence sur le graphe courant
- `compare_models.py` : évaluation et sélection du meilleur modèle

**Rapport et alertes**
- Synthèse des prédictions en recommandations stratégiques
- Alertes à seuils configurables (niveau : info / warning / critical)

### 9.7 LLM Factory

`backend/app/core/llm.py` expose des fonctions décorées `@lru_cache` :

| Fonction | Usage |
|----------|-------|
| `get_llm()` | LLM principal (streaming désactivé pour la stabilité avec tool calling) |
| `get_json_llm()` | LLM en mode JSON pour l'orchestrateur |
| `get_llm_with_tools(tools)` | LLM avec outils LangChain liés |
| `invoke_with_retry(llm, messages)` | Auto-retry sur HTTP 429 avec backoff exponentiel |
| `truncate_tool_result(result_str)` | Tronque à 1 500 caractères |

> **Important :** le cache `lru_cache` persiste en mémoire. Redémarrer le processus après avoir changé `GROQ_MODEL` dans `.env`.

---

## 10. Frontend — détail des modules

### Pages

| Page | Route | Description |
|------|-------|-------------|
| `Landing.tsx` | `/` | Page d'accueil marketing |
| `Login.tsx` | `/login` | Authentification JWT |
| `Signup.tsx` | `/signup` | Inscription |
| `Chat.tsx` | `/chat` | Interface de chat SSE avec streaming Markdown |
| `Dashboard.tsx` | `/dashboard` | KPIs adaptés au rôle (employé/manager/admin) |
| `MarketAnalysis.tsx` | `/market` | Prédictions GNN, actualités, alertes, graphe KG |
| `CompetitiveIntel.tsx` | `/competitive` | Radar de menaces, signaux emploi, timeline actualités |
| `WorldModelExplorer.tsx` | `/world-model` | Visualisation 3D du graphe Neo4j |
| `DigitalTwin.tsx` | `/digital-twin` | Jumeau numérique de l'entreprise |
| `Simulation.tsx` | `/simulation` | Modélisation de scénarios stratégiques |

### Composants clés

**Chat**
- `MessageBubble.tsx` — Rendu Markdown des messages (streaming partiel inclus)
- `MeetingCard.tsx` — Carte de réunion extraite automatiquement des réponses IA

**Market Analysis**
- `GNNPredictions.tsx` — Tableau des prédictions avec scores et tendances
- `KGExplorer.tsx` — Explorateur interactif du graphe de connaissances
- `AlertsFeed.tsx` — Flux d'alertes marché en temps réel
- `PipelineStatusBar.tsx` — Progression du pipeline d'analyse
- `PricesTicker.tsx` — Ticker de prix en défilement
- `StrategicRecommendations.tsx` — Recommandations générées par le LLM

**Competitive Intel**
- `ThreatRadar.tsx` — Radar Chart (Recharts) des niveaux de menaces
- `JobSignalsChart.tsx` — Signaux de recrutement concurrents (graphique barres)
- `NewsTimeline.tsx` — Timeline des actualités concurrentes
- `AnticipationPanel.tsx` — Panel de détection anticipée de mouvements

**World Model**
- `GraphViewer.tsx` — Visualisation 3D force-directed (React Force Graph)
- `LeftSidebar.tsx` — Filtres de nœuds et légende
- `RightPanel.tsx` — Détail d'un nœud sélectionné
- `StatsBar.tsx` — Statistiques globales du graphe

**UI Primitives**
- `GlassCard.tsx` — Carte glassmorphism
- `SkeletonCard.tsx` — Placeholder de chargement
- `ParticleCanvas.tsx` — Fond animé particules

### State management

- **Zustand** (`authStore.ts`) : token JWT, utilisateur courant, rôle
- **TanStack Query** : cache et invalidation des requêtes API
- **ThemeContext** : thème sombre / clair

---

## 11. Tests

```bash
cd backend

# Tests rapides (LLM mocké, sans Docker)
python -m pytest tests/ -v -m "not live"

# Tests complets (nécessitent Docker + PostgreSQL + clé Groq)
python -m pytest tests/ -v -m live

# Fichier unique
python -m pytest tests/test_agent_crm.py -v -m live

# Test spécifique
python -m pytest tests/test_agent_crm.py::test_crm_list_opportunities -v -m live
```

| Type | Marqueur | Prérequis | Taux de succès attendu |
|------|----------|-----------|------------------------|
| Rapides | `not live` | Aucun | 100% |
| Live | `live` | Docker + Groq API | ~16/18 |

IDs de test utilisés dans les fixtures :
- RH : `EMP0001` – `EMP0010`
- CRM : `ACC0001` – `ACC0010`
- ERP : `CUS0001` – `CUS0157`

---

## 12. Valeurs d'énumération (base de données)

Toutes les valeurs enum sont en **anglais**. Elles doivent être utilisées exactement telles quelles dans les prompts et les outils SQL :

| Table | Colonne | Valeurs valides |
|-------|---------|-----------------|
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

---

## 13. Quotas LLM (Groq Free Tier)

Chaque requête au pipeline consomme environ **2 000 tokens** → ~50 requêtes/jour sur le tier gratuit.

| Modèle | TPM | TPD | Notes |
|--------|-----|-----|-------|
| `llama-3.3-70b-versatile` | 12 000 | 100 000 | **Recommandé** — meilleur tool calling |
| `qwen/qwen3-32b` | 6 000 | 100 000 | Fallback — limiter les résultats |
| `meta-llama/llama-4-scout-17b-16e-instruct` | 30 000 | 500 000 | Fallback haut-débit |
| `moonshotai/kimi-k2-instruct` | 10 000 | — | À éviter — échoue sur tool calling |

En cas d'épuisement du quota : modifier `GROQ_MODEL` dans `backend/.env` et **redémarrer le processus**.

---

## 14. Outils de développement

| Script | Usage |
|--------|-------|
| `start_backend.bat` | Démarre le backend sous Windows |
| `start_frontend.bat` | Démarre le frontend sous Windows |
| `backend/chat_cli.py` | CLI interactif pour tester les agents |
| `backend/check_llm_quota.py` | Vérifie la connectivité et le quota Groq |
| `backend/build_gnn_dataset.py` | Construit le dataset GNN depuis Neo4j |
| `http://localhost:8000/docs` | Swagger UI auto-généré (FastAPI) |
| `http://localhost:8080` | Adminer (interface web PostgreSQL) |
| `http://localhost:7474` | Neo4j Browser |

---

## 15. Auteur

**Projet PFE — Talan Tunisie 2025**

Développé dans le cadre d'un stage de fin d'études (PFE) au sein de [Talan Tunisie](https://talan.com).
