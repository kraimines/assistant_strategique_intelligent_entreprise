"""Analyst Module v2 — Cognitive Extraction Engine.

Pipeline per article:
1. Prefer Anthropic Claude (tool-use / structured output) if ANTHROPIC_API_KEY is set.
2. Fall back to Groq/Gemini JSON-mode if Claude is unavailable.
3. Validate against the NewsAnalysis Pydantic schema (v2 — richer ontology).
4. Persist structured analysis to PostgreSQL (market_news_analyses).
5. Mark source article as analysed.

New in v2:
- Anthropic tool-use for guaranteed structured JSON output
- Entity slug deduplication (canonical name → slug)
- Expanded ontology: Company | Person | Technology | Regulation | Competitor |
  MarketTrend | Sector | Country | Event | MacroIndicator
- Expanded relations: ACQUIRED | COMPETES_WITH | INFLUENCES | LAUNCHED | IMPACTS |
  RECRUITS_IN | (+ all v1 relations)
- Temporal metadata: valid_from, extraction_confidence on every extraction
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from functools import lru_cache as _lru_cache
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import get_json_llm, invoke_with_retry
from app.models.market_analysis_models import MarketNewsAnalysis
from app.prompts.market_analysis_prompts import ANALYST_SYSTEM_PROMPT
from app.schemas.market_analysis_schemas import (
    CausalRelation, Entity, EntityType, ImpactDirection,
    NewsAnalysis, RelationType,
)

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 1200   # qwen3-32b: 6000 TPM total (input+output). ~1200 chars ≈ 400 tokens input

# ── Anthropic availability check ──────────────────────────────────────────────

_ANTHROPIC_AVAILABLE: Optional[bool] = None

def _has_anthropic() -> bool:
    global _ANTHROPIC_AVAILABLE
    if _ANTHROPIC_AVAILABLE is not None:
        return _ANTHROPIC_AVAILABLE
    try:
        import anthropic  # noqa: F401
        _ANTHROPIC_AVAILABLE = bool(settings.anthropic_api_key)
    except ImportError:
        _ANTHROPIC_AVAILABLE = False
    return _ANTHROPIC_AVAILABLE


# ── Anthropic tool schema (structured output) ─────────────────────────────────

_EXTRACTION_TOOL = {
    "name": "extract_knowledge_graph",
    "description": (
        "Extract all entities, relations and metadata from a news article "
        "to populate a strategic intelligence Knowledge Graph."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "description": "Named entities found in the article",
                "items": {
                    "type": "object",
                    "required": ["id", "name", "label", "type"],
                    "properties": {
                        "id":      {"type": "string", "description": "Unique slug e.g. 'openai'"},
                        "name":    {"type": "string"},
                        "label":   {"type": "string", "enum": [
                            "Company", "Person", "Technology", "Regulation",
                            "Competitor", "MarketTrend", "Sector", "Country",
                            "Event", "MacroIndicator",
                        ]},
                        "type":    {"type": "string", "enum": [
                            "company", "person", "technology", "regulation",
                            "competitor", "market_trend", "sector", "country",
                            "event", "macro_indicator",
                        ]},
                        "ticker":  {"type": ["string", "null"]},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "properties": {
                            "type": "object",
                            "properties": {
                                "description":          {"type": "string"},
                                "relevance_to_talan":   {"type": "string", "enum": ["high", "medium", "low"]},
                            },
                        },
                    },
                },
            },
            "relations": {
                "type": "array",
                "description": "Directed relations between entities",
                "items": {
                    "type": "object",
                    "required": ["from_entity", "to_entity", "type"],
                    "properties": {
                        "from_id":        {"type": "string"},
                        "from_entity":    {"type": "string"},
                        "from_type":      {"type": "string"},
                        "to_id":          {"type": "string"},
                        "to_entity":      {"type": "string"},
                        "to_type":        {"type": "string"},
                        "type":           {"type": "string", "enum": [
                            "ACQUIRED", "COMPETES_WITH", "INFLUENCES", "LAUNCHED",
                            "IMPACTS", "RECRUITS_IN", "CAUSES_IMPACT_ON",
                            "BELONGS_TO_SECTOR", "SUPPLY_CHAIN_LINK", "OPERATES_IN",
                            "TRIGGERS_EVENT", "AFFECTS_INDICATOR",
                        ]},
                        "impact_score":   {"type": "number", "minimum": -1.0, "maximum": 1.0},
                        "sentiment":      {"type": "number", "minimum": -1.0, "maximum": 1.0},
                        "confidence":     {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "causality_score":{"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "reason":         {"type": "string"},
                        "evidence":       {"type": "string"},
                        "time_horizon":   {"type": "string"},
                        "talan_relevant": {"type": "boolean"},
                    },
                },
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "overall_sentiment":     {"type": "number", "minimum": -1.0, "maximum": 1.0},
                    "extraction_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "detected_category":     {"type": "string"},
                    "event_summary":         {"type": "string"},
                    "event_type":            {"type": "string"},
                    "severity":              {"type": "number"},
                    "urgency":               {"type": "string"},
                    "talan_impact_score":    {"type": "number"},
                    "talan_impact_reason":   {"type": "string"},
                    "talan_action_recommended": {"type": ["string", "null"]},
                    "affected_tickers":      {"type": "array", "items": {"type": "string"}},
                    "macro_indicators_affected": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "required": ["entities", "relations", "metadata"],
    },
}


# ── DB engine ─────────────────────────────────────────────────────────────────

@_lru_cache(maxsize=1)
def _get_engine():
    return create_engine(settings.database_url("hr"), pool_pre_ping=True)


# ── JSON extraction helpers ────────────────────────────────────────────────────

def _extract_json_from_response(raw: str) -> Optional[Dict[str, Any]]:
    """Robustly extract JSON from an LLM response that may contain markdown fences."""
    clean = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            pass
    logger.warning("Could not extract JSON from response: %s", clean[:200])
    return None


def _slugify(name: str) -> str:
    """Generate a unique slug from an entity name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Anthropic extraction ──────────────────────────────────────────────────────

def _extract_with_anthropic(
    title: str, source: str, published_at: datetime, content: str
) -> Optional[Dict[str, Any]]:
    """Use Claude tool-use for guaranteed structured JSON extraction."""
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)

        user_message = (
            ANALYST_SYSTEM_PROMPT
            .replace("{title}", title)
            .replace("{source}", source)
            .replace("{published_at}", published_at.strftime("%Y-%m-%d %H:%M UTC"))
            .replace("{content}", content[:_MAX_CONTENT_CHARS])
        )

        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            tools=[_EXTRACTION_TOOL],
            tool_choice={"type": "any"},  # Force tool use
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract tool_use block
        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_knowledge_graph":
                tool_input = block.input
                # Flatten tool response into NewsAnalysis format
                meta = tool_input.get("metadata", {})
                return {
                    "entities":                   tool_input.get("entities", []),
                    "relations":                  tool_input.get("relations", []),
                    "overall_sentiment":          meta.get("overall_sentiment", 0.0),
                    "extraction_confidence":      meta.get("extraction_confidence", 0.7),
                    "detected_category":          meta.get("detected_category", "other"),
                    "event_summary":              meta.get("event_summary", ""),
                    "event_type":                 meta.get("event_type", "other"),
                    "severity":                   meta.get("severity", 0.3),
                    "urgency":                    meta.get("urgency", "low"),
                    "talan_impact_score":         meta.get("talan_impact_score", 0.0),
                    "talan_impact_reason":        meta.get("talan_impact_reason", ""),
                    "talan_action_recommended":   meta.get("talan_action_recommended"),
                    "affected_tickers":           meta.get("affected_tickers", []),
                    "macro_indicators_affected":  meta.get("macro_indicators_affected", []),
                }
        logger.warning("Anthropic: no tool_use block in response")
        return None

    except Exception as e:
        logger.error("Anthropic extraction failed: %s", e)
        return None


# ── Groq/Gemini extraction (fallback) ─────────────────────────────────────────

def _extract_with_groq(
    title: str, source: str, published_at: datetime, content: str
) -> Optional[Dict[str, Any]]:
    """Use existing Groq/Gemini JSON LLM as fallback."""
    filled_prompt = (
        ANALYST_SYSTEM_PROMPT
        .replace("{title}", title)
        .replace("{source}", source)
        .replace("{published_at}", published_at.strftime("%Y-%m-%d %H:%M UTC"))
        .replace("{content}", content[:_MAX_CONTENT_CHARS])
    )
    messages = [
        SystemMessage(content="You are a JSON-only output machine. Return only valid JSON."),
        HumanMessage(content=filled_prompt),
    ]
    try:
        llm = get_json_llm()
        response = invoke_with_retry(llm, messages)
        raw = response.content if hasattr(response, "content") else str(response)
        return _extract_json_from_response(raw)
    except Exception as e:
        logger.error("Groq/Gemini extraction failed: %s", e)
        return None


# ── Analyst ───────────────────────────────────────────────────────────────────

class NewsAnalyst:
    """Cognitive extraction engine — Claude (primary) → Groq/Gemini (fallback)."""

    def __init__(self):
        self._use_anthropic = _has_anthropic()
        if self._use_anthropic:
            logger.info("NewsAnalyst: using Anthropic Claude (%s)", settings.anthropic_model)
        else:
            logger.info("NewsAnalyst: using Groq/Gemini (Anthropic not available)")

    def analyse_article(
        self,
        article_id:   str,
        external_id:  str,
        title:        str,
        content:      str,
        source:       str,
        published_at: datetime,
        language:     str = "en",
    ) -> Optional[NewsAnalysis]:
        """Analyse a single article. Returns None on failure."""
        t0 = time.perf_counter()

        # ── Step 1: LLM extraction ────────────────────────────────────────────
        data: Optional[Dict[str, Any]] = None
        if self._use_anthropic:
            data = _extract_with_anthropic(title, source, published_at, content)
        if data is None:
            # Fallback to Groq/Gemini
            data = _extract_with_groq(title, source, published_at, content)
        if data is None:
            logger.error("All LLM backends failed for article %s", external_id)
            return None

        # ── Step 2: Inject article identity ───────────────────────────────────
        data["article_external_id"] = external_id
        data["article_title"]       = title

        # ── Step 3: Entity deduplication + slug generation ────────────────────
        data = _dedup_entities(data)

        # ── Step 4: Validate with Pydantic ────────────────────────────────────
        try:
            analysis = NewsAnalysis(**data)
        except Exception as e:
            logger.warning(
                "NewsAnalysis validation failed for %s: %s — attempting recovery",
                external_id, e,
            )
            try:
                analysis = _minimal_analysis(data, external_id, title)
            except Exception as e2:
                logger.error("Recovery also failed for %s: %s", external_id, e2)
                return None

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "Analyst [%s]: '%s' → entities=%d relations=%d talan=%.2f in %.0fms",
            "Claude" if self._use_anthropic else "Groq",
            title[:60], len(analysis.entities), len(analysis.causal_relations),
            analysis.talan_impact_score, elapsed,
        )
        return analysis

    def analyse_batch(
        self,
        articles: List[Dict[str, Any]],
        delay_between_calls: float = 1.2,
    ) -> Tuple[List[NewsAnalysis], List[str]]:
        """Analyse a batch of articles. Returns (analyses, failed_ids)."""
        analyses: List[NewsAnalysis] = []
        failed: List[str] = []

        for i, art in enumerate(articles):
            article_id  = str(art.get("id", ""))
            external_id = str(art.get("external_id", ""))
            logger.info(
                "Analyst batch %d/%d — %s", i + 1, len(articles), art.get("title", "")[:60]
            )
            analysis = self.analyse_article(
                article_id=article_id,
                external_id=external_id,
                title=art.get("title", ""),
                content=art.get("content", ""),
                source=art.get("source", ""),
                published_at=art.get("published_at") or datetime.utcnow(),
                language=art.get("language", "en"),
            )
            if analysis:
                analyses.append(analysis)
                self._persist_analysis(article_id, analysis)
            else:
                failed.append(article_id or external_id)

            if i < len(articles) - 1:
                time.sleep(delay_between_calls)

        logger.info(
            "Analyst batch done: %d/%d succeeded (%d failed)",
            len(analyses), len(articles), len(failed),
        )
        return analyses, failed

    def _persist_analysis(self, article_id: str, analysis: NewsAnalysis) -> None:
        """Save a NewsAnalysis to the market_news_analyses table."""
        engine = _get_engine()
        with Session(engine) as session:
            row = MarketNewsAnalysis(
                article_id=article_id,
                article_external_id=analysis.article_external_id,
                article_title=analysis.article_title,
                analysis_timestamp=analysis.analysis_timestamp,
                event_summary=analysis.event_summary,
                event_type=analysis.event_type,
                severity=analysis.severity,
                urgency=analysis.urgency,
                entities=[e.model_dump() for e in analysis.entities],
                causal_relations=[r.model_dump() for r in analysis.causal_relations],
                talan_impact_score=analysis.talan_impact_score,
                talan_impact_reason=analysis.talan_impact_reason,
                talan_action_recommended=analysis.talan_action_recommended,
                affected_tickers=analysis.affected_tickers,
                macro_indicators_affected=analysis.macro_indicators_affected,
            )
            session.add(row)
            session.execute(
                text("UPDATE market_raw_articles SET analysed = true WHERE id = :aid"),
                {"aid": article_id},
            )
            session.commit()

    def get_recent_analyses(
        self, hours: int = 24, min_talan_impact: float = 0.0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        engine = _get_engine()
        with Session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT a.*, "
                    "       r.url          AS article_url, "
                    "       r.source       AS article_source, "
                    "       r.published_at AS article_published_at "
                    "FROM market_news_analyses a "
                    "LEFT JOIN market_raw_articles r ON r.id::text = a.article_id::text "
                    "WHERE a.analysis_timestamp >= NOW() - (INTERVAL '1 hour' * :hrs) "
                    "  AND a.talan_impact_score >= :min_impact "
                    "ORDER BY a.talan_impact_score DESC, a.analysis_timestamp DESC "
                    "LIMIT :lim"
                ),
                {"hrs": hours, "min_impact": min_talan_impact, "lim": limit},
            ).mappings().all()
        from decimal import Decimal
        _float_cols = {"severity", "talan_impact_score"}
        result = []
        for r in rows:
            row_dict = dict(r)
            for k, v in row_dict.items():
                if isinstance(v, datetime):
                    row_dict[k] = v.isoformat()
                elif hasattr(v, "hex"):
                    row_dict[k] = str(v)
                elif isinstance(v, Decimal) or k in _float_cols:
                    try:
                        row_dict[k] = float(v)
                    except (TypeError, ValueError):
                        pass
            result.append(row_dict)
        return result

    def get_unsynced_analyses(self, limit: int = 100) -> List[Dict[str, Any]]:
        engine = _get_engine()
        with Session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT * FROM market_news_analyses "
                    "WHERE kg_synced = false "
                    "ORDER BY analysis_timestamp ASC "
                    "LIMIT :lim"
                ),
                {"lim": limit},
            ).mappings().all()
        return [dict(r) for r in rows]

    def mark_kg_synced(self, analysis_ids: List[str]) -> None:
        if not analysis_ids:
            return
        engine = _get_engine()
        with Session(engine) as session:
            session.execute(
                text(
                    "UPDATE market_news_analyses SET kg_synced = true "
                    "WHERE id::text = ANY(:ids)"
                ),
                {"ids": analysis_ids},
            )
            session.commit()


# ── Entity deduplication ──────────────────────────────────────────────────────

def _dedup_entities(data: Dict[str, Any]) -> Dict[str, Any]:
    """Deduplicate entities by slug and fill missing slugs."""
    raw_entities = data.get("entities", [])
    if not isinstance(raw_entities, list):
        return data

    seen_slugs: Dict[str, Dict] = {}
    for ent in raw_entities:
        if not isinstance(ent, dict):
            continue
        name = ent.get("name", "")
        if not name:
            continue
        slug = ent.get("id") or _slugify(name)
        ent["id"] = slug
        if slug not in seen_slugs:
            seen_slugs[slug] = ent
        else:
            # Merge aliases
            existing_aliases = seen_slugs[slug].get("aliases", [])
            new_aliases = ent.get("aliases", [])
            seen_slugs[slug]["aliases"] = list(set(existing_aliases + new_aliases))

    data["entities"] = list(seen_slugs.values())

    # Also fill from_id / to_id on relations
    relations_key = "relations" if "relations" in data else "causal_relations"
    for rel in data.get(relations_key, []):
        if not isinstance(rel, dict):
            continue
        if not rel.get("from_id") and rel.get("from_entity"):
            rel["from_id"] = _slugify(rel["from_entity"])
        if not rel.get("to_id") and rel.get("to_entity"):
            rel["to_id"] = _slugify(rel["to_entity"])

    return data


# ── Fallback minimal analysis ─────────────────────────────────────────────────

def _minimal_analysis(
    data: Dict[str, Any], external_id: str, title: str
) -> NewsAnalysis:
    """Build a minimal valid NewsAnalysis when full validation fails."""
    return NewsAnalysis(
        article_external_id=external_id,
        article_title=title,
        event_summary=data.get("event_summary", title[:100]),
        event_type=data.get("event_type", "other"),
        severity=float(data.get("severity", 0.3)),
        urgency=data.get("urgency", "low"),
        entities=_parse_entities(data.get("entities", [])),
        causal_relations=_parse_relations(
            data.get("relations") or data.get("causal_relations", [])
        ),
        talan_impact_score=float(data.get("talan_impact_score", 0.0)),
        talan_impact_reason=data.get("talan_impact_reason", "Analyse incomplète"),
        talan_action_recommended=data.get("talan_action_recommended"),
        affected_tickers=data.get("affected_tickers", []),
        macro_indicators_affected=data.get("macro_indicators_affected", []),
        overall_sentiment=float(data.get("overall_sentiment", 0.0)),
        extraction_confidence=float(data.get("extraction_confidence", 0.3)),
        detected_category=data.get("detected_category", "other"),
    )


def _parse_entities(raw: List[Any]) -> List[Entity]:
    out = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        try:
            out.append(Entity(
                id=e.get("id") or _slugify(e.get("name", "unknown")),
                name=e.get("name", "Unknown"),
                label=e.get("label", "Company"),
                type=EntityType(
                    e.get("type", "company") if e.get("type") in {et.value for et in EntityType}
                    else "company"
                ),
                ticker=e.get("ticker"),
                aliases=e.get("aliases", []),
                properties=e.get("properties", {}),
            ))
        except Exception:
            pass
    return out


def _parse_relations(raw: List[Any]) -> List[CausalRelation]:
    valid_relations = {r.value for r in RelationType}
    valid_types     = {et.value for et in EntityType}
    out = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        try:
            rel_type_raw = str(r.get("type") or r.get("relation_type") or "CAUSES_IMPACT_ON").upper()
            rel_type = rel_type_raw if rel_type_raw in valid_relations else "CAUSES_IMPACT_ON"

            from_type_raw = str(r.get("from_type", "company")).lower()
            to_type_raw   = str(r.get("to_type", "company")).lower()
            from_type = from_type_raw if from_type_raw in valid_types else "company"
            to_type   = to_type_raw   if to_type_raw   in valid_types else "company"

            out.append(CausalRelation(
                from_id=r.get("from_id") or _slugify(r.get("from_entity", "unknown")),
                from_entity=r.get("from_entity", "Unknown"),
                from_type=EntityType(from_type),
                to_id=r.get("to_id") or _slugify(r.get("to_entity", "unknown")),
                to_entity=r.get("to_entity", "Unknown"),
                to_type=EntityType(to_type),
                relation_type=RelationType(rel_type),
                type=RelationType(rel_type),
                impact_direction=ImpactDirection(
                    r.get("impact_direction", "uncertain")
                    if r.get("impact_direction") in {"positive", "negative", "neutral", "uncertain"}
                    else "uncertain"
                ),
                impact_score=float(r.get("impact_score", 0.0)),
                sentiment=float(r.get("sentiment", 0.0)),
                confidence=float(r.get("confidence", 0.3)),
                causality_score=float(r.get("causality_score", 0.3)),
                reason=r.get("reason", ""),
                evidence=r.get("evidence", ""),
                time_horizon=r.get("time_horizon", "immediate"),
                talan_relevant=bool(r.get("talan_relevant", False)),
            ))
        except Exception as ex:
            logger.debug("Relation parse error: %s — %s", ex, r)
    return out
