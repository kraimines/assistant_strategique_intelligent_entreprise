"""World Model query service — domain-scoped Neo4j snapshot.

Fetches a lightweight, pre-built context snapshot from the Neo4j graph
for a given detected domain.  Used by world_model_node to inject graph
awareness into domain agent system prompts.

Design constraints
------------------
- Max latency : 3 seconds (asyncio.wait_for timeout guard)
- Never raises : all exceptions are caught; empty dict is the fallback
- Never blocks : Neo4j unavailability is fully graceful
- Read-only    : only MATCH queries (no MERGE / CREATE / SET)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from neo4j import AsyncGraphDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 3.0

# ── Domain-scoped Cypher queries ──────────────────────────────────────────────

_QUERY_HR = """\
MATCH (e:Employee)
OPTIONAL MATCH (e)-[:BELONGS_TO]->(d:Department)
OPTIONAL MATCH (e)-[:MANAGED_BY]->(m:Employee)
RETURN
    e.employee_id                          AS employee_id,
    (e.first_name + ' ' + e.last_name)    AS full_name,
    e.role                                 AS role,
    d.department_name                      AS department,
    (m.first_name + ' ' + m.last_name)    AS manager
ORDER BY d.department_name, e.last_name
LIMIT 50
"""

_QUERY_CRM = """\
MATCH (o:Opportunity)
WHERE o.stage IS NOT NULL
  AND NOT o.stage IN ['Closed Won', 'Closed Lost']
OPTIONAL MATCH (a:Account)-[:HAS_OPPORTUNITY]->(o)
OPTIONAL MATCH (emp:Employee)-[:OWNS_OPPORTUNITY]->(o)
RETURN
    o.opportunity_id                              AS opportunity_id,
    o.deal_name                                   AS deal_name,
    o.stage                                       AS stage,
    o.amount                                      AS amount,
    a.name                                        AS account,
    (emp.first_name + ' ' + emp.last_name)        AS owner
ORDER BY o.amount DESC
LIMIT 30
"""

_QUERY_ERP = """\
MATCH (c:Customer)-[:HAS_INVOICE]->(i:Invoice)
WHERE i.payment_status IN ['Unpaid', 'Overdue']
RETURN
    i.invoice_id      AS invoice_id,
    i.payment_status  AS payment_status,
    i.amount          AS amount,
    c.name            AS customer,
    c.customer_id     AS customer_id
ORDER BY i.payment_status DESC, i.amount DESC
LIMIT 30
"""

_QUERY_MULTI = """\
MATCH (p:Project)
WHERE p.status IN ['Active', 'Planning']
OPTIONAL MATCH (emp:Employee)-[:MANAGES_PROJECT]->(p)
RETURN
    p.project_id                                  AS project_id,
    p.project_name                                AS project_name,
    p.status                                      AS status,
    (emp.first_name + ' ' + emp.last_name)        AS project_manager
ORDER BY p.status, p.project_name
LIMIT 20
"""

_DOMAIN_QUERIES: Dict[str, str] = {
    "hr":    _QUERY_HR,
    "crm":   _QUERY_CRM,
    "erp":   _QUERY_ERP,
    "multi": _QUERY_MULTI,
}


# ── Driver factory ────────────────────────────────────────────────────────────

def _driver():
    """Create a transient Neo4j async driver (same pattern as neo4j_sync.py)."""
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


# ── Internal fetch ────────────────────────────────────────────────────────────

async def _fetch_snapshot(domain: str) -> Dict[str, Any]:
    """Execute the domain Cypher query and return structured records.

    Args:
        domain: One of "hr", "crm", "erp", "multi".

    Returns:
        Dict with keys "domain", "records", "count".

    Raises:
        Any neo4j or asyncio exception — caller must handle.
    """
    query = _DOMAIN_QUERIES.get(domain)
    if not query:
        logger.debug("_fetch_snapshot: no query for domain='%s' — returning {}", domain)
        return {}

    driver = _driver()
    try:
        async with driver.session() as session:
            result = await session.run(query)
            records = await result.data()
            return {"domain": domain, "records": records, "count": len(records)}
    finally:
        await driver.close()


# ── Public API ────────────────────────────────────────────────────────────────

async def get_world_model_snapshot(domain: str) -> Dict[str, Any]:
    """Fetch a domain-scoped Neo4j snapshot.  Never raises.  Max 3 seconds.

    Args:
        domain: Detected domain string — "hr" | "crm" | "erp" | "multi".
                Any other value returns {} immediately (e.g. "rag").

    Returns:
        Dict with keys:
          - "domain"  (str)
          - "records" (list[dict])
          - "count"   (int)
        Returns {} on timeout, Neo4j unavailability, or unknown domain.
    """
    try:
        return await asyncio.wait_for(
            _fetch_snapshot(domain),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "world_model_service: Neo4j query timed out after %.1fs for domain='%s'",
            _TIMEOUT_SECONDS,
            domain,
        )
        return {}
    except Exception as exc:
        logger.warning(
            "world_model_service: Neo4j unavailable for domain='%s' — %s",
            domain,
            exc,
        )
        return {}
