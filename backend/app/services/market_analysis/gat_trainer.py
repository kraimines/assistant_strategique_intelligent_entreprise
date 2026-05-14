"""
GAT Impact Propagation Trainer

Learns how impact propagates through the Talan Knowledge Graph using
Graph Attention Networks.  Each attention coefficient α_ij answers:
"in this context, how much should node i listen to neighbour j?"

Architecture (3-layer GAT → regression head):
  GATConv(396 → 128, heads=8, concat)  →  1024-d
  GATConv(1024 → 64, heads=4, concat)  →  256-d
  GATConv(256  → 32, heads=1)          →  32-d
  Linear(32 → 1) + Sigmoid             →  impact ∈ [0, 1]

Two execution modes
  - PyG present  : uses torch_geometric.nn.GATConv  (fast, sparse)
  - PyG absent   : uses ManualGATConv (pure torch, dense attention matrix)

Dataset: backend/gnn_dataset/  (nodes.csv, edges.csv, node_features.npy)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── PyG / torch availability ──────────────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _TORCH = True
except ImportError:
    _TORCH = False

try:
    from torch_geometric.data import Data as PyGData
    from torch_geometric.nn import GATConv
    _PYG = True
except ImportError:
    _PYG = False

# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

NODE_TYPES = [
    "Company", "BusinessUnit", "Sector", "Geography",
    "Client", "Project", "Competitor", "Regulation",
    "MacroIndicator", "Event",
]
TYPE_TO_IDX = {t: i for i, t in enumerate(NODE_TYPES)}


def load_pyg_data(dataset_dir: str | Path) -> "PyGData | dict":
    """
    Load nodes.csv + edges.csv + node_features.npy into a PyG Data object.

    If torch_geometric is absent returns a plain dict with numpy arrays
    so the rest of the code can still run in degraded mode.

    Returns
    -------
    PyGData  (or dict with keys x, edge_index, edge_attr, y, node_names, node_types)
    """
    dataset_dir = Path(dataset_dir)
    nodes_df = pd.read_csv(dataset_dir / "nodes.csv")
    edges_df = pd.read_csv(dataset_dir / "edges.csv")
    features: np.ndarray = np.load(dataset_dir / "node_features.npy").astype(np.float32)

    # Build a contiguous id→row mapping (ids in CSV may not be 0-N)
    id_to_row = {int(row["id"]): i for i, (_, row) in enumerate(nodes_df.iterrows())}

    # Edge indices in row space
    src_rows, dst_rows, weights = [], [], []
    for _, e in edges_df.iterrows():
        s, d = id_to_row.get(int(e["source"])), id_to_row.get(int(e["target"]))
        if s is not None and d is not None:
            src_rows.append(s)
            dst_rows.append(d)
            weights.append(float(e.get("weight", 1.0)))

    node_names = list(nodes_df["name"])
    node_types = list(nodes_df["type"])

    if not _TORCH:
        return {
            "x": features,
            "edge_index": np.array([src_rows, dst_rows], dtype=np.int64),
            "edge_attr": np.array(weights, dtype=np.float32).reshape(-1, 1),
            "y": features[:, 11],
            "node_names": node_names,
            "node_types": node_types,
        }

    import torch  # noqa: F811

    x = torch.tensor(features, dtype=torch.float32)
    edge_index = torch.tensor([src_rows, dst_rows], dtype=torch.long)
    edge_attr = torch.tensor(weights, dtype=torch.float32).unsqueeze(1)
    y = x[:, 11].clone()

    if _PYG:
        data = PyGData(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)
        data.node_names = node_names
        data.node_types = node_types
        return data

    # Fallback: return plain dict of tensors (used by ManualGATConv path)
    return {
        "x": x,
        "edge_index": edge_index,
        "edge_attr": edge_attr,
        "y": y,
        "node_names": node_names,
        "node_types": node_types,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Manual GATConv (pure torch, no PyG)
# ─────────────────────────────────────────────────────────────────────────────

class _ManualGATConv(nn.Module):
    """
    Single GAT layer — pure PyTorch, no torch_geometric dependency.

    e_ij  = LeakyReLU(a^T [W·h_i || W·h_j])
    α_ij  = softmax_{j ∈ N(i)}(e_ij)
    h'_i  = ELU( Σ_j α_ij · W·h_j )          (single head)

    Multi-head: H independent projections, results concatenated (or averaged).
    """

    def __init__(self, in_dim: int, out_dim: int, heads: int = 1, concat: bool = True):
        super().__init__()
        self.heads = heads
        self.out_dim = out_dim
        self.concat = concat

        self.W = nn.ModuleList([nn.Linear(in_dim, out_dim, bias=False) for _ in range(heads)])
        self.a = nn.ParameterList([
            nn.Parameter(torch.empty(2 * out_dim)) for _ in range(heads)
        ])
        for i in range(heads):
            nn.init.xavier_uniform_(self.W[i].weight)
            nn.init.xavier_uniform_(self.a[i].unsqueeze(0))

        self.leaky = nn.LeakyReLU(0.2)

    def forward(
        self, x: torch.Tensor, edge_index: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        N = x.shape[0]
        src, dst = edge_index[0], edge_index[1]
        head_outs = []
        all_attn = []

        for h in range(self.heads):
            Wh = self.W[h](x)                          # [N, out_dim]
            e = self.leaky(
                torch.cat([Wh[src], Wh[dst]], dim=1) @ self.a[h]  # [E]
            )
            # Softmax per destination node
            alpha = torch.zeros(N, N, device=x.device)
            alpha[dst, src] = e  # note: scatter would be more mem-efficient
            # Mask to keep only edges, then softmax row-wise
            mask = torch.full((N, N), float("-inf"), device=x.device)
            mask[dst, src] = e
            alpha_soft = torch.softmax(mask, dim=1)            # [N, N]
            alpha_soft = torch.nan_to_num(alpha_soft, nan=0.0)
            agg = alpha_soft @ Wh                              # [N, out_dim]
            head_outs.append(F.elu(agg))
            all_attn.append(alpha_soft.detach())

        if self.concat:
            return torch.cat(head_outs, dim=1), torch.stack(all_attn)
        else:
            return torch.stack(head_outs).mean(dim=0), torch.stack(all_attn)


# ─────────────────────────────────────────────────────────────────────────────
# GATImpactModel
# ─────────────────────────────────────────────────────────────────────────────

class GATImpactModel(nn.Module):
    """
    3-layer GAT with regression head for node-level impact prediction.

    In-features : 396  (one-hot type + centrality + impact + SBERT)
    Out-features: 1    (predicted impact score, sigmoid → [0,1])
    """

    def __init__(
        self,
        in_dim: int = 396,
        heads: tuple[int, int, int] = (8, 4, 1),
        dropout: float = 0.3,
    ):
        super().__init__()
        if not _TORCH:
            raise RuntimeError("torch is required for GATImpactModel")

        h1, h2, h3 = heads
        self.dropout_p = dropout
        self._attention_cache: list[torch.Tensor] = []

        if _PYG:
            self.conv1 = GATConv(in_dim,   128, heads=h1, concat=True,  dropout=dropout)
            self.conv2 = GATConv(128 * h1,  64, heads=h2, concat=True,  dropout=dropout)
            self.conv3 = GATConv(64  * h2,  32, heads=h3, concat=False, dropout=dropout)
        else:
            self.conv1 = _ManualGATConv(in_dim,   128, heads=h1, concat=True)
            self.conv2 = _ManualGATConv(128 * h1,  64, heads=h2, concat=True)
            self.conv3 = _ManualGATConv(64  * h2,  32, heads=h3, concat=False)

        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(32, 1)

    def forward(self, data: "PyGData | dict") -> tuple[torch.Tensor, list]:
        if isinstance(data, dict):
            x, edge_index = data["x"], data["edge_index"]
        else:
            x, edge_index = data.x, data.edge_index

        attn_weights: list[torch.Tensor] = []

        if _PYG:
            h1, (ei1, a1) = self.conv1(x, edge_index, return_attention_weights=True)
            h1 = F.elu(h1)
            h2, (ei2, a2) = self.conv2(h1, edge_index, return_attention_weights=True)
            h2 = F.elu(h2)
            h3, (ei3, a3) = self.conv3(h2, edge_index, return_attention_weights=True)
            h3 = F.elu(h3)
            attn_weights = [a1.detach(), a2.detach(), a3.detach()]
        else:
            h1, a1 = self.conv1.forward(x, edge_index)
            h2, a2 = self.conv2.forward(h1, edge_index)
            h3, a3 = self.conv3.forward(h2, edge_index)
            attn_weights = [a1, a2, a3]

        self._attention_cache = attn_weights
        out = torch.sigmoid(self.head(self.dropout(h3)))   # [N, 1]
        return out, attn_weights

    def get_attention_weights(self) -> list[torch.Tensor]:
        """Return cached attention weights from the last forward pass."""
        return self._attention_cache


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def train_gat(
    data: "PyGData | dict",
    model: GATImpactModel,
    epochs: int = 100,
    lr: float = 1e-3,
) -> tuple[GATImpactModel, list[float]]:
    """
    Unsupervised-style training: MSE on nodes with known impact (y > 0).

    Returns (trained_model, loss_history).
    """
    import torch
    import torch.optim as optim

    torch.manual_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    if isinstance(data, dict):
        data_dev = {k: (v.to(device) if isinstance(v, torch.Tensor) else v)
                    for k, v in data.items()}
        y = data_dev["y"]
    else:
        data_dev = data.to(device)
        y = data_dev.y

    # Only train on nodes with a known impact score
    mask = (y > 0).to(device)
    if mask.sum() == 0:
        logger.warning("No nodes with impact score > 0 — training on all nodes")
        mask = torch.ones(len(y), dtype=torch.bool, device=device)

    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", patience=10, factor=0.5
    )
    criterion = nn.MSELoss()

    loss_history: list[float] = []
    t0 = time.time()

    model.train()
    for epoch in range(1, epochs + 1):
        optimizer.zero_grad()
        preds, _ = model.forward(data_dev)           # [N, 1]
        loss = criterion(preds[mask].squeeze(), y[mask])
        loss.backward()
        optimizer.step()
        scheduler.step(loss)

        loss_val = float(loss.item())
        loss_history.append(loss_val)

        if epoch % 10 == 0 or epoch == 1:
            logger.info(
                "  epoch %d/%d  loss=%.4f  (%.1fs)",
                epoch, epochs, loss_val, time.time() - t0,
            )

    model.eval()
    logger.info("GAT training complete — final loss=%.4f", loss_history[-1])
    return model, loss_history


# ─────────────────────────────────────────────────────────────────────────────
# Impact simulation
# ─────────────────────────────────────────────────────────────────────────────

def simulate_impact_propagation(
    model: GATImpactModel,
    data: "PyGData | dict",
    shock_node_name: str,
    shock_value: float = 1.0,
    top_k: int = 20,
) -> list[dict]:
    """
    Inject a shock at shock_node_name, propagate through the GAT, return
    the top_k most impacted nodes sorted by predicted impact (descending).

    Returns
    -------
    list of dicts: name, type, predicted_impact, attention_weight
    """
    import torch

    if isinstance(data, dict):
        node_names: list[str] = data["node_names"]
        node_types: list[str] = data["node_types"]
        x_orig: torch.Tensor = data["x"]
    else:
        node_names = data.node_names
        node_types = data.node_types
        x_orig = data.x

    if shock_node_name not in node_names:
        # Fuzzy match (case-insensitive prefix)
        lower = shock_node_name.lower()
        candidates = [n for n in node_names if lower in n.lower()]
        if not candidates:
            raise ValueError(
                f"Node '{shock_node_name}' not found in graph. "
                f"Available: {node_names[:10]}…"
            )
        shock_node_name = candidates[0]
        logger.warning("Node fuzzy-matched to '%s'", shock_node_name)

    shock_idx = node_names.index(shock_node_name)
    device = next(model.parameters()).device

    # Clone + inject shock
    x_shock = x_orig.clone().to(device)
    x_shock[shock_idx, 11] = shock_value

    if isinstance(data, dict):
        data_shock = dict(data)
        data_shock["x"] = x_shock
    else:
        from torch_geometric.data import Data as PyGData  # noqa: F811
        data_shock = PyGData(
            x=x_shock,
            edge_index=data.edge_index,
            edge_attr=data.edge_attr,
            y=data.y,
        )
        data_shock.node_names = node_names
        data_shock.node_types = node_types

    model.eval()
    with torch.no_grad():
        preds, attn_list = model.forward(data_shock)   # [N, 1]

    scores = preds.squeeze().cpu().numpy()             # [N]

    # Per-node attention: mean of last layer's attention weights
    # attn_list[-1] shape depends on PyG vs manual
    if _PYG and attn_list:
        # PyG returns attention per edge [E, heads] → mean across heads
        last_attn = attn_list[-1].cpu().numpy().mean(axis=-1)  # [E]
        # Aggregate to destination nodes
        if isinstance(data, dict):
            edge_index_np = data["edge_index"].cpu().numpy()
        else:
            edge_index_np = data.edge_index.cpu().numpy()
        node_attn = np.zeros(len(node_names))
        np.add.at(node_attn, edge_index_np[1], last_attn)
        # Normalise
        mx = node_attn.max()
        if mx > 0:
            node_attn /= mx
    else:
        # Manual GATConv: attn is [heads, N, N] → take row mean for each node
        if attn_list:
            last_attn = attn_list[-1].cpu().numpy()    # [heads, N, N]
            node_attn = last_attn.mean(axis=0)[shock_idx]  # [N] — row of shock node
        else:
            node_attn = np.zeros(len(node_names))

    # Sort by predicted impact
    order = np.argsort(scores)[::-1][:top_k]
    results = []
    for idx in order:
        results.append(
            {
                "name": node_names[idx],
                "type": node_types[idx],
                "predicted_impact": round(float(scores[idx]), 4),
                "attention_weight": round(float(node_attn[idx]), 4),
            }
        )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Save / evaluate
# ─────────────────────────────────────────────────────────────────────────────

def save_gat_artefacts(
    output_dir: str | Path,
    model: GATImpactModel,
    loss_history: list[float],
    node_names: list[str],
) -> Path:
    """Save model, loss history and node index to output_dir/embeddings/."""
    import torch

    out = Path(output_dir) / "embeddings"
    out.mkdir(parents=True, exist_ok=True)

    torch.save(model.state_dict(), out / "gat_model.pt")
    (out / "gat_loss_history.json").write_text(
        json.dumps(loss_history, indent=2), encoding="utf-8"
    )
    index = {name: i for i, name in enumerate(node_names)}
    (out / "gat_node_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("GAT artefacts saved to %s", out)
    return out


def evaluate_gat(
    model: GATImpactModel,
    data: "PyGData | dict",
    node_names: list[str],
    node_types: list[str] | None = None,
) -> dict:
    """
    Compute MAE and R² on nodes with known impact (y > 0).
    Also returns top-10 predicted nodes for qualitative validation.
    """
    import torch

    if isinstance(data, dict):
        y_true = data["y"].cpu().numpy()
        node_types_list: list[str] = data.get("node_types", ["?"] * len(node_names))
    else:
        y_true = data.y.cpu().numpy()
        node_types_list = getattr(data, "node_types", ["?"] * len(node_names))

    model.eval()
    with torch.no_grad():
        preds, _ = model.forward(data)
    y_pred = preds.squeeze().cpu().numpy()

    mask = y_true > 0
    if mask.sum() == 0:
        mask = np.ones(len(y_true), dtype=bool)

    mae = float(np.abs(y_pred[mask] - y_true[mask]).mean())
    ss_res = float(((y_true[mask] - y_pred[mask]) ** 2).sum())
    ss_tot = float(((y_true[mask] - y_true[mask].mean()) ** 2).sum())
    r2 = 1.0 - ss_res / (ss_tot + 1e-8)

    # Top-10 by predicted impact
    top10_idx = np.argsort(y_pred)[::-1][:10]
    top_impacted = [
        {
            "name": node_names[i],
            "type": node_types_list[i],
            "predicted_impact": round(float(y_pred[i]), 4),
            "true_impact": round(float(y_true[i]), 4),
        }
        for i in top10_idx
    ]

    return {"mae": round(mae, 4), "r2": round(r2, 4), "top_impacted": top_impacted}
