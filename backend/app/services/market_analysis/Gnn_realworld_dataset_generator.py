"""
gnn_realworld_dataset_generator.py
===================================
Production-grade real-world GNN dataset generator for Talan's Strategic Knowledge Graph.

Replaces synthetic data with real historical event-driven data from:
  - GDELT 2.0 (global events database, free API)
  - Yahoo Finance / yfinance (stock prices, sector ETFs)

Pipeline stages:
  1. RealWorldEventGenerator  — fetch & filter GDELT events (economic, financial, corporate, geopolitical)
  2. MarketDataFetcher         — pull stock prices & compute returns/volatility via yfinance
  3. EventEntityMapper         — rule-based deterministic mapping: event → companies / sectors / macros
  4. GraphBuilder              — construct GNNNode / GNNEdge objects compatible with existing pipeline
  5. DatasetExporter           — write nodes.csv / edges.csv / node_features.npy / metadata.json

Fully compatible with GNNDatasetPipeline (gnn_dataset_builder.py):
  - same GNNNode / GNNEdge dataclasses
  - same FEATURE_DIM = 396
  - same node types / edge types
  - same Neo4j MERGE structure
  - same PyTorch Geometric HeteroData layout

Scale: supports generation of 10 000+ event-based graph samples.

Caching:
  - GDELT responses cached as gzip-compressed JSON under .cache/gdelt/
  - yfinance price data cached as Parquet under .cache/yfinance/
  - Cache TTL configurable (default 24 h for GDELT, 7 days for price data)

Usage
-----
    from gnn_realworld_dataset_generator import RealWorldDatasetPipeline

    pipeline = RealWorldDatasetPipeline(
        output_dir="./gnn_realworld_dataset",
        cache_dir="./.cache",
        start_date="2020-01-01",
        end_date="2024-12-31",
        max_events=10_000,
    )
    summary = pipeline.run()
    print(summary["stats"])

    # Optional: push enriched data back into Neo4j
    # pipeline.push_to_neo4j(neo4j_uri=..., neo4j_user=..., neo4j_password=...)
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import numpy as np
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

# ─────────────────────────────────────────────────────────────────────────────
# § 1  SCHEMA CONSTANTS  (must stay in sync with gnn_dataset_builder.py)
# ─────────────────────────────────────────────────────────────────────────────

GNN_NODE_TYPES: List[str] = [
    "Company", "BusinessUnit", "Sector", "Geography",
    "Client", "Project", "Competitor", "Regulation",
    "MacroIndicator", "Event",
]

GNN_EDGE_TYPES: List[str] = [
    "AFFECTS", "BELONGS_TO_SECTOR", "COMPETES_WITH",
    "DELIVERED_FOR", "IMPACTS", "INFLUENCES",
    "OPERATES_IN", "SERVES", "SUPPLY_CHAIN_LINK",
]

EMBEDDING_DIM: int = 384
STRUCTURAL_DIM: int = 2
FEATURE_DIM: int = len(GNN_NODE_TYPES) + STRUCTURAL_DIM + EMBEDDING_DIM  # 396

# ─────────────────────────────────────────────────────────────────────────────
# § 2  DATA STRUCTURES  (same as existing pipeline)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GNNNode:
    gnn_id: int
    gnn_type: str
    name: str
    slug: str
    props: Dict[str, Any] = field(default_factory=dict)
    degree: int = 0
    impact_score: float = 0.0
    source: str = "realworld"

@dataclass
class GNNEdge:
    source_id: int
    target_id: int
    gnn_type: str
    weight: float = 1.0
    timestamp: Optional[str] = None
    source_system: str = "realworld"

# ─────────────────────────────────────────────────────────────────────────────
# § 3  UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "_", text).strip("_")


def _normalize(values: List[float]) -> List[float]:
    lo, hi = min(values, default=0.0), max(values, default=1.0)
    rng = hi - lo or 1.0
    return [(v - lo) / rng for v in values]


def _cache_key(url: str, params: Dict) -> str:
    raw = url + json.dumps(params, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def _is_fresh(path: Path, ttl_hours: int) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_hours * 3600


# ─────────────────────────────────────────────────────────────────────────────
# § 4  ENTITY KNOWLEDGE BASE (deterministic rule-based mapping)
# ─────────────────────────────────────────────────────────────────────────────

# Maps keyword patterns (lowercase) → (entity_name, entity_type)
# Checked in order; first match wins for high-priority rules.
# These cover the most economically significant actors in Talan's target markets.

ENTITY_KEYWORD_RULES: List[Tuple[str, str, str]] = [
    # ── Central banks ──────────────────────────────────────────────────────
    ("european central bank",   "ECB Interest Rates",       "MacroIndicator"),
    ("ecb",                      "ECB Interest Rates",       "MacroIndicator"),
    ("federal reserve",          "Federal Reserve Rate",     "MacroIndicator"),
    ("fed rate",                 "Federal Reserve Rate",     "MacroIndicator"),
    ("bank of england",          "Bank of England Rate",     "MacroIndicator"),
    ("boe",                      "Bank of England Rate",     "MacroIndicator"),
    # ── Macro indicators ───────────────────────────────────────────────────
    ("inflation",                "Eurozone Inflation",       "MacroIndicator"),
    ("consumer price",           "Eurozone Inflation",       "MacroIndicator"),
    ("cpi",                      "Eurozone Inflation",       "MacroIndicator"),
    ("unemployment",             "France Unemployment Rate", "MacroIndicator"),
    ("crude oil",                "Brent Crude Oil Price",    "MacroIndicator"),
    ("brent",                    "Brent Crude Oil Price",    "MacroIndicator"),
    ("oil price",                "Brent Crude Oil Price",    "MacroIndicator"),
    ("exchange rate",            "EUR/USD Exchange Rate",    "MacroIndicator"),
    ("eur/usd",                  "EUR/USD Exchange Rate",    "MacroIndicator"),
    ("cac 40",                   "CAC 40 Index",             "MacroIndicator"),
    ("gdp",                      "IT Sector Growth",         "MacroIndicator"),
    ("interest rate",            "ECB Interest Rates",       "MacroIndicator"),
    ("bond yield",               "ECB Interest Rates",       "MacroIndicator"),
    ("semiconductor",            "Semiconductors",           "Sector"),
    ("chip",                     "Semiconductors",           "Sector"),
    ("cybersecurity",            "Cybersecurity Spending Index", "MacroIndicator"),
    ("cloud",                    "Cloud Adoption Rate",      "MacroIndicator"),
    ("ai regulation",            "AI Market Growth Index",   "MacroIndicator"),
    ("artificial intelligence",  "AI Market Growth Index",   "MacroIndicator"),
    ("digital",                  "Government Digital Spending","MacroIndicator"),
    # ── Companies ──────────────────────────────────────────────────────────
    ("apple",           "Apple",            "Company"),
    ("microsoft",       "Microsoft",        "Company"),
    ("amazon",          "Amazon",           "Company"),
    ("alphabet",        "Alphabet",         "Company"),
    ("google",          "Alphabet",         "Company"),
    ("meta",            "Meta",             "Company"),
    ("nvidia",          "NVIDIA",           "Company"),
    ("tesla",           "Tesla",            "Company"),
    ("samsung",         "Samsung",          "Company"),
    ("tsmc",            "TSMC",             "Company"),
    ("intel",           "Intel",            "Company"),
    ("amd",             "AMD",              "Company"),
    ("qualcomm",        "Qualcomm",         "Company"),
    ("asml",            "ASML",             "Company"),
    ("sap",             "SAP",              "Company"),
    ("capgemini",       "Capgemini",        "Competitor"),
    ("accenture",       "Accenture",        "Competitor"),
    ("sopra steria",    "Sopra Steria",     "Competitor"),
    ("atos",            "Atos",             "Competitor"),
    ("cgi",             "CGI",              "Competitor"),
    ("ibm",             "IBM Consulting",   "Competitor"),
    ("deloitte",        "Deloitte",         "Competitor"),
    ("pwc",             "PwC Consulting",   "Competitor"),
    ("ernst & young",   "Ernst & Young",    "Competitor"),
    ("kpmg",            "KPMG Advisory",    "Competitor"),
    ("wavestone",       "Wavestone",        "Competitor"),
    ("jpmorgan",        "JPMorgan",         "Company"),
    ("jp morgan",       "JPMorgan",         "Company"),
    ("goldman sachs",   "Goldman Sachs",    "Company"),
    ("bnp paribas",     "BNP Paribas",      "Company"),
    ("societe generale","Société Générale", "Company"),
    ("credit agricole", "Crédit Agricole",  "Company"),
    ("axa",             "AXA",              "Company"),
    ("lvmh",            "LVMH",             "Company"),
    ("total energies",  "TotalEnergies",    "Company"),
    ("totalenergies",   "TotalEnergies",    "Company"),
    ("orange",          "Orange",           "Company"),
    ("airbus",          "Airbus",           "Company"),
    ("renault",         "Renault",          "Company"),
    ("stellantis",      "Stellantis",       "Company"),
    ("edf",             "EDF",              "Company"),
    ("engie",           "ENGIE",            "Company"),
    ("thales",          "Thales",           "Company"),
    ("dassault",        "Dassault Systèmes","Company"),
    ("alstom",          "Alstom",           "Company"),
    ("sanofi",          "Sanofi",           "Company"),
    ("astrazeneca",     "AstraZeneca",      "Company"),
    ("pfizer",          "Pfizer",           "Company"),
    ("novartis",        "Novartis",         "Company"),
    ("hsbc",            "HSBC",             "Company"),
    ("barclays",        "Barclays",         "Company"),
    ("volkswagen",      "Volkswagen",       "Company"),
    ("siemens",         "Siemens",          "Company"),
    # ── Sectors ────────────────────────────────────────────────────────────
    ("banking",             "Banking & Finance",             "Sector"),
    ("financial services",  "Financial Services",            "Sector"),
    ("fintech",             "Financial Services",            "Sector"),
    ("insurance",           "Insurance",                     "Sector"),
    ("energy",              "Energy & Utilities",            "Sector"),
    ("utilities",           "Energy & Utilities",            "Sector"),
    ("telecom",             "Telecommunications",            "Sector"),
    ("telecommunications",  "Telecommunications",            "Sector"),
    ("government",          "Public Sector",                 "Sector"),
    ("public sector",       "Public Sector",                 "Sector"),
    ("retail",              "Retail & Consumer Goods",       "Sector"),
    ("consumer",            "Retail & Consumer Goods",       "Sector"),
    ("healthcare",          "Healthcare & Life Sciences",    "Sector"),
    ("pharma",              "Healthcare & Life Sciences",    "Sector"),
    ("transport",           "Transportation & Logistics",    "Sector"),
    ("logistics",           "Transportation & Logistics",    "Sector"),
    ("manufacturing",       "Industry & Manufacturing",      "Sector"),
    ("industry",            "Industry & Manufacturing",      "Sector"),
    ("defense",             "Defense & Aerospace",           "Sector"),
    ("aerospace",           "Defense & Aerospace",           "Sector"),
    ("real estate",         "Real Estate & Construction",    "Sector"),
    ("construction",        "Real Estate & Construction",    "Sector"),
    ("media",               "Media & Entertainment",         "Sector"),
    ("entertainment",       "Media & Entertainment",         "Sector"),
    ("it services",         "IT Services",                   "Sector"),
    ("software",            "IT Services",                   "Sector"),
    # ── Geographies ────────────────────────────────────────────────────────
    ("france",          "France",           "Geography"),
    ("french",          "France",           "Geography"),
    ("germany",         "Germany",          "Geography"),
    ("german",          "Germany",          "Geography"),
    ("united kingdom",  "United Kingdom",   "Geography"),
    ("britain",         "United Kingdom",   "Geography"),
    ("uk ",             "United Kingdom",   "Geography"),
    ("spain",           "Spain",            "Geography"),
    ("spain",           "Spain",            "Geography"),
    ("italy",           "Italy",            "Geography"),
    ("european union",  "European Union",   "Geography"),
    ("europe",          "European Union",   "Geography"),
    ("eurozone",        "European Union",   "Geography"),
    ("united states",   "United States",    "Geography"),
    ("u.s.",            "United States",    "Geography"),
    ("china",           "China",            "Geography"),
    ("chinese",         "China",            "Geography"),
    ("russia",          "Russia",           "Geography"),
    ("ukraine",         "Ukraine",          "Geography"),
    ("middle east",     "Saudi Arabia",     "Geography"),
    # ── Regulations ────────────────────────────────────────────────────────
    ("gdpr",            "GDPR",             "Regulation"),
    ("ai act",          "EU AI Act",        "Regulation"),
    ("dora",            "DORA",             "Regulation"),
    ("nis2",            "NIS2 Directive",   "Regulation"),
    ("mifid",           "MiFID II",         "Regulation"),
    ("basel",           "Basel III",        "Regulation"),
    ("solvency",        "Solvency II",      "Regulation"),
    ("sanctions",       "Economic Sanctions","Regulation"),
    ("antitrust",       "Antitrust Regulation","Regulation"),
]

# Ticker → Company name (used for market data cross-referencing)
TICKER_TO_COMPANY: Dict[str, str] = {
    "AAPL":  "Apple",           "MSFT":  "Microsoft",
    "AMZN":  "Amazon",          "GOOGL": "Alphabet",
    "META":  "Meta",            "NVDA":  "NVIDIA",
    "TSLA":  "Tesla",           "005930.KS": "Samsung",
    "TSM":   "TSMC",            "INTC":  "Intel",
    "AMD":   "AMD",             "QCOM":  "Qualcomm",
    "ASML":  "ASML",            "SAP":   "SAP",
    "CAP.PA":"Capgemini",       "ATO.PA":"Atos",
    "SOP.PA":"Sopra Steria",    "IBM":   "IBM Consulting",
    "ACN":   "Accenture",       "JPM":   "JPMorgan",
    "GS":    "Goldman Sachs",   "BNP.PA":"BNP Paribas",
    "GLE.PA":"Société Générale","ACA.PA":"Crédit Agricole",
    "CS.PA": "AXA",             "MC.PA": "LVMH",
    "TTE.PA":"TotalEnergies",   "ORA.PA":"Orange",
    "AIR.PA":"Airbus",          "RNO.PA":"Renault",
    "STLAM": "Stellantis",      "EDF.PA":"EDF",
    "ENGI.PA":"ENGIE",          "HO.PA": "Thales",
    "DSY.PA":"Dassault Systèmes","ALO.PA":"Alstom",
    "SAN.PA":"Sanofi",          "AZN":   "AstraZeneca",
    "PFE":   "Pfizer",          "NVS":   "Novartis",
    "SIE.DE":"Siemens",         "VOW3.DE":"Volkswagen",
    # Sector ETFs
    "XLF":  "Financial Services", "XLK": "IT Services",
    "XLE":  "Energy & Utilities", "XLV": "Healthcare & Life Sciences",
    "XLI":  "Industry & Manufacturing", "XLY": "Retail & Consumer Goods",
    "XLC":  "Telecommunications", "XLU": "Energy & Utilities",
    "IYR":  "Real Estate & Construction",
    "HACK": "Cybersecurity Spending Index",
}

# GDELT CAMEO root codes → financial/economic event filter
# https://www.gdeltproject.org/data/lookups/CAMEO.eventcodes.txt
# We keep only codes with material market impact
RELEVANT_CAMEO_ROOTS: Set[str] = {
    "01",  # MAKE PUBLIC STATEMENT
    "02",  # APPEAL
    "03",  # EXPRESS INTENT TO COOPERATE
    "04",  # CONSULT
    "06",  # COOPERATE ECONOMICALLY
    "08",  # YIELD
    "09",  # INVESTIGATE
    "10",  # DEMAND
    "11",  # DISAPPROVE
    "12",  # REJECT
    "13",  # THREATEN
    "14",  # PROTEST
    "15",  # EXHIBIT FORCE POSTURE
    "17",  # COERCE
    "18",  # ASSAULT
    "19",  # FIGHT
    "20",  # USE UNCONVENTIONAL MASS VIOLENCE
}

# GDELT themes that indicate economic/market relevance
RELEVANT_THEME_PREFIXES: Tuple[str, ...] = (
    "ECON_", "BUSINESS_", "FINANCE_", "MARKET_",
    "TRADE_", "BANK_", "ENERGY_", "OIL_",
    "TECH_", "CYBER_", "REGULATION_", "SANCTION_",
    "CRISIS_", "MERGER_", "IPO_", "INFLATION_",
    "INTEREST_RATE", "CURRENCY_",
)

# ─────────────────────────────────────────────────────────────────────────────
# § 5  REAL WORLD EVENT GENERATOR  (GDELT 2.0)
# ─────────────────────────────────────────────────────────────────────────────

GDELT_API_BASE = "https://api.gdeltproject.org/api/v2"
GDELT_DOC_API  = f"{GDELT_API_BASE}/doc/doc"

_GDELT_TONE_THRESHOLD = -2.0   # Only keep events with negative average tone (market-moving)
_GDELT_MIN_MENTIONS   = 5      # Minimum article mentions to count as a real event


class RealWorldEventGenerator:
    """
    Fetches real historical events from GDELT 2.0 Document API.

    Filters for economic, financial, corporate, and geopolitical events with
    likely market impact. Caches results locally.
    """

    # Queries that reliably surface market-relevant events
    _ECONOMIC_QUERIES: List[Tuple[str, str]] = [
        ("central bank interest rate decision",        "MacroIndicator"),
        ("corporate earnings quarterly results",       "Company"),
        ("merger acquisition deal billion",            "Company"),
        ("trade war tariff sanctions economic",        "Regulation"),
        ("oil price energy crisis supply",             "MacroIndicator"),
        ("stock market crash correction recession",    "MacroIndicator"),
        ("inflation consumer prices eurozone",         "MacroIndicator"),
        ("banking crisis financial stability",         "Banking & Finance"),
        ("technology regulation antitrust fine",       "Regulation"),
        ("geopolitical conflict supply chain impact",  "Geography"),
        ("IPO listing stock exchange",                 "Company"),
        ("cybersecurity breach data leak",             "MacroIndicator"),
        ("climate regulation green energy transition", "Regulation"),
        ("semiconductor chip shortage supply",         "Semiconductors"),
        ("AI artificial intelligence investment",      "MacroIndicator"),
        ("currency exchange rate devaluation",         "MacroIndicator"),
        ("government stimulus fiscal policy",          "MacroIndicator"),
        ("debt default sovereign bond yield",          "MacroIndicator"),
        ("company layoffs restructuring",              "Company"),
        ("pharmaceutical FDA approval drug",           "Healthcare & Life Sciences"),
    ]

    def __init__(
        self,
        cache_dir: Path,
        ttl_hours: int = 24,
        max_events_per_query: int = 250,
        retry_delay: float = 1.5,
        session: Optional[requests.Session] = None,
    ):
        self.cache_dir = Path(cache_dir) / "gdelt"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours
        self.max_events_per_query = max_events_per_query
        self.retry_delay = retry_delay
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": "GNNPipeline/1.0 (research)"})

    # ── Low-level GDELT fetcher ────────────────────────────────────────────────

    def _fetch_gdelt(
        self,
        query: str,
        start_date: str,
        end_date: str,
        max_records: int = 250,
    ) -> List[Dict[str, Any]]:
        """
        Call GDELT Doc API and return list of article records.
        Response is cached as gzip JSON.
        """
        params = {
            "query":      query,
            "mode":       "artlist",
            "maxrecords": str(min(max_records, 250)),
            "startdatetime": _date_to_gdelt(start_date),
            "enddatetime":   _date_to_gdelt(end_date),
            "format":     "json",
            "sort":       "toneasc",  # most negative tone first (market-moving)
        }

        cache_path = self.cache_dir / f"{_cache_key(GDELT_DOC_API, params)}.json.gz"
        if _is_fresh(cache_path, self.ttl_hours):
            with gzip.open(cache_path, "rt", encoding="utf-8") as f:
                return json.load(f)

        try:
            resp = self._session.get(GDELT_DOC_API, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            articles = data.get("articles") or []
        except Exception as exc:
            logger.warning("GDELT fetch failed (%s) for query=%r — returning []", exc, query[:60])
            return []

        with gzip.open(cache_path, "wt", encoding="utf-8") as f:
            json.dump(articles, f)

        time.sleep(self.retry_delay)   # respect GDELT rate limits
        return articles

    # ── Tone & mention filters ─────────────────────────────────────────────────

    @staticmethod
    def _parse_tone(article: Dict) -> float:
        """Extract average tone from GDELT article dict."""
        try:
            return float(article.get("tone", {}).get("tone", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _extract_event_date(article: Dict) -> Optional[str]:
        """Parse seendate → ISO date string."""
        raw = article.get("seendate", "")
        if not raw:
            return None
        try:
            dt = datetime.strptime(str(raw)[:8], "%Y%m%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _article_to_event(article: Dict, category: str) -> Optional[Dict[str, Any]]:
        """Convert a GDELT article dict to our internal event record."""
        title  = article.get("title", "").strip()
        url    = article.get("url", "")
        source = article.get("domain", "")
        date   = RealWorldEventGenerator._extract_event_date(article)
        tone   = RealWorldEventGenerator._parse_tone(article)

        if not title or not date:
            return None

        # Compute a rough impact magnitude from tone (negative tone → higher impact)
        impact = min(abs(tone) / 10.0, 1.0)

        return {
            "title":          title,
            "url":            url,
            "source_domain":  source,
            "event_date":     date,
            "tone":           tone,
            "impact_score":   round(impact, 4),
            "gdelt_category": category,
            "description":    title,
        }

    # ── Public interface ───────────────────────────────────────────────────────

    def fetch_events(
        self,
        start_date: str,
        end_date: str,
        max_events: int = 10_000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch up to `max_events` real-world events from GDELT between
        start_date and end_date (inclusive, YYYY-MM-DD format).

        Queries are chunked into ~30-day windows to comply with GDELT
        pagination limits and maximize event diversity.
        """
        all_events: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()
        date_windows = list(_date_windows(start_date, end_date, window_days=30))

        per_query_budget = max(
            1,
            max_events // (len(self._ECONOMIC_QUERIES) * max(len(date_windows), 1))
        )
        per_query_budget = min(per_query_budget, 250)

        logger.info(
            "EventGenerator: fetching events %s → %s  (%d windows × %d queries, budget=%d/query)",
            start_date, end_date, len(date_windows), len(self._ECONOMIC_QUERIES), per_query_budget,
        )

        for win_start, win_end in date_windows:
            if len(all_events) >= max_events:
                break
            for query_text, category in self._ECONOMIC_QUERIES:
                if len(all_events) >= max_events:
                    break
                articles = self._fetch_gdelt(query_text, win_start, win_end, per_query_budget)
                for article in articles:
                    if len(all_events) >= max_events:
                        break
                    url = article.get("url", "")
                    if url in seen_urls:
                        continue
                    tone = self._parse_tone(article)
                    if tone > _GDELT_TONE_THRESHOLD:
                        continue  # too positive / not market-moving
                    ev = self._article_to_event(article, category)
                    if ev is None:
                        continue
                    all_events.append(ev)
                    seen_urls.add(url)

        logger.info("EventGenerator: collected %d unique real-world events", len(all_events))
        return all_events


# ─────────────────────────────────────────────────────────────────────────────
# § 6  MARKET DATA FETCHER  (yfinance)
# ─────────────────────────────────────────────────────────────────────────────

_PRICE_CACHE_TTL_DAYS = 7
_MAIN_TICKERS = list(TICKER_TO_COMPANY.keys())


class MarketDataFetcher:
    """
    Fetches historical OHLCV data via yfinance and computes per-event
    market statistics:
      - 1-day return after event
      - 7-day return after event
      - 5-day post-event volatility (std of daily returns)
    """

    def __init__(self, cache_dir: Path, ttl_days: int = _PRICE_CACHE_TTL_DAYS):
        self.cache_dir = Path(cache_dir) / "yfinance"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self._price_cache: Dict[str, Any] = {}   # ticker → DataFrame (in-memory)

    # ── Data loading ───────────────────────────────────────────────────────────

    def _load_ticker(self, ticker: str, start: str, end: str) -> Optional[Any]:
        """
        Return a pandas DataFrame with daily Close prices for `ticker`.
        Uses on-disk Parquet cache; fetches from yfinance on cache miss.
        """
        import pandas as pd

        cache_key = f"{slugify(ticker)}_{start}_{end}"
        cache_path = self.cache_dir / f"{cache_key}.parquet"

        if ticker in self._price_cache:
            return self._price_cache[ticker]

        if _is_fresh(cache_path, self.ttl_days * 24):
            try:
                df = pd.read_parquet(cache_path)
                self._price_cache[ticker] = df
                return df
            except Exception:
                pass

        try:
            import yfinance as yf
            df = yf.download(
                ticker,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if df is None or df.empty:
                return None
            df = df[["Close"]].rename(columns={"Close": "close"})
            df.index = pd.to_datetime(df.index)
            df.to_parquet(cache_path)
            self._price_cache[ticker] = df
            logger.debug("MarketDataFetcher: downloaded %s (%d rows)", ticker, len(df))
            return df
        except Exception as exc:
            logger.warning("MarketDataFetcher: failed to download %s — %s", ticker, exc)
            return None

    def bulk_load(self, start_date: str, end_date: str, tickers: Optional[List[str]] = None) -> None:
        """Pre-load price data for all tickers; call once before compute_metrics."""
        tickers = tickers or _MAIN_TICKERS
        # Add a 14-day post-window buffer so we can compute 7-day returns at end_date
        end_buf = (
            datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=14)
        ).strftime("%Y-%m-%d")
        for ticker in tickers:
            self._load_ticker(ticker, start_date, end_buf)
        logger.info("MarketDataFetcher: loaded price data for %d tickers", len(tickers))

    # ── Per-event metrics ──────────────────────────────────────────────────────

    def compute_metrics(
        self,
        ticker: str,
        event_date: str,
    ) -> Dict[str, Optional[float]]:
        """
        For a given ticker and event date, compute:
          return_1d    : (close[T+1] - close[T]) / close[T]
          return_7d    : (close[T+5] - close[T]) / close[T]   (≈ 7 calendar days)
          volatility_5d: std(daily returns[T+1 .. T+5])
        Returns None for each metric if price data is unavailable.
        """
        import pandas as pd

        df = self._price_cache.get(ticker)
        if df is None or df.empty:
            return {"return_1d": None, "return_7d": None, "volatility_5d": None}

        try:
            ev_dt = pd.Timestamp(event_date)
            # Find the next available trading day on or after event_date
            future = df[df.index >= ev_dt]
            if len(future) < 2:
                return {"return_1d": None, "return_7d": None, "volatility_5d": None}

            p0 = float(future["close"].iloc[0])
            p1 = float(future["close"].iloc[1]) if len(future) > 1 else None
            p5 = float(future["close"].iloc[5]) if len(future) > 5 else None

            r1d = (p1 - p0) / p0 if p1 is not None and p0 > 0 else None
            r7d = (p5 - p0) / p0 if p5 is not None and p0 > 0 else None

            if len(future) >= 6:
                daily_returns = future["close"].pct_change().iloc[1:6].dropna()
                vol = float(daily_returns.std()) if len(daily_returns) >= 2 else None
            else:
                vol = None

            return {
                "return_1d":     round(r1d, 6)  if r1d  is not None else None,
                "return_7d":     round(r7d, 6)  if r7d  is not None else None,
                "volatility_5d": round(vol, 6)  if vol  is not None else None,
            }
        except Exception as exc:
            logger.debug("compute_metrics failed for %s @ %s: %s", ticker, event_date, exc)
            return {"return_1d": None, "return_7d": None, "volatility_5d": None}


# ─────────────────────────────────────────────────────────────────────────────
# § 7  EVENT ENTITY MAPPER  (deterministic, rule-based)
# ─────────────────────────────────────────────────────────────────────────────

class EventEntityMapper:
    """
    Maps a raw event text to a ranked list of relevant entities using
    keyword-based rules.  No LLM calls required.

    Deterministic: same input always produces same output.
    """

    def map(
        self,
        event_text: str,
        max_entities: int = 8,
    ) -> List[Tuple[str, str]]:
        """
        Args:
            event_text:   event title + description (concatenated, lowercase)
            max_entities: cap on number of linked entities

        Returns list of (entity_name, entity_type) tuples.
        Higher-priority rules appear first (order of ENTITY_KEYWORD_RULES).
        """
        text = event_text.lower()
        seen: Set[str] = set()
        matched: List[Tuple[str, str]] = []

        for keyword, entity_name, entity_type in ENTITY_KEYWORD_RULES:
            if len(matched) >= max_entities:
                break
            if keyword in text and entity_name not in seen:
                matched.append((entity_name, entity_type))
                seen.add(entity_name)

        # Always add Talan as an affected company (it's the focal node of the KG)
        if "Talan" not in seen:
            matched.append(("Talan", "Company"))

        return matched[:max_entities]

    def map_tickers(self, event_text: str) -> List[str]:
        """Return a list of relevant tickers for market data fetching."""
        text = event_text.lower()
        tickers = []
        for ticker, name in TICKER_TO_COMPANY.items():
            if name.lower() in text or ticker.lower() in text:
                tickers.append(ticker)
        # Include major sector ETFs for macro events
        for kw in ("inflation", "rate", "oil", "market", "economy"):
            if kw in text:
                tickers.extend(["XLF", "XLK", "XLE"])
                break
        return list(dict.fromkeys(tickers))[:10]  # dedup, max 10


# ─────────────────────────────────────────────────────────────────────────────
# § 8  GRAPH BUILDER
# ─────────────────────────────────────────────────────────────────────────────

class GraphBuilder:
    """
    Converts a list of enriched event records into GNNNode + GNNEdge lists
    compatible with the existing pipeline schema.

    One graph is built per dataset (all events share nodes; edges carry timestamps).
    """

    def __init__(self):
        self._nodes: List[GNNNode] = []
        self._edges: List[GNNEdge] = []
        self._slug_to_id: Dict[str, int] = {}
        self._next_id: int = 0
        self._edge_keys: Set[Tuple[int, int, str]] = set()

    # ── Node management ────────────────────────────────────────────────────────

    def _get_or_create_node(
        self,
        name: str,
        gnn_type: str,
        props: Optional[Dict] = None,
        source: str = "realworld",
    ) -> GNNNode:
        slug = slugify(name)
        if slug in self._slug_to_id:
            node = self._nodes[self._slug_to_id[slug]]
            # Merge props if richer data available
            if props:
                node.props.update({k: v for k, v in props.items() if v is not None})
            return node

        node = GNNNode(
            gnn_id=self._next_id,
            gnn_type=gnn_type,
            name=name,
            slug=slug,
            props=props or {},
            source=source,
        )
        self._nodes.append(node)
        self._slug_to_id[slug] = self._next_id
        self._next_id += 1
        return node

    def _add_edge(
        self,
        src_id: int,
        dst_id: int,
        edge_type: str,
        weight: float,
        timestamp: Optional[str] = None,
        source_system: str = "realworld",
    ) -> None:
        key = (src_id, dst_id, edge_type)
        if key in self._edge_keys:
            return
        self._edges.append(GNNEdge(
            source_id=src_id,
            target_id=dst_id,
            gnn_type=edge_type,
            weight=round(weight, 6),
            timestamp=timestamp,
            source_system=source_system,
        ))
        self._edge_keys.add(key)

    # ── Ingestion ──────────────────────────────────────────────────────────────

    def ingest_event(
        self,
        event: Dict[str, Any],
        entities: List[Tuple[str, str]],
        market_metrics: Dict[str, Dict[str, Optional[float]]],
    ) -> GNNNode:
        """
        Ingest one event into the graph.

        Creates:
          - An Event node
          - Entity nodes (Company, Sector, MacroIndicator, Geography, Regulation)
          - IMPACTS edges: Event → Entity
          - INFLUENCES edges: MacroIndicator → Sector
          - OPERATES_IN edges: Company → Geography
          - BELONGS_TO_SECTOR edges: Company → Sector

        Args:
            event:          raw event dict (from RealWorldEventGenerator)
            entities:       [(entity_name, entity_type), ...] from EventEntityMapper
            market_metrics: {ticker: {return_1d, return_7d, volatility_5d}}

        Returns the Event GNNNode.
        """
        impact = float(event.get("impact_score", 0.5))
        ts     = event.get("event_date")

        # ── Create Event node ──────────────────────────────────────────────
        event_node = self._get_or_create_node(
            name=event["title"][:120],
            gnn_type="Event",
            props={
                "description":    event.get("description", ""),
                "event_date":     ts,
                "tone":           event.get("tone", 0.0),
                "impact_score":   impact,
                "source_domain":  event.get("source_domain", ""),
                "gdelt_category": event.get("gdelt_category", ""),
                "url":            event.get("url", ""),
            },
            source="gdelt",
        )
        event_node.impact_score = max(event_node.impact_score, impact)

        # ── Build entity nodes and edges ───────────────────────────────────
        entity_nodes: List[GNNNode] = []
        sectors_in_event: List[GNNNode]       = []
        geos_in_event: List[GNNNode]          = []
        companies_in_event: List[GNNNode]     = []
        macros_in_event: List[GNNNode]        = []

        for ent_name, ent_type in entities:
            ent_node = self._get_or_create_node(ent_name, ent_type)
            entity_nodes.append(ent_node)

            # Derive edge weight from market data if available
            weight = impact
            if ent_type == "Company":
                ticker = _company_to_ticker(ent_name)
                if ticker and ticker in market_metrics:
                    m = market_metrics[ticker]
                    vol = m.get("volatility_5d")
                    if vol is not None:
                        weight = min(0.3 + abs(vol) * 5, 1.0)

            self._add_edge(
                src_id=event_node.gnn_id,
                dst_id=ent_node.gnn_id,
                edge_type="IMPACTS",
                weight=weight,
                timestamp=ts,
            )

            # Categorise for structural edges below
            if ent_type == "Sector":
                sectors_in_event.append(ent_node)
            elif ent_type == "Geography":
                geos_in_event.append(ent_node)
            elif ent_type in ("Company", "Competitor"):
                companies_in_event.append(ent_node)
            elif ent_type == "MacroIndicator":
                macros_in_event.append(ent_node)

        # ── MacroIndicator → Sector (INFLUENCES) ──────────────────────────
        for macro in macros_in_event:
            for sector in sectors_in_event:
                self._add_edge(
                    macro.gnn_id, sector.gnn_id,
                    "INFLUENCES", weight=impact, timestamp=ts,
                )

        # ── Company → Sector (BELONGS_TO_SECTOR) ──────────────────────────
        for company in companies_in_event:
            for sector in sectors_in_event:
                self._add_edge(
                    company.gnn_id, sector.gnn_id,
                    "BELONGS_TO_SECTOR", weight=0.8, timestamp=ts,
                )

        # ── Company → Geography (OPERATES_IN) ─────────────────────────────
        for company in companies_in_event:
            for geo in geos_in_event:
                self._add_edge(
                    company.gnn_id, geo.gnn_id,
                    "OPERATES_IN", weight=0.85, timestamp=ts,
                )

        # ── MacroIndicator → Sector (macro affects sector) ────────────────
        for macro in macros_in_event:
            for sector in sectors_in_event:
                self._add_edge(
                    macro.gnn_id, sector.gnn_id,
                    "AFFECTS", weight=impact, timestamp=ts,
                )

        return event_node

    # ── Degree computation ─────────────────────────────────────────────────────

    def finalize_degrees(self) -> None:
        """Update each node's degree based on in-edges."""
        counter: Dict[int, int] = {}
        for edge in self._edges:
            counter[edge.target_id] = counter.get(edge.target_id, 0) + 1
        for node in self._nodes:
            node.degree = counter.get(node.gnn_id, 0)

    # ── Results ────────────────────────────────────────────────────────────────

    @property
    def nodes(self) -> List[GNNNode]:
        return self._nodes

    @property
    def edges(self) -> List[GNNEdge]:
        return self._edges

    @property
    def slug_to_id(self) -> Dict[str, int]:
        return self._slug_to_id


# ─────────────────────────────────────────────────────────────────────────────
# § 9  FEATURE BUILDER  (same logic as existing pipeline)
# ─────────────────────────────────────────────────────────────────────────────

class FeatureBuilder:
    """
    Builds float32 [N × 396] feature matrix:
      [0:10]   one-hot node type
      [10:11]  in-degree normalized
      [11:12]  impact_score normalized
      [12:396] sentence-transformer embedding (all-MiniLM-L6-v2)
    """

    def __init__(self):
        self._embedder = None

    def _load_embedder(self):
        if self._embedder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("FeatureBuilder: sentence-transformer loaded")
        except Exception as exc:
            logger.warning("FeatureBuilder: sentence-transformers unavailable (%s) → zeros", exc)

    def _embed(self, texts: List[str]) -> np.ndarray:
        self._load_embedder()
        if self._embedder is not None:
            try:
                vecs = self._embedder.encode(texts, show_progress_bar=False, batch_size=64)
                return vecs.astype(np.float32)
            except Exception as exc:
                logger.warning("FeatureBuilder: encode failed (%s) → zeros", exc)
        return np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)

    def build(self, nodes: List[GNNNode]) -> np.ndarray:
        n = len(nodes)
        matrix = np.zeros((n, FEATURE_DIM), dtype=np.float32)

        type_index = {t: i for i, t in enumerate(GNN_NODE_TYPES)}
        for i, node in enumerate(nodes):
            idx = type_index.get(node.gnn_type, 0)
            matrix[i, idx] = 1.0

        degrees = _normalize([float(nd.degree) for nd in nodes])
        impacts = _normalize([float(nd.impact_score) for nd in nodes])
        for i, (d, s) in enumerate(zip(degrees, impacts)):
            matrix[i, len(GNN_NODE_TYPES)]     = d
            matrix[i, len(GNN_NODE_TYPES) + 1] = s

        texts = [
            f"{nd.gnn_type}: {nd.name}. "
            f"{nd.props.get('description', '') or nd.props.get('gdelt_category', '')}"
            for nd in nodes
        ]
        emb_start = len(GNN_NODE_TYPES) + STRUCTURAL_DIM
        matrix[:, emb_start:] = self._embed(texts)

        logger.info("FeatureBuilder: built %d × %d matrix", n, FEATURE_DIM)
        return matrix


# ─────────────────────────────────────────────────────────────────────────────
# § 10  DATASET EXPORTER  (same format as existing pipeline)
# ─────────────────────────────────────────────────────────────────────────────

class DatasetExporter:
    """Writes nodes.csv, edges.csv, node_features.npy, metadata.json."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        features: np.ndarray,
        extra_meta: Optional[Dict] = None,
    ) -> Dict[str, Path]:
        paths = {
            "nodes":    self._write_nodes(nodes),
            "edges":    self._write_edges(edges),
            "features": self._write_features(features),
            "metadata": self._write_metadata(nodes, edges, features, extra_meta),
        }
        logger.info("DatasetExporter: written to %s", self.output_dir)
        return paths

    def _write_nodes(self, nodes: List[GNNNode]) -> Path:
        path = self.output_dir / "nodes.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "type", "name", "slug", "source"])
            writer.writeheader()
            for n in nodes:
                writer.writerow({"id": n.gnn_id, "type": n.gnn_type,
                                  "name": n.name, "slug": n.slug, "source": n.source})
        return path

    def _write_edges(self, edges: List[GNNEdge]) -> Path:
        path = self.output_dir / "edges.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["source", "target", "type", "weight", "timestamp", "source_system"])
            writer.writeheader()
            for e in edges:
                writer.writerow({
                    "source": e.source_id, "target": e.target_id,
                    "type": e.gnn_type, "weight": round(e.weight, 6),
                    "timestamp": e.timestamp or "", "source_system": e.source_system,
                })
        return path

    def _write_features(self, features: np.ndarray) -> Path:
        path = self.output_dir / "node_features.npy"
        np.save(str(path), features)
        return path

    def _write_metadata(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        features: np.ndarray,
        extra: Optional[Dict],
    ) -> Path:
        type_counts:      Dict[str, int] = {}
        edge_type_counts: Dict[str, int] = {}
        for n in nodes:
            type_counts[n.gnn_type] = type_counts.get(n.gnn_type, 0) + 1
        for e in edges:
            edge_type_counts[e.gnn_type] = edge_type_counts.get(e.gnn_type, 0) + 1

        meta: Dict[str, Any] = {
            "generated_at":    datetime.now(timezone.utc).isoformat(),
            "generator":       "gnn_realworld_dataset_generator.py",
            "data_sources":    ["GDELT 2.0 Doc API", "Yahoo Finance (yfinance)"],
            "num_nodes":        len(nodes),
            "num_edges":        len(edges),
            "feature_dim":      int(features.shape[1]),
            "node_types":       GNN_NODE_TYPES,
            "edge_types":       GNN_EDGE_TYPES,
            "node_type_counts": type_counts,
            "edge_type_counts": edge_type_counts,
            "feature_layout": {
                "0_to_9":   "one-hot node type (10-d)",
                "10":       "in-degree centrality normalized",
                "11":       "impact/risk score normalized",
                "12_to_395":"sentence-transformer embedding (384-d, all-MiniLM-L6-v2)",
            },
        }
        if extra:
            meta.update(extra)

        path = self.output_dir / "metadata.json"
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return path


# ─────────────────────────────────────────────────────────────────────────────
# § 11  PYTORCH GEOMETRIC CONVERTER  (same as existing pipeline)
# ─────────────────────────────────────────────────────────────────────────────

class PyGConverter:
    """Converts flat dataset to torch_geometric.data.HeteroData."""

    def convert(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        features: np.ndarray,
    ) -> Optional[Any]:
        try:
            import torch
            from torch_geometric.data import HeteroData
        except ImportError:
            logger.warning("PyGConverter: torch_geometric not installed — skipping")
            return None

        data = HeteroData()
        type_to_global: Dict[str, List[int]] = {t: [] for t in GNN_NODE_TYPES}
        gnn_id_to_local: Dict[int, int] = {}

        for node in nodes:
            local = len(type_to_global[node.gnn_type])
            type_to_global[node.gnn_type].append(node.gnn_id)
            gnn_id_to_local[node.gnn_id] = local

        for ntype in GNN_NODE_TYPES:
            gids = type_to_global[ntype]
            if not gids:
                import torch
                data[ntype].x = torch.zeros((0, FEATURE_DIM), dtype=torch.float32)
                data[ntype].node_id = []
                continue
            import torch
            data[ntype].x = torch.tensor(features[gids], dtype=torch.float32)
            data[ntype].node_id = gids

        id_to_type = {n.gnn_id: n.gnn_type for n in nodes}
        buckets: Dict[Tuple[str, str, str], Tuple[List, List, List]] = {}
        now = datetime.now(timezone.utc)

        for edge in edges:
            st = id_to_type.get(edge.source_id)
            dt = id_to_type.get(edge.target_id)
            if st is None or dt is None:
                continue
            sl = gnn_id_to_local.get(edge.source_id)
            dl = gnn_id_to_local.get(edge.target_id)
            if sl is None or dl is None:
                continue
            ts_norm = 0.5
            if edge.timestamp:
                try:
                    ts = datetime.fromisoformat(edge.timestamp.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts_norm = min(max((now - ts).total_seconds() / (365 * 86400), 0.0), 1.0)
                except Exception:
                    pass
            triplet = (st, edge.gnn_type, dt)
            if triplet not in buckets:
                buckets[triplet] = ([], [], [])
            s, d, a = buckets[triplet]
            s.append(sl); d.append(dl); a.append([edge.weight, ts_norm])

        import torch
        for (st, et, dt), (s, d, a) in buckets.items():
            data[st, et, dt].edge_index = torch.tensor([s, d], dtype=torch.long)
            data[st, et, dt].edge_attr  = torch.tensor(a,      dtype=torch.float32)

        logger.info("PyGConverter: HeteroData built — %d edge triplets", len(buckets))
        return data


# ─────────────────────────────────────────────────────────────────────────────
# § 12  REAL-WORLD DATASET PIPELINE  (main orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

class RealWorldDatasetPipeline:
    """
    Orchestrates the full real-world GNN dataset generation pipeline.

    Args:
        output_dir:   where to write nodes.csv, edges.csv, *.npy, metadata.json
        cache_dir:    directory for GDELT + yfinance caches
        start_date:   earliest event date, YYYY-MM-DD
        end_date:     latest event date, YYYY-MM-DD (default: today)
        max_events:   maximum number of GDELT events to ingest
        skip_pyg:     skip PyTorch Geometric conversion (faster for export-only runs)
        tickers:      override list of tickers for market data (default: _MAIN_TICKERS)
        gdelt_ttl_h:  GDELT cache TTL in hours
        price_ttl_d:  yfinance cache TTL in days
    """

    def __init__(
        self,
        output_dir: str = "./gnn_realworld_dataset",
        cache_dir:  str = "./.cache",
        start_date: str = "2020-01-01",
        end_date:   Optional[str] = None,
        max_events: int = 10_000,
        skip_pyg:   bool = False,
        tickers:    Optional[List[str]] = None,
        gdelt_ttl_h: int = 24,
        price_ttl_d: int = 7,
    ):
        self.output_dir  = Path(output_dir)
        self.cache_dir   = Path(cache_dir)
        self.start_date  = start_date
        self.end_date    = end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.max_events  = max_events
        self.skip_pyg    = skip_pyg
        self.tickers     = tickers or _MAIN_TICKERS

        self._event_gen  = RealWorldEventGenerator(
            cache_dir=self.cache_dir, ttl_hours=gdelt_ttl_h)
        self._market     = MarketDataFetcher(
            cache_dir=self.cache_dir, ttl_days=price_ttl_d)
        self._mapper     = EventEntityMapper()
        self._builder    = GraphBuilder()
        self._feat       = FeatureBuilder()
        self._exporter   = DatasetExporter(self.output_dir)
        self._pyg        = PyGConverter()

        # Populated during run()
        self.nodes:    List[GNNNode]       = []
        self.edges:    List[GNNEdge]       = []
        self.features: Optional[np.ndarray] = None
        self.pyg_data: Optional[Any]        = None
        self._events:  List[Dict]           = []

    # ── Stage runners ──────────────────────────────────────────────────────────

    def _stage_fetch_events(self) -> None:
        logger.info("Stage 1/6 — Fetching real-world events from GDELT …")
        self._events = self._event_gen.fetch_events(
            self.start_date, self.end_date, self.max_events)
        logger.info("Stage 1/6 — %d events fetched", len(self._events))

    def _stage_load_market_data(self) -> None:
        logger.info("Stage 2/6 — Loading market data (yfinance) …")
        self._market.bulk_load(self.start_date, self.end_date, self.tickers)
        logger.info("Stage 2/6 — Market data loaded")

    def _stage_build_graph(self) -> None:
        logger.info("Stage 3/6 — Building graph from %d events …", len(self._events))
        for i, event in enumerate(self._events):
            if i % 500 == 0:
                logger.info("  … ingesting event %d / %d", i, len(self._events))

            # Entity mapping
            text = f"{event.get('title','')} {event.get('description','')}"
            entities = self._mapper.map(text, max_entities=8)

            # Market data for relevant tickers
            relevant_tickers = self._mapper.map_tickers(text)
            market_metrics: Dict[str, Dict] = {}
            for ticker in relevant_tickers:
                market_metrics[ticker] = self._market.compute_metrics(
                    ticker, event["event_date"])

            # Ingest into graph
            self._builder.ingest_event(event, entities, market_metrics)

        self._builder.finalize_degrees()
        self.nodes = self._builder.nodes
        self.edges = self._builder.edges
        logger.info("Stage 3/6 — Graph: %d nodes, %d edges", len(self.nodes), len(self.edges))

    def _stage_features(self) -> None:
        logger.info("Stage 4/6 — Building feature matrix …")
        self.features = self._feat.build(self.nodes)
        logger.info("Stage 4/6 — Features: %s", self.features.shape)

    def _stage_export(self) -> Dict[str, Path]:
        logger.info("Stage 5/6 — Exporting dataset …")
        extra_meta = {
            "start_date": self.start_date,
            "end_date":   self.end_date,
            "num_events": len(self._events),
            "tickers":    self.tickers,
        }
        return self._exporter.export(self.nodes, self.edges, self.features, extra_meta)

    def _stage_pyg(self) -> None:
        logger.info("Stage 6/6 — Converting to PyG HeteroData …")
        self.pyg_data = self._pyg.convert(self.nodes, self.edges, self.features)

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """
        Execute all pipeline stages end-to-end.

        Returns:
            {
                "paths":    {name: Path},
                "pyg_data": HeteroData | None,
                "stats":    {...},
                "events":   List[Dict],   # raw GDELT event records
            }
        """
        logger.info("=== RealWorldDatasetPipeline START ===")
        logger.info("    date range : %s → %s", self.start_date, self.end_date)
        logger.info("    max_events : %d", self.max_events)

        self._stage_fetch_events()
        self._stage_load_market_data()
        self._stage_build_graph()
        self._stage_features()
        paths = self._stage_export()
        if not self.skip_pyg:
            self._stage_pyg()

        stats = {
            "num_nodes":       len(self.nodes),
            "num_edges":       len(self.edges),
            "num_events":      len(self._events),
            "feature_dim":     int(self.features.shape[1]) if self.features is not None else 0,
            "node_type_counts": {
                t: sum(1 for n in self.nodes if n.gnn_type == t)
                for t in GNN_NODE_TYPES
            },
            "edge_type_counts": {
                et: sum(1 for e in self.edges if e.gnn_type == et)
                for et in GNN_EDGE_TYPES
            },
        }

        logger.info("=== RealWorldDatasetPipeline END — %d nodes / %d edges ===",
                    len(self.nodes), len(self.edges))

        return {
            "paths":    paths,
            "pyg_data": self.pyg_data,
            "stats":    stats,
            "events":   self._events,
        }

    def push_to_neo4j(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
    ) -> Dict[str, int]:
        """
        Push enriched nodes and edges to Neo4j (MERGE — idempotent).
        Requires the existing gnn_dataset_builder.Neo4jWriter.

        Returns {'nodes': N, 'edges': E}.
        """
        try:
            from gnn_dataset_builder import Neo4jWriter  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "gnn_dataset_builder.py must be on the Python path to use push_to_neo4j"
            ) from exc

        if not self.nodes:
            raise RuntimeError("Pipeline has not been run yet — call .run() first.")

        writer = Neo4jWriter(neo4j_uri, neo4j_user, neo4j_password)
        try:
            counts = writer.push_all(self.nodes, self.edges)
        finally:
            writer.close()

        logger.info("push_to_neo4j: %d nodes + %d edges written", counts["nodes"], counts["edges"])
        return counts


# ─────────────────────────────────────────────────────────────────────────────
# § 13  CONVENIENCE: LOAD SAVED DATASET  (no Neo4j / no re-fetch)
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(dataset_dir: str) -> Dict[str, Any]:
    """
    Reload a previously exported dataset from disk.

    Returns:
        {
            "nodes": List[GNNNode], "edges": List[GNNEdge],
            "features": np.ndarray, "metadata": dict,
            "pyg_data": HeteroData | None, "slug_to_id": dict
        }
    """
    base = Path(dataset_dir)
    nodes: List[GNNNode] = []
    slug_to_id: Dict[str, int] = {}

    with open(base / "nodes.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n = GNNNode(
                gnn_id=int(row["id"]), gnn_type=row["type"],
                name=row["name"], slug=row["slug"],
                source=row.get("source", "realworld"),
            )
            nodes.append(n)
            slug_to_id[row["slug"]] = n.gnn_id

    edges: List[GNNEdge] = []
    with open(base / "edges.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            edges.append(GNNEdge(
                source_id=int(row["source"]), target_id=int(row["target"]),
                gnn_type=row["type"], weight=float(row["weight"]),
                timestamp=row.get("timestamp") or None,
                source_system=row.get("source_system", "realworld"),
            ))

    features = np.load(str(base / "node_features.npy"))
    metadata = json.loads((base / "metadata.json").read_text(encoding="utf-8"))
    pyg_data = PyGConverter().convert(nodes, edges, features)

    logger.info("load_dataset: %d nodes, %d edges from %s", len(nodes), len(edges), base)
    return {
        "nodes": nodes, "edges": edges, "features": features,
        "metadata": metadata, "pyg_data": pyg_data, "slug_to_id": slug_to_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# § 14  HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _date_to_gdelt(date_str: str) -> str:
    """Convert YYYY-MM-DD to GDELT datetime format YYYYMMDDHHMMSS."""
    return date_str.replace("-", "") + "000000"


def _date_windows(
    start: str, end: str, window_days: int = 30
) -> Iterator[Tuple[str, str]]:
    """Yield (window_start, window_end) tuples covering [start, end]."""
    cur = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while cur < end_dt:
        win_end = min(cur + timedelta(days=window_days - 1), end_dt)
        yield cur.strftime("%Y-%m-%d"), win_end.strftime("%Y-%m-%d")
        cur = win_end + timedelta(days=1)


_COMPANY_TO_TICKER: Dict[str, str] = {v: k for k, v in TICKER_TO_COMPANY.items()
                                        if not k[0].isdigit()}


def _company_to_ticker(company_name: str) -> Optional[str]:
    """Reverse lookup: company name → primary ticker."""
    return _COMPANY_TO_TICKER.get(company_name)


# ─────────────────────────────────────────────────────────────────────────────
# § 15  CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a real-world GNN dataset from GDELT + yfinance."
    )
    parser.add_argument("--output-dir",  default="./gnn_realworld_dataset")
    parser.add_argument("--cache-dir",   default="./.cache")
    parser.add_argument("--start-date",  default="2020-01-01")
    parser.add_argument("--end-date",    default=None)
    parser.add_argument("--max-events",  type=int, default=10_000)
    parser.add_argument("--skip-pyg",    action="store_true")
    parser.add_argument("--push-neo4j",  action="store_true",
                        help="Push enriched nodes/edges to Neo4j after generation")
    parser.add_argument("--neo4j-uri",   default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user",  default="neo4j")
    parser.add_argument("--neo4j-password", default="talan_neo4j")
    args = parser.parse_args()

    pipeline = RealWorldDatasetPipeline(
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        max_events=args.max_events,
        skip_pyg=args.skip_pyg,
    )
    summary = pipeline.run()

    print("\n=== Dataset Summary ===")
    print(json.dumps(summary["stats"], indent=2))
    print("\nOutput files:")
    for name, path in summary["paths"].items():
        print(f"  {name:12s} → {path}")

    if args.push_neo4j:
        counts = pipeline.push_to_neo4j(
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
        )
        print(f"\nNeo4j: pushed {counts['nodes']} nodes + {counts['edges']} edges")