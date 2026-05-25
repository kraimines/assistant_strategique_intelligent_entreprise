"""Pydantic schemas for the Market Analysis Agent.

Covers:
- Raw article ingestion (Collector output)
- Causal analysis (Analyst output) — strict JSON contract with the LLM
- Knowledge-graph update payloads (World Model)
- GNN prediction output
- API request/response models

Ontology (v2):
  Entity labels : Company | Person | Technology | Regulation | Competitor |
                  MarketTrend | Sector | Country | Event | MacroIndicator | News
  Relation types: ACQUIRED | COMPETES_WITH | INFLUENCES | LAUNCHED | IMPACTS |
                  RECRUITS_IN | CAUSES_IMPACT_ON | BELONGS_TO_SECTOR |
                  SUPPLY_CHAIN_LINK | OPERATES_IN | TRIGGERS_EVENT |
                  AFFECTS_INDICATOR | MENTIONS
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    # Core business / market entities
    COMPANY         = "company"
    PERSON          = "person"
    TECHNOLOGY      = "technology"
    REGULATION      = "regulation"
    COMPETITOR      = "competitor"
    MARKET_TREND    = "market_trend"
    # Legacy / structural
    SECTOR          = "sector"
    COUNTRY         = "country"
    EVENT           = "event"
    MACRO_INDICATOR = "macro_indicator"
    NEWS            = "news"


# LLM sometimes returns non-standard type strings — map them to valid values
_ENTITY_TYPE_ALIASES: Dict[str, str] = {
    # Person
    "individual":           "person",
    "executive":            "person",
    "ceo":                  "person",
    "founder":              "person",
    "politician":           "person",
    # Company / org
    "organization":         "company",
    "organisation":         "company",
    "org":                  "company",
    "institution":          "company",
    "government":           "company",
    "ngo":                  "company",
    "product":              "company",
    "brand":                "company",
    "startup":              "company",
    "vendor":               "company",
    # Technology
    "ai_model":             "technology",
    "software":             "technology",
    "platform":             "technology",
    "framework":            "technology",
    "tool":                 "technology",
    "model":                "technology",
    "algorithm":            "technology",
    "chip":                 "technology",
    "hardware":             "technology",
    # Regulation
    "law":                  "regulation",
    "act":                  "regulation",
    "directive":            "regulation",
    "standard":             "regulation",
    "policy":               "regulation",
    "compliance":           "regulation",
    "norm":                 "regulation",
    # Competitor (ESN/consulting)
    "esn":                  "competitor",
    "consulting":           "competitor",
    "consulting_firm":      "competitor",
    # Market trend
    "trend":                "market_trend",
    "market_dynamic":       "market_trend",
    "macro_trend":          "market_trend",
    "market":               "market_trend",
    "shift":                "market_trend",
    # Geography → country
    "region":               "country",
    "location":             "country",
    "city":                 "country",
    "place":                "country",
    "territory":            "country",
    "continent":            "country",
    # Sector
    "industry":             "sector",
    # Events
    "religion":             "event",
    "culture":              "event",
    "conflict":             "event",
    "crisis":               "event",
    # Commodities / macro
    "commodity":            "macro_indicator",
    "resource":             "macro_indicator",
    "energy":               "macro_indicator",
    "oil":                  "macro_indicator",
    "gas":                  "macro_indicator",
    "metal":                "macro_indicator",
    "raw_material":         "macro_indicator",
    "indicator":            "macro_indicator",
    "metric":               "macro_indicator",
    "index":                "macro_indicator",
    "currency":             "macro_indicator",
    # News
    "article":              "news",
    "report":               "news",
}


# ── Entity name canonicalization & blacklist ─────────────────────────────────
# Applied at three entry points: analyst._dedup_entities, world_model._upsert_entity,
# and synthetic_enricher._match_templates. Keeps "GenAI", "Generative AI", "Gen AI"
# from creating separate KG nodes.

_ENTITY_NAME_ALIASES: Dict[str, str] = {
    # AI / GenAI variants
    "genai":                              "Generative AI",
    "gen ai":                             "Generative AI",
    "generative ai":                      "Generative AI",
    "generative-ai":                      "Generative AI",
    "gpt ai":                             "Generative AI",
    "llm":                                "Large Language Models",
    "llms":                               "Large Language Models",
    "large language model":               "Large Language Models",
    "large language models":              "Large Language Models",
    # Company name variants
    "open ai":                            "OpenAI",
    "openai inc":                         "OpenAI",
    "anthropic pbc":                      "Anthropic",
    "anthropic inc":                      "Anthropic",
    "meta platforms":                     "Meta",
    "meta inc":                           "Meta",
    "facebook":                           "Meta",
    "alphabet":                           "Google",
    "google llc":                         "Google",
    # Geographic variants
    "european union":                     "EU",
    "eu27":                               "EU",
    "uk":                                 "United Kingdom",
    "britain":                            "United Kingdom",
    "usa":                                "United States",
    "u.s.":                               "United States",
    "u.s.a.":                             "United States",
    "america":                            "United States",
    # Regulation variants
    "eu ai act":                          "EU AI Act",
    "eu ai regulation":                   "EU AI Act",
    "ai act":                             "EU AI Act",
    "digital operational resilience act": "DORA",
    "gdpr":                               "GDPR",
    # Banking / Finance variants
    "crédit immobilier":                  "Crédit Immobilier",
    "credit immobilier":                  "Crédit Immobilier",
    "ai consulting":                      "AI Transformation Consulting",
    "ai transformation":                  "AI Transformation Consulting",
}


def _canonical_entity_name(name: str) -> str:
    """Return the canonical form for an entity name. Applies alias map + trim.

    Use this BEFORE generating slugs or matching against templates so that
    'GenAI' and 'Generative AI' collapse to the same canonical entity.
    """
    if not name:
        return name
    return _ENTITY_NAME_ALIASES.get(name.strip().lower(), name.strip())


# Generic / non-actor entities that should never appear as propagation sources.
# These are too vague to carry causal meaning (e.g. "Europe", "Investors").
_ENTITY_BLACKLIST: frozenset = frozenset({
    # Geography too vague
    "europe", "world", "global", "international", "asia", "africa",
    # Generic actor categories
    "investor", "investors", "customer", "customers", "client", "clients",
    "consumer", "consumers", "user", "users",
    "business", "businesses", "industry", "industries",
    "market", "markets", "economy", "economies",
    "company", "companies", "corporation", "corporations",
    "technology", "technologies", "innovation", "innovations",
    # Generic people / roles
    "people", "person", "human", "humans", "team", "teams",
    "expert", "experts", "analyst", "analysts", "executive", "executives",
    "researcher", "researchers", "developer", "developers",
    # Generic media references
    "research", "study", "studies", "report", "reports", "news",
    "article", "articles",
    # Placeholder names
    "bob", "alice", "john", "jane",
})


def _is_blacklisted_entity(name: str) -> bool:
    """True if the entity name is too generic to be a meaningful propagation source."""
    return (name or "").strip().lower() in _ENTITY_BLACKLIST


class ImpactDirection(str, Enum):
    POSITIVE  = "positive"
    NEGATIVE  = "negative"
    NEUTRAL   = "neutral"
    UNCERTAIN = "uncertain"


class RelationType(str, Enum):
    # ── New strategic relations (v2) ──────────────────────────────────────────
    ACQUIRED        = "ACQUIRED"           # Company A acquired Company B
    COMPETES_WITH   = "COMPETES_WITH"      # direct competition
    INFLUENCES      = "INFLUENCES"         # indirect causal influence
    LAUNCHED        = "LAUNCHED"           # company/person launched a technology
    IMPACTS         = "IMPACTS"            # event/trend impacts entity
    RECRUITS_IN     = "RECRUITS_IN"        # company recruiting in a domain/country
    # ── Legacy causal relations (v1) ─────────────────────────────────────────
    CAUSES_IMPACT_ON  = "CAUSES_IMPACT_ON"
    BELONGS_TO_SECTOR = "BELONGS_TO_SECTOR"
    SUPPLY_CHAIN_LINK = "SUPPLY_CHAIN_LINK"
    OPERATES_IN       = "OPERATES_IN"
    TRIGGERS_EVENT    = "TRIGGERS_EVENT"
    AFFECTS_INDICATOR = "AFFECTS_INDICATOR"
    MENTIONS          = "MENTIONS"


class AlertLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# ── Collector Schemas ─────────────────────────────────────────────────────────

class RawArticle(BaseModel):
    """A raw news article as returned by the Collector."""
    external_id:  str = Field(description="Unique ID from the source (URL hash or API id)")
    title:        str
    content:      str = Field(description="Full article text or summary")
    source:       str = Field(description="Source name, e.g. 'NewsAPI', 'Reuters RSS'")
    url:          str
    published_at: datetime
    language:     str = Field(default="en")
    tickers:      List[str] = Field(default_factory=list)
    keywords:     List[str] = Field(default_factory=list)
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)


class CollectorResult(BaseModel):
    """Batch result from one collector run."""
    run_at:           datetime = Field(default_factory=datetime.utcnow)
    articles_fetched: int
    articles_new:     int
    articles:         List[RawArticle]
    errors:           List[str] = Field(default_factory=list)


# ── Analyst Schemas (LLM JSON contract) ──────────────────────────────────────

def _normalize_entity_type(v: Any) -> Any:
    if isinstance(v, str):
        normalized = _ENTITY_TYPE_ALIASES.get(v.lower().strip(), v.lower().strip())
        return normalized
    return v


class Entity(BaseModel):
    """A named entity extracted from a news article."""
    id:      Optional[str] = Field(None, description="Unique slug, e.g. 'openai', 'eu-ai-act'")
    name:    str = Field(description="Canonical name, e.g. 'OpenAI', 'EU AI Act'")
    label:   str = Field(description="Node label from ontology: Company|Person|Technology|Regulation|Competitor|MarketTrend|Sector|Country|Event|MacroIndicator")
    type:    EntityType
    ticker:  Optional[str] = Field(None, description="Stock ticker if applicable")
    aliases: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict, description="Extra properties e.g. founded, hq, revenue")

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: Any) -> Any:
        return _normalize_entity_type(v)

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, v: Any) -> Any:
        # Capitalize first letter of each word, handle underscores
        if isinstance(v, str):
            return v.replace("_", " ").title().replace(" ", "")
        return v

    @model_validator(mode="after")
    def sync_type_label(self) -> "Entity":
        """Ensure type and label are consistent; generate id slug if missing."""
        import re
        # Generate slug from name if id missing
        if not self.id and self.name:
            slug = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")
            object.__setattr__(self, "id", slug)
        # Sync label from type if label is generic
        _type_to_label = {
            EntityType.COMPANY:         "Company",
            EntityType.PERSON:          "Person",
            EntityType.TECHNOLOGY:      "Technology",
            EntityType.REGULATION:      "Regulation",
            EntityType.COMPETITOR:      "Competitor",
            EntityType.MARKET_TREND:    "MarketTrend",
            EntityType.SECTOR:          "Sector",
            EntityType.COUNTRY:         "Country",
            EntityType.EVENT:           "Event",
            EntityType.MACRO_INDICATOR: "MacroIndicator",
            EntityType.NEWS:            "News",
        }
        if not self.label or self.label in ("", "Entity", "Unknown"):
            object.__setattr__(self, "label", _type_to_label.get(self.type, "Company"))
        return self


class CausalRelation(BaseModel):
    """A directed relationship extracted by the LLM."""
    from_id:          Optional[str] = Field(None, description="Source entity slug")
    from_entity:      str = Field(description="Source entity name")
    from_type:        EntityType
    to_id:            Optional[str] = Field(None, description="Target entity slug")
    to_entity:        str = Field(description="Target entity name")
    to_type:          EntityType

    @field_validator("from_type", "to_type", mode="before")
    @classmethod
    def normalize_types(cls, v: Any) -> Any:
        return _normalize_entity_type(v)

    type:             RelationType = Field(
        default=RelationType.CAUSES_IMPACT_ON,
        alias="type",
    )
    relation_type:    RelationType = Field(default=RelationType.CAUSES_IMPACT_ON)

    @field_validator("relation_type", "type", mode="before")
    @classmethod
    def normalize_relation_type(cls, v: Any) -> Any:
        valid = {r.value for r in RelationType}
        if isinstance(v, str):
            upper = v.upper().strip()
            if upper in valid:
                return upper
            # common aliases
            _rel_aliases = {
                "ACQUIRED_BY":          "ACQUIRED",
                "MERGE":                "ACQUIRED",
                "MERGES_WITH":          "ACQUIRED",
                "COMPETES":             "COMPETES_WITH",
                "COMPETE":              "COMPETES_WITH",
                "IMPACT":               "IMPACTS",
                "IMPACTS_ON":           "IMPACTS",
                "INFLUENCE":            "INFLUENCES",
                "LAUNCH":               "LAUNCHED",
                "LAUNCHES":             "LAUNCHED",
                "RECRUIT":              "RECRUITS_IN",
                "RECRUITS":             "RECRUITS_IN",
                "CAUSES":               "CAUSES_IMPACT_ON",
                "AFFECTS":              "CAUSES_IMPACT_ON",
                "LINKED_TO":            "SUPPLY_CHAIN_LINK",
                "SUPPLY_CHAIN":         "SUPPLY_CHAIN_LINK",
                "OPERATES":             "OPERATES_IN",
                "TRIGGERS":             "TRIGGERS_EVENT",
                "AFFECTS_INDICATOR":    "AFFECTS_INDICATOR",
            }
            mapped = _rel_aliases.get(upper)
            if mapped:
                return mapped
            return RelationType.CAUSES_IMPACT_ON.value
        return v

    @model_validator(mode="after")
    def sync_relation_types(self) -> "CausalRelation":
        """Keep type and relation_type in sync (both fields accepted from LLM)."""
        if self.type != RelationType.CAUSES_IMPACT_ON:
            object.__setattr__(self, "relation_type", self.type)
        elif self.relation_type != RelationType.CAUSES_IMPACT_ON:
            object.__setattr__(self, "type", self.relation_type)
        return self

    impact_direction: ImpactDirection = Field(default=ImpactDirection.UNCERTAIN)
    impact_score:     float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence:       float = Field(default=0.3, ge=0.0, le=1.0)
    reason:           str   = Field(default="", description="1-2 sentence causal explanation")
    time_horizon:     str   = Field(default="immediate")
    talan_relevant:   bool  = Field(default=False)
    sentiment:        float = Field(default=0.0, ge=-1.0, le=1.0, description="Sentiment of the relation")
    causality_score:  float = Field(default=0.3, ge=0.0, le=1.0, description="How causal (vs correlational)")
    evidence:         str   = Field(default="", description="Quoted text evidence from article")

    @field_validator("impact_score", "sentiment")
    @classmethod
    def round_score(cls, v: float) -> float:
        return round(v, 3)


class NewsAnalysis(BaseModel):
    """Complete structured analysis of a single news article — the LLM output contract."""
    article_external_id: str
    article_title:       str
    analysis_timestamp:  datetime = Field(default_factory=datetime.utcnow)

    # ── LLM extraction fields ─────────────────────────────────────────────────
    entities:         List[Entity]
    relations:        List[CausalRelation] = Field(default_factory=list)
    causal_relations: List[CausalRelation] = Field(default_factory=list)

    # ── Metadata ──────────────────────────────────────────────────────────────
    overall_sentiment:        float = Field(default=0.0, ge=-1.0, le=1.0)
    extraction_confidence:    float = Field(default=0.5, ge=0.0, le=1.0)
    detected_category:        str   = Field(default="other")

    # ── Legacy / summary fields (kept for backward compat) ───────────────────
    event_summary:            str   = Field(default="")
    event_type:               str   = Field(default="other")
    severity:                 float = Field(default=0.3, ge=0.0, le=1.0)
    urgency:                  str   = Field(default="low")
    talan_impact_score:       float = Field(default=0.0, ge=-1.0, le=1.0)
    talan_impact_reason:      str   = Field(default="")
    talan_action_recommended: Optional[str] = None
    affected_tickers:         List[str] = Field(default_factory=list)
    macro_indicators_affected: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def merge_relation_fields(self) -> "NewsAnalysis":
        """Keep relations and causal_relations in sync — accept either key from LLM."""
        merged = list({id(r): r for r in self.causal_relations + self.relations}.values())
        object.__setattr__(self, "causal_relations", merged)
        object.__setattr__(self, "relations", merged)
        return self


# ── World Model Schemas ───────────────────────────────────────────────────────

class KGNode(BaseModel):
    node_type:  EntityType
    name:       str
    slug:       Optional[str] = None
    label:      str = ""
    properties: Dict[str, Any] = Field(default_factory=dict)


class KGRelation(BaseModel):
    from_name:     str
    from_type:     EntityType
    to_name:       str
    to_type:       EntityType
    relation_type: RelationType
    properties:    Dict[str, Any] = Field(default_factory=dict)


class KGUpdatePayload(BaseModel):
    nodes:             List[KGNode]
    relations:         List[KGRelation]
    source_article_id: str
    timestamp:         datetime = Field(default_factory=datetime.utcnow)


# ── GNN Predictor Schemas ─────────────────────────────────────────────────────

class NodeFeatureVector(BaseModel):
    node_name:          str
    node_type:          EntityType
    embedding:          List[float]
    financial_features: List[float] = Field(default_factory=list)


class GNNPrediction(BaseModel):
    entity_name:       str
    entity_type:       EntityType
    predicted_impact:  float = Field(ge=-1.0, le=1.0)
    confidence:        float = Field(ge=0.0, le=1.0)
    propagation_hops:  int
    hidden_risk:       bool


class PropagationStep(BaseModel):
    """One node in a multi-hop causal chain reaching Talan."""
    node_name:    str
    node_type:    str
    relation_type: str
    reason:       str
    impact_score: float
    time_horizon: str
    # ── v3 propagation-engine fields ──────────────────────────────────────
    relation_strength:   float = Field(default=0.5, ge=0.0, le=1.0)
    business_relevance:  float = Field(default=0.5, ge=0.0, le=1.0)
    freshness_score:     float = Field(default=0.5, ge=0.0, le=1.0)
    edge_confidence:     float = Field(default=0.5, ge=0.0, le=1.0)
    is_generic_hub_step: bool  = False


class PropagationExplanation(BaseModel):
    """Structured rationale produced by ExplanationGenerator (§3 / §6).

    Designed to be scannable by Talan directors and BU managers — every
    field answers a specific question they ask:
      - headline               → "What's the one-line takeaway?"
      - causal_reasoning       → "Why does this matter to us?"
      - financial_impact_eur   → "How much money is at risk?"
      - recommended_action     → "What do we do, concretely?"
      - recommended_owner      → "Who owns this?"
      - deadline_label         → "By when?"
      - confidence_label       → "How sure are we?" (plain language)
    """
    headline:                str = ""             # one-line executive summary
    causal_reasoning:        str
    affected_business_unit:  str
    affected_sector:         str
    risk_category:           str  # competitive|regulatory|supply_chain|macro|cyber|talent|tech_disruption|growth_opportunity
    severity:                str  # low|medium|high|critical
    recommended_action:      str
    recommended_owner:       str = ""             # e.g. "Direction Banking BU", "DAF", "CISO"
    time_horizon:            str  # immediate|short|medium|long
    deadline_label:          str = ""             # e.g. "avant Q2 2026", "sous 2 semaines"
    financial_impact_eur:    str = ""             # e.g. "≈ €3-5M sur 6 mois"
    confidence_label:        str = ""             # plain language: "Forte" | "Moyenne" | "Spéculative"
    confidence_rationale:    str = ""
    business_relevance:      str = ""             # "Why this matters to Talan" — concrete business reason


class PropagationPath(BaseModel):
    """Full causal chain: source → [steps] → Talan, enriched with narrative."""
    source_name:        str
    source_type:        str
    steps:              List[PropagationStep]
    chain_score:        float
    chain_conf:         float
    hops:               int
    time_horizon_label: str
    narrative:          str
    # UX enrichment fields
    event_title:        str = ""
    key_impact:         str = ""
    source_evidence:    str = ""
    # ── v3 ranking outputs ────────────────────────────────────────────────
    business_plausibility:         float = Field(default=0.5, ge=0.0, le=1.0)
    causal_coherence:              float = Field(default=0.5, ge=0.0, le=1.0)
    path_specificity:              float = Field(default=0.5, ge=0.0, le=1.0)
    weighted_score:                float = 0.0
    impact_probability:            float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_business_impact_pct: float = 0.0
    confidence:                    float = Field(default=0.5, ge=0.0, le=1.0)
    uncertainty:                   str   = "medium"  # low|medium|high
    explanation:                   Optional[PropagationExplanation] = None


class ManualEntity(BaseModel):
    """A human-authored entity to inject into the KG for a simulation."""
    name:     str
    type:     str            # Company | Competitor | Sector | Country | Event | Regulation | Supplier | Client | Concept | Technology | MacroIndicator
    sector:   Optional[str] = None
    country:  Optional[str] = None
    ticker:   Optional[str] = None
    aliases:  List[str] = Field(default_factory=list)


class ManualRelation(BaseModel):
    """A human-authored causal edge to inject."""
    from_entity:    str
    to_entity:      str
    relation_type:  str = "CAUSES_IMPACT_ON"
    impact_score:   float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence:     float = Field(default=0.7, ge=0.0, le=1.0)
    reason:         str   = ""
    time_horizon:   str   = "short_term"
    evidence:       str   = ""


class QuickSimulationRequest(BaseModel):
    """Natural-language what-if request for non-technical users.

    The backend will:
      1. Call the LLM (same analyst as the live pipeline) to extract entities
         and causal relations from `event_text`.
      2. Augment the current Talan KG snapshot in-memory with the extracted
         entities + relations.
      3. Run predict_v3 on the augmented snapshot.
      4. If `commit=true`, persist the extracted entities/relations to Neo4j.
    """
    event_text:  str
    category:    Optional[str] = None   # hint for the LLM: 'competition' | 'regulation' | etc.


class ManualSimulationRequest(BaseModel):
    """A what-if scenario authored by a human analyst (low-level API).

    The backend will:
      1. Build an augmented KG snapshot = current Talan snapshot + these
         entities + these relations.
      2. Run predict_v3 on the augmented snapshot.
      3. If `commit=true`, also write the entities/relations to Neo4j
         (otherwise the simulation is transient — nothing is persisted).
    """
    title:        str
    summary:      Optional[str] = ""
    severity:     float = Field(default=0.5, ge=0.0, le=1.0)
    urgency:      str   = "medium"   # low|medium|high|critical
    source:       str   = "manual"
    entities:     List[ManualEntity]   = Field(default_factory=list)
    relations:    List[ManualRelation] = Field(default_factory=list)


class GNNInferenceResult(BaseModel):
    run_at:              datetime = Field(default_factory=datetime.utcnow)
    trigger_event:       str
    predictions:         List[GNNPrediction]
    talan_prediction:    Optional[GNNPrediction] = None
    systemic_risk_score: float = Field(ge=0.0, le=1.0)
    top_hidden_risks:    List[GNNPrediction] = Field(default_factory=list)
    propagation_paths:   List[PropagationPath] = Field(default_factory=list)
    # tgat_trained | tgat_random | heuristic
    inference_mode:      str = "tgat_trained"
    # ── v3 metadata ───────────────────────────────────────────────────────
    calibration_method:  str = "none"   # platt|isotonic|none
    filtered_path_count: int = 0
    rejected_path_count: int = 0


class ManualSimulationResult(BaseModel):
    """What the /market/simulate endpoint returns."""
    simulation_id:           str
    committed:               bool
    talan_impact_pct:        float
    talan_impact_prob:       float = Field(ge=0.0, le=1.0)
    systemic_risk_score:     float = Field(ge=0.0, le=1.0)
    propagation_paths:       List[PropagationPath] = Field(default_factory=list)
    filtered_path_count:     int = 0
    rejected_path_count:     int = 0
    augmented_node_count:    int = 0
    augmented_edge_count:    int = 0
    # LLM extraction metadata (populated by /market/simulate when using QuickSimulationRequest)
    extracted_entities:      List[str] = Field(default_factory=list)
    extracted_relations_count: int = 0
    llm_event_summary:       str = ""
    # Strategic advice generated by a dedicated explain LLM (separate from extraction LLM)
    strategic_advice:        str = ""
    # Raw LLM-extracted causal graph (nodes + edges from the event text only, no KG data)
    event_graph: Dict[str, Any] = Field(default_factory=dict)


# ── Report / Alert Schemas ────────────────────────────────────────────────────

class MarketAlert(BaseModel):
    alert_id:                  str
    generated_at:              datetime = Field(default_factory=datetime.utcnow)
    level:                     AlertLevel
    title:                     str
    summary:                   str
    affected_entities:         List[str]
    talan_impact_score:        float
    talan_recommended_action:  Optional[str] = None
    source_articles:           List[str] = Field(default_factory=list)
    gnn_hidden_risks:          List[str]  = Field(default_factory=list)


class MarketReport(BaseModel):
    report_id:           str
    generated_at:        datetime = Field(default_factory=datetime.utcnow)
    period_start:        datetime
    period_end:          datetime
    executive_summary:   str
    key_events:          List[NewsAnalysis]
    alerts:              List[MarketAlert]
    gnn_predictions:     Optional[GNNInferenceResult] = None
    talan_risk_level:    AlertLevel
    talan_impact_summary: str
    recommended_actions: List[str]
    kg_nodes_added:      int = 0
    kg_relations_added:  int = 0


# ── API Request / Response ────────────────────────────────────────────────────

class MarketAnalysisRequest(BaseModel):
    query:      Optional[str] = None
    tickers:    List[str] = Field(default_factory=list)
    force_gnn:  bool = False


class MarketAnalysisResponse(BaseModel):
    status:  str
    report:  Optional[MarketReport] = None
    alerts:  List[MarketAlert] = Field(default_factory=list)
    message: str = ""


class PipelineStatus(BaseModel):
    running:          bool
    cycle_running:    bool = False
    last_run_at:      Optional[datetime] = None
    next_run_at:      Optional[datetime] = None
    articles_in_db:   int = 0
    kg_nodes:         int = 0
    kg_relations:     int = 0
    last_report_id:   Optional[str] = None
    errors_last_run:  List[str] = Field(default_factory=list)


# ── Manager feedback ─────────────────────────────────────────────────────────


class FeedbackRating(str, Enum):
    RELEVANT  = "relevant"     # 👍 pertinente
    OFF_TOPIC = "off_topic"    # 👎 hors-sujet
    NUANCED   = "nuanced"      # 🤔 à nuancer


class FeedbackItemKind(str, Enum):
    PATH           = "path"
    RECOMMENDATION = "recommendation"
    ALERT          = "alert"
    SIMULATION     = "simulation"


class ManagerFeedbackCreate(BaseModel):
    """Payload sent by the UI when a manager rates an item."""
    item_kind:     FeedbackItemKind
    item_id:       str = Field(min_length=1, max_length=256)
    item_category: str = Field(default="", max_length=64)
    rating:        FeedbackRating
    comment:       str = Field(default="", max_length=2000)
    context:       Dict[str, Any] = Field(default_factory=dict)


class ManagerFeedback(BaseModel):
    """One feedback record returned by the API."""
    id:           str
    submitted_at: datetime
    user_id:      str
    user_role:    str = "manager"
    item_kind:    FeedbackItemKind
    item_id:      str
    item_category:str = ""
    rating:       FeedbackRating
    comment:      str = ""
    context:      Dict[str, Any] = Field(default_factory=dict)


class TrustScoreBucket(BaseModel):
    """Aggregated trust score for a given (item_kind, item_category) bucket."""
    item_kind:     FeedbackItemKind
    item_category: str = ""
    total:         int = 0
    relevant:      int = 0
    off_topic:     int = 0
    nuanced:       int = 0
    trust_score:   float = Field(default=0.0, ge=0.0, le=1.0)   # (relevant + 0.5·nuanced) / total
    label:         str = "insufficient"                          # high|medium|low|insufficient


class TrustScoresResponse(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    window_days:  int      = 90
    total_feedback: int    = 0
    buckets:      List[TrustScoreBucket] = Field(default_factory=list)
    overall:      Optional[TrustScoreBucket] = None


# ── Comex brief export ───────────────────────────────────────────────────────


class BriefExportRequest(BaseModel):
    period_days:        int  = Field(default=7, ge=1, le=90)
    include_paths:      bool = True
    include_alerts:     bool = True
    include_recommendations: bool = True
    include_forecast:   bool = True
    max_paths:          int  = Field(default=5, ge=1, le=20)
    max_alerts:         int  = Field(default=5, ge=1, le=20)
