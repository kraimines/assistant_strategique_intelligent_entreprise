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

@router.get(
    "/market/gnn/predict",
    summary="GNN inference",
    description="Run on-demand GNN inference on the current Knowledge Graph state.",
)
async def gnn_predict(
    trigger: str = Query("on_demand", description="Trigger event description"),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        from app.services.market_analysis.world_model import WorldModel
        from app.services.market_analysis.gnn_predictor import GNNPredictor
        from app.services.market_analysis.collector import MarketDataCollector

        wm = WorldModel()
        if not wm.is_available():
            raise HTTPException(status_code=503, detail="Neo4j unavailable")

        kg_snapshot = wm.get_snapshot("Talan", hops=2)
        price_data = MarketDataCollector().fetch_price_snapshot()
        gnn = GNNPredictor()
        result = gnn.predict(kg_snapshot, price_data=price_data, trigger_event=trigger)
        return result.model_dump()
    except HTTPException:
        raise
    except Exception as e:
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
