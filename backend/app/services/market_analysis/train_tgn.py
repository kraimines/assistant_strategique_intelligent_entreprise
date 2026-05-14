"""
train_tgn.py
============
Full Temporal Graph Network (TGN) for causal link prediction
on Talan's market knowledge graph.

Architecture (Option A — full paper implementation):
  1. Time2Vec encoder          : scalar t → 32-d sinusoidal time embedding
  2. GRU Memory module         : per-node state s_i ∈ R^64, updated each batch
  3. MLP Message function      : f(s_src, s_dst, Δt_enc, edge_feat) → msg ∈ R^64
  4. Temporal Attention Embedding (TGAT-style):
       Q = memory[v] + time_enc(0)
       K = memory[nbrs] + time_enc(t − t_nbr)
       V = x[nbrs] + memory[nbrs]
       → multi-head attention → embed ∈ R^128
  5. Link prediction MLP       : concat(emb_src, emb_dst) → sigmoid

Task  : binary link prediction on IMPACTS edges (causal_label 0 / 1)
Loss  : weighted BCE (handles 71 / 29 class imbalance)
Split : train < 2023  |  val = 2023  |  test ≥ 2024

Outputs:
  checkpoints/tgn_best.pt     best model weights (highest val AUC)
  results/tgn_metrics.json    per-epoch log + final test metrics

Run:
    cd backend/app/services/market_analysis
    python train_tgn.py
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
log = logging.getLogger("train_tgn")

HERE   = Path(__file__).parent.resolve()
CKPT   = HERE / "checkpoints"; CKPT.mkdir(exist_ok=True)
RESULT = HERE / "results";     RESULT.mkdir(exist_ok=True)

# ── Device ────────────────────────────────────────────────────────────────────
if not torch.cuda.is_available():
    log.warning("CUDA NOT FOUND! Training on CPU will be extremely slow.")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
log.info("Using device: %s", DEVICE)
if DEVICE.type == "cuda":
    log.info("  GPU: %s", torch.cuda.get_device_name(0))
    # Enable cuDNN benchmark for faster training on fixed-size inputs
    torch.backends.cudnn.benchmark = True

# ── Hyper-parameters ──────────────────────────────────────────────────────────
TIME_DIM    = 32      # Time2Vec output dimension
MEMORY_DIM  = 64      # per-node GRU hidden state
MSG_DIM     = 64      # message MLP output
EMBED_DIM   = 128     # final node embedding dimension
ATTN_HEADS  = 4       # temporal attention heads
N_NEIGHBORS = 20      # max temporal neighbors used in attention
BATCH_SIZE  = 500     # edges per temporal mini-batch
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
    Time2Vec: φ(t) = [t, sin(w_1·t + b_1), …, sin(w_d·t + b_d)]
    Output dimension = dim + 1
    """
    def __init__(self, dim: int):
        super().__init__()
        self.w = nn.Parameter(torch.randn(dim) * 0.1)
        self.b = nn.Parameter(torch.zeros(dim))

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        t = t.unsqueeze(-1)                          # [N, 1]
        periodic = torch.sin(t * self.w + self.b)    # [N, dim]
        return torch.cat([t, periodic], dim=-1)       # [N, dim+1]

    @property
    def out_dim(self) -> int:
        return self.w.shape[0] + 1


# ─────────────────────────────────────────────────────────────────────────────
# § 2  MESSAGE MODULE  (MLP)
# ─────────────────────────────────────────────────────────────────────────────

class MessageModule(nn.Module):
    """
    Computes a message for each directed edge:
      msg = MLP( cat(s_src, s_dst, time_enc(Δt), edge_feat) )
    """
    def __init__(self, memory_dim: int, time_enc_dim: int,
                 edge_feat_dim: int, out_dim: int):
        super().__init__()
        in_dim = 2 * memory_dim + time_enc_dim + edge_feat_dim
        self.mlp = nn.Sequential(
            nn.Linear(in_dim, out_dim * 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(out_dim * 2, out_dim),
        )

    def forward(self, s_src: torch.Tensor, s_dst: torch.Tensor,
                dt_enc: torch.Tensor, edge_feat: torch.Tensor) -> torch.Tensor:
        return self.mlp(torch.cat([s_src, s_dst, dt_enc, edge_feat], dim=-1))


# ─────────────────────────────────────────────────────────────────────────────
# § 3  MEMORY MODULE  (GRU)
# ─────────────────────────────────────────────────────────────────────────────

class MemoryModule(nn.Module):
    """
    Per-node GRU memory.
    state[i] ∈ R^memory_dim, updated when node i appears in a batch.
    """
    def __init__(self, num_nodes: int, memory_dim: int, msg_dim: int):
        super().__init__()
        self.num_nodes  = num_nodes
        self.memory_dim = memory_dim
        self.gru        = nn.GRUCell(msg_dim, memory_dim)
        self.register_buffer("memory", torch.zeros(num_nodes, memory_dim))
        self.register_buffer("last_t",  torch.zeros(num_nodes))

    def reset(self) -> None:
        self.memory.zero_()
        self.last_t.zero_()

    def detach(self) -> None:
        self.memory = self.memory.detach()

    def get(self, node_ids: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.memory[node_ids], self.last_t[node_ids]

    def update(self, node_ids: torch.Tensor, messages: torch.Tensor,
               timestamps: torch.Tensor) -> None:
        """
        Mean-aggregate messages for nodes that appear multiple times,
        then update GRU state.
        """
        unique_ids, inv = torch.unique(node_ids, return_inverse=True)
        # Allocate on the same device as the memory buffer
        dev = self.memory.device
        agg_msgs = torch.zeros(unique_ids.size(0), messages.size(-1), device=dev)
        agg_msgs.scatter_add_(0, inv.unsqueeze(1).expand_as(messages), messages)
        counts   = torch.bincount(inv, minlength=unique_ids.size(0)).float().unsqueeze(1)
        agg_msgs = agg_msgs / counts.clamp(min=1)

        old_mem = self.memory[unique_ids]
        new_mem = self.gru(agg_msgs, old_mem)
        self.memory[unique_ids] = new_mem

        # Update last_t: max timestamp seen for each unique node
        agg_t = torch.zeros(unique_ids.size(0), device=dev)
        agg_t.scatter_reduce_(0, inv, timestamps, reduce="amax", include_self=True)
        self.last_t[unique_ids] = agg_t


# ─────────────────────────────────────────────────────────────────────────────
# § 4  TEMPORAL ATTENTION EMBEDDING  (TGAT-style)
# ─────────────────────────────────────────────────────────────────────────────

class TemporalAttentionEmbedding(nn.Module):
    """
    Embeds a node at time t using multi-head attention over its
    temporal neighborhood:

      Q  = Linear(memory[v]  ⊕ time_enc(0))
      K  = Linear(memory[nbr] ⊕ time_enc(t − t_nbr))
      V  = Linear(x[nbr]     ⊕ memory[nbr])
      h  = MHA(Q, K, V)  →  Linear  → embed ∈ R^out_dim
    """
    def __init__(self, memory_dim: int, node_feat_dim: int,
                 time_enc_dim: int, out_dim: int, n_heads: int = 4):
        super().__init__()
        self.out_dim  = out_dim
        self.n_heads  = n_heads
        # Head dim must divide evenly
        assert out_dim % n_heads == 0

        q_in = memory_dim + time_enc_dim
        k_in = memory_dim + time_enc_dim
        v_in = node_feat_dim + memory_dim

        self.q_proj = nn.Linear(q_in, out_dim)
        self.k_proj = nn.Linear(k_in, out_dim)
        self.v_proj = nn.Linear(v_in, out_dim)
        self.attn   = nn.MultiheadAttention(out_dim, n_heads, batch_first=True,
                                             dropout=0.1)
        self.out    = nn.Sequential(nn.Linear(out_dim, out_dim), nn.ReLU())
        # Fallback when no neighbors: project memory directly
        self.fallback = nn.Linear(memory_dim, out_dim)

    def forward(
        self,
        node_ids:    torch.Tensor,     # [B] node indices to embed
        t_query:     torch.Tensor,     # [B] query timestamps (normalised)
        memory:      torch.Tensor,     # [N, memory_dim]
        x:           torch.Tensor,     # [N, node_feat_dim]
        time_enc:    nn.Module,
        nbr_ids:     List[torch.Tensor],  # per-node: [K_i] neighbor ids
        nbr_ts:      List[torch.Tensor],  # per-node: [K_i] neighbor timestamps
    ) -> torch.Tensor:

        B   = node_ids.size(0)
        dev = memory.device
        embeds = []

        # Compute time_enc(0) on the correct device
        t0_enc = time_enc(torch.zeros(1, device=dev))   # [1, time_enc_dim]

        for i in range(B):
            vid   = node_ids[i].item()
            t_now = t_query[i]
            m_v   = memory[vid]                   # [memory_dim]

            nbrs  = nbr_ids[i].to(dev)
            if nbrs.numel() == 0:
                # No neighbors → fallback to memory projection
                embeds.append(self.fallback(m_v))
                continue

            nts   = nbr_ts[i].to(dev)             # [K]
            m_nbr = memory[nbrs]                   # [K, memory_dim]
            x_nbr = x[nbrs]                        # [K, feat_dim]

            dt        = (t_now - nts).clamp(min=0)  # [K]
            t_enc_nbr = time_enc(dt)                  # [K, time_enc_dim]
            t_enc_v   = t0_enc.expand(1, -1)          # [1, time_enc_dim]

            # Query: [1, out_dim]
            q = self.q_proj(torch.cat([m_v.unsqueeze(0), t_enc_v], dim=-1))
            # Keys:  [K, out_dim]
            k = self.k_proj(torch.cat([m_nbr, t_enc_nbr], dim=-1))
            # Values:[K, out_dim]
            v = self.v_proj(torch.cat([x_nbr, m_nbr], dim=-1))

            # Attention: q [1,1,D] × K [1,K,D] → [1,1,D]
            h, _ = self.attn(
                q.unsqueeze(0), k.unsqueeze(0), v.unsqueeze(0)
            )
            embeds.append(self.out(h.squeeze(0).squeeze(0)))

        return torch.stack(embeds, dim=0)   # [B, out_dim]


# ─────────────────────────────────────────────────────────────────────────────
# § 5  LINK PREDICTOR
# ─────────────────────────────────────────────────────────────────────────────

class LinkPredictor(nn.Module):
    def __init__(self, embed_dim: int):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(2 * embed_dim, embed_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(embed_dim, 1),
        )

    def forward(self, z_src: torch.Tensor, z_dst: torch.Tensor) -> torch.Tensor:
        return self.mlp(torch.cat([z_src, z_dst], dim=-1)).squeeze(-1)


# ─────────────────────────────────────────────────────────────────────────────
# § 6  FULL TGN MODEL
# ─────────────────────────────────────────────────────────────────────────────

class TGN(nn.Module):
    def __init__(self, num_nodes: int, node_feat_dim: int,
                 edge_feat_dim: int = 2):
        super().__init__()
        self.time_enc   = TimeEncoder(TIME_DIM)
        t_dim           = self.time_enc.out_dim      # TIME_DIM + 1

        self.memory     = MemoryModule(num_nodes, MEMORY_DIM, MSG_DIM)
        self.msg_fn     = MessageModule(MEMORY_DIM, t_dim, edge_feat_dim, MSG_DIM)
        self.embed      = TemporalAttentionEmbedding(
            MEMORY_DIM, node_feat_dim, t_dim, EMBED_DIM, ATTN_HEADS,
        )
        self.predictor  = LinkPredictor(EMBED_DIM)

        # Initial node feature projection (optional warmup of memory)
        self.feat_proj  = nn.Linear(node_feat_dim, MEMORY_DIM)

    def warmup_memory(self, x: torch.Tensor) -> None:
        """Initialise memory states from static node features."""
        with torch.no_grad():
            self.memory.memory.copy_(self.feat_proj(x))

    def process_batch(
        self,
        src:       torch.Tensor,    # [B]
        dst:       torch.Tensor,    # [B]
        t:         torch.Tensor,    # [B] normalised timestamps
        edge_feat: torch.Tensor,    # [B, edge_feat_dim]
    ) -> None:
        """
        Update memory for all nodes in this batch.
        Called on EVERY edge (not just IMPACTS) to keep memory current.
        """
        s_src, t_src = self.memory.get(src)
        s_dst, t_dst = self.memory.get(dst)
        dt_src_enc   = self.time_enc((t - t_src).clamp(min=0))
        dt_dst_enc   = self.time_enc((t - t_dst).clamp(min=0))

        msg_src = self.msg_fn(s_src, s_dst, dt_src_enc, edge_feat)
        msg_dst = self.msg_fn(s_dst, s_src, dt_dst_enc, edge_feat)

        # Update both source and destination memories
        self.memory.update(torch.cat([src, dst]),
                           torch.cat([msg_src, msg_dst]),
                           torch.cat([t, t]))

    def embed_nodes(
        self,
        node_ids:  torch.Tensor,
        t_query:   torch.Tensor,
        x:         torch.Tensor,
        nbr_ids:   List[torch.Tensor],
        nbr_ts:    List[torch.Tensor],
    ) -> torch.Tensor:
        return self.embed(
            node_ids, t_query, self.memory.memory, x,
            self.time_enc, nbr_ids, nbr_ts,
        )

    def predict(self, z_src: torch.Tensor, z_dst: torch.Tensor) -> torch.Tensor:
        return self.predictor(z_src, z_dst)


# ─────────────────────────────────────────────────────────────────────────────
# § 7  TEMPORAL NEIGHBOR STORE
# ─────────────────────────────────────────────────────────────────────────────

class TemporalNeighborStore:
    """
    Maintains, per node, the last N_NEIGHBORS interactions sorted by time.
    Used by the TGAT embedding module at query time.
    Note: stores CPU tensors internally; moved to device on demand in § 4.
    """
    def __init__(self, num_nodes: int, max_nbrs: int = N_NEIGHBORS):
        self.max_nbrs  = max_nbrs
        self._nbrs: Dict[int, List[Tuple[int, float]]] = defaultdict(list)

    def add_edges(self, src: torch.Tensor, dst: torch.Tensor,
                  t: torch.Tensor) -> None:
        # Always work from CPU-side values for the Python dict
        src_cpu = src.cpu(); dst_cpu = dst.cpu(); t_cpu = t.cpu()
        for s, d, ti in zip(src_cpu.tolist(), dst_cpu.tolist(), t_cpu.tolist()):
            self._nbrs[s].append((d, ti))
            self._nbrs[d].append((s, ti))

    def query(self, node_ids: torch.Tensor, t_now: torch.Tensor,
              before_t: Optional[torch.Tensor] = None
    ) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
        """
        For each node in node_ids, return its temporal neighbors
        strictly before the corresponding query time.
        Returns CPU tensors; TemporalAttentionEmbedding moves them to device.
        """
        nbr_ids_list, nbr_ts_list = [], []
        node_ids_cpu = node_ids.cpu()
        t_now_cpu    = t_now.cpu()
        before_t_cpu = before_t.cpu() if before_t is not None else None

        # Pre-convert _nbrs entries to dict for faster access if not already
        # In a real TGN optimization, we'd use a C++ / Numba accelerated store.
        for i, nid in enumerate(node_ids_cpu.tolist()):
            cutoff = (before_t_cpu[i].item() if before_t_cpu is not None
                      else t_now_cpu[i].item())
            
            # Optimization: slice or filter neighbors
            # The list is already sorted by time because of how we add them
            node_nbrs = self._nbrs[nid]
            
            # Simple linear filter (Bottleneck in Python)
            pairs = [p for p in node_nbrs if p[1] < cutoff]
            
            # Keep only the N_NEIGHBORS most recent
            pairs = pairs[-self.max_nbrs:]
            
            if pairs:
                ids = torch.tensor([p[0] for p in pairs], dtype=torch.long)
                ts  = torch.tensor([p[1] for p in pairs], dtype=torch.float)
            else:
                ids = torch.tensor([], dtype=torch.long)
                ts  = torch.tensor([], dtype=torch.float)
            nbr_ids_list.append(ids)
            nbr_ts_list.append(ts)
        return nbr_ids_list, nbr_ts_list


# ─────────────────────────────────────────────────────────────────────────────
# § 8  METRICS & UTILITIES
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


def _class_weight(labels: np.ndarray) -> torch.Tensor:
    n1 = int((labels == 1).sum()); n0 = int((labels == 0).sum())
    total = n1 + n0 or 1
    return torch.tensor(n0 / max(n1, 1), dtype=torch.float)


# ─────────────────────────────────────────────────────────────────────────────
# § 9  TRAINING LOOP
# ─────────────────────────────────────────────────────────────────────────────

def _run_epoch(
    model:       TGN,
    x:           torch.Tensor,
    src:         torch.Tensor,
    dst:         torch.Tensor,
    t:           torch.Tensor,
    edge_attr:   torch.Tensor,
    y:           torch.Tensor,
    impacts_mask: torch.Tensor,
    split_mask:  torch.Tensor,
    nbr_store:   TemporalNeighborStore,
    optimizer:   Optional[torch.optim.Optimizer],
    criterion:   nn.Module,
    is_train:    bool,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    One pass through edges in temporal order.
    - All edges update memory (process_batch).
    - Only IMPACTS edges in split_mask contribute to predictions.
    Returns (probs, labels) for IMPACTS edges in the split.
    """
    all_probs, all_labels = [], []
    # Combine masks: must be in this split AND be an IMPACTS edge
    active = split_mask & impacts_mask
    E = src.size(0)

    for batch_start in range(0, E, BATCH_SIZE):
        batch_end  = min(batch_start + BATCH_SIZE, E)
        b_src      = src[batch_start:batch_end]
        b_dst      = dst[batch_start:batch_end]
        b_t        = t[batch_start:batch_end]
        b_attr     = edge_attr[batch_start:batch_end]
        b_active   = active[batch_start:batch_end]

        if is_train:
            # Memory update with grad
            model.process_batch(b_src, b_dst, b_t, b_attr)
        else:
            with torch.no_grad():
                model.process_batch(b_src, b_dst, b_t, b_attr)

        # Add this batch to neighbor store (only for future lookups)
        nbr_store.add_edges(b_src, b_dst, b_t)

        if b_active.sum() == 0:
            continue

        pred_src = b_src[b_active]
        pred_dst = b_dst[b_active]
        pred_t   = b_t[b_active]
        pred_y   = y[batch_start:batch_end][b_active]

        # Query neighbor store for current IMPACTS nodes
        nbr_ids_src, nbr_ts_src = nbr_store.query(pred_src, pred_t)
        nbr_ids_dst, nbr_ts_dst = nbr_store.query(pred_dst, pred_t)

        if is_train:
            z_src = model.embed_nodes(pred_src, pred_t, x, nbr_ids_src, nbr_ts_src)
            z_dst = model.embed_nodes(pred_dst, pred_t, x, nbr_ids_dst, nbr_ts_dst)
            logits = model.predict(z_src, z_dst)
            loss   = criterion(logits, pred_y.float())
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            model.memory.detach()
        else:
            with torch.no_grad():
                z_src  = model.embed_nodes(pred_src, pred_t, x, nbr_ids_src, nbr_ts_src)
                z_dst  = model.embed_nodes(pred_dst, pred_t, x, nbr_ids_dst, nbr_ts_dst)
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

    # ── Move all tensors to device ────────────────────────────────────────────
    x          = temporal["x"].to(DEVICE)
    src        = temporal["src"].to(DEVICE)
    dst        = temporal["dst"].to(DEVICE)
    t          = temporal["t"].to(DEVICE)
    edge_attr  = temporal["edge_attr"].to(DEVICE)
    y          = temporal["y"].to(DEVICE)
    impacts    = temporal["impacts_mask"].to(DEVICE)
    train_mask = temporal["train_mask"].to(DEVICE)
    val_mask   = temporal["val_mask"].to(DEVICE)
    test_mask  = temporal["test_mask"].to(DEVICE)
    num_nodes  = temporal["num_nodes"]

    model     = TGN(num_nodes, node_feat_dim=x.size(1),
                    edge_feat_dim=edge_attr.size(1)).to(DEVICE)
    model.warmup_memory(x)

    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WD)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    # Class weight from train IMPACTS labels (computed on CPU for numpy compat)
    tr_imp_y  = y[train_mask & impacts].cpu().numpy()
    pos_weight = _class_weight(tr_imp_y).to(DEVICE)
    criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    log.info("TGN (Full) — memory=%d  embed=%d  heads=%d  epochs=%d",
             MEMORY_DIM, EMBED_DIM, ATTN_HEADS, EPOCHS)
    log.info("  pos_weight=%.4f  train_impacts=%d", float(pos_weight),
             int((train_mask & impacts).sum()))

    best_val_auc = 0.0
    patience_ctr = 0
    history:     List[dict] = []
    t0 = time.time()

    for epoch in range(1, EPOCHS + 1):
        ep_t0 = time.time()

        # ── Train pass ────────────────────────────────────────────────────────
        model.train()
        model.memory.reset()
        nbr_train = TemporalNeighborStore(num_nodes)
        tr_probs, tr_labels = _run_epoch(
            model, x, src, dst, t, edge_attr, y, impacts,
            train_mask, nbr_train, optimizer, criterion, is_train=True,
        )

        # ── Val pass (resume from train memory state) ─────────────────────────
        model.eval()
        nbr_val = TemporalNeighborStore(num_nodes)
        # Feed all train edges to val store to build context
        nbr_val.add_edges(src[train_mask], dst[train_mask], t[train_mask])
        val_probs, val_labels = _run_epoch(
            model, x, src, dst, t, edge_attr, y, impacts,
            val_mask, nbr_val, None, criterion, is_train=False,
        )

        train_m = _metrics(tr_probs, tr_labels)
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
            torch.save(model.state_dict(), CKPT / "tgn_best.pt")
            patience_ctr = 0
        else:
            patience_ctr += 1
            if patience_ctr >= PATIENCE:
                log.info("Early stopping at epoch %d", epoch)
                break

    train_time = round(time.time() - t0, 2)

    # ── Test ──────────────────────────────────────────────────────────────────
    model.load_state_dict(torch.load(CKPT / "tgn_best.pt",
                                     map_location=DEVICE, weights_only=True))
    model.eval()
    model.memory.reset()
    # Warm up memory on train + val edges before testing
    with torch.no_grad():
        warmup_mask = train_mask | val_mask
        model.process_batch(
            src[warmup_mask], dst[warmup_mask],
            t[warmup_mask], edge_attr[warmup_mask],
        )
    nbr_test = TemporalNeighborStore(num_nodes)
    nbr_test.add_edges(src[warmup_mask], dst[warmup_mask], t[warmup_mask])
    test_probs, test_labels = _run_epoch(
        model, x, src, dst, t, edge_attr, y, impacts,
        test_mask, nbr_test, None, criterion, is_train=False,
    )

    # Calibrate threshold on val
    val_probs_np  = val_probs
    opt_thresh    = _best_threshold(val_probs_np, val_labels) if len(val_probs_np) > 0 else 0.5
    test_m        = _metrics(test_probs, test_labels, threshold=opt_thresh)

    log.info("=" * 55)
    log.info("TGN FINAL TEST RESULTS  (threshold=%.3f)", opt_thresh)
    log.info("  AUC-ROC   : %.4f", test_m["auc"])
    log.info("  Avg Prec  : %.4f", test_m["ap"])
    log.info("  F1        : %.4f", test_m["f1"])
    log.info("  Precision : %.4f", test_m["precision"])
    log.info("  Recall    : %.4f", test_m["recall"])
    log.info("  Train time: %.1f s", train_time)
    log.info("=" * 55)

    output = {
        "model":        "TGN",
        "config":       {"memory_dim": MEMORY_DIM, "embed_dim": EMBED_DIM,
                         "attn_heads": ATTN_HEADS, "lr": LR,
                         "epochs_run": len(history)},
        "test":         test_m,
        "best_val_auc": round(best_val_auc, 4),
        "train_time_s": train_time,
        "history":      history,
    }
    (RESULT / "tgn_metrics.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8")
    log.info("Results saved → results/tgn_metrics.json")
    log.info("Checkpoint  → checkpoints/tgn_best.pt")
    return output


# ─────────────────────────────────────────────────────────────────────────────
# § 10  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _, temporal = load_dataset()
    train(temporal)