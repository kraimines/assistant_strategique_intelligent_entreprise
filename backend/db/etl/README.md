# ETL Pipeline — Talan Intelligent Platform

Pipeline production-ready pour l'extraction, transformation et chargement des données de trois domaines métier (RH, CRM, ERP) vers PostgreSQL et Neo4j.

## Architecture

```
RH_Talan_Tunisie.xlsx ──┐
CRM_Talan_Tunisie.xlsx ─┼─→ [T-04/05/06/07] ──→ PostgreSQL ──┐
ERP_Talan_Tunisie.xlsx ─┘                                      ├─→ [T-08] ──→ Neo4j Graph
                                                                 ↑
                                                          (Synchronisation)
```

### Phases

| Phase | Module | Input | Output | Description |
|-------|--------|-------|--------|-------------|
| **T-04/05** | `etl_rh.py` | `RH_Talan_Tunisie.xlsx` | `talan_hr` | Données RH : depts, employés, projets, compétences, congés, revues |
| **T-06** | `etl_crm.py` | `CRM_Talan_Tunisie.xlsx` | `talan_crm` | Données CRM : comptes, contacts, opportunités, activités |
| **T-07** | `etl_erp.py` | `ERP_Talan_Tunisie.xlsx` | `talan_erp` | Données ERP : clients, fournisseurs, produits, commandes, factures |
| **T-08** | `etl_neo4j.py` | `talan_hr/crm/erp` | `Neo4j Graph` | 15 types de nœuds + 24 relations cross-domain |

## Fichiers

```
backend/etl/
├── config.py              ← Configuration (à adapter pour chaque env)
├── utils.py               ← Helpers DB, logging, pandas
├── etl_rh.py              ← T-04/05 RH Extraction
├── etl_crm.py             ← T-06 CRM Extraction
├── etl_erp.py             ← T-07 ERP Extraction
├── etl_neo4j.py           ← T-08 Neo4j Sync
├── run_all_etl.py         ← Master Orchestrator
├── __init__.py            ← Package init
└── README.md              ← Cette documentation
```

## Configuration

Tous les paramètres se configurent via **`.env`** à la racine du projet :

```bash
# PostgreSQL (3 bases séparées)
POSTGRES_USER=talan
POSTGRES_PASSWORD=talan_secret
POSTGRES_HOST=postgres      # "localhost" en dev local
POSTGRES_PORT=5432
POSTGRES_DB_HR=talan_hr
POSTGRES_DB_CRM=talan_crm
POSTGRES_DB_ERP=talan_erp

# Neo4j
NEO4J_URI=bolt://neo4j:7687        # "bolt://localhost:7687" en dev local
NEO4J_USER=neo4j
NEO4J_PASSWORD=talan_neo4j

# ETL
DATA_DIR=./data                     # Dossier contenant les Excel
LOG_LEVEL=INFO                      # DEBUG / INFO / WARNING / ERROR
ENVIRONMENT=development
```

## Fichiers Excel requis

Place dans `data/` :

| Fichier | Tables | Exemples de feuilles |
|---------|--------|----------------------|
| `RH_Talan_Tunisie.xlsx` | hr_* (9 tables) | departments, employees, projects, skills, leave_requests, timesheets, performance_reviews, project_milestones, employee_projects |
| `CRM_Talan_Tunisie.xlsx` | crm_* (4 tables) | accounts, contacts, opportunities, activities |
| `ERP_Talan_Tunisie.xlsx` | erp_* (7 tables) | suppliers, customers, products, sales_orders, purchase_orders, invoices, payments |

## Installation & Dépendances

```bash
# Installer les dépendances Python depuis le Dockerfile backend
pip install -r backend/requirements.txt

# Dépendances clés pour l'ETL :
pandas==2.x           # Lecture/traitement Excel
psycopg2==2.9.x       # PostgreSQL
neo4j==5.x            # Neo4j
openpyxl==3.x         # Support Excel (pandas → openpyxl)
```

## Utilisation

### 1. Vérifier la configuration

```bash
cd backend/etl
python config.py

# Affiche :
# === ETL Configuration ===
# Environment: development
# Data Directory: /path/to/data
# Excel Files:
#   ✓ RH: /path/to/data/RH_Talan_Tunisie.xlsx
#   ...
```

### 2. Exécuter l'ETL complet

```bash
# Depuis la racine du projet
python -m backend.etl.run_all_etl

# Ou depuis backend/etl
cd backend/etl
python run_all_etl.py
```

Output :
```
╔════════════════════════════════════════════════════════════════╗
║           Talan Platform - ETL Orchestrator                   ║
╚════════════════════════════════════════════════════════════════╝

┌─ Phase 1: PostgreSQL ETL ────────────────────────────────┐
... [T-04/05 RH logs] ...
... [T-06 CRM logs] ...
... [T-07 ERP logs] ...
└────────────────────────────────────────────────────────────┘

┌─ Phase 2: Neo4j Graph ETL ──────────────────────────────┐
... [T-08 Neo4j logs] ...
└────────────────────────────────────────────────────────────┘

================== RÉSUMÉ ETL ==================

  ✅  T-04/05 RH
  ✅  T-06 CRM
  ✅  T-07 ERP
  ✅  T-08 Neo4j

  Durée totale : 45.2s
  Statut global : ✅ SUCCÈS
```

### 3. Exécuter partiellement

```bash
# Seulement PostgreSQL (pas Neo4j)
python run_all_etl.py --skip-neo4j

# Seulement Neo4j (si PostgreSQL déjà chargé)
python run_all_etl.py --neo4j-only

# Seulement domaines spécifiques
python run_all_etl.py --hr --crm          # RH + CRM
python run_all_etl.py --hr                # RH seul
python run_all_etl.py --crm               # CRM seul
python run_all_etl.py --erp               # ERP seul
```

### 4. Exécuter un script individuel

```bash
cd backend/etl

# T-04/05 RH
python etl_rh.py
# T-06 CRM
python etl_crm.py
# T-07 ERP
python etl_erp.py
# T-08 Neo4j
python etl_neo4j.py
```

### 5. En environnement Docker

```bash
# Depuis le container API
docker exec -it talan_api python -m backend.etl.run_all_etl

# Ou en buildant une task Docker
docker run --name etl --network talan-intelligent-platform_talan-network \
  -e POSTGRES_HOST=postgres \
  -e NEO4J_URI=bolt://neo4j:7687 \
  -v ./data:/data \
  talan:latest python -m backend.etl.run_all_etl
```

## Architecture détaillée de chaque script

### config.py

```python
# Variables d'env avec défauts sensibles
POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD
POSTGRES_DB_HR, POSTGRES_DB_CRM, POSTGRES_DB_ERP
NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
EXCEL_FILES = {"rh": ..., "crm": ..., "erp": ...}

# Fonctions utilitaires
pg_connection_string(domain)  # SQLAlchemy URI
pg_dsn(domain)                # psycopg2 DSN
```

### utils.py

```python
# Logging
get_logger(name)              # Logger configuré

# Context managers
pg_conn(domain)               # Connexion PostgreSQL avec autocommit
execute_ddl(conn, ddl_sql)    # Exécuter DDL

# Pandas helpers
read_sheet(excel_path, sheet_name)    # Lire feuille Excel
clean_str_cols(df)                    # Strip + remplacer '' par None
coerce_dates(df, date_cols)           # Convertir en DATE
nullable_float(df, float_cols)        # Convertir en FLOAT NULL

# Upsert
upsert_dataframe(conn, df, table_name, key_columns)  # INSERT ... ON CONFLICT
```

### etl_*.py

Structure commune :

```python
# 1. DDL (CREATE SCHEMA + CREATE TABLE + CREATE INDEX)
DDL_SCHEMA = "CREATE SCHEMA IF NOT EXISTS ..."
DDL_TABLES = """..."""

# 2. Loaders (une fonction par table)
def load_table_name(conn) -> int:
    # Lire Excel → pandas DataFrame
    # Nettoyer (clean_str_cols, coerce_dates, etc.)
    # Upsert vers PostgreSQL
    # Retourner nombre de lignes

# 3. Main entry point
def run():
    with pg_conn(domain) as conn:
        execute_ddl(conn, DDL_SCHEMA)
        execute_ddl(conn, DDL_TABLES)
        load_table_1(conn)
        load_table_2(conn)
        ...

if __name__ == "__main__":
    run()
```

### etl_neo4j.py (Spécificités)

```python
# 1. Créer contraintes d'unicité (équivalent FK relationnelles)
create_constraints(session)
create_indexes(session)

# 2. Créer nœuds (batch de BATCH_SIZE)
load_departments(session)   # :Department
load_employees(session)     # :Employee
load_projects(session)      # :Project
load_accounts(session)      # :Account (CRM)
load_opportunities(session) # :Opportunity
load_customers(session)     # :Customer (ERP)
load_skills(session)        # :Skill

# 3. Créer relations (MATCH + CREATE)
load_relationships(session)
  # Employee -[BELONGS_TO]-> Department
  # Employee -[MANAGED_BY]-> Employee
  # Employee -[ASSIGNED_TO]-> Project
  # Employee -[HAS_SKILL]-> Skill
  # Project -[FOR_ACCOUNT]-> Account
  # Opportunity -[HAS_ACCOUNT]-> Account
  # Customer -[LINKED_TO_ACCOUNT]-> Account
  # ...

# 4. Validation
validate_graph(session)
```

## Résultats attendus

### PostgreSQL

```
talan_hr (HR Domain)           talan_crm (CRM Domain)        talan_erp (ERP Domain)
├─ hr_departments       50      ├─ crm_accounts        80     ├─ erp_suppliers       15
├─ hr_employees        200      ├─ crm_contacts       300     ├─ erp_customers       80
├─ hr_projects          30      ├─ crm_opportunities  150     ├─ erp_products       200
├─ hr_employee_projects 120     └─ crm_activities      500     ├─ erp_sales_orders   180
├─ hr_project_milestones 60                                   ├─ erp_invoices       500
├─ hr_timesheets       400                                    ├─ erp_purchase_orders 100
├─ hr_skills           600                                    └─ erp_payments       550
├─ hr_leave_requests     80
└─ hr_performance_reviews 50
```

### Neo4j

```
15 Node Labels:
  - Employee (200), Department (50), Project (30)
  - Account (80), Opportunity (150), Contact (300)
  - Customer (80), Supplier (15), Product (200)
  - SalesOrder (180), Invoice (500), Payment (550)
  - Skill (600), LeaveRequest (80), PerformanceReview (50)

24 Relationship Types:
  - BELONGS_TO, MANAGED_BY, ASSIGNED_TO, HAS_SKILL
  - FOR_ACCOUNT, HAS_ACCOUNT, LINKED_TO_ACCOUNT
  - SUPPLIES, PLACED_ORDER, HAS_INVOICE
  - ... (24 total)

Total: ~3000 nœuds, ~5000+ relations
```

## Validation au post-ETL

### PostgreSQL

```sql
-- Par domaine
SELECT schemaname, COUNT(*) as tables 
FROM pg_tables 
WHERE schemaname IN ('hr', 'crm', 'erp') 
GROUP BY schemaname;

-- Par table
SELECT 'hr_departments' AS table_name, COUNT(*) FROM hr.hr_departments
UNION ALL
SELECT 'hr_employees', COUNT(*) FROM hr.hr_employees
UNION ALL
... (toutes les tables)
ORDER BY COUNT(*) DESC;

-- Vérifier les clés étrangères
SELECT constraint_name FROM information_schema.table_constraints 
WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'hr';
```

### Neo4j

```cypher
-- Compter les nœuds
MATCH (n) 
RETURN labels(n)[0] AS label, COUNT(n) AS count 
ORDER BY count DESC;

-- Compter les relations
MATCH ()-[r]->() 
RETURN type(r) AS rel_type, COUNT(r) AS count 
ORDER BY count DESC;

-- Vérifier les contraintes
CALL db.constraints();

-- Top 5 nœuds les plus connectés
MATCH (n)
RETURN n, size((n)--()) AS connections
ORDER BY connections DESC
LIMIT 5;
```

## Troubleshooting

### Excel file not found
```
FileNotFoundError: Excel file not found: /path/to/RH_Talan_Tunisie.xlsx
```
**Solution** : Placer les fichiers dans `data/` ou régler `DATA_DIR` dans `.env`

### Sheet not found
```
ValueError: Sheet 'employees' not found in RH_Talan_Tunisie.xlsx
```
**Solution** : Vérifier que la feuille Excel existe et que son nom est exact (case-sensitive)

### PostgreSQL connection failed
```
psycopg2.OperationalError: could not translate host name "postgres" to address
```
**Solution** : En dev local, régler `POSTGRES_HOST=localhost` dans `.env`

### Neo4j connection failed
```
neo4j.exceptions.ServiceUnavailable: bolt://neo4j:7687
```
**Solution** : Vérifier que Neo4j tourne (Docker) et que `NEO4J_URI` est correct

### Foreign Key constraint violation
```
psycopg2.IntegrityError: insert or update on table "..." violates foreign key...
```
**Solution** : S'assurer que l'ordre de chargement respecte les dépendances (ex: departments avant employees)

### Duplicate key value
```
psycopg2.IntegrityError: duplicate key value violates unique constraint
```
**Solution** : Data d'entrée contient des doublons. Les filtrer avant l'import ou utiliser `ON CONFLICT DO UPDATE`.

## Performance

| Métrique | Típique |
|----------|---------|
| **RH ETL** (T-04/05) | 5-10s (200 emp, 500 skills, 80 leaves, ...) |
| **CRM ETL** (T-06) | 3-5s (80 accts, 150 opps, 300 contacts) |
| **ERP ETL** (T-07) | 8-12s (500 invoices, 200 products, 180 orders) |
| **Neo4j Sync** (T-08) | 10-15s (3000+ nœuds, 5000+ relations, batch UNWIND) |
| **ETL Total** | ~30-45s |

Optimisations :
- Batch upsert de 500 lignes (SQL INSERT ... VALUES())
- Neo4j UNWIND pour relations (batch 200)
- Index sur FK et colonnes de recherche
- Connexion pool (optionnel)

## Development

### Ajouter une nouvelle table

1. Ajouter la feuille Excel
2. Ajouter le DDL dans `DDL_TABLES`
3. Écrire `load_table_name(conn)` fonction
4. Appeler dans `run()`

Exemple :

```python
def load_new_table(conn) -> int:
    log.info("Chargement de new_table …")
    df = read_sheet(RH_PATH, "new_data")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["date_column"])
    df = nullable_float(df, ["amount_column"])
    
    cols = ["id", "name", "date_column", "amount_column"]
    df = df[[c for c in cols if c in df.columns]]
    
    n = upsert_dataframe(conn, df, "hr.new_table", ["id"])
    log.info(f"  → {n} lignes")
    return n
```

### Ajouter une nouvelle relation Neo4j

```python
# Dans load_relationships(session)
log.info("  Relation NEW_REL (NodeType1 → NodeType2) …")
rows = pg_fetchall("domain", "SELECT id1, id2 FROM table WHERE id2 IS NOT NULL")
cypher = """
MATCH (n1:NodeType1 {id: record.id1})
MATCH (n2:NodeType2 {id: record.id2})
CREATE (n1)-[:NEW_REL]->(n2)
"""
for i in range(0, len(rows), BATCH_SIZE):
    run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
```

## Roadmap

- [ ] Validation de schéma vs fichiers Excel
- [ ] Retry logic pour résilience réseau
- [ ] Incremental ETL (juste les deltas)
- [ ] Audit trail (log des imports, versions, checksum)
- [ ] Chiffrement des données sensibles (salaires)
- [ ] Streaming pour gros fichiers Excel
- [ ] Monitoring & alertes (Prometheus)
- [ ] Transaction distribuée (2PC PostgreSQL + Neo4j)

## Support

Pour toute question ou bug :
- Vérifier les logs (niveau `DEBUG` pour plus de détails)
- Consulter cette documentation
- Ouvrir une GitHub issue avec logs + étapes pour reproduire
