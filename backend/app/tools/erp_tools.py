"""LangChain tools for the ERP domain — talan_erp PostgreSQL database.

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
    settings.database_url("erp"),
    pool_pre_ping=True,
    connect_args={"options": "-csearch_path=erp,public"},
)
_Session = sessionmaker(bind=_engine)


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
def get_invoice_status(
    customer_id: Optional[str] = None,
    invoice_id: Optional[str] = None,
    payment_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve ERP invoices with optional filters on customer, invoice ID or payment status.

    Typical payment_status values: "Paid", "Unpaid", "Overdue", "Partial".

    All parameters are optional — omitting all of them returns the 50 most
    recently issued invoices across all customers.

    Args:
        customer_id:    Filter by ERP customer identifier (optional).
        invoice_id:     Fetch a specific invoice by its ID (optional).
        payment_status: Filter by payment status string (optional).

    Returns a list of invoice dicts ordered by issue_date descending (max 50).
    Returns [{"error": "..."}] on DB failure.
    """
    t0 = time.perf_counter()
    try:
        conditions: List[str] = []
        params: Dict[str, Any] = {"limit": 8}

        if customer_id is not None:
            conditions.append("customer_id = :customer_id")
            params["customer_id"] = customer_id

        if invoice_id is not None:
            conditions.append("invoice_id = :invoice_id")
            params["invoice_id"] = invoice_id

        if payment_status is not None:
            conditions.append("payment_status = :payment_status")
            params["payment_status"] = payment_status

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = text(
            f"""
            SELECT *
            FROM erp.erp_invoices
            {where_clause}
            ORDER BY issue_date DESC
            LIMIT :limit
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_invoice_status(customer=%s, invoice=%s, status=%s) "
            "— %d rows — %.1f ms",
            customer_id, invoice_id, payment_status, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("get_invoice_status failed")
        return [{"error": str(exc)}]


@tool
def get_payment_history(
    customer_id: str,
    months: int = 6,
) -> Dict[str, Any]:
    """Return the payment history for an ERP customer with recovery-rate KPIs.

    Joins erp_payments with erp_invoices and restricts to invoices issued
    within the last N months.

    Args:
        customer_id: Unique identifier of the ERP customer.
        months:      Look-back window in months (default 6, clamped to 1–120).

    Returns a dict with keys:
        - payments       (list of payment dicts)
        - total_invoiced (float)  — sum of invoice amounts in the window
        - total_paid     (float)  — sum of payment amounts collected
        - recovery_rate  (float)  — total_paid / total_invoiced * 100, or 0 if no invoices

    Returns {"error": "..."} on DB failure.
    """
    t0 = time.perf_counter()
    months = max(1, min(months, 120))

    try:
        # ── Fetch individual payment rows ────────────────────────────────────
        payments_sql = text(
            """
            SELECT
                p.payment_id,
                p.invoice_id,
                p.payment_date,
                p.amount         AS payment_amount,
                p.payment_method,
                p.reference,
                p.currency,
                p.bank_account,
                i.issue_date,
                i.due_date,
                i.amount         AS invoice_amount,
                i.payment_status
            FROM erp.erp_payments  p
            JOIN erp.erp_invoices  i ON p.invoice_id = i.invoice_id
            WHERE i.customer_id = :customer_id
              AND i.issue_date  >= NOW() - CAST(:months_interval AS INTERVAL)
            ORDER BY p.payment_date DESC
            """
        )

        # ── Aggregate totals ─────────────────────────────────────────────────
        totals_sql = text(
            """
            SELECT
                COALESCE(SUM(i.amount), 0)         AS total_invoiced,
                COALESCE(SUM(p.amount), 0)         AS total_paid
            FROM erp.erp_invoices  i
            LEFT JOIN erp.erp_payments p ON p.invoice_id = i.invoice_id
            WHERE i.customer_id = :customer_id
              AND i.issue_date  >= NOW() - CAST(:months_interval AS INTERVAL)
            """
        )

        params = {
            "customer_id": customer_id,
            "months_interval": f"{months} months",
        }

        with _Session() as session:
            payment_rows = session.execute(payments_sql, params).fetchall()
            totals_row = session.execute(totals_sql, params).fetchone()

        total_invoiced = float(totals_row._mapping["total_invoiced"] or 0)
        total_paid = float(totals_row._mapping["total_paid"] or 0)
        recovery_rate = (
            round(total_paid / total_invoiced * 100, 2) if total_invoiced > 0 else 0.0
        )

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_payment_history(%s, months=%d) — %d payments — recovery=%.1f%% — %.1f ms",
            customer_id, months, len(payment_rows), recovery_rate, elapsed,
        )

        return {
            "payments": [_row_to_dict(r) for r in payment_rows],
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "recovery_rate": recovery_rate,
        }

    except Exception as exc:
        logger.exception("get_payment_history failed for customer_id=%s", customer_id)
        return {"error": str(exc)}


@tool
def list_sales_orders(
    customer_id: Optional[str] = None,
    sales_rep_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List ERP sales orders with optional filters, ordered by order_date descending.

    All parameters are optional. Without filters the 20 most recent orders
    across all customers are returned.

    Args:
        customer_id:  Filter by ERP customer identifier (optional).
        sales_rep_id: Filter by the responsible sales representative (optional).
        status:       Filter by order status (e.g. "Pending", "Delivered", "Cancelled").

    Returns a list of sales order dicts (max 20 rows).
    Returns [{"error": "..."}] on DB failure.
    """
    t0 = time.perf_counter()
    try:
        conditions: List[str] = []
        params: Dict[str, Any] = {"limit": 8}

        if customer_id is not None:
            conditions.append("customer_id = :customer_id")
            params["customer_id"] = customer_id

        if sales_rep_id is not None:
            conditions.append("sales_rep_id = :sales_rep_id")
            params["sales_rep_id"] = sales_rep_id

        if status is not None:
            conditions.append("status = :status")
            params["status"] = status

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = text(
            f"""
            SELECT *
            FROM erp.erp_sales_orders
            {where_clause}
            ORDER BY order_date DESC
            LIMIT :limit
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "list_sales_orders(customer=%s, rep=%s, status=%s) "
            "— %d rows — %.1f ms",
            customer_id, sales_rep_id, status, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("list_sales_orders failed")
        return [{"error": str(exc)}]


@tool
def get_supplier_info(
    supplier_id: Optional[str] = None,
    name_search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return supplier master data enriched with purchase-order aggregates.

    Joins erp_suppliers with erp_purchase_orders to compute the total number
    of orders and cumulative spend per supplier.

    At least one of supplier_id or name_search must be provided.

    Args:
        supplier_id:  Exact supplier identifier (optional).
        name_search:  Case-insensitive partial match on supplier name (optional).

    Returns a list of supplier dicts each including:
        - all columns from erp_suppliers
        - nb_orders   (int)   — number of purchase orders ever placed
        - total_spend (float) — cumulative amount across all purchase orders

    Returns [{"error": "..."}] when no filter is supplied or on DB failure.
    """
    t0 = time.perf_counter()

    if supplier_id is None and name_search is None:
        return [
            {"error": "At least one of supplier_id or name_search must be provided."}
        ]

    try:
        conditions: List[str] = []
        params: Dict[str, Any] = {}

        if supplier_id is not None:
            conditions.append("s.supplier_id = :supplier_id")
            params["supplier_id"] = supplier_id

        if name_search is not None:
            conditions.append("s.name ILIKE :name_search")
            params["name_search"] = f"%{name_search}%"

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = text(
            f"""
            SELECT
                s.*,
                COUNT(po.po_id)            AS nb_orders,
                COALESCE(SUM(po.amount), 0) AS total_spend
            FROM erp.erp_suppliers s
            LEFT JOIN erp.erp_purchase_orders po
                   ON s.supplier_id = po.supplier_id
            {where_clause}
            GROUP BY s.supplier_id
            ORDER BY total_spend DESC
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_supplier_info(id=%s, search=%s) — %d rows — %.1f ms",
            supplier_id, name_search, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("get_supplier_info failed")
        return [{"error": str(exc)}]


@tool
def get_purchase_orders(
    supplier_id: Optional[str] = None,
    status: Optional[str] = None,
    warehouse: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return purchase orders with their line items, optionally filtered.

    Joins erp_purchase_orders with erp_po_lines so that every row in the
    result represents one order line (a PO with multiple lines produces
    multiple rows).

    All parameters are optional. Without filters the 50 most recent POs
    (across all lines) are returned.

    Args:
        supplier_id: Filter by supplier identifier (optional).
        status:      Filter by PO status (e.g. "Pending", "Received", "Cancelled").
        warehouse:   Filter by destination warehouse (optional, partial match not applied
                     — use the exact value stored in the database).

    Returns a list of dicts, each containing all po columns plus
    product_id, quantity_ordered (as quantity), and unit_cost (as unit_price)
    from the PO line.
    Returns [{"error": "..."}] on DB failure.
    """
    t0 = time.perf_counter()
    try:
        conditions: List[str] = []
        params: Dict[str, Any] = {"limit": 8}

        if supplier_id is not None:
            conditions.append("po.supplier_id = :supplier_id")
            params["supplier_id"] = supplier_id

        if status is not None:
            conditions.append("po.status = :status")
            params["status"] = status

        if warehouse is not None:
            conditions.append("po.warehouse = :warehouse")
            params["warehouse"] = warehouse

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = text(
            f"""
            SELECT
                po.po_id,
                po.supplier_id,
                po.order_date,
                po.expected_delivery,
                po.amount,
                po.status,
                po.approved_by,
                po.currency,
                po.warehouse,
                pol.po_line_id,
                pol.product_id,
                pol.quantity_ordered  AS quantity,
                pol.unit_cost         AS unit_price,
                pol.line_total,
                pol.quantity_received,
                pol.expected_delivery AS line_delivery,
                pol.notes
            FROM erp.erp_purchase_orders po
            JOIN erp.erp_po_lines pol ON po.po_id = pol.po_id
            {where_clause}
            ORDER BY po.order_date DESC
            LIMIT :limit
            """
        )

        with _Session() as session:
            rows = session.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "get_purchase_orders(supplier=%s, status=%s, warehouse=%s) "
            "— %d rows — %.1f ms",
            supplier_id, status, warehouse, len(rows), elapsed,
        )
        return [_row_to_dict(r) for r in rows]

    except Exception as exc:
        logger.exception("get_purchase_orders failed")
        return [{"error": str(exc)}]
