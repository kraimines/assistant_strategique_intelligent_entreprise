"""
generate_synthetic_dataset.py
==============================
Generates a large realistic synthetic GNN dataset for Talan's market analysis.

Design:
  - Entity knowledge base (companies, sectors, macros) mirrors the real generator's
    ENTITY_KEYWORD_RULES + TICKER_TO_COMPANY — no new hardcoding
  - Events generated via Poisson arrival times + category templates (algorithmic)
  - Edges derived from sector-alignment probability rules (not random noise)
  - Features: node-type Gaussian prototypes + small perturbation per node
  - Causal labels: simulated abnormal returns + explicit-mention flag
  - Output format: identical to RealWorldDatasetPipeline + causal patches

Output written to:  gnn_causal_dataset/
  nodes.csv, edges.csv, node_features.npy, metadata.json
  edge_labels.csv, causal_map.json, snapshots/<period>.npz

Run:
    cd backend/app/services/market_analysis
    python generate_synthetic_dataset.py
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("synth")

HERE = Path(__file__).parent.resolve()
OUT  = HERE / "gnn_causal_dataset"

# ─────────────────────────────────────────────────────────────────────────────
# § 1  SCHEMA CONSTANTS  (must stay in sync with Gnn_realworld_dataset_generator.py)
# ─────────────────────────────────────────────────────────────────────────────

SEED        = 42
N_EVENTS    = 5_000
FEATURE_DIM = 396      # 10 (type one-hot) + 2 (degree/risk) + 384 (embedding)

START = datetime(2021, 1, 1, tzinfo=timezone.utc)
END   = datetime(2024, 12, 31, tzinfo=timezone.utc)
TOTAL_DAYS = (END - START).days

GNN_NODE_TYPES = [
    "Company", "BusinessUnit", "Sector", "Geography",
    "Client", "Project", "Competitor", "Regulation",
    "MacroIndicator", "Event",
]
GNN_EDGE_TYPES = [
    "AFFECTS", "BELONGS_TO_SECTOR", "COMPETES_WITH",
    "DELIVERED_FOR", "IMPACTS", "INFLUENCES",
    "OPERATES_IN", "SERVES", "SUPPLY_CHAIN_LINK",
]
TYPE_IDX = {t: i for i, t in enumerate(GNN_NODE_TYPES)}

# ─────────────────────────────────────────────────────────────────────────────
# § 2  ENTITY KNOWLEDGE BASE
#       Derived from ENTITY_KEYWORD_RULES + TICKER_TO_COMPANY in the real generator.
#       These are schema constants — not event data.
# ─────────────────────────────────────────────────────────────────────────────

COMPANIES = [
    # IT consulting (Talan's direct peers)
    "Talan", "Capgemini", "Atos", "Sopra Steria", "IBM Consulting", "Accenture",
    # Big Tech / Cloud / AI
    "Apple", "Microsoft", "Amazon", "Alphabet", "Meta", "NVIDIA", "Tesla",
    # Semiconductors
    "Samsung", "TSMC", "Intel", "AMD", "Qualcomm", "ASML",
    # ERP / Enterprise software
    "SAP", "Dassault Systèmes",
    # Banking & Finance
    "JPMorgan", "Goldman Sachs", "BNP Paribas", "Société Générale",
    "Crédit Agricole", "AXA",
    # Luxury / Retail
    "LVMH",
    # Energy
    "TotalEnergies", "EDF", "ENGIE",
    # Telecom
    "Orange",
    # Aerospace / Defense / Industry
    "Airbus", "Thales", "Renault", "Stellantis", "Alstom", "Siemens", "Volkswagen",
    # Healthcare / Pharma
    "Sanofi", "AstraZeneca", "Pfizer", "Novartis",
]

SECTORS = [
    "IT Services", "Semiconductors", "Financial Services", "Banking & Finance",
    "Energy & Utilities", "Healthcare & Life Sciences", "Retail & Consumer Goods",
    "Telecommunications", "Transportation & Logistics", "Industry & Manufacturing",
    "Real Estate & Construction", "Defense & Aerospace", "Media & Entertainment",
]

MACROS = [
    "ECB Interest Rates", "Federal Reserve Rate", "Bank of England Rate",
    "Eurozone Inflation", "Brent Crude Oil Price", "EUR/USD Exchange Rate",
    "CAC 40 Index", "IT Sector Growth", "France Unemployment Rate",
    "AI Market Growth Index", "Cybersecurity Spending Index", "Cloud Adoption Rate",
]

GEOGRAPHIES = [
    "France", "Germany", "United States", "United Kingdom",
    "European Union", "China", "Japan", "Netherlands", "South Korea", "Global",
]

# Which companies belong to which sector (drives BELONGS_TO_SECTOR + IMPACTS routing)
SECTOR_MEMBERSHIP: Dict[str, List[str]] = {
    "IT Services":               ["Talan", "Capgemini", "Atos", "Sopra Steria",
                                  "IBM Consulting", "Accenture", "SAP", "Dassault Systèmes"],
    "Semiconductors":            ["NVIDIA", "Intel", "AMD", "Qualcomm", "ASML",
                                  "TSMC", "Samsung"],
    "Financial Services":        ["JPMorgan", "Goldman Sachs", "AXA"],
    "Banking & Finance":         ["BNP Paribas", "Société Générale", "Crédit Agricole"],
    "Energy & Utilities":        ["TotalEnergies", "EDF", "ENGIE"],
    "Healthcare & Life Sciences":["Sanofi", "AstraZeneca", "Pfizer", "Novartis"],
    "Telecommunications":        ["Orange"],
    "Transportation & Logistics":["Airbus", "Renault", "Stellantis", "Alstom"],
    "Industry & Manufacturing":  ["Siemens", "Volkswagen"],
    "Defense & Aerospace":       ["Thales", "Airbus"],
    "Retail & Consumer Goods":   ["LVMH", "Apple", "Amazon", "Tesla"],
    "Media & Entertainment":     ["Alphabet", "Meta", "Microsoft"],
}

# Event category → sectors most likely to be impacted (drives IMPACTS edge routing)
CATEGORIES: List[str] = [
    "MacroIndicator", "AI Market Growth Index", "Cybersecurity Spending Index",
    "Company", "Semiconductors", "Energy & Utilities",
    "Healthcare & Life Sciences", "Banking & Finance",
]

CATEGORY_SECTORS: Dict[str, List[str]] = {
    "MacroIndicator":               ["Financial Services", "Banking & Finance", "IT Services"],
    "AI Market Growth Index":       ["IT Services", "Semiconductors", "Media & Entertainment"],
    "Cybersecurity Spending Index": ["IT Services", "Defense & Aerospace", "Telecommunications"],
    "Company":                      ["IT Services", "Financial Services", "Industry & Manufacturing"],
    "Semiconductors":               ["Semiconductors", "IT Services", "Industry & Manufacturing"],
    "Energy & Utilities":           ["Energy & Utilities", "Transportation & Logistics"],
    "Healthcare & Life Sciences":   ["Healthcare & Life Sciences"],
    "Banking & Finance":            ["Banking & Finance", "Financial Services"],
}

# Macro indicators that each event category tends to influence
CATEGORY_MACROS: Dict[str, List[str]] = {
    "MacroIndicator":               ["ECB Interest Rates", "Eurozone Inflation", "CAC 40 Index"],
    "AI Market Growth Index":       ["AI Market Growth Index", "IT Sector Growth"],
    "Cybersecurity Spending Index": ["Cybersecurity Spending Index"],
    "Company":                      ["CAC 40 Index", "EUR/USD Exchange Rate"],
    "Semiconductors":               ["IT Sector Growth", "CAC 40 Index"],
    "Energy & Utilities":           ["Brent Crude Oil Price", "Eurozone Inflation"],
    "Healthcare & Life Sciences":   ["France Unemployment Rate"],
    "Banking & Finance":            ["ECB Interest Rates", "EUR/USD Exchange Rate"],
}

# ─────────────────────────────────────────────────────────────────────────────
# § 3  DATA STRUCTURES  (identical to the real generator)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GNNNode:
    gnn_id:       int
    gnn_type:     str
    name:         str
    slug:         str
    props:        Dict[str, Any] = field(default_factory=dict)
    degree:       int   = 0
    impact_score: float = 0.0
    source:       str   = "synthetic"


@dataclass
class GNNEdge:
    source_id:    int
    target_id:    int
    gnn_type:     str
    weight:       float = 1.0
    timestamp:    Optional[str] = None
    source_system: str = "synthetic"


def slugify(text: str) -> str:
    import re, unicodedata
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "_", text).strip("_")


# ─────────────────────────────────────────────────────────────────────────────
# § 4  NODE GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def build_static_nodes(rng: np.random.Generator):
    nodes:       List[GNNNode] = []
    sector_idx:  Dict[str, int] = {}
    company_idx: Dict[str, int] = {}
    macro_idx:   Dict[str, int] = {}
    nid = 0

    for name in COMPANIES:
        n = GNNNode(nid, "Company", name, slugify(name),
                    impact_score=float(rng.uniform(0.2, 0.8)))
        nodes.append(n); company_idx[name] = nid; nid += 1

    for name in SECTORS:
        n = GNNNode(nid, "Sector", name, slugify(name),
                    impact_score=float(rng.uniform(0.4, 0.9)))
        nodes.append(n); sector_idx[name] = nid; nid += 1

    for name in MACROS:
        n = GNNNode(nid, "MacroIndicator", name, slugify(name),
                    impact_score=float(rng.uniform(0.5, 1.0)))
        nodes.append(n); macro_idx[name] = nid; nid += 1

    for name in GEOGRAPHIES:
        n = GNNNode(nid, "Geography", name, slugify(name))
        nodes.append(n); nid += 1

    return nodes, nid, sector_idx, company_idx, macro_idx


def build_event_nodes(start_id: int, rng: np.random.Generator) -> List[GNNNode]:
    """
    Generate N_EVENTS event nodes with temporally clustered arrival times.
    Clusters correspond to known market-moving periods (rate hikes, AI boom, etc.)
    """
    # Cluster centers in days-from-start: Q1-2022 rate hike cycle, 2023 AI boom, etc.
    centers = [120, 240, 365, 480, 600, 730, 850, 950, 1050, 1150, 1300]

    dates: List[datetime] = []
    for _ in range(N_EVENTS):
        if rng.random() < 0.4:          # 40% cluster around market events
            c = int(rng.choice(centers))
            day = int(np.clip(rng.normal(c, 22), 0, TOTAL_DAYS - 1))
        else:                            # 60% uniform background
            day = int(rng.integers(0, TOTAL_DAYS))
        dt = START + timedelta(days=day)
        while dt.weekday() >= 5:         # skip weekends
            dt += timedelta(days=1)
        dates.append(dt)
    dates.sort()

    nodes: List[GNNNode] = []
    for i, dt in enumerate(dates):
        cat    = CATEGORIES[int(rng.integers(0, len(CATEGORIES)))]
        impact = float(np.clip(rng.exponential(0.35), 0.05, 1.0))
        dstr   = dt.strftime("%Y-%m-%d")
        nodes.append(GNNNode(
            gnn_id      = start_id + i,
            gnn_type    = "Event",
            name        = f"{cat} {dstr} #{i}",
            slug        = f"evt_{slugify(cat)}_{dstr}_{i}",
            impact_score= impact,
            props       = {"event_date": dstr, "gdelt_category": cat,
                           "impact_score": impact,
                           "tone": float(rng.uniform(-10.0, -0.5))},
        ))
    return nodes


# ─────────────────────────────────────────────────────────────────────────────
# § 5  EDGE GENERATION
# ─────────────────────────────────────────────────────────────────────────────

_AR_POS = 0.010    # |AR| > 1 % → causal
_AR_NEG = 0.003    # |AR| < 0.3 % → not causal

def _label(ar: float, explicit: bool) -> int:
    if explicit:           return 1
    if abs(ar) >= _AR_POS: return 1
    if abs(ar) < _AR_NEG:  return 0
    return 0


def _make_edge(s, t, etype, w, ts, sys_, causal, existing: Set) -> Optional[GNNEdge]:
    k = (s, t, etype)
    if k in existing or s == t:
        return None
    e = GNNEdge(s, t, etype, round(float(w), 6), ts, sys_)
    e.props = {"causal_label": causal}  # type: ignore[attr-defined]
    existing.add(k)
    return e


def build_static_edges(
    all_nodes: List[GNNNode],
    sector_idx: Dict[str, int],
    company_idx: Dict[str, int],
    macro_idx:  Dict[str, int],
    rng: np.random.Generator,
) -> Tuple[List[GNNEdge], Set]:
    edges:    List[GNNEdge] = []
    existing: Set           = set()

    def add(s, t, etype, w, causal=-1):
        e = _make_edge(s, t, etype, w, None, "synthetic", causal, existing)
        if e:
            edges.append(e)

    # BELONGS_TO_SECTOR
    for sec_name, members in SECTOR_MEMBERSHIP.items():
        if sec_name not in sector_idx:
            continue
        sid = sector_idx[sec_name]
        for cname in members:
            if cname in company_idx:
                add(company_idx[cname], sid, "BELONGS_TO_SECTOR", 1.0)

    # COMPETES_WITH (within same sector, prob 0.6)
    for members in SECTOR_MEMBERSHIP.values():
        cids = [company_idx[c] for c in members if c in company_idx]
        for i, a in enumerate(cids):
            for b in cids[i + 1:]:
                if rng.random() < 0.6:
                    w = float(rng.uniform(0.3, 0.9))
                    add(a, b, "COMPETES_WITH", w)
                    add(b, a, "COMPETES_WITH", w)

    # OPERATES_IN geography (1–3 geos per company)
    geo_nodes = [n for n in all_nodes if n.gnn_type == "Geography"]
    geo_ids   = np.array([n.gnn_id for n in geo_nodes])
    for cid in company_idx.values():
        k = int(rng.integers(1, 4))
        for gid in rng.choice(geo_ids, size=min(k, len(geo_ids)), replace=False):
            add(int(cid), int(gid), "OPERATES_IN", 1.0)

    # INFLUENCES macro → sector (2–5 sectors per macro)
    sector_ids = np.array(list(sector_idx.values()))
    for mid in macro_idx.values():
        k = int(rng.integers(2, 6))
        for sid in rng.choice(sector_ids, size=min(k, len(sector_ids)), replace=False):
            add(int(mid), int(sid), "INFLUENCES", float(rng.uniform(0.4, 0.9)))

    return edges, existing


def build_event_edges(
    event_nodes: List[GNNNode],
    sector_idx:  Dict[str, int],
    company_idx: Dict[str, int],
    macro_idx:   Dict[str, int],
    existing:    Set,
    rng:         np.random.Generator,
) -> List[GNNEdge]:
    edges: List[GNNEdge] = []

    # Build sector → [company_ids] lookup
    sec_cos: Dict[int, List[int]] = defaultdict(list)
    for sec_name, members in SECTOR_MEMBERSHIP.items():
        if sec_name not in sector_idx:
            continue
        sid = sector_idx[sec_name]
        for cname in members:
            if cname in company_idx:
                sec_cos[sid].append(company_idx[cname])

    sector_id_list = np.array(list(sector_idx.values()))
    macro_id_list  = np.array(list(macro_idx.values()))

    def add(s, t, etype, w, ts, sys_, ar, explicit):
        causal = _label(ar, explicit)
        e = _make_edge(s, t, etype, w, ts, sys_, causal, existing)
        if e:
            edges.append(e)

    for ev in event_nodes:
        cat  = ev.props.get("gdelt_category", CATEGORIES[0])
        ts   = ev.props.get("event_date")
        w0   = ev.impact_score

        primary_secs = CATEGORY_SECTORS.get(cat, SECTORS[:2])
        primary_sids = [sector_idx[s] for s in primary_secs if s in sector_idx]

        # ── Positive IMPACTS: primary sector nodes ────────────────────────────
        for sid in primary_sids:
            ar = float(np.clip(rng.normal(0.025, 0.012), -0.05, 0.12))
            add(ev.gnn_id, sid, "IMPACTS", w0 * 0.85, ts, "realworld", ar, True)

            # Companies in that sector
            cos = sec_cos.get(sid, [])
            n_hit = min(int(rng.integers(2, 5)), len(cos))
            if cos:
                for cid in rng.choice(cos, size=n_hit, replace=False):
                    ar_c = float(np.clip(rng.normal(0.018, 0.013), -0.05, 0.10))
                    explicit = rng.random() < 0.55
                    add(ev.gnn_id, int(cid), "IMPACTS", w0 * 0.72, ts,
                        "realworld", ar_c, explicit)

        # ── Hard negatives: off-sector companies (label=0) ───────────────────
        primary_sid_set = set(primary_sids)
        off_sids = [s for s in sec_cos if s not in primary_sid_set]
        if off_sids:
            neg_sid = int(rng.choice(off_sids))
            neg_cos = sec_cos[neg_sid]
            n_neg   = min(3, len(neg_cos))
            if neg_cos:
                for cid in rng.choice(neg_cos, size=n_neg, replace=False):
                    ar_n = float(np.clip(rng.normal(0.0, 0.001), -0.002, 0.002))
                    add(ev.gnn_id, int(cid), "IMPACTS", 0.05, ts,
                        "hard_negative", ar_n, False)

        # ── INFLUENCES macro (causal propagation) ────────────────────────────
        rel_macros = [macro_idx[m] for m in CATEGORY_MACROS.get(cat, [])
                      if m in macro_idx]
        for mid in rel_macros[:2]:
            ar_m = float(np.clip(rng.normal(0.015, 0.010), -0.03, 0.08))
            add(ev.gnn_id, mid, "INFLUENCES", w0 * 0.6, ts,
                "causal_chain", ar_m, w0 > 0.3)

    return edges


# ─────────────────────────────────────────────────────────────────────────────
# § 6  FEATURE MATRIX
# ─────────────────────────────────────────────────────────────────────────────

def build_features(nodes: List[GNNNode], rng: np.random.Generator) -> np.ndarray:
    """
    [N × 396]:
      [0:10]   one-hot node type
      [10]     normalized in-degree centrality
      [11]     impact / risk score
      [12:396] structured 384-d embedding

    Embedding strategy:
      Each node type has a fixed prototype (seeded separately for stability).
      Event nodes get a mixture of their type-prototype and a category sub-prototype.
      Individual nodes = 0.75 * prototype + 0.25 * Gaussian noise, L2-normalised.
    This produces realistic cluster structure without any LLM call.
    """
    N  = len(nodes)
    X  = np.zeros((N, FEATURE_DIM), dtype=np.float32)
    p_rng = np.random.default_rng(0)   # fixed seed → stable prototypes across runs
    type_proto = p_rng.standard_normal((len(GNN_NODE_TYPES), 384)).astype(np.float32)
    cat_proto  = p_rng.standard_normal((len(CATEGORIES), 384)).astype(np.float32)

    max_deg = max((n.degree for n in nodes), default=1) or 1

    for i, nd in enumerate(nodes):
        ti = TYPE_IDX.get(nd.gnn_type, 0)
        X[i, ti] = 1.0
        X[i, 10] = nd.degree / max_deg
        X[i, 11] = nd.impact_score

        proto = type_proto[ti].copy()
        if nd.gnn_type == "Event":
            cat = nd.props.get("gdelt_category", CATEGORIES[0])
            ci  = CATEGORIES.index(cat) if cat in CATEGORIES else 0
            proto = 0.7 * proto + 0.3 * cat_proto[ci]

        noise = rng.standard_normal(384).astype(np.float32) * 0.28
        emb   = 0.75 * proto + 0.25 * noise
        norm  = float(np.linalg.norm(emb)) or 1.0
        X[i, 12:] = emb / norm

    return X


# ─────────────────────────────────────────────────────────────────────────────
# § 7  TEMPORAL SNAPSHOTS  (quarterly, compatible with TGN / TGAT)
# ─────────────────────────────────────────────────────────────────────────────

def export_snapshots(edges: List[GNNEdge], out: Path) -> int:
    snap_dir = out / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    buckets: Dict[str, List[GNNEdge]] = defaultdict(list)
    for e in edges:
        if e.timestamp:
            try:
                dt  = datetime.fromisoformat(e.timestamp)
                key = f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
                buckets[key].append(e)
            except Exception:
                pass

    for period, pedges in sorted(buckets.items()):
        srcs = np.array([e.source_id for e in pedges], dtype=np.int64)
        dsts = np.array([e.target_id for e in pedges], dtype=np.int64)
        wts  = np.array([e.weight    for e in pedges], dtype=np.float32)
        lbls = np.array(
            [getattr(e, "props", {}).get("causal_label", -1) for e in pedges],
            dtype=np.float32,
        )
        np.savez_compressed(
            snap_dir / f"snapshot_{period}.npz",
            edge_index = np.stack([srcs, dsts]),
            edge_attr  = np.stack([wts, lbls], axis=1),
            node_ids   = np.array(sorted(set(srcs.tolist() + dsts.tolist())),
                                   dtype=np.int64),
        )
    return len(buckets)


# ─────────────────────────────────────────────────────────────────────────────
# § 8  CSV / JSON WRITERS  (identical column schema to the real exporter)
# ─────────────────────────────────────────────────────────────────────────────

def write_nodes(nodes: List[GNNNode], out: Path) -> None:
    with open(out / "nodes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "type", "name", "slug", "source"])
        w.writeheader()
        for n in nodes:
            w.writerow({"id": n.gnn_id, "type": n.gnn_type,
                        "name": n.name, "slug": n.slug, "source": n.source})


def write_edges(edges: List[GNNEdge], out: Path) -> None:
    with open(out / "edges.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source", "target", "type",
                                           "weight", "timestamp", "source_system"])
        w.writeheader()
        for e in edges:
            w.writerow({"source": e.source_id, "target": e.target_id,
                        "type": e.gnn_type, "weight": round(e.weight, 6),
                        "timestamp": e.timestamp or "", "source_system": e.source_system})


def write_edge_labels(edges: List[GNNEdge], out: Path) -> None:
    with open(out / "edge_labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source", "target", "type",
                                           "weight", "causal_label", "source_system"])
        w.writeheader()
        for e in edges:
            lbl = getattr(e, "props", {}).get("causal_label", -1)
            w.writerow({"source": e.source_id, "target": e.target_id,
                        "type": e.gnn_type, "weight": round(e.weight, 6),
                        "causal_label": lbl, "source_system": e.source_system})


def write_causal_map(nodes: List[GNNNode], edges: List[GNNEdge], out: Path) -> None:
    id2n = {n.gnn_id: n for n in nodes}
    cmap: Dict[str, Any] = {}
    for e in edges:
        if e.gnn_type != "IMPACTS":
            continue
        ev  = id2n.get(e.source_id)
        dst = id2n.get(e.target_id)
        if ev is None or ev.gnn_type != "Event" or dst is None:
            continue
        if ev.slug not in cmap:
            cmap[ev.slug] = {"name": ev.name,
                              "date": ev.props.get("event_date", ""),
                              "impact_score": ev.impact_score, "entities": []}
        lbl = getattr(e, "props", {}).get("causal_label", -1)
        cmap[ev.slug]["entities"].append({
            "name": dst.name, "type": dst.gnn_type,
            "causal_label": lbl, "edge_weight": round(e.weight, 6),
            "edge_source": e.source_system,
        })
    (out / "causal_map.json").write_text(
        json.dumps(cmap, indent=2, ensure_ascii=False), encoding="utf-8")


def write_metadata(nodes: List[GNNNode], edges: List[GNNEdge],
                   features: np.ndarray, out: Path) -> None:
    nc = Counter(n.gnn_type for n in nodes)
    ec = Counter(e.gnn_type for e in edges)
    meta = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "generator":       "generate_synthetic_dataset.py",
        "data_sources":    ["synthetic — Talan domain knowledge base"],
        "num_nodes":        len(nodes),
        "num_edges":        len(edges),
        "feature_dim":      int(features.shape[1]),
        "node_types":       GNN_NODE_TYPES,
        "edge_types":       GNN_EDGE_TYPES,
        "node_type_counts": dict(nc),
        "edge_type_counts": dict(ec),
        "feature_layout":  {
            "0_to_9":    "one-hot node type (10-d)",
            "10":        "in-degree centrality normalized",
            "11":        "impact / risk score normalized",
            "12_to_395": "structured Gaussian cluster embedding (384-d)",
        },
    }
    (out / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# § 9  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    log.info("=" * 55)
    log.info("Talan Synthetic GNN Dataset Generator")
    log.info("  events      : %d", N_EVENTS)
    log.info("  feature_dim : %d", FEATURE_DIM)
    log.info("  output      : %s", OUT)
    log.info("=" * 55)

    # ── Step 1: static nodes ─────────────────────────────────────────────────
    log.info("Step 1/5 — Static nodes (companies / sectors / macros / geos)")
    static_nodes, next_id, sector_idx, company_idx, macro_idx = build_static_nodes(rng)
    log.info("          %d static nodes", len(static_nodes))

    # ── Step 2: event nodes ──────────────────────────────────────────────────
    log.info("Step 2/5 — Event nodes")
    event_nodes = build_event_nodes(next_id, rng)
    all_nodes   = static_nodes + event_nodes
    log.info("          %d total nodes", len(all_nodes))

    # ── Step 3: edges ────────────────────────────────────────────────────────
    log.info("Step 3/5 — Static edges (sector / competition / geo / macro)")
    static_edges, existing = build_static_edges(
        all_nodes, sector_idx, company_idx, macro_idx, rng)
    log.info("          %d static edges", len(static_edges))

    log.info("Step 3/5 — Event edges (IMPACTS / INFLUENCES / hard negatives)")
    event_edges = build_event_edges(
        event_nodes, sector_idx, company_idx, macro_idx, existing, rng)
    log.info("          %d event edges", len(event_edges))

    all_edges = static_edges + event_edges

    # Compute in-degrees
    deg = Counter(e.target_id for e in all_edges)
    for n in all_nodes:
        n.degree = deg.get(n.gnn_id, 0)

    # ── Step 4: feature matrix ───────────────────────────────────────────────
    log.info("Step 4/5 — Feature matrix [%d × %d]", len(all_nodes), FEATURE_DIM)
    features = build_features(all_nodes, rng)

    # ── Step 5: export ───────────────────────────────────────────────────────
    log.info("Step 5/5 — Writing output files")
    np.save(str(OUT / "node_features.npy"), features)
    write_nodes(all_nodes, OUT)
    write_edges(all_edges, OUT)
    write_edge_labels(all_edges, OUT)
    write_causal_map(all_nodes, all_edges, OUT)
    write_metadata(all_nodes, all_edges, features, OUT)
    n_snaps = export_snapshots(all_edges, OUT)

    # ── Summary ──────────────────────────────────────────────────────────────
    pos = sum(1 for e in all_edges if getattr(e, "props", {}).get("causal_label") == 1)
    neg = sum(1 for e in all_edges if getattr(e, "props", {}).get("causal_label") == 0)
    log.info("=" * 55)
    log.info("  Nodes total : %d  (events=%d, other=%d)",
             len(all_nodes), len(event_nodes), len(static_nodes))
    log.info("  Edges total : %d", len(all_edges))
    log.info("  causal=1    : %d  (%.1f%%)", pos, 100 * pos / max(pos + neg, 1))
    log.info("  causal=0    : %d  (%.1f%%)", neg, 100 * neg / max(pos + neg, 1))
    log.info("  Snapshots   : %d quarterly files", n_snaps)
    log.info("  Features    : shape %s  dtype %s", features.shape, features.dtype)
    log.info("=" * 55)
    log.info("Done. Ready for GNN training.")


if __name__ == "__main__":
    main()
