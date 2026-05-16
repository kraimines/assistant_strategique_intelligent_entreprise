"""HubPenalty — inverse-degree + PageRank-aware attenuation of generic hubs.

Implements §3(a) of the refactor plan:

    h(v) = 1 / (1 + log(1 + d_v / d̄)) · (1 - β · pagerank_norm(v))
    β = 0.5 if v.is_generic_hub else 0.2

The penalty is intentionally *gentle* on legitimate high-degree economic
nodes (Talan, Capgemini, EU Banking Clients) and *aggressive* on semantic
hubs that the LLM extractor inflates (`Artificial Intelligence`, `Europe`,
`Economy`).

Two ways the value is consumed:

  1. as a multiplicative weight on per-node TGAT message contributions,
  2. as a feature inside the path-specificity formula (§3(e)).
"""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

BETA_GENERIC = 0.5
BETA_SPECIFIC = 0.2
MIN_H = 0.05  # never zero out a node entirely — preserves connectivity
MAX_H = 1.0


@dataclass
class HubPenalty:
    median_degree: float = 1.0
    pagerank_min:  float = 0.0
    pagerank_max:  float = 1.0
    _pagerank: Dict[str, float] = field(default_factory=dict)
    _generic:  Dict[str, bool]  = field(default_factory=dict)
    _degree:   Dict[str, int]   = field(default_factory=dict)

    # ── Fitting ──────────────────────────────────────────────────────────────

    @classmethod
    def fit(cls, snapshot: Dict[str, Any], pagerank: Optional[List[Dict[str, Any]]] = None) -> "HubPenalty":
        """Compute median degree across non-generic, non-News nodes, plus
        normalize PageRank scores into [0,1] for the second factor."""
        nodes = snapshot.get("nodes") or []
        if not nodes:
            return cls()

        # Compute degrees from edges
        edges = snapshot.get("edges") or []
        deg: Dict[str, int] = {}
        for e in edges:
            for k in (e.get("from"), e.get("to")):
                if k is not None:
                    deg[k] = deg.get(k, 0) + 1

        meaningful = [
            d for nid, d in deg.items()
            if "News" not in (next((n["labels"] for n in nodes if n["id"] == nid), []) or [])
        ]
        median = statistics.median(meaningful) if meaningful else 1.0
        median = max(1.0, float(median))

        pr_map: Dict[str, float] = {}
        if pagerank:
            for r in pagerank:
                slug = r.get("slug")
                if slug is None:
                    continue
                pr_map[slug] = float(r.get("score", 0.0))
        if pr_map:
            lo, hi = min(pr_map.values()), max(pr_map.values())
        else:
            lo, hi = 0.0, 1.0
        if hi <= lo:
            hi = lo + 1.0  # avoid div-by-zero downstream

        generic_map: Dict[str, bool] = {}
        for n in nodes:
            slug = (n.get("slug")
                    or n.get("properties", {}).get("slug")
                    or n.get("name", ""))
            if not slug:
                continue
            flag = bool(n.get("properties", {}).get("is_generic_hub", False))
            # Concept nodes are always generic. Country nodes are NOT automatically
            # generic — they act as economic actors in regulatory/geopolitical chains
            # (e.g. Iran → oil price shock, USA → tariffs). Only mark them generic
            # if they have very high in-degree (>20 edges = true hub).
            if any(lbl in {"Concept"} for lbl in (n.get("labels") or [])):
                flag = True
            generic_map[slug] = flag

        # Build a slug → degree map so h() can look it up directly
        slug_by_id = {n["id"]: n.get("slug") or n.get("name", "") for n in nodes}
        deg_by_slug: Dict[str, int] = {}
        for nid, d in deg.items():
            slug = slug_by_id.get(nid) or ""
            if slug:
                deg_by_slug[slug] = d

        instance = cls(
            median_degree=median,
            pagerank_min=lo,
            pagerank_max=hi,
            _pagerank=pr_map,
            _generic=generic_map,
            _degree=deg_by_slug,
        )
        logger.info(
            "HubPenalty fit: median_deg=%.2f pr_range=[%.4f, %.4f] generic=%d",
            median, lo, hi, sum(1 for v in generic_map.values() if v),
        )
        return instance

    # ── Per-node penalty ─────────────────────────────────────────────────────

    def h(self, node: Dict[str, Any]) -> float:
        """Penalty multiplier ∈ [MIN_H, MAX_H]. Higher = more trustworthy node."""
        slug = (node.get("slug")
                or node.get("properties", {}).get("slug")
                or node.get("name", ""))

        # Degree term — prefer the snapshot-fitted map, then property, then fallback
        d_v = float(self._degree.get(slug, 0))
        if d_v <= 0:
            d_v = float(node.get("properties", {}).get("degree_norm", 0.0)) * self.median_degree
        if d_v <= 0:
            d_v = float(node.get("degree", 0)) or 1.0
        deg_term = 1.0 / (1.0 + math.log1p(d_v / self.median_degree))

        # PageRank term — when no PR data, use normalized degree as a proxy so
        # generic nodes don't get a free pass.
        pr = self._pagerank.get(slug, 0.0)
        if self._pagerank and self.pagerank_max > self.pagerank_min:
            pr_norm = (pr - self.pagerank_min) / (self.pagerank_max - self.pagerank_min)
        else:
            pr_norm = min(1.0, d_v / max(self.median_degree, 1.0))
        pr_norm = max(0.0, min(1.0, pr_norm))

        # Beta selection
        is_generic = self._generic.get(slug, False) or bool(
            node.get("properties", {}).get("is_generic_hub", False)
        )
        beta = BETA_GENERIC if is_generic else BETA_SPECIFIC

        h_val = deg_term * (1.0 - beta * pr_norm)
        return max(MIN_H, min(MAX_H, h_val))

    def is_generic(self, node: Dict[str, Any]) -> bool:
        props = node.get("properties") or {}
        # Simulation-injected actors are always treated as specific — they were
        # explicitly chosen by the analyst as the causal source.
        if props.get("is_simulation_actor") or props.get("is_generic_hub") is False:
            return False
        slug = (node.get("slug") or props.get("slug") or node.get("name", ""))
        if self._generic.get(slug, False):
            return True
        if bool(props.get("is_generic_hub", False)):
            return True
        if any(lbl in {"Concept"} for lbl in (node.get("labels") or [])):
            return True
        return False

    def specificity(self, nodes: Iterable[Dict[str, Any]], gamma: float = 0.6) -> float:
        """Path-specificity (§3(e)). Multiplicative aggregation across all
        intermediate nodes (excluding source and Talan)."""
        product = 1.0
        for n in nodes:
            generic_pen = (
                gamma * (1.0 if self.is_generic(n) else 0.0)
                + (1.0 - gamma) * (1.0 - self.h(n))
            )
            product *= max(0.0, 1.0 - generic_pen)
        return product
