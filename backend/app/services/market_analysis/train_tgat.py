"""
train_tgat.py
=============
Temporal Graph Attention Network (TGAT) for causal link prediction
on Talan's market knowledge graph.

Architecture:
  1. Time2Vec encoder     : scalar t → (TIME_DIM+1)-d sinusoidal embedding
  2. 2 × TSAT layers      : Temporal Self-Attention — for node v at time t,
                            attends over its K most-recent temporal neighbors
                            using raw node features + time encoding.
                            No memory module (stateless per-event embedding).
  3. Link prediction MLP  : concat(z_src, z_dst) → sigmoid

Key difference from TGN:
  - NO per-node GRU memory — embedding is computed fresh each time
  - Faster per epoch, no state leakage between batches
  - Less expressive for long-range temporal dependencies

Task  : binary link prediction on IMPACTS edges (causal_label 0 / 1)
Loss  : weighted BCE (handles 71 / 29 class imbalance)
Split : train < 2023  |  val = 2023  |  test ≥ 2024

Outputs:
  checkpoints/tgat_best.pt    best model weights (highest val AUC)
  results/tgat_metrics.json   per-epoch log + final test metrics

Run:
    cd backend/app/services/market_analysis
    python train_tgat.py
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
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

from gnn_data_adapter import load_dataset

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("train_tgat")

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
TIME_DIM    = 32    # Time2Vec periodic components
HIDDEN_DIM  = 128   # TSAT hidden / output dimension
N_HEADS     = 4     # attention heads per TSAT layer
N_LAYERS    = 2     # stacked TSAT layers
N_NEIGHBORS = 20    # max temporal neighbors per node per layer
BATCH_SIZE  = 200   # IMPACTS edges per mini-batch (smaller than TGN — no memory)
LR          = 5e-4
WD          = 1e-4
EPOCHS      = 50
PATIENCE    = 10
SEED        = 42


# ─────────────────────────────────────────────────────────────────────────────
# § 1  TIME ENCODING  (Time2Vec)
# ─────────────────────────────────────────────────────────────────────────────

class TimeEncoder(nn.Module):
    """
    Time2Vec: φ(t) = [t, sin(w_1·t+b_1), …, sin(w_d·t+b_d)]
    out_dim = TIME_DIM + 1
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# § 2  TEMPORAL SELF-ATTENTION LAYER  (TSAT)
# ─────────────────────────────────────────────────────────────────────────────

class TSATLayer(nn.Module):
    """
    One Temporal Self-Attention layer.

    For a node v with feature h_v ∈ R^feat_dim at query time t:
      Q = Linear( cat(h_v,    φ(0)) )             [1, hidden]
      K = Linear( cat(h_nbrs, φ(t - t_nbrs)) )   [K, hidden]
      V = Linear( cat(h_nbrs, φ(t - t_nbrs)) )   [K, hidden]
      attn_out = MHA(Q, K, V)                     [1, hidden]
      out = LayerNorm( Linear(cat(attn_out, h_v)) )

    When no neighbors exist: out = LayerNorm(Linear(h_v))
    """

    def __init__(self, feat_dim: int, time_enc_dim: int,
                 hidden: int, n_heads: int):
        super().__init__()
        in_qkv = feat_dim + time_enc_dim
        self.q_proj = nn.Linear(in_qkv, hidden)
        self.k_proj = nn.Linear(in_qkv, hidden)
        self.v_proj = nn.Linear(in_qkv, hidden)
        self.attn   = nn.MultiheadAttention(hidden, n_heads,
                                             batch_first=True, dropout=0.1)
        # Merge attended output with input feature (skip connection)
        self.ff     = nn.Sequential(
            nn.Linear(hidden + feat_dim, hidden),
            nn.GELU(),
        )
        self.norm   = nn.LayerNorm(hidden)
        # Fallback when no neighbors
        self.no_nbr = nn.Linear(feat_dim, hidden)

    def forward(
        self,
        h_v:    torch.Tensor,           # [B, feat_dim]
        h_nbrs: List[torch.Tensor],     # per node: [K_i, feat_dim]
        t_v:    torch.Tensor,           # [B]  query timestamps
        t_nbrs: List[torch.Tensor],     # per node: [K_i] neighbor timestamps
        time_enc: nn.Module,
    ) -> torch.Tensor:                  # [B, hidden]

        B   = h_v.size(0)
        t0  = time_enc(torch.zeros(1, device=h_v.device))   # [1, t_enc_dim]
        out = []

        for i in range(B):
            nbrs = h_nbrs[i]
            if nbrs.numel() == 0 or nbrs.size(0) == 0:
                out.append(self.norm(self.no_nbr(h_v[i])))
                continue

            nts     = t_nbrs[i].to(h_v.device)          # [K]
            dt      = (t_v[i] - nts).clamp(min=0)        # [K]
            t_nbr_enc = time_enc(dt)                      # [K, t_enc_dim]
            t_v_enc   = t0.expand(1, -1)                  # [1, t_enc_dim]

            # Queries, keys, values
            q = self.q_proj(
                torch.cat([h_v[i].unsqueeze(0), t_v_enc], dim=-1)
            )                                              # [1, hidden]
            kv_in = torch.cat([nbrs.to(h_v.device), t_nbr_enc], dim=-1)
            k = self.k_proj(kv_in)                        # [K, hidden]
            v = self.v_proj(kv_in)                        # [K, hidden]

            # Batched multi-head attention: [1, 1, H] ← [1, K, H]
            attn_out, _ = self.attn(
                q.unsqueeze(0), k.unsqueeze(0), v.unsqueeze(0)
            )
            attn_out = attn_out.squeeze(0).squeeze(0)     # [hidden]

            # Skip connection + FF
            merged = self.ff(torch.cat([attn_out, h_v[i]], dim=-1))
            out.append(self.norm(merged))

        return torch.stack(out, dim=0)    # [B, hidden]


# ─────────────────────────────────────────────────────────────────────────────
# § 3  TGAT MODEL
# ─────────────────────────────────────────────────────────────────────────────

class TGAT(nn.Module):
    """
    2-layer Temporal Graph Attention Network.

    Layer 1: embed each 1-hop neighbor using ITS OWN temporal neighborhood
             (raw features only for simplicity — avoids O(K²) recursion).
    Layer 2: embed the target node using Layer-1 neighbor embeddings.

    This is the standard 2-hop TGAT approximation efficient on CPU.
    """

    def __init__(self, node_feat_dim: int, edge_feat_dim: int = 2):
        super().__init__()
        self.time_enc = TimeEncoder(TIME_DIM)
        t_dim         = self.time_enc.out_dim

        # Layer 1: raw features → HIDDEN_DIM  (used to embed neighbors)
        self.layer1 = TSATLayer(node_feat_dim, t_dim, HIDDEN_DIM, N_HEADS)
        # Layer 2: HIDDEN_DIM  → HIDDEN_DIM  (used to embed target node)
        self.layer2 = TSATLayer(HIDDEN_DIM,    t_dim, HIDDEN_DIM, N_HEADS)

        self.predictor = nn.Sequential(
            nn.Linear(2 * HIDDEN_DIM, HIDDEN_DIM),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(HIDDEN_DIM, 1),
        )

    def embed_nodes(
        self,
        node_ids:  torch.Tensor,         # [B]
        t_query:   torch.Tensor,         # [B]
        x:         torch.Tensor,         # [N, feat_dim]
        nbr_store: "TemporalNeighborStore",
    ) -> torch.Tensor:                   # [B, HIDDEN_DIM]
        """
        Two-layer temporal attention embedding.

        Layer 1 — embed each neighbor of each query node:
          For every (node, neighbor) pair, embed the neighbor using ITS
          own temporal context (raw features only, for efficiency).

        Layer 2 — embed each query node:
          Use the Layer-1 embeddings of its neighbors.
        """
        B = node_ids.size(0)

        # ── Layer 2 neighbor lookup (query nodes' neighbors) ──────────────────
        nbr_ids_L2, nbr_ts_L2 = nbr_store.query(node_ids, t_query)

        # ── Layer 1: embed each neighbor ──────────────────────────────────────
        # Collect all unique neighbors across the batch
        all_nbr_ids = torch.cat(
            [n for n in nbr_ids_L2 if n.numel() > 0]
        ) if any(n.numel() > 0 for n in nbr_ids_L2) else torch.tensor([], dtype=torch.long)
        all_nbr_t   = torch.cat(
            [t for t in nbr_ts_L2  if t.numel() > 0]
        ) if any(t.numel() > 0 for t in nbr_ts_L2)  else torch.tensor([], dtype=torch.float)

        nbr_embed: Dict[int, torch.Tensor] = {}
        if all_nbr_ids.numel() > 0:
            unique_nbrs, _ = torch.unique(all_nbr_ids, return_inverse=True)
            # Map unique neighbor id → its most recent query time in this batch
            nbr_t_map: Dict[int, float] = {}
            for nid, nt in zip(all_nbr_ids.tolist(), all_nbr_t.tolist()):
                nbr_t_map[nid] = max(nbr_t_map.get(nid, 0.0), nt)

            un_list = unique_nbrs.tolist()
            un_t    = torch.tensor([nbr_t_map[nid] for nid in un_list])
            # Look up each unique neighbor's own 1-hop context
            nn_ids, nn_ts = nbr_store.query(unique_nbrs, un_t)

            # Batch-embed unique neighbors (Layer 1)
            h_unique = x[unique_nbrs]                       # [U, feat_dim]
            nn_feats = [x[ids] if ids.numel() > 0
                        else torch.zeros(0, x.size(1))
                        for ids in nn_ids]
            with torch.no_grad():   # Layer-1 neighbors don't need grad tracking
                h_unique = self.layer1(h_unique, nn_feats, un_t, nn_ts,
                                       self.time_enc)       # [U, HIDDEN_DIM]

            for uid, h in zip(unique_nbrs.tolist(), h_unique):
                nbr_embed[uid] = h

        # ── Layer 2: embed query nodes ────────────────────────────────────────
        h_target    = x[node_ids]                            # [B, feat_dim]
        # Project raw features to HIDDEN_DIM so Layer 2 gets correct input shape
        # (Layer 2 expects feat_dim = HIDDEN_DIM; use layer1's no_nbr fallback trick)
        # We project via a dummy layer1 call with no neighbors
        dummy_nbrs = [torch.zeros(0, x.size(1)) for _ in range(B)]
        dummy_ts   = [torch.zeros(0) for _ in range(B)]
        h_target   = self.layer1(h_target, dummy_nbrs, t_query, dummy_ts,
                                  self.time_enc)             # [B, HIDDEN_DIM]

        # Build per-query-node neighbor embedding lists for Layer 2
        nbr_h_L2 = []
        for i in range(B):
            ids = nbr_ids_L2[i]
            if ids.numel() == 0:
                nbr_h_L2.append(torch.zeros(0, HIDDEN_DIM))
            else:
                nbr_h_L2.append(
                    torch.stack([nbr_embed.get(nid, torch.zeros(HIDDEN_DIM))
                                  for nid in ids.tolist()])
                )

        z = self.layer2(h_target, nbr_h_L2, t_query, nbr_ts_L2,
                         self.time_enc)                      # [B, HIDDEN_DIM]
        return z

    def predict(self, z_src: torch.Tensor, z_dst: torch.Tensor) -> torch.Tensor:
        return self.predictor(torch.cat([z_src, z_dst], dim=-1)).squeeze(-1)


# ─────────────────────────────────────────────────────────────────────────────
# § 4  TEMPORAL NEIGHBOR STORE  (identical to TGN version)
# ─────────────────────────────────────────────────────────────────────────────

class TemporalNeighborStore:
    def __init__(self, max_nbrs: int = N_NEIGHBORS):
        self.max_nbrs = max_nbrs
        self._nbrs: Dict[int, List[Tuple[int, float]]] = defaultdict(list)

    def add_edges(self, src: torch.Tensor, dst: torch.Tensor,
                  t: torch.Tensor) -> None:
        for s, d, ti in zip(src.tolist(), dst.tolist(), t.tolist()):
            self._nbrs[s].append((d, float(ti)))
            self._nbrs[d].append((s, float(ti)))

    def query(
        self, node_ids: torch.Tensor, t_now: torch.Tensor
    ) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
        out_ids, out_ts = [], []
        for i, nid in enumerate(node_ids.tolist()):
            cutoff = float(t_now[i].item())
            pairs  = [(n, ti) for n, ti in self._nbrs[nid] if ti < cutoff]
            pairs  = sorted(pairs, key=lambda p: p[1])[-self.max_nbrs:]
            if pairs:
                out_ids.append(torch.tensor([p[0] for p in pairs], dtype=torch.long))
                out_ts.append(torch.tensor([p[1] for p in pairs], dtype=torch.float))
            else:
                out_ids.append(torch.tensor([], dtype=torch.long))
                out_ts.append(torch.tensor([], dtype=torch.float))
        return out_ids, out_ts


# ─────────────────────────────────────────────────────────────────────────────
# § 5  METRICS & UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _best_threshold(probs: np.ndarray, labels: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(labels, probs)
    f1s = 2 * precision * recall / np.clip(precision + recall, 1e-8, None)
    return float(thresholds[int(np.argmax(f1s[:-1]))])


def _metrics(probs: np.ndarray, labels: np.ndarray,
             threshold: Optional[float] = None) -> dict:
    if len(probs) == 0:
        return {"auc": 0.0, "ap": 0.0, "f1": 0.0,
                "precision": 0.0, "recall": 0.0, "threshold": 0.5}
    t     = threshold if threshold is not None else 0.5
    preds = (probs >= t).astype(int)
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
# § 6  TRAINING LOOP
# ─────────────────────────────────────────────────────────────────────────────

def _run_split(
    model:        TGAT,
    x:            torch.Tensor,
    src:          torch.Tensor,
    dst:          torch.Tensor,
    t:            torch.Tensor,
    y:            torch.Tensor,
    impacts_mask: torch.Tensor,
    split_mask:   torch.Tensor,
    nbr_store:    TemporalNeighborStore,
    optimizer:    Optional[torch.optim.Optimizer],
    criterion:    nn.Module,
    is_train:     bool,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Process all edges in temporal order.
    Every edge updates the neighbor store.
    Only IMPACTS edges in split_mask produce predictions.
    """
    active      = split_mask & impacts_mask
    all_probs, all_labels = [], []
    E = src.size(0)

    for batch_start in range(0, E, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, E)
        b_src     = src[batch_start:batch_end]
        b_dst     = dst[batch_start:batch_end]
        b_t       = t[batch_start:batch_end]
        b_active  = active[batch_start:batch_end]
        b_y       = y[batch_start:batch_end]

        # Always feed edges to neighbor store (builds temporal context)
        nbr_store.add_edges(b_src, b_dst, b_t)

        if b_active.sum() == 0:
            continue

        pred_src = b_src[b_active]
        pred_dst = b_dst[b_active]
        pred_t   = b_t[b_active]
        pred_y   = b_y[b_active]

        if is_train:
            z_src  = model.embed_nodes(pred_src, pred_t, x, nbr_store)
            z_dst  = model.embed_nodes(pred_dst, pred_t, x, nbr_store)
            logits = model.predict(z_src, z_dst)
            loss   = criterion(logits, pred_y.float())
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
        else:
            with torch.no_grad():
                z_src  = model.embed_nodes(pred_src, pred_t, x, nbr_store)
                z_dst  = model.embed_nodes(pred_dst, pred_t, x, nbr_store)
                logits = model.predict(z_src, z_dst)

        probs = torch.sigmoid(logits.detach()).cpu().numpy()
        all_probs.append(probs)
        all_labels.append(pred_y.cpu().numpy())

    if not all_probs:
        return np.array([]), np.array([])
    return np.concatenate(all_probs), np.concatenate(all_labels)


def train(temporal: dict) -> dict:
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    x          = temporal["x"].to(DEVICE)
    src        = temporal["src"].to(DEVICE)
    dst        = temporal["dst"].to(DEVICE)
    t          = temporal["t"].to(DEVICE)
    y          = temporal["y"].to(DEVICE)
    impacts    = temporal["impacts_mask"].to(DEVICE)
    train_mask = temporal["train_mask"].to(DEVICE)
    val_mask   = temporal["val_mask"].to(DEVICE)
    test_mask  = temporal["test_mask"].to(DEVICE)
    num_nodes  = temporal["num_nodes"]

    model     = TGAT(node_feat_dim=x.size(1),
                     edge_feat_dim=temporal["edge_attr"].size(1)).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WD)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    tr_imp_y   = y[train_mask & impacts].cpu().numpy()
    n1, n0     = int((tr_imp_y == 1).sum()), int((tr_imp_y == 0).sum())
    pos_weight = torch.tensor(n0 / max(n1, 1), dtype=torch.float).to(DEVICE)
    criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    log.info("TGAT — hidden=%d  heads=%d  layers=%d  epochs=%d",
             HIDDEN_DIM, N_HEADS, N_LAYERS, EPOCHS)
    log.info("  pos_weight=%.4f  (n0=%d  n1=%d)", float(pos_weight), n0, n1)
    log.info("  NOTE: TGAT is stateless — embedding computed fresh per event")

    best_val_auc = 0.0
    patience_ctr = 0
    history: List[dict] = []
    t0 = time.time()

    for epoch in range(1, EPOCHS + 1):
        ep_t0 = time.time()

        # ── Train ─────────────────────────────────────────────────────────────
        model.train()
        nbr_train = TemporalNeighborStore()
        tr_probs, tr_labels = _run_split(
            model, x, src, dst, t, y, impacts,
            train_mask, nbr_train, optimizer, criterion, is_train=True,
        )

        # ── Val (continue from where train left off in time) ──────────────────
        model.eval()
        # Seed val store with all train edges for temporal context
        nbr_val = TemporalNeighborStore()
        nbr_val.add_edges(src[train_mask], dst[train_mask], t[train_mask])
        val_probs, val_labels = _run_split(
            model, x, src, dst, t, y, impacts,
            val_mask, nbr_val, None, criterion, is_train=False,
        )

        train_m = _metrics(tr_probs,  tr_labels)
        val_m   = _metrics(val_probs, val_labels)
        scheduler.step()

        row = {
            "epoch":     epoch,
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
            "Epoch %3d/%d | train_auc=%.4f | val_auc=%.4f  val_f1=%.4f"
            "  val_ap=%.4f  [%.1fs]",
            epoch, EPOCHS, row["train_auc"], row["val_auc"],
            row["val_f1"], row["val_ap"], row["epoch_s"],
        )

        if val_m["auc"] > best_val_auc + 1e-4:
            best_val_auc = val_m["auc"]
            torch.save(model.state_dict(), CKPT / "tgat_best.pt")
            patience_ctr = 0
        else:
            patience_ctr += 1
            if patience_ctr >= PATIENCE:
                log.info("Early stopping at epoch %d", epoch)
                break

    train_time = round(time.time() - t0, 2)

    # ── Test ──────────────────────────────────────────────────────────────────
    model.load_state_dict(torch.load(CKPT / "tgat_best.pt",
                                     map_location=DEVICE, weights_only=True))
    model.eval()
    nbr_test = TemporalNeighborStore()
    warmup = train_mask | val_mask
    nbr_test.add_edges(src[warmup], dst[warmup], t[warmup])
    test_probs, test_labels = _run_split(
        model, x, src, dst, t, y, impacts,
        test_mask, nbr_test, None, criterion, is_train=False,
    )

    opt_thresh = _best_threshold(val_probs, val_labels) if len(val_probs) > 0 else 0.5
    test_m     = _metrics(test_probs, test_labels, threshold=opt_thresh)

    log.info("=" * 55)
    log.info("TGAT FINAL TEST RESULTS  (threshold=%.3f)", opt_thresh)
    log.info("  AUC-ROC   : %.4f", test_m["auc"])
    log.info("  Avg Prec  : %.4f", test_m["ap"])
    log.info("  F1        : %.4f", test_m["f1"])
    log.info("  Precision : %.4f", test_m["precision"])
    log.info("  Recall    : %.4f", test_m["recall"])
    log.info("  Train time: %.1f s", train_time)
    log.info("=" * 55)

    output = {
        "model":        "TGAT",
        "config":       {"hidden": HIDDEN_DIM, "heads": N_HEADS,
                         "layers": N_LAYERS, "lr": LR,
                         "epochs_run": len(history)},
        "test":         test_m,
        "best_val_auc": round(best_val_auc, 4),
        "train_time_s": train_time,
        "history":      history,
    }
    (RESULT / "tgat_metrics.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8")
    log.info("Results saved → results/tgat_metrics.json")
    log.info("Checkpoint  → checkpoints/tgat_best.pt")
    return output


# ─────────────────────────────────────────────────────────────────────────────
# § 7  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _, temporal = load_dataset()
    train(temporal)
