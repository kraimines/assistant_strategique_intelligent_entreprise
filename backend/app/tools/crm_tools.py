"""LangChain tools for the CRM domain — talan_crm PostgreSQL database.

All tools are synchronous and use a module-level SQLAlchemy engine so that
the connection pool is shared across calls within the same process.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# ── Module-level engine & session factory ─────────────────────────────────────
logger = logging.getLogger(__name__)

_engine = create_engine(
    settings.database_url("crm"),
    pool_pre_ping=True,
    connect_args={"options": "-csearch_path=crm,public"},
)
_Session = sessionmaker(bind=_engine)

# ── Valid enumerated values ────────────────────────────────────────────────────
_VALID_STAGES = {
    "Prospecting",
    "Qualification",
    "Proposal",
    "Negotiation",
    "Closed Won",
    "Closed Lost",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a SQLAlchemy Row to a JSON-serialisable plain dict."""
    result: Dict[str, Any] = {}
    mapping = row._mapping if hasattr(row, "_mapping") else dict(row)
    for key, value in mapping.items():
        if isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
        else:
            try:
                result[key] = float(value) if value is not None else None
            except (TypeError, ValueError):
                result[key] = value
    return result


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def search_account_by_name(name: str) -> List[Dict[str, Any]]:
    """Search CRM accounts by company name (partial match, case-insensitive).

    Use this tool when you have a company name (e.g. "Attijari Bank") but not
    the account_id. Returns matching accounts with their account_id so you can
    then call get_account_summary or get_contacts with the correct account_id.

    Args:
        name: Full or partial company name to search for (e.g. "Attijari", "BIAT", "Leoni").
    """
    t0 = time.perf_counter()
    try:
        sql = text(
            """
            SELECT account_id, name, industry, country, city, phone, website
            FROM crm.crm_accounts
            WHERE LOWER(name) LIKE LOWER(:term)
            ORDER BY name
            LIMIT 10
            """
        )
        with _Session() as session:
            rows = session.execute(sql, {"term": f"%{name}%"}).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("search_account_by_name('%s') — %d rows — %.1f ms", name, len(rows), elapsed)

        if not rows:
            return [{"error": f"No account found matching '{name}'"}]
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("search_account_by_name failed for name=%s", name)
        return [{"error": str(exc)}]


@tool
def get_account_summary(account_id: str) -> Dict[str, Any]:
    """Return a comprehensive commercial profile for a CRM account.

    Joins crm_accounts with:
      - crm_opportunities  (total number and sum of opportunity amounts)
      - crm_revenue_history (total recognised revenue over the last 12 months)

    Args:
        account_id: The unique CRM account identifier (e.g. "ACC0012").

    Returns a dict combining the account master data with commercial KPIs:
        - nb_opportunities  (int)
        - total_pipeline    (float)  — sum of all open opportunity amounts
        - revenue_12m       (float)  — total revenue recognised in last 12 months

    Returns {"error": "Account not found"} when no matching account exists.
    Returns {"error": "..."} on DB failure.
    """
    t0 = time.perf_counter()
    try:
        # ── Fetch account master data ────────────────────────────────────────
        account_sql = text(
            """
            SELECT *
            FROM crm.crm_accounts
            WHERE account_id = :account_id
            """
        )

        # ── Opportunity aggregates ───────────────────────────────────────────
        opp_sql = text(
            """
            SELECT
                COUNT(*)           AS nb_opportunities,
                COALESCE(SUM(amount), 0) AS total_pipeline
            FROM crm.crm_opportunities
            WHERE account_id = :account_id
            """
        )

        # ── Revenue last 12 months ───────────────────────────────────────────
        rev_sql = text(
            """
            SELECT COALESCE(SUM(revenue), 0) AS revenue_12m
            FROM crm.crm_revenue_history
            WHERE account_id = :account_id
              AND year_month >= TO_CHAR(NOW() - INTERVAL '12 months', 'YYYY-MM')
            """
        )

        with _Session() as session:
            account_row = session.execute(
                account_sql, {"account_id": account_id}
            ).fetchone()

            if account_row is None:
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info(
                    "get_account_summary(%s) not found — %.1f ms", account_id, elapsed
                )
                return {"error": "Account not found"}

            opp_row = session.execute(opp_sql, {"account_id": account_id}).fetchone()
            rev_row = session.execute(rev_sql, {"account_id": account_id}).fetchone()

        result = _row_to_dict(account_row)

        if opp_row is not None:
            result["nb_opportunities"] = int(opp_row._mapping["nb_opportunities"] or 0)
            result["total_pipeline"] = float(opp_row._mapping["total_pipeline"] or 0)

        if rev_row is not None:
            result["revenue_12m"] = float(rev_row._mapping["revenue_12m"] or 0)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("get_account_summary(%s) — %.1f ms", account_id, elapsed)
        return result

    except Exception as exc:
        logger.exception("get_account_summary failed for account_id=%s", account_id)
        return {"error": str(exc)}


@tool
def list_opportunities(
    account_id: Optional[str] = None,
    stage: Optional[str] = None,
    owner_id: Optional[str] = None,
    min_amount: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """List CRM opportunities with optional filters, ordered by close_date ascending.

    All filter parameters are optional — omitting them returns all opportunities
    (up to the 50-row safety cap).

    Valid stages: Prospecting, Qualification, Proposal, Negotiation,
                  Closed Won, Closed Lost.

    Args:
        account_id:  Filter by CRM account (optional).
        stage:       Filter by pipeline stage (optional).
        owner_id:    Filter by the owning sales representative (optional).
        min_amount:  Only return opportunities with amount >= this value (optional).

    Returns a list of opportunity dicts, at most 50 rows.
    Returns [{"error": "..."}] on validation failure or DB error.
    """
    t0 = time.perf_counter()

    if stage is not None and stage not in _VALID_STAGES:
        return [
            {
                "error": (
                    f"Invalid stage '{stage}'. "
                    f"Must be one of: {sorted(_VALID_STAGES)}"
                )
            }
        ]

    try:
        conditions: List[str] = []
        params: Dict[str, Any] = {"limit": 8}

        if account_id is not None:
            conditions.append("account_id = :account_id")
            params["account_id"] = account_id

        if stage is not None:
            conditions.append("stage = :stage")
            params["stage"] = stage

        if owner_id is not None:
            conditions.append("owner_id = :owner_id")
            params["owner_id"] = owner_id

        if min_amount is not None:
            conditions.append("amount >= :min_amount")
            params["min_amount"] = min_amount

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = text(
            f"""
            SELECT *
            FROM crm.crm_opportunities
            {where_clause}
            ORDER BY close_date ASC
            LIMIT :limit
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "list_opportunities(account=%s, stage=%s, owner=%s, min_amount=%s) "
            "— %d rows — %.1f ms",
            account_id, stage, owner_id, min_amount, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("list_opportunities failed")
        return [{"error": str(exc)}]


@tool
def get_revenue_history(
    account_id: str,
    months: int = 12,
) -> Dict[str, Any]:
    """Return the revenue history for a CRM account aggregated by period.

    Also computes a simple trend indicator by comparing the sum of the more
    recent half of periods against the older half.

    Args:
        account_id: The unique CRM account identifier.
        months:     How many months back to look (default 12, max clamped at 120).

    Returns a dict with keys:
        - account_id  (str)
        - months      (int)
        - periods     (list of {"period": str, "total": float})
        - total_revenue (float)
        - trend       ("up" | "down" | "stable") — based on first-half vs second-half sum
        - trend_detail (dict with first_half and second_half totals)

    Returns {"error": "..."} on DB failure.
    """
    t0 = time.perf_counter()
    # Safety clamp
    months = max(1, min(months, 120))

    try:
        sql = text(
            """
            SELECT
                year_month AS period,
                SUM(revenue) AS total
            FROM crm.crm_revenue_history
            WHERE account_id = :account_id
              AND year_month >= TO_CHAR(NOW() - CAST(:months_interval AS INTERVAL), 'YYYY-MM')
            GROUP BY year_month
            ORDER BY year_month ASC
            """
        )
        params = {
            "account_id": account_id,
            "months_interval": f"{months} months",
        }

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_revenue_history(%s, months=%d) — %d periods — %.1f ms",
            account_id, months, len(rows), elapsed,
        )

        periods = [
            {"period": r._mapping["period"], "total": float(r._mapping["total"] or 0)}
            for r in rows
        ]
        total_revenue = sum(p["total"] for p in periods)

        # ── Trend: compare older half vs newer half ──────────────────────────
        n = len(periods)
        if n >= 2:
            mid = n // 2
            first_half_sum = sum(p["total"] for p in periods[:mid])
            second_half_sum = sum(p["total"] for p in periods[mid:])
            if second_half_sum > first_half_sum * 1.05:
                trend = "up"
            elif second_half_sum < first_half_sum * 0.95:
                trend = "down"
            else:
                trend = "stable"
        else:
            first_half_sum = 0.0
            second_half_sum = total_revenue
            trend = "stable"

        return {
            "account_id": account_id,
            "months": months,
            "periods": periods,
            "total_revenue": total_revenue,
            "trend": trend,
            "trend_detail": {
                "first_half_total": first_half_sum,
                "second_half_total": second_half_sum,
            },
        }

    except Exception as exc:
        logger.exception("get_revenue_history failed for account_id=%s", account_id)
        return {"error": str(exc)}


@tool
def get_global_revenue_summary(months: int = 12) -> Dict[str, Any]:
    """Return the global revenue summary across ALL CRM accounts.

    Primary source: crm_revenue_history (all available history, no date cap).
    Fallback source: crm_opportunities WHERE stage = 'Closed Won', used when
    crm_revenue_history contains no data.

    Args:
        months: Kept for API compatibility — no longer used to filter history.
                Pass any value; the tool always returns the full available dataset.

    Returns a dict with:
        - total_revenue   (float)
        - data_source     ("revenue_history" | "closed_won_opportunities")
        - top_accounts    (list of {account_id, account_name, total} — top 5)
        - monthly_totals  (list of {period, total} — only for revenue_history source)
    """
    t0 = time.perf_counter()
    try:
        # ── Primary: aggregate all crm_revenue_history (no date filter) ─────────
        top_sql = text(
            """
            SELECT
                r.account_id,
                a.name AS account_name,
                SUM(r.revenue) AS total
            FROM crm.crm_revenue_history r
            LEFT JOIN crm.crm_accounts a ON a.account_id = r.account_id
            GROUP BY r.account_id, a.name
            ORDER BY total DESC
            LIMIT 5
            """
        )
        monthly_sql = text(
            """
            SELECT
                year_month AS period,
                SUM(revenue) AS total
            FROM crm.crm_revenue_history
            GROUP BY year_month
            ORDER BY year_month ASC
            """
        )

        # ── Fallback: sum Closed Won opportunities ────────────────────────────
        closed_won_sql = text(
            """
            SELECT
                o.account_id,
                a.name AS account_name,
                SUM(o.amount) AS total
            FROM crm.crm_opportunities o
            LEFT JOIN crm.crm_accounts a ON a.account_id = o.account_id
            WHERE o.stage = 'Closed Won'
            GROUP BY o.account_id, a.name
            ORDER BY total DESC
            LIMIT 5
            """
        )
        closed_won_total_sql = text(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM crm.crm_opportunities
            WHERE stage = 'Closed Won'
            """
        )

        with _Session() as session:
            top_rows    = session.execute(top_sql).fetchall()
            monthly_rows = session.execute(monthly_sql).fetchall()
            cw_rows     = session.execute(closed_won_sql).fetchall()
            cw_total_row = session.execute(closed_won_total_sql).fetchone()

        monthly_totals = [
            {"period": r._mapping["period"], "total": float(r._mapping["total"] or 0)}
            for r in monthly_rows
        ]
        revenue_history_total = sum(m["total"] for m in monthly_totals)

        closed_won_total = float(cw_total_row._mapping["total"] or 0) if cw_total_row else 0.0

        elapsed = (time.perf_counter() - t0) * 1000

        if revenue_history_total > 0:
            # Primary source has data — use it
            top_accounts = [
                {
                    "account_id":   r._mapping["account_id"],
                    "account_name": r._mapping["account_name"],
                    "total":        float(r._mapping["total"] or 0),
                }
                for r in top_rows
            ]
            logger.info(
                "get_global_revenue_summary — revenue_history total=%.2f — %.1f ms",
                revenue_history_total, elapsed,
            )
            return {
                "total_revenue": revenue_history_total,
                "data_source":   "revenue_history",
                "top_accounts":  top_accounts,
                "monthly_totals": monthly_totals,
            }

        # Fallback: crm_revenue_history is empty — use Closed Won opportunities
        logger.warning(
            "get_global_revenue_summary — revenue_history empty, "
            "falling back to closed_won_opportunities total=%.2f — %.1f ms",
            closed_won_total, elapsed,
        )
        cw_top_accounts = [
            {
                "account_id":   r._mapping["account_id"],
                "account_name": r._mapping["account_name"],
                "total":        float(r._mapping["total"] or 0),
            }
            for r in cw_rows
        ]
        return {
            "total_revenue": closed_won_total,
            "data_source":   "closed_won_opportunities",
            "top_accounts":  cw_top_accounts,
            "monthly_totals": [],
        }

    except Exception as exc:
        logger.exception("get_global_revenue_summary failed")
        return {"error": str(exc)}


@tool
def get_contacts(account_id: str) -> List[Dict[str, Any]]:
    """Return all contacts associated with a CRM account.

    Rows are ordered by last_activity_date descending so the most recently
    active contacts appear first.

    Args:
        account_id: The unique CRM account identifier.

    Returns a list of contact dicts.
    Returns [{"error": "..."}] on DB failure.
    """
    t0 = time.perf_counter()
    try:
        sql = text(
            """
            SELECT *
            FROM crm.crm_contacts
            WHERE account_id = :account_id
            ORDER BY created_at DESC
            """
        )

        with _Session() as session:
            rows = session.execute(sql, {"account_id": account_id}).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_contacts(%s) — %d rows — %.1f ms", account_id, len(rows), elapsed
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("get_contacts failed for account_id=%s", account_id)
        return [{"error": str(exc)}]


@tool
def list_recent_activities(
    opportunity_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return recent CRM activities linked to an opportunity and/or a contact.

    At least one of opportunity_id or contact_id must be provided; providing
    both returns activities matching either (OR logic).

    Args:
        opportunity_id: Filter by opportunity (optional).
        contact_id:     Filter by contact (optional).
        limit:          Maximum number of rows returned (default 10).

    Returns a list of activity dicts ordered by date descending.
    Returns [{"error": "..."}] when no filter is provided or on DB failure.
    """
    t0 = time.perf_counter()

    if opportunity_id is None and contact_id is None:
        return [
            {"error": "At least one of opportunity_id or contact_id must be provided."}
        ]

    try:
        conditions: List[str] = []
        params: Dict[str, Any] = {"limit": max(1, limit)}

        if opportunity_id is not None:
            conditions.append("opportunity_id = :opportunity_id")
            params["opportunity_id"] = opportunity_id

        if contact_id is not None:
            conditions.append("contact_id = :contact_id")
            params["contact_id"] = contact_id

        # Use OR when both filters are present
        where_clause = " OR ".join(conditions)
        sql = text(
            f"""
            SELECT *
            FROM crm.crm_activities
            WHERE ({where_clause})
            ORDER BY date DESC
            LIMIT :limit
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "list_recent_activities(opp=%s, contact=%s, limit=%d) "
            "— %d rows — %.1f ms",
            opportunity_id, contact_id, limit, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("list_recent_activities failed")
        return [{"error": str(exc)}]
