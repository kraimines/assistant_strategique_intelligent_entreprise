"""Integration tests — ERP API (3 tests)."""
from datetime import date

from httpx import AsyncClient


# ── 1. Create sales order ─────────────────────────────────────────────────────

async def test_create_order(client: AsyncClient, admin_headers: dict):
    """POST /erp/orders creates and returns a new sales order."""
    payload = {
        "order_date": str(date.today()),
        "status": "Pending",
        "total_amount": 12500.0,
        "currency": "EUR",
    }
    resp = await client.post("/api/v1/erp/orders", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "Pending"
    assert data["order_id"] > 0


# ── 2. List invoices with status filter ───────────────────────────────────────

async def test_list_invoices_filtered(client: AsyncClient, admin_headers: dict):
    """GET /erp/invoices?payment_status=Paid returns only matching invoices."""
    resp = await client.get("/api/v1/erp/invoices?payment_status=Paid", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data and "items" in data
    for inv in data["items"]:
        assert inv["payment_status"] == "Paid"


# ── 3. ERP stats requires admin (employee gets 403) ───────────────────────────

async def test_unauthorized_erp_stats(client: AsyncClient, employee_headers: dict, admin_headers: dict):
    """GET /stats/erp returns 403 for employee, 200 for admin."""
    assert (await client.get("/api/v1/stats/erp", headers=employee_headers)).status_code == 403
    assert (await client.get("/api/v1/stats/erp", headers=admin_headers)).status_code == 200
