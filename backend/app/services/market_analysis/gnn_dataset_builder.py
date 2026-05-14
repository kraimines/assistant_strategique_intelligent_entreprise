"""
gnn_dataset_builder.py
======================
Production GNN dataset pipeline for Talan's Strategic Knowledge Graph.

Pipeline stages:
  1. Neo4jExtractor  — pull nodes & edges from Neo4j (market KG + business KG)
  2. GraphEnricher   — inject predefined strategic nodes (sectors, BUs, macro indicators, competitors)
  3. FeatureBuilder  — build float32 [N × D] node feature matrix
  4. DatasetExporter — write nodes.csv / edges.csv / node_features.npy / metadata.json
  5. PyGConverter    — wrap as torch_geometric.data.HeteroData for training / inference
  6. simulate_event_impact() — inject a hypothetical event for GNN forward pass

Feature vector layout per node (FEATURE_DIM = 396):
  [0 : 10]   one-hot node type  (len(GNN_NODE_TYPES))
  [10 : 11]  degree centrality  (normalized 0–1)
  [11 : 12]  risk / impact score (normalized 0–1)
  [12 : 396] LLM embedding      (sentence-transformers "all-MiniLM-L6-v2", 384-d)
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import numpy as np
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# § 1  SCHEMA CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

GNN_NODE_TYPES: List[str] = [
    "Company",       # Talan + market companies
    "BusinessUnit",  # Internal divisions (from Neo4j Department)
    "Sector",        # Industry verticals
    "Geography",     # Countries / regions (from Neo4j Country)
    "Client",        # Client firms (from Neo4j Account)
    "Project",       # Delivery projects
    "Competitor",    # Competitor companies (from Neo4j Competitor label)
    "Regulation",    # Laws / directives (AI Act, GDPR …)
    "MacroIndicator",# Economic metrics (interest rates, inflation …)
    "Event",         # Discrete market events
]

# Maps every Neo4j label to a GNN node type; None = skip that node
LABEL_TO_GNN_TYPE: Dict[str, Optional[str]] = {
    # ── Market KG ──────────────────────────────────────────────────────────────
    "Company":          "Company",
    "Competitor":       "Competitor",
    "Sector":           "Sector",
    "Country":          "Geography",
    "Regulation":       "Regulation",
    "MacroIndicator":   "MacroIndicator",
    "Event":            "Event",
    # ── Business KG (strategic subset) ────────────────────────────────────────
    "Department":       "BusinessUnit",
    "Account":          "Client",
    "Project":          "Project",
    # ── Skip (operational / non-strategic) ────────────────────────────────────
    "Person": None,           "Technology": None,     "MarketTrend": None,
    "News": None,             "Employee": None,       "Skill": None,
    "Contact": None,          "Opportunity": None,    "Customer": None,
    "Invoice": None,          "Payment": None,        "Supplier": None,
    "Product": None,          "SalesOrder": None,     "PurchaseOrder": None,
    "Inventory": None,        "Milestone": None,      "LeaveRequest": None,
    "PerformanceReview": None,"JobOpening": None,     "Activity": None,
    "RevenueHistory": None,
}

# Maps every Neo4j relationship type to a GNN edge type; None = skip
REL_TO_GNN_EDGE: Dict[str, Optional[str]] = {
    "CAUSES_IMPACT_ON":  "IMPACTS",
    "IMPACTS":           "IMPACTS",
    "TRIGGERS_EVENT":    "IMPACTS",
    "ACQUIRED":          "IMPACTS",
    "INFLUENCES":        "INFLUENCES",
    "AFFECTS_INDICATOR": "INFLUENCES",
    "COMPETES_WITH":     "COMPETES_WITH",
    "BELONGS_TO_SECTOR": "BELONGS_TO_SECTOR",
    "OPERATES_IN":       "OPERATES_IN",
    "SUPPLY_CHAIN_LINK": "SUPPLY_CHAIN_LINK",
    "FOR_ACCOUNT":       "DELIVERED_FOR",
    "BELONGS_TO_DEPT":   "AFFECTS",
    "AFFECTS":           "AFFECTS",
    "SERVES":            "SERVES",
    # Skip all business-operational relations
    **{k: None for k in [
        "HAS_OPPORTUNITY", "HAS_CONTACT", "LINKED_TO_ACCOUNT", "ASSIGNED_TO",
        "MANAGED_BY", "HAS_SKILL", "SUBMITTED_LEAVE", "APPROVED_LEAVE",
        "HAD_REVIEW", "REVIEWED_BY", "OPENS_POSITION", "RECRUITS_FOR",
        "MANAGES_PROJECT", "HAS_MILESTONE", "OWNS_MILESTONE", "LOGGED_TIME",
        "OWNS_OPPORTUNITY", "HAS_REVENUE", "LOGGED_ACTIVITY",
        "ACTIVITY_ON_CONTACT", "ACTIVITY_FOR_OPP", "PLACED_ORDER",
        "HAS_INVOICE", "INVOICES_ORDER", "SETTLES", "SUPPLIES",
        "HANDLES_ORDER", "ORDERED_FROM", "APPROVED_PO", "CONTAINS_PRODUCT",
        "REQUESTS_PRODUCT", "HAS_STOCK", "BELONGS_TO", "RECRUITS_IN",
        "LAUNCHED", "MENTIONS",
    ]},
}

GNN_EDGE_TYPES: List[str] = sorted(
    {v for v in REL_TO_GNN_EDGE.values() if v is not None}
)

EMBEDDING_DIM: int = 384   # "all-MiniLM-L6-v2" sentence embeddings
STRUCTURAL_DIM: int = 2    # [degree_norm, impact_norm]
FEATURE_DIM: int = len(GNN_NODE_TYPES) + STRUCTURAL_DIM + EMBEDDING_DIM  # 396

# ─────────────────────────────────────────────────────────────────────────────
# § 2  PREDEFINED ENRICHMENT DATA
# ─────────────────────────────────────────────────────────────────────────────

PREDEFINED_SECTORS: List[str] = [
    "Financial Services", "Banking & Finance", "Insurance",
    "Energy & Utilities", "Telecommunications", "Public Sector",
    "Retail & Consumer Goods", "Healthcare & Life Sciences",
    "Transportation & Logistics", "Industry & Manufacturing",
    "Defense & Aerospace", "Real Estate & Construction",
    "Media & Entertainment", "IT Services", "Artificial Intelligence",
    "Semiconductors",
]

PREDEFINED_BUSINESS_UNITS: List[str] = [
    "Digital Transformation", "Data & AI", "Cloud & Infrastructure",
    "Cybersecurity", "Regulatory & Compliance", "Process Automation",
    "IT Consulting", "Software Engineering", "Enterprise Architecture",
    "Innovation Lab",
]

PREDEFINED_MACRO_INDICATORS: List[str] = [
    "ECB Interest Rates", "Eurozone Inflation", "Brent Crude Oil Price",
    "EUR/USD Exchange Rate", "CAC 40 Index", "IT Sector Growth",
    "France Unemployment Rate", "Government Digital Spending",
    "AI Market Growth Index", "Cloud Adoption Rate",
    "Cybersecurity Spending Index", "Global Tech M&A Volume",
]

PREDEFINED_COMPETITORS: List[str] = [
    "Capgemini", "Accenture", "Sopra Steria", "Atos", "CGI",
    "IBM Consulting", "Deloitte", "PwC Consulting", "Ernst & Young",
    "KPMG Advisory", "Wavestone", "Devoteam",
]

PREDEFINED_GEOGRAPHIES: List[str] = [
    "France", "Germany", "United Kingdom", "Spain", "Italy",
    "Belgium", "Netherlands", "Luxembourg", "Morocco", "Tunisia",
    "United States", "Canada", "European Union",
]

# Predefined edges: (src_name, src_type, edge_type, dst_name, dst_type, weight, source_system)
_PE = Tuple[str, str, str, str, str, float, str]
PREDEFINED_EDGES: List[_PE] = [
    # Talan ↔ Competitors
    *[("Talan", "Company", "COMPETES_WITH", c, "Competitor", 0.85, "manual")
      for c in PREDEFINED_COMPETITORS],
    # Talan → Geographies
    *[("Talan", "Company", "OPERATES_IN", g, "Geography", 0.9, "manual")
      for g in ["France", "Belgium", "Netherlands", "Luxembourg",
                "Morocco", "Tunisia", "Germany", "Spain"]],
    # Talan → Sectors (client markets)
    *[("Talan", "Company", "SERVES", s, "Sector", 0.8, "manual")
      for s in ["Financial Services", "Banking & Finance", "Insurance",
                "Public Sector", "Telecommunications", "Energy & Utilities"]],
    # Sector → BusinessUnit (demand-driven focus)
    ("Financial Services",      "Sector", "AFFECTS", "Data & AI",               "BusinessUnit", 0.75, "manual"),
    ("Banking & Finance",        "Sector", "AFFECTS", "Regulatory & Compliance", "BusinessUnit", 0.90, "manual"),
    ("Banking & Finance",        "Sector", "AFFECTS", "Data & AI",               "BusinessUnit", 0.80, "manual"),
    ("Insurance",               "Sector", "AFFECTS", "Regulatory & Compliance", "BusinessUnit", 0.85, "manual"),
    ("Public Sector",           "Sector", "AFFECTS", "Digital Transformation",  "BusinessUnit", 0.80, "manual"),
    ("Public Sector",           "Sector", "AFFECTS", "Cybersecurity",           "BusinessUnit", 0.70, "manual"),
    ("Telecommunications",      "Sector", "AFFECTS", "Cloud & Infrastructure",  "BusinessUnit", 0.75, "manual"),
    ("Healthcare & Life Sciences","Sector","AFFECTS", "Data & AI",              "BusinessUnit", 0.65, "manual"),
    ("Industry & Manufacturing", "Sector", "AFFECTS", "Process Automation",     "BusinessUnit", 0.80, "manual"),
    ("Defense & Aerospace",     "Sector", "AFFECTS", "Cybersecurity",           "BusinessUnit", 0.85, "manual"),
    # MacroIndicator → Sector (economic influence chains)
    ("ECB Interest Rates",      "MacroIndicator", "INFLUENCES", "Banking & Finance",         "Sector", 0.92, "manual"),
    ("ECB Interest Rates",      "MacroIndicator", "INFLUENCES", "Real Estate & Construction","Sector", 0.82, "manual"),
    ("Eurozone Inflation",      "MacroIndicator", "INFLUENCES", "Retail & Consumer Goods",   "Sector", 0.80, "manual"),
    ("Eurozone Inflation",      "MacroIndicator", "INFLUENCES", "Energy & Utilities",        "Sector", 0.75, "manual"),
    ("Brent Crude Oil Price",   "MacroIndicator", "INFLUENCES", "Energy & Utilities",        "Sector", 0.95, "manual"),
    ("Brent Crude Oil Price",   "MacroIndicator", "INFLUENCES", "Transportation & Logistics","Sector", 0.88, "manual"),
    ("AI Market Growth Index",  "MacroIndicator", "INFLUENCES", "IT Services",               "Sector", 0.90, "manual"),
    ("AI Market Growth Index",  "MacroIndicator", "INFLUENCES", "Artificial Intelligence",   "Sector", 0.95, "manual"),
    ("AI Market Growth Index",  "MacroIndicator", "INFLUENCES", "Financial Services",        "Sector", 0.70, "manual"),
    ("Cloud Adoption Rate",     "MacroIndicator", "INFLUENCES", "Telecommunications",        "Sector", 0.80, "manual"),
    ("Cloud Adoption Rate",     "MacroIndicator", "INFLUENCES", "IT Services",               "Sector", 0.85, "manual"),
    ("Government Digital Spending","MacroIndicator","INFLUENCES","Public Sector",            "Sector", 0.95, "manual"),
    ("Cybersecurity Spending Index","MacroIndicator","INFLUENCES","Defense & Aerospace",     "Sector", 0.88, "manual"),
    # Competitors → Sectors (market positioning)
    ("Capgemini",   "Competitor", "BELONGS_TO_SECTOR", "Financial Services",  "Sector", 0.80, "manual"),
    ("Accenture",   "Competitor", "BELONGS_TO_SECTOR", "Financial Services",  "Sector", 0.90, "manual"),
    ("Sopra Steria","Competitor", "BELONGS_TO_SECTOR", "Public Sector",       "Sector", 0.90, "manual"),
    ("Atos",        "Competitor", "BELONGS_TO_SECTOR", "Industry & Manufacturing","Sector", 0.75, "manual"),
    ("IBM Consulting","Competitor","BELONGS_TO_SECTOR","Financial Services",  "Sector", 0.80, "manual"),
    ("Deloitte",    "Competitor", "BELONGS_TO_SECTOR", "Financial Services",  "Sector", 0.85, "manual"),
    ("Wavestone",   "Competitor", "BELONGS_TO_SECTOR", "Banking & Finance",   "Sector", 0.85, "manual"),
    # Competitors operate in geographies
    ("Capgemini",   "Competitor", "OPERATES_IN", "France",   "Geography", 0.95, "manual"),
    ("Accenture",   "Competitor", "OPERATES_IN", "France",   "Geography", 0.90, "manual"),
    ("Sopra Steria","Competitor", "OPERATES_IN", "France",   "Geography", 0.95, "manual"),
]

# ─────────────────────────────────────────────────────────────────────────────
# § 3  DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GNNNode:
    gnn_id: int
    gnn_type: str
    name: str
    slug: str
    props: Dict[str, Any] = field(default_factory=dict)
    degree: int = 0
    impact_score: float = 0.0
    source: str = "neo4j"

@dataclass
class GNNEdge:
    source_id: int
    target_id: int
    gnn_type: str
    weight: float = 1.0
    timestamp: Optional[str] = None
    source_system: str = "neo4j"

# ─────────────────────────────────────────────────────────────────────────────
# § 4  UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert any string to a stable ASCII slug for deduplication."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "_", text).strip("_")


def _normalize(values: List[float]) -> List[float]:
    """Min-max normalize a list of floats to [0, 1]."""
    lo, hi = min(values, default=0.0), max(values, default=1.0)
    rng = hi - lo or 1.0
    return [(v - lo) / rng for v in values]


# ─────────────────────────────────────────────────────────────────────────────
# § 5  NEO4J EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

# Cypher that fetches all strategic nodes from both KGs in one pass
_NODE_QUERY = """
MATCH (n)
WHERE any(label IN labels(n)
      WHERE label IN [
          'Company','Competitor','Sector','Country','Regulation',
          'MacroIndicator','Event','Department','Account','Project'
      ])
RETURN
    elementId(n)       AS neo4j_eid,
    labels(n)          AS labels,
    n.name             AS name,
    n.slug             AS slug,
    n.impact_score     AS impact_score,
    n.risk_score       AS risk_score,
    n.description      AS description,
    n.ticker           AS ticker,
    n.sector           AS sector,
    n.country          AS country,
    n.revenue_eur      AS revenue_eur,
    n.employees        AS employees
ORDER BY elementId(n)
"""

# Fetch all strategic relationships (skip pure HR/ERP operational edges)
_EDGE_QUERY = """
MATCH (a)-[r]->(b)
WHERE type(r) IN [
    'CAUSES_IMPACT_ON','IMPACTS','TRIGGERS_EVENT','ACQUIRED',
    'INFLUENCES','AFFECTS_INDICATOR',
    'COMPETES_WITH','BELONGS_TO_SECTOR','OPERATES_IN',
    'SUPPLY_CHAIN_LINK','FOR_ACCOUNT','BELONGS_TO_DEPT','AFFECTS','SERVES'
]
AND any(label IN labels(a) WHERE label IN [
    'Company','Competitor','Sector','Country','Regulation',
    'MacroIndicator','Event','Department','Account','Project'
])
AND any(label IN labels(b) WHERE label IN [
    'Company','Competitor','Sector','Country','Regulation',
    'MacroIndicator','Event','Department','Account','Project'
])
RETURN
    elementId(a)       AS from_eid,
    elementId(b)       AS to_eid,
    type(r)            AS rel_type,
    r.weight           AS weight,
    r.impact_score     AS impact_score,
    r.confidence       AS confidence,
    r.timestamp        AS timestamp,
    r.source           AS source_system
"""


class Neo4jExtractor:
    """Pulls nodes and relationships from Neo4j using the official sync driver."""

    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def extract(self) -> Tuple[List[Dict], List[Dict]]:
        """Return (raw_nodes, raw_edges) as plain dicts."""
        with self._driver.session() as session:
            raw_nodes = [dict(r) for r in session.run(_NODE_QUERY)]
            raw_edges = [dict(r) for r in session.run(_EDGE_QUERY)]
        logger.info("Neo4j: extracted %d nodes, %d edges", len(raw_nodes), len(raw_edges))
        return raw_nodes, raw_edges

    def compute_degrees(self) -> Dict[str, int]:
        """Return {node_eid: in_degree} for centrality normalization."""
        query = """
        MATCH (n)<-[r]-(m)
        WHERE any(label IN labels(n) WHERE label IN [
            'Company','Competitor','Sector','Country','Regulation',
            'MacroIndicator','Event','Department','Account','Project'
        ])
        RETURN elementId(n) AS eid, count(r) AS in_degree
        """
        with self._driver.session() as session:
            return {r["eid"]: r["in_degree"] for r in session.run(query)}


# ─────────────────────────────────────────────────────────────────────────────
# § 6  GRAPH ENRICHER
# ─────────────────────────────────────────────────────────────────────────────

class GraphEnricher:
    """
    Injects predefined strategic nodes and relationships into the extracted graph.
    Uses slug-based deduplication to avoid creating duplicates of nodes already
    present in Neo4j.
    """

    def enrich(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        slug_to_id: Dict[str, int],
        next_id: int,
    ) -> Tuple[List[GNNNode], List[GNNEdge], Dict[str, int], int]:
        """
        Args:
            nodes:      existing GNNNode list (will be extended in-place)
            edges:      existing GNNEdge list (will be extended in-place)
            slug_to_id: global slug → gnn_id mapping
            next_id:    next available integer id

        Returns the (possibly extended) nodes, edges, slug_to_id, next_id.
        """
        # ── Inject predefined nodes ────────────────────────────────────────────
        predefined_batches: List[Tuple[List[str], str]] = [
            (PREDEFINED_SECTORS,         "Sector"),
            (PREDEFINED_BUSINESS_UNITS,  "BusinessUnit"),
            (PREDEFINED_MACRO_INDICATORS,"MacroIndicator"),
            (PREDEFINED_COMPETITORS,     "Competitor"),
            (PREDEFINED_GEOGRAPHIES,     "Geography"),
        ]
        for names, gnn_type in predefined_batches:
            for name in names:
                slug = slugify(name)
                if slug not in slug_to_id:
                    node = GNNNode(
                        gnn_id=next_id, gnn_type=gnn_type,
                        name=name, slug=slug,
                        source="enriched",
                    )
                    nodes.append(node)
                    slug_to_id[slug] = next_id
                    next_id += 1

        # Always ensure Talan exists
        talan_slug = slugify("Talan")
        if talan_slug not in slug_to_id:
            nodes.append(GNNNode(
                gnn_id=next_id, gnn_type="Company",
                name="Talan", slug=talan_slug, source="enriched",
            ))
            slug_to_id[talan_slug] = next_id
            next_id += 1

        # ── Inject predefined edges ────────────────────────────────────────────
        existing_edge_keys: Set[Tuple[int, int, str]] = {
            (e.source_id, e.target_id, e.gnn_type) for e in edges
        }

        for src_name, _src_type, edge_type, dst_name, _dst_type, weight, sys_ in PREDEFINED_EDGES:
            src_slug = slugify(src_name)
            dst_slug = slugify(dst_name)
            src_id = slug_to_id.get(src_slug)
            dst_id = slug_to_id.get(dst_slug)
            if src_id is None or dst_id is None:
                continue
            key = (src_id, dst_id, edge_type)
            if key not in existing_edge_keys:
                edges.append(GNNEdge(
                    source_id=src_id, target_id=dst_id,
                    gnn_type=edge_type, weight=weight,
                    source_system=sys_,
                ))
                existing_edge_keys.add(key)

        logger.info("Enricher: graph now has %d nodes, %d edges", len(nodes), len(edges))
        return nodes, edges, slug_to_id, next_id


# ─────────────────────────────────────────────────────────────────────────────
# § 7  FEATURE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

class FeatureBuilder:
    """
    Builds a float32 [num_nodes × FEATURE_DIM] feature matrix.

    Feature layout:
      [0:10]   one-hot node type          (10-d)
      [10:11]  in-degree (normalized)      (1-d)
      [11:12]  risk / impact score (norm)  (1-d)
      [12:396] LLM text embedding          (384-d)
    """

    def __init__(self):
        self._embedder = None  # lazy-loaded

    def _load_embedder(self):
        if self._embedder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("FeatureBuilder: sentence-transformer loaded")
        except Exception as exc:
            logger.warning("FeatureBuilder: sentence-transformers unavailable (%s) → zero embeddings", exc)
            self._embedder = None

    def _embed(self, texts: List[str]) -> np.ndarray:
        """Return [N × 384] float32 embeddings, or zeros if model unavailable."""
        self._load_embedder()
        if self._embedder is not None:
            try:
                vecs = self._embedder.encode(texts, show_progress_bar=False, batch_size=64)
                return vecs.astype(np.float32)
            except Exception as exc:
                logger.warning("FeatureBuilder: encode failed (%s) → zeros", exc)
        return np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)

    def build(self, nodes: List[GNNNode]) -> np.ndarray:
        """
        Build and return the full feature matrix.

        Args:
            nodes: list of GNNNode (must have .degree and .impact_score set)

        Returns:
            np.ndarray of shape [len(nodes), FEATURE_DIM], float32
        """
        n = len(nodes)
        matrix = np.zeros((n, FEATURE_DIM), dtype=np.float32)

        # ── One-hot node type ──────────────────────────────────────────────────
        type_index = {t: i for i, t in enumerate(GNN_NODE_TYPES)}
        for i, node in enumerate(nodes):
            idx = type_index.get(node.gnn_type, 0)
            matrix[i, idx] = 1.0

        # ── Structural features (degree + impact, both normalized) ─────────────
        degrees = [float(node.degree) for node in nodes]
        impacts = [float(node.impact_score) for node in nodes]
        degrees_norm = _normalize(degrees)
        impacts_norm = _normalize(impacts)
        for i, (d, s) in enumerate(zip(degrees_norm, impacts_norm)):
            matrix[i, len(GNN_NODE_TYPES)]     = d
            matrix[i, len(GNN_NODE_TYPES) + 1] = s

        # ── LLM text embeddings ────────────────────────────────────────────────
        texts = [
            f"{node.gnn_type}: {node.name}. "
            f"{node.props.get('description', '') or node.props.get('sector', '')}"
            for node in nodes
        ]
        emb_start = len(GNN_NODE_TYPES) + STRUCTURAL_DIM  # = 12
        matrix[:, emb_start:] = self._embed(texts)

        logger.info("FeatureBuilder: built %d × %d matrix", n, FEATURE_DIM)
        return matrix


# ─────────────────────────────────────────────────────────────────────────────
# § 8  DATASET EXPORTER
# ─────────────────────────────────────────────────────────────────────────────

class DatasetExporter:
    """Writes nodes.csv, edges.csv, node_features.npy, metadata.json."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        features: np.ndarray,
    ) -> Dict[str, Path]:
        """Write all four output files. Returns a dict of {name: path}."""
        paths = {
            "nodes":    self._write_nodes(nodes),
            "edges":    self._write_edges(edges),
            "features": self._write_features(features),
            "metadata": self._write_metadata(nodes, edges, features),
        }
        logger.info("DatasetExporter: dataset written to %s", self.output_dir)
        return paths

    def _write_nodes(self, nodes: List[GNNNode]) -> Path:
        path = self.output_dir / "nodes.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "type", "name", "slug", "source"])
            writer.writeheader()
            for node in nodes:
                writer.writerow({
                    "id":     node.gnn_id,
                    "type":   node.gnn_type,
                    "name":   node.name,
                    "slug":   node.slug,
                    "source": node.source,
                })
        logger.info("Exported %d nodes → %s", len(nodes), path)
        return path

    def _write_edges(self, edges: List[GNNEdge]) -> Path:
        path = self.output_dir / "edges.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["source", "target", "type", "weight", "timestamp", "source_system"],
            )
            writer.writeheader()
            for edge in edges:
                writer.writerow({
                    "source":        edge.source_id,
                    "target":        edge.target_id,
                    "type":          edge.gnn_type,
                    "weight":        round(edge.weight, 6),
                    "timestamp":     edge.timestamp or "",
                    "source_system": edge.source_system,
                })
        logger.info("Exported %d edges → %s", len(edges), path)
        return path

    def _write_features(self, features: np.ndarray) -> Path:
        path = self.output_dir / "node_features.npy"
        np.save(str(path), features)
        logger.info("Saved feature matrix %s → %s", features.shape, path)
        return path

    def _write_metadata(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        features: np.ndarray,
    ) -> Path:
        type_counts: Dict[str, int] = {}
        for node in nodes:
            type_counts[node.gnn_type] = type_counts.get(node.gnn_type, 0) + 1

        edge_type_counts: Dict[str, int] = {}
        for edge in edges:
            edge_type_counts[edge.gnn_type] = edge_type_counts.get(edge.gnn_type, 0) + 1

        meta = {
            "generated_at":    datetime.now(timezone.utc).isoformat(),
            "num_nodes":        len(nodes),
            "num_edges":        len(edges),
            "feature_dim":      int(features.shape[1]),
            "node_types":       GNN_NODE_TYPES,
            "edge_types":       GNN_EDGE_TYPES,
            "node_type_counts": type_counts,
            "edge_type_counts": edge_type_counts,
            "feature_layout": {
                "0_to_9":   "one-hot node type (10-d)",
                "10":       "in-degree centrality normalized",
                "11":       "impact / risk score normalized",
                "12_to_395":"sentence-transformer embedding (384-d, all-MiniLM-L6-v2)",
            },
            "edge_sources": ["neo4j", "manual", "llm"],
        }

        path = self.output_dir / "metadata.json"
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Metadata written → %s", path)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# § 9  NEO4J WRITER  — push enriched nodes/edges back into the graph DB
# ─────────────────────────────────────────────────────────────────────────────

# Maps GNN node type → Neo4j label used in MERGE clauses
GNN_TYPE_TO_NEO4J_LABEL: Dict[str, str] = {
    "Company":       "Company",
    "BusinessUnit":  "BusinessUnit",   # new label (not in original schema)
    "Sector":        "Sector",
    "Geography":     "Country",        # stored as Country in Neo4j
    "Competitor":    "Competitor",
    "Regulation":    "Regulation",
    "MacroIndicator":"MacroIndicator",
    "Event":         "Event",
    # Client / Project come from business KG — skip predefined creation
}

# Maps GNN edge type → Neo4j relationship type for MERGE
GNN_EDGE_TO_NEO4J_REL: Dict[str, str] = {
    "IMPACTS":           "IMPACTS",
    "INFLUENCES":        "INFLUENCES",
    "AFFECTS":           "AFFECTS",
    "COMPETES_WITH":     "COMPETES_WITH",
    "OPERATES_IN":       "OPERATES_IN",
    "SERVES":            "SERVES",
    "BELONGS_TO_SECTOR": "BELONGS_TO_SECTOR",
    "SUPPLY_CHAIN_LINK": "SUPPLY_CHAIN_LINK",
    "DELIVERED_FOR":     "FOR_ACCOUNT",
}

_BATCH_SIZE = 200  # nodes/edges per Cypher transaction


def _node_merge_cypher(label: str) -> str:
    return f"""
UNWIND $rows AS row
MERGE (n:{label} {{name: row.name}})
ON CREATE SET
    n.slug        = row.slug,
    n.source      = 'enriched',
    n.created_at  = datetime()
ON MATCH SET
    n.enriched_at = datetime()
"""


def _edge_merge_cypher(rel_type: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (src {{name: row.src_name}})
MATCH (dst {{name: row.dst_name}})
MERGE (src)-[r:{rel_type}]->(dst)
ON CREATE SET
    r.weight        = row.weight,
    r.source        = row.source_system,
    r.created_at    = datetime()
ON MATCH SET
    r.weight        = row.weight,
    r.updated_at    = datetime()
"""


class Neo4jWriter:
    """
    Writes enriched nodes and edges back into Neo4j so they are immediately
    visible in the frontend KG Explorer.

    Only nodes with source='enriched' are pushed (predefined strategic context).
    Neo4j-sourced nodes already exist — no duplicate creation needed.
    """

    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def push_nodes(self, nodes: List[GNNNode]) -> int:
        """MERGE all enriched nodes into Neo4j. Returns count of pushed nodes."""
        # Group by GNN type (→ Neo4j label)
        by_label: Dict[str, List[Dict]] = {}
        for node in nodes:
            if node.source != "enriched":
                continue
            label = GNN_TYPE_TO_NEO4J_LABEL.get(node.gnn_type)
            if label is None:
                continue
            by_label.setdefault(label, []).append({
                "name": node.name,
                "slug": node.slug,
            })

        total = 0
        with self._driver.session() as session:
            for label, rows in by_label.items():
                cypher = _node_merge_cypher(label)
                for i in range(0, len(rows), _BATCH_SIZE):
                    batch = rows[i: i + _BATCH_SIZE]
                    session.run(cypher, rows=batch)
                    total += len(batch)
                logger.info("Neo4jWriter: pushed %d %s nodes", len(rows), label)

        logger.info("Neo4jWriter: %d enriched nodes written to Neo4j", total)
        return total

    def push_edges(self, nodes: List[GNNNode], edges: List[GNNEdge]) -> int:
        """MERGE all enriched edges into Neo4j. Returns count of pushed edges."""
        id_to_name: Dict[int, str] = {n.gnn_id: n.name for n in nodes}

        # Group by GNN edge type (→ Neo4j rel type), only enriched/manual edges
        by_rel: Dict[str, List[Dict]] = {}
        for edge in edges:
            if edge.source_system not in ("manual", "enriched", "simulation"):
                continue
            rel_type = GNN_EDGE_TO_NEO4J_REL.get(edge.gnn_type)
            if rel_type is None:
                continue
            src_name = id_to_name.get(edge.source_id)
            dst_name = id_to_name.get(edge.target_id)
            if not src_name or not dst_name:
                continue
            by_rel.setdefault(rel_type, []).append({
                "src_name":     src_name,
                "dst_name":     dst_name,
                "weight":       round(edge.weight, 6),
                "source_system": edge.source_system,
            })

        total = 0
        with self._driver.session() as session:
            for rel_type, rows in by_rel.items():
                cypher = _edge_merge_cypher(rel_type)
                for i in range(0, len(rows), _BATCH_SIZE):
                    batch = rows[i: i + _BATCH_SIZE]
                    session.run(cypher, rows=batch)
                    total += len(batch)
                logger.info("Neo4jWriter: pushed %d [%s] edges", len(rows), rel_type)

        logger.info("Neo4jWriter: %d enriched edges written to Neo4j", total)
        return total

    def push_all(self, nodes: List[GNNNode], edges: List[GNNEdge]) -> Dict[str, int]:
        """Push both nodes and edges. Returns {'nodes': N, 'edges': E}."""
        n_count = self.push_nodes(nodes)
        e_count = self.push_edges(nodes, edges)
        return {"nodes": n_count, "edges": e_count}


# ─────────────────────────────────────────────────────────────────────────────
# § 10  PYTORCH GEOMETRIC CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

class PyGConverter:
    """
    Converts the flat CSV dataset into a torch_geometric.data.HeteroData graph.
    Gracefully no-ops when PyTorch Geometric is not installed.
    """

    def convert(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        features: np.ndarray,
    ) -> Optional[Any]:
        """
        Returns HeteroData if PyG is available, otherwise None.

        HeteroData structure:
          data[node_type].x            = float32 tensor [N_type × D]
          data[node_type].node_id      = list of gnn_ids (for reverse lookup)
          data[src, edge_type, dst].edge_index = long tensor [2 × E]
          data[src, edge_type, dst].edge_attr  = float32 tensor [E × 2]
              (columns: [weight, timestamp_norm])
        """
        try:
            import torch
            from torch_geometric.data import HeteroData
        except ImportError:
            logger.warning("PyGConverter: torch_geometric not installed — skipping conversion")
            return None

        data = HeteroData()

        # ── Node tensors grouped by type ───────────────────────────────────────
        type_to_local_ids: Dict[str, List[int]] = {t: [] for t in GNN_NODE_TYPES}
        gnn_id_to_local: Dict[int, int] = {}  # gnn_id → local index within type

        for node in nodes:
            local_idx = len(type_to_local_ids[node.gnn_type])
            type_to_local_ids[node.gnn_type].append(node.gnn_id)
            gnn_id_to_local[node.gnn_id] = local_idx

        for ntype in GNN_NODE_TYPES:
            global_ids = type_to_local_ids[ntype]
            if not global_ids:
                data[ntype].x = torch.zeros((0, FEATURE_DIM), dtype=torch.float32)
                data[ntype].node_id = []
                continue
            feat_rows = features[global_ids]  # [N_type × D]
            data[ntype].x = torch.tensor(feat_rows, dtype=torch.float32)
            data[ntype].node_id = global_ids

        # ── Edge tensors grouped by (src_type, edge_type, dst_type) ───────────
        # We need to know the type of each node
        id_to_type: Dict[int, str] = {n.gnn_id: n.gnn_type for n in nodes}

        # Collect edges per canonical triplet
        edge_buckets: Dict[Tuple[str, str, str], Tuple[List[int], List[int], List[List[float]]]] = {}
        now = datetime.now(timezone.utc)

        for edge in edges:
            src_type = id_to_type.get(edge.source_id)
            dst_type = id_to_type.get(edge.target_id)
            if src_type is None or dst_type is None:
                continue

            src_local = gnn_id_to_local.get(edge.source_id)
            dst_local = gnn_id_to_local.get(edge.target_id)
            if src_local is None or dst_local is None:
                continue

            # Normalize timestamp to time-delta in [0, 1] (1 year window)
            if edge.timestamp:
                try:
                    ts = datetime.fromisoformat(edge.timestamp.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    delta = (now - ts).total_seconds() / (365 * 86400)
                    ts_norm = min(max(delta, 0.0), 1.0)
                except Exception:
                    ts_norm = 0.5
            else:
                ts_norm = 0.5

            triplet = (src_type, edge.gnn_type, dst_type)
            if triplet not in edge_buckets:
                edge_buckets[triplet] = ([], [], [])
            srcs, dsts, attrs = edge_buckets[triplet]
            srcs.append(src_local)
            dsts.append(dst_local)
            attrs.append([edge.weight, ts_norm])

        for (src_t, et, dst_t), (srcs, dsts, attrs) in edge_buckets.items():
            data[src_t, et, dst_t].edge_index = torch.tensor(
                [srcs, dsts], dtype=torch.long
            )
            data[src_t, et, dst_t].edge_attr = torch.tensor(
                attrs, dtype=torch.float32
            )

        logger.info("PyGConverter: HeteroData built — %d node types, %d edge types",
                    len([t for t in GNN_NODE_TYPES if len(type_to_local_ids[t]) > 0]),
                    len(edge_buckets))
        return data


# ─────────────────────────────────────────────────────────────────────────────
# § 10  PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class GNNDatasetPipeline:
    """
    Top-level orchestrator.  Call .run() to execute the full pipeline end-to-end.

    Args:
        neo4j_uri:      bolt://host:port
        neo4j_user:     Neo4j username
        neo4j_password: Neo4j password
        output_dir:     directory where CSV/NPY/JSON files are written
    """

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        output_dir: str = "./gnn_dataset",
    ):
        self._neo4j_uri      = neo4j_uri
        self._neo4j_user     = neo4j_user
        self._neo4j_password = neo4j_password

        self.extractor    = Neo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
        self.enricher     = GraphEnricher()
        self.feat_builder = FeatureBuilder()
        self.exporter     = DatasetExporter(Path(output_dir))
        self.pyg          = PyGConverter()

        # State shared across stages (populated during .run())
        self.nodes:      List[GNNNode] = []
        self.edges:      List[GNNEdge] = []
        self.slug_to_id: Dict[str, int] = {}
        self.features:   Optional[np.ndarray] = None
        self.pyg_data:   Optional[Any] = None

    # ── Stage 1: Extract ───────────────────────────────────────────────────────
    def _stage_extract(self) -> None:
        raw_nodes, raw_edges = self.extractor.extract()
        degree_map = self.extractor.compute_degrees()

        next_id = 0
        for rn in raw_nodes:
            label = (rn.get("labels") or ["Company"])[0]
            gnn_type = LABEL_TO_GNN_TYPE.get(label)
            if gnn_type is None:
                continue
            name = rn.get("name") or rn.get("slug") or f"node_{next_id}"
            slug = slugify(rn.get("slug") or name)
            if slug in self.slug_to_id:
                continue  # deduplicate

            eid = rn["neo4j_eid"]
            impact = float(rn.get("impact_score") or rn.get("risk_score") or 0.0)
            node = GNNNode(
                gnn_id=next_id, gnn_type=gnn_type,
                name=name, slug=slug,
                props={k: v for k, v in rn.items() if k not in ("neo4j_eid", "labels")},
                degree=degree_map.get(eid, 0),
                impact_score=impact,
                source="neo4j",
            )
            self.nodes.append(node)
            self.slug_to_id[slug] = next_id
            next_id += 1

        # Build edge id map (neo4j_eid → gnn_id) for edge wiring
        eid_to_gnn: Dict[str, int] = {}
        for rn in raw_nodes:
            label = (rn.get("labels") or ["Company"])[0]
            if LABEL_TO_GNN_TYPE.get(label) is None:
                continue
            name = rn.get("name") or f"node_{rn['neo4j_eid']}"
            slug = slugify(rn.get("slug") or name)
            gid = self.slug_to_id.get(slug)
            if gid is not None:
                eid_to_gnn[rn["neo4j_eid"]] = gid

        for re_ in raw_edges:
            gnn_etype = REL_TO_GNN_EDGE.get(re_["rel_type"])
            if gnn_etype is None:
                continue
            src_id = eid_to_gnn.get(re_["from_eid"])
            dst_id = eid_to_gnn.get(re_["to_eid"])
            if src_id is None or dst_id is None:
                continue
            # Weight: prefer explicit weight, then impact_score × confidence
            impact  = float(re_.get("impact_score") or 0.0)
            conf    = float(re_.get("confidence")   or 1.0)
            weight  = float(re_.get("weight") or (impact * conf) or 1.0)
            ts = re_.get("timestamp")
            if ts is not None:
                ts = str(ts)
            self.edges.append(GNNEdge(
                source_id=src_id, target_id=dst_id,
                gnn_type=gnn_etype, weight=weight,
                timestamp=ts,
                source_system=re_.get("source_system") or "neo4j",
            ))

        logger.info("Stage 1 — extracted %d nodes, %d edges", len(self.nodes), len(self.edges))
        self._next_id = next_id

    # ── Stage 2: Enrich ────────────────────────────────────────────────────────
    def _stage_enrich(self) -> None:
        self.nodes, self.edges, self.slug_to_id, self._next_id = \
            self.enricher.enrich(self.nodes, self.edges, self.slug_to_id, self._next_id)
        logger.info("Stage 2 — enriched graph: %d nodes, %d edges",
                    len(self.nodes), len(self.edges))

    # ── Stage 3: Compute degrees (after enrichment) ────────────────────────────
    def _stage_update_degrees(self) -> None:
        degree_counter: Dict[int, int] = {n.gnn_id: 0 for n in self.nodes}
        for edge in self.edges:
            degree_counter[edge.target_id] = degree_counter.get(edge.target_id, 0) + 1
        for node in self.nodes:
            # Use max of Neo4j degree and computed in-graph degree
            node.degree = max(node.degree, degree_counter.get(node.gnn_id, 0))

    # ── Stage 4: Build features ────────────────────────────────────────────────
    def _stage_features(self) -> None:
        self.features = self.feat_builder.build(self.nodes)
        logger.info("Stage 4 — features built: %s", self.features.shape)

    # ── Stage 5: Export ────────────────────────────────────────────────────────
    def _stage_export(self) -> Dict[str, Path]:
        return self.exporter.export(self.nodes, self.edges, self.features)

    # ── Stage 6: Convert to PyG ────────────────────────────────────────────────
    def _stage_pyg(self) -> None:
        self.pyg_data = self.pyg.convert(self.nodes, self.edges, self.features)

    # ── Stage 7 (optional): Write enrichment back to Neo4j ────────────────────
    def push_to_neo4j(self) -> Dict[str, int]:
        """
        Write all enriched (predefined) nodes and edges back into Neo4j so they
        are immediately visible in the frontend KG Explorer.

        Must be called AFTER .run() (or at least after _stage_enrich()).
        Uses MERGE — fully idempotent, safe to call multiple times.

        Returns {'nodes': N, 'edges': E} counts of written objects.
        """
        if not self.nodes:
            raise RuntimeError("Pipeline has not been run yet — call .run() first.")

        writer = Neo4jWriter(self._neo4j_uri, self._neo4j_user, self._neo4j_password)
        try:
            counts = writer.push_all(self.nodes, self.edges)
        finally:
            writer.close()

        logger.info(
            "push_to_neo4j: %d nodes + %d edges written to Neo4j",
            counts["nodes"], counts["edges"],
        )
        return counts

    # ── Full pipeline ──────────────────────────────────────────────────────────
    def run(self, skip_pyg: bool = False) -> Dict[str, Any]:
        """
        Execute all pipeline stages.

        Returns a summary dict with:
          - "paths"    : {name: Path} for the four output files
          - "stats"    : basic counts
          - "pyg_data" : HeteroData | None
        """
        logger.info("=== GNN Dataset Pipeline START ===")
        try:
            self._stage_extract()
            self._stage_enrich()
            self._stage_update_degrees()
            self._stage_features()
            paths = self._stage_export()
            if not skip_pyg:
                self._stage_pyg()
        finally:
            self.extractor.close()

        summary = {
            "paths":    paths,
            "pyg_data": self.pyg_data,
            "stats": {
                "num_nodes":  len(self.nodes),
                "num_edges":  len(self.edges),
                "feature_dim": int(self.features.shape[1]) if self.features is not None else 0,
                "node_types": {t: sum(1 for n in self.nodes if n.gnn_type == t)
                               for t in GNN_NODE_TYPES},
                "edge_types": {et: sum(1 for e in self.edges if e.gnn_type == et)
                               for et in GNN_EDGE_TYPES},
            },
        }
        logger.info("=== GNN Dataset Pipeline END — %d nodes / %d edges ===",
                    len(self.nodes), len(self.edges))
        return summary


# ─────────────────────────────────────────────────────────────────────────────
# § 11  SIMULATE EVENT IMPACT  (Bonus)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_event_impact(
    event_name: str,
    affected_entities: List[Dict[str, str]],
    impact_score: float = 0.7,
    pipeline: Optional[GNNDatasetPipeline] = None,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "talan_neo4j",
    output_dir: str = "./gnn_simulation",
) -> Dict[str, Any]:
    """
    Inject a hypothetical event into the graph and prepare it for GNN inference.

    Workflow:
      1. Build (or reuse) the base GNN dataset
      2. Create a new Event node
      3. Connect it to the specified entities with IMPACTS edges
      4. Rebuild the feature matrix for the new graph
      5. Return the updated HeteroData + dataset paths

    Args:
        event_name:        Human-readable event description
            e.g. "ECB emergency rate hike +100bps"
        affected_entities: List of {"name": ..., "type": ...} dicts
            e.g. [{"name": "Banking & Finance", "type": "Sector"},
                  {"name": "Talan", "type": "Company"}]
        impact_score:      Strength of impact [0, 1]
        pipeline:          Existing GNNDatasetPipeline (reuse if already built)
        neo4j_uri/user/password: Connection params (only used if pipeline is None)
        output_dir:        Directory for simulation output files

    Returns:
        {
            "event_node":  GNNNode,
            "new_edges":   List[GNNEdge],
            "pyg_data":    HeteroData | None,
            "paths":       {name: Path},
            "stats":       {...},
        }
    """
    # ── 1. Obtain base graph ───────────────────────────────────────────────────
    if pipeline is None:
        pipeline = GNNDatasetPipeline(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            output_dir=output_dir,
        )
        pipeline.run(skip_pyg=True)  # build base graph without PyG conversion
    else:
        # If pipeline already ran, repoint its exporter to the simulation dir
        pipeline.exporter = DatasetExporter(Path(output_dir))

    # Work on copies so the original pipeline state is preserved
    sim_nodes = list(pipeline.nodes)
    sim_edges = list(pipeline.edges)
    sim_slug_to_id = dict(pipeline.slug_to_id)
    next_id = max((n.gnn_id for n in sim_nodes), default=-1) + 1

    # ── 2. Create the hypothetical event node ─────────────────────────────────
    event_slug = slugify(event_name)
    if event_slug in sim_slug_to_id:
        event_node = next(n for n in sim_nodes if n.slug == event_slug)
        logger.info("simulate_event_impact: event node already exists — id=%d", event_node.gnn_id)
    else:
        event_node = GNNNode(
            gnn_id=next_id, gnn_type="Event",
            name=event_name, slug=event_slug,
            props={"description": event_name, "impact_score": impact_score},
            impact_score=impact_score,
            source="simulation",
        )
        sim_nodes.append(event_node)
        sim_slug_to_id[event_slug] = next_id
        next_id += 1

    # ── 3. Connect event to affected entities ──────────────────────────────────
    new_edges: List[GNNEdge] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for entity in affected_entities:
        entity_slug = slugify(entity["name"])
        entity_id = sim_slug_to_id.get(entity_slug)

        # Auto-create entity node if it doesn't exist yet
        if entity_id is None:
            gnn_type = entity.get("type", "Company")
            if gnn_type not in GNN_NODE_TYPES:
                gnn_type = "Company"
            new_node = GNNNode(
                gnn_id=next_id, gnn_type=gnn_type,
                name=entity["name"], slug=entity_slug,
                source="simulation",
            )
            sim_nodes.append(new_node)
            sim_slug_to_id[entity_slug] = next_id
            entity_id = next_id
            next_id += 1

        edge = GNNEdge(
            source_id=event_node.gnn_id,
            target_id=entity_id,
            gnn_type="IMPACTS",
            weight=impact_score,
            timestamp=timestamp,
            source_system="simulation",
        )
        sim_edges.append(edge)
        new_edges.append(edge)
        logger.info("simulate_event_impact: %r → IMPACTS → %r (weight=%.2f)",
                    event_name, entity["name"], impact_score)

    # ── 4. Recompute degrees and rebuild features ──────────────────────────────
    degree_counter: Dict[int, int] = {n.gnn_id: n.degree for n in sim_nodes}
    for e in sim_edges:
        degree_counter[e.target_id] = degree_counter.get(e.target_id, 0) + 1
    for n in sim_nodes:
        n.degree = degree_counter.get(n.gnn_id, 0)

    feat_builder = FeatureBuilder()
    sim_features = feat_builder.build(sim_nodes)

    # ── 5. Export simulation dataset ───────────────────────────────────────────
    exporter = DatasetExporter(Path(output_dir))
    paths = exporter.export(sim_nodes, sim_edges, sim_features)

    # ── 6. Convert to PyG for immediate inference ──────────────────────────────
    pyg_data = PyGConverter().convert(sim_nodes, sim_edges, sim_features)

    return {
        "event_node": event_node,
        "new_edges":  new_edges,
        "pyg_data":   pyg_data,
        "paths":      paths,
        "stats": {
            "num_nodes":  len(sim_nodes),
            "num_edges":  len(sim_edges),
            "event_name": event_name,
            "connections": len(new_edges),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# § 12  CONVENIENCE LOADER  (re-load a saved dataset without Neo4j)
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(dataset_dir: str) -> Dict[str, Any]:
    """
    Reload a previously exported dataset from disk (no Neo4j required).

    Returns:
        {
            "nodes":    List[GNNNode],
            "edges":    List[GNNEdge],
            "features": np.ndarray,
            "metadata": dict,
            "pyg_data": HeteroData | None,
        }
    """
    base = Path(dataset_dir)
    # Nodes
    nodes: List[GNNNode] = []
    slug_to_id: Dict[str, int] = {}
    with open(base / "nodes.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            node = GNNNode(
                gnn_id=int(row["id"]),
                gnn_type=row["type"],
                name=row["name"],
                slug=row["slug"],
                source=row.get("source", "neo4j"),
            )
            nodes.append(node)
            slug_to_id[row["slug"]] = node.gnn_id

    # Edges
    edges: List[GNNEdge] = []
    with open(base / "edges.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            edges.append(GNNEdge(
                source_id=int(row["source"]),
                target_id=int(row["target"]),
                gnn_type=row["type"],
                weight=float(row["weight"]),
                timestamp=row.get("timestamp") or None,
                source_system=row.get("source_system", "neo4j"),
            ))

    features = np.load(str(base / "node_features.npy"))
    metadata = json.loads((base / "metadata.json").read_text(encoding="utf-8"))
    pyg_data = PyGConverter().convert(nodes, edges, features)

    logger.info("load_dataset: %d nodes, %d edges from %s", len(nodes), len(edges), base)
    return {
        "nodes": nodes, "edges": edges,
        "features": features, "metadata": metadata,
        "pyg_data": pyg_data, "slug_to_id": slug_to_id,
    }
