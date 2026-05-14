"""
compare_models.py
=================
Loads results/hgt_metrics.json, results/tgn_metrics.json, results/tgat_metrics.json
and prints a ranked comparison table across all available models.

Run:
    cd backend/app/services/market_analysis
    python compare_models.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE        = Path(__file__).parent.resolve()
RESULT_DIR  = HERE / "results"

MODEL_FILES = {
    "HGT":     "hgt_metrics.json",
    "TGN":     "tgn_metrics.json",
    "TGAT":    "tgat_metrics.json",
    "TGN+HGT": "tgn_hgt_metrics.json",
    "HTGN":    "htgn_metrics.json",
}

METRICS_LABELS = {
    "auc":       "AUC-ROC",
    "ap":        "Avg Precision",
    "f1":        "F1",
    "precision": "Precision",
    "recall":    "Recall",
}

# ─────────────────────────────────────────────────────────────────────────────

def load_results() -> dict:
    results = {}
    for name, fname in MODEL_FILES.items():
        path = RESULT_DIR / fname
        if path.exists():
            with open(path, encoding="utf-8") as f:
                results[name] = json.load(f)
        else:
            print(f"  [MISSING] {fname} — run train_{name.lower()}.py first")
    return results


def print_comparison(results: dict) -> None:
    if not results:
        print("No results found. Run at least one trainer first.")
        return

    models   = list(results.keys())
    metrics  = list(METRICS_LABELS.keys())

    # ── Header ────────────────────────────────────────────────────────────────
    col_w  = 16
    name_w = 14
    sep    = "─" * (name_w + col_w * len(models) + 2)

    print()
    print("=" * len(sep))
    print("  GNN MODEL COMPARISON — Talan Market Analysis (test set)")
    print("=" * len(sep))
    print()

    # Column headers
    header = f"{'Metric':<{name_w}}" + "".join(f"{m:>{col_w}}" for m in models)
    print(header)
    print(sep)

    # Metric rows
    best: dict[str, tuple] = {}   # metric → (best_value, best_model)
    for mkey, mlabel in METRICS_LABELS.items():
        row_vals = {}
        for name in models:
            val = results[name].get("test", {}).get(mkey)
            row_vals[name] = val

        # Find best (highest) for this metric
        valid = {n: v for n, v in row_vals.items() if v is not None}
        if valid:
            best_model = max(valid, key=lambda n: valid[n])
            best[mkey] = (valid[best_model], best_model)

        row = f"{mlabel:<{name_w}}"
        for name in models:
            val = row_vals.get(name)
            if val is None:
                cell = "—"
            else:
                is_best = (best.get(mkey, (None, None))[1] == name)
                cell    = f"{val:.4f}{'*' if is_best else ' '}"
            row += f"{cell:>{col_w}}"
        print(row)

    print(sep)

    # Threshold row
    thresh_row = f"{'Threshold':<{name_w}}"
    for name in models:
        t = results[name].get("test", {}).get("threshold")
        thresh_row += f"{'—' if t is None else f'{t:.3f}':>{col_w}}"
    print(thresh_row)

    # Training time row
    time_row = f"{'Train time':<{name_w}}"
    for name in models:
        s = results[name].get("train_time_s")
        if s is None:
            cell = "—"
        elif s < 60:
            cell = f"{s:.1f}s"
        elif s < 3600:
            cell = f"{s/60:.1f}min"
        else:
            cell = f"{s/3600:.1f}h"
        time_row += f"{cell:>{col_w}}"
    print(time_row)

    # Epochs run row
    epoch_row = f"{'Epochs run':<{name_w}}"
    for name in models:
        e = results[name].get("config", {}).get("epochs_run")
        epoch_row += f"{'—' if e is None else str(e):>{col_w}}"
    print(epoch_row)

    # Best val AUC row
    bvauc_row = f"{'Best val AUC':<{name_w}}"
    for name in models:
        v = results[name].get("best_val_auc")
        bvauc_row += f"{'—' if v is None else f'{v:.4f}':>{col_w}}"
    print(bvauc_row)

    print(sep)
    print("  * = best value for that metric")
    print()

    # ── Config summary ────────────────────────────────────────────────────────
    print("  Model configurations:")
    for name in models:
        cfg = results[name].get("config", {})
        print(f"    {name:<6} {cfg}")
    print()

    # ── Winner ────────────────────────────────────────────────────────────────
    print("  Ranking by AUC-ROC:")
    ranked = sorted(
        [(name, results[name].get("test", {}).get("auc", 0)) for name in models],
        key=lambda x: x[1], reverse=True,
    )
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, auc) in enumerate(ranked):
        medal = medals[i] if i < 3 else "  "
        ap    = results[name].get("test", {}).get("ap",  0)
        f1    = results[name].get("test", {}).get("f1",  0)
        t     = results[name].get("train_time_s", 0)
        tstr  = f"{t:.0f}s" if t < 60 else (f"{t/60:.0f}min" if t < 3600 else f"{t/3600:.1f}h")
        print(f"    {medal} {name:<6}  AUC={auc:.4f}  AP={ap:.4f}  F1={f1:.4f}  time={tstr}")
    print()

    # ── Recommendation ────────────────────────────────────────────────────────
    if len(ranked) >= 2:
        winner, winner_auc = ranked[0]
        runner, runner_auc = ranked[1]
        delta = winner_auc - runner_auc
        print(f"  Recommendation: {winner} leads by {delta:.4f} AUC over {runner}.")

        winner_time = results[winner].get("train_time_s", 0)
        runner_time = results[runner].get("train_time_s", 1)
        if winner_time < runner_time:
            print(f"  It also trains {runner_time/max(winner_time,1):.0f}× faster — clear winner.")
        else:
            print(f"  {runner} trains {winner_time/max(runner_time,1):.0f}× faster — consider trade-off.")

    print("=" * len(sep))


def print_learning_curves(results: dict) -> None:
    """Print a mini ASCII learning curve (val AUC per epoch)."""
    print()
    print("  Val AUC learning curves (per epoch):")
    for name, data in results.items():
        history = data.get("history", [])
        if not history:
            continue
        aucs = [row.get("val_auc", 0) for row in history]
        # Mini sparkline: map to 8 levels
        lo, hi = min(aucs), max(aucs)
        rng    = max(hi - lo, 1e-6)
        bars   = " ▁▂▃▄▅▆▇█"
        spark  = "".join(bars[min(int((v - lo) / rng * 8), 8)] for v in aucs)
        print(f"    {name:<6}  [{spark}]  "
              f"start={aucs[0]:.4f} → best={max(aucs):.4f}  ({len(aucs)} epochs)")
    print()


if __name__ == "__main__":
    print("\nLoading results...")
    results = load_results()
    print(f"  Found: {list(results.keys())}\n")
    print_comparison(results)
    print_learning_curves(results)
