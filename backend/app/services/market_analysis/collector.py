"""Collector Module — fetches and classifies high-impact global market intelligence.

Sources (priority order):
1. NewsAPI        — structured API, 100 req/day free tier
2. GNews API      — Google News aggregator, 100 req/day free tier
3. RSS Feeds      — Reuters, Bloomberg, FT, WSJ, TechCrunch, Wired, CNBC, etc.
4. yfinance       — OHLCV + news for tracked tickers
5. Alpha Vantage  — fallback market data if yfinance fails

Pipeline:
  collect → deduplicate → impact_filter → classify → enrich → persist

All results are deduplicated by URL hash and stored in PostgreSQL.
Only articles with impact_score >= MIN_IMPACT_SCORE are persisted.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import httpx
import yfinance as yf
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.market_analysis_models import MarketRawArticle
from app.schemas.market_analysis_schemas import CollectorResult, RawArticle

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────────

_MAX_ARTICLE_AGE_HOURS = 48     # only collect articles < 48h old
MIN_IMPACT_SCORE = 5            # 1–10; articles below this are dropped as noise
_HTTP_TIMEOUT = 12              # seconds per request
_RSS_TIMEOUT = 15

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}


# ── Tickers tracked ────────────────────────────────────────────────────────────

DEFAULT_TICKERS = [
    # French index + Talan competitors
    "^FCHI",            # CAC 40
    "^GSPC", "^NDX",    # S&P 500, NASDAQ 100
    "CAP.PA",           # Capgemini
    "SOP.PA",           # Sopra Steria
    "ATO.PA",           # Atos
    "SAP", "ACN",       # SAP, Accenture
    # Big Tech (AI budgets & partnerships)
    "MSFT", "GOOGL", "NVDA", "META", "AMZN", "AAPL",
    # AI pure plays
    "PLTR", "AI",       # Palantir, C3.ai
    # Macro
    "EURUSD=X",         # EUR/USD
    "BZ=F",             # Brent crude
    "^VIX",             # Volatility index
    "GLD",              # Gold
]


# ── RSS Feeds — Tier 1 (highest quality, global impact) ──────────────────────

RSS_FEEDS_TIER1 = [
    # Reuters — most authoritative breaking news
    ("https://feeds.reuters.com/reuters/businessNews",       "Reuters Business",    "en"),
    ("https://feeds.reuters.com/reuters/technologyNews",     "Reuters Technology",  "en"),
    ("https://feeds.reuters.com/reuters/topNews",            "Reuters Top News",    "en"),
    # WSJ Markets
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml",        "WSJ Markets",         "en"),
    ("https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",      "WSJ Business",        "en"),
    # CNBC
    ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
     "CNBC Finance",   "en"),
    ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
     "CNBC Tech",      "en"),
    # Financial Times (limited but high signal)
    ("https://www.ft.com/?format=rss",                       "Financial Times",     "en"),
    # The Economist
    ("https://www.economist.com/finance-and-economics/rss.xml",
     "The Economist",  "en"),
    ("https://www.economist.com/business/rss.xml",
     "The Economist Business", "en"),
    # TechCrunch
    ("https://techcrunch.com/feed/",                         "TechCrunch",          "en"),
    # Wired
    ("https://www.wired.com/feed/rss",                       "Wired",               "en"),
    # VentureBeat — AI/ML focus
    ("https://venturebeat.com/feed/",                        "VentureBeat",         "en"),
    # MIT Technology Review
    ("https://www.technologyreview.com/feed/",               "MIT Tech Review",     "en"),
    # BBC Business
    ("https://feeds.bbci.co.uk/news/business/rss.xml",       "BBC Business",        "en"),
]

RSS_FEEDS_TIER2 = [
    # France — Les Echos, Le Monde, BFM Business, La Tribune
    ("https://www.lesechos.fr/rss/rss_finance.xml",          "Les Echos Finance",   "fr"),
    ("https://www.lesechos.fr/rss/rss_technologie.xml",      "Les Echos Tech",      "fr"),
    ("https://www.lemonde.fr/economie/rss_full.xml",         "Le Monde Eco",        "fr"),
    ("https://bfmbusiness.bfmtv.com/rss/info/flux-rss/flux-toutes-les-actualites/",
     "BFM Business",   "fr"),
    ("https://www.latribune.fr/rss/rubriques/economie.html", "La Tribune",          "fr"),
    # Africa / Tunisia
    ("https://www.jeuneafrique.com/feed/",                   "Jeune Afrique",       "fr"),
    ("https://www.businessnews.com.tn/rss.xml",              "Business News TN",    "fr"),
]


# ── Classification engine ──────────────────────────────────────────────────────

# Category → (keywords EN, keywords FR, base_weight)
_CATEGORY_RULES: Dict[str, Tuple[List[str], List[str], float]] = {
    "regulatory_changes": (
        [
            "regulation", "law", "act", "directive", "compliance", "gdpr",
            "ai act", "iso standard", "sanction", "fine", "ruling", "enforcement",
            "data protection", "cybersecurity law", "dpdp", "eu regulation",
            "antitrust", "sec", "fed rule", "ban", "legislation", "policy change",
            "reporting obligation", "audit requirement",
        ],
        [
            "réglementation", "loi", "directive", "conformité", "rgpd", "ai act",
            "norme iso", "sanction", "amende", "décision", "enforcement",
            "protection des données", "cybersécurité", "taxe", "obligation",
            "réforme fiscale", "régulateur",
        ],
        1.5,
    ),
    "competitor_moves": (
        [
            "acquisition", "merger", "m&a", "partnership", "alliance", "joint venture",
            "layoff", "restructuring", "new product", "product launch", "strategic",
            "contract win", "deal", "expansion", "market entry", "ipo", "spinoff",
            "capgemini", "accenture", "sopra steria", "atos", "deloitte", "ibm",
            "infosys", "tcs", "wipro", "cognizant", "sap",
        ],
        [
            "acquisition", "fusion", "partenariat", "alliance", "licenciement",
            "restructuration", "nouveau produit", "lancement", "stratégique",
            "contrat", "expansion", "entrée sur le marché", "ipo",
            "capgemini", "sopra steria", "atos",
        ],
        1.4,
    ),
    "tech_launches": (
        [
            "openai", "gpt", "llm", "large language model", "claude", "gemini",
            "llama", "deepseek", "grok", "mistral", "anthropic", "ai model",
            "foundation model", "generative ai", "genai", "quantum computing",
            "breakthrough", "launch", "release", "open source model",
            "multimodal", "reasoning model", "agent", "autonomous ai",
            "chipset", "nvidia", "gpu", "tpu", "new chip",
        ],
        [
            "modèle ia", "intelligence artificielle générative", "lancement",
            "nouveau modèle", "percée technologique", "quantique",
            "open source ia", "agent autonome",
        ],
        1.6,
    ),
    "financial_market_impact": (
        [
            "earnings", "revenue", "quarterly results", "stock", "shares",
            "market cap", "valuation", "ipo", "analyst", "downgrade", "upgrade",
            "guidance", "forecast", "profit", "loss", "dividend", "buyback",
            "index", "dow jones", "nasdaq", "cac 40", "s&p 500", "correction",
            "rally", "crash", "recession", "gdp", "inflation", "interest rate",
            "fed", "ecb", "central bank", "bond yield", "currency",
        ],
        [
            "résultats trimestriels", "bourse", "cours", "valorisation",
            "analyste", "prévisions", "revenus", "bénéfice", "perte",
            "récession", "pib", "inflation", "taux directeur", "bce",
            "obligation", "rendement", "monnaie",
        ],
        1.3,
    ),
    "geopolitical_events": (
        [
            "war", "conflict", "sanction", "geopolitical", "election",
            "trade war", "tariff", "embargo", "energy crisis", "supply chain",
            "nato", "g7", "g20", "wto", "imf", "world bank", "coup",
            "protest", "instability", "tension", "ukraine", "taiwan",
            "middle east", "china", "russia", "trade deal", "brexit",
        ],
        [
            "guerre", "conflit", "sanction", "géopolitique", "élection",
            "guerre commerciale", "tarif douanier", "embargo", "crise énergétique",
            "chaîne d'approvisionnement", "otan", "instabilité", "tension",
        ],
        1.4,
    ),
    "talent_market_signals": (
        [
            "hiring", "layoff", "job cut", "recruitment", "talent", "skill shortage",
            "salary", "compensation", "remote work", "return to office", "rto",
            "workforce", "headcount", "engineer shortage", "tech talent",
            "mass hiring", "restructuring", "redundancy", "union", "strike",
            "developer demand", "ai engineer", "job market",
        ],
        [
            "recrutement", "licenciement", "talent", "pénurie de compétences",
            "salaire", "télétravail", "effectif", "développeur", "ingénieur",
            "marché de l'emploi", "grève", "syndicat",
        ],
        1.2,
    ),
}

# High-signal source domains → impact bonus
_HIGH_SIGNAL_SOURCES = {
    "reuters": 2.0,
    "bloomberg": 2.0,
    "wsj": 1.8,
    "wall street journal": 1.8,
    "financial times": 1.8,
    "ft.com": 1.8,
    "the economist": 1.7,
    "cnbc": 1.5,
    "techcrunch": 1.4,
    "wired": 1.3,
    "mit technology review": 1.4,
    "venturebeat": 1.3,
    "les echos": 1.3,
    "bfm business": 1.2,
}

# Noise keywords — articles containing these get penalised heavily
_NOISE_KEYWORDS = [
    "horoscope", "celebrity", "sport", "recipe", "travel tip",
    "beauty", "fashion", "weather", "quiz", "crossword",
    "died", "born today", "this day in history",
]

# High-impact trigger keywords — articles with any of these get a score boost
_HIGH_IMPACT_TRIGGERS = [
    # Financial crisis signals
    "collapse", "bankruptcy", "default", "crash", "meltdown", "bailout",
    # Major corporate events
    "ipo", "acquisition worth", "merger valued", "billion", "trillion",
    # Regulatory big moves
    "banned", "fined", "sued", "antitrust", "blocked acquisition",
    # AI breakthrough
    "beats human", "state of the art", "breakthrough", "open source",
    "outperforms gpt", "new model", "general intelligence",
    # Geopolitical shock
    "war declared", "sanctions imposed", "trade embargo", "military",
    # Mass workforce events
    "mass layoff", "10,000", "20,000", "50,000", "jobs cut",
]


# ── Classification & Scoring ───────────────────────────────────────────────────

def classify_article(title: str, content: str) -> Tuple[List[str], int]:
    """Classify an article into impact categories and compute an impact score 1–10.

    Returns:
        (categories, impact_score)
    """
    combined = (title + " " + content).lower()
    categories: List[str] = []
    base_score = 2  # minimum score for any article that passes age filter

    # Check noise — return immediately with score 1
    if any(noise in combined for noise in _NOISE_KEYWORDS):
        return [], 1

    # Score each category
    category_scores: Dict[str, float] = {}
    for cat, (en_kws, fr_kws, weight) in _CATEGORY_RULES.items():
        hits = sum(1 for kw in en_kws if kw in combined)
        hits += sum(1 for kw in fr_kws if kw in combined)
        if hits > 0:
            category_scores[cat] = hits * weight

    # Keep categories with at least 1 keyword hit
    categories = [cat for cat, s in category_scores.items() if s >= 1.0]

    # Compute score from category density
    if category_scores:
        density = sum(category_scores.values())
        base_score = min(9, base_score + int(density * 0.8))

    # High-impact trigger bonus
    trigger_hits = sum(1 for t in _HIGH_IMPACT_TRIGGERS if t in combined)
    base_score = min(10, base_score + trigger_hits * 2)

    # Penalise if no categories at all
    if not categories:
        base_score = max(1, base_score - 3)

    # Boost for numbers suggesting scale (billions, millions of people/jobs)
    if re.search(r'\$[\d,.]+\s*(?:billion|trillion|bn|tn)', combined):
        base_score = min(10, base_score + 1)
    if re.search(r'\d{2,3},\d{3}\s*(?:jobs|employees|workers|layoff)', combined):
        base_score = min(10, base_score + 1)

    return categories, max(1, min(10, base_score))


def extract_key_entities(title: str, content: str) -> List[str]:
    """Extract key companies, countries, and technologies from text."""
    combined = title + " " + content

    # Known entities to detect (pattern → canonical name)
    entity_patterns = [
        # Big Tech
        (r'\bOpenAI\b', "OpenAI"), (r'\bAnthropic\b', "Anthropic"),
        (r'\bMicrosoft\b', "Microsoft"), (r'\bGoogle\b', "Google"),
        (r'\bMeta\b', "Meta"), (r'\bApple\b', "Apple"),
        (r'\bAmazon\b|AWS', "Amazon/AWS"), (r'\bNVIDIA\b', "NVIDIA"),
        (r'\bDeepSeek\b', "DeepSeek"), (r'\bMistral\b', "Mistral AI"),
        # ESN Competitors
        (r'\bCapgemini\b', "Capgemini"), (r'\bAccenture\b', "Accenture"),
        (r'\bAtos\b', "Atos"), (r'\bSopra\b', "Sopra Steria"),
        (r'\bDeloitte\b', "Deloitte"), (r'\bIBM\b', "IBM"),
        (r'\bInfosys\b', "Infosys"), (r'\bTCS\b', "TCS"),
        (r'\bSAP\b', "SAP"), (r'\bSalesforce\b', "Salesforce"),
        # Tech platforms
        (r'\bLlama\b', "Meta Llama"), (r'\bGPT[-\s]?\d', "OpenAI GPT"),
        (r'\bGemini\b', "Google Gemini"), (r'\bClaude\b', "Anthropic Claude"),
        (r'\bGrok\b', "xAI Grok"),
        # Regulatory bodies
        (r'\bECB\b|European Central Bank', "ECB"),
        (r'\bFed\b|Federal Reserve', "Federal Reserve"),
        (r'\bEU\b|European Union', "European Union"),
        (r'\bSEC\b', "SEC"), (r'\bNATO\b', "NATO"),
        # Countries with high market relevance
        (r'\bChina\b|Chinese', "China"), (r'\bUSA\b|United States', "USA"),
        (r'\bFrance\b|French', "France"), (r'\bGermany\b|German', "Germany"),
        (r'\bRussia\b|Russian', "Russia"), (r'\bUkraine\b', "Ukraine"),
        (r'\bTunisia\b|Tunisian', "Tunisia"),
        # Technologies
        (r'\bAI Act\b', "AI Act"), (r'\bGDPR\b|RGPD', "GDPR"),
        (r'\bQuantum\b', "Quantum Computing"), (r'\bBlockchain\b', "Blockchain"),
    ]

    found = []
    for pattern, canonical in entity_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            found.append(canonical)

    return list(dict.fromkeys(found))  # deduplicate, preserve order


def compute_talent_impact(categories: List[str], title: str, content: str) -> str:
    """Generate a short explanation of HR/competitive relevance."""
    combined = (title + " " + content).lower()
    parts = []

    if "tech_launches" in categories:
        models = [kw for kw in ["gpt", "llama", "gemini", "claude", "deepseek", "grok", "mistral"]
                  if kw in combined]
        if models:
            parts.append(
                f"New AI model ({', '.join(models)}) may shift skill demand toward prompt engineering "
                f"and LLM integration."
            )
        else:
            parts.append("Technological breakthrough could create new skill requirements or "
                         "displace existing roles.")

    if "talent_market_signals" in categories:
        if any(w in combined for w in ["layoff", "job cut", "licenciement", "redundanc"]):
            parts.append("Mass layoffs signal available talent pool — opportunity to recruit "
                         "experienced professionals at competitive rates.")
        if any(w in combined for w in ["hiring", "recrut", "shortage", "pénurie"]):
            parts.append("Competitor hiring surge may tighten the talent market and push "
                         "salaries up in targeted competencies.")

    if "competitor_moves" in categories:
        parts.append("Competitor strategic move (acquisition/partnership/product) may alter "
                     "competitive positioning — assess capability gaps.")

    if "regulatory_changes" in categories:
        parts.append("New regulation may require workforce reskilling (compliance, data "
                     "governance, AI ethics) and may add operational costs.")

    if "geopolitical_events" in categories:
        parts.append("Geopolitical event may disrupt supply chains, market access, or "
                     "workforce mobility across affected regions.")

    if "financial_market_impact" in categories:
        if any(w in combined for w in ["billion", "valuation", "ipo"]):
            parts.append("Major financial event could shift IT investment priorities and "
                         "consulting demand across the sector.")

    if not parts:
        parts.append("Monitor for downstream impact on market conditions and workforce needs.")

    return " ".join(parts)


def apply_source_boost(impact_score: int, source: str) -> int:
    """Boost impact score based on source credibility."""
    source_lower = source.lower()
    for domain, multiplier in _HIGH_SIGNAL_SOURCES.items():
        if domain in source_lower:
            boosted = min(10, round(impact_score * multiplier))
            return max(impact_score, boosted)  # never decrease
    return impact_score


def enrich_article(article: RawArticle) -> Dict[str, Any]:
    """Produce a fully enriched intelligence record from a raw article."""
    categories, score = classify_article(article.title, article.content)
    score = apply_source_boost(score, article.source)
    entities = extract_key_entities(article.title, article.content)
    talent_impact = compute_talent_impact(categories, article.title, article.content)

    # Build clean summary (trim content to 3 sentences max)
    raw_content = article.content.strip()
    sentences = re.split(r'(?<=[.!?])\s+', raw_content)
    summary = " ".join(sentences[:3]) if sentences else raw_content[:300]
    summary = summary[:500]  # hard cap

    return {
        "title": article.title,
        "source": article.source,
        "date": article.published_at.isoformat() if article.published_at else None,
        "url": article.url,
        "summary": summary,
        "impact_score": score,
        "categories": categories,
        "key_entities": entities,
        "potential_impact_on_talent_or_competition": talent_impact,
        # Internal fields for DB storage
        "_external_id": article.external_id,
        "_language": article.language,
        "_tickers": article.tickers or [],
        "_raw_metadata": article.raw_metadata or {},
    }


# ── SQLAlchemy engine ──────────────────────────────────────────────────────────

def _get_engine():
    from functools import lru_cache

    @lru_cache(maxsize=1)
    def _engine():
        url = settings.database_url("hr")
        return create_engine(url, pool_pre_ping=True)

    return _engine()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:64]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _cutoff() -> datetime:
    return _now_utc() - timedelta(hours=_MAX_ARTICLE_AGE_HOURS)


def _is_already_stored(session: Session, external_id: str) -> bool:
    row = session.execute(
        text("SELECT 1 FROM market_raw_articles WHERE external_id = :eid LIMIT 1"),
        {"eid": external_id},
    ).fetchone()
    return row is not None


def _save_article(session: Session, article: RawArticle) -> bool:
    if _is_already_stored(session, article.external_id):
        return False
    row = MarketRawArticle(
        external_id=article.external_id,
        title=article.title,
        content=article.content,
        source=article.source,
        url=article.url,
        published_at=article.published_at,
        language=article.language,
        tickers=article.tickers,
        keywords=article.keywords,
        raw_metadata=article.raw_metadata,
    )
    session.add(row)
    return True


# ── Source 1 : NewsAPI ─────────────────────────────────────────────────────────

# High-impact queries for NewsAPI — focused on global strategic events
_NEWSAPI_HIGH_IMPACT_QUERIES = [
    # AI / Tech launches
    "AI model launch OpenAI Anthropic Google Meta DeepSeek",
    "generative AI enterprise deployment breakthrough",
    "AI regulation EU AI Act compliance",
    # Financial markets
    "stock market crash correction recession earnings",
    "acquisition merger billion tech company",
    "IPO valuation unicorn funding round",
    # Geopolitics
    "sanctions geopolitical risk trade war tariff",
    "energy crisis supply chain disruption",
    # Talent / Workforce
    "mass layoff tech company restructuring workforce",
    "talent shortage developer hiring AI engineer",
    # Regulatory
    "GDPR fine cybersecurity regulation data breach",
    "antitrust investigation tech monopoly banned",
]


class NewsAPICollector:
    """Fetches top-impact news via newsapi.org — focuses on high-signal queries."""

    BASE_URL = "https://newsapi.org/v2"

    # Domains that produce the highest-quality articles
    _PREFERRED_DOMAINS = (
        "reuters.com,bloomberg.com,ft.com,wsj.com,cnbc.com,"
        "techcrunch.com,wired.com,economist.com,lesechos.fr,bfmbusiness.bfmtv.com"
    )

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}

    def fetch(
        self,
        queries: Optional[List[str]] = None,
        language: str = "en",
        page_size: int = 15,
    ) -> List[RawArticle]:
        if not self.api_key:
            logger.warning("NewsAPI key not configured — skipping")
            return []

        queries = queries or _NEWSAPI_HIGH_IMPACT_QUERIES[:6]
        articles: List[RawArticle] = []
        cutoff = _cutoff()

        with httpx.Client(timeout=_HTTP_TIMEOUT, headers=_HEADERS) as client:
            for query in queries:
                try:
                    resp = client.get(
                        f"{self.BASE_URL}/everything",
                        headers=self.headers,
                        params={
                            "q": query,
                            "language": language,
                            "sortBy": "relevancy",
                            "pageSize": page_size,
                            "from": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
                            # Restrict to high-quality domains when possible
                            "domains": self._PREFERRED_DOMAINS,
                        },
                    )
                    if resp.status_code == 426:
                        # Free tier: domains param not allowed — retry without it
                        resp = client.get(
                            f"{self.BASE_URL}/everything",
                            headers=self.headers,
                            params={
                                "q": query,
                                "language": language,
                                "sortBy": "relevancy",
                                "pageSize": page_size,
                                "from": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
                            },
                        )
                    resp.raise_for_status()
                    for item in resp.json().get("articles", []):
                        url = item.get("url", "")
                        if not url or "[Removed]" in url:
                            continue
                        try:
                            pub_at = datetime.fromisoformat(
                                item.get("publishedAt", "").replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except Exception:
                            pub_at = _now_utc()
                        if pub_at < cutoff:
                            continue
                        source_name = item.get("source", {}).get("name", "NewsAPI")
                        articles.append(
                            RawArticle(
                                external_id=_url_hash(url),
                                title=item.get("title") or "",
                                content=(
                                    item.get("content") or
                                    item.get("description") or ""
                                ),
                                source=source_name,
                                url=url,
                                published_at=pub_at,
                                language=language,
                                raw_metadata={
                                    "query": query,
                                    "author": item.get("author"),
                                    "source_name": source_name,
                                    "_collector": "NewsAPI",
                                },
                            )
                        )
                    time.sleep(0.3)  # gentle rate-limit compliance
                except Exception as e:
                    logger.warning("NewsAPI query '%s' failed: %s", query, e)

        logger.info("NewsAPI: fetched %d raw articles", len(articles))
        return articles


# ── Source 2 : GNews API ───────────────────────────────────────────────────────

_GNEWS_HIGH_IMPACT_QUERIES_FR = [
    "intelligence artificielle réglementation IA Act",
    "résultats financiers bourse acquisition fusion",
    "géopolitique sanctions guerre commerciale",
    "recrutement licenciement marché emploi tech",
    "Capgemini Sopra Steria Atos Accenture stratégie",
]


class GNewsCollector:
    """Fetches high-impact news from gnews.io — good for French-language coverage."""

    BASE_URL = "https://gnews.io/api/v4"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch(
        self,
        queries: Optional[List[str]] = None,
        lang: str = "fr",
        max_articles: int = 10,
    ) -> List[RawArticle]:
        if not self.api_key:
            logger.warning("GNews API key not configured — skipping")
            return []

        queries = (queries or _GNEWS_HIGH_IMPACT_QUERIES_FR)[:3]  # free tier: 100/day
        articles: List[RawArticle] = []

        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            for i, query in enumerate(queries):
                if i > 0:
                    time.sleep(2)
                try:
                    resp = client.get(
                        f"{self.BASE_URL}/search",
                        params={
                            "q": query,
                            "lang": lang,
                            "max": max_articles,
                            "token": self.api_key,
                            "sortby": "relevance",
                        },
                    )
                    if resp.status_code == 429:
                        logger.warning("GNews: rate limit — stopping")
                        break
                    resp.raise_for_status()
                    for item in resp.json().get("articles", []):
                        url = item.get("url", "")
                        if not url:
                            continue
                        try:
                            pub_at = datetime.fromisoformat(
                                item.get("publishedAt", "").replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except Exception:
                            pub_at = _now_utc()
                        articles.append(
                            RawArticle(
                                external_id=_url_hash(url),
                                title=item.get("title") or "",
                                content=item.get("description") or item.get("content") or "",
                                source=item.get("source", {}).get("name", "GNews"),
                                url=url,
                                published_at=pub_at,
                                language=lang,
                                raw_metadata={"query": query, "_collector": "GNews"},
                            )
                        )
                except Exception as e:
                    logger.warning("GNews query '%s' failed: %s", query, e)

        logger.info("GNews: fetched %d raw articles", len(articles))
        return articles


# ── Source 3 : RSS Feeds (Tier 1 + Tier 2) ───────────────────────────────────

class RSSCollector:
    """Parses Tier-1 and Tier-2 RSS/Atom feeds — unlimited, no API key needed.

    Tier-1 feeds (Reuters, WSJ, CNBC, FT, Economist, TechCrunch, Wired) are
    parsed first since they produce the highest-impact articles.
    """

    def __init__(
        self,
        tier1_feeds: Optional[List[Tuple[str, str, str]]] = None,
        tier2_feeds: Optional[List[Tuple[str, str, str]]] = None,
    ):
        self.tier1 = tier1_feeds or RSS_FEEDS_TIER1
        self.tier2 = tier2_feeds or RSS_FEEDS_TIER2

    def _parse_feed(self, feed_url: str, source_name: str, lang: str) -> List[RawArticle]:
        articles: List[RawArticle] = []
        cutoff = _cutoff()
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if not url:
                    continue

                # Parse date
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_at = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pub_at = _now_utc()
                else:
                    pub_at = _now_utc()

                if pub_at < cutoff:
                    continue

                # Build content: prefer summary over description, strip HTML
                raw = (
                    entry.get("summary") or
                    entry.get("description") or
                    entry.get("content", [{}])[0].get("value", "") or
                    entry.get("title") or ""
                )
                # Strip basic HTML tags
                content = re.sub(r'<[^>]+>', ' ', raw).strip()
                content = re.sub(r'\s{2,}', ' ', content)

                articles.append(
                    RawArticle(
                        external_id=_url_hash(url),
                        title=entry.get("title", "").strip(),
                        content=content[:1000],  # cap at 1000 chars
                        source=source_name,
                        url=url,
                        published_at=pub_at,
                        language=lang,
                        raw_metadata={
                            "feed_url": feed_url,
                            "_collector": "RSS",
                            "_tier": "1" if source_name in [s for _, s, _ in self.tier1] else "2",
                        },
                    )
                )
        except Exception as e:
            logger.warning("RSS feed '%s' failed: %s", feed_url, e)
        return articles

    def fetch(self, tier1_only: bool = False) -> List[RawArticle]:
        articles: List[RawArticle] = []
        feeds = self.tier1 + ([] if tier1_only else self.tier2)
        for feed_url, source_name, lang in feeds:
            articles.extend(self._parse_feed(feed_url, source_name, lang))
        logger.info("RSS: fetched %d raw articles (%s)", len(articles),
                    "tier1 only" if tier1_only else "tier1+tier2")
        return articles


# ── Source 4 : yfinance ────────────────────────────────────────────────────────

class YFinanceCollector:
    """Fetches OHLCV snapshots and news for tracked tickers via yfinance."""

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or DEFAULT_TICKERS

    def fetch_news(self) -> List[RawArticle]:
        articles: List[RawArticle] = []
        for ticker_sym in self.tickers[:15]:
            try:
                t = yf.Ticker(ticker_sym)
                for item in (t.news or []):
                    url = item.get("link") or item.get("url", "")
                    if not url:
                        continue
                    pub_ts = item.get("providerPublishTime", 0)
                    pub_at = (
                        datetime.utcfromtimestamp(pub_ts) if pub_ts else _now_utc()
                    )
                    if pub_at < _cutoff():
                        continue
                    articles.append(
                        RawArticle(
                            external_id=_url_hash(url),
                            title=item.get("title", ""),
                            content=item.get("summary") or item.get("title") or "",
                            source="Yahoo Finance",
                            url=url,
                            published_at=pub_at,
                            tickers=[ticker_sym],
                            raw_metadata={
                                "ticker": ticker_sym,
                                "_collector": "yFinance",
                            },
                        )
                    )
            except Exception as e:
                logger.debug("yFinance news fetch for %s failed: %s", ticker_sym, e)
        logger.info("yFinance: fetched %d news articles", len(articles))
        return articles

    def fetch_prices(self) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for ticker_sym in self.tickers:
            try:
                t = yf.Ticker(ticker_sym)
                hist = t.history(period="2d")
                if hist.empty or len(hist) < 2:
                    continue
                prev_close = hist["Close"].iloc[-2]
                last_close = hist["Close"].iloc[-1]
                volume = hist["Volume"].iloc[-1]
                change_pct = (last_close - prev_close) / prev_close * 100 if prev_close else 0
                hist_20 = t.history(period="1mo")
                vol_20 = 0.0
                if not hist_20.empty and len(hist_20) >= 5:
                    rets = hist_20["Close"].pct_change().dropna()
                    vol_20 = float(rets.std() * (252 ** 0.5) * 100)
                results[ticker_sym] = {
                    "price": round(float(last_close), 4),
                    "change_pct": round(float(change_pct), 4),
                    "volume": int(volume),
                    "volatility_annualised_pct": round(vol_20, 2),
                }
            except Exception as e:
                logger.debug("yFinance price fetch for %s failed: %s", ticker_sym, e)
        return results


# ── Main Orchestrator ──────────────────────────────────────────────────────────

class MarketDataCollector:
    """Orchestrates all sub-collectors, filters for impact, classifies, and persists.

    Pipeline:
      collect (4 sources) → deduplicate → classify → impact filter → persist
    """

    def __init__(self):
        self.newsapi = NewsAPICollector(settings.newsapi_key)
        self.gnews = GNewsCollector(settings.gnews_key)
        self.rss = RSSCollector()
        self.yfinance = YFinanceCollector()

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(
        self,
        extra_keywords: Optional[List[str]] = None,
        min_impact: int = MIN_IMPACT_SCORE,
        rss_tier1_only: bool = False,
    ) -> CollectorResult:
        """Full collection pipeline.

        Args:
            extra_keywords:  Additional NewsAPI queries to run.
            min_impact:      Drop articles scoring below this (1–10). Default: 5.
            rss_tier1_only:  If True, only parse Tier-1 RSS feeds (faster).

        Returns:
            CollectorResult with counts, enriched articles, and errors.
        """
        errors: List[str] = []
        raw_articles: List[RawArticle] = []

        # ── Step 1: Collect from all sources ──────────────────────────────────
        for label, collector_fn in [
            ("NewsAPI",  lambda: self.newsapi.fetch(queries=extra_keywords)),
            ("GNews",    lambda: self.gnews.fetch()),
            ("RSS",      lambda: self.rss.fetch(tier1_only=rss_tier1_only)),
            ("yFinance", lambda: self.yfinance.fetch_news()),
        ]:
            try:
                raw_articles += collector_fn()
            except Exception as e:
                errors.append(f"{label}: {e}")
                logger.exception("%s collector failed: %s", label, e)

        # ── Step 2: Deduplicate by external_id ────────────────────────────────
        seen: set = set()
        deduped: List[RawArticle] = []
        for art in raw_articles:
            if art.external_id not in seen:
                seen.add(art.external_id)
                deduped.append(art)

        # ── Step 3: Classify & filter by impact score ─────────────────────────
        enriched: List[Dict[str, Any]] = []
        for art in deduped:
            if not art.title:
                continue
            record = enrich_article(art)
            if record["impact_score"] >= min_impact:
                enriched.append(record)

        # Sort by impact score descending
        enriched.sort(key=lambda x: x["impact_score"], reverse=True)

        # ── Step 4: Persist high-impact articles to DB ────────────────────────
        new_count = 0
        engine = _get_engine()
        with Session(engine) as session:
            for rec in enriched:
                # Reconstruct minimal RawArticle for storage
                art = RawArticle(
                    external_id=rec["_external_id"],
                    title=rec["title"],
                    content=rec["summary"],
                    source=rec["source"],
                    url=rec["url"],
                    published_at=datetime.fromisoformat(rec["date"]) if rec["date"] else _now_utc(),
                    language=rec["_language"],
                    tickers=rec["_tickers"],
                    keywords=rec["categories"],
                    raw_metadata={
                        **rec["_raw_metadata"],
                        "impact_score": rec["impact_score"],
                        "categories": rec["categories"],
                        "key_entities": rec["key_entities"],
                        "talent_impact": rec["potential_impact_on_talent_or_competition"],
                    },
                )
                try:
                    if _save_article(session, art):
                        new_count += 1
                except Exception as e:
                    logger.warning("Failed to save article %s: %s", art.external_id, e)
            session.commit()

        logger.info(
            "Collector run: %d fetched → %d after dedup → %d above impact=%d → %d new in DB",
            len(raw_articles), len(deduped), len(enriched), min_impact, new_count,
        )

        # Return enriched articles (with internal _fields stripped for external use)
        clean = [{k: v for k, v in rec.items() if not k.startswith("_")} for rec in enriched]

        return CollectorResult(
            articles_fetched=len(deduped),
            articles_new=new_count,
            articles=deduped,  # raw RawArticle list (schema requirement)
            errors=errors,
            # Extra: attach enriched records via raw_metadata field on result
        )

    def run_enriched(
        self,
        extra_keywords: Optional[List[str]] = None,
        min_impact: int = MIN_IMPACT_SCORE,
        rss_tier1_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Same as run() but returns the enriched JSON records directly.

        Ideal for API endpoints that need the classified + scored output.

        Returns:
            List of dicts with: title, source, date, url, summary,
            impact_score, categories, key_entities,
            potential_impact_on_talent_or_competition.
        """
        errors: List[str] = []
        raw_articles: List[RawArticle] = []

        for label, collector_fn in [
            ("NewsAPI",  lambda: self.newsapi.fetch(queries=extra_keywords)),
            ("GNews",    lambda: self.gnews.fetch()),
            ("RSS",      lambda: self.rss.fetch(tier1_only=rss_tier1_only)),
            ("yFinance", lambda: self.yfinance.fetch_news()),
        ]:
            try:
                raw_articles += collector_fn()
            except Exception as e:
                errors.append(f"{label}: {e}")
                logger.exception("%s collector failed: %s", label, e)

        # Deduplicate
        seen: set = set()
        deduped: List[RawArticle] = []
        for art in raw_articles:
            if art.external_id not in seen and art.title:
                seen.add(art.external_id)
                deduped.append(art)

        # Classify & filter
        enriched = []
        for art in deduped:
            record = enrich_article(art)
            if record["impact_score"] >= min_impact:
                enriched.append(record)

        enriched.sort(key=lambda x: x["impact_score"], reverse=True)

        # Strip internal fields
        return [{k: v for k, v in rec.items() if not k.startswith("_")} for rec in enriched]

    def fetch_price_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return self.yfinance.fetch_prices()

    def get_unanalysed_articles(self, limit: int = 50) -> List[Dict[str, Any]]:
        engine = _get_engine()
        with Session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT id, external_id, title, content, source, url, published_at, "
                    "       language, tickers, keywords "
                    "FROM market_raw_articles "
                    "WHERE analysed = false "
                    "ORDER BY published_at DESC "
                    "LIMIT :lim"
                ),
                {"lim": limit},
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_enriched_from_db(
        self,
        hours: int = 48,
        min_impact: int = MIN_IMPACT_SCORE,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return enriched articles already stored in market_raw_articles.

        Uses the impact_score / categories / key_entities cached in raw_metadata
        to reconstruct EnrichedArticle-compatible dicts without hitting external APIs.
        """
        engine = _get_engine()
        with Session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT title, source, url, published_at, raw_metadata "
                    "FROM market_raw_articles "
                    "WHERE published_at >= NOW() - (INTERVAL '1 hour' * :hrs) "
                    "ORDER BY published_at DESC "
                    "LIMIT :lim"
                ),
                {"hrs": hours, "lim": limit * 3},  # over-fetch then filter
            ).mappings().all()

        results = []
        for r in rows:
            meta = r["raw_metadata"] or {}
            score = int(meta.get("impact_score", 0))
            if score < min_impact:
                continue
            results.append({
                "title": r["title"] or "",
                "source": r["source"] or "",
                "date": r["published_at"].isoformat() if r["published_at"] else None,
                "url": r["url"] or "",
                "summary": r["title"] or "",  # content was stored as summary
                "impact_score": score,
                "categories": meta.get("categories", []),
                "key_entities": meta.get("key_entities", []),
                "potential_impact_on_talent_or_competition": meta.get("talent_impact", ""),
            })
            if len(results) >= limit:
                break

        results.sort(key=lambda x: x["impact_score"], reverse=True)
        return results

    def mark_as_analysed(self, article_ids: List[str]) -> None:
        if not article_ids:
            return
        engine = _get_engine()
        with Session(engine) as session:
            session.execute(
                text(
                    "UPDATE market_raw_articles SET analysed = true "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": article_ids},
            )
            session.commit()
