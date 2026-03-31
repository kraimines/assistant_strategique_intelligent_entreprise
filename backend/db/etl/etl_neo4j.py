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
        # CRM extended
        "CREATE CONSTRAINT contact_id    IF NOT EXISTS FOR (c:Contact)        REQUIRE c.contact_id    IS UNIQUE",
        "CREATE CONSTRAINT activity_id   IF NOT EXISTS FOR (a:Activity)       REQUIRE a.activity_id   IS UNIQUE",
        "CREATE CONSTRAINT revenue_id    IF NOT EXISTS FOR (r:RevenueHistory)  REQUIRE r.revenue_id    IS UNIQUE",
        # ERP extended
        "CREATE CONSTRAINT payment_id    IF NOT EXISTS FOR (p:Payment)        REQUIRE p.payment_id    IS UNIQUE",
        "CREATE CONSTRAINT po_id         IF NOT EXISTS FOR (p:PurchaseOrder)  REQUIRE p.po_id         IS UNIQUE",
        "CREATE CONSTRAINT inventory_id  IF NOT EXISTS FOR (i:Inventory)      REQUIRE i.inventory_id  IS UNIQUE",
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


def load_contacts(session):
    """Crée les nœuds Contact (CRM)."""
    log.info("Création des nœuds Contact …")
    rows = pg_fetchall("crm", "SELECT * FROM crm.crm_contacts")

    cypher = """
    CREATE (c:Contact {
        contact_id: record.contact_id,
        first_name:  record.first_name,
        last_name:   record.last_name,
        email:       record.email,
        phone:       record.phone,
        job_title:   record.job_title,
        country:     record.country,
        account_id:  record.account_id,
        created_at:  toString(coalesce(record.created_at, ''))
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_activities(session):
    """Crée les nœuds Activity (CRM)."""
    log.info("Création des nœuds Activity …")
    rows = pg_fetchall("crm", "SELECT * FROM crm.crm_activities")

    cypher = """
    CREATE (a:Activity {
        activity_id:      record.activity_id,
        type:             record.type,
        date:             toString(coalesce(record.date, '')),
        duration_minutes: record.duration_minutes,
        notes:            record.notes,
        contact_id:       record.contact_id,
        opportunity_id:   record.opportunity_id,
        created_by:       record.created_by
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_revenue_history(session):
    """Crée les nœuds RevenueHistory (CRM)."""
    log.info("Création des nœuds RevenueHistory …")
    rows = pg_fetchall("crm", "SELECT * FROM crm.crm_revenue_history")

    cypher = """
    CREATE (r:RevenueHistory {
        revenue_id:        record.revenue_id,
        account_id:        record.account_id,
        year_month:        record.year_month,
        revenue:           record.revenue,
        recurring_revenue: record.recurring_revenue,
        new_revenue:       record.new_revenue,
        currency:          record.currency,
        source:            record.source
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_payments(session):
    """Crée les nœuds Payment (ERP)."""
    log.info("Création des nœuds Payment …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_payments")

    cypher = """
    CREATE (p:Payment {
        payment_id:     record.payment_id,
        invoice_id:     record.invoice_id,
        payment_date:   toString(coalesce(record.payment_date, '')),
        amount:         record.amount,
        payment_method: record.payment_method,
        reference:      record.reference,
        currency:       record.currency,
        bank_account:   record.bank_account
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_purchase_orders(session):
    """Crée les nœuds PurchaseOrder (ERP)."""
    log.info("Création des nœuds PurchaseOrder …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_purchase_orders")

    cypher = """
    CREATE (po:PurchaseOrder {
        po_id:             record.po_id,
        supplier_id:       record.supplier_id,
        order_date:        toString(coalesce(record.order_date, '')),
        expected_delivery: toString(coalesce(record.expected_delivery, '')),
        amount:            record.amount,
        status:            record.status,
        approved_by:       record.approved_by,
        currency:          record.currency,
        warehouse:         record.warehouse
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_inventory(session):
    """Crée les nœuds Inventory (ERP)."""
    log.info("Création des nœuds Inventory …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_inventory")

    cypher = """
    CREATE (inv:Inventory {
        inventory_id:       record.inventory_id,
        product_id:         record.product_id,
        warehouse_location: record.warehouse_location,
        stock_quantity:     record.stock_quantity,
        reorder_level:      record.reorder_level,
        unit_cost:          record.unit_cost,
        last_updated:       toString(coalesce(record.last_updated, ''))
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_suppliers(session):
    """Crée les nœuds Supplier (ERP)."""
    log.info("Création des nœuds Supplier …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_suppliers")

    cypher = """
    CREATE (s:Supplier {
        supplier_id:    record.supplier_id,
        name:           record.name,
        country:        record.country,
        category:       record.category,
        contact_email:  record.contact_email,
        phone:          record.phone,
        rating:         record.rating,
        payment_terms:  record.payment_terms,
        created_at:     toString(coalesce(record.created_at, ''))
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_products(session):
    """Crée les nœuds Product (ERP)."""
    log.info("Création des nœuds Product …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_products")

    cypher = """
    CREATE (p:Product {
        product_id:      record.product_id,
        name:            record.name,
        category:        record.category,
        unit_price:      record.unit_price,
        currency:        record.currency,
        sku:             record.sku,
        supplier_id:     record.supplier_id,
        unit_of_measure: record.unit_of_measure,
        created_at:      toString(coalesce(record.created_at, ''))
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_sales_orders(session):
    """Crée les nœuds SalesOrder (ERP)."""
    log.info("Création des nœuds SalesOrder …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_sales_orders")

    cypher = """
    CREATE (so:SalesOrder {
        order_id:        record.order_id,
        customer_id:     record.customer_id,
        order_date:      toString(coalesce(record.order_date, '')),
        delivery_date:   toString(coalesce(record.delivery_date, '')),
        amount:          record.amount,
        status:          record.status,
        sales_rep_id:    record.sales_rep_id,
        currency:        record.currency,
        delivery_status: record.delivery_status
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_invoices(session):
    """Crée les nœuds Invoice (ERP)."""
    log.info("Création des nœuds Invoice …")
    rows = pg_fetchall("erp", "SELECT * FROM erp.erp_invoices")

    cypher = """
    CREATE (i:Invoice {
        invoice_id:     record.invoice_id,
        customer_id:    record.customer_id,
        order_id:       record.order_id,
        amount:         record.amount,
        tax_amount:     record.tax_amount,
        issue_date:     toString(coalesce(record.issue_date, '')),
        due_date:       toString(coalesce(record.due_date, '')),
        payment_status: record.payment_status,
        currency:       record.currency
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_leave_requests(session):
    """Crée les nœuds LeaveRequest (HR)."""
    log.info("Création des nœuds LeaveRequest …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_leave_requests")

    cypher = """
    CREATE (l:LeaveRequest {
        leave_id:       record.leave_id,
        employee_id:    record.employee_id,
        leave_type:     record.leave_type,
        start_date:     toString(coalesce(record.start_date, '')),
        end_date:       toString(coalesce(record.end_date, '')),
        days_requested: record.days_requested,
        status:         record.status,
        approved_by:    record.approved_by,
        request_date:   toString(coalesce(record.request_date, '')),
        notes:          record.notes
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_performance_reviews(session):
    """Crée les nœuds PerformanceReview (HR)."""
    log.info("Création des nœuds PerformanceReview …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_performance_reviews")

    cypher = """
    CREATE (pr:PerformanceReview {
        review_id:              record.review_id,
        employee_id:            record.employee_id,
        review_period:          record.review_period,
        overall_score:          record.overall_score,
        delivery_quality_score: record.delivery_quality_score,
        teamwork_score:         record.teamwork_score,
        innovation_score:       record.innovation_score,
        technical_skills_score: record.technical_skills_score,
        goals_achieved_pct:     record.goals_achieved_pct,
        promotion_eligible:     record.promotion_eligible,
        reviewer_id:            record.reviewer_id,
        review_date:            toString(coalesce(record.review_date, '')),
        comments:               record.comments
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_job_openings(session):
    """Crée les nœuds JobOpening (HR)."""
    log.info("Création des nœuds JobOpening …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_recruitment_pipeline")

    cypher = """
    CREATE (j:JobOpening {
        job_id:             record.job_id,
        role:               record.job_title,
        department_id:      record.department_id,
        status:             record.status,
        open_date:          toString(coalesce(record.open_date, '')),
        expected_hire_date: toString(coalesce(record.expected_hire_date, '')),
        salary_budget:      record.salary_budget,
        recruiter_id:       record.recruiter_id,
        priority:           record.priority
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


def load_milestones(session):
    """Crée les nœuds Milestone (HR/Cross-domain)."""
    log.info("Création des nœuds Milestone …")
    rows = pg_fetchall("hr", "SELECT * FROM hr.hr_project_milestones")

    cypher = """
    CREATE (m:Milestone {
        milestone_id:     record.milestone_id,
        project_id:       record.project_id,
        milestone_name:   record.milestone_name,
        due_date:         toString(coalesce(record.due_date, '')),
        completion_pct:   record.completion_pct,
        status:           record.status,
        owner_id:         record.owner_id,
        budget_allocated: record.budget_allocated,
        actual_cost:      record.actual_cost,
        notes:            record.notes
    })
    """

    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])

    log.info(f"  → {len(rows)} nœuds créés")
    return len(rows)


# ═══════════════════════════════════════════════════════════════════════════════
#  Création des relations
# ═══════════════════════════════════════════════════════════════════════════════

def _rel(session, label, sql_schema, sql, cypher):
    """Helper : charge une relation depuis PostgreSQL et l'insère en batch."""
    log.info(f"  Relation {label} …")
    rows = pg_fetchall(sql_schema, sql)
    for i in range(0, len(rows), BATCH_SIZE):
        run_cypher_batch(session, cypher, rows[i:i + BATCH_SIZE])
    log.info(f"    → {len(rows)} relations")
    return len(rows)


def load_relationships(session):
    """Crée TOUTES les relations entre nœuds (38 types)."""
    log.info("Création des relations …")

    # ── RH intra-domain ──────────────────────────────────────────────────────

    _rel(session, "BELONGS_TO (Employee→Department)", "hr",
         "SELECT employee_id, department_id FROM hr.hr_employees WHERE department_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.employee_id})"
         " MATCH (d:Department {department_id: record.department_id})"
         " MERGE (e)-[:BELONGS_TO]->(d)")

    _rel(session, "MANAGED_BY (Employee→Employee)", "hr",
         "SELECT employee_id, manager_id FROM hr.hr_employees WHERE manager_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.employee_id})"
         " MATCH (m:Employee {employee_id: record.manager_id})"
         " MERGE (e)-[:MANAGED_BY]->(m)")

    _rel(session, "HEADED_BY (Department→Employee)", "hr",
         "SELECT department_id, manager_id FROM hr.hr_departments WHERE manager_id IS NOT NULL",
         "MATCH (d:Department {department_id: record.department_id})"
         " MATCH (e:Employee {employee_id: record.manager_id})"
         " MERGE (d)-[:HEADED_BY]->(e)")

    _rel(session, "HAS_SKILL (Employee→Skill)", "hr",
         "SELECT DISTINCT employee_id, skill_id FROM hr.hr_skills",
         "MATCH (e:Employee {employee_id: record.employee_id})"
         " MATCH (s:Skill {skill_id: record.skill_id})"
         " MERGE (e)-[:HAS_SKILL]->(s)")

    _rel(session, "SUBMITTED_LEAVE (Employee→LeaveRequest)", "hr",
         "SELECT employee_id, leave_id FROM hr.hr_leave_requests",
         "MATCH (e:Employee {employee_id: record.employee_id})"
         " MATCH (l:LeaveRequest {leave_id: record.leave_id})"
         " MERGE (e)-[:SUBMITTED_LEAVE]->(l)")

    _rel(session, "APPROVED_LEAVE (Employee→LeaveRequest)", "hr",
         "SELECT approved_by, leave_id FROM hr.hr_leave_requests WHERE approved_by IS NOT NULL",
         "MATCH (mgr:Employee {employee_id: record.approved_by})"
         " MATCH (l:LeaveRequest {leave_id: record.leave_id})"
         " MERGE (mgr)-[:APPROVED_LEAVE]->(l)")

    _rel(session, "HAD_REVIEW (Employee→PerformanceReview)", "hr",
         "SELECT employee_id, review_id FROM hr.hr_performance_reviews",
         "MATCH (e:Employee {employee_id: record.employee_id})"
         " MATCH (pr:PerformanceReview {review_id: record.review_id})"
         " MERGE (e)-[:HAD_REVIEW]->(pr)")

    _rel(session, "REVIEWED_BY (PerformanceReview→Employee)", "hr",
         "SELECT review_id, reviewer_id FROM hr.hr_performance_reviews WHERE reviewer_id IS NOT NULL",
         "MATCH (pr:PerformanceReview {review_id: record.review_id})"
         " MATCH (rev:Employee {employee_id: record.reviewer_id})"
         " MERGE (pr)-[:REVIEWED_BY]->(rev)")

    _rel(session, "OPENS_POSITION (Department→JobOpening)", "hr",
         "SELECT department_id, job_id FROM hr.hr_recruitment_pipeline WHERE department_id IS NOT NULL",
         "MATCH (d:Department {department_id: record.department_id})"
         " MATCH (j:JobOpening {job_id: record.job_id})"
         " MERGE (d)-[:OPENS_POSITION]->(j)")

    _rel(session, "RECRUITS_FOR (Employee→JobOpening)", "hr",
         "SELECT recruiter_id, job_id FROM hr.hr_recruitment_pipeline WHERE recruiter_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.recruiter_id})"
         " MATCH (j:JobOpening {job_id: record.job_id})"
         " MERGE (e)-[:RECRUITS_FOR]->(j)")

    _rel(session, "ASSIGNED_TO (Employee→Project)", "hr",
         "SELECT employee_id, project_id FROM hr.hr_employee_projects WHERE project_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.employee_id})"
         " MATCH (p:Project {project_id: record.project_id})"
         " MERGE (e)-[:ASSIGNED_TO]->(p)")

    _rel(session, "MANAGES_PROJECT (Employee→Project)", "hr",
         "SELECT project_manager_id, project_id FROM hr.hr_projects WHERE project_manager_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.project_manager_id})"
         " MATCH (p:Project {project_id: record.project_id})"
         " MERGE (e)-[:MANAGES_PROJECT]->(p)")

    _rel(session, "BELONGS_TO_DEPT (Project→Department)", "hr",
         "SELECT project_id, department_id FROM hr.hr_projects WHERE department_id IS NOT NULL",
         "MATCH (p:Project {project_id: record.project_id})"
         " MATCH (d:Department {department_id: record.department_id})"
         " MERGE (p)-[:BELONGS_TO_DEPT]->(d)")

    _rel(session, "FOR_ACCOUNT (Project→Account)", "hr",
         "SELECT project_id, client_account_id FROM hr.hr_projects WHERE client_account_id IS NOT NULL",
         "MATCH (p:Project {project_id: record.project_id})"
         " MATCH (a:Account {account_id: record.client_account_id})"
         " MERGE (p)-[:FOR_ACCOUNT]->(a)")

    _rel(session, "HAS_MILESTONE (Project→Milestone)", "hr",
         "SELECT project_id, milestone_id FROM hr.hr_project_milestones",
         "MATCH (p:Project {project_id: record.project_id})"
         " MATCH (m:Milestone {milestone_id: record.milestone_id})"
         " MERGE (p)-[:HAS_MILESTONE]->(m)")

    _rel(session, "OWNS_MILESTONE (Employee→Milestone)", "hr",
         "SELECT owner_id, milestone_id FROM hr.hr_project_milestones WHERE owner_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.owner_id})"
         " MATCH (m:Milestone {milestone_id: record.milestone_id})"
         " MERGE (e)-[:OWNS_MILESTONE]->(m)")

    # LOGGED_TIME a des propriétés sur la relation — traitement séparé
    log.info("  Relation LOGGED_TIME (Employee→Project) …")
    ts_rows = pg_fetchall("hr",
        "SELECT employee_id, project_id, timesheet_id, actual_hours, planned_hours,"
        " overtime_hours, billable, week_start_date FROM hr.hr_timesheets")
    lt_cypher = """
    MATCH (e:Employee {employee_id: record.employee_id})
    MATCH (p:Project  {project_id:  record.project_id})
    MERGE (e)-[lt:LOGGED_TIME {timesheet_id: record.timesheet_id}]->(p)
    SET lt.actual_hours    = record.actual_hours,
        lt.planned_hours   = record.planned_hours,
        lt.overtime_hours  = record.overtime_hours,
        lt.billable        = record.billable,
        lt.week_start_date = toString(coalesce(record.week_start_date, ''))
    """
    for i in range(0, len(ts_rows), BATCH_SIZE):
        run_cypher_batch(session, lt_cypher, ts_rows[i:i + BATCH_SIZE])
    log.info(f"    → {len(ts_rows)} relations")

    # ── CRM intra-domain ─────────────────────────────────────────────────────

    _rel(session, "HAS_CONTACT (Account→Contact)", "crm",
         "SELECT account_id, contact_id FROM crm.crm_contacts WHERE account_id IS NOT NULL",
         "MATCH (a:Account {account_id: record.account_id})"
         " MATCH (c:Contact {contact_id: record.contact_id})"
         " MERGE (a)-[:HAS_CONTACT]->(c)")

    _rel(session, "HAS_OPPORTUNITY (Account→Opportunity)", "crm",
         "SELECT account_id, opportunity_id FROM crm.crm_opportunities WHERE account_id IS NOT NULL",
         "MATCH (a:Account {account_id: record.account_id})"
         " MATCH (o:Opportunity {opportunity_id: record.opportunity_id})"
         " MERGE (a)-[:HAS_OPPORTUNITY]->(o)")

    _rel(session, "OWNS_OPPORTUNITY (Employee→Opportunity)", "crm",
         "SELECT owner_id, opportunity_id FROM crm.crm_opportunities WHERE owner_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.owner_id})"
         " MATCH (o:Opportunity {opportunity_id: record.opportunity_id})"
         " MERGE (e)-[:OWNS_OPPORTUNITY]->(o)")

    _rel(session, "HAS_REVENUE (Account→RevenueHistory)", "crm",
         "SELECT account_id, revenue_id FROM crm.crm_revenue_history WHERE account_id IS NOT NULL",
         "MATCH (a:Account {account_id: record.account_id})"
         " MATCH (rv:RevenueHistory {revenue_id: record.revenue_id})"
         " MERGE (a)-[:HAS_REVENUE]->(rv)")

    _rel(session, "LOGGED_ACTIVITY (Employee→Activity)", "crm",
         "SELECT created_by, activity_id FROM crm.crm_activities WHERE created_by IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.created_by})"
         " MATCH (a:Activity {activity_id: record.activity_id})"
         " MERGE (e)-[:LOGGED_ACTIVITY]->(a)")

    _rel(session, "ACTIVITY_ON_CONTACT (Activity→Contact)", "crm",
         "SELECT activity_id, contact_id FROM crm.crm_activities WHERE contact_id IS NOT NULL",
         "MATCH (act:Activity {activity_id: record.activity_id})"
         " MATCH (c:Contact {contact_id: record.contact_id})"
         " MERGE (act)-[:ACTIVITY_ON_CONTACT]->(c)")

    _rel(session, "ACTIVITY_FOR_OPP (Activity→Opportunity)", "crm",
         "SELECT activity_id, opportunity_id FROM crm.crm_activities WHERE opportunity_id IS NOT NULL",
         "MATCH (act:Activity {activity_id: record.activity_id})"
         " MATCH (o:Opportunity {opportunity_id: record.opportunity_id})"
         " MERGE (act)-[:ACTIVITY_FOR_OPP]->(o)")

    # ── ERP intra-domain ─────────────────────────────────────────────────────

    _rel(session, "LINKED_TO_ACCOUNT (Customer→Account)", "erp",
         "SELECT customer_id, account_id FROM erp.erp_customers WHERE account_id IS NOT NULL",
         "MATCH (c:Customer {customer_id: record.customer_id})"
         " MATCH (a:Account {account_id: record.account_id})"
         " MERGE (c)-[:LINKED_TO_ACCOUNT]->(a)")

    _rel(session, "PLACED_ORDER (Customer→SalesOrder)", "erp",
         "SELECT customer_id, order_id FROM erp.erp_sales_orders WHERE customer_id IS NOT NULL",
         "MATCH (c:Customer {customer_id: record.customer_id})"
         " MATCH (so:SalesOrder {order_id: record.order_id})"
         " MERGE (c)-[:PLACED_ORDER]->(so)")

    _rel(session, "HANDLES_ORDER (Employee→SalesOrder)", "erp",
         "SELECT sales_rep_id, order_id FROM erp.erp_sales_orders WHERE sales_rep_id IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.sales_rep_id})"
         " MATCH (so:SalesOrder {order_id: record.order_id})"
         " MERGE (e)-[:HANDLES_ORDER]->(so)")

    _rel(session, "HAS_INVOICE (Customer→Invoice)", "erp",
         "SELECT customer_id, invoice_id FROM erp.erp_invoices WHERE customer_id IS NOT NULL",
         "MATCH (c:Customer {customer_id: record.customer_id})"
         " MATCH (i:Invoice {invoice_id: record.invoice_id})"
         " MERGE (c)-[:HAS_INVOICE]->(i)")

    _rel(session, "INVOICES_ORDER (Invoice→SalesOrder)", "erp",
         "SELECT invoice_id, order_id FROM erp.erp_invoices WHERE order_id IS NOT NULL",
         "MATCH (i:Invoice {invoice_id: record.invoice_id})"
         " MATCH (so:SalesOrder {order_id: record.order_id})"
         " MERGE (i)-[:INVOICES_ORDER]->(so)")

    _rel(session, "SETTLES (Payment→Invoice)", "erp",
         "SELECT payment_id, invoice_id FROM erp.erp_payments WHERE invoice_id IS NOT NULL",
         "MATCH (p:Payment {payment_id: record.payment_id})"
         " MATCH (i:Invoice {invoice_id: record.invoice_id})"
         " MERGE (p)-[:SETTLES]->(i)")

    _rel(session, "SUPPLIES (Supplier→Product)", "erp",
         "SELECT supplier_id, product_id FROM erp.erp_products WHERE supplier_id IS NOT NULL",
         "MATCH (s:Supplier {supplier_id: record.supplier_id})"
         " MATCH (p:Product {product_id: record.product_id})"
         " MERGE (s)-[:SUPPLIES]->(p)")

    _rel(session, "HAS_STOCK (Product→Inventory)", "erp",
         "SELECT product_id, inventory_id FROM erp.erp_inventory WHERE product_id IS NOT NULL",
         "MATCH (p:Product {product_id: record.product_id})"
         " MATCH (inv:Inventory {inventory_id: record.inventory_id})"
         " MERGE (p)-[:HAS_STOCK]->(inv)")

    _rel(session, "ORDERED_FROM (PurchaseOrder→Supplier)", "erp",
         "SELECT po_id, supplier_id FROM erp.erp_purchase_orders WHERE supplier_id IS NOT NULL",
         "MATCH (po:PurchaseOrder {po_id: record.po_id})"
         " MATCH (s:Supplier {supplier_id: record.supplier_id})"
         " MERGE (po)-[:ORDERED_FROM]->(s)")

    _rel(session, "APPROVED_PO (Employee→PurchaseOrder)", "erp",
         "SELECT approved_by, po_id FROM erp.erp_purchase_orders WHERE approved_by IS NOT NULL",
         "MATCH (e:Employee {employee_id: record.approved_by})"
         " MATCH (po:PurchaseOrder {po_id: record.po_id})"
         " MERGE (e)-[:APPROVED_PO]->(po)")

    # CONTAINS_PRODUCT et REQUESTS_PRODUCT ont des propriétés — traitement séparé
    log.info("  Relation CONTAINS_PRODUCT (SalesOrder→Product via order_lines) …")
    ol_rows = pg_fetchall("erp",
        "SELECT order_line_id, order_id, product_id, quantity, unit_price,"
        " discount_pct, line_total, currency FROM erp.erp_order_lines")
    ol_cypher = """
    MATCH (so:SalesOrder {order_id:   record.order_id})
    MATCH (p:Product     {product_id: record.product_id})
    MERGE (so)-[ol:CONTAINS_PRODUCT {order_line_id: record.order_line_id}]->(p)
    SET ol.quantity     = record.quantity,
        ol.unit_price   = record.unit_price,
        ol.discount_pct = record.discount_pct,
        ol.line_total   = record.line_total,
        ol.currency     = record.currency
    """
    for i in range(0, len(ol_rows), BATCH_SIZE):
        run_cypher_batch(session, ol_cypher, ol_rows[i:i + BATCH_SIZE])
    log.info(f"    → {len(ol_rows)} relations")

    log.info("  Relation REQUESTS_PRODUCT (PurchaseOrder→Product via po_lines) …")
    pol_rows = pg_fetchall("erp",
        "SELECT po_line_id, po_id, product_id, quantity_ordered, quantity_received,"
        " unit_cost, line_total, currency FROM erp.erp_po_lines")
    pol_cypher = """
    MATCH (po:PurchaseOrder {po_id:       record.po_id})
    MATCH (p:Product        {product_id:  record.product_id})
    MERGE (po)-[pol:REQUESTS_PRODUCT {po_line_id: record.po_line_id}]->(p)
    SET pol.quantity_ordered  = record.quantity_ordered,
        pol.quantity_received = record.quantity_received,
        pol.unit_cost         = record.unit_cost,
        pol.line_total        = record.line_total,
        pol.currency          = record.currency
    """
    for i in range(0, len(pol_rows), BATCH_SIZE):
        run_cypher_batch(session, pol_cypher, pol_rows[i:i + BATCH_SIZE])
    log.info(f"    → {len(pol_rows)} relations")

    log.info("  ✓ Toutes les relations créées")


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
                # ── HR ──────────────────────────────────────────────────────
                load_departments(session)
                load_employees(session)
                load_skills(session)
                load_leave_requests(session)
                load_performance_reviews(session)
                load_job_openings(session)
                # ── Cross-domain ────────────────────────────────────────────
                load_projects(session)
                load_milestones(session)
                # ── CRM ─────────────────────────────────────────────────────
                load_accounts(session)
                load_contacts(session)
                load_opportunities(session)
                load_activities(session)
                load_revenue_history(session)
                # ── ERP ─────────────────────────────────────────────────────
                load_customers(session)
                load_suppliers(session)
                load_products(session)
                load_sales_orders(session)
                load_invoices(session)
                load_payments(session)
                load_purchase_orders(session)
                load_inventory(session)
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
