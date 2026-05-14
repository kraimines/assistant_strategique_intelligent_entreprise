"""Unit tests for the v3 propagation engine.

These tests are pure-Python — they do NOT require Neo4j, Postgres, or the
LLM. The PathRanker / HubPenalty / EdgeTypePolicy / PlausibilityScorer
should all behave deterministically when given hand-built fixtures.
"""
from __future__ import annotations

import pytest

from app.services.market_analysis.policy.edge_type_policy import EdgeTypePolicy
from app.services.market_analysis.scoring.hub_penalty import HubPenalty
from app.services.market_analysis.scoring.temporal_decay import TemporalDecay
from app.services.market_analysis.scoring.calibration import TGATCalibrator
from app.services.market_analysis.scoring.plausibility import PlausibilityScorer
from app.services.market_analysis.ranking.path_ranker import PathRanker


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def edge_policy():
    return EdgeTypePolicy.from_dict({
        ("CAUSES_IMPACT_ON", "Competitor", "Company"): {"alpha": 1.0, "half_life_days": 60, "category": "competitive"},
        ("CAUSES_IMPACT_ON", "Sector",     "Company"): {"alpha": 0.7, "half_life_days": 90, "category": "sector"},
        ("CAUSES_IMPACT_ON", "Concept",    "Company"): {"alpha": 0.3, "half_life_days": 90, "category": "generic"},
        ("CAUSES_IMPACT_ON", "Country",    "Concept"): {"alpha": 0.0, "half_life_days": 180, "category": "blocked"},
        ("MENTIONS",         "News",       "Company"): {"alpha": 0.3, "half_life_days": 14, "category": "evidence"},
    })


@pytest.fixture
def talan_profile():
    return {
        "company": "Talan",
        "country": "France",
        "geos": ["France", "European Union"],
        "sectors_served": ["Banking & Finance", "Insurance", "Public Sector"],
        "competitors": ["Capgemini", "Sopra Steria", "Atos", "Anthropic"],
        "business_units": [
            {
                "name": "Talan GenAI Studio",
                "slug": "bu-genai-studio",
                "revenue_share": 0.18,
                "sector_focus": ["Artificial Intelligence", "IT Services"],
                "geo_focus": ["France", "European Union"],
                "depends_on": ["OpenAI API", "Anthropic API"],
                "serves": ["European Banking Clients"],
            },
            {
                "name": "Talan Banking & Insurance Consulting",
                "slug": "bu-banking-insurance",
                "revenue_share": 0.32,
                "sector_focus": ["Banking & Finance", "Insurance"],
                "geo_focus": ["France", "European Union"],
                "depends_on": [],
                "serves": ["European Banking Clients"],
            },
        ],
    }


@pytest.fixture
def snapshot_with_hub():
    """Tiny snapshot — one specific node and one giant generic hub."""
    nodes = [
        {"id": "1", "slug": "talan",     "name": "Talan",     "labels": ["Company"],   "properties": {}},
        {"id": "2", "slug": "anthropic", "name": "Anthropic", "labels": ["Competitor"], "properties": {}},
        {"id": "3", "slug": "concept-ai","name": "AI",        "labels": ["Concept"],   "properties": {"is_generic_hub": True}},
    ]
    edges = [
        {"from": "3", "to": "1", "type": "CAUSES_IMPACT_ON"},
        {"from": "3", "to": "2", "type": "CAUSES_IMPACT_ON"},
        {"from": "2", "to": "1", "type": "CAUSES_IMPACT_ON"},
    ]
    return {"nodes": nodes, "edges": edges}


# ── EdgeTypePolicy ───────────────────────────────────────────────────────────

def test_edge_policy_alpha_lookup(edge_policy):
    assert edge_policy.alpha("CAUSES_IMPACT_ON", "Competitor", "Company") == 1.0
    assert edge_policy.alpha("CAUSES_IMPACT_ON", "Concept",    "Company") == 0.3
    assert edge_policy.alpha("CAUSES_IMPACT_ON", "Country",    "Concept") == 0.0


def test_edge_policy_default_for_unknown_pair(edge_policy):
    # Unknown pair falls back to default α=0.5, not crash
    assert edge_policy.alpha("FOO", "Bar", "Baz") == 0.5


def test_edge_policy_gate_drops_blocked(edge_policy):
    edges = [
        {"type": "CAUSES_IMPACT_ON", "src_label": "Competitor", "dst_label": "Company"},
        {"type": "CAUSES_IMPACT_ON", "src_label": "Country",    "dst_label": "Concept"},  # α=0
    ]
    kept = edge_policy.gate_edges(edges)
    assert len(kept) == 1
    assert kept[0]["src_label"] == "Competitor"
    assert kept[0]["relation_strength"] == 1.0


# ── HubPenalty ───────────────────────────────────────────────────────────────

def test_hub_penalty_specific_node_high_h(snapshot_with_hub):
    h = HubPenalty.fit(snapshot_with_hub)
    specific = next(n for n in snapshot_with_hub["nodes"] if n["name"] == "Anthropic")
    generic  = next(n for n in snapshot_with_hub["nodes"] if n["name"] == "AI")
    assert h.h(specific) > h.h(generic)


def test_hub_penalty_concept_label_treated_as_generic(snapshot_with_hub):
    h = HubPenalty.fit(snapshot_with_hub)
    concept_node = next(n for n in snapshot_with_hub["nodes"] if n["labels"] == ["Concept"])
    assert h.is_generic(concept_node) is True


# ── TemporalDecay ────────────────────────────────────────────────────────────

def test_temporal_decay_uses_freshness_when_present():
    d = TemporalDecay()
    edge = {"freshness_score": 0.42, "type": "CAUSES_IMPACT_ON"}
    assert d.tau(edge) == pytest.approx(0.42)


def test_temporal_decay_geo_mean_path_freshness():
    d = TemporalDecay()
    edges = [{"freshness_score": 0.9}, {"freshness_score": 0.1}]
    assert d.path_freshness(edges) == pytest.approx(0.3, rel=0.01)


# ── Calibrator ───────────────────────────────────────────────────────────────

def test_calibrator_identity_when_unfitted():
    c = TGATCalibrator()
    # Not fitted ⇒ sigmoid squash (∈[0,1]) but monotone in raw
    assert c.transform(0.0) == pytest.approx(0.5, abs=0.01)
    assert c.transform(2.0) > c.transform(0.0)


# ── Plausibility ─────────────────────────────────────────────────────────────

def test_plausibility_high_for_competitor_to_talan(talan_profile):
    p = PlausibilityScorer(talan_profile=talan_profile, llm_judge=None)
    path = {
        "source_name": "Anthropic Claude 4 launch",
        "steps": [
            {"node_name": "Anthropic", "node_type": "Competitor", "relation_type": "COMPETES_WITH"},
            {"node_name": "Talan",     "node_type": "Company",    "relation_type": "CAUSES_IMPACT_ON"},
        ],
    }
    res = p.score(path)
    assert res.score >= 0.5  # competitor + sector overlap satisfied via dependency_flag


def test_plausibility_low_for_australia_inflation_to_talan(talan_profile):
    p = PlausibilityScorer(talan_profile=talan_profile, llm_judge=None)
    path = {
        "source_name": "Australia inflation spike",
        "steps": [
            {"node_name": "Australia",         "node_type": "Country", "relation_type": "OPERATES_IN",      "node_properties": {"country": "Australia"}},
            {"node_name": "Inflation concept", "node_type": "Concept", "relation_type": "CAUSES_IMPACT_ON", "node_properties": {}},
            {"node_name": "Talan",             "node_type": "Company", "relation_type": "CAUSES_IMPACT_ON", "node_properties": {}},
        ],
    }
    res = p.score(path)
    assert res.score < 0.35  # no sector overlap, no geo overlap, no dependency, no exposure


# ── PathRanker integration ──────────────────────────────────────────────────

def _make_ranker(edge_policy, talan_profile, snapshot):
    return PathRanker(
        hub_penalty=HubPenalty.fit(snapshot),
        temporal_decay=TemporalDecay(edge_policy=edge_policy),
        plausibility_scorer=PlausibilityScorer(talan_profile=talan_profile, llm_judge=None),
        calibrator=TGATCalibrator(),
        edge_policy=edge_policy,
    )


def test_path_ranker_filters_implausible_chain(edge_policy, talan_profile, snapshot_with_hub):
    ranker = _make_ranker(edge_policy, talan_profile, snapshot_with_hub)

    bad_path = {
        "source_name": "Australia inflation spike",
        "chain_score": 0.4,
        "chain_conf":  0.5,
        "hops":        3,
        "steps": [
            {"node_name": "Australia",         "node_type": "Country",
             "relation_type": "CAUSES_IMPACT_ON", "src_label": "Country", "dst_label": "Concept",
             "relation_strength": 0.0, "freshness_score": 0.5, "edge_confidence": 0.5,
             "category": "blocked", "impact_score": 0.1, "time_horizon": "short_term", "reason": ""},
            {"node_name": "AI", "node_type": "Concept",
             "relation_type": "CAUSES_IMPACT_ON", "src_label": "Concept", "dst_label": "Company",
             "relation_strength": 0.3, "freshness_score": 0.5, "edge_confidence": 0.5,
             "category": "generic", "impact_score": 0.1, "time_horizon": "short_term", "reason": ""},
            {"node_name": "Talan", "node_type": "Company",
             "relation_type": "CAUSES_IMPACT_ON", "src_label": "Concept", "dst_label": "Company",
             "relation_strength": 0.3, "freshness_score": 0.5, "edge_confidence": 0.5,
             "category": "generic", "impact_score": 0.1, "time_horizon": "short_term", "reason": ""},
        ],
    }
    s = ranker.score_path(bad_path)
    assert s.rejected is True
    assert "blocked_edge" in s.rejection_reasons or "plausibility<0.35" in s.rejection_reasons


def test_path_ranker_keeps_competitor_chain(edge_policy, talan_profile, snapshot_with_hub):
    ranker = _make_ranker(edge_policy, talan_profile, snapshot_with_hub)

    good_path = {
        "source_name": "Anthropic Claude 4 launch",
        "chain_score": 0.6,
        "chain_conf":  0.8,
        "hops":        1,
        "steps": [
            {"node_name": "Anthropic", "node_type": "Competitor",
             "relation_type": "CAUSES_IMPACT_ON", "src_label": "Competitor", "dst_label": "Company",
             "relation_strength": 1.0, "freshness_score": 0.9, "edge_confidence": 0.85,
             "category": "competitive", "impact_score": 0.6, "time_horizon": "short_term",
             "reason": "Direct competition in GenAI consulting"},
            {"node_name": "Talan", "node_type": "Company",
             "relation_type": "CAUSES_IMPACT_ON", "src_label": "Competitor", "dst_label": "Company",
             "relation_strength": 1.0, "freshness_score": 0.9, "edge_confidence": 0.85,
             "category": "competitive", "impact_score": 0.6, "time_horizon": "short_term",
             "reason": ""},
        ],
    }
    s = ranker.score_path(good_path)
    assert s.rejected is False, f"Unexpectedly rejected: {s.rejection_reasons}"
    assert s.weighted_score > 0
    assert s.plausibility >= 0.5


def test_path_ranker_top_k_orders_by_weighted_score(edge_policy, talan_profile, snapshot_with_hub):
    ranker = _make_ranker(edge_policy, talan_profile, snapshot_with_hub)
    p1 = {
        "source_name": "Capgemini layoffs",
        "chain_score": 0.5, "chain_conf": 0.7, "hops": 1,
        "steps": [
            {"node_name": "Capgemini", "node_type": "Competitor",
             "relation_type": "CAUSES_IMPACT_ON", "src_label": "Competitor", "dst_label": "Company",
             "relation_strength": 1.0, "freshness_score": 0.9, "edge_confidence": 0.8,
             "category": "competitive", "impact_score": 0.5, "time_horizon": "short_term", "reason": ""},
            {"node_name": "Talan", "node_type": "Company", "relation_type": "CAUSES_IMPACT_ON",
             "src_label": "Competitor", "dst_label": "Company",
             "relation_strength": 1.0, "freshness_score": 0.9, "edge_confidence": 0.8,
             "category": "competitive", "impact_score": 0.5, "time_horizon": "short_term", "reason": ""},
        ],
    }
    p2 = {
        "source_name": "Sector trend",
        "chain_score": 0.2, "chain_conf": 0.5, "hops": 1,
        "steps": [
            {"node_name": "IT Services", "node_type": "Sector",
             "relation_type": "CAUSES_IMPACT_ON", "src_label": "Sector", "dst_label": "Company",
             "relation_strength": 0.7, "freshness_score": 0.6, "edge_confidence": 0.5,
             "category": "sector", "impact_score": 0.2, "time_horizon": "medium_term", "reason": ""},
            {"node_name": "Talan", "node_type": "Company", "relation_type": "CAUSES_IMPACT_ON",
             "src_label": "Sector", "dst_label": "Company",
             "relation_strength": 0.7, "freshness_score": 0.6, "edge_confidence": 0.5,
             "category": "sector", "impact_score": 0.2, "time_horizon": "medium_term", "reason": ""},
        ],
    }
    kept, _ = ranker.rank([p2, p1], top_k=2)
    if len(kept) == 2:
        assert kept[0].weighted_score >= kept[1].weighted_score
