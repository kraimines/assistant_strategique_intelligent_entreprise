"""TemporalDecay — per-relation exponential half-life weighting (§3(b)).

    τ(e) = exp(-ln(2) · Δ_t / λ_r)

λ_r is read from the EdgeTypePolicy (which in turn pulls it from the
:CompatibilityRule table in Neo4j). Default fallbacks are encoded here so
the module is still useful even when Neo4j is unreachable.

Use cases:

  * weight a single edge: ``decay.tau(edge, now)``
  * aggregate over a path: ``decay.path_freshness(path)`` returns the
    geometric mean of edge τ's so a single very-old edge cannot drag the
    whole path to zero (which an arithmetic mean would).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

LN2 = math.log(2.0)

# Fallback half-lives (days) by relation category — used only if no rule found
DEFAULT_HALF_LIFE_DAYS = {
    "cyber":         14.0,
    "competitive":   60.0,
    "regulatory":    180.0,
    "macro":         120.0,
    "supply_chain":  45.0,
    "sector":        90.0,
    "event":         30.0,
    "structural":    9999.0,
    "evidence":      14.0,
    "default":       90.0,
}


class TemporalDecay:
    def __init__(self, edge_policy=None):
        self._edge_policy = edge_policy

    # ── Per-edge ─────────────────────────────────────────────────────────────

    def tau(self, edge: Dict[str, Any], now: Optional[datetime] = None) -> float:
        """Decay weight for a single edge."""
        # Trust a precomputed value if the WorldModel already wrote one.
        if isinstance(edge.get("freshness_score"), (int, float)) and edge["freshness_score"] > 0:
            return float(edge["freshness_score"])

        ts = edge.get("timestamp")
        if ts is None:
            return 0.5  # unknown timestamp → moderate prior

        # Parse the timestamp robustly
        if isinstance(ts, str):
            try:
                ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return 0.5
        elif isinstance(ts, datetime):
            ts_dt = ts
        else:
            return 0.5

        now_dt = now or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)

        age_days = max(0.0, (now_dt - ts_dt).total_seconds() / 86400.0)

        half_life = self._half_life_for(edge)
        return math.exp(-LN2 * age_days / max(half_life, 1.0))

    def _half_life_for(self, edge: Dict[str, Any]) -> float:
        # Prefer attribute on the edge first (set by EdgeTypePolicy.gate_edges)
        if isinstance(edge.get("half_life_days"), (int, float)):
            return float(edge["half_life_days"])
        # Then ask the policy
        if self._edge_policy is not None:
            try:
                return float(self._edge_policy.half_life(
                    edge.get("type") or edge.get("relation_type") or "",
                    edge.get("src_label") or "",
                    edge.get("dst_label") or "",
                ))
            except Exception:  # noqa: BLE001
                pass
        # Last resort: category lookup
        cat = edge.get("category") or "default"
        return DEFAULT_HALF_LIFE_DAYS.get(cat, DEFAULT_HALF_LIFE_DAYS["default"])

    # ── Path aggregation ─────────────────────────────────────────────────────

    def path_freshness(self, edges: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> float:
        """Geometric mean of per-edge τ — robust to a single old edge."""
        taus = [max(1e-6, self.tau(e, now)) for e in edges]
        if not taus:
            return 1.0
        log_sum = sum(math.log(t) for t in taus)
        return math.exp(log_sum / len(taus))
