"""GNN Predictor — TGAT (Temporal Graph Attention Network).

Architecture (ported from train_tgat.py):
  1. Time2Vec encoder    : scalar t → 33-d sinusoidal embedding (learnable freq/phase)
  2. 2 × TSAT layers    : Temporal Self-Attention over K most-recent temporal neighbours
  3. Link prediction MLP : concat(z_src, z_dst) → sigmoid score

Checkpoint: checkpoints/tgat_best.pt  (AUC 0.9227, AP 0.9600, F1 0.9532)

Inference workflow:
  1. LiveGraphAdapter converts a KG snapshot (from Neo4j / orchestrator) into TGAT tensors:
       - x [N, 396]  — one-hot type + centrality + 384-d embedding slot
       - src/dst      — edge indices
       - t            — timestamps normalised to [0, 1] (days since 2021-01-01 / 1461)
  2. All edges are fed to TemporalNeighborStore to build temporal context.
  3. TGAT scores each IMPACTS-type edge: P(causal) ∈ [0, 1].
  4. Edge scores are aggregated per entity:
       - predicted_impact ∈ [-1, 1]  (signed by edge impact_direction)
       - systemic_risk_score         (mean of all link scores)
  5. Returns GNNInferenceResult — same schema as before; orchestrator unchanged.

Feature layout (must match training, see gnn_causal_dataset/metadata.json):
  [0:10]   one-hot node type  (Company=0 … Event=9)
  [10]     in-degree centrality normalised
  [11]     impact / risk score normalised
  [12:396] 384-d Gaussian cluster embedding (zeros at inference — temporal attention
           patterns learned during training dominate over raw feature values)
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    _TORCH_AVAILABLE = True
    logger.info("GNN: PyTorch available — using TGAT predictor")
except ImportError:
    _TORCH_AVAILABLE = False
    logger.warning("GNN: PyTorch not installed — GNNPredictor unavailable.")

# ── Paths & hyper-parameters (must match training) ────────────────────────────

HERE      = Path(__file__).parent.resolve()
CKPT_PATH = HERE / "checkpoints" / "tgat_best.pt"

TIME_DIM    = 32
HIDDEN_DIM  = 128
N_HEADS     = 4
N_NEIGHBORS = 20
FEAT_DIM    = 396   # from metadata.json — fixed by the trained checkpoint weights

_TOTAL_DAYS = (datetime(2025, 1, 1) - datetime(2021, 1, 1)).days   # 1461
_START_DATE = datetime(2021, 1, 1, tzinfo=timezone.utc)

# Training node types (order = one-hot index, must match generator)
_TRAIN_NODE_TYPES = [
    "Company", "BusinessUnit", "Sector", "Geography",
    "Client", "Project", "Competitor", "Regulation",
    "MacroIndicator", "Event",
]
_TYPE_INDEX = {t: i for i, t in enumerate(_TRAIN_NODE_TYPES)}

# Neo4j label → training node type
_LABEL_MAP: Dict[str, str] = {
    "Company":       "Company",
    "Competitor":    "Competitor",
    "Sector":        "Sector",
    "Country":       "Geography",
    "Event":         "Event",
    "MacroIndicator":"MacroIndicator",
    "Regulation":    "Regulation",
    "Person":        "Company",
    "Technology":    "BusinessUnit",
    "MarketTrend":   "Sector",
    "News":          "Event",
}


# ══════════════════════════════════════════════════════════════════════════════
# §1  TGAT MODEL (exact port from train_tgat.py)
# ══════════════════════════════════════════════════════════════════════════════

if _TORCH_AVAILABLE:

    class TimeEncoder(nn.Module):
        """Time2Vec: φ(t) = [t, sin(w₁·t+b₁), …, sin(w_d·t+b_d)]  (learnable)."""

        def __init__(self, dim: int = TIME_DIM):
            super().__init__()
            self.w = nn.Parameter(torch.randn(dim) * 0.1)
            self.b = nn.Parameter(torch.zeros(dim))

        def forward(self, t: "torch.Tensor") -> "torch.Tensor":
            t = t.unsqueeze(-1)
            return torch.cat([t, torch.sin(t * self.w + self.b)], dim=-1)

        @property
        def out_dim(self) -> int:
            return int(self.w.shape[0]) + 1


    class TSATLayer(nn.Module):
        """
        Temporal Self-Attention layer.

        For node v with feature h_v at query time t:
          Q = Linear(cat(h_v,    φ(0)))
          K = Linear(cat(h_nbrs, φ(t − t_nbrs)))
          V = same
          out = LayerNorm(FF(cat(MHA(Q,K,V), h_v)))
        """

        def __init__(self, feat_dim: int, time_enc_dim: int, hidden: int, n_heads: int):
            super().__init__()
            in_qkv      = feat_dim + time_enc_dim
            self.q_proj = nn.Linear(in_qkv, hidden)
            self.k_proj = nn.Linear(in_qkv, hidden)
            self.v_proj = nn.Linear(in_qkv, hidden)
            self.attn   = nn.MultiheadAttention(hidden, n_heads, batch_first=True, dropout=0.1)
            self.ff     = nn.Sequential(nn.Linear(hidden + feat_dim, hidden), nn.GELU())
            self.norm   = nn.LayerNorm(hidden)
            self.no_nbr = nn.Linear(feat_dim, hidden)

        def forward(
            self,
            h_v:    "torch.Tensor",
            h_nbrs: List["torch.Tensor"],
            t_v:    "torch.Tensor",
            t_nbrs: List["torch.Tensor"],
            time_enc: "TimeEncoder",
        ) -> "torch.Tensor":
            B   = h_v.size(0)
            t0  = time_enc(torch.zeros(1, device=h_v.device))
            out = []
            for i in range(B):
                nbrs = h_nbrs[i]
                if nbrs.numel() == 0 or nbrs.size(0) == 0:
                    out.append(self.norm(self.no_nbr(h_v[i])))
                    continue
                nts       = t_nbrs[i].to(h_v.device)
                dt        = (t_v[i] - nts).clamp(min=0)
                t_nbr_enc = time_enc(dt)
                t_v_enc   = t0.expand(1, -1)
                q = self.q_proj(torch.cat([h_v[i].unsqueeze(0), t_v_enc], dim=-1))
                kv_in = torch.cat([nbrs.to(h_v.device), t_nbr_enc], dim=-1)
                k = self.k_proj(kv_in)
                v = self.v_proj(kv_in)
                attn_out, _ = self.attn(q.unsqueeze(0), k.unsqueeze(0), v.unsqueeze(0))
                attn_out = attn_out.squeeze(0).squeeze(0)
                merged = self.ff(torch.cat([attn_out, h_v[i]], dim=-1))
                out.append(self.norm(merged))
            return torch.stack(out, dim=0)


    class TGAT(nn.Module):
        """2-layer Temporal Graph Attention Network (stateless, no GRU memory)."""

        def __init__(self, node_feat_dim: int = FEAT_DIM):
            super().__init__()
            self.time_enc  = TimeEncoder(TIME_DIM)
            t_dim          = self.time_enc.out_dim
            self.layer1    = TSATLayer(node_feat_dim, t_dim, HIDDEN_DIM, N_HEADS)
            self.layer2    = TSATLayer(HIDDEN_DIM,    t_dim, HIDDEN_DIM, N_HEADS)
            self.predictor = nn.Sequential(
                nn.Linear(2 * HIDDEN_DIM, HIDDEN_DIM),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(HIDDEN_DIM, 1),
            )

        def embed_nodes(
            self,
            node_ids:  "torch.Tensor",
            t_query:   "torch.Tensor",
            x:         "torch.Tensor",
            nbr_store: "TemporalNeighborStore",
        ) -> "torch.Tensor":
            B = node_ids.size(0)
            nbr_ids_L2, nbr_ts_L2 = nbr_store.query(node_ids, t_query)

            # Collect unique neighbours to embed in Layer 1
            all_nbr_ids = (
                torch.cat([n for n in nbr_ids_L2 if n.numel() > 0])
                if any(n.numel() > 0 for n in nbr_ids_L2)
                else torch.tensor([], dtype=torch.long)
            )
            all_nbr_t = (
                torch.cat([t for t in nbr_ts_L2 if t.numel() > 0])
                if any(t.numel() > 0 for t in nbr_ts_L2)
                else torch.tensor([], dtype=torch.float)
            )

            nbr_embed: Dict[int, "torch.Tensor"] = {}
            if all_nbr_ids.numel() > 0:
                unique_nbrs, _ = torch.unique(all_nbr_ids, return_inverse=True)
                nbr_t_map: Dict[int, float] = {}
                for nid, nt in zip(all_nbr_ids.tolist(), all_nbr_t.tolist()):
                    nbr_t_map[nid] = max(nbr_t_map.get(nid, 0.0), nt)
                un_list = unique_nbrs.tolist()
                un_t    = torch.tensor([nbr_t_map[nid] for nid in un_list])
                nn_ids, nn_ts = nbr_store.query(unique_nbrs, un_t)
                h_unique  = x[unique_nbrs]
                nn_feats  = [
                    x[ids] if ids.numel() > 0 else torch.zeros(0, x.size(1))
                    for ids in nn_ids
                ]
                with torch.no_grad():
                    h_unique = self.layer1(h_unique, nn_feats, un_t, nn_ts, self.time_enc)
                for uid, h in zip(unique_nbrs.tolist(), h_unique):
                    nbr_embed[uid] = h

            # Project target node raw features → HIDDEN_DIM via Layer 1 (no-neighbour path)
            h_target   = x[node_ids]
            dummy_nbrs = [torch.zeros(0, x.size(1)) for _ in range(B)]
            dummy_ts   = [torch.zeros(0) for _ in range(B)]
            h_target   = self.layer1(h_target, dummy_nbrs, t_query, dummy_ts, self.time_enc)

            # Layer 2: embed target using Layer-1 neighbour embeddings
            nbr_h_L2 = []
            for i in range(B):
                ids = nbr_ids_L2[i]
                if ids.numel() == 0:
                    nbr_h_L2.append(torch.zeros(0, HIDDEN_DIM))
                else:
                    nbr_h_L2.append(
                        torch.stack([
                            nbr_embed.get(nid, torch.zeros(HIDDEN_DIM))
                            for nid in ids.tolist()
                        ])
                    )
            return self.layer2(h_target, nbr_h_L2, t_query, nbr_ts_L2, self.time_enc)

        def predict(self, z_src: "torch.Tensor", z_dst: "torch.Tensor") -> "torch.Tensor":
            return self.predictor(torch.cat([z_src, z_dst], dim=-1)).squeeze(-1)


    class TemporalNeighborStore:
        """Maintains a causal temporal adjacency list (only past events visible)."""

        def __init__(self, max_nbrs: int = N_NEIGHBORS):
            self.max_nbrs = max_nbrs
            self._nbrs: Dict[int, List[Tuple[int, float]]] = defaultdict(list)

        def add_edges(self, src: "torch.Tensor", dst: "torch.Tensor",
                      t: "torch.Tensor") -> None:
            for s, d, ti in zip(src.tolist(), dst.tolist(), t.tolist()):
                self._nbrs[s].append((d, float(ti)))
                self._nbrs[d].append((s, float(ti)))

        def query(
            self, node_ids: "torch.Tensor", t_now: "torch.Tensor"
        ) -> Tuple[List["torch.Tensor"], List["torch.Tensor"]]:
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


# ══════════════════════════════════════════════════════════════════════════════
# §2  LIVE GRAPH ADAPTER
#     Converts a KG snapshot dict (from Neo4j / orchestrator) into TGAT tensors.
# ══════════════════════════════════════════════════════════════════════════════

class LiveGraphAdapter:
    """
    Converts a kg_snapshot dict (Neo4j ego-graph) into the tensors TGAT expects.

    Feature vector (396-d, matches training layout):
      [0:10]   one-hot node type
      [10]     in-degree centrality normalised  (by max degree in snapshot)
      [11]     outgoing impact score normalised (mean |impact_score| of edges)
      [12:396] zeros  (training used Gaussian cluster embeddings; at inference
               the temporal attention pattern dominates raw features)

    Edge timestamps are normalised as:  days_since_2021 / 1461  ∈ [0, 1]
    Missing timestamps default to "now".
    """

    _IMPACT_EDGE_TYPES = {
        "IMPACTS", "CAUSES_IMPACT_ON", "INFLUENCES", "AFFECTS",
        "AFFECTS_INDICATOR", "TRIGGERS_EVENT",
    }

    def build(
        self,
        snapshot: Dict[str, Any],
        price_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Returns a dict with keys:
          x          : torch.Tensor [N, 396]
          src        : torch.Tensor [E]  (int64)
          dst        : torch.Tensor [E]  (int64)
          t          : torch.Tensor [E]  (float32, normalised)
          impacts_mask: torch.Tensor [E] (bool, True for IMPACTS-type edges)
          edge_impact_dir: List[float]   (+1 / −1 per edge, from impact_direction)
          edge_confidence: List[float]   per edge
          node_names  : List[str]        name for each node index
          node_types  : List[str]        training type for each node index
        """
        nodes = snapshot.get("nodes", [])
        edges = snapshot.get("edges", [])
        if not nodes:
            return None

        now_ts = self._ts_to_norm(datetime.now(timezone.utc).isoformat())

        # ── Build node index ──────────────────────────────────────────────────
        node_id_to_idx: Dict[str, int] = {}
        node_names:     List[str]      = []
        node_type_names:List[str]      = []

        for node in nodes:
            neo_id = str(node.get("id", node.get("name", "")))
            if neo_id in node_id_to_idx:
                continue
            idx = len(node_names)
            node_id_to_idx[neo_id] = idx
            node_names.append(node.get("name", neo_id))
            raw_label = (node.get("labels") or ["Company"])[0]
            node_type_names.append(_LABEL_MAP.get(raw_label, "Company"))

        N = len(node_names)

        # ── Compute degree centrality (for feature dim 10) ─────────────────────
        in_degree: Dict[int, int] = defaultdict(int)
        out_impact: Dict[int, List[float]] = defaultdict(list)

        for edge in edges:
            src_id = str(edge.get("from", ""))
            dst_id = str(edge.get("to",   ""))
            if src_id in node_id_to_idx and dst_id in node_id_to_idx:
                in_degree[node_id_to_idx[dst_id]] += 1
                score = abs(float(edge.get("impact_score") or 0.0))
                out_impact[node_id_to_idx[src_id]].append(score)

        max_degree = max(in_degree.values(), default=1) or 1

        # ── Build feature matrix ───────────────────────────────────────────────
        x = np.zeros((N, FEAT_DIM), dtype=np.float32)
        for i, (_, ttype) in enumerate(zip(node_names, node_type_names)):
            type_idx = _TYPE_INDEX.get(ttype, 0)
            x[i, type_idx] = 1.0                                          # one-hot
            x[i, 10] = in_degree.get(i, 0) / max_degree                  # centrality
            scores = out_impact.get(i, [])
            x[i, 11] = float(np.mean(scores)) if scores else 0.0          # impact norm
            # Inject price data for companies if available
            if price_data:
                # find ticker from snapshot node
                node_meta = next(
                    (n for n in nodes
                     if str(n.get("id", n.get("name", ""))) == list(node_id_to_idx.keys())[i]),
                    {},
                )
                ticker = node_meta.get("ticker", "")
                if ticker and ticker in price_data:
                    pd = price_data[ticker]
                    x[i, 12] = max(-1.0, min(1.0, pd.get("change_pct", 0.0) / 10.0))
                    x[i, 13] = min(math.log1p(pd.get("volume", 0)) / 20, 1.0)

        # ── Build edge tensors ─────────────────────────────────────────────────
        srcs:           List[int]   = []
        dsts:           List[int]   = []
        ts:             List[float] = []
        impacts_mask:   List[bool]  = []
        edge_impact_dir:List[float] = []
        edge_confidence:List[float] = []

        for edge in edges:
            src_id = str(edge.get("from", ""))
            dst_id = str(edge.get("to",   ""))
            if src_id not in node_id_to_idx or dst_id not in node_id_to_idx:
                continue

            srcs.append(node_id_to_idx[src_id])
            dsts.append(node_id_to_idx[dst_id])

            ts_str = edge.get("timestamp")
            ts.append(self._ts_to_norm(ts_str) if ts_str else now_ts)

            etype  = str(edge.get("type", ""))
            impacts_mask.append(etype in self._IMPACT_EDGE_TYPES)

            direction = str(edge.get("impact_direction", "uncertain")).lower()
            edge_impact_dir.append(-1.0 if direction == "negative" else 1.0)
            edge_confidence.append(float(edge.get("confidence") or 0.5))

        if not srcs:
            return None

        if not _TORCH_AVAILABLE:
            return None

        return {
            "x":              torch.tensor(x, dtype=torch.float32),
            "src":            torch.tensor(srcs, dtype=torch.long),
            "dst":            torch.tensor(dsts, dtype=torch.long),
            "t":              torch.tensor(ts,   dtype=torch.float32),
            "impacts_mask":   torch.tensor(impacts_mask, dtype=torch.bool),
            "edge_impact_dir":edge_impact_dir,
            "edge_confidence":edge_confidence,
            "node_names":     node_names,
            "node_types":     node_type_names,
        }

    @staticmethod
    def _ts_to_norm(ts: str) -> float:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            days = (dt - _START_DATE).days
            return float(np.clip(days / _TOTAL_DAYS, 0.0, 1.0))
        except Exception:
            return 1.0   # default: "now" (end of range)


# ══════════════════════════════════════════════════════════════════════════════
# §3  GNN PREDICTOR — main interface
# ══════════════════════════════════════════════════════════════════════════════

class GNNPredictor:
    """
    TGAT-based market impact predictor.

    Loads checkpoint/tgat_best.pt on first call.
    Falls back to heuristic scoring if PyTorch is unavailable or the
    snapshot has no scorable edges.
    """

    def __init__(self):
        self._model: Optional["TGAT"] = None
        self._adapter = LiveGraphAdapter()
        self._trained  = CKPT_PATH.exists()
        if not _TORCH_AVAILABLE:
            logger.warning("GNN: PyTorch unavailable — heuristic fallback active")

    @property
    def is_trained(self) -> bool:
        return self._trained

    def _load_model(self) -> "TGAT":
        if self._model is not None:
            return self._model
        if not _TORCH_AVAILABLE:
            raise RuntimeError("PyTorch not installed.")
        model = TGAT(node_feat_dim=FEAT_DIM)
        if CKPT_PATH.exists():
            state = torch.load(str(CKPT_PATH), map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            logger.info("GNN: loaded TGAT checkpoint from %s", CKPT_PATH)
        else:
            logger.warning(
                "GNN: %s not found — running with random weights. "
                "Train first with: python train_tgat.py", CKPT_PATH
            )
        model.eval()
        self._model = model
        return model

    def predict(
        self,
        kg_snapshot: Dict[str, Any],
        price_data: Optional[Dict[str, Any]] = None,
        trigger_event: str = "unknown",
    ) -> Any:
        """
        Run TGAT inference on a KG snapshot.

        Raises ValueError if the snapshot is empty.
        Falls back to heuristic scoring if TGAT cannot run.
        """
        nodes = kg_snapshot.get("nodes", [])
        if not nodes:
            raise ValueError("KG snapshot is empty — cannot run GNN inference.")

        # Try TGAT inference
        try:
            result = self._tgat_predict(kg_snapshot, price_data, trigger_event)
            if result is not None:
                return result
        except Exception as exc:
            logger.warning("GNN: TGAT inference failed (%s) — using heuristic fallback", exc)

        # Heuristic fallback
        return self._heuristic_predict(kg_snapshot, trigger_event)

    # ── TGAT inference ────────────────────────────────────────────────────────

    def _tgat_predict(
        self,
        snapshot: Dict[str, Any],
        price_data: Optional[Dict[str, Any]],
        trigger_event: str,
    ) -> Optional[Any]:
        from app.schemas.market_analysis_schemas import GNNInferenceResult, GNNPrediction

        tensors = self._adapter.build(snapshot, price_data)
        if tensors is None:
            return None

        model = self._load_model()

        x            = tensors["x"]
        src          = tensors["src"]
        dst          = tensors["dst"]
        t            = tensors["t"]
        impacts_mask = tensors["impacts_mask"]
        dir_signs    = tensors["edge_impact_dir"]
        confidences  = tensors["edge_confidence"]
        node_names   = tensors["node_names"]
        node_types   = tensors["node_types"]

        # Build temporal neighbour store from all edges (causal temporal context)
        nbr_store = TemporalNeighborStore()
        nbr_store.add_edges(src, dst, t)

        # Score IMPACTS edges
        imp_idx = impacts_mask.nonzero(as_tuple=True)[0]
        if imp_idx.numel() == 0:
            logger.info("GNN: no IMPACTS edges in snapshot — heuristic fallback")
            return None

        imp_src = src[imp_idx]
        imp_dst = dst[imp_idx]
        imp_t   = t[imp_idx]
        imp_dir = [dir_signs[i] for i in imp_idx.tolist()]
        imp_conf= [confidences[i] for i in imp_idx.tolist()]

        with torch.no_grad():
            z_src  = model.embed_nodes(imp_src, imp_t, x, nbr_store)
            z_dst  = model.embed_nodes(imp_dst, imp_t, x, nbr_store)
            logits = model.predict(z_src, z_dst)
            scores = torch.sigmoid(logits).cpu().numpy()   # [E_imp], ∈ [0, 1]

        logger.info(
            "GNN TGAT [%s]: %d nodes, %d impact edges, trigger='%s' | "
            "score μ=%.3f σ=%.3f",
            "trained" if self._trained else "random",
            len(node_names), imp_idx.numel(), trigger_event[:60],
            float(scores.mean()), float(scores.std()),
        )

        # ── Per-entity impact aggregation ─────────────────────────────────────
        # score ∈ [0,1] → signed_score ∈ [-1, 1] then map to [-1, 1] impact
        entity_scores: Dict[int, List[float]] = defaultdict(list)
        entity_conf:   Dict[int, List[float]] = defaultdict(list)

        for dst_i, score, sign, conf in zip(
            imp_dst.tolist(), scores.tolist(), imp_dir, imp_conf
        ):
            signed = (2 * score - 1) * sign    # map [0,1] → [-1,1], apply direction
            entity_scores[dst_i].append(signed)
            entity_conf[dst_i].append(conf)

        systemic_risk = float(np.clip(scores.mean() * 1.2, 0.0, 1.0))

        predictions = []
        for idx, (name, ntype) in enumerate(zip(node_names, node_types)):
            esc = entity_scores.get(idx, [])
            if not esc:
                continue
            conf_weights = entity_conf.get(idx, [1.0] * len(esc))
            w = np.array(conf_weights)
            impact = float(np.clip(np.average(esc, weights=w), -1.0, 1.0))
            mean_conf = float(np.mean(conf_weights))
            hop  = _compute_hops(snapshot, name, trigger_event)
            hidden = abs(impact) > 0.3 and hop > 1 and name != "Talan"

            from app.schemas.market_analysis_schemas import EntityType as ET
            etype_map = {
                "Company": ET.COMPANY, "Competitor": ET.COMPETITOR,
                "Sector": ET.SECTOR, "Geography": ET.COUNTRY,
                "MacroIndicator": ET.MACRO_INDICATOR, "Event": ET.EVENT,
                "Regulation": ET.REGULATION, "BusinessUnit": ET.COMPANY,
                "Client": ET.COMPANY, "Project": ET.COMPANY,
            }
            predictions.append(GNNPrediction(
                entity_name      = name,
                entity_type      = etype_map.get(ntype, ET.COMPANY),
                predicted_impact = round(impact, 4),
                confidence       = round(min(mean_conf, 1.0), 3),
                propagation_hops = hop,
                hidden_risk      = hidden,
            ))

        talan_pred  = next((p for p in predictions if p.entity_name == "Talan"), None)
        hidden_risks = sorted(
            [p for p in predictions if p.hidden_risk and p.predicted_impact < -0.2],
            key=lambda p: p.predicted_impact,
        )
        prop_paths = _extract_propagation_paths(
            snapshot, predictions,
            entity_title_map=snapshot.get("entity_title_map"),
            max_hops=4,   # synthetic 2-node chains: Entity→M1→M2→Exposure→Talan = 4 hops
        )

        logger.info(
            "GNN result: talan=%s systemic=%.3f predictions=%d hidden=%d paths=%d",
            f"{talan_pred.predicted_impact:+.3f}" if talan_pred else "N/A",
            systemic_risk, len(predictions), len(hidden_risks), len(prop_paths),
        )

        return GNNInferenceResult(
            run_at               = datetime.now(timezone.utc),
            trigger_event        = trigger_event,
            predictions          = predictions,
            talan_prediction     = talan_pred,
            systemic_risk_score  = round(systemic_risk, 4),
            top_hidden_risks     = hidden_risks[:5],
            propagation_paths    = prop_paths,
            inference_mode       = "tgat_trained" if self._trained else "tgat_random",
        )

    # ── Heuristic fallback ────────────────────────────────────────────────────

    def _heuristic_predict(
        self,
        snapshot: Dict[str, Any],
        trigger_event: str,
    ) -> Any:
        """Rule-based scoring used when TGAT cannot run (no edges, no torch…)."""
        from app.schemas.market_analysis_schemas import (
            GNNInferenceResult, GNNPrediction, EntityType as ET,
        )

        nodes = snapshot.get("nodes", [])
        edges = snapshot.get("edges", [])

        # Aggregate impact scores from edge metadata
        entity_impact: Dict[str, List[float]] = defaultdict(list)
        entity_conf:   Dict[str, List[float]] = defaultdict(list)
        name_map: Dict[str, str] = {
            n.get("id", n.get("name", "")): n.get("name", "?") for n in nodes
        }

        for edge in edges:
            to_name = name_map.get(str(edge.get("to", "")), "")
            if not to_name:
                continue
            score = float(edge.get("impact_score") or 0.0)
            direction = str(edge.get("impact_direction", "uncertain")).lower()
            signed = score if direction != "negative" else -abs(score)
            entity_impact[to_name].append(signed)
            entity_conf[to_name].append(float(edge.get("confidence") or 0.5))

        predictions = []
        for node in nodes:
            name = node.get("name", "?")
            raw_label = (node.get("labels") or ["Company"])[0]
            etype_map = {
                "Company": ET.COMPANY, "Competitor": ET.COMPETITOR,
                "Sector": ET.SECTOR, "Country": ET.COUNTRY,
                "MacroIndicator": ET.MACRO_INDICATOR, "Event": ET.EVENT,
                "Regulation": ET.REGULATION,
            }
            etype = etype_map.get(raw_label, ET.COMPANY)
            scores = entity_impact.get(name, [])
            if not scores:
                continue
            impact = float(np.clip(np.mean(scores), -1.0, 1.0))
            conf   = float(np.mean(entity_conf.get(name, [0.5])))
            hop    = _compute_hops(snapshot, name, trigger_event)
            hidden = abs(impact) > 0.3 and hop > 1 and name != "Talan"
            predictions.append(GNNPrediction(
                entity_name      = name,
                entity_type      = etype,
                predicted_impact = round(impact, 4),
                confidence       = round(conf, 3),
                propagation_hops = hop,
                hidden_risk      = hidden,
            ))

        all_scores = [abs(p.predicted_impact) for p in predictions]
        systemic   = float(np.clip(np.mean(all_scores) if all_scores else 0.3, 0.0, 1.0))
        talan_pred = next((p for p in predictions if p.entity_name == "Talan"), None)
        hidden_risks = sorted(
            [p for p in predictions if p.hidden_risk and p.predicted_impact < -0.2],
            key=lambda p: p.predicted_impact,
        )
        prop_paths = _extract_propagation_paths(
            snapshot, predictions,
            entity_title_map=snapshot.get("entity_title_map"),
            max_hops=5,
        )

        logger.info("GNN heuristic: predictions=%d hidden=%d paths=%d",
                    len(predictions), len(hidden_risks), len(prop_paths))

        return GNNInferenceResult(
            run_at              = datetime.utcnow(),
            trigger_event       = trigger_event,
            predictions         = predictions,
            talan_prediction    = talan_pred,
            systemic_risk_score = round(systemic, 4),
            top_hidden_risks    = hidden_risks[:5],
            propagation_paths   = prop_paths,
            inference_mode      = "heuristic",
        )

    # ── v3 inference (post-processing of TGAT/heuristic output) ───────────────

    def predict_v3(
        self,
        kg_snapshot: Dict[str, Any],
        price_data: Optional[Dict[str, Any]] = None,
        trigger_event: str = "unknown",
        *,
        edge_policy=None,
        path_ranker=None,
        explanation_generator=None,
        top_k_paths: int = 10,
    ) -> Any:
        """Run TGAT/heuristic prediction, then apply v3 ranking + filtering.

        This is a non-invasive wrapper: the underlying TGAT inference is the
        same as ``predict()``. After the raw ``GNNInferenceResult`` is
        produced, we:

          1. gate edges by EdgeTypePolicy (drops α=0 paths),
          2. score every PropagationPath through the PathRanker
             (W(p) = T̂·ρ·τ̄·spec·coh·conf̄, §3(h)),
          3. filter paths via §3(j) thresholds,
          4. attach a structured PropagationExplanation per kept path,
          5. populate the new schema fields on PropagationPath.

        Edge gating is also applied to the snapshot view that the path
        ranker sees, so blocked relations cannot resurface in `_filter`.
        """
        # 1. Apply edge gating to the snapshot's edges in-place — this means
        # the heuristic / TGAT path extractors no longer see α=0 edges.
        if edge_policy is not None:
            self._annotate_edge_labels(kg_snapshot)
            kg_snapshot["edges"] = edge_policy.gate_edges(kg_snapshot.get("edges") or [])

        result = self.predict(kg_snapshot, price_data, trigger_event)
        if path_ranker is None or not getattr(result, "propagation_paths", None):
            return result

        # 2-3. Score + rank + filter paths
        path_dicts = []
        for p in result.propagation_paths:
            path_dict = p.model_dump() if hasattr(p, "model_dump") else p.dict()
            self._annotate_step_edges(path_dict, kg_snapshot)
            path_dicts.append(path_dict)

        kept, rejected = path_ranker.rank(path_dicts, top_k=top_k_paths)

        # 4-5. Rebuild PropagationPath objects with v3 fields populated
        from app.schemas.market_analysis_schemas import (
            PropagationExplanation, PropagationPath, PropagationStep,
        )

        new_paths: List[PropagationPath] = []
        for s in kept:
            steps = [
                PropagationStep(
                    node_name=step.get("node_name", ""),
                    node_type=step.get("node_type", ""),
                    relation_type=step.get("relation_type", ""),
                    reason=step.get("reason", ""),
                    impact_score=float(step.get("impact_score") or 0.0),
                    time_horizon=step.get("time_horizon") or "short_term",
                    relation_strength=float(step.get("relation_strength") or 0.5),
                    business_relevance=float(step.get("business_relevance") or s.plausibility),
                    freshness_score=float(step.get("freshness_score") or s.path_freshness),
                    edge_confidence=float(step.get("edge_confidence") or step.get("confidence") or s.avg_edge_confidence),
                    is_generic_hub_step=bool(step.get("is_generic_hub_step", False)),
                )
                for step in (s.path.get("steps") or [])
            ]
            explanation = None
            if explanation_generator is not None:
                draft = explanation_generator.explain(s)
                explanation = PropagationExplanation(**draft.as_dict())

            new_paths.append(PropagationPath(
                source_name=s.path.get("source_name", ""),
                source_type=s.path.get("source_type", ""),
                steps=steps,
                chain_score=float(s.path.get("chain_score") or 0.0),
                chain_conf=float(s.path.get("chain_conf") or 0.0),
                hops=int(s.path.get("hops") or len(steps)),
                time_horizon_label=s.path.get("time_horizon_label", ""),
                narrative=s.path.get("narrative", ""),
                event_title=s.path.get("event_title", ""),
                key_impact=s.path.get("key_impact", ""),
                source_evidence=s.path.get("source_evidence", ""),
                business_plausibility=s.plausibility,
                causal_coherence=s.causal_coherence,
                path_specificity=s.path_specificity,
                weighted_score=s.weighted_score,
                impact_probability=s.impact_probability,
                estimated_business_impact_pct=s.estimated_business_impact_pct,
                confidence=s.confidence,
                uncertainty=s.uncertainty,
                explanation=explanation,
            ))

        result.propagation_paths    = new_paths
        result.filtered_path_count  = len(new_paths)
        result.rejected_path_count  = len(rejected)
        result.calibration_method   = "isotonic" if path_ranker.calib.is_fitted else "none"

        logger.info(
            "GNN v3 ranking: kept=%d rejected=%d (top_k=%d)",
            len(new_paths), len(rejected), top_k_paths,
        )
        return result

    # ── v3 helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _annotate_edge_labels(snapshot: Dict[str, Any]) -> None:
        """Stamp src_label / dst_label on each edge so EdgeTypePolicy can look
        them up. Idempotent."""
        nodes = snapshot.get("nodes") or []
        label_by_id: Dict[str, str] = {}
        for n in nodes:
            labels = n.get("labels") or []
            label_by_id[str(n.get("id"))] = labels[0] if labels else "Unknown"
        for e in snapshot.get("edges") or []:
            e.setdefault("src_label", label_by_id.get(str(e.get("from")), "Unknown"))
            e.setdefault("dst_label", label_by_id.get(str(e.get("to")), "Unknown"))

    @staticmethod
    def _annotate_step_edges(path_dict: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
        """Decorate each step with relation_strength / freshness_score / etc.
        Looked up from the snapshot edges by (relation_type, node_name)."""
        edges = snapshot.get("edges") or []
        # index edges by (type, dst-name)
        nodes_by_id = {str(n.get("id")): n for n in (snapshot.get("nodes") or [])}
        edge_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for e in edges:
            dst_name = (nodes_by_id.get(str(e.get("to")), {}) or {}).get("name", "")
            edge_index[(e.get("type") or "", dst_name)] = e

        for step in path_dict.get("steps") or []:
            key = (step.get("relation_type") or "", step.get("node_name") or "")
            edge = edge_index.get(key)
            if not edge:
                continue
            step.setdefault("relation_strength", edge.get("relation_strength"))
            step.setdefault("freshness_score",   edge.get("freshness_score"))
            step.setdefault("edge_confidence",   edge.get("confidence"))
            step.setdefault("evidence_quality",  edge.get("evidence_quality"))
            step.setdefault("category",          edge.get("category"))
            step.setdefault("half_life_days",    edge.get("half_life_days"))
            step.setdefault("src_label",         edge.get("src_label"))
            step.setdefault("dst_label",         edge.get("dst_label"))


# ── Helper ─────────────────────────────────────────────────────────────────────

def _compute_hops(snapshot: Dict, target_name: str, source_name: str) -> int:
    """BFS hop count from source to target in the snapshot graph."""
    edges  = snapshot.get("edges", [])
    nodes  = snapshot.get("nodes", [])
    id_map = {n["name"]: n["id"] for n in nodes if "id" in n and "name" in n}

    src_id = id_map.get(source_name)
    dst_id = id_map.get(target_name)
    if src_id is None or dst_id is None:
        return 1

    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(str(e.get("from", "")), []).append(str(e.get("to", "")))

    visited: set = {src_id}
    queue: deque = deque([(src_id, 0)])
    while queue:
        cur, hops = queue.popleft()
        if cur == dst_id:
            return hops
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, hops + 1))
    return 3


# ── Propagation path extraction ────────────────────────────────────────────────

_HORIZON_ORDER  = {"immediate": 0, "short_term": 1, "medium_term": 2, "long_term": 3}
_HORIZON_LABELS = {
    "immediate":   "1-2 semaines",
    "short_term":  "2-4 semaines",
    "medium_term": "1-3 mois",
    "long_term":   "3-6 mois",
}
_SOURCE_PRIORITY_LABELS = {
    "Event", "News", "Competitor", "Regulation", "MacroIndicator",
}
# Types that are valid intermediate BFS steps but NOT valid sources.
# Technology (GPU, iOS, ChatGPT…), Person (Reid Hoffman…), Sector, Country, MarketTrend
# get added to the KG as entities mentioned in articles — they are nodes that
# appear in causal chains but they are NOT the events that drive the chain.
_SOURCE_NEVER_LABELS = {
    "Technology", "Person", "Sector", "MarketTrend", "Country",
}


def _horizon_label(horizons: List[str]) -> str:
    if not horizons:
        return "1-3 mois"
    worst = max(horizons, key=lambda h: _HORIZON_ORDER.get(h, 1))
    return _HORIZON_LABELS.get(worst, "1-3 mois")


def _build_narrative(source_name: str, steps: List[Any], chain_score: float) -> str:
    """Director-readable French summary, ~3 lines, no jargon.

    Structure:
      1. Headline: nature + force + sens du signal
      2. Chaîne de transmission (entités intermédiaires, sans Talan)
      3. Raisons concrètes (les `reason` non-génériques des étapes)
    """
    is_negative = chain_score < 0
    abs_score   = abs(chain_score)
    if abs_score > 0.5:
        intensity, lead = ("fort", "🔴" if is_negative else "🟢")
    elif abs_score > 0.25:
        intensity, lead = ("modéré", "🟠" if is_negative else "🟢")
    else:
        intensity, lead = ("faible", "🟡")
    nature = "menace" if is_negative else "opportunité"

    # Build the transmission chain — drop the source and Talan for readability
    mids = [s.node_name for s in steps[1:] if s.node_name and s.node_name.lower() != "talan"]
    chain_desc = " → ".join(mids) if mids else "impact direct"

    # Aggregate the concrete reasons (skip auto-generated fallbacks)
    reasons = [
        s.reason for s in steps
        if s.reason and s.reason.strip() and not s.reason.startswith("Propagation via")
    ]
    rationale = " ".join(reasons)[:400]

    parts = [
        f"{lead} **{source_name}** constitue une {nature} d'intensité {intensity} pour Talan.",
        f"**Chaîne de transmission** : {chain_desc} → Talan.",
    ]
    if rationale:
        parts.append(f"**Mécanisme** : {rationale}")
    return "\n\n".join(parts)


def _extract_propagation_paths(
    snapshot: Dict[str, Any],
    predictions: List[Any],
    max_paths: int = 30,
    max_hops: int = 4,
    entity_title_map: Optional[Dict[str, str]] = None,
) -> List[Any]:
    """
    BFS from each high-impact source node to Talan, reconstructing the full
    causal edge chain.  Returns up to max_paths PropagationPath objects,
    sorted by absolute chain_score descending.
    """
    from app.schemas.market_analysis_schemas import PropagationPath, PropagationStep

    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])
    if not nodes or not edges:
        return []

    # ── Build lookup tables ──────────────────────────────────────────────────
    node_by_id:   Dict[str, Dict] = {}
    node_by_name: Dict[str, Dict] = {}
    for n in nodes:
        nid = str(n.get("id", n.get("name", "")))
        node_by_id[nid] = n
        node_by_name[n.get("name", "")] = n

    talan_node = node_by_name.get("Talan")
    if not talan_node:
        return []
    talan_id = str(talan_node.get("id", talan_node.get("name", "Talan")))

    # Forward adjacency: from_id → [(to_id, edge_dict), …]
    adj: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
    # Reverse adjacency: to_id → [(from_id, edge_dict), …]  — used to find News triggers
    rev_adj: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
    for edge in edges:
        src_id = str(edge.get("from", ""))
        dst_id = str(edge.get("to",   ""))
        if src_id and dst_id and src_id != dst_id:
            adj[src_id].append((dst_id, edge))
            rev_adj[dst_id].append((src_id, edge))

    def _find_news_trigger(entity_id: str) -> Optional[Dict]:
        """Return the first News node that directly points to entity_id."""
        for pred_id, _ in rev_adj.get(entity_id, []):
            pred_node = node_by_id.get(pred_id, {})
            if "News" in (pred_node.get("labels") or []):
                return pred_node
        return None

    # ── BFS: find all directed paths from start_id to Talan (≤ max_hops) ────
    def bfs_to_talan(start_id: str) -> List[List[Tuple[str, str, Dict]]]:
        if start_id == talan_id:
            return []
        found: List[List[Tuple[str, str, Dict]]] = []
        queue: deque = deque([(start_id, [], {start_id})])
        while queue:
            cur_id, path_edges, visited = queue.popleft()
            if len(path_edges) >= max_hops:
                continue
            for next_id, edge in adj.get(cur_id, []):
                if next_id in visited:
                    continue
                new_path = path_edges + [(cur_id, next_id, edge)]
                if next_id == talan_id:
                    found.append(new_path)
                else:
                    queue.append((next_id, new_path, visited | {next_id}))
        return found

    # ── Candidate source nodes ───────────────────────────────────────────────
    # News nodes first (they carry article titles → comprehensible events),
    # then other priority types (Event, Competitor, Regulation, MacroIndicator).
    pred_by_name = {p.entity_name: p for p in predictions}

    # Import blacklist from schemas — generic entities like "Europe", "Investors"
    # never make meaningful propagation sources.
    from app.schemas.market_analysis_schemas import _is_blacklisted_entity

    news_ids:   List[str] = []
    entity_ids: List[str] = []
    for nid, node in node_by_id.items():
        if nid == talan_id:
            continue
        labels = node.get("labels") or ["Company"]
        label  = labels[0]
        name   = node.get("name", "")
        props  = node.get("properties") or {}
        pred   = pred_by_name.get(name)

        # Drop blacklisted generic entities ("Europe", "Investors", "Technology", …)
        # even if they're already in the KG from older ingestion runs.
        if _is_blacklisted_entity(name):
            continue

        # Exclude pure Talan exposure endpoints — they're valid path targets but
        # not informative trigger sources (TALAN_EXPOSURE nodes have no upstream event).
        if props.get("synthetic") and props.get("exposure_weight") is not None:
            continue
        # Exclude intermediate synthetic mechanism nodes — they're path steps, not sources.
        if props.get("synthetic") and props.get("description", "").startswith("Economic mechanism:"):
            continue

        if "News" in labels:
            news_ids.append(nid)
        elif label in _SOURCE_NEVER_LABELS:
            # Technology/Person/Sector/Country/MarketTrend are path intermediates, never sources.
            continue
        elif label in _SOURCE_PRIORITY_LABELS:
            # Real market events: Event, Competitor, Regulation, MacroIndicator.
            entity_ids.append(nid)
        elif pred and abs(pred.predicted_impact) > 0.30:
            # Company nodes only if GNN predicts a strong direct impact on Talan
            # (threshold raised from 0.15 to avoid pulling in generic brand mentions).
            entity_ids.append(nid)

    # News nodes processed first so they fill seen_names before entity duplicates
    candidate_ids = news_ids + entity_ids

    # ── Edge semantic weights (§2 — stronger than raw impact_score) ─────────
    from app.services.market_analysis.synthetic_enricher import EDGE_SEMANTIC_WEIGHTS
    from app.services.market_analysis.policy.edge_type_policy import (
        TIER1_RELATIONS, TIER2_RELATIONS,
    )

    def _rel_of(edge: Dict) -> str:
        return str(edge.get("type") or edge.get("relation_type") or "")

    def _edge_weight(edge: Dict) -> float:
        """Per-edge propagation weight ∈ [0, 1].

        Semantics:
          - Tier-2 (MENTIONS, CORRELATED_WITH, …) → 0   (hard-gated)
          - Unknown relation type                  → 0   (fail closed)
          - Otherwise: semantic_weight × |impact| × freshness_decay × confidence

        No magnitude floor: an edge with impact_score=0 means "unknown",
        not "small", so it contributes 0 and the geometric-mean chain score
        will reject the path. This is the correct behavior for causal
        propagation (a missing transmission coefficient breaks the chain).
        """
        rel_type = _rel_of(edge)
        if not rel_type or rel_type in TIER2_RELATIONS:
            return 0.0

        sem_w = EDGE_SEMANTIC_WEIGHTS.get(rel_type, 0.0)
        if sem_w <= 0.0:
            return 0.0

        raw = float(edge.get("impact_score") or 0.0)
        magnitude = abs(raw)
        if magnitude == 0.0:
            # only after passing tier check: give known causal edges with
            # missing magnitude a minimal-but-nonzero weight so they can
            # still chain (the geometric mean will dampen them anyway)
            magnitude = 0.15

        # Temporal decay from the CORRECT field (freshness_score, not
        # relation_strength which is the α from EdgeTypePolicy).
        hl_days   = float(edge.get("half_life_days") or 30.0)
        freshness = float(edge.get("freshness_score") or 0.5)
        days_old  = max(0.0, (1.0 - freshness) * hl_days)
        t_decay   = math.exp(-math.log(2) / max(hl_days, 1.0) * days_old)

        conf = float(edge.get("confidence") or 0.5)
        w = sem_w * magnitude * t_decay * conf
        return max(0.0, min(1.0, w))

    def _chain_score(path_edges: List) -> float:
        """Geometric-mean chain score with tier gating.

        Propagation is multiplicative: a chain is only as strong as the
        product of its transmission coefficients. One weak hop should
        meaningfully drag the score down (financial contagion, supply
        shock, regulatory cascade all behave this way).

        Hard gates (return 0):
          - any Tier-2 edge in the path (semantic-only contamination)
          - path is purely Tier-1 (structural with no causal mechanism)
          - any edge has weight 0 (unknown / blocked relation)

        Sign comes from the LAST hop into Talan — that's the
        operationally meaningful direction (final cause).
        """
        if not path_edges:
            return 0.0

        # Gate 0: require multi-hop causal propagation (Event → Mech → Sector → … → Talan).
        # Direct or 2-hop shortcuts (Event → Talan, Event → Sector → Talan) are rejected:
        # propagation must traverse at least one intermediate economic mechanism to be
        # considered a real causal chain. The SyntheticEnricher guarantees a 4-hop chain
        # for matched entities (Entity → Mech1 → Mech2 → Exposure → Talan).
        if len(path_edges) < 3:
            return 0.0

        rels = [_rel_of(e) for _, _, e in path_edges]
        # Gate 1: tier-2 contamination kills the path
        if any(r in TIER2_RELATIONS for r in rels):
            return 0.0
        # Gate 2: pure structural path with no causal edge
        if all(r in TIER1_RELATIONS for r in rels):
            return 0.0

        weights = [_edge_weight(e) for _, _, e in path_edges]
        # Gate 3: any zero weight kills the chain (broken transmission)
        if any(w <= 0.0 for w in weights):
            return 0.0

        # Geometric mean — multiplicative aggregation
        log_sum = sum(math.log(max(w, 1e-9)) for w in weights)
        geom    = math.exp(log_sum / len(weights))

        # Sign: use the last CAUSAL edge (skip structural DEPENDS_ON/DRIVES at the end).
        # The synthetic enricher appends a DEPENDS_ON edge (exposure→Talan) with
        # positive impact_score regardless of chain direction. Using that edge's sign
        # would always produce positive chains even for threat paths.
        _STRUCTURAL_SIGN_SKIP = frozenset({"DEPENDS_ON", "BELONGS_TO_SECTOR", "OPERATES_IN",
                                            "SERVES_SECTOR", "PART_OF"})
        # Walk backwards to find the first non-structural edge
        sign_edge = path_edges[-1][2]
        for _, _, e in reversed(path_edges):
            if _rel_of(e) not in _STRUCTURAL_SIGN_SKIP:
                sign_edge = e
                break

        sign_raw = float(sign_edge.get("impact_score") or 0.0)
        sign_neg = (str(sign_edge.get("impact_direction", "")).lower() == "negative"
                    or sign_raw < 0)
        sign = -1.0 if sign_neg else 1.0

        return float(max(-1.0, min(1.0, sign * geom)))

    # ── Collect all paths ────────────────────────────────────────────────────
    seen_path_keys: set = set()
    scored: List[Tuple[float, float, str, str, List]] = []

    for src_id in candidate_ids:
        paths = bfs_to_talan(src_id)
        for path_edges in paths:
            chain_score = _chain_score(path_edges)
            # Skip paths that fail tier gating (chain_score=0 from gate)
            if abs(chain_score) < 1e-6:
                continue
            chain_conf  = float(np.mean([float(e.get("confidence") or 0.5)
                                         for _, _, e in path_edges]))
            src_node = node_by_id.get(src_id, {})
            src_name = src_node.get("name", src_id)
            # Dedup key: source name + ordered intermediate node IDs
            mid_ids = tuple(to_id for _, to_id, _ in path_edges[:-1])
            path_key = (src_name, mid_ids)
            if path_key in seen_path_keys:
                continue
            seen_path_keys.add(path_key)
            scored.append((chain_score, chain_conf, src_id, src_name, path_edges))

    if not scored:
        return []

    # ── Cap paths per identical intermediate chain (FIRST) ───────────────────
    # Many distinct entities (GPU, ChatGPT, iOS, …) match the same template and
    # therefore share the same Mech1 → Mech2 → Exposure intermediate. Without a
    # cap, 17+ paths would have the identical visible chain (only the source
    # entity differs), making the UI look repetitive. We diversify BEFORE the
    # pos/neg quota so that minority chains are not eliminated by the top-N
    # sort on |score| (which would otherwise pack the result with one dominant
    # chain because all its sources happen to score high).
    MAX_PER_CHAIN = 1  # 1 source per intermediate chain — eliminates duplicate GPU/ChatGPT/iOS paths
    chain_counter: Dict[Tuple, int] = {}
    # Sort once by |score| so the strongest path per chain is kept first
    scored.sort(key=lambda x: abs(x[0]), reverse=True)
    diversified: List[Tuple[float, float, str, str, List]] = []
    for s in scored:
        _, _, _, _, path_edges = s
        intermediate_sig = tuple(to_id for _, to_id, _ in path_edges[:-1])
        count = chain_counter.get(intermediate_sig, 0)
        if count < MAX_PER_CHAIN:
            diversified.append(s)
            chain_counter[intermediate_sig] = count + 1
    scored = diversified

    # ── Diversity-aware selection: guarantee ≥ 1/3 negative paths ───────────
    # Applied after chain-diversification so minority chains can still surface.
    positives = sorted([s for s in scored if s[0] >= 0], key=lambda x: abs(x[0]), reverse=True)
    negatives = sorted([s for s in scored if s[0] <  0], key=lambda x: abs(x[0]), reverse=True)
    neg_quota = min(len(negatives), max(max_paths // 3, 1))
    pos_quota = min(len(positives), max_paths - neg_quota)
    pos_quota = min(len(positives), max_paths - min(neg_quota, len(negatives)))
    selected = positives[:pos_quota] + negatives[:neg_quota]
    selected.sort(key=lambda x: abs(x[0]), reverse=True)
    scored = selected

    # ── Build PropagationPath objects ─────────────────────────────────────────
    result: List[Any] = []
    for chain_score, chain_conf, src_id, src_name, path_edges in scored[:max_paths]:
        src_node  = node_by_id.get(src_id, {})
        src_label = (src_node.get("labels") or ["Company"])[0]
        src_props = src_node.get("properties", {})

        steps: List[PropagationStep] = []
        for from_id, to_id, edge in path_edges:
            from_node  = node_by_id.get(from_id, {})
            from_name  = from_node.get("name", from_id)
            from_label = (from_node.get("labels") or ["Company"])[0]
            from_type  = _LABEL_MAP.get(from_label, "Company")

            to_name = node_by_id.get(to_id, {}).get("name", to_id)
            reason  = (edge.get("reason") or edge.get("evidence") or
                       f"Propagation via {edge.get('type', 'CAUSES_IMPACT_ON')} vers {to_name}")
            th      = edge.get("time_horizon") or "short_term"
            rel     = str(edge.get("type", "CAUSES_IMPACT_ON"))

            steps.append(PropagationStep(
                node_name     = from_name,
                node_type     = from_type,
                relation_type = rel,
                reason        = reason,
                impact_score  = round(_edge_weight(edge), 3),
                time_horizon  = th,
            ))

        # Event title — priority order:
        #  1. News node: use stored article title directly
        #  2. Entity: best incoming-edge reason (what caused this entity to matter)
        #  3. Entity: linked News node title (reverse lookup)
        #  4. Entity: description from KG properties
        #  5. Last resort: entity name
        src_labels = src_node.get("labels") or []

        def _best_incoming_reason(node_id: str) -> str:
            """Pick the most informative reason from edges pointing TO this node."""
            candidates = []
            for pred_id, edge in rev_adj.get(node_id, []):
                r = edge.get("reason") or edge.get("evidence") or ""
                # Skip generic auto-generated fallback reasons
                if r and not r.startswith("Propagation via"):
                    candidates.append(r)
            return max(candidates, key=len) if candidates else ""

        # entity_title_map from orchestrator: entity_name → article headline
        _etm = entity_title_map or snapshot.get("entity_title_map") or {}

        _type_fr = {
            "Company": "Entreprise", "Competitor": "Concurrent",
            "MacroIndicator": "Indicateur macro", "Event": "Événement",
            "Regulation": "Réglementation", "Sector": "Secteur",
            "Country": "Pays", "News": "Article",
        }
        _impact_fr = (
            "risque critique" if chain_score < -0.5 else
            "menace significative" if chain_score < -0.2 else
            "signal positif" if chain_score > 0.2 else "signal neutre"
        )

        def _contextual_title() -> str:
            """Build a descriptive title when no article text is available."""
            intermediates = [s.node_name for s in steps[1:] if s.node_name != "Talan"]
            via = " → ".join(intermediates) if intermediates else ""
            type_label = _type_fr.get(src_label, src_label)
            if via:
                return f"{src_name} ({type_label}) — {_impact_fr} via {via} → Talan"
            return f"{src_name} ({type_label}) — {_impact_fr} sur Talan"

        if "News" in src_labels:
            event_title = (src_props.get("title") or src_name)[:160]
        elif src_name in _etm:
            event_title = _etm[src_name][:160]
        else:
            incoming_reason = _best_incoming_reason(src_id)
            if incoming_reason:
                event_title = incoming_reason[:160]
            else:
                news_trigger = _find_news_trigger(src_id)
                if news_trigger:
                    news_props = news_trigger.get("properties", {})
                    news_title = news_props.get("title") or _etm.get(src_name) or ""
                    event_title = (news_title[:160] if news_title
                                   else _contextual_title())
                else:
                    node_desc = src_props.get("description") or ""
                    event_title = (node_desc[:120] if node_desc
                                   else _contextual_title())

        # Key impact: the step with the most negative score
        key_step = min(steps, key=lambda s: s.impact_score) if steps else None
        key_impact = key_step.reason[:200] if key_step else ""

        # Source evidence: URL if News node, else best edge evidence/reason
        source_evidence = ""
        if "News" in src_labels:
            source_evidence = (src_props.get("external_id") or
                               src_props.get("url") or "")
        if not source_evidence:
            news_trigger = _find_news_trigger(src_id)
            if news_trigger:
                nt_props = news_trigger.get("properties", {})
                source_evidence = (nt_props.get("external_id") or
                                   nt_props.get("url") or "")
        if not source_evidence:
            # Use the best incoming-edge evidence as article excerpt
            for pred_id, edge in rev_adj.get(src_id, []):
                ev = edge.get("evidence") or ""
                if ev and not ev.startswith("Propagation via"):
                    source_evidence = ev[:300]
                    break
        if not source_evidence:
            # Last fallback: first edge in the chain
            for _, _, edge in path_edges:
                ev = edge.get("evidence") or ""
                if ev:
                    source_evidence = ev[:300]
                    break

        result.append(PropagationPath(
            source_name        = src_name,
            source_type        = _LABEL_MAP.get(src_label, "Company"),
            steps              = steps,
            chain_score        = round(chain_score, 4),
            chain_conf         = round(chain_conf, 3),
            hops               = len(path_edges),
            time_horizon_label = _horizon_label([s.time_horizon for s in steps]),
            narrative          = _build_narrative(src_name, steps, chain_score),
            event_title        = event_title,
            key_impact         = key_impact,
            source_evidence    = source_evidence,
        ))

    return result
