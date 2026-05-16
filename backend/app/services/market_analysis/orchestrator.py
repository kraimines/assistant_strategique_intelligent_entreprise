"""Market Analysis Orchestrator — APScheduler-driven pipeline loop.

Full pipeline (runs every PIPELINE_INTERVAL_MINUTES):
    Step 1 — Collect   : fetch raw articles from all sources
    Step 2 — Analyse   : LLM causal extraction on new articles
    Step 3 — KG Update : upsert all analysis results into Neo4j
    Step 4 — GNN       : run heterogeneous GNN inference
    Step 5 — Report    : synthesise Markdown report + generate alerts
    Step 6 — Notify    : dispatch high-priority alerts (log / optional Slack/email)

The orchestrator is a singleton started by the FastAPI lifespan hook.
It exposes get_status(), run_now(), and start()/stop() for the API layer.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.market_analysis_models import MarketAlert as MarketAlertModel
from app.models.market_analysis_models import MarketPipelineRun, MarketReport as MarketReportModel
from app.models.market_analysis_models import MarketGNNScore
from app.schemas.market_analysis_schemas import (
    AlertLevel, MarketAlert, MarketReport, PipelineStatus,
)

logger = logging.getLogger(__name__)

PIPELINE_INTERVAL_MINUTES = int(
    getattr(settings, "market_analysis_interval_minutes", 30)
)
ALERT_IMPACT_THRESHOLD = float(
    getattr(settings, "market_alert_threshold", 0.4)
)


from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=1)
def _get_engine():
    return create_engine(settings.database_url("hr"), pool_pre_ping=True)


def _ensure_tables() -> None:
    """Create market analysis tables synchronously if they don't exist yet."""
    from app.core.database import Base
    from app.models.market_analysis_models import (  # noqa: F401 — register models
        MarketRawArticle, MarketNewsAnalysis,
        MarketAlert as _MA, MarketReport as _MR, MarketPipelineRun,
        MarketGNNScore, MarketRecommendation,  # noqa: F401 — register tables with Base.metadata
    )
    engine = _get_engine()
    Base.metadata.create_all(
        engine,
        tables=[
            MarketRawArticle.__table__,
            MarketNewsAnalysis.__table__,
            _MA.__table__,
            _MR.__table__,
            MarketPipelineRun.__table__,
        ],
        checkfirst=True,
    )


# ── Pipeline run ──────────────────────────────────────────────────────────────

class MarketAnalysisPipeline:
    """Executes one full pipeline cycle."""

    def __init__(self):
        from app.services.market_analysis.collector import MarketDataCollector
        from app.services.market_analysis.analyst import NewsAnalyst
        from app.services.market_analysis.world_model import WorldModel
        from app.services.market_analysis.gnn_predictor import GNNPredictor
        from app.services.market_analysis.policy import EdgeTypePolicy, GraphSanitizer
        from app.services.market_analysis.scoring import (
            HubPenalty, TemporalDecay, TGATCalibrator, PlausibilityScorer,
        )
        from app.services.market_analysis.ranking import PathRanker
        from app.services.market_analysis.explain import ExplanationGenerator
        from pathlib import Path as _P

        self.collector = MarketDataCollector()
        self.analyst = NewsAnalyst()
        self.world_model = WorldModel()
        self.gnn = GNNPredictor()

        # ── v3 propagation engine ──
        self.edge_policy   = EdgeTypePolicy.from_world_model(self.world_model)
        self.graph_sanitizer = GraphSanitizer(self.world_model)
        self.temporal_decay  = TemporalDecay(edge_policy=self.edge_policy)
        self._calibrator   = TGATCalibrator.load(
            _P(__file__).parent / "checkpoints" / "tgat_calibrator.pkl"
        )
        self._sanitizer_runs_today: bool = False  # cron-like guard

        # path-ranker / plausibility / explanation-generator are rebuilt per run
        # because they depend on the live snapshot (HubPenalty.fit) and on the
        # latest Talan profile.
        self._PathRanker = PathRanker
        self._HubPenalty = HubPenalty
        self._PlausibilityScorer = PlausibilityScorer
        self._ExplanationGenerator = ExplanationGenerator

    def run(self, extra_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """Execute the full pipeline. Returns a summary dict."""
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        errors: List[str] = []
        kg_nodes = 0
        kg_rels = 0
        gnn_ran = False
        report_id: Optional[str] = None

        # ── Persist run record ────────────────────────────────────────────────
        engine = _get_engine()
        with Session(engine) as session:
            run_record = MarketPipelineRun(id=run_id, started_at=started_at)
            session.add(run_record)
            session.commit()

        try:
            # ── Step 1: Collect ───────────────────────────────────────────────
            logger.info("Pipeline %s — Step 1: Collecting", run_id)
            collect_result = self.collector.run(extra_keywords=extra_keywords)
            errors += collect_result.errors

            # ── Step 2: Analyse ────────────────────────────────────────────────
            logger.info("Pipeline %s — Step 2: Analysing %d new articles",
                        run_id, collect_result.articles_new)
            unanalysed = self.collector.get_unanalysed_articles(limit=10)
            analyses, failed = self.analyst.analyse_batch(
                unanalysed, delay_between_calls=12.0
            )
            if failed:
                errors.append(f"Analyst failed on {len(failed)} articles")

            # ── Step 3: KG Update ─────────────────────────────────────────────
            logger.info("Pipeline %s — Step 3: Updating KG with %d analyses",
                        run_id, len(analyses))
            self.world_model.ensure_schema()
            self.world_model.ensure_talan_node()
            for analysis in analyses:
                try:
                    payload = self.world_model.update_from_analysis(analysis)
                    kg_nodes += len(payload.nodes)
                    kg_rels += len(payload.relations)
                except Exception as e:
                    errors.append(f"KG update failed for {analysis.article_external_id}: {e}")
                    logger.warning("KG update error: %s", e)

            # Mark analyses as KG-synced
            if analyses:
                unsynced_ids = self.analyst.get_unsynced_analyses(limit=200)
                ids = [str(r["id"]) for r in unsynced_ids]
                self.analyst.mark_kg_synced(ids)

            # ── Step 3.5: KG hygiene (low-conf prune, dup collapse, hub flag) ─
            # Cheap to run; cron-style guard prevents running it more than once
            # per process-day. The GraphSanitizer is idempotent so re-running
            # is safe but pointless.
            try:
                if not self._sanitizer_runs_today:
                    self.graph_sanitizer.run(dry_run=False)
                    self._sanitizer_runs_today = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("GraphSanitizer skipped: %s", exc)

            # ── Step 4: GNN Inference ─────────────────────────────────────────
            logger.info("Pipeline %s — Step 4: GNN inference", run_id)
            gnn_result = None
            try:
                # Restrict snapshot to causal + structural relations only —
                # MENTIONS-into-hubs noise is the main cause of bad paths.
                kg_snapshot = self.world_model.get_snapshot(
                    "Talan",
                    hops=3,
                    rel_whitelist=[
                        "CAUSES_IMPACT_ON", "IMPACTS", "INFLUENCES",
                        "COMPETES_WITH", "BELONGS_TO_SECTOR", "OPERATES_IN",
                        "SERVES_SECTOR", "OPERATES_BU", "BU_SERVES",
                        "BU_DEPENDS_ON",
                        # MENTIONS deliberately excluded — context only, never propagation
                    ],
                )
                price_data = self.collector.fetch_price_snapshot()
                # Build entity_title_map: entity_name → article headline
                # Combines current-run analyses (Pydantic) + DB history (dicts)
                entity_title_map: dict = {}

                def _etm_from_pydantic(analysis_list):
                    for a in analysis_list:
                        title = getattr(a, "article_title", "") or ""
                        for ent in (getattr(a, "entities", None) or []):
                            name = getattr(ent, "name", None) or (
                                ent.get("name") if isinstance(ent, dict) else None
                            )
                            if name and title and name not in entity_title_map:
                                entity_title_map[name] = title

                def _etm_from_dicts(rows):
                    for row in rows:
                        title = row.get("article_title") or ""
                        entities = row.get("entities") or []
                        if isinstance(entities, str):
                            import json as _json
                            try:
                                entities = _json.loads(entities)
                            except Exception:
                                entities = []
                        for ent in entities:
                            name = (ent.get("name") if isinstance(ent, dict) else None)
                            if name and title and name not in entity_title_map:
                                entity_title_map[name] = title

                _etm_from_pydantic(analyses)
                recent_for_gnn = self.analyst.get_recent_analyses(hours=72, limit=50)
                _etm_from_dicts(recent_for_gnn)

                trigger_event = (analyses[0].event_summary if analyses
                                 else (recent_for_gnn[0].get("event_summary", "periodic_scan")
                                       if recent_for_gnn else "periodic_scan"))
                kg_snapshot["entity_title_map"] = entity_title_map
                logger.info("GNN entity_title_map: %d entries", len(entity_title_map))

                # Build the v3 ranking pipeline from the *current* snapshot.
                hub_penalty = self._HubPenalty.fit(
                    kg_snapshot,
                    pagerank=self.world_model.get_pagerank(top_n=200),
                )
                talan_profile = self.world_model.get_talan_profile()
                plausibility = self._PlausibilityScorer(talan_profile=talan_profile, llm_judge=None)
                path_ranker = self._PathRanker(
                    hub_penalty=hub_penalty,
                    temporal_decay=self.temporal_decay,
                    plausibility_scorer=plausibility,
                    calibrator=self._calibrator,
                    edge_policy=self.edge_policy,
                )
                explanation_gen = self._ExplanationGenerator(talan_profile=talan_profile)

                gnn_result = self.gnn.predict_v3(
                    kg_snapshot,
                    price_data=price_data,
                    trigger_event=trigger_event,
                    edge_policy=self.edge_policy,
                    path_ranker=path_ranker,
                    explanation_generator=explanation_gen,
                    top_k_paths=10,
                )
                gnn_ran = True
                talan_impact = gnn_result.talan_prediction.predicted_impact if gnn_result.talan_prediction else 0
                logger.info(
                    "Pipeline %s — GNN: Talan impact=%.3f systemic_risk=%.3f",
                    run_id, talan_impact, gnn_result.systemic_risk_score,
                )
                # Persist GNN score for LSTM forecaster
                _persist_gnn_score(gnn_result, run_id, engine)
            except Exception as e:
                errors.append(f"GNN inference failed: {e}")
                logger.exception("GNN error: %s", e)

            # ── Step 5: Generate Report & Alerts ──────────────────────────────
            logger.info("Pipeline %s — Step 5: Generating report", run_id)
            recent_analyses = self.analyst.get_recent_analyses(hours=24, limit=20)
            alerts = _generate_alerts(recent_analyses, gnn_result)
            report = _build_report(
                run_id=run_id,
                analyses=recent_analyses,
                alerts=alerts,
                gnn_result=gnn_result,
                kg_nodes=kg_nodes,
                kg_rels=kg_rels,
            )
            report_id = report.report_id if report else None

            # ── Step 6: Notify ────────────────────────────────────────────────
            logger.info("Pipeline %s — Step 6: Dispatching notifications", run_id)
            critical_alerts = [a for a in alerts if a.level in (AlertLevel.HIGH, AlertLevel.CRITICAL)]
            for alert in critical_alerts:
                _dispatch_alert(alert)

        except Exception as e:
            errors.append(f"Pipeline fatal error: {e}")
            logger.exception("Pipeline %s fatal error: %s", run_id, e)

        # ── Finalise run record ───────────────────────────────────────────────
        finished_at = datetime.utcnow()
        with Session(engine) as session:
            session.execute(
                text(
                    "UPDATE market_pipeline_runs SET "
                    "finished_at=:fin, status=:st, "
                    "articles_fetched=:af, articles_analysed=:aa, "
                    "kg_nodes_added=:kn, kg_relations_added=:kr, "
                    "gnn_ran=:gr, report_id=:rid, errors=:err "
                    "WHERE id=:run_id"
                ),
                {
                    "fin": finished_at,
                    "st": "failed" if errors else "completed",
                    "af": collect_result.articles_fetched if "collect_result" in dir() else 0,
                    "aa": len(analyses) if "analyses" in dir() else 0,
                    "kn": kg_nodes,
                    "kr": kg_rels,
                    "gr": gnn_ran,
                    "rid": report_id,
                    "err": json.dumps(errors[:10]),
                    "run_id": run_id,
                },
            )
            session.commit()

        elapsed = (finished_at - started_at).total_seconds()
        logger.info(
            "Pipeline %s finished in %.1fs — %d errors",
            run_id, elapsed, len(errors)
        )
        return {
            "run_id": run_id,
            "elapsed_seconds": elapsed,
            "errors": errors,
            "kg_nodes_added": kg_nodes,
            "kg_relations_added": kg_rels,
            "gnn_ran": gnn_ran,
            "report_id": report_id,
        }


# ── GNN score persistence ─────────────────────────────────────────────────────

def _persist_gnn_score(gnn_result: Any, pipeline_run_id: str, engine) -> None:
    """Save one GNN inference result row to market_gnn_scores."""
    try:
        tp = gnn_result.talan_prediction
        hidden = gnn_result.top_hidden_risks or []
        with Session(engine) as session:
            row = MarketGNNScore(
                trigger_event      = gnn_result.trigger_event[:500] if gnn_result.trigger_event else "periodic_scan",
                talan_impact       = float(tp.predicted_impact) if tp else 0.0,
                systemic_risk      = float(gnn_result.systemic_risk_score),
                talan_confidence   = float(tp.confidence) if tp else 0.0,
                hidden_risks_count = len(hidden),
                top_hidden_risks   = [
                    {"name": r.entity_name, "impact": r.predicted_impact}
                    for r in hidden
                ],
                all_predictions    = [
                    {"name": p.entity_name, "impact": p.predicted_impact,
                     "hops": p.propagation_hops, "hidden": p.hidden_risk}
                    for p in (gnn_result.predictions or [])
                ],
                pipeline_run_id    = pipeline_run_id,
            )
            session.add(row)
            session.commit()
            logger.info("GNN score persisted (talan_impact=%.3f)", row.talan_impact)
    except Exception as e:
        logger.warning("Failed to persist GNN score: %s", e)


# ── Alert generation ──────────────────────────────────────────────────────────

def _generate_alerts(
    analyses: List[Dict[str, Any]],
    gnn_result: Optional[Any],
) -> List[MarketAlert]:
    alerts: List[MarketAlert] = []

    # LLM-based alerts: high talan_impact_score
    for analysis in analyses:
        score = float(analysis.get("talan_impact_score", 0.0))
        if abs(score) >= ALERT_IMPACT_THRESHOLD:
            level = (
                AlertLevel.CRITICAL if abs(score) >= 0.7
                else AlertLevel.HIGH if abs(score) >= 0.5
                else AlertLevel.MEDIUM
            )
            urgency = analysis.get("urgency", "medium")
            alert = MarketAlert(
                alert_id=str(uuid.uuid4()),
                level=level,
                title=f"[{level.upper()}] {analysis.get('event_summary', '')[:80]}",
                summary=analysis.get("talan_impact_reason", ""),
                affected_entities=[
                    e.get("name", "") for e in (analysis.get("entities") or [])[:5]
                ],
                talan_impact_score=score,
                talan_recommended_action=analysis.get("talan_action_recommended"),
                source_articles=[analysis.get("article_external_id", "")],
            )
            alerts.append(alert)
            _persist_alert(alert)

    # GNN-based alerts: hidden risks
    if gnn_result:
        for pred in gnn_result.top_hidden_risks:
            if abs(pred.predicted_impact) >= 0.3:
                alert = MarketAlert(
                    alert_id=str(uuid.uuid4()),
                    level=AlertLevel.HIGH,
                    title=f"🔴 Risque Caché GNN : {pred.entity_name} → Talan (impact={pred.predicted_impact:+.2f})",
                    summary=(
                        f"Le modèle GNN a détecté un risque propagé en {pred.propagation_hops} sauts "
                        f"depuis {pred.entity_name} vers Talan. "
                        f"Probabilité: {pred.confidence*100:.0f}%"
                    ),
                    affected_entities=[pred.entity_name, "Talan"],
                    talan_impact_score=pred.predicted_impact,
                    gnn_hidden_risks=[pred.entity_name],
                )
                alerts.append(alert)
                _persist_alert(alert)

        # Systemic risk alert
        if gnn_result.systemic_risk_score >= 0.6:
            alert = MarketAlert(
                alert_id=str(uuid.uuid4()),
                level=AlertLevel.CRITICAL,
                title=f"⚠️ Risque Systémique Détecté — Score: {gnn_result.systemic_risk_score:.1%}",
                summary=f"Le modèle GNN signale un risque systémique élevé. Évènement déclencheur: {gnn_result.trigger_event}",
                affected_entities=["Marché Global", "Talan"],
                talan_impact_score=gnn_result.talan_prediction.predicted_impact if gnn_result.talan_prediction else 0.0,
            )
            alerts.append(alert)
            _persist_alert(alert)

    return alerts


def _persist_alert(alert: MarketAlert) -> None:
    engine = _get_engine()
    try:
        with Session(engine) as session:
            row = MarketAlertModel(
                id=alert.alert_id,
                level=alert.level.value,
                title=alert.title,
                summary=alert.summary,
                affected_entities=alert.affected_entities,
                talan_impact_score=alert.talan_impact_score,
                talan_recommended_action=alert.talan_recommended_action,
                source_articles=alert.source_articles,
                gnn_hidden_risks=alert.gnn_hidden_risks,
            )
            session.add(row)
            session.commit()
    except Exception as e:
        logger.warning("Failed to persist alert: %s", e)


def _build_report(
    run_id: str,
    analyses: List[Dict],
    alerts: List[MarketAlert],
    gnn_result: Optional[Any],
    kg_nodes: int,
    kg_rels: int,
) -> Optional[MarketReport]:
    """Build and persist a MarketReport."""
    if not analyses and not alerts:
        return None

    now = datetime.utcnow()
    period_start = now - timedelta(hours=24)

    # Compute overall risk level
    max_score = max((abs(float(a.get("talan_impact_score", 0) or 0)) for a in analyses), default=0.0)
    risk_level = (
        AlertLevel.CRITICAL if max_score >= 0.7
        else AlertLevel.HIGH if max_score >= 0.5
        else AlertLevel.MEDIUM if max_score >= 0.3
        else AlertLevel.LOW
    )

    recommended = [
        a.talan_recommended_action
        for a in alerts
        if a.talan_recommended_action
    ][:5]

    report_id = str(uuid.uuid4())
    engine = _get_engine()
    try:
        with Session(engine) as session:
            row = MarketReportModel(
                id=report_id,
                period_start=period_start,
                period_end=now,
                executive_summary=_build_executive_summary(analyses, alerts),
                talan_risk_level=risk_level.value,
                talan_impact_summary=_build_impact_summary(analyses),
                recommended_actions=recommended,
                key_events_json=analyses[:10],
                alerts_json=[a.model_dump(mode='json') for a in alerts],
                gnn_predictions_json=gnn_result.model_dump(mode='json') if gnn_result else None,
                kg_nodes_added=kg_nodes,
                kg_relations_added=kg_rels,
            )
            session.add(row)
            session.commit()
    except Exception as e:
        logger.error("Failed to persist report: %s", e)
        return None

    from app.schemas.market_analysis_schemas import MarketReport as MarketReportSchema
    return MarketReportSchema(
        report_id=report_id,
        period_start=period_start,
        period_end=now,
        executive_summary=_build_executive_summary(analyses, alerts),
        key_events=[],
        alerts=alerts,
        gnn_predictions=gnn_result,
        talan_risk_level=risk_level,
        talan_impact_summary=_build_impact_summary(analyses),
        recommended_actions=recommended,
        kg_nodes_added=kg_nodes,
        kg_relations_added=kg_rels,
    )


def _build_executive_summary(analyses: List[Dict], alerts: List[MarketAlert]) -> str:
    critical = [a for a in alerts if a.level == AlertLevel.CRITICAL]
    high = [a for a in alerts if a.level == AlertLevel.HIGH]
    parts = [
        f"Période analysée : dernières 24h. "
        f"{len(analyses)} articles traités, {len(alerts)} alertes générées.",
    ]
    if critical:
        parts.append(f"⚠️ {len(critical)} alerte(s) CRITIQUE(S) : {critical[0].title[:60]}")
    if high:
        parts.append(f"🔶 {len(high)} alerte(s) HAUTE : {high[0].title[:60]}")
    if not critical and not high:
        parts.append("✅ Aucun risque majeur détecté pour Talan.")
    return " | ".join(parts)


def _build_impact_summary(analyses: List[Dict]) -> str:
    if not analyses:
        return "Aucune analyse disponible pour cette période."
    scores = [float(a.get("talan_impact_score", 0)) for a in analyses]
    avg = sum(scores) / len(scores)
    worst = min(scores)
    return (
        f"Impact moyen sur Talan : {avg:+.2f}/1.0. "
        f"Impact le plus sévère : {worst:+.2f}. "
        f"Basé sur {len(analyses)} articles analysés."
    )


def _dispatch_alert(alert: MarketAlert) -> None:
    """Dispatch a critical alert. Currently logs; extend with Slack/email."""
    logger.critical(
        "MARKET ALERT [%s] %s — Talan impact: %+.2f",
        alert.level.upper(),
        alert.title,
        alert.talan_impact_score,
    )
    # TODO: integrate Slack webhook or email via settings.slack_webhook_url


# ── Singleton Orchestrator ────────────────────────────────────────────────────

class MarketAnalysisOrchestrator:
    """Singleton that manages the APScheduler job for the pipeline."""

    _instance: Optional["MarketAnalysisOrchestrator"] = None

    def __init__(self):
        self._scheduler = None
        self._pipeline: Optional[MarketAnalysisPipeline] = None
        self._last_run_at: Optional[datetime] = None
        self._next_run_at: Optional[datetime] = None
        self._last_errors: List[str] = []
        self._scheduler_active = False   # scheduler alive and will fire jobs
        self._cycle_running = False      # a pipeline cycle is currently executing

    @classmethod
    def get_instance(cls) -> "MarketAnalysisOrchestrator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_pipeline(self) -> MarketAnalysisPipeline:
        if self._pipeline is None:
            self._pipeline = MarketAnalysisPipeline()
        return self._pipeline

    def start(self) -> None:
        """Start the APScheduler background job.

        Uses BackgroundScheduler (thread-based) instead of AsyncIOScheduler
        to avoid conflicts with FastAPI's event loop.
        """
        _ensure_tables()
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self._scheduler = BackgroundScheduler(timezone="UTC")
            self._scheduler.add_job(
                self._run_pipeline_job_sync,
                "interval",
                minutes=PIPELINE_INTERVAL_MINUTES,
                id="market_analysis_pipeline",
                max_instances=1,
                coalesce=True,
                next_run_time=datetime.utcnow() + timedelta(minutes=PIPELINE_INTERVAL_MINUTES),
            )
            self._scheduler.start()
            self._scheduler_active = True
            self._next_run_at = datetime.utcnow() + timedelta(minutes=PIPELINE_INTERVAL_MINUTES)
            logger.info(
                "MarketAnalysisOrchestrator started — interval=%dm — next run: %s",
                PIPELINE_INTERVAL_MINUTES,
                self._next_run_at.strftime("%H:%M UTC"),
            )
        except Exception as e:
            logger.error("Failed to start orchestrator scheduler: %s", e)
            self._scheduler_active = False

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._scheduler_active = False
        logger.info("MarketAnalysisOrchestrator stopped")

    def _run_pipeline_job_sync(self) -> None:
        """Synchronous job called by BackgroundScheduler in its own thread."""
        try:
            self._cycle_running = True
            result = self._get_pipeline().run()
            self._last_run_at = datetime.utcnow()
            self._next_run_at = self._last_run_at + timedelta(minutes=PIPELINE_INTERVAL_MINUTES)
            self._last_errors = result.get("errors", [])
        except Exception as e:
            logger.exception("Scheduled pipeline run failed: %s", e)
            self._last_errors = [str(e)]
        finally:
            self._cycle_running = False

    def run_now(self, extra_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """Trigger an immediate synchronous pipeline run (for API endpoint)."""
        self._cycle_running = True
        try:
            pipeline = self._get_pipeline()
            result = pipeline.run(extra_keywords=extra_keywords)
            self._last_run_at = datetime.utcnow()
            self._last_errors = result.get("errors", [])
            if not self._scheduler_active:
                # Auto-start scheduler on first manual run if not yet started
                self.start()
            return result
        finally:
            self._cycle_running = False

    def get_status(self) -> PipelineStatus:
        """Return current pipeline status for the /status API endpoint."""
        engine = _get_engine()
        article_count = 0
        try:
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT COUNT(*) FROM market_raw_articles")
                ).scalar()
                article_count = int(row or 0)
        except Exception:
            pass

        kg_stats = {}
        try:
            from app.services.market_analysis.world_model import WorldModel as _WM
            # Use pipeline's WorldModel if available, else create a fresh one.
            # This fixes the "0 nodes" bug that appeared before the first pipeline
            # cycle: self._pipeline was None on startup so the stats query was skipped.
            wm = self._pipeline.world_model if self._pipeline else _WM()
            if wm.is_available():
                kg_stats = wm.get_stats()
        except Exception:
            pass

        last_report_id: Optional[str] = None
        try:
            with Session(engine) as session:
                row = session.execute(
                    text(
                        "SELECT id FROM market_reports ORDER BY generated_at DESC LIMIT 1"
                    )
                ).scalar()
                last_report_id = str(row) if row else None
        except Exception:
            pass

        return PipelineStatus(
            running=self._scheduler_active,
            cycle_running=self._cycle_running,
            last_run_at=self._last_run_at,
            next_run_at=self._next_run_at,
            articles_in_db=article_count,
            kg_nodes=kg_stats.get("total_nodes", 0),
            kg_relations=kg_stats.get("total_relations", 0),
            last_report_id=last_report_id,
            errors_last_run=self._last_errors[:5],
        )
