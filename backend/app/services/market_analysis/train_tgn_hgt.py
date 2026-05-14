"""
train_tgn_hgt.py
================
Combined TGN + HGT model (Option A — Sequential fusion).

Pipeline per epoch:
  1. TGN memory pass   (no_grad): process all temporal edges chronologically
                                  → per-node state s_i ∈ R^64 capturing event history
  2. Feature fusion    (grad)   : h_i = LayerNorm(Linear(cat(x_i, s_i))) ∈ R^128
                                  TGN memory enriches raw node features with temporal context
  3. HGT encoding      (grad)   : 2× HGTConv over the heterogeneous graph
                                  HGT propagates enriched features across typed relations
  4. Link prediction   (grad)   : MLP(cat(z_src, z_dst)) → sigmoid

Why this combination works:
  - TGN sees WHEN events happen and builds a temporal context per node
  - HGT sees WHO is connected to WHOM across different entity types
  - Fusion: Event nodes "remember" their temporal history before HGT attention

Gradient flow: only through fusion → HGT → head (memory updates are detached,
consistent with standard TGN training to avoid unrolling thousands of GRU steps).

Task  : binary link prediction on IMPACTS edges (causal_label 0 / 1)
Loss  : weighted BCE (71 / 29 class imbalance)
Split : train < 2023  |  val = 2023  |  test ≥ 2024

Outputs:
  checkpoints/tgn_hgt_best.pt    best model weights
  results/tgn_hgt_metrics.json   per-epoch log + test metrics

Run:
    cd backend/app/services/market_analysis
    python train_tgn_hgt.py
"""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import (
    average_precision_score, f1_score, precision_recall_curve,
    precision_score, recall_score, roc_auc_score,
)
from torch_geometric.nn import HGTConv

from gnn_data_adapter import load_dataset

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("train_tgn_hgt")

HERE   = Path(__file__).parent.resolve()
CKPT   = HERE / "checkpoints"; CKPT.mkdir(exist_ok=True)
RESULT = HERE / "results";     RESULT.mkdir(exist_ok=True)
DATA_DIR = HERE / "gnn_causal_dataset"

# ── Device ────────────────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
log.info("Device: %s%s", DEVICE,
         f"  ({torch.cuda.get_device_name(0)})" if DEVICE.type == "cuda" else "")
if DEVICE.type == "cuda":
    torch.backends.cudnn.benchmark = True

# ── Hyper-parameters ──────────────────────────────────────────────────────────
TIME_DIM    = 32     # Time2Vec output dim
MEMORY_DIM  = 64     # TGN per-node GRU state
MSG_DIM     = 64     # TGN message MLP output
HIDDEN      = 128    # HGT hidden / output dim
HGT_LAYERS  = 2
HEADS       = 4
BATCH_SIZE  = 500    # edges per TGN memory-update mini-batch
LR          = 5e-4
WD          = 1e-4
EPOCHS      = 50
PATIENCE    = 10
SEED        = 42


# ─────────────────────────────────────────────────────────────────────────────
# § 1  TGN COMPONENTS
# ─────────────────────────────────────────────────────────────────────────────

class TimeEncoder(nn.Module):
    """Time2Vec: [t, sin(w·t + b)] → R^(TIME_DIM+1)"""
    def __init__(self, dim: int = TIME_DIM):
        super().__init__()
        self.w = nn.Parameter(torch.randn(dim) * 0.1)
        self.b = nn.Parameter(torch.zeros(dim))

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        t = t.unsqueeze(-1)
        return torch.cat([t, torch.sin(t * self.w + self.b)], dim=-1)

    @property
    def out_dim(self) -> int:
        return int(self.w.shape[0]) + 1


class MessageModule(nn.Module):
    """msg = MLP(cat(s_src, s_dst, time_enc(Δt), edge_feat))"""
    def __init__(self, memory_dim: int, t_dim: int,
                 edge_dim: int, out_dim: int):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(2 * memory_dim + t_dim + edge_dim, out_dim * 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(out_dim * 2, out_dim),
        )

    def forward(self, s_src, s_dst, dt_enc, edge_feat):
        return self.mlp(torch.cat([s_src, s_dst, dt_enc, edge_feat], dim=-1))


class MemoryModule(nn.Module):
    """Per-node GRU memory, state[i] ∈ R^MEMORY_DIM."""
    def __init__(self, num_nodes: int, memory_dim: int, msg_dim: int):
        super().__init__()
        self.gru = nn.GRUCell(msg_dim, memory_dim)
        self.register_buffer("memory", torch.zeros(num_nodes, memory_dim))
        self.register_buffer("last_t",  torch.zeros(num_nodes))

    def reset(self) -> None:
        self.memory.zero_(); self.last_t.zero_()

    def detach(self) -> None:
        self.memory = self.memory.detach()

    def get(self, ids: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.memory[ids], self.last_t[ids]

    def update(self, ids: torch.Tensor, msgs: torch.Tensor,
               ts: torch.Tensor) -> None:
        unique, inv = torch.unique(ids, return_inverse=True)
        dev = self.memory.device
        agg  = torch.zeros(unique.size(0), msgs.size(-1), device=dev)
        agg.scatter_add_(0, inv.unsqueeze(1).expand_as(msgs), msgs)
        cnt  = torch.bincount(inv, minlength=unique.size(0)).float().unsqueeze(1)
        agg  = agg / cnt.clamp(min=1)
        self.memory[unique] = self.gru(agg, self.memory[unique])
        agg_t = torch.zeros(unique.size(0), device=dev)
        agg_t.scatter_reduce_(0, inv, ts, reduce="amax", include_self=True)
        self.last_t[unique] = agg_t


# ─────────────────────────────────────────────────────────────────────────────
# § 2  COMBINED TGN + HGT MODEL
# ─────────────────────────────────────────────────────────────────────────────

class TGNHGTModel(nn.Module):
    """
    Sequential TGN → HGT model.

    Memory update (no_grad):
        For every edge (src, dst, t, feat) in chronological order:
            msg_src = MLP(s_src, s_dst, time_enc(t−last_t[src]), feat)
            msg_dst = MLP(s_dst, s_src, time_enc(t−last_t[dst]), feat)
            s_src, s_dst ← GRU(msg)

    Encode (grad):
        h[v] = LayerNorm(Linear(cat(x[v], s[v])))   for each node type
        h    = HGTConv × 2 (h, edge_index)
        → z_dict per node type

    Decode:
        score = MLP(cat(z_src, z_dst)) → sigmoid
    """

    def __init__(self, num_nodes: int, metadata, node_feat_dim: int = 396,
                 edge_feat_dim: int = 2):
        super().__init__()
        node_types = metadata[0]

        # TGN
        self.time_enc = TimeEncoder(TIME_DIM)
        t_dim         = self.time_enc.out_dim
        self.memory   = MemoryModule(num_nodes, MEMORY_DIM, MSG_DIM)
        self.msg_fn   = MessageModule(MEMORY_DIM, t_dim, edge_feat_dim, MSG_DIM)
        self.feat_proj = nn.Linear(node_feat_dim, MEMORY_DIM)   # warmup

        # Fusion per node type: cat(x, memory) → HIDDEN
        self.fusion = nn.ModuleDict({
            nt: nn.Sequential(
                nn.Linear(node_feat_dim + MEMORY_DIM, HIDDEN),
                nn.LayerNorm(HIDDEN),
                nn.ReLU(),
            )
            for nt in node_types
        })

        # HGT layers + residual norms
        self.convs = nn.ModuleList([
            HGTConv(HIDDEN, HIDDEN, metadata, heads=HEADS)
            for _ in range(HGT_LAYERS)
        ])
        self.norms = nn.ModuleList([
            nn.ModuleDict({nt: nn.LayerNorm(HIDDEN) for nt in node_types})
            for _ in range(HGT_LAYERS)
        ])

        # Link prediction head
        self.head = nn.Sequential(
            nn.Linear(2 * HIDDEN, HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(HIDDEN, 1),
        )

    # ── TGN memory ────────────────────────────────────────────────────────────

    def warmup_memory(self, x: torch.Tensor) -> None:
        with torch.no_grad():
            self.memory.memory.copy_(self.feat_proj(x))

    @torch.no_grad()
    def update_memory(self, src: torch.Tensor, dst: torch.Tensor,
                      t: torch.Tensor, edge_feat: torch.Tensor) -> None:
        """One mini-batch of TGN memory updates (no gradient tracked)."""
        s_src, t_src = self.memory.get(src)
        s_dst, t_dst = self.memory.get(dst)
        dt_src = self.time_enc((t - t_src).clamp(min=0))
        dt_dst = self.time_enc((t - t_dst).clamp(min=0))
        msg_src = self.msg_fn(s_src, s_dst, dt_src, edge_feat)
        msg_dst = self.msg_fn(s_dst, s_src, dt_dst, edge_feat)
        self.memory.update(torch.cat([src, dst]),
                           torch.cat([msg_src, msg_dst]),
                           torch.cat([t, t]))

    # ── HGT encode ────────────────────────────────────────────────────────────

    def encode(self, x_dict: dict, edge_index_dict: dict,
               type_to_gids: dict) -> dict:
        """
        Fuse TGN memory into raw features, then run HGT.
        type_to_gids: {node_type → LongTensor of global IDs (same order as x_dict)}
        """
        h = {}
        for ntype, x in x_dict.items():
            gids = type_to_gids[ntype]
            mem  = self.memory.memory[gids]          # [N_type, MEMORY_DIM]
            h[ntype] = self.fusion[ntype](
                torch.cat([x, mem], dim=-1)          # [N_type, feat+mem]
            )

        for i, conv in enumerate(self.convs):
            h_new = conv(h, edge_index_dict)
            h = {
                nt: self.norms[i][nt](h[nt] + h_new[nt])
                if nt in h_new else h[nt]
                for nt in h
            }
        return h

    def decode(self, z_src: torch.Tensor, z_dst: torch.Tensor) -> torch.Tensor:
        return self.head(torch.cat([z_src, z_dst], dim=-1)).squeeze(-1)


# ─────────────────────────────────────────────────────────────────────────────
# § 3  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_type_to_gids(node_types: List[str]) -> Dict[str, torch.Tensor]:
    """Read nodes.csv and build {node_type: [global_ids]} in local order."""
    type_to_gids: Dict[str, List[int]] = {nt: [] for nt in node_types}
    with open(DATA_DIR / "nodes.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            nt = row["type"]
            if nt in type_to_gids:
                type_to_gids[nt].append(int(row["id"]))
    return {nt: torch.tensor(gids, dtype=torch.long, device=DEVICE)
            for nt, gids in type_to_gids.items() if gids}


def _run_memory_pass(model: TGNHGTModel, src, dst, t, edge_attr,
                     mask: torch.Tensor) -> None:
    """Feed all edges covered by mask into TGN memory in temporal order."""
    idxs = mask.nonzero(as_tuple=True)[0]
    for i in range(0, idxs.size(0), BATCH_SIZE):
        batch = idxs[i: i + BATCH_SIZE]
        model.update_memory(src[batch], dst[batch], t[batch], edge_attr[batch])


def _get_impacts(data, split: str, device):
    """Collect (ei_src, ei_dst, y, src_type, dst_type) for IMPACTS edges in split."""
    result = []
    for rel in data.edge_types:
        st, et, dt = rel
        if et != "IMPACTS":
            continue
        rd   = data[st, et, dt]
        mask = getattr(rd, f"{split}_mask")
        if mask.sum() == 0:
            continue
        ei = rd.edge_index[:, mask].to(device)
        y  = rd.y[mask].to(device)
        result.append((ei[0], ei[1], y, st, dt))
    return result


def _predict(model, z_dict, data, split, device):
    all_logits, all_y = [], []
    for si, di, y, st, dt in _get_impacts(data, split, device):
        logits = model.decode(z_dict[st][si], z_dict[dt][di])
        all_logits.append(logits); all_y.append(y)
    if not all_logits:
        return torch.tensor([]), torch.tensor([])
    return torch.cat(all_logits), torch.cat(all_y)


def _best_threshold(probs: np.ndarray, labels: np.ndarray) -> float:
    p, r, thr = precision_recall_curve(labels, probs)
    f1s = 2 * p * r / np.clip(p + r, 1e-8, None)
    return float(thr[int(np.argmax(f1s[:-1]))])


def _metrics(probs: np.ndarray, labels: np.ndarray,
             threshold: Optional[float] = None) -> dict:
    if len(probs) == 0:
        return {"auc": 0., "ap": 0., "f1": 0.,
                "precision": 0., "recall": 0., "threshold": .5}
    t     = threshold if threshold is not None else 0.5
    preds = (probs >= t).astype(int)
    try:
        auc = float(roc_auc_score(labels, probs))
        ap  = float(average_precision_score(labels, probs))
    except ValueError:
        auc = ap = 0.
    return {
        "auc":       round(auc, 4),
        "ap":        round(ap, 4),
        "f1":        round(float(f1_score(labels, preds, zero_division=0)), 4),
        "precision": round(float(precision_score(labels, preds, zero_division=0)), 4),
        "recall":    round(float(recall_score(labels, preds, zero_division=0)), 4),
        "threshold": round(t, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# § 4  TRAINING LOOP
# ─────────────────────────────────────────────────────────────────────────────

def train(hetero, temporal: dict) -> dict:
    torch.manual_seed(SEED); np.random.seed(SEED)

    # Temporal tensors
    src        = temporal["src"].to(DEVICE)
    dst        = temporal["dst"].to(DEVICE)
    t          = temporal["t"].to(DEVICE)
    edge_attr  = temporal["edge_attr"].to(DEVICE)
    train_mask = temporal["train_mask"].to(DEVICE)
    val_mask   = temporal["val_mask"].to(DEVICE)
    test_mask  = temporal["test_mask"].to(DEVICE)
    num_nodes  = temporal["num_nodes"]

    # HeteroData tensors
    x_dict          = {nt: hetero[nt].x.to(DEVICE) for nt in hetero.node_types}
    edge_index_dict = {rel: hetero[rel].edge_index.to(DEVICE)
                       for rel in hetero.edge_types}
    type_to_gids    = _build_type_to_gids(list(hetero.node_types))

    # Model
    metadata = hetero.metadata()
    model    = TGNHGTModel(num_nodes, metadata,
                           node_feat_dim=396,
                           edge_feat_dim=edge_attr.size(1)).to(DEVICE)
    model.warmup_memory(temporal["x"].to(DEVICE))

    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WD)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    # Class weight across all IMPACTS train edges
    n0, n1 = 0, 0
    for rel in hetero.edge_types:
        st, et, dt = rel
        if et != "IMPACTS" or not hasattr(hetero[st, et, dt], "y"):
            continue
        tr_y = hetero[st, et, dt].y[hetero[st, et, dt].train_mask]
        n1  += int((tr_y == 1).sum()); n0 += int((tr_y == 0).sum())
    pos_weight = torch.tensor(n0 / max(n1, 1), dtype=torch.float).to(DEVICE)
    criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    log.info("TGN+HGT — memory=%d  hidden=%d  hgt_layers=%d  heads=%d  epochs=%d",
             MEMORY_DIM, HIDDEN, HGT_LAYERS, HEADS, EPOCHS)
    log.info("  pos_weight=%.4f  (n0=%d  n1=%d)", float(pos_weight), n0, n1)
    log.info("  Architecture: TGN memory → fusion → 2×HGTConv → MLP head")

    best_val_auc = 0.0
    patience_ctr = 0
    history: List[dict] = []
    t0 = time.time()

    for epoch in range(1, EPOCHS + 1):
        ep_t0 = time.time()

        # ── Phase 1: TGN memory pass over train edges (no gradient) ───────────
        model.train()
        model.memory.reset()
        model.warmup_memory(temporal["x"].to(DEVICE))
        _run_memory_pass(model, src, dst, t, edge_attr, train_mask)

        # ── Phase 2: HGT encode + decode + loss (gradient tracked) ────────────
        optimizer.zero_grad()
        z_dict = model.encode(x_dict, edge_index_dict, type_to_gids)
        train_logits, train_y = _predict(model, z_dict, hetero, "train", DEVICE)
        loss = criterion(train_logits, train_y.float())
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        # ── Phase 3: Validation (extend memory with val edges) ────────────────
        model.eval()
        with torch.no_grad():
            _run_memory_pass(model, src, dst, t, edge_attr, val_mask)
            z_dict   = model.encode(x_dict, edge_index_dict, type_to_gids)
            val_log, val_y = _predict(model, z_dict, hetero, "val", DEVICE)

        train_m = _metrics(
            torch.sigmoid(train_logits.detach()).cpu().numpy(),
            train_y.cpu().numpy(),
        )
        val_m = _metrics(
            torch.sigmoid(val_log).cpu().numpy(),
            val_y.cpu().numpy(),
        )

        row = {
            "epoch":     epoch,
            "loss":      round(float(loss.detach()), 5),
            "train_auc": train_m["auc"],
            "val_auc":   val_m["auc"],
            "val_ap":    val_m["ap"],
            "val_f1":    val_m["f1"],
            "val_prec":  val_m["precision"],
            "val_rec":   val_m["recall"],
            "epoch_s":   round(time.time() - ep_t0, 1),
        }
        history.append(row)
        log.info(
            "Epoch %3d/%d | loss=%.4f | train_auc=%.4f | "
            "val_auc=%.4f  val_f1=%.4f  val_ap=%.4f  [%.1fs]",
            epoch, EPOCHS, row["loss"], row["train_auc"],
            row["val_auc"], row["val_f1"], row["val_ap"], row["epoch_s"],
        )

        if val_m["auc"] > best_val_auc + 1e-4:
            best_val_auc = val_m["auc"]
            torch.save(model.state_dict(), CKPT / "tgn_hgt_best.pt")
            patience_ctr = 0
        else:
            patience_ctr += 1
            if patience_ctr >= PATIENCE:
                log.info("Early stopping at epoch %d", epoch)
                break

    train_time = round(time.time() - t0, 2)

    # ── Test ──────────────────────────────────────────────────────────────────
    model.load_state_dict(torch.load(CKPT / "tgn_hgt_best.pt",
                                     map_location=DEVICE, weights_only=True))
    model.eval()
    with torch.no_grad():
        model.memory.reset()
        model.warmup_memory(temporal["x"].to(DEVICE))
        _run_memory_pass(model, src, dst, t, edge_attr, train_mask | val_mask)
        z_dict            = model.encode(x_dict, edge_index_dict, type_to_gids)
        val_log2, val_y2  = _predict(model, z_dict, hetero, "val", DEVICE)
        opt_thresh        = _best_threshold(
            torch.sigmoid(val_log2).cpu().numpy(), val_y2.cpu().numpy()
        )
        _run_memory_pass(model, src, dst, t, edge_attr, test_mask)
        z_dict            = model.encode(x_dict, edge_index_dict, type_to_gids)
        test_log, test_y  = _predict(model, z_dict, hetero, "test", DEVICE)

    test_m = _metrics(
        torch.sigmoid(test_log).cpu().numpy(),
        test_y.cpu().numpy(),
        threshold=opt_thresh,
    )

    log.info("=" * 55)
    log.info("TGN+HGT FINAL TEST RESULTS  (threshold=%.3f)", opt_thresh)
    log.info("  AUC-ROC   : %.4f", test_m["auc"])
    log.info("  Avg Prec  : %.4f", test_m["ap"])
    log.info("  F1        : %.4f", test_m["f1"])
    log.info("  Precision : %.4f", test_m["precision"])
    log.info("  Recall    : %.4f", test_m["recall"])
    log.info("  Train time: %.1f s", train_time)
    log.info("=" * 55)

    output = {
        "model":        "TGN+HGT",
        "config":       {"memory_dim": MEMORY_DIM, "hidden": HIDDEN,
                         "hgt_layers": HGT_LAYERS, "heads": HEADS,
                         "lr": LR, "epochs_run": len(history)},
        "test":         test_m,
        "best_val_auc": round(best_val_auc, 4),
        "train_time_s": train_time,
        "history":      history,
    }
    (RESULT / "tgn_hgt_metrics.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8")
    log.info("Results saved → results/tgn_hgt_metrics.json")
    log.info("Checkpoint  → checkpoints/tgn_hgt_best.pt")
    return output


# ─────────────────────────────────────────────────────────────────────────────
# § 5  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    hetero, temporal = load_dataset()
    train(hetero, temporal)
