"""
main.py — Point d'entrée FastAPI
Talan Platform — Assistant IA, Dashboard, Digital Twin
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine_hr, engine_crm, engine_erp
from app.models import hr_models, crm_models, erp_models  # noqa: F401 — enregistre les modèles
from app.api.routes import chat, hr, crm, erp, simulate


def _tables_for(prefix: str):
    """Retourne uniquement les tables dont le nom commence par `prefix`."""
    return [t for t in Base.metadata.tables.values() if t.name.startswith(prefix)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup / shutdown events."""
    # Créer uniquement les tables du bon domaine dans chaque base
    Base.metadata.create_all(bind=engine_hr,  tables=_tables_for("hr_"))
    Base.metadata.create_all(bind=engine_crm, tables=_tables_for("crm_"))
    Base.metadata.create_all(bind=engine_erp, tables=_tables_for("erp_"))
    yield
    # Shutdown: fermer les connexions proprement


app = FastAPI(
    title="Talan Platform API",
    description="Plateforme Intelligente Talan — Assistant IA, Dashboard, Digital Twin",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(chat.router,     prefix="/api/v1/chat",     tags=["chat"])
app.include_router(hr.router,       prefix="/api/v1/hr",       tags=["hr"])
app.include_router(crm.router,      prefix="/api/v1/crm",      tags=["crm"])
app.include_router(erp.router,      prefix="/api/v1/erp",      tags=["erp"])
app.include_router(simulate.router, prefix="/api/v1/simulate", tags=["simulate"])


# ── Santé ─────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "talan-api", "version": app.version}


@app.get("/", tags=["system"])
def root():
    return {
        "message": "Talan Platform API",
        "docs": "/docs",
        "version": app.version,
    }
