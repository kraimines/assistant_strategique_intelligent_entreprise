#!/usr/bin/env python3
"""
load_kg_into_neo4j.py
=====================
Loads 150 historical market events into Neo4j, respecting the ETL schema.

Existing uniqueness constraints (from the ETL pipeline):
  Company    : name*, id*, slug
  Sector     : name*, id*, slug
  Country    : name*, id*
  Event      : id*, name*, slug
  MacroIndicator: name*, id*

Strategy:
  - Company/Sector/Country/MacroIndicator : MERGE on name, then SET our id
  - Event nodes                           : MERGE on id (our ids like "evt_001"
                                            are short keys, not UUIDs — safe)
  - Event.name not set (unique constraint) — stored as event_label instead
  - Edges: MATCH by the id we just set above

Usage:
    cd backend/data/documents
    python load_kg_into_neo4j.py [--dry-run]
"""

import json
import os
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "talan_neo4j")

KG_FILE = Path(__file__).parent / "kg_events.json"


# ─────────────────────────────────────────────────────────────────────────────
# Cypher templates (parameterised — no string interpolation)
# ─────────────────────────────────────────────────────────────────────────────

# Event: merge on id (our sequential keys won't clash with ETL UUIDs).
# We do NOT set .name (unique constraint) — use .event_label instead.
_EVT = """
MERGE (e:Event {id: $id})
ON CREATE SET
    e.event_label         = $label,
    e.event_type          = $event_type,
    e.date                = $date,
    e.severity            = $severity,
    e.confidence          = $confidence,
    e.is_historical       = true,
    e.target_impact_talan = $target_impact
ON MATCH SET
    e.event_type          = $event_type,
    e.severity            = $severity,
    e.target_impact_talan = $target_impact,
    e.is_historical       = true
"""

# Company: merge on name (unique in ETL), then tag our id so edges can MATCH.
_COMPANY = """
MERGE (n:Company {name: $name})
ON CREATE SET n.id = $id, n.country = $country, n.sector = $sector,
              n.ticker = $ticker, n.revenue_eur_m = $revenue,
              n.headcount = $headcount, n.is_historical = true
ON MATCH SET  n.id = $id, n.is_historical = true
"""

# Sector: merge on name (unique in ETL), tag our id.
_SECTOR = """
MERGE (s:Sector {name: $name})
ON CREATE SET s.id = $id, s.is_historical = true
ON MATCH SET  s.id = $id, s.is_historical = true
"""

# Country: merge on name (unique in ETL), tag our id.
_COUNTRY = """
MERGE (c:Country {name: $name})
ON CREATE SET c.id = $id, c.is_historical = true
ON MATCH SET  c.id = $id, c.is_historical = true
"""

# MacroIndicator: merge on name, tag our id.
_MACRO = """
MERGE (m:MacroIndicator {name: $name})
ON CREATE SET m.id = $id, m.is_historical = true
ON MATCH SET  m.id = $id, m.is_historical = true
"""

# Edge (relation type injected as format string — safe: controlled set of values)
def _edge_cypher(rel: str) -> str:
    return (
        f"MATCH (a {{id: $from_id}}) "
        f"MATCH (b {{id: $to_id}}) "
        f"MERGE (a)-[r:{rel} {{event: $event_id, ts: $ts}}]->(b) "
        f"ON CREATE SET r.impact_score = $score, r.confidence = $conf, "
        f"              r.reasoning = $reasoning "
        f"ON MATCH SET  r.impact_score = $score, r.confidence = $conf"
    )

# Macro-context edge
_MACRO_CTX = """
MATCH (e:Event {id: $event_id})
MERGE (m:MacroIndicator {name: $macro_name})
ON CREATE SET m.id = $macro_id, m.is_historical = true
ON MATCH SET  m.id = $macro_id
MERGE (e)-[r:HAS_MACRO_CONTEXT {event: $event_id, indicator: $macro_name}]->(m)
ON CREATE SET r.value = $value
ON MATCH SET  r.value = $value
"""


# ─────────────────────────────────────────────────────────────────────────────
# Node loaders
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_nodes(tx, evt: dict) -> None:
    gt = evt["gnn_training"]

    # 1. Sequential Event node  (e.g. id="evt_001")
    tx.run(_EVT, {
        "id":            evt["event_id"],
        "label":         evt["event_name"][:200],
        "event_type":    evt["event_type"],
        "date":          evt["event_date"],
        "severity":      evt["severity"],
        "confidence":    evt["confidence"],
        "target_impact": gt["target_impact"],
    })

    # 2. All nodes in the nodes list
    for node in evt["nodes"]:
        ntype = node["type"]

        if ntype == "Event":
            # Internal event ref node (e.g. id="evt_covid_pandemic")
            tx.run(_EVT, {
                "id":            node["id"],
                "label":         node.get("name", node["id"])[:200],
                "event_type":    node.get("event_type", evt["event_type"]),
                "date":          node.get("date", evt["event_date"]),
                "severity":      evt["severity"],
                "confidence":    evt["confidence"],
                "target_impact": gt["target_impact"],
            })

        elif ntype == "Company":
            tx.run(_COMPANY, {
                "id":       node["id"],
                "name":     node["name"],
                "country":  node.get("country", ""),
                "sector":   node.get("sector", ""),
                "ticker":   node.get("ticker"),
                "revenue":  node.get("revenue_eur_m", 0),
                "headcount":node.get("headcount", 0),
            })

        elif ntype == "Sector":
            tx.run(_SECTOR, {"id": node["id"], "name": node["name"]})

        elif ntype == "Country":
            tx.run(_COUNTRY, {"id": node["id"], "name": node["name"]})

        elif ntype == "MacroIndicator":
            tx.run(_MACRO, {"id": node["id"], "name": node["name"]})


def _upsert_edges(tx, evt: dict) -> None:
    allowed_rels = {
        "CAUSES_IMPACT_ON", "BELONGS_TO_SECTOR", "COMPETES_WITH",
        "SUPPLY_CHAIN_LINK", "SAME_AS", "HAS_MACRO_CONTEXT",
    }
    for edge in evt["edges"]:
        rel = edge["relation"]
        if rel not in allowed_rels:
            continue
        tx.run(_edge_cypher(rel), {
            "from_id":  edge["from_id"],
            "to_id":    edge["to_id"],
            "event_id": evt["event_id"],
            "ts":       edge["timestamp"],
            "score":    edge["impact_score"],
            "conf":     edge["confidence"],
            "reasoning":edge.get("reasoning", "")[:200],
        })


def _upsert_macro_context(tx, evt: dict) -> None:
    macro_map = {
        "cac40":    ("CAC40",    evt["macro_context"].get("CAC40_level")),
        "sp500":    ("SP500",    evt["macro_context"].get("SP500_change_pct")),
        "vix":      ("VIX",      evt["macro_context"].get("VIX")),
        "eur_usd":  ("EUR_USD",  evt["macro_context"].get("EUR_USD")),
        "brent":    ("Brent",    evt["macro_context"].get("brent_usd")),
        "fed_rate": ("Fed_Rate", evt["macro_context"].get("fed_rate")),
        "ecb_rate": ("ECB_Rate", evt["macro_context"].get("ecb_rate")),
    }
    for mid, (mname, mval) in macro_map.items():
        if mval is not None:
            tx.run(_MACRO_CTX, {
                "event_id":   evt["event_id"],
                "macro_id":   mid,
                "macro_name": mname,
                "value":      float(mval),
            })


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def load(dry_run: bool = False) -> None:
    if not KG_FILE.exists():
        print(f"ERROR: {KG_FILE} not found. Run generate_gnn_dataset.py first.")
        sys.exit(1)

    events = json.loads(KG_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(events)} events from {KG_FILE.name}")

    if dry_run:
        evt = events[0]
        print(f"\n[DRY RUN] First event: {evt['event_id']} — {evt['event_name'][:60]}")
        print(f"  Nodes  : {[n['type']+':'+n['id'] for n in evt['nodes']]}")
        print(f"  Edges  : {len(evt['edges'])} edges")
        print(f"  Target : {evt['gnn_training']['target_impact']:+.2f}")
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # Wait for Neo4j
    print(f"Connecting to {NEO4J_URI} ...", flush=True)
    for _ in range(30):
        try:
            driver.verify_connectivity()
            print("  Neo4j is up.\n")
            break
        except Exception:
            time.sleep(2)
    else:
        print("ERROR: Neo4j not reachable", file=sys.stderr)
        sys.exit(1)

    errors = []
    t0 = time.time()

    with driver.session(database="neo4j") as session:

        # ── Step 1: nodes (one explicit transaction per event) ────────────────
        print(f"-- Step 1/3: upserting nodes ({len(events)} events)...")
        for evt in events:
            try:
                session.execute_write(_upsert_nodes, evt)
            except Exception as e:
                errors.append(("nodes", evt["event_id"], str(e)[:160]))

        # ── Step 2: edges (one explicit transaction per event) ────────────────
        print(f"-- Step 2/3: upserting edges + macro context...")
        for evt in events:
            try:
                session.execute_write(_upsert_edges, evt)
                session.execute_write(_upsert_macro_context, evt)
            except Exception as e:
                errors.append(("edges", evt["event_id"], str(e)[:160]))

        # ── Step 3: verify ────────────────────────────────────────────────────
        print("-- Step 3/3: verification...")
        q = lambda c: session.run(c).single()[0]
        n_hist_events = q("MATCH (e:Event {is_historical:true})  RETURN count(e)")
        n_companies   = q("MATCH (c:Company {is_historical:true}) RETURN count(c)")
        n_sectors     = q("MATCH (s:Sector  {is_historical:true}) RETURN count(s)")
        n_countries   = q("MATCH (c:Country {is_historical:true}) RETURN count(c)")
        n_causes      = q("MATCH ()-[r:CAUSES_IMPACT_ON]->() RETURN count(r)")
        n_belongs     = q("MATCH ()-[r:BELONGS_TO_SECTOR]->() RETURN count(r)")
        n_competes    = q("MATCH ()-[r:COMPETES_WITH]->()    RETURN count(r)")
        n_macro_ctx   = q("MATCH ()-[r:HAS_MACRO_CONTEXT]->() RETURN count(r)")

    driver.close()
    elapsed = time.time() - t0

    print(f"\n{'='*62}")
    print(f"  KG load complete  ({elapsed:.1f}s)  —  errors: {len(errors)}")
    print(f"{'='*62}")
    print(f"  Historical Event nodes   : {n_hist_events}  (expect 150+)")
    print(f"  Company nodes tagged     : {n_companies}")
    print(f"  Sector  nodes tagged     : {n_sectors}")
    print(f"  Country nodes tagged     : {n_countries}")
    print(f"  CAUSES_IMPACT_ON edges   : {n_causes}")
    print(f"  BELONGS_TO_SECTOR edges  : {n_belongs}")
    print(f"  COMPETES_WITH edges      : {n_competes}")
    print(f"  HAS_MACRO_CONTEXT edges  : {n_macro_ctx}")

    if errors:
        print(f"\nFirst {min(10, len(errors))} errors:")
        for kind, eid, msg in errors[:10]:
            print(f"  [{kind}] {eid}: {msg}")
    else:
        print("\n  All events loaded without errors.")


if __name__ == "__main__":
    load(dry_run="--dry-run" in sys.argv)
