"""
Train the HeteroTemporalGNN (neural mode of gnn_predictor.py).

Strategy
--------
We have 658 historical NewsAnalysis rows in PostgreSQL, each with a
talan_impact_score ∈ [-1, +1].  The current Neo4j KG snapshot (155 nodes,
386 edges) serves as the graph structure for ALL training samples — we do not
have historical snapshots, so we approximate with the current graph and vary
only the target impact value.

For each training sample we also inject the event_summary text as a temporary
perturbation on the "center" node features (sentence-transformer encoding),
so the model learns to associate event semantics with impact magnitudes.

Output
------
  backend/gnn_model.pt   ← loaded automatically by GNNPredictor at inference time

Usage
-----
  cd backend
  python train_gnn_predictor.py                        # default 60 epochs
  python train_gnn_predictor.py --epochs 120 --lr 5e-4
  python train_gnn_predictor.py --min-impact 0.1 --epochs 80
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path
from typing import List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# ── torch gate ────────────────────────────────────────────────────────────────
try:
    import torch
except ImportError:
    print("[ERROR] torch is required.  pip install torch")
    sys.exit(1)

try:
    import torch_geometric  # noqa: F401
except ImportError:
    print("[ERROR] torch_geometric is required.  pip install torch-geometric")
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train HeteroTemporalGNN on Talan KG")
    p.add_argument("--epochs",     type=int,   default=60)
    p.add_argument("--lr",         type=float, default=1e-4)
    p.add_argument("--min-impact", type=float, default=0.0,
                   help="Keep only samples with |talan_impact_score| >= this (default 0.0 = all)")
    p.add_argument("--limit",      type=int,   default=500,
                   help="Max training samples to load from DB (default 500)")
    p.add_argument("--model-path", default="./gnn_model.pt",
                   help="Where to save the trained model (default: ./gnn_model.pt)")
    p.add_argument("--seed",       type=int,   default=42)
    return p.parse_args()


# ── Load training samples from PostgreSQL ────────────────────────────────────

def load_training_targets(
    min_impact: float = 0.0,
    limit: int = 500,
) -> List[Tuple[str, float]]:
    """
    Returns list of (event_summary, talan_impact_score) from market_news_analyses.
    Filters out rows with |score| < min_impact.
    """
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
    query = text("""
        SELECT event_summary, talan_impact_score
        FROM market_news_analyses
        WHERE talan_impact_score IS NOT NULL
          AND ABS(talan_impact_score) >= :min_impact
        ORDER BY ABS(talan_impact_score) DESC
        LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"min_impact": min_impact, "lim": limit}).fetchall()

    samples = [(r[0] or "", float(r[1])) for r in rows if r[0]]
    logger.info("Loaded %d training samples (min_impact=%.2f)", len(samples), min_impact)
    return samples


# ── Build HeteroData with event perturbation ─────────────────────────────────

def build_training_data(
    snapshot: dict,
    samples: List[Tuple[str, float]],
    price_data: dict,
) -> List[Tuple["torch_geometric.data.HeteroData", float]]:
    """
    For each (event_summary, target) pair, build a HeteroData object by:
      1. Starting from the base snapshot graph.
      2. Injecting the event_summary as a sentence-transformer perturbation
         on the first node's features (approximation of event signal).

    Returns list of (HeteroData, target_impact) for GNNPredictor.train().
    """
    from app.services.market_analysis.gnn_predictor import GraphBuilder

    builder = GraphBuilder()

    # Build base graph once (expensive: encodes all node names)
    logger.info("Building base HeteroData from KG snapshot (%d nodes, %d edges) …",
                len(snapshot.get("nodes", [])), len(snapshot.get("edges", [])))

    base_data = builder.build_from_kg_snapshot(snapshot, price_data)
    if base_data is None:
        logger.error("GraphBuilder returned None — snapshot may be empty")
        return []

    logger.info("Base graph built.  Generating %d training copies …", len(samples))

    training_pairs: List[Tuple] = []
    for i, (event_text, target) in enumerate(samples):
        # Clone base data (shallow copy of tensors is fine — we only change x slightly)
        from torch_geometric.data import HeteroData
        clone = HeteroData()
        for store in base_data.node_types:
            if hasattr(base_data[store], "x"):
                clone[store].x = base_data[store].x.clone()
        for et in base_data.edge_types:
            if hasattr(base_data[et], "edge_index"):
                clone[et].edge_index = base_data[et].edge_index
            if hasattr(base_data[et], "edge_attr"):
                clone[et].edge_attr = base_data[et].edge_attr

        # Inject event embedding into first Company node (index 0 = Talan by convention)
        event_emb = builder._text_embedding(event_text)  # 384-d
        if "Company" in clone.node_types and clone["Company"].x.shape[0] > 0:
            node_feat = clone["Company"].x[0].clone()
            # Replace only the SBERT slice [0:384] with event embedding
            event_t = torch.tensor(event_emb, dtype=torch.float32)
            if node_feat.shape[0] >= 384:
                node_feat[:384] = event_t
            clone["Company"].x[0] = node_feat

        training_pairs.append((clone, target))

        if (i + 1) % 50 == 0:
            logger.info("  built %d / %d samples", i + 1, len(samples))

    return training_pairs


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)

    # Suppress the HeteroConv "node types not updated" warning
    # (Event/MacroIndicator are source-only by design — expected behaviour)
    warnings.filterwarnings("ignore", message="There exist node types")

    # ── 1. Load KG snapshot ──────────────────────────────────────────────────
    logger.info("Connecting to Neo4j …")
    from app.services.market_analysis.world_model import WorldModel
    wm = WorldModel()
    try:
        snapshot = wm.get_snapshot("Talan", hops=2)
        logger.info("Snapshot: %d nodes, %d edges",
                    len(snapshot.get("nodes", [])), len(snapshot.get("edges", [])))
    finally:
        wm.close()

    if not snapshot.get("nodes"):
        logger.error("Empty KG snapshot — run the market pipeline first to populate Neo4j")
        sys.exit(1)

    # ── 2. Fetch price data ──────────────────────────────────────────────────
    logger.info("Fetching price snapshot …")
    try:
        from app.services.market_analysis.collector import MarketDataCollector
        price_data = MarketDataCollector().fetch_price_snapshot()
        logger.info("Price data: %d tickers", len(price_data))
    except Exception as e:
        logger.warning("Price fetch failed (%s) — using empty prices", e)
        price_data = {}

    # ── 3. Load training targets ─────────────────────────────────────────────
    samples = load_training_targets(
        min_impact=args.min_impact,
        limit=args.limit,
    )
    if not samples:
        logger.error("No training samples found. Run the analysis pipeline first.")
        sys.exit(1)

    # ── 4. Build HeteroData training set ────────────────────────────────────
    training_pairs = build_training_data(snapshot, samples, price_data)
    if not training_pairs:
        logger.error("Could not build training data.")
        sys.exit(1)
    logger.info("Training set: %d samples", len(training_pairs))

    # ── 5. Train ─────────────────────────────────────────────────────────────
    from app.services.market_analysis.gnn_predictor import GNNPredictor
    import os

    # Point GNN_MODEL_PATH to our desired output
    os.environ["GNN_MODEL_PATH"] = str(Path(args.model_path).resolve())

    predictor = GNNPredictor()
    logger.info("Starting training — epochs=%d  lr=%.0e  samples=%d",
                args.epochs, args.lr, len(training_pairs))

    history = predictor.train(
        training_snapshots=training_pairs,
        epochs=args.epochs,
        lr=args.lr,
    )

    losses = history.get("train_losses", [])
    if losses:
        logger.info("Training complete — initial loss=%.4f  final loss=%.4f",
                    losses[0], losses[-1])

    # ── 6. Sanity-check inference ────────────────────────────────────────────
    logger.info("Running inference sanity check …")
    result = predictor.predict(
        snapshot,
        price_data=price_data,
        trigger_event="ECB raises interest rates",
    )

    print("\n" + "═" * 55)
    print("  Neural GNN — Inference Sanity Check")
    print("═" * 55)
    print(f"  Trigger     : ECB raises interest rates")
    print(f"  Systemic risk score : {result.systemic_risk_score:.4f}")
    if result.talan_prediction:
        tp = result.talan_prediction
        print(f"  Talan predicted impact : {tp.predicted_impact:+.4f}  "
              f"(confidence={tp.confidence:.2f}, hops={tp.propagation_hops})")
    print(f"\n  Top predictions (all companies):")
    sorted_preds = sorted(result.predictions, key=lambda p: p.predicted_impact)
    for pred in sorted_preds[:10]:
        flag = " ← HIDDEN RISK" if pred.hidden_risk else ""
        print(f"    {pred.entity_name:<35} {pred.predicted_impact:+.4f}"
              f"  hops={pred.propagation_hops}{flag}")
    if result.top_hidden_risks:
        print(f"\n  Hidden risks detected:")
        for r in result.top_hidden_risks:
            print(f"    {r.entity_name:<35} {r.predicted_impact:+.4f}")
    print("═" * 55)
    print(f"\n  Model saved → {args.model_path}")


if __name__ == "__main__":
    main()
