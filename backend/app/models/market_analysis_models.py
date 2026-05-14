"""SQLAlchemy ORM models for the Market Analysis Agent.

Tables (created in talan_hr DB under schema 'public'):
- market_raw_articles   — raw articles from all collectors
- market_news_analyses  — LLM-extracted causal analyses
- market_alerts         — generated alerts
- market_reports        — periodic full reports
- market_pipeline_runs  — audit log of each pipeline execution
- market_gnn_scores     — time-series of GNN inference scores (for LSTM forecaster)
- market_recommendations — LLM strategic recommendations from GNN + forecast
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer,
    String, Text, JSON, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class MarketRawArticle(Base):
    """Raw article as fetched by the Collector — deduplicated by external_id."""
    __tablename__ = "market_raw_articles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    external_id = Column(String(512), nullable=False)       # URL hash / API id
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(128), nullable=False)            # 'NewsAPI', 'Reuters RSS', …
    url = Column(Text, nullable=False)
    published_at = Column(DateTime, nullable=False)
    language = Column(String(8), default="en")
    tickers = Column(JSON, default=list)                    # ["NVDA", "MSFT"]
    keywords = Column(JSON, default=list)
    raw_metadata = Column(JSON, default=dict)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    analysed = Column(Boolean, default=False)               # flipped after LLM analysis

    __table_args__ = (
        UniqueConstraint("external_id", name="uq_market_raw_articles_external_id"),
        Index("ix_market_raw_articles_published_at", "published_at"),
        Index("ix_market_raw_articles_analysed", "analysed"),
    )


class MarketNewsAnalysis(Base):
    """LLM-extracted structured causal analysis for one article."""
    __tablename__ = "market_news_analyses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    article_id = Column(UUID(as_uuid=False), nullable=False)  # FK → market_raw_articles.id
    article_external_id = Column(String(512), nullable=False)
    article_title = Column(Text, nullable=False)
    analysis_timestamp = Column(DateTime, default=datetime.utcnow)

    event_summary = Column(Text)
    event_type = Column(String(64))
    severity = Column(Float, default=0.0)
    urgency = Column(String(16), default="low")

    entities = Column(JSON, default=list)          # List[Entity]
    causal_relations = Column(JSON, default=list)  # List[CausalRelation]

    talan_impact_score = Column(Float, default=0.0)
    talan_impact_reason = Column(Text, default="")
    talan_action_recommended = Column(Text)
    affected_tickers = Column(JSON, default=list)
    macro_indicators_affected = Column(JSON, default=list)

    kg_synced = Column(Boolean, default=False)      # flipped after Neo4j upsert

    __table_args__ = (
        Index("ix_market_news_analyses_article_id", "article_id"),
        Index("ix_market_news_analyses_talan_impact", "talan_impact_score"),
        Index("ix_market_news_analyses_kg_synced", "kg_synced"),
    )


class MarketAlert(Base):
    """Alert generated when impact threshold exceeded."""
    __tablename__ = "market_alerts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    generated_at = Column(DateTime, default=datetime.utcnow)
    level = Column(String(16), nullable=False)          # low|medium|high|critical
    title = Column(Text, nullable=False)
    summary = Column(Text)
    affected_entities = Column(JSON, default=list)
    talan_impact_score = Column(Float, default=0.0)
    talan_recommended_action = Column(Text)
    source_articles = Column(JSON, default=list)         # List[article_external_id]
    gnn_hidden_risks = Column(JSON, default=list)
    sent = Column(Boolean, default=False)                # True once notification dispatched

    __table_args__ = (
        Index("ix_market_alerts_level", "level"),
        Index("ix_market_alerts_generated_at", "generated_at"),
    )


class MarketReport(Base):
    """Periodic full market analysis report."""
    __tablename__ = "market_reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    generated_at = Column(DateTime, default=datetime.utcnow)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    executive_summary = Column(Text)
    talan_risk_level = Column(String(16), default="low")
    talan_impact_summary = Column(Text)
    recommended_actions = Column(JSON, default=list)

    # Serialised payloads (full JSON blobs)
    key_events_json = Column(JSON, default=list)
    alerts_json = Column(JSON, default=list)
    gnn_predictions_json = Column(JSON)

    kg_nodes_added = Column(Integer, default=0)
    kg_relations_added = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_market_reports_generated_at", "generated_at"),
    )


class MarketPipelineRun(Base):
    """Audit log of each background pipeline execution."""
    __tablename__ = "market_pipeline_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(16), default="running")      # running|completed|failed
    articles_fetched = Column(Integer, default=0)
    articles_analysed = Column(Integer, default=0)
    kg_nodes_added = Column(Integer, default=0)
    kg_relations_added = Column(Integer, default=0)
    gnn_ran = Column(Boolean, default=False)
    report_id = Column(UUID(as_uuid=False))
    errors = Column(JSON, default=list)

    __table_args__ = (
        Index("ix_market_pipeline_runs_started_at", "started_at"),
        Index("ix_market_pipeline_runs_status", "status"),
    )


class MarketGNNScore(Base):
    """One GNN inference result persisted after each pipeline cycle."""
    __tablename__ = "market_gnn_scores"

    id                  = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    recorded_at         = Column(DateTime, default=datetime.utcnow, nullable=False)
    trigger_event       = Column(Text, default="periodic_scan")
    talan_impact        = Column(Float, default=0.0)   # predicted_impact on Talan ∈ [-1,+1]
    systemic_risk       = Column(Float, default=0.0)   # systemic_risk_score ∈ [0,1]
    talan_confidence    = Column(Float, default=0.0)
    hidden_risks_count  = Column(Integer, default=0)
    top_hidden_risks    = Column(JSON,  default=list)  # [{name, impact}, ...]
    all_predictions     = Column(JSON,  default=list)  # full predictions list
    pipeline_run_id     = Column(UUID(as_uuid=False), nullable=True)

    __table_args__ = (
        Index("ix_market_gnn_scores_recorded_at", "recorded_at"),
    )


class MarketRecommendation(Base):
    """LLM-generated strategic recommendation from GNN + forecast output."""
    __tablename__ = "market_recommendations"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=_gen_uuid)
    generated_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    trigger_event   = Column(Text)
    talan_impact    = Column(Float)
    systemic_risk   = Column(Float)
    forecast_7d     = Column(Float, nullable=True)
    forecast_30d    = Column(Float, nullable=True)
    recommendations = Column(JSON,  default=list)   # [{title, action, urgency, horizon}, ...]
    raw_llm_output  = Column(Text)
    model_used      = Column(String(64))
    gnn_score_id    = Column(UUID(as_uuid=False), nullable=True)

    __table_args__ = (
        Index("ix_market_recommendations_generated_at", "generated_at"),
    )
