"""Integration tests — Authentication (6 tests)."""
import uuid

import pytest
from httpx import AsyncClient


# ── 1. Successful login ───────────────────────────────────────────────────────

async def test_login_success(client: AsyncClient, admin_headers: dict):
    """Login with valid credentials returns a JWT token."""
    # admin_headers fixture already logged in — just verify the token works
    resp = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "email" in data
    assert "role" in data


# ── 2. Wrong password ─────────────────────────────────────────────────────────

async def test_login_wrong_password(client: AsyncClient):
    """Wrong password returns 401."""
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nobody@talan.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


# ── 3. Unknown email ──────────────────────────────────────────────────────────

async def test_login_unknown_email(client: AsyncClient):
    """Non-existent email returns 401."""
    resp = await client.post("/api/v1/auth/login", json={
        "email": f"ghost_{uuid.uuid4().hex}@talan.com",
        "password": "anything",
    })
    assert resp.status_code == 401


# ── 4. Token required (401 without token) ────────────────────────────────────

async def test_protected_endpoint_requires_token(client: AsyncClient):
    """Accessing a protected endpoint without a token returns 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── 5. /me returns enriched profile ──────────────────────────────────────────

async def test_me_returns_profile(client: AsyncClient, admin_headers: dict):
    """GET /me returns id, email, role, and optional HR fields."""
    resp = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "admin"
    assert "emp_id" in data          # field present (may be null)
    assert "department" in data
    assert "hire_date" in data


# ── 6. Invalid token rejected ─────────────────────────────────────────────────

async def test_me_invalid_token(client: AsyncClient):
    """A forged / malformed token returns 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert resp.status_code == 401
