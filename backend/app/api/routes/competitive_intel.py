"""REST API routes for the competitive intelligence dashboard.

These routes are consumed directly by the frontend visualization page
(independent of the LangGraph chatbot pipeline).

Endpoints
---------
GET  /competitive-intel/scan   — full scan: news + jobs + analysis
GET  /competitive-intel/news   — news only for one company
GET  /competitive-intel/jobs   — job postings only for one company
GET  /competitive-intel/cache/clear — invalidate scraping cache
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.routes.auth import get_current_user
from app.tools.competitive_intel_tools import (
    _CACHE,
    analyze_competitive_landscape,
    scrape_company_news,
    scrape_job_postings,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/competitive-intel", tags=["competitive-intel"])


# ── Response schemas ──────────────────────────────────────────────────────────

class ScanResponse(BaseModel):
    companies: list[str]
    topic: str
    news: list[dict[str, Any]]
    jobs: dict[str, Any]
    analysis: dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_tool(tool_fn, **kwargs) -> Any:
    """Invoke a LangChain tool synchronously and surface errors as HTTP 502."""
    try:
        return tool_fn.invoke(kwargs)
    except Exception as exc:
        logger.exception("competitive-intel tool error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Scraping error: {exc}") from exc


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/scan", response_model=None)
async def scan_competitors(
    companies: str = Query(..., description="Comma-separated company names, e.g. 'Sopra Steria,Vermeg'"),
    topic: str = Query("intelligence artificielle", description="Strategic topic to analyze"),
    max_news: int = Query(8, ge=1, le=20),
    _user=Depends(get_current_user),
) -> dict:
    """Run a full competitive intelligence scan: news + jobs + analysis.

    Scrapes Google News RSS and Indeed RSS for each company, then synthesizes
    a structured radar report. Results are cached for 1 hour.

    Returns a JSON object with: companies, topic, news, jobs, analysis.
    """
    company_list = [c.strip() for c in companies.split(",") if c.strip()]
    if not company_list:
        raise HTTPException(status_code=422, detail="At least one company name is required.")
    if len(company_list) > 5:
        raise HTTPException(status_code=422, detail="Maximum 5 companies per scan.")

    logger.info("competitive-intel scan — companies=%s topic=%s", company_list, topic)

    # Scrape each company (use first company for jobs to save quota)
    all_news: list[dict] = []
    for company in company_list:
        news = _run_tool(scrape_company_news, company_name=company, max_articles=max_news)
        if isinstance(news, list):
            for article in news:
                if isinstance(article, dict) and "error" not in article:
                    article["company"] = company
            all_news.extend([a for a in news if isinstance(a, dict) and "error" not in a])

    jobs_data = _run_tool(scrape_job_postings, company_name=company_list[0], keywords=topic)

    analysis = _run_tool(
        analyze_competitive_landscape,
        companies=company_list,
        topic=topic,
        news_data=all_news,
        jobs_data=jobs_data,
    )

    return {
        "companies": company_list,
        "topic": topic,
        "news": all_news,
        "jobs": jobs_data,
        "analysis": analysis,
    }


@router.get("/news", response_model=None)
async def get_company_news(
    company: str = Query(..., description="Company name"),
    limit: int = Query(10, ge=1, le=20),
    _user=Depends(get_current_user),
) -> list[dict]:
    """Fetch recent news articles for a single competitor company."""
    logger.info("competitive-intel news — company=%s", company)
    result = _run_tool(scrape_company_news, company_name=company, max_articles=limit)
    if isinstance(result, list):
        return result
    return [result]


@router.get("/jobs", response_model=None)
async def get_company_jobs(
    company: str = Query(..., description="Company name"),
    keywords: str = Query("", description="Optional skill/domain filter"),
    _user=Depends(get_current_user),
) -> dict:
    """Fetch recent job postings for a single competitor company."""
    logger.info("competitive-intel jobs — company=%s keywords=%s", company, keywords)
    return _run_tool(scrape_job_postings, company_name=company, keywords=keywords)


@router.delete("/cache/clear")
async def clear_cache(_user=Depends(get_current_user)) -> dict:
    """Invalidate the in-process scraping cache (forces fresh scraping on next request)."""
    count = len(_CACHE)
    _CACHE.clear()
    logger.info("competitive-intel cache cleared — %d entries removed", count)
    return {"cleared": count, "message": f"{count} entrées supprimées du cache."}
