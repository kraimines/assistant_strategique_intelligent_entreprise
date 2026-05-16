#!/usr/bin/env python3
"""
Financial Impact Scorer — TGAT Continuous Signal Estimator
===========================================================
Replaces the binary causal output of the Temporal Graph Attention Network
with a calibrated, continuous financial impact score in the range [-100%, +100%].

Algorithm pipeline (multiplicative adjustments → tanh normalization):
  base_chain_score
      × entity_importance_multiplier
      × sector_amplification_factor
      × confidence_factor
      × time_horizon_factor
      × propagation_breadth_factor
      × direction_sign
    ──► tanh(·) × MAX_PCT  →  estimated_impact_percent

Calibration anchors (from measured_impacts in kg_events.json):
  COVID-19 pandemic  → Talan  ≈ −42 %  (strong_negative)
  France Relance     → Talan  ≈ +20 %  (moderate_positive)
  Biden BBB          → Talan  ≈  +4 %  (weak_positive / neutral)
  AI boom (general)  → Talan  ≈ +18 %  (weak_to_moderate_positive)

Usage (standalone):
    python impact_scorer.py --event evt_001 --data kg_events.json
    python impact_scorer.py --all --data kg_events.json

Usage (library):
    from impact_scorer import ImpactScorer, build_scorer_input_from_event
    scorer = ImpactScorer()
    result = scorer.score_from_event(event_dict)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS & LOOKUP TABLES
# ──────────────────────────────────────────────────────────────────────────────

# Normalization ceiling — scores above this magnitude are truly systemic
MAX_PCT: float = 65.0

# ── Entity importance weights ─────────────────────────────────────────────────
# MacroIndicators: proxy for systemic reach
MACRO_IMPORTANCE: dict[str, float] = {
    "vix":       1.60,   # volatility index = pure systemic fear gauge
    "cac40":     1.55,   # French market benchmark (Talan is French)
    "sp500":     1.50,
    "nasdaq":    1.45,
    "fed_rate":  1.50,   # monetary policy = structural
    "ecb_rate":  1.50,
    "eur_usd":   1.20,
    "brent":     1.15,
}
MACRO_IMPORTANCE_DEFAULT: float = 1.25

# Sectors: how much a sector amplifies Talan's exposure
SECTOR_IMPORTANCE: dict[str, float] = {
    "it services / esn":              1.50,   # Talan's own sector
    "ai/ml":                          1.45,   # most strategic adjacent sector
    "cloud computing":                1.30,
    "cybersécurité":                  1.20,
    "data & analytics":               1.20,
    "consulting":                     1.10,
    "finance / banque":               1.10,
    "secteur public / gouvernement":  1.15,
    "santé / healthcare":             1.05,
    "industrie / manufacturing":      1.00,
    "énergie":                        0.95,
}
SECTOR_IMPORTANCE_DEFAULT: float = 1.00

# Company size brackets by revenue (M€)
COMPANY_SIZE_BRACKETS: list[tuple[float, float]] = [
    (500_000, 1.40),   # hyperscaler (Amazon, Microsoft, Google)
    (100_000, 1.30),   # mega-cap (Accenture, IBM, Deloitte)
    ( 20_000, 1.20),   # large-cap (Capgemini, SAP, Salesforce)
    (  5_000, 1.10),   # mid-large (Sopra, Atos)
    (  1_000, 1.00),   # mid (Talan ~600 M€)
    (    100, 0.90),   # small
    (      0, 0.80),   # micro / startup
]

# Time horizon → impact magnitude factor
HORIZON_MULTIPLIERS: dict[str, float] = {
    "1w":  1.15,   # immediate shock: peak amplitude, high uncertainty
    "1m":  1.00,   # baseline reference horizon
    "3m":  0.88,
    "6m":  0.76,
    "1y":  0.64,
    "1y+": 0.55,
}
HORIZON_DEFAULT: float = 1.00

# ── Sector/context amplification keyword sets ─────────────────────────────────
# Each entry: (frozenset_of_keywords, applies_to_negative, applies_to_positive, factor)
# Only applied if the event description/name contains at least one keyword.
AMPLIFICATION_RULES: list[tuple[frozenset[str], bool, bool, float]] = [
    # Systemic crises amplify negative shocks strongly
    (frozenset(["pandémie","pandemic","covid","confinement","lockdown"]),    True, False, 1.35),
    (frozenset(["récession","recession","crise financière","effondrement"]), True, False, 1.30),
    (frozenset(["guerre","war","invasion","conflit","géopolitique"]),         True, False, 1.25),
    (frozenset(["tarif","tariffs","trade war","douanier"]),                   True, False, 1.20),
    # Regulatory events amplify both directions
    (frozenset(["rgpd","gdpr","ia act","ai act","réglementation","regulation","compliance"]), True, True, 1.15),
    # Positive structural booms amplify positive shocks
    (frozenset(["ai boom","ia","intelligence artificielle","genai","gpt","llm","agent"]),     False, True, 1.25),
    (frozenset(["cloud","migration cloud","azure","aws"]),                                    False, True, 1.15),
    (frozenset(["relance","stimulus","plan","budget numérique"]),                             False, True, 1.20),
    (frozenset(["acquisition","merger","rachat","consolidation"]),                            True,  True, 1.10),
    # Cybersecurity events (asymmetric amplification)
    (frozenset(["cyberattaque","ransomware","cyberattack","solarwinds","breach"]),            True,  False, 1.20),
]

# ── Impact label thresholds (percentage) ─────────────────────────────────────
IMPACT_LABELS: list[tuple[float, float, str]] = [
    (-100.0, -40.0, "strong_negative"),
    ( -40.0, -15.0, "moderate_negative"),
    ( -15.0,  -5.0, "weak_negative"),
    (  -5.0,   5.0, "neutral"),
    (   5.0,  15.0, "weak_positive"),
    (  15.0,  40.0, "moderate_positive"),
    (  40.0, 100.0, "strong_positive"),
]

# ── Relation types that carry causal weight ───────────────────────────────────
CAUSAL_RELATIONS: frozenset[str] = frozenset(
    ["CAUSES_IMPACT_ON", "INFLUENCES", "IMPACTS", "AFFECTS"]
)

# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Entity:
    id:            str
    type:          str            # "company" | "sector" | "macro" | "country" | "event"
    name:          str = ""
    revenue_eur_m: float | None = None
    country:       str | None   = None
    sector:        str | None   = None
    ticker:        str | None   = None
    headcount:     int | None   = None

    @property
    def importance(self) -> float:
        """Return a 0.8–1.6 importance weight for this entity."""
        t = self.type.lower()
        if t == "macroindicator":
            key = self.id.lower()
            return MACRO_IMPORTANCE.get(key, MACRO_IMPORTANCE_DEFAULT)
        if t == "sector":
            key = self.name.lower()
            return SECTOR_IMPORTANCE.get(key, SECTOR_IMPORTANCE_DEFAULT)
        if t == "company":
            rev = self.revenue_eur_m or 0.0
            for threshold, weight in COMPANY_SIZE_BRACKETS:
                if rev >= threshold:
                    return weight
        return 1.00


@dataclass
class PropagationPath:
    """
    One causal chain: source → [intermediate nodes] → target.
    chain_score is the net impact along this path (pre-computed from the GNN
    or derived by multiplying edge-level impact_scores in the chain).
    """
    source:             str
    target:             str
    chain_score:        float          # signed, e.g. −0.45
    confidence:         float          # 0–1
    time_horizon:       str            # "1w" | "1m" | "3m" | "6m" | "1y+"
    intermediate_nodes: list[str]      = field(default_factory=list)
    relation_types:     list[str]      = field(default_factory=list)

    @property
    def horizon_factor(self) -> float:
        return HORIZON_MULTIPLIERS.get(self.time_horizon, HORIZON_DEFAULT)

    @property
    def is_causal(self) -> bool:
        return any(r in CAUSAL_RELATIONS for r in self.relation_types)


@dataclass
class ScorerInput:
    trigger_event:       str                   # human-readable event name/description
    entities_impacted:   list[Entity]
    propagation_paths:   list[PropagationPath]
    model_binary_output: int                   # 0 or 1
    direction_sign:      int                   # +1 or −1
    event_type:          str = "unknown"       # geopolitical_events | tech_launch | etc.
    event_date:          str = ""


@dataclass
class ScoreBreakdown:
    """Step-by-step contributions to the final score (in % points for display)."""
    base_raw:          float   # tanh-normalised base chain score (%)
    entity_delta:      float   # % change from entity importance
    sector_delta:      float   # % change from sector amplification
    confidence_delta:  float   # % change from confidence penalty
    horizon_delta:     float   # % change from time horizon
    breadth_delta:     float   # % change from propagation breadth
    direction_correction: float  # % change from direction override
    final_pct:         float

    # Raw multiplicative factors (for explainability table)
    entity_multiplier:    float
    sector_amplifier:     float
    confidence_factor:    float
    horizon_factor:       float
    breadth_factor:       float


@dataclass
class ScorerOutput:
    estimated_impact_percent: float
    impact_label:             str
    confidence:               float
    explanation:              str
    breakdown:                ScoreBreakdown
    # Input echo for audit trail
    event_name:               str = ""
    event_type:               str = ""
    event_date:               str = ""


# ──────────────────────────────────────────────────────────────────────────────
# IMPACT SCORER
# ──────────────────────────────────────────────────────────────────────────────

class ImpactScorer:
    """
    Converts a structured GNN input into a calibrated continuous impact score.

    The pipeline is purely deterministic and interpretable — every factor
    has a documented lookup table and can be audited in ScoreBreakdown.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def score(self, inp: ScorerInput) -> ScorerOutput:
        """Full scoring pipeline. Returns a ScorerOutput with breakdown."""
        # ── Step 1: Weighted base chain score ──────────────────────────────
        base_raw_signed = self._base_chain_score(inp.propagation_paths)

        # ── Step 2: Entity importance ───────────────────────────────────────
        entity_mult = self._entity_importance(inp.entities_impacted)

        # ── Step 3: Sector amplification ────────────────────────────────────
        sector_amp = self._sector_amplification(
            inp.trigger_event, inp.event_type, base_raw_signed
        )

        # ── Step 4: Confidence ──────────────────────────────────────────────
        mean_conf  = self._mean_confidence(inp.propagation_paths)
        conf_factor = self._confidence_factor(mean_conf)

        # ── Step 5: Time horizon ─────────────────────────────────────────────
        horizon_f = self._horizon_factor(inp.propagation_paths)

        # ── Step 6: Propagation breadth ─────────────────────────────────────
        breadth_f = self._breadth_factor(
            inp.entities_impacted, inp.propagation_paths
        )

        # ── Combine (multiplicative) ─────────────────────────────────────────
        raw_combined = (
            base_raw_signed
            * entity_mult
            * sector_amp
            * conf_factor
            * horizon_f
            * breadth_f
        )

        # ── Step 7: Direction alignment ──────────────────────────────────────
        raw_combined = self._apply_direction(
            raw_combined, inp.direction_sign, inp.model_binary_output
        )

        # ── Step 8: Normalise → %  ────────────────────────────────────────────
        final_pct = self._normalize(raw_combined)

        # ── Build breakdown (waterfall deltas) ───────────────────────────────
        base_pct       = self._normalize(base_raw_signed)
        after_entity   = self._normalize(base_raw_signed * entity_mult)
        after_sector   = self._normalize(base_raw_signed * entity_mult * sector_amp)
        after_conf     = self._normalize(base_raw_signed * entity_mult * sector_amp * conf_factor)
        after_horizon  = self._normalize(base_raw_signed * entity_mult * sector_amp * conf_factor * horizon_f)
        after_breadth  = self._normalize(base_raw_signed * entity_mult * sector_amp * conf_factor * horizon_f * breadth_f)

        breakdown = ScoreBreakdown(
            base_raw          = base_pct,
            entity_delta      = after_entity  - base_pct,
            sector_delta      = after_sector  - after_entity,
            confidence_delta  = after_conf    - after_sector,
            horizon_delta     = after_horizon - after_conf,
            breadth_delta     = after_breadth - after_horizon,
            direction_correction = final_pct  - after_breadth,
            final_pct         = final_pct,
            entity_multiplier = entity_mult,
            sector_amplifier  = sector_amp,
            confidence_factor = conf_factor,
            horizon_factor    = horizon_f,
            breadth_factor    = breadth_f,
        )

        label       = _assign_label(final_pct)
        explanation = self._build_explanation(inp, breakdown, label, mean_conf)

        return ScorerOutput(
            estimated_impact_percent = round(final_pct, 2),
            impact_label             = label,
            confidence               = round(mean_conf, 3),
            explanation              = explanation,
            breakdown                = breakdown,
            event_name               = inp.trigger_event[:120],
            event_type               = inp.event_type,
            event_date               = inp.event_date,
        )

    def score_from_event(self, event_dict: dict[str, Any],
                         target: str = "talan") -> ScorerOutput:
        """
        Convenience wrapper: parse a raw kg_events.json event dict and score it.
        target — the node ID whose impact we want to estimate (default: 'talan').
        """
        inp = build_scorer_input_from_event(event_dict, target=target)
        return self.score(inp)

    # ── Internal pipeline steps ───────────────────────────────────────────────

    @staticmethod
    def _base_chain_score(paths: list[PropagationPath]) -> float:
        """
        Confidence-weighted mean of chain_scores across all propagation paths.
        Falls back to 0 if no paths are supplied.
        """
        if not paths:
            return 0.0
        total_w  = sum(p.confidence for p in paths)
        if total_w == 0:
            return sum(p.chain_score for p in paths) / len(paths)
        return sum(p.chain_score * p.confidence for p in paths) / total_w

    @staticmethod
    def _entity_importance(entities: list[Entity]) -> float:
        """
        Geometric mean of entity importance weights, clipped to [0.80, 1.60].
        Using geometric mean avoids extreme values from a single outlier.
        """
        if not entities:
            return 1.00
        weights = [e.importance for e in entities]
        geo_mean = math.exp(sum(math.log(max(w, 0.01)) for w in weights) / len(weights))
        return max(0.80, min(1.60, geo_mean))

    @staticmethod
    def _sector_amplification(event_text: str, event_type: str,
                              base_score: float) -> float:
        """
        Scan the event description for amplification keyword groups.
        A keyword group only applies if the event goes in the 'right' direction
        (e.g., crisis amplifiers only apply to negative shocks).
        Returns a multiplicative factor ≥ 1.0.
        """
        text_lower = (event_text + " " + event_type).lower()
        best_factor = 1.00

        for keywords, amp_neg, amp_pos, factor in AMPLIFICATION_RULES:
            if not any(kw in text_lower for kw in keywords):
                continue
            applies = (base_score < 0 and amp_neg) or (base_score > 0 and amp_pos)
            if applies:
                best_factor = max(best_factor, factor)

        return best_factor

    @staticmethod
    def _mean_confidence(paths: list[PropagationPath]) -> float:
        if not paths:
            return 0.70
        return sum(p.confidence for p in paths) / len(paths)

    @staticmethod
    def _confidence_factor(mean_conf: float) -> float:
        """
        Penalise low-confidence estimates.
        ≥0.85 → 1.00 (no penalty), 0.70 → 0.92, 0.50 → 0.80, <0.50 → 0.72
        """
        if mean_conf >= 0.85:
            return 1.00
        if mean_conf >= 0.70:
            return 0.90 + (mean_conf - 0.70) / 0.15 * 0.10   # 0.90–1.00
        if mean_conf >= 0.55:
            return 0.80 + (mean_conf - 0.55) / 0.15 * 0.10   # 0.80–0.90
        return max(0.65, mean_conf)

    @staticmethod
    def _horizon_factor(paths: list[PropagationPath]) -> float:
        """Confidence-weighted mean of per-path horizon factors."""
        if not paths:
            return HORIZON_DEFAULT
        total_w = sum(p.confidence for p in paths)
        if total_w == 0:
            return sum(p.horizon_factor for p in paths) / len(paths)
        return sum(p.horizon_factor * p.confidence for p in paths) / total_w

    @staticmethod
    def _breadth_factor(entities: list[Entity],
                        paths: list[PropagationPath]) -> float:
        """
        More affected entities + longer chains = broader systemic reach.
        Scale: n_entities × avg_chain_length → [0.88, 1.35].
        """
        n_ent = max(len(entities), 1)
        avg_chain_len = (
            sum(len(p.intermediate_nodes) + 2 for p in paths) / len(paths)
            if paths else 2
        )
        breadth_score = n_ent * (avg_chain_len / 2.0)
        # piecewise mapping
        if breadth_score >= 30:
            return 1.35
        if breadth_score >= 20:
            return 1.25
        if breadth_score >= 12:
            return 1.18
        if breadth_score >=  6:
            return 1.10
        if breadth_score >=  3:
            return 1.00
        if breadth_score >=  1:
            return 0.93
        return 0.88

    @staticmethod
    def _apply_direction(raw: float, direction_sign: int,
                         binary_output: int) -> float:
        """
        Enforce sign consistency with direction_sign.
        If binary_output == 0 (no causal link), dampen the magnitude by 25 %
        but do NOT zero it out — the chain score is a stronger signal.
        """
        if direction_sign != 0:
            raw = abs(raw) * direction_sign
        if binary_output == 0:
            raw *= 0.75
        return raw

    @staticmethod
    def _normalize(raw: float) -> float:
        """Map any real-valued raw score → (−MAX_PCT, +MAX_PCT) via tanh."""
        return math.tanh(raw) * MAX_PCT

    @staticmethod
    def _build_explanation(
        inp: ScorerInput,
        bd: ScoreBreakdown,
        label: str,
        mean_conf: float,
    ) -> str:
        sign_word = "positive" if bd.final_pct >= 0 else "negative"
        n_paths   = len(inp.propagation_paths)
        n_ents    = len(inp.entities_impacted)

        dominant_path = ""
        if inp.propagation_paths:
            best = max(inp.propagation_paths, key=lambda p: abs(p.chain_score))
            dominant_path = (
                f" Dominant chain: {best.source} → "
                f"{' → '.join(best.intermediate_nodes)} → {best.target}"
                f" (chain_score={best.chain_score:+.2f}, conf={best.confidence:.2f})."
            )

        adjustments = []
        if abs(bd.entity_delta) > 0.5:
            adjustments.append(
                f"entity importance ×{bd.entity_multiplier:.2f} ({bd.entity_delta:+.1f}%)"
            )
        if abs(bd.sector_delta) > 0.5:
            adjustments.append(
                f"sector amplification ×{bd.sector_amplifier:.2f} ({bd.sector_delta:+.1f}%)"
            )
        if abs(bd.confidence_delta) > 0.3:
            adjustments.append(
                f"confidence penalty ×{bd.confidence_factor:.2f} ({bd.confidence_delta:+.1f}%)"
            )
        if abs(bd.horizon_delta) > 0.3:
            adjustments.append(
                f"time-horizon ×{bd.horizon_factor:.2f} ({bd.horizon_delta:+.1f}%)"
            )
        if abs(bd.breadth_delta) > 0.3:
            adjustments.append(
                f"propagation breadth ×{bd.breadth_factor:.2f} ({bd.breadth_delta:+.1f}%)"
            )
        if abs(bd.direction_correction) > 0.5:
            adjustments.append(
                f"direction override ({bd.direction_correction:+.1f}%)"
            )

        adj_str = (
            "Adjustments applied: " + "; ".join(adjustments) + "."
            if adjustments else "No significant adjustments."
        )

        return (
            f"[{label.upper()}] Estimated {sign_word} impact of {bd.final_pct:+.1f}% "
            f"on Talan from event '{inp.trigger_event[:80]}'. "
            f"Based on {n_paths} propagation path(s) across {n_ents} entity/entities "
            f"with mean confidence {mean_conf:.2f}. "
            f"Base chain score: {bd.base_raw:+.1f}%."
            f"{dominant_path} "
            f"{adj_str}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# LABEL ASSIGNMENT
# ──────────────────────────────────────────────────────────────────────────────

def _assign_label(pct: float) -> str:
    for lo, hi, label in IMPACT_LABELS:
        if lo <= pct < hi:
            return label
    return "strong_positive" if pct >= 40.0 else "strong_negative"


# ──────────────────────────────────────────────────────────────────────────────
# PARSER — kg_events.json → ScorerInput
# ──────────────────────────────────────────────────────────────────────────────

def build_scorer_input_from_event(
    event_dict: dict[str, Any],
    target: str = "talan",
) -> ScorerInput:
    """
    Parse one event dict from kg_events.json and return a ScorerInput.

    Propagation paths are derived by finding chains of edges that originate
    from the event node and eventually reach `target`.
    For direct edges (event → target), the chain is length-1.
    For indirect edges (event → macro/sector → target), the chain is length-2.

    chain_score for a path of length n = product of edge-level impact_scores
    along the chain (geometric product with sign preservation).
    """
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in event_dict.get("nodes", [])}
    edges: list[dict]            = event_dict.get("edges", [])
    gnn                          = event_dict.get("gnn_training", {})
    measured                     = event_dict.get("measured_impacts", {})

    # ── Build adjacency: source → list[(to_id, edge)] ────────────────────────
    adj: dict[str, list[tuple[str, dict]]] = {}
    for e in edges:
        adj.setdefault(e["from_id"], []).append((e["to_id"], e))

    # ── Identify event node(s) (type == "Event") ─────────────────────────────
    event_nodes = [nid for nid, n in nodes_by_id.items() if n.get("type") == "Event"]

    # ── Build propagation paths ───────────────────────────────────────────────
    paths: list[PropagationPath] = []

    # Time horizon from gnn_training
    raw_horizon = gnn.get("horizon", "1m")
    horizon_map = {"1w": "1w", "1m": "1m", "3m": "3m", "6m": "6m",
                   "1y": "1y", "12m": "1y", "1y+": "1y+"}
    horizon = horizon_map.get(str(raw_horizon).lower(), "1m")

    for ev_node in event_nodes:
        # Direct paths: ev_node → target
        for to_id, edge in adj.get(ev_node, []):
            if to_id == target:
                paths.append(PropagationPath(
                    source             = ev_node,
                    target             = target,
                    chain_score        = edge.get("impact_score", 0.0),
                    confidence         = edge.get("confidence", 0.70),
                    time_horizon       = horizon,
                    intermediate_nodes = [],
                    relation_types     = [edge.get("relation", "UNKNOWN")],
                ))

        # Indirect paths: ev_node → intermediate → target
        for mid_id, edge1 in adj.get(ev_node, []):
            if mid_id == target:
                continue
            for to_id, edge2 in adj.get(mid_id, []):
                if to_id == target:
                    # Sign-preserving product
                    s1, s2 = edge1.get("impact_score", 0.0), edge2.get("impact_score", 0.0)
                    chain_score = _sign_product(s1, s2)
                    conf = min(
                        edge1.get("confidence", 0.70),
                        edge2.get("confidence", 0.70),
                    ) * 0.92   # 8% propagation uncertainty penalty
                    paths.append(PropagationPath(
                        source             = ev_node,
                        target             = target,
                        chain_score        = chain_score,
                        confidence         = conf,
                        time_horizon       = horizon,
                        intermediate_nodes = [mid_id],
                        relation_types     = [
                            edge1.get("relation", "UNKNOWN"),
                            edge2.get("relation", "UNKNOWN"),
                        ],
                    ))

    # ── Fall back to measured_impacts if no paths found ───────────────────────
    if not paths and target in measured:
        m   = measured[target]
        key = f"impact_{horizon}" if f"impact_{horizon}" in m else "impact_1m"
        imp = m.get(key, m.get("impact_1m", 0.0))
        paths.append(PropagationPath(
            source       = "measured_data",
            target       = target,
            chain_score  = imp,
            confidence   = m.get("confidence", 0.70),
            time_horizon = horizon,
        ))

    # ── Fallback: use gnn_training.target_impact ──────────────────────────────
    if not paths and "target_impact" in gnn:
        paths.append(PropagationPath(
            source       = "gnn_training",
            target       = target,
            chain_score  = gnn["target_impact"],
            confidence   = event_dict.get("confidence", 0.70),
            time_horizon = horizon,
        ))

    # ── Build entities ────────────────────────────────────────────────────────
    entities: list[Entity] = []
    for nid, node in nodes_by_id.items():
        entities.append(Entity(
            id            = nid,
            type          = node.get("type", "Company"),
            name          = node.get("name", nid),
            revenue_eur_m = node.get("revenue_eur_m"),
            country       = node.get("country"),
            sector        = node.get("sector"),
            ticker        = node.get("ticker"),
            headcount     = node.get("headcount"),
        ))

    # ── Derive direction sign ─────────────────────────────────────────────────
    measured_direction = (measured.get(target, {}) or {}).get("direction", None)
    if measured_direction == "positive":
        direction_sign = +1
    elif measured_direction == "negative":
        direction_sign = -1
    else:
        direction_sign = +1 if (sum(p.chain_score for p in paths) >= 0) else -1

    # ── Binary model output from gnn_training ────────────────────────────────
    target_impact = gnn.get("target_impact",
                             (measured.get(target, {}) or {}).get("impact_1m", 0.0))
    model_binary_output = 1 if abs(target_impact or 0) > 0.05 else 0

    return ScorerInput(
        trigger_event       = event_dict.get("event_name", ""),
        entities_impacted   = entities,
        propagation_paths   = paths,
        model_binary_output = model_binary_output,
        direction_sign      = direction_sign,
        event_type          = event_dict.get("event_type", "unknown"),
        event_date          = event_dict.get("event_date", ""),
    )


def _sign_product(a: float, b: float) -> float:
    """Multiply two impact scores preserving sign logic (sign(a) × sign(b) × sqrt(|a×b|))."""
    if a == 0 or b == 0:
        return 0.0
    sign = 1 if (a * b > 0) else -1
    return sign * math.sqrt(abs(a) * abs(b))


# ──────────────────────────────────────────────────────────────────────────────
# BATCH SCORING
# ──────────────────────────────────────────────────────────────────────────────

def batch_score_events(
    events: list[dict[str, Any]],
    target: str = "talan",
) -> list[dict[str, Any]]:
    """Score all events and return a list of result dicts (JSON-serialisable)."""
    scorer = ImpactScorer()
    results = []
    for evt in events:
        try:
            out = scorer.score_from_event(evt, target=target)
            results.append({
                "event_id":               evt.get("event_id", ""),
                "event_date":             out.event_date,
                "event_type":             out.event_type,
                "event_name":             out.event_name,
                "estimated_impact_pct":   out.estimated_impact_percent,
                "impact_label":           out.impact_label,
                "confidence":             out.confidence,
                "explanation":            out.explanation,
                # measured reference (if available) for calibration check
                "measured_impact_1m":     (evt.get("measured_impacts", {})
                                           .get(target, {}) or {})
                                          .get("impact_1m"),
                "measured_direction":     (evt.get("measured_impacts", {})
                                           .get(target, {}) or {})
                                          .get("direction"),
            })
        except Exception as exc:
            results.append({
                "event_id":   evt.get("event_id", ""),
                "event_name": evt.get("event_name", ""),
                "error":      str(exc),
            })
    return results


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Score financial impact of KG events for a target node."
    )
    parser.add_argument(
        "--data", default="kg_events.json",
        help="Path to kg_events.json (default: ./kg_events.json)",
    )
    parser.add_argument("--event", default=None, help="event_id to score")
    parser.add_argument(
        "--all", action="store_true",
        help="Score all events and print a summary table",
    )
    parser.add_argument(
        "--target", default="talan",
        help="Target node ID (default: talan)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Write batch results to this JSON file (only with --all)",
    )
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"[ERROR] File not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    with open(data_path, encoding="utf-8") as fh:
        events: list[dict] = json.load(fh)

    scorer = ImpactScorer()

    if args.all:
        results = batch_score_events(events, target=args.target)
        _print_table(results)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(results, fh, indent=2, ensure_ascii=False)
            print(f"\n✓ Results written to {args.out}")
        return

    # Single event mode
    evt_id = args.event
    evt    = next((e for e in events if e.get("event_id") == evt_id), None)
    if evt is None:
        available = [e.get("event_id", "?") for e in events[:10]]
        print(f"[ERROR] event_id '{evt_id}' not found.", file=sys.stderr)
        print(f"Available (first 10): {available}", file=sys.stderr)
        sys.exit(1)

    out = scorer.score_from_event(evt, target=args.target)

    print("\n" + "═" * 60)
    print(f"  Event : {out.event_name[:70]}")
    print(f"  Date  : {out.event_date}  |  Type: {out.event_type}")
    print("─" * 60)
    print(f"  Impact  : {out.estimated_impact_percent:+.2f} %")
    print(f"  Label   : {out.impact_label}")
    print(f"  Conf.   : {out.confidence:.3f}")
    print("─" * 60)
    print("  Breakdown:")
    bd = out.breakdown
    steps = [
        ("Base chain score",       bd.base_raw),
        ("Entity importance",      bd.entity_delta),
        ("Sector amplification",   bd.sector_delta),
        ("Confidence adjustment",  bd.confidence_delta),
        ("Time-horizon factor",    bd.horizon_delta),
        ("Propagation breadth",    bd.breadth_delta),
        ("Direction correction",   bd.direction_correction),
    ]
    for name, delta in steps:
        bar = "█" * int(abs(delta) / 1.5) if abs(delta) > 0.1 else ""
        sign = "+" if delta >= 0 else ""
        print(f"    {name:<26}  {sign}{delta:5.1f}%  {bar}")
    print(f"    {'FINAL':26}  {bd.final_pct:+5.1f}%")
    print("─" * 60)
    print(f"  Explanation:\n  {out.explanation}")
    print("═" * 60 + "\n")

    # JSON output for piping
    print(json.dumps({
        "estimated_impact_percent": out.estimated_impact_percent,
        "impact_label":             out.impact_label,
        "confidence":               out.confidence,
        "explanation":              out.explanation,
    }, indent=2, ensure_ascii=False))


def _print_table(results: list[dict]) -> None:
    header = (
        f"{'Event ID':<12} {'Date':<12} {'Score':>8} {'Label':<22} "
        f"{'Conf':>6} {'Measured_1m':>12} {'Dir':<10}"
    )
    print("\n" + "═" * len(header))
    print(header)
    print("─" * len(header))
    for r in results:
        if "error" in r:
            print(f"{'ERROR':<12} {r.get('event_id','?'):<12} {r['error']}")
            continue
        m1m = r.get("measured_impact_1m")
        m1m_str = f"{m1m:+.2f}" if m1m is not None else "   N/A"
        print(
            f"{r['event_id']:<12} {r['event_date']:<12} "
            f"{r['estimated_impact_pct']:>+7.1f}%  "
            f"{r['impact_label']:<22} "
            f"{r['confidence']:>5.2f}  "
            f"{m1m_str:>12}  "
            f"{r.get('measured_direction','?'):<10}"
        )
    print("═" * len(header) + "\n")


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _cli()
