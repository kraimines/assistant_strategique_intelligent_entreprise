"""EdgeTypePolicy — compatibility matrix between (relation_type, src_label, dst_label).

Backs §3(c) of the refactor plan. The policy plays three roles:

  1. **Hard gate**  : edges with α=0 are dropped from the temporal neighbor
                      store (no propagation through them at all).
  2. **Soft mask**  : edges with α<1 receive an additive log(α) bias on the
                      TGAT attention logits, suppressing their influence
                      without zeroing them out.
  3. **Decay key**  : every rule carries a per-relation half-life (days)
                      that the temporal-decay scorer reads from here so we
                      never have to keep two sources of truth in sync.

The matrix lives in Neo4j as `:CompatibilityRule` nodes (seeded by
``improve_gnn_data.py``). At process startup we pull it once into memory.

Math:

    α(e) = matrix[ rel_type(e), label(src), label(dst) ]   ∈ {0, 0.3, 0.7, 1.0}
    bias = log(α(e) + ε),  ε = 1e-3

A missing rule defaults to α=0.5, half_life=90d — i.e. mildly suppressed but
not blocked, so a new relation type does not silently disable propagation.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_ALPHA = 0.55   # restored — unknown causal edges are suppressed but not blocked
DEFAULT_HALF_LIFE_DAYS = 90.0
EPS = 1e-3

# Tier-2 (semantic-only) relations: always α=0, regardless of what the
# Neo4j compatibility matrix says. These are informational, never causal.
# Mentioning someone in an article does not transmit economic risk.
TIER2_RELATIONS: frozenset = frozenset({
    "MENTIONS", "CORRELATED_WITH", "ASSOCIATED_WITH",
    "REFERS_TO", "DISCUSSES",
})

# Tier-1 (structural) relations: identity / membership, propagation only
# when chained with at least one Tier-0 (causal) edge.
TIER1_RELATIONS: frozenset = frozenset({
    "BELONGS_TO_SECTOR", "OPERATES_IN", "SERVES_SECTOR",
    "LOCATED_IN", "OWNS", "PART_OF",
})


@dataclass(frozen=True)
class CompatibilityRule:
    rel_type:       str
    src_label:      str
    dst_label:      str
    alpha:          float
    half_life_days: float
    category:       str

    @property
    def is_blocked(self) -> bool:
        return self.alpha <= 0.0


class EdgeTypePolicy:
    """In-memory cache around the Neo4j CompatibilityRule table.

    Construction:
        >>> policy = EdgeTypePolicy.from_world_model(world_model)
        >>> policy.alpha("CAUSES_IMPACT_ON", "Competitor", "Company")
        1.0
        >>> kept = policy.gate_edges(edges)
        >>> bias = policy.attention_bias(edges)
    """

    def __init__(self, matrix: Dict[Tuple[str, str, str], CompatibilityRule]):
        self._matrix = matrix

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, raw: Dict[Tuple[str, str, str], Dict[str, Any]]) -> "EdgeTypePolicy":
        matrix = {
            key: CompatibilityRule(
                rel_type=key[0],
                src_label=key[1],
                dst_label=key[2],
                alpha=float(val.get("alpha", DEFAULT_ALPHA)),
                half_life_days=float(val.get("half_life_days", DEFAULT_HALF_LIFE_DAYS)),
                category=str(val.get("category", "default")),
            )
            for key, val in raw.items()
        }
        return cls(matrix)

    @classmethod
    def from_world_model(cls, world_model) -> "EdgeTypePolicy":
        try:
            raw = world_model.get_compatibility_matrix()
        except Exception as exc:  # noqa: BLE001
            logger.warning("EdgeTypePolicy: could not load matrix from Neo4j (%s) — using empty default", exc)
            raw = {}
        if not raw:
            logger.warning("EdgeTypePolicy: matrix is empty — every edge defaults to α=%.2f", DEFAULT_ALPHA)
        return cls.from_dict(raw)

    # ── Lookups ──────────────────────────────────────────────────────────────

    def lookup(self, rel_type: str, src_label: str, dst_label: str) -> CompatibilityRule:
        # Tier-2 relations are always blocked — semantic, not causal.
        if rel_type in TIER2_RELATIONS:
            return CompatibilityRule(
                rel_type=rel_type,
                src_label=src_label,
                dst_label=dst_label,
                alpha=0.0,
                half_life_days=DEFAULT_HALF_LIFE_DAYS,
                category="semantic",
            )
        rule = self._matrix.get((rel_type, src_label, dst_label))
        if rule is not None:
            # Even matrix-loaded MENTIONS-style relations are hard-blocked.
            if rule.rel_type in TIER2_RELATIONS and rule.alpha > 0:
                return CompatibilityRule(
                    rel_type=rule.rel_type,
                    src_label=rule.src_label,
                    dst_label=rule.dst_label,
                    alpha=0.0,
                    half_life_days=rule.half_life_days,
                    category="semantic",
                )
            return rule
        # Unknown triple → low default (not blocked, but suppressed)
        return CompatibilityRule(
            rel_type=rel_type,
            src_label=src_label,
            dst_label=dst_label,
            alpha=DEFAULT_ALPHA,
            half_life_days=DEFAULT_HALF_LIFE_DAYS,
            category="default",
        )

    def alpha(self, rel_type: str, src_label: str, dst_label: str) -> float:
        return self.lookup(rel_type, src_label, dst_label).alpha

    def half_life(self, rel_type: str, src_label: str, dst_label: str) -> float:
        return self.lookup(rel_type, src_label, dst_label).half_life_days

    # ── Edge filtering ───────────────────────────────────────────────────────

    def gate_edges(self, edges: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Drop α==0 edges and annotate the rest with `relation_strength` and
        `half_life_days` in-place. The annotation is what TGAT, the temporal
        decay scorer and the path ranker all read downstream."""
        kept: List[Dict[str, Any]] = []
        for e in edges:
            rule = self.lookup(
                e.get("type") or e.get("relation_type") or "",
                e.get("src_label") or e.get("from_label") or "",
                e.get("dst_label") or e.get("to_label") or "",
            )
            if rule.is_blocked:
                continue
            # only set relation_strength if the edge does not already carry one;
            # writers that already filled it (e.g. WorldModel._merge_causal_rel_cypher)
            # win, so manual overrides survive.
            if e.get("relation_strength") in (None, 0):
                e["relation_strength"] = rule.alpha
            e.setdefault("half_life_days", rule.half_life_days)
            e.setdefault("category", rule.category)
            kept.append(e)
        return kept

    def attention_bias(self, edges: Iterable[Dict[str, Any]]) -> List[float]:
        """Per-edge additive bias for TGAT attention logits."""
        out: List[float] = []
        for e in edges:
            alpha = float(e.get("relation_strength") or self.alpha(
                e.get("type") or "",
                e.get("src_label") or "",
                e.get("dst_label") or "",
            ))
            out.append(math.log(alpha + EPS))
        return out

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        if not self._matrix:
            return {"rules": 0}
        alphas = [r.alpha for r in self._matrix.values()]
        return {
            "rules":   len(self._matrix),
            "blocked": sum(1 for a in alphas if a == 0.0),
            "weak":    sum(1 for a in alphas if 0 < a < 0.5),
            "full":    sum(1 for a in alphas if a >= 1.0),
            "min":     min(alphas),
            "max":     max(alphas),
        }

    def categories(self) -> List[str]:
        return sorted({r.category for r in self._matrix.values()})

    def __len__(self) -> int:
        return len(self._matrix)

    def __contains__(self, key: Tuple[str, str, str]) -> bool:
        return key in self._matrix

    def get_rule(self, key: Tuple[str, str, str]) -> Optional[CompatibilityRule]:
        return self._matrix.get(key)
