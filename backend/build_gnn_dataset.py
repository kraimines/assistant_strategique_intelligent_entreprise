"""
build_gnn_dataset.py
====================
CLI entrypoint for the GNN dataset pipeline.

Usage
-----
# Build full dataset
python build_gnn_dataset.py --output-dir ./gnn_dataset

# Build + run an event simulation
python build_gnn_dataset.py --output-dir ./gnn_dataset --simulate "ECB rate hike 100bps" \\
    --affects "Banking & Finance:Sector" "Talan:Company" "Real Estate & Construction:Sector"

# Reload an existing dataset (no Neo4j connection needed)
python build_gnn_dataset.py --load ./gnn_dataset

Environment variables (or .env file):
  NEO4J_URI       bolt://localhost:7687
  NEO4J_USER      neo4j
  NEO4J_PASSWORD  talan_neo4j
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Allow running from the backend/ directory or the project root
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from app.services.market_analysis.gnn_dataset_builder import (
    GNNDatasetPipeline,
    load_dataset,
    simulate_event_impact,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_gnn_dataset")


# ─────────────────────────────────────────────────────────────────────────────
# Argument parser
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build a GNN training dataset from the Talan Knowledge Graph."
    )
    p.add_argument(
        "--output-dir", default="./gnn_dataset",
        help="Directory where nodes.csv / edges.csv / node_features.npy / metadata.json are saved.",
    )
    p.add_argument(
        "--load", metavar="DIR",
        help="Skip Neo4j extraction and reload a previously built dataset from DIR.",
    )
    p.add_argument(
        "--neo4j-uri",     default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    )
    p.add_argument(
        "--neo4j-user",    default=os.getenv("NEO4J_USER", "neo4j"),
    )
    p.add_argument(
        "--neo4j-password",default=os.getenv("NEO4J_PASSWORD", "talan_neo4j"),
    )
    p.add_argument(
        "--skip-pyg", action="store_true",
        help="Do not attempt to build the PyTorch Geometric HeteroData object.",
    )
    p.add_argument(
        "--simulate", metavar="EVENT_NAME",
        help="Inject a hypothetical event and output a simulation dataset.",
    )
    p.add_argument(
        "--affects", nargs="+", metavar="NAME:TYPE",
        help="Entities affected by --simulate. Format: 'Entity Name:NodeType'  "
             "e.g. 'Banking & Finance:Sector' 'Talan:Company'",
    )
    p.add_argument(
        "--impact-score", type=float, default=0.75,
        help="Impact strength for the simulated event [0.0 – 1.0].",
    )
    p.add_argument(
        "--sim-output-dir", default=None,
        help="Directory for simulation output files (defaults to <output-dir>/simulation).",
    )
    p.add_argument(
        "--push-neo4j", action="store_true",
        help="After building the dataset, write enriched nodes/edges back into Neo4j "
             "so they appear immediately in the frontend KG Explorer.",
    )
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_summary(summary: dict) -> None:
    stats = summary["stats"]
    print("\n" + "=" * 60)
    print(f"  GNN Dataset Summary")
    print("=" * 60)
    print(f"  Nodes : {stats['num_nodes']}")
    print(f"  Edges : {stats['num_edges']}")
    print(f"  Feature dim : {stats['feature_dim']}")
    print("\n  Node type breakdown:")
    for ntype, count in sorted(stats["node_types"].items()):
        if count:
            print(f"    {ntype:<20} {count:>4}")
    print("\n  Edge type breakdown:")
    for etype, count in sorted(stats["edge_types"].items()):
        if count:
            print(f"    {etype:<30} {count:>4}")
    print("\n  Output files:")
    for name, path in summary.get("paths", {}).items():
        print(f"    {name:<14} → {path}")
    if summary.get("pyg_data") is not None:
        print("\n  PyG HeteroData: ✓ available for training / inference")
    else:
        print("\n  PyG HeteroData: ✗ torch-geometric not installed")
    print("=" * 60 + "\n")


def _parse_affected_entities(raw: list[str]) -> list[dict]:
    """Parse 'Name:Type' strings into {"name": ..., "type": ...} dicts."""
    entities = []
    for item in raw or []:
        if ":" in item:
            name, etype = item.rsplit(":", 1)
            entities.append({"name": name.strip(), "type": etype.strip()})
        else:
            entities.append({"name": item.strip(), "type": "Company"})
    return entities


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _build_parser().parse_args()

    # ── Mode A: reload existing dataset ───────────────────────────────────────
    if args.load:
        logger.info("Loading existing dataset from %s …", args.load)
        dataset = load_dataset(args.load)
        meta = dataset["metadata"]
        print(f"\n  Loaded dataset: {meta['num_nodes']} nodes, "
              f"{meta['num_edges']} edges, "
              f"{meta['feature_dim']}-d features")
        if dataset["pyg_data"] is not None:
            print("  PyG HeteroData: ✓ ready")
        else:
            print("  PyG HeteroData: ✗ torch-geometric not installed")

        # If a simulation is also requested, run it on the loaded dataset
        if args.simulate:
            _run_simulation(args, existing_dataset=dataset)
        return

    # ── Mode B: full pipeline ─────────────────────────────────────────────────
    logger.info("Connecting to Neo4j at %s …", args.neo4j_uri)
    pipeline = GNNDatasetPipeline(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        output_dir=args.output_dir,
    )
    summary = pipeline.run(skip_pyg=args.skip_pyg)
    _print_summary(summary)

    # ── Optional: push enrichment back to Neo4j ────────────────────────────────
    if args.push_neo4j:
        logger.info("Pushing enriched nodes/edges to Neo4j …")
        counts = pipeline.push_to_neo4j()
        print(f"\n  Neo4j write-back: {counts['nodes']} nodes + {counts['edges']} edges pushed")
        print("  → Rafraîchis le KG Explorer dans le frontend pour les voir.\n")

    # ── Optional: event simulation after full pipeline ─────────────────────────
    if args.simulate:
        _run_simulation(args, pipeline=pipeline)


def _run_simulation(args, pipeline=None, existing_dataset=None) -> None:
    """Run the event simulation, reusing the built pipeline or existing dataset."""
    affected = _parse_affected_entities(args.affects or [])
    if not affected:
        logger.warning("--simulate requires at least one --affects entity.")
        return

    sim_dir = args.sim_output_dir or str(Path(args.output_dir) / "simulation")

    logger.info("Simulating event: %r → %d entities …", args.simulate, len(affected))

    if pipeline is not None:
        result = simulate_event_impact(
            event_name=args.simulate,
            affected_entities=affected,
            impact_score=args.impact_score,
            pipeline=pipeline,
            output_dir=sim_dir,
        )
    else:
        # Rebuild from env if only a loaded dataset was provided
        result = simulate_event_impact(
            event_name=args.simulate,
            affected_entities=affected,
            impact_score=args.impact_score,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            output_dir=sim_dir,
        )

    stats = result["stats"]
    print("\n" + "=" * 60)
    print("  Event Simulation Result")
    print("=" * 60)
    print(f"  Event      : {stats['event_name']}")
    print(f"  Connections: {stats['connections']} new IMPACTS edges")
    print(f"  Graph size : {stats['num_nodes']} nodes / {stats['num_edges']} edges")
    print(f"  Sim output : {sim_dir}")
    if result["pyg_data"] is not None:
        print("  PyG ready  : ✓ forward-pass ready for inference")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
