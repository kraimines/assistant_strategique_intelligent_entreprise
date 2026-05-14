"""
train_hgt.py
============
Heterogeneous Graph Transformer (HGT) + temporal encoding
for causal link prediction on Talan's market knowledge graph.

Architecture:
  1. Per-type linear projection  : 396 → 128
  2. Sinusoidal temporal encoding: already injected into Event.x by the adapter
  3. 2 × HGTConv layers          : 128-d, 4 attention heads
  4. Link prediction MLP head    : concat(z_src, z_dst) → sigmoid

Task  : binary link prediction on IMPACTS edges  (causal_label 0 / 1)
Loss  : weighted BCE   (class weights from adapter, handles 71 / 29 imbalance)
Split : train < 2023  |  val = 2023  |  test ≥ 2024

Outputs:
  checkpoints/hgt_best.pt     best model weights (highest val AUC)
  results/hgt_metrics.json    per-epoch log + final test metrics

Run:
    cd backend/app/services/market_analysis
    python train_hgt.py
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import (
    roc_auc_score, f1_score, precision_score, recall_score, average_precision_score,
)
from torch_geometric.nn import HGTConv, Linear

from gnn_data_adapter import load_dataset

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("train_hgt")

HERE   = Path(__file__).parent.resolve()
CKPT   = HERE / "checkpoints"; CKPT.mkdir(exist_ok=True)
RESULT = HERE / "results";     RESULT.mkdir(exist_ok=True)

# ── Device ────────────────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
log.info("Device: %s%s", DEVICE,
         f"  ({torch.cuda.get_device_name(0)})" if DEVICE.type == "cuda" else "")
if DEVICE.type == "cuda":
    torch.backends.cudnn.benchmark = True

# ── Hyper-parameters ──────────────────────────────────────────────────────────
HIDDEN   = 128
HEADS    = 4
LAYERS   = 2
LR       = 1e-3
WD       = 1e-4
EPOCHS   = 50
PATIENCE = 10
SEED     = 42
THRESH   = 0.5   # default; overridden by val-set optimal threshold after training


# ─────────────────────────────────────────────────────────────────────────────
# § 1  MODEL
# ─────────────────────────────────────────────────────────────────────────────

class HGTLinkPredictor(nn.Module):
    """
    Heterogeneous Graph Transformer for link prediction.

    Encodes every node in the heterogeneous graph using HGTConv, then scores
    each IMPACTS edge via a 2-layer MLP on the concatenated (src, dst) embeddings.
    """

    def __init__(self, metadata, in_dim: int = 396,
                 hidden: int = 128, heads: int = 4, num_layers: int = 2):
        super().__init__()

        node_types = metadata[0]

        # Per-type input projection (all share the same in_dim = 396)
        self.proj = nn.ModuleDict({
            ntype: Linear(in_dim, hidden, bias=True)
            for ntype in node_types
        })

        # HGT message-passing layers
        self.convs = nn.ModuleList([
            HGTConv(hidden, hidden, metadata, heads=heads)
            for _ in range(num_layers)
        ])

        # Batch norms per layer per node type
        self.norms = nn.ModuleList([
            nn.ModuleDict({ntype: nn.LayerNorm(hidden) for ntype in node_types})
            for _ in range(num_layers)
        ])

        # Link prediction head
        self.head = nn.Sequential(
            nn.Linear(2 * hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden, 1),
        )

    def encode(self, x_dict: dict, edge_index_dict: dict) -> dict:
        # Input projection
        h = {ntype: F.elu(self.proj[ntype](x)) for ntype, x in x_dict.items()}

        # HGT layers
        for i, conv in enumerate(self.convs):
            h_new = conv(h, edge_index_dict)
            # Residual + LayerNorm per node type
            h = {
                ntype: self.norms[i][ntype](h[ntype] + h_new[ntype])
                if ntype in h_new else h[ntype]
                for ntype in h
            }
        return h

    def decode(self, z_src: torch.Tensor, z_dst: torch.Tensor) -> torch.Tensor:
        """Score edges given source and destination embeddings."""
        return self.head(torch.cat([z_src, z_dst], dim=-1)).squeeze(-1)

    def forward(self, x_dict, edge_index_dict):
        return self.encode(x_dict, edge_index_dict)


# ─────────────────────────────────────────────────────────────────────────────
# § 2  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_impacts_tensors(data, split: str):
    """
    Collect (src_emb_indices, dst_emb_indices, labels, src_type, dst_type)
    for all IMPACTS relations in the requested split mask.

    Returns list of (ei_src, ei_dst, y, src_type, dst_type) tuples.
    """
    result = []
    for rel in data.edge_types:
        src_t, et, dst_t = rel
        if et != "IMPACTS":
            continue
        rel_data = data[src_t, et, dst_t]
        mask = getattr(rel_data, f"{split}_mask")
        if mask.sum() == 0:
            continue
        ei  = rel_data.edge_index[:, mask].to(DEVICE)
        y   = rel_data.y[mask].to(DEVICE)
        result.append((ei[0], ei[1], y, src_t, dst_t))
    return result


def _predict(model, z_dict, data, split: str):
    """Run decode on all IMPACTS relations for a given split. Returns (logits, labels)."""
    all_logits, all_y = [], []
    for src_idx, dst_idx, y, src_t, dst_t in _get_impacts_tensors(data, split):
        z_src = z_dict[src_t][src_idx]
        z_dst = z_dict[dst_t][dst_idx]
        logits = model.decode(z_src, z_dst)
        all_logits.append(logits)
        all_y.append(y)
    if not all_logits:
        return torch.tensor([]), torch.tensor([])
    return torch.cat(all_logits), torch.cat(all_y)


def _best_threshold(probs: np.ndarray, labels: np.ndarray) -> float:
    """Find the threshold maximising F1 on the given set."""
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(labels, probs)
    f1s = 2 * precision * recall / np.clip(precision + recall, 1e-8, None)
    best_idx = int(np.argmax(f1s[:-1]))   # thresholds is 1 shorter
    return float(thresholds[best_idx])


def _metrics(logits: torch.Tensor, y: torch.Tensor,
             threshold: Optional[float] = None) -> dict:
    if logits.numel() == 0:
        return {"auc": 0.0, "ap": 0.0, "f1": 0.0, "precision": 0.0,
                "recall": 0.0, "threshold": THRESH}
    probs  = torch.sigmoid(logits).detach().cpu().numpy()
    labels = y.cpu().numpy()
    t      = threshold if threshold is not None else THRESH
    preds  = (probs >= t).astype(int)
    try:
        auc = float(roc_auc_score(labels, probs))
        ap  = float(average_precision_score(labels, probs))
    except ValueError:
        auc = ap = 0.0
    return {
        "auc":       round(auc, 4),
        "ap":        round(ap, 4),
        "f1":        round(float(f1_score(labels, preds, zero_division=0)), 4),
        "precision": round(float(precision_score(labels, preds, zero_division=0)), 4),
        "recall":    round(float(recall_score(labels, preds, zero_division=0)), 4),
        "threshold": round(t, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# § 3  TRAINING LOOP
# ─────────────────────────────────────────────────────────────────────────────

def train(data):
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    metadata  = data.metadata()
    model     = HGTLinkPredictor(metadata, in_dim=396, hidden=HIDDEN,
                                  heads=HEADS, num_layers=LAYERS).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WD)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    # Class weights — aggregate n0/n1 across ALL IMPACTS relations (avoid
    # the zero-tensor falsy bug that occurs when one relation is all-positive)
    n0_total, n1_total = 0, 0
    for rel in data.edge_types:
        src_t, et, dst_t = rel
        if et != "IMPACTS":
            continue
        rel_store = data[src_t, et, dst_t]
        if not hasattr(rel_store, "y") or not hasattr(rel_store, "train_mask"):
            continue
        tr_y = rel_store.y[rel_store.train_mask]
        n1_total += int((tr_y == 1).sum())
        n0_total += int((tr_y == 0).sum())

    pos_weight = torch.tensor(n0_total / max(n1_total, 1), dtype=torch.float).to(DEVICE)
    criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    # Prepare x_dict and edge_index_dict (move to device — CPU)
    x_dict          = {nt: data[nt].x.to(DEVICE)         for nt in data.node_types}
    edge_index_dict = {rel: data[rel].edge_index.to(DEVICE) for rel in data.edge_types}

    best_val_auc = 0.0
    patience_ctr = 0
    history      = []

    log.info("HGT training — hidden=%d  heads=%d  layers=%d  epochs=%d",
             HIDDEN, HEADS, LAYERS, EPOCHS)
    log.info("  pos_weight = %.4f  (n0=%d  n1=%d)", float(pos_weight), n0_total, n1_total)

    t0 = time.time()

    for epoch in range(1, EPOCHS + 1):
        # ── Train ─────────────────────────────────────────────────────────────
        model.train()
        optimizer.zero_grad()

        z_dict = model(x_dict, edge_index_dict)

        train_logits, train_y = _predict(model, z_dict, data, "train")
        loss = criterion(train_logits, train_y.float())
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        # ── Validate ──────────────────────────────────────────────────────────
        model.eval()
        with torch.no_grad():
            z_dict   = model(x_dict, edge_index_dict)
            val_log, val_y = _predict(model, z_dict, data, "val")
            val_m    = _metrics(val_log, val_y)
            train_m  = _metrics(train_logits.detach(), train_y)

        row = {
            "epoch":      epoch,
            "loss":       round(float(loss.detach()), 5),
            "train_auc":  train_m["auc"],
            "val_auc":    val_m["auc"],
            "val_ap":     val_m["ap"],
            "val_f1":     val_m["f1"],
            "val_prec":   val_m["precision"],
            "val_rec":    val_m["recall"],
        }
        history.append(row)

        log.info(
            "Epoch %3d/%d | loss=%.4f | train_auc=%.4f | "
            "val_auc=%.4f  val_f1=%.4f  val_ap=%.4f",
            epoch, EPOCHS, row["loss"], row["train_auc"],
            row["val_auc"], row["val_f1"], row["val_ap"],
        )

        # ── Early stopping ────────────────────────────────────────────────────
        if val_m["auc"] > best_val_auc + 1e-4:
            best_val_auc = val_m["auc"]
            torch.save(model.state_dict(), CKPT / "hgt_best.pt")
            patience_ctr = 0
        else:
            patience_ctr += 1
            if patience_ctr >= PATIENCE:
                log.info("Early stopping at epoch %d (patience=%d)", epoch, PATIENCE)
                break

    train_time = round(time.time() - t0, 2)

    # ── Test on best checkpoint ───────────────────────────────────────────────
    model.load_state_dict(torch.load(CKPT / "hgt_best.pt",
                                     map_location=DEVICE, weights_only=True))
    model.eval()
    with torch.no_grad():
        z_dict           = model(x_dict, edge_index_dict)
        # Calibrate threshold on val set, then apply to test
        val_log2, val_y2 = _predict(model, z_dict, data, "val")
        val_probs        = torch.sigmoid(val_log2).cpu().numpy()
        opt_thresh       = _best_threshold(val_probs, val_y2.cpu().numpy())
        test_log, test_y = _predict(model, z_dict, data, "test")
        test_m           = _metrics(test_log, test_y, threshold=opt_thresh)

    log.info("=" * 55)
    log.info("HGT FINAL TEST RESULTS  (threshold=%.3f)", opt_thresh)
    log.info("  AUC-ROC   : %.4f", test_m["auc"])
    log.info("  Avg Prec  : %.4f", test_m["ap"])
    log.info("  F1        : %.4f", test_m["f1"])
    log.info("  Precision : %.4f", test_m["precision"])
    log.info("  Recall    : %.4f", test_m["recall"])
    log.info("  Train time: %.1f s", train_time)
    log.info("=" * 55)

    # ── Save results ──────────────────────────────────────────────────────────
    output = {
        "model":       "HGT",
        "config":      {"hidden": HIDDEN, "heads": HEADS,
                        "layers": LAYERS, "lr": LR, "epochs_run": len(history)},
        "test":        test_m,
        "best_val_auc": round(best_val_auc, 4),
        "train_time_s": train_time,
        "history":     history,
    }
    (RESULT / "hgt_metrics.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    log.info("Results saved → results/hgt_metrics.json")
    log.info("Checkpoint  → checkpoints/hgt_best.pt")
    return output


# ─────────────────────────────────────────────────────────────────────────────
# § 4  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    hetero, _ = load_dataset()
    train(hetero)
