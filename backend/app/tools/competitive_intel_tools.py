"""Competitive intelligence tools — web scraping for strategic foresight.

Each tool is a LangChain @tool that scrapes public sources (Google News RSS,
job boards, company blogs) and returns structured data for the
competitive_intel_agent ReAct loop.

Sources used:
- Google News RSS      : légal, pas d'authentification, données fiables
- Indeed RSS           : offres d'emploi publiques
- BeautifulSoup        : parsing HTML statique des blogs/sites officiels

All HTTP requests use httpx with a 10s timeout and a realistic User-Agent.
Results are cached in-process (TTL 1h) via a simple dict + timestamp to
avoid hammering the same sources on repeated queries.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── HTTP client (shared, sync) ─────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

_HTTP_TIMEOUT = 10  # seconds

# ── Simple in-process cache (key → {data, expires_at}) ───────────────────────

_CACHE: dict[str, dict] = {}
_CACHE_TTL = 3600  # 1 hour


def _cache_get(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry and time.time() < entry["expires_at"]:
        return entry["data"]
    return None


def _cache_set(key: str, data: Any) -> None:
    _CACHE[key] = {"data": data, "expires_at": time.time() + _CACHE_TTL}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch(url: str) -> str | None:
    """Fetch a URL and return the response text, or None on error."""
    try:
        with httpx.Client(headers=_HEADERS, timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("_fetch failed for %s — %s", url, exc)
        return None


def _parse_rss(xml_text: str, max_items: int) -> list[dict]:
    """Parse an RSS/Atom feed and return a list of article dicts."""
    soup = BeautifulSoup(xml_text, "xml")
    items = []
    for item in soup.find_all("item")[:max_items]:
        title = item.find("title")
        link = item.find("link")
        pub_date = item.find("pubDate")
        description = item.find("description")
        source_tag = item.find("source")

        # Clean HTML from description
        desc_text = ""
        if description and description.text:
            desc_soup = BeautifulSoup(description.text, "html.parser")
            desc_text = desc_soup.get_text(separator=" ", strip=True)[:300]

        items.append({
            "title": title.text.strip() if title else "",
            "url": link.text.strip() if link else "",
            "published": pub_date.text.strip() if pub_date else "",
            "summary": desc_text,
            "source": source_tag.text.strip() if source_tag else "Google News",
        })
    return items


def _extract_skills_from_text(text: str) -> list[str]:
    """Extract tech/business keywords from job description text."""
    keywords = [
        "Python", "Java", "JavaScript", "TypeScript", "React", "Angular",
        "Vue", "Node.js", "FastAPI", "Django", "Spring", "AWS", "Azure",
        "GCP", "Docker", "Kubernetes", "Terraform", "DevOps", "MLOps",
        "Machine Learning", "Deep Learning", "LLM", "LangChain", "NLP",
        "Data Science", "Spark", "Kafka", "PostgreSQL", "MongoDB", "Redis",
        "Microservices", "API REST", "GraphQL", "Agile", "Scrum",
        "Business Intelligence", "Power BI", "Tableau", "SAP", "Salesforce",
        "cybersécurité", "blockchain", "cloud", "IA", "GenAI",
    ]
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def scrape_company_news(company_name: str, max_articles: int = 8) -> list[dict]:
    """Scrape the latest public news about a competitor company via Google News RSS.

    Args:
        company_name: Name of the competitor company (e.g. 'Sopra Steria').
        max_articles: Maximum number of articles to return (default 8).

    Returns:
        List of article dicts with keys: title, url, published, summary, source.
    """
    cache_key = f"news:{company_name}:{max_articles}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("scrape_company_news: cache hit for '%s'", company_name)
        return cached

    logger.info("scrape_company_news: scraping news for '%s'", company_name)

    # Google News RSS — public, no auth, legal
    query = quote_plus(f'"{company_name}"')
    url = f"https://news.google.com/rss/search?q={query}&hl=fr&gl=FR&ceid=FR:fr"

    xml_text = _fetch(url)
    if not xml_text:
        return [{"error": f"Impossible de récupérer les actualités pour '{company_name}'"}]

    articles = _parse_rss(xml_text, max_articles)
    logger.info("scrape_company_news: found %d articles for '%s'", len(articles), company_name)

    _cache_set(cache_key, articles)
    return articles


@tool
def scrape_job_postings(company_name: str, keywords: str = "") -> dict:
    """Scrape recent job postings for a competitor via Google News job queries.

    Uses Google News RSS with job-related search terms since job boards
    (Indeed, LinkedIn) block automated access.  Also detects hiring signals
    directly from news headlines (e.g. "Sopra Steria recrute 3400 personnes").

    Args:
        company_name: Name of the competitor company.
        keywords:     Optional skill/domain filter (e.g. 'machine learning').

    Returns:
        Dict with total_jobs_found, jobs list, top_skills_recruited, strategic_signals.
    """
    cache_key = f"jobs:{company_name}:{keywords}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("scrape_job_postings: cache hit for '%s'", company_name)
        return cached

    logger.info("scrape_job_postings: scraping job signals for '%s'", company_name)

    # Strategy: search Google News for hiring/recruitment news about the company
    # This is more reliable than scraping job boards directly
    job_queries = [
        f'"{company_name}" recrutement',
        f'"{company_name}" embauche',
        f'"{company_name}" hiring',
    ]
    if keywords:
        job_queries.append(f'"{company_name}" {keywords} emploi')

    all_news_items = []
    for query in job_queries[:2]:  # limit to 2 queries to avoid rate limiting
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=fr&gl=FR&ceid=FR:fr"
        xml_text = _fetch(url)
        if xml_text:
            items = _parse_rss(xml_text, 5)
            all_news_items.extend(items)

    # Deduplicate by title
    seen = set()
    unique_items = []
    for item in all_news_items:
        t = item.get("title", "")
        if t and t not in seen:
            seen.add(t)
            unique_items.append(item)

    # Extract job-like entries and detect skills from titles/summaries
    jobs = []
    all_skills: list[str] = []
    for item in unique_items:
        combined_text = item.get("title", "") + " " + item.get("summary", "")
        skills = _extract_skills_from_text(combined_text)
        all_skills.extend(skills)
        # Count as a "job signal" if it mentions hiring keywords
        hire_keywords = ["recrut", "embauche", "poste", "emploi", "CDI", "CDD", "offre", "hiring"]
        if any(kw.lower() in combined_text.lower() for kw in hire_keywords):
            jobs.append({
                "title": item.get("title", ""),
                "company": company_name,
                "location": "France",
                "date_posted": item.get("published", ""),
                "skills": skills,
                "description_snippet": item.get("summary", "")[:200],
                "url": item.get("url", ""),
            })

    # Skill frequency
    skill_freq: dict[str, int] = {}
    for s in all_skills:
        skill_freq[s] = skill_freq.get(s, 0) + 1
    top_skills = sorted(skill_freq.items(), key=lambda x: x[1], reverse=True)[:10]

    # Strategic signals
    signals = []
    title_corpus = " ".join(i.get("title", "") for i in unique_items).lower()
    if any(w in title_corpus for w in ["ia", "intelligence artificielle", "llm", "machine learning", "genai"]):
        signals.append("Investissement en IA/ML détecté dans les recrutements")
    if any(w in title_corpus for w in ["cloud", "devops", "azure", "aws", "kubernetes"]):
        signals.append("Expansion cloud et infrastructure en cours")
    if any(w in title_corpus for w in ["cybersécurité", "cyber", "sécurité informatique"]):
        signals.append("Renforcement de la cybersécurité")
    if any(w in title_corpus for w in ["commercial", "vente", "sales", "business developer"]):
        signals.append("Expansion commerciale — nouveaux marchés visés")

    # Detect volume from headlines (e.g. "3 400 recrutements")
    import re
    volume_match = re.search(r'(\d[\d\s]*\d+)\s*(?:recrutements?|embauches?|postes?)', title_corpus)
    if volume_match:
        signals.append(f"Volume de recrutement annoncé : ~{volume_match.group(1).strip()} postes")

    result = {
        "company": company_name,
        "total_jobs_found": len(jobs),
        "jobs": jobs,
        "top_skills_recruited": [{"skill": s, "count": c} for s, c in top_skills],
        "strategic_signals": signals,
        "hiring_news": unique_items[:5],
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    _cache_set(cache_key, result)
    return result


@tool
def scrape_company_blog(company_url: str, company_name: str, max_posts: int = 5) -> list[dict]:
    """Scrape the latest posts from a competitor's public blog or news page.

    Reveals R&D direction, product announcements, and technology choices.

    Args:
        company_url:  Full URL of the blog/news page (e.g. 'https://blog.soprasteria.com').
        company_name: Human-readable company name for labeling results.
        max_posts:    Maximum number of posts to extract (default 5).

    Returns:
        List of post dicts with keys: title, url, date, excerpt, company.
    """
    cache_key = f"blog:{company_url}:{max_posts}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    logger.info("scrape_company_blog: scraping blog '%s'", company_url)
    html = _fetch(company_url)
    if not html:
        return [{"error": f"Impossible d'accéder au blog de {company_name}"}]

    soup = BeautifulSoup(html, "html.parser")
    posts = []

    # Heuristic: look for article tags, then h2/h3 with links
    articles = soup.find_all("article")[:max_posts]
    if not articles:
        # Fallback: look for heading + link pairs
        for heading in soup.find_all(["h2", "h3"])[:max_posts]:
            link = heading.find("a") or (heading.parent and heading.parent.find("a"))
            if not link:
                continue
            href = link.get("href", "")
            if href and not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(company_url, href)
            posts.append({
                "title": heading.get_text(strip=True),
                "url": href,
                "date": "",
                "excerpt": "",
                "company": company_name,
            })
    else:
        for article in articles:
            title_el = article.find(["h2", "h3", "h1"])
            link_el = article.find("a")
            date_el = article.find(["time", "span"], class_=lambda c: c and "date" in c.lower() if c else False)
            para_el = article.find("p")

            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(company_url, href)

            posts.append({
                "title": title_el.get_text(strip=True) if title_el else "",
                "url": href,
                "date": date_el.get_text(strip=True) if date_el else "",
                "excerpt": para_el.get_text(strip=True)[:200] if para_el else "",
                "company": company_name,
            })

    _cache_set(cache_key, posts)
    return posts


@tool
def analyze_competitive_landscape(
    companies: list[str],
    topic: str,
    news_data: list[dict] | None = None,
    jobs_data: dict | None = None,
) -> dict:
    """Aggregate scraped data to produce a structured competitive intelligence report.

    Computes threat radar scores (0–100) on 5 strategic axes, identifies key
    competitor moves, and produces actionable recommendations.

    This tool is meant to be called AFTER scrape_company_news and
    scrape_job_postings have already been called in the ReAct loop, using their
    results as input.

    Args:
        companies:  List of competitor names analyzed.
        topic:      Strategic topic (e.g. 'intelligence artificielle', 'cloud').
        news_data:  Aggregated list of news articles from previous tool calls.
        jobs_data:  Aggregated jobs result dict from previous tool calls.

    Returns:
        Structured dict with threat_level, radar_scores, key_moves,
        recommended_actions, and summary.
    """
    logger.info("analyze_competitive_landscape: topic='%s' companies=%s", topic, companies)

    news_data = news_data or []
    jobs_data = jobs_data or {}

    topic_lower = topic.lower()

    # ── Compute radar scores ──────────────────────────────────────────────────
    # Each axis is scored 0–100 based on signal density in scraped data

    all_news_text = " ".join(
        (a.get("title", "") + " " + a.get("summary", "")).lower()
        for a in news_data
        if isinstance(a, dict)
    )
    all_skills = []
    if isinstance(jobs_data, dict):
        for item in jobs_data.get("top_skills_recruited", []):
            skill = item.get("skill", "")
            count = item.get("count", 1)
            all_skills.extend([skill.lower()] * count)
    skill_text = " ".join(all_skills)

    ai_keywords = ["machine learning", "llm", "ia", "deep learning", "genai", "gpt", "nlp", "intelligence artificielle"]
    cloud_keywords = ["cloud", "aws", "azure", "gcp", "kubernetes", "devops", "saas", "paas"]
    hiring_keywords = ["recrut", "embauche", "talent", "ingénieur", "développeur", "engineer"]
    partner_keywords = ["partenariat", "acquisition", "fusion", "alliance", "contrat", "accord"]
    innovation_keywords = ["innovation", "r&d", "brevet", "produit", "lancement", "plateforme", "solution"]

    def _score(keywords: list[str], texts: list[str]) -> int:
        combined = " ".join(texts).lower()
        hits = sum(combined.count(kw) for kw in keywords)
        return min(100, hits * 12)

    texts = [all_news_text, skill_text]
    radar_scores = {
        "IA_Générative": _score(ai_keywords, texts),
        "Cloud": _score(cloud_keywords, texts),
        "Recrutement": min(100, (jobs_data.get("total_jobs_found", 0) if isinstance(jobs_data, dict) else 0) * 7),
        "Partenariats": _score(partner_keywords, texts),
        "Innovation_Produit": _score(innovation_keywords, texts),
    }

    # Overall threat level = weighted average
    weights = [0.30, 0.25, 0.20, 0.10, 0.15]
    threat_level = round(
        sum(v * w for v, w in zip(radar_scores.values(), weights)) / 100, 2
    )

    # ── Extract key moves from news titles ───────────────────────────────────
    key_moves = []
    for article in news_data[:5]:
        if isinstance(article, dict) and article.get("title"):
            key_moves.append({
                "company": companies[0] if companies else "Concurrent",
                "move": article["title"],
                "date": article.get("published", ""),
                "source": article.get("source", ""),
                "url": article.get("url", ""),
            })

    # ── Job signals as moves ──────────────────────────────────────────────────
    if isinstance(jobs_data, dict):
        for signal in jobs_data.get("strategic_signals", []):
            key_moves.append({
                "company": jobs_data.get("company", "Concurrent"),
                "move": signal,
                "date": jobs_data.get("scraped_at", ""),
                "source": "Indeed",
                "url": "",
            })

    # ── Recommendations ───────────────────────────────────────────────────────
    recommended_actions = []
    if radar_scores["IA_Générative"] >= 40:
        recommended_actions.append({
            "priority": "haute",
            "action": f"Accélérer la roadmap IA interne — les concurrents investissent fortement sur {topic}",
            "axis": "IA_Générative",
        })
    if radar_scores["Recrutement"] >= 50:
        recommended_actions.append({
            "priority": "moyenne",
            "action": "Surveiller les profils recrutés pour anticiper les nouvelles capacités concurrentes",
            "axis": "Recrutement",
        })
    if radar_scores["Partenariats"] >= 30:
        recommended_actions.append({
            "priority": "haute",
            "action": "Identifier les partenariats annoncés et évaluer leur impact sur votre positionnement",
            "axis": "Partenariats",
        })
    if radar_scores["Cloud"] >= 40:
        recommended_actions.append({
            "priority": "moyenne",
            "action": "Renforcer les offres cloud et certifications pour rester compétitif",
            "axis": "Cloud",
        })
    if not recommended_actions:
        recommended_actions.append({
            "priority": "basse",
            "action": "Continuer la veille — aucun signal d'alarme majeur détecté",
            "axis": "Général",
        })

    # ── Anticipated future moves (what they will likely do next) ─────────────
    anticipated_moves: list[dict] = []

    if radar_scores["IA_Générative"] >= 30:
        anticipated_moves.append({
            "horizon": "3–6 mois",
            "prediction": "Lancement d'une offre ou plateforme IA/GenAI",
            "confidence": min(100, radar_scores["IA_Générative"]),
            "axis": "IA_Générative",
            "rationale": "Investissement en recrutement IA et communications récentes sur l'IA",
        })
    if radar_scores["Cloud"] >= 30:
        anticipated_moves.append({
            "horizon": "6–12 mois",
            "prediction": "Migration/expansion infrastructure cloud",
            "confidence": min(100, radar_scores["Cloud"]),
            "axis": "Cloud",
            "rationale": "Signaux de recrutement DevOps/Cloud et partenariats cloud détectés",
        })
    if radar_scores["Recrutement"] >= 40:
        anticipated_moves.append({
            "horizon": "1–3 mois",
            "prediction": "Montée en capacité opérationnelle — expansion équipes",
            "confidence": min(100, radar_scores["Recrutement"]),
            "axis": "Recrutement",
            "rationale": f"{jobs_data.get('total_jobs_found', 0) if isinstance(jobs_data, dict) else 0} offres d'emploi actives détectées",
        })
    if radar_scores["Partenariats"] >= 30:
        anticipated_moves.append({
            "horizon": "3–9 mois",
            "prediction": "Consolidation via acquisitions ou partenariats stratégiques",
            "confidence": min(100, radar_scores["Partenariats"]),
            "axis": "Partenariats",
            "rationale": "Annonces de partenariats/acquisitions dans la presse récente",
        })

    # Extract strategic signals from hiring news titles
    hiring_signals: list[str] = []
    if isinstance(jobs_data, dict):
        hiring_signals = jobs_data.get("strategic_signals", [])
        for news_item in jobs_data.get("hiring_news", []):
            title = news_item.get("title", "")
            if title and not any(title in s for s in hiring_signals):
                hiring_signals.append(title)

    # ── Summary text ─────────────────────────────────────────────────────────
    threat_label = (
        "Critique" if threat_level >= 0.75
        else "Élevé" if threat_level >= 0.5
        else "Modéré" if threat_level >= 0.25
        else "Faible"
    )

    summary = (
        f"Analyse concurrentielle sur le thème '{topic}' pour {', '.join(companies)}. "
        f"Niveau de menace global : {threat_label} ({int(threat_level * 100)}%). "
        f"{len(news_data)} actualités et {jobs_data.get('total_jobs_found', 0) if isinstance(jobs_data, dict) else 0} "
        f"signaux recrutement analysés."
    )

    return {
        "companies_analyzed": companies,
        "topic": topic,
        "threat_level": threat_level,
        "threat_label": threat_label,
        "radar_scores": radar_scores,
        "key_moves": key_moves,
        "anticipated_moves": anticipated_moves,
        "hiring_signals": hiring_signals,
        "recommended_actions": recommended_actions,
        "summary": summary,
        "total_news": len(news_data),
        "total_jobs": jobs_data.get("total_jobs_found", 0) if isinstance(jobs_data, dict) else 0,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Agentic tools (read stored intelligence — no live scraping) ───────────────

@tool
def query_stored_intel(company_name: str, days: int = 7) -> dict:
    """Query the competitive intelligence knowledge base for stored snapshots.

    Returns the latest snapshots and trend summary for a company WITHOUT
    triggering any live scraping. The agent should call this FIRST before
    deciding whether fresh data is needed.

    Args:
        company_name: Competitor name (e.g. 'Capgemini').
        days:         Look-back window in days (default 7).

    Returns:
        Dict with latest_snapshot, trend (threat_level over time),
        pending_alerts, data_age_hours.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from functools import lru_cache
    from app.core.config import settings

    @lru_cache(maxsize=1)
    def _engine():
        return create_engine(settings.database_url("hr"), pool_pre_ping=True)

    try:
        engine = _engine()
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        with Session(engine) as session:
            # Latest full snapshot
            row = session.execute(
                text(
                    "SELECT id, radar_scores, threat_level, threat_label, "
                    "key_moves, anticipated_moves, hiring_signals, "
                    "llm_assessment, llm_vulnerability, llm_response, "
                    "is_significant, delta_scores, change_summary, "
                    "financial_data, snapshot_at "
                    "FROM ci_snapshots "
                    "WHERE company_name = :name "
                    "ORDER BY snapshot_at DESC LIMIT 1"
                ),
                {"name": company_name},
            ).fetchone()

            if not row:
                return {
                    "company": company_name,
                    "status": "no_data",
                    "message": f"No stored intelligence for '{company_name}'. "
                               "Trigger a fresh scan with scrape_company_news.",
                }

            latest = {
                "id":              row[0],
                "radar_scores":    row[1],
                "threat_level":    row[2],
                "threat_label":    row[3],
                "key_moves":       (row[4] or [])[:5],
                "anticipated_moves": (row[5] or [])[:5],
                "hiring_signals":  (row[6] or [])[:5],
                "llm_assessment":  row[7],
                "llm_vulnerability": row[8],
                "llm_response":    row[9],
                "is_significant":  row[10],
                "delta_scores":    row[11],
                "change_summary":  row[12],
                "financial_summary": {
                    k: v for k, v in (row[13] or {}).items()
                    if k in ("price_change_1m_pct", "analyst_recommendation",
                             "market_cap", "revenue_growth_yoy")
                },
                "snapshot_at": str(row[14]),
            }

            # Age of data
            snapshot_dt = row[14]
            if hasattr(snapshot_dt, "timestamp"):
                age_hours = round(
                    (datetime.utcnow() - snapshot_dt).total_seconds() / 3600, 1
                )
            else:
                age_hours = None

            # Threat trend over the look-back window
            trend_rows = session.execute(
                text(
                    "SELECT threat_level, snapshot_at "
                    "FROM ci_snapshots "
                    "WHERE company_name = :name AND snapshot_at >= :cutoff "
                    "ORDER BY snapshot_at ASC"
                ),
                {"name": company_name, "cutoff": cutoff},
            ).fetchall()
            trend = [
                {"threat_level": r[0], "at": str(r[1])}
                for r in trend_rows
            ]

            # Unacknowledged alerts
            alert_rows = session.execute(
                text(
                    "SELECT level, title, created_at "
                    "FROM ci_alerts "
                    "WHERE company_name = :name AND acknowledged = false "
                    "ORDER BY created_at DESC LIMIT 3"
                ),
                {"name": company_name},
            ).fetchall()
            pending_alerts = [
                {"level": r[0], "title": r[1], "at": str(r[2])}
                for r in alert_rows
            ]

        return {
            "company":       company_name,
            "status":        "ok",
            "data_age_hours": age_hours,
            "latest":        latest,
            "trend":         trend,
            "pending_alerts": pending_alerts,
            "stale":         (age_hours or 0) > 6,
        }
    except Exception as exc:
        return {"company": company_name, "error": str(exc)}


@tool
def detect_strategic_shift(company_name: str, baseline_days: int = 7) -> dict:
    """Compare the latest snapshot to the N-day baseline average to detect
    significant strategic changes.

    Use this after query_stored_intel when you want to understand if the
    current threat level represents a meaningful trend change.

    Args:
        company_name:   Competitor name.
        baseline_days:  Days to use as baseline for comparison (default 7).

    Returns:
        Dict with per-axis deltas, shift_detected flag, shift_description,
        most_changed_axis, and strategic_interpretation.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from functools import lru_cache
    from app.core.config import settings

    @lru_cache(maxsize=1)
    def _engine():
        return create_engine(settings.database_url("hr"), pool_pre_ping=True)

    try:
        engine = _engine()
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=baseline_days)

        with Session(engine) as session:
            # Latest snapshot scores
            latest_row = session.execute(
                text(
                    "SELECT radar_scores, threat_level, financial_data, snapshot_at "
                    "FROM ci_snapshots WHERE company_name = :name "
                    "ORDER BY snapshot_at DESC LIMIT 1"
                ),
                {"name": company_name},
            ).fetchone()

            if not latest_row:
                return {"company": company_name, "error": "No data available."}

            latest_scores  = latest_row[0] or {}
            latest_threat  = latest_row[1] or 0.0
            latest_fin     = latest_row[2] or {}

            # Baseline: average of snapshots in the look-back window (excluding latest)
            baseline_rows = session.execute(
                text(
                    "SELECT radar_scores, threat_level FROM ci_snapshots "
                    "WHERE company_name = :name AND snapshot_at >= :cutoff "
                    "ORDER BY snapshot_at ASC"
                ),
                {"name": company_name, "cutoff": cutoff},
            ).fetchall()

        if len(baseline_rows) < 2:
            return {
                "company": company_name,
                "shift_detected": False,
                "message": "Not enough historical data for shift detection (need ≥2 snapshots).",
            }

        # Compute baseline averages (exclude last row = latest)
        baseline_samples = baseline_rows[:-1]
        baseline_avg: Dict[str, float] = {}
        for axis in latest_scores:
            vals = [r[0].get(axis, 0) for r in baseline_samples if r[0]]
            baseline_avg[axis] = sum(vals) / len(vals) if vals else 0.0

        baseline_threat_avg = sum(r[1] or 0 for r in baseline_samples) / len(baseline_samples)

        # Delta
        delta = {
            axis: round(latest_scores.get(axis, 0) - baseline_avg.get(axis, 0), 1)
            for axis in latest_scores
        }
        threat_delta = round(latest_threat - baseline_threat_avg, 3)

        # Most changed axis
        most_changed_axis = max(delta, key=lambda k: abs(delta[k])) if delta else None
        max_delta = abs(delta.get(most_changed_axis, 0)) if most_changed_axis else 0

        shift_detected = max_delta >= CHANGE_THRESHOLD or abs(threat_delta) >= 0.10

        # Strategic interpretation
        interpretation = []
        for axis, d in delta.items():
            if abs(d) >= CHANGE_THRESHOLD:
                direction = "increased" if d > 0 else "decreased"
                interpretation.append(
                    f"{axis} score {direction} by {abs(d):.0f} pts — "
                    + _AXIS_INTERPRETATIONS.get(axis, {}).get("up" if d > 0 else "down", "")
                )

        price_change = latest_fin.get("price_change_1m_pct")
        if price_change is not None and abs(price_change) >= 5:
            interpretation.append(
                f"Stock moved {price_change:+.1f}% in the last month — "
                + ("possible M&A or major contract win" if price_change > 0
                   else "financial pressure or investor concern")
            )

        return {
            "company":            company_name,
            "shift_detected":     shift_detected,
            "threat_delta":       threat_delta,
            "axis_deltas":        delta,
            "most_changed_axis":  most_changed_axis,
            "max_axis_delta":     max_delta,
            "baseline_days":      baseline_days,
            "baseline_samples":   len(baseline_samples),
            "strategic_interpretation": interpretation,
            "shift_description": (
                f"Significant shift on {most_changed_axis}: {delta.get(most_changed_axis, 0):+.0f}pts "
                f"vs {baseline_days}-day baseline."
                if shift_detected else
                f"No significant shift detected for {company_name} vs {baseline_days}-day baseline."
            ),
        }
    except Exception as exc:
        return {"company": company_name, "error": str(exc)}


# Axis interpretation lookup used by detect_strategic_shift
_AXIS_INTERPRETATIONS: Dict[str, Dict[str, str]] = {
    "IA_Générative": {
        "up":   "likely preparing an AI/GenAI product launch in 3–6 months",
        "down": "reducing AI investment or pivoting away from GenAI",
    },
    "Cloud": {
        "up":   "accelerating cloud migration or cloud-native offering",
        "down": "cloud activity stabilizing or shifting to other priorities",
    },
    "Recrutement": {
        "up":   "operational capacity expansion — watch for service area growth",
        "down": "hiring freeze or restructuring underway",
    },
    "Partenariats": {
        "up":   "alliance or acquisition likely in next 3–9 months",
        "down": "partnership activity quieting",
    },
    "Innovation_Produit": {
        "up":   "product or platform launch imminent",
        "down": "innovation activity consolidating",
    },
}


@tool
def get_competitor_financial_data(ticker: str, company_name: str) -> dict:
    """Fetch real-time stock performance and financial health for a
    publicly traded competitor via yfinance.

    Use this when the user asks about financial strength, stock trends,
    or when detecting a financial signal in stored data.

    Args:
        ticker:       Yahoo Finance ticker (e.g. 'CAP.PA', 'SOP.PA', 'ACN').
        company_name: Human-readable company name for labeling.

    Returns:
        Dict with price_change_1m_pct, market_cap, pe_ratio,
        revenue_growth_yoy, analyst_recommendation, recent_news_titles.
    """
    cache_key = f"fin:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        logger.info("get_competitor_financial_data: cache hit for '%s'", ticker)
        return cached

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

        news  = t.news or []
        result = {
            "company":                company_name,
            "ticker":                 ticker,
            "price_change_1m_pct":    price_change,
            "market_cap":             info.get("marketCap"),
            "pe_ratio":               info.get("trailingPE"),
            "revenue_growth_yoy":     info.get("revenueGrowth"),
            "profit_margins":         info.get("profitMargins"),
            "analyst_recommendation": info.get("recommendationKey"),
            "number_of_analysts":     info.get("numberOfAnalystOpinions"),
            "52w_high":               info.get("fiftyTwoWeekHigh"),
            "52w_low":                info.get("fiftyTwoWeekLow"),
            "recent_news_titles":     [n.get("title", "") for n in news[:5]],
            "fetched_at":             datetime.now(timezone.utc).isoformat(),
        }
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        return {"ticker": ticker, "company": company_name, "error": str(exc)}


@tool
def get_competitor_kg_context(company_name: str) -> dict:
    """Query the Neo4j Knowledge Graph for a competitor's nodes, relationships,
    and causal chains that may affect Talan.

    Use this to understand how a competitor is positioned in the broader
    market graph — their sector relationships, shared entities with Talan,
    and any causal risk paths.

    Args:
        company_name: Competitor name as stored in the KG (e.g. 'Capgemini').

    Returns:
        Dict with kg_nodes, kg_edges, threat_level (from KG edge),
        shared_entities_with_talan, causal_risk_paths.
    """
    try:
        from app.services.market_analysis.world_model import WorldModel
        import re as _re

        def _slugify(name: str) -> str:
            return _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

        wm = WorldModel()
        if not wm.is_available():
            return {"error": "Knowledge Graph unavailable", "company": company_name}

        slug = _slugify(company_name)

        # Ego-graph around the competitor (1 hop)
        snapshot = wm.get_snapshot(company_name, hops=1)

        # COMPETES_WITH edge properties toward Talan
        competes_edge = wm._run(
            """
            MATCH (c:Competitor {slug: $slug})-[r:COMPETES_WITH]->(t:Company {slug: 'talan'})
            RETURN r.threat_level AS threat_level, r.threat_label AS threat_label,
                   r.updated_at AS updated_at
            """,
            {"slug": slug},
        )
        edge_data = {}
        if competes_edge:
            rec = competes_edge[0]
            edge_data = {
                "threat_level": rec.get("threat_level"),
                "threat_label": rec.get("threat_label"),
                "last_updated": rec.get("updated_at"),
            }

        # Shared entities between this competitor and Talan
        shared = wm._run(
            """
            MATCH (c {slug: $slug})-[]-(shared)-[]-(t:Company {slug: 'talan'})
            WHERE c <> t
            RETURN shared.name AS name, labels(shared)[0] AS type
            LIMIT 10
            """,
            {"slug": slug},
        )
        shared_entities = [
            {"name": r.get("name"), "type": r.get("type")}
            for r in shared
        ]

        # Causal risk paths: competitor → ... → Talan
        risk_paths = wm.find_hidden_risks(target="Talan", max_hops=3)
        relevant_paths = [
            p for p in risk_paths
            if company_name.lower() in (p.get("source", "") or "").lower()
        ]

        return {
            "company":          company_name,
            "kg_nodes":         snapshot.get("nodes", [])[:15],
            "kg_edges":         snapshot.get("edges", [])[:20],
            "kg_node_count":    snapshot.get("total_nodes", 0),
            "competes_with_talan": edge_data,
            "shared_entities_with_talan": shared_entities,
            "causal_risk_paths_to_talan": relevant_paths[:5],
        }
    except Exception as exc:
        return {"company": company_name, "error": str(exc)}
