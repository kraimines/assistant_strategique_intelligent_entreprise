"""graph.py — Neo4j World Model API.

Exposes graph data (nodes + relationships) for the WorldModelExplorer frontend.
Five perspectives: org | crm | hr | erp | cross
Uses simple, fast Cypher queries with explicit LIMIT guards.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncGraphDatabase

from app.api.routes.auth import get_current_user
from app.core.config import settings
from app.models.user_models import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["graph"])

_TIMEOUT = 10.0  # seconds max per Neo4j call


# ── Driver factory ─────────────────────────────────────────────────────────────

def _driver():
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _node(id_val: Any, label: str, name: str, props: dict) -> dict:
    if id_val is None:
        return None
    return {
        "id":    str(id_val),
        "label": label,
        "name":  name or str(id_val),
        "props": {k: (v.iso_format() if hasattr(v, "iso_format") else v)
                  for k, v in props.items() if v is not None},
    }


def _link(src: Any, tgt: Any, rel_type: str) -> dict | None:
    if src is None or tgt is None:
        return None
    return {"source": str(src), "target": str(tgt), "type": rel_type}


def _build_graph(raw_nodes: list, raw_links: list) -> dict:
    """Deduplicate nodes and keep only links where both ends exist."""
    seen_ids: set = set()
    nodes = []
    for n in raw_nodes:
        if n and n.get("id") and n["id"] not in seen_ids:
            seen_ids.add(n["id"])
            nodes.append(n)

    links = []
    seen_links: set = set()
    for l in raw_links:
        if not l:
            continue
        src, tgt, t = l["source"], l["target"], l["type"]
        if src not in seen_ids or tgt not in seen_ids:
            continue
        key = f"{src}-{t}-{tgt}"
        if key not in seen_links:
            seen_links.add(key)
            links.append(l)

    return {"nodes": nodes, "links": links}


async def _run_query(cypher: str, **params) -> list:
    """Execute a Cypher query with a timeout guard. Returns list of records as dicts."""
    driver = _driver()
    try:
        async def _do():
            async with driver.session() as session:
                result = await session.run(cypher, **params)
                return await result.data()
        records = await asyncio.wait_for(_do(), timeout=_TIMEOUT)
        return records
    except asyncio.TimeoutError:
        logger.warning("Neo4j query timed out after %ss", _TIMEOUT)
        raise HTTPException(status_code=503, detail="Requête Neo4j trop lente (timeout 10s)")
    except Exception as exc:
        logger.warning("Neo4j error: %s", exc)
        raise HTTPException(status_code=503, detail=f"Neo4j: {exc}")
    finally:
        await driver.close()


# ── Perspective queries ────────────────────────────────────────────────────────

async def _get_org() -> dict:
    """Departments → Employees → Projects."""
    records = await _run_query("""
        MATCH (d:Department)
        OPTIONAL MATCH (d)<-[:BELONGS_TO]-(e:Employee)
        OPTIONAL MATCH (e)-[:MANAGES_PROJECT]->(p:Project)
        RETURN
            d.department_id AS dept_id, d.department_name AS dept_name,
            d.location AS dept_loc, d.budget AS dept_budget,
            e.employee_id AS emp_id,
            (e.first_name + ' ' + e.last_name) AS emp_name,
            e.role AS emp_role, e.contract_type AS emp_contract,
            p.project_id AS proj_id, p.project_name AS proj_name,
            p.status AS proj_status, p.budget AS proj_budget
        LIMIT 200
    """)

    raw_nodes, raw_links = [], []
    for r in records:
        raw_nodes.append(_node(r["dept_id"], "Department", r["dept_name"],
                               {"location": r["dept_loc"], "budget": r["dept_budget"]}))
        if r["emp_id"]:
            raw_nodes.append(_node(r["emp_id"], "Employee", r["emp_name"],
                                   {"role": r["emp_role"], "contract_type": r["emp_contract"]}))
            raw_links.append(_link(r["emp_id"], r["dept_id"], "BELONGS_TO"))
        if r["proj_id"]:
            raw_nodes.append(_node(r["proj_id"], "Project", r["proj_name"],
                                   {"status": r["proj_status"], "budget": r["proj_budget"]}))
            if r["emp_id"]:
                raw_links.append(_link(r["emp_id"], r["proj_id"], "MANAGES_PROJECT"))

    return _build_graph(raw_nodes, raw_links)


async def _get_crm() -> dict:
    """Accounts + Opportunities + Contacts + Employees — 4 separate queries, no cartesian product."""
    # 1. All accounts
    acc_records = await _run_query("""
        MATCH (a:Account)
        RETURN a.account_id AS acc_id, a.name AS acc_name,
               a.industry AS acc_industry, a.account_status AS acc_status
    """)
    # 2. All opportunities with their account
    opp_records = await _run_query("""
        MATCH (a:Account)-[:HAS_OPPORTUNITY]->(o:Opportunity)
        RETURN a.account_id AS acc_id,
               o.opportunity_id AS opp_id, o.deal_name AS opp_name,
               o.stage AS opp_stage, o.amount AS opp_amount
        LIMIT 500
    """)
    # 3. Contacts (sample per account)
    ct_records = await _run_query("""
        MATCH (a:Account)-[:HAS_CONTACT]->(ct:Contact)
        RETURN a.account_id AS acc_id,
               ct.contact_id AS ct_id,
               (ct.first_name + ' ' + ct.last_name) AS ct_name
        LIMIT 300
    """)
    # 4. Employees owning opportunities
    emp_records = await _run_query("""
        MATCH (e:Employee)-[:OWNS_OPPORTUNITY]->(o:Opportunity)
        RETURN e.employee_id AS emp_id,
               (e.first_name + ' ' + e.last_name) AS emp_name,
               e.role AS emp_role,
               o.opportunity_id AS opp_id
        LIMIT 300
    """)

    raw_nodes, raw_links = [], []

    for r in acc_records:
        raw_nodes.append(_node(r["acc_id"], "Account", r["acc_name"],
                               {"industry": r["acc_industry"], "status": r["acc_status"]}))

    for r in opp_records:
        raw_nodes.append(_node(r["opp_id"], "Opportunity", r["opp_name"],
                               {"stage": r["opp_stage"], "amount": r["opp_amount"]}))
        raw_links.append(_link(r["acc_id"], r["opp_id"], "HAS_OPPORTUNITY"))

    for r in ct_records:
        raw_nodes.append(_node(r["ct_id"], "Contact", r["ct_name"], {}))
        raw_links.append(_link(r["acc_id"], r["ct_id"], "HAS_CONTACT"))

    for r in emp_records:
        raw_nodes.append(_node(r["emp_id"], "Employee", r["emp_name"], {"role": r["emp_role"]}))
        raw_links.append(_link(r["emp_id"], r["opp_id"], "OWNS_OPPORTUNITY"))

    return _build_graph(raw_nodes, raw_links)


async def _get_hr() -> dict:
    """Departments → Employees → Skills (top skills only)."""
    records = await _run_query("""
        MATCH (d:Department)<-[:BELONGS_TO]-(e:Employee)
        OPTIONAL MATCH (e)-[:HAS_SKILL]->(s:Skill)
        RETURN
            d.department_id AS dept_id, d.department_name AS dept_name,
            d.location AS dept_loc,
            e.employee_id AS emp_id,
            (e.first_name + ' ' + e.last_name) AS emp_name,
            e.role AS emp_role, e.salary AS emp_salary,
            s.skill_id AS sk_id, s.skill_name AS sk_name,
            s.level AS sk_level
        LIMIT 300
    """)

    raw_nodes, raw_links = [], []
    for r in records:
        raw_nodes.append(_node(r["dept_id"], "Department", r["dept_name"],
                               {"location": r["dept_loc"]}))
        if r["emp_id"]:
            raw_nodes.append(_node(r["emp_id"], "Employee", r["emp_name"],
                                   {"role": r["emp_role"], "salary": r["emp_salary"]}))
            raw_links.append(_link(r["emp_id"], r["dept_id"], "BELONGS_TO"))
        if r["sk_id"]:
            raw_nodes.append(_node(r["sk_id"], "Skill", r["sk_name"],
                                   {"level": r["sk_level"]}))
            raw_links.append(_link(r["emp_id"], r["sk_id"], "HAS_SKILL"))

    return _build_graph(raw_nodes, raw_links)


async def _get_erp() -> dict:
    """Customers → Invoices (unpaid/overdue focus) + Suppliers."""
    records = await _run_query("""
        MATCH (c:Customer)-[:HAS_INVOICE]->(i:Invoice)
        WHERE i.payment_status IN ['Unpaid', 'Overdue', 'Partially Paid']
        RETURN
            c.customer_id AS cust_id, c.name AS cust_name, c.country AS cust_country,
            i.invoice_id AS inv_id, i.payment_status AS inv_status,
            i.amount AS inv_amount
        LIMIT 150
    """)

    sup_records = await _run_query("""
        MATCH (sup:Supplier)
        OPTIONAL MATCH (sup)-[:SUPPLIES]->(pr:Product)
        RETURN
            sup.supplier_id AS sup_id, sup.name AS sup_name, sup.country AS sup_country,
            pr.product_id AS pr_id, pr.product_name AS pr_name, pr.category AS pr_cat
        LIMIT 80
    """)

    raw_nodes, raw_links = [], []
    for r in records:
        raw_nodes.append(_node(r["cust_id"], "Customer", r["cust_name"],
                               {"country": r["cust_country"]}))
        raw_nodes.append(_node(r["inv_id"], "Invoice", f"INV-{r['inv_id']}",
                               {"payment_status": r["inv_status"], "amount": r["inv_amount"]}))
        raw_links.append(_link(r["cust_id"], r["inv_id"], "HAS_INVOICE"))

    for r in sup_records:
        raw_nodes.append(_node(r["sup_id"], "Supplier", r["sup_name"],
                               {"country": r["sup_country"]}))
        if r["pr_id"]:
            raw_nodes.append(_node(r["pr_id"], "Product", r["pr_name"],
                                   {"category": r["pr_cat"]}))
            raw_links.append(_link(r["sup_id"], r["pr_id"], "SUPPLIES"))

    return _build_graph(raw_nodes, raw_links)


async def _get_cross() -> dict:
    """Employee ↔ Project ↔ Account ↔ Customer cross-domain view."""
    proj_records = await _run_query("""
        MATCH (e:Employee)-[:MANAGES_PROJECT]->(p:Project)
        WHERE p.status IN ['Active', 'Planning']
        RETURN
            e.employee_id AS emp_id,
            (e.first_name + ' ' + e.last_name) AS emp_name,
            e.role AS emp_role, e.department_id AS emp_dept,
            p.project_id AS proj_id, p.project_name AS proj_name,
            p.status AS proj_status
        LIMIT 100
    """)

    crm_records = await _run_query("""
        MATCH (e:Employee)-[:OWNS_OPPORTUNITY]->(o:Opportunity)<-[:HAS_OPPORTUNITY]-(a:Account)
        WHERE o.stage NOT IN ['Closed Lost']
        RETURN
            e.employee_id AS emp_id,
            (e.first_name + ' ' + e.last_name) AS emp_name,
            e.role AS emp_role,
            o.opportunity_id AS opp_id, o.deal_name AS opp_name,
            o.stage AS opp_stage, o.amount AS opp_amount,
            a.account_id AS acc_id, a.name AS acc_name
        LIMIT 100
    """)

    raw_nodes, raw_links = [], []
    for r in proj_records:
        raw_nodes.append(_node(r["emp_id"], "Employee", r["emp_name"],
                               {"role": r["emp_role"]}))
        raw_nodes.append(_node(r["proj_id"], "Project", r["proj_name"],
                               {"status": r["proj_status"]}))
        raw_links.append(_link(r["emp_id"], r["proj_id"], "MANAGES_PROJECT"))

    for r in crm_records:
        raw_nodes.append(_node(r["emp_id"], "Employee", r["emp_name"],
                               {"role": r["emp_role"]}))
        raw_nodes.append(_node(r["opp_id"], "Opportunity", r["opp_name"],
                               {"stage": r["opp_stage"], "amount": r["opp_amount"]}))
        raw_nodes.append(_node(r["acc_id"], "Account", r["acc_name"], {}))
        raw_links.append(_link(r["emp_id"], r["opp_id"], "OWNS_OPPORTUNITY"))
        raw_links.append(_link(r["acc_id"], r["opp_id"], "HAS_OPPORTUNITY"))

    return _build_graph(raw_nodes, raw_links)


_PERSPECTIVE_FNS = {
    "org":   _get_org,
    "crm":   _get_crm,
    "hr":    _get_hr,
    "erp":   _get_erp,
    "cross": _get_cross,
}


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/world")
async def get_world_graph(
    view: str = Query("org", pattern="^(org|crm|hr|erp|cross)$"),
    current_user: User = Depends(get_current_user),
):
    """Return nodes + relationships for the selected perspective."""
    fn = _PERSPECTIVE_FNS[view]
    return await fn()


@router.get("/timeline")
async def get_timeline(
    current_user: User = Depends(get_current_user),
):
    """Return major recent events from Neo4j."""
    records = await _run_query("""
        CALL {
            MATCH (e:Employee) WHERE e.hire_date IS NOT NULL
            RETURN 'hire' AS event_type,
                   toString(e.hire_date) AS date,
                   ('Recrutement: ' + e.first_name + ' ' + e.last_name) AS description,
                   e.employee_id AS entity_id, 'Employee' AS entity_label
            ORDER BY e.hire_date DESC LIMIT 5

            UNION ALL

            MATCH (o:Opportunity) WHERE o.stage = 'Closed Won' AND o.close_date IS NOT NULL
            RETURN 'deal_won' AS event_type,
                   toString(o.close_date) AS date,
                   ('Deal gagné: ' + o.deal_name) AS description,
                   o.opportunity_id AS entity_id, 'Opportunity' AS entity_label
            ORDER BY o.close_date DESC LIMIT 5

            UNION ALL

            MATCH (i:Invoice) WHERE i.payment_status = 'Overdue' AND i.due_date IS NOT NULL
            RETURN 'overdue' AS event_type,
                   toString(i.due_date) AS date,
                   ('Facture impayée: ' + i.invoice_id) AS description,
                   i.invoice_id AS entity_id, 'Invoice' AS entity_label
            ORDER BY i.due_date DESC LIMIT 5

            UNION ALL

            MATCH (p:Project) WHERE p.status = 'Active' AND p.start_date IS NOT NULL
            RETURN 'project_start' AS event_type,
                   toString(p.start_date) AS date,
                   ('Projet actif: ' + p.project_name) AS description,
                   p.project_id AS entity_id, 'Project' AS entity_label
            ORDER BY p.start_date DESC LIMIT 5
        }
        RETURN event_type, date, description, entity_id, entity_label
        ORDER BY date DESC
        LIMIT 20
    """)

    events = [dict(r) for r in records if r.get("date")]
    return {"events": events}


@router.get("/search")
async def search_nodes(
    q: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
):
    """Full-text search across main node types."""
    records = await _run_query("""
        CALL {
            MATCH (e:Employee)
            WHERE toLower(e.first_name + ' ' + e.last_name) CONTAINS toLower($q)
               OR toLower(coalesce(e.role,'')) CONTAINS toLower($q)
            RETURN e.employee_id AS id, 'Employee' AS label,
                   (e.first_name + ' ' + e.last_name) AS name,
                   e.role AS detail LIMIT 8

            UNION

            MATCH (d:Department)
            WHERE toLower(coalesce(d.department_name,'')) CONTAINS toLower($q)
            RETURN d.department_id AS id, 'Department' AS label,
                   d.department_name AS name, d.location AS detail LIMIT 5

            UNION

            MATCH (p:Project)
            WHERE toLower(coalesce(p.project_name,'')) CONTAINS toLower($q)
            RETURN p.project_id AS id, 'Project' AS label,
                   p.project_name AS name, p.status AS detail LIMIT 5

            UNION

            MATCH (a:Account)
            WHERE toLower(coalesce(a.name,'')) CONTAINS toLower($q)
            RETURN a.account_id AS id, 'Account' AS label,
                   a.name AS name, a.industry AS detail LIMIT 5

            UNION

            MATCH (o:Opportunity)
            WHERE toLower(coalesce(o.deal_name,'')) CONTAINS toLower($q)
            RETURN o.opportunity_id AS id, 'Opportunity' AS label,
                   o.deal_name AS name, o.stage AS detail LIMIT 5
        }
        RETURN id, label, name, detail
        LIMIT 20
    """, q=q)

    return {
        "results": [
            {"id": str(r["id"]), "label": r["label"],
             "name": r["name"], "props": {"detail": r.get("detail")}}
            for r in records if r.get("id")
        ]
    }


@router.get("/node/{node_id}")
async def get_node_detail(
    node_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return full properties + direct neighbours for a given node id."""
    records = await _run_query("""
        MATCH (n)
        WHERE n.employee_id = $nid OR n.department_id = $nid OR n.project_id = $nid
           OR n.opportunity_id = $nid OR n.account_id = $nid OR n.contact_id = $nid
           OR n.customer_id = $nid OR n.invoice_id = $nid OR n.supplier_id = $nid
           OR n.skill_id = $nid OR n.order_id = $nid OR n.product_id = $nid
        WITH n LIMIT 1
        OPTIONAL MATCH (n)-[r]-(nb)
        RETURN
            labels(n)[0] AS label,
            properties(n) AS props,
            type(r) AS rel_type,
            CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END AS direction,
            labels(nb)[0] AS nb_label,
            coalesce(
                nb.department_name, nb.deal_name, nb.project_name,
                nb.name, nb.product_name, nb.skill_name,
                nb.first_name + ' ' + nb.last_name,
                toString(id(nb))
            ) AS nb_name
        LIMIT 50
    """, nid=node_id)

    if not records:
        raise HTTPException(status_code=404, detail="Node not found")

    first = records[0]
    raw_props = dict(first["props"] or {})
    props = {}
    for k, v in raw_props.items():
        if hasattr(v, "iso_format"):
            props[k] = v.iso_format()
        else:
            props[k] = v

    relations = [
        {"type": r["rel_type"], "direction": r["direction"],
         "label": r["nb_label"], "name": r["nb_name"]}
        for r in records
        if r.get("rel_type") and r.get("nb_label")
    ]

    return {
        "label": first["label"],
        "props": props,
        "relations": relations,
    }
