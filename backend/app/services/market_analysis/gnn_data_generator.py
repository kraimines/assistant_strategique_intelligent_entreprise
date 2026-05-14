"""
gnn_causal_patches.py
=====================
Patch-style upgrades to gnn_realworld_dataset_generator.py.

Apply by importing this module and calling patch_pipeline(pipeline) BEFORE
calling pipeline.run(), or replace individual class methods as shown below.

Patches are organized by objective:
  P1 — Causal labeling + negative edge sampling
  P2 — Abnormal returns + volatility regime normalization
  P3 — Temporal decay weighting + snapshot export
  P4 — Dataset balancing (neutral events + hard negatives)
  P5 — Fuzzy entity mapping fallback
  P6 — Causal propagation edges (Event → Macro → Sector → Company)
  P7 — Extended output: edge_labels.csv, causal_map.json, snapshots/

Each patch is a standalone function or drop-in class replacement.
No existing class is deleted; patches extend or monkey-patch them.

Dependencies added (all pip-installable):
  difflib   — stdlib, fuzzy string matching
  pandas    — already required by yfinance
  numpy     — already required
"""

from __future__ import annotations

import csv
import json
import logging
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

# Re-use types from the generator (must be on sys.path)
from gnn_realworld_dataset_generator import (
    GNNEdge,
    GNNNode,
    GNN_NODE_TYPES,
    GNN_EDGE_TYPES,
    TICKER_TO_COMPANY,
    ENTITY_KEYWORD_RULES,
    DatasetExporter,
    MarketDataFetcher,
    RealWorldDatasetPipeline,
    slugify,
    _normalize,
    _company_to_ticker,
    FEATURE_DIM,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# § P1  CAUSAL LABELING  +  NEGATIVE EDGE SAMPLING
# ─────────────────────────────────────────────────────────────────────────────
# Strategy
# --------
# Positive edge  (label=1): Event IMPACTS entity AND |abnormal_return| > threshold
#                           OR event mentioned that entity explicitly (rule-match)
# Negative edge  (label=0): Event is in same sector as company BUT
#                           company was NOT mentioned AND |abnormal_return| < epsilon
#
# The label is stored as edge property "causal_label" (int 0|1).
# A separate edge_labels.csv is written by P7.

_AR_POSITIVE_THRESHOLD = 0.01    # |abnormal return| > 1 % → likely causal
_AR_NEGATIVE_EPSILON   = 0.003   # |abnormal return| < 0.3 % → likely no impact
_HARD_NEG_PER_EVENT    = 3       # hard negatives injected per event


def _causal_label(
    abnormal_return: Optional[float],
    entity_explicitly_mentioned: bool,
) -> int:
    """
    Returns 1 (impact) or 0 (no-impact).

    Rules (in priority order):
      1. Explicitly mentioned  → always 1
      2. |AR| > threshold      → 1
      3. |AR| < epsilon        → 0
      4. AR unknown            → 1 if mentioned, else 0
    """
    if entity_explicitly_mentioned:
        return 1
    if abnormal_return is not None:
        if abs(abnormal_return) >= _AR_POSITIVE_THRESHOLD:
            return 1
        if abs(abnormal_return) < _AR_NEGATIVE_EPSILON:
            return 0
    return 0  # conservative default when no market data


def patch_graph_builder_causal(builder_instance) -> None:
    """
    Monkey-patch GraphBuilder.ingest_event to attach causal_label to each edge.
    Call BEFORE pipeline.run().
    """
    original_ingest = builder_instance.ingest_event

    def patched_ingest(event, entities, market_metrics):
        event_node = original_ingest(event, entities, market_metrics)

        # Attach causal labels to the IMPACTS edges just created
        for edge in builder_instance._edges:
            if edge.source_id != event_node.gnn_id:
                continue
            if edge.gnn_type != "IMPACTS":
                continue
            dst_node = builder_instance._nodes[edge.target_id]
            ticker   = _company_to_ticker(dst_node.name)
            ar       = None
            if ticker and ticker in market_metrics:
                metrics = market_metrics[ticker]
                ar = metrics.get("abnormal_return_1d")   # set by P2
                if ar is None:
                    ar = metrics.get("return_1d")        # fallback

            explicitly = any(
                e[0] == dst_node.name for e in entities
            )
            edge.props = getattr(edge, "props", {}) or {}
            edge.props["causal_label"] = _causal_label(ar, explicitly)

        return event_node

    builder_instance.ingest_event = patched_ingest
    logger.info("P1: causal labeling patch applied to GraphBuilder")


class HardNegativeSampler:
    """
    Injects hard-negative IMPACTS edges (causal_label=0) into the graph.

    Hard negative: event is in sector S, company C is also in sector S,
    but C was NOT in the event's entity list AND |AR| < epsilon.
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def sample(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        events: List[Dict[str, Any]],
        market: MarketDataFetcher,
        negatives_per_event: int = _HARD_NEG_PER_EVENT,
    ) -> List[GNNEdge]:
        """
        For each event node already in the graph, find companies in the same
        sector that are NOT already connected, verify low abnormal return,
        and inject negative edges.

        Returns the list of new GNNEdge objects added (already appended to edges).
        """
        slug_to_node = {n.slug: n for n in nodes}
        id_to_node   = {n.gnn_id: n for n in nodes}

        # Build sector → [company_ids] map
        sector_to_companies: Dict[int, List[int]] = defaultdict(list)
        for e in edges:
            if e.gnn_type == "BELONGS_TO_SECTOR":
                sector_to_companies[e.target_id].append(e.source_id)

        # Find event nodes
        event_nodes = [n for n in nodes if n.gnn_type == "Event"]

        # Existing positive IMPACTS keys
        existing_impacts: Set[Tuple[int, int]] = {
            (e.source_id, e.target_id)
            for e in edges if e.gnn_type == "IMPACTS"
        }

        new_edges: List[GNNEdge] = []
        next_id_start = max((e.source_id for e in edges), default=0) + 10_000

        for ev_node in event_nodes:
            # Find sectors this event already impacts
            impacted_sector_ids: Set[int] = set()
            for e in edges:
                if e.source_id == ev_node.gnn_id and e.gnn_type == "IMPACTS":
                    dst = id_to_node.get(e.target_id)
                    if dst and dst.gnn_type == "Sector":
                        impacted_sector_ids.add(dst.gnn_id)

            # Candidate companies in those sectors NOT already impacted
            candidates: List[int] = []
            for sec_id in impacted_sector_ids:
                for comp_id in sector_to_companies.get(sec_id, []):
                    if (ev_node.gnn_id, comp_id) not in existing_impacts:
                        candidates.append(comp_id)

            self._rng.shuffle(candidates)
            sampled = 0
            for comp_id in candidates:
                if sampled >= negatives_per_event:
                    break
                comp_node = id_to_node.get(comp_id)
                if comp_node is None:
                    continue

                # Verify low abnormal return
                ticker = _company_to_ticker(comp_node.name)
                ev_date = ev_node.props.get("event_date")
                if ticker and ev_date:
                    m = market.compute_metrics(ticker, ev_date)
                    ar = m.get("abnormal_return_1d") or m.get("return_1d") or 0.0
                    if abs(ar) >= _AR_POSITIVE_THRESHOLD:
                        continue   # not a clean negative — skip

                edge = GNNEdge(
                    source_id=ev_node.gnn_id,
                    target_id=comp_id,
                    gnn_type="IMPACTS",
                    weight=0.05,
                    timestamp=ev_node.props.get("event_date"),
                    source_system="hard_negative",
                )
                edge.props = {"causal_label": 0}  # type: ignore[attr-defined]
                edges.append(edge)
                new_edges.append(edge)
                existing_impacts.add((ev_node.gnn_id, comp_id))
                sampled += 1

        logger.info("P1: HardNegativeSampler added %d negative edges", len(new_edges))
        return new_edges


# ─────────────────────────────────────────────────────────────────────────────
# § P2  ABNORMAL RETURNS  +  VOLATILITY REGIME NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────
# Abnormal Return (AR) = stock_return - benchmark_return
# Benchmark: sector ETF return on the same day (preferred) or SPY fallback.
#
# Volatility regime normalization: divide AR by rolling 21-day σ of the stock
# so high-volatility regimes don't dominate the signal.

# Sector → best available ETF ticker for benchmark
SECTOR_ETF_MAP: Dict[str, str] = {
    "Financial Services":          "XLF",
    "Banking & Finance":           "XLF",
    "Insurance":                   "XLF",
    "Energy & Utilities":          "XLE",
    "Telecommunications":          "XLC",
    "IT Services":                 "XLK",
    "Artificial Intelligence":     "XLK",
    "Semiconductors":              "SOXX",
    "Healthcare & Life Sciences":  "XLV",
    "Retail & Consumer Goods":     "XLY",
    "Industry & Manufacturing":    "XLI",
    "Real Estate & Construction":  "IYR",
    "Defense & Aerospace":         "ITA",
    "Transportation & Logistics":  "XTN",
    "Media & Entertainment":       "XLC",
    "Public Sector":               "SPY",   # no direct ETF
    "Cybersecurity Spending Index":"HACK",
}
SPY_TICKER = "SPY"


def patch_market_data_fetcher(fetcher: MarketDataFetcher) -> None:
    """
    Extend MarketDataFetcher.compute_metrics to also return:
      - abnormal_return_1d:   AR(T+1) vs sector ETF
      - abnormal_return_7d:   AR(T+5) vs sector ETF
      - vol_normalized_ar_1d: abnormal_return_1d / rolling_21d_vol

    Patches instance in-place. Call before pipeline._stage_load_market_data().
    """
    import pandas as pd

    # Pre-load benchmark tickers alongside stocks
    orig_bulk_load = fetcher.bulk_load

    def patched_bulk_load(start_date: str, end_date: str, tickers=None):
        orig_bulk_load(start_date, end_date, tickers)
        # Also load sector ETFs + SPY
        benchmark_tickers = list(SECTOR_ETF_MAP.values()) + [SPY_TICKER]
        benchmark_tickers = list(set(benchmark_tickers))
        for tk in benchmark_tickers:
            try:
                fetcher._load_ticker(tk, start_date, end_date)
            except Exception as exc:
                logger.debug("P2: could not load benchmark %s: %s", tk, exc)

    fetcher.bulk_load = patched_bulk_load

    orig_compute = fetcher.compute_metrics

    def patched_compute_metrics(ticker: str, event_date: str) -> Dict[str, Optional[float]]:
        base = orig_compute(ticker, event_date)

        # Identify sector for this company
        company_name = TICKER_TO_COMPANY.get(ticker, "")
        benchmark_tk = SPY_TICKER
        # Walk ENTITY_KEYWORD_RULES to find sector membership
        for _kw, ent_name, ent_type in ENTITY_KEYWORD_RULES:
            if ent_type == "Sector" and company_name.lower() in _kw.lower():
                benchmark_tk = SECTOR_ETF_MAP.get(ent_name, SPY_TICKER)
                break

        def _return_on_date(tk_: str, date_: str, horizon: int) -> Optional[float]:
            df_ = fetcher._price_cache.get(tk_)
            if df_ is None or df_.empty:
                return None
            try:
                ev_dt = pd.Timestamp(date_)
                future = df_[df_.index >= ev_dt]
                if len(future) <= horizon:
                    return None
                p0 = float(future["close"].iloc[0])
                ph = float(future["close"].iloc[horizon])
                return (ph - p0) / p0 if p0 > 0 else None
            except Exception:
                return None

        bench_r1 = _return_on_date(benchmark_tk, event_date, 1)
        bench_r5 = _return_on_date(benchmark_tk, event_date, 5)

        r1 = base.get("return_1d")
        r5 = base.get("return_7d")

        ar1 = (r1 - bench_r1) if (r1 is not None and bench_r1 is not None) else r1
        ar5 = (r5 - bench_r5) if (r5 is not None and bench_r5 is not None) else r5

        # Volatility normalization: rolling 21-day σ
        vol_norm_ar1: Optional[float] = None
        df_stock = fetcher._price_cache.get(ticker)
        if df_stock is not None and not df_stock.empty and ar1 is not None:
            try:
                ev_dt = pd.Timestamp(event_date)
                pre = df_stock[df_stock.index < ev_dt].tail(21)
                if len(pre) >= 5:
                    daily_vol = float(pre["close"].pct_change().dropna().std())
                    vol_norm_ar1 = ar1 / daily_vol if daily_vol > 1e-8 else ar1
            except Exception:
                pass

        base["abnormal_return_1d"]   = round(ar1, 6)   if ar1   is not None else None
        base["abnormal_return_7d"]   = round(ar5, 6)   if ar5   is not None else None
        base["vol_normalized_ar_1d"] = round(vol_norm_ar1, 6) if vol_norm_ar1 is not None else None
        base["benchmark_ticker"]     = benchmark_tk
        return base

    fetcher.compute_metrics = patched_compute_metrics
    logger.info("P2: abnormal return + vol-norm patch applied to MarketDataFetcher")


# ─────────────────────────────────────────────────────────────────────────────
# § P3  TEMPORAL DECAY WEIGHTING  +  SNAPSHOT EXPORT
# ─────────────────────────────────────────────────────────────────────────────
# Time decay: edge weight *= exp(-λ * Δt_days)
# This makes recent events dominate the signal, matching financial intuition.
#
# Snapshot export: partition edges by calendar month → one HeteroData per month
# Compatible with TGN / TGAT which expect (edge_index, t) pairs.

_DECAY_LAMBDA = 0.02   # λ: half-life ≈ 35 days  (tune per use-case)


def apply_temporal_decay(edges: List[GNNEdge], reference_date: Optional[str] = None) -> None:
    """
    Multiply each edge weight by exp(-λ * days_since_event).
    Mutates edges in-place.

    Args:
        edges:          list of GNNEdge objects
        reference_date: ISO date string used as "now" (default: today)
    """
    ref = (
        datetime.fromisoformat(reference_date)
        if reference_date
        else datetime.now(timezone.utc)
    )
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    for edge in edges:
        if not edge.timestamp:
            continue
        try:
            ts = datetime.fromisoformat(edge.timestamp.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta_days = max((ref - ts).days, 0)
            decay = math.exp(-_DECAY_LAMBDA * delta_days)
            edge.weight = round(edge.weight * decay, 6)
        except Exception:
            pass

    logger.info("P3: temporal decay applied to %d edges (λ=%.3f)", len(edges), _DECAY_LAMBDA)


def export_temporal_snapshots(
    nodes: List[GNNNode],
    edges: List[GNNEdge],
    features: np.ndarray,
    output_dir: Path,
    freq: str = "month",        # "month" | "week" | "quarter"
) -> List[Dict[str, Any]]:
    """
    Partition edges by time window and export one snapshot per window.
    Each snapshot is a dict:
      {
        "period":     "2021-03",
        "edge_index": np.ndarray [2, E],   (src, dst pairs)
        "edge_attr":  np.ndarray [E, 3],   (weight, ts_norm, causal_label)
        "node_ids":   List[int],           active node ids in this snapshot
        "path":       Path                  .npz file
      }

    Compatible with TGN / TGAT: pass edge_index + timestamps externally.
    """
    snap_dir = Path(output_dir) / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    def _period_key(ts_str: str) -> str:
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if freq == "week":
                return dt.strftime("%Y-W%W")
            if freq == "quarter":
                q = (dt.month - 1) // 3 + 1
                return f"{dt.year}-Q{q}"
            return dt.strftime("%Y-%m")
        except Exception:
            return "unknown"

    # Group edges by period
    period_edges: Dict[str, List[GNNEdge]] = defaultdict(list)
    for edge in edges:
        if edge.timestamp:
            period_edges[_period_key(edge.timestamp)].append(edge)

    id_to_type = {n.gnn_id: n.gnn_type for n in nodes}
    snapshots: List[Dict[str, Any]] = []

    for period, pedges in sorted(period_edges.items()):
        if period == "unknown":
            continue

        src_ids = [e.source_id for e in pedges]
        dst_ids = [e.target_id for e in pedges]
        weights = [e.weight for e in pedges]
        labels  = [getattr(e, "props", {}).get("causal_label", -1) if hasattr(e, "props") else -1
                   for e in pedges]
        # ts_norm: days since period start
        period_ref = _parse_period_start(period, freq)
        ts_norms = []
        for e in pedges:
            try:
                ts = datetime.fromisoformat((e.timestamp or "").replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ts_norms.append(min((ts - period_ref).days / 30.0, 1.0))
            except Exception:
                ts_norms.append(0.5)

        edge_index = np.array([src_ids, dst_ids], dtype=np.int64)
        edge_attr  = np.array(
            [[w, tn, lb] for w, tn, lb in zip(weights, ts_norms, labels)],
            dtype=np.float32,
        )
        active_ids = sorted(set(src_ids + dst_ids))

        path = snap_dir / f"snapshot_{period}.npz"
        np.savez_compressed(
            str(path),
            edge_index=edge_index,
            edge_attr=edge_attr,
            node_ids=np.array(active_ids, dtype=np.int64),
        )

        snapshots.append({
            "period":     period,
            "num_edges":  len(pedges),
            "num_nodes":  len(active_ids),
            "edge_index": edge_index,
            "edge_attr":  edge_attr,
            "node_ids":   active_ids,
            "path":       path,
        })

    logger.info("P3: exported %d temporal snapshots to %s", len(snapshots), snap_dir)
    return snapshots


def _parse_period_start(period: str, freq: str) -> datetime:
    try:
        if freq == "week":
            year, week = period.split("-W")
            dt = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
        elif freq == "quarter":
            year, q = period.split("-Q")
            month = (int(q) - 1) * 3 + 1
            dt = datetime(int(year), month, 1)
        else:
            dt = datetime.strptime(period, "%Y-%m")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# § P4  DATASET BALANCING  (neutral events + GDELT non-financial query)
# ─────────────────────────────────────────────────────────────────────────────
# Inject neutral events (sports, culture, science) with causal_label=0
# so the GNN learns what a non-market event looks like.

NEUTRAL_GDELT_QUERIES: List[str] = [
    "sports championship tournament award",
    "cultural festival arts music performance",
    "scientific discovery research publication",
    "weather natural disaster unrelated economy",
    "celebrity entertainment social media trend",
]

_NEUTRAL_EVENT_RATIO = 0.15   # 15 % of final dataset will be neutral


def fetch_neutral_events(
    gdelt_generator,
    start_date: str,
    end_date: str,
    n_neutral: int = 500,
) -> List[Dict[str, Any]]:
    """
    Fetch non-financial GDELT events and mark them as causal_label=0.
    Uses same RealWorldEventGenerator caching infrastructure.
    """
    orig_queries = gdelt_generator._ECONOMIC_QUERIES
    # Temporarily override queries with neutral ones
    gdelt_generator._ECONOMIC_QUERIES = [
        (q, "neutral") for q in NEUTRAL_GDELT_QUERIES
    ]
    # Raise tone threshold so we capture neutral (positive-tone) events
    import gnn_realworld_dataset_generator as gen_mod
    orig_threshold = gen_mod._GDELT_TONE_THRESHOLD
    gen_mod._GDELT_TONE_THRESHOLD = -999.0   # admit all tones

    neutral = gdelt_generator.fetch_events(start_date, end_date, max_events=n_neutral)

    # Restore
    gdelt_generator._ECONOMIC_QUERIES = orig_queries
    gen_mod._GDELT_TONE_THRESHOLD = orig_threshold

    for ev in neutral:
        ev["impact_score"]   = 0.0
        ev["causal_label"]   = 0
        ev["gdelt_category"] = "neutral"

    logger.info("P4: fetched %d neutral (non-financial) events", len(neutral))
    return neutral


# ─────────────────────────────────────────────────────────────────────────────
# § P5  FUZZY ENTITY MAPPING FALLBACK
# ─────────────────────────────────────────────────────────────────────────────
# Adds two fallback layers on top of the keyword rules:
#   Layer 1: difflib.SequenceMatcher (trigram-like, stdlib only)
#   Layer 2: direct ticker symbol detection via regex (e.g. "$AAPL", "NVDA stock")
#
# Only activates when the exact-keyword pass returns < 2 entities.

import difflib
import re as _re

# Flat lists for fuzzy matching
_ALL_ENTITY_NAMES: List[Tuple[str, str]] = list(dict.fromkeys(
    (name, typ) for _, name, typ in ENTITY_KEYWORD_RULES
))

_TICKER_RE = _re.compile(r"\b\$?([A-Z]{2,5})\b")   # matches $AAPL or AAPL


class FuzzyEntityMapper:
    """
    Drop-in replacement for EventEntityMapper that adds fuzzy fallback.
    Extends (not replaces) the original keyword-rule pass.
    """

    def __init__(self, fuzzy_threshold: float = 0.72):
        self.fuzzy_threshold = fuzzy_threshold

    def map(self, event_text: str, max_entities: int = 8) -> List[Tuple[str, str]]:
        from gnn_realworld_dataset_generator import EventEntityMapper
        base_mapper = EventEntityMapper()
        results = base_mapper.map(event_text, max_entities=max_entities)
        seen_names = {r[0] for r in results}

        if len(results) >= 3:
            return results[:max_entities]   # keyword pass sufficient

        text_lower = event_text.lower()

        # ── Layer 1: ticker regex ───────────────────────────────────────────
        for match in _TICKER_RE.finditer(event_text.upper()):
            sym = match.group(1)
            if sym in TICKER_TO_COMPANY:
                name = TICKER_TO_COMPANY[sym]
                if name not in seen_names:
                    gtype = "Company"
                    results.append((name, gtype))
                    seen_names.add(name)

        if len(results) >= max_entities:
            return results[:max_entities]

        # ── Layer 2: difflib fuzzy matching ────────────────────────────────
        words = text_lower.split()
        window_size = 4
        ngrams: List[str] = []
        for i in range(len(words)):
            for w in range(1, min(window_size, len(words) - i) + 1):
                ngrams.append(" ".join(words[i:i + w]))

        for ngram in ngrams:
            if len(results) >= max_entities:
                break
            for entity_name, entity_type in _ALL_ENTITY_NAMES:
                if entity_name in seen_names:
                    continue
                ratio = difflib.SequenceMatcher(
                    None, ngram, entity_name.lower()
                ).ratio()
                if ratio >= self.fuzzy_threshold:
                    results.append((entity_name, entity_type))
                    seen_names.add(entity_name)
                    break   # one match per ngram

        # Always add Talan
        if "Talan" not in seen_names:
            results.append(("Talan", "Company"))

        return results[:max_entities]

    def map_tickers(self, event_text: str) -> List[str]:
        from gnn_realworld_dataset_generator import EventEntityMapper
        base = EventEntityMapper().map_tickers(event_text)
        # Add ticker-regex hits
        for match in _TICKER_RE.finditer(event_text.upper()):
            sym = match.group(1)
            if sym in TICKER_TO_COMPANY and sym not in base:
                base.append(sym)
        return base[:10]


# ─────────────────────────────────────────────────────────────────────────────
# § P6  CAUSAL PROPAGATION EDGES
# ─────────────────────────────────────────────────────────────────────────────
# Adds the causal chain:
#   Event → MacroIndicator  (INFLUENCES)
#   MacroIndicator → Sector (INFLUENCES, already partially in builder)
#   Sector → Company        (AFFECTS)
#
# These are ADDITIONAL edges beyond existing IMPACTS edges.
# Weight is decayed across the chain: w_macro = w*0.9, w_sector = w*0.8, w_co = w*0.65

_CAUSAL_CHAIN_MACRO_MAP: Dict[str, str] = {
    # gdelt_category or keyword → macro indicator name
    "ECB Interest Rates":          "ECB Interest Rates",
    "Federal Reserve Rate":        "Federal Reserve Rate",
    "inflation":                   "Eurozone Inflation",
    "oil":                         "Brent Crude Oil Price",
    "energy":                      "Brent Crude Oil Price",
    "AI Market Growth Index":      "AI Market Growth Index",
    "cybersecurity":               "Cybersecurity Spending Index",
    "MacroIndicator":              "ECB Interest Rates",   # generic fallback
}


def inject_causal_propagation_edges(
    nodes: List[GNNNode],
    edges: List[GNNEdge],
    slug_to_id: Dict[str, int],
) -> int:
    """
    For every existing Event → Entity IMPACTS edge, walk the causal chain
    Event → Macro → Sector → Company and add INFLUENCES / AFFECTS edges.

    Returns count of new edges added.
    """
    from gnn_realworld_dataset_generator import GNNEdge as _E

    id_to_node = {n.gnn_id: n for n in nodes}
    existing_keys: Set[Tuple[int, int, str]] = {
        (e.source_id, e.target_id, e.gnn_type) for e in edges
    }

    def _add(src: int, dst: int, etype: str, w: float, ts: Optional[str]) -> bool:
        k = (src, dst, etype)
        if k in existing_keys or src == dst:
            return False
        edges.append(_E(
            source_id=src, target_id=dst,
            gnn_type=etype, weight=round(w, 6),
            timestamp=ts, source_system="causal_chain",
        ))
        existing_keys.add(k)
        return True

    added = 0

    # Index lookup helpers
    macro_by_name   = {n.name: n for n in nodes if n.gnn_type == "MacroIndicator"}
    sector_by_name  = {n.name: n for n in nodes if n.gnn_type == "Sector"}
    company_by_sector: Dict[str, List[GNNNode]] = defaultdict(list)
    for e in edges:
        if e.gnn_type == "BELONGS_TO_SECTOR":
            src = id_to_node.get(e.source_id)
            dst = id_to_node.get(e.target_id)
            if src and dst:
                company_by_sector[dst.name].append(src)

    for edge in list(edges):   # iterate copy — we append during loop
        if edge.gnn_type != "IMPACTS":
            continue
        ev_node  = id_to_node.get(edge.source_id)
        dst_node = id_to_node.get(edge.target_id)
        if ev_node is None or ev_node.gnn_type != "Event":
            continue
        if dst_node is None:
            continue

        w_base = edge.weight
        ts     = edge.timestamp

        # Event → Macro
        category = ev_node.props.get("gdelt_category", "")
        macro_name = _CAUSAL_CHAIN_MACRO_MAP.get(category) or _CAUSAL_CHAIN_MACRO_MAP.get(
            dst_node.name, None
        )
        if macro_name is None:
            # Infer macro from event text keywords
            ev_text = (ev_node.name + " " + ev_node.props.get("description", "")).lower()
            for kw, mname in _CAUSAL_CHAIN_MACRO_MAP.items():
                if kw.lower() in ev_text:
                    macro_name = mname
                    break

        macro_node = macro_by_name.get(macro_name) if macro_name else None
        if macro_node:
            if _add(ev_node.gnn_id, macro_node.gnn_id, "INFLUENCES", w_base * 0.9, ts):
                added += 1

            # Macro → Sector
            for sec_name, sec_node in sector_by_name.items():
                # Use existing INFLUENCES edges as ground truth
                existing_inf = any(
                    e.source_id == macro_node.gnn_id and e.target_id == sec_node.gnn_id
                    and e.gnn_type == "INFLUENCES"
                    for e in edges
                )
                if not existing_inf:
                    continue
                if _add(macro_node.gnn_id, sec_node.gnn_id, "INFLUENCES", w_base * 0.8, ts):
                    added += 1

                # Sector → Companies in that sector
                for comp_node in company_by_sector.get(sec_name, []):
                    if _add(sec_node.gnn_id, comp_node.gnn_id, "AFFECTS", w_base * 0.65, ts):
                        added += 1

    logger.info("P6: injected %d causal propagation edges", added)
    return added


# ─────────────────────────────────────────────────────────────────────────────
# § P7  EXTENDED OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

class ExtendedDatasetExporter(DatasetExporter):
    """
    Extends base DatasetExporter to also write:
      - edge_labels.csv      : source, target, type, causal_label, weight
      - causal_map.json      : event → [affected entities + confidence + AR]
      - snapshots/           : temporal .npz files (optional)
    """

    def export_extended(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
        features: np.ndarray,
        extra_meta: Optional[Dict] = None,
        write_snapshots: bool = True,
        snapshot_freq: str = "month",
    ) -> Dict[str, Any]:
        # Base export (nodes, edges, features, metadata)
        paths = self.export(nodes, edges, features, extra_meta)

        # edge_labels.csv
        label_path = self._write_edge_labels(edges)
        paths["edge_labels"] = label_path

        # causal_map.json
        causal_path = self._write_causal_map(nodes, edges)
        paths["causal_map"] = causal_path

        # temporal snapshots
        snapshot_meta: List[Dict] = []
        if write_snapshots:
            snapshot_meta = export_temporal_snapshots(
                nodes, edges, features, self.output_dir, freq=snapshot_freq
            )
            paths["snapshots_dir"] = self.output_dir / "snapshots"

        return {
            "paths":     paths,
            "snapshots": snapshot_meta,
        }

    def _write_edge_labels(self, edges: List[GNNEdge]) -> Path:
        path = self.output_dir / "edge_labels.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["source", "target", "type", "weight", "causal_label", "source_system"],
            )
            writer.writeheader()
            for e in edges:
                label = -1
                if hasattr(e, "props") and isinstance(e.props, dict):
                    label = e.props.get("causal_label", -1)
                writer.writerow({
                    "source":       e.source_id,
                    "target":       e.target_id,
                    "type":         e.gnn_type,
                    "weight":       round(e.weight, 6),
                    "causal_label": label,
                    "source_system": e.source_system,
                })
        logger.info("P7: edge_labels.csv written (%d rows)", len(edges))
        return path

    def _write_causal_map(
        self,
        nodes: List[GNNNode],
        edges: List[GNNEdge],
    ) -> Path:
        """
        causal_map.json structure:
          {
            "<event_slug>": {
              "name":     "...",
              "date":     "YYYY-MM-DD",
              "entities": [
                {
                  "name":          "...",
                  "type":          "...",
                  "causal_label":  1|0,
                  "edge_weight":   float,
                  "edge_source":   "realworld|hard_negative|causal_chain"
                }
              ]
            }
          }
        """
        id_to_node = {n.gnn_id: n for n in nodes}
        causal_map: Dict[str, Any] = {}

        for edge in edges:
            if edge.gnn_type != "IMPACTS":
                continue
            ev_node = id_to_node.get(edge.source_id)
            if ev_node is None or ev_node.gnn_type != "Event":
                continue
            dst_node = id_to_node.get(edge.target_id)
            if dst_node is None:
                continue

            key = ev_node.slug
            if key not in causal_map:
                causal_map[key] = {
                    "name":     ev_node.name,
                    "date":     ev_node.props.get("event_date", ""),
                    "impact_score": ev_node.impact_score,
                    "entities": [],
                }

            label = -1
            if hasattr(edge, "props") and isinstance(edge.props, dict):
                label = edge.props.get("causal_label", -1)

            causal_map[key]["entities"].append({
                "name":         dst_node.name,
                "type":         dst_node.gnn_type,
                "causal_label": label,
                "edge_weight":  round(edge.weight, 6),
                "edge_source":  edge.source_system,
            })

        path = self.output_dir / "causal_map.json"
        path.write_text(
            json.dumps(causal_map, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("P7: causal_map.json written (%d events)", len(causal_map))
        return path


# ─────────────────────────────────────────────────────────────────────────────
# § MASTER PATCH  — apply all upgrades to an existing pipeline instance
# ─────────────────────────────────────────────────────────────────────────────

def patch_pipeline(pipeline: RealWorldDatasetPipeline) -> None:
    """
    Apply all causal patches to an existing RealWorldDatasetPipeline instance.

    Call this BEFORE pipeline.run().

    Patches applied:
      P2 — MarketDataFetcher: abnormal returns + vol normalization
      P1 — GraphBuilder: causal labeling on IMPACTS edges
      P5 — EventEntityMapper: replaced with FuzzyEntityMapper
      P3 — temporal decay applied after graph build (hooked into _stage_features)
      P6 — causal propagation edges injected after graph build
      P7 — DatasetExporter replaced with ExtendedDatasetExporter
    """
    # P2: abnormal returns
    patch_market_data_fetcher(pipeline._market)

    # P5: fuzzy entity mapper
    pipeline._mapper = FuzzyEntityMapper(fuzzy_threshold=0.72)

    # P1: causal labeling (graph builder patch — applied after builder is used)
    # We override _stage_build_graph to apply the patch at the right moment
    orig_build = pipeline._stage_build_graph

    def patched_build():
        # Apply causal label patch before ingestion starts
        patch_graph_builder_causal(pipeline._builder)
        orig_build()

        # P6: causal propagation edges (after graph is built)
        inject_causal_propagation_edges(
            pipeline._builder.nodes,
            pipeline._builder.edges,
            pipeline._builder.slug_to_id,
        )
        pipeline.nodes = pipeline._builder.nodes
        pipeline.edges = pipeline._builder.edges

    pipeline._stage_build_graph = patched_build

    # P3: temporal decay (hooked before feature building)
    orig_features = pipeline._stage_features

    def patched_features():
        apply_temporal_decay(pipeline.edges, reference_date=pipeline.end_date)
        orig_features()

    pipeline._stage_features = patched_features

    # P7: swap exporter with extended version
    pipeline._exporter = ExtendedDatasetExporter(pipeline.output_dir)

    # Override _stage_export to call export_extended
    orig_export = pipeline._stage_export

    def patched_export():
        extra_meta = {
            "start_date":       pipeline.start_date,
            "end_date":         pipeline.end_date,
            "num_events":       len(pipeline._events),
            "tickers":          pipeline.tickers,
            "causal_patches":   ["P1", "P2", "P3", "P5", "P6", "P7"],
        }
        result = pipeline._exporter.export_extended(
            pipeline.nodes,
            pipeline.edges,
            pipeline.features,
            extra_meta=extra_meta,
            write_snapshots=True,
            snapshot_freq="month",
        )
        return result["paths"]

    pipeline._stage_export = patched_export

    logger.info(
        "patch_pipeline: all causal patches applied "
        "(P1 causal labels, P2 abnormal returns, P3 decay+snapshots, "
        "P5 fuzzy mapping, P6 causal edges, P7 extended export)"
    )


def patch_pipeline_with_negatives(
    pipeline: RealWorldDatasetPipeline,
    negatives_per_event: int = _HARD_NEG_PER_EVENT,
) -> None:
    """
    Additional patch: inject hard negative edges AFTER graph build.
    Call after patch_pipeline() for the full upgrade.
    """
    orig_build = pipeline._stage_build_graph

    def patched_build_with_negatives():
        orig_build()
        sampler = HardNegativeSampler(seed=42)
        sampler.sample(
            pipeline.nodes,
            pipeline.edges,
            pipeline._events,
            pipeline._market,
            negatives_per_event=negatives_per_event,
        )

    pipeline._stage_build_graph = patched_build_with_negatives
    logger.info("patch_pipeline_with_negatives: hard negative sampler hooked")


# ─────────────────────────────────────────────────────────────────────────────
# § USAGE EXAMPLE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Minimal usage:

        python gnn_causal_patches.py

    Full integration with your existing pipeline:

        from gnn_realworld_dataset_generator import RealWorldDatasetPipeline
        from gnn_causal_patches import patch_pipeline, patch_pipeline_with_negatives

        pipeline = RealWorldDatasetPipeline(
            output_dir="./gnn_causal_dataset",
            cache_dir="./.cache",
            start_date="2021-01-01",
            end_date="2024-12-31",
            max_events=10_000,
        )

        patch_pipeline(pipeline)                    # all upgrades
        patch_pipeline_with_negatives(pipeline)     # P1 hard negatives

        summary = pipeline.run()
        print(summary["stats"])
    """
    logging.basicConfig(level=logging.INFO)
    print("gnn_causal_patches.py loaded — import patch_pipeline and apply to your pipeline.")
    print("See module docstring for usage.")