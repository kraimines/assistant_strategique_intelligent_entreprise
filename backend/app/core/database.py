"""Database connectivity — SQLAlchemy engines + session factories par domaine."""
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


# ── Base ORM ──────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Engines (un par base de données) ─────────────────────────────────────────

_engine_kwargs = {
    "pool_pre_ping": True,   # valide la connexion avant usage
    "pool_size": 5,
    "max_overflow": 10,
}

engine_hr  = create_engine(settings.database_url("hr"),  **_engine_kwargs)
engine_crm = create_engine(settings.database_url("crm"), **_engine_kwargs)
engine_erp = create_engine(settings.database_url("erp"), **_engine_kwargs)

SessionHR  = sessionmaker(bind=engine_hr,  autocommit=False, autoflush=False)
SessionCRM = sessionmaker(bind=engine_crm, autocommit=False, autoflush=False)
SessionERP = sessionmaker(bind=engine_erp, autocommit=False, autoflush=False)

_SESSIONS = {"hr": SessionHR, "crm": SessionCRM, "erp": SessionERP}


def get_session(domain: str) -> Generator[Session, None, None]:
    """
    Générateur de session SQLAlchemy pour un domaine.
    À utiliser comme dépendance FastAPI via Depends().

    Args:
        domain: "hr", "crm", ou "erp"
    """
    factory = _SESSIONS.get(domain)
    if factory is None:
        raise ValueError(f"Unknown domain '{domain}'")
    db = factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ping_all() -> dict:
    """Vérifie la connectivité de chaque base PostgreSQL."""
    results: dict[str, str] = {}
    for domain, engine in [("hr", engine_hr), ("crm", engine_crm), ("erp", engine_erp)]:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            results[domain] = "ok"
        except Exception as exc:
            results[domain] = str(exc)
    return results
