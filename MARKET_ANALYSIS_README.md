# Market Analysis Agent — Documentation Complète

> Agent d'intelligence de marché autonome pour **Talan**, intégré au pipeline LangGraph existant.
> Surveille les actualités économiques, analyse les impacts causaux via LLM, met à jour un Knowledge Graph Neo4j, et prédit les risques futurs avec un GNN hétérogène temporel.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   APScheduler (toutes les 30min)         │
│                                                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │Collector │ → │ Analyst  │ → │  World   │             │
│  │          │   │  (LLM)   │   │  Model   │             │
│  │NewsAPI   │   │          │   │ (Neo4j)  │             │
│  │GNews     │   │Causal    │   │          │             │
│  │RSS Feeds │   │Extraction│   │Temporal  │             │
│  │yfinance  │   │JSON out  │   │Het. KG   │             │
│  └──────────┘   └──────────┘   └────┬─────┘             │
│                                     │                    │
│  ┌──────────┐   ┌──────────┐   ┌────▼─────┐             │
│  │ Alerts   │ ← │  Report  │ ← │   GNN    │             │
│  │ Slack/   │   │Synthesis │   │Predictor │             │
│  │ Email    │   │          │   │          │             │
│  │ Log      │   │ Markdown │   │HetGATConv│             │
│  └──────────┘   └──────────┘   │ Temporal │             │
│                                 │ Encoding │             │
│                                 └──────────┘             │
└─────────────────────────────────────────────────────────┘

         ┌────────────────────────────────┐
         │   LangGraph Chat Interface     │
         │                                │
         │  User: "Quel est le risque     │
         │  de la crise Moyen-Orient      │
         │  sur Talan ?"                  │
         │                                │
         │  → market_analysis_agent_node  │
         │    ↳ get_talan_risk_snapshot   │
         │    ↳ get_gnn_predictions       │
         │    ↳ get_hidden_risks          │
         │    → Réponse Markdown FR       │
         └────────────────────────────────┘
```

### Fichiers créés

```
backend/
├── app/
│   ├── agents/
│   │   └── market_analysis_agent.py          # LangGraph node + 5 tools
│   ├── api/routes/
│   │   └── market_analysis.py                # 12 REST endpoints
│   ├── core/
│   │   └── config.py                         # + 7 nouvelles variables
│   ├── models/
│   │   └── market_analysis_models.py         # 5 tables SQLAlchemy
│   ├── prompts/
│   │   └── market_analysis_prompts.py        # 3 prompts LLM
│   ├── schemas/
│   │   └── market_analysis_schemas.py        # 20 schémas Pydantic
│   └── services/market_analysis/
│       ├── __init__.py
│       ├── collector.py                       # NewsAPI + GNews + RSS + yfinance
│       ├── analyst.py                         # LLM causal extraction
│       ├── world_model.py                     # Neo4j KG updater
│       ├── gnn_predictor.py                   # Heterogeneous Temporal GNN
│       ├── orchestrator.py                    # APScheduler pipeline
│       └── kg_schema.cypher                   # Schéma Neo4j + seed data
└── MARKET_ANALYSIS_README.md
```

---

## Installation

### 1. Variables d'environnement

Ajouter dans `backend/.env` :

```env
# ── Market Analysis ───────────────────────────────────────────────────────────
# NewsAPI (https://newsapi.org) — 100 req/jour gratuit
NEWSAPI_KEY=your_newsapi_key_here

# GNews (https://gnews.io) — 100 req/jour gratuit
GNEWS_KEY=your_gnews_key_here

# Alpha Vantage — optionnel (fallback yfinance)
ALPHA_VANTAGE_KEY=your_alpha_vantage_key_here

# Slack webhook pour alertes critiques (optionnel)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Intervalle pipeline en minutes (défaut: 30)
MARKET_ANALYSIS_INTERVAL_MINUTES=30

# Seuil d'alerte talan_impact_score (défaut: 0.4)
MARKET_ALERT_THRESHOLD=0.4

# Chemin du modèle GNN sauvegardé
GNN_MODEL_PATH=./gnn_model.pt
```

### 2. Dépendances Python

```bash
cd backend
pip install yfinance httpx
```

#### GNN (optionnel mais recommandé)

**CPU uniquement :**
```bash
pip install torch==2.3.0 torch-geometric
```

**GPU CUDA 12.1 :**
```bash
pip install torch==2.3.0+cu121 -f https://download.pytorch.org/whl/torch_stable.html
pip install torch-geometric -f https://data.pyg.org/whl/torch-2.3.0+cu121.html
```

> ℹ️ Sans PyTorch Geometric, l'agent utilise automatiquement un prédicteur heuristique basé sur la propagation de poids dans le graphe.

### 3. Schéma Neo4j

Initialiser le KG avec les contraintes et données de seed :

```bash
# Via la CLI cypher-shell (Docker)
docker exec -i neo4j cypher-shell -u neo4j -p talan_neo4j \
  < backend/app/services/market_analysis/kg_schema.cypher

# Ou via le navigateur Neo4j (http://localhost:7474)
# Copier-coller le contenu de kg_schema.cypher
```

Ou via Python :
```python
from app.services.market_analysis.world_model import WorldModel
wm = WorldModel()
wm.ensure_schema()
wm.ensure_talan_node()
```

---

## Démarrage

### Avec Docker (recommandé)

```bash
cd infra
docker-compose up --build
```

Le pipeline démarre automatiquement au lancement de l'API FastAPI.

### Sans Docker

```bash
cd backend
uvicorn app.main:app --reload
```

Le pipeline se lance en arrière-plan toutes les 30 minutes.

### Déclencher manuellement (API)

```bash
curl -X POST http://localhost:8000/api/v1/market/run \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["NVDA", "MSFT"], "force_gnn": true}'
```

---

## API Endpoints

| Méthode | URL | Description |
|---|---|---|
| `GET` | `/api/v1/market/status` | Statut du pipeline |
| `POST` | `/api/v1/market/run` | Déclencher un cycle (manager+) |
| `GET` | `/api/v1/market/alerts` | Alertes récentes |
| `GET` | `/api/v1/market/reports` | Liste des rapports |
| `GET` | `/api/v1/market/reports/{id}` | Rapport complet |
| `GET` | `/api/v1/market/kg/snapshot` | Ego-graphe Neo4j autour de Talan |
| `GET` | `/api/v1/market/kg/risks` | Risques directs sur Talan |
| `GET` | `/api/v1/market/kg/hidden` | Risques cachés (2-3 sauts) |
| `GET` | `/api/v1/market/kg/stats` | Stats du KG |
| `GET` | `/api/v1/market/gnn/predict` | Inférence GNN à la demande |
| `GET` | `/api/v1/market/analyses` | Analyses LLM récentes |
| `GET` | `/api/v1/market/prices` | Snapshot prix/volumes/volatilité |

Tous les endpoints requièrent un JWT Bearer token (`POST /api/v1/auth/login`).

---

## Utilisation via le Chat

L'agent répond aux questions en langue naturelle dans l'interface de chat :

**Exemples de questions :**
- *"Quel est l'impact de la hausse des taux BCE sur Talan ?"*
- *"Y a-t-il des risques cachés liés au conflit Moyen-Orient ?"*
- *"Quelles sont les dernières alertes de marché ?"*
- *"Analyse l'impact de DeepSeek sur notre secteur"*
- *"Quel est le risque systémique actuel ?"*

Le pipeline LangGraph route automatiquement vers `market_analysis_agent_node` quand le domaine détecté est `market`.

> **Note :** Pour activer ce routing, ajouter `"market"` comme domaine valide dans l'orchestrateur LangGraph (`backend/app/agents/orchestrator.py`) et entraîner/mettre à jour le prompt de classification.

---

## Entraînement du GNN

### Données historiques depuis Neo4j

```python
from app.services.market_analysis.world_model import WorldModel
from app.services.market_analysis.gnn_predictor import GNNPredictor, GraphBuilder

wm = WorldModel()
gnn = GNNPredictor()
builder = GraphBuilder()

# Récupérer snapshots historiques
snapshots = []
for event_date in historical_dates:  # e.g. 2020-2026
    snap = wm.get_snapshot_at_date("Talan", date=event_date)
    actual_impact = get_actual_talan_impact(event_date)  # from financial data
    data = builder.build_from_kg_snapshot(snap)
    if data:
        snapshots.append((data, actual_impact))

# Entraînement
metrics = gnn.train(
    training_snapshots=snapshots,
    epochs=100,
    lr=1e-3,
)
print(f"Losses: {metrics['train_losses'][-5:]}")

# Le modèle est sauvegardé automatiquement vers GNN_MODEL_PATH
```

---

## Architecture GNN — Détails

```
Input Features (par nœud Company):
  [384-dim LLM embedding]           ← sentence-transformers/all-MiniLM-L6-v2
+ [4 financial features]            ← price_change%, volume, volatility, market_cap
+ [4 structural features]           ← degree, betweenness, etc.
= 392-dim feature vector

Architecture:
  PerNodeType Linear(392 → 128)
  ↓
  HeteroGATConv × 2 (128 → 128, 4 heads)
    + edge_attr: [impact_score, confidence, time_delta] + TemporalEncoding(32)
  ↓
  ┌─── Node Regression: Linear(128→64→1) + Tanh   → impact ∈ [-1, 1]
  ├─── Link Prediction: Linear(256→128→1) + Sigmoid → P(new edge)
  └─── Graph Risk:      MeanPool → Linear(128→64→1) + Sigmoid → risk ∈ [0, 1]

Node types: Company, Sector, Country, Event, MacroIndicator
Edge types: CAUSES_IMPACT_ON, BELONGS_TO_SECTOR, SUPPLY_CHAIN_LINK,
            COMPETES_WITH, OPERATES_IN, TRIGGERS_EVENT, AFFECTS_INDICATOR
```

---

## Prompt LLM Analyst — Points Clés

Le prompt `ANALYST_SYSTEM_PROMPT` :
- Extrait **entités** (entreprises, secteurs, pays, événements, indicateurs macro)
- Extrait **relations causales** avec `impact_score` ∈ [-1, +1] et `confidence` ∈ [0, 1]
- Capture les **effets de second ordre** automatiquement
- Évalue toujours l'**impact sur Talan** spécifiquement (ESN, consulting IT, France)
- Retourne un **JSON strict** validé par Pydantic `NewsAnalysis`
- Marque `talan_relevant=true` sur les relations qui peuvent atteindre Talan en 1-3 sauts

---

## Quotas et Limites

| Source | Quota gratuit | Stratégie |
|---|---|---|
| NewsAPI | 100 req/jour | 5 queries × 20 articles = 100 max |
| GNews | 100 req/jour | 3 queries × 10 articles = 30 max |
| RSS | Illimité | 8 feeds, polled chaque cycle |
| yfinance | Soft limit | 15 tickers max par cycle |
| Groq LLM | ~100k tokens/jour | ~40 articles/jour analysés |

**Recommandation production :** Passer à NewsAPI Premium + compte Groq payant pour analyser 200+ articles/jour.

---

## Monitoring

### Logs importants

```bash
# Voir les logs du pipeline
docker logs talan-backend -f | grep -E "Pipeline|GNN|WorldModel|Analyst"

# Vérifier Neo4j
curl http://localhost:7474/browser/

# Stats KG en temps réel
curl http://localhost:8000/api/v1/market/kg/stats \
  -H "Authorization: Bearer TOKEN"
```

### Tableau de bord Neo4j Bloom

1. Ouvrir http://localhost:7474
2. Se connecter (neo4j / talan_neo4j)
3. Requête de visualisation :
```cypher
MATCH (t:Company {name: 'Talan'})-[r*1..2]-(neighbor)
RETURN t, r, neighbor LIMIT 100
```

---

## Roadmap / Extensions

- [ ] Intégration Slack/Teams pour alertes critiques (implémenter `_dispatch_alert`)
- [ ] Entraînement GNN sur données historiques 2020-2026
- [ ] Playwright scraper pour articles sans RSS
- [ ] Tableau de bord React pour visualisation du KG et prédictions GNN
- [ ] Support multi-entreprises (pas seulement Talan)
- [ ] Fine-tuning du LLM Analyst sur données annotées Talan
- [ ] Link prediction pour anticiper nouvelles relations causales
