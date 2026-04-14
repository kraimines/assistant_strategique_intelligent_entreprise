"""Pydantic schemas for the Market Analysis Agent.

Covers:
- Raw article ingestion (Collector output)
- Causal analysis (Analyst output) — strict JSON contract with the LLM
- Knowledge-graph update payloads (World Model)
- GNN prediction output
- API request/response models
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    COMPANY = "company"
    SECTOR = "sector"
    COUNTRY = "country"
    EVENT = "event"
    MACRO_INDICATOR = "macro_indicator"
    NEWS = "news"


# LLM sometimes returns non-standard types — map them to valid EntityType values
_ENTITY_TYPE_ALIASES: Dict[str, str] = {
    # Person / orgs → company
    "person":           "company",
    "individual":       "company",
    "organization":     "company",
    "organisation":     "company",
    "org":              "company",
    "institution":      "company",
    "government":       "company",
    "ngo":              "company",
    "product":          "company",   # product belongs to a company
    "brand":            "company",
    # Geography → country
    "region":           "country",
    "location":         "country",
    "city":             "country",
    "place":            "country",
    "territory":        "country",
    "continent":        "country",
    # Sector-like
    "industry":         "sector",
    "market":           "sector",
    "religion":         "event",     # religion used as context → event
    "culture":          "event",
    "conflict":         "event",
    "crisis":           "event",
    "policy":           "event",
    # Macro indicators
    "indicator":        "macro_indicator",
    "metric":           "macro_indicator",
    "index":            "macro_indicator",
    "currency":         "macro_indicator",
    # News
    "article":          "news",
    "report":           "news",
}


class ImpactDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"


class RelationType(str, Enum):
    CAUSES_IMPACT_ON = "CAUSES_IMPACT_ON"
    BELONGS_TO_SECTOR = "BELONGS_TO_SECTOR"
    SUPPLY_CHAIN_LINK = "SUPPLY_CHAIN_LINK"
    COMPETES_WITH = "COMPETES_WITH"
    OPERATES_IN = "OPERATES_IN"
    TRIGGERS_EVENT = "TRIGGERS_EVENT"
    AFFECTS_INDICATOR = "AFFECTS_INDICATOR"
    MENTIONS = "MENTIONS"


class AlertLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Collector Schemas ─────────────────────────────────────────────────────────

class RawArticle(BaseModel):
    """A raw news article as returned by the Collector."""
    external_id: str = Field(description="Unique ID from the source (URL hash or API id)")
    title: str
    content: str = Field(description="Full article text or summary")
    source: str = Field(description="Source name, e.g. 'NewsAPI', 'Reuters RSS'")
    url: str
    published_at: datetime
    language: str = Field(default="en")
    tickers: List[str] = Field(default_factory=list, description="Stock tickers mentioned")
    keywords: List[str] = Field(default_factory=list)
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)


class CollectorResult(BaseModel):
    """Batch result from one collector run."""
    run_at: datetime = Field(default_factory=datetime.utcnow)
    articles_fetched: int
    articles_new: int
    articles: List[RawArticle]
    errors: List[str] = Field(default_factory=list)


# ── Analyst Schemas (LLM JSON contract) ───────────────────────────────────────

def _normalize_entity_type(v: Any) -> Any:
    """Map LLM-invented type strings to valid EntityType values."""
    if isinstance(v, str):
        normalized = _ENTITY_TYPE_ALIASES.get(v.lower(), v)
        return normalized
    return v


class Entity(BaseModel):
    """A named entity extracted from a news article."""
    name: str = Field(description="Canonical name, e.g. 'NVIDIA', 'Technology', 'United States'")
    type: EntityType
    ticker: Optional[str] = Field(None, description="Stock ticker if applicable")
    aliases: List[str] = Field(default_factory=list)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: Any) -> Any:
        return _normalize_entity_type(v)


class CausalRelation(BaseModel):
    """A directed causal relationship extracted by the LLM."""
    from_entity: str = Field(description="Source entity name")
    from_type: EntityType
    to_entity: str = Field(description="Target entity name")
    to_type: EntityType

    @field_validator("from_type", "to_type", mode="before")
    @classmethod
    def normalize_types(cls, v: Any) -> Any:
        return _normalize_entity_type(v)

    relation_type: RelationType = Field(default=RelationType.CAUSES_IMPACT_ON)

    @field_validator("relation_type", mode="before")
    @classmethod
    def normalize_relation_type(cls, v: Any) -> Any:
        """Fall back to CAUSES_IMPACT_ON for any unknown relation type."""
        if isinstance(v, str) and v not in {r.value for r in RelationType}:
            return RelationType.CAUSES_IMPACT_ON.value
        return v
    impact_direction: ImpactDirection
    impact_score: float = Field(
        ge=-1.0, le=1.0,
        description="Causal impact strength: -1 (very negative) to +1 (very positive)"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="LLM confidence in this relation")
    reason: str = Field(description="1-2 sentence causal explanation")
    time_horizon: str = Field(
        default="immediate",
        description="When impact manifests: 'immediate'|'24h'|'48h'|'1week'|'1month'|'long-term'"
    )
    talan_relevant: bool = Field(
        default=False,
        description="True if this relation may impact Talan (IT services / consulting sector)"
    )

    @field_validator("impact_score")
    @classmethod
    def round_score(cls, v: float) -> float:
        return round(v, 3)


class NewsAnalysis(BaseModel):
    """Complete structured analysis of a single news article — the LLM output contract."""
    article_external_id: str
    article_title: str
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Summary
    event_summary: str = Field(description="1-sentence plain summary of the event")
    event_type: str = Field(
        description="e.g. 'earnings_report', 'geopolitical_conflict', 'product_launch', "
                    "'macro_policy', 'merger_acquisition', 'regulatory', 'natural_disaster'"
    )
    severity: float = Field(ge=0.0, le=1.0, description="Overall market severity 0=negligible 1=systemic")
    urgency: str = Field(description="'low'|'medium'|'high'|'critical'")

    # Extracted graph elements
    entities: List[Entity]
    causal_relations: List[CausalRelation]

    # Talan-specific
    talan_impact_score: float = Field(
        ge=-1.0, le=1.0,
        description="Estimated direct/indirect impact on Talan (-1 to +1)"
    )
    talan_impact_reason: str = Field(
        description="Why this event affects Talan (IT consulting, ESN, digital transformation)"
    )
    talan_action_recommended: Optional[str] = Field(
        None,
        description="Specific action Talan management should consider"
    )

    # Financial context
    affected_tickers: List[str] = Field(default_factory=list)
    macro_indicators_affected: List[str] = Field(
        default_factory=list,
        description="e.g. ['EUR/USD', 'CAC40', 'VIX', 'Oil_Brent']"
    )


# ── World Model Schemas ────────────────────────────────────────────────────────

class KGNode(BaseModel):
    """A node to upsert into the Knowledge Graph."""
    node_type: EntityType
    name: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class KGRelation(BaseModel):
    """An edge to upsert into the Knowledge Graph."""
    from_name: str
    from_type: EntityType
    to_name: str
    to_type: EntityType
    relation_type: RelationType
    properties: Dict[str, Any] = Field(default_factory=dict)


class KGUpdatePayload(BaseModel):
    """Full payload to update the Knowledge Graph after one article analysis."""
    nodes: List[KGNode]
    relations: List[KGRelation]
    source_article_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── GNN Predictor Schemas ─────────────────────────────────────────────────────

class NodeFeatureVector(BaseModel):
    """Feature vector for a single graph node passed to the GNN."""
    node_name: str
    node_type: EntityType
    embedding: List[float] = Field(description="LLM text embedding (384-dim)")
    financial_features: List[float] = Field(
        default_factory=list,
        description="[price_change_pct, volume_ratio, volatility, market_cap_log]"
    )


class GNNPrediction(BaseModel):
    """Single node-level prediction from the GNN."""
    entity_name: str
    entity_type: EntityType
    predicted_impact: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    propagation_hops: int = Field(description="How many hops away from the trigger event")
    hidden_risk: bool = Field(description="True if impact was non-obvious (discovered by GNN)")


class GNNInferenceResult(BaseModel):
    """Full inference result from one GNN forward pass."""
    run_at: datetime = Field(default_factory=datetime.utcnow)
    trigger_event: str
    predictions: List[GNNPrediction]
    talan_prediction: Optional[GNNPrediction] = None
    systemic_risk_score: float = Field(ge=0.0, le=1.0)
    top_hidden_risks: List[GNNPrediction] = Field(default_factory=list)


# ── Report / Alert Schemas ─────────────────────────────────────────────────────

class MarketAlert(BaseModel):
    """Alert generated when impact score exceeds threshold."""
    alert_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    level: AlertLevel
    title: str
    summary: str
    affected_entities: List[str]
    talan_impact_score: float
    talan_recommended_action: Optional[str] = None
    source_articles: List[str] = Field(default_factory=list)
    gnn_hidden_risks: List[str] = Field(default_factory=list)


class MarketReport(BaseModel):
    """Full periodic market analysis report."""
    report_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime

    executive_summary: str
    key_events: List[NewsAnalysis]
    alerts: List[MarketAlert]
    gnn_predictions: Optional[GNNInferenceResult] = None

    talan_risk_level: AlertLevel
    talan_impact_summary: str
    recommended_actions: List[str]

    # KG stats
    kg_nodes_added: int = 0
    kg_relations_added: int = 0


# ── API Request / Response ─────────────────────────────────────────────────────

class MarketAnalysisRequest(BaseModel):
    """Request to trigger an on-demand market analysis cycle."""
    query: Optional[str] = Field(None, description="Optional focused query, e.g. 'AI regulation Europe'")
    tickers: List[str] = Field(default_factory=list, description="Extra tickers to monitor")
    force_gnn: bool = Field(default=False, description="Force GNN inference even if no new articles")


class MarketAnalysisResponse(BaseModel):
    """Response from the market analysis API endpoint."""
    status: str
    report: Optional[MarketReport] = None
    alerts: List[MarketAlert] = Field(default_factory=list)
    message: str = ""


class PipelineStatus(BaseModel):
    """Status of the background market analysis pipeline."""
    running: bool            # scheduler is alive (will fire jobs on schedule)
    cycle_running: bool = False  # a pipeline cycle is currently executing
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    articles_in_db: int = 0
    kg_nodes: int = 0
    kg_relations: int = 0
    last_report_id: Optional[str] = None
    errors_last_run: List[str] = Field(default_factory=list)
