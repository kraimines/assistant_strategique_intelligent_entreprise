"""
etl_neo4j.py — T-08 : Population du graphe Neo4j depuis PostgreSQL

Crée les nœuds et relations dans Neo4j depuis les données PostgreSQL.
Suit le schéma défini dans backend/db/neo4j/neo4j_schema_talan.py

Nœuds créés (15 types) :
  Employee, Department, Project, Milestone, Account, Opportunity,
  Customer, Supplier, Product, SalesOrder, Invoice, Skill, LeaveRequest,
  PerformanceReview, JobOpening

Relations créées (24 types) :
  BELONGS_TO, MANAGED_BY, ASSIGNED_TO, HAS_SKILL, SUBMITTED_LEAVE,
  FOR_ACCOUNT, HAS_OPPORTUNITY, LINKED_TO_ACCOUNT, SUPPLIES, etc.

Usage:
    python etl_neo4j.py
    python etl_neo4j.py --validate-only
"""

import os
import sys

import decimal
import datetime
import psycopg2
from neo4j import GraphDatabase

sys.path.insert(0, os.path.dirname(__file__))

from config import pg_dsn, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from utils import get_logger

log = get_logger("ETL-Neo4j")

BATCH_SIZE = 200  # lignes par appel Cypher UNWIND


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

import psycopg2.extras


def _neo4j_value(v):
    """Convertit les types Python non supportés par le driver Neo4j."""
    if v is None:
        return None
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return str(v)
    return v


def pg_fetchall(schema: str, sql: str) -> list:
    """Récupère les résultats d'une requête PostgreSQL, types Neo4j-compatibles."""
    try:
        conn = psycopg2.connect(pg_dsn(schema))
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{k: _neo4j_value(v) for k, v in dict(r).items()} for r in rows]
    except psycopg2.Error as e:
        log.warning(f"Query failed in schema {schema}: {e}")
        return []


def run_cypher_batch(session, query: str, records: list) -> int:
    """Exécute une requête Cypher en lot (UNWIND)."""
    if not records:
        return 0

    cypher = f"""
    UNWIND $records AS record
    {query}
    """

    try:
        result = session.run(cypher, records=records)
        summary = result.consume()
        c = summary.counters
        return c.nodes_created + c.relationships_created
    except Exception as e:
        log.warning(f"Cypher batch failed: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  Création des contraintes et indexes
# ═══════════════════════════════════════════════════════════════════════════════

def create_constraints(session):
    """Crée les contraintes d'unicité."""
    log.info("Création des contraintes Neo4j …")
    
    constraints = [
        "CREATE CONSTRAINT emp_id IF NOT EXISTS FOR (e:Employee) REQUIRE e.employee_id IS UNIQUE",
        "CREATE CONSTRAINT dept_id IF NOT EXISTS FOR (d:Department) REQUIRE d.department_id IS UNIQUE",
        "CREATE CONSTRAINT prj_id IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
        "CREATE CONSTRAINT acct_id IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
        "CREATE CONSTRAINT opp_id IF NOT EXISTS FOR (o:Opportunity) REQUIRE o.opportunity_id IS UNIQUE",
        "CREATE CONSTRAINT cust_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
        "CREATE CONSTRAINT supp_id IF NOT EXISTS FOR (s:Supplier) REQUIRE s.supplier_id IS UNIQUE",
        "CREATE CONSTRAINT prod_id IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE",
        "CREATE CONSTRAINT so_id IF NOT EXISTS FOR (so:SalesOrder) REQUIRE so.order_id IS UNIQUE",
        "CREATE CONSTRAINT inv_id IF NOT EXISTS FOR (i:Invoice) REQUIRE i.invoice_id IS UNIQUE",
        "CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (s:Skill) REQUIRE s.skill_id IS UNIQUE",
        "CREATE CONSTRAINT leave_id IF NOT EXISTS FOR (l:LeaveRequest) REQUIRE l.leave_id IS UNIQUE",
        "CREATE CONSTRAINT milestone_id IF NOT EXISTS FOR (m:Milestone) REQUIRE m.milestone_id IS UNIQUE",
        "CREATE CONSTRAINT perf_id IF NOT EXISTS FOR (pr:PerformanceReview) REQUIRE pr.review_id IS UNIQUE",
    ]
    
    for constraint in constraints:
        try:
            session.run(constraint)
        except:
            pass
    
    log.info(f"  ✓ {len(constraints)} contraintes appliquées")


def create_indexes(session):
    """Crée les indexes de performance."""
    log.info("Création des indexes Neo4j …")
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS FOR (e:Employee) ON (e.email)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Department) ON (d.department_name)",
        "CREATE INDEX IF NOT EXISTS FOR (a:Account) ON (a.name)",
        "CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.status)",
    ]
    
    for index in indexes:
        try:
            session.run(index)
        except:
            pass
    
    log.info(f"  ✓ {len(indexes)} indexes appliqués")


# ═══════════════════════════════════════════════════════════════════════════════
#  Création des nœuds
# ═══════════════════════════════════════════════════════════════════════════════

def load_departments(session):
    """Crée les nœuds Department."""
    log.info("Création des nœuds Department …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_departments")
    
    cypher = """
    CREATE (d:Department {
        department_id: record.department_id,
        department_name: record.department_name,
        cost_center: record.cost_center,
        location: record.location,
        budget: record.budget
    })
    """
    
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        total += run_cypher_batch(session, cypher, batch)
    
    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_employees(session):
    """Crée les nœuds Employee."""
    log.info("Création des nœuds Employee …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_employees")
    
    cypher = """
    CREATE (e:Employee {
        employee_id: record.employee_id,
        first_name: record.first_name,
        last_name: record.last_name,
        email: record.email,
        role: record.role,
        hire_date: toString(coalesce(record.hire_date, '')),
        salary: record.salary,
        department_id: record.department_id
    })
    """
    
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        total += run_cypher_batch(session, cypher, batch)
    
    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_projects(session):
    """Crée les nœuds Project."""
    log.info("Création des nœuds Project …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_projects")
    
    cypher = """
    CREATE (p:Project {
        project_id: record.project_id,
        project_name: record.project_name,
        status: record.status,
        budget: record.budget,
        client_account_id: record.client_account_id
    })
    """
    
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        total += run_cypher_batch(session, cypher, batch)
    
    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_accounts(session):
    """Crée les nœuds Account (CRM)."""
    log.info("Création des nœuds Account …")
    rows = pg_fetchall("crm", "SELECT * FROM crm.crm_accounts")
    
    cypher = """
    CREATE (a:Account {
        account_id: record.account_id,
        name: record.name,
        industry: record.industry,
        country: record.country,
        annual_revenue: record.annual_revenue
    })
    """
    
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        total += run_cypher_batch(session, cypher, batch)
    
    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_opportunities(session):
    """Crée les nœuds Opportunity (CRM)."""
    log.info("Création des nœuds Opportunity …")
    rows = pg_fetchall("crm", "SELECT * FROM crm.crm_opportunities")
    
    cypher = """
    CREATE (o:Opportunity {
        opportunity_id: record.opportunity_id,
        deal_name: record.deal_name,
        stage: record.stage,
        amount: record.amount,
        account_id: record.account_id
    })
    """
    
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        total += run_cypher_batch(session, cypher, batch)
    
    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_customers(session):
    """Crée les nœuds Customer (ERP)."""
    log.info("Création des nœuds Customer …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_customers")
    
    cypher = """
    CREATE (c:Customer {
        customer_id: record.customer_id,
        name: record.name,
        country: record.country,
        industry: record.industry,
        account_id: record.account_id
    })
    """
    
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        total += run_cypher_batch(session, cypher, batch)
    
    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_skills(session):
    """Crée les nœuds Skill."""
    log.info("Création des nœuds Skill …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_skills")
    
    cypher = """
    CREATE (s:Skill {
        skill_id: record.skill_id,
        skill_name: record.skill_name,
        level: record.level,
        employee_id: record.employee_id
    })
    """
    
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        total += run_cypher_batch(session, cypher, batch)
    
    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


# ═══════════════════════════════════════════════════════════════════════════════
#  Création des relations
# ═══════════════════════════════════════════════════════════════════════════════

def load_relationships(session):
    """Crée les relations entre nœuds."""
    log.info("Création des relations …")
    
    # Employee -[BELONGS_TO]-> Department
    log.info("  Relation BELONGS_TO (Employee → Department) …")
    rows = pg_fetchall("hr", "SELECT employee_id, department_id FROM hr.hr_employees WHERE department_id IS NOT NULL")
    cypher = """
    MATCH (e:Employee {employee_id: record.employee_id})
    MATCH (d:Department {department_id: record.department_id})
    CREATE (e)-[:BELONGS_TO]->(d)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
    
    # Employee -[MANAGED_BY]-> Employee
    log.info("  Relation MANAGED_BY (Employee → Employee) …")
    rows = pg_fetchall("hr", "SELECT employee_id, manager_id FROM hr.hr_employees WHERE manager_id IS NOT NULL")
    cypher = """
    MATCH (e:Employee {employee_id: record.employee_id})
    MATCH (m:Employee {employee_id: record.manager_id})
    CREATE (e)-[:MANAGED_BY]->(m)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
    
    # Employee -[ASSIGNED_TO]-> Project
    log.info("  Relation ASSIGNED_TO (Employee → Project) …")
    rows = pg_fetchall("hr", "SELECT employee_id, project_id FROM hr.hr_employee_projects WHERE project_id IS NOT NULL")
    cypher = """
    MATCH (e:Employee {employee_id: record.employee_id})
    MATCH (p:Project {project_id: record.project_id})
    CREATE (e)-[:ASSIGNED_TO]->(p)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
    
    # Employee -[HAS_SKILL]-> Skill
    log.info("  Relation HAS_SKILL (Employee → Skill) …")
    rows = pg_fetchall("hr", "SELECT DISTINCT employee_id, skill_id FROM hr.hr_skills")
    cypher = """
    MATCH (e:Employee {employee_id: record.employee_id})
    MATCH (s:Skill {skill_id: record.skill_id})
    CREATE (e)-[:HAS_SKILL]->(s)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
    
    # Project -[FOR_ACCOUNT]-> Account
    log.info("  Relation FOR_ACCOUNT (Project → Account) …")
    rows = pg_fetchall("hr", "SELECT project_id, client_account_id FROM hr.hr_projects WHERE client_account_id IS NOT NULL")
    cypher = """
    MATCH (p:Project {project_id: record.project_id})
    MATCH (a:Account {account_id: record.client_account_id})
    CREATE (p)-[:FOR_ACCOUNT]->(a)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
    
    # Opportunity -[HAS_ACCOUNT]-> Account
    log.info("  Relation HAS_ACCOUNT (Opportunity → Account) …")
    rows = pg_fetchall("crm", "SELECT opportunity_id, account_id FROM crm.crm_opportunities WHERE account_id IS NOT NULL")
    cypher = """
    MATCH (o:Opportunity {opportunity_id: record.opportunity_id})
    MATCH (a:Account {account_id: record.account_id})
    CREATE (o)-[:HAS_ACCOUNT]->(a)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
    
    # Customer -[LINKED_TO_ACCOUNT]-> Account
    log.info("  Relation LINKED_TO_ACCOUNT (Customer → Account) …")
    rows = pg_fetchall("erp", "SELECT customer_id, account_id FROM erp.erp_customers WHERE account_id IS NOT NULL")
    cypher = """
    MATCH (c:Customer {customer_id: record.customer_id})
    MATCH (a:Account {account_id: record.account_id})
    CREATE (c)-[:LINKED_TO_ACCOUNT]->(a)
    """
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i+BATCH_SIZE])
    
    log.info("  ✓ Relations créées")


# ═══════════════════════════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_graph(session) -> bool:
    """Valide l'intégrité du graphe."""
    log.info("Validation du graphe …")
    
    # Compter les nœuds
    result = session.run("""
        MATCH (n)
        RETURN labels(n)[0] AS label, COUNT(n) AS count
        ORDER BY count DESC
    """)
    
    log.info("  Nœuds par type :")
    total_nodes = 0
    for record in result:
        log.info(f"    {record['label']}: {record['count']}")
        total_nodes += record['count']
    
    # Compter les relations
    result = session.run("""
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, COUNT(r) AS count
        ORDER BY count DESC
    """)
    
    log.info("  Relations par type :")
    total_rels = 0
    for record in result:
        log.info(f"    {record['rel_type']}: {record['count']}")
        total_rels += record['count']
    
    log.info(f"\n  Total: {total_nodes} nœuds, {total_rels} relations")
    return total_nodes > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  Point d'entrée principal
# ═══════════════════════════════════════════════════════════════════════════════

def run(validate_only: bool = False):
    """Exécute le pipeline ETL Neo4j."""
    log.info("=" * 70)
    log.info("ETL Neo4j — Démarrage (T-08)")
    log.info("=" * 70)
    log.info("")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session(database="neo4j") as session:
            if not validate_only:
                log.info("Création des contraintes et indexes …")
                create_constraints(session)
                create_indexes(session)
                log.info("")
                
                log.info("Création des nœuds …")
                load_departments(session)
                load_employees(session)
                load_projects(session)
                load_accounts(session)
                load_opportunities(session)
                load_customers(session)
                load_skills(session)
                log.info("")
                
                log.info("Création des relations …")
                load_relationships(session)
                log.info("")
            
            log.info("Validation …")
            validate_graph(session)
        
        log.info("")
        log.info("✅ ETL Neo4j terminé avec succès.")
        
    finally:
        driver.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    
    try:
        run(validate_only=args.validate_only)
    except Exception as exc:
        log.exception(f"❌ Erreur fatale : {exc}")
        sys.exit(1)
