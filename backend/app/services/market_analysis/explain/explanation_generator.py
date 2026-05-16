"""ExplanationGenerator — director-grade propagation rationale.

Each output is built so a BU director or DAF can act on it without a
technical briefing. The fields answer the questions executives actually
ask in a strategy review:

  - headline               → one-line takeaway for dashboards / emails
  - causal_reasoning       → why this path threatens (or helps) Talan
  - affected_business_unit → who owns the P&L exposure
  - recommended_action     → concrete first move
  - recommended_owner      → which Talan function should act
  - deadline_label         → quarter / week-anchored deadline
  - financial_impact_eur   → € range based on Talan revenue × BU share
  - confidence_label       → plain-language reliability of the signal

A deterministic rule path always works (free, reproducible). An optional
LLM polish rewrites the prose for executive tone.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

# Talan public revenue baseline used for € estimates. Conservative anchor
# (Talan group 2024 revenue ≈ €650M). Override via TalanProfile.annual_revenue_eur.
TALAN_REVENUE_EUR_DEFAULT = 650_000_000

# Risk category mapping (path edge category → executive risk family)
_CATEGORY_TO_RISK: Dict[str, str] = {
    "competitive":        "competitive",
    "supply_chain":       "supply_chain",
    "regulatory":         "regulatory",
    "macro":              "macro",
    "event":              "tech_disruption",
    "sector":             "tech_disruption",
    "evidence":           "competitive",
    "geo":                "macro",
    "default":            "tech_disruption",
    "growth_opportunity": "growth_opportunity",
    "market":             "growth_opportunity",
    "public":             "growth_opportunity",
}

# Risk category → recommended owner (Talan org function)
_RISK_TO_OWNER: Dict[str, str] = {
    "competitive":        "Direction Commerciale BU",
    "supply_chain":       "Direction Achats & Partenariats",
    "regulatory":         "Direction Juridique & Compliance",
    "macro":              "Direction Financière (DAF)",
    "cyber":              "RSSI / CISO",
    "talent":             "Direction RH",
    "tech_disruption":    "Direction de l'Innovation",
    "growth_opportunity": "Direction Commerciale BU",
}

# Risk category → action verb prefix (French, action-oriented)
_RISK_TO_ACTION: Dict[str, str] = {
    "competitive":        "Repositionner",
    "supply_chain":       "Sécuriser",
    "regulatory":         "Auditer la conformité",
    "macro":              "Stress-tester les prévisions",
    "cyber":              "Lancer un audit de résilience",
    "talent":             "Renforcer le pipeline de talents",
    "tech_disruption":    "Réviser la roadmap technologique",
    "growth_opportunity": "Mobiliser l'offre commerciale",
}

# Severity → French label + emoji
_SEVERITY_FR = {
    "critical": "🔴 Critique",
    "high":     "🟠 Élevée",
    "medium":   "🟡 Modérée",
    "low":      "🟢 Faible",
}

# Confidence buckets → plain language (French)
_CONFIDENCE_LABEL = [
    (0.75, "Forte"),
    (0.55, "Moyenne"),
    (0.35, "Limitée"),
    (0.00, "Spéculative"),
]

_HORIZON_LABELS = {
    "immediate":   "immediate",
    "short_term":  "short",
    "short":       "short",
    "medium_term": "medium",
    "medium":      "medium",
    "long_term":   "long",
    "long":        "long",
}

# Time horizon → executive deadline language anchored to next quarter
_HORIZON_TO_DEADLINE_DAYS = {
    "immediate": 14,
    "short":     45,
    "medium":    120,
    "long":      270,
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


def _horizon_from_freshness(freshness: float) -> str:
    if freshness >= 0.90:
        return "short"
    if freshness >= 0.60:
        return "medium"
    return "long"


def _confidence_label(confidence: float) -> str:
    for threshold, label in _CONFIDENCE_LABEL:
        if confidence >= threshold:
            return label
    return "Spéculative"


def _quarter_label(target: datetime) -> str:
    q = (target.month - 1) // 3 + 1
    return f"Q{q} {target.year}"


def _deadline_label(horizon: str) -> str:
    days = _HORIZON_TO_DEADLINE_DAYS.get(horizon, 60)
    target = datetime.now(timezone.utc) + timedelta(days=days)
    if horizon == "immediate":
        return f"sous 2 semaines (avant le {target.strftime('%d/%m/%Y')})"
    if horizon == "short":
        return f"avant {_quarter_label(target)}"
    if horizon == "medium":
        return f"d'ici {_quarter_label(target)}"
    return f"à horizon {_quarter_label(target)}"


def _format_eur(amount: float) -> str:
    if amount >= 1_000_000:
        return f"€{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"€{amount / 1_000:.0f}k"
    return f"€{amount:.0f}"


def _financial_impact_eur(
    annual_revenue: float,
    bu_revenue_share: float,
    impact_pct: float,
    horizon: str,
) -> str:
    """Translate impact_pct (estimated_business_impact_pct) into a € range.

    impact_pct is signed [-100, +100], applied to the affected BU's
    annualised revenue × time-horizon fraction. Returns a band with
    ±30% uncertainty for executive readability.
    """
    if abs(impact_pct) < 0.10:
        return "Impact financier négligeable"

    bu_share = max(0.05, min(1.0, bu_revenue_share or 0.15))
    horizon_fraction = {
        "immediate": 0.5 / 12,   # ~2 weeks
        "short":     1.5 / 12,   # 6 weeks
        "medium":    3.0 / 12,   # 1 quarter
        "long":      6.0 / 12,   # 6 months
    }.get(horizon, 3.0 / 12)

    central = annual_revenue * bu_share * (abs(impact_pct) / 100.0) * horizon_fraction
    low  = central * 0.7
    high = central * 1.3

    sign = "-" if impact_pct < 0 else "+"
    label = "revenu à risque" if impact_pct < 0 else "revenu additionnel"
    return f"{sign}{_format_eur(low)} à {sign}{_format_eur(high)} de {label}"


# ── DTO ──────────────────────────────────────────────────────────────────────

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
    headline:                str = ""
    recommended_owner:       str = ""
    deadline_label:          str = ""
    financial_impact_eur:    str = ""
    confidence_label:        str = ""
    business_relevance:      str = ""   # "Why this matters to Talan" — one-line business reason

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
        self._bu_revenue_share: Dict[str, float] = {}
        for bu in self.profile.get("business_units", []):
            self._bu_revenue_share[bu.get("name", "")] = float(bu.get("revenue_share") or 0.15)
            for sector in bu.get("sector_focus", []) or []:
                self._bu_by_sector.setdefault(sector, bu["name"])
        self._annual_revenue = float(
            self.profile.get("annual_revenue_eur") or TALAN_REVENUE_EUR_DEFAULT
        )

    # ── Main entry ───────────────────────────────────────────────────────────

    def explain(self, scored_path) -> PropagationExplanationDict:
        path = scored_path.path
        steps = path.get("steps") or []
        source = path.get("source_name") or "Événement non identifié"

        affected_sector = self._infer_sector(steps)
        affected_bu = self._infer_bu(affected_sector, steps)

        chain_score = float(path.get("chain_score", 0.0))
        # is_positive is determined solely by chain_score sign so it's consistent
        # with what was computed in the TGAT scoring pipeline.
        is_positive = chain_score >= 0

        # Risk category from dominant edge category + first step node type
        cats = [s.get("category") or "default" for s in steps]
        dominant_cat = max(set(cats), key=cats.count) if cats else "default"
        if is_positive and dominant_cat in {"event", "sector", "public", "default"}:
            risk_cat = "growth_opportunity"
        else:
            risk_cat = _CATEGORY_TO_RISK.get(dominant_cat, "tech_disruption")
            # Refine risk_cat for fallback-injected negative paths whose steps
            # carry only "default" category (no explicit edge classification).
            if not is_positive and risk_cat == "tech_disruption" and dominant_cat == "default":
                # Use first step node_type to pick a more accurate category
                first_type = (steps[0].get("node_type") or "").lower() if steps else ""
                if first_type in ("macro_indicator", "macroindicator", "event"):
                    risk_cat = "macro"
                elif first_type in ("sector", "competitor"):
                    risk_cat = "competitive"
                elif first_type == "regulation":
                    risk_cat = "regulatory"
                else:
                    risk_cat = "macro"  # default for generic negative company paths

        severity = _severity_from_score(scored_path.weighted_score, scored_path.plausibility)
        horizon = _horizon_from_freshness(scored_path.path_freshness)
        confidence_label = _confidence_label(scored_path.confidence)

        # Executive-grade content
        headline = self._draft_headline(
            source, affected_bu, affected_sector, severity, risk_cat, is_positive,
        )
        causal_reasoning = self._draft_causal_reasoning(
            source, steps, affected_bu, affected_sector, positive=is_positive,
        )
        recommended_action = self._draft_recommendation(
            source, affected_bu, affected_sector, risk_cat, severity, is_positive,
        )
        business_relevance = self._draft_business_relevance(
            source, affected_sector, affected_bu, risk_cat, is_positive,
        )
        recommended_owner = _RISK_TO_OWNER.get(risk_cat, "Direction Générale")
        deadline_label = _deadline_label(horizon)
        financial_impact_eur = _financial_impact_eur(
            annual_revenue   = self._annual_revenue,
            bu_revenue_share = self._bu_revenue_share.get(affected_bu, 0.15),
            impact_pct       = scored_path.estimated_business_impact_pct,
            horizon          = horizon,
        )
        rationale = self._draft_rationale(scored_path)

        explanation = PropagationExplanationDict(
            causal_reasoning       = causal_reasoning,
            affected_business_unit = affected_bu,
            affected_sector        = affected_sector,
            risk_category          = risk_cat,
            severity               = severity,
            recommended_action     = recommended_action,
            time_horizon           = horizon,
            confidence_rationale   = rationale,
            headline               = headline,
            recommended_owner      = recommended_owner,
            deadline_label         = deadline_label,
            financial_impact_eur   = financial_impact_eur,
            confidence_label       = confidence_label,
            business_relevance     = business_relevance,
        )

        # Optional LLM polish — fail-soft
        if self._llm is not None:
            try:
                polished = self._llm_polish(explanation)
                if polished is not None:
                    return polished
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ExplanationGenerator: LLM polish failed (%s) — keeping draft", exc,
                )
        return explanation

    # ── Heuristics ───────────────────────────────────────────────────────────

    def _infer_sector(self, steps: List[Dict[str, Any]]) -> str:
        for s in steps:
            if s.get("node_type") == "Sector":
                return s.get("node_name") or "IT Services"
        return "IT Services"

    def _infer_bu(self, sector: str, steps: List[Dict[str, Any]]) -> str:
        for s in steps:
            if s.get("node_type") == "BusinessUnit":
                return s.get("node_name") or "Talan"
        if sector in self._bu_by_sector:
            return self._bu_by_sector[sector]
        bus = self.profile.get("business_units", [])
        if bus:
            return max(bus, key=lambda b: b.get("revenue_share", 0)).get("name", "Talan")
        return "Talan"

    # ── Executive drafters ───────────────────────────────────────────────────

    @staticmethod
    def _draft_headline(
        source: str,
        bu: str,
        sector: str,
        severity: str,
        risk_cat: str,
        positive: bool,
    ) -> str:
        sev = _SEVERITY_FR.get(severity, severity.title())
        if positive or risk_cat == "growth_opportunity":
            return f"📈 Opportunité {sev} — {source} ouvre une fenêtre commerciale sur {sector} (BU {bu})"
        risk_fr = {
            "competitive":     "Pression concurrentielle",
            "supply_chain":    "Risque supply chain",
            "regulatory":      "Risque réglementaire",
            "macro":           "Risque macro-économique",
            "cyber":           "Risque cyber",
            "talent":          "Tension sur les talents",
            "tech_disruption": "Disruption technologique",
        }.get(risk_cat, "Risque stratégique")
        return f"{sev} — {risk_fr} sur {bu} ({sector}) déclenchée par : {source}"

    @staticmethod
    def _draft_causal_reasoning(
        source: str,
        steps: List[Dict[str, Any]],
        bu: str,
        sector: str,
        positive: bool = False,
    ) -> str:
        chain_nodes = [s.get("node_name") or "?" for s in steps]
        # Remove the source duplicate and trailing Talan for readability
        mids = [n for n in chain_nodes[1:] if n.lower() != "talan"]
        chain = " → ".join(mids) if mids else "(impact direct)"
        if positive:
            return (
                f"L'événement « {source} » stimule la demande via la chaîne {chain}, "
                f"créant une opportunité de croissance pour la BU {bu} sur le segment {sector}. "
                f"Le mécanisme de transmission est causal et économiquement plausible."
            )
        return (
            f"L'événement « {source} » se propage via la chaîne {chain} et exerce une pression "
            f"sur la BU {bu} via le segment {sector}. Chaque maillon de la chaîne représente un "
            f"mécanisme économique réel (demande, coûts, ou contrainte réglementaire)."
        )

    @staticmethod
    def _draft_recommendation(
        source: str,
        bu: str,
        sector: str,
        risk: str,
        severity: str,
        positive: bool,
    ) -> str:
        if positive or risk == "growth_opportunity":
            return (
                f"Mobiliser dès à présent l'offre {sector} de la BU {bu} : pré-positionner les "
                f"équipes de delivery, accélérer les réponses aux appels d'offres et briefer "
                f"l'équipe commerciale sur l'impact de « {source} ». "
                f"Objectif : capter ≥ 1-2 nouveaux contrats sur le trimestre."
            )
        prefix = _RISK_TO_ACTION.get(risk, "Réévaluer")
        urgency = " urgemment" if severity in {"high", "critical"} else ""
        return (
            f"{prefix}{urgency} le portefeuille {sector} de la BU {bu} face à « {source} ». "
            f"Étapes concrètes : (1) inventorier les contrats exposés sur les 6 prochains mois, "
            f"(2) chiffrer l'impact P&L et l'inscrire au registre des risques BU, "
            f"(3) préparer un plan de mitigation à présenter au prochain ComEx."
        )

    @staticmethod
    def _draft_rationale(scored_path) -> str:
        return (
            f"Plausibilité {scored_path.plausibility:.0%}, "
            f"spécificité {scored_path.path_specificity:.0%}, "
            f"fraîcheur {scored_path.path_freshness:.0%}, "
            f"confiance des sources {scored_path.avg_edge_confidence:.0%}."
        )

    @staticmethod
    def _draft_business_relevance(
        source: str, sector: str, bu: str, risk: str, positive: bool,
    ) -> str:
        """One-line 'why this matters to Talan' — concrete business reason
        tied to Talan's exposure profile. Transforms abstract graph signals
        into actionable strategic context."""
        if positive or risk == "growth_opportunity":
            return (
                f"Talan a une exposition forte aux projets {sector} dans le secteur "
                f"bancaire & enterprise IT — cette dynamique peut accélérer la demande "
                f"sur l'offre de la BU {bu} dès le prochain trimestre."
            )
        reasons = {
            "competitive":     f"Pression accrue sur nos taux et marges dans {sector} ; risque de churn client.",
            "regulatory":      f"Nouveaux coûts de conformité chez nos clients {sector} réduisent leur budget IT discrétionnaire.",
            "macro":           f"Contraction des budgets clients dans {sector} → allongement de nos cycles de vente.",
            "supply_chain":    f"Perturbation chez nos partenaires {sector} retarde les livraisons projet et le revenu reconnu.",
            "cyber":           f"Incident sécurité accélère la demande audit mais expose nos engagements existants chez {bu}.",
            "talent":          f"Tension sur les compétences {sector} renchérit nos coûts de delivery et réduit les marges.",
            "tech_disruption": f"Risque d'obsolescence de notre offre {sector} face à cette évolution — repositionnement requis.",
        }
        return reasons.get(risk, f"Exposition directe aux évolutions du marché {sector} ; surveillance rapprochée recommandée.")

    # ── LLM polish (optional) ────────────────────────────────────────────────

    def _llm_polish(self, draft: PropagationExplanationDict) -> Optional[PropagationExplanationDict]:
        if self._llm is None:
            return None
        import json as _json
        import re as _re
        prompt = (
            "Tu es un consultant stratégique senior. Réécris la fiche d'impact suivante "
            "dans un français exécutif, factuel et orienté décision (style note de "
            "Direction). Conserve TOUS les champs identiques sauf 'headline', "
            "'causal_reasoning' et 'recommended_action' que tu reformules en 2-3 phrases "
            "claires et actionnables. Ne supprime aucun chiffre, BU, secteur ou délai. "
            "Renvoie UNIQUEMENT du JSON valide, sans balises markdown.\n\n"
            f"{_json.dumps(draft.as_dict(), ensure_ascii=False)}"
        )
        try:
            out = self._llm(prompt)
            if not isinstance(out, str):
                return None
            text = _re.sub(r"^```(?:json)?\s*", "", out.strip(), flags=_re.MULTILINE)
            text = _re.sub(r"\s*```$", "", text, flags=_re.MULTILINE)
            data = _json.loads(text)
            return PropagationExplanationDict(
                causal_reasoning=       str(data.get("causal_reasoning",       draft.causal_reasoning)),
                affected_business_unit= str(data.get("affected_business_unit", draft.affected_business_unit)),
                affected_sector=        str(data.get("affected_sector",        draft.affected_sector)),
                risk_category=          str(data.get("risk_category",          draft.risk_category)),
                severity=               str(data.get("severity",               draft.severity)),
                recommended_action=     str(data.get("recommended_action",     draft.recommended_action)),
                time_horizon=           str(data.get("time_horizon",           draft.time_horizon)),
                confidence_rationale=   str(data.get("confidence_rationale",   draft.confidence_rationale)),
                headline=               str(data.get("headline",               draft.headline)),
                recommended_owner=      str(data.get("recommended_owner",      draft.recommended_owner)),
                deadline_label=         str(data.get("deadline_label",         draft.deadline_label)),
                financial_impact_eur=   str(data.get("financial_impact_eur",   draft.financial_impact_eur)),
                confidence_label=       str(data.get("confidence_label",       draft.confidence_label)),
            )
        except Exception as exc:
            logger.warning(
                "ExplanationGenerator._llm_polish parse failed (%s) — keeping draft", exc,
            )
            return None
