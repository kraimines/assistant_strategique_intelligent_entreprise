#!/usr/bin/env python3
"""
seed_kg_events.py
=================
Charge les 150 événements historiques (2020-2026) depuis generate_gnn_dataset.py
dans Neo4j, afin que le pipeline GNN dispose d'un graphe de connaissance initial.

Usage:
    cd backend
    python seed_kg_events.py
    python seed_kg_events.py --clear   # vide Neo4j avant de charger
    python seed_kg_events.py --dry-run # affiche les stats sans toucher Neo4j
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed_kg")

# ── Label mapping: local type → Neo4j label ───────────────────────────────────
_TYPE_TO_LABEL = {
    "Company":       "Company",
    "Event":         "Event",
    "Sector":        "Sector",
    "Country":       "Country",
    "MacroIndicator":"MacroIndicator",
}

# ── Edges that count as causal (used by find_hidden_risks) ────────────────────
_CAUSAL_RELS = {
    "CAUSES_IMPACT_ON", "IMPACTS", "AFFECTS_INDICATOR",
    "TRIGGERS_EVENT", "INFLUENCES", "AFFECTS",
}


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def seed(clear: bool = False, dry_run: bool = False) -> None:
    from app.services.market_analysis.world_model import WorldModel
    from data.documents.generate_gnn_dataset import HISTORICAL_EVENTS

    wm = WorldModel()
    if not wm.is_available():
        log.error("Neo4j unavailable — check NEO4J_URI / credentials in .env")
        sys.exit(1)

    if clear and not dry_run:
        log.warning("Clearing existing graph …")
        wm._run("MATCH (n) DETACH DELETE n")
        log.info("Graph cleared.")

    node_count = 0
    rel_count  = 0

    for evt in HISTORICAL_EVENTS:
        eid   = evt["event_id"]
        ename = evt["event_name"]
        etype = evt["event_type"]
        edate = evt["event_date"]

        # ── 1. Upsert all nodes ───────────────────────────────────────────────
        for node in evt["nodes"]:
            nid    = str(node.get("id", ""))
            nname  = node.get("name", nid)
            ntype  = node.get("type", "Company")
            label  = _TYPE_TO_LABEL.get(ntype, "Company")
            slug   = _slugify(nname)

            if dry_run:
                node_count += 1
                continue

            extra_props = ""
            if ntype == "Company":
                ticker  = node.get("ticker") or ""
                country = node.get("country") or ""
                sector  = node.get("sector") or ""
                extra_props = (
                    f', n.ticker = "{ticker}"'
                    f', n.country = "{country}"'
                    f', n.sector = "{sector}"'
                )
            elif ntype == "Event":
                extra_props = f', n.event_type = "{node.get("event_type","")}"'

            wm._run(
                f'MERGE (n:{label} {{slug: $slug}}) '
                f'SET n.name = $name, n.id = $nid'
                + extra_props,
                {"slug": slug, "name": nname, "nid": nid},
            )
            node_count += 1

        # ── 2. Upsert all edges ───────────────────────────────────────────────
        for edge in evt["edges"]:
            fid      = str(edge.get("from_id", ""))
            tid      = str(edge.get("to_id",   ""))
            rel      = str(edge.get("relation", "CAUSES_IMPACT_ON")).upper()
            score    = float(edge.get("impact_score", 0.0))
            conf     = float(edge.get("confidence",   0.5))
            reason   = str(edge.get("reasoning", ""))[:300].replace('"', '\\"')
            ts       = edge.get("timestamp", edate)
            horizon  = "short_term"

            # Derive direction from score
            direction = "negative" if score < 0 else "positive"

            if dry_run:
                rel_count += 1
                continue

            # Look up nodes by id field (slugified name used as slug)
            wm._run(
                f"""
                MATCH (a {{id: $fid}}), (b {{id: $tid}})
                MERGE (a)-[r:{rel} {{event_id: $eid, timestamp: $ts}}]->(b)
                SET r.impact_score    = $score,
                    r.confidence      = $conf,
                    r.reason          = $reason,
                    r.impact_direction= $direction,
                    r.time_horizon    = $horizon,
                    r.source_article  = $eid
                """,
                {
                    "fid": fid, "tid": tid, "eid": eid,
                    "ts": ts, "score": score, "conf": conf,
                    "reason": reason, "direction": direction, "horizon": horizon,
                },
            )
            rel_count += 1

    mode = "[DRY RUN] " if dry_run else ""
    log.info(
        "%sSeeding complete — %d events | %d nodes | %d edges",
        mode, len(HISTORICAL_EVENTS), node_count, rel_count,
    )

    if not dry_run:
        # Verify Talan node exists
        talan = wm._run("MATCH (n {name: 'Talan'}) RETURN n.name AS name LIMIT 1")
        if talan:
            log.info("✓ Talan node present in Neo4j")
        else:
            log.warning("⚠ Talan node NOT found — check event data")

        # Count causal edges arriving at Talan
        causal = wm._run(
            "MATCH (a)-[r:CAUSES_IMPACT_ON|IMPACTS]->(t {name: 'Talan'}) "
            "RETURN count(r) AS cnt"
        )
        if causal:
            log.info("✓ %d direct causal edges → Talan", causal[0]["cnt"])

        wm.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Neo4j with historical KG events")
    parser.add_argument("--clear",   action="store_true", help="Delete all existing nodes first")
    parser.add_argument("--dry-run", action="store_true", help="Count without writing to Neo4j")
    args = parser.parse_args()
    seed(clear=args.clear, dry_run=args.dry_run)
