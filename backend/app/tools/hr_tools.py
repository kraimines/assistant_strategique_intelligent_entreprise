"""LangChain tools for the HR domain — talan_hr PostgreSQL database.

All tools are synchronous and use a module-level SQLAlchemy engine so that
the connection pool is shared across calls within the same process.
"""

from __future__ import annotations

import logging
import re
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
    settings.database_url("hr"),
    pool_pre_ping=True,
    connect_args={"options": "-csearch_path=hr,public"},
)
_Session = sessionmaker(bind=_engine)

# ── Valid enumerated values ────────────────────────────────────────────────────
_VALID_LEAVE_TYPES = {
    "Annual Leave",
    "Sick Leave",
    "Unpaid Leave",
    "Maternity/Paternity Leave",
    "Training Leave",
}

_ANNUAL_LEAVE_ALLOWANCE = 30  # days per year


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a SQLAlchemy Row or RowMapping to a plain Python dict,
    casting non-JSON-serialisable types (date, Decimal …) to str/float."""
    result: Dict[str, Any] = {}
    mapping = row._mapping if hasattr(row, "_mapping") else dict(row)
    for key, value in mapping.items():
        if isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
        else:
            # Decimal → float so the dict is JSON-serialisable by default
            try:
                result[key] = float(value) if value is not None else None
            except (TypeError, ValueError):
                result[key] = value
    return result


def _business_days(start: date, end: date) -> int:
    """Return the number of weekdays (Mon–Fri) between start and end inclusive."""
    if end < start:
        return 0
    total = 0
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Mon … 4=Fri
            total += 1
        from datetime import timedelta
        current += timedelta(days=1)
    return total


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_employee_info(employee_id: str) -> Dict[str, Any]:
    """Retrieve the full profile of an HR employee by their employee_id.

    Returns a dictionary with fields: employee_id, first_name, last_name,
    role, department_id, hire_date, salary, manager_id, contract_type, city,
    hourly_cost, capacity_hours_per_week.

    Returns {"error": "Employee not found"} when no matching record exists.

    Args:
        employee_id: The unique identifier of the employee (e.g. "EMP0042").
    """
    t0 = time.perf_counter()
    try:
        sql = text(
            """
            SELECT
                employee_id, first_name, last_name, role,
                department_id, hire_date, salary, manager_id,
                contract_type, city, hourly_cost, capacity_hours_per_week
            FROM hr.hr_employees
            WHERE employee_id = :employee_id
            """
        )
        with _Session() as session:
            row = session.execute(sql, {"employee_id": employee_id}).fetchone()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("get_employee_info(%s) — %.1f ms", employee_id, elapsed)

        if row is None:
            return {"error": "Employee not found"}
        return _row_to_dict(row)

    except Exception as exc:
        logger.exception("get_employee_info failed for employee_id=%s", employee_id)
        return {"error": str(exc)}


@tool
def get_leave_balance(
    employee_id: str,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Return the leave consumption summary and remaining balance for an employee.

    Queries approved leave requests grouped by leave_type for the given year
    (defaults to the current calendar year).

    Returns a dict with keys:
        - employee_id (str)
        - year (int)
        - leave_consumed (dict mapping leave_type -> days consumed)
        - annual_allowance (int) — fixed at 30 days
        - remaining_annual (int) — allowance minus consumed Annual Leave days

    Args:
        employee_id: The unique identifier of the employee.
        year:        The calendar year to query (default: current year).
    """
    t0 = time.perf_counter()
    if year is None:
        year = date.today().year

    try:
        sql = text(
            """
            SELECT
                leave_type,
                SUM(days_requested) AS days_consumed
            FROM hr.hr_leave_requests
            WHERE employee_id = :employee_id
              AND status       = 'Approved'
              AND EXTRACT(YEAR FROM start_date::date) = :year
            GROUP BY leave_type
            """
        )
        with _Session() as session:
            rows = session.execute(
                sql, {"employee_id": employee_id, "year": year}
            ).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_leave_balance(%s, %d) — %.1f ms", employee_id, year, elapsed
        )

        leave_consumed: Dict[str, int] = {}
        for row in rows:
            lt = row._mapping["leave_type"] or "Unknown"
            days = int(row._mapping["days_consumed"] or 0)
            leave_consumed[lt] = days

        annual_consumed = leave_consumed.get("Annual Leave", 0)
        remaining = _ANNUAL_LEAVE_ALLOWANCE - annual_consumed

        return {
            "employee_id": employee_id,
            "year": year,
            "leave_consumed": leave_consumed,
            "annual_allowance": _ANNUAL_LEAVE_ALLOWANCE,
            "remaining_annual": remaining,
        }

    except Exception as exc:
        logger.exception(
            "get_leave_balance failed for employee_id=%s year=%s", employee_id, year
        )
        return {"error": str(exc)}


@tool
def create_leave_request(
    employee_id: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    notes: str = "",
) -> Dict[str, Any]:
    """Submit a new leave request on behalf of an employee.

    Performs idempotency check: if a Pending request for the same employee,
    dates and leave_type already exists, returns the existing record instead
    of inserting a duplicate.

    Business days (Mon–Fri) are counted between start_date and end_date
    inclusive to compute days_requested.

    The generated leave_id follows the pattern "LVExxxx" (e.g. "LVE0043").

    Args:
        employee_id: Unique identifier of the requesting employee.
        leave_type:  One of: Annual Leave, Sick Leave, Unpaid Leave,
                     Maternity/Paternity Leave, Training Leave.
        start_date:  ISO-8601 date string (YYYY-MM-DD).
        end_date:    ISO-8601 date string (YYYY-MM-DD).
        notes:       Optional free-text justification.

    Returns a dict with keys: leave_id, days_requested, status, message.
    Returns {"error": "..."} on validation failure or DB error.
    """
    t0 = time.perf_counter()

    # ── Validate leave_type ──────────────────────────────────────────────────
    if leave_type not in _VALID_LEAVE_TYPES:
        return {
            "error": (
                f"Invalid leave_type '{leave_type}'. "
                f"Must be one of: {sorted(_VALID_LEAVE_TYPES)}"
            )
        }

    # ── Parse dates ──────────────────────────────────────────────────────────
    try:
        d_start = date.fromisoformat(start_date)
        d_end = date.fromisoformat(end_date)
    except ValueError as exc:
        return {"error": f"Invalid date format: {exc}"}

    if d_end < d_start:
        return {"error": "end_date must be >= start_date"}

    days_requested = _business_days(d_start, d_end)
    if days_requested == 0:
        return {"error": "The requested period contains no business days (Mon–Fri)."}

    try:
        with _Session() as session:
            # ── Idempotency check ────────────────────────────────────────────
            check_sql = text(
                """
                SELECT leave_id
                FROM hr.hr_leave_requests
                WHERE employee_id = :employee_id
                  AND leave_type  = :leave_type
                  AND start_date  = :start_date
                  AND end_date    = :end_date
                  AND status      = 'Pending'
                LIMIT 1
                """
            )
            existing = session.execute(
                check_sql,
                {
                    "employee_id": employee_id,
                    "leave_type": leave_type,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).fetchone()

            if existing is not None:
                existing_id = existing._mapping["leave_id"]
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info(
                    "create_leave_request idempotent hit — %s — %.1f ms",
                    existing_id,
                    elapsed,
                )
                return {
                    "leave_id": existing_id,
                    "days_requested": days_requested,
                    "status": "Pending",
                    "message": "Duplicate request — an identical Pending request already exists.",
                }

            # ── Generate next leave_id ───────────────────────────────────────
            max_sql = text(
                "SELECT MAX(leave_id) AS max_id FROM hr.hr_leave_requests"
            )
            max_row = session.execute(max_sql).fetchone()
            max_val: str = max_row._mapping["max_id"] or "LVE0000"

            # Extract trailing digits from any "LVExxxx" style id
            match = re.search(r"(\d+)$", max_val)
            next_num = (int(match.group(1)) + 1) if match else 1
            new_leave_id = "LVE" + str(next_num).zfill(4)

            # ── INSERT ───────────────────────────────────────────────────────
            insert_sql = text(
                """
                INSERT INTO hr.hr_leave_requests
                    (leave_id, employee_id, leave_type,
                     start_date, end_date, days_requested,
                     status, request_date, notes)
                VALUES
                    (:leave_id, :employee_id, :leave_type,
                     :start_date, :end_date, :days_requested,
                     'Pending', :request_date, :notes)
                """
            )
            session.execute(
                insert_sql,
                {
                    "leave_id": new_leave_id,
                    "employee_id": employee_id,
                    "leave_type": leave_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "days_requested": days_requested,
                    "request_date": date.today().isoformat(),
                    "notes": notes,
                },
            )
            session.commit()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "create_leave_request(%s) — new id=%s — %.1f ms",
            employee_id,
            new_leave_id,
            elapsed,
        )
        return {
            "leave_id": new_leave_id,
            "days_requested": days_requested,
            "status": "Pending",
            "message": (
                f"Leave request {new_leave_id} created successfully "
                f"({days_requested} business day(s))."
            ),
        }

    except Exception as exc:
        logger.exception("create_leave_request failed for employee_id=%s", employee_id)
        return {"error": str(exc)}


@tool
def get_timesheets(
    employee_id: str,
    project_id: Optional[str] = None,
    week_start: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch timesheet entries for an employee, with optional filters.

    Rows are returned in reverse chronological order (most recent week first).

    Args:
        employee_id: Unique identifier of the employee (required).
        project_id:  Filter by a specific project (optional).
        week_start:  ISO-8601 date of the week's Monday (optional, e.g. "2024-03-04").
        limit:       Maximum number of rows to return (default 20).

    Returns a list of dicts, each representing one timesheet row.
    Returns [{"error": "..."}] on DB failure.
    """
    t0 = time.perf_counter()
    try:
        # Build query dynamically to avoid passing NULL parameters into
        # equality comparisons (which would never match in SQL).
        conditions = ["employee_id = :employee_id"]
        params: Dict[str, Any] = {"employee_id": employee_id, "limit": limit}

        if project_id is not None:
            conditions.append("project_id = :project_id")
            params["project_id"] = project_id

        if week_start is not None:
            conditions.append("week_start_date = :week_start")
            params["week_start"] = week_start

        where_clause = " AND ".join(conditions)
        sql = text(
            f"""
            SELECT *
            FROM hr.hr_timesheets
            WHERE {where_clause}
            ORDER BY week_start_date DESC
            LIMIT :limit
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_timesheets(%s, project=%s, week=%s, limit=%d) — %d rows — %.1f ms",
            employee_id, project_id, week_start, limit, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("get_timesheets failed for employee_id=%s", employee_id)
        return [{"error": str(exc)}]


@tool
def get_employee_skills(
    employee_id: str,
    certified_only: bool = False,
) -> List[Dict[str, Any]]:
    """Return the skill profile of an employee, optionally filtered to certified skills.

    Rows are sorted by years_experience descending so the most experienced
    skills appear first.

    Args:
        employee_id:    Unique identifier of the employee.
        certified_only: When True, only skills where certified = 'Yes' are returned.

    Returns a list of dicts with fields: skill_name, level, years_experience,
    certified, last_assessed.
    Returns [{"error": "..."}] on DB failure.
    """
    t0 = time.perf_counter()
    try:
        conditions = ["employee_id = :employee_id"]
        params: Dict[str, Any] = {"employee_id": employee_id}

        if certified_only:
            conditions.append("certified = 'Yes'")

        where_clause = " AND ".join(conditions)
        sql = text(
            f"""
            SELECT skill_name, level, years_experience, certified, last_assessed
            FROM hr.hr_skills
            WHERE {where_clause}
            ORDER BY years_experience DESC
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_employee_skills(%s, certified_only=%s) — %d rows — %.1f ms",
            employee_id, certified_only, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("get_employee_skills failed for employee_id=%s", employee_id)
        return [{"error": str(exc)}]


@tool
def get_performance_review(
    employee_id: str,
    period: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve the most recent performance review for an employee.

    Optionally restrict to a specific review period (e.g. "2024-H1").
    Always returns at most one row — the most recently dated review.

    Args:
        employee_id: Unique identifier of the employee.
        period:      Review period string (optional, e.g. "2024-H1", "2023-Annual").

    Returns a dict with all columns from hr_performance_reviews, or
    {"error": "No performance review found"} when there is no matching record.
    Returns {"error": "..."} on DB failure.
    """
    t0 = time.perf_counter()
    try:
        conditions = ["employee_id = :employee_id"]
        params: Dict[str, Any] = {"employee_id": employee_id}

        if period is not None:
            conditions.append("review_period = :period")
            params["period"] = period

        where_clause = " AND ".join(conditions)
        sql = text(
            f"""
            SELECT *
            FROM hr.hr_performance_reviews
            WHERE {where_clause}
            ORDER BY review_date DESC
            LIMIT 1
            """
        )

        with _Session() as session:
            row = session.execute(sql, params).fetchone()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_performance_review(%s, period=%s) — %.1f ms",
            employee_id, period, elapsed,
        )

        if row is None:
            return {"error": "No performance review found"}
        return _row_to_dict(row)

    except Exception as exc:
        logger.exception(
            "get_performance_review failed for employee_id=%s", employee_id
        )
        return {"error": str(exc)}
