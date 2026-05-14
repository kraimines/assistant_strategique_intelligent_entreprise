"""
run_pipeline.py
===============
Generates the real-world GNN dataset with all causal patches applied.

Run from the market_analysis/ directory:
    cd backend/app/services/market_analysis
    python run_pipeline.py

Output written to: gnn_causal_dataset/
  nodes.csv, edges.csv, node_features.npy, metadata.json
  edge_labels.csv, causal_map.json, snapshots/*.npz
"""

import logging
import sys
import json
import types as _types
from pathlib import Path

# ── Make sure both generator modules are importable ───────────────────────────
HERE = Path(__file__).parent.resolve()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# The file is named Gnn_realworld_dataset_generator.py (capital G) but
# gnn_data_generator.py imports it as gnn_realworld_dataset_generator (lowercase).
# Register the module under both names before any other import touches it.
import importlib.util as _ilu

def _register_module(canonical_name: str, file_path: Path) -> None:
    if canonical_name not in sys.modules:
        spec = _ilu.spec_from_file_location(canonical_name, file_path)
        mod  = _ilu.module_from_spec(spec)
        sys.modules[canonical_name] = mod
        spec.loader.exec_module(mod)

_register_module(
    "gnn_realworld_dataset_generator",
    HERE / "Gnn_realworld_dataset_generator.py",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("run_pipeline")

# ── Imports ───────────────────────────────────────────────────────────────────
from gnn_realworld_dataset_generator import RealWorldDatasetPipeline  # noqa: E402
from gnn_data_generator import (                                        # noqa: E402
    patch_pipeline,
    patch_pipeline_with_negatives,
)

# ── Configuration ─────────────────────────────────────────────────────────────
OUTPUT_DIR  = HERE / "gnn_causal_dataset"
CACHE_DIR   = HERE / ".cache"
START_DATE  = "2021-01-01"
END_DATE    = "2024-12-31"
MAX_EVENTS  = 5_000          # > 2 000 as requested; ~10–20 min on free GDELT API
SKIP_PYG    = True           # skip PyG conversion here — trainers do it themselves


# 8 focused queries covering Talan's core markets (IT consulting, finance, AI, energy)
_TALAN_QUERIES = [
    ("central bank interest rate ECB Fed decision",   "MacroIndicator"),
    ("artificial intelligence investment regulation", "AI Market Growth Index"),
    ("cybersecurity breach data leak attack",         "Cybersecurity Spending Index"),
    ("technology consulting merger acquisition deal", "Company"),
    ("semiconductor chip shortage supply chain",      "Semiconductors"),
    ("oil price energy crisis supply disruption",     "Energy & Utilities"),
    ("inflation CPI economic recession outlook",      "MacroIndicator"),
    ("company layoffs restructuring earnings",        "Company"),
]


def _patch_gdelt_fetcher(pipeline) -> None:
    """
    Replaces the event generator's fetch_events with a version that uses
    90-day windows (quarterly) instead of 30-day, 8 targeted queries instead
    of 20, and a 5-second inter-request delay to avoid 429 rate limits.
    """
    from gnn_realworld_dataset_generator import _date_windows, _GDELT_TONE_THRESHOLD

    gen = pipeline._event_gen
    gen.retry_delay = 10.0              # was 1.5 s — 10 s avoids GDELT 429s
    gen._ECONOMIC_QUERIES = _TALAN_QUERIES

    def _patched_fetch_events(self, start_date, end_date, max_events=10_000):
        all_events, seen_urls = [], set()
        date_windows = list(_date_windows(start_date, end_date, window_days=90))
        queries = self._ECONOMIC_QUERIES

        per_query_budget = max(
            1,
            max_events // (len(queries) * max(len(date_windows), 1))
        )
        per_query_budget = min(per_query_budget, 250)

        logger.info(
            "EventGenerator (patched): %s → %s  (%d windows × %d queries, budget=%d/query)",
            start_date, end_date, len(date_windows), len(queries), per_query_budget,
        )

        for win_start, win_end in date_windows:
            if len(all_events) >= max_events:
                break
            for query_text, category in queries:
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
                        continue
                    ev = self._article_to_event(article, category)
                    if ev is None:
                        continue
                    all_events.append(ev)
                    seen_urls.add(url)

        logger.info("EventGenerator: collected %d unique real-world events", len(all_events))
        return all_events

    gen.fetch_events = _types.MethodType(_patched_fetch_events, gen)
    logger.info(
        "_patch_gdelt_fetcher: 90-day windows, %d queries, %.1fs delay",
        len(_TALAN_QUERIES), gen.retry_delay,
    )


def main() -> None:
    logger.info("=" * 60)
    logger.info("Talan GNN Causal Dataset Generator")
    logger.info("  date range : %s → %s", START_DATE, END_DATE)
    logger.info("  max events : %d", MAX_EVENTS)
    logger.info("  output     : %s", OUTPUT_DIR)
    logger.info("=" * 60)

    # 1. Build pipeline
    pipeline = RealWorldDatasetPipeline(
        output_dir  = str(OUTPUT_DIR),
        cache_dir   = str(CACHE_DIR),
        start_date  = START_DATE,
        end_date    = END_DATE,
        max_events  = MAX_EVENTS,
        skip_pyg    = SKIP_PYG,
    )

    # 2. Patch GDELT event generator to avoid rate-limiting
    #    Original: 49 windows × 20 queries = 980 calls with 1.5 s delay → 4+ hours
    #    Patched:  16 windows × 8 queries  = 128 calls with 10.0 s delay → ~22 min
    _patch_gdelt_fetcher(pipeline)

    # 3. Apply all causal patches (P1–P7)
    patch_pipeline(pipeline)                   # abnormal returns, causal labels,
                                               # temporal decay, fuzzy mapping,
                                               # causal propagation, extended export
    patch_pipeline_with_negatives(pipeline)    # hard-negative edge injection (P1+)

    # 4. Run
    summary = pipeline.run()

    # 4. Print stats
    stats = summary.get("stats", {})
    logger.info("=" * 60)
    logger.info("Pipeline complete!")
    logger.info("  nodes       : %d", stats.get("num_nodes", 0))
    logger.info("  edges       : %d", stats.get("num_edges", 0))
    logger.info("  events      : %d", stats.get("num_events", 0))
    logger.info("  feature_dim : %d", stats.get("feature_dim", 0))

    logger.info("\n  Node type breakdown:")
    for ntype, count in stats.get("node_type_counts", {}).items():
        logger.info("    %-20s %d", ntype, count)

    logger.info("\n  Edge type breakdown:")
    for etype, count in stats.get("edge_type_counts", {}).items():
        logger.info("    %-25s %d", etype, count)

    # 5. Validate critical output files
    logger.info("\n  Output files:")
    required = [
        "nodes.csv", "edges.csv", "node_features.npy",
        "metadata.json", "edge_labels.csv", "causal_map.json",
    ]
    all_ok = True
    for fname in required:
        p = OUTPUT_DIR / fname
        exists = p.exists()
        size   = p.stat().st_size if exists else 0
        status = f"OK ({size:,} bytes)" if exists else "MISSING"
        logger.info("    %-25s %s", fname, status)
        if not exists:
            all_ok = False

    snap_dir = OUTPUT_DIR / "snapshots"
    n_snaps  = len(list(snap_dir.glob("*.npz"))) if snap_dir.exists() else 0
    logger.info("    snapshots/               %d .npz files", n_snaps)

    # 6. Quick class-balance check on edge_labels.csv
    label_path = OUTPUT_DIR / "edge_labels.csv"
    if label_path.exists():
        import csv
        pos = neg = unknown = 0
        with open(label_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lbl = int(row.get("causal_label", -1))
                if lbl == 1:
                    pos += 1
                elif lbl == 0:
                    neg += 1
                else:
                    unknown += 1
        total = pos + neg + unknown or 1
        logger.info(
            "\n  Edge label balance (IMPACTS edges):\n"
            "    positive (causal=1)  : %d  (%.1f%%)\n"
            "    negative (causal=0)  : %d  (%.1f%%)\n"
            "    unlabelled (-1)      : %d  (%.1f%%)",
            pos, 100 * pos / total,
            neg, 100 * neg / total,
            unknown, 100 * unknown / total,
        )

    if all_ok:
        logger.info("\nAll output files present. Ready to train GNN models.")
    else:
        logger.warning("\nSome output files are missing — check the logs above.")

    return summary


if __name__ == "__main__":
    main()
