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
from datetime import datetime, timezone
from typing import Any
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
