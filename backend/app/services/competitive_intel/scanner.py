"""Autonomous Competitive Intelligence Scanner.

Runs every SCAN_INTERVAL_HOURS via APScheduler (BackgroundScheduler —
same pattern as MarketAnalysisOrchestrator).

Full cycle for each company in WATCHLIST:
  Step 1 — Parallel data collection (news + jobs + financial)
  Step 2 — Radar scoring (5 axes, rule-based, free)
  Step 3 — Change detection vs last PostgreSQL snapshot
  Step 4 — Conditional LLM deep analysis (only if significant change
            OR no LLM call in last LLM_COOLDOWN_HOURS)
  Step 5 — Persist CompetitorSnapshot to PostgreSQL
  Step 6 — Upsert Competitor node + COMPETES_WITH edge in Neo4j
  Step 7 — Dispatch CompetitorAlert if shift is significant
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.competitive_intel_models import CompetitorAlert, CompetitorSnapshot

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SCAN_INTERVAL_HOURS   = 6
CHANGE_THRESHOLD      = 15      # radar axis delta that flags a significant change
FINANCIAL_DROP_PCT    = 5.0     # stock price drop (%) that flags significance
LLM_COOLDOWN_HOURS    = 12      # minimum hours between LLM calls per company

# Competitor watchlist — name → Yahoo Finance ticker (None = private)
WATCHLIST: Dict[str, Optional[str]] = {
    "Capgemini":    "CAP.PA",
    "Sopra Steria": "SOP.PA",
    "Atos":         "ATO.PA",
    "Accenture":    "ACN",
    "CGI":          "GIB",
    "Devoteam":     None,
    "Wavestone":    "WAVE.PA",
}


# ── DB engine (sync — same pattern as market analysis orchestrator) ───────────

@lru_cache(maxsize=1)
def _get_engine():
    return create_engine(settings.database_url("hr"), pool_pre_ping=True)


def _ensure_tables() -> None:
    from app.core.database import Base
    from app.models.competitive_intel_models import CompetitorSnapshot, CompetitorAlert  # noqa
    engine = _get_engine()
    Base.metadata.create_all(
        engine,
        tables=[CompetitorSnapshot.__table__, CompetitorAlert.__table__],
        checkfirst=True,
    )


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load_last_snapshot(company: str) -> Optional[Dict[str, Any]]:
    """Return the most recent snapshot dict for a company, or None."""
    engine = _get_engine()
    try:
        with Session(engine) as session:
            row = session.execute(
                text(
                    "SELECT radar_scores, threat_level, financial_data, "
                    "llm_assessment, snapshot_at "
                    "FROM ci_snapshots "
                    "WHERE company_name = :name "
                    "ORDER BY snapshot_at DESC LIMIT 1"
                ),
                {"name": company},
            ).fetchone()
            if row:
                return {
                    "radar_scores":    row[0] or {},
                    "threat_level":    row[1] or 0.0,
                    "financial_data":  row[2] or {},
                    "llm_assessment":  row[3],
                    "snapshot_at":     row[4],
                }
    except Exception as exc:
        logger.warning("_load_last_snapshot failed for %s: %s", company, exc)
    return None


def _has_recent_llm_analysis(company: str) -> bool:
    """Return True if LLM analysis was run for this company within LLM_COOLDOWN_HOURS."""
    engine = _get_engine()
    cutoff = datetime.utcnow() - timedelta(hours=LLM_COOLDOWN_HOURS)
    try:
        with Session(engine) as session:
            row = session.execute(
                text(
                    "SELECT COUNT(*) FROM ci_snapshots "
                    "WHERE company_name = :name "
                    "  AND llm_assessment IS NOT NULL "
                    "  AND snapshot_at >= :cutoff"
                ),
                {"name": company, "cutoff": cutoff},
            ).scalar()
            return (row or 0) > 0
    except Exception:
        return False


def _persist_snapshot(data: Dict[str, Any]) -> None:
    engine = _get_engine()
    try:
        with Session(engine) as session:
            row = CompetitorSnapshot(
                id=data["id"],
                company_name=data["company_name"],
                ticker=data.get("ticker"),
                scan_type=data.get("scan_type", "scheduled"),
                news_data=data.get("news_data", []),
                jobs_data=data.get("jobs_data", {}),
                financial_data=data.get("financial_data", {}),
                radar_scores=data.get("radar_scores", {}),
                threat_level=data.get("threat_level", 0.0),
                threat_label=data.get("threat_label"),
                key_moves=data.get("key_moves", []),
                anticipated_moves=data.get("anticipated_moves", []),
                hiring_signals=data.get("hiring_signals", []),
                llm_assessment=data.get("llm_assessment"),
                llm_vulnerability=data.get("llm_vulnerability"),
                llm_response=data.get("llm_response"),
                is_significant=data.get("is_significant", False),
                delta_scores=data.get("delta_scores", {}),
                change_summary=data.get("change_summary"),
                snapshot_at=datetime.utcnow(),
            )
            session.add(row)
            session.commit()
    except Exception as exc:
        logger.error("_persist_snapshot failed for %s: %s", data.get("company_name"), exc)


def _persist_alert(alert_data: Dict[str, Any]) -> None:
    engine = _get_engine()
    try:
        with Session(engine) as session:
            row = CompetitorAlert(
                id=str(uuid.uuid4()),
                company_name=alert_data["company_name"],
                alert_type=alert_data.get("alert_type", "shift_detected"),
                level=alert_data.get("level", "medium"),
                title=alert_data.get("title", ""),
                detail=alert_data.get("detail", ""),
                recommended_action=alert_data.get("recommended_action"),
                snapshot_id=alert_data.get("snapshot_id"),
            )
            session.add(row)
            session.commit()
    except Exception as exc:
        logger.warning("_persist_alert failed: %s", exc)


# ── Change detection ──────────────────────────────────────────────────────────

def _compute_delta(
    current_scores: Dict[str, float],
    previous: Optional[Dict[str, Any]],
) -> Dict[str, float]:
    """Return axis-by-axis delta vs previous snapshot. Empty dict if no previous."""
    if not previous or not previous.get("radar_scores"):
        return {}
    prev_scores = previous["radar_scores"]
    return {
        axis: round(current_scores.get(axis, 0) - prev_scores.get(axis, 0), 1)
        for axis in current_scores
    }


def _is_significant_change(
    delta: Dict[str, float],
    financial_data: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
) -> bool:
    """Return True if any radar axis moved by CHANGE_THRESHOLD or stock dropped."""
    if any(abs(v) >= CHANGE_THRESHOLD for v in delta.values()):
        return True

    # Financial: stock price drop > FINANCIAL_DROP_PCT
    price_change = financial_data.get("price_change_1m_pct")
    if price_change is not None and price_change <= -FINANCIAL_DROP_PCT:
        return True

    return False


def _describe_delta(
    company: str,
    delta: Dict[str, float],
    financial_data: Dict[str, Any],
) -> str:
    if not delta:
        return f"First scan for {company} — baseline established."
    parts = []
    for axis, d in delta.items():
        if abs(d) >= CHANGE_THRESHOLD:
            direction = "↑" if d > 0 else "↓"
            parts.append(f"{axis} {direction}{abs(d):.0f}pts")
    price = financial_data.get("price_change_1m_pct")
    if price is not None and abs(price) >= 3:
        parts.append(f"Stock {price:+.1f}% (1m)")
    return f"{company}: " + (", ".join(parts) if parts else "no significant axis movement")


# ── Financial data fetch (yfinance) ──────────────────────────────────────────

def _fetch_financial(ticker: str, company: str) -> Dict[str, Any]:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period="1mo")
        price_change = None
        if not hist.empty and len(hist) >= 2:
            price_change = round(
                (hist["Close"].iloc[-1] - hist["Close"].iloc[0])
                / hist["Close"].iloc[0] * 100, 2,
            )
        news = t.news or []
        return {
            "company":               company,
            "ticker":                ticker,
            "price_change_1m_pct":   price_change,
            "market_cap":            info.get("marketCap"),
            "pe_ratio":              info.get("trailingPE"),
            "revenue_growth_yoy":    info.get("revenueGrowth"),
            "profit_margins":        info.get("profitMargins"),
            "analyst_recommendation": info.get("recommendationKey"),
            "number_of_analysts":    info.get("numberOfAnalystOpinions"),
            "52w_high":              info.get("fiftyTwoWeekHigh"),
            "52w_low":               info.get("fiftyTwoWeekLow"),
            "recent_news_titles":    [n.get("title", "") for n in news[:5]],
            "fetched_at":            datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.warning("_fetch_financial failed for %s: %s", ticker, exc)
        return {"ticker": ticker, "error": str(exc)}


# ── LLM strategic analysis (conditional — only on significant scans) ──────────

def _run_llm_analysis(
    company: str,
    news_data: List[Dict],
    jobs_data: Dict,
    financial_data: Dict,
    radar_scores: Dict,
    landscape: Dict,
    delta: Dict,
) -> Dict[str, Any]:
    """Call the JSON LLM to produce a qualitative strategic assessment."""
    from app.core.llm import get_json_llm, invoke_with_retry
    from langchain_core.messages import HumanMessage

    news_titles = [a.get("title", "") for a in news_data[:8]]
    top_skills  = [s.get("skill") for s in jobs_data.get("top_skills_recruited", [])[:6]]
    signals     = jobs_data.get("strategic_signals", [])
    fin_summary = (
        f"Stock {financial_data.get('price_change_1m_pct', 'N/A')}% (1m), "
        f"analyst: {financial_data.get('analyst_recommendation', 'N/A')}"
        if financial_data else "No financial data available."
    )
    delta_str = ", ".join(f"{k}: {v:+.0f}pts" for k, v in delta.items() if abs(v) >= 5) or "no major delta"

    prompt = f"""You are a senior strategic analyst for Talan (French IT consulting firm).
Analyze the following data about competitor "{company}" and return ONLY valid JSON.

DATA:
- Recent news headlines: {json.dumps(news_titles, ensure_ascii=False)}
- Top skills being recruited: {top_skills}
- Strategic hiring signals: {signals}
- Financial snapshot: {fin_summary}
- Radar scores (0-100): {json.dumps(radar_scores)}
- Delta vs previous scan: {delta_str}

Return this exact JSON structure (no markdown, no explanation):
{{
  "threat_assessment": "2-sentence qualitative assessment of the competitive threat",
  "talan_vulnerability": "specific area where Talan is most exposed to this competitor",
  "recommended_response": "one concrete, actionable recommendation for Talan"
}}"""

    llm = get_json_llm()
    response = invoke_with_retry(llm, [HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)

    # Strip markdown fences if present
    content = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("```").strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "threat_assessment": content[:300],
            "talan_vulnerability": None,
            "recommended_response": None,
        }


# ── Neo4j KG update ───────────────────────────────────────────────────────────

def _update_kg(company: str, snapshot: Dict[str, Any]) -> None:
    """Upsert Competitor node and COMPETES_WITH → Talan edge in Neo4j."""
    try:
        from app.services.market_analysis.world_model import WorldModel
        import re as _re

        def _slugify(name: str) -> str:
            return _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

        wm = WorldModel()
        if not wm.is_available():
            return

        slug = _slugify(company)
        wm._upsert_node_safe(
            label="Competitor",
            slug=slug,
            name=company,
            ticker=snapshot.get("ticker"),
            source_article="ci_scanner",
        )

        now = datetime.utcnow().isoformat()
        wm._run(
            """
            MATCH (c:Competitor {slug: $slug}), (t:Company {slug: 'talan'})
            MERGE (c)-[r:COMPETES_WITH]->(t)
            ON CREATE SET
                r.threat_level  = $threat,
                r.threat_label  = $label,
                r.created_at    = $now,
                r.source        = 'ci_scanner'
            ON MATCH SET
                r.threat_level  = $threat,
                r.threat_label  = $label,
                r.updated_at    = $now
            """,
            {
                "slug":   slug,
                "threat": snapshot.get("threat_level", 0.0),
                "label":  snapshot.get("threat_label", "Faible"),
                "now":    now,
            },
        )

        # Add RECRUITS_IN edge if hiring signals detected
        if snapshot.get("hiring_signals"):
            wm._run(
                """
                MATCH (c:Competitor {slug: $slug})
                MERGE (c)-[r:RECRUITS_IN]->(s:Sector {slug: 'it-consulting'})
                ON CREATE SET
                    r.signals   = $signals,
                    r.created_at = $now,
                    s.name       = 'IT Consulting',
                    s.created_at = $now
                ON MATCH SET
                    r.signals   = $signals,
                    r.updated_at = $now
                """,
                {
                    "slug":    slug,
                    "signals": snapshot.get("hiring_signals", [])[:5],
                    "now":     now,
                },
            )

        logger.info("CI Scanner: KG updated for '%s' (threat=%.2f)", company, snapshot.get("threat_level", 0))
    except Exception as exc:
        logger.warning("_update_kg failed for %s: %s", company, exc)


# ── Alert generation ──────────────────────────────────────────────────────────

def _generate_and_persist_alerts(
    company: str,
    snapshot: Dict[str, Any],
    delta: Dict[str, float],
) -> None:
    threat_level = snapshot.get("threat_level", 0.0)
    level = (
        "critical" if threat_level >= 0.75
        else "high"   if threat_level >= 0.50
        else "medium"
    )

    # Build a human-readable description of what changed
    significant_axes = [
        f"{axis} {'+' if d > 0 else ''}{d:.0f}pts"
        for axis, d in delta.items()
        if abs(d) >= CHANGE_THRESHOLD
    ]

    price_change = snapshot.get("financial_data", {}).get("price_change_1m_pct")
    if price_change is not None and price_change <= -FINANCIAL_DROP_PCT:
        significant_axes.append(f"Stock {price_change:+.1f}% (1m)")

    alert_type = "shift_detected"
    if any("Recrutement" in a for a in significant_axes):
        alert_type = "hiring_surge"
    elif any("Stock" in a for a in significant_axes):
        alert_type = "financial_drop"
    elif any("IA" in a or "Innovation" in a for a in significant_axes):
        alert_type = "news_spike"

    title = (
        f"[{level.upper()}] {company} — Strategic shift detected: "
        + ", ".join(significant_axes[:3])
    )

    _persist_alert({
        "company_name":      company,
        "alert_type":        alert_type,
        "level":             level,
        "title":             title[:280],
        "detail":            snapshot.get("change_summary", ""),
        "recommended_action": snapshot.get("llm_response"),
        "snapshot_id":       snapshot.get("id"),
    })

    logger.warning(
        "CI ALERT [%s] %s — threat=%.2f delta=%s",
        level.upper(), company, threat_level,
        ", ".join(significant_axes),
    )


# ── Main scanner ──────────────────────────────────────────────────────────────

class CompetitiveIntelScanner:
    """Singleton autonomous scanner — mirrors MarketAnalysisOrchestrator pattern."""

    _instance: Optional["CompetitiveIntelScanner"] = None

    @classmethod
    def get_instance(cls) -> "CompetitiveIntelScanner":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._scheduler = None
        self._active   = False

    def start(self) -> None:
        _ensure_tables()
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler(timezone="UTC")
            self._scheduler.add_job(
                self._scan_all_watchlist,
                "interval",
                hours=SCAN_INTERVAL_HOURS,
                id="ci_watchlist_scan",
                max_instances=1,
                coalesce=True,
                # First run 5 min after startup to not compete with market analysis
                next_run_time=datetime.utcnow() + timedelta(minutes=5),
            )
            self._scheduler.start()
            self._active = True
            logger.info(
                "CompetitiveIntelScanner started — interval=%dh — %d companies watched",
                SCAN_INTERVAL_HOURS, len(WATCHLIST),
            )
        except Exception as exc:
            logger.error("CompetitiveIntelScanner failed to start: %s", exc)

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._active = False
        logger.info("CompetitiveIntelScanner stopped")

    # ── Internal scheduler job ────────────────────────────────────────────────

    def _scan_all_watchlist(self) -> None:
        logger.info("CI Scanner: watchlist scan starting (%d companies)", len(WATCHLIST))
        # Parallel scans — max 3 workers to avoid hammering sources
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.scan_company, name, ticker): name
                for name, ticker in WATCHLIST.items()
            }
            for future in as_completed(futures):
                company = futures[future]
                try:
                    result = future.result(timeout=60)
                    logger.info(
                        "CI Scanner: %-18s threat=%.2f  significant=%-5s  %s",
                        company,
                        result.get("threat_level", 0),
                        result.get("is_significant", False),
                        result.get("change_summary", "")[:60],
                    )
                except Exception as exc:
                    logger.exception("CI Scanner: '%s' failed — %s", company, exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def scan_company(
        self,
        company: str,
        ticker: Optional[str] = None,
        scan_type: str = "scheduled",
    ) -> Dict[str, Any]:
        """Run a full intelligence scan for one competitor. Returns the snapshot dict."""
        from app.tools.competitive_intel_tools import (
            scrape_company_news,
            scrape_job_postings,
            analyze_competitive_landscape,
        )

        logger.info("CI Scanner: scanning '%s' (ticker=%s)", company, ticker)

        # ── Step 1: Parallel data collection ──────────────────────────────────
        news_data:      List[Dict] = []
        jobs_data:      Dict       = {}
        financial_data: Dict       = {}

        with ThreadPoolExecutor(max_workers=3) as ex:
            f_news = ex.submit(
                scrape_company_news.invoke,
                {"company_name": company, "max_articles": 10},
            )
            f_jobs = ex.submit(
                scrape_job_postings.invoke,
                {"company_name": company},
            )
            f_fin = ex.submit(_fetch_financial, ticker, company) if ticker else None

            for f, label in [(f_news, "news"), (f_jobs, "jobs")]:
                try:
                    result = f.result(timeout=25)
                    if label == "news":
                        news_data = result or []
                    else:
                        jobs_data = result or {}
                except Exception as exc:
                    logger.warning("CI: %s scrape failed for %s: %s", label, company, exc)

            if f_fin:
                try:
                    financial_data = f_fin.result(timeout=20) or {}
                except Exception as exc:
                    logger.warning("CI: financial fetch failed for %s: %s", company, exc)

        # ── Step 2: Radar scoring ──────────────────────────────────────────────
        landscape = analyze_competitive_landscape.invoke({
            "companies":  [company],
            "topic":      "stratégie globale",
            "news_data":  news_data,
            "jobs_data":  jobs_data,
        })
        radar_scores = landscape.get("radar_scores", {})
        threat_level = landscape.get("threat_level", 0.0)
        threat_label = landscape.get("threat_label", "Faible")

        # ── Step 3: Change detection ───────────────────────────────────────────
        previous      = _load_last_snapshot(company)
        delta         = _compute_delta(radar_scores, previous)
        is_significant = _is_significant_change(delta, financial_data, previous)
        change_summary = _describe_delta(company, delta, financial_data)

        # ── Step 4: Conditional LLM deep analysis ─────────────────────────────
        llm_assessment = llm_vulnerability = llm_response = None
        if is_significant or not _has_recent_llm_analysis(company):
            try:
                llm_result = _run_llm_analysis(
                    company, news_data, jobs_data, financial_data,
                    radar_scores, landscape, delta,
                )
                llm_assessment   = llm_result.get("threat_assessment")
                llm_vulnerability = llm_result.get("talan_vulnerability")
                llm_response      = llm_result.get("recommended_response")
            except Exception as exc:
                logger.warning("CI: LLM analysis failed for %s: %s", company, exc)

        # ── Step 5: Build snapshot dict ────────────────────────────────────────
        snapshot_id = str(uuid.uuid4())
        snapshot = {
            "id":               snapshot_id,
            "company_name":     company,
            "ticker":           ticker,
            "scan_type":        scan_type,
            "news_data":        news_data[:10],
            "jobs_data":        jobs_data,
            "financial_data":   financial_data,
            "radar_scores":     radar_scores,
            "threat_level":     threat_level,
            "threat_label":     threat_label,
            "key_moves":        landscape.get("key_moves", []),
            "anticipated_moves": landscape.get("anticipated_moves", []),
            "hiring_signals":   landscape.get("hiring_signals", []),
            "llm_assessment":   llm_assessment,
            "llm_vulnerability": llm_vulnerability,
            "llm_response":     llm_response,
            "is_significant":   is_significant,
            "delta_scores":     delta,
            "change_summary":   change_summary,
            "snapshot_at":      datetime.utcnow().isoformat(),
        }

        # ── Step 5: Persist ────────────────────────────────────────────────────
        _persist_snapshot(snapshot)

        # ── Step 6: Update Neo4j KG ────────────────────────────────────────────
        try:
            _update_kg(company, snapshot)
        except Exception as exc:
            logger.warning("CI: KG update failed for %s: %s", company, exc)

        # ── Step 7: Dispatch alert if significant ──────────────────────────────
        if is_significant and delta:
            _generate_and_persist_alerts(company, snapshot, delta)

        return snapshot

    def run_now(
        self,
        companies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Trigger an immediate scan. Pass company names or None for full watchlist."""
        targets = (
            {c: WATCHLIST.get(c) for c in companies if c in WATCHLIST}
            if companies
            else WATCHLIST
        )
        results = {}
        for name, ticker in targets.items():
            try:
                results[name] = self.scan_company(name, ticker, scan_type="ondemand")
            except Exception as exc:
                results[name] = {"error": str(exc)}
        return results

    def get_status(self) -> Dict[str, Any]:
        engine = _get_engine()
        snapshot_count = 0
        alert_count    = 0
        try:
            with Session(engine) as session:
                snapshot_count = session.execute(
                    text("SELECT COUNT(*) FROM ci_snapshots")
                ).scalar() or 0
                alert_count = session.execute(
                    text("SELECT COUNT(*) FROM ci_alerts WHERE acknowledged = false")
                ).scalar() or 0
        except Exception:
            pass
        return {
            "active":            self._active,
            "watchlist_size":    len(WATCHLIST),
            "scan_interval_h":   SCAN_INTERVAL_HOURS,
            "snapshots_in_db":   snapshot_count,
            "unacknowledged_alerts": alert_count,
            "companies":         list(WATCHLIST.keys()),
        }
