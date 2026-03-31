"""Integration tests — HR API (7 tests)."""
from httpx import AsyncClient

from tests.conftest import unique_email


def _employee_payload(email: str | None = None) -> dict:
    return {
        "first_name": "Integration",
        "last_name": "Test",
        "email": email or unique_email(),
        "role": "Developer",
        "is_active": True,
    }


# ── 1. Create employee ────────────────────────────────────────────────────────

async def test_create_employee(client: AsyncClient, admin_headers: dict):
    """POST /hr/employees creates and returns the new employee."""
    payload = _employee_payload()
    resp = await client.post("/api/v1/hr/employees", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == payload["email"]
    assert data["emp_id"] > 0


# ── 2. Read employee ──────────────────────────────────────────────────────────

async def test_read_employee(client: AsyncClient, admin_headers: dict):
    """GET /hr/employees/{id} returns the correct employee."""
    payload = _employee_payload()
    emp_id = (await client.post("/api/v1/hr/employees", json=payload, headers=admin_headers)).json()["emp_id"]

    resp = await client.get(f"/api/v1/hr/employees/{emp_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["emp_id"] == emp_id


# ── 3. Update employee ────────────────────────────────────────────────────────

async def test_update_employee(client: AsyncClient, admin_headers: dict):
    """PUT /hr/employees/{id} updates and returns updated data."""
    emp_id = (await client.post(
        "/api/v1/hr/employees", json=_employee_payload(), headers=admin_headers
    )).json()["emp_id"]

    resp = await client.put(
        f"/api/v1/hr/employees/{emp_id}",
        json={"role": "Senior Developer"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "Senior Developer"


# ── 4. Delete employee ────────────────────────────────────────────────────────

async def test_delete_employee(client: AsyncClient, admin_headers: dict):
    """DELETE /hr/employees/{id} removes the record (204), then 404."""
    emp_id = (await client.post(
        "/api/v1/hr/employees", json=_employee_payload(), headers=admin_headers
    )).json()["emp_id"]

    assert (await client.delete(f"/api/v1/hr/employees/{emp_id}", headers=admin_headers)).status_code == 204
    assert (await client.get(f"/api/v1/hr/employees/{emp_id}", headers=admin_headers)).status_code == 404


# ── 5. Non-existent employee → 404 ───────────────────────────────────────────

async def test_read_nonexistent_employee_returns_404(client: AsyncClient, admin_headers: dict):
    """GET /hr/employees/99999999 returns 404."""
    assert (await client.get("/api/v1/hr/employees/99999999", headers=admin_headers)).status_code == 404


# ── 6. Pagination ─────────────────────────────────────────────────────────────

async def test_list_employees_paginated(client: AsyncClient, admin_headers: dict):
    """GET /hr/employees returns paginated list with total and items."""
    resp = await client.get("/api/v1/hr/employees?skip=0&limit=5", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data and "items" in data
    assert len(data["items"]) <= 5


# ── 7. Duplicate email → 409 ─────────────────────────────────────────────────

async def test_create_duplicate_email_returns_409(client: AsyncClient, admin_headers: dict):
    """Creating two employees with the same email returns 409 Conflict."""
    payload = _employee_payload()
    await client.post("/api/v1/hr/employees", json=payload, headers=admin_headers)
    resp = await client.post("/api/v1/hr/employees", json=payload, headers=admin_headers)
    assert resp.status_code == 409
