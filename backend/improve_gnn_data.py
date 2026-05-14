"""improve_gnn_data.py — Schema migration + KG hygiene for the propagation engine.

Run once after deploying the v3 refactor (or any time the KG drifts):

    cd backend && python improve_gnn_data.py [--dry-run]

What it does (idempotent):

  1. Applies the v3 schema (kg_schema.cypher) — constraints, indexes,
     BU / Client / Supplier / Concept seed nodes, and the
     edge-type Compatibility Matrix.
  2. Backfills `relation_strength`, `evidence_quality`, `freshness_score`
     on existing causal edges using the compatibility matrix and timestamps.
  3. Detects generic hubs via in-degree percentile + label heuristics
     (Concept / abstract Sector) and writes node.is_generic_hub = true.
  4. Computes node.degree_norm (in_degree / median) and node.specificity
     so the hub-penalty module can read them straight from Neo4j.
  5. Demotes MENTIONS edges that point into generic hubs (sets
     relation_strength = 0.1) — they are the main source of noisy paths.

The script ONLY reads/writes Neo4j. It does not retrain the TGAT.
Re-running is safe.
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

# Allow execution from repo root or from backend/
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from app.core.config import settings  # noqa: E402
from app.services.market_analysis.world_model import WorldModel  # noqa: E402

logger = logging.getLogger("improve_gnn_data")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

SCHEMA_FILE = HERE / "app" / "services" / "market_analysis" / "kg_schema.cypher"

GENERIC_HUB_PERCENTILE = 95          # nodes above p95 in-degree are hub candidates
GENERIC_HUB_LABEL_HINTS = {"Concept", "Country"}  # labels we always treat as semantic hubs
GENERIC_NAME_PATTERNS = {
    "artificial intelligence", "ai", "europe", "economy", "technology",
    "innovation", "digital transformation", "genai", "generative ai",
    "world", "global", "industry", "market",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_schema_statements() -> list[str]:
    """Split kg_schema.cypher into individual statements (semicolon-separated,
    ignoring lines that are pure comments)."""
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # keep blank lines so MERGE blocks stay intact, but drop comment-only lines
        if stripped.startswith("//"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    parts = [p.strip() for p in cleaned.split(";")]
    return [p for p in parts if p]


def apply_schema(world: WorldModel, dry_run: bool = False) -> None:
    if not SCHEMA_FILE.exists():
        logger.error("Schema file not found at %s", SCHEMA_FILE)
        return
    statements = _load_schema_statements()
    logger.info("Applying %d schema statements from %s", len(statements), SCHEMA_FILE.name)
    if dry_run:
        return
    ok, failed = 0, 0
    for stmt in statements:
        try:
            world._run(stmt)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("Schema statement failed (%s): %s", exc, stmt[:90])
    logger.info("Schema applied — %d ok, %d failed", ok, failed)


def backfill_edge_attributes(world: WorldModel, dry_run: bool = False) -> None:
    """Fill relation_strength + evidence_quality + freshness_score.

    Handles two storage formats for r.timestamp:
      - Neo4j datetime type  (newer edges written by the v3 WorldModel)
      - ISO-8601 string      (older edges written before v3 — cast via datetime())
    """
    if dry_run:
        logger.info("[dry-run] would backfill edge attributes")
        return

    # Two separate passes to avoid the String ↔ datetime type mismatch.
    # Pass 1: datetime-typed timestamps.
    cypher_dt = """
    MATCH (a)-[r]->(b)
    WHERE type(r) IN ['CAUSES_IMPACT_ON','IMPACTS','INFLUENCES','MENTIONS']
      AND r.timestamp IS NOT NULL
      AND NOT r.timestamp STARTS WITH '20'
    OPTIONAL MATCH (rule:CompatibilityRule {
        rel_type:  type(r),
        src_label: labels(a)[0],
        dst_label: labels(b)[0]
    })
    WITH r, rule
    SET r.relation_strength = COALESCE(r.relation_strength, COALESCE(rule.alpha, 0.5)),
        r.evidence_quality  = COALESCE(r.evidence_quality,
                                       CASE
                                         WHEN COALESCE(r.confidence,0) >= 0.75 THEN 'primary'
                                         WHEN COALESCE(r.confidence,0) >= 0.45 THEN 'secondary'
                                         ELSE 'tertiary'
                                       END),
        r.freshness_score   = exp( -0.6931471805599453 *
                                   (duration.between(r.timestamp, datetime()).days /
                                    toFloat(COALESCE(rule.half_life_days, 90))) )
    RETURN count(r) AS updated
    """

    # Pass 2: string-typed timestamps — cast first.
    cypher_str = """
    MATCH (a)-[r]->(b)
    WHERE type(r) IN ['CAUSES_IMPACT_ON','IMPACTS','INFLUENCES','MENTIONS']
      AND r.timestamp IS NOT NULL
      AND r.timestamp STARTS WITH '20'
    OPTIONAL MATCH (rule:CompatibilityRule {
        rel_type:  type(r),
        src_label: labels(a)[0],
        dst_label: labels(b)[0]
    })
    WITH r, rule,
         datetime(replace(r.timestamp, ' ', 'T')) AS ts_dt
    SET r.relation_strength = COALESCE(r.relation_strength, COALESCE(rule.alpha, 0.5)),
        r.evidence_quality  = COALESCE(r.evidence_quality,
                                       CASE
                                         WHEN COALESCE(r.confidence,0) >= 0.75 THEN 'primary'
                                         WHEN COALESCE(r.confidence,0) >= 0.45 THEN 'secondary'
                                         ELSE 'tertiary'
                                       END),
        r.freshness_score   = exp( -0.6931471805599453 *
                                   (duration.between(ts_dt, datetime()).days /
                                    toFloat(COALESCE(rule.half_life_days, 90))) )
    RETURN count(r) AS updated
    """

    # Pass 3: NULL timestamps — set default values only.
    cypher_null = """
    MATCH (a)-[r]->(b)
    WHERE type(r) IN ['CAUSES_IMPACT_ON','IMPACTS','INFLUENCES','MENTIONS']
      AND r.timestamp IS NULL
    OPTIONAL MATCH (rule:CompatibilityRule {
        rel_type:  type(r),
        src_label: labels(a)[0],
        dst_label: labels(b)[0]
    })
    WITH r, rule
    SET r.relation_strength = COALESCE(r.relation_strength, COALESCE(rule.alpha, 0.5)),
        r.evidence_quality  = COALESCE(r.evidence_quality, 'tertiary'),
        r.freshness_score   = COALESCE(r.freshness_score, 0.3)
    RETURN count(r) AS updated
    """

    total = 0
    for label, cypher in [("datetime", cypher_dt), ("string", cypher_str), ("null", cypher_null)]:
        try:
            res = world._run(cypher)
            n = res[0]["updated"] if res else 0
            total += n
            logger.info("Edge backfill [%s timestamps] — %d edges updated", label, n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Edge backfill [%s] failed: %s", label, exc)

    logger.info("Edge attribute backfill total — %d edges updated", total)


def deduplicate_suppliers(world: WorldModel, dry_run: bool = False) -> None:
    """Remove duplicate Supplier nodes sharing the same name.

    For each group of duplicates, keeps the first node in each group and
    DETACH DELETEs the rest. Pure Cypher — no APOC required.

    Note: Supplier nodes created by the schema file (AWS, Azure, etc.) have
    explicit BU_DEPENDS_ON links; the duplicates created by LLM extraction
    typically don't. Deleting duplicates is therefore safe — the schema's
    MERGE statements will re-create the correct named nodes on the next run.
    """
    # Dry-run: just count.
    check = world._run("""
        MATCH (s:Supplier)
        WITH s.name AS name, count(s) AS cnt
        WHERE cnt > 1
        RETURN name, cnt ORDER BY cnt DESC
    """)
    if not check:
        logger.info("deduplicate_suppliers: no duplicates found")
        return

    total_dups = sum(int(r["cnt"]) - 1 for r in check)
    logger.info(
        "deduplicate_suppliers: %d names with duplicates, %d extra nodes to remove",
        len(check), total_dups,
    )
    for r in check:
        logger.info("  duplicated Supplier name='%s' (%d copies)", r["name"], r["cnt"])

    if dry_run:
        return

    # Delete all but one node per name group in a single Cypher pass.
    # `tail(nodes)` returns every node after the first, all of which get detached.
    res = world._run("""
        MATCH (s:Supplier)
        WITH s.name AS name, collect(s) AS nodes
        WHERE size(nodes) > 1
        UNWIND tail(nodes) AS dupe
        DETACH DELETE dupe
        RETURN count(*) AS deleted
    """)
    deleted = res[0]["deleted"] if res else 0
    logger.info("deduplicate_suppliers: removed %d duplicate Supplier nodes", deleted)


def detect_generic_hubs(world: WorldModel, dry_run: bool = False) -> None:
    """Flag nodes as generic hubs based on in-degree percentile + label hints."""
    # 1. Compute in-degree distribution (excluding News)
    deg_records = world._run("""
        MATCH (n)
        WHERE NOT n:News
        WITH n, size([(n)<-[r]-(m) WHERE NOT m:News | r]) AS in_deg
        RETURN n.slug AS slug, n.name AS name, labels(n)[0] AS label, in_deg
    """)
    if not deg_records:
        logger.warning("No nodes found while computing in-degree")
        return

    degrees = sorted(int(rec["in_deg"]) for rec in deg_records)
    median = degrees[len(degrees) // 2] or 1
    p_idx = int(len(degrees) * GENERIC_HUB_PERCENTILE / 100)
    p_idx = min(p_idx, len(degrees) - 1)
    threshold = degrees[p_idx] or median

    logger.info(
        "in-degree median=%d  p%d threshold=%d  (n=%d)",
        median, GENERIC_HUB_PERCENTILE, threshold, len(degrees),
    )

    flagged = 0
    for rec in deg_records:
        slug = rec["slug"]
        name = (rec["name"] or "").lower().strip()
        label = rec["label"]
        in_deg = int(rec["in_deg"])

        is_hub = False
        if label in GENERIC_HUB_LABEL_HINTS:
            is_hub = True
        elif name in GENERIC_NAME_PATTERNS:
            is_hub = True
        elif in_deg >= threshold and label not in {"Company", "BusinessUnit", "Client", "Supplier"}:
            # high-degree non-economic node → treat as hub
            is_hub = True

        # Specificity: shrinks logarithmically with degree, capped at [0.1, 1.0]
        specificity = max(0.1, min(1.0, 1.0 / (1.0 + math.log1p(in_deg / max(1.0, median)))))
        degree_norm = in_deg / max(1.0, median)

        if dry_run:
            continue
        if not slug:
            continue
        world._run(
            """
            MATCH (n {slug: $slug})
            SET n.is_generic_hub = $is_hub,
                n.specificity    = $spec,
                n.degree_norm    = $deg_norm
            """,
            {"slug": slug, "is_hub": bool(is_hub), "spec": float(specificity), "deg_norm": float(degree_norm)},
        )
        if is_hub:
            flagged += 1

    logger.info("Generic-hub flagging — %d / %d nodes flagged", flagged, len(deg_records))


def demote_mentions_into_hubs(world: WorldModel, dry_run: bool = False) -> None:
    """Push MENTIONS-into-generic-hub edges down to relation_strength = 0.1."""
    if dry_run:
        logger.info("[dry-run] would demote MENTIONS edges into generic hubs")
        return
    res = world._run("""
        MATCH (a)-[r:MENTIONS]->(b)
        WHERE COALESCE(b.is_generic_hub, false) = true
        SET r.relation_strength = 0.1
        RETURN count(r) AS demoted
    """)
    n = res[0]["demoted"] if res else 0
    logger.info("MENTIONS → generic hub demotion — %d edges weakened", n)


# ── Entry point ──────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> int:
    logger.info("Connecting to Neo4j at %s", settings.neo4j_uri)
    world = WorldModel()
    if not world.is_available():
        logger.error("Neo4j is not reachable. Aborting.")
        return 2

    world.ensure_schema()
    deduplicate_suppliers(world, dry_run=dry_run)
    apply_schema(world, dry_run=dry_run)
    backfill_edge_attributes(world, dry_run=dry_run)
    detect_generic_hubs(world, dry_run=dry_run)
    demote_mentions_into_hubs(world, dry_run=dry_run)
    world.close()
    logger.info("Done.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply v3 schema + KG hygiene")
    parser.add_argument("--dry-run", action="store_true", help="Plan-only, no writes")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
