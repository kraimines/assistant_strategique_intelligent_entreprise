"""GraphSanitizer — nightly KG hygiene job.

Reduces propagation noise *before* TGAT inference (§8 step 2 of plan):

  * prune low-confidence edges                       (confidence < 0.4)
  * collapse duplicated semantic edges between same endpoints
  * demote MENTIONS that point into generic hubs     (relation_strength=0.1)
  * detect and flag generic hubs (delegates to improve_gnn_data heuristics)

The sanitizer is idempotent and intended to be run on a schedule, not on
every request. The `dry_run=True` flag returns the would-be changes
without writing — useful when validating thresholds.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SanitizerReport:
    pruned_low_conf:    int = 0
    collapsed_dups:     int = 0
    demoted_mentions:   int = 0
    hubs_flagged:       int = 0


class GraphSanitizer:
    MIN_EDGE_CONFIDENCE: float = 0.4

    def __init__(self, world_model, min_edge_confidence: Optional[float] = None):
        self.world = world_model
        if min_edge_confidence is not None:
            self.MIN_EDGE_CONFIDENCE = min_edge_confidence

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def run(self, dry_run: bool = False) -> SanitizerReport:
        rep = SanitizerReport()
        rep.pruned_low_conf  = self.prune_low_confidence(dry_run=dry_run)
        rep.collapsed_dups   = self.collapse_duplicate_semantic_links(dry_run=dry_run)
        rep.demoted_mentions = self.demote_weak_mentions(dry_run=dry_run)
        rep.hubs_flagged     = self.detect_generic_hubs(dry_run=dry_run)
        logger.info(
            "GraphSanitizer: pruned=%d collapsed=%d demoted=%d hubs=%d (dry_run=%s)",
            rep.pruned_low_conf, rep.collapsed_dups, rep.demoted_mentions,
            rep.hubs_flagged, dry_run,
        )
        return rep

    # ── Stages ───────────────────────────────────────────────────────────────

    def prune_low_confidence(self, dry_run: bool = False) -> int:
        """Detach causal edges with confidence < threshold AND no recent timestamp."""
        if dry_run:
            res = self.world._run("""
                MATCH ()-[r:CAUSES_IMPACT_ON|IMPACTS|INFLUENCES]->()
                WHERE COALESCE(r.confidence, 0.0) < $thr
                  AND (r.timestamp IS NULL OR
                       duration.between(r.timestamp, datetime()).days > 90)
                RETURN count(r) AS n
            """, {"thr": self.MIN_EDGE_CONFIDENCE})
            return int(res[0]["n"]) if res else 0
        res = self.world._run("""
            MATCH ()-[r:CAUSES_IMPACT_ON|IMPACTS|INFLUENCES]->()
            WHERE COALESCE(r.confidence, 0.0) < $thr
              AND (r.timestamp IS NULL OR
                   duration.between(r.timestamp, datetime()).days > 90)
            WITH r LIMIT 5000
            DELETE r
            RETURN count(*) AS n
        """, {"thr": self.MIN_EDGE_CONFIDENCE})
        return int(res[0]["n"]) if res else 0

    def collapse_duplicate_semantic_links(self, dry_run: bool = False) -> int:
        """When the same (a)-[same rel-type]->(b) is duplicated by source_article,
        keep the highest-confidence one and detach the rest."""
        if dry_run:
            res = self.world._run("""
                MATCH (a)-[r:CAUSES_IMPACT_ON|IMPACTS|INFLUENCES]->(b)
                WITH a, b, type(r) AS t, collect(r) AS rels
                WHERE size(rels) > 1
                RETURN sum(size(rels) - 1) AS extra
            """)
            return int(res[0]["extra"]) if res and res[0]["extra"] is not None else 0
        res = self.world._run("""
            MATCH (a)-[r:CAUSES_IMPACT_ON|IMPACTS|INFLUENCES]->(b)
            WITH a, b, type(r) AS t, collect(r) AS rels
            WHERE size(rels) > 1
            UNWIND rels AS r
            WITH a, b, t, rels, r
            ORDER BY COALESCE(r.confidence, 0.0) DESC
            WITH a, b, t, rels, collect(r) AS sorted
            UNWIND sorted[1..] AS extra
            DELETE extra
            RETURN count(*) AS n
        """)
        return int(res[0]["n"]) if res else 0

    def demote_weak_mentions(self, dry_run: bool = False) -> int:
        """MENTIONS into generic hubs ⇒ relation_strength = 0.1."""
        if dry_run:
            res = self.world._run("""
                MATCH ()-[r:MENTIONS]->(b)
                WHERE COALESCE(b.is_generic_hub, false) = true
                RETURN count(r) AS n
            """)
            return int(res[0]["n"]) if res else 0
        res = self.world._run("""
            MATCH ()-[r:MENTIONS]->(b)
            WHERE COALESCE(b.is_generic_hub, false) = true
            SET r.relation_strength = 0.1
            RETURN count(r) AS n
        """)
        return int(res[0]["n"]) if res else 0

    def detect_generic_hubs(self, dry_run: bool = False) -> int:
        """Re-flag generic hubs based on degree percentile + label hint.

        Uses the same heuristic as improve_gnn_data.py but cheaper (no Python
        round-trip): we let Cypher compute it directly so the sanitizer can
        be cron'd safely.
        """
        # Three-step pipeline that does NOT depend on APOC.
        # 1. Pull degree distribution into Python.
        deg_rows = self.world._run("""
            MATCH (n) WHERE NOT n:News
            WITH n, size([(n)<-[r]-(m) WHERE NOT m:News | r]) AS d
            RETURN d ORDER BY d
        """)
        if not deg_rows:
            return 0
        degs = [int(r["d"]) for r in deg_rows]
        p_idx = int(len(degs) * 0.95)
        p95 = degs[min(p_idx, len(degs) - 1)] if degs else 1

        # 2. Count or flag.
        if dry_run:
            res = self.world._run("""
                MATCH (n) WHERE NOT n:News
                WITH n, size([(n)<-[r]-(m) WHERE NOT m:News | r]) AS d
                WHERE (d >= $p95 AND NOT (n:Company OR n:BusinessUnit OR n:Client OR n:Supplier))
                   OR n:Concept OR n:Country
                RETURN count(n) AS n
            """, {"p95": p95})
            return int(res[0]["n"]) if res else 0
        res = self.world._run("""
            MATCH (n) WHERE NOT n:News
            WITH n, size([(n)<-[r]-(m) WHERE NOT m:News | r]) AS d
            WHERE (d >= $p95 AND NOT (n:Company OR n:BusinessUnit OR n:Client OR n:Supplier))
               OR n:Concept OR n:Country
            SET n.is_generic_hub = true
            RETURN count(n) AS n
        """, {"p95": p95})
        return int(res[0]["n"]) if res else 0
