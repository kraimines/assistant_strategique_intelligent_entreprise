"""Integration tests — CRM API (4 tests)."""
from httpx import AsyncClient

from tests.conftest import unique_name


def _account_payload(name: str | None = None) -> dict:
    return {
        "name": name or unique_name(),
        "industry": "Technology",
        "country": "France",
        "annual_revenue": 500000.0,
    }


# ── 1. Create account ─────────────────────────────────────────────────────────

async def test_create_account(client: AsyncClient, admin_headers: dict):
    """POST /crm/accounts creates and returns the new account."""
    payload = _account_payload()
    resp = await client.post("/api/v1/crm/accounts", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == payload["name"]
    assert data["account_id"] > 0


# ── 2. Read account ───────────────────────────────────────────────────────────

async def test_read_account(client: AsyncClient, admin_headers: dict):
    """GET /crm/accounts/{id} returns the correct account."""
    account_id = (await client.post(
        "/api/v1/crm/accounts", json=_account_payload(), headers=admin_headers
    )).json()["account_id"]

    resp = await client.get(f"/api/v1/crm/accounts/{account_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["account_id"] == account_id


# ── 3. Update account ─────────────────────────────────────────────────────────

async def test_update_account(client: AsyncClient, admin_headers: dict):
    """PUT /crm/accounts/{id} updates the account."""
    account_id = (await client.post(
        "/api/v1/crm/accounts", json=_account_payload(), headers=admin_headers
    )).json()["account_id"]

    resp = await client.put(
        f"/api/v1/crm/accounts/{account_id}",
        json={"industry": "Finance"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["industry"] == "Finance"


# ── 4. Delete requires admin (employee gets 403) ──────────────────────────────

async def test_delete_account_requires_admin(client: AsyncClient, admin_headers: dict, employee_headers: dict):
    """DELETE /crm/accounts/{id} returns 403 for employee, 204 for admin."""
    account_id = (await client.post(
        "/api/v1/crm/accounts", json=_account_payload(), headers=admin_headers
    )).json()["account_id"]

    # employee cannot delete
    assert (await client.delete(
        f"/api/v1/crm/accounts/{account_id}", headers=employee_headers
    )).status_code == 403

    # admin can delete
    assert (await client.delete(
        f"/api/v1/crm/accounts/{account_id}", headers=admin_headers
    )).status_code == 204
