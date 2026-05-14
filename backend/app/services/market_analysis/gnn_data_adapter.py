"""
gnn_data_adapter.py
====================
Shared data-loading layer for all three GNN trainers (HGT, TGN, TGAT).

Loads the CSV / NPY files produced by generate_synthetic_dataset.py (or the
real pipeline) and returns two ready-to-use data structures:

  hetero_data   — torch_geometric.data.HeteroData
                  Used by HGT + temporal encoding.
                  Node features split by type; edge_index per relation;
                  causal labels + train/val/test masks on IMPACTS edges.

  temporal_data — plain dict with sorted temporal edge stream
                  Used by TGN and TGAT.
                  Keys: src, dst, t, edge_attr, y,
                        train_mask, val_mask, test_mask,
                        x (global feature matrix), class_weight

Split strategy (time-based, no data leakage):
  train : events with timestamp < 2023-01-01   (2021 + 2022)
  val   : events with timestamp in 2023
  test  : events with timestamp >= 2024-01-01

Usage:
    from gnn_data_adapter import load_dataset
    hetero, temporal = load_dataset()
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch_geometric.data import HeteroData

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE      = Path(__file__).parent.resolve()
DATA_DIR  = HERE / "gnn_causal_dataset"

# ── Schema (must match the generator) ────────────────────────────────────────
NODE_TYPES = [
    "Company", "BusinessUnit", "Sector", "Geography",
    "Client", "Project", "Competitor", "Regulation",
    "MacroIndicator", "Event",
]
EDGE_TYPES = [
    "AFFECTS", "BELONGS_TO_SECTOR", "COMPETES_WITH",
    "DELIVERED_FOR", "IMPACTS", "INFLUENCES",
    "OPERATES_IN", "SERVES", "SUPPLY_CHAIN_LINK",
]

# Time split boundaries (ISO strings, compared against edge timestamps)
_TRAIN_END = "2023-01-01"
_VAL_END   = "2024-01-01"

START_DATE = datetime(2021, 1, 1, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# § 1  RAW LOADERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_nodes(data_dir: Path):
    """Returns (global_ids, types, names) as parallel lists."""
    ids, types, names = [], [], []
    with open(data_dir / "nodes.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ids.append(int(row["id"]))
            types.append(row["type"])
            names.append(row["name"])
    return ids, types, names


def _load_edges_with_labels(data_dir: Path):
    """
    Merges edges.csv + edge_labels.csv into one list of dicts with keys:
      src, dst, etype, weight, timestamp, source_system, causal_label
    Only rows where causal_label is 0 or 1 (labelled edges).
    """
    # Build label lookup from edge_labels.csv
    label_map: Dict[Tuple[int, int, str], int] = {}
    lpath = data_dir / "edge_labels.csv"
    if lpath.exists():
        with open(lpath, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lbl = int(row.get("causal_label", -1))
                k   = (int(row["source"]), int(row["target"]), row["type"])
                label_map[k] = lbl

    edges = []
    with open(data_dir / "edges.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s, t, etype = int(row["source"]), int(row["target"]), row["type"]
            lbl = label_map.get((s, t, etype), -1)
            edges.append({
                "src":           s,
                "dst":           t,
                "etype":         etype,
                "weight":        float(row["weight"]),
                "timestamp":     row["timestamp"],
                "source_system": row["source_system"],
                "causal_label":  lbl,
            })
    return edges


# ─────────────────────────────────────────────────────────────────────────────
# § 2  HeteroData BUILDER  (for HGT)
# ─────────────────────────────────────────────────────────────────────────────

def _build_hetero(
    global_ids: List[int],
    node_types: List[str],
    features:   np.ndarray,
    edges:      List[dict],
) -> HeteroData:
    """
    Builds a PyG HeteroData object.

    Node feature matrices are split per node type.
    Edge indices are split per (src_type, edge_type, dst_type) relation.
    IMPACTS edges carry causal_label as .y and train/val/test masks.
    """
    # ── global_id → (node_type, local_idx) ───────────────────────────────────
    gid_to_type  = {gid: t for gid, t in zip(global_ids, node_types)}
    type_to_lids: Dict[str, List[int]] = {t: [] for t in NODE_TYPES}
    gid_to_local: Dict[int, int] = {}

    for gid, ntype in zip(global_ids, node_types):
        local = len(type_to_lids[ntype])
        type_to_lids[ntype].append(gid)
        gid_to_local[gid] = local

    data = HeteroData()

    # ── node features per type ────────────────────────────────────────────────
    for ntype, gids in type_to_lids.items():
        if not gids:
            continue
        feat = features[np.array(gids, dtype=np.int64)]
        data[ntype].x    = torch.from_numpy(feat)
        data[ntype].name = ntype
        # Attach temporal encoding for Event nodes (sinusoidal day-of-year)
        if ntype == "Event":
            data[ntype].x = _add_temporal_encoding(data[ntype].x, gids, edges)

    # ── edge indices per relation ─────────────────────────────────────────────
    # Collect per relation: {(src_type, etype, dst_type): ([src_local], [dst_local], [w], [lbl], [ts])}
    rel_srcs:  Dict[tuple, List[int]]   = {}
    rel_dsts:  Dict[tuple, List[int]]   = {}
    rel_wts:   Dict[tuple, List[float]] = {}
    rel_lbls:  Dict[tuple, List[int]]   = {}
    rel_ts:    Dict[tuple, List[str]]   = {}

    for e in edges:
        s, t, et = e["src"], e["dst"], e["etype"]
        st = gid_to_type.get(s)
        dt = gid_to_type.get(t)
        if st is None or dt is None:
            continue
        if s not in gid_to_local or t not in gid_to_local:
            continue
        rel = (st, et, dt)
        rel_srcs.setdefault(rel, []).append(gid_to_local[s])
        rel_dsts.setdefault(rel, []).append(gid_to_local[t])
        rel_wts.setdefault(rel, []).append(e["weight"])
        rel_lbls.setdefault(rel, []).append(e["causal_label"])
        rel_ts.setdefault(rel, []).append(e["timestamp"])

    for rel, srcs in rel_srcs.items():
        st, et, dt = rel
        dsts = rel_dsts[rel]
        idx  = torch.tensor([srcs, dsts], dtype=torch.long)
        data[st, et, dt].edge_index = idx
        data[st, et, dt].edge_attr  = torch.tensor(rel_wts[rel], dtype=torch.float).unsqueeze(1)

        # Supervision labels + masks for IMPACTS edges
        if et == "IMPACTS":
            lbls = np.array(rel_lbls[rel], dtype=np.int64)
            tss  = rel_ts[rel]
            train_m, val_m, test_m = _time_masks(tss)
            data[st, et, dt].y          = torch.from_numpy(lbls)
            data[st, et, dt].train_mask = torch.from_numpy(train_m)
            data[st, et, dt].val_mask   = torch.from_numpy(val_m)
            data[st, et, dt].test_mask  = torch.from_numpy(test_m)

    return data


def _add_temporal_encoding(x: torch.Tensor, gids: List[int], edges: List[dict]) -> torch.Tensor:
    """
    Prepend a 2-d sinusoidal time encoding to each Event node's feature vector.
    Encoding: [sin(2π·day/365), cos(2π·day/365)] where day = days since 2021-01-01.

    The extra 2 dims overwrite features [0:2] which are the one-hot type bits for
    node-type index 0 ("Company") — safe to overwrite for Event nodes.
    Actually we ADD them to the existing features so no dimension changes.
    The feature vector stays at 396-d; we use a weighted sum trick:
      x_new[i, 0] += sin_enc,  x_new[i, 1] += cos_enc
    This injects temporal signal without changing tensor shape.
    """
    # Build gid → event_date lookup from edges
    gid_date: Dict[int, str] = {}
    for e in edges:
        if e["etype"] == "IMPACTS" and e["timestamp"]:
            gid_date.setdefault(e["src"], e["timestamp"])

    x = x.clone()
    for local_idx, gid in enumerate(gids):
        ts = gid_date.get(gid, "")
        if not ts:
            continue
        try:
            dt  = datetime.fromisoformat(ts)
            day = (dt.replace(tzinfo=timezone.utc) - START_DATE).days
            x[local_idx, 0] = x[local_idx, 0] + float(np.sin(2 * np.pi * day / 365))
            x[local_idx, 1] = x[local_idx, 1] + float(np.cos(2 * np.pi * day / 365))
        except Exception:
            pass
    return x


# ─────────────────────────────────────────────────────────────────────────────
# § 3  TEMPORAL DATA BUILDER  (for TGN + TGAT)
# ─────────────────────────────────────────────────────────────────────────────

def _build_temporal(
    global_ids: List[int],
    features:   np.ndarray,
    edges:      List[dict],
) -> dict:
    """
    Builds a sorted temporal edge stream dict for TGN / TGAT.

    All edges (not just IMPACTS) are included in the stream so the temporal
    models see the full graph dynamics. Supervision signal is IMPACTS edges
    with causal_label ∈ {0, 1}.

    Keys:
      x          : float32 tensor [N, 396]   global node features
      src        : int64 tensor  [E]          source global IDs
      dst        : int64 tensor  [E]          target global IDs
      t          : float32 tensor [E]         days since 2021-01-01 (normalised 0-1)
      edge_attr  : float32 tensor [E, 2]      (weight, causal_label or -1)
      y          : int64 tensor  [E]          causal_label (-1 = unlabelled)
      impacts_mask: bool tensor  [E]          True for IMPACTS edges
      train_mask : bool tensor  [E]           train split on IMPACTS edges
      val_mask   : bool tensor  [E]           val split
      test_mask  : bool tensor  [E]           test split
      class_weight: float32 tensor [2]        [w_neg, w_pos] for weighted BCE
      num_nodes  : int
    """
    # Sort all edges by timestamp
    labelled = [e for e in edges if e["timestamp"]]
    labelled.sort(key=lambda e: e["timestamp"])

    srcs  = np.array([e["src"]         for e in labelled], dtype=np.int64)
    dsts  = np.array([e["dst"]         for e in labelled], dtype=np.int64)
    wts   = np.array([e["weight"]      for e in labelled], dtype=np.float32)
    lbls  = np.array([e["causal_label"] for e in labelled], dtype=np.int64)
    etypes = np.array([e["etype"]      for e in labelled])
    tss   = [e["timestamp"]            for e in labelled]

    # Normalised timestamp: days / TOTAL_DAYS → [0, 1]
    total_days = (datetime(2025, 1, 1) - datetime(2021, 1, 1)).days
    t_float = np.array([_ts_to_days(ts) / total_days for ts in tss], dtype=np.float32)

    impacts_mask = (etypes == "IMPACTS")
    train_m, val_m, test_m = _time_masks(tss)

    # Class weights for weighted BCE (on positive IMPACTS edges)
    imp_lbls = lbls[impacts_mask & (train_m)]
    n_pos = int((imp_lbls == 1).sum())
    n_neg = int((imp_lbls == 0).sum())
    total = n_pos + n_neg or 1
    w_pos = total / (2 * n_pos) if n_pos > 0 else 1.0
    w_neg = total / (2 * n_neg) if n_neg > 0 else 1.0

    return {
        "x":            torch.from_numpy(features),
        "src":          torch.from_numpy(srcs),
        "dst":          torch.from_numpy(dsts),
        "t":            torch.from_numpy(t_float),
        "edge_attr":    torch.stack([
                            torch.from_numpy(wts),
                            torch.from_numpy(lbls.astype(np.float32)),
                        ], dim=1),
        "y":            torch.from_numpy(lbls),
        "impacts_mask": torch.from_numpy(impacts_mask),
        "train_mask":   torch.from_numpy(train_m),
        "val_mask":     torch.from_numpy(val_m),
        "test_mask":    torch.from_numpy(test_m),
        "class_weight": torch.tensor([w_neg, w_pos], dtype=torch.float),
        "num_nodes":    int(features.shape[0]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# § 4  UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _time_masks(timestamps: List[str]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return boolean train/val/test masks based on timestamp strings."""
    n      = len(timestamps)
    train  = np.zeros(n, dtype=bool)
    val    = np.zeros(n, dtype=bool)
    test   = np.zeros(n, dtype=bool)
    for i, ts in enumerate(timestamps):
        if not ts:
            train[i] = True     # no timestamp → assign to train
            continue
        if ts < _TRAIN_END:
            train[i] = True
        elif ts < _VAL_END:
            val[i]   = True
        else:
            test[i]  = True
    return train, val, test


def _ts_to_days(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        dt  = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        return float((dt - START_DATE).days)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# § 5  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(
    data_dir: Optional[Path] = None,
) -> Tuple[HeteroData, dict]:
    """
    Load the GNN dataset and return (hetero_data, temporal_data).

    hetero_data   → use with HGT trainer
    temporal_data → use with TGN / TGAT trainers

    Args:
        data_dir: path to gnn_causal_dataset/. Defaults to
                  <this_file>/../gnn_causal_dataset/

    Returns:
        (HeteroData, dict)
    """
    ddir = Path(data_dir) if data_dir else DATA_DIR
    log.info("Loading dataset from %s", ddir)

    # Raw data
    global_ids, node_types, names = _load_nodes(ddir)
    features = np.load(str(ddir / "node_features.npy"))
    edges    = _load_edges_with_labels(ddir)

    log.info("  nodes: %d, edges: %d, feature_dim: %d",
             len(global_ids), len(edges), features.shape[1])

    # Split summary
    impacts = [e for e in edges if e["etype"] == "IMPACTS"]
    tss     = [e["timestamp"] for e in impacts]
    trm, vm, tem = _time_masks(tss)
    log.info("  IMPACTS edges — train: %d  val: %d  test: %d",
             int(trm.sum()), int(vm.sum()), int(tem.sum()))

    # Class balance on training IMPACTS
    train_lbls = np.array([e["causal_label"] for e in impacts])[trm]
    n1, n0 = int((train_lbls == 1).sum()), int((train_lbls == 0).sum())
    log.info("  Train label balance — pos: %d (%.1f%%)  neg: %d (%.1f%%)",
             n1, 100 * n1 / max(n1 + n0, 1), n0, 100 * n0 / max(n1 + n0, 1))

    # Build structures
    hetero   = _build_hetero(global_ids, node_types, features, edges)
    temporal = _build_temporal(global_ids, features, edges)

    log.info("HeteroData node types: %s", list(hetero.node_types))
    log.info("HeteroData edge types: %s", [str(r) for r in hetero.edge_types])
    log.info("Temporal stream: %d edges, class_weight=%s",
             temporal["src"].shape[0], temporal["class_weight"].tolist())

    return hetero, temporal


# ─────────────────────────────────────────────────────────────────────────────
# § 6  QUICK VALIDATION  (run directly to sanity-check the data)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s")

    hetero, temporal = load_dataset()

    print("\n── HeteroData ──────────────────────────────────────")
    for ntype in hetero.node_types:
        print(f"  {ntype:20s}  x={tuple(hetero[ntype].x.shape)}")
    for rel in hetero.edge_types:
        st, et, dt = rel
        ei = hetero[st, et, dt].edge_index
        has_y = hasattr(hetero[st, et, dt], "y")
        print(f"  ({st}, {et}, {dt})  edges={ei.shape[1]}"
              + ("  [labelled]" if has_y else ""))

    print("\n── Temporal stream ─────────────────────────────────")
    print(f"  total edges  : {temporal['src'].shape[0]:,}")
    print(f"  num_nodes    : {temporal['num_nodes']:,}")
    print(f"  train edges  : {temporal['train_mask'].sum().item():,}")
    print(f"  val   edges  : {temporal['val_mask'].sum().item():,}")
    print(f"  test  edges  : {temporal['test_mask'].sum().item():,}")
    print(f"  class_weight : {temporal['class_weight'].tolist()}")
    print(f"  x shape      : {tuple(temporal['x'].shape)}")
    print(f"  t range      : [{temporal['t'].min():.3f}, {temporal['t'].max():.3f}]")
    print("\nAdapter OK — ready for model training.")
