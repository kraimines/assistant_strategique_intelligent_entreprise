"""SQLAlchemy ORM models for the Competitive Intelligence Agent.

Tables (created in talan_hr DB, public schema — same as market analysis):
  ci_snapshots   — one full scan per company per cycle
  ci_alerts      — alerts generated on significant change detection
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Index,
    String, Text, JSON,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class CompetitorSnapshot(Base):
    """Full scan result for one competitor at one point in time.

    Populated by the autonomous scanner every 6h.
    Read by the conversational agent via query_stored_intel().
    """
    __tablename__ = "ci_snapshots"

    id               = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    company_name     = Column(String(200), nullable=False)
    ticker           = Column(String(20))
    scan_type        = Column(String(50), default="scheduled")  # scheduled | ondemand | triggered

    # ── Raw scraped data ───────────────────────────────────────────────────────
    news_data        = Column(JSON, default=list)    # list[dict] from scrape_company_news
    jobs_data        = Column(JSON, default=dict)    # dict from scrape_job_postings
    financial_data   = Column(JSON, default=dict)    # dict from yfinance

    # ── Computed intelligence ──────────────────────────────────────────────────
    radar_scores     = Column(JSON, default=dict)    # {IA_Générative: 72, Cloud: 45, ...}
    threat_level     = Column(Float, default=0.0)    # 0.0 – 1.0
    threat_label     = Column(String(50))            # Faible / Modéré / Élevé / Critique
    key_moves        = Column(JSON, default=list)    # list[dict]
    anticipated_moves= Column(JSON, default=list)    # list[dict] with horizon + confidence
    hiring_signals   = Column(JSON, default=list)    # list[str]

    # ── LLM strategic assessment (generated only when is_significant=True) ─────
    llm_assessment   = Column(Text)                  # "Capgemini accélère sur GenAI..."
    llm_vulnerability= Column(Text)                  # "Talan exposé sur les offres cloud mid-market"
    llm_response     = Column(Text)                  # "Accélérer roadmap IA, cibler PME cloud"

    # ── Change detection vs previous snapshot ─────────────────────────────────
    is_significant   = Column(Boolean, default=False)
    delta_scores     = Column(JSON, default=dict)    # {axis: delta, ...} vs last snapshot
    change_summary   = Column(Text)                  # human-readable delta description

    snapshot_at      = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ci_snapshots_company_at", "company_name", "snapshot_at"),
    )


class CompetitorAlert(Base):
    """Alert generated when a significant competitive shift is detected."""
    __tablename__ = "ci_alerts"

    id               = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    company_name     = Column(String(200), nullable=False)
    alert_type       = Column(String(100))           # hiring_surge | financial_drop | news_spike | shift_detected
    level            = Column(String(20))            # low | medium | high | critical
    title            = Column(String(300))
    detail           = Column(Text)
    recommended_action = Column(Text)
    snapshot_id      = Column(UUID(as_uuid=False))   # FK → ci_snapshots.id
    acknowledged     = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ci_alerts_company_created", "company_name", "created_at"),
        Index("ix_ci_alerts_level", "level"),
    )
