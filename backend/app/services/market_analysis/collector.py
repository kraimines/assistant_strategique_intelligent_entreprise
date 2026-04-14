"""Collector Module — fetches real-time economic and financial news.

Sources (in priority order):
1. NewsAPI        — structured API, 100 req/day free
2. GNews API      — Google News aggregator, 100 req/day free
3. RSS Feeds      — Reuters, Les Echos, Bloomberg, FT, WSJ (unlimited)
4. yfinance       — price/volume snapshots for tracked tickers
5. Alpha Vantage  — fallback market data if yfinance fails

All results are deduplicated by URL hash and stored in PostgreSQL.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import feedparser  # already in requirements
import httpx
import yfinance as yf
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.market_analysis_models import MarketRawArticle
from app.schemas.market_analysis_schemas import CollectorResult, RawArticle

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_TICKERS = [
    # French market index (Talan est non coté — on suit ses concurrents cotés)
    "^FCHI",              # CAC 40 (correct yfinance symbol)
    "^GSPC", "^NDX",      # S&P 500, NASDAQ 100
    # IT services concurrents de Talan
    "CAP.PA",             # Capgemini
    "SOP.PA",             # Sopra Steria
    "ATO.PA",             # Atos
    "SAP",                # SAP
    "ACN",                # Accenture
    # Big tech (influence IA et budgets IT)
    "MSFT", "GOOGL", "NVDA", "META",
    # Macro
    "EURUSD=X",           # EUR/USD
    "BZ=F",               # Brent crude oil
    "^VIX",               # Volatility index
]

DEFAULT_KEYWORDS = [
    # ── 1. Macroéconomie & Marchés ────────────────────────────────────────────
    # Croissance / Récession
    "PIB croissance économique", "récession inflation", "taux d'intérêt BCE",
    "politique monétaire Fed", "GDP recession", "inflation eurozone",
    "interest rates ECB Fed", "stagflation",
    # Matières premières & Supply chain
    "pétrole brut prix", "matières premières hausse", "supply chain disruption",
    "pénurie composants", "crude oil price", "commodity supply chain",
    # Devises & Finance
    "EUR/USD taux de change", "TND dinar tunisien", "crise monétaire",
    "dette publique financement", "currency crisis", "sovereign debt",
    # Indicateurs avancés
    "PMI manufacturing", "indice confiance consommateur", "chômage emploi",
    "ventes au détail", "PMI Africa", "consumer confidence index",

    # ── 2. Réglementation & Conformité ───────────────────────────────────────
    # RGPD / Données
    "RGPD données personnelles", "AI Act Europe", "privacy law DPDP",
    "loi numérique réglementation", "GDPR enforcement", "data protection law",
    # IA & Tech
    "régulation intelligence artificielle", "éthique IA", "cybersécurité réglementation",
    "AI regulation ethics", "cybersecurity law", "EU AI Act compliance",
    # Fiscalité / Douanes
    "réforme fiscale TVA", "taxe carbone", "accords libre-échange",
    "douane Tunisie", "trade agreement", "carbon tax reform",
    # Fintech
    "réglementation fintech", "open banking", "crypto régulation",
    "fintech regulation", "crypto regulation Europe",

    # ── 3. Tendances Technologiques & Innovation ──────────────────────────────
    "GenAI deployment", "edge computing quantum", "breakthrough innovation tech",
    "premier déploiement IA", "partenariat stratégique tech",
    "proof of concept MVP", "roadmap 2026 technology",
    "investissement R&D innovation", "budget innovation 2025 2026",
    "AI adoption enterprise", "generative AI enterprise",

    # ── 4. Financement & Investissements ─────────────────────────────────────
    "levée de fonds Series A B C", "funding round venture capital",
    "investissement stratégique tech", "acquisition fusion M&A",
    "startup funding ESN consulting", "fonds souverain subvention",
    "Banque Mondiale BAD investissement Afrique",
    "M&A digital transformation", "private equity tech Europe",

    # ── 5. Chaîne d'Approvisionnement & Opérations ───────────────────────────
    "nearshoring friendshoring", "coût transport fret maritime",
    "Suez Panama logistique", "logistique Afrique", "retard livraison",
    "hausse tarif électricité énergie", "transition énergétique",
    "nearshoring Africa", "shipping cost freight",

    # ── 6. Comportement Consommateur & Marché ────────────────────────────────
    "tendance consommation Gen Z", "personnalisation durabilité",
    "churn insatisfaction client", "Ramadan consommation",
    "JO 2028 opportunité", "Black Friday e-commerce",
    "consumer trend sustainability", "digital consumer behavior",

    # ── 7. Géopolitique & Risques Pays ───────────────────────────────────────
    "tension géopolitique sanction", "guerre commerciale",
    "accord UE Tunisie AfCFTA", "instabilité politique élection",
    "geopolitical risk sanctions", "EU Africa trade",
    "Tunisia economy politics", "AfCFTA Africa free trade",

    # ── Concurrents & Secteur Talan ───────────────────────────────────────────
    "Talan ESN consulting", "Capgemini Sopra Steria Atos",
    "digital transformation ESN", "IT consulting France Tunisie",
    "cloud cybersecurity consulting", "tech layoffs ESN",
]

RSS_FEEDS = [
    # ── International (EN) ────────────────────────────────────────────────────
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/reuters/technologyNews",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",        # WSJ Markets
    "https://feeds.bbci.co.uk/news/business/rss.xml",       # BBC Business
    "https://www.ft.com/?format=rss",                       # Financial Times

    # ── France (FR) ───────────────────────────────────────────────────────────
    "https://www.lesechos.fr/rss/rss_finance.xml",
    "https://www.lesechos.fr/rss/rss_technologie.xml",
    "https://www.lemonde.fr/economie/rss_full.xml",
    "https://bfmbusiness.bfmtv.com/rss/info/flux-rss/flux-toutes-les-actualites/",
    "https://www.latribune.fr/rss/rubriques/economie.html",

    # ── Afrique & Tunisie ─────────────────────────────────────────────────────
    "https://www.jeuneafrique.com/feed/",                   # Jeune Afrique
    "https://africanews.com/feed/",                         # African News EN
    "https://www.tap.info.tn/en/feed/",                     # TAP Tunisie EN
    "https://www.businessnews.com.tn/rss.xml",              # Business News TN
    "https://kapitalis.com/tunisie/feed/",                  # Kapitalis TN

    # ── Tech & Innovation ─────────────────────────────────────────────────────
    "https://techcrunch.com/feed/",                         # TechCrunch
    "https://www.wired.com/feed/rss",                       # Wired
    "https://venturebeat.com/feed/",                        # VentureBeat AI/Tech
]

_MAX_ARTICLE_AGE_HOURS = 48   # only collect articles < 48h old


# ── SQLAlchemy engine (uses talan_hr DB for storage) ─────────────────────────

def _get_engine():
    from functools import lru_cache

    @lru_cache(maxsize=1)
    def _engine():
        url = settings.database_url("hr")
        return create_engine(url, pool_pre_ping=True)

    return _engine()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    """SHA-256 of URL → used as external_id for deduplication."""
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
    """Insert article if not duplicate. Returns True if new."""
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


# ── Source 1 : NewsAPI ────────────────────────────────────────────────────────

class NewsAPICollector:
    """Collects top headlines and keyword searches from newsapi.org."""

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}

    def fetch(
        self,
        queries: Optional[List[str]] = None,
        language: str = "en",
        page_size: int = 20,
    ) -> List[RawArticle]:
        if not self.api_key:
            logger.warning("NewsAPI key not configured — skipping")
            return []
        queries = queries or DEFAULT_KEYWORDS[:5]
        articles: List[RawArticle] = []
        cutoff = _cutoff()

        with httpx.Client(timeout=15) as client:
            for query in queries:
                try:
                    resp = client.get(
                        f"{self.BASE_URL}/everything",
                        headers=self.headers,
                        params={
                            "q": query,
                            "language": language,
                            "sortBy": "publishedAt",
                            "pageSize": page_size,
                            "from": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for item in data.get("articles", []):
                        try:
                            pub_at = datetime.fromisoformat(
                                item.get("publishedAt", "").replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                            if pub_at < cutoff:
                                continue
                            url = item.get("url", "")
                            if not url:
                                continue
                            articles.append(
                                RawArticle(
                                    external_id=_url_hash(url),
                                    title=item.get("title", ""),
                                    content=(
                                        item.get("content") or
                                        item.get("description") or ""
                                    ),
                                    source="NewsAPI",
                                    url=url,
                                    published_at=pub_at,
                                    language=language,
                                    raw_metadata={
                                        "query": query,
                                        "author": item.get("author"),
                                        "source_name": item.get("source", {}).get("name"),
                                    },
                                )
                            )
                        except Exception as e:
                            logger.debug("NewsAPI article parse error: %s", e)
                except Exception as e:
                    logger.warning("NewsAPI query '%s' failed: %s", query, e)
        logger.info("NewsAPI: fetched %d articles", len(articles))
        return articles


# ── Source 2 : GNews API ──────────────────────────────────────────────────────

class GNewsCollector:
    """Collects news from gnews.io — good for French-language coverage."""

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
        queries = queries or ["Talan ESN", "économie France", "marché financier"]
        # GNews free tier: 100 req/day → limit to 3 queries per cycle with delay
        queries = queries[:3]
        articles: List[RawArticle] = []

        with httpx.Client(timeout=15) as client:
            for i, query in enumerate(queries):
                if i > 0:
                    time.sleep(2)  # avoid 429
                try:
                    resp = client.get(
                        f"{self.BASE_URL}/search",
                        params={
                            "q": query,
                            "lang": lang,
                            "max": max_articles,
                            "token": self.api_key,
                        },
                    )
                    if resp.status_code == 429:
                        logger.warning("GNews: rate limit hit — stopping queries")
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
                                title=item.get("title", ""),
                                content=item.get("description") or item.get("content") or "",
                                source="GNews",
                                url=url,
                                published_at=pub_at,
                                language=lang,
                                raw_metadata={"query": query},
                            )
                        )
                except Exception as e:
                    logger.warning("GNews query '%s' failed: %s", query, e)
        logger.info("GNews: fetched %d articles", len(articles))
        return articles


# ── Source 3 : RSS Feeds ──────────────────────────────────────────────────────

class RSSCollector:
    """Parses RSS/Atom feeds — unlimited, no API key needed."""

    def __init__(self, feed_urls: Optional[List[str]] = None):
        self.feeds = feed_urls or RSS_FEEDS

    def fetch(self) -> List[RawArticle]:
        articles: List[RawArticle] = []
        cutoff = _cutoff()

        for feed_url in self.feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    url = entry.get("link", "")
                    if not url:
                        continue
                    # Parse publication date
                    pub_at: datetime
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        import time as _time
                        pub_at = datetime(*entry.published_parsed[:6])
                    else:
                        pub_at = _now_utc()

                    if pub_at < cutoff:
                        continue

                    content = (
                        entry.get("summary") or
                        entry.get("description") or
                        entry.get("title") or ""
                    )
                    # Detect language from feed domain
                    lang = "fr" if any(
                        d in feed_url for d in ["lesechos", "lemonde", "bfm"]
                    ) else "en"

                    articles.append(
                        RawArticle(
                            external_id=_url_hash(url),
                            title=entry.get("title", ""),
                            content=content,
                            source=f"RSS:{feed.feed.get('title', feed_url[:40])}",
                            url=url,
                            published_at=pub_at,
                            language=lang,
                            raw_metadata={"feed_url": feed_url},
                        )
                    )
            except Exception as e:
                logger.warning("RSS feed '%s' failed: %s", feed_url, e)
        logger.info("RSS: fetched %d articles", len(articles))
        return articles


# ── Source 4 : yfinance Market Snapshots ─────────────────────────────────────

class YFinanceCollector:
    """Fetches OHLCV snapshots and news for tracked tickers via yfinance."""

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or DEFAULT_TICKERS

    def fetch_news(self) -> List[RawArticle]:
        """Fetches recent news attached to tickers from Yahoo Finance."""
        articles: List[RawArticle] = []
        for ticker_sym in self.tickers[:15]:   # limit to avoid rate limit
            try:
                t = yf.Ticker(ticker_sym)
                news_items = t.news or []
                for item in news_items:
                    url = item.get("link") or item.get("url", "")
                    if not url:
                        continue
                    pub_ts = item.get("providerPublishTime", 0)
                    pub_at = (
                        datetime.utcfromtimestamp(pub_ts)
                        if pub_ts else _now_utc()
                    )
                    if pub_at < _cutoff():
                        continue
                    articles.append(
                        RawArticle(
                            external_id=_url_hash(url),
                            title=item.get("title", ""),
                            content=item.get("summary") or item.get("title") or "",
                            source="yFinance",
                            url=url,
                            published_at=pub_at,
                            tickers=[ticker_sym],
                            raw_metadata={"ticker": ticker_sym},
                        )
                    )
            except Exception as e:
                logger.debug("yFinance news fetch for %s failed: %s", ticker_sym, e)
        logger.info("yFinance: fetched %d news articles", len(articles))
        return articles

    def fetch_prices(self) -> Dict[str, Dict[str, Any]]:
        """Returns a {ticker: {price, change_pct, volume, volatility}} snapshot."""
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
                # Simple volatility: 20-day std dev of daily returns
                hist_20 = t.history(period="1mo")
                vol_20 = 0.0
                if not hist_20.empty and len(hist_20) >= 5:
                    returns = hist_20["Close"].pct_change().dropna()
                    vol_20 = float(returns.std() * (252 ** 0.5) * 100)  # annualised %
                results[ticker_sym] = {
                    "price": round(float(last_close), 4),
                    "change_pct": round(float(change_pct), 4),
                    "volume": int(volume),
                    "volatility_annualised_pct": round(vol_20, 2),
                }
            except Exception as e:
                logger.debug("yFinance price fetch for %s failed: %s", ticker_sym, e)
        return results


# ── Main Collector ────────────────────────────────────────────────────────────

class MarketDataCollector:
    """Orchestrates all sub-collectors and persists results to PostgreSQL."""

    def __init__(self):
        self.newsapi = NewsAPICollector(settings.newsapi_key)
        self.gnews = GNewsCollector(settings.gnews_key)
        self.rss = RSSCollector()
        self.yfinance = YFinanceCollector()

    def run(self, extra_keywords: Optional[List[str]] = None) -> CollectorResult:
        """Run all collectors, deduplicate, and persist to DB.

        Returns a CollectorResult with counts and the list of new articles.
        """
        errors: List[str] = []
        all_articles: List[RawArticle] = []

        # Collect from all sources
        try:
            all_articles += self.newsapi.fetch(queries=extra_keywords)
        except Exception as e:
            errors.append(f"NewsAPI: {e}")
            logger.exception("NewsAPI collector failed: %s", e)

        try:
            all_articles += self.gnews.fetch()
        except Exception as e:
            errors.append(f"GNews: {e}")
            logger.exception("GNews collector failed: %s", e)

        try:
            all_articles += self.rss.fetch()
        except Exception as e:
            errors.append(f"RSS: {e}")
            logger.exception("RSS collector failed: %s", e)

        try:
            all_articles += self.yfinance.fetch_news()
        except Exception as e:
            errors.append(f"yFinance: {e}")
            logger.exception("yFinance collector failed: %s", e)

        # Deduplicate by external_id (within this batch)
        seen: set[str] = set()
        deduped: List[RawArticle] = []
        for art in all_articles:
            if art.external_id not in seen:
                seen.add(art.external_id)
                deduped.append(art)

        # Persist new articles to DB
        new_count = 0
        engine = _get_engine()
        with Session(engine) as session:
            for art in deduped:
                try:
                    if _save_article(session, art):
                        new_count += 1
                except Exception as e:
                    logger.warning("Failed to save article %s: %s", art.external_id, e)
            session.commit()

        logger.info(
            "Collector run complete: %d fetched, %d new after dedup",
            len(deduped), new_count
        )
        return CollectorResult(
            articles_fetched=len(deduped),
            articles_new=new_count,
            articles=deduped,
            errors=errors,
        )

    def fetch_price_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Returns current price snapshots for all tracked tickers."""
        return self.yfinance.fetch_prices()

    def get_unanalysed_articles(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch articles from DB that have not yet been analysed by the LLM."""
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

    def mark_as_analysed(self, article_ids: List[str]) -> None:
        """Mark a batch of articles as analysed."""
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
