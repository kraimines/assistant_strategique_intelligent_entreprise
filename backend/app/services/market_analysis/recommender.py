"""
Strategic Recommender — génère des recommandations actionnables
en combinant GNN output + LSTM forecast + contexte Talan.

LLM utilisé : Groq (llama-3.3-70b) avec fallback Gemini.

Output structuré :
[
  {
    "title":    "Renforcer le pipeline ESN face à la concurrence",
    "action":   "Accélérer les discussions avec 3 comptes bancaires clés...",
    "urgency":  "high",        # low | medium | high | critical
    "horizon":  "7_days",      # 7_days | 30_days | 90_days
    "domain":   "commercial",  # commercial | rh | financier | technologique | risque
  },
  ...
]
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm import get_json_llm, invoke_with_retry
from app.models.market_analysis_models import MarketRecommendation
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """Tu es un conseiller stratégique senior pour Talan, cabinet de conseil en transformation numérique (4 000 consultants, présence en Europe, Afrique du Nord, Moyen-Orient).

Tu reçois :
- Le résultat d'un modèle GNN (Graph Neural Network) qui prédit l'impact d'événements macro-économiques sur Talan
- Une prévision LSTM à 7 et 30 jours de l'évolution de cet impact
- Les risques cachés détectés dans le graphe de connaissance

Tu dois générer exactement 4 recommandations stratégiques concrètes et actionnables pour Talan.

Règles :
- Chaque recommandation doit être spécifique à Talan (pas de conseils génériques)
- Les actions doivent être faisables dans l'horizon indiqué
- Couvre des domaines variés : commercial, RH, financier, technologique, risque
- Tiens compte du score d'impact prédit (négatif = menace, positif = opportunité)
- Si systemic_risk > 0.6 : au moins 1 recommandation de mitigation des risques
- Si des concurrents sont impactés : identifier les opportunités de parts de marché

Réponds UNIQUEMENT avec un JSON valide, sans texte avant ou après :
[
  {
    "title": "titre court (< 60 caractères)",
    "action": "description concrète de l'action à mener (2-3 phrases)",
    "urgency": "low|medium|high|critical",
    "horizon": "7_days|30_days|90_days",
    "domain": "commercial|rh|financier|technologique|risque"
  }
]"""


# ── Main function ─────────────────────────────────────────────────────────────

def generate_recommendations(
    gnn_result: dict,
    forecast_result: dict | None = None,
    gnn_score_id: str | None = None,
) -> dict:
    """
    Generate strategic recommendations from GNN + forecast data.

    Parameters
    ----------
    gnn_result     : output of GNNPredictor.predict().model_dump()
    forecast_result: output of forecaster.forecast()
    gnn_score_id   : UUID of the persisted MarketGNNScore row (for FK)

    Returns
    -------
    dict with keys: recommendations, raw_llm_output, model_used, generated_at
    """
    talan_impact   = 0.0
    systemic_risk  = float(gnn_result.get("systemic_risk_score", 0))
    trigger_event  = gnn_result.get("trigger_event", "événement inconnu")

    tp = gnn_result.get("talan_prediction") or {}
    if isinstance(tp, dict):
        talan_impact = float(tp.get("predicted_impact", 0))

    hidden_risks = gnn_result.get("top_hidden_risks", [])
    hidden_names = [r.get("entity_name", "") if isinstance(r, dict) else str(r)
                    for r in hidden_risks[:5]]

    # Top impacted competitors from predictions
    predictions = gnn_result.get("predictions", [])
    competitors  = [
        p for p in predictions
        if isinstance(p, dict) and p.get("entity_type") == "company"
        and p.get("entity_name") != "Talan"
        and abs(float(p.get("predicted_impact", 0))) > 0.2
    ]
    competitors.sort(key=lambda p: abs(float(p.get("predicted_impact", 0))), reverse=True)

    # Build user message
    impact_label = (
        "FORTE MENACE" if talan_impact < -0.5 else
        "menace modérée" if talan_impact < -0.2 else
        "impact neutre" if abs(talan_impact) <= 0.2 else
        "opportunité modérée" if talan_impact < 0.5 else
        "FORTE OPPORTUNITÉ"
    )

    forecast_block = ""
    if forecast_result:
        f7  = forecast_result.get("forecast_7d",  "N/A")
        f30 = forecast_result.get("forecast_30d", "N/A")
        trend = forecast_result.get("trend", "stable")
        forecast_block = f"""
Prévision LSTM :
- Impact prédit dans 7 jours  : {f7} ({trend})
- Impact prédit dans 30 jours : {f30}
- Confiance du modèle         : {forecast_result.get('confidence', 'N/A')}"""

    competitors_block = ""
    if competitors:
        lines = [f"  - {c['entity_name']}: {c['predicted_impact']:+.3f}" for c in competitors[:5]]
        competitors_block = "\nConcurrents également impactés :\n" + "\n".join(lines)

    user_message = f"""Analyse stratégique Talan — {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC

Événement déclencheur : {trigger_event}

Impact GNN sur Talan : {talan_impact:+.3f}  → {impact_label}
Risque systémique    : {systemic_risk:.3f} / 1.0
{forecast_block}
{competitors_block}
Risques cachés détectés : {', '.join(hidden_names) if hidden_names else 'Aucun'}

Génère 4 recommandations stratégiques concrètes pour Talan."""

    # Call LLM
    llm = get_json_llm()
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    raw_output = ""
    model_used = getattr(settings, "groq_model", "unknown")
    recommendations = []

    try:
        response = invoke_with_retry(llm, messages)
        raw_output = response.content if hasattr(response, "content") else str(response)
        recommendations = _parse_recommendations(raw_output)
        logger.info("Recommender: generated %d recommendations", len(recommendations))
    except Exception as e:
        logger.error("Recommender LLM call failed: %s", e)
        recommendations = _fallback_recommendations(talan_impact, systemic_risk)
        raw_output = json.dumps(recommendations)

    # Persist to DB
    _persist_recommendation(
        trigger_event   = trigger_event,
        talan_impact    = talan_impact,
        systemic_risk   = systemic_risk,
        forecast_7d     = forecast_result.get("forecast_7d") if forecast_result else None,
        forecast_30d    = forecast_result.get("forecast_30d") if forecast_result else None,
        recommendations = recommendations,
        raw_llm_output  = raw_output,
        model_used      = model_used,
        gnn_score_id    = gnn_score_id,
    )

    return {
        "recommendations": recommendations,
        "raw_llm_output":  raw_output,
        "model_used":      model_used,
        "generated_at":    datetime.utcnow().isoformat(),
        "trigger_event":   trigger_event,
        "talan_impact":    talan_impact,
        "systemic_risk":   systemic_risk,
        "forecast_7d":     forecast_result.get("forecast_7d") if forecast_result else None,
        "forecast_30d":    forecast_result.get("forecast_30d") if forecast_result else None,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_recommendations(raw: str) -> list[dict]:
    """Extract JSON array from LLM output, tolerant to markdown fences."""
    text = raw.strip()
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    # Find first [ ... ] block
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [_validate_rec(r) for r in data if isinstance(r, dict)]
    except json.JSONDecodeError:
        pass
    logger.warning("Could not parse recommendations JSON")
    return []


def _validate_rec(r: dict) -> dict:
    return {
        "title":   str(r.get("title",   "Recommandation"))[:80],
        "action":  str(r.get("action",  "")),
        "urgency": r.get("urgency", "medium") if r.get("urgency") in ("low","medium","high","critical") else "medium",
        "horizon": r.get("horizon", "30_days") if r.get("horizon") in ("7_days","30_days","90_days") else "30_days",
        "domain":  r.get("domain",  "commercial") if r.get("domain") in ("commercial","rh","financier","technologique","risque") else "commercial",
    }


def _fallback_recommendations(talan_impact: float, systemic_risk: float) -> list[dict]:
    """Static fallback when LLM is unavailable."""
    recs = [
        {"title": "Surveiller l'évolution du marché",
         "action": "Mettre en place un tableau de bord hebdomadaire sur les indicateurs clés détectés par le système.",
         "urgency": "medium", "horizon": "7_days", "domain": "risque"},
        {"title": "Renforcer la relation clients stratégiques",
         "action": "Organiser des revues de compte avec les top 10 clients dans les secteurs impactés.",
         "urgency": "medium", "horizon": "30_days", "domain": "commercial"},
    ]
    if talan_impact < -0.4:
        recs.insert(0, {
            "title": "Plan de mitigation des risques prioritaire",
            "action": "Activer le comité de crise stratégique pour évaluer l'exposition de Talan aux risques identifiés.",
            "urgency": "high", "horizon": "7_days", "domain": "risque",
        })
    return recs


def _persist_recommendation(**kwargs) -> None:
    try:
        engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
        with Session(engine) as session:
            row = MarketRecommendation(**kwargs)
            session.add(row)
            session.commit()
    except Exception as e:
        logger.warning("Failed to persist recommendation: %s", e)


# ── Read helpers (for API) ────────────────────────────────────────────────────

def get_recent_recommendations(limit: int = 10) -> list[dict]:
    """Fetch most recent recommendations from DB."""
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, generated_at, trigger_event, talan_impact,
                   systemic_risk, forecast_7d, forecast_30d,
                   recommendations, model_used
            FROM market_recommendations
            ORDER BY generated_at DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
    return [dict(r._mapping) for r in rows]
