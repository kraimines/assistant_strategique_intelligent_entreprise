"""PostgreSQL → Neo4j nightly sync service.

Syncs core entities from the three PostgreSQL databases into the Neo4j graph.
All Cypher statements use MERGE (idempotent — safe to run repeatedly).

Nodes:    Employee, Department, Project, Account, Contact, Opportunity,
          Customer, Invoice, Supplier, Product, SalesOrder,
          Payment, PurchaseOrder, Inventory, RevenueHistory
Relations: BELONGS_TO, MANAGED_BY, HEADED_BY, HAS_SKILL, SUBMITTED_LEAVE,
           APPROVED_LEAVE, HAD_REVIEW, REVIEWED_BY, OPENS_POSITION,
           RECRUITS_FOR, ASSIGNED_TO, MANAGES_PROJECT, BELONGS_TO_DEPT,
           FOR_ACCOUNT, HAS_MILESTONE, OWNS_MILESTONE, LOGGED_TIME,
           HAS_CONTACT, HAS_OPPORTUNITY, OWNS_OPPORTUNITY, HAS_REVENUE,
           LOGGED_ACTIVITY, ACTIVITY_ON_CONTACT, ACTIVITY_FOR_OPP,
           LINKED_TO_ACCOUNT, PLACED_ORDER, HANDLES_ORDER, HAS_INVOICE,
           INVOICES_ORDER, SETTLES, SUPPLIES, HAS_STOCK,
           ORDERED_FROM, APPROVED_PO, CONTAINS_PRODUCT, REQUESTS_PRODUCT
"""
import logging
from typing import Any

from neo4j import AsyncGraphDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionCRM, SessionERP, SessionHR
from app.models.crm_models import Account, Contact, Opportunity
from app.models.erp_models import Customer, Invoice, Payment, Product, PurchaseOrder, SalesOrder, Supplier
from app.models.hr_models import Department, Employee, Project

logger = logging.getLogger(__name__)


# ── Driver factory ────────────────────────────────────────────────────────────

def _driver():
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _str(v: Any) -> str | None:
    return str(v) if v is not None else None


# ── Individual sync functions ─────────────────────────────────────────────────

async def _sync_departments(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Department))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (d:Department {department_id: r.department_id})
        SET d.name = r.name, d.location = r.location
        """,
        rows=[{"department_id": d.department_id, "name": d.department_name, "location": d.location} for d in rows],
    )
    return len(rows)


async def _sync_employees(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Employee))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (e:Employee {employee_id: r.employee_id})
        SET e.full_name  = r.full_name,
            e.email      = r.email,
            e.role       = r.role
        """,
        rows=[
            {
                "employee_id": e.employee_id,
                "full_name":   f"{e.first_name} {e.last_name}",
                "email":       e.email,
                "role":        e.role,
            }
            for e in rows
        ],
    )
    return len(rows)


async def _sync_projects(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Project))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (p:Project {project_id: r.project_id})
        SET p.name = r.name, p.status = r.status
        """,
        rows=[{"project_id": p.project_id, "name": p.project_name, "status": p.status} for p in rows],
    )
    return len(rows)


async def _sync_accounts(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Account))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (a:Account {account_id: r.account_id})
        SET a.name     = r.name,
            a.industry = r.industry,
            a.country  = r.country
        """,
        rows=[
            {"account_id": a.account_id, "name": a.name, "industry": a.industry, "country": a.country}
            for a in rows
        ],
    )
    return len(rows)


async def _sync_opportunities(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Opportunity))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (o:Opportunity {opportunity_id: r.opportunity_id})
        SET o.deal_name = r.deal_name,
            o.stage     = r.stage,
            o.amount    = r.amount
        """,
        rows=[
            {
                "opportunity_id": o.opportunity_id,
                "deal_name":      o.deal_name,
                "stage":          o.stage,
                "amount":         float(o.amount) if o.amount else None,
            }
            for o in rows
        ],
    )
    return len(rows)


# ── Relationship sync ─────────────────────────────────────────────────────────

async def _sync_works_in(db: AsyncSession, session) -> int:
    rows = (await db.execute(
        select(Employee.employee_id, Employee.department_id).where(Employee.department_id.isnot(None))
    )).all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MATCH (e:Employee {employee_id: r.employee_id})
        MATCH (d:Department {department_id: r.department_id})
        MERGE (e)-[:WORKS_IN]->(d)
        """,
        rows=[{"employee_id": r.employee_id, "department_id": r.department_id} for r in rows],
    )
    return len(rows)


async def _sync_reports_to(db: AsyncSession, session) -> int:
    rows = (await db.execute(
        select(Employee.employee_id, Employee.manager_id).where(Employee.manager_id.isnot(None))
    )).all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MATCH (e:Employee {employee_id: r.employee_id})
        MATCH (m:Employee {employee_id: r.manager_id})
        MERGE (e)-[:REPORTS_TO]->(m)
        """,
        rows=[{"employee_id": r.employee_id, "manager_id": r.manager_id} for r in rows],
    )
    return len(rows)


async def _sync_has_opportunity(db: AsyncSession, session) -> int:
    rows = (await db.execute(
        select(Opportunity.opportunity_id, Opportunity.account_id)
        .where(Opportunity.account_id.isnot(None))
    )).all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MATCH (a:Account {account_id: r.account_id})
        MATCH (o:Opportunity {opportunity_id: r.opportunity_id})
        MERGE (a)-[:HAS_OPPORTUNITY]->(o)
        """,
        rows=[{"account_id": r.account_id, "opportunity_id": r.opportunity_id} for r in rows],
    )
    return len(rows)


# ── CRM extended sync ─────────────────────────────────────────────────────────

async def _sync_contacts(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Contact))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (c:Contact {contact_id: r.contact_id})
        SET c.first_name = r.first_name,
            c.last_name  = r.last_name,
            c.email      = r.email,
            c.job_title  = r.job_title,
            c.account_id = r.account_id
        """,
        rows=[
            {
                "contact_id": c.contact_id,
                "first_name": c.first_name,
                "last_name":  c.last_name,
                "email":      c.email,
                "job_title":  c.job_title,
                "account_id": c.account_id,
            }
            for c in rows
        ],
    )
    return len(rows)


async def _sync_has_contact(db: AsyncSession, session) -> int:
    rows = (await db.execute(
        select(Contact.contact_id, Contact.account_id).where(Contact.account_id.isnot(None))
    )).all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MATCH (a:Account {account_id: r.account_id})
        MATCH (c:Contact {contact_id: r.contact_id})
        MERGE (a)-[:HAS_CONTACT]->(c)
        """,
        rows=[{"account_id": r.account_id, "contact_id": r.contact_id} for r in rows],
    )
    return len(rows)


async def _sync_owns_opportunity(db: AsyncSession, session) -> int:
    rows = (await db.execute(
        select(Opportunity.opportunity_id, Opportunity.owner_id)
        .where(Opportunity.owner_id.isnot(None))
    )).all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MATCH (e:Employee    {employee_id:    r.owner_id})
        MATCH (o:Opportunity {opportunity_id: r.opportunity_id})
        MERGE (e)-[:OWNS_OPPORTUNITY]->(o)
        """,
        rows=[{"owner_id": r.owner_id, "opportunity_id": r.opportunity_id} for r in rows],
    )
    return len(rows)


# ── ERP extended sync ─────────────────────────────────────────────────────────

async def _sync_customers(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Customer))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (c:Customer {customer_id: r.customer_id})
        SET c.name       = r.name,
            c.country    = r.country,
            c.industry   = r.industry,
            c.account_id = r.account_id
        """,
        rows=[
            {
                "customer_id": c.customer_id,
                "name":        c.name,
                "country":     c.country,
                "industry":    c.industry,
                "account_id":  c.account_id,
            }
            for c in rows
        ],
    )
    return len(rows)


async def _sync_suppliers(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Supplier))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (s:Supplier {supplier_id: r.supplier_id})
        SET s.name     = r.name,
            s.country  = r.country,
            s.category = r.category,
            s.rating   = r.rating
        """,
        rows=[
            {
                "supplier_id": s.supplier_id,
                "name":        s.name,
                "country":     s.country,
                "category":    s.category,
                "rating":      float(s.rating) if s.rating else None,
            }
            for s in rows
        ],
    )
    return len(rows)


async def _sync_products(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Product))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (p:Product {product_id: r.product_id})
        SET p.name        = r.name,
            p.category    = r.category,
            p.unit_price  = r.unit_price,
            p.sku         = r.sku,
            p.supplier_id = r.supplier_id
        """,
        rows=[
            {
                "product_id":  p.product_id,
                "name":        p.name,
                "category":    p.category,
                "unit_price":  float(p.unit_price) if p.unit_price else None,
                "sku":         p.sku,
                "supplier_id": p.supplier_id,
            }
            for p in rows
        ],
    )
    return len(rows)


async def _sync_sales_orders(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(SalesOrder))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (so:SalesOrder {order_id: r.order_id})
        SET so.status          = r.status,
            so.amount          = r.amount,
            so.customer_id     = r.customer_id,
            so.sales_rep_id    = r.sales_rep_id
        """,
        rows=[
            {
                "order_id":      o.order_id,
                "status":        o.status,
                "amount":        float(o.amount) if o.amount else None,
                "customer_id":   o.customer_id,
                "sales_rep_id":  o.sales_rep_id,
            }
            for o in rows
        ],
    )
    return len(rows)


async def _sync_invoices(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Invoice))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (i:Invoice {invoice_id: r.invoice_id})
        SET i.payment_status = r.payment_status,
            i.amount         = r.amount,
            i.customer_id    = r.customer_id,
            i.order_id       = r.order_id
        """,
        rows=[
            {
                "invoice_id":      i.invoice_id,
                "payment_status":  i.payment_status,
                "amount":          float(i.amount) if i.amount else None,
                "customer_id":     i.customer_id,
                "order_id":        i.order_id,
            }
            for i in rows
        ],
    )
    return len(rows)


async def _sync_payments(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(Payment))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (p:Payment {payment_id: r.payment_id})
        SET p.amount         = r.amount,
            p.payment_method = r.payment_method,
            p.invoice_id     = r.invoice_id
        """,
        rows=[
            {
                "payment_id":     p.payment_id,
                "amount":         float(p.amount) if p.amount else None,
                "payment_method": p.payment_method,
                "invoice_id":     p.invoice_id,
            }
            for p in rows
        ],
    )
    return len(rows)


async def _sync_purchase_orders(db: AsyncSession, session) -> int:
    rows = (await db.execute(select(PurchaseOrder))).scalars().all()
    if not rows:
        return 0
    await session.run(
        """
        UNWIND $rows AS r
        MERGE (po:PurchaseOrder {po_id: r.po_id})
        SET po.status      = r.status,
            po.amount      = r.amount,
            po.supplier_id = r.supplier_id,
            po.approved_by = r.approved_by
        """,
        rows=[
            {
                "po_id":       po.po_id,
                "status":      po.status,
                "amount":      float(po.amount) if po.amount else None,
                "supplier_id": po.supplier_id,
                "approved_by": po.approved_by,
            }
            for po in rows
        ],
    )
    return len(rows)


async def _sync_erp_relationships(db: AsyncSession, session) -> dict[str, int]:
    """Sync all ERP relationships in a single pass."""
    counts: dict[str, int] = {}

    # Customer → Account
    rows = (await db.execute(
        select(Customer.customer_id, Customer.account_id).where(Customer.account_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (c:Customer {customer_id: r.customer_id})"
            " MATCH (a:Account  {account_id:  r.account_id})"
            " MERGE (c)-[:LINKED_TO_ACCOUNT]->(a)",
            rows=[{"customer_id": r.customer_id, "account_id": r.account_id} for r in rows],
        )
    counts["rel_linked_to_account"] = len(rows)

    # Customer → SalesOrder
    rows = (await db.execute(
        select(SalesOrder.order_id, SalesOrder.customer_id).where(SalesOrder.customer_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (c:Customer   {customer_id: r.customer_id})"
            " MATCH (so:SalesOrder {order_id:   r.order_id})"
            " MERGE (c)-[:PLACED_ORDER]->(so)",
            rows=[{"customer_id": r.customer_id, "order_id": r.order_id} for r in rows],
        )
    counts["rel_placed_order"] = len(rows)

    # Employee → SalesOrder
    rows = (await db.execute(
        select(SalesOrder.order_id, SalesOrder.sales_rep_id).where(SalesOrder.sales_rep_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (e:Employee   {employee_id: r.sales_rep_id})"
            " MATCH (so:SalesOrder {order_id:   r.order_id})"
            " MERGE (e)-[:HANDLES_ORDER]->(so)",
            rows=[{"sales_rep_id": r.sales_rep_id, "order_id": r.order_id} for r in rows],
        )
    counts["rel_handles_order"] = len(rows)

    # Customer → Invoice
    rows = (await db.execute(
        select(Invoice.invoice_id, Invoice.customer_id).where(Invoice.customer_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (c:Customer {customer_id: r.customer_id})"
            " MATCH (i:Invoice  {invoice_id:  r.invoice_id})"
            " MERGE (c)-[:HAS_INVOICE]->(i)",
            rows=[{"customer_id": r.customer_id, "invoice_id": r.invoice_id} for r in rows],
        )
    counts["rel_has_invoice"] = len(rows)

    # Invoice → SalesOrder
    rows = (await db.execute(
        select(Invoice.invoice_id, Invoice.order_id).where(Invoice.order_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (i:Invoice    {invoice_id: r.invoice_id})"
            " MATCH (so:SalesOrder {order_id:  r.order_id})"
            " MERGE (i)-[:INVOICES_ORDER]->(so)",
            rows=[{"invoice_id": r.invoice_id, "order_id": r.order_id} for r in rows],
        )
    counts["rel_invoices_order"] = len(rows)

    # Payment → Invoice
    rows = (await db.execute(
        select(Payment.payment_id, Payment.invoice_id).where(Payment.invoice_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (p:Payment {payment_id: r.payment_id})"
            " MATCH (i:Invoice {invoice_id: r.invoice_id})"
            " MERGE (p)-[:SETTLES]->(i)",
            rows=[{"payment_id": r.payment_id, "invoice_id": r.invoice_id} for r in rows],
        )
    counts["rel_settles"] = len(rows)

    # Supplier → Product
    rows = (await db.execute(
        select(Product.product_id, Product.supplier_id).where(Product.supplier_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (s:Supplier {supplier_id: r.supplier_id})"
            " MATCH (p:Product  {product_id:  r.product_id})"
            " MERGE (s)-[:SUPPLIES]->(p)",
            rows=[{"supplier_id": r.supplier_id, "product_id": r.product_id} for r in rows],
        )
    counts["rel_supplies"] = len(rows)

    # PurchaseOrder → Supplier
    rows = (await db.execute(
        select(PurchaseOrder.po_id, PurchaseOrder.supplier_id).where(PurchaseOrder.supplier_id.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (po:PurchaseOrder {po_id:       r.po_id})"
            " MATCH (s:Supplier       {supplier_id: r.supplier_id})"
            " MERGE (po)-[:ORDERED_FROM]->(s)",
            rows=[{"po_id": r.po_id, "supplier_id": r.supplier_id} for r in rows],
        )
    counts["rel_ordered_from"] = len(rows)

    # Employee → PurchaseOrder (approved_by)
    rows = (await db.execute(
        select(PurchaseOrder.po_id, PurchaseOrder.approved_by).where(PurchaseOrder.approved_by.isnot(None))
    )).all()
    if rows:
        await session.run(
            "UNWIND $rows AS r"
            " MATCH (e:Employee      {employee_id: r.approved_by})"
            " MATCH (po:PurchaseOrder {po_id:      r.po_id})"
            " MERGE (e)-[:APPROVED_PO]->(po)",
            rows=[{"approved_by": r.approved_by, "po_id": r.po_id} for r in rows],
        )
    counts["rel_approved_po"] = len(rows)

    return counts


# ── Main entry point ──────────────────────────────────────────────────────────

async def sync_all() -> dict[str, int]:
    """
    Full PostgreSQL → Neo4j sync.
    Returns a dict of entity → count of records synced.
    Uses MERGE so it is fully idempotent.
    """
    counts: dict[str, int] = {}
    logger.info("Starting Neo4j sync…")

    driver = _driver()
    try:
        async with driver.session() as neo_session:
            # ── HR ────────────────────────────────────────────────────────────
            async with SessionHR() as hr_db:
                counts["departments"]    = await _sync_departments(hr_db, neo_session)
                counts["employees"]      = await _sync_employees(hr_db, neo_session)
                counts["projects"]       = await _sync_projects(hr_db, neo_session)
                counts["rel_works_in"]   = await _sync_works_in(hr_db, neo_session)
                counts["rel_reports_to"] = await _sync_reports_to(hr_db, neo_session)

            # ── CRM ───────────────────────────────────────────────────────────
            async with SessionCRM() as crm_db:
                counts["accounts"]          = await _sync_accounts(crm_db, neo_session)
                counts["contacts"]          = await _sync_contacts(crm_db, neo_session)
                counts["opportunities"]     = await _sync_opportunities(crm_db, neo_session)
                counts["rel_has_opp"]       = await _sync_has_opportunity(crm_db, neo_session)
                counts["rel_has_contact"]   = await _sync_has_contact(crm_db, neo_session)
                counts["rel_owns_opp"]      = await _sync_owns_opportunity(crm_db, neo_session)

            # ── ERP ───────────────────────────────────────────────────────────
            async with SessionERP() as erp_db:
                counts["customers"]       = await _sync_customers(erp_db, neo_session)
                counts["suppliers"]       = await _sync_suppliers(erp_db, neo_session)
                counts["products"]        = await _sync_products(erp_db, neo_session)
                counts["sales_orders"]    = await _sync_sales_orders(erp_db, neo_session)
                counts["invoices"]        = await _sync_invoices(erp_db, neo_session)
                counts["payments"]        = await _sync_payments(erp_db, neo_session)
                counts["purchase_orders"] = await _sync_purchase_orders(erp_db, neo_session)
                erp_rels = await _sync_erp_relationships(erp_db, neo_session)
                counts.update(erp_rels)
    finally:
        await driver.close()

    total = sum(counts.values())
    logger.info("Neo4j sync complete — %d records synced: %s", total, counts)
    return counts
