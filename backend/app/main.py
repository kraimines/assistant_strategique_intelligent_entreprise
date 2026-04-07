"""main.py — FastAPI entry point.
Talan Platform — AI Assistant, Dashboard, Digital Twin
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine_crm, engine_erp, engine_hr
from app.models import crm_models, erp_models, hr_models  # noqa: F401
from app.models import user_models  # noqa: F401 — registers User in Base.metadata
from app.api.routes import auth, chat, crm, erp, hr, simulate, stats

logger = logging.getLogger(__name__)

# ── OpenAPI tag descriptions ───────────────────────────────────────────────────

tags_metadata = [
    {
        "name": "auth",
        "description": "Authentication — JWT register / login / profile (`/me`).",
    },
    {
        "name": "hr",
        "description": (
            "Human Resources — departments, employees, skills, "
            "leave requests, performance reviews, headcount KPIs."
        ),
    },
    {
        "name": "crm",
        "description": (
            "Customer Relationship Management — accounts, contacts, "
            "opportunities (pipeline), activities, revenue KPIs."
        ),
    },
    {
        "name": "erp",
        "description": (
            "Enterprise Resource Planning — suppliers, customers, products, "
            "sales orders, invoices, payments, revenue KPIs."
        ),
    },
    {
        "name": "stats",
        "description": (
            "Aggregated KPIs per domain (role-gated). "
            "Admin: HR + CRM + ERP. Manager: HR + CRM. "
            "Includes manual Neo4j sync trigger."
        ),
    },
    {
        "name": "chat",
        "description": "AI assistant chat — LangGraph orchestrated agents (HR / CRM / ERP / RAG).",
    },
    {
        "name": "simulate",
        "description": "Strategic simulation — scenario modelling for managers and directors.",
    },
    {
        "name": "system",
        "description": "Health check and API root.",
    },
]


def _tables_for(prefix: str):
    """Return only tables whose name starts with `prefix`."""
    return [t for t in Base.metadata.tables.values() if t.name.startswith(prefix)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create domain-specific tables at startup; start nightly Neo4j sync scheduler."""
    # ── DB table creation ──────────────────────────────────────────────────────
    async with engine_hr.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_tables_for("hr_") + _tables_for("users"),
        )
    async with engine_crm.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_tables_for("crm_"))
    async with engine_erp.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_tables_for("erp_"))

    # ── APScheduler — nightly Neo4j sync at 02:00 ─────────────────────────────
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from app.services.neo4j_sync import sync_all

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(sync_all, "cron", hour=2, minute=0, id="neo4j_sync")
        scheduler.start()
        logger.info("APScheduler started — Neo4j sync scheduled at 02:00 UTC")
    except Exception as exc:  # noqa: BLE001
        logger.warning("APScheduler not started: %s", exc)
        scheduler = None  # type: ignore[assignment]

    yield

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Talan Platform API",
    description=(
        "**Plateforme Intelligente Talan** — AI-driven strategic assistant "
        "for HR, CRM, and ERP domains.\n\n"
        "## Authentication\n"
        "All protected endpoints require a **Bearer JWT** token obtained via `POST /api/v1/auth/login`.\n\n"
        "## Role-based access\n"
        "- `admin` — full access\n"
        "- `manager` — HR + CRM read/write, ERP read\n"
        "- `employee` — own profile only\n"
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
    contact={"name": "Talan Engineering", "email": "dev@talan.com"},
    license_info={"name": "Proprietary"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,     prefix="/api/v1/auth",     tags=["auth"])
app.include_router(hr.router,       prefix="/api/v1/hr",       tags=["hr"])
app.include_router(crm.router,      prefix="/api/v1/crm",      tags=["crm"])
app.include_router(erp.router,      prefix="/api/v1/erp",      tags=["erp"])
app.include_router(stats.router,    prefix="/api/v1/stats",    tags=["stats"])
app.include_router(chat.router,     prefix="/api/v1/chat",     tags=["chat"])
app.include_router(simulate.router, prefix="/api/v1/simulate", tags=["simulate"])


# ── System endpoints ──────────────────────────────────────────────────────────

@app.get("/health", tags=["system"], summary="Health check")
async def health():
    """Returns API status and PostgreSQL connectivity for all 3 databases."""
    from app.core.database import ping_all
    db_status = await ping_all()
    return {"status": "ok", "service": "talan-api", "version": app.version, "databases": db_status}


@app.get("/", tags=["system"], summary="API root")
def root():
    """Welcome message with links to documentation."""
    return {"message": "Talan Platform API", "docs": "/docs", "version": app.version}
