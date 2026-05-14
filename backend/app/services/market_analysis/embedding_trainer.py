"""
GNN Embedding Trainer — Node2Vec + GraphSAGE

Dataset layout (gnn_dataset/):
  nodes.csv            id,type,name,slug,source
  edges.csv            source,target,type,weight,timestamp,source_system
  node_features.npy    float32 [N, 396]  (10 type-OH + 1 degree + 1 impact + 384 sbert)
  metadata.json        stats + feature_layout

Outputs (gnn_dataset/embeddings/):
  node2vec_embeddings.npy       [N, 128]
  graphsage_embeddings.npy      [N, 128]
  node2vec_model.pkl            gensim Word2Vec object
  graphsage_model.pt            torch state_dict
  embedding_index.json          name → row index map
  evaluation_report.json        cosine similarity checks
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Evaluation anchors ────────────────────────────────────────────────────────

EVAL_ANCHORS = [
    ("Talan", ["Capgemini", "Accenture", "Sopra Steria"]),
    ("Financial Services", ["Banking", "Insurance", "Asset Management"]),
    ("ECB Interest Rates", ["Federal Reserve Rate", "Inflation Rate", "GDP Growth"]),
    ("Capgemini", ["Atos", "IBM", "Infosys"]),
]

# ── Load graph ────────────────────────────────────────────────────────────────


def load_graph(dataset_dir: str | Path) -> tuple[nx.DiGraph, pd.DataFrame, np.ndarray]:
    """Return (G, nodes_df, features) from the GNN dataset directory."""
    dataset_dir = Path(dataset_dir)

    nodes_df = pd.read_csv(dataset_dir / "nodes.csv")
    edges_df = pd.read_csv(dataset_dir / "edges.csv")
    features: np.ndarray = np.load(dataset_dir / "node_features.npy").astype(np.float32)

    G = nx.DiGraph()
    for _, row in nodes_df.iterrows():
        G.add_node(
            int(row["id"]),
            name=row["name"],
            type=row["type"],
            slug=row.get("slug", ""),
        )
    for _, row in edges_df.iterrows():
        G.add_edge(
            int(row["source"]),
            int(row["target"]),
            rel_type=row["type"],
            weight=float(row.get("weight", 1.0)),
        )

    logger.info(
        "Graph loaded: %d nodes, %d edges, features %s",
        G.number_of_nodes(),
        G.number_of_edges(),
        features.shape,
    )
    return G, nodes_df, features


# ── Node2Vec ──────────────────────────────────────────────────────────────────


def run_node2vec(
    G: nx.DiGraph,
    dim: int = 128,
    walk_length: int = 20,
    num_walks: int = 10,
    p: float = 1.0,
    q: float = 0.5,
    workers: int = 4,
    seed: int = 42,
) -> tuple[np.ndarray, Any]:
    """
    Train Node2Vec embeddings.

    Returns (embeddings [N, dim], gensim Word2Vec model).
    Falls back to random embeddings if node2vec/gensim not installed.
    """
    num_nodes = G.number_of_nodes()
    node_ids = sorted(G.nodes())

    try:
        from node2vec import Node2Vec  # type: ignore

        logger.info("Running Node2Vec (dim=%d, walk=%d, walks=%d, p=%.1f, q=%.1f) …",
                    dim, walk_length, num_walks, p, q)
        n2v = Node2Vec(
            G,
            dimensions=dim,
            walk_length=walk_length,
            num_walks=num_walks,
            p=p,
            q=q,
            workers=workers,
            seed=seed,
            quiet=True,
        )
        model = n2v.fit(window=5, min_count=1, sg=1, epochs=5, seed=seed)

        embeddings = np.zeros((num_nodes, dim), dtype=np.float32)
        for i, nid in enumerate(node_ids):
            if str(nid) in model.wv:
                embeddings[i] = model.wv[str(nid)]
        logger.info("Node2Vec done — embeddings %s", embeddings.shape)
        return embeddings, model

    except ImportError:
        logger.warning("node2vec not installed — using random embeddings as fallback")
        rng = np.random.default_rng(seed)
        embeddings = rng.standard_normal((num_nodes, dim)).astype(np.float32)
        # Normalise rows
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
        embeddings /= norms
        return embeddings, None


# ── GraphSAGE ─────────────────────────────────────────────────────────────────


def _build_adj(G: nx.DiGraph, node_ids: list[int]) -> list[list[int]]:
    """Return adjacency list (index-based) for the ordered node_ids."""
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    adj: list[list[int]] = [[] for _ in node_ids]
    for src, dst in G.edges():
        if src in id_to_idx and dst in id_to_idx:
            adj[id_to_idx[src]].append(id_to_idx[dst])
            adj[id_to_idx[dst]].append(id_to_idx[src])  # treat as undirected for agg
    return adj


class _SAGEConv:
    """Minimal hand-rolled SAGEConv layer (no PyG dependency)."""

    def __init__(self, in_dim: int, out_dim: int):
        import torch
        import torch.nn as nn  # noqa: F401

        # Xavier init
        self.W_self = torch.nn.Linear(in_dim, out_dim, bias=False)
        self.W_neigh = torch.nn.Linear(in_dim, out_dim, bias=False)
        torch.nn.init.xavier_uniform_(self.W_self.weight)
        torch.nn.init.xavier_uniform_(self.W_neigh.weight)

    def forward(self, x, adj: list[list[int]]):
        import torch
        import torch.nn.functional as F

        N = x.shape[0]
        agg = torch.zeros(N, x.shape[1], dtype=x.dtype, device=x.device)
        for i, neighbors in enumerate(adj):
            if neighbors:
                agg[i] = x[neighbors].mean(dim=0)
            else:
                agg[i] = x[i]
        out = self.W_self(x) + self.W_neigh(agg)
        return F.relu(out)

    def parameters(self):
        return list(self.W_self.parameters()) + list(self.W_neigh.parameters())

    def state_dict(self):
        return {
            "W_self": self.W_self.state_dict(),
            "W_neigh": self.W_neigh.state_dict(),
        }

    def load_state_dict(self, d: dict):
        self.W_self.load_state_dict(d["W_self"])
        self.W_neigh.load_state_dict(d["W_neigh"])

    def to(self, device):
        self.W_self = self.W_self.to(device)
        self.W_neigh = self.W_neigh.to(device)
        return self


class GraphSAGEModel:
    """2-layer GraphSAGE: 396 → 256 → 128, unsupervised link-prediction loss."""

    def __init__(self, in_dim: int = 396, hidden: int = 256, out_dim: int = 128):
        self.conv1 = _SAGEConv(in_dim, hidden)
        self.conv2 = _SAGEConv(hidden, out_dim)

    def forward(self, x, adj: list[list[int]]):
        import torch.nn.functional as F

        h = self.conv1.forward(x, adj)
        h = self.conv2.forward(h, adj)
        # L2 normalise for cosine-style dot product
        norms = h.norm(dim=1, keepdim=True).clamp(min=1e-8)
        return h / norms

    def parameters(self):
        return self.conv1.parameters() + self.conv2.parameters()

    def state_dict(self):
        return {"conv1": self.conv1.state_dict(), "conv2": self.conv2.state_dict()}

    def load_state_dict(self, d: dict):
        self.conv1.load_state_dict(d["conv1"])
        self.conv2.load_state_dict(d["conv2"])

    def to(self, device):
        self.conv1.to(device)
        self.conv2.to(device)
        return self


def run_graphsage(
    G: nx.DiGraph,
    features: np.ndarray,
    in_dim: int = 396,
    hidden: int = 256,
    out_dim: int = 128,
    epochs: int = 50,
    lr: float = 1e-3,
    neg_samples: int = 5,
    batch_size: int = 256,
    seed: int = 42,
) -> tuple[np.ndarray, GraphSAGEModel | None]:
    """
    Train GraphSAGE with unsupervised link-prediction loss.

    Returns (embeddings [N, out_dim], model).
    Falls back to PCA-reduced features if torch not installed.
    """
    try:
        import torch
        import torch.optim as optim

    except ImportError:
        logger.warning("torch not installed — falling back to PCA feature reduction")
        from sklearn.decomposition import PCA  # type: ignore

        pca = PCA(n_components=out_dim, random_state=seed)
        emb = pca.fit_transform(features).astype(np.float32)
        norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8
        return emb / norms, None

    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("GraphSAGE training on %s (epochs=%d)", device, epochs)

    node_ids = sorted(G.nodes())
    N = len(node_ids)
    adj = _build_adj(G, node_ids)

    # Positive edges as index pairs
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    pos_pairs = [
        (id_to_idx[u], id_to_idx[v])
        for u, v in G.edges()
        if u in id_to_idx and v in id_to_idx
    ]
    pos_src = torch.tensor([p[0] for p in pos_pairs], dtype=torch.long, device=device)
    pos_dst = torch.tensor([p[1] for p in pos_pairs], dtype=torch.long, device=device)

    X = torch.tensor(features, dtype=torch.float32, device=device)
    model = GraphSAGEModel(in_dim, hidden, out_dim).to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)

    rng = np.random.default_rng(seed)
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        # Mini-batch over positive edges
        perm = rng.permutation(len(pos_pairs))
        epoch_loss = 0.0
        steps = 0

        for start in range(0, len(perm), batch_size):
            idx = perm[start: start + batch_size]
            bs = pos_src[idx]
            bd = pos_dst[idx]

            # Negative samples (random nodes)
            neg = torch.randint(0, N, (len(idx) * neg_samples,), device=device)

            h = model.forward(X, adj)

            pos_score = (h[bs] * h[bd]).sum(dim=1)
            neg_score = (h[bs.repeat_interleave(neg_samples)] * h[neg]).sum(dim=1)

            loss = -torch.log(torch.sigmoid(pos_score) + 1e-8).mean() \
                   - torch.log(1 - torch.sigmoid(neg_score) + 1e-8).mean()

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            steps += 1

        if epoch % 10 == 0 or epoch == 1:
            logger.info("  epoch %d/%d  loss=%.4f  (%.1fs)", epoch, epochs,
                        epoch_loss / max(steps, 1), time.time() - t0)

    # Final embeddings
    with torch.no_grad():
        h_final = model.forward(X, adj)
        embeddings = h_final.cpu().numpy().astype(np.float32)

    logger.info("GraphSAGE done — embeddings %s", embeddings.shape)
    return embeddings, model


# ── Save ──────────────────────────────────────────────────────────────────────


def save_embeddings(
    output_dir: str | Path,
    nodes_df: pd.DataFrame,
    n2v_emb: np.ndarray | None = None,
    sage_emb: np.ndarray | None = None,
    n2v_model: Any = None,
    sage_model: GraphSAGEModel | None = None,
) -> Path:
    """Save all artefacts to output_dir/embeddings/. Returns the directory path."""
    out = Path(output_dir) / "embeddings"
    out.mkdir(parents=True, exist_ok=True)

    # Index map: name → row index
    index = {row["name"]: int(row["id"]) for _, row in nodes_df.iterrows()}
    # Ensure contiguous index (id may not equal row number)
    name_to_row = {row["name"]: i for i, (_, row) in enumerate(nodes_df.iterrows())}
    (out / "embedding_index.json").write_text(
        json.dumps(name_to_row, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if n2v_emb is not None:
        np.save(out / "node2vec_embeddings.npy", n2v_emb)
        logger.info("Saved node2vec_embeddings.npy %s", n2v_emb.shape)
    if n2v_model is not None:
        with open(out / "node2vec_model.pkl", "wb") as f:
            pickle.dump(n2v_model, f)
        logger.info("Saved node2vec_model.pkl")

    if sage_emb is not None:
        np.save(out / "graphsage_embeddings.npy", sage_emb)
        logger.info("Saved graphsage_embeddings.npy %s", sage_emb.shape)
    if sage_model is not None:
        try:
            import torch
            torch.save(sage_model.state_dict(), out / "graphsage_model.pt")
            logger.info("Saved graphsage_model.pt")
        except ImportError:
            pass

    return out


# ── Evaluate ──────────────────────────────────────────────────────────────────


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def evaluate_embeddings(
    nodes_df: pd.DataFrame,
    embeddings: np.ndarray,
    method: str = "unknown",
) -> dict:
    """
    Compute cosine similarities between anchor pairs and return a report dict.
    Also identifies top-5 nearest neighbours for each anchor.
    """
    name_to_row = {row["name"]: i for i, (_, row) in enumerate(nodes_df.iterrows())}
    all_names = list(nodes_df["name"])

    results: list[dict] = []

    for anchor, neighbors in EVAL_ANCHORS:
        if anchor not in name_to_row:
            logger.warning("Anchor '%s' not in embedding index — skipped", anchor)
            continue

        a_row = name_to_row[anchor]
        a_emb = embeddings[a_row]

        # Similarities to named neighbours
        pair_sims = {}
        for nb in neighbors:
            if nb in name_to_row:
                pair_sims[nb] = _cosine(a_emb, embeddings[name_to_row[nb]])

        # Top-5 nearest overall
        sims_all = np.array([_cosine(a_emb, embeddings[i]) for i in range(len(nodes_df))])
        sims_all[a_row] = -1.0  # exclude self
        top5_idx = np.argsort(sims_all)[::-1][:5]
        top5 = [(all_names[i], round(float(sims_all[i]), 4)) for i in top5_idx]

        results.append(
            {
                "anchor": anchor,
                "named_similarities": {k: round(v, 4) for k, v in pair_sims.items()},
                "top5_nearest": top5,
            }
        )

    report = {
        "method": method,
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "num_nodes": len(nodes_df),
        "embedding_dim": int(embeddings.shape[1]),
        "anchors": results,
    }
    return report


def save_evaluation(output_dir: str | Path, report: dict) -> None:
    out = Path(output_dir) / "embeddings"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "evaluation_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Evaluation report saved → %s", path)
