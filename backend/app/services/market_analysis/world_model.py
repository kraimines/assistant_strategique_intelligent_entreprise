"""World Model — Heterogeneous Temporal Knowledge Graph in Neo4j.

Node types  : Event, Company, Sector, Country, MacroIndicator, News
Relation types: CAUSES_IMPACT_ON, BELONGS_TO_SECTOR, SUPPLY_CHAIN_LINK,
                COMPETES_WITH, OPERATES_IN, TRIGGERS_EVENT, AFFECTS_INDICATOR,
                MENTIONS

Each CAUSES_IMPACT_ON edge carries:
    impact_score   float  -1 to +1
    confidence     float   0 to  1
    reason         str
    timestamp      datetime
    time_horizon   str
    source_article str

The module performs incremental upserts — nodes and relations are merged,
never duplicated.  New observations on the same edge accumulate as a
time-series list (edge property `history`).

Usage:
    wm = WorldModel()
    wm.ensure_schema()                   # idempotent constraints / indexes
    wm.update_from_analysis(analysis)    # upsert nodes + relations
    snapshot = wm.get_snapshot("Talan")  # ego-graph for a company
    stats = wm.get_stats()
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable

from app.core.config import settings
from app.schemas.market_analysis_schemas import (
    CausalRelation, EntityType, KGNode, KGRelation, KGUpdatePayload,
    NewsAnalysis, RelationType,
)

logger = logging.getLogger(__name__)

# ── Cypher templates ──────────────────────────────────────────────────────────

_MERGE_NODE = """
MERGE (n:{label} {name: $name})
ON CREATE SET n.created_at = $now, n.ticker = $ticker, n.aliases = $aliases
ON MATCH  SET n.updated_at = $now,
              n.aliases = CASE WHEN $aliases IS NULL THEN n.aliases ELSE $aliases END,
              n.ticker   = CASE WHEN $ticker  IS NULL THEN n.ticker  ELSE $ticker  END
RETURN n
"""

_MERGE_CAUSES_IMPACT = """
MATCH (a {name: $from_name}), (b {name: $to_name})
MERGE (a)-[r:CAUSES_IMPACT_ON {source_article: $source_article}]->(b)
ON CREATE SET r.impact_score   = $impact_score,
              r.confidence     = $confidence,
              r.reason         = $reason,
              r.time_horizon   = $time_horizon,
              r.timestamp      = $timestamp,
              r.talan_relevant = $talan_relevant,
              r.history        = [$impact_score]
ON MATCH  SET r.impact_score   = $impact_score,
              r.confidence     = $confidence,
              r.reason         = $reason,
              r.timestamp      = $timestamp,
              r.history        = r.history + [$impact_score]
RETURN r
"""

_MERGE_GENERIC_REL = """
MATCH (a {name: $from_name}), (b {name: $to_name})
MERGE (a)-[r:{rel_type}]->(b)
ON CREATE SET r.created_at = $now
RETURN r
"""

_UPSERT_NEWS_NODE = """
MERGE (n:News {external_id: $external_id})
ON CREATE SET n.title = $title,
              n.event_type = $event_type,
              n.severity   = $severity,
              n.urgency    = $urgency,
              n.published_at = $published_at,
              n.talan_impact_score = $talan_impact_score,
              n.created_at = $now
ON MATCH  SET n.updated_at = $now
RETURN n
"""

_LINK_NEWS_TO_ENTITY = """
MATCH (news:News {external_id: $news_id}), (entity {name: $entity_name})
MERGE (news)-[r:MENTIONS]->(entity)
ON CREATE SET r.created_at = $now
"""

_SNAPSHOT_QUERY = """
MATCH path = (center {name: $name})-[r*1..2]-(neighbor)
RETURN path
LIMIT 150
"""

_STATS_QUERY = """
MATCH (n) WITH labels(n)[0] AS label, count(n) AS cnt
RETURN label, cnt
ORDER BY cnt DESC
"""

_TALAN_EGO_QUERY = """
MATCH (t:Company {name: 'Talan'})-[r]-(neighbor)
RETURN t, r, neighbor
ORDER BY r.impact_score ASC
LIMIT 50
"""


# ── Label mapping ─────────────────────────────────────────────────────────────

_ENTITY_TYPE_TO_LABEL: Dict[EntityType, str] = {
    EntityType.COMPANY: "Company",
    EntityType.SECTOR: "Sector",
    EntityType.COUNTRY: "Country",
    EntityType.EVENT: "Event",
    EntityType.MACRO_INDICATOR: "MacroIndicator",
    EntityType.NEWS: "News",
}


# ── World Model ───────────────────────────────────────────────────────────────

class WorldModel:
    """Neo4j-backed heterogeneous temporal Knowledge Graph."""

    def __init__(self):
        self._driver: Optional[Driver] = None

    def _get_driver(self) -> Optional[Driver]:
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
                self._driver.verify_connectivity()
                logger.info("WorldModel: connected to Neo4j at %s", settings.neo4j_uri)
            except ServiceUnavailable as e:
                logger.warning("WorldModel: Neo4j unavailable — %s", e)
                self._driver = None
        return self._driver

    def _run(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        driver = self._get_driver()
        if driver is None:
            return []
        try:
            with driver.session() as session:
                result = session.run(query, params or {})
                return list(result)
        except Exception as e:
            logger.error("Neo4j query failed: %s — %s", e, query[:100])
            return []

    def is_available(self) -> bool:
        return self._get_driver() is not None

    def ensure_schema(self) -> None:
        """Create constraints and indexes — idempotent."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Company) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Sector) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Country) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Event) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:MacroIndicator) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:News) REQUIRE n.external_id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (n:Company) ON (n.ticker)",
            "CREATE INDEX IF NOT EXISTS FOR (r:CAUSES_IMPACT_ON) ON (r.timestamp)",
            "CREATE INDEX IF NOT EXISTS FOR (r:CAUSES_IMPACT_ON) ON (r.impact_score)",
        ]
        for stmt in constraints + indexes:
            self._run(stmt)
        logger.info("WorldModel: schema ensured")

    def ensure_talan_node(self) -> None:
        """Always ensure Talan exists as a Company node."""
        self._run(
            _MERGE_NODE.replace("{label}", "Company"),
            {
                "name": "Talan",
                "now": datetime.utcnow().isoformat(),
                "ticker": "TAL.PA",
                "aliases": ["Talan ESN", "Talan Group", "Talan SA"],
            },
        )

    def _upsert_node(self, entity_type: EntityType, name: str,
                     ticker: Optional[str] = None,
                     aliases: Optional[List[str]] = None) -> None:
        label = _ENTITY_TYPE_TO_LABEL.get(entity_type, "Entity")
        self._run(
            _MERGE_NODE.replace("{label}", label),
            {
                "name": name,
                "now": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "aliases": aliases or [],
            },
        )

    def _upsert_causal_relation(
        self, rel: CausalRelation, source_article: str, timestamp: datetime
    ) -> None:
        self._run(
            _MERGE_CAUSES_IMPACT,
            {
                "from_name": rel.from_entity,
                "to_name": rel.to_entity,
                "impact_score": rel.impact_score,
                "confidence": rel.confidence,
                "reason": rel.reason,
                "time_horizon": rel.time_horizon,
                "timestamp": timestamp.isoformat(),
                "talan_relevant": rel.talan_relevant,
                "source_article": source_article,
            },
        )

    def _upsert_generic_relation(
        self, from_name: str, to_name: str, rel_type: str
    ) -> None:
        cypher = _MERGE_GENERIC_REL.replace("{rel_type}", rel_type)
        self._run(cypher, {"from_name": from_name, "to_name": to_name,
                            "now": datetime.utcnow().isoformat()})

    def update_from_analysis(self, analysis: NewsAnalysis) -> KGUpdatePayload:
        """Full incremental upsert from a NewsAnalysis object.

        1. Upsert all entities as nodes.
        2. Upsert the News node.
        3. Upsert all causal relations.
        4. Link News node → each mentioned entity.
        5. Return a KGUpdatePayload with counts.
        """
        nodes_added = 0
        rels_added = 0
        now = datetime.utcnow()

        # 1. Entity nodes
        for entity in analysis.entities:
            self._upsert_node(
                entity.type, entity.name,
                ticker=entity.ticker, aliases=entity.aliases,
            )
            nodes_added += 1

        # Always ensure Talan is present
        self.ensure_talan_node()

        # 2. News node
        self._run(
            _UPSERT_NEWS_NODE,
            {
                "external_id": analysis.article_external_id,
                "title": analysis.article_title,
                "event_type": analysis.event_type,
                "severity": analysis.severity,
                "urgency": analysis.urgency,
                "published_at": analysis.analysis_timestamp.isoformat(),
                "talan_impact_score": analysis.talan_impact_score,
                "now": now.isoformat(),
            },
        )
        nodes_added += 1

        # 3. Causal relations
        for rel in analysis.causal_relations:
            if rel.relation_type == RelationType.CAUSES_IMPACT_ON:
                self._upsert_causal_relation(rel, analysis.article_external_id, now)
            else:
                # Ensure both nodes exist before linking
                self._upsert_node(rel.from_type, rel.from_entity)
                self._upsert_node(rel.to_type, rel.to_entity)
                self._upsert_generic_relation(
                    rel.from_entity, rel.to_entity, rel.relation_type.value
                )
            rels_added += 1

        # 4. News → entity MENTIONS links
        for entity in analysis.entities:
            self._run(
                _LINK_NEWS_TO_ENTITY,
                {
                    "news_id": analysis.article_external_id,
                    "entity_name": entity.name,
                    "now": now.isoformat(),
                },
            )
            rels_added += 1

        logger.info(
            "WorldModel: updated from '%s' — %d nodes, %d relations",
            analysis.article_title[:60], nodes_added, rels_added,
        )

        # Build payload for audit
        from app.schemas.market_analysis_schemas import KGNode, KGRelation
        return KGUpdatePayload(
            nodes=[
                KGNode(node_type=e.type, name=e.name)
                for e in analysis.entities
            ],
            relations=[
                KGRelation(
                    from_name=r.from_entity,
                    from_type=r.from_type,
                    to_name=r.to_entity,
                    to_type=r.to_type,
                    relation_type=r.relation_type,
                )
                for r in analysis.causal_relations
            ],
            source_article_id=analysis.article_external_id,
        )

    def get_snapshot(self, company_name: str = "Talan", hops: int = 2) -> Dict[str, Any]:
        """Return an ego-graph snapshot around a company node for the LLM context."""
        records = self._run(
            _SNAPSHOT_QUERY,
            {"name": company_name},
        )
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
                        "id": nid,
                        "labels": list(node.labels),
                        "name": node.get("name", "?"),
                        "ticker": node.get("ticker"),
                    }
            for rel in path.relationships:
                edges.append({
                    "from": str(rel.start_node.id),
                    "to": str(rel.end_node.id),
                    "type": rel.type,
                    "impact_score": rel.get("impact_score"),
                    "confidence": rel.get("confidence"),
                    "reason": rel.get("reason"),
                    "timestamp": rel.get("timestamp"),
                })
        return {"nodes": list(nodes.values()), "edges": edges, "center": company_name}

    def get_talan_risks(self) -> List[Dict[str, Any]]:
        """Return all direct CAUSES_IMPACT_ON relations pointing at Talan."""
        records = self._run(
            """
            MATCH (cause)-[r:CAUSES_IMPACT_ON]->(t {name: 'Talan'})
            RETURN cause.name AS cause, labels(cause)[0] AS cause_type,
                   r.impact_score AS score, r.confidence AS confidence,
                   r.reason AS reason, r.timestamp AS ts
            ORDER BY r.impact_score ASC
            LIMIT 30
            """
        )
        return [
            {
                "cause": rec["cause"],
                "cause_type": rec["cause_type"],
                "impact_score": rec["score"],
                "confidence": rec["confidence"],
                "reason": rec["reason"],
                "timestamp": rec["ts"],
            }
            for rec in records
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Return KG statistics: node count per label, total relation count."""
        node_records = self._run(_STATS_QUERY)
        rel_record = self._run("MATCH ()-[r]->() RETURN count(r) AS total")
        node_counts = {rec["label"]: rec["cnt"] for rec in node_records}
        total_rels = rel_record[0]["total"] if rel_record else 0
        total_nodes = sum(node_counts.values())
        return {
            "total_nodes": total_nodes,
            "total_relations": total_rels,
            "nodes_by_label": node_counts,
        }

    def find_hidden_risks(self, target: str = "Talan", max_hops: int = 3) -> List[Dict]:
        """Find second/third-order causal chains reaching the target (hidden risks)."""
        records = self._run(
            f"""
            MATCH path = (source)-[rels:CAUSES_IMPACT_ON*2..{max_hops}]->(t {{name: $target}})
            WHERE ALL(r IN rels WHERE r.confidence > 0.4)
            WITH path, source,
                 REDUCE(s = 0.0, r IN relationships(path) | s + r.impact_score) AS chain_score,
                 length(path) AS hops
            WHERE chain_score < -0.3
            RETURN source.name AS source_name, labels(source)[0] AS source_type,
                   chain_score, hops,
                   [r IN relationships(path) | r.reason] AS reasons
            ORDER BY chain_score ASC
            LIMIT 20
            """,
            {"target": target},
        )
        return [
            {
                "source": rec["source_name"],
                "source_type": rec["source_type"],
                "chain_score": rec["chain_score"],
                "hops": rec["hops"],
                "reasons": rec["reasons"],
            }
            for rec in records
        ]

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None
