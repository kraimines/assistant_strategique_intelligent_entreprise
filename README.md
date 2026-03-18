# assistant_strategique_intelligent_entreprise

![Python](https://img.shields.io/badge/Python-3.11-blue)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

Plateforme d'Entreprise Intelligente développée dans le cadre d'un PFE chez Talan Tunisie.
Le projet combine un assistant IA conversationnel, des tableaux de bord personnalisés selon le profil utilisateur (Employé / Manager / Direction), et un moteur de simulation stratégique orienté prise de décision.
L'objectif est d'unifier les données RH, CRM et ERP pour accélérer l'analyse, améliorer la visibilité métier et soutenir la planification proactive.

## Architecture (vue par couche)

- **Backend (FastAPI)** : expose des API métiers, orchestre les agents IA, et centralise la logique de sécurité, configuration et accès aux données.
- **IA (LangGraph/LangChain + ChromaDB)** : coordonne les agents spécialisés, le RAG documentaire et la génération de réponses contextuelles.
- **Frontend (React + Vite + Tailwind + Recharts)** : fournit une expérience conversationnelle et des dashboards interactifs adaptés aux rôles.
- **Données (PostgreSQL + Neo4j + Redis)** : PostgreSQL stocke les données transactionnelles (schémas hr/crm/erp), Neo4j les relations métiers, Redis la couche cache/session.
- **Infrastructure (Docker Compose + LangSmith)** : normalise l'exécution locale des services et l'observabilité des flux IA.

## Prérequis

- Python **3.11**
- Node.js **18+**
- Docker + Docker Compose

## Lancement local

1. **Cloner le dépôt**
   ```bash
   git clone https://github.com/<votre-org>/assistant_strategique_intelligent_entreprise.git
   cd assistant_strategique_intelligent_entreprise
   ```
2. **Copier et compléter l'environnement**
   ```bash
   Copy-Item .env.example .env
   ```
   Puis renseigner les variables dans `.env`.
3. **Démarrer les services**
   ```bash
   cd infra
   docker-compose up --build
   ```
4. **Frontend** : http://localhost:5173
5. **API Swagger** : http://localhost:8000/docs

## Structure du projet

```text
.
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── hr.py
│   │   │   │   ├── crm.py
│   │   │   │   ├── erp.py
│   │   │   │   ├── chat.py
│   │   │   │   └── simulate.py
│   │   │   └── deps.py
│   │   ├── agents/
│   │   │   ├── orchestrator.py
│   │   │   ├── hr_agent.py
│   │   │   ├── crm_agent.py
│   │   │   ├── erp_agent.py
│   │   │   ├── rag_agent.py
│   │   │   └── simulator_agent.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── database.py
│   │   ├── models/
│   │   │   ├── hr_models.py
│   │   │   ├── crm_models.py
│   │   │   └── erp_models.py
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── etl/
│   │   ├── etl_hr.py
│   │   ├── etl_crm.py
│   │   ├── etl_erp.py
│   │   └── etl_neo4j.py
│   ├── rag/
│   │   ├── ingest.py
│   │   └── retriever.py
│   ├── simulation/
│   │   ├── metamodel.py
│   │   ├── scenario_builder.py
│   │   └── propagation.py
│   ├── tests/
│   │   ├── test_hr_api.py
│   │   ├── test_crm_api.py
│   │   ├── test_erp_api.py
│   │   └── test_agents.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Chat/
│   │   │   ├── Dashboard/
│   │   │   └── Simulation/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── types/
│   │   └── main.tsx
│   ├── Dockerfile
│   └── package.json
├── data/
│   ├── raw/
│   │   ├── RH_Talan_Tunisie.xlsx
│   │   ├── CRM_Talan_Tunisie.xlsx
│   │   └── ERP_Talan_Tunisie.xlsx
│   └── documents/
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── nginx/
├── docs/
│   ├── architecture.md
│   └── api_guide.md
├── .env.example
├── .gitignore
└── README.md
```

## Auteur

**Auteur** : Projet PFE – Talan Tunisie 2025
