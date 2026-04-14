"""Unit tests for ERP domain tools — mock the SQLAlchemy engine.

Strategy
--------
- Patch ``app.tools.erp_tools._Session`` so no real PostgreSQL connection
  is needed.
- Tests cover argument handling, return shapes, computed KPIs (recovery_rate),
  and error paths.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_row(data: dict):
    """Create a MagicMock that exposes ._mapping like a SQLAlchemy Row."""
    row = MagicMock()
    type(row)._mapping = PropertyMock(return_value=data)
    return row


def _make_session_mock(fetchone=None, fetchall=None):
    """Return (session_factory, mock_session) with pre-configured execute results."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = fetchone
    mock_result.fetchall.return_value = fetchall or []

    mock_session = MagicMock()
    mock_session.execute.return_value = mock_result
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    session_factory = MagicMock(return_value=mock_session)
    return session_factory, mock_session


# ── get_invoice_status ────────────────────────────────────────────────────────

class TestGetInvoiceStatus:

    def test_returns_invoice_list(self):
        """Should return a list of invoice dicts."""
        from app.tools.erp_tools import get_invoice_status

        invoice_rows = [
            _make_row({
                "invoice_id": "SINV00123",
                "customer_id": "CUS0022",
                "issue_date": date(2025, 1, 15),
                "due_date": date(2025, 2, 15),
                "amount": 12500.0,
                "payment_status": "Unpaid",
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=invoice_rows)

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_invoice_status.invoke({"customer_id": "CUS0022"})

        assert len(result) == 1
        assert result[0]["invoice_id"] == "SINV00123"
        assert result[0]["payment_status"] == "Unpaid"
        assert result[0]["issue_date"] == "2025-01-15"

    def test_returns_all_when_no_filters(self):
        """Should return rows when called with no optional filters."""
        from app.tools.erp_tools import get_invoice_status

        session_factory, _ = _make_session_mock(fetchall=[])

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_invoice_status.invoke({})

        assert result == []

    def test_payment_status_filter_applied(self):
        """When payment_status is set the WHERE clause should include it."""
        from app.tools.erp_tools import get_invoice_status

        session_factory, mock_session = _make_session_mock(fetchall=[])

        with patch("app.tools.erp_tools._Session", session_factory):
            get_invoice_status.invoke({"payment_status": "Overdue"})

        call_args = mock_session.execute.call_args
        sql_str = str(call_args[0][0])
        assert "payment_status" in sql_str

    def test_returns_error_on_db_exception(self):
        """Should catch exceptions and return [{'error': ...}]."""
        from app.tools.erp_tools import get_invoice_status

        session_factory = MagicMock(side_effect=Exception("connection refused"))

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_invoice_status.invoke({})

        assert isinstance(result, list)
        assert "error" in result[0]


# ── get_payment_history ───────────────────────────────────────────────────────

class TestGetPaymentHistory:

    def test_returns_payments_with_recovery_rate(self):
        """Should return payments list and compute recovery_rate correctly."""
        from app.tools.erp_tools import get_payment_history

        payment_rows = [
            _make_row({
                "payment_id": "PAY001",
                "invoice_id": "SINV00100",
                "payment_date": date(2025, 2, 1),
                "payment_amount": 5000.0,
                "payment_method": "Bank Transfer",
                "reference": "REF-001",
                "currency": "TND",
                "bank_account": "BA001",
                "issue_date": date(2025, 1, 15),
                "due_date": date(2025, 2, 15),
                "invoice_amount": 10000.0,
                "payment_status": "Partial",
            }),
        ]
        totals_row = _make_row({"total_invoiced": 10000.0, "total_paid": 5000.0})

        call_count = {"n": 0}
        mock_result_payments = MagicMock()
        mock_result_payments.fetchall.return_value = payment_rows

        mock_result_totals = MagicMock()
        mock_result_totals.fetchone.return_value = totals_row

        mock_session = MagicMock()

        def execute_side_effect(sql, params=None):
            if call_count["n"] == 0:
                call_count["n"] += 1
                return mock_result_payments
            return mock_result_totals

        mock_session.execute.side_effect = execute_side_effect
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        session_factory = MagicMock(return_value=mock_session)

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_payment_history.invoke({"customer_id": "CUS0022", "months": 6})

        assert result["total_invoiced"] == pytest.approx(10000.0)
        assert result["total_paid"] == pytest.approx(5000.0)
        assert result["recovery_rate"] == pytest.approx(50.0)
        assert len(result["payments"]) == 1

    def test_recovery_rate_zero_when_no_invoices(self):
        """Should return recovery_rate=0.0 when total_invoiced is 0."""
        from app.tools.erp_tools import get_payment_history

        totals_row = _make_row({"total_invoiced": 0.0, "total_paid": 0.0})

        mock_result_payments = MagicMock()
        mock_result_payments.fetchall.return_value = []

        mock_result_totals = MagicMock()
        mock_result_totals.fetchone.return_value = totals_row

        call_count = {"n": 0}
        mock_session = MagicMock()

        def execute_side_effect(sql, params=None):
            if call_count["n"] == 0:
                call_count["n"] += 1
                return mock_result_payments
            return mock_result_totals

        mock_session.execute.side_effect = execute_side_effect
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        session_factory = MagicMock(return_value=mock_session)

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_payment_history.invoke({"customer_id": "CUS9999"})

        assert result["recovery_rate"] == 0.0

    def test_returns_error_on_db_exception(self):
        """Should catch exceptions and return {'error': ...}."""
        from app.tools.erp_tools import get_payment_history

        session_factory = MagicMock(side_effect=Exception("DB down"))

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_payment_history.invoke({"customer_id": "CUS0001"})

        assert "error" in result


# ── list_sales_orders ─────────────────────────────────────────────────────────

class TestListSalesOrders:

    def test_returns_sales_order_list(self):
        """Should return a list of sales order dicts."""
        from app.tools.erp_tools import list_sales_orders

        order_rows = [
            _make_row({
                "order_id": "SO00001",
                "customer_id": "CUS0022",
                "order_date": date(2025, 3, 10),
                "status": "Pending",
                "sales_rep_id": "EMP0005",
                "total_amount": 7500.0,
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=order_rows)

        with patch("app.tools.erp_tools._Session", session_factory):
            result = list_sales_orders.invoke({"customer_id": "CUS0022"})

        assert len(result) == 1
        assert result[0]["order_id"] == "SO00001"

    def test_status_filter_applied(self):
        """When status is set the WHERE clause should include it."""
        from app.tools.erp_tools import list_sales_orders

        session_factory, mock_session = _make_session_mock(fetchall=[])

        with patch("app.tools.erp_tools._Session", session_factory):
            list_sales_orders.invoke({"status": "Delivered"})

        call_args = mock_session.execute.call_args
        sql_str = str(call_args[0][0])
        assert "status" in sql_str

    def test_returns_error_on_db_exception(self):
        """Should return [{'error': ...}] on DB failure."""
        from app.tools.erp_tools import list_sales_orders

        session_factory = MagicMock(side_effect=Exception("timeout"))

        with patch("app.tools.erp_tools._Session", session_factory):
            result = list_sales_orders.invoke({})

        assert isinstance(result, list)
        assert "error" in result[0]


# ── get_supplier_info ─────────────────────────────────────────────────────────

class TestGetSupplierInfo:

    def test_requires_at_least_one_filter(self):
        """Should return [{'error': ...}] when no filter is provided."""
        from app.tools.erp_tools import get_supplier_info

        result = get_supplier_info.invoke({})

        assert isinstance(result, list)
        assert "error" in result[0]

    def test_returns_supplier_with_aggregates(self):
        """Should return supplier data enriched with nb_orders and total_spend."""
        from app.tools.erp_tools import get_supplier_info

        supplier_rows = [
            _make_row({
                "supplier_id": "SUP001",
                "name": "Fournitures Pro",
                "country": "FR",
                "nb_orders": 12,
                "total_spend": 45000.0,
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=supplier_rows)

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_supplier_info.invoke({"supplier_id": "SUP001"})

        assert len(result) == 1
        assert result[0]["supplier_id"] == "SUP001"
        assert result[0]["nb_orders"] == 12.0  # _row_to_dict casts to float

    def test_name_search_returns_results(self):
        """Should pass name_search as ILIKE parameter and return matches."""
        from app.tools.erp_tools import get_supplier_info

        supplier_rows = [
            _make_row({
                "supplier_id": "SUP002",
                "name": "Tech Supplies SARL",
                "country": "TN",
                "nb_orders": 5,
                "total_spend": 12000.0,
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=supplier_rows)

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_supplier_info.invoke({"name_search": "Tech"})

        assert len(result) == 1
        assert "Tech" in result[0]["name"]

    def test_returns_error_on_db_exception(self):
        """Should return [{'error': ...}] on DB failure."""
        from app.tools.erp_tools import get_supplier_info

        session_factory = MagicMock(side_effect=Exception("connection lost"))

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_supplier_info.invoke({"supplier_id": "SUP001"})

        assert isinstance(result, list)
        assert "error" in result[0]


# ── get_purchase_orders ───────────────────────────────────────────────────────

class TestGetPurchaseOrders:

    def test_returns_po_lines_list(self):
        """Should return joined PO + line rows as a flat list."""
        from app.tools.erp_tools import get_purchase_orders

        po_rows = [
            _make_row({
                "po_id": "PO00456",
                "supplier_id": "SUP001",
                "order_date": date(2025, 2, 1),
                "expected_delivery": date(2025, 2, 28),
                "amount": 5000.0,
                "status": "Pending",
                "approved_by": "EMP0010",
                "currency": "TND",
                "warehouse": "WH-01",
                "po_line_id": "POL001",
                "product_id": "PROD001",
                "quantity": 50.0,
                "unit_price": 100.0,
                "line_total": 5000.0,
                "quantity_received": 0.0,
                "line_delivery": date(2025, 2, 28),
                "notes": "",
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=po_rows)

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_purchase_orders.invoke({"supplier_id": "SUP001"})

        assert len(result) == 1
        assert result[0]["po_id"] == "PO00456"

    def test_returns_all_when_no_filters(self):
        """Should return rows when called with no optional filters."""
        from app.tools.erp_tools import get_purchase_orders

        session_factory, _ = _make_session_mock(fetchall=[])

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_purchase_orders.invoke({})

        assert result == []

    def test_warehouse_filter_applied(self):
        """When warehouse is set the WHERE clause should include it."""
        from app.tools.erp_tools import get_purchase_orders

        session_factory, mock_session = _make_session_mock(fetchall=[])

        with patch("app.tools.erp_tools._Session", session_factory):
            get_purchase_orders.invoke({"warehouse": "WH-02"})

        call_args = mock_session.execute.call_args
        sql_str = str(call_args[0][0])
        assert "warehouse" in sql_str

    def test_returns_error_on_db_exception(self):
        """Should return [{'error': ...}] on DB failure."""
        from app.tools.erp_tools import get_purchase_orders

        session_factory = MagicMock(side_effect=Exception("DB unavailable"))

        with patch("app.tools.erp_tools._Session", session_factory):
            result = get_purchase_orders.invoke({})

        assert isinstance(result, list)
        assert "error" in result[0]
