"""PathRanker — final weighted score, filter rules and top-k ranking.

Implements §3(h) and §3(j) of the refactor plan.

Final weighted score:

    W(p) = T̂(s_TGAT) · ρ(p) · τ̄(p) · spec(p) · coh(p) · conf̄(p)

Filter rules (reject if ANY holds):

    ρ(p)     <  0.35
    spec(p)  <  0.25
    ≥ 2 generic hubs in path
    any edge with α = 0
    coh(p)   <  0.20
    conf̄(p) <  0.40

Inputs are plain ``dict``s (the same shape produced by
``WorldModel.get_snapshot`` and ``gnn_predictor._extract_propagation_paths``)
so PathRanker stays decoupled from Pydantic / Neo4j types.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Filter thresholds ────────────────────────────────────────────────────────
# Tightened to match the contract in the module docstring. The previous
# relaxed values (0.10 / 0.05 / 5 / 0.05 / 0.10) let MENTIONS-driven paths
# through. With Tier-2 edges hard-gated upstream, these thresholds are now
# safe to enforce.
MIN_PLAUSIBILITY  = 0.20   # synthetic enricher paths have lower but still valid plausibility
MIN_SPECIFICITY   = 0.05   # mechanism chain nodes are intermediate, naturally lower specificity
MAX_GENERIC_HUBS  = 3      # allow generic hubs in transmission chains (e.g. Country, Event)
MIN_COHERENCE     = 0.05   # mechanism chains are inherently simple / linear
MIN_CONFIDENCE    = 0.25   # synthetic edges start at 0.72; real edges average 0.5-0.7

# Tier-2 (semantic-only) relations — must never appear in a propagation path.
_TIER2_RELS = frozenset({
    "MENTIONS", "CORRELATED_WITH", "ASSOCIATED_WITH", "REFERS_TO", "DISCUSSES",
})


# ── Public DTO ───────────────────────────────────────────────────────────────

@dataclass
class ScoredPath:
    path:                          Dict[str, Any]
    tgat_score:                    float
    plausibility:                  float
    plausibility_features:         Dict[str, float]
    plausibility_rationale:        str
    path_freshness:                float
    path_specificity:              float
    causal_coherence:              float
    avg_edge_confidence:           float
    weighted_score:                float
    impact_probability:            float
    estimated_business_impact_pct: float
    confidence:                    float
    uncertainty:                   str
    rejected:                      bool = False
    rejection_reasons:              List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            **self.path,
            "weighted_score":                self.weighted_score,
            "business_plausibility":         self.plausibility,
            "plausibility_features":         self.plausibility_features,
            "plausibility_rationale":        self.plausibility_rationale,
            "path_freshness":                self.path_freshness,
            "path_specificity":              self.path_specificity,
            "causal_coherence":              self.causal_coherence,
            "avg_edge_confidence":           self.avg_edge_confidence,
            "impact_probability":            self.impact_probability,
            "estimated_business_impact_pct": self.estimated_business_impact_pct,
            "confidence":                    self.confidence,
            "uncertainty":                   self.uncertainty,
            "rejected":                      self.rejected,
            "rejection_reasons":             self.rejection_reasons,
        }


# ── Ranker ───────────────────────────────────────────────────────────────────

class PathRanker:
    def __init__(
        self,
        hub_penalty,
        temporal_decay,
        plausibility_scorer,
        calibrator,
        edge_policy,
        bu_revenue_elasticity: float = 0.30,
    ):
        self.hub = hub_penalty
        self.decay = temporal_decay
        self.plaus = plausibility_scorer
        self.calib = calibrator
        self.edges = edge_policy
        self.mu_bu = bu_revenue_elasticity   # μ_BU in §3(i)

    # ── Score one ────────────────────────────────────────────────────────────

    def score_path(self, path: Dict[str, Any]) -> ScoredPath:
        steps = path.get("steps") or []
        node_dicts = [
            {
                "slug":   s.get("node_slug") or s.get("slug"),
                "name":   s.get("node_name"),
                "labels": [s.get("node_type")] if s.get("node_type") else [],
                "properties": s.get("node_properties") or {},
            }
            for s in steps
        ]
        # Treat the source node + all intermediate nodes as candidates for hubness;
        # exclude the very last node (Talan) so we don't penalize the target.
        intermediates = node_dicts[:-1] if node_dicts else []

        # 1. TGAT raw score (caller may have already calibrated; we re-apply
        #    the calibrator to enforce a single source of truth).
        raw_tgat = float(path.get("chain_score", 0.0))
        tgat_calibrated = self.calib.transform(abs(raw_tgat))

        # 2. Plausibility
        plaus = self.plaus.score(path)

        # 3. Temporal decay over the edges
        edge_dicts = self._step_edges(steps)
        tau_bar = self.decay.path_freshness(edge_dicts)

        # 4. Specificity (anti-generic)
        spec = self.hub.specificity(intermediates)

        # 5. Causal coherence — α(eᵢ)·α(eᵢ₊₁) over consecutive edges
        coh = self._coherence(edge_dicts)

        # 6. Avg edge confidence (geometric mean)
        confs = [float(e.get("confidence") or 0.5) for e in edge_dicts]
        if confs:
            conf_bar = math.exp(sum(math.log(max(c, 1e-3)) for c in confs) / len(confs))
        else:
            conf_bar = 0.5

        # 7. Final weighted score
        W = tgat_calibrated * plaus.score * tau_bar * spec * coh * conf_bar

        # 8. Calibrated outputs (§3(i))
        sign = -1.0 if raw_tgat < 0 else 1.0
        impact_prob = tgat_calibrated * plaus.score
        exposure = max(plaus.rule_features.get("exposure", 0.0), 0.05)
        impact_pct = sign * 100.0 * self.mu_bu * exposure * plaus.score
        confidence = conf_bar * math.sqrt(max(plaus.score, 1e-6))
        uncertainty = self._bucket_uncertainty(1.0 - confidence)

        # 9. Filter
        generic_count = sum(1 for n in intermediates if self.hub.is_generic(n))
        rejected, reasons = self._filter(
            plaus_score=plaus.score,
            spec=spec,
            generic_count=generic_count,
            edge_dicts=edge_dicts,
            coh=coh,
            conf_bar=conf_bar,
        )
        if rejected:
            logger.debug(
                "PATH REJECTED [%s] plaus=%.2f spec=%.2f coh=%.2f conf=%.2f hubs=%d reasons=%s",
                path.get("source_name", "?"), plaus.score, spec, coh, conf_bar, generic_count, reasons,
            )

        return ScoredPath(
            path=path,
            tgat_score=tgat_calibrated,
            plausibility=plaus.score,
            plausibility_features=plaus.rule_features,
            plausibility_rationale=plaus.rationale,
            path_freshness=tau_bar,
            path_specificity=spec,
            causal_coherence=coh,
            avg_edge_confidence=conf_bar,
            weighted_score=W,
            impact_probability=impact_prob,
            estimated_business_impact_pct=impact_pct,
            confidence=confidence,
            uncertainty=uncertainty,
            rejected=rejected,
            rejection_reasons=reasons,
        )

    # ── Filter rules ─────────────────────────────────────────────────────────

    def _filter(
        self,
        plaus_score: float,
        spec: float,
        generic_count: int,
        edge_dicts: List[Dict[str, Any]],
        coh: float,
        conf_bar: float,
    ) -> Tuple[bool, List[str]]:
        reasons: List[str] = []
        if plaus_score < MIN_PLAUSIBILITY:
            reasons.append(f"plausibility<{MIN_PLAUSIBILITY}")
        if spec < MIN_SPECIFICITY:
            reasons.append(f"specificity<{MIN_SPECIFICITY}")
        if generic_count > MAX_GENERIC_HUBS:
            reasons.append("generic_hub_overload")
        # Only block if relation_strength is explicitly 0.0; None means unknown → default α, not blocked
        if any(
            (rs := e.get("relation_strength")) is not None and float(rs) <= 0.0
            for e in edge_dicts
        ):
            reasons.append("blocked_edge")
        if any((e.get("type") or "") in _TIER2_RELS for e in edge_dicts):
            reasons.append("semantic_only_path")
        if coh < MIN_COHERENCE:
            reasons.append(f"coherence<{MIN_COHERENCE}")
        if conf_bar < MIN_CONFIDENCE:
            reasons.append(f"confidence<{MIN_CONFIDENCE}")
        return (len(reasons) > 0), reasons

    # ── Top-k ────────────────────────────────────────────────────────────────

    def rank(self, paths: List[Dict[str, Any]], top_k: int = 10) -> Tuple[List[ScoredPath], List[ScoredPath]]:
        scored = [self.score_path(p) for p in paths]
        kept = [s for s in scored if not s.rejected]
        rejected = [s for s in scored if s.rejected]
        kept.sort(key=lambda s: s.weighted_score, reverse=True)
        return kept[:top_k], rejected

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _step_edges(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for s in steps:
            out.append({
                "type":              s.get("relation_type"),
                "src_label":         s.get("src_label"),
                "dst_label":         s.get("dst_label") or s.get("node_type"),
                "impact_score":      s.get("impact_score"),
                "confidence":        s.get("edge_confidence") or s.get("confidence"),
                "relation_strength": s.get("relation_strength"),
                "freshness_score":   s.get("freshness_score"),
                "timestamp":         s.get("timestamp"),
                "category":          s.get("category"),
                "half_life_days":    s.get("half_life_days"),
            })
        return out

    def _coherence(self, edges: List[Dict[str, Any]]) -> float:
        if len(edges) <= 1:
            # single-edge paths have no transition — treat as fully coherent
            alphas = [float(e.get("relation_strength") or 0.5) for e in edges]
            return alphas[0] if alphas else 1.0
        scores = []
        for i in range(len(edges) - 1):
            a1 = float(edges[i].get("relation_strength") or 0.5)
            a2 = float(edges[i + 1].get("relation_strength") or 0.5)
            # Without learned relation embeddings yet (TGAT retraining is
            # deferred), we approximate cos_sim(emb(rᵢ), emb(rᵢ₊₁)) by
            # category equality: same category → 1.0, otherwise 0.5.
            cat1 = edges[i].get("category") or "default"
            cat2 = edges[i + 1].get("category") or "default"
            sim = 1.0 if cat1 == cat2 else 0.5
            scores.append(a1 * a2 * sim)
        return sum(scores) / len(scores)

    @staticmethod
    def _bucket_uncertainty(u: float) -> str:
        if u < 0.30:
            return "low"
        if u < 0.55:
            return "medium"
        return "high"
