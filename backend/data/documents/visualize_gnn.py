#!/usr/bin/env python3
"""
Temporal Heterogeneous GNN — Interactive Dataset Explorer
==========================================================
Launch:  streamlit run visualize_gnn.py
Requires: pip install streamlit pyvis networkx plotly pandas
"""

import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Optional — impact scorer lives alongside this file
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from impact_scorer import (
        ImpactScorer as _ImpactScorer,
        build_scorer_input_from_event as _build_scorer_input,
        batch_score_events as _batch_score,
        IMPACT_LABELS as _IMPACT_LABELS,
    )
    _SCORER_AVAILABLE = True
except Exception as _imp_err:
    _SCORER_AVAILABLE = False
    _imp_err_msg = str(_imp_err)

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG  (must be first Streamlit call)
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="THGNN Explorer — Talan KG",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent

NODE_COLORS: dict[str, str] = {
    "Company":        "#4C72B0",   # steel blue
    "Sector":         "#55A868",   # green
    "Country":        "#C44E52",   # red
    "Event":          "#DD8452",   # orange
    "MacroIndicator": "#8172B2",   # purple
}

NODE_SIZES: dict[str, int] = {
    "Company": 22, "Sector": 18, "Country": 16,
    "Event": 28, "MacroIndicator": 20,
}

NODE_SHAPES: dict[str, str] = {
    "Company": "dot", "Sector": "square",
    "Country": "triangle", "Event": "star",
    "MacroIndicator": "diamond",
}

EDGE_COLORS: dict[str, str] = {
    "CAUSES_IMPACT_ON":  "#FF6B35",
    "INFLUENCES":        "#AA66FF",
    "BELONGS_TO_SECTOR": "#AAAAAA",
    "COMPETES_WITH":     "#FF4444",
    "OPERATES_IN":       "#66AAFF",
    "SUPPLY_CHAIN_LINK": "#66CC66",
}
EDGE_COLOR_DEFAULT = "#888888"

# Edges that carry a causal / temporal signal
CAUSAL_RELATIONS: set[str] = {"CAUSES_IMPACT_ON", "INFLUENCES"}

# ──────────────────────────────────────────────────────────────────────────────
# CSS INJECTION
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
[data-testid="stSidebar"] {background: #0f0f1a;}
.block-container {padding-top: 1rem;}
h1 {color: #e0e0ff;}
.stTabs [data-baseweb="tab"] {font-size: 0.9rem; font-weight: 600;}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# DATA LOADING  (cached)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading kg_events.json …")
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Parse kg_events.json → (nodes_df, edges_df, event_meta)."""
    kg_path = DATA_DIR / "kg_events.json"
    if not kg_path.exists():
        return pd.DataFrame(), pd.DataFrame(), {}

    with open(kg_path, encoding="utf-8") as fh:
        events: list[dict] = json.load(fh)

    nodes_map: dict[str, dict] = {}
    edges_rows: list[dict] = []
    event_meta: dict[str, dict] = {}

    for evt in events:
        evt_id   = evt["event_id"]
        evt_date = evt["event_date"]          # "YYYY-MM-DD"
        evt_ts   = _date_to_ts(evt_date)

        event_meta[evt_id] = {
            "name":        evt.get("event_name", ""),
            "type":        evt.get("event_type", "unknown"),
            "date":        evt_date,
            "timestamp":   evt_ts,
            "severity":    evt.get("severity", 0.5),
            "confidence":  evt.get("confidence", 0.5),
            "description": evt.get("event_description", ""),
        }

        # ── Nodes ──────────────────────────────────────────────────────────
        for node in evt.get("nodes", []):
            nid = node.get("id")
            if nid and nid not in nodes_map:
                nodes_map[nid] = node

        # ── Edges ──────────────────────────────────────────────────────────
        for edge in evt.get("edges", []):
            raw_ts = edge.get("timestamp", evt_date)
            if isinstance(raw_ts, str) and raw_ts:
                ts_float = _date_to_ts(raw_ts[:10])
            else:
                ts_float = evt_ts

            relation = edge.get("relation", "UNKNOWN")
            impact   = edge.get("impact_score", 0.0)

            edges_rows.append({
                "from_id":      edge.get("from_id", ""),
                "to_id":        edge.get("to_id", ""),
                "relation":     relation,
                "impact_score": impact,
                "confidence":   edge.get("confidence", 0.5),
                "timestamp":    ts_float,
                "date":         raw_ts[:10] if isinstance(raw_ts, str) else evt_date,
                "reasoning":    edge.get("reasoning", ""),
                "event_id":     evt_id,
                # causal_label: 1 if this is a causal/temporal edge, else 0
                "causal_label": 1 if relation in CAUSAL_RELATIONS else 0,
                # binary impact label: 1 = positive causal, 0 = negative causal
                "impact_label": 1 if impact > 0 else 0,
            })

    nodes_df = pd.DataFrame(list(nodes_map.values()))
    edges_df = pd.DataFrame(edges_rows) if edges_rows else pd.DataFrame()

    if not edges_df.empty:
        edges_df["datetime"] = pd.to_datetime(edges_df["date"])
        edges_df["year"]     = edges_df["datetime"].dt.year
        edges_df["month"]    = edges_df["datetime"].dt.to_period("M").astype(str)

    return nodes_df, edges_df, event_meta


def _date_to_ts(date_str: str) -> float:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").timestamp()
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# GRAPH BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_graph(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    *,
    node_types: list[str] | None = None,
    edge_types: list[str] | None = None,
    causal_only: bool = False,
    ts_min: float | None = None,
    ts_max: float | None = None,
    max_nodes: int = 200,
    max_edges: int = 800,
    sample_seed: int = 42,
) -> tuple[nx.MultiDiGraph, pd.DataFrame, pd.DataFrame]:
    """Filter and sample, then build a NetworkX graph."""

    # ── Node filtering ──────────────────────────────────────────────────────
    ndf = nodes_df.copy()
    if node_types:
        ndf = ndf[ndf["type"].isin(node_types)]
    if len(ndf) > max_nodes:
        # Keep Talan + sample the rest
        keep_talan  = ndf[ndf["id"] == "talan"]
        rest        = ndf[ndf["id"] != "talan"]
        rest_sample = rest.sample(min(max_nodes - len(keep_talan), len(rest)),
                                  random_state=sample_seed)
        ndf = pd.concat([keep_talan, rest_sample])
    node_ids = set(ndf["id"])

    # ── Edge filtering ──────────────────────────────────────────────────────
    edf = edges_df.copy()
    if ts_min is not None:
        edf = edf[edf["timestamp"] >= ts_min]
    if ts_max is not None:
        edf = edf[edf["timestamp"] <= ts_max]
    if edge_types:
        edf = edf[edf["relation"].isin(edge_types)]
    if causal_only:
        edf = edf[edf["causal_label"] == 1]
    edf = edf[edf["from_id"].isin(node_ids) & edf["to_id"].isin(node_ids)]
    if len(edf) > max_edges:
        edf = edf.sample(max_edges, random_state=sample_seed)

    # ── Build graph ─────────────────────────────────────────────────────────
    G: nx.MultiDiGraph = nx.MultiDiGraph()
    for _, row in ndf.iterrows():
        G.add_node(row["id"], **row.to_dict())
    for _, row in edf.iterrows():
        if row["from_id"] in G and row["to_id"] in G:
            G.add_edge(row["from_id"], row["to_id"], **row.to_dict())

    return G, ndf, edf


# ──────────────────────────────────────────────────────────────────────────────
# PYVIS RENDERER
# ──────────────────────────────────────────────────────────────────────────────

def _pyvis_html(
    G: nx.MultiDiGraph,
    nodes_df: pd.DataFrame,
    highlight_node: str | None = None,
    height: int = 600,
) -> str:
    """Render a NetworkX graph with PyVis and return raw HTML string."""
    from pyvis.network import Network  # lazy import — optional dependency

    net = Network(
        height=f"{height}px", width="100%",
        directed=True, bgcolor="#1a1a2e", font_color="white",
    )
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -10000,
          "centralGravity": 0.3,
          "springLength": 140,
          "springConstant": 0.04,
          "damping": 0.09
        },
        "stabilization": {"iterations": 180, "fit": true}
      },
      "edges": {
        "smooth": {"type": "dynamic"},
        "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}}
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "tooltipDelay": 80,
        "hideEdgesOnDrag": true
      }
    }
    """)

    id_to_row = nodes_df.set_index("id").to_dict("index")

    # ── Add nodes ────────────────────────────────────────────────────────────
    for nid in G.nodes():
        data  = id_to_row.get(nid, {})
        ntype = data.get("type", "Company")
        color = NODE_COLORS.get(ntype, "#888888")
        shape = NODE_SHAPES.get(ntype, "dot")
        base_size = NODE_SIZES.get(ntype, 20)
        deg = G.degree(nid)
        size = min(base_size + deg * 0.8, 45)

        if highlight_node and nid == highlight_node:
            color = "#FFD700"
            size  = 40

        label = data.get("name", nid)
        label = label[:22] + "…" if len(label) > 22 else label

        # Tooltip
        tip_lines = [f"<b>{data.get('name', nid)}</b>", f"<i>{ntype}</i>"]
        for field, prefix in [
            ("country",      "Country"),
            ("sector",       "Sector"),
            ("ticker",       "Ticker"),
            ("event_type",   "Event type"),
            ("revenue_eur_m","Revenue"),
            ("headcount",    "Headcount"),
        ]:
            v = data.get(field)
            if v:
                tip_lines.append(f"{prefix}: {v:,}" if isinstance(v, int) else f"{prefix}: {v}")
        tip_lines.append(f"Degree: {deg}")

        net.add_node(
            nid, label=label, color=color, shape=shape,
            size=size, title="<br>".join(tip_lines),
        )

    # ── Add edges ────────────────────────────────────────────────────────────
    for u, v, data in G.edges(data=True):
        relation = data.get("relation", "UNKNOWN")
        color    = EDGE_COLORS.get(relation, EDGE_COLOR_DEFAULT)
        impact   = data.get("impact_score", 0.0)
        width    = max(1.0, 1.0 + abs(impact) * 3.5)
        is_causal= data.get("causal_label", 0) == 1

        reasoning = data.get("reasoning", "")
        if len(reasoning) > 120:
            reasoning = reasoning[:118] + "…"
        tip = (
            f"<b>{relation}</b><br>"
            f"Impact: {impact:+.2f} | Conf: {data.get('confidence', 0):.2f}<br>"
            f"Date: {data.get('date', '')}<br>"
            f"{reasoning}"
        )

        net.add_edge(
            u, v, title=tip, color=color, width=width,
            dashes=not is_causal,          # static = dashed
        )

    tmp = tempfile.mktemp(suffix=".html")
    net.save_graph(tmp)
    with open(tmp, encoding="utf-8") as fh:
        html = fh.read()
    os.unlink(tmp)
    return html


# ──────────────────────────────────────────────────────────────────────────────
# K-HOP SUBGRAPH
# ──────────────────────────────────────────────────────────────────────────────

def khop_subgraph(
    G: nx.MultiDiGraph,
    center: str,
    k: int = 2,
    max_nodes: int = 50,
) -> nx.MultiDiGraph:
    if center not in G:
        return G.subgraph([])
    seen     = {center}
    frontier = {center}
    for _ in range(k):
        nxt = set()
        for n in frontier:
            nxt |= set(G.predecessors(n)) | set(G.successors(n))
        frontier = nxt - seen
        seen    |= frontier
        if len(seen) >= max_nodes:
            break
    return G.subgraph(list(seen)[:max_nodes])


# ──────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Header ───────────────────────────────────────────────────────────────
    st.title("🧠 Temporal Heterogeneous GNN — Dataset Explorer")
    st.caption("Interactive exploration of the Talan Market Intelligence Knowledge Graph")

    # ── Load ─────────────────────────────────────────────────────────────────
    nodes_df, edges_df, event_meta = load_data()

    if nodes_df.empty:
        st.error("❌ `kg_events.json` not found. Run `generate_gnn_dataset.py` first.")
        return

    # ── Quick metrics bar ─────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Nodes",   len(nodes_df))
    m2.metric("Edges",   len(edges_df))
    m3.metric("Events",  len(event_meta))
    m4.metric("Relations", edges_df["relation"].nunique() if not edges_df.empty else 0)
    m5.metric(
        "Causal edges",
        int(edges_df["causal_label"].sum()) if not edges_df.empty else 0,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # SIDEBAR
    # ══════════════════════════════════════════════════════════════════════════
    with st.sidebar:
        st.markdown("## ⚙️ Filters")

        # Node types
        all_node_types = sorted(nodes_df["type"].unique().tolist())
        sel_node_types = st.multiselect(
            "Node Types", all_node_types, default=all_node_types, key="sb_nt",
        )

        # Edge types
        all_edge_types = (
            sorted(edges_df["relation"].unique().tolist()) if not edges_df.empty else []
        )
        sel_edge_types = st.multiselect(
            "Edge Types", all_edge_types, default=all_edge_types, key="sb_et",
        )

        st.markdown("---")
        causal_only = st.toggle("🔴 Causal edges only", value=False)

        st.markdown("---")
        st.markdown("### 📅 Time Range")
        if not edges_df.empty:
            min_d = edges_df["datetime"].min().date()
            max_d = edges_df["datetime"].max().date()
            date_range = st.slider(
                "Filter edges", min_value=min_d, max_value=max_d,
                value=(min_d, max_d), format="YYYY-MM",
            )
            ts_min = datetime(date_range[0].year, date_range[0].month, date_range[0].day).timestamp()
            ts_max = datetime(date_range[1].year, date_range[1].month, date_range[1].day, 23, 59).timestamp()
        else:
            ts_min = ts_max = None
            date_range = (None, None)

        st.markdown("---")
        st.markdown("### 📊 Sampling")
        max_nodes_g = st.slider("Max nodes", 20, 300, 150, 10)
        max_edges_g = st.slider("Max edges", 20, 2000, 600, 20)

        st.markdown("---")
        st.markdown("### 🎨 Legend")
        for ntype, color in NODE_COLORS.items():
            st.markdown(
                f'<span style="color:{color};font-size:1.2em">■</span> {ntype}',
                unsafe_allow_html=True,
            )
        st.markdown("---")
        for rel, color in EDGE_COLORS.items():
            st.markdown(
                f'<span style="color:{color};font-size:1.2em">—</span> {rel}',
                unsafe_allow_html=True,
            )

    # ── Build main graph ──────────────────────────────────────────────────────
    G, ndf_g, edf_g = build_graph(
        nodes_df, edges_df,
        node_types=sel_node_types, edge_types=sel_edge_types,
        causal_only=causal_only,
        ts_min=ts_min, ts_max=ts_max,
        max_nodes=max_nodes_g, max_edges=max_edges_g,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # TABS
    # ══════════════════════════════════════════════════════════════════════════
    tab_graph, tab_time, tab_causal, tab_sub, tab_stats, tab_scorer = st.tabs([
        "🌐 Graph View",
        "⏱️ Temporal",
        "🔴 Causality",
        "🔍 Subgraph",
        "📊 Statistics",
        "🎯 Impact Scorer",
    ])

    # ════════════════════════ TAB 1 — GRAPH VIEW ═════════════════════════════
    with tab_graph:
        hcol, gcol = st.columns([4, 1])
        with hcol:
            st.subheader(
                f"Knowledge Graph — {G.number_of_nodes()} nodes · {G.number_of_edges()} edges"
            )
        with gcol:
            graph_h = st.select_slider("Height px", [400, 500, 600, 700, 800], 600)

        try:
            html = _pyvis_html(G, ndf_g, height=graph_h)
            st.components.v1.html(html, height=graph_h + 10, scrolling=False)
        except ImportError:
            st.error("PyVis not installed. Run: `pip install pyvis`")

        with st.expander("📋 Edge table"):
            show_cols = [c for c in
                         ["from_id","to_id","relation","impact_score","confidence","date","reasoning"]
                         if c in edf_g.columns]
            st.dataframe(
                edf_g[show_cols].sort_values("date").reset_index(drop=True),
                use_container_width=True,
            )

    # ════════════════════════ TAB 2 — TEMPORAL ═══════════════════════════════
    with tab_time:
        st.subheader("⏱️ Temporal Analysis")

        if edges_df.empty:
            st.info("No edge data loaded.")
        else:
            # ── Event timeline scatter ──────────────────────────────────────
            evt_rows = []
            for eid, em in event_meta.items():
                d = em["date"]
                if date_range[0] and date_range[1]:
                    try:
                        ed = datetime.strptime(d, "%Y-%m-%d").date()
                        if not (date_range[0] <= ed <= date_range[1]):
                            continue
                    except Exception:
                        pass
                evt_rows.append({
                    "date":       d,
                    "type":       em["type"],
                    "name":       em["name"][:70],
                    "severity":   em["severity"],
                    "confidence": em["confidence"],
                })
            if evt_rows:
                evt_df = pd.DataFrame(evt_rows)
                evt_df["datetime"] = pd.to_datetime(evt_df["date"])
                fig_evts = px.scatter(
                    evt_df, x="datetime", y="type",
                    size="severity", color="type",
                    hover_name="name", hover_data=["confidence", "date"],
                    title="Events Over Time by Type",
                    height=320,
                    size_max=22,
                )
                fig_evts.update_layout(showlegend=False, yaxis_title="")
                st.plotly_chart(fig_evts, use_container_width=True)

            # ── Monthly edge count bar ──────────────────────────────────────
            edf_time = edf_g.copy()
            if not edf_time.empty:
                monthly = (
                    edf_time.groupby(["month", "relation"])
                    .size()
                    .reset_index(name="count")
                    .sort_values("month")
                )
                fig_monthly = px.bar(
                    monthly, x="month", y="count", color="relation",
                    color_discrete_map=EDGE_COLORS,
                    title="Edge Count per Month (filtered view)",
                    height=340,
                )
                fig_monthly.update_xaxes(tickangle=45)
                st.plotly_chart(fig_monthly, use_container_width=True)

                # ── Impact score scatter over time ──────────────────────────
                causal_t = edf_time[edf_time["causal_label"] == 1]
                if not causal_t.empty:
                    fig_imp = px.scatter(
                        causal_t, x="datetime", y="impact_score",
                        color="relation",
                        size=(causal_t["confidence"] * 14 + 4).clip(upper=20),
                        hover_data=["from_id", "to_id", "reasoning"],
                        color_discrete_map=EDGE_COLORS,
                        title="Causal Impact Score Over Time",
                        height=360,
                    )
                    fig_imp.add_hline(y=0, line_dash="dash", line_color="rgba(200,50,50,0.6)")
                    fig_imp.update_layout(showlegend=True)
                    st.plotly_chart(fig_imp, use_container_width=True)

                # ── Macro context heat (from events) ───────────────────────
                macro_rows = []
                for evt in _raw_events_cached():
                    mc = evt.get("macro_context", {})
                    if mc:
                        row = {"date": evt["event_date"]}
                        row.update({k: v for k, v in mc.items() if isinstance(v, (int, float))})
                        macro_rows.append(row)
                if macro_rows:
                    mdf = pd.DataFrame(macro_rows).sort_values("date")
                    macro_indicators = [c for c in mdf.columns if c != "date"]
                    if macro_indicators:
                        indicator = st.selectbox(
                            "Macro indicator to plot", macro_indicators,
                            index=macro_indicators.index("VIX") if "VIX" in macro_indicators else 0,
                        )
                        fig_macro = px.line(
                            mdf, x="date", y=indicator,
                            title=f"{indicator} Over Time (event snapshots)",
                            markers=True, height=300,
                            color_discrete_sequence=["#8172B2"],
                        )
                        st.plotly_chart(fig_macro, use_container_width=True)

    # ════════════════════════ TAB 3 — CAUSALITY ══════════════════════════════
    with tab_causal:
        st.subheader("🔴 Causal Analysis")

        causal_e  = edf_g[edf_g["causal_label"] == 1]
        static_e  = edf_g[edf_g["causal_label"] == 0]
        pos_causal = causal_e[causal_e["impact_score"] > 0]
        neg_causal = causal_e[causal_e["impact_score"] <= 0]

        # ── KPIs ──────────────────────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Causal edges",    len(causal_e))
        k2.metric("Static edges",    len(static_e))
        k3.metric("Positive impacts", len(pos_causal), delta=None)
        k4.metric("Negative impacts", len(neg_causal), delta=None)

        c1, c2 = st.columns(2)
        with c1:
            # Balance pie
            if not causal_e.empty:
                bal_df = pd.DataFrame({
                    "Direction": ["Positive (score > 0)", "Negative (score ≤ 0)"],
                    "Count":     [len(pos_causal), len(neg_causal)],
                })
                fig_pie = px.pie(
                    bal_df, names="Direction", values="Count",
                    title="Causal Impact Balance",
                    color_discrete_sequence=["#55A868", "#C44E52"],
                )
                st.plotly_chart(fig_pie, use_container_width=True)

        with c2:
            # Impact score histogram
            if not causal_e.empty:
                fig_hist = px.histogram(
                    causal_e, x="impact_score", nbins=30,
                    color_discrete_sequence=["#DD8452"],
                    title="Impact Score Distribution",
                )
                fig_hist.add_vline(x=0, line_dash="dash", line_color="red")
                st.plotly_chart(fig_hist, use_container_width=True)

        # ── Top impacted nodes ─────────────────────────────────────────────
        if not causal_e.empty:
            top_targets = (
                causal_e.groupby("to_id")
                .agg(freq=("to_id","count"), avg_impact=("impact_score","mean"))
                .reset_index()
                .sort_values("freq", ascending=False)
                .head(25)
            )
            fig_targets = px.bar(
                top_targets, x="to_id", y="freq",
                color="avg_impact",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0,
                title="Top 25 Most Targeted Nodes (causal edges)",
                labels={"to_id":"Node","freq":"# Causal Edges","avg_impact":"Avg Impact"},
                height=380,
            )
            fig_targets.update_xaxes(tickangle=45)
            st.plotly_chart(fig_targets, use_container_width=True)

            # ── Top causal sources ──────────────────────────────────────────
            top_sources = (
                causal_e.groupby("from_id")
                .agg(freq=("from_id","count"), avg_impact=("impact_score","mean"))
                .reset_index()
                .sort_values("freq", ascending=False)
                .head(25)
            )
            fig_sources = px.bar(
                top_sources, x="from_id", y="freq",
                color="avg_impact",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0,
                title="Top 25 Most Causal Source Nodes",
                labels={"from_id":"Node","freq":"# Outgoing Causal Edges"},
                height=380,
            )
            fig_sources.update_xaxes(tickangle=45)
            st.plotly_chart(fig_sources, use_container_width=True)

        # ── Causal-only graph ─────────────────────────────────────────────
        st.markdown("#### Causal Subgraph")
        G_c, ndf_c, _ = build_graph(
            nodes_df, edges_df,
            node_types=sel_node_types, causal_only=True,
            ts_min=ts_min, ts_max=ts_max,
            max_nodes=max_nodes_g, max_edges=max_edges_g,
        )
        if G_c.number_of_nodes() > 0:
            try:
                html_c = _pyvis_html(G_c, ndf_c, height=520)
                st.components.v1.html(html_c, height=530, scrolling=False)
            except ImportError:
                st.error("PyVis not installed.")
        else:
            st.info("No causal edges match current filters.")

    # ════════════════════════ TAB 4 — SUBGRAPH ════════════════════════════════
    with tab_sub:
        st.subheader("🔍 Subgraph Explorer")

        all_ids = sorted(nodes_df["id"].tolist())
        default_idx = all_ids.index("talan") if "talan" in all_ids else 0

        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            center = st.selectbox("Center node", all_ids, index=default_idx)
        with sc2:
            k_hops = st.slider("K-hop radius", 1, 4, 2)
        with sc3:
            max_nb = st.slider("Max neighbors", 5, 120, 40)

        # Optional temporal cutoff for subgraph
        if not edges_df.empty:
            all_dates = sorted(edges_df["date"].unique())
            cutoff_date = st.select_slider(
                "Show only edges ≤ date",
                options=all_dates, value=all_dates[-1],
            )
            cutoff_ts = _date_to_ts(cutoff_date)
        else:
            cutoff_ts = None

        G_full, ndf_full, _ = build_graph(
            nodes_df, edges_df,
            max_nodes=400, max_edges=5000,
            ts_max=cutoff_ts,
        )
        G_sub = khop_subgraph(G_full, center, k=k_hops, max_nodes=max_nb)

        st.info(
            f"**{G_sub.number_of_nodes()}** nodes · **{G_sub.number_of_edges()}** edges "
            f"| Center: `{center}` | {k_hops}-hop"
        )

        if G_sub.number_of_nodes() > 0:
            try:
                html_sub = _pyvis_html(G_sub, nodes_df, highlight_node=center, height=560)
                st.components.v1.html(html_sub, height=570, scrolling=False)
            except ImportError:
                st.error("PyVis not installed.")

            # Neighbor table
            with st.expander("📋 Neighbor node details"):
                sub_node_ids = list(G_sub.nodes())
                nb_df = nodes_df[nodes_df["id"].isin(sub_node_ids)].copy()
                show_cols = [c for c in ["id","name","type","country","sector","revenue_eur_m","headcount"]
                             if c in nb_df.columns]
                st.dataframe(nb_df[show_cols].reset_index(drop=True), use_container_width=True)

            # Export
            with st.expander("💾 Export subgraph"):
                export = {
                    "center":    center,
                    "k_hops":    k_hops,
                    "cutoff":    cutoff_date if not edges_df.empty else None,
                    "nodes":     [
                        {k: v for k, v in G_sub.nodes[n].items() if v is not None}
                        for n in G_sub.nodes()
                    ],
                    "edges":     [
                        {"from": u, "to": v, **{k: str(d[k]) for k in d}}
                        for u, v, d in G_sub.edges(data=True)
                    ],
                }
                st.download_button(
                    "⬇️ Download JSON",
                    data=json.dumps(export, indent=2, ensure_ascii=False),
                    file_name=f"subgraph_{center}_{k_hops}hop.json",
                    mime="application/json",
                )
        else:
            st.warning(f"Node `{center}` not in the current graph. Widen the filters.")

    # ════════════════════════ TAB 5 — STATISTICS ══════════════════════════════
    with tab_stats:
        st.subheader("📊 Dataset Statistics")

        # ── Node type distribution ─────────────────────────────────────────
        sa, sb = st.columns(2)
        with sa:
            ntc = nodes_df["type"].value_counts().reset_index()
            ntc.columns = ["Type", "Count"]
            fig_nt = px.bar(
                ntc, x="Type", y="Count", color="Type",
                color_discrete_map=NODE_COLORS,
                title="Nodes per Type",
            )
            st.plotly_chart(fig_nt, use_container_width=True)

        with sb:
            if not edges_df.empty:
                etc = edges_df["relation"].value_counts().reset_index()
                etc.columns = ["Relation", "Count"]
                fig_et = px.bar(
                    etc, x="Relation", y="Count",
                    color="Relation",
                    color_discrete_map={**EDGE_COLORS},
                    title="Edges per Relation Type",
                )
                fig_et.update_xaxes(tickangle=45)
                st.plotly_chart(fig_et, use_container_width=True)

        sc, sd = st.columns(2)
        with sc:
            # Event type pie
            if event_meta:
                et_series = pd.Series([e["type"] for e in event_meta.values()])
                et_counts = et_series.value_counts().reset_index()
                et_counts.columns = ["Event Type", "Count"]
                fig_etpie = px.pie(
                    et_counts, names="Event Type", values="Count",
                    title="Events by Type",
                )
                st.plotly_chart(fig_etpie, use_container_width=True)

        with sd:
            # Degree distribution of main graph
            if G.number_of_nodes() > 0:
                degs = [d for _, d in G.degree()]
                fig_deg = px.histogram(
                    x=degs, nbins=30,
                    title="Degree Distribution (current view)",
                    labels={"x": "Degree"},
                    color_discrete_sequence=["#4C72B0"],
                )
                st.plotly_chart(fig_deg, use_container_width=True)

        # ── Severity distribution ──────────────────────────────────────────
        if event_meta:
            sev_df = pd.DataFrame([
                {"date": e["date"], "severity": e["severity"],
                 "type": e["type"], "name": e["name"][:60]}
                for e in event_meta.values()
            ]).sort_values("date")
            fig_sev = px.bar(
                sev_df, x="date", y="severity", color="type",
                hover_name="name",
                title="Event Severity Over Time",
                height=320,
            )
            fig_sev.update_xaxes(tickangle=45)
            st.plotly_chart(fig_sev, use_container_width=True)

        # ── Company table ──────────────────────────────────────────────────
        with st.expander("🏢 Company nodes"):
            cdf = nodes_df[nodes_df["type"] == "Company"]
            show = [c for c in ["id","name","country","sector","ticker","revenue_eur_m","headcount"]
                    if c in cdf.columns]
            st.dataframe(
                cdf[show].sort_values("revenue_eur_m", ascending=False).reset_index(drop=True),
                use_container_width=True,
            )

        # ── Full event list ────────────────────────────────────────────────
        with st.expander("📅 All events"):
            evm_df = pd.DataFrame([{"id": k, **v} for k, v in event_meta.items()])
            show = [c for c in ["id","date","type","name","severity","confidence"]
                    if c in evm_df.columns]
            st.dataframe(evm_df[show].sort_values("date").reset_index(drop=True),
                         use_container_width=True)

        # ── GNN training label balance (from gnn_training_samples.json) ────
        gnn_path = DATA_DIR / "gnn_training_samples.json"
        if gnn_path.exists():
            with st.expander("🤖 GNN Training Sample Stats"):
                with open(gnn_path, encoding="utf-8") as fh:
                    samples = json.load(fh)
                if isinstance(samples, list) and samples:
                    impacts = [s.get("target_impact", s.get("gnn_training", {}).get("target_impact", 0))
                               for s in samples if isinstance(s, dict)]
                    if impacts:
                        pos = sum(1 for x in impacts if x > 0)
                        neg = sum(1 for x in impacts if x <= 0)
                        st.metric("Positive samples (impact > 0)", pos)
                        st.metric("Negative samples (impact ≤ 0)", neg)
                        fig_gnn = px.histogram(
                            x=impacts, nbins=30,
                            title="GNN Target Impact Distribution",
                            labels={"x": "Target Impact"},
                            color_discrete_sequence=["#55A868"],
                        )
                        fig_gnn.add_vline(x=0, line_dash="dash", line_color="red")
                        st.plotly_chart(fig_gnn, use_container_width=True)


    # ════════════════════════ TAB 6 — IMPACT SCORER ══════════════════════════
    with tab_scorer:
        st.subheader("🎯 Continuous Financial Impact Scorer")
        st.caption(
            "Replaces the binary GNN output with a calibrated continuous score "
            "in the range −65 % → +65 %, using graph-propagation reasoning."
        )

        if not _SCORER_AVAILABLE:
            st.error(
                f"⚠️ `impact_scorer.py` could not be imported: `{_imp_err_msg}`. "
                "Make sure it lives in the same directory as this file."
            )
        else:
            raw_events = _raw_events_cached()
            if not raw_events:
                st.warning("No events loaded.")
            else:
                scorer = _ImpactScorer()

                # ── Mode selector ─────────────────────────────────────────────
                mode = st.radio(
                    "Mode", ["Single Event", "Batch — all events"],
                    horizontal=True, key="scorer_mode",
                )

                # ══════════════ SINGLE EVENT MODE ════════════════════════════
                if mode == "Single Event":
                    evt_options = {
                        f"{e['event_id']} · {e['event_date']} · {e['event_name'][:60]}": e
                        for e in raw_events
                    }
                    chosen_key = st.selectbox(
                        "Select event", list(evt_options.keys()), key="scorer_evt"
                    )
                    chosen_evt = evt_options[chosen_key]

                    target_node = st.text_input(
                        "Target node ID", value="talan", key="scorer_target"
                    )

                    # ── Manual overrides ──────────────────────────────────────
                    with st.expander("⚙️ Override binary signal"):
                        ov_col1, ov_col2 = st.columns(2)
                        with ov_col1:
                            override_binary = st.selectbox(
                                "model_binary_output", [None, 0, 1],
                                format_func=lambda x: "auto (from data)" if x is None else str(x),
                                key="scorer_binary",
                            )
                        with ov_col2:
                            override_dir = st.selectbox(
                                "direction_sign", [None, +1, -1],
                                format_func=lambda x: "auto (from data)" if x is None else ("+1 (positive)" if x == 1 else "−1 (negative)"),
                                key="scorer_dir",
                            )

                    if st.button("▶ Score this event", key="scorer_run"):
                        with st.spinner("Scoring …"):
                            inp = _build_scorer_input(chosen_evt, target=target_node)
                            if override_binary is not None:
                                inp.model_binary_output = override_binary
                            if override_dir is not None:
                                inp.direction_sign = override_dir
                            out = scorer.score(inp)

                        bd = out.breakdown

                        # ── Gauge ─────────────────────────────────────────────
                        GAUGE_STEPS = [
                            {"range": [-65, -40], "color": "#8B0000"},
                            {"range": [-40, -15], "color": "#CC3333"},
                            {"range": [-15,  -5], "color": "#FF8C00"},
                            {"range": [ -5,   5], "color": "#888888"},
                            {"range": [  5,  15], "color": "#90EE90"},
                            {"range": [ 15,  40], "color": "#228B22"},
                            {"range": [ 40,  65], "color": "#006400"},
                        ]
                        fig_gauge = go.Figure(go.Indicator(
                            mode="gauge+number+delta",
                            value=out.estimated_impact_percent,
                            delta={"reference": 0, "valueformat": ".1f",
                                   "suffix": "%"},
                            number={"suffix": "%", "valueformat": ".2f"},
                            title={"text": f"{out.impact_label.replace('_', ' ').title()}",
                                   "font": {"size": 18}},
                            gauge={
                                "axis": {"range": [-65, 65],
                                         "ticksuffix": "%",
                                         "tickmode": "linear", "dtick": 13},
                                "bar": {"color": "#FFD700", "thickness": 0.25},
                                "steps": GAUGE_STEPS,
                                "threshold": {
                                    "line": {"color": "white", "width": 3},
                                    "thickness": 0.8,
                                    "value": out.estimated_impact_percent,
                                },
                            },
                        ))
                        fig_gauge.update_layout(
                            height=320, margin=dict(t=60, b=20, l=20, r=20),
                            paper_bgcolor="#1a1a2e", font_color="white",
                        )

                        # ── Waterfall ─────────────────────────────────────────
                        wf_labels = [
                            "Base\nchain score",
                            "Entity\nimportance",
                            "Sector\namplification",
                            "Confidence\nadjustment",
                            "Time\nhorizon",
                            "Propagation\nbreadth",
                            "Direction\ncorrection",
                            "FINAL",
                        ]
                        wf_values = [
                            bd.base_raw,
                            bd.entity_delta,
                            bd.sector_delta,
                            bd.confidence_delta,
                            bd.horizon_delta,
                            bd.breadth_delta,
                            bd.direction_correction,
                            bd.final_pct,
                        ]
                        wf_measures = ["absolute"] + ["relative"] * 6 + ["total"]

                        fig_wf = go.Figure(go.Waterfall(
                            orientation="v",
                            measure=wf_measures,
                            x=wf_labels,
                            y=wf_values,
                            text=[f"{v:+.1f}%" for v in wf_values],
                            textposition="outside",
                            connector={"line": {"color": "rgba(200,200,200,0.3)"}},
                            increasing={"marker": {"color": "#55A868"}},
                            decreasing={"marker": {"color": "#C44E52"}},
                            totals={"marker": {"color": "#FFD700"}},
                        ))
                        fig_wf.add_hline(y=0, line_dash="dash",
                                         line_color="rgba(255,255,255,0.3)")
                        fig_wf.update_layout(
                            title="Score Build-up (waterfall)",
                            yaxis_title="Impact (%)",
                            yaxis_ticksuffix="%",
                            height=380,
                            paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e",
                            font_color="white",
                            margin=dict(t=50, b=10),
                        )

                        # ── Layout: gauge left, waterfall right ───────────────
                        gc, wc = st.columns([1, 2])
                        with gc:
                            st.plotly_chart(fig_gauge, use_container_width=True)
                            # KPI pills
                            label_color = {
                                "strong_negative": "#8B0000",
                                "moderate_negative": "#CC3333",
                                "weak_negative": "#FF8C00",
                                "neutral": "#888888",
                                "weak_positive": "#90EE90",
                                "moderate_positive": "#228B22",
                                "strong_positive": "#006400",
                            }.get(out.impact_label, "#555")
                            st.markdown(
                                f'<div style="text-align:center;padding:8px;'
                                f'background:{label_color};border-radius:8px;'
                                f'font-weight:bold;font-size:1.1em;color:white;">'
                                f'{out.impact_label.replace("_", " ").upper()}</div>',
                                unsafe_allow_html=True,
                            )
                            st.metric("Scorer confidence", f"{out.confidence:.3f}")
                        with wc:
                            st.plotly_chart(fig_wf, use_container_width=True)

                        # ── Breakdown table ───────────────────────────────────
                        st.markdown("#### Factor Breakdown")
                        factor_rows = [
                            ("Entity importance multiplier",   f"×{bd.entity_multiplier:.3f}",   f"{bd.entity_delta:+.2f}%"),
                            ("Sector amplification factor",    f"×{bd.sector_amplifier:.3f}",    f"{bd.sector_delta:+.2f}%"),
                            ("Confidence factor",              f"×{bd.confidence_factor:.3f}",   f"{bd.confidence_delta:+.2f}%"),
                            ("Time-horizon factor",            f"×{bd.horizon_factor:.3f}",      f"{bd.horizon_delta:+.2f}%"),
                            ("Propagation breadth factor",     f"×{bd.breadth_factor:.3f}",      f"{bd.breadth_delta:+.2f}%"),
                        ]
                        factor_df = pd.DataFrame(
                            factor_rows, columns=["Factor", "Multiplier", "Δ Impact"]
                        )
                        st.dataframe(factor_df, use_container_width=True, hide_index=True)

                        # ── Explanation ───────────────────────────────────────
                        st.markdown("#### Explanation")
                        st.info(out.explanation)

                        # ── Propagation paths detail ──────────────────────────
                        inp_obj = _build_scorer_input(chosen_evt, target=target_node)
                        if inp_obj.propagation_paths:
                            with st.expander(f"🔗 {len(inp_obj.propagation_paths)} propagation path(s)"):
                                path_rows = []
                                for p in inp_obj.propagation_paths:
                                    chain = (
                                        p.source
                                        + (" → " + " → ".join(p.intermediate_nodes) if p.intermediate_nodes else "")
                                        + f" → {p.target}"
                                    )
                                    path_rows.append({
                                        "Chain": chain,
                                        "chain_score": f"{p.chain_score:+.3f}",
                                        "confidence":  f"{p.confidence:.3f}",
                                        "horizon":     p.time_horizon,
                                        "relations":   ", ".join(p.relation_types),
                                    })
                                st.dataframe(
                                    pd.DataFrame(path_rows),
                                    use_container_width=True, hide_index=True,
                                )

                        # ── JSON output ───────────────────────────────────────
                        with st.expander("📄 Raw JSON output"):
                            st.code(
                                json.dumps({
                                    "estimated_impact_percent": out.estimated_impact_percent,
                                    "impact_label":             out.impact_label,
                                    "confidence":               out.confidence,
                                    "explanation":              out.explanation,
                                }, indent=2, ensure_ascii=False),
                                language="json",
                            )

                # ══════════════ BATCH MODE ════════════════════════════════════
                else:
                    batch_target = st.text_input(
                        "Target node ID", value="talan", key="batch_target"
                    )
                    if st.button("▶ Score all events", key="batch_run"):
                        with st.spinner(f"Scoring {len(raw_events)} events …"):
                            results = _batch_score(raw_events, target=batch_target)

                        res_df = pd.DataFrame([
                            r for r in results if "error" not in r
                        ])
                        if res_df.empty:
                            st.error("All events failed to score.")
                        else:
                            # ── Overview scatter ──────────────────────────────
                            fig_batch = px.scatter(
                                res_df,
                                x="event_date",
                                y="estimated_impact_pct",
                                color="impact_label",
                                symbol="event_type",
                                size=res_df["confidence"] * 18 + 4,
                                hover_name="event_name",
                                hover_data=["event_id", "confidence",
                                            "measured_impact_1m", "measured_direction"],
                                color_discrete_map={
                                    "strong_negative":   "#8B0000",
                                    "moderate_negative": "#CC3333",
                                    "weak_negative":     "#FF8C00",
                                    "neutral":           "#888888",
                                    "weak_positive":     "#90EE90",
                                    "moderate_positive": "#228B22",
                                    "strong_positive":   "#006400",
                                },
                                title=f"Estimated Impact Scores — all events (target: {batch_target})",
                                height=450,
                            )
                            fig_batch.add_hline(y=0, line_dash="dash",
                                                line_color="rgba(255,255,255,0.4)")
                            st.plotly_chart(fig_batch, use_container_width=True)

                            # ── Label distribution bar ────────────────────────
                            label_order = [l for _, _, l in _IMPACT_LABELS]
                            lc = (
                                res_df["impact_label"]
                                .value_counts()
                                .reindex(label_order, fill_value=0)
                                .reset_index()
                            )
                            lc.columns = ["Label", "Count"]
                            fig_lc = px.bar(
                                lc, x="Label", y="Count",
                                color="Label",
                                color_discrete_map={
                                    "strong_negative":   "#8B0000",
                                    "moderate_negative": "#CC3333",
                                    "weak_negative":     "#FF8C00",
                                    "neutral":           "#888888",
                                    "weak_positive":     "#90EE90",
                                    "moderate_positive": "#228B22",
                                    "strong_positive":   "#006400",
                                },
                                title="Impact Label Distribution",
                                height=320,
                            )
                            fig_lc.update_layout(showlegend=False)
                            st.plotly_chart(fig_lc, use_container_width=True)

                            # ── Calibration check: scorer vs measured ─────────
                            cal_df = res_df.dropna(
                                subset=["estimated_impact_pct", "measured_impact_1m"]
                            ).copy()
                            if not cal_df.empty:
                                cal_df["measured_pct"] = cal_df["measured_impact_1m"] * 100
                                fig_cal = px.scatter(
                                    cal_df,
                                    x="measured_pct",
                                    y="estimated_impact_pct",
                                    hover_name="event_name",
                                    hover_data=["event_id", "impact_label"],
                                    trendline="ols",
                                    title="Calibration: Scorer Estimate vs Measured Impact (×100)",
                                    labels={
                                        "measured_pct":          "Measured impact_1m × 100 (%)",
                                        "estimated_impact_pct":  "Scorer estimate (%)",
                                    },
                                    height=400,
                                    color="impact_label",
                                    color_discrete_map={
                                        "strong_negative":   "#8B0000",
                                        "moderate_negative": "#CC3333",
                                        "weak_negative":     "#FF8C00",
                                        "neutral":           "#888888",
                                        "weak_positive":     "#90EE90",
                                        "moderate_positive": "#228B22",
                                        "strong_positive":   "#006400",
                                    },
                                )
                                fig_cal.add_shape(
                                    type="line",
                                    x0=cal_df["measured_pct"].min(),
                                    y0=cal_df["measured_pct"].min(),
                                    x1=cal_df["measured_pct"].max(),
                                    y1=cal_df["measured_pct"].max(),
                                    line=dict(color="rgba(255,255,255,0.3)", dash="dash"),
                                )
                                st.plotly_chart(fig_cal, use_container_width=True)

                            # ── Full results table ────────────────────────────
                            with st.expander("📋 Full results table"):
                                show = [c for c in [
                                    "event_id","event_date","event_type","event_name",
                                    "estimated_impact_pct","impact_label","confidence",
                                    "measured_impact_1m","measured_direction",
                                ] if c in res_df.columns]
                                st.dataframe(
                                    res_df[show].sort_values("event_date"),
                                    use_container_width=True, hide_index=True,
                                )

                            # ── Download ──────────────────────────────────────
                            st.download_button(
                                "⬇️ Download results JSON",
                                data=json.dumps(results, indent=2, ensure_ascii=False),
                                file_name=f"impact_scores_{batch_target}.json",
                                mime="application/json",
                            )


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS  (cached raw events for macro context panel)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _raw_events_cached() -> list[dict]:
    p = DATA_DIR / "kg_events.json"
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
