"""Shared pytest fixtures for integration tests.

Strategy:
- Use the real PostgreSQL containers (same as dev) via httpx AsyncClient.
- A session-scoped admin user is created once and cleaned up after all tests.
- Each test creates its own data with uuid-suffixed identifiers to avoid conflicts.
"""
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"

# ── Unique test-run suffix so parallel runs don't collide ────────────────────

RUN_ID = uuid.uuid4().hex[:8]


# ── HTTP client ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as ac:
        yield ac


# ── Admin user + headers (created once per test session) ─────────────────────

@pytest_asyncio.fixture(scope="session")
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    email = f"test_admin_{RUN_ID}@talan.com"
    password = "TestSecret123!"

    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Test Admin",
        "role": "admin",
    })

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="session")
async def manager_headers(client: AsyncClient) -> dict[str, str]:
    email = f"test_manager_{RUN_ID}@talan.com"
    password = "TestSecret123!"

    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Test Manager",
        "role": "manager",
    })

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="session")
async def employee_headers(client: AsyncClient) -> dict[str, str]:
    email = f"test_employee_{RUN_ID}@talan.com"
    password = "TestSecret123!"

    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Test Employee",
        "role": "employee",
    })

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def unique_email() -> str:
    return f"emp_{uuid.uuid4().hex[:8]}@talan.com"


def unique_name() -> str:
    return f"Company {uuid.uuid4().hex[:6]}"
