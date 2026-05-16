"""FastAPI routes for the Market Analysis Agent.

Endpoints:
    GET  /api/v1/market/status         — pipeline status
    POST /api/v1/market/run            — trigger immediate pipeline run
    GET  /api/v1/market/alerts         — list recent alerts
    GET  /api/v1/market/reports        — list recent reports
    GET  /api/v1/market/reports/{id}   — get specific report
    GET  /api/v1/market/kg/snapshot    — KG ego-graph around Talan
    GET  /api/v1/market/kg/risks       — direct risks on Talan
    GET  /api/v1/market/kg/hidden      — hidden causal chains
    GET  /api/v1/market/gnn/predict    — run GNN inference on demand
    GET  /api/v1/market/analyses       — recent LLM analyses
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.api.deps import get_current_user
from app.core.database import get_session
from app.schemas.market_analysis_schemas import (
    ManualSimulationRequest,
    ManualSimulationResult,
    QuickSimulationRequest,
    MarketAlert,
    MarketAnalysisRequest,
    MarketAnalysisResponse,
    PipelineStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_orchestrator():
    from app.services.market_analysis.orchestrator import MarketAnalysisOrchestrator
    return MarketAnalysisOrchestrator.get_instance()


# ── Status ────────────────────────────────────────────────────────────────────

@router.get(
    "/market/status",
    response_model=PipelineStatus,
    summary="Pipeline status",
    description="Returns current status of the market analysis background pipeline.",
)
async def get_pipeline_status(
    current_user: dict = Depends(get_current_user),
):
    try:
        orchestrator = _get_orchestrator()
        return orchestrator.get_status()
    except Exception as e:
        logger.exception("get_pipeline_status error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Trigger pipeline ──────────────────────────────────────────────────────────

@router.post(
    "/market/run",
    response_model=MarketAnalysisResponse,
    summary="Trigger pipeline run",
    description="Immediately trigger one full market analysis cycle (blocking).",
)
async def run_pipeline(
    request: MarketAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    # Only managers and admins can trigger manual runs
    role = getattr(current_user, "role", "employee")
    if role not in ("admin", "manager"):
        raise HTTPException(
            status_code=403,
            detail="Seuls les managers et admins peuvent déclencher une analyse manuelle.",
        )
    try:
        import asyncio
        orchestrator = _get_orchestrator()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: orchestrator.run_now(extra_keywords=request.tickers or None),
        )
        return MarketAnalysisResponse(
            status="completed" if not result.get("errors") else "completed_with_errors",
            message=(
                f"Pipeline terminé en {result.get('elapsed_seconds', 0):.1f}s. "
                f"KG: +{result.get('kg_nodes_added', 0)} nœuds, "
                f"+{result.get('kg_relations_added', 0)} relations. "
                f"GNN: {'✓' if result.get('gnn_ran') else '✗'}. "
                + (f"Erreurs: {len(result.get('errors', []))}" if result.get("errors") else "")
            ),
        )
    except Exception as e:
        logger.exception("run_pipeline error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get(
    "/market/alerts",
    summary="Recent market alerts",
    description="List recent market alerts sorted by severity.",
)
async def get_alerts(
    limit: int = Query(20, ge=1, le=100),
    level: Optional[str] = Query(None, description="Filter by level: low|medium|high|critical"),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        base_q = "SELECT * FROM market_alerts"
        params: Dict[str, Any] = {"lim": limit}
        if level:
            base_q += " WHERE level = :level"
            params["level"] = level
        base_q += " ORDER BY generated_at DESC LIMIT :lim"
        async for db in get_session("hr"):
            result = await db.execute(text(base_q), params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]
        return []
    except Exception as e:
        logger.exception("get_alerts error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get(
    "/market/reports",
    summary="Recent market reports",
    description="List recent market analysis reports.",
)
async def list_reports(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        async for db in get_session("hr"):
            result = await db.execute(
                text(
                    "SELECT id, generated_at, period_start, period_end, "
                    "       talan_risk_level, executive_summary, kg_nodes_added, kg_relations_added "
                    "FROM market_reports ORDER BY generated_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            )
            return [dict(r) for r in result.mappings().all()]
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/reports/{report_id}",
    summary="Get full report",
    description="Retrieve the full content of a specific market analysis report.",
)
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        async for db in get_session("hr"):
            result = await db.execute(
                text("SELECT * FROM market_reports WHERE id = :rid"),
                {"rid": report_id},
            )
            row = result.mappings().first()
            if not row:
                raise HTTPException(status_code=404, detail="Rapport introuvable")
            return dict(row)
        raise HTTPException(status_code=404, detail="Rapport introuvable")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Knowledge Graph ───────────────────────────────────────────────────────────

@router.get(
    "/market/kg/snapshot",
    summary="KG ego-graph snapshot",
    description="Return the Knowledge Graph ego-graph around a company (default: Talan).",
)
async def get_kg_snapshot(
    company: str = Query("Talan", description="Company name"),
    hops: int = Query(2, ge=1, le=3),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        return wm.get_snapshot(company, hops=hops)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/kg/risks",
    summary="Direct risks on Talan",
    description="All direct CAUSES_IMPACT_ON edges pointing at Talan in the KG.",
)
async def get_talan_kg_risks(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        return wm.get_talan_risks()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/kg/hidden",
    summary="Hidden causal chains",
    description="Discover non-obvious causal chains reaching Talan (2-3 hops).",
)
async def get_hidden_risks(
    max_hops: int = Query(3, ge=2, le=4),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        return wm.find_hidden_risks("Talan", max_hops=max_hops)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/kg/pagerank",
    summary="KG PageRank scores",
    description=(
        "Compute PageRank centrality on the Knowledge Graph. "
        "Uses Neo4j GDS if available, falls back to Cypher-based approximation. "
        "Returns nodes sorted by importance — used for node sizing in the 3D visualizer."
    ),
)
async def get_pagerank(
    top_n: int = Query(40, ge=5, le=100),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        return wm.get_pagerank(top_n=top_n)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_pagerank error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/kg/temporal",
    summary="Temporal impact evolution",
    description="Return the time-series of impact scores pointing at an entity.",
)
async def get_temporal_evolution(
    entity: str = Query("Talan", description="Entity name to track"),
    hours:  int = Query(168, ge=1, le=720),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        return wm.get_temporal_evolution(entity_name=entity, hours=hours)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/kg/full",
    summary="Full Knowledge Graph",
    description="Return ALL nodes and edges from the Knowledge Graph (capped at limit).",
)
async def get_kg_full(
    limit: int = Query(1200, ge=100, le=3000),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        from neo4j import GraphDatabase as _GDB
        from app.core.config import settings

        uri  = settings.neo4j_uri
        user = settings.neo4j_user
        pwd  = settings.neo4j_password

        node_q = """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN [
            'Company','Competitor','Sector','Country','Regulation',
            'MacroIndicator','Event','Department','Account','Project',
            'BusinessUnit','Person','Technology','MarketTrend'
        ])
        WITH n LIMIT $lim
        RETURN
            elementId(n)                                    AS id,
            labels(n)                                       AS labels,
            COALESCE(n.name, n.event_label, n.id, '?')     AS name,
            n.impact_score                                  AS impact_score,
            n.is_historical                                 AS is_historical,
            n.event_type                                    AS event_type,
            n.date                                          AS date
        """

        edge_q = """
        MATCH (a)-[r]->(b)
        WHERE any(label IN labels(a) WHERE label IN [
            'Company','Competitor','Sector','Country','Regulation',
            'MacroIndicator','Event','Department','Account','Project',
            'BusinessUnit','Person','Technology','MarketTrend'
        ])
        AND any(label IN labels(b) WHERE label IN [
            'Company','Competitor','Sector','Country','Regulation',
            'MacroIndicator','Event','Department','Account','Project',
            'BusinessUnit','Person','Technology','MarketTrend'
        ])
        WITH a, r, b LIMIT $lim
        RETURN
            elementId(a)   AS `from`,
            elementId(b)   AS `to`,
            type(r)        AS type,
            r.weight       AS weight,
            r.impact_score AS impact_score,
            r.confidence   AS confidence,
            r.reasoning    AS reason
        """

        import asyncio
        loop = asyncio.get_event_loop()

        def _query():
            driver = _GDB.driver(uri, auth=(user, pwd))
            try:
                with driver.session() as s:
                    nodes = [dict(r) for r in s.run(node_q, lim=limit)]
                    edges = [dict(r) for r in s.run(edge_q, lim=limit * 2)]
                return {"nodes": nodes, "edges": edges}
            finally:
                driver.close()

        result = await loop.run_in_executor(None, _query)
        return result

    except Exception as e:
        logger.exception("get_kg_full error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/kg/stats",
    summary="KG statistics",
    description="Node and relation counts per type in the Knowledge Graph.",
)
async def get_kg_stats(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            return {"available": False, "message": "Neo4j unavailable"}
        return {**wm.get_stats(), "available": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GNN ───────────────────────────────────────────────────────────────────────

_HORIZON_PRIORITY = {"immediate": 0, "short_term": 1, "medium_term": 2, "long_term": 3}
_HORIZON_LABELS   = {
    "immediate":   "1-2 semaines",
    "short_term":  "2-4 semaines",
    "medium_term": "1-3 mois",
    "long_term":   "3-6 mois",
}


def _combined_horizon(horizons: List[str]) -> str:
    if not horizons:
        return "2-4 semaines"
    max_h = max(horizons, key=lambda h: _HORIZON_PRIORITY.get(h, 1))
    return _HORIZON_LABELS.get(max_h, "2-4 semaines")


def _build_narrative(path_nodes: List[str], path_node_types: List[str],
                     reasons: List[str], chain_score: float) -> str:
    if not path_nodes:
        return ""
    source      = path_nodes[0]
    source_type = (path_node_types[0] or "").lower() if path_node_types else ""

    if "event" in source_type:
        intro = f"L'événement **{source}**"
    elif "competitor" in source_type:
        intro = f"Le concurrent **{source}**"
    elif "macro" in source_type:
        intro = f"L'indicateur macro **{source}**"
    elif "regulation" in source_type:
        intro = f"La réglementation **{source}**"
    elif "sector" in source_type:
        intro = f"Le secteur **{source}**"
    else:
        intro = f"**{source}**"

    chain_parts: List[str] = []
    for i, reason in enumerate(reasons or []):
        if reason and reason.strip():
            chain_parts.append(reason.strip())
        elif i + 1 < len(path_nodes):
            node_type = (path_node_types[i + 1] or "").lower() if i + 1 < len(path_node_types) else ""
            next_node = path_nodes[i + 1]
            if "sector" in node_type:
                chain_parts.append(f"affectant le secteur {next_node}")
            elif node_type in ("company", "client"):
                chain_parts.append(f"impactant le client {next_node}")
            elif "macro" in node_type:
                chain_parts.append(f"faisant pression sur {next_node}")
            else:
                chain_parts.append(f"influençant {next_node}")

    chain_text = " → ".join(chain_parts) if chain_parts else "propagation causale détectée"

    severity = abs(chain_score)
    if severity >= 0.7:
        conclusion = "Risque critique — action immédiate recommandée."
    elif severity >= 0.4:
        conclusion = "Impact significatif prévu sur le pipeline commercial de Talan."
    else:
        conclusion = "Impact modéré sur les activités de Talan à surveiller."

    return f"{intro} : {chain_text}. {conclusion}"


def _build_propagation_paths(hidden_risks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from app.schemas.market_analysis_schemas import PropagationPath, PropagationStep

    paths = []
    for risk in hidden_risks:
        path_nodes      = list(risk.get("path_nodes") or [])
        path_node_types = list(risk.get("path_node_types") or [])
        reasons         = list(risk.get("reasons") or [])
        path_rel_types  = list(risk.get("path_rel_types") or [])
        path_scores     = list(risk.get("path_scores") or [])
        path_horizons   = list(risk.get("path_horizons") or [])

        steps = []
        for i, node in enumerate(path_nodes):
            steps.append(PropagationStep(
                node_name    = node,
                node_type    = path_node_types[i] if i < len(path_node_types) else "Company",
                relation_type= path_rel_types[i]  if i < len(path_rel_types)  else "CAUSES_IMPACT_ON",
                reason       = reasons[i]          if i < len(reasons)         else "",
                impact_score = float(path_scores[i]) if i < len(path_scores)   else 0.0,
                time_horizon = path_horizons[i]    if i < len(path_horizons)   else "short_term",
            ))

        narrative = _build_narrative(path_nodes, path_node_types, reasons,
                                     float(risk.get("chain_score") or 0.0))

        paths.append(PropagationPath(
            source_name        = risk.get("source") or "",
            source_type        = risk.get("source_type") or "Company",
            steps              = steps,
            chain_score        = float(risk.get("chain_score") or 0.0),
            chain_conf         = float(risk.get("chain_conf") or 0.0),
            hops               = int(risk.get("hops") or len(steps)),
            time_horizon_label = _combined_horizon(path_horizons),
            narrative          = narrative,
        ).model_dump())

    return paths


@router.get(
    "/market/gnn/predict",
    summary="GNN inference",
    description="Run on-demand GNN inference on the current Knowledge Graph state.",
)
async def gnn_predict(
    trigger: str = Query("on_demand", description="Trigger event description"),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    import asyncio
    import json as _json

    def _run_gnn_sync() -> Dict[str, Any]:
        from pathlib import Path as _P
        from datetime import datetime, timezone as _tz
        from app.services.market_analysis.world_model import WorldModel
        from app.services.market_analysis.gnn_predictor import GNNPredictor
        from app.services.market_analysis.collector import MarketDataCollector
        from app.services.market_analysis.analyst import NewsAnalyst as MarketAnalyst
        from app.services.market_analysis.policy import EdgeTypePolicy
        from app.services.market_analysis.scoring.hub_penalty import HubPenalty
        from app.services.market_analysis.scoring.temporal_decay import TemporalDecay
        from app.services.market_analysis.scoring.plausibility import PlausibilityScorer
        from app.services.market_analysis.scoring.calibration import TGATCalibrator
        from app.services.market_analysis.ranking import PathRanker
        from app.services.market_analysis.explain.explanation_generator import ExplanationGenerator
        from app.services.market_analysis.synthetic_enricher import SyntheticEnricher

        wm = WorldModel()
        if not wm.is_available():
            raise ConnectionError("neo4j_unavailable")

        # Causal + structural relations only — MENTIONS is deliberately excluded.
        # hops=2 keeps the base snapshot small (faster TGAT inference).
        # SyntheticEnricher adds mechanism nodes on top, so 2-hop chains still reach
        # exposure nodes via: Entity→M1→M2→ExposureNode→Talan (4 hops).
        kg_snapshot = wm.get_snapshot(
            "Talan", hops=2,
            rel_whitelist=[
                "CAUSES_IMPACT_ON", "IMPACTS", "INFLUENCES",
                "COMPETES_WITH", "BELONGS_TO_SECTOR", "OPERATES_IN",
                "SERVES_SECTOR", "AFFECTS_INDICATOR", "TRIGGERS_EVENT",
                "SUPPLY_CHAIN_LINK", "ACQUIRED",
                # synthetic mechanism edges (not in Neo4j, but hint to keep whitelist consistent)
                "DRIVES", "ENABLES", "REDUCES", "RESTRICTS", "GENERATES", "DEPENDS_ON",
            ],
        )
        # Price data is used for market signals but not for propagation paths.
        # Skip to avoid 5-second Yahoo Finance network call on every prediction.
        price_data = None

        # ── SyntheticEnricher: inject dramatic multi-hop mechanism chains ─────
        # This applies the 21 event-category templates to ALL real entities in
        # the snapshot, creating 3-4 hop chains:
        #   EVENT → MECHANISM → SECONDARY EFFECT → EXPOSURE → Talan
        try:
            # Limit to 30 recent analyses (not 200) to keep enrichment fast.
            # The SyntheticEnricher also processes snapshot entities, so we get
            # coverage from the KG even with a small analysis window.
            recent_rows = MarketAnalyst().get_recent_analyses(hours=168, limit=30)
            entity_title_map: dict = {}
            extracted_entities_for_enricher: list = []
            seen_ent_names: set = set()
            for row in recent_rows:
                row_title    = row.get("article_title") or ""
                row_entities = row.get("entities") or []
                if isinstance(row_entities, str):
                    try: row_entities = _json.loads(row_entities)
                    except Exception: row_entities = []
                for ent in row_entities:
                    name = ent.get("name") if isinstance(ent, dict) else None
                    if name and row_title and name not in entity_title_map:
                        entity_title_map[name] = row_title
                    if isinstance(ent, dict) and ent.get("name") and ent["name"] not in seen_ent_names:
                        seen_ent_names.add(ent["name"])
                        etype = (ent.get("type") or ent.get("label") or "company").lower()
                        extracted_entities_for_enricher.append({
                            "name": ent["name"],
                            "type": etype,
                            "id": ent.get("id") or ent["name"].lower().replace(" ", "-"),
                        })
            kg_snapshot["entity_title_map"] = entity_title_map

            enricher    = SyntheticEnricher()
            kg_snapshot = enricher.enrich(
                kg_snapshot,
                extracted_entities=extracted_entities_for_enricher,
                published_at=datetime.now(_tz.utc),
            )
            logger.info(
                "gnn_predict: SyntheticEnricher applied — snapshot now %d nodes, %d edges",
                len(kg_snapshot.get("nodes", [])),
                len(kg_snapshot.get("edges", [])),
            )
        except Exception as exc:
            logger.warning("gnn_predict: SyntheticEnricher failed: %s", exc)

        # v3 ranking pipeline — same wiring as /market/simulate so the
        # endpoint surfaces director-grade explanations.
        edge_policy  = EdgeTypePolicy.from_world_model(wm)
        hub_penalty  = HubPenalty.fit(kg_snapshot, pagerank=wm.get_pagerank(top_n=200))
        temporal_dec = TemporalDecay(edge_policy=edge_policy)
        calibrator   = TGATCalibrator.load(
            _P(__file__).resolve().parent.parent.parent
            / "services" / "market_analysis" / "checkpoints" / "tgat_calibrator.pkl"
        )
        talan_profile   = wm.get_talan_profile()
        plausibility    = PlausibilityScorer(talan_profile=talan_profile, llm_judge=None)
        path_ranker     = PathRanker(
            hub_penalty=hub_penalty, temporal_decay=temporal_dec,
            plausibility_scorer=plausibility, calibrator=calibrator,
            edge_policy=edge_policy,
        )
        explanation_gen = ExplanationGenerator(talan_profile=talan_profile)

        gnn    = GNNPredictor()
        result = gnn.predict_v3(
            kg_snapshot, price_data=price_data, trigger_event=trigger,
            edge_policy=edge_policy,
            path_ranker=path_ranker,
            explanation_generator=explanation_gen,
            top_k_paths=30,
        )
        return result.model_dump()

    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_gnn_sync)
    except ConnectionError as e:
        if "neo4j_unavailable" in str(e):
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Dedicated explain LLM — enriches paths + generates strategic advice ──────

_EXPLAIN_SYSTEM = """Tu es un conseiller stratégique senior pour Talan (ESN française, 4 000 consultants, spécialisée en transformation numérique, cloud, IA et conseil).

Ta mission : analyser l'impact d'un événement de marché sur Talan et produire :
1. Pour chaque chemin de propagation : une explication causale précise en français (2-3 phrases) + une recommandation concrète et actionnableque Talan peut mettre en œuvre immédiatement.
2. Un conseil stratégique global (4-6 phrases en style consulting) qui synthétise la situation et indique clairement ce que Talan devrait faire.

Règles :
- Sois spécifique à Talan en tant que groupe unique : mentionne ses secteurs clients (banque, assurance, secteur public) et compétences clés (cloud AWS/Azure, IA générative, data engineering). Ne décompose pas Talan en sous-entités ou business units.
- Les recommandations doivent être actionnables dans les 30-90 jours.
- Utilise un ton professionnel, direct, sans jargon inutile.
- Réponds UNIQUEMENT en JSON valide, sans texte avant ou après."""

def _enrich_simulation_with_llm(
    event_text: str,
    talan_impact_pct: float,
    paths: list,
    llm_callable,
) -> dict:
    """One LLM call (explain LLM) to enrich all paths + generate strategic_advice.

    Returns dict with keys:
      - paths_enrichment: list of {causal_reasoning, recommended_action}
      - strategic_advice: str
    """
    import json as _json
    import re as _re
    from langchain_core.messages import HumanMessage, SystemMessage

    if not paths:
        paths_block = "Aucun chemin de propagation identifié."
    else:
        lines = []
        for i, p in enumerate(paths[:15], 1):  # cap at 15 to stay within token budget
            p_dict = p.model_dump() if hasattr(p, "model_dump") else (p if isinstance(p, dict) else {})
            source = p_dict.get("source_name", "?")
            steps  = " → ".join(s.get("node_name", "?") for s in (p_dict.get("steps") or []))
            impact = p_dict.get("estimated_business_impact_pct", 0.0)
            lines.append(f"  Chemin {i}: {source} → {steps} → Talan  (impact estimé : {impact:+.1f}%)")
        paths_block = "\n".join(lines)

    n_paths = min(len(paths), 15)
    direction = "positif (opportunité)" if talan_impact_pct >= 0 else "négatif (menace)"

    user_msg = f"""Événement analysé : {event_text}

Impact GNN prédit sur Talan : {talan_impact_pct:+.1f}%  ({direction})

{n_paths} chemin(s) de propagation identifiés :
{paths_block}

Génère le JSON suivant (exactement {n_paths} objets dans "paths") :
{{
  "paths": [
    {{"causal_reasoning": "...", "recommended_action": "..."}},
    ...
  ],
  "strategic_advice": "conseil stratégique global pour Talan (4-6 phrases)"
}}"""

    try:
        response = llm_callable([SystemMessage(content=_EXPLAIN_SYSTEM), HumanMessage(content=user_msg)])
        raw = response.content if hasattr(response, "content") else str(response)
        # Strip markdown fences
        raw = _re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=_re.MULTILINE)
        raw = _re.sub(r"\s*```$", "", raw, flags=_re.MULTILINE)
        data = _json.loads(raw)
        return {
            "paths_enrichment": data.get("paths", []),
            "strategic_advice":  str(data.get("strategic_advice", "")),
        }
    except Exception as exc:
        logger.warning("explain LLM failed: %s", exc)
        return {"paths_enrichment": [], "strategic_advice": ""}


# ── Human-in-the-loop: natural-language what-if simulation ───────────────────

def _run_simulation_sync(
    event_text: str,
    category: Optional[str],
    commit: bool,
) -> Dict[str, Any]:
    """All blocking I/O for simulate_event — runs in a thread-pool worker."""
    from uuid import uuid4
    from datetime import datetime, timezone
    from pathlib import Path as _P
    from app.services.market_analysis.analyst import NewsAnalyst
    from app.services.market_analysis.world_model import WorldModel
    from app.services.market_analysis.gnn_predictor import GNNPredictor
    from app.services.market_analysis.policy import EdgeTypePolicy
    from app.services.market_analysis.scoring import (
        HubPenalty, TemporalDecay, TGATCalibrator, PlausibilityScorer,
    )
    from app.services.market_analysis.ranking import PathRanker
    from app.services.market_analysis.explain import ExplanationGenerator

    analyst = NewsAnalyst()
    sim_id  = str(uuid4())
    now     = datetime.now(timezone.utc)

    category_hint = f"[Category: {category}]\n\n" if category else ""
    enriched_text = category_hint + event_text

    analysis = analyst.analyse_article(
        article_id   = sim_id,
        external_id  = f"sim_{sim_id[:8]}",
        title        = event_text[:120],
        content      = enriched_text,
        source       = "manual_simulation",
        published_at = now,
        language     = "en",
    )

    if analysis is None:
        raise ValueError("llm_failed")

    wm = WorldModel()
    if not wm.is_available():
        raise ConnectionError("neo4j_unavailable")

    # rel_whitelist=None → toutes les relations Neo4j sont incluses (pas de filtre)
    # hops=4 → exploration plus profonde du graphe de connaissance
    base_snapshot = wm.get_snapshot(
        "Talan",
        hops=4,
        rel_whitelist=None,
    )

    event_text_lower = event_text.lower()
    structural_types = {"sector", "country", "macroindicator", "regulation", "event"}

    def _entity_is_relevant(e) -> bool:
        if e.name.lower() == "talan":
            return True
        etype = (e.type.value if e.type else "").lower()
        if etype in structural_types:
            return True
        name_lower = e.name.lower()
        words = [w for w in name_lower.split() if len(w) > 3]
        return name_lower in event_text_lower or any(w in event_text_lower for w in words)

    relevant_entities  = [e for e in analysis.entities if _entity_is_relevant(e)]
    relevant_names     = {e.name for e in relevant_entities}
    relevant_relations = [
        r for r in analysis.causal_relations
        if r.from_entity in relevant_names or r.to_entity in relevant_names
    ]

    logger.info(
        "Simulation entity filter: %d → %d entities, %d → %d relations",
        len(analysis.entities), len(relevant_entities),
        len(analysis.causal_relations), len(relevant_relations),
    )

    manual_entities = [
        {
            "name":   e.name,
            "type":   e.label or e.type.value,
            "sector": (e.properties or {}).get("sector"),
            "country":(e.properties or {}).get("country"),
            "ticker": e.ticker,
        }
        for e in relevant_entities
    ]
    manual_relations = [
        {
            "from_entity":   r.from_entity,
            "to_entity":     r.to_entity,
            "relation_type": r.relation_type.value if r.relation_type else "CAUSES_IMPACT_ON",
            "impact_score":  r.impact_score,
            "confidence":    r.confidence,
            "reason":        r.reason,
            "time_horizon":  r.time_horizon or "short_term",
            "evidence":      r.evidence or "",
        }
        for r in relevant_relations
    ]

    augmented = wm.augment_snapshot(
        base_snapshot,
        manual_entities=manual_entities,
        manual_relations=manual_relations,
        news_title=analysis.article_title or event_text[:80],
        severity=float(analysis.severity or 0.5),
    )

    # Inject synthetic economic mechanism nodes + semantic edges
    from app.services.market_analysis.synthetic_enricher import SyntheticEnricher
    enricher  = SyntheticEnricher()
    enriched_entities = [
        {"name": e.name, "type": e.type.value if e.type else "event",
         "label": e.label or "Event", "id": e.name}
        for e in relevant_entities
    ]
    augmented = enricher.enrich(augmented, extracted_entities=enriched_entities, published_at=now)

    edge_policy  = EdgeTypePolicy.from_world_model(wm)
    hub_penalty  = HubPenalty.fit(augmented, pagerank=wm.get_pagerank(top_n=200))
    temporal_dec = TemporalDecay(edge_policy=edge_policy)
    calibrator   = TGATCalibrator.load(
        _P(__file__).resolve().parent.parent.parent
        / "services" / "market_analysis" / "checkpoints" / "tgat_calibrator.pkl"
    )
    talan_profile   = wm.get_talan_profile()
    plausibility    = PlausibilityScorer(talan_profile=talan_profile, llm_judge=None)
    path_ranker     = PathRanker(
        hub_penalty=hub_penalty, temporal_decay=temporal_dec,
        plausibility_scorer=plausibility, calibrator=calibrator,
        edge_policy=edge_policy,
    )
    explanation_gen = ExplanationGenerator(talan_profile=talan_profile)

    gnn    = GNNPredictor()
    result = gnn.predict_v3(
        augmented, price_data=None,
        trigger_event=f"sim:{event_text[:60]}",
        edge_policy=None,        # pas de gate — toutes les relations sont visibles
        path_ranker=path_ranker,
        explanation_generator=explanation_gen,
        top_k_paths=30,
    )

    committed = False
    if commit:
        wm.commit_simulation(
            manual_entities=manual_entities,
            manual_relations=manual_relations,
            news_title=analysis.article_title or event_text[:80],
            severity=float(analysis.severity or 0.5),
            urgency=analysis.urgency or "medium",
            source="manual_simulation",
        )
        committed = True

    paths      = list(result.propagation_paths or [])
    talan_pct  = 0.0
    talan_prob = 0.0
    if paths:
        top       = max(paths, key=lambda p: abs(getattr(p, "weighted_score", 0)))
        talan_pct = float(getattr(top, "estimated_business_impact_pct", 0.0))
        talan_prob= float(getattr(top, "impact_probability", 0.0))
    elif result.talan_prediction:
        raw_impact = float(result.talan_prediction.predicted_impact)
        talan_pct  = max(-35.0, min(35.0, raw_impact * 35.0))
        talan_prob = float(result.talan_prediction.confidence) * 0.5

    # ── Dedicated explain LLM: enrich path explanations + strategic advice ──
    from app.core.llm import get_explain_llm, invoke_with_retry
    from app.schemas.market_analysis_schemas import PropagationExplanation

    explain_llm = get_explain_llm()
    enrichment  = _enrich_simulation_with_llm(event_text, talan_pct, paths, explain_llm.invoke)
    strategic_advice = enrichment.get("strategic_advice", "")
    path_enrichments = enrichment.get("paths_enrichment", [])

    # Merge LLM enrichment back into each path's explanation fields
    for i, path in enumerate(paths):
        llm_data = path_enrichments[i] if i < len(path_enrichments) else {}
        if llm_data and (path.explanation is not None or llm_data):
            causal  = str(llm_data.get("causal_reasoning", ""))
            action  = str(llm_data.get("recommended_action", ""))
            if path.explanation is not None:
                # Overwrite heuristic fields with LLM output
                if causal:
                    path.explanation.causal_reasoning = causal
                if action:
                    path.explanation.recommended_action = action
            elif causal or action:
                # No heuristic explanation — create one from LLM output only
                paths[i] = path.model_copy(update={"explanation": PropagationExplanation(
                    causal_reasoning=causal,
                    affected_business_unit="Talan",
                    affected_sector="IT Services",
                    risk_category="tech_disruption",
                    severity="medium",
                    recommended_action=action,
                    time_horizon="short",
                )})

    meta = augmented.get("simulation_meta", {})
    out  = ManualSimulationResult(
        simulation_id          = sim_id,
        committed              = committed,
        talan_impact_pct       = talan_pct,
        talan_impact_prob      = max(0.0, min(1.0, talan_prob)),
        systemic_risk_score    = float(result.systemic_risk_score or 0.0),
        propagation_paths      = paths,
        filtered_path_count    = int(result.filtered_path_count or 0),
        rejected_path_count    = int(result.rejected_path_count or 0),
        augmented_node_count   = int(meta.get("added_entities", 0)),
        augmented_edge_count   = int(meta.get("added_edges", 0)),
        extracted_entities        = [e.name for e in relevant_entities],
        extracted_relations_count = len(relevant_relations),
        llm_event_summary      = analysis.event_summary or "",
        strategic_advice       = strategic_advice,
    )
    return out.model_dump()


@router.post(
    "/market/simulate",
    summary="Simulate impact of a free-text event on Talan",
    description=(
        "The manager describes an event in plain text. The LLM extracts entities "
        "and causal relations automatically (same analyst as the live pipeline), "
        "then the GNN propagation engine predicts Talan's impact. Transient by "
        "default — set commit=true to persist the scenario to Neo4j."
    ),
)
async def simulate_event(
    payload: QuickSimulationRequest,
    commit: bool = Query(False, description="Persist the extracted scenario to Neo4j"),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    import asyncio
    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _run_simulation_sync(payload.event_text, payload.category, commit),
        )
        return result
    except ValueError as e:
        if "llm_failed" in str(e):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Le modèle de langage n'a pas pu analyser cet événement. "
                    "Vérifiez les quotas LLM et réessayez."
                ),
            )
        raise HTTPException(status_code=500, detail=str(e))
    except ConnectionError as e:
        if "neo4j_unavailable" in str(e):
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("simulate_event error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Analyses ──────────────────────────────────────────────────────────────────

@router.get(
    "/market/analyses",
    summary="Recent LLM analyses",
    description="Fetch the most recent causal analyses extracted by the LLM.",
)
async def get_recent_analyses(
    hours: int = Query(24, ge=1, le=168),
    min_impact: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        from app.services.market_analysis.analyst import NewsAnalyst
        return NewsAnalyst().get_recent_analyses(
            hours=hours, min_talan_impact=min_impact, limit=limit
        )
    except Exception as e:
        logger.exception("get_recent_analyses error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/prices",
    summary="Live price snapshot",
    description="Fetch current price/volume/volatility for tracked tickers.",
)
async def get_prices(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        from app.services.market_analysis.collector import MarketDataCollector
        return MarketDataCollector().fetch_price_snapshot()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Enriched news (new classifier pipeline) ───────────────────────────────────

@router.get(
    "/market/news/enriched",
    summary="Enriched & classified news",
    description=(
        "Run the new high-impact collector pipeline and return articles enriched with "
        "impact_score (1–10), categories, key_entities, and talent/competition impact. "
        "Only articles with impact_score >= min_impact are returned."
    ),
)
async def get_enriched_news(
    min_impact: int = Query(5, ge=1, le=10, description="Minimum impact score to include (1–10)"),
    tier1_only: bool = Query(False, description="Only parse Tier-1 RSS feeds (faster)"),
    live: bool = Query(False, description="Force live fetch from external sources even if DB has data"),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        import asyncio
        from app.services.market_analysis.collector import MarketDataCollector
        collector = MarketDataCollector()

        # Serve from DB first (fast, no external calls)
        if not live:
            db_results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: collector.get_enriched_from_db(hours=48, min_impact=min_impact, limit=50),
            )
            if db_results:
                return db_results

        # Fall back to live fetch when DB is empty or live=true
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: collector.run_enriched(min_impact=min_impact, rss_tier1_only=tier1_only),
        )
        return results
    except Exception as e:
        logger.exception("get_enriched_news error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Forecast ──────────────────────────────────────────────────────────────────

@router.get(
    "/market/forecast",
    summary="LSTM impact forecast",
    description="Predict Talan impact score at 7d and 30d using the LSTM forecaster trained on GNN time-series.",
)
async def get_forecast(
    hours: int = Query(720, ge=24, le=8760, description="History window in hours (default 30 days)"),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        import asyncio
        from app.services.market_analysis.forecaster import forecast, load_gnn_series
        series = await asyncio.get_event_loop().run_in_executor(
            None, lambda: load_gnn_series(hours=hours)
        )
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: forecast(series)
        )
        result["data_points"] = len(series)
        return result
    except Exception as e:
        logger.exception("forecast error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Recommendations ───────────────────────────────────────────────────────────

@router.post(
    "/market/recommend",
    summary="Generate strategic recommendations",
    description="Run GNN inference + LSTM forecast and generate LLM strategic recommendations for Talan.",
)
async def get_recommendations(
    trigger: str = Query("on_demand", description="Trigger event description"),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        import asyncio
        from app.services.market_analysis.world_model import WorldModel
        from app.services.market_analysis.gnn_predictor import GNNPredictor
        from app.services.market_analysis.collector import MarketDataCollector
        from app.services.market_analysis.forecaster import forecast, load_gnn_series
        from app.services.market_analysis.recommender import generate_recommendations

        loop = asyncio.get_event_loop()

        # 1. GNN inference
        from app.services.market_analysis.analyst import NewsAnalyst as MarketAnalyst
        import json as _json

        wm = WorldModel()
        if not wm.is_available():
            raise HTTPException(status_code=503, detail="Neo4j unavailable")
        kg_snapshot = await loop.run_in_executor(None, lambda: wm.get_snapshot("Talan", hops=3))
        price_data  = await loop.run_in_executor(None, MarketDataCollector().fetch_price_snapshot)

        # Enrich with article titles
        recent_rows_sa = await loop.run_in_executor(
            None, lambda: MarketAnalyst().get_recent_analyses(hours=72, limit=50)
        )
        etm_sa: dict = {}
        for row in recent_rows_sa:
            row_title = row.get("article_title") or ""
            row_ents  = row.get("entities") or []
            if isinstance(row_ents, str):
                try: row_ents = _json.loads(row_ents)
                except Exception: row_ents = []
            for ent in row_ents:
                n = ent.get("name") if isinstance(ent, dict) else None
                if n and row_title and n not in etm_sa:
                    etm_sa[n] = row_title
        kg_snapshot["entity_title_map"] = etm_sa

        gnn         = GNNPredictor()
        gnn_result  = await loop.run_in_executor(
            None, lambda: gnn.predict(kg_snapshot, price_data=price_data, trigger_event=trigger)
        )
        wm.close()

        # 2. Forecast
        series        = await loop.run_in_executor(None, lambda: load_gnn_series(hours=720))
        forecast_data = await loop.run_in_executor(None, lambda: forecast(series))

        # 3. Recommendations
        result = await loop.run_in_executor(
            None,
            lambda: generate_recommendations(
                gnn_result=gnn_result.model_dump(),
                forecast_result=forecast_data,
            )
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("recommend error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market/recommend/history",
    summary="Recent recommendations",
    description="Fetch the last N strategic recommendations from the database.",
)
async def list_recommendations(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        from app.services.market_analysis.recommender import get_recent_recommendations
        return get_recent_recommendations(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
