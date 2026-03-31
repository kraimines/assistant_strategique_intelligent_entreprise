"""Async database connectivity — SQLAlchemy async engines + session factories per domain."""
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ── Base ORM ──────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Async engines (one per database) ─────────────────────────────────────────

_engine_kwargs = {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10,
    "echo": False,
}


def _async_url(domain: str) -> str:
    """Convert postgresql+psycopg2 URL to postgresql+asyncpg."""
    return settings.database_url(domain).replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    ) + "?ssl=disable"


engine_hr  = create_async_engine(_async_url("hr"),  **_engine_kwargs,
    connect_args={"server_settings": {"search_path": "hr,public"}})
engine_crm = create_async_engine(_async_url("crm"), **_engine_kwargs,
    connect_args={"server_settings": {"search_path": "crm,public"}})
engine_erp = create_async_engine(_async_url("erp"), **_engine_kwargs,
    connect_args={"server_settings": {"search_path": "erp,public"}})

SessionHR  = async_sessionmaker(engine_hr,  class_=AsyncSession, expire_on_commit=False)
SessionCRM = async_sessionmaker(engine_crm, class_=AsyncSession, expire_on_commit=False)
SessionERP = async_sessionmaker(engine_erp, class_=AsyncSession, expire_on_commit=False)

_SESSIONS = {"hr": SessionHR, "crm": SessionCRM, "erp": SessionERP}
_ENGINES  = {"hr": engine_hr, "crm": engine_crm, "erp": engine_erp}


async def get_session(domain: str) -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator yielding an AsyncSession for the given domain.
    Use as a FastAPI dependency via Depends().

    Args:
        domain: "hr", "crm", or "erp"
    """
    factory = _SESSIONS.get(domain)
    if factory is None:
        raise ValueError(f"Unknown domain '{domain}'")
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def ping_all() -> dict[str, str]:
    """Check connectivity for all three PostgreSQL databases."""
    results: dict[str, str] = {}
    for domain, engine in _ENGINES.items():
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            results[domain] = "ok"
        except Exception as exc:
            results[domain] = str(exc)
    return results
