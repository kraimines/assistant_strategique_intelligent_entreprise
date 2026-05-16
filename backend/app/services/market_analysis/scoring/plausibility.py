"""PlausibilityScorer — hybrid rule + LLM-judge plausibility (§3(d)).

    ρ_rules(p) = w₁·sector_overlap + w₂·geo_overlap
               + w₃·dependency_flag + w₄·exposure_magnitude

    ρ_llm(p)  : cached, only invoked when 0.3 ≤ ρ_rules ≤ 0.7

    ρ(p) = clip( 0.6·ρ_rules + 0.4·ρ_llm , 0, 1 )

Default weights (w₁..w₄) = (0.35, 0.20, 0.30, 0.15).

The LLM judge is **opt-in**: instantiate the scorer with
``llm_judge=None`` and only the rule path runs (deterministic + free).
This is the recommended default for unit tests and CI; production wires a
real ``LLMJudge`` whose ``score(path, context) -> (float, rationale)`` method
calls Groq/Anthropic with a strict JSON-only prompt.

Caching: results are keyed on a stable signature of the path
(source slug + ordered relation+slug pairs) so identical paths produced by
different runs hit the cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

W_SECTOR     = 0.35
W_GEO        = 0.20
W_DEPENDENCY = 0.30
W_EXPOSURE   = 0.15

LLM_GATE_LO  = 0.30
LLM_GATE_HI  = 0.70

RULE_WEIGHT_IN_HYBRID = 0.6
LLM_WEIGHT_IN_HYBRID  = 0.4


# ── Public DTO ───────────────────────────────────────────────────────────────

@dataclass
class PlausibilityResult:
    score:           float
    rule_score:      float
    llm_score:       Optional[float] = None
    rule_features:   Dict[str, float] = field(default_factory=dict)
    rationale:       str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "score":         self.score,
            "rule_score":    self.rule_score,
            "llm_score":     self.llm_score,
            "rule_features": self.rule_features,
            "rationale":     self.rationale,
        }


LLMJudgeFn = Callable[[Dict[str, Any], Dict[str, Any]], Tuple[float, str]]


# ── Scorer ───────────────────────────────────────────────────────────────────

class PlausibilityScorer:
    """Score a propagation path against Talan's operational profile.

    Args:
        talan_profile : dict produced by WorldModel.get_talan_profile()
        llm_judge     : optional callable. Signature
                        ``(path, context) -> (score, rationale)``.
        cache         : optional dict-like; can be a dict, an LRU, or a
                        Redis-backed wrapper. ``None`` = no cache.
    """

    def __init__(
        self,
        talan_profile: Dict[str, Any],
        llm_judge:     Optional[LLMJudgeFn] = None,
        cache:         Optional[Dict[str, Any]] = None,
    ):
        self.profile = talan_profile or {}
        self._llm = llm_judge
        self._cache = cache if cache is not None else {}

        # Pre-extract sets we need on every call
        self._talan_sectors: set[str] = {s.lower() for s in self.profile.get("sectors_served", [])}
        self._talan_geos: set[str] = {g.lower() for g in self.profile.get("geos", []) or [self.profile.get("country", "France")]}
        self._talan_competitors: set[str] = {c.lower() for c in self.profile.get("competitors", [])}
        self._bu_index = {bu["name"]: bu for bu in self.profile.get("business_units", [])}
        self._bu_supplier_index: Dict[str, List[str]] = {
            bu["name"]: [d.lower() for d in bu.get("depends_on", [])]
            for bu in self.profile.get("business_units", [])
        }

        # Talan's real market footprint — IT consulting / ESN / digital services
        # These keywords appear in news article entities and synthetic mechanism nodes.
        self._market_keywords: frozenset = frozenset({
            "it", "digital", "consulting", "technology", "tech", "ai", "artificial intelligence",
            "cloud", "data", "software", "cybersecurity", "cyber", "automation", "erp",
            "saas", "transformation", "innovation", "engineering", "genai", "llm",
            "banking", "finance", "financial", "insurance", "public sector", "government",
            "enterprise", "corporate", "infrastructure", "services", "outsourcing", "esn",
            "talan", "capgemini", "sopra", "atos", "accenture", "cgi",
        })
        # Talan primary geographies
        self._talan_geos.update({"france", "europe", "eu", "french", "european", "paris"})

    # ── Rule scorer ──────────────────────────────────────────────────────────

    def rule_score(self, path: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        steps = path.get("steps") or []
        node_names = [s.get("node_name", "") for s in steps]
        node_types = [s.get("node_type", "") for s in steps]
        node_props = [s.get("node_properties", {}) or {} for s in steps]

        # 1. sector_overlap — does the path touch a sector Talan serves?
        sector_overlap = 0.0
        for i, t in enumerate(node_types):
            name_l = node_names[i].lower()
            if t == "Sector" and name_l in self._talan_sectors:
                sector_overlap = 1.0
                break
            # BU's sector_focus also counts
            if t == "BusinessUnit":
                sector_overlap = max(sector_overlap, 0.8)
            # Competitor implies same sector by definition (Talan is an ESN, so
            # any tagged Competitor competes in IT services / consulting).
            if t == "Competitor" or name_l in self._talan_competitors:
                sector_overlap = max(sector_overlap, 0.8)
            # Suppliers / Clients of Talan also live in adjacent sectors.
            if t in {"Supplier", "Client"}:
                sector_overlap = max(sector_overlap, 0.6)
            # MacroIndicator / Sector / MarketTrend nodes that contain IT/consulting
            # keywords are directly in Talan's market — give partial credit.
            if t in {"MacroIndicator", "Sector", "MarketTrend", "Technology"} or (
                node_props[i].get("synthetic") and t in {"Sector", "MacroIndicator"}
            ):
                if any(kw in name_l for kw in self._market_keywords):
                    sector_overlap = max(sector_overlap, 0.65)
            # Synthetic exposure nodes end at Talan exposure names (e.g. "AI Consulting Demand")
            if node_props[i].get("synthetic") and any(
                kw in name_l for kw in {"consulting", "it services", "digital", "ai", "cloud", "enterprise"}
            ):
                sector_overlap = max(sector_overlap, 0.70)

        # 2. geo_overlap
        geo_overlap = 0.0
        for i, t in enumerate(node_types):
            name_l = node_names[i].lower()
            country = (node_props[i].get("country") or "").lower()
            if t == "Country" and name_l in self._talan_geos:
                geo_overlap = 1.0
                break
            if country and country in self._talan_geos:
                geo_overlap = max(geo_overlap, 0.8)
            # Macro events with no specific country still affect Talan's EU/France market
            if t in {"MacroIndicator", "Event", "Regulation"} and geo_overlap < 0.4:
                geo_overlap = max(geo_overlap, 0.40)  # non-zero default for macro events

        # 3. dependency_flag — competitor / supplier / client / BU is on the path
        dep_flag = 0.0
        for i, t in enumerate(node_types):
            name_l = node_names[i].lower()
            if t in {"Competitor", "Supplier", "Client", "BusinessUnit"}:
                dep_flag = 1.0
                break
            if name_l in self._talan_competitors:
                dep_flag = 1.0
                break
            # Paths ending at known Talan exposure nodes get half credit
            if node_props[i].get("synthetic") and t in {"Sector", "MacroIndicator"}:
                dep_flag = max(dep_flag, 0.5)

        # 4. exposure_magnitude — revenue_share of any BU/Client touched
        exposure = 0.0
        for i, t in enumerate(node_types):
            if t == "BusinessUnit":
                rs = float(node_props[i].get("revenue_share") or 0.0)
                exposure = max(exposure, rs)
            if t == "Client":
                rs = float(node_props[i].get("revenue_share") or 0.0)
                exposure = max(exposure, rs)
            # Synthetic exposure nodes carry a fixed exposure weight
            if node_props[i].get("synthetic") and "exposure_weight" in node_props[i]:
                ew = float(node_props[i].get("exposure_weight", 0.0))
                exposure = max(exposure, ew * 0.5)  # discount vs real BU revenue

        score = (
            W_SECTOR     * sector_overlap
            + W_GEO        * geo_overlap
            + W_DEPENDENCY * dep_flag
            + W_EXPOSURE   * exposure
        )
        score = max(0.0, min(1.0, score))
        features = {
            "sector_overlap": sector_overlap,
            "geo_overlap":    geo_overlap,
            "dependency":     dep_flag,
            "exposure":       exposure,
        }
        return score, features

    # ── LLM judge ────────────────────────────────────────────────────────────

    def _llm_eval(self, path: Dict[str, Any]) -> Tuple[float, str]:
        if self._llm is None:
            return 0.5, ""
        sig = self._signature(path)
        if sig in self._cache:
            cached = self._cache[sig]
            return float(cached.get("score", 0.5)), str(cached.get("rationale", ""))
        try:
            score, rationale = self._llm(path, self.profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM judge failed (%s) — defaulting to neutral 0.5", exc)
            score, rationale = 0.5, "llm_judge_failed"
        score = max(0.0, min(1.0, float(score)))
        self._cache[sig] = {"score": score, "rationale": rationale}
        return score, rationale

    @staticmethod
    def _signature(path: Dict[str, Any]) -> str:
        steps = path.get("steps") or []
        payload = {
            "src":   (path.get("source_name") or "").lower(),
            "chain": [
                (s.get("node_name", "").lower(), s.get("relation_type", ""))
                for s in steps
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    # ── Hybrid scorer ────────────────────────────────────────────────────────

    def score(self, path: Dict[str, Any]) -> PlausibilityResult:
        rule, feats = self.rule_score(path)

        if self._llm is None or not (LLM_GATE_LO <= rule <= LLM_GATE_HI):
            return PlausibilityResult(
                score=rule,
                rule_score=rule,
                llm_score=None,
                rule_features=feats,
                rationale="rule-only" + (" (LLM gated)" if self._llm else ""),
            )

        llm_score, rationale = self._llm_eval(path)
        hybrid = RULE_WEIGHT_IN_HYBRID * rule + LLM_WEIGHT_IN_HYBRID * llm_score
        hybrid = max(0.0, min(1.0, hybrid))
        return PlausibilityResult(
            score=hybrid,
            rule_score=rule,
            llm_score=llm_score,
            rule_features=feats,
            rationale=rationale or "hybrid",
        )

    # ── Batch helper ─────────────────────────────────────────────────────────

    def score_many(self, paths: List[Dict[str, Any]]) -> List[PlausibilityResult]:
        return [self.score(p) for p in paths]
