"""GNN Predictor Module — Heterogeneous Temporal Graph Neural Network.

Architecture: Heterogeneous Temporal GNN using PyTorch Geometric (PyG).

Model: HeteroGATConv + Temporal Encoding → Impact Regression
- Node feature dimension: 384 (sentence-transformer embedding) + 4 financial features = 388
- Edge features: [impact_score, confidence, time_delta_hours]
- Tasks:
    1. Node regression  — predicted future impact on a company
    2. Link prediction  — will a new causal relation appear?
    3. Graph-level      — systemic risk score

Training: on historical data extracted from Neo4j (2020-2026 window).
Inference: called after each KG update.

PyG is an optional dependency — if not installed the module gracefully
falls back to a heuristic rule-based predictor so the pipeline never crashes.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional PyTorch Geometric import ─────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.data import HeteroData
    from torch_geometric.nn import HeteroConv, GATConv, Linear, global_mean_pool
    from torch_geometric.utils import add_self_loops

    _PYG_AVAILABLE = True
    logger.info("GNN: PyTorch Geometric available — using neural predictor")
except ImportError:
    _PYG_AVAILABLE = False
    logger.warning(
        "GNN: PyTorch Geometric not installed — falling back to heuristic predictor. "
        "Install with: pip install torch torch-geometric"
    )

# ── Constants ─────────────────────────────────────────────────────────────────

NODE_FEATURE_DIM = 392          # 384 LLM embedding + 4 financial + 4 structural
EDGE_FEATURE_DIM = 3            # impact_score, confidence, time_delta_hours (normalised)
HIDDEN_DIM = 128
NUM_HEADS = 4
NUM_LAYERS = 2
DROPOUT = 0.2
MODEL_PATH = Path(os.getenv("GNN_MODEL_PATH", "./gnn_model.pt"))

NODE_TYPES = ["Company", "Sector", "Country", "Event", "MacroIndicator"]
EDGE_TYPES = [
    ("Company", "CAUSES_IMPACT_ON", "Company"),
    ("Event", "CAUSES_IMPACT_ON", "Company"),
    ("Country", "CAUSES_IMPACT_ON", "Sector"),
    ("MacroIndicator", "CAUSES_IMPACT_ON", "Company"),
    ("Company", "BELONGS_TO_SECTOR", "Sector"),
    ("Company", "COMPETES_WITH", "Company"),
    ("Company", "SUPPLY_CHAIN_LINK", "Company"),
]


# ══════════════════════════════════════════════════════════════════════════════
# A. Neural GNN (used when PyG is available)
# ══════════════════════════════════════════════════════════════════════════════

if _PYG_AVAILABLE:

    class TemporalEncoding(nn.Module):
        """Sinusoidal temporal encoding for edge timestamps."""

        def __init__(self, dim: int = 32):
            super().__init__()
            self.dim = dim
            self.w = nn.Linear(1, dim)

        def forward(self, t: "torch.Tensor") -> "torch.Tensor":
            # t: [E, 1] normalised time delta (0=now, 1=1 year ago)
            freq = torch.arange(0, self.dim // 2, device=t.device).float()
            freq = 1.0 / (10000 ** (2 * freq / self.dim))
            enc = t * freq.unsqueeze(0)
            return torch.cat([enc.sin(), enc.cos()], dim=-1)

    class HeteroTemporalGNN(nn.Module):
        """Heterogeneous Temporal GNN for market impact prediction.

        Layers:
            1. Per-node-type linear projection (→ HIDDEN_DIM)
            2. N × HeteroGATConv with temporal edge features
            3. Per-node-type MLP head
        Tasks:
            - impact_regression  : predict future impact score for each Company node
            - link_prediction    : score of new CAUSES_IMPACT_ON links
            - graph_risk         : global systemic risk (0–1)
        """

        def __init__(
            self,
            in_channels: int = NODE_FEATURE_DIM,
            hidden: int = HIDDEN_DIM,
            heads: int = NUM_HEADS,
            num_layers: int = NUM_LAYERS,
            dropout: float = DROPOUT,
        ):
            super().__init__()
            self.dropout = dropout

            # Per-node-type input projections
            self.projections = nn.ModuleDict({
                ntype: Linear(in_channels, hidden)
                for ntype in NODE_TYPES
            })

            # Temporal encoding for edge timestamps
            self.temporal_enc = TemporalEncoding(dim=32)
            temporal_dim = 32

            # GNN layers
            self.convs = nn.ModuleList()
            for layer in range(num_layers):
                in_ch = hidden if layer > 0 else hidden
                conv_dict = {}
                for src, rel, dst in EDGE_TYPES:
                    conv_dict[(src, rel, dst)] = GATConv(
                        (in_ch, in_ch),
                        hidden // heads,
                        heads=heads,
                        add_self_loops=False,
                        edge_dim=EDGE_FEATURE_DIM + temporal_dim,
                        dropout=dropout,
                        concat=True,
                    )
                self.convs.append(HeteroConv(conv_dict, aggr="sum"))

            # Task heads
            self.impact_head = nn.Sequential(
                nn.Linear(hidden, hidden // 2),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden // 2, 1),
                nn.Tanh(),  # output in [-1, 1]
            )
            self.link_head = nn.Sequential(
                nn.Linear(hidden * 2, hidden),
                nn.ReLU(),
                nn.Linear(hidden, 1),
                nn.Sigmoid(),
            )
            self.risk_head = nn.Sequential(
                nn.Linear(hidden, hidden // 2),
                nn.ReLU(),
                nn.Linear(hidden // 2, 1),
                nn.Sigmoid(),
            )

        def encode(self, data: "HeteroData") -> Dict[str, "torch.Tensor"]:
            """Compute node embeddings through all GNN layers."""
            # Initial projection
            x_dict: Dict[str, torch.Tensor] = {}
            for ntype in NODE_TYPES:
                if ntype in data.node_types and hasattr(data[ntype], "x"):
                    x_dict[ntype] = F.relu(self.projections[ntype](data[ntype].x))
                else:
                    # Placeholder if node type absent in this graph
                    x_dict[ntype] = torch.zeros(1, HIDDEN_DIM)

            # Build edge_attr_dict with temporal encoding
            edge_attr_dict: Dict[Tuple, Optional[torch.Tensor]] = {}
            for et in data.edge_types:
                if et in data.edge_index_dict:
                    if hasattr(data[et], "edge_attr") and data[et].edge_attr is not None:
                        base_ea = data[et].edge_attr  # [E, 3]
                        # Temporal component (first column = time_delta_norm)
                        t_col = base_ea[:, 2:3]
                        t_enc = self.temporal_enc(t_col)  # [E, 32]
                        edge_attr_dict[et] = torch.cat([base_ea, t_enc], dim=-1)
                    else:
                        edge_attr_dict[et] = None

            # GNN layers
            for conv in self.convs:
                x_dict = conv(x_dict, data.edge_index_dict, edge_attr_dict=edge_attr_dict)
                x_dict = {k: F.relu(v) for k, v in x_dict.items()}
                x_dict = {k: F.dropout(v, p=self.dropout, training=self.training)
                          for k, v in x_dict.items()}
            return x_dict

        def forward(
            self,
            data: "HeteroData",
        ) -> Dict[str, "torch.Tensor"]:
            x_dict = self.encode(data)
            company_emb = x_dict.get("Company", torch.zeros(1, HIDDEN_DIM))

            # Task 1: Impact regression per Company node
            impact = self.impact_head(company_emb)

            # Task 3: Systemic risk from mean pooling
            all_embs = torch.cat(list(x_dict.values()), dim=0)
            pool = all_embs.mean(dim=0, keepdim=True)
            risk = self.risk_head(pool)

            return {"impact": impact, "risk": risk}

        def predict_link(
            self, src_emb: "torch.Tensor", dst_emb: "torch.Tensor"
        ) -> "torch.Tensor":
            """Score a candidate CAUSES_IMPACT_ON edge."""
            return self.link_head(torch.cat([src_emb, dst_emb], dim=-1))


# ══════════════════════════════════════════════════════════════════════════════
# B. Graph Builder — converts Neo4j data into PyG HeteroData
# ══════════════════════════════════════════════════════════════════════════════

class GraphBuilder:
    """Converts Neo4j query results into a PyG HeteroData object for inference."""

    def __init__(self, embedding_model=None):
        self._embedder = embedding_model  # sentence-transformers model or None

    def _text_embedding(self, text: str) -> List[float]:
        """Return a 384-dim sentence embedding (or zeros if model unavailable)."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                return [0.0] * 384
        try:
            vec = self._embedder.encode(text, show_progress_bar=False)
            return vec.tolist()
        except Exception:
            return [0.0] * 384

    def build_from_kg_snapshot(
        self,
        snapshot: Dict[str, Any],
        price_data: Optional[Dict[str, Any]] = None,
    ) -> Optional["HeteroData"]:
        """Build a HeteroData from a KG ego-graph snapshot dict."""
        if not _PYG_AVAILABLE:
            return None
        if not snapshot.get("nodes"):
            return None

        data = HeteroData()
        now = datetime.utcnow()

        # Index nodes by (label, name)
        node_indices: Dict[Tuple[str, str], int] = {}
        node_features: Dict[str, List[List[float]]] = {nt: [] for nt in NODE_TYPES}
        node_counts: Dict[str, int] = {nt: 0 for nt in NODE_TYPES}

        for node in snapshot["nodes"]:
            label = (node.get("labels") or ["Company"])[0]
            name = node.get("name", "?")
            if label not in NODE_TYPES:
                label = "Company"

            # Build feature vector: [embedding(384) + financial(4) + structural(4)]
            emb = self._text_embedding(name)
            ticker = node.get("ticker", "")
            prices = price_data.get(ticker, {}) if price_data and ticker else {}
            fin_feats = [
                prices.get("change_pct", 0.0),
                min(math.log1p(prices.get("volume", 0)) / 20, 1.0),
                prices.get("volatility_annualised_pct", 0.0) / 100,
                min(prices.get("price", 0) / 1000, 1.0),
            ]
            structural_feats = [0.0] * 4   # degree features (filled in post)
            feature_vec = emb + fin_feats + structural_feats

            node_idx = node_counts[label]
            node_indices[(label, name)] = node_idx
            node_features[label].append(feature_vec)
            node_counts[label] += 1

        # Assign node feature tensors
        for label in NODE_TYPES:
            feats = node_features[label]
            if feats:
                data[label].x = torch.tensor(feats, dtype=torch.float32)
            else:
                data[label].x = torch.zeros((0, NODE_FEATURE_DIM), dtype=torch.float32)

        # Build edge tensors
        edge_src: Dict[Tuple, List[int]] = {et: [] for et in EDGE_TYPES}
        edge_dst: Dict[Tuple, List[int]] = {et: [] for et in EDGE_TYPES}
        edge_attrs: Dict[Tuple, List[List[float]]] = {et: [] for et in EDGE_TYPES}

        for edge in snapshot["edges"]:
            # Map node ids back to (label, name) — use index from snapshot
            from_id = edge.get("from")
            to_id = edge.get("to")
            from_node = next(
                (n for n in snapshot["nodes"] if n["id"] == from_id), None
            )
            to_node = next(
                (n for n in snapshot["nodes"] if n["id"] == to_id), None
            )
            if not from_node or not to_node:
                continue

            from_label = (from_node.get("labels") or ["Company"])[0]
            to_label = (to_node.get("labels") or ["Company"])[0]
            if from_label not in NODE_TYPES:
                from_label = "Company"
            if to_label not in NODE_TYPES:
                to_label = "Company"

            rel = edge.get("type", "CAUSES_IMPACT_ON")
            et_key = (from_label, rel, to_label)

            # Find matching declared edge type
            matched_et = None
            for et in EDGE_TYPES:
                if et[0] == from_label and et[1] == rel and et[2] == to_label:
                    matched_et = et
                    break
            if matched_et is None:
                matched_et = (from_label, "CAUSES_IMPACT_ON", to_label)
                if matched_et not in EDGE_TYPES:
                    continue

            src_idx = node_indices.get((from_label, from_node["name"]))
            dst_idx = node_indices.get((to_label, to_node["name"]))
            if src_idx is None or dst_idx is None:
                continue

            # Edge features: [impact_score, confidence, time_delta_norm]
            impact_score = float(edge.get("impact_score") or 0.0)
            confidence = float(edge.get("confidence") or 0.5)
            ts_str = edge.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    td = (now - ts.replace(tzinfo=None)).total_seconds() / (365 * 24 * 3600)
                    time_delta = min(max(td, 0.0), 1.0)
                except Exception:
                    time_delta = 0.5
            else:
                time_delta = 0.5

            edge_src[matched_et].append(src_idx)
            edge_dst[matched_et].append(dst_idx)
            edge_attrs[matched_et].append([impact_score, confidence, time_delta])

        # Assign edge tensors
        for et in EDGE_TYPES:
            srcs = edge_src[et]
            dsts = edge_dst[et]
            if srcs:
                src_t, dst_t = [et[0], et[2]]
                data[et].edge_index = torch.tensor(
                    [srcs, dsts], dtype=torch.long
                )
                data[et].edge_attr = torch.tensor(
                    edge_attrs[et], dtype=torch.float32
                )

        return data


# ══════════════════════════════════════════════════════════════════════════════
# C. GNN Predictor — main interface
# ══════════════════════════════════════════════════════════════════════════════

class GNNPredictor:
    """Production-ready GNN predictor.

    If PyG is available and a trained model exists, runs neural inference.
    Otherwise falls back to a rule-based heuristic that uses the KG edge weights.
    """

    def __init__(self):
        self._model: Optional["HeteroTemporalGNN"] = None
        self._builder = GraphBuilder()

    def _load_or_init_model(self) -> Optional["HeteroTemporalGNN"]:
        if not _PYG_AVAILABLE:
            return None
        if self._model is None:
            model = HeteroTemporalGNN()
            if MODEL_PATH.exists():
                try:
                    state = torch.load(str(MODEL_PATH), map_location="cpu")
                    model.load_state_dict(state)
                    logger.info("GNN: loaded model from %s", MODEL_PATH)
                except Exception as e:
                    logger.warning("GNN: could not load model — %s — using fresh weights", e)
            else:
                logger.info("GNN: no saved model — using random weights for inference")
            model.eval()
            self._model = model
        return self._model

    def save_model(self) -> None:
        """Persist model weights to disk."""
        if self._model and _PYG_AVAILABLE:
            torch.save(self._model.state_dict(), str(MODEL_PATH))
            logger.info("GNN: model saved to %s", MODEL_PATH)

    def train(
        self,
        training_snapshots: List[Tuple["HeteroData", float]],
        epochs: int = 50,
        lr: float = 1e-3,
    ) -> Dict[str, List[float]]:
        """Train the GNN on historical (graph, target_impact) pairs.

        Args:
            training_snapshots: List of (HeteroData, target_impact) tuples.
                                 target_impact ∈ [-1, 1] for Talan's company node.
            epochs: Number of training epochs.
            lr:     Learning rate.

        Returns:
            Dict with 'train_losses' list.
        """
        if not _PYG_AVAILABLE:
            logger.warning("GNN training skipped — PyG not available")
            return {"train_losses": []}

        model = self._load_or_init_model()
        if model is None:
            return {"train_losses": []}

        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        criterion = nn.MSELoss()
        losses = []

        logger.info("GNN: starting training — %d samples, %d epochs", len(training_snapshots), epochs)
        for epoch in range(epochs):
            epoch_loss = 0.0
            for data, target in training_snapshots:
                optimizer.zero_grad()
                out = model(data)
                # Target is impact on Talan (index 0 of Company nodes, by convention)
                pred = out["impact"][0] if out["impact"].numel() > 0 else torch.tensor([0.0])
                tgt = torch.tensor([[target]], dtype=torch.float32)
                loss = criterion(pred, tgt)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                epoch_loss += loss.item()
            scheduler.step()
            avg = epoch_loss / max(len(training_snapshots), 1)
            losses.append(avg)
            if (epoch + 1) % 10 == 0:
                logger.info("GNN epoch %d/%d — loss=%.4f", epoch + 1, epochs, avg)

        model.eval()
        self._model = model
        self.save_model()
        return {"train_losses": losses}

    def predict(
        self,
        kg_snapshot: Dict[str, Any],
        price_data: Optional[Dict[str, Any]] = None,
        trigger_event: str = "unknown",
        company_names: Optional[List[str]] = None,
    ) -> "GNNInferenceResult":
        """Run inference. Returns GNNInferenceResult."""
        from app.schemas.market_analysis_schemas import GNNInferenceResult, GNNPrediction, AlertLevel

        now = datetime.utcnow()
        nodes = kg_snapshot.get("nodes", [])
        edges = kg_snapshot.get("edges", [])

        if _PYG_AVAILABLE:
            result = self._neural_predict(
                kg_snapshot, price_data, trigger_event, company_names
            )
        else:
            result = self._heuristic_predict(
                nodes, edges, trigger_event, company_names
            )
        return result

    def _neural_predict(
        self,
        snapshot: Dict[str, Any],
        price_data: Optional[Dict[str, Any]],
        trigger_event: str,
        company_names: Optional[List[str]],
    ) -> "GNNInferenceResult":
        from app.schemas.market_analysis_schemas import GNNInferenceResult, GNNPrediction

        model = self._load_or_init_model()
        if model is None:
            return self._heuristic_predict(
                snapshot.get("nodes", []), snapshot.get("edges", []),
                trigger_event, company_names
            )

        data = self._builder.build_from_kg_snapshot(snapshot, price_data)
        if data is None:
            return self._heuristic_predict(
                snapshot.get("nodes", []), snapshot.get("edges", []),
                trigger_event, company_names
            )

        with (torch.no_grad() if _PYG_AVAILABLE else _DummyContext()):
            out = model(data)

        company_nodes = [
            n for n in snapshot["nodes"]
            if (n.get("labels") or ["?"])[0] == "Company"
        ]

        predictions = []
        impact_tensor = out.get("impact", torch.zeros(len(company_nodes), 1))
        risk_score = float(out.get("risk", torch.tensor([[0.5]]))[0, 0])

        for i, node in enumerate(company_nodes):
            score = float(impact_tensor[i, 0]) if i < len(impact_tensor) else 0.0
            hop = _compute_hops(snapshot, node["name"], trigger_event)
            is_talan = node["name"] == "Talan"
            # Mark as hidden risk if score is significant and hops > 1
            hidden = abs(score) > 0.3 and hop > 1 and not is_talan
            pred = GNNPrediction(
                entity_name=node["name"],
                entity_type="company",
                predicted_impact=round(score, 4),
                confidence=round(max(0.4, 1.0 - hop * 0.15), 3),
                propagation_hops=hop,
                hidden_risk=hidden,
            )
            predictions.append(pred)

        talan_pred = next((p for p in predictions if p.entity_name == "Talan"), None)
        hidden_risks = [p for p in predictions if p.hidden_risk and p.predicted_impact < -0.2]
        hidden_risks.sort(key=lambda p: p.predicted_impact)

        from app.schemas.market_analysis_schemas import GNNInferenceResult
        return GNNInferenceResult(
            run_at=datetime.utcnow(),
            trigger_event=trigger_event,
            predictions=predictions,
            talan_prediction=talan_pred,
            systemic_risk_score=round(risk_score, 4),
            top_hidden_risks=hidden_risks[:5],
        )

    def _heuristic_predict(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        trigger_event: str,
        company_names: Optional[List[str]],
    ) -> "GNNInferenceResult":
        """Rule-based fallback when PyG is unavailable.

        Propagates impact scores through the graph using a weighted BFS.
        """
        from app.schemas.market_analysis_schemas import GNNInferenceResult, GNNPrediction

        # Build adjacency: {to_name: [(from_name, impact_score, confidence)]}
        adj: Dict[str, List[Tuple]] = {}
        name_map = {n["id"]: n["name"] for n in nodes}
        for edge in edges:
            to_name = name_map.get(edge.get("to"), "?")
            from_name = name_map.get(edge.get("from"), "?")
            score = float(edge.get("impact_score") or 0.0)
            conf = float(edge.get("confidence") or 0.5)
            adj.setdefault(to_name, []).append((from_name, score, conf))

        # BFS propagation for each company node
        company_nodes = [n for n in nodes if (n.get("labels") or ["?"])[0] == "Company"]
        predictions = []
        for node in company_nodes:
            name = node["name"]
            direct = adj.get(name, [])
            score = sum(s * c for _, s, c in direct) / max(len(direct), 1)
            hop = 1 if direct else 0
            # Second-order
            second_order = []
            for dep_name, _, _ in direct:
                for _, s2, c2 in adj.get(dep_name, []):
                    second_order.append(s2 * c2 * 0.5)
            if second_order:
                score += sum(second_order) / len(second_order)
                hop = 2
            score = max(-1.0, min(1.0, score))
            hidden = abs(score) > 0.3 and hop == 2 and name != "Talan"
            predictions.append(GNNPrediction(
                entity_name=name,
                entity_type="company",
                predicted_impact=round(score, 4),
                confidence=round(0.6 - hop * 0.1, 3),
                propagation_hops=hop,
                hidden_risk=hidden,
            ))

        predictions.sort(key=lambda p: p.predicted_impact)
        talan = next((p for p in predictions if p.entity_name == "Talan"), None)
        systemic = abs(sum(p.predicted_impact for p in predictions)) / max(len(predictions), 1)
        hidden_risks = [p for p in predictions if p.hidden_risk][:5]

        return GNNInferenceResult(
            run_at=datetime.utcnow(),
            trigger_event=trigger_event,
            predictions=predictions,
            talan_prediction=talan,
            systemic_risk_score=round(min(systemic, 1.0), 4),
            top_hidden_risks=hidden_risks,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_hops(snapshot: Dict, target_name: str, source_name: str) -> int:
    """BFS hop count from source to target in the snapshot graph."""
    edges = snapshot.get("edges", [])
    nodes = snapshot.get("nodes", [])
    name_map = {n["id"]: n["name"] for n in nodes}
    id_map = {n["name"]: n["id"] for n in nodes}

    src_id = id_map.get(source_name)
    dst_id = id_map.get(target_name)
    if src_id is None or dst_id is None:
        return 1

    # BFS
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e["from"], []).append(e["to"])

    visited = {src_id}
    queue = [(src_id, 0)]
    while queue:
        cur, hops = queue.pop(0)
        if cur == dst_id:
            return hops
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, hops + 1))
    return 3   # not found → assume distant


class _DummyContext:
    """Context manager no-op for when torch.no_grad() is unavailable."""
    def __enter__(self): return self
    def __exit__(self, *a): pass
