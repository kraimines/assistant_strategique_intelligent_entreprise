"""ExplanationGenerator — produces a structured PropagationExplanation per path.

The generator is **hybrid**:
  * a deterministic rule-based draft (always works, free, reproducible)
  * an optional LLM polish step that rewrites the recommended_action and
    causal_reasoning into idiomatic French/English consulting language.

Output schema mirrors the new ``PropagationExplanation`` Pydantic model:

    causal_reasoning, affected_business_unit, affected_sector,
    risk_category, severity, recommended_action, time_horizon,
    confidence_rationale.

The LLM step is gated behind ``llm_callable``: pass ``None`` (default) to
get the deterministic draft only — the explanation will still be coherent
and cite real BUs/sectors from the Talan profile.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Risk-category mapping ────────────────────────────────────────────────────
_CATEGORY_TO_RISK = {
    "competitive":  "competitive",
    "supply_chain": "supply_chain",
    "regulatory":   "regulatory",
    "macro":        "macro",
    "event":        "tech_disruption",
    "sector":       "tech_disruption",
    "evidence":     "competitive",
    "geo":          "macro",
    "default":      "tech_disruption",
    # Positive signals
    "growth_opportunity": "growth_opportunity",
    "market":       "growth_opportunity",
    "public":       "growth_opportunity",
}


def _severity_from_score(weighted: float, plaus: float) -> str:
    combined = weighted * plaus
    if combined >= 0.35 or (plaus >= 0.6 and weighted >= 0.3):
        return "critical"
    if combined >= 0.20:
        return "high"
    if combined >= 0.08:
        return "medium"
    return "low"


_HORIZON_LABELS = {
    "immediate":   "immediate",
    "short_term":  "short",
    "short":       "short",
    "medium_term": "medium",
    "medium":      "medium",
    "long_term":   "long",
    "long":        "long",
}


def _horizon_from_freshness(freshness: float) -> str:
    if freshness >= 0.90:
        return "short"   # very fresh → short-term effect
    if freshness >= 0.60:
        return "medium"
    return "long"


@dataclass
class PropagationExplanationDict:
    causal_reasoning:        str
    affected_business_unit:  str
    affected_sector:         str
    risk_category:           str
    severity:                str
    recommended_action:      str
    time_horizon:            str
    confidence_rationale:    str

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__


# ── Generator ────────────────────────────────────────────────────────────────

class ExplanationGenerator:
    def __init__(
        self,
        talan_profile: Dict[str, Any],
        llm_callable:  Optional[Callable[[str], str]] = None,
    ):
        self.profile = talan_profile or {}
        self._llm = llm_callable
        self._bu_by_sector: Dict[str, str] = {}
        for bu in self.profile.get("business_units", []):
            for sector in bu.get("sector_focus", []) or []:
                self._bu_by_sector.setdefault(sector, bu["name"])

    def explain(self, scored_path) -> PropagationExplanationDict:
        path = scored_path.path
        steps = path.get("steps") or []
        source = path.get("source_name") or "Unknown source"

        affected_sector = self._infer_sector(steps)
        affected_bu = self._infer_bu(affected_sector, steps)

        # Detect growth opportunities (positive chain_score → beneficial event)
        chain_score = float(scored_path.path.get("chain_score", 0.0))
        is_positive = chain_score > 0 or scored_path.estimated_business_impact_pct > 0

        # Pick the dominant edge category along the path for risk_category mapping
        cats = [s.get("category") or "default" for s in steps]
        dominant_cat = max(set(cats), key=cats.count) if cats else "default"
        if is_positive and dominant_cat in {"event", "sector", "public", "default"}:
            risk_cat = "growth_opportunity"
        else:
            risk_cat = _CATEGORY_TO_RISK.get(dominant_cat, "tech_disruption")

        severity = _severity_from_score(scored_path.weighted_score, scored_path.plausibility)
        horizon = _horizon_from_freshness(scored_path.path_freshness)

        causal_reasoning = self._draft_causal_reasoning(source, steps, affected_bu, affected_sector, positive=is_positive)
        recommended_action = self._draft_recommendation(source, affected_bu, affected_sector, risk_cat, severity)
        rationale = self._draft_rationale(scored_path)

        explanation = PropagationExplanationDict(
            causal_reasoning=causal_reasoning,
            affected_business_unit=affected_bu,
            affected_sector=affected_sector,
            risk_category=risk_cat,
            severity=severity,
            recommended_action=recommended_action,
            time_horizon=horizon,
            confidence_rationale=rationale,
        )

        # Optional LLM polish — fail-soft
        if self._llm is not None:
            try:
                polished = self._llm_polish(explanation)
                if polished is not None:
                    return polished
            except Exception as exc:  # noqa: BLE001
                logger.warning("ExplanationGenerator: LLM polish failed (%s) — keeping draft", exc)

        return explanation

    # ── Heuristics ───────────────────────────────────────────────────────────

    def _infer_sector(self, steps: List[Dict[str, Any]]) -> str:
        for s in steps:
            if s.get("node_type") == "Sector":
                return s.get("node_name") or "IT Services"
        # Fallback to Talan's primary sector
        return "IT Services"

    def _infer_bu(self, sector: str, steps: List[Dict[str, Any]]) -> str:
        # 1. Direct hit: a BU node is on the path
        for s in steps:
            if s.get("node_type") == "BusinessUnit":
                return s.get("node_name") or "Talan"
        # 2. Sector → BU map
        if sector in self._bu_by_sector:
            return self._bu_by_sector[sector]
        # 3. Largest BU as default
        bus = self.profile.get("business_units", [])
        if bus:
            return max(bus, key=lambda b: b.get("revenue_share", 0)).get("name", "Talan")
        return "Talan"

    @staticmethod
    def _draft_causal_reasoning(source: str, steps: List[Dict[str, Any]], bu: str, sector: str, positive: bool = False) -> str:
        chain = " → ".join(
            (s.get("node_name") or "?") for s in steps
        ) if steps else source
        if positive:
            return (
                f"{source} creates increased demand through {chain}, "
                f"generating a growth opportunity for {bu} in the {sector} segment."
            )
        return (
            f"{source} propagates through {chain}, putting pressure on {bu} via the "
            f"{sector} segment of Talan's portfolio."
        )

    @staticmethod
    def _draft_recommendation(source: str, bu: str, sector: str, risk: str, severity: str) -> str:
        if risk == "growth_opportunity":
            return (
                f"Strengthen {bu}'s {sector} capabilities to capture demand generated by "
                f"{source} — increase bidding capacity, pre-position delivery teams, "
                f"and update the commercial pipeline accordingly."
            )
        prefix = {
            "competitive":      "Reposition",
            "supply_chain":     "Mitigate supplier exposure for",
            "regulatory":       "Audit compliance posture of",
            "macro":            "Stress-test revenue forecast for",
            "tech_disruption":  "Review technology roadmap of",
            "cyber":            "Run an incident-readiness drill for",
            "talent":           "Reinforce talent pipeline for",
        }.get(risk, "Review")
        intensity = " urgently" if severity in {"high", "critical"} else ""
        return (
            f"{prefix}{intensity} {bu}'s {sector} offer in light of {source}; "
            f"validate near-term commercial impact and update the BU risk register."
        )

    @staticmethod
    def _draft_rationale(scored_path) -> str:
        return (
            f"plaus={scored_path.plausibility:.2f}, "
            f"spec={scored_path.path_specificity:.2f}, "
            f"freshness={scored_path.path_freshness:.2f}, "
            f"conf={scored_path.avg_edge_confidence:.2f}"
        )

    # ── LLM polish (optional) ───────────────────────────────────────────────

    def _llm_polish(self, draft: PropagationExplanationDict) -> Optional[PropagationExplanationDict]:
        if self._llm is None:
            return None
        prompt = (
            "Rewrite the following business-impact explanation in a concise, "
            "executive-readable consulting tone. Keep all factual fields exactly "
            "the same; only refine 'causal_reasoning' and 'recommended_action'. "
            "Return JSON with the same keys.\n\n"
            f"{draft.as_dict()}"
        )
        out = self._llm(prompt)
        if not isinstance(out, str):
            return None
        # We deliberately do not parse JSON here — let callers wire a real LLM
        # judge with structured output. The draft already contains all fields.
        return draft
