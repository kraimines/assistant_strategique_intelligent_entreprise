"""
CLI — Train GNN embeddings (Node2Vec + GraphSAGE) from the local dataset.

Usage examples:

  # Train both methods
  python train_embeddings.py --dataset-dir ./gnn_dataset --output-dir ./gnn_dataset

  # Node2Vec only, custom dimensions
  python train_embeddings.py --method node2vec --dim 64

  # GraphSAGE with more epochs
  python train_embeddings.py --method graphsage --epochs 100

  # Evaluate existing embeddings without retraining
  python train_embeddings.py --evaluate-only
"""

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Resolve backend root so imports work from any cwd
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train GNN embeddings for the Talan KG")
    p.add_argument(
        "--method",
        choices=["node2vec", "graphsage", "both"],
        default="both",
        help="Embedding method to run (default: both)",
    )
    p.add_argument(
        "--dataset-dir",
        default="./gnn_dataset",
        help="Directory containing nodes.csv, edges.csv, node_features.npy (default: ./gnn_dataset)",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Root output directory — embeddings saved in <output-dir>/embeddings/. Defaults to --dataset-dir",
    )
    p.add_argument("--dim", type=int, default=128, help="Embedding dimension (default: 128)")
    p.add_argument(
        "--epochs", type=int, default=50, help="GraphSAGE training epochs (default: 50)"
    )
    p.add_argument(
        "--walk-length", type=int, default=20, help="Node2Vec walk length (default: 20)"
    )
    p.add_argument(
        "--num-walks", type=int, default=10, help="Node2Vec walks per node (default: 10)"
    )
    p.add_argument("--p", type=float, default=1.0, help="Node2Vec return param p (default: 1.0)")
    p.add_argument(
        "--q", type=float, default=0.5, help="Node2Vec in-out param q (default: 0.5)"
    )
    p.add_argument(
        "--evaluate",
        action="store_true",
        help="Run cosine-similarity evaluation after training",
    )
    p.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Skip training; load existing embeddings and evaluate",
    )
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else dataset_dir

    from app.services.market_analysis.embedding_trainer import (
        evaluate_embeddings,
        load_graph,
        run_graphsage,
        run_node2vec,
        save_embeddings,
        save_evaluation,
    )
    import numpy as np

    # ── Load data ────────────────────────────────────────────────────────────
    logger.info("Loading dataset from %s …", dataset_dir)
    G, nodes_df, features = load_graph(dataset_dir)
    logger.info(
        "  %d nodes · %d edges · features %s",
        G.number_of_nodes(),
        G.number_of_edges(),
        features.shape,
    )

    emb_dir = output_dir / "embeddings"

    # ── Evaluate-only mode ───────────────────────────────────────────────────
    if args.evaluate_only:
        reports = []
        for method, fname in [("node2vec", "node2vec_embeddings.npy"),
                               ("graphsage", "graphsage_embeddings.npy")]:
            path = emb_dir / fname
            if path.exists():
                emb = np.load(path)
                report = evaluate_embeddings(nodes_df, emb, method=method)
                reports.append(report)
                print(f"\n{'='*60}")
                print(f"  {method.upper()}  ({emb.shape})")
                print(f"{'='*60}")
                for anchor_res in report["anchors"]:
                    print(f"  Anchor: {anchor_res['anchor']}")
                    for name, sim in anchor_res["named_similarities"].items():
                        print(f"    ↔ {name:<35} cos={sim:.4f}")
                    print("  Top-5 nearest:")
                    for name, sim in anchor_res["top5_nearest"]:
                        print(f"    • {name:<35} cos={sim:.4f}")
            else:
                logger.warning("Embeddings not found: %s", path)
        if reports:
            # Save combined report
            (emb_dir / "evaluation_report.json").write_text(
                json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return

    # ── Training ─────────────────────────────────────────────────────────────
    n2v_emb = sage_emb = None
    n2v_model = sage_model = None

    if args.method in ("node2vec", "both"):
        logger.info("── Node2Vec ──────────────────────────────────────────")
        n2v_emb, n2v_model = run_node2vec(
            G,
            dim=args.dim,
            walk_length=args.walk_length,
            num_walks=args.num_walks,
            p=args.p,
            q=args.q,
            seed=args.seed,
        )

    if args.method in ("graphsage", "both"):
        logger.info("── GraphSAGE ─────────────────────────────────────────")
        sage_emb, sage_model = run_graphsage(
            G,
            features,
            in_dim=features.shape[1],
            hidden=256,
            out_dim=args.dim,
            epochs=args.epochs,
            seed=args.seed,
        )

    # ── Save ─────────────────────────────────────────────────────────────────
    save_embeddings(
        output_dir,
        nodes_df,
        n2v_emb=n2v_emb,
        sage_emb=sage_emb,
        n2v_model=n2v_model,
        sage_model=sage_model,
    )
    logger.info("All embeddings saved to %s", emb_dir)

    # ── Evaluate ─────────────────────────────────────────────────────────────
    if args.evaluate or args.method == "both":
        for method, emb in [("node2vec", n2v_emb), ("graphsage", sage_emb)]:
            if emb is None:
                continue
            report = evaluate_embeddings(nodes_df, emb, method=method)
            save_evaluation(output_dir, report)
            print(f"\n{'='*60}")
            print(f"  {method.upper()} Evaluation  ({emb.shape})")
            print(f"{'='*60}")
            for anchor_res in report["anchors"]:
                print(f"  Anchor: {anchor_res['anchor']}")
                for name, sim in anchor_res["named_similarities"].items():
                    print(f"    ↔ {name:<35} cos={sim:.4f}")
                print("  Top-5 nearest:")
                for name, sim in anchor_res["top5_nearest"]:
                    print(f"    • {name:<35} cos={sim:.4f}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
