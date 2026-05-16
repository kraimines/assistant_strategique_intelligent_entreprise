"""
bulk_kg_inject.py — Bulk inject ALL analyzed articles into Neo4j KG.

This script bypasses the 10-article-per-run orchestrator limit and processes
ALL market_news_analyses rows that are either not yet synced, or forcibly re-syncs
all rows if --force is passed.

Usage:
    python bulk_kg_inject.py          # sync unsynced analyses only
    python bulk_kg_inject.py --force  # re-sync ALL analyses (wipes kg_synced flag)
    python bulk_kg_inject.py --limit 50  # process at most 50 rows
"""
from __future__ import annotations

import json
import logging
import sys
import os
import re

# ── make sure imports resolve when run directly ──────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bulk_kg_inject")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Arg parsing ──────────────────────────────────────────────────────────────

force  = "--force" in sys.argv
limit_arg = 9999
for i, arg in enumerate(sys.argv):
    if arg == "--limit" and i + 1 < len(sys.argv):
        limit_arg = int(sys.argv[i + 1])


# ── Config & DB ──────────────────────────────────────────────────────────────

from app.core.config import settings
from app.services.market_analysis.world_model import WorldModel
from app.schemas.market_analysis_schemas import (
    CausalRelation, Entity, EntityType, RelationType, NewsAnalysis,
)

engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
wm     = WorldModel()


def _load_rows(force: bool, limit: int):
    with Session(engine) as session:
        if force:
            session.execute(text("UPDATE market_news_analyses SET kg_synced = false"))
            session.commit()
            logger.info("Cleared kg_synced flag on all rows (--force)")

        rows = session.execute(
            text(
                "SELECT id, article_external_id, article_title, analysis_timestamp, "
                "event_summary, event_type, severity, urgency, entities, causal_relations, "
                "talan_impact_score, talan_impact_reason, talan_action_recommended, "
                "affected_tickers, macro_indicators_affected "
                "FROM market_news_analyses "
                "WHERE kg_synced = false "
                "ORDER BY analysis_timestamp ASC "
                "LIMIT :lim"
            ),
            {"lim": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


def _row_to_analysis(row: dict) -> NewsAnalysis:
    """Re-hydrate a DB row into a NewsAnalysis Pydantic object."""

    def _parse_json(val):
        if isinstance(val, (list, dict)):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return []
        return []

    raw_entities     = _parse_json(row.get("entities") or [])
    raw_relations    = _parse_json(row.get("causal_relations") or [])
    affected_tickers = _parse_json(row.get("affected_tickers") or [])
    macro_affected   = _parse_json(row.get("macro_indicators_affected") or [])

    # ── re-hydrate entities ──────────────────────────────────────────────────
    entities: list[Entity] = []
    for e in raw_entities:
        if not isinstance(e, dict):
            continue
        name = e.get("name") or ""
        if not name:
            continue
        raw_type = (e.get("type") or e.get("label") or "company").lower()
        type_map = {
            "company": EntityType.COMPANY, "competitor": EntityType.COMPETITOR,
            "technology": EntityType.TECHNOLOGY, "regulation": EntityType.REGULATION,
            "person": EntityType.PERSON, "sector": EntityType.SECTOR,
            "country": EntityType.COUNTRY, "event": EntityType.EVENT,
            "market_trend": EntityType.MARKET_TREND, "markettrend": EntityType.MARKET_TREND,
            "macro_indicator": EntityType.MACRO_INDICATOR, "macroindicator": EntityType.MACRO_INDICATOR,
            "news": EntityType.NEWS,
        }
        etype = type_map.get(raw_type, EntityType.COMPANY)
        label_map = {
            EntityType.COMPANY: "Company", EntityType.COMPETITOR: "Competitor",
            EntityType.TECHNOLOGY: "Technology", EntityType.REGULATION: "Regulation",
            EntityType.PERSON: "Person", EntityType.SECTOR: "Sector",
            EntityType.COUNTRY: "Country", EntityType.EVENT: "Event",
            EntityType.MARKET_TREND: "MarketTrend", EntityType.MACRO_INDICATOR: "MacroIndicator",
            EntityType.NEWS: "News",
        }
        # label may be stored in DB as "Company", "Technology", etc. — use it if valid
        stored_label = e.get("label") or ""
        valid_labels = set(label_map.values())
        label = stored_label if stored_label in valid_labels else label_map.get(etype, "Company")
        entities.append(Entity(
            id=e.get("id") or _slugify(name),
            name=name,
            label=label,
            type=etype,
            ticker=e.get("ticker"),
            aliases=e.get("aliases") or [],
            properties=e.get("properties") or {},
        ))

    # Build entity-name → type lookup for relation hydration
    entity_type_by_name: dict[str, EntityType] = {}
    for ent in raw_entities:
        if isinstance(ent, dict) and ent.get("name"):
            raw_t = (ent.get("type") or ent.get("label") or "company").lower()
            type_map2 = {
                "company": EntityType.COMPANY, "competitor": EntityType.COMPETITOR,
                "technology": EntityType.TECHNOLOGY, "regulation": EntityType.REGULATION,
                "person": EntityType.PERSON, "sector": EntityType.SECTOR,
                "country": EntityType.COUNTRY, "event": EntityType.EVENT,
                "market_trend": EntityType.MARKET_TREND, "markettrend": EntityType.MARKET_TREND,
                "macro_indicator": EntityType.MACRO_INDICATOR, "macroindicator": EntityType.MACRO_INDICATOR,
                "news": EntityType.NEWS,
            }
            entity_type_by_name[ent["name"]] = type_map2.get(raw_t, EntityType.COMPANY)

    # ── re-hydrate causal relations ──────────────────────────────────────────
    causal_relations: list[CausalRelation] = []
    for r in raw_relations:
        if not isinstance(r, dict):
            continue
        from_entity = r.get("from_entity") or ""
        to_entity   = r.get("to_entity") or ""
        if not from_entity or not to_entity:
            continue

        raw_rel = (r.get("relation_type") or r.get("type") or "CAUSES_IMPACT_ON").upper()
        rel_map = {
            "CAUSES_IMPACT_ON": RelationType.CAUSES_IMPACT_ON,
            "IMPACTS": RelationType.IMPACTS,
            "INFLUENCES": RelationType.INFLUENCES,
            "COMPETES_WITH": RelationType.COMPETES_WITH,
            "BELONGS_TO_SECTOR": RelationType.BELONGS_TO_SECTOR,
            "OPERATES_IN": RelationType.OPERATES_IN,
            "SUPPLY_CHAIN_LINK": RelationType.SUPPLY_CHAIN_LINK,
            "ACQUIRED": RelationType.ACQUIRED,
            "RECRUITS_IN": RelationType.RECRUITS_IN,
            "SERVES_SECTOR": RelationType.BELONGS_TO_SECTOR,
            "AFFECTS_INDICATOR": RelationType.AFFECTS_INDICATOR,
            "TRIGGERS_EVENT": RelationType.TRIGGERS_EVENT,
            "MENTIONS": RelationType.MENTIONS,
            "LAUNCHED": RelationType.LAUNCHED,
        }
        rel_type = rel_map.get(raw_rel, RelationType.CAUSES_IMPACT_ON)

        # Derive from_type / to_type from entity lookup, or from stored value, or default
        def _etype(name: str, stored: str | None) -> EntityType:
            if name in entity_type_by_name:
                return entity_type_by_name[name]
            if stored:
                raw = stored.lower()
                return {
                    "company": EntityType.COMPANY, "competitor": EntityType.COMPETITOR,
                    "technology": EntityType.TECHNOLOGY, "regulation": EntityType.REGULATION,
                    "person": EntityType.PERSON, "sector": EntityType.SECTOR,
                    "country": EntityType.COUNTRY, "event": EntityType.EVENT,
                    "market_trend": EntityType.MARKET_TREND, "markettrend": EntityType.MARKET_TREND,
                    "macro_indicator": EntityType.MACRO_INDICATOR, "macroindicator": EntityType.MACRO_INDICATOR,
                    "news": EntityType.NEWS,
                }.get(raw, EntityType.COMPANY)
            # Talan is always a company
            if "talan" in name.lower():
                return EntityType.COMPANY
            return EntityType.COMPANY

        from_type = _etype(from_entity, r.get("from_type"))
        to_type   = _etype(to_entity,   r.get("to_type"))

        causal_relations.append(CausalRelation(
            from_entity=from_entity,
            from_type=from_type,
            to_entity=to_entity,
            to_type=to_type,
            relation_type=rel_type,
            impact_score=float(r.get("impact_score") or 0.0),
            sentiment=float(r.get("sentiment") or 0.0),
            confidence=float(r.get("confidence") or 0.5),
            causality_score=float(r.get("causality_score") or 0.5),
            reason=r.get("reason") or "",
            evidence=r.get("evidence") or "",
            time_horizon=r.get("time_horizon") or "medium_term",
            talan_relevant=bool(r.get("talan_relevant", False)),
        ))

    return NewsAnalysis(
        id=str(row["id"]),
        article_external_id=row.get("article_external_id") or "",
        article_title=row.get("article_title") or "",
        analysis_timestamp=row.get("analysis_timestamp"),
        event_summary=row.get("event_summary") or "",
        event_type=row.get("event_type") or "general",
        severity=float(row.get("severity") or 0.0),
        urgency=row.get("urgency") or "low",
        talan_impact_score=float(row.get("talan_impact_score") or 0.0),
        talan_impact_reason=row.get("talan_impact_reason") or "",
        talan_action_recommended=row.get("talan_action_recommended"),
        affected_tickers=affected_tickers or [],
        macro_indicators_affected=macro_affected or [],
        entities=entities,
        causal_relations=causal_relations,
    )


def _mark_synced(ids: list[str]) -> None:
    if not ids:
        return
    with Session(engine) as session:
        session.execute(
            text("UPDATE market_news_analyses SET kg_synced = true WHERE id::text = ANY(:ids)"),
            {"ids": ids},
        )
        session.commit()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    wm.ensure_schema()
    wm.ensure_talan_node()

    logger.info("Loading unsynced analyses (limit=%d, force=%s)…", limit_arg, force)
    rows = _load_rows(force=force, limit=limit_arg)
    logger.info("Found %d rows to process", len(rows))

    if not rows:
        logger.info("Nothing to sync. Use --force to re-sync all.")
        return

    ok_ids, failed_ids = [], []
    total_nodes = total_rels = 0

    for i, row in enumerate(rows, 1):
        title = (row.get("article_title") or "")[:70]
        try:
            analysis = _row_to_analysis(row)

            # Skip rows with zero entities/relations — nothing to push
            if not analysis.entities and not analysis.causal_relations:
                logger.debug("[%d/%d] SKIP (no entities): %s", i, len(rows), title)
                ok_ids.append(str(row["id"]))
                continue

            payload = wm.update_from_analysis(analysis)
            total_nodes += len(payload.nodes)
            total_rels  += len(payload.relations)
            ok_ids.append(str(row["id"]))

            logger.info(
                "[%d/%d] OK  +%d nodes +%d rels — %s",
                i, len(rows),
                len(payload.nodes), len(payload.relations),
                title,
            )

        except Exception as exc:
            logger.warning("[%d/%d] FAIL %s — %s", i, len(rows), title, exc)
            failed_ids.append(str(row["id"]))

        # Batch-commit every 10 rows
        if len(ok_ids) % 10 == 0:
            _mark_synced(ok_ids[-10:])

    # Final batch
    _mark_synced(ok_ids)

    logger.info(
        "\n===== BULK INJECT COMPLETE =====\n"
        "  Rows processed : %d / %d\n"
        "  Failed         : %d\n"
        "  KG nodes added : %d\n"
        "  KG rels added  : %d",
        len(ok_ids), len(rows), len(failed_ids),
        total_nodes, total_rels,
    )

    # Print updated KG stats
    try:
        stats = wm.get_stats()
        logger.info(
            "\n===== KG STATS AFTER INJECT =====\n"
            "  Total nodes : %d\n"
            "  Total rels  : %d\n"
            "  Node types  : %s",
            stats.total_nodes,
            stats.total_relations,
            dict(stats.nodes_by_label),
        )
    except Exception as e:
        logger.warning("Could not fetch KG stats: %s", e)


if __name__ == "__main__":
    main()
