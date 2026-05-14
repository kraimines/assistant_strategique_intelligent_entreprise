"""World Model v2 — Heterogeneous Temporal Knowledge Graph (Neo4j).

Node types (v2 ontology):
    Company | Person | Technology | Regulation | Competitor |
    MarketTrend | Sector | Country | Event | MacroIndicator | News

Relation types (v2):
    ACQUIRED | COMPETES_WITH | INFLUENCES | LAUNCHED | IMPACTS | RECRUITS_IN
    CAUSES_IMPACT_ON | BELONGS_TO_SECTOR | SUPPLY_CHAIN_LINK | OPERATES_IN
    TRIGGERS_EVENT | AFFECTS_INDICATOR | MENTIONS

All nodes carry:
    - slug (unique, kebab-case) → entity resolution
    - created_at, updated_at → temporal tracking
    - source_articles[] → provenance

CAUSES_IMPACT_ON / IMPACTS edges carry full temporal versioning:
    - impact_score, confidence, sentiment, causality_score
    - timestamp, time_horizon, source_article
    - history[] → time-series accumulation
    - evidence → quoted text fragment

PageRank: uses simplified Cypher-based PageRank or Neo4j GDS if available.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable

from app.core.config import settings
from app.schemas.market_analysis_schemas import (
    CausalRelation, Entity, EntityType, KGNode, KGRelation,
    KGUpdatePayload, NewsAnalysis, RelationType,
)

logger = logging.getLogger(__name__)


# ── Label mapping ─────────────────────────────────────────────────────────────

_ENTITY_TYPE_TO_LABEL: Dict[str, str] = {
    EntityType.COMPANY.value:         "Company",
    EntityType.PERSON.value:          "Person",
    EntityType.TECHNOLOGY.value:      "Technology",
    EntityType.REGULATION.value:      "Regulation",
    EntityType.COMPETITOR.value:      "Competitor",
    EntityType.MARKET_TREND.value:    "MarketTrend",
    EntityType.SECTOR.value:          "Sector",
    EntityType.COUNTRY.value:         "Country",
    EntityType.EVENT.value:           "Event",
    EntityType.MACRO_INDICATOR.value: "MacroIndicator",
    EntityType.NEWS.value:            "News",
}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Cypher templates ──────────────────────────────────────────────────────────
# NOTE: placeholders __LABEL__ and __REL_TYPE__ are replaced at call time via
# .replace().  All Cypher braces are single — these are plain strings, NOT
# f-strings, so {{ would reach Neo4j literally.

def _merge_node_safe_cypher(label: str) -> str:
    return (
        "MERGE (n:" + label + " {slug: $slug})\n"
        "ON CREATE SET\n"
        "    n.name            = $name,\n"
        "    n.slug            = $slug,\n"
        "    n.ticker          = $ticker,\n"
        "    n.aliases         = $aliases,\n"
        "    n.source_articles = [$source_article],\n"
        "    n.created_at      = $now,\n"
        "    n.valid_from      = $now\n"
        "ON MATCH SET\n"
        "    n.name            = CASE WHEN $name <> '' THEN $name ELSE n.name END,\n"
        "    n.ticker          = CASE WHEN $ticker IS NOT NULL THEN $ticker ELSE n.ticker END,\n"
        "    n.updated_at      = $now\n"
        "RETURN n"
    )


def _merge_causal_rel_cypher(rel_type: str) -> str:
    """Upsert a temporal causal edge.

    v3 attributes (set or refreshed on every write):
      - relation_strength : pulled from CompatibilityRule (alpha) at write time
      - evidence_quality  : derived from confidence band
      - freshness_score   : computed on read (not persisted here — it depends on `now`)
    """
    return (
        "MATCH (a {slug: $from_slug}), (b {slug: $to_slug})\n"
        "OPTIONAL MATCH (rule:CompatibilityRule {\n"
        "    rel_type:  '" + rel_type + "',\n"
        "    src_label: labels(a)[0],\n"
        "    dst_label: labels(b)[0]\n"
        "})\n"
        "MERGE (a)-[r:" + rel_type + " {source_article: $source_article}]->(b)\n"
        "ON CREATE SET\n"
        "    r.impact_score      = $impact_score,\n"
        "    r.sentiment         = $sentiment,\n"
        "    r.confidence        = $confidence,\n"
        "    r.causality_score   = $causality_score,\n"
        "    r.reason            = $reason,\n"
        "    r.evidence          = $evidence,\n"
        "    r.time_horizon      = $time_horizon,\n"
        "    r.talan_relevant    = $talan_relevant,\n"
        "    r.timestamp         = $timestamp,\n"
        "    r.valid_from        = $timestamp,\n"
        "    r.history           = [$impact_score],\n"
        "    r.relation_strength = COALESCE(rule.alpha, 0.5),\n"
        "    r.evidence_quality  = CASE\n"
        "        WHEN COALESCE($confidence,0) >= 0.75 THEN 'primary'\n"
        "        WHEN COALESCE($confidence,0) >= 0.45 THEN 'secondary'\n"
        "        ELSE 'tertiary'\n"
        "    END\n"
        "ON MATCH SET\n"
        "    r.impact_score      = $impact_score,\n"
        "    r.sentiment         = $sentiment,\n"
        "    r.confidence        = $confidence,\n"
        "    r.reason            = $reason,\n"
        "    r.evidence          = $evidence,\n"
        "    r.timestamp         = $timestamp,\n"
        "    r.history           = r.history + [$impact_score],\n"
        "    r.relation_strength = COALESCE(r.relation_strength, COALESCE(rule.alpha, 0.5)),\n"
        "    r.evidence_quality  = CASE\n"
        "        WHEN COALESCE($confidence,0) >= 0.75 THEN 'primary'\n"
        "        WHEN COALESCE($confidence,0) >= 0.45 THEN 'secondary'\n"
        "        ELSE COALESCE(r.evidence_quality,'tertiary')\n"
        "    END\n"
        "RETURN r"
    )


def _merge_simple_rel_cypher(rel_type: str) -> str:
    return (
        "MATCH (a {slug: $from_slug}), (b {slug: $to_slug})\n"
        "MERGE (a)-[r:" + rel_type + "]->(b)\n"
        "ON CREATE SET\n"
        "    r.created_at     = $now,\n"
        "    r.source_article = $source_article,\n"
        "    r.confidence     = $confidence\n"
        "ON MATCH SET\n"
        "    r.updated_at     = $now\n"
        "RETURN r"
    )


_UPSERT_NEWS_NODE = (
    "MERGE (n:News {slug: $slug})\n"
    "ON CREATE SET\n"
    "    n.external_id           = $external_id,\n"
    "    n.title                 = $title,\n"
    "    n.event_type            = $event_type,\n"
    "    n.severity              = $severity,\n"
    "    n.urgency               = $urgency,\n"
    "    n.published_at          = $published_at,\n"
    "    n.talan_impact_score    = $talan_impact_score,\n"
    "    n.detected_category     = $detected_category,\n"
    "    n.overall_sentiment     = $overall_sentiment,\n"
    "    n.extraction_confidence = $extraction_confidence,\n"
    "    n.created_at            = $now\n"
    "ON MATCH SET\n"
    "    n.updated_at = $now\n"
    "RETURN n"
)

_LINK_NEWS = (
    "MATCH (news:News {slug: $news_slug}), (entity {slug: $entity_slug})\n"
    "MERGE (news)-[r:MENTIONS]->(entity)\n"
    "ON CREATE SET r.created_at = $now, r.source_article = $news_slug"
)

# Write impact_score onto a node using EWMA so the signal accumulates over time.
# Formula: new = 0.7 * old + 0.3 * signal  (keeps history, avoids overwriting)
# First-time write: n.impact_score = signal directly.
_UPDATE_NODE_IMPACT_SCORE = """
MATCH (n {slug: $slug})
WHERE $score > 0
SET n.impact_score = CASE
        WHEN n.impact_score IS NULL OR n.impact_score = 0
        THEN $score
        ELSE 0.7 * n.impact_score + 0.3 * $score
    END,
    n.impact_updated_at = $now
"""

_SNAPSHOT_QUERY    = "MATCH path = (center {name: $name})-[r*1..HOPS]-(neighbor) RETURN path LIMIT 1000"
_SNAPSHOT_BY_SLUG  = "MATCH path = (center {slug: $slug})-[r*1..HOPS]-(neighbor) RETURN path LIMIT 1000"

_STATS_NODES = """
MATCH (n) WITH labels(n)[0] AS label, count(n) AS cnt
RETURN label, cnt ORDER BY cnt DESC
"""

_PAGERANK_GDS = """
CALL gds.pageRank.stream('kgGraph', {{
    maxIterations: 20,
    dampingFactor: 0.85
}})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS name,
       gds.util.asNode(nodeId).slug AS slug,
       labels(gds.util.asNode(nodeId))[0] AS label,
       score
ORDER BY score DESC
LIMIT 30
"""

# Fallback PageRank via Cypher — damped 2-iteration approximation.
# r_v ≈ (1-d) + d · Σ_{u→v} r_u(t-1) / out_deg(u)
# We compute two iterations rooted in in/out-degree which is a common cheap proxy.
_PAGERANK_CYPHER = """
MATCH (n)
WHERE NOT n:News
WITH collect(n) AS allNodes
UNWIND allNodes AS n
OPTIONAL MATCH (n)<-[r1]-(u) WHERE NOT u:News
WITH n, count(DISTINCT r1) AS in_deg, allNodes
OPTIONAL MATCH (n)-[r2]->(v) WHERE NOT v:News
WITH n, in_deg, count(DISTINCT r2) AS out_deg, allNodes
// First pass: r0(v) = 1/N.  r1(v) = (1-d) + d * sum_u in_deg_u / out_deg_u
WITH n, in_deg, out_deg, size(allNodes) AS N
WITH n, 0.15 + 0.85 * (toFloat(in_deg) / toFloat(CASE WHEN N=0 THEN 1 ELSE N END)) AS pr1
RETURN
    n.name AS name,
    COALESCE(n.slug, toLower(replace(n.name, ' ', '-'))) AS slug,
    labels(n)[0] AS label,
    pr1 AS score
ORDER BY score DESC
LIMIT 200
"""


# ── World Model ───────────────────────────────────────────────────────────────

class WorldModel:
    """Neo4j-backed heterogeneous temporal Knowledge Graph v2."""

    def __init__(self):
        self._driver: Optional[Driver] = None
        self._gds_available: Optional[bool] = None

    # ── Connection ────────────────────────────────────────────────────────────

    def _get_driver(self) -> Optional[Driver]:
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
                self._driver.verify_connectivity()
                logger.info("WorldModel v2: connected to Neo4j at %s", settings.neo4j_uri)
            except (ServiceUnavailable, Exception) as e:
                logger.warning("WorldModel: Neo4j unavailable — %s", e)
                self._driver = None
        return self._driver

    def _run(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        driver = self._get_driver()
        if driver is None:
            return []
        try:
            with driver.session() as session:
                return list(session.run(query, params or {}))
        except Exception as e:
            logger.error("Neo4j query failed: %s — query: %s", e, query[:100])
            return []

    def is_available(self) -> bool:
        return self._get_driver() is not None

    # ── Schema setup ──────────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        """Idempotent constraints and indexes for all node types."""
        constraints = [
            # Slug uniqueness (primary key for entity resolution)
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Company)         REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person)          REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Technology)      REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Regulation)      REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Competitor)      REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:MarketTrend)     REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Sector)          REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Country)         REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Event)           REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:MacroIndicator)  REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:News)            REQUIRE n.slug IS UNIQUE",
            # v3 additions — operational structure of Talan + edge-type policy table
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:BusinessUnit)    REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Client)          REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Supplier)        REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Concept)         REQUIRE n.slug IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:CompatibilityRule) "
            "REQUIRE (n.rel_type, n.src_label, n.dst_label) IS UNIQUE",
        ]
        indexes = [
            # Name index for search
            "CREATE INDEX IF NOT EXISTS FOR (n:Company)         ON (n.name)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Technology)      ON (n.name)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Competitor)      ON (n.name)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Regulation)      ON (n.name)",
            # Temporal indexes
            "CREATE INDEX IF NOT EXISTS FOR (r:CAUSES_IMPACT_ON) ON (r.timestamp)",
            "CREATE INDEX IF NOT EXISTS FOR (r:CAUSES_IMPACT_ON) ON (r.impact_score)",
            "CREATE INDEX IF NOT EXISTS FOR (r:IMPACTS)          ON (r.timestamp)",
            "CREATE INDEX IF NOT EXISTS FOR (r:INFLUENCES)       ON (r.confidence)",
            # Financial
            "CREATE INDEX IF NOT EXISTS FOR (n:Company)         ON (n.ticker)",
        ]
        for stmt in constraints + indexes:
            self._run(stmt)
        logger.info("WorldModel: schema v2 ensured")

    def ensure_talan_node(self) -> None:
        """Upsert the Talan node, merging on name (which carries the uniqueness constraint)."""
        now = datetime.utcnow().isoformat()
        self._run(
            """
            MERGE (n:Company {name: 'Talan'})
            ON CREATE SET
                n.slug            = 'talan',
                n.ticker          = 'TAL.PA',
                n.aliases         = ['Talan ESN', 'Talan Group', 'Talan SA'],
                n.source_articles = ['bootstrap'],
                n.created_at      = $now,
                n.updated_at      = $now
            ON MATCH SET
                n.slug            = COALESCE(n.slug, 'talan'),
                n.ticker          = COALESCE(n.ticker, 'TAL.PA'),
                n.updated_at      = $now
            RETURN n
            """,
            {"now": now},
        )

    # ── Node upsert ───────────────────────────────────────────────────────────

    def _upsert_node_safe(
        self,
        label:          str,
        slug:           str,
        name:           str,
        ticker:         Optional[str] = None,
        aliases:        Optional[List[str]] = None,
        properties:     Optional[Dict] = None,
        source_article: str = "",
    ) -> None:
        self._run(
            _merge_node_safe_cypher(label),
            {
                "slug":           slug,
                "name":           name,
                "ticker":         ticker,
                "aliases":        aliases or [],
                "source_article": source_article,
                "now":            datetime.utcnow().isoformat(),
            },
        )

    def _upsert_entity(self, entity: Entity, source_article: str = "") -> None:
        label = entity.label or _ENTITY_TYPE_TO_LABEL.get(entity.type.value, "Company")
        slug  = entity.id or _slugify(entity.name)
        props = {k: v for k, v in (entity.properties or {}).items() if isinstance(v, (str, int, float, bool))}
        self._upsert_node_safe(
            label=label,
            slug=slug,
            name=entity.name,
            ticker=entity.ticker,
            aliases=entity.aliases,
            properties=props,
            source_article=source_article,
        )

    # ── Relation upsert ───────────────────────────────────────────────────────

    # Relations that carry full temporal versioning
    _TEMPORAL_RELS = {
        RelationType.CAUSES_IMPACT_ON,
        RelationType.IMPACTS,
        RelationType.INFLUENCES,
        RelationType.ACQUIRED,
    }

    def _update_node_impact(self, slug: str, score: float, now: datetime) -> None:
        """Write (or EWMA-update) impact_score on a Neo4j node identified by slug."""
        if not slug or score <= 0:
            return
        self._run(
            _UPDATE_NODE_IMPACT_SCORE,
            {"slug": slug, "score": float(score), "now": now.isoformat()},
        )

    def _upsert_relation(
        self, rel: CausalRelation, source_article: str, timestamp: datetime
    ) -> None:
        from_slug = rel.from_id or _slugify(rel.from_entity)
        to_slug   = rel.to_id   or _slugify(rel.to_entity)
        rel_type  = rel.relation_type.value if rel.relation_type else rel.type.value

        if rel.relation_type in self._TEMPORAL_RELS:
            self._run(
                _merge_causal_rel_cypher(rel_type),
                {
                    "from_slug":      from_slug,
                    "to_slug":        to_slug,
                    "impact_score":   rel.impact_score,
                    "sentiment":      rel.sentiment,
                    "confidence":     rel.confidence,
                    "causality_score": rel.causality_score,
                    "reason":         rel.reason,
                    "evidence":       rel.evidence,
                    "time_horizon":   rel.time_horizon,
                    "talan_relevant": rel.talan_relevant,
                    "timestamp":      timestamp.isoformat(),
                    "source_article": source_article,
                },
            )
        else:
            self._run(
                _merge_simple_rel_cypher(rel_type),
                {
                    "from_slug":      from_slug,
                    "to_slug":        to_slug,
                    "now":            timestamp.isoformat(),
                    "source_article": source_article,
                    "confidence":     rel.confidence,
                },
            )

    # ── Main update ───────────────────────────────────────────────────────────

    def update_from_analysis(self, analysis: NewsAnalysis) -> KGUpdatePayload:
        """Full incremental upsert from a NewsAnalysis v2 object.

        Steps:
        1. Upsert all entity nodes (with slug-based deduplication).
        2. Upsert the News node.
        3. Upsert all relations with temporal versioning.
        4. Link News → each entity (MENTIONS).
        5. Return KGUpdatePayload with counts.
        """
        nodes_added = 0
        rels_added  = 0
        now         = datetime.utcnow()
        source      = analysis.article_external_id

        # 1. Entity nodes
        for entity in analysis.entities:
            self._upsert_entity(entity, source_article=source)
            nodes_added += 1

        # Always ensure Talan is present
        self.ensure_talan_node()

        # 2. News node
        news_slug = f"news-{source[:40]}"
        self._run(
            _UPSERT_NEWS_NODE,
            {
                "slug":                 news_slug,
                "external_id":          source,
                "title":                analysis.article_title,
                "event_type":           analysis.event_type,
                "severity":             analysis.severity,
                "urgency":              analysis.urgency,
                "published_at":         now.isoformat(),
                "talan_impact_score":   analysis.talan_impact_score,
                "detected_category":    analysis.detected_category,
                "overall_sentiment":    analysis.overall_sentiment,
                "extraction_confidence": analysis.extraction_confidence,
                "now":                  now.isoformat(),
            },
        )
        nodes_added += 1

        # 3. Relations
        for rel in analysis.causal_relations:
            # Ensure both endpoint nodes exist
            from_slug = rel.from_id or _slugify(rel.from_entity)
            to_slug   = rel.to_id   or _slugify(rel.to_entity)
            from_label = _ENTITY_TYPE_TO_LABEL.get(rel.from_type.value, "Company")
            to_label   = _ENTITY_TYPE_TO_LABEL.get(rel.to_type.value,   "Company")
            self._upsert_node_safe(from_label, from_slug, rel.from_entity, source_article=source)
            self._upsert_node_safe(to_label,   to_slug,   rel.to_entity,   source_article=source)
            self._upsert_relation(rel, source, now)
            rels_added += 1

            # Propagate relation impact_score onto destination node
            if rel.impact_score and rel.impact_score > 0:
                self._update_node_impact(to_slug, abs(rel.impact_score), now)

        # Propagate talan_impact_score onto the Talan node itself
        if analysis.talan_impact_score and abs(analysis.talan_impact_score) > 0:
            self._update_node_impact("talan", abs(analysis.talan_impact_score), now)

        # 4. MENTIONS links
        for entity in analysis.entities:
            entity_slug = entity.id or _slugify(entity.name)
            self._run(
                _LINK_NEWS,
                {
                    "news_slug":   news_slug,
                    "entity_slug": entity_slug,
                    "now":         now.isoformat(),
                },
            )
            rels_added += 1

        logger.info(
            "WorldModel: updated from '%s' — %d nodes, %d relations",
            analysis.article_title[:60], nodes_added, rels_added,
        )

        return KGUpdatePayload(
            nodes=[KGNode(node_type=e.type, name=e.name, slug=e.id, label=e.label)
                   for e in analysis.entities],
            relations=[KGRelation(
                from_name=r.from_entity, from_type=r.from_type,
                to_name=r.to_entity,   to_type=r.to_type,
                relation_type=r.relation_type,
            ) for r in analysis.causal_relations],
            source_article_id=source,
        )

    # ── Read queries ──────────────────────────────────────────────────────────

    def get_snapshot(
        self,
        company_name: str = "Talan",
        hops: int = 2,
        rel_whitelist: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return an ego-graph snapshot for the propagation engine + frontend.

        rel_whitelist : if provided, only edges with these relation types are
        included in the path expansion. This is critical for keeping the
        propagation engine on causal/structural edges (drops noisy MENTIONS,
        unrelated geographic jumps, etc.).
        """
        slug = _slugify(company_name)
        if rel_whitelist:
            rel_pattern = "|".join(rel_whitelist)
            cypher_slug = (
                "MATCH path = (center {slug: $slug})-[r:" + rel_pattern + "*1.." + str(hops) +
                "]-(neighbor) RETURN path LIMIT 1000"
            )
            cypher_name = (
                "MATCH path = (center {name: $name})-[r:" + rel_pattern + "*1.." + str(hops) +
                "]-(neighbor) RETURN path LIMIT 1000"
            )
        else:
            cypher_slug = _SNAPSHOT_BY_SLUG.replace("HOPS", str(hops))
            cypher_name = _SNAPSHOT_QUERY.replace("HOPS", str(hops))

        records = self._run(cypher_slug, {"slug": slug})
        if not records:
            records = self._run(cypher_name, {"name": company_name})

        nodes: Dict[str, Dict] = {}
        edges: List[Dict] = []

        for rec in records:
            path = rec.get("path") or rec.data().get("path")
            if path is None:
                continue
            for node in path.nodes:
                nid = str(node.id)
                if nid not in nodes:
                    nodes[nid] = {
                        "id":     nid,
                        "slug":   node.get("slug") or _slugify(node.get("name") or node.get("event_label") or nid),
                        "labels": list(node.labels),
                        "name":   (node.get("name") or
                           # News nodes have no 'name' — use article title as display name
                           ("title" in dict(node) and node.get("title") or None) or
                           node.get("event_label") or node.get("id") or "?"),
                        "ticker": node.get("ticker"),
                        "properties": {
                            k: v for k, v in dict(node).items()
                            if k not in {"name", "slug", "ticker", "aliases",
                                         "created_at", "updated_at", "valid_from",
                                         "source_articles", "history",
                                         "event_label"}
                        },
                    }
            for rel in path.relationships:
                edges.append({
                    "from":              str(rel.start_node.id),
                    "to":                str(rel.end_node.id),
                    "type":              rel.type,
                    "impact_score":      rel.get("impact_score"),
                    "sentiment":         rel.get("sentiment"),
                    "confidence":        rel.get("confidence"),
                    "causality_score":   rel.get("causality_score"),
                    "reason":            rel.get("reason"),
                    "evidence":          rel.get("evidence"),
                    "time_horizon":      rel.get("time_horizon"),
                    "timestamp":         rel.get("timestamp"),
                    "talan_relevant":    rel.get("talan_relevant"),
                    # v3 fields — populated by improve_gnn_data.py / new write path
                    "relation_strength": rel.get("relation_strength"),
                    "evidence_quality":  rel.get("evidence_quality"),
                    "freshness_score":   rel.get("freshness_score"),
                })

        return {
            "nodes":  list(nodes.values()),
            "edges":  edges,
            "center": company_name,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }

    def get_talan_risks(self) -> List[Dict[str, Any]]:
        records = self._run("""
            MATCH (cause)-[r:CAUSES_IMPACT_ON|IMPACTS]->(t {name: 'Talan'})
            RETURN
                cause.name           AS cause,
                cause.slug           AS cause_slug,
                labels(cause)[0]     AS cause_type,
                type(r)              AS rel_type,
                r.impact_score       AS score,
                r.confidence         AS confidence,
                r.sentiment          AS sentiment,
                r.reason             AS reason,
                r.timestamp          AS ts
            ORDER BY r.impact_score ASC
            LIMIT 30
        """)
        return [
            {
                "cause":       rec["cause"],
                "cause_slug":  rec["cause_slug"],
                "cause_type":  rec["cause_type"],
                "rel_type":    rec["rel_type"],
                "impact_score": rec["score"],
                "confidence":  rec["confidence"],
                "sentiment":   rec["sentiment"],
                "reason":      rec["reason"],
                "timestamp":   rec["ts"],
            }
            for rec in records
        ]

    def get_stats(self) -> Dict[str, Any]:
        node_records = self._run(_STATS_NODES)
        rel_record   = self._run("MATCH ()-[r]->() RETURN count(r) AS total")
        # Per-relation-type counts
        rel_type_records = self._run("""
            MATCH ()-[r]->()
            WITH type(r) AS rtype, count(r) AS cnt
            RETURN rtype, cnt
            ORDER BY cnt DESC LIMIT 20
        """)
        node_counts  = {rec["label"]: rec["cnt"] for rec in node_records if rec["label"]}
        total_rels   = rel_record[0]["total"] if rel_record else 0
        rels_by_type = {rec["rtype"]: rec["cnt"] for rec in rel_type_records}
        return {
            "total_nodes":     sum(node_counts.values()),
            "total_relations": total_rels,
            "nodes_by_label":  node_counts,
            "relations_by_type": rels_by_type,
        }

    def find_hidden_risks(self, target: str = "Talan", max_hops: int = 3) -> List[Dict]:
        records = self._run(
            f"""
            MATCH path = (source)-[rels:CAUSES_IMPACT_ON|IMPACTS*2..{max_hops}]->(t {{name: $target}})
            WHERE ALL(r IN rels WHERE r.confidence > 0.3)
              AND source.name <> $target
            WITH path, source,
                 REDUCE(s = 0.0, r IN relationships(path) | s + r.impact_score) AS chain_score,
                 REDUCE(c = 1.0, r IN relationships(path) | c * r.confidence)   AS chain_conf,
                 length(path) AS hops
            WHERE chain_score < -0.2
            RETURN
                source.name          AS source_name,
                source.slug          AS source_slug,
                labels(source)[0]    AS source_type,
                chain_score, chain_conf, hops,
                [r IN relationships(path) | r.reason]                              AS reasons,
                [n IN nodes(path)[0..-1] | n.name]                                 AS path_nodes,
                [n IN nodes(path)[0..-1] | labels(n)[0]]                           AS path_node_types,
                [r IN relationships(path) | COALESCE(r.time_horizon, 'short_term')] AS path_horizons,
                [r IN relationships(path) | type(r)]                               AS path_rel_types,
                [r IN relationships(path) | COALESCE(r.impact_score, 0.0)]         AS path_scores
            ORDER BY chain_score ASC
            LIMIT 20
            """,
            {"target": target},
        )
        return [
            {
                "source":          rec["source_name"],
                "source_slug":     rec["source_slug"],
                "source_type":     rec["source_type"],
                "chain_score":     rec["chain_score"],
                "chain_conf":      rec["chain_conf"],
                "hops":            rec["hops"],
                "reasons":         rec["reasons"],
                "path_nodes":      rec["path_nodes"],
                "path_node_types": rec["path_node_types"],
                "path_horizons":   rec["path_horizons"],
                "path_rel_types":  rec["path_rel_types"],
                "path_scores":     rec["path_scores"],
            }
            for rec in records
        ]

    def get_pagerank(self, top_n: int = 30) -> List[Dict[str, Any]]:
        """Compute PageRank on the KG. Uses GDS if available, else Cypher approximation."""
        # Try GDS first
        if self._gds_available is None:
            test = self._run("RETURN gds.version() AS v")
            self._gds_available = bool(test)

        if self._gds_available:
            # Project graph and run PageRank
            self._run("""
                CALL gds.graph.project.cypher(
                    'kgGraph',
                    'MATCH (n) WHERE NOT n:News RETURN id(n) AS id',
                    'MATCH (a)-[r]->(b) WHERE NOT a:News AND NOT b:News RETURN id(a) AS source, id(b) AS target'
                ) YIELD graphName
            """)
            records = self._run(_PAGERANK_GDS)
            self._run("CALL gds.graph.drop('kgGraph') YIELD graphName")
        else:
            records = self._run(_PAGERANK_CYPHER)

        results = []
        for rec in records[:top_n]:
            try:
                results.append({
                    "name":  rec.get("name") or "?",
                    "slug":  rec.get("slug") or _slugify(rec.get("name", "?")),
                    "label": rec.get("label") or "Company",
                    "score": round(float(rec.get("score", 0)), 4),
                })
            except Exception:
                pass
        return results

    def get_temporal_evolution(
        self, entity_name: str, hours: int = 168
    ) -> List[Dict[str, Any]]:
        """Return the time-series of impact scores for an entity over the last N hours."""
        records = self._run(
            """
            MATCH (a)-[r:CAUSES_IMPACT_ON|IMPACTS]->(b {name: $name})
            WHERE r.timestamp >= $cutoff
            RETURN a.name AS from_entity, type(r) AS rel_type,
                   r.impact_score AS score, r.timestamp AS ts
            ORDER BY r.timestamp ASC
            LIMIT 200
            """,
            {
                "name":   entity_name,
                "cutoff": (datetime.utcnow().isoformat()[:10]),  # simple date cutoff
            },
        )
        return [
            {
                "from":      rec["from_entity"],
                "rel_type":  rec["rel_type"],
                "score":     rec["score"],
                "timestamp": rec["ts"],
            }
            for rec in records
        ]

    # ── v3: Manual what-if simulation helpers ────────────────────────────────

    def augment_snapshot(
        self,
        snapshot: Dict[str, Any],
        manual_entities: List[Dict[str, Any]],
        manual_relations: List[Dict[str, Any]],
        news_title: str = "Manual simulation",
        severity: float = 0.5,
    ) -> Dict[str, Any]:
        """Return a NEW snapshot augmented with the manual entities/relations.

        The original `snapshot` is NOT mutated — this is what makes the
        simulation transient. The propagation engine then runs on the
        augmented snapshot exactly as if these nodes/edges were real.

        A synthetic News node is also injected and linked via MENTIONS to
        every manual entity, so the GNN sees a complete provenance subgraph.
        """
        new_nodes = list(snapshot.get("nodes") or [])
        new_edges = list(snapshot.get("edges") or [])

        # Build a name → id lookup of existing nodes so manual relations
        # can refer to nodes already in the KG snapshot by name.
        id_by_name: Dict[str, str] = {}
        for n in new_nodes:
            if n.get("name"):
                id_by_name[n["name"].strip().lower()] = n["id"]

        next_id = max(
            (int(n["id"]) for n in new_nodes if str(n.get("id", "")).isdigit()),
            default=900_000,
        ) + 1

        # Inject a synthetic News node first
        sim_news_id = str(next_id); next_id += 1
        news_slug = f"sim-news-{abs(hash(news_title)) % 10_000_000}"
        new_nodes.append({
            "id":     sim_news_id,
            "slug":   news_slug,
            "labels": ["News"],
            "name":   news_title,
            "properties": {"severity": severity, "simulation": True},
        })

        # Inject manual entity nodes (re-using existing ones by name when possible)
        manual_id_by_name: Dict[str, str] = {}
        for ent in manual_entities:
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in id_by_name:
                manual_id_by_name[name] = id_by_name[key]
                continue
            ent_id = str(next_id); next_id += 1
            new_nodes.append({
                "id":     ent_id,
                "slug":   re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
                "labels": [ent.get("type") or "Company"],
                "name":   name,
                "ticker": ent.get("ticker"),
                "properties": {
                    "sector":              ent.get("sector"),
                    "country":             ent.get("country"),
                    "simulation":          True,
                    # Prevent hub-penalty from silencing simulation actors
                    # (e.g. "French Government" is typed Country but IS relevant).
                    "is_generic_hub":      False,
                    "is_simulation_actor": True,
                },
            })
            id_by_name[key] = ent_id
            manual_id_by_name[name] = ent_id
            # News → MENTIONS → entity
            new_edges.append({
                "from": sim_news_id, "to": ent_id, "type": "MENTIONS",
                "confidence": 0.9,
                "simulation": True,
            })

        # Inject manual relations
        added_edges = 0
        for rel in manual_relations:
            from_name = (rel.get("from_entity") or "").strip()
            to_name   = (rel.get("to_entity")   or "").strip()
            if not from_name or not to_name:
                continue
            src_id = manual_id_by_name.get(from_name) or id_by_name.get(from_name.lower())
            dst_id = manual_id_by_name.get(to_name)   or id_by_name.get(to_name.lower())
            if not src_id or not dst_id:
                logger.warning("Manual relation skipped — unknown endpoint %s → %s", from_name, to_name)
                continue
            conf = float(rel.get("confidence") or 0.7)
            new_edges.append({
                "from":             src_id,
                "to":               dst_id,
                "type":             rel.get("relation_type") or "CAUSES_IMPACT_ON",
                "impact_score":     float(rel.get("impact_score") or 0.0),
                "confidence":       conf,
                "reason":           rel.get("reason") or "",
                "evidence":         rel.get("evidence") or "",
                "time_horizon":     rel.get("time_horizon") or "short_term",
                "timestamp":        datetime.utcnow().isoformat(),
                "talan_relevant":   True,
                "simulation":       True,
                # Pre-fill scoring fields so PathRanker doesn't default them to 0
                "relation_strength": 0.75,
                "freshness_score":   0.95,   # just injected → maximally fresh
                "edge_confidence":   conf,
                "category":         "event",
                "half_life_days":    30.0,
            })
            added_edges += 1

        return {
            "nodes":  new_nodes,
            "edges":  new_edges,
            "center": snapshot.get("center", "Talan"),
            "total_nodes": len(new_nodes),
            "total_edges": len(new_edges),
            "simulation_meta": {
                "added_entities":     len(manual_entities),
                "resolved_entities":  len(manual_id_by_name),
                "added_edges":        added_edges,
                "synthetic_news_id":  sim_news_id,
            },
        }

    def commit_simulation(
        self,
        manual_entities: List[Dict[str, Any]],
        manual_relations: List[Dict[str, Any]],
        news_title: str,
        severity: float = 0.5,
        urgency:  str   = "medium",
        source:   str   = "manual",
    ) -> Dict[str, int]:
        """Persist a manual simulation to Neo4j (the irreversible path)."""
        now = datetime.utcnow()
        slug = re.sub(r"[^a-z0-9]+", "-", (news_title or "manual").lower()).strip("-") or "manual"
        news_slug = f"sim-news-{slug}-{int(now.timestamp())}"
        external_id = f"manual_{int(now.timestamp())}"

        # 1. News node
        self._run(
            _UPSERT_NEWS_NODE,
            {
                "slug":                 news_slug,
                "external_id":          external_id,
                "title":                news_title,
                "event_type":           "manual_simulation",
                "severity":             severity,
                "urgency":              urgency,
                "published_at":         now.isoformat(),
                "talan_impact_score":   0.0,
                "detected_category":    "manual",
                "overall_sentiment":    0.0,
                "extraction_confidence": 1.0,
                "now":                  now.isoformat(),
            },
        )

        # 2. Entities
        nodes_added = 0
        for ent in manual_entities:
            name  = (ent.get("name") or "").strip()
            label = ent.get("type") or "Company"
            if not name:
                continue
            slug_e = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            self._upsert_node_safe(
                label=label,
                slug=slug_e,
                name=name,
                ticker=ent.get("ticker"),
                aliases=ent.get("aliases") or [],
                source_article=external_id,
            )
            nodes_added += 1
            # MENTIONS link
            self._run(_LINK_NEWS, {
                "news_slug":   news_slug,
                "entity_slug": slug_e,
                "now":         now.isoformat(),
            })

        # 3. Relations
        rels_added = 0
        for rel in manual_relations:
            from_name = (rel.get("from_entity") or "").strip()
            to_name   = (rel.get("to_entity")   or "").strip()
            if not from_name or not to_name:
                continue
            from_slug = re.sub(r"[^a-z0-9]+", "-", from_name.lower()).strip("-")
            to_slug   = re.sub(r"[^a-z0-9]+", "-", to_name.lower()).strip("-")
            rel_type  = rel.get("relation_type") or "CAUSES_IMPACT_ON"
            if rel_type in {"CAUSES_IMPACT_ON", "IMPACTS", "INFLUENCES", "ACQUIRED"}:
                self._run(_merge_causal_rel_cypher(rel_type), {
                    "from_slug":      from_slug,
                    "to_slug":        to_slug,
                    "impact_score":   float(rel.get("impact_score") or 0.0),
                    "sentiment":      float(rel.get("sentiment") or 0.0),
                    "confidence":     float(rel.get("confidence") or 0.7),
                    "causality_score": float(rel.get("causality_score") or 0.7),
                    "reason":         rel.get("reason") or "",
                    "evidence":       rel.get("evidence") or "",
                    "time_horizon":   rel.get("time_horizon") or "short_term",
                    "talan_relevant": True,
                    "timestamp":      now.isoformat(),
                    "source_article": external_id,
                })
            else:
                self._run(_merge_simple_rel_cypher(rel_type), {
                    "from_slug":      from_slug,
                    "to_slug":        to_slug,
                    "now":            now.isoformat(),
                    "source_article": external_id,
                    "confidence":     float(rel.get("confidence") or 0.7),
                })
            rels_added += 1

        logger.info(
            "commit_simulation: persisted %d nodes, %d relations under '%s'",
            nodes_added, rels_added, news_slug,
        )
        return {"nodes_added": nodes_added, "rels_added": rels_added, "news_slug": news_slug}

    # ── v3: Edge-type compatibility matrix accessors ─────────────────────────

    def get_compatibility_matrix(self) -> Dict[tuple, Dict[str, Any]]:
        """Read all CompatibilityRule nodes — keyed by (rel_type, src_label, dst_label).

        Used by EdgeTypePolicy and TemporalDecay at process startup. Result is
        small (≤ a few hundred rows) so loading once and caching in-memory is fine.
        """
        records = self._run("""
            MATCH (r:CompatibilityRule)
            RETURN r.rel_type AS rel_type, r.src_label AS src_label,
                   r.dst_label AS dst_label, r.alpha AS alpha,
                   r.half_life_days AS half_life_days, r.category AS category
        """)
        out: Dict[tuple, Dict[str, Any]] = {}
        for rec in records:
            out[(rec["rel_type"], rec["src_label"], rec["dst_label"])] = {
                "alpha":          float(rec["alpha"]) if rec["alpha"] is not None else 0.5,
                "half_life_days": float(rec["half_life_days"]) if rec["half_life_days"] is not None else 90.0,
                "category":       rec["category"] or "default",
            }
        return out

    def get_generic_hubs(self) -> List[str]:
        """Return slugs of nodes flagged as generic hubs by improve_gnn_data.py."""
        records = self._run("""
            MATCH (n) WHERE COALESCE(n.is_generic_hub, false) = true
            RETURN n.slug AS slug
        """)
        return [rec["slug"] for rec in records if rec.get("slug")]

    def get_talan_profile(self) -> Dict[str, Any]:
        """Return Talan's operational profile — BUs, clients, suppliers — for
        the plausibility scorer and the explanation generator."""
        bus = self._run("""
            MATCH (t:Company {name:'Talan'})-[:OPERATES_BU]->(bu:BusinessUnit)
            OPTIONAL MATCH (bu)-[:BU_SERVES]->(target)
            OPTIONAL MATCH (bu)-[:BU_DEPENDS_ON]->(dep)
            RETURN bu.name AS name, bu.slug AS slug,
                   bu.revenue_share AS revenue_share,
                   bu.sector_focus  AS sector_focus,
                   bu.geo_focus     AS geo_focus,
                   collect(DISTINCT target.name) AS serves,
                   collect(DISTINCT dep.name)    AS depends_on
        """)
        return {
            "company": "Talan",
            "country": "France",
            "sectors_served": ["Banking & Finance", "Insurance", "Public Sector"],
            "competitors": ["Capgemini", "Sopra Steria", "Atos", "Accenture", "CGI", "Anthropic"],
            "business_units": [
                {
                    "name":          rec["name"],
                    "slug":          rec["slug"],
                    "revenue_share": rec["revenue_share"],
                    "sector_focus":  rec["sector_focus"] or [],
                    "geo_focus":     rec["geo_focus"] or [],
                    "serves":        [s for s in (rec["serves"] or []) if s],
                    "depends_on":    [d for d in (rec["depends_on"] or []) if d],
                }
                for rec in bus
            ],
        }

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None
