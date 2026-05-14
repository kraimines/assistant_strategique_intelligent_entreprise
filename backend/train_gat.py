"""
CLI — Train GAT Impact Propagation model on the Talan Knowledge Graph.

Usage examples:

  # Train + evaluate + simulate a BCE rate shock
  python train_gat.py --epochs 100 --evaluate --shock "ECB Interest Rates"

  # Quick smoke test (10 epochs)
  python train_gat.py --epochs 10 --evaluate

  # Simulate only (load existing model)
  python train_gat.py --simulate-only --shock "Capgemini" --shock-value 0.9

  # Custom attention heads
  python train_gat.py --heads 4,2,1 --dropout 0.2 --epochs 150
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

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# ── torch gate ────────────────────────────────────────────────────────────────
try:
    import torch  # noqa: F401
except ImportError:
    print(
        "\n[ERROR] PyTorch is required for GAT training.\n"
        "Install it with:\n"
        "  pip install torch==2.3.0          # CPU-only\n"
        "  # or for CUDA 12.1:\n"
        "  pip install torch==2.3.0+cu121 -f https://download.pytorch.org/whl/cu121\n"
    )
    sys.exit(1)


def _banner(title: str) -> None:
    width = 42
    print(f"\n╔{'═' * width}╗")
    print(f"║  {title:<{width - 2}}║")
    print(f"╚{'═' * width}╝\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train GAT Impact Propagation on Talan KG")
    p.add_argument("--dataset-dir", default="./gnn_dataset",
                   help="Directory with nodes.csv, edges.csv, node_features.npy")
    p.add_argument("--output-dir", default=None,
                   help="Root output dir (embeddings/ sub-dir created). Default = dataset-dir")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--heads", default="8,4,1",
                   help="Attention heads per layer, comma-separated (default: 8,4,1)")
    p.add_argument("--dropout", type=float, default=0.3)
    p.add_argument("--shock", default=None,
                   help="Node name to shock for impact simulation")
    p.add_argument("--shock-value", type=float, default=1.0,
                   help="Shock intensity [0,1] (default: 1.0 = maximum)")
    p.add_argument("--evaluate", action="store_true",
                   help="Evaluate MAE + R² after training")
    p.add_argument("--simulate-only", action="store_true",
                   help="Skip training; load existing gat_model.pt and simulate")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    import torch

    torch.manual_seed(args.seed)

    dataset_dir = Path(args.dataset_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else dataset_dir
    emb_dir = output_dir / "embeddings"

    try:
        heads_tuple = tuple(int(h) for h in args.heads.split(","))
        if len(heads_tuple) != 3:
            raise ValueError
    except ValueError:
        print("[ERROR] --heads must be 3 comma-separated integers, e.g. 8,4,1")
        sys.exit(1)

    from app.services.market_analysis.gat_trainer import (
        GATImpactModel,
        evaluate_gat,
        load_pyg_data,
        save_gat_artefacts,
        simulate_impact_propagation,
        train_gat,
    )

    # ── Load data ─────────────────────────────────────────────────────────────
    logger.info("Loading dataset from %s …", dataset_dir)
    data = load_pyg_data(dataset_dir)

    if isinstance(data, dict):
        node_names = data["node_names"]
        node_types = data["node_types"]
        N = len(node_names)
        in_dim = int(data["x"].shape[1])
    else:
        node_names = data.node_names
        node_types = data.node_types
        N = data.num_nodes
        in_dim = int(data.x.shape[1])

    logger.info("  %d nodes  ·  in_dim=%d  ·  heads=%s", N, in_dim, heads_tuple)

    # ── Model ─────────────────────────────────────────────────────────────────
    model = GATImpactModel(in_dim=in_dim, heads=heads_tuple, dropout=args.dropout)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    # ── Simulate-only mode ────────────────────────────────────────────────────
    if args.simulate_only:
        model_path = emb_dir / "gat_model.pt"
        if not model_path.exists():
            print(f"[ERROR] No saved model found at {model_path}")
            print("  Run without --simulate-only first to train the model.")
            sys.exit(1)
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.eval()
        logger.info("Loaded existing model from %s", model_path)
    else:
        # ── Train ─────────────────────────────────────────────────────────────
        logger.info(
            "Training GAT — epochs=%d  lr=%.0e  dropout=%.2f  device=%s",
            args.epochs, args.lr, args.dropout, device,
        )
        model, loss_history = train_gat(data, model, epochs=args.epochs, lr=args.lr)
        save_gat_artefacts(output_dir, model, loss_history, node_names)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    if args.evaluate or args.simulate_only:
        metrics = evaluate_gat(model, data, node_names, node_types)
        _banner("GAT Evaluation")
        print(f"  MAE  = {metrics['mae']:.4f}")
        print(f"  R²   = {metrics['r2']:.4f}")
        print()
        print("  Top-10 highest predicted impacts:")
        for rank, node in enumerate(metrics["top_impacted"], 1):
            print(
                f"  #{rank:<3} {node['name']:<35} {node['type']:<16} "
                f"pred={node['predicted_impact']:.4f}  true={node['true_impact']:.4f}"
            )

        # Save metrics
        emb_dir.mkdir(parents=True, exist_ok=True)
        (emb_dir / "gat_evaluation.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Simulate impact propagation ───────────────────────────────────────────
    if args.shock:
        try:
            results = simulate_impact_propagation(
                model, data, args.shock, shock_value=args.shock_value
            )
        except ValueError as exc:
            print(f"\n[ERROR] {exc}")
            sys.exit(1)

        _banner("GAT Impact Propagation — Results")
        print(f"  Shock node  : {args.shock}  (value={args.shock_value:.2f})\n")
        print(f"  Top {len(results)} impacted nodes :\n")
        for rank, r in enumerate(results, 1):
            print(
                f"  #{rank:<3} {r['name']:<38} {r['type']:<16} "
                f"impact={r['predicted_impact']:.4f}  attn={r['attention_weight']:.4f}"
            )

        # Save simulation result
        emb_dir.mkdir(parents=True, exist_ok=True)
        safe_name = args.shock.replace(" ", "_").lower()
        out_path = emb_dir / f"simulation_{safe_name}.json"
        out_path.write_text(
            json.dumps(
                {
                    "shock_node": args.shock,
                    "shock_value": args.shock_value,
                    "top_impacted": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("Simulation saved → %s", out_path)

    logger.info("Done.")


if __name__ == "__main__":
    main()
