"""Analyst Module — LLM-powered causal extraction from raw news articles.

For each unanalysed article the Analyst:
1. Calls the LLM with the ANALYST_SYSTEM_PROMPT (strict JSON output).
2. Validates the response against the NewsAnalysis Pydantic schema.
3. Persists the structured analysis to PostgreSQL (market_news_analyses).
4. Marks the source article as analysed.

Uses the same Groq/Gemini LLM as the rest of the platform (get_json_llm).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from functools import lru_cache as _lru_cache
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import get_json_llm, invoke_with_retry
from app.models.market_analysis_models import MarketNewsAnalysis
from app.prompts.market_analysis_prompts import ANALYST_SYSTEM_PROMPT
from app.schemas.market_analysis_schemas import NewsAnalysis

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 3000  # truncate article content before sending to LLM


# ── DB engine ─────────────────────────────────────────────────────────────────

@_lru_cache(maxsize=1)
def _get_engine():
    return create_engine(settings.database_url("hr"), pool_pre_ping=True)


# ── JSON extraction helpers ────────────────────────────────────────────────────

def _extract_json_from_response(raw: str) -> Optional[Dict[str, Any]]:
    """Robustly extract JSON from an LLM response that may contain markdown fences."""
    # Strip markdown code fences
    clean = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    # Try direct parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Try to find the first { ... } block
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("Could not extract JSON from LLM response: %s", clean[:200])
    return None


# ── Analyst ───────────────────────────────────────────────────────────────────

class NewsAnalyst:
    """LLM-powered analyst that extracts causal relations from news articles."""

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_json_llm()
        return self._llm

    def analyse_article(
        self,
        article_id: str,
        external_id: str,
        title: str,
        content: str,
        source: str,
        published_at: datetime,
        language: str = "en",
    ) -> Optional[NewsAnalysis]:
        """Analyse a single article. Returns None on failure."""
        t0 = time.perf_counter()

        # Truncate content to avoid token overflow
        truncated_content = content[:_MAX_CONTENT_CHARS]
        if len(content) > _MAX_CONTENT_CHARS:
            truncated_content += "\n[... content truncated]"

        # Build the prompt — use manual replacement to avoid .format() choking
        # on JSON curly braces inside the prompt template
        filled_prompt = (
            ANALYST_SYSTEM_PROMPT
            .replace("{title}", title)
            .replace("{source}", source)
            .replace("{published_at}", published_at.strftime("%Y-%m-%d %H:%M UTC"))
            .replace("{content}", truncated_content)
        )
        # Replace article_external_id placeholder in the prompt output expectation
        # (the LLM fills it from context — we validate below)

        messages = [
            SystemMessage(content="You are a JSON-only output machine. Return only valid JSON."),
            HumanMessage(content=filled_prompt),
        ]

        try:
            llm = self._get_llm()
            response = invoke_with_retry(llm, messages)
            raw_content = (
                response.content
                if hasattr(response, "content")
                else str(response)
            )
        except Exception as e:
            logger.error("LLM call failed for article %s: %s", external_id, e)
            return None

        # Parse JSON
        data = _extract_json_from_response(raw_content)
        if not data:
            return None

        # Ensure article_external_id is set correctly
        data["article_external_id"] = external_id
        data["article_title"] = title

        # Validate with Pydantic
        try:
            analysis = NewsAnalysis(**data)
        except Exception as e:
            logger.warning(
                "NewsAnalysis validation failed for %s: %s — raw: %s",
                external_id, e, str(data)[:300],
            )
            # Attempt minimal recovery
            try:
                analysis = _minimal_analysis(data, external_id, title)
            except Exception:
                return None

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "Analyst: article '%s' → severity=%.2f talan=%.2f in %.0fms",
            title[:60], analysis.severity, analysis.talan_impact_score, elapsed,
        )
        return analysis

    def analyse_batch(
        self, articles: List[Dict[str, Any]], delay_between_calls: float = 1.5
    ) -> Tuple[List[NewsAnalysis], List[str]]:
        """Analyse a batch of articles. Returns (analyses, failed_ids)."""
        analyses: List[NewsAnalysis] = []
        failed: List[str] = []

        for i, art in enumerate(articles):
            article_id = str(art.get("id", ""))
            external_id = str(art.get("external_id", ""))
            logger.info(
                "Analyst batch: %d/%d — %s", i + 1, len(articles), art.get("title", "")[:60]
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

            # Respect rate limits between calls
            if i < len(articles) - 1:
                time.sleep(delay_between_calls)

        logger.info(
            "Analyst batch done: %d/%d succeeded", len(analyses), len(articles)
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
            # Mark source article as analysed
            session.execute(
                text(
                    "UPDATE market_raw_articles SET analysed = true WHERE id = :aid"
                ),
                {"aid": article_id},
            )
            session.commit()

    def get_recent_analyses(
        self, hours: int = 24, min_talan_impact: float = 0.0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve recent analyses from DB for report generation."""
        engine = _get_engine()
        cutoff = datetime.utcnow().replace(
            hour=0, minute=0, second=0
        ) if hours >= 24 else None
        with Session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT a.*, "
                    "       r.url            AS article_url, "
                    "       r.source         AS article_source, "
                    "       r.published_at   AS article_published_at "
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
                elif hasattr(v, 'hex'):  # UUID
                    row_dict[k] = str(v)
                elif isinstance(v, Decimal) or k in _float_cols:
                    try:
                        row_dict[k] = float(v)
                    except (TypeError, ValueError):
                        pass
            result.append(row_dict)
        return result

    def get_unsynced_analyses(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Analyses not yet pushed to Neo4j."""
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


# ── Fallback minimal analysis ─────────────────────────────────────────────────

def _minimal_analysis(data: Dict[str, Any], external_id: str, title: str) -> NewsAnalysis:
    """Build a minimal valid NewsAnalysis when full validation fails."""
    from app.schemas.market_analysis_schemas import Entity, EntityType, ImpactDirection, CausalRelation, RelationType

    return NewsAnalysis(
        article_external_id=external_id,
        article_title=title,
        event_summary=data.get("event_summary", title[:100]),
        event_type=data.get("event_type", "other"),
        severity=float(data.get("severity", 0.3)),
        urgency=data.get("urgency", "low"),
        entities=_parse_entities(data.get("entities", [])),
        causal_relations=_parse_relations(data.get("causal_relations", [])),
        talan_impact_score=float(data.get("talan_impact_score", 0.0)),
        talan_impact_reason=data.get("talan_impact_reason", "Analyse incomplète"),
        talan_action_recommended=data.get("talan_action_recommended"),
        affected_tickers=data.get("affected_tickers", []),
        macro_indicators_affected=data.get("macro_indicators_affected", []),
    )


def _parse_entities(raw: List[Any]):
    from app.schemas.market_analysis_schemas import Entity, EntityType
    out = []
    for e in raw:
        if isinstance(e, dict):
            try:
                out.append(Entity(
                    name=e.get("name", "Unknown"),
                    type=EntityType(e.get("type", "company")),
                    ticker=e.get("ticker"),
                    aliases=e.get("aliases", []),
                ))
            except Exception:
                pass
    return out


def _parse_relations(raw: List[Any]):
    from app.schemas.market_analysis_schemas import (
        CausalRelation, EntityType, ImpactDirection, RelationType
    )
    out = []
    for r in raw:
        if isinstance(r, dict):
            try:
                out.append(CausalRelation(
                    from_entity=r.get("from_entity", "Unknown"),
                    from_type=EntityType(r.get("from_type", "company")),
                    to_entity=r.get("to_entity", "Unknown"),
                    to_type=EntityType(r.get("to_type", "company")),
                    relation_type=RelationType(r.get("relation_type", "CAUSES_IMPACT_ON")),
                    impact_direction=ImpactDirection(r.get("impact_direction", "uncertain")),
                    impact_score=float(r.get("impact_score", 0.0)),
                    confidence=float(r.get("confidence", 0.3)),
                    reason=r.get("reason", ""),
                    time_horizon=r.get("time_horizon", "immediate"),
                    talan_relevant=bool(r.get("talan_relevant", False)),
                ))
            except Exception:
                pass
    return out
