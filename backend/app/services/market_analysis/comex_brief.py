"""Comex Brief generator — server-side PDF rendering.

Aggregates the live pipeline data (top alerts, propagation paths,
recommendations, forecast) and renders a 1-2 page executive PDF that the
manager can hand to their N+1 without copy-pasting into PowerPoint.

The function ``build_brief_pdf`` returns the raw PDF bytes; the FastAPI
route streams them to the browser with a sensible filename.

Dependency: ``reportlab`` (added to requirements.txt). All numeric data
comes from the existing Market Analysis services, so the brief stays in
sync with whatever the dashboard shows.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Helpers — pull live data from the existing services ─────────────────────


def _safe_get_alerts(days: int, max_n: int) -> List[Dict[str, Any]]:
    """Top alerts of the period, sorted by impact then recency."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings
    engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, level, title, summary, talan_impact_score, "
                    "       talan_recommended_action, generated_at "
                    "FROM market_alerts WHERE generated_at >= :cutoff "
                    "ORDER BY (CASE level "
                    "  WHEN 'critical' THEN 4 WHEN 'high' THEN 3 "
                    "  WHEN 'medium' THEN 2 ELSE 1 END) DESC, "
                    "  ABS(COALESCE(talan_impact_score,0)) DESC, "
                    "  generated_at DESC LIMIT :lim"
                ),
                {"cutoff": cutoff, "lim": max_n},
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("brief: alerts fetch failed: %s", exc)
        return []


def _safe_get_recommendations(max_n: int) -> List[Dict[str, Any]]:
    """Most recent strategic recommendations."""
    try:
        from app.services.market_analysis.recommender import get_recent_recommendations
        recs = get_recent_recommendations(limit=1) or []
        if not recs:
            return []
        latest = recs[0] or {}
        items = latest.get("recommendations") or []
        return items[:max_n]
    except Exception as exc:
        logger.warning("brief: recommendations fetch failed: %s", exc)
        return []


def _safe_get_forecast() -> Optional[Dict[str, Any]]:
    try:
        from app.services.market_analysis.forecaster import forecast, load_gnn_series
        series = load_gnn_series(hours=720)
        if not series:
            return None
        return forecast(series)
    except Exception as exc:
        logger.warning("brief: forecast fetch failed: %s", exc)
        return None


def _safe_get_top_paths(max_n: int) -> List[Dict[str, Any]]:
    """Run a fresh GNN inference and return the top-N propagation paths."""
    try:
        from app.services.market_analysis.world_model import WorldModel
        from app.services.market_analysis.gnn_predictor import GNNPredictor
        wm = WorldModel()
        if not wm.is_available():
            return []
        snap = wm.get_snapshot("Talan", hops=2)
        gnn  = GNNPredictor()
        res  = gnn.predict(snap, price_data=None, trigger_event="comex_brief")
        paths = list(getattr(res, "propagation_paths", []) or [])
        paths.sort(key=lambda p: abs(getattr(p, "weighted_score", 0) or 0), reverse=True)
        out: List[Dict[str, Any]] = []
        for p in paths[:max_n]:
            d = p.model_dump() if hasattr(p, "model_dump") else dict(p)
            out.append(d)
        return out
    except Exception as exc:
        logger.warning("brief: paths fetch failed: %s", exc)
        return []


def _safe_get_trust_score(days: int = 90) -> Optional[float]:
    """Aggregated trust score across all manager feedback in the window."""
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
        cutoff = datetime.utcnow() - timedelta(days=days)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT rating, COUNT(*) AS n FROM market_manager_feedback "
                    "WHERE submitted_at >= :cutoff GROUP BY rating"
                ),
                {"cutoff": cutoff},
            ).mappings().all()
        counts = {r["rating"]: int(r["n"]) for r in rows}
        total = sum(counts.values())
        if total == 0:
            return None
        rel = counts.get("relevant", 0)
        nua = counts.get("nuanced", 0)
        return round((rel + 0.5 * nua) / total, 3)
    except Exception as exc:
        logger.debug("brief: trust score fetch failed: %s", exc)
        return None


# ── PDF rendering ──────────────────────────────────────────────────────────


_SEVERITY_TO_COLOR = {
    "critical": (0.86, 0.15, 0.15),
    "high":     (0.92, 0.36, 0.10),
    "medium":   (0.85, 0.54, 0.02),
    "low":      (0.08, 0.65, 0.32),
}


def build_brief_pdf(
    period_days: int = 7,
    include_paths: bool = True,
    include_alerts: bool = True,
    include_recommendations: bool = True,
    include_forecast: bool = True,
    max_paths: int = 5,
    max_alerts: int = 5,
    generated_by: str = "TALAN Intelligence Entreprise",
) -> bytes:
    """Build the Comex Brief PDF and return its raw bytes."""
    # Late import so the rest of the codebase still imports cleanly when
    # reportlab is not yet installed in a dev environment.
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether,
    )
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT

    # ── Data ────────────────────────────────────────────────────────────
    period_end   = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=period_days)
    alerts          = _safe_get_alerts(period_days, max_alerts) if include_alerts else []
    recommendations = _safe_get_recommendations(max_alerts)     if include_recommendations else []
    forecast_data   = _safe_get_forecast()                      if include_forecast else None
    paths           = _safe_get_top_paths(max_paths)            if include_paths else []
    trust_score     = _safe_get_trust_score(days=90)

    critical_count = sum(1 for a in alerts if (a.get("level") == "critical"))
    high_count     = sum(1 for a in alerts if (a.get("level") == "high"))
    opportunities  = sum(
        1 for p in paths
        if (p.get("estimated_business_impact_pct") or 0) > 0
    )

    avg_confidence = None
    if paths:
        confs = [float(p.get("confidence") or 0) for p in paths]
        if confs:
            avg_confidence = round(sum(confs) / len(confs), 2)

    # ── Styles ──────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=9, leading=12, alignment=TA_LEFT,
    )
    bold = ParagraphStyle(
        "bold", parent=body, fontName="Helvetica-Bold",
    )
    title = ParagraphStyle(
        "title", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=2,
        textColor=colors.HexColor("#0B1F4A"),
    )
    subtitle = ParagraphStyle(
        "subtitle", parent=body, fontSize=10, textColor=colors.HexColor("#475569"),
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=12, leading=16,
        textColor=colors.HexColor("#0B1F4A"), spaceBefore=8, spaceAfter=4,
    )
    item_title = ParagraphStyle(
        "item_title", parent=body, fontName="Helvetica-Bold", fontSize=10,
        textColor=colors.HexColor("#111827"),
    )
    item_meta = ParagraphStyle(
        "item_meta", parent=body, fontSize=8, textColor=colors.HexColor("#6B7280"),
    )
    footer = ParagraphStyle(
        "footer", parent=body, fontSize=7.5, textColor=colors.HexColor("#94A3B8"),
        alignment=TA_RIGHT,
    )

    # ── Document ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        title="Note d'intelligence stratégique — Talan",
        author=generated_by,
    )
    story: List[Any] = []

    # Header
    story.append(Paragraph("TALAN — Note d'intelligence stratégique", title))
    period_label = f"{period_start.strftime('%d %b %Y')} → {period_end.strftime('%d %b %Y')}"
    story.append(Paragraph(f"Période : {period_label}", subtitle))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceBefore=4, spaceAfter=8))

    # KPI strip
    kpi_data = [[
        Paragraph(f"<b>{critical_count}</b><br/><font size=7 color='#64748B'>critiques</font>", body),
        Paragraph(f"<b>{high_count}</b><br/><font size=7 color='#64748B'>élevés</font>", body),
        Paragraph(f"<b>{opportunities}</b><br/><font size=7 color='#64748B'>opportunités</font>", body),
        Paragraph(
            f"<b>{int((avg_confidence or 0)*100)}%</b><br/><font size=7 color='#64748B'>confiance moy.</font>"
            if avg_confidence is not None
            else "<b>—</b><br/><font size=7 color='#64748B'>confiance moy.</font>", body),
    ]]
    kpi_table = Table(kpi_data, colWidths=[44*mm, 44*mm, 44*mm, 44*mm])
    kpi_table.setStyle(TableStyle([
        ("BOX",          (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ("INNERGRID",    (0,0), (-1,-1), 0.4, colors.HexColor("#E2E8F0")),
        ("BACKGROUND",   (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 8))

    # Forecast band
    if forecast_data:
        f7  = forecast_data.get("forecast_7d")
        f30 = forecast_data.get("forecast_30d")
        trend = forecast_data.get("trend", "stable")
        trend_fr = {"improving": "Amélioration", "deteriorating": "Dégradation"}.get(trend, "Stable")

        def _fmt(v: Optional[float]) -> str:
            if v is None:
                return "N/A"
            return f"{v:+.3f}"

        forecast_line = (
            f"<b>Prévision LSTM</b> · 7j : <b>{_fmt(f7)}</b> · "
            f"30j : <b>{_fmt(f30)}</b> · tendance : <b>{trend_fr}</b>"
        )
        story.append(Paragraph(forecast_line, body))
        story.append(Spacer(1, 6))

    # ── Section: risques critiques (paths + alerts unified) ──────────
    story.append(Paragraph("Risques &amp; opportunités prioritaires", h2))

    items_rendered = 0
    for idx, p in enumerate(paths[:max_paths], 1):
        expl = p.get("explanation") or {}
        head    = (expl.get("headline") or "").strip()
        if not head:
            head = (p.get("event_title") or p.get("source_name") or "Chemin de propagation").strip()
        impact_pct = p.get("estimated_business_impact_pct") or 0.0
        sev        = (expl.get("severity") or "").lower()
        sev_color  = _SEVERITY_TO_COLOR.get(sev, (0.4, 0.4, 0.4))
        action     = (expl.get("recommended_action") or p.get("narrative") or "").strip()
        owner      = (expl.get("recommended_owner") or "").strip()
        deadline   = (expl.get("deadline_label") or p.get("time_horizon_label") or "").strip()
        money      = (expl.get("financial_impact_eur") or "").strip()

        # Severity color bar
        sev_label = sev or "—"
        bar = Table(
            [[Paragraph(
                f"<font color='white'><b>&nbsp;{sev_label.upper()}&nbsp;</b></font>",
                ParagraphStyle("sev", parent=body, fontSize=7.5))]],
            colWidths=[18*mm],
        )
        bar.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), colors.Color(*sev_color)),
            ("BOX",        (0,0),(-1,-1), 0.3, colors.Color(*sev_color)),
            ("ALIGN",      (0,0),(-1,-1), "CENTER"),
            ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ]))

        impact_str = f"{impact_pct:+.1f}% CA Talan"
        title_row = Table(
            [[
                bar,
                Paragraph(f"<b>{idx}.</b> {head}", item_title),
                Paragraph(f"<b>{impact_str}</b>", ParagraphStyle("imp", parent=item_title, alignment=TA_RIGHT)),
            ]],
            colWidths=[20*mm, 115*mm, 45*mm],
        )
        title_row.setStyle(TableStyle([
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ]))

        meta_bits: List[str] = []
        if action:   meta_bits.append(f"<b>Action :</b> {action[:220]}")
        if owner:    meta_bits.append(f"<b>Owner :</b> {owner}")
        if deadline: meta_bits.append(f"<b>Échéance :</b> {deadline}")
        if money:    meta_bits.append(f"<b>Impact financier :</b> {money}")
        meta_par = Paragraph("<br/>".join(meta_bits) if meta_bits else "—", item_meta)

        story.append(KeepTogether([
            title_row,
            Spacer(1, 1),
            meta_par,
            Spacer(1, 6),
        ]))
        items_rendered += 1

    # Add any alerts that are not yet covered by paths
    seen = {(p.get("explanation") or {}).get("headline", "")[:80] for p in paths}
    for a in alerts:
        if items_rendered >= max_paths + max_alerts:
            break
        head = (a.get("title") or "").strip()
        if head[:80] in seen:
            continue
        sev = (a.get("level") or "low").lower()
        sev_color = _SEVERITY_TO_COLOR.get(sev, (0.4, 0.4, 0.4))
        action = (a.get("talan_recommended_action") or a.get("summary") or "").strip()
        impact = a.get("talan_impact_score")
        impact_str = f"impact {impact:+.2f}" if isinstance(impact, (int, float)) else "—"

        bar = Table(
            [[Paragraph(f"<font color='white'><b>&nbsp;{sev.upper()}&nbsp;</b></font>",
                        ParagraphStyle("sev", parent=body, fontSize=7.5))]],
            colWidths=[18*mm],
        )
        bar.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), colors.Color(*sev_color)),
            ("BOX",        (0,0),(-1,-1), 0.3, colors.Color(*sev_color)),
            ("ALIGN",      (0,0),(-1,-1), "CENTER"),
            ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
        ]))

        items_rendered += 1
        title_row = Table(
            [[
                bar,
                Paragraph(f"<b>{items_rendered}.</b> {head} <font color='#94A3B8' size=8>(alerte)</font>", item_title),
                Paragraph(f"<b>{impact_str}</b>", ParagraphStyle("imp", parent=item_title, alignment=TA_RIGHT)),
            ]],
            colWidths=[20*mm, 115*mm, 45*mm],
        )
        title_row.setStyle(TableStyle([
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ]))
        meta = Paragraph(
            f"<b>Action :</b> {action[:220]}" if action else "—",
            item_meta,
        )
        story.append(KeepTogether([title_row, Spacer(1, 1), meta, Spacer(1, 6)]))

    if items_rendered == 0:
        story.append(Paragraph(
            "<i>Aucun risque ou opportunité au-dessus du seuil sur cette période — situation stable.</i>",
            body,
        ))

    # ── Strategic recommendations ──────────────────────────────────────
    if recommendations:
        story.append(Spacer(1, 4))
        story.append(Paragraph("Recommandations stratégiques", h2))
        for i, rec in enumerate(recommendations, 1):
            urg = (rec.get("urgency") or "medium").lower()
            sev_color = _SEVERITY_TO_COLOR.get(urg, (0.4, 0.4, 0.4))
            horizon   = rec.get("horizon") or ""
            domain    = rec.get("domain") or ""
            head      = rec.get("title") or "—"
            action    = rec.get("action") or ""

            bar = Table(
                [[Paragraph(f"<font color='white'><b>&nbsp;{urg.upper()}&nbsp;</b></font>",
                            ParagraphStyle("sev", parent=body, fontSize=7.5))]],
                colWidths=[18*mm],
            )
            bar.setStyle(TableStyle([
                ("BACKGROUND", (0,0),(-1,-1), colors.Color(*sev_color)),
                ("BOX",        (0,0),(-1,-1), 0.3, colors.Color(*sev_color)),
                ("ALIGN",      (0,0),(-1,-1), "CENTER"),
                ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
            ]))
            title_row = Table(
                [[
                    bar,
                    Paragraph(f"<b>R{i}.</b> {head}", item_title),
                    Paragraph(f"<i>{domain} · {horizon}</i>",
                              ParagraphStyle("meta_r", parent=item_meta, alignment=TA_RIGHT)),
                ]],
                colWidths=[20*mm, 115*mm, 45*mm],
            )
            title_row.setStyle(TableStyle([
                ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
                ("BOTTOMPADDING", (0,0),(-1,-1), 2),
            ]))
            story.append(KeepTogether([
                title_row,
                Spacer(1, 1),
                Paragraph(action[:280] or "—", item_meta),
                Spacer(1, 6),
            ]))

    # ── Footer ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")))
    trust_str = (
        f" · Trust manager : {int((trust_score or 0)*100)}%"
        if trust_score is not None else ""
    )
    story.append(Paragraph(
        f"Généré par {generated_by} le "
        f"{period_end.strftime('%d %b %Y %H:%M UTC')}"
        f"{trust_str}",
        footer,
    ))

    doc.build(story)
    return buf.getvalue()
