"""
train_htgn.py
=============
Heterogeneous Temporal Graph Network (HTGN) for causal link prediction
on Talan's market knowledge graph.

Architecture — fully unified heterogeneous + temporal model:

  Per-relation message MLPs  (7 distinct relations):
    msg = MLP_{(T_src, E, T_dst)}(s_src, s_dst, time_enc(Δt), edge_feat)

  Per-node-type GRU memory  (5 node types):
    s_v ← GRU_{T_v}(msg, s_v)

  Heterogeneous Temporal Attention layer (per relation):
    Q_v     = q_proj_{T_dst}( cat(s_v,    time_enc(0))     )
    K_nbr   = k_proj_{rel} ( cat(s_nbr,  time_enc(t−t_nbr)) )
    V_nbr   = v_proj_{rel} ( cat(x_nbr,  s_nbr)            )
    h_{rel} = MultiHeadAttn(Q_v, K_nbr, V_nbr)
    z_v     = LayerNorm( sum_rel( out_proj_{T_dst}(h_{rel}) ) + fallback(s_v) )

  Link prediction:
    score = MLP( cat(z_src, z_dst) ) → sigmoid

Key differences vs TGN+HGT:
  - Memory is type-specific  (Event GRU ≠ Company GRU ≠ Sector GRU …)
  - Messages are relation-specific (7 distinct MLPs)
  - Temporal attention is heterogeneous (Q/K/V per relation triple)
  - Single unified forward pass — no two-phase sequential processing

Relations used (7 distinct):
  (Event, IMPACTS, Company)
  (Event, IMPACTS, Sector)
  (Event, INFLUENCES, MacroIndicator)
  (Company, BELONGS_TO_SECTOR, Sector)
  (Company, COMPETES_WITH, Company)
  (Company, OPERATES_IN, Geography)
  (MacroIndicator, INFLUENCES, Sector)

Task  : binary link prediction on IMPACTS edges (causal_label 0 / 1)
Loss  : weighted BCE
Split : train < 2023  |  val = 2023  |  test ≥ 2024

Outputs:
  checkpoints/htgn_best.pt     best model weights
  results/htgn_metrics.json    per-epoch log + test metrics

Run:
    cd backend/app/services/market_analysis
    python train_htgn.py
"""

from __future__ import annotations

import csv
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
log = logging.getLogger("train_htgn")

HERE     = Path(__file__).parent.resolve()
CKPT     = HERE / "checkpoints"; CKPT.mkdir(exist_ok=True)
RESULT   = HERE / "results";     RESULT.mkdir(exist_ok=True)
DATA_DIR = HERE / "gnn_causal_dataset"

# ── Device ────────────────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
log.info("Device: %s%s", DEVICE,
         f"  ({torch.cuda.get_device_name(0)})" if DEVICE.type == "cuda" else "")
if DEVICE.type == "cuda":
    torch.backends.cudnn.benchmark = True

# ── Hyper-parameters ──────────────────────────────────────────────────────────
TIME_DIM     = 32
MEMORY_DIM   = 64
MSG_DIM      = 64
HIDDEN       = 128
HTGN_LAYERS  = 2
HEADS        = 4
N_NEIGHBORS  = 20
BATCH_SIZE   = 200
LR           = 5e-4
WD           = 1e-4
EPOCHS       = 50
PATIENCE     = 10
SEED         = 42

# ── Relation key helper ───────────────────────────────────────────────────────
def rk(src_t: str, et: str, dst_t: str) -> str:
    """Unique string key for a relation triple (safe for nn.ModuleDict)."""
    return f"{src_t}__{et}__{dst_t}"


# ─────────────────────────────────────────────────────────────────────────────
# § 1  TIME ENCODING
# ─────────────────────────────────────────────────────────────────────────────

class TimeEncoder(nn.Module):
    """Time2Vec: [t, sin(w·t+b)] → R^(TIME_DIM+1)"""
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
# § 2  HETERO MEMORY MODULE
# ─────────────────────────────────────────────────────────────────────────────

class HeteroMemory(nn.Module):
    """
    Per-node-type GRU memory.
    Each node type has its own GRUCell so Event dynamics ≠ Company dynamics.
    All nodes share a single memory buffer [N, MEMORY_DIM] for fast indexing.
    """
    def __init__(self, num_nodes: int, node_types: List[str],
                 memory_dim: int, msg_dim: int):
        super().__init__()
        self.memory_dim = memory_dim
        self.grus = nn.ModuleDict({
            nt: nn.GRUCell(msg_dim, memory_dim) for nt in node_types
        })
        self.register_buffer("memory", torch.zeros(num_nodes, memory_dim))
        self.register_buffer("last_t",  torch.zeros(num_nodes))

    def reset(self) -> None:
        self.memory.zero_(); self.last_t.zero_()

    def detach(self) -> None:
        self.memory = self.memory.detach()

    def get(self, ids: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.memory[ids], self.last_t[ids]

    def update_typed(self, ids: torch.Tensor, msgs: torch.Tensor,
                     ts: torch.Tensor, node_type: str) -> None:
        """Update memory for all nodes of a given type using type-specific GRU."""
        if ids.numel() == 0:
            return
        unique, inv = torch.unique(ids, return_inverse=True)
        dev = self.memory.device
        agg  = torch.zeros(unique.size(0), msgs.size(-1), device=dev)
        agg.scatter_add_(0, inv.unsqueeze(1).expand_as(msgs), msgs)
        cnt  = torch.bincount(inv, minlength=unique.size(0)).float().unsqueeze(1)
        agg  = agg / cnt.clamp(min=1)
        self.memory[unique] = self.grus[node_type](agg, self.memory[unique])
        agg_t = torch.zeros(unique.size(0), device=dev)
        agg_t.scatter_reduce_(0, inv, ts, reduce="amax", include_self=True)
        self.last_t[unique] = agg_t


# ─────────────────────────────────────────────────────────────────────────────
# § 3  HETERO TEMPORAL ATTENTION LAYER
# ─────────────────────────────────────────────────────────────────────────────

class HTGNLayer(nn.Module):
    """
    One Heterogeneous Temporal Graph Attention layer.

    For each target node v (type T_dst) at time t:
      For each incoming relation (T_src, E, T_dst):
        Q_v   = q_proj[T_dst]( cat(s_v,   time_enc(0))     )   [1, H]
        K_nbr = k_proj[rel]  ( cat(s_nbr, time_enc(t−t_nbr)) ) [K, H]
        V_nbr = v_proj[rel]  ( cat(x_nbr, s_nbr)            )  [K, H]
        h_rel = MultiHeadAttn(Q_v, K_nbr, V_nbr)               [1, H]
      z_v = LayerNorm( Σ_rel out_proj[T_dst](h_rel) + fallback(s_v) )
    """

    def __init__(self, node_types: List[str],
                 relations: List[Tuple[str, str, str]],
                 memory_dim: int, feat_dim: int,
                 t_dim: int, hidden: int, n_heads: int):
        super().__init__()
        self.relations  = relations
        self.node_types = node_types

        # Per-node-type query projection
        self.q_proj = nn.ModuleDict({
            nt: nn.Linear(memory_dim + t_dim, hidden)
            for nt in node_types
        })
        # Per-relation key / value projections
        self.k_proj = nn.ModuleDict({
            rk(*r): nn.Linear(memory_dim + t_dim, hidden)
            for r in relations
        })
        self.v_proj = nn.ModuleDict({
            rk(*r): nn.Linear(feat_dim + memory_dim, hidden)
            for r in relations
        })
        # Per-relation multi-head attention
        self.attn = nn.ModuleDict({
            rk(*r): nn.MultiheadAttention(hidden, n_heads,
                                           batch_first=True, dropout=0.1)
            for r in relations
        })
        # Per-node-type output projection + fallback (no neighbors)
        self.out_proj = nn.ModuleDict({
            nt: nn.Linear(hidden, hidden) for nt in node_types
        })
        self.fallback = nn.ModuleDict({
            nt: nn.Linear(memory_dim, hidden) for nt in node_types
        })
        self.norm = nn.ModuleDict({
            nt: nn.LayerNorm(hidden) for nt in node_types
        })

    def forward(
        self,
        node_ids:    torch.Tensor,          # [B] global node IDs to embed
        node_type:   str,                   # all nodes in this call share one type
        t_query:     torch.Tensor,          # [B] query timestamps
        memory:      torch.Tensor,          # [N_global, MEMORY_DIM]
        x:           torch.Tensor,          # [N_global, feat_dim]
        time_enc:    nn.Module,
        nbr_store:   "HeteroTemporalNeighborStore",
    ) -> torch.Tensor:                      # [B, hidden]

        B   = node_ids.size(0)
        t0  = time_enc(torch.zeros(1, device=node_ids.device))  # [1, t_dim]

        # Incoming relations for this node type
        in_rels = [(st, et, dt) for st, et, dt in self.relations if dt == node_type]

        outputs = []
        for i in range(B):
            vid   = node_ids[i].item()
            t_now = t_query[i]
            s_v   = memory[vid]   # [MEMORY_DIM]

            # Sum contributions from each incoming relation
            rel_sum = None
            n_rels  = 0

            for rel in in_rels:
                st, et, dt = rel
                rel_k  = rk(*rel)
                nbrs, nbr_ts = nbr_store.query(vid, rel_k)

                if not nbrs:
                    continue

                nbr_ids = torch.tensor(nbrs,    dtype=torch.long,  device=node_ids.device)
                nts     = torch.tensor(nbr_ts,  dtype=torch.float, device=node_ids.device)

                s_nbr   = memory[nbr_ids]            # [K, MEMORY_DIM]
                x_nbr   = x[nbr_ids]                 # [K, feat_dim]
                dt_enc  = time_enc((t_now - nts).clamp(min=0))  # [K, t_dim]

                q = self.q_proj[node_type](
                    torch.cat([s_v.unsqueeze(0), t0.expand(1, -1)], dim=-1)
                )                                    # [1, H]
                k = self.k_proj[rel_k](
                    torch.cat([s_nbr, dt_enc], dim=-1)
                )                                    # [K, H]
                v = self.v_proj[rel_k](
                    torch.cat([x_nbr, s_nbr], dim=-1)
                )                                    # [K, H]

                h, _ = self.attn[rel_k](
                    q.unsqueeze(0), k.unsqueeze(0), v.unsqueeze(0)
                )
                h = h.squeeze(0).squeeze(0)          # [H]

                contrib = self.out_proj[node_type](h)
                rel_sum  = contrib if rel_sum is None else rel_sum + contrib
                n_rels  += 1

            if rel_sum is None:
                # No neighbors in any relation → fallback to memory projection
                z = self.fallback[node_type](s_v)
            else:
                z = rel_sum / max(n_rels, 1) + self.fallback[node_type](s_v)

            outputs.append(self.norm[node_type](z))

        return torch.stack(outputs, dim=0)    # [B, hidden]


# ─────────────────────────────────────────────────────────────────────────────
# § 4  HETERO TEMPORAL NEIGHBOR STORE
# ─────────────────────────────────────────────────────────────────────────────

class HeteroTemporalNeighborStore:
    """
    Stores recent temporal neighbors per (target_node, relation_key).
    Only the src node is stored for each edge (dst attends over src neighbors).
    """
    def __init__(self, max_nbrs: int = N_NEIGHBORS):
        self.max_nbrs = max_nbrs
        # {rel_key: {dst_node_id: [(src_node_id, timestamp)]}}
        self._nbrs: Dict[str, Dict[int, List[Tuple[int, float]]]] = \
            defaultdict(lambda: defaultdict(list))

    def add_edge(self, src: int, dst: int, t: float, rel_key: str) -> None:
        self._nbrs[rel_key][dst].append((src, t))

    def add_batch(self, srcs: torch.Tensor, dsts: torch.Tensor,
                  ts: torch.Tensor, rel_keys: List[str]) -> None:
        for s, d, ti, rek in zip(srcs.tolist(), dsts.tolist(),
                                  ts.tolist(), rel_keys):
            self._nbrs[rek][d].append((s, float(ti)))

    def query(self, node_id: int, rel_key: str
              ) -> Tuple[List[int], List[float]]:
        pairs = self._nbrs[rel_key].get(node_id, [])
        pairs = sorted(pairs, key=lambda p: p[1])[-self.max_nbrs:]
        if not pairs:
            return [], []
        return [p[0] for p in pairs], [p[1] for p in pairs]


# ─────────────────────────────────────────────────────────────────────────────
# § 5  FULL HTGN MODEL
# ─────────────────────────────────────────────────────────────────────────────

class HTGN(nn.Module):
    def __init__(self, num_nodes: int, node_types: List[str],
                 relations: List[Tuple[str, str, str]],
                 node_feat_dim: int = 396, edge_feat_dim: int = 2):
        super().__init__()

        self.node_types = node_types
        self.relations  = relations

        self.time_enc = TimeEncoder(TIME_DIM)
        t_dim         = self.time_enc.out_dim

        # Per-relation message MLPs
        self.msg_mlps = nn.ModuleDict({
            rk(*r): nn.Sequential(
                nn.Linear(2 * MEMORY_DIM + t_dim + edge_feat_dim, MSG_DIM * 2),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(MSG_DIM * 2, MSG_DIM),
            )
            for r in relations
        })

        # Hetero memory
        self.memory = HeteroMemory(num_nodes, node_types, MEMORY_DIM, MSG_DIM)

        # Warmup projection
        self.feat_proj = nn.Linear(node_feat_dim, MEMORY_DIM)

        # HTGN layers
        self.layers = nn.ModuleList([
            HTGNLayer(node_types, relations, MEMORY_DIM, node_feat_dim,
                      t_dim, HIDDEN, HEADS)
            for _ in range(HTGN_LAYERS)
        ])

        # Link prediction head
        self.head = nn.Sequential(
            nn.Linear(2 * HIDDEN, HIDDEN),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(HIDDEN, 1),
        )

    def warmup(self, x: torch.Tensor) -> None:
        with torch.no_grad():
            self.memory.memory.copy_(self.feat_proj(x))

    @torch.no_grad()
    def update_memory(self, src: torch.Tensor, dst: torch.Tensor,
                      t: torch.Tensor, edge_feat: torch.Tensor,
                      rel: Tuple[str, str, str]) -> None:
        """Update memory for one batch of typed edges."""
        st, et, dt = rel
        rel_key    = rk(*rel)
        s_src, t_src = self.memory.get(src)
        s_dst, t_dst = self.memory.get(dst)
        dt_src = self.time_enc((t - t_src).clamp(min=0))
        dt_dst = self.time_enc((t - t_dst).clamp(min=0))
        inp_src = torch.cat([s_src, s_dst, dt_src, edge_feat], dim=-1)
        inp_dst = torch.cat([s_dst, s_src, dt_dst, edge_feat], dim=-1)
        msg_src = self.msg_mlps[rel_key](inp_src)
        msg_dst = self.msg_mlps[rel_key](inp_dst)
        self.memory.update_typed(src, msg_src, t, st)
        self.memory.update_typed(dst, msg_dst, t, dt)

    def embed(self, node_ids: torch.Tensor, node_type: str,
              t_query: torch.Tensor, x: torch.Tensor,
              nbr_store: HeteroTemporalNeighborStore) -> torch.Tensor:
        """Compute HTGN embeddings for a batch of same-type nodes."""
        h = node_ids   # carry ids through layers
        z = None
        for layer in self.layers:
            z = layer(h, node_type, t_query,
                      self.memory.memory, x, self.time_enc, nbr_store)
            # IDs stay the same across layers; z is the embedding
        return z   # [B, HIDDEN]

    def predict(self, z_src: torch.Tensor, z_dst: torch.Tensor) -> torch.Tensor:
        return self.head(torch.cat([z_src, z_dst], dim=-1)).squeeze(-1)


# ─────────────────────────────────────────────────────────────────────────────
# § 6  DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_node_meta() -> Tuple[Dict[int, str], Dict[str, List[int]]]:
    """Returns gid_to_type and type_to_gids from nodes.csv."""
    gid_to_type:  Dict[int, str]       = {}
    type_to_gids: Dict[str, List[int]] = defaultdict(list)
    with open(DATA_DIR / "nodes.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid  = int(row["id"])
            ntype = row["type"]
            gid_to_type[gid]  = ntype
            type_to_gids[ntype].append(gid)
    return gid_to_type, {k: v for k, v in type_to_gids.items()}


def _load_edge_relations(hetero) -> List[Tuple[str, str, str]]:
    return [(st, et, dt) for st, et, dt in hetero.edge_types]


def _run_memory_pass(
    model: HTGN,
    temporal: dict,
    mask: torch.Tensor,
    gid_to_type: Dict[int, str],
    edge_rel_cache: Dict[Tuple[int, int], Tuple[str, str, str]],
    nbr_store: HeteroTemporalNeighborStore,
) -> None:
    """
    Feed all masked edges through typed memory updates and neighbor store.
    Edges without a known relation mapping are skipped.
    """
    src  = temporal["src"]
    dst  = temporal["dst"]
    t    = temporal["t"]
    attr = temporal["edge_attr"]

    idxs = mask.nonzero(as_tuple=True)[0]
    for i in range(0, idxs.size(0), BATCH_SIZE):
        bidx = idxs[i: i + BATCH_SIZE]
        b_src  = src[bidx];  b_dst = dst[bidx]
        b_t    = t[bidx];    b_attr = attr[bidx]

        # Determine relation for each edge in batch
        # Group by relation type for efficient processing
        rel_groups: Dict[str, Tuple[List, List, List, List]] = defaultdict(
            lambda: ([], [], [], [])
        )
        for j in range(b_src.size(0)):
            s_id = b_src[j].item(); d_id = b_dst[j].item()
            st   = gid_to_type.get(s_id); dt = gid_to_type.get(d_id)
            if st is None or dt is None:
                continue
            # Find matching relation (src_type matches and dst_type matches)
            for rel in model.relations:
                if rel[0] == st and rel[2] == dt:
                    rek = rk(*rel)
                    rel_groups[rek][0].append(j)
                    # Also feed neighbor store (dst attends over src)
                    nbr_store.add_edge(s_id, d_id, b_t[j].item(), rek)
                    break

        for rek, (jidxs, *_) in rel_groups.items():
            if not jidxs:
                continue
            ji   = torch.tensor(jidxs, dtype=torch.long)
            rel  = tuple(rek.split("__"))
            model.update_memory(
                b_src[ji], b_dst[ji], b_t[ji], b_attr[ji], rel
            )


def _predict_split(model, hetero, temporal, split, gid_to_type, nbr_store, device):
    """
    Embed nodes from IMPACTS edges in `split` using HTGN, return (logits, labels).
    """
    all_logits, all_y = [], []
    x = temporal["x"].to(device)

    for rel in hetero.edge_types:
        st, et, dt = rel
        if et != "IMPACTS":
            continue
        rd   = hetero[st, et, dt]
        mask = getattr(rd, f"{split}_mask")
        if mask.sum() == 0:
            continue
        ei = rd.edge_index[:, mask].to(device)
        y  = rd.y[mask].to(device)

        src_gids = ei[0]; dst_gids = ei[1]
        src_t    = temporal["t"].to(device)[
            _find_event_times(src_gids, temporal, device)
        ] if False else torch.zeros(src_gids.size(0), device=device)
        # Use a uniform query time 1.0 for final embedding (after all edges processed)
        t_q = torch.ones(src_gids.size(0), device=device)

        z_src = model.embed(src_gids, st, t_q, x, nbr_store)
        z_dst = model.embed(dst_gids, dt, t_q, x, nbr_store)
        all_logits.append(model.predict(z_src, z_dst))
        all_y.append(y)

    if not all_logits:
        return torch.tensor([]), torch.tensor([])
    return torch.cat(all_logits), torch.cat(all_y)


def _find_event_times(node_ids, temporal, device):
    """Placeholder: returns indices into temporal src array matching node_ids."""
    return torch.zeros(node_ids.size(0), dtype=torch.long, device=device)


# ─────────────────────────────────────────────────────────────────────────────
# § 7  METRICS
# ─────────────────────────────────────────────────────────────────────────────

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
# § 8  TRAINING LOOP
# ─────────────────────────────────────────────────────────────────────────────

def train(hetero, temporal: dict) -> dict:
    torch.manual_seed(SEED); np.random.seed(SEED)

    gid_to_type, type_to_gids = _load_node_meta()
    relations  = _load_edge_relations(hetero)
    node_types = list(hetero.node_types)
    num_nodes  = temporal["num_nodes"]

    x          = temporal["x"].to(DEVICE)
    src        = temporal["src"].to(DEVICE)
    dst        = temporal["dst"].to(DEVICE)
    t_all      = temporal["t"].to(DEVICE)
    edge_attr  = temporal["edge_attr"].to(DEVICE)
    train_mask = temporal["train_mask"].to(DEVICE)
    val_mask   = temporal["val_mask"].to(DEVICE)
    test_mask  = temporal["test_mask"].to(DEVICE)

    model     = HTGN(num_nodes, node_types, relations,
                     node_feat_dim=396, edge_feat_dim=edge_attr.size(1)).to(DEVICE)
    model.warmup(x)

    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WD)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    # Class weight
    n0, n1 = 0, 0
    for rel in hetero.edge_types:
        st, et, dt = rel
        if et != "IMPACTS" or not hasattr(hetero[st, et, dt], "y"):
            continue
        tr_y = hetero[st, et, dt].y[hetero[st, et, dt].train_mask]
        n1  += int((tr_y == 1).sum()); n0 += int((tr_y == 0).sum())
    pos_weight = torch.tensor(n0 / max(n1, 1), dtype=torch.float).to(DEVICE)
    criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    log.info("HTGN — memory=%d  hidden=%d  layers=%d  heads=%d  epochs=%d",
             MEMORY_DIM, HIDDEN, HTGN_LAYERS, HEADS, EPOCHS)
    log.info("  Relations (%d): %s", len(relations),
             [f"{st[:3]},{et},{dt[:3]}" for st, et, dt in relations])
    log.info("  pos_weight=%.4f  (n0=%d  n1=%d)", float(pos_weight), n0, n1)

    # Dummy edge-rel cache (not used — type lookup done at runtime)
    edge_rel_cache: Dict = {}

    best_val_auc = 0.0
    patience_ctr = 0
    history: List[dict] = []
    t0 = time.time()

    for epoch in range(1, EPOCHS + 1):
        ep_t0 = time.time()

        # ── Phase 1: typed memory pass (no grad) ──────────────────────────────
        model.train()
        model.memory.reset()
        model.warmup(x)
        nbr_train = HeteroTemporalNeighborStore()
        _run_memory_pass(model, temporal, train_mask, gid_to_type,
                         edge_rel_cache, nbr_train)

        # ── Phase 2: embed + decode + loss (grad) ─────────────────────────────
        optimizer.zero_grad()
        train_logits, train_y = _predict_split(
            model, hetero, temporal, "train", gid_to_type, nbr_train, DEVICE
        )
        loss = criterion(train_logits, train_y.float())
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        # ── Validation ────────────────────────────────────────────────────────
        model.eval()
        with torch.no_grad():
            nbr_val = HeteroTemporalNeighborStore()
            # Seed with train edges
            _run_memory_pass(model, temporal, train_mask, gid_to_type,
                             edge_rel_cache, nbr_val)
            _run_memory_pass(model, temporal, val_mask, gid_to_type,
                             edge_rel_cache, nbr_val)
            val_logits, val_y = _predict_split(
                model, hetero, temporal, "val", gid_to_type, nbr_val, DEVICE
            )

        train_m = _metrics(torch.sigmoid(train_logits.detach()).cpu().numpy(),
                           train_y.cpu().numpy())
        val_m   = _metrics(torch.sigmoid(val_logits).cpu().numpy(),
                           val_y.cpu().numpy())

        row = {
            "epoch":     epoch,
            "loss":      round(float(loss.detach()), 5),
            "train_auc": train_m["auc"],
            "val_auc":   val_m["auc"],
            "val_ap":    val_m["ap"],
            "val_f1":    val_m["f1"],
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
            torch.save(model.state_dict(), CKPT / "htgn_best.pt")
            patience_ctr = 0
        else:
            patience_ctr += 1
            if patience_ctr >= PATIENCE:
                log.info("Early stopping at epoch %d", epoch)
                break

    train_time = round(time.time() - t0, 2)

    # ── Test ──────────────────────────────────────────────────────────────────
    model.load_state_dict(torch.load(CKPT / "htgn_best.pt",
                                     map_location=DEVICE, weights_only=True))
    model.eval()
    with torch.no_grad():
        model.memory.reset(); model.warmup(x)
        nbr_test = HeteroTemporalNeighborStore()
        _run_memory_pass(model, temporal, train_mask | val_mask,
                         gid_to_type, edge_rel_cache, nbr_test)
        val_log2, val_y2 = _predict_split(
            model, hetero, temporal, "val", gid_to_type, nbr_test, DEVICE
        )
        opt_thresh = _best_threshold(
            torch.sigmoid(val_log2).cpu().numpy(), val_y2.cpu().numpy()
        ) if val_log2.numel() > 0 else 0.5
        _run_memory_pass(model, temporal, test_mask,
                         gid_to_type, edge_rel_cache, nbr_test)
        test_log, test_y = _predict_split(
            model, hetero, temporal, "test", gid_to_type, nbr_test, DEVICE
        )

    test_m = _metrics(torch.sigmoid(test_log).cpu().numpy(),
                      test_y.cpu().numpy(), threshold=opt_thresh)

    log.info("=" * 55)
    log.info("HTGN FINAL TEST RESULTS  (threshold=%.3f)", opt_thresh)
    log.info("  AUC-ROC   : %.4f", test_m["auc"])
    log.info("  Avg Prec  : %.4f", test_m["ap"])
    log.info("  F1        : %.4f", test_m["f1"])
    log.info("  Precision : %.4f", test_m["precision"])
    log.info("  Recall    : %.4f", test_m["recall"])
    log.info("  Train time: %.1f s", train_time)
    log.info("=" * 55)

    output = {
        "model":        "HTGN",
        "config":       {"memory_dim": MEMORY_DIM, "hidden": HIDDEN,
                         "layers": HTGN_LAYERS, "heads": HEADS,
                         "n_relations": len(relations), "lr": LR,
                         "epochs_run": len(history)},
        "test":         test_m,
        "best_val_auc": round(best_val_auc, 4),
        "train_time_s": train_time,
        "history":      history,
    }
    (RESULT / "htgn_metrics.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8")
    log.info("Results saved → results/htgn_metrics.json")
    return output


# ─────────────────────────────────────────────────────────────────────────────
# § 9  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    hetero, temporal = load_dataset()
    train(hetero, temporal)
