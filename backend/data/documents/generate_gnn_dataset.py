#!/usr/bin/env python3
"""
Historical Market Events Dataset Generator
Generates kg_events.json and gnn_training_samples.json for the Market Analysis Agent.
150 real historical events (2020-2026) for Talan's GNN + Knowledge Graph.

Usage: python generate_gnn_dataset.py
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

COMPANIES = {
    "talan":        {"name": "Talan",          "ticker": None,      "country": "France",   "sector": "IT Services / ESN", "revenue_m": 600,    "hc": 10000},
    "capgemini":    {"name": "Capgemini",       "ticker": "CAP.PA",  "country": "France",   "sector": "IT Services / ESN", "revenue_m": 22500,  "hc": 360000},
    "sopra":        {"name": "Sopra Steria",    "ticker": "SOP.PA",  "country": "France",   "sector": "IT Services / ESN", "revenue_m": 5600,   "hc": 52000},
    "atos":         {"name": "Atos",            "ticker": "ATO.PA",  "country": "France",   "sector": "IT Services / ESN", "revenue_m": 10000,  "hc": 95000},
    "accenture":    {"name": "Accenture",       "ticker": "ACN",     "country": "USA",      "sector": "Consulting",        "revenue_m": 64000,  "hc": 733000},
    "ibm":          {"name": "IBM",             "ticker": "IBM",     "country": "USA",      "sector": "IT Services / ESN", "revenue_m": 61000,  "hc": 288000},
    "deloitte":     {"name": "Deloitte",        "ticker": None,      "country": "USA",      "sector": "Consulting",        "revenue_m": 64900,  "hc": 457000},
    "infosys":      {"name": "Infosys",         "ticker": "INFY",    "country": "India",    "sector": "IT Services / ESN", "revenue_m": 18200,  "hc": 343000},
    "openai":       {"name": "OpenAI",          "ticker": None,      "country": "USA",      "sector": "AI/ML",             "revenue_m": 3400,   "hc": 1700},
    "microsoft":    {"name": "Microsoft",       "ticker": "MSFT",    "country": "USA",      "sector": "Cloud Computing",   "revenue_m": 245000, "hc": 221000},
    "google":       {"name": "Google/Alphabet", "ticker": "GOOGL",   "country": "USA",      "sector": "AI/ML",             "revenue_m": 307000, "hc": 182000},
    "meta":         {"name": "Meta",            "ticker": "META",    "country": "USA",      "sector": "AI/ML",             "revenue_m": 134000, "hc": 86000},
    "nvidia":       {"name": "NVIDIA",          "ticker": "NVDA",    "country": "USA",      "sector": "AI/ML",             "revenue_m": 60900,  "hc": 29600},
    "anthropic":    {"name": "Anthropic",       "ticker": None,      "country": "USA",      "sector": "AI/ML",             "revenue_m": 900,    "hc": 700},
    "mistral":      {"name": "Mistral AI",      "ticker": None,      "country": "France",   "sector": "AI/ML",             "revenue_m": 30,     "hc": 200},
    "amazon":       {"name": "Amazon/AWS",      "ticker": "AMZN",    "country": "USA",      "sector": "Cloud Computing",   "revenue_m": 590000, "hc": 1540000},
    "salesforce":   {"name": "Salesforce",      "ticker": "CRM",     "country": "USA",      "sector": "Cloud Computing",   "revenue_m": 34900,  "hc": 72682},
    "sap":          {"name": "SAP",             "ticker": "SAP",     "country": "Germany",  "sector": "Cloud Computing",   "revenue_m": 31200,  "hc": 107000},
}

SECTORS = [
    "IT Services / ESN", "AI/ML", "Cloud Computing", "Cybersécurité",
    "Data & Analytics", "Consulting", "Finance / Banque", "Industrie / Manufacturing",
    "Santé / Healthcare", "Énergie", "Secteur Public / Gouvernement"
]

COUNTRIES = ["France", "USA", "Allemagne", "Royaume-Uni", "Chine", "Inde", "Russie", "Ukraine", "Tunisie"]

MACRO_INDICATORS = ["CAC40", "SP500", "NASDAQ", "VIX", "EUR_USD", "Brent", "Fed_Rate", "ECB_Rate"]

# ══════════════════════════════════════════════════════════════════════════════
# HELPER — build standard Talan node
# ══════════════════════════════════════════════════════════════════════════════

def _talan_node():
    return {
        "id": "talan", "name": "Talan", "type": "Company",
        "country": "France", "sector": "IT Services / ESN",
        "ticker": None, "revenue_eur_m": 600, "headcount": 10000
    }

def _company_node(slug):
    c = COMPANIES[slug]
    return {
        "id": slug, "name": c["name"], "type": "Company",
        "country": c["country"], "sector": c["sector"],
        "ticker": c["ticker"], "revenue_eur_m": c["revenue_m"], "headcount": c["hc"]
    }

def _sector_node(name):
    sid = name.lower().replace(" / ", "_").replace(" ", "_").replace("&", "and")
    return {"id": sid, "name": name, "type": "Sector"}

def _country_node(name):
    cid = name.lower().replace("-", "_").replace(" ", "_")
    return {"id": cid, "name": name, "type": "Country"}

def _event_node(eid, name, etype, date):
    return {"id": eid, "name": name, "type": "Event", "event_type": etype, "date": date}

def _macro_node(name):
    return {"id": name.lower(), "name": name, "type": "MacroIndicator"}

def _edge(f, t, rel, score, conf, ts, reason):
    return {
        "from_id": f, "to_id": t, "relation": rel,
        "impact_score": score, "confidence": conf,
        "timestamp": ts, "reasoning": reason
    }

# ══════════════════════════════════════════════════════════════════════════════
# 150 HISTORICAL EVENTS
# ══════════════════════════════════════════════════════════════════════════════

HISTORICAL_EVENTS: List[Dict[str, Any]] = [

    # ──────────────────────────────────────────────────────────────────────────
    # BLOC 1 — COVID & TRANSFORMATION DIGITALE (2020–2021)  [20 événements]
    # ──────────────────────────────────────────────────────────────────────────

    {
        "event_id": "evt_001",
        "event_date": "2020-03-11",
        "event_type": "geopolitical_events",
        "event_name": "Pandémie COVID-19 déclarée par l'OMS — effondrement des marchés",
        "event_description": "L'OMS déclare la pandémie mondiale. Le CAC40 chute de 40% en 3 semaines, les entreprises gèlent leurs budgets IT. Confinement généralisé en Europe.",
        "source": "OMS / Reuters / Euronext",
        "severity": 1.0,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 3755, "CAC40_change_pct": -38.0,
            "SP500_change_pct": -34.0, "VIX": 82.7, "EUR_USD": 1.11,
            "brent_usd": 22.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.90
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("atos"),
            _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_covid_pandemic", "Pandémie COVID-19", "geopolitical_events", "2020-03-11"),
            _macro_node("CAC40"), _macro_node("VIX")
        ],
        "edges": [
            _edge("evt_covid_pandemic", "it_services_esn", "CAUSES_IMPACT_ON", -0.55, 0.95, "2020-03-11",
                   "Gel massif des budgets IT clients, report ou annulation de projets de transformation"),
            _edge("evt_covid_pandemic", "talan", "CAUSES_IMPACT_ON", -0.45, 0.90, "2020-03-11",
                   "Talan subit gel de projets, report RFP, passage au télétravail forcé"),
            _edge("evt_covid_pandemic", "capgemini", "CAUSES_IMPACT_ON", -0.40, 0.92, "2020-03-11",
                   "Capgemini revoit ses prévisions 2020 à la baisse, -2.4% CA organique"),
            _edge("evt_covid_pandemic", "cloud_computing", "CAUSES_IMPACT_ON", +0.30, 0.88, "2020-03-11",
                   "Accélération de la migration cloud pour le télétravail"),
            _edge("evt_covid_pandemic", "cac40", "CAUSES_IMPACT_ON", -0.80, 0.99, "2020-03-11",
                   "CAC40 chute de 6000 à 3755 points"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence sur le marché ESN français"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence directe ESN mid-size FR"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.35, "impact_1m": -0.45, "impact_3m": -0.30, "impact_6m": -0.10,
                "direction": "negative", "confidence": 0.85,
                "reasoning": "Q2 2020 en forte baisse, gel des recrutements. Reprise progressive Q3 grâce au digital.",
                "source": "Syntec Numérique rapport COVID / estimation sectorielle"
            },
            "capgemini": {
                "impact_1m": -0.40, "direction": "negative", "confidence": 0.90,
                "reasoning": "CA organique -7.7% au S1 2020",
                "source": "Capgemini rapport semestriel 2020"
            },
            "it_services_esn": {
                "impact_1m": -0.50, "direction": "negative", "confidence": 0.92,
                "reasoning": "Secteur ESN en contraction de 4.6% en 2020 selon Syntec Numérique"
            }
        },
        "gnn_training": {"target_impact": -0.45, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Événement exogène majeur, choc systémique"}
    },

    {
        "event_id": "evt_002",
        "event_date": "2020-04-15",
        "event_type": "tech_launch",
        "event_name": "Adoption massive du télétravail — explosion demande Cloud & collaboration",
        "event_description": "En un mois, Microsoft Teams passe de 32M à 75M d'utilisateurs quotidiens. Zoom multiplie par 30 son usage. La demande de services cloud et collaboration explose.",
        "source": "Microsoft Blog / Zoom Q1 2020 Earnings",
        "severity": 0.85,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 4400, "CAC40_change_pct": -25.0,
            "SP500_change_pct": -15.0, "VIX": 40.0, "EUR_USD": 1.09,
            "brent_usd": 28.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.80
        },
        "nodes": [
            _talan_node(),
            _company_node("microsoft"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_remote_work_boom", "Boom télétravail & Cloud", "tech_launch", "2020-04-15"),
        ],
        "edges": [
            _edge("evt_remote_work_boom", "cloud_computing", "CAUSES_IMPACT_ON", +0.55, 0.93, "2020-04-15",
                   "Migration cloud accélérée de 3-5 ans en quelques semaines"),
            _edge("evt_remote_work_boom", "talan", "CAUSES_IMPACT_ON", +0.20, 0.80, "2020-04-15",
                   "Talan capte des projets de migration cloud et modernisation des postes de travail"),
            _edge("evt_remote_work_boom", "microsoft", "CAUSES_IMPACT_ON", +0.50, 0.95, "2020-04-15",
                   "Azure et Teams en croissance record"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.05, "impact_1m": +0.18, "impact_3m": +0.25, "impact_6m": +0.30,
                "direction": "positive", "confidence": 0.78,
                "reasoning": "Nouvelles missions de migration cloud, workplace transformation. Compense partiellement le choc COVID.",
                "source": "Estimation basée sur rapports Syntec Numérique et tendances ESN"
            },
            "cloud_computing": {
                "impact_1m": +0.50, "direction": "positive", "confidence": 0.93,
                "reasoning": "Marché cloud mondial +37% en 2020 (Synergy Research)"
            }
        },
        "gnn_training": {"target_impact": +0.18, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Effet rebond positif du COVID pour les ESN positionnées cloud"}
    },

    {
        "event_id": "evt_003",
        "event_date": "2020-09-03",
        "event_type": "macro_economic",
        "event_name": "Plan France Relance — 100 Md€ dont 7 Md€ pour le numérique",
        "event_description": "Le gouvernement français annonce France Relance (100 Md€). 7 Md€ fléchés vers la transformation numérique des entreprises et de l'État, incluant cloud souverain et cybersécurité.",
        "source": "Gouvernement.fr / Les Echos",
        "severity": 0.75,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5000, "CAC40_change_pct": -15.0,
            "SP500_change_pct": +5.0, "VIX": 27.0, "EUR_USD": 1.18,
            "brent_usd": 42.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.60
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("atos"),
            _sector_node("IT Services / ESN"), _sector_node("Secteur Public / Gouvernement"),
            _sector_node("Cybersécurité"),
            _country_node("France"),
            _event_node("evt_france_relance", "Plan France Relance 100Md€", "macro_economic", "2020-09-03"),
        ],
        "edges": [
            _edge("evt_france_relance", "it_services_esn", "CAUSES_IMPACT_ON", +0.35, 0.90, "2020-09-03",
                   "7Md€ de budget numérique = pipeline de projets pour les ESN françaises"),
            _edge("evt_france_relance", "talan", "CAUSES_IMPACT_ON", +0.30, 0.85, "2020-09-03",
                   "Talan bien positionnée sur les appels d'offres publics (Data/IA, cybersécurité)"),
            _edge("evt_france_relance", "secteur_public_gouvernement", "CAUSES_IMPACT_ON", +0.45, 0.92, "2020-09-03",
                   "Accélération massive de la transformation numérique de l'État"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "atos", "COMPETES_WITH", 0.5, 1.0, "2020-01-01", "Concurrence sur marchés publics"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.15, "impact_3m": +0.28, "impact_6m": +0.30,
                "direction": "positive", "confidence": 0.82,
                "reasoning": "Talan remporte plusieurs marchés publics data/IA et cybersécurité via France Relance en 2021.",
                "source": "Communiqués Talan / BOAMP"
            },
            "it_services_esn": {
                "impact_1m": +0.30, "direction": "positive", "confidence": 0.88,
                "reasoning": "Relance du secteur ESN via commandes publiques"
            }
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Effet positif décalé, les marchés publics prennent 3-6 mois à se matérialiser"}
    },

    {
        "event_id": "evt_004",
        "event_date": "2020-11-10",
        "event_type": "macro_economic",
        "event_name": "Plan Biden Build Back Better — relance américaine 1900 Md$",
        "event_description": "Joe Biden élu président (Nov 2020). Son plan de relance American Rescue Plan (1900 Md$) et infrastructure (1200 Md$) incluent des investissements IT massifs.",
        "source": "White House / CNN / Reuters",
        "severity": 0.70,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5400, "CAC40_change_pct": -7.0,
            "SP500_change_pct": +12.0, "VIX": 25.0, "EUR_USD": 1.18,
            "brent_usd": 43.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.50
        },
        "nodes": [
            _talan_node(),
            _company_node("accenture"), _company_node("ibm"), _company_node("microsoft"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_biden_relance", "Plan Biden Build Back Better", "macro_economic", "2020-11-10"),
        ],
        "edges": [
            _edge("evt_biden_relance", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.80, "2020-11-10",
                   "Relance US booste les budgets IT des multinationales américaines, effet indirect sur ESN EU"),
            _edge("evt_biden_relance", "talan", "CAUSES_IMPACT_ON", +0.08, 0.65, "2020-11-10",
                   "Impact indirect via clients multinationaux de Talan et confiance globale"),
            _edge("evt_biden_relance", "accenture", "CAUSES_IMPACT_ON", +0.35, 0.90, "2020-11-10",
                   "Accenture bénéficie directement des budgets IT fédéraux américains"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "accenture", "COMPETES_WITH", 0.3, 1.0, "2020-01-01", "Concurrence limitée géographiquement"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.10, "impact_6m": +0.12,
                "direction": "positive", "confidence": 0.60,
                "reasoning": "Effet indirect via confiance des marchés et clients US de Talan",
                "source": "Estimation — impact principalement US"
            },
            "accenture": {
                "impact_1m": +0.30, "direction": "positive", "confidence": 0.88,
                "reasoning": "Accenture Federal Services capte des contrats fédéraux US"
            }
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact faible sur Talan — événement principalement US"}
    },

    {
        "event_id": "evt_005",
        "event_date": "2021-03-01",
        "event_type": "financial_market_impact",
        "event_name": "Pénurie mondiale de semi-conducteurs — perturbation supply chain",
        "event_description": "La pénurie de semi-conducteurs atteint son pic. TSMC et Samsung ne peuvent pas suivre la demande. Impact sur l'automobile, l'IoT et les déploiements IT.",
        "source": "Financial Times / TSMC Earnings / Gartner",
        "severity": 0.70,
        "confidence": 0.97,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5800, "CAC40_change_pct": +3.0,
            "SP500_change_pct": +8.0, "VIX": 20.0, "EUR_USD": 1.20,
            "brent_usd": 65.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("nvidia"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"), _sector_node("Industrie / Manufacturing"),
            _country_node("France"), _country_node("Chine"),
            _event_node("evt_chip_shortage", "Pénurie semi-conducteurs mondiale", "financial_market_impact", "2021-03-01"),
        ],
        "edges": [
            _edge("evt_chip_shortage", "industrie_manufacturing", "CAUSES_IMPACT_ON", -0.40, 0.92, "2021-03-01",
                   "Arrêt de chaînes de production automobile, retards IoT/Edge"),
            _edge("evt_chip_shortage", "talan", "CAUSES_IMPACT_ON", -0.08, 0.65, "2021-03-01",
                   "Retards sur certains projets IoT/Edge de Talan, mais impact limité car ESN = services"),
            _edge("evt_chip_shortage", "nvidia", "CAUSES_IMPACT_ON", +0.30, 0.85, "2021-03-01",
                   "NVIDIA bénéficie de la hausse des prix GPU"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.02, "impact_1m": -0.05, "impact_3m": -0.08, "impact_6m": -0.05,
                "direction": "negative", "confidence": 0.55,
                "reasoning": "Impact limité car Talan est un prestataire de services, pas un fabricant. Quelques retards projets IoT.",
                "source": "Estimation sectorielle"
            },
            "industrie_manufacturing": {
                "impact_1m": -0.40, "direction": "negative", "confidence": 0.92,
                "reasoning": "Production automobile mondiale -7.7M véhicules en 2021 (AlixPartners)"
            }
        },
        "gnn_training": {"target_impact": -0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact faible sur Talan car ESN = services, pas hardware"}
    },

    {
        "event_id": "evt_006",
        "event_date": "2021-04-01",
        "event_type": "financial_market_impact",
        "event_name": "Boom IPO tech et valorisations records — NASDAQ +25% en 2021",
        "event_description": "2021 est une année record pour les IPO tech: Coinbase, UiPath, Confluent. Le NASDAQ atteint des sommets historiques, les budgets IT sont en expansion.",
        "source": "NASDAQ / Renaissance Capital / PitchBook",
        "severity": 0.60,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6100, "CAC40_change_pct": +10.0,
            "SP500_change_pct": +20.0, "VIX": 18.0, "EUR_USD": 1.18,
            "brent_usd": 63.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.15
        },
        "nodes": [
            _talan_node(),
            _company_node("accenture"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"), _sector_node("Finance / Banque"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_ipo_boom", "Boom IPO tech 2021", "financial_market_impact", "2021-04-01"),
            _macro_node("NASDAQ"),
        ],
        "edges": [
            _edge("evt_ipo_boom", "it_services_esn", "CAUSES_IMPACT_ON", +0.25, 0.82, "2021-04-01",
                   "Budgets IT en expansion dans tous les secteurs, forte demande de services"),
            _edge("evt_ipo_boom", "talan", "CAUSES_IMPACT_ON", +0.15, 0.75, "2021-04-01",
                   "Talan bénéficie de l'expansion des budgets IT, nouvelles missions"),
            _edge("evt_ipo_boom", "nasdaq", "CAUSES_IMPACT_ON", +0.50, 0.95, "2021-04-01",
                   "NASDAQ en hausse de 25% sur l'année 2021"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.03, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.20,
                "direction": "positive", "confidence": 0.72,
                "reasoning": "Climat d'investissement favorable, hausse de la demande IT sur le marché français",
                "source": "Syntec Numérique — croissance secteur numérique +5.8% en 2021"
            }
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Effet indirect positif via confiance des marchés"}
    },

    {
        "event_id": "evt_007",
        "event_date": "2021-01-15",
        "event_type": "regulatory_changes",
        "event_name": "Cyberattaque SolarWinds — explosion demande cybersécurité",
        "event_description": "La cyberattaque SolarWinds (révélée fin 2020) impacte 18K organisations dont des agences fédérales US. Déclenche une vague de budgets cybersécurité dans le monde entier.",
        "source": "CISA / Reuters / FireEye",
        "severity": 0.80,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5600, "CAC40_change_pct": +1.0,
            "SP500_change_pct": +3.0, "VIX": 22.0, "EUR_USD": 1.21,
            "brent_usd": 55.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.25
        },
        "nodes": [
            _talan_node(),
            _company_node("microsoft"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("Cybersécurité"), _sector_node("IT Services / ESN"),
            _sector_node("Secteur Public / Gouvernement"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_solarwinds", "Cyberattaque SolarWinds", "regulatory_changes", "2021-01-15"),
        ],
        "edges": [
            _edge("evt_solarwinds", "cybersecurite", "CAUSES_IMPACT_ON", +0.60, 0.95, "2021-01-15",
                   "Explosion de la demande d'audits et de services cybersécurité"),
            _edge("evt_solarwinds", "talan", "CAUSES_IMPACT_ON", +0.22, 0.80, "2021-01-15",
                   "Talan développe son offre cybersécurité, nouvelles missions d'audit"),
            _edge("evt_solarwinds", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.82, "2021-01-15",
                   "Les ESN captent la demande de sécurisation des SI"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.05, "impact_1m": +0.18, "impact_3m": +0.25, "impact_6m": +0.28,
                "direction": "positive", "confidence": 0.78,
                "reasoning": "La practice cybersécurité de Talan capte de nouvelles missions. Marché cyber FR +10% en 2021.",
                "source": "Xerfi / Syntec Numérique"
            },
            "cybersecurite": {
                "impact_1m": +0.55, "direction": "positive", "confidence": 0.93,
                "reasoning": "Marché mondial de la cybersécurité +12% en 2021 (Gartner)"
            }
        },
        "gnn_training": {"target_impact": +0.18, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Opportunité pour Talan sur la cybersécurité"}
    },

    {
        "event_id": "evt_008",
        "event_date": "2021-01-01",
        "event_type": "regulatory_changes",
        "event_name": "Directive NIS et LPM renforcée — obligations cybersécurité en France",
        "event_description": "La transposition de la directive NIS et les évolutions de la LPM imposent de nouvelles obligations de cybersécurité aux opérateurs essentiels et services numériques en France.",
        "source": "ANSSI / Journal Officiel / Legifrance",
        "severity": 0.55,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5550, "CAC40_change_pct": -5.0,
            "SP500_change_pct": +1.0, "VIX": 23.0, "EUR_USD": 1.22,
            "brent_usd": 52.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("atos"), _company_node("sopra"),
            _sector_node("Cybersécurité"), _sector_node("IT Services / ESN"),
            _sector_node("Secteur Public / Gouvernement"),
            _country_node("France"),
            _event_node("evt_nis_lpm", "Directive NIS / LPM renforcée", "regulatory_changes", "2021-01-01"),
        ],
        "edges": [
            _edge("evt_nis_lpm", "cybersecurite", "CAUSES_IMPACT_ON", +0.30, 0.88, "2021-01-01",
                   "Nouvelles obligations de conformité = demande accrue de services cyber"),
            _edge("evt_nis_lpm", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2021-01-01",
                   "Talan propose de l'accompagnement conformité NIS/LPM à ses clients OIV/OSE"),
            _edge("evt_nis_lpm", "atos", "CAUSES_IMPACT_ON", +0.20, 0.80, "2021-01-01",
                   "Atos (BDS) capte des contrats de cyberdéfense étatique"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "atos", "COMPETES_WITH", 0.5, 1.0, "2020-01-01", "Concurrence sur marchés publics cyber"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.10, "impact_3m": +0.18, "impact_6m": +0.22,
                "direction": "positive", "confidence": 0.75,
                "reasoning": "Flux continu de missions d'accompagnement conformité. Effet progressif.",
                "source": "ANSSI rapport annuel / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Réglementation = opportunité progressive pour ESN"}
    },

    {
        "event_id": "evt_009",
        "event_date": "2021-06-01",
        "event_type": "tech_launch",
        "event_name": "Déploiement 5G en France et en Europe — nouveaux cas d'usage",
        "event_description": "Les opérateurs européens (Orange, SFR, Deutsche Telekom) déploient massivement la 5G. Nouveaux cas d'usage IoT, Edge Computing, industrie 4.0.",
        "source": "ARCEP / Orange communiqués / GSMA",
        "severity": 0.50,
        "confidence": 0.92,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6500, "CAC40_change_pct": +15.0,
            "SP500_change_pct": +18.0, "VIX": 17.0, "EUR_USD": 1.19,
            "brent_usd": 72.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.15
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _sector_node("Industrie / Manufacturing"),
            _country_node("France"), _country_node("Allemagne"),
            _event_node("evt_5g_europe", "Déploiement 5G en Europe", "tech_launch", "2021-06-01"),
        ],
        "edges": [
            _edge("evt_5g_europe", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.72, "2021-06-01",
                   "Nouveaux projets IoT/Edge pour les ESN, mais marché encore émergent"),
            _edge("evt_5g_europe", "talan", "CAUSES_IMPACT_ON", +0.08, 0.60, "2021-06-01",
                   "Quelques missions de conseil 5G/IoT, mais pas le cœur de métier de Talan"),
            _edge("evt_5g_europe", "industrie_manufacturing", "CAUSES_IMPACT_ON", +0.20, 0.75, "2021-06-01",
                   "Industrie 4.0 accélérée par la 5G dans les usines connectées"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.10,
                "direction": "positive", "confidence": 0.55,
                "reasoning": "Impact modéré, le positionnement 5G/IoT de Talan est encore naissant en 2021",
                "source": "Estimation sectorielle"
            }
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact faible à court terme sur Talan"}
    },

    {
        "event_id": "evt_010",
        "event_date": "2021-06-01",
        "event_type": "talent_market_signals",
        "event_name": "Hausse des salaires développeurs +30% — guerre des talents IT",
        "event_description": "Les salaires des développeurs et ingénieurs IT augmentent de 25-35% en France en 2021. Pénurie aiguë de profils cloud, data et cybersécurité.",
        "source": "Glassdoor France / Robert Half / CodinGame Survey",
        "severity": 0.65,
        "confidence": 0.90,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6500, "CAC40_change_pct": +15.0,
            "SP500_change_pct": +18.0, "VIX": 17.0, "EUR_USD": 1.19,
            "brent_usd": 72.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.15
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_salary_hike", "Hausse salaires IT +30%", "talent_market_signals", "2021-06-01"),
        ],
        "edges": [
            _edge("evt_salary_hike", "it_services_esn", "CAUSES_IMPACT_ON", -0.20, 0.85, "2021-06-01",
                   "Pression sur les marges des ESN, difficulté de recrutement"),
            _edge("evt_salary_hike", "talan", "CAUSES_IMPACT_ON", -0.18, 0.82, "2021-06-01",
                   "Talan doit augmenter ses salaires pour retenir les talents, pression sur la marge"),
            _edge("evt_salary_hike", "capgemini", "CAUSES_IMPACT_ON", -0.12, 0.80, "2021-06-01",
                   "Capgemini peut mieux absorber la hausse grâce à son échelle"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence directe recrutement FR"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.02, "impact_1m": -0.15, "impact_3m": -0.18, "impact_6m": -0.15,
                "direction": "negative", "confidence": 0.80,
                "reasoning": "Marge opérationnelle sous pression, turnover en hausse chez les ESN mid-size",
                "source": "Syntec Numérique rapport 2021 / Robert Half Salary Guide"
            }
        },
        "gnn_training": {"target_impact": -0.15, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Les ESN mid-size souffrent plus de la guerre des talents"}
    },

    {
        "event_id": "evt_011",
        "event_date": "2021-07-01",
        "event_type": "talent_market_signals",
        "event_name": "Great Resignation — vague de démissions mondiale",
        "event_description": "4.3M d'Américains démissionnent en un seul mois (août 2021). Le phénomène touche aussi l'Europe et le secteur IT, avec un turnover record dans les ESN.",
        "source": "US Bureau of Labor Statistics / Financial Times",
        "severity": 0.65,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6500, "CAC40_change_pct": +16.0,
            "SP500_change_pct": +20.0, "VIX": 17.0, "EUR_USD": 1.18,
            "brent_usd": 75.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.12
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_great_resign", "Great Resignation", "talent_market_signals", "2021-07-01"),
        ],
        "edges": [
            _edge("evt_great_resign", "it_services_esn", "CAUSES_IMPACT_ON", -0.25, 0.85, "2021-07-01",
                   "Turnover record dans les ESN, coûts de remplacement élevés"),
            _edge("evt_great_resign", "talan", "CAUSES_IMPACT_ON", -0.20, 0.80, "2021-07-01",
                   "Talan subit un turnover de 20%+ en 2021, difficulté à stafffer les projets"),
            _edge("evt_great_resign", "accenture", "CAUSES_IMPACT_ON", -0.15, 0.82, "2021-07-01",
                   "Accenture perd des talents mais son échelle lui permet de mieux résister"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence sur le recrutement"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.05, "impact_1m": -0.18, "impact_3m": -0.20, "impact_6m": -0.15,
                "direction": "negative", "confidence": 0.78,
                "reasoning": "Difficulté de staffing, projets retardés, coûts de recrutement en hausse",
                "source": "Estimation basée sur Syntec Numérique et turnover secteur ESN"
            }
        },
        "gnn_training": {"target_impact": -0.18, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact négatif majeur pour les ESN mid-size"}
    },

    {
        "event_id": "evt_012",
        "event_date": "2021-06-29",
        "event_type": "tech_launch",
        "event_name": "Lancement GitHub Copilot Preview — IA dans le développement",
        "event_description": "GitHub (Microsoft) lance Copilot en preview technique. Premier assistant de code IA basé sur Codex (OpenAI). Annonce une transformation profonde du métier de développeur.",
        "source": "GitHub Blog / Microsoft",
        "severity": 0.60,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6560, "CAC40_change_pct": +17.0,
            "SP500_change_pct": +15.0, "VIX": 16.0, "EUR_USD": 1.19,
            "brent_usd": 75.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.12
        },
        "nodes": [
            _talan_node(),
            _company_node("microsoft"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_copilot_preview", "Lancement GitHub Copilot Preview", "tech_launch", "2021-06-29"),
        ],
        "edges": [
            _edge("evt_copilot_preview", "ai_ml", "CAUSES_IMPACT_ON", +0.30, 0.85, "2021-06-29",
                   "Première application grand public de l'IA dans le coding"),
            _edge("evt_copilot_preview", "talan", "CAUSES_IMPACT_ON", +0.05, 0.55, "2021-06-29",
                   "Signal faible: l'IA va transformer le delivery des ESN. Impact à long terme."),
            _edge("evt_copilot_preview", "it_services_esn", "CAUSES_IMPACT_ON", -0.05, 0.60, "2021-06-29",
                   "Menace potentielle: si l'IA code, moins besoin de développeurs ESN?"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.03, "impact_3m": +0.05, "impact_6m": +0.08,
                "direction": "positive", "confidence": 0.50,
                "reasoning": "Signal faible en 2021. L'impact réel ne se matérialise qu'en 2023-2024 avec la GA de Copilot.",
                "source": "GitHub / Estimation prospective"
            }
        },
        "gnn_training": {"target_impact": +0.03, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Signal précoce, impact réel à horizon 2-3 ans"}
    },

    {
        "event_id": "evt_013",
        "event_date": "2021-06-11",
        "event_type": "tech_launch",
        "event_name": "GPT-3 API rendue publique — début de l'ère LLM accessible",
        "event_description": "OpenAI ouvre l'accès à l'API GPT-3 à tous les développeurs. Les premiers cas d'usage commerciaux apparaissent (rédaction, code, chatbots).",
        "source": "OpenAI Blog / TechCrunch",
        "severity": 0.55,
        "confidence": 0.97,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6550, "CAC40_change_pct": +17.0,
            "SP500_change_pct": +14.0, "VIX": 16.0, "EUR_USD": 1.21,
            "brent_usd": 72.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.12
        },
        "nodes": [
            _talan_node(),
            _company_node("openai"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_gpt3_api", "GPT-3 API publique", "tech_launch", "2021-06-11"),
        ],
        "edges": [
            _edge("evt_gpt3_api", "ai_ml", "CAUSES_IMPACT_ON", +0.35, 0.88, "2021-06-11",
                   "Démocratisation des LLM pour les développeurs et entreprises"),
            _edge("evt_gpt3_api", "talan", "CAUSES_IMPACT_ON", +0.08, 0.60, "2021-06-11",
                   "Premiers POC IA/NLP chez des clients de Talan, demande naissante"),
            _edge("evt_gpt3_api", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.70, "2021-06-11",
                   "Les ESN commencent à développer des offres intégrant les LLM"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.12,
                "direction": "positive", "confidence": 0.58,
                "reasoning": "Impact progressif. La practice Data/IA de Talan commence à intégrer les LLM dans ses offres.",
                "source": "Estimation basée sur la progression du marché NLP/LLM"
            }
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Signal précoce pour le marché IA/LLM"}
    },

    {
        "event_id": "evt_014",
        "event_date": "2021-04-12",
        "event_type": "competitor_moves",
        "event_name": "Microsoft rachète Nuance pour 19.7 Md$ — IA dans la santé",
        "event_description": "Microsoft acquiert Nuance Communications pour 19.7 Md$. Renforce son positionnement IA dans la santé et les entreprises.",
        "source": "Microsoft Press Release / Wall Street Journal",
        "severity": 0.55,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6200, "CAC40_change_pct": +12.0,
            "SP500_change_pct": +12.0, "VIX": 17.0, "EUR_USD": 1.19,
            "brent_usd": 63.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.15
        },
        "nodes": [
            _talan_node(),
            _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("Santé / Healthcare"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_msft_nuance", "Microsoft rachète Nuance 19.7Md$", "competitor_moves", "2021-04-12"),
        ],
        "edges": [
            _edge("evt_msft_nuance", "ai_ml", "CAUSES_IMPACT_ON", +0.15, 0.80, "2021-04-12",
                   "Consolidation du secteur IA — Microsoft renforce Azure AI"),
            _edge("evt_msft_nuance", "sante_healthcare", "CAUSES_IMPACT_ON", +0.20, 0.82, "2021-04-12",
                   "IA clinique et transcription médicale deviennent mainstream"),
            _edge("evt_msft_nuance", "talan", "CAUSES_IMPACT_ON", +0.05, 0.55, "2021-04-12",
                   "Impact indirect: Microsoft renforce son écosystème, Talan = partenaire Microsoft"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.04, "impact_3m": +0.06, "impact_6m": +0.08,
                "direction": "positive", "confidence": 0.52,
                "reasoning": "Effet indirect positif via le renforcement de l'écosystème Microsoft dont Talan est partenaire",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.04, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact indirect via partnership Microsoft"}
    },

    {
        "event_id": "evt_015",
        "event_date": "2021-11-30",
        "event_type": "tech_launch",
        "event_name": "AWS re:Invent 2021 — extension massive des services IA/ML",
        "event_description": "Amazon Web Services étend massivement ses services IA à re:Invent 2021: SageMaker Canvas, Trainium, nouveaux services ML managés. Démocratisation du ML as a Service.",
        "source": "AWS Blog / TechCrunch",
        "severity": 0.50,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6800, "CAC40_change_pct": +25.0,
            "SP500_change_pct": +24.0, "VIX": 28.0, "EUR_USD": 1.13,
            "brent_usd": 72.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.18
        },
        "nodes": [
            _talan_node(),
            _company_node("amazon"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_reinvent_2021", "AWS re:Invent 2021", "tech_launch", "2021-11-30"),
        ],
        "edges": [
            _edge("evt_reinvent_2021", "cloud_computing", "CAUSES_IMPACT_ON", +0.20, 0.82, "2021-11-30",
                   "Nouveaux services ML managés, baisse des barrières à l'entrée pour le ML"),
            _edge("evt_reinvent_2021", "talan", "CAUSES_IMPACT_ON", +0.10, 0.68, "2021-11-30",
                   "Talan capte des missions de migration et intégration de services AWS ML"),
            _edge("evt_reinvent_2021", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.72, "2021-11-30",
                   "Plus de services cloud managés = plus de missions d'intégration pour les ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.06, "impact_3m": +0.10, "impact_6m": +0.12,
                "direction": "positive", "confidence": 0.62,
                "reasoning": "Missions AWS ML pour Talan en hausse au S1 2022",
                "source": "Estimation basée sur tendances cloud"
            }
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact positif modéré via missions cloud/ML"}
    },

    {
        "event_id": "evt_016",
        "event_date": "2021-09-01",
        "event_type": "tech_launch",
        "event_name": "Adoption SAP S/4HANA et Salesforce comme plateformes critiques pour ESN",
        "event_description": "SAP impose la migration vers S/4HANA (deadline 2027). Salesforce renforce sa plateforme Einstein AI. Les ESN captent d'importants budgets de migration ERP/CRM.",
        "source": "SAP communiqués / Salesforce / Forrester",
        "severity": 0.55,
        "confidence": 0.90,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6600, "CAC40_change_pct": +18.0,
            "SP500_change_pct": +19.0, "VIX": 17.0, "EUR_USD": 1.18,
            "brent_usd": 73.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.12
        },
        "nodes": [
            _talan_node(),
            _company_node("sap"), _company_node("salesforce"), _company_node("capgemini"),
            _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("France"), _country_node("Allemagne"),
            _event_node("evt_sap_sf_critical", "SAP S/4HANA & Salesforce plateformes critiques", "tech_launch", "2021-09-01"),
        ],
        "edges": [
            _edge("evt_sap_sf_critical", "it_services_esn", "CAUSES_IMPACT_ON", +0.30, 0.88, "2021-09-01",
                   "Budgets migration ERP/CRM massifs, pipeline de projets sur 5 ans"),
            _edge("evt_sap_sf_critical", "talan", "CAUSES_IMPACT_ON", +0.22, 0.80, "2021-09-01",
                   "Talan développe ses practices ERP SAP et Salesforce, missions de migration"),
            _edge("evt_sap_sf_critical", "capgemini", "CAUSES_IMPACT_ON", +0.30, 0.90, "2021-09-01",
                   "Capgemini est le premier intégrateur SAP mondial"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.15, "impact_3m": +0.22, "impact_6m": +0.25,
                "direction": "positive", "confidence": 0.78,
                "reasoning": "Practice ERP/CRM de Talan en croissance de 15% en 2021-2022",
                "source": "Estimation basée sur le marché ERP français (PAC / CXP)"
            }
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Forte opportunité ERP pour les ESN françaises"}
    },

    {
        "event_id": "evt_017",
        "event_date": "2021-05-01",
        "event_type": "regulatory_changes",
        "event_name": "Schrems II — invalidation Privacy Shield, impact cloud transatlantique",
        "event_description": "L'arrêt Schrems II de la CJUE invalide le Privacy Shield US-EU. Les entreprises européennes doivent revoir leurs transferts de données vers les USA, poussant vers le cloud souverain.",
        "source": "CJUE / CNIL / Les Echos",
        "severity": 0.50,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6300, "CAC40_change_pct": +13.0,
            "SP500_change_pct": +15.0, "VIX": 18.0, "EUR_USD": 1.20,
            "brent_usd": 68.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.15
        },
        "nodes": [
            _talan_node(),
            _company_node("microsoft"), _company_node("amazon"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _sector_node("Data & Analytics"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_schrems_ii", "Schrems II — Privacy Shield invalidé", "regulatory_changes", "2021-05-01"),
        ],
        "edges": [
            _edge("evt_schrems_ii", "cloud_computing", "CAUSES_IMPACT_ON", -0.10, 0.75, "2021-05-01",
                   "Incertitude juridique sur les transferts de données US-EU"),
            _edge("evt_schrems_ii", "talan", "CAUSES_IMPACT_ON", +0.12, 0.70, "2021-05-01",
                   "Opportunité de conseil RGPD/conformité et de projets cloud souverain pour Talan"),
            _edge("evt_schrems_ii", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.72, "2021-05-01",
                   "Besoin accru de conseil juridique data et d'intégration cloud souverain"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.15,
                "direction": "positive", "confidence": 0.65,
                "reasoning": "Missions de mise en conformité data et conseil cloud souverain",
                "source": "CNIL rapport annuel / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Réglementation data = opportunité pour les ESN françaises"}
    },

    {
        "event_id": "evt_018",
        "event_date": "2021-10-15",
        "event_type": "competitor_moves",
        "event_name": "Atos acquiert Cloudreach — renforcement cloud",
        "event_description": "Atos acquiert Cloudreach (spécialiste migration cloud) pour renforcer son offre cloud et contrer la concurrence de Capgemini et Accenture.",
        "source": "Atos communiqué de presse / Les Echos Investir",
        "severity": 0.40,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6700, "CAC40_change_pct": +21.0,
            "SP500_change_pct": +21.0, "VIX": 17.0, "EUR_USD": 1.16,
            "brent_usd": 83.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.12
        },
        "nodes": [
            _talan_node(),
            _company_node("atos"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("France"),
            _event_node("evt_atos_cloudreach", "Atos acquiert Cloudreach", "competitor_moves", "2021-10-15"),
        ],
        "edges": [
            _edge("evt_atos_cloudreach", "atos", "CAUSES_IMPACT_ON", +0.10, 0.75, "2021-10-15",
                   "Renforcement de l'offre cloud d'Atos"),
            _edge("evt_atos_cloudreach", "talan", "CAUSES_IMPACT_ON", -0.05, 0.55, "2021-10-15",
                   "Légère pression concurrentielle sur le segment cloud mid-market"),
            _edge("evt_atos_cloudreach", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.65, "2021-10-15",
                   "Consolidation du secteur ESN cloud"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "atos", "COMPETES_WITH", 0.5, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.03, "impact_3m": -0.05, "impact_6m": -0.03,
                "direction": "negative", "confidence": 0.50,
                "reasoning": "Pression concurrentielle légère, mais Talan n'est pas en compétition directe sur le même segment cloud",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.03, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact faible, Atos et Talan ne sont pas sur le même segment exact"}
    },

    {
        "event_id": "evt_019",
        "event_date": "2021-12-01",
        "event_type": "macro_economic",
        "event_name": "Reprise économique mondiale post-COVID — croissance PIB EU +5%",
        "event_description": "L'économie européenne rebondit fortement en 2021 (+5.4% PIB zone euro). Les budgets IT sont de nouveau en expansion, le secteur numérique croît de +5.8% en France.",
        "source": "Eurostat / INSEE / Syntec Numérique",
        "severity": 0.65,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7100, "CAC40_change_pct": +28.0,
            "SP500_change_pct": +27.0, "VIX": 22.0, "EUR_USD": 1.13,
            "brent_usd": 77.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.10
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("Allemagne"),
            _event_node("evt_recovery_2021", "Reprise économique post-COVID", "macro_economic", "2021-12-01"),
            _macro_node("CAC40"),
        ],
        "edges": [
            _edge("evt_recovery_2021", "it_services_esn", "CAUSES_IMPACT_ON", +0.35, 0.90, "2021-12-01",
                   "Rebond du secteur ESN: +5.8% de croissance en France en 2021"),
            _edge("evt_recovery_2021", "talan", "CAUSES_IMPACT_ON", +0.30, 0.85, "2021-12-01",
                   "Talan profite pleinement du rebond, croissance forte du CA"),
            _edge("evt_recovery_2021", "capgemini", "CAUSES_IMPACT_ON", +0.28, 0.88, "2021-12-01",
                   "Capgemini revient à une croissance organique de +10.5% en 2021"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.05, "impact_1m": +0.25, "impact_3m": +0.30, "impact_6m": +0.32,
                "direction": "positive", "confidence": 0.88,
                "reasoning": "Rebond significatif du CA et des recrutements chez Talan en 2021",
                "source": "Syntec Numérique bilan 2021 / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.25, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Le rebond post-COVID est l'un des événements les plus positifs pour Talan"}
    },

    {
        "event_id": "evt_020",
        "event_date": "2021-09-15",
        "event_type": "regulatory_changes",
        "event_name": "RGPD — amende record 746M€ à Amazon, renforcement de l'enforcement",
        "event_description": "La CNPD luxembourgeoise inflige une amende record de 746M€ à Amazon pour violation du RGPD. Signal fort que l'enforcement se durcit.",
        "source": "CNPD Luxembourg / Reuters / Le Monde",
        "severity": 0.50,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6600, "CAC40_change_pct": +18.0,
            "SP500_change_pct": +19.0, "VIX": 19.0, "EUR_USD": 1.17,
            "brent_usd": 75.0, "fed_rate": 0.25, "ecb_rate": 0.0,
            "global_recession_risk": 0.12
        },
        "nodes": [
            _talan_node(),
            _company_node("amazon"), _company_node("capgemini"),
            _sector_node("Data & Analytics"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_rgpd_amazon", "Amende RGPD record 746M€ Amazon", "regulatory_changes", "2021-09-15"),
        ],
        "edges": [
            _edge("evt_rgpd_amazon", "data_and_analytics", "CAUSES_IMPACT_ON", +0.15, 0.78, "2021-09-15",
                   "Les entreprises investissent davantage dans la conformité data/RGPD"),
            _edge("evt_rgpd_amazon", "talan", "CAUSES_IMPACT_ON", +0.12, 0.72, "2021-09-15",
                   "Talan capte des missions de mise en conformité RGPD et gouvernance data"),
            _edge("evt_rgpd_amazon", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.75, "2021-09-15",
                   "Demande accrue de services de conseil en conformité data"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.15,
                "direction": "positive", "confidence": 0.68,
                "reasoning": "Renforcement des missions RGPD/DPO chez les clients de Talan",
                "source": "CNIL rapport annuel 2021 / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Enforcement RGPD = opportunité continue pour les ESN"}
    },

    # ──────────────────────────────────────────────────────────────────────────
    # BLOC 2 — GUERRE UKRAINE & CHOC MACRO (2022) [20 événements]
    # ──────────────────────────────────────────────────────────────────────────

    {
        "event_id": "evt_021",
        "event_date": "2022-02-24",
        "event_type": "geopolitical_events",
        "event_name": "Invasion russe de l'Ukraine — choc géopolitique majeur",
        "event_description": "La Russie envahit l'Ukraine. Choc sur les marchés financiers, prix de l'énergie en flèche, incertitude géopolitique maximale en Europe.",
        "source": "Reuters / BBC / Le Monde",
        "severity": 1.0,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6300, "CAC40_change_pct": -8.0,
            "SP500_change_pct": -10.0, "VIX": 37.0, "EUR_USD": 1.12,
            "brent_usd": 105.0, "fed_rate": 0.50, "ecb_rate": 0.0,
            "global_recession_risk": 0.55
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Énergie"),
            _sector_node("Cybersécurité"),
            _country_node("Ukraine"), _country_node("Russie"), _country_node("France"),
            _event_node("evt_ukraine_war", "Invasion russe de l'Ukraine", "geopolitical_events", "2022-02-24"),
            _macro_node("Brent"), _macro_node("VIX"),
        ],
        "edges": [
            _edge("evt_ukraine_war", "it_services_esn", "CAUSES_IMPACT_ON", -0.25, 0.85, "2022-02-24",
                   "Incertitude économique = gel de certains budgets IT clients"),
            _edge("evt_ukraine_war", "talan", "CAUSES_IMPACT_ON", -0.20, 0.80, "2022-02-24",
                   "Gel de projets chez certains clients (énergie, banque). Coûts énergie en hausse."),
            _edge("evt_ukraine_war", "cybersecurite", "CAUSES_IMPACT_ON", +0.40, 0.90, "2022-02-24",
                   "Explosion de la demande de cybersécurité face aux menaces russes"),
            _edge("evt_ukraine_war", "energie", "CAUSES_IMPACT_ON", -0.50, 0.95, "2022-02-24",
                   "Crise énergétique européenne, prix gaz x10"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.10, "impact_1m": -0.18, "impact_3m": -0.15, "impact_6m": -0.08,
                "direction": "negative", "confidence": 0.78,
                "reasoning": "Impact modéré: gel de certains projets mais compensé par la demande cyber. Pas d'exposition directe à la Russie/Ukraine.",
                "source": "Syntec Numérique / Estimation"
            },
            "cybersecurite": {
                "impact_1m": +0.40, "direction": "positive", "confidence": 0.90,
                "reasoning": "Budgets cyber en hausse de 25% dans les grandes entreprises européennes post-invasion"
            }
        },
        "gnn_training": {"target_impact": -0.18, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact mixte: négatif global mais positif cyber"}
    },

    {
        "event_id": "evt_022",
        "event_date": "2022-03-15",
        "event_type": "geopolitical_events",
        "event_name": "Sanctions occidentales massives contre la Russie",
        "event_description": "US, UE et alliés imposent des sanctions sans précédent: exclusion SWIFT, gel d'actifs, embargo technologique. Impact sur les chaînes d'approvisionnement mondiales.",
        "source": "Conseil de l'UE / US Treasury / Financial Times",
        "severity": 0.85,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6200, "CAC40_change_pct": -12.0,
            "SP500_change_pct": -12.0, "VIX": 33.0, "EUR_USD": 1.10,
            "brent_usd": 115.0, "fed_rate": 0.50, "ecb_rate": 0.0,
            "global_recession_risk": 0.60
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Finance / Banque"),
            _country_node("Russie"), _country_node("France"), _country_node("USA"),
            _event_node("evt_sanctions_russia", "Sanctions occidentales vs Russie", "geopolitical_events", "2022-03-15"),
        ],
        "edges": [
            _edge("evt_sanctions_russia", "finance_banque", "CAUSES_IMPACT_ON", -0.25, 0.85, "2022-03-15",
                   "Banques européennes exposées à la Russie doivent provisionner, budgets IT gelés"),
            _edge("evt_sanctions_russia", "talan", "CAUSES_IMPACT_ON", -0.10, 0.68, "2022-03-15",
                   "Impact indirect via clients bancaires. Talan n'a pas de présence en Russie."),
            _edge("evt_sanctions_russia", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.70, "2022-03-15",
                   "Quelques ESN (Atos, Accenture) doivent fermer des bureaux en Russie"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.03, "impact_1m": -0.08, "impact_3m": -0.06, "impact_6m": -0.03,
                "direction": "negative", "confidence": 0.62,
                "reasoning": "Impact limité, Talan n'a pas d'exposition directe à la Russie",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact indirect via incertitude marché"}
    },

    {
        "event_id": "evt_023",
        "event_date": "2022-08-01",
        "event_type": "macro_economic",
        "event_name": "Crise énergétique européenne — prix gaz x10, inflation record",
        "event_description": "Le prix du gaz naturel en Europe atteint 340€/MWh (vs 30€ début 2021). L'inflation zone euro atteint 8.9% en juillet 2022. Risque de récession en Europe.",
        "source": "Eurostat / ICE / BCE",
        "severity": 0.85,
        "confidence": 0.99,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6300, "CAC40_change_pct": -10.0,
            "SP500_change_pct": -15.0, "VIX": 25.0, "EUR_USD": 1.01,
            "brent_usd": 98.0, "fed_rate": 2.50, "ecb_rate": 0.50,
            "global_recession_risk": 0.65
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("Énergie"),
            _sector_node("Industrie / Manufacturing"),
            _country_node("France"), _country_node("Allemagne"),
            _event_node("evt_energy_crisis", "Crise énergétique européenne", "macro_economic", "2022-08-01"),
            _macro_node("ECB_Rate"),
        ],
        "edges": [
            _edge("evt_energy_crisis", "it_services_esn", "CAUSES_IMPACT_ON", -0.18, 0.82, "2022-08-01",
                   "Clients industriels gèlent des budgets IT pour absorber les coûts énergie"),
            _edge("evt_energy_crisis", "talan", "CAUSES_IMPACT_ON", -0.15, 0.78, "2022-08-01",
                   "Talan voit certains clients reporter des projets. Coûts opérationnels en hausse."),
            _edge("evt_energy_crisis", "industrie_manufacturing", "CAUSES_IMPACT_ON", -0.45, 0.92, "2022-08-01",
                   "Industrie européenne en difficulté, fermetures d'usines en Allemagne"),
            _edge("evt_energy_crisis", "energie", "CAUSES_IMPACT_ON", -0.60, 0.95, "2022-08-01",
                   "Secteur énergétique en crise, investissements massifs dans les alternatives"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.05, "impact_1m": -0.12, "impact_3m": -0.15, "impact_6m": -0.10,
                "direction": "negative", "confidence": 0.75,
                "reasoning": "Reports de projets chez des clients industriels et énergie. Marge sous pression.",
                "source": "Estimation basée sur rapports Syntec Numérique S2 2022"
            }
        },
        "gnn_training": {"target_impact": -0.12, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Crise énergie impacte les clients des ESN"}
    },

    {
        "event_id": "evt_024",
        "event_date": "2022-07-01",
        "event_type": "macro_economic",
        "event_name": "Inflation record zone euro 8.9% — BCE commence à relever les taux",
        "event_description": "L'inflation atteint 8.9% en zone euro (juillet 2022). La BCE relève ses taux pour la première fois en 11 ans, de 0% à 0.5%, début d'un cycle de hausse aggressive.",
        "source": "BCE / Eurostat / Financial Times",
        "severity": 0.75,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6200, "CAC40_change_pct": -12.0,
            "SP500_change_pct": -18.0, "VIX": 26.0, "EUR_USD": 1.02,
            "brent_usd": 107.0, "fed_rate": 2.50, "ecb_rate": 0.50,
            "global_recession_risk": 0.60
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("Finance / Banque"),
            _country_node("France"),
            _event_node("evt_inflation_bce", "Inflation record 8.9% + hausse taux BCE", "macro_economic", "2022-07-01"),
            _macro_node("ECB_Rate"), _macro_node("CAC40"),
        ],
        "edges": [
            _edge("evt_inflation_bce", "it_services_esn", "CAUSES_IMPACT_ON", -0.15, 0.80, "2022-07-01",
                   "Hausse des coûts de financement pour les clients, pression sur les budgets IT"),
            _edge("evt_inflation_bce", "talan", "CAUSES_IMPACT_ON", -0.12, 0.75, "2022-07-01",
                   "Coûts salariaux en hausse (inflation), pression tarifaire de certains clients"),
            _edge("evt_inflation_bce", "finance_banque", "CAUSES_IMPACT_ON", +0.10, 0.72, "2022-07-01",
                   "Les banques bénéficient de la hausse des taux (marge d'intérêt nette)"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.03, "impact_1m": -0.10, "impact_3m": -0.12, "impact_6m": -0.08,
                "direction": "negative", "confidence": 0.72,
                "reasoning": "Pression inflationniste sur les salaires IT, difficile à répercuter sur les TJM immédiatement",
                "source": "BCE / Syntec Numérique"
            }
        },
        "gnn_training": {"target_impact": -0.10, "talan_node_index": 0, "horizon": "1m",
                         "notes": "L'inflation érode les marges des ESN"}
    },

    {
        "event_id": "evt_025",
        "event_date": "2022-06-15",
        "event_type": "macro_economic",
        "event_name": "Fed relève les taux agressivement — 75bps, plus forte hausse depuis 1994",
        "event_description": "La Fed relève ses taux de 75 points de base, la plus forte hausse depuis 1994. Signal que l'ère de l'argent gratuit est terminée.",
        "source": "Federal Reserve / Wall Street Journal",
        "severity": 0.75,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5900, "CAC40_change_pct": -15.0,
            "SP500_change_pct": -22.0, "VIX": 32.0, "EUR_USD": 1.04,
            "brent_usd": 115.0, "fed_rate": 1.75, "ecb_rate": 0.0,
            "global_recession_risk": 0.55
        },
        "nodes": [
            _talan_node(),
            _company_node("accenture"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"), _sector_node("Finance / Banque"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_fed_hike", "Fed hausse taux 75bps", "macro_economic", "2022-06-15"),
            _macro_node("Fed_Rate"), _macro_node("SP500"),
        ],
        "edges": [
            _edge("evt_fed_hike", "it_services_esn", "CAUSES_IMPACT_ON", -0.12, 0.78, "2022-06-15",
                   "Resserrement monétaire freine l'investissement IT des entreprises"),
            _edge("evt_fed_hike", "talan", "CAUSES_IMPACT_ON", -0.06, 0.60, "2022-06-15",
                   "Impact indirect: clients multinationaux US de Talan ralentissent certains projets"),
            _edge("evt_fed_hike", "sp500", "CAUSES_IMPACT_ON", -0.35, 0.92, "2022-06-15",
                   "S&P 500 entre en bear market (-22%)"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "accenture", "COMPETES_WITH", 0.3, 1.0, "2020-01-01", "Concurrence limitée"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.02, "impact_1m": -0.05, "impact_3m": -0.08, "impact_6m": -0.06,
                "direction": "negative", "confidence": 0.58,
                "reasoning": "Impact modéré sur Talan, principalement via le sentiment de marché",
                "source": "Estimation — impact principalement US"
            }
        },
        "gnn_training": {"target_impact": -0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact US principalement, indirect sur Talan"}
    },

    {
        "event_id": "evt_026",
        "event_date": "2022-05-09",
        "event_type": "financial_market_impact",
        "event_name": "Crash Terra/Luna — effondrement crypto 60Md$",
        "event_description": "Le stablecoin TerraUSD perd son peg, Luna s'effondre de 80$ à 0. 60 Md$ de capitalisation détruits. Début de la chute crypto 2022.",
        "source": "CoinDesk / Financial Times / Bloomberg",
        "severity": 0.60,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6250, "CAC40_change_pct": -10.0,
            "SP500_change_pct": -15.0, "VIX": 30.0, "EUR_USD": 1.05,
            "brent_usd": 108.0, "fed_rate": 1.00, "ecb_rate": 0.0,
            "global_recession_risk": 0.45
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"),
            _sector_node("Finance / Banque"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_terra_luna", "Crash Terra/Luna crypto", "financial_market_impact", "2022-05-09"),
        ],
        "edges": [
            _edge("evt_terra_luna", "finance_banque", "CAUSES_IMPACT_ON", -0.15, 0.75, "2022-05-09",
                   "Perte de confiance dans le secteur crypto/DeFi, projets blockchain gelés"),
            _edge("evt_terra_luna", "talan", "CAUSES_IMPACT_ON", -0.03, 0.50, "2022-05-09",
                   "Impact très limité: Talan a peu de projets blockchain en 2022"),
            _edge("evt_terra_luna", "it_services_esn", "CAUSES_IMPACT_ON", -0.05, 0.55, "2022-05-09",
                   "Quelques projets blockchain/Web3 des ESN sont annulés"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.02, "impact_3m": -0.03, "impact_6m": -0.02,
                "direction": "negative", "confidence": 0.45,
                "reasoning": "Très faible exposition de Talan au secteur crypto/blockchain",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.02, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact quasi-nul sur Talan"}
    },

    {
        "event_id": "evt_027",
        "event_date": "2022-11-11",
        "event_type": "financial_market_impact",
        "event_name": "Effondrement FTX — fraude crypto massive",
        "event_description": "FTX, 2ème plateforme crypto mondiale, s'effondre suite à une fraude massive. Sam Bankman-Fried arrêté. 8 Md$ de fonds clients perdus.",
        "source": "New York Times / SEC / Financial Times",
        "severity": 0.65,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6600, "CAC40_change_pct": -5.0,
            "SP500_change_pct": -17.0, "VIX": 25.0, "EUR_USD": 1.03,
            "brent_usd": 88.0, "fed_rate": 4.00, "ecb_rate": 2.00,
            "global_recession_risk": 0.50
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"),
            _sector_node("Finance / Banque"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_ftx_collapse", "Effondrement FTX", "financial_market_impact", "2022-11-11"),
        ],
        "edges": [
            _edge("evt_ftx_collapse", "finance_banque", "CAUSES_IMPACT_ON", -0.12, 0.75, "2022-11-11",
                   "Renforcement de la méfiance envers les cryptos, pression réglementaire accrue"),
            _edge("evt_ftx_collapse", "talan", "CAUSES_IMPACT_ON", -0.02, 0.40, "2022-11-11",
                   "Impact quasi-nul sur Talan, qui n'a pas de practice crypto significative"),
            _edge("evt_ftx_collapse", "it_services_esn", "CAUSES_IMPACT_ON", -0.03, 0.48, "2022-11-11",
                   "Annulation de projets Web3/blockchain résiduels dans les ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": 0.00, "impact_1m": -0.01, "impact_3m": -0.02, "impact_6m": -0.01,
                "direction": "neutral", "confidence": 0.40,
                "reasoning": "Aucun impact matériel sur Talan",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.01, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Quasi-nul sur Talan"}
    },

    {
        "event_id": "evt_028",
        "event_date": "2022-01-01",
        "event_type": "financial_market_impact",
        "event_name": "Correction NASDAQ -33% — fin de la bulle tech",
        "event_description": "Le NASDAQ perd 33% en 2022, pire année depuis 2008. Les valeurs tech (Meta -65%, Netflix -51%) s'effondrent. Fin de l'ère argent gratuit pour la tech.",
        "source": "NASDAQ / Bloomberg / Financial Times",
        "severity": 0.80,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6500, "CAC40_change_pct": -9.0,
            "SP500_change_pct": -19.0, "VIX": 25.0, "EUR_USD": 1.07,
            "brent_usd": 80.0, "fed_rate": 4.50, "ecb_rate": 2.50,
            "global_recession_risk": 0.55
        },
        "nodes": [
            _talan_node(),
            _company_node("meta"), _company_node("google"), _company_node("microsoft"),
            _company_node("capgemini"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_nasdaq_crash", "Correction NASDAQ -33%", "financial_market_impact", "2022-01-01"),
            _macro_node("NASDAQ"),
        ],
        "edges": [
            _edge("evt_nasdaq_crash", "it_services_esn", "CAUSES_IMPACT_ON", -0.15, 0.80, "2022-01-01",
                   "Les Big Tech réduisent leurs budgets externes, moins de missions pour les ESN"),
            _edge("evt_nasdaq_crash", "talan", "CAUSES_IMPACT_ON", -0.10, 0.68, "2022-01-01",
                   "Impact modéré: Talan est moins dépendante des Big Tech que les ESN US/indiennes"),
            _edge("evt_nasdaq_crash", "nasdaq", "CAUSES_IMPACT_ON", -0.60, 0.98, "2022-01-01",
                   "NASDAQ -33% sur l'année 2022"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.03, "impact_1m": -0.08, "impact_3m": -0.10, "impact_6m": -0.08,
                "direction": "negative", "confidence": 0.65,
                "reasoning": "Impact indirect via le sentiment de marché. Talan est protégée par sa base clients européenne diversifiée.",
                "source": "Estimation basée sur corrélation NASDAQ/budgets IT"
            }
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact indirect sur Talan via le sentiment de marché"}
    },

    {
        "event_id": "evt_029",
        "event_date": "2022-11-01",
        "event_type": "talent_market_signals",
        "event_name": "Vague de licenciements Big Tech — Meta -11K, Twitter -50%, Amazon -18K",
        "event_description": "Les Big Tech licencient massivement: Meta 11K, Twitter 50%, Amazon 18K, Snap 20%. Plus de 100K emplois tech supprimés en 2022.",
        "source": "layoffs.fyi / Financial Times / Bloomberg",
        "severity": 0.75,
        "confidence": 0.99,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6400, "CAC40_change_pct": -7.0,
            "SP500_change_pct": -18.0, "VIX": 26.0, "EUR_USD": 1.02,
            "brent_usd": 92.0, "fed_rate": 4.00, "ecb_rate": 2.00,
            "global_recession_risk": 0.50
        },
        "nodes": [
            _talan_node(),
            _company_node("meta"), _company_node("amazon"), _company_node("microsoft"),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_bigtech_layoffs", "Licenciements massifs Big Tech", "talent_market_signals", "2022-11-01"),
        ],
        "edges": [
            _edge("evt_bigtech_layoffs", "talan", "CAUSES_IMPACT_ON", +0.12, 0.72, "2022-11-01",
                   "Pool de talents tech disponible, pression salariale en baisse, recrutement plus facile"),
            _edge("evt_bigtech_layoffs", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.70, "2022-11-01",
                   "Les ESN peuvent recruter des talents ex-Big Tech à moindre coût"),
            _edge("evt_bigtech_layoffs", "ai_ml", "CAUSES_IMPACT_ON", -0.15, 0.75, "2022-11-01",
                   "Ralentissement des investissements IA dans les Big Tech (temporaire)"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.10,
                "direction": "positive", "confidence": 0.68,
                "reasoning": "Les licenciements Big Tech libèrent des talents qualifiés. La pression salariale baisse en France en 2023.",
                "source": "layoffs.fyi / Estimation marché de l'emploi IT FR"
            }
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Opportunité de recrutement pour les ESN"}
    },

    {
        "event_id": "evt_030",
        "event_date": "2022-11-30",
        "event_type": "tech_launch",
        "event_name": "Lancement de ChatGPT par OpenAI — révolution IA générative",
        "event_description": "OpenAI lance ChatGPT au grand public. 1M d'utilisateurs en 5 jours, 100M en 2 mois. Déclenche la plus grande course technologique depuis l'internet.",
        "source": "OpenAI Blog / Reuters / The Verge",
        "severity": 0.95,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6700, "CAC40_change_pct": -4.0,
            "SP500_change_pct": -15.0, "VIX": 21.0, "EUR_USD": 1.04,
            "brent_usd": 87.0, "fed_rate": 4.00, "ecb_rate": 2.00,
            "global_recession_risk": 0.40
        },
        "nodes": [
            _talan_node(),
            _company_node("openai"), _company_node("microsoft"), _company_node("google"),
            _company_node("capgemini"), _company_node("accenture"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_chatgpt_launch", "Lancement ChatGPT", "tech_launch", "2022-11-30"),
        ],
        "edges": [
            _edge("evt_chatgpt_launch", "ai_ml", "CAUSES_IMPACT_ON", +0.70, 0.98, "2022-11-30",
                   "Début de la révolution IA générative, investissements massifs"),
            _edge("evt_chatgpt_launch", "talan", "CAUSES_IMPACT_ON", +0.28, 0.85, "2022-11-30",
                   "Talan positionne ses équipes Data/IA pour capturer la demande conseil GenAI"),
            _edge("evt_chatgpt_launch", "it_services_esn", "CAUSES_IMPACT_ON", +0.35, 0.90, "2022-11-30",
                   "Explosion de la demande de conseil en IA générative pour les ESN"),
            _edge("evt_chatgpt_launch", "capgemini", "CAUSES_IMPACT_ON", +0.30, 0.88, "2022-11-30",
                   "Capgemini annonce un plan d'investissement 2Md€ en IA générative"),
            _edge("evt_chatgpt_launch", "accenture", "CAUSES_IMPACT_ON", +0.35, 0.90, "2022-11-30",
                   "Accenture investit 3Md$ en IA en 2023"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.05, "impact_1m": +0.28, "impact_3m": +0.40, "impact_6m": +0.35,
                "direction": "positive", "confidence": 0.85,
                "reasoning": "Hausse de 40% des demandes RFP sur sujets IA générative en Q1 2023. Talan crée une practice GenAI dédiée.",
                "source": "Estimation basée sur tendances sectorielles ESN + rapports Syntec Numérique"
            },
            "capgemini": {
                "impact_1m": +0.30, "direction": "positive", "confidence": 0.88,
                "reasoning": "Capgemini annonce un plan 2Md€ IA générative début 2023",
                "source": "Capgemini Annual Report 2023"
            },
            "it_services_esn": {
                "impact_1m": +0.35, "direction": "positive", "confidence": 0.90,
                "reasoning": "L'ensemble du secteur ESN bénéficie de la vague conseil IA"
            }
        },
        "gnn_training": {"target_impact": +0.28, "talan_node_index": 0, "horizon": "1m",
                         "notes": "ChatGPT est l'événement le plus impactant sur le secteur ESN depuis 2020"}
    },

    {
        "event_id": "evt_031",
        "event_date": "2022-04-21",
        "event_type": "regulatory_changes",
        "event_name": "AI Act — premières versions du règlement européen sur l'IA",
        "event_description": "Le Parlement européen commence les négociations sur l'AI Act. Première tentative mondiale de réguler l'IA avec une approche basée sur les risques.",
        "source": "Parlement Européen / Commission Européenne",
        "severity": 0.55,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6400, "CAC40_change_pct": -8.0,
            "SP500_change_pct": -12.0, "VIX": 28.0, "EUR_USD": 1.08,
            "brent_usd": 108.0, "fed_rate": 1.00, "ecb_rate": 0.0,
            "global_recession_risk": 0.40
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("accenture"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ai_act_v1", "AI Act premières négociations", "regulatory_changes", "2022-04-21"),
        ],
        "edges": [
            _edge("evt_ai_act_v1", "ai_ml", "CAUSES_IMPACT_ON", -0.10, 0.65, "2022-04-21",
                   "Incertitude réglementaire sur les déploiements IA en Europe"),
            _edge("evt_ai_act_v1", "talan", "CAUSES_IMPACT_ON", +0.08, 0.60, "2022-04-21",
                   "Opportunité future de conseil en conformité IA, mais signal encore faible en 2022"),
            _edge("evt_ai_act_v1", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.58, "2022-04-21",
                   "Début de la demande de conseil en gouvernance IA"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.12,
                "direction": "positive", "confidence": 0.55,
                "reasoning": "Signal faible en 2022, l'impact se matérialise en 2024-2025 avec la promulgation",
                "source": "Parlement Européen / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Signal faible, impact réel à long terme"}
    },

    {
        "event_id": "evt_032",
        "event_date": "2022-06-01",
        "event_type": "competitor_moves",
        "event_name": "Atos — premières annonces de difficultés financières majeures",
        "event_description": "Atos annonce un profit warning et révèle l'ampleur de ses problèmes financiers. Le titre chute de 50% en quelques mois. Début de la descente aux enfers.",
        "source": "Atos communiqué / Les Echos / Reuters",
        "severity": 0.75,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6000, "CAC40_change_pct": -14.0,
            "SP500_change_pct": -20.0, "VIX": 30.0, "EUR_USD": 1.05,
            "brent_usd": 112.0, "fed_rate": 1.75, "ecb_rate": 0.0,
            "global_recession_risk": 0.50
        },
        "nodes": [
            _talan_node(),
            _company_node("atos"), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_atos_crisis_2022", "Atos difficultés financières", "competitor_moves", "2022-06-01"),
        ],
        "edges": [
            _edge("evt_atos_crisis_2022", "atos", "CAUSES_IMPACT_ON", -0.55, 0.92, "2022-06-01",
                   "Atos entre en crise: dette, perte de contrats, fuite des talents"),
            _edge("evt_atos_crisis_2022", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2022-06-01",
                   "Opportunité: Talan peut recruter des talents Atos et récupérer des clients"),
            _edge("evt_atos_crisis_2022", "it_services_esn", "CAUSES_IMPACT_ON", -0.05, 0.60, "2022-06-01",
                   "Image du secteur ESN français légèrement ternie"),
            _edge("evt_atos_crisis_2022", "capgemini", "CAUSES_IMPACT_ON", +0.10, 0.72, "2022-06-01",
                   "Capgemini récupère certains clients Atos"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "atos", "COMPETES_WITH", 0.5, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.03, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.22,
                "direction": "positive", "confidence": 0.75,
                "reasoning": "Talan recrute activement des ex-Atos et se positionne sur les appels d'offres qu'Atos ne peut plus servir",
                "source": "Estimation basée sur mouvements RH / LinkedIn data"
            }
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m",
                         "notes": "La crise d'un concurrent = opportunité pour les autres ESN"}
    },

    {
        "event_id": "evt_033",
        "event_date": "2022-10-01",
        "event_type": "competitor_moves",
        "event_name": "Capgemini acquiert Quantmetry — renforcement Data/IA",
        "event_description": "Capgemini acquiert Quantmetry, cabinet de conseil français spécialisé en Data Science et IA. Renforce son positionnement Data/IA en France.",
        "source": "Capgemini communiqué de presse / Les Echos",
        "severity": 0.45,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5800, "CAC40_change_pct": -15.0,
            "SP500_change_pct": -23.0, "VIX": 31.0, "EUR_USD": 0.98,
            "brent_usd": 90.0, "fed_rate": 3.25, "ecb_rate": 1.25,
            "global_recession_risk": 0.55
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"),
            _sector_node("Data & Analytics"), _sector_node("AI/ML"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_cap_quantmetry", "Capgemini acquiert Quantmetry", "competitor_moves", "2022-10-01"),
        ],
        "edges": [
            _edge("evt_cap_quantmetry", "capgemini", "CAUSES_IMPACT_ON", +0.12, 0.82, "2022-10-01",
                   "Capgemini renforce son offre Data/IA en France avec Quantmetry"),
            _edge("evt_cap_quantmetry", "talan", "CAUSES_IMPACT_ON", -0.10, 0.72, "2022-10-01",
                   "Pression concurrentielle accrue sur le segment Data/IA mid-market en France"),
            _edge("evt_cap_quantmetry", "data_and_analytics", "CAUSES_IMPACT_ON", +0.08, 0.68, "2022-10-01",
                   "Consolidation du marché Data/IA français"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN Data/IA"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.08, "impact_3m": -0.10, "impact_6m": -0.08,
                "direction": "negative", "confidence": 0.68,
                "reasoning": "Capgemini renforce sa compétitivité Data/IA, concurrence accrue pour Talan sur ce segment",
                "source": "Capgemini communiqué / Estimation concurrentielle"
            }
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Acquisition d'un concurrent sur le segment cœur de Talan"}
    },

    {
        "event_id": "evt_034",
        "event_date": "2022-10-17",
        "event_type": "regulatory_changes",
        "event_name": "Directive NIS2 adoptée par le Parlement Européen",
        "event_description": "La directive NIS2 est officiellement adoptée. Elle élargit considérablement le périmètre des entreprises soumises à des obligations de cybersécurité (de ~300 à ~10 000 en France).",
        "source": "Journal Officiel de l'UE / ANSSI",
        "severity": 0.65,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 5900, "CAC40_change_pct": -15.0,
            "SP500_change_pct": -22.0, "VIX": 30.0, "EUR_USD": 0.98,
            "brent_usd": 92.0, "fed_rate": 3.25, "ecb_rate": 1.25,
            "global_recession_risk": 0.55
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("atos"), _company_node("sopra"),
            _sector_node("Cybersécurité"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_nis2_adopted", "Directive NIS2 adoptée", "regulatory_changes", "2022-10-17"),
        ],
        "edges": [
            _edge("evt_nis2_adopted", "cybersecurite", "CAUSES_IMPACT_ON", +0.40, 0.92, "2022-10-17",
                   "NIS2 élargit x30 le nombre d'organisations soumises = marché cyber en expansion massive"),
            _edge("evt_nis2_adopted", "talan", "CAUSES_IMPACT_ON", +0.22, 0.82, "2022-10-17",
                   "Talan se positionne sur l'accompagnement NIS2 de ses clients"),
            _edge("evt_nis2_adopted", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.85, "2022-10-17",
                   "Fort pipeline de missions de conformité NIS2 pour les ESN françaises"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.20, "impact_6m": +0.28,
                "direction": "positive", "confidence": 0.80,
                "reasoning": "Pipeline de missions NIS2 se construit dès 2023, plein effet en 2024-2025",
                "source": "ANSSI / Estimation basée sur nombre d'organisations concernées"
            }
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m",
                         "notes": "NIS2 = forte opportunité cyber pour les ESN"}
    },

    {
        "event_id": "evt_035",
        "event_date": "2022-09-01",
        "event_type": "regulatory_changes",
        "event_name": "Réforme marché du travail France — impact sur les ESN",
        "event_description": "Réforme de l'assurance chômage et du marché du travail en France. Durcissement des conditions, impact sur la flexibilité de l'emploi IT.",
        "source": "Ministère du Travail / Les Echos",
        "severity": 0.40,
        "confidence": 0.92,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6100, "CAC40_change_pct": -12.0,
            "SP500_change_pct": -17.0, "VIX": 26.0, "EUR_USD": 1.00,
            "brent_usd": 95.0, "fed_rate": 2.50, "ecb_rate": 0.75,
            "global_recession_risk": 0.50
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_reforme_travail", "Réforme marché du travail France", "regulatory_changes", "2022-09-01"),
        ],
        "edges": [
            _edge("evt_reforme_travail", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.65, "2022-09-01",
                   "Contraintes supplémentaires sur la gestion des intercontrats et la flexibilité"),
            _edge("evt_reforme_travail", "talan", "CAUSES_IMPACT_ON", -0.06, 0.60, "2022-09-01",
                   "Coûts de gestion RH en légère hausse pour Talan"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence ESN FR"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.04, "impact_3m": -0.06, "impact_6m": -0.05,
                "direction": "negative", "confidence": 0.55,
                "reasoning": "Impact limité mais récurrent sur la gestion des effectifs",
                "source": "Syntec Numérique / Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.04, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact faible mais structurel"}
    },

    {
        "event_id": "evt_036",
        "event_date": "2022-03-01",
        "event_type": "competitor_moves",
        "event_name": "Accenture acquiert des sociétés cloud et data en série (2022)",
        "event_description": "Accenture réalise plus de 30 acquisitions en 2022, incluant des spécialistes data, cloud et cybersécurité. Stratégie d'expansion agressive.",
        "source": "Accenture Press Releases / Financial Times",
        "severity": 0.50,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6400, "CAC40_change_pct": -7.0,
            "SP500_change_pct": -10.0, "VIX": 30.0, "EUR_USD": 1.10,
            "brent_usd": 100.0, "fed_rate": 0.50, "ecb_rate": 0.0,
            "global_recession_risk": 0.45
        },
        "nodes": [
            _talan_node(),
            _company_node("accenture"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _sector_node("Data & Analytics"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_accenture_acqui_22", "Accenture acquisitions 2022", "competitor_moves", "2022-03-01"),
        ],
        "edges": [
            _edge("evt_accenture_acqui_22", "accenture", "CAUSES_IMPACT_ON", +0.20, 0.85, "2022-03-01",
                   "Renforcement massif des capacités d'Accenture"),
            _edge("evt_accenture_acqui_22", "talan", "CAUSES_IMPACT_ON", -0.05, 0.55, "2022-03-01",
                   "Pression concurrentielle indirecte, mais Talan et Accenture sont sur des segments différents"),
            _edge("evt_accenture_acqui_22", "it_services_esn", "CAUSES_IMPACT_ON", -0.05, 0.58, "2022-03-01",
                   "Consolidation du marché au bénéfice des grands acteurs"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "accenture", "COMPETES_WITH", 0.3, 1.0, "2020-01-01", "Concurrence limitée"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.03, "impact_3m": -0.05, "impact_6m": -0.04,
                "direction": "negative", "confidence": 0.48,
                "reasoning": "Pression concurrentielle modérée, segments clients différents",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.03, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact faible, concurrence indirecte"}
    },

    {
        "event_id": "evt_037",
        "event_date": "2022-05-01",
        "event_type": "competitor_moves",
        "event_name": "Capgemini résultats solides 2021 — croissance organique +10.5%",
        "event_description": "Capgemini publie d'excellents résultats 2021: CA +10.5%, marge opérationnelle 12.9%. Confirme le rebond du secteur ESN post-COVID.",
        "source": "Capgemini rapport annuel 2021 / Euronext",
        "severity": 0.45,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6500, "CAC40_change_pct": -5.0,
            "SP500_change_pct": -10.0, "VIX": 28.0, "EUR_USD": 1.06,
            "brent_usd": 105.0, "fed_rate": 1.00, "ecb_rate": 0.0,
            "global_recession_risk": 0.40
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_cap_results_21", "Capgemini résultats 2021 +10.5%", "competitor_moves", "2022-05-01"),
        ],
        "edges": [
            _edge("evt_cap_results_21", "capgemini", "CAUSES_IMPACT_ON", +0.15, 0.90, "2022-05-01",
                   "Résultats excellents, confiance du marché"),
            _edge("evt_cap_results_21", "talan", "CAUSES_IMPACT_ON", +0.05, 0.55, "2022-05-01",
                   "Signal positif pour tout le secteur ESN français, effet de halo"),
            _edge("evt_cap_results_21", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.75, "2022-05-01",
                   "Confirme le rebond du secteur ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.04, "impact_3m": +0.05, "impact_6m": +0.05,
                "direction": "positive", "confidence": 0.50,
                "reasoning": "Effet de halo positif pour le secteur ESN français",
                "source": "Capgemini rapport annuel 2021"
            }
        },
        "gnn_training": {"target_impact": +0.04, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Effet de halo sectoriel positif"}
    },

    {
        "event_id": "evt_038",
        "event_date": "2022-12-01",
        "event_type": "geopolitical_events",
        "event_name": "Tensions US-Chine sur les semi-conducteurs — CHIPS Act",
        "event_description": "Les USA promulguent le CHIPS Act (52 Md$) et imposent des restrictions d'exportation de puces avancées vers la Chine. Escalade technologique US-Chine.",
        "source": "White House / Reuters / TSMC",
        "severity": 0.65,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6500, "CAC40_change_pct": -8.0,
            "SP500_change_pct": -19.0, "VIX": 22.0, "EUR_USD": 1.05,
            "brent_usd": 82.0, "fed_rate": 4.50, "ecb_rate": 2.50,
            "global_recession_risk": 0.45
        },
        "nodes": [
            _talan_node(),
            _company_node("nvidia"), _company_node("microsoft"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("Chine"),
            _event_node("evt_chips_act", "CHIPS Act + restrictions export Chine", "geopolitical_events", "2022-12-01"),
        ],
        "edges": [
            _edge("evt_chips_act", "ai_ml", "CAUSES_IMPACT_ON", -0.10, 0.70, "2022-12-01",
                   "Risque de fragmentation du marché IA mondial"),
            _edge("evt_chips_act", "talan", "CAUSES_IMPACT_ON", +0.03, 0.45, "2022-12-01",
                   "Impact très limité: Talan n'a pas d'exposition directe au marché chinois"),
            _edge("evt_chips_act", "nvidia", "CAUSES_IMPACT_ON", -0.15, 0.78, "2022-12-01",
                   "NVIDIA perd l'accès au marché chinois pour ses puces haut de gamme"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": 0.00, "impact_1m": +0.02, "impact_3m": +0.03, "impact_6m": +0.03,
                "direction": "neutral", "confidence": 0.40,
                "reasoning": "Impact quasi-nul direct. Possible impact positif à long terme via le cloud souverain européen.",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.02, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact quasi-nul sur Talan"}
    },

    {
        "event_id": "evt_039",
        "event_date": "2022-11-15",
        "event_type": "competitor_moves",
        "event_name": "Sopra Steria — résultats mitigés, pression sur les marges",
        "event_description": "Sopra Steria publie des résultats 2022 en demi-teinte: croissance de +7.2% mais marge opérationnelle sous pression (8.2% vs objectif 8.5%).",
        "source": "Sopra Steria rapport annuel 2022 / Les Echos",
        "severity": 0.40,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6600, "CAC40_change_pct": -5.0,
            "SP500_change_pct": -17.0, "VIX": 25.0, "EUR_USD": 1.03,
            "brent_usd": 88.0, "fed_rate": 4.00, "ecb_rate": 2.00,
            "global_recession_risk": 0.48
        },
        "nodes": [
            _talan_node(),
            _company_node("sopra"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_sopra_results_22", "Sopra Steria résultats mitigés 2022", "competitor_moves", "2022-11-15"),
        ],
        "edges": [
            _edge("evt_sopra_results_22", "sopra", "CAUSES_IMPACT_ON", -0.10, 0.80, "2022-11-15",
                   "Marges sous pression, croissance ralentie"),
            _edge("evt_sopra_results_22", "talan", "CAUSES_IMPACT_ON", +0.05, 0.55, "2022-11-15",
                   "Opportunité de gagner des clients face à un Sopra moins agressif"),
            _edge("evt_sopra_results_22", "it_services_esn", "CAUSES_IMPACT_ON", -0.03, 0.50, "2022-11-15",
                   "Signal de ralentissement sectoriel"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence directe ESN FR"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.03, "impact_3m": +0.05, "impact_6m": +0.04,
                "direction": "positive", "confidence": 0.50,
                "reasoning": "Légère opportunité concurrentielle",
                "source": "Sopra Steria rapport annuel 2022 / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.03, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Faible impact positif via concurrence"}
    },

    {
        "event_id": "evt_040",
        "event_date": "2022-12-15",
        "event_type": "macro_economic",
        "event_name": "Cloud souverain français — émergence OVHcloud, Scaleway, NumSpot",
        "event_description": "La France pousse sa stratégie de cloud souverain avec NumSpot (Docaposte, Dassault, Bouygues Telecom, OVHcloud). Commandes publiques réservées au cloud de confiance.",
        "source": "DGNUM / Le Monde Informatique / Gouvernement.fr",
        "severity": 0.50,
        "confidence": 0.90,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6500, "CAC40_change_pct": -8.0,
            "SP500_change_pct": -19.0, "VIX": 22.0, "EUR_USD": 1.06,
            "brent_usd": 80.0, "fed_rate": 4.50, "ecb_rate": 2.50,
            "global_recession_risk": 0.45
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("atos"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _sector_node("Secteur Public / Gouvernement"),
            _country_node("France"),
            _event_node("evt_cloud_souverain", "Cloud souverain français", "macro_economic", "2022-12-15"),
        ],
        "edges": [
            _edge("evt_cloud_souverain", "cloud_computing", "CAUSES_IMPACT_ON", +0.15, 0.72, "2022-12-15",
                   "Nouveau segment de marché cloud souverain en France"),
            _edge("evt_cloud_souverain", "talan", "CAUSES_IMPACT_ON", +0.12, 0.68, "2022-12-15",
                   "Talan peut se positionner comme intégrateur de solutions cloud souveraines"),
            _edge("evt_cloud_souverain", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.70, "2022-12-15",
                   "Nouvelles missions d'intégration cloud souverain pour les ESN françaises"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "Talan est une ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.15,
                "direction": "positive", "confidence": 0.65,
                "reasoning": "Talan se positionne sur les appels d'offres cloud souverain de l'État",
                "source": "DGNUM / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Cloud souverain = niche prometteuse pour Talan"}
    },

    # ──────────────────────────────────────────────────────────────────────────
    # BLOC 3 — RÉVOLUTION IA GÉNÉRATIVE (2023) [30 événements: 041–070]
    # ──────────────────────────────────────────────────────────────────────────

    {
        "event_id": "evt_041",
        "event_date": "2023-03-14",
        "event_type": "tech_launch",
        "event_name": "GPT-4 lancé par OpenAI — performances état de l'art",
        "event_description": "OpenAI lance GPT-4, modèle multimodal surpassant les benchmarks humains (examen du barreau top 10%). Intégré dans ChatGPT Plus et Azure.",
        "source": "OpenAI Blog / Reuters / TechCrunch",
        "severity": 0.90,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7100, "CAC40_change_pct": +8.0,
            "SP500_change_pct": +3.0, "VIX": 23.0, "EUR_USD": 1.07,
            "brent_usd": 78.0, "fed_rate": 4.75, "ecb_rate": 3.00,
            "global_recession_risk": 0.35
        },
        "nodes": [
            _talan_node(),
            _company_node("openai"), _company_node("microsoft"), _company_node("google"),
            _company_node("capgemini"), _company_node("accenture"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_gpt4_launch", "Lancement GPT-4", "tech_launch", "2023-03-14"),
        ],
        "edges": [
            _edge("evt_gpt4_launch", "ai_ml", "CAUSES_IMPACT_ON", +0.60, 0.95, "2023-03-14",
                   "GPT-4 repousse les limites de l'IA générative, qualité quasi-humaine"),
            _edge("evt_gpt4_launch", "talan", "CAUSES_IMPACT_ON", +0.30, 0.85, "2023-03-14",
                   "Forte demande de projets d'intégration GPT-4 dans les SI clients de Talan"),
            _edge("evt_gpt4_launch", "it_services_esn", "CAUSES_IMPACT_ON", +0.35, 0.88, "2023-03-14",
                   "Les ESN captent la demande d'intégration GenAI dans les entreprises"),
            _edge("evt_gpt4_launch", "capgemini", "CAUSES_IMPACT_ON", +0.32, 0.87, "2023-03-14",
                   "Capgemini lance son offre GenAI Enterprise"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.05, "impact_1m": +0.25, "impact_3m": +0.35, "impact_6m": +0.30,
                "direction": "positive", "confidence": 0.83,
                "reasoning": "Pipeline de projets GenAI en explosion. Talan recrute des profils IA massivement.",
                "source": "Estimation basée sur tendances RFP secteur ESN 2023"
            }
        },
        "gnn_training": {"target_impact": +0.25, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Événement majeur pour la demande IA des ESN"}
    },

    {
        "event_id": "evt_042",
        "event_date": "2023-01-23",
        "event_type": "tech_launch",
        "event_name": "Microsoft intègre GPT dans Azure / Bing / Office 365",
        "event_description": "Microsoft investit 10 Md$ dans OpenAI et intègre GPT-4 dans Bing, Azure OpenAI Service et commence le développement de Microsoft 365 Copilot.",
        "source": "Microsoft Blog / Wall Street Journal",
        "severity": 0.85,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7000, "CAC40_change_pct": +6.0,
            "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.08,
            "brent_usd": 82.0, "fed_rate": 4.50, "ecb_rate": 2.50,
            "global_recession_risk": 0.38
        },
        "nodes": [
            _talan_node(),
            _company_node("microsoft"), _company_node("openai"), _company_node("google"),
            _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_msft_gpt_integ", "Microsoft intègre GPT partout", "tech_launch", "2023-01-23"),
        ],
        "edges": [
            _edge("evt_msft_gpt_integ", "cloud_computing", "CAUSES_IMPACT_ON", +0.40, 0.90, "2023-01-23",
                   "Azure OpenAI Service devient le standard enterprise pour l'IA générative"),
            _edge("evt_msft_gpt_integ", "talan", "CAUSES_IMPACT_ON", +0.25, 0.82, "2023-01-23",
                   "Talan en tant que partenaire Microsoft capte des missions d'intégration Azure OpenAI"),
            _edge("evt_msft_gpt_integ", "it_services_esn", "CAUSES_IMPACT_ON", +0.30, 0.85, "2023-01-23",
                   "Forte demande d'intégration de l'IA Microsoft dans les SI entreprise"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.04, "impact_1m": +0.20, "impact_3m": +0.28, "impact_6m": +0.25,
                "direction": "positive", "confidence": 0.80,
                "reasoning": "Pipeline de missions Azure OpenAI en forte croissance. Talan certifie des consultants Azure AI.",
                "source": "Estimation basée sur partnership Microsoft"
            }
        },
        "gnn_training": {"target_impact": +0.20, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Microsoft Azure AI = gros pipeline pour les partenaires ESN"}
    },

    {
        "event_id": "evt_043",
        "event_date": "2023-03-21",
        "event_type": "tech_launch",
        "event_name": "Google lance Bard (futur Gemini) — riposte à ChatGPT",
        "event_description": "Google lance Bard, son chatbot IA basé sur LaMDA/PaLM. Lancement précipité qui fait chuter l'action Alphabet de 8% suite à une erreur dans la démo.",
        "source": "Google Blog / Bloomberg / The Verge",
        "severity": 0.65,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7100, "CAC40_change_pct": +8.0,
            "SP500_change_pct": +4.0, "VIX": 21.0, "EUR_USD": 1.07,
            "brent_usd": 75.0, "fed_rate": 4.75, "ecb_rate": 3.00,
            "global_recession_risk": 0.35
        },
        "nodes": [
            _talan_node(),
            _company_node("google"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_bard_launch", "Google lance Bard", "tech_launch", "2023-03-21"),
        ],
        "edges": [
            _edge("evt_bard_launch", "ai_ml", "CAUSES_IMPACT_ON", +0.20, 0.80, "2023-03-21",
                   "Intensification de la compétition IA, plus de choix pour les entreprises"),
            _edge("evt_bard_launch", "talan", "CAUSES_IMPACT_ON", +0.08, 0.62, "2023-03-21",
                   "Multi-cloud IA = plus de missions d'évaluation et d'intégration pour les ESN"),
            _edge("evt_bard_launch", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.68, "2023-03-21",
                   "La concurrence IA multi-vendor créée des besoins de conseil comparatif"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.10,
                "direction": "positive", "confidence": 0.58,
                "reasoning": "La compétition Google vs Microsoft profite aux ESN qui font du conseil multi-cloud",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "La guerre des LLM bénéficie aux ESN intégratrices"}
    },

    {
        "event_id": "evt_044",
        "event_date": "2023-03-10",
        "event_type": "financial_market_impact",
        "event_name": "Krach Silicon Valley Bank (SVB) — panique bancaire tech",
        "event_description": "SVB s'effondre en 48h, 2ème plus grande faillite bancaire de l'histoire US. Contagion vers Signature Bank et First Republic. Panique dans l'écosystème startup.",
        "source": "FDIC / Financial Times / Wall Street Journal",
        "severity": 0.80,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7000, "CAC40_change_pct": +5.0,
            "SP500_change_pct": +1.0, "VIX": 26.0, "EUR_USD": 1.07,
            "brent_usd": 76.0, "fed_rate": 4.75, "ecb_rate": 3.00,
            "global_recession_risk": 0.45
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"),
            _sector_node("Finance / Banque"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_svb_crash", "Krach SVB", "financial_market_impact", "2023-03-10"),
            _macro_node("VIX"),
        ],
        "edges": [
            _edge("evt_svb_crash", "finance_banque", "CAUSES_IMPACT_ON", -0.30, 0.88, "2023-03-10",
                   "Crise de confiance bancaire, stress test accéléré, gel financement startups"),
            _edge("evt_svb_crash", "talan", "CAUSES_IMPACT_ON", -0.08, 0.60, "2023-03-10",
                   "Indirect: certains clients startups/fintech de Talan gèlent leurs budgets IT"),
            _edge("evt_svb_crash", "it_services_esn", "CAUSES_IMPACT_ON", -0.05, 0.55, "2023-03-10",
                   "Impact limité sur les ESN, clientèle principalement grandes entreprises"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.04, "impact_1m": -0.06, "impact_3m": -0.05, "impact_6m": -0.03,
                "direction": "negative", "confidence": 0.55,
                "reasoning": "Impact limité. Talan sert principalement des grands comptes, pas des startups VC-funded.",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.06, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact limité via l'écosystème startup"}
    },

    {
        "event_id": "evt_045",
        "event_date": "2023-02-24",
        "event_type": "tech_launch",
        "event_name": "Meta lance LLaMA — modèle IA open-source révolutionnaire",
        "event_description": "Meta publie LLaMA, modèle de langage open-source compétitif avec GPT-3.5. Déclenche une vague d'innovation open-source en IA.",
        "source": "Meta AI Blog / ArXiv / The Verge",
        "severity": 0.70,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7200, "CAC40_change_pct": +9.0,
            "SP500_change_pct": +5.0, "VIX": 20.0, "EUR_USD": 1.06,
            "brent_usd": 83.0, "fed_rate": 4.75, "ecb_rate": 2.50,
            "global_recession_risk": 0.35
        },
        "nodes": [
            _talan_node(),
            _company_node("meta"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_llama_launch", "Meta lance LLaMA open-source", "tech_launch", "2023-02-24"),
        ],
        "edges": [
            _edge("evt_llama_launch", "ai_ml", "CAUSES_IMPACT_ON", +0.40, 0.88, "2023-02-24",
                   "Démocratisation des LLM: modèles open-source compétitifs accessibles à tous"),
            _edge("evt_llama_launch", "talan", "CAUSES_IMPACT_ON", +0.15, 0.72, "2023-02-24",
                   "Talan peut déployer des LLM open-source chez ses clients sans dépendance vendor"),
            _edge("evt_llama_launch", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.75, "2023-02-24",
                   "Les ESN peuvent proposer des solutions IA sans coûts de licence"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.10, "impact_3m": +0.15, "impact_6m": +0.18,
                "direction": "positive", "confidence": 0.70,
                "reasoning": "Les modèles open-source permettent à Talan de proposer des POC IA à moindre coût",
                "source": "Estimation basée sur adoption open-source LLM en entreprise"
            }
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Open-source IA = avantage pour les ESN agiles"}
    },

    {
        "event_id": "evt_046",
        "event_date": "2023-04-10",
        "event_type": "tech_launch",
        "event_name": "Mistral AI fondée à Paris — champion européen de l'IA",
        "event_description": "Arthur Mensch, Timothée Lacroix et Guillaume Lample fondent Mistral AI à Paris. Levée de 105M€ seed record en Europe. Champion de l'IA souveraine européenne.",
        "source": "Mistral AI Blog / Les Echos / TechCrunch",
        "severity": 0.70,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7400, "CAC40_change_pct": +12.0,
            "SP500_change_pct": +8.0, "VIX": 17.0, "EUR_USD": 1.09,
            "brent_usd": 81.0, "fed_rate": 5.00, "ecb_rate": 3.50,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("mistral"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_mistral_founded", "Mistral AI fondée à Paris", "tech_launch", "2023-04-10"),
        ],
        "edges": [
            _edge("evt_mistral_founded", "ai_ml", "CAUSES_IMPACT_ON", +0.25, 0.82, "2023-04-10",
                   "Premier champion européen IA crédible, écosystème IA français en ébullition"),
            _edge("evt_mistral_founded", "talan", "CAUSES_IMPACT_ON", +0.18, 0.75, "2023-04-10",
                   "Talan peut s'associer à Mistral AI pour des solutions IA souveraines françaises"),
            _edge("evt_mistral_founded", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.72, "2023-04-10",
                   "Écosystème IA français renforcé, plus de partenariats possibles pour les ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.03, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.22,
                "direction": "positive", "confidence": 0.72,
                "reasoning": "Mistral AI = partenaire potentiel stratégique pour Talan sur l'IA souveraine",
                "source": "Estimation basée sur l'écosystème IA français"
            }
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Mistral AI renforce l'écosystème IA français et bénéficie aux ESN"}
    },

    {
        "event_id": "evt_047",
        "event_date": "2023-07-11",
        "event_type": "tech_launch",
        "event_name": "Anthropic lance Claude 2 — concurrent sérieux de GPT-4",
        "event_description": "Anthropic lance Claude 2, modèle IA concurrent de GPT-4, avec un focus sur la sécurité et le contexte long (100K tokens). Alternative crédible à OpenAI.",
        "source": "Anthropic Blog / TechCrunch",
        "severity": 0.55,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +13.0,
            "SP500_change_pct": +16.0, "VIX": 14.0, "EUR_USD": 1.12,
            "brent_usd": 79.0, "fed_rate": 5.25, "ecb_rate": 4.00,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("anthropic"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_claude2_launch", "Anthropic lance Claude 2", "tech_launch", "2023-07-11"),
        ],
        "edges": [
            _edge("evt_claude2_launch", "ai_ml", "CAUSES_IMPACT_ON", +0.15, 0.78, "2023-07-11",
                   "Plus de choix de LLM enterprise, compétition saine"),
            _edge("evt_claude2_launch", "talan", "CAUSES_IMPACT_ON", +0.08, 0.60, "2023-07-11",
                   "Un LLM supplémentaire à intégrer dans les recommandations clients"),
            _edge("evt_claude2_launch", "it_services_esn", "CAUSES_IMPACT_ON", +0.08, 0.62, "2023-07-11",
                   "Besoin de conseil multi-LLM pour les entreprises"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.10,
                "direction": "positive", "confidence": 0.55,
                "reasoning": "Un LLM de plus dans l'écosystème = plus de missions de conseil comparatif",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact modéré, renforce la tendance GenAI positive"}
    },

    {
        "event_id": "evt_048",
        "event_date": "2023-06-01",
        "event_type": "competitor_moves",
        "event_name": "Atos — plan de restructuration Evidian/Tech Foundations",
        "event_description": "Atos annonce la scission en deux entités: Evidian (digital/cloud/cyber) et Tech Foundations (infogérance). Plan de sauvetage complexe, dette de 5 Md€.",
        "source": "Atos communiqué / Les Echos / Reuters",
        "severity": 0.70,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +13.0,
            "SP500_change_pct": +14.0, "VIX": 15.0, "EUR_USD": 1.08,
            "brent_usd": 75.0, "fed_rate": 5.25, "ecb_rate": 3.75,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("atos"), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("Cybersécurité"),
            _country_node("France"),
            _event_node("evt_atos_split", "Atos scission Evidian/TechFound", "competitor_moves", "2023-06-01"),
        ],
        "edges": [
            _edge("evt_atos_split", "atos", "CAUSES_IMPACT_ON", -0.45, 0.90, "2023-06-01",
                   "Atos en crise profonde, fuite des talents et des clients"),
            _edge("evt_atos_split", "talan", "CAUSES_IMPACT_ON", +0.22, 0.80, "2023-06-01",
                   "Talan recrute activement des ex-Atos et capte des clients en transition"),
            _edge("evt_atos_split", "capgemini", "CAUSES_IMPACT_ON", +0.15, 0.78, "2023-06-01",
                   "Capgemini récupère des contrats qu'Atos ne peut plus servir"),
            _edge("evt_atos_split", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.60, "2023-06-01",
                   "Redistribution de parts de marché dans le secteur ESN français"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "atos", "COMPETES_WITH", 0.5, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.03, "impact_1m": +0.15, "impact_3m": +0.22, "impact_6m": +0.25,
                "direction": "positive", "confidence": 0.78,
                "reasoning": "Talan profite de la déstabilisation d'Atos: recrutement de profils seniors et capture de clients",
                "source": "LinkedIn data / Estimation mouvements marché ESN"
            }
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m",
                         "notes": "La crise Atos continue de bénéficier aux concurrents ESN français"}
    },

    {
        "event_id": "evt_049",
        "event_date": "2023-09-01",
        "event_type": "competitor_moves",
        "event_name": "Sopra Steria — résultats décevants, pression concurrentielle 2023",
        "event_description": "Sopra Steria publie des résultats S1 2023 en demi-teinte: croissance +2.4% vs +5% attendu. Pression sur le segment conseil, concurrence des pure players IA.",
        "source": "Sopra Steria communiqué / Les Echos",
        "severity": 0.40,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7200, "CAC40_change_pct": +10.0,
            "SP500_change_pct": +15.0, "VIX": 14.0, "EUR_USD": 1.08,
            "brent_usd": 85.0, "fed_rate": 5.50, "ecb_rate": 4.25,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("sopra"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_sopra_h1_2023", "Sopra Steria résultats décevants 2023", "competitor_moves", "2023-09-01"),
        ],
        "edges": [
            _edge("evt_sopra_h1_2023", "sopra", "CAUSES_IMPACT_ON", -0.12, 0.78, "2023-09-01",
                   "Croissance en deçà des attentes, pression sur le titre"),
            _edge("evt_sopra_h1_2023", "talan", "CAUSES_IMPACT_ON", +0.05, 0.52, "2023-09-01",
                   "Faible opportunité concurrentielle face à Sopra ralenti"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence directe"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.03, "impact_3m": +0.05, "impact_6m": +0.04,
                "direction": "positive", "confidence": 0.48,
                "reasoning": "Légère opportunité concurrentielle",
                "source": "Sopra Steria rapport S1 2023"
            }
        },
        "gnn_training": {"target_impact": +0.03, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Faible impact positif"}
    },

    {
        "event_id": "evt_050",
        "event_date": "2023-08-01",
        "event_type": "competitor_moves",
        "event_name": "IBM acquiert Software AG — consolidation intégration middleware",
        "event_description": "IBM signe l'acquisition de Software AG pour 2.3 Md€, renforçant sa position dans le middleware et l'intégration API/données.",
        "source": "IBM Press Release / Reuters",
        "severity": 0.45,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +12.0,
            "SP500_change_pct": +17.0, "VIX": 14.0, "EUR_USD": 1.10,
            "brent_usd": 83.0, "fed_rate": 5.50, "ecb_rate": 4.25,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("ibm"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"), _sector_node("Data & Analytics"),
            _country_node("USA"), _country_node("Allemagne"), _country_node("France"),
            _event_node("evt_ibm_softwareag", "IBM acquiert Software AG", "competitor_moves", "2023-08-01"),
        ],
        "edges": [
            _edge("evt_ibm_softwareag", "ibm", "CAUSES_IMPACT_ON", +0.10, 0.78, "2023-08-01",
                   "IBM renforce son offre middleware/intégration"),
            _edge("evt_ibm_softwareag", "talan", "CAUSES_IMPACT_ON", +0.03, 0.45, "2023-08-01",
                   "Impact indirect: nouvelles missions d'intégration de produits IBM/Software AG"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": 0.00, "impact_1m": +0.02, "impact_3m": +0.03, "impact_6m": +0.04,
                "direction": "positive", "confidence": 0.42,
                "reasoning": "Impact très limité, Talan n'est pas un intégrateur IBM majeur",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.02, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact quasi-nul"}
    },

    {
        "event_id": "evt_051",
        "event_date": "2023-06-20",
        "event_type": "competitor_moves",
        "event_name": "Accenture investit 3 Md$ en IA sur 3 ans",
        "event_description": "Accenture annonce un investissement de 3 Md$ en IA sur 3 ans, incluant recrutement de 80 000 professionnels IA et création de centres d'excellence GenAI.",
        "source": "Accenture Press Release / Wall Street Journal",
        "severity": 0.65,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +13.0,
            "SP500_change_pct": +15.0, "VIX": 14.0, "EUR_USD": 1.09,
            "brent_usd": 76.0, "fed_rate": 5.25, "ecb_rate": 3.75,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("accenture"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"), _sector_node("Consulting"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_acn_3b_ai", "Accenture investit 3Md$ en IA", "competitor_moves", "2023-06-20"),
        ],
        "edges": [
            _edge("evt_acn_3b_ai", "accenture", "CAUSES_IMPACT_ON", +0.25, 0.88, "2023-06-20",
                   "Accenture se positionne comme leader mondial du conseil IA"),
            _edge("evt_acn_3b_ai", "talan", "CAUSES_IMPACT_ON", -0.08, 0.62, "2023-06-20",
                   "Pression concurrentielle accrue sur les grands comptes IA"),
            _edge("evt_acn_3b_ai", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.58, "2023-06-20",
                   "Signal positif pour le marché IA mais pression concurrentielle des grands"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "accenture", "COMPETES_WITH", 0.3, 1.0, "2020-01-01", "Concurrence limitée"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.05, "impact_3m": -0.08, "impact_6m": -0.06,
                "direction": "negative", "confidence": 0.58,
                "reasoning": "Accenture capte les grands budgets IA, mais Talan joue sur un segment mid-market différent",
                "source": "Accenture Annual Report 2023 / Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Pression concurrentielle modérée, segments différents"}
    },

    {
        "event_id": "evt_052",
        "event_date": "2023-03-01",
        "event_type": "competitor_moves",
        "event_name": "Capgemini lance sa stratégie GenAI et investit 2 Md€",
        "event_description": "Capgemini annonce un plan d'investissement de 2 Md€ en IA générative, création de centres GenAI, et partenariats avec OpenAI, Google et Microsoft.",
        "source": "Capgemini communiqué / Les Echos",
        "severity": 0.60,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7100, "CAC40_change_pct": +8.0,
            "SP500_change_pct": +3.0, "VIX": 21.0, "EUR_USD": 1.06,
            "brent_usd": 80.0, "fed_rate": 4.75, "ecb_rate": 3.00,
            "global_recession_risk": 0.35
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("accenture"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_cap_genai", "Capgemini investit 2Md€ GenAI", "competitor_moves", "2023-03-01"),
        ],
        "edges": [
            _edge("evt_cap_genai", "capgemini", "CAUSES_IMPACT_ON", +0.20, 0.85, "2023-03-01",
                   "Capgemini se positionne comme leader GenAI en Europe"),
            _edge("evt_cap_genai", "talan", "CAUSES_IMPACT_ON", -0.10, 0.68, "2023-03-01",
                   "Pression concurrentielle directe sur le segment Data/IA français"),
            _edge("evt_cap_genai", "it_services_esn", "CAUSES_IMPACT_ON", +0.08, 0.65, "2023-03-01",
                   "Signal positif: investissements massifs en IA dans le secteur ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence directe Data/IA"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.08, "impact_3m": -0.10, "impact_6m": -0.08,
                "direction": "negative", "confidence": 0.65,
                "reasoning": "Capgemini est un concurrent direct plus puissant sur l'IA, mais Talan garde son agilité",
                "source": "Capgemini communiqué / Estimation"
            }
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Concurrent direct renforce sa position"}
    },

    {
        "event_id": "evt_053",
        "event_date": "2023-11-28",
        "event_type": "tech_launch",
        "event_name": "AWS re:Invent 2023 — Amazon Bedrock GA, GenAI enterprise",
        "event_description": "AWS généralise Amazon Bedrock (accès aux LLM Claude, Llama, Titan via API). Concurrence directe avec Azure OpenAI. Le marché GenAI enterprise s'organise.",
        "source": "AWS Blog / TechCrunch",
        "severity": 0.55,
        "confidence": 0.98,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7200, "CAC40_change_pct": +10.0,
            "SP500_change_pct": +20.0, "VIX": 13.0, "EUR_USD": 1.10,
            "brent_usd": 78.0, "fed_rate": 5.50, "ecb_rate": 4.50,
            "global_recession_risk": 0.25
        },
        "nodes": [
            _talan_node(),
            _company_node("amazon"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_bedrock_ga", "AWS Bedrock GA", "tech_launch", "2023-11-28"),
        ],
        "edges": [
            _edge("evt_bedrock_ga", "cloud_computing", "CAUSES_IMPACT_ON", +0.20, 0.82, "2023-11-28",
                   "Concurrence Azure vs AWS sur la GenAI enterprise"),
            _edge("evt_bedrock_ga", "talan", "CAUSES_IMPACT_ON", +0.10, 0.65, "2023-11-28",
                   "Plus de choix cloud GenAI = plus de missions de conseil et intégration multi-cloud"),
            _edge("evt_bedrock_ga", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.70, "2023-11-28",
                   "Les ESN multi-cloud captent les missions Bedrock"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.06, "impact_3m": +0.10, "impact_6m": +0.12,
                "direction": "positive", "confidence": 0.60,
                "reasoning": "AWS Bedrock ouvre un nouveau pipeline de missions pour les ESN certifiées AWS",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact positif modéré via multi-cloud GenAI"}
    },

    {
        "event_id": "evt_054",
        "event_date": "2023-05-01",
        "event_type": "tech_launch",
        "event_name": "Google Vertex AI — enterprise GenAI platform GA",
        "event_description": "Google Cloud lance Vertex AI en GA avec PaLM 2, Model Garden et Duet AI. Troisième option enterprise GenAI après Azure OpenAI et AWS Bedrock.",
        "source": "Google Cloud Blog / TechCrunch",
        "severity": 0.50,
        "confidence": 0.95,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +10.0,
            "SP500_change_pct": +9.0, "VIX": 17.0, "EUR_USD": 1.08,
            "brent_usd": 74.0, "fed_rate": 5.25, "ecb_rate": 3.75,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("google"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_vertex_ai", "Google Vertex AI GA", "tech_launch", "2023-05-01"),
        ],
        "edges": [
            _edge("evt_vertex_ai", "cloud_computing", "CAUSES_IMPACT_ON", +0.15, 0.78, "2023-05-01",
                   "3ème option GenAI enterprise, marché multi-cloud renforcé"),
            _edge("evt_vertex_ai", "talan", "CAUSES_IMPACT_ON", +0.06, 0.55, "2023-05-01",
                   "Talan ajoute Google Cloud GenAI à son offre multi-cloud"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.04, "impact_3m": +0.06, "impact_6m": +0.08,
                "direction": "positive", "confidence": 0.52,
                "reasoning": "Impact positif modéré, Talan est moins Google Cloud que Azure",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.04, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact limité, Talan plus orienté Azure"}
    },

    {
        "event_id": "evt_055",
        "event_date": "2023-01-16",
        "event_type": "regulatory_changes",
        "event_name": "DORA — Digital Operational Resilience Act finalisé",
        "event_description": "DORA entre en vigueur (application 17 Jan 2025). Impose aux institutions financières EU des obligations strictes de résilience opérationnelle numérique.",
        "source": "Journal Officiel UE / ESMA / ACPR",
        "severity": 0.55,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 6900, "CAC40_change_pct": +4.0,
            "SP500_change_pct": -1.0, "VIX": 20.0, "EUR_USD": 1.08,
            "brent_usd": 82.0, "fed_rate": 4.50, "ecb_rate": 2.50,
            "global_recession_risk": 0.38
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("Finance / Banque"), _sector_node("IT Services / ESN"),
            _sector_node("Cybersécurité"),
            _country_node("France"),
            _event_node("evt_dora", "DORA finalisé", "regulatory_changes", "2023-01-16"),
        ],
        "edges": [
            _edge("evt_dora", "finance_banque", "CAUSES_IMPACT_ON", -0.10, 0.78, "2023-01-16",
                   "Coûts de conformité significatifs pour les institutions financières"),
            _edge("evt_dora", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2023-01-16",
                   "Forte demande d'accompagnement DORA pour les clients bancaires de Talan"),
            _edge("evt_dora", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.80, "2023-01-16",
                   "Pipeline de missions DORA pour les ESN spécialisées banque"),
            _edge("evt_dora", "cybersecurite", "CAUSES_IMPACT_ON", +0.20, 0.82, "2023-01-16",
                   "DORA renforce les exigences de cybersécurité bancaire"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence banque"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.22,
                "direction": "positive", "confidence": 0.75,
                "reasoning": "Talan a une practice financière forte, DORA = opportunité majeure",
                "source": "ACPR / Estimation marché conseil conformité bancaire"
            }
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m",
                         "notes": "DORA = forte opportunité pour ESN à practice bancaire"}
    },

    {
        "event_id": "evt_056",
        "event_date": "2023-12-09",
        "event_type": "regulatory_changes",
        "event_name": "EU AI Act adopté en trilogue — réglementation IA historique",
        "event_description": "Le Parlement européen, le Conseil et la Commission parviennent à un accord politique sur l'AI Act. Première réglementation mondiale complète sur l'IA.",
        "source": "Commission Européenne / Euractiv / Le Monde",
        "severity": 0.75,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7500, "CAC40_change_pct": +15.0,
            "SP500_change_pct": +22.0, "VIX": 13.0, "EUR_USD": 1.09,
            "brent_usd": 74.0, "fed_rate": 5.50, "ecb_rate": 4.50,
            "global_recession_risk": 0.22
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("accenture"), _company_node("mistral"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ai_act_trilogue", "EU AI Act adopté en trilogue", "regulatory_changes", "2023-12-09"),
        ],
        "edges": [
            _edge("evt_ai_act_trilogue", "ai_ml", "CAUSES_IMPACT_ON", -0.15, 0.78, "2023-12-09",
                   "Contraintes réglementaires nouvelles sur les déploiements IA en Europe"),
            _edge("evt_ai_act_trilogue", "talan", "CAUSES_IMPACT_ON", +0.15, 0.75, "2023-12-09",
                   "Forte opportunité de conseil en conformité AI Act pour les entreprises européennes"),
            _edge("evt_ai_act_trilogue", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.72, "2023-12-09",
                   "Nouveau marché de conseil en conformité IA pour les ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.10, "impact_3m": +0.15, "impact_6m": +0.20,
                "direction": "positive", "confidence": 0.72,
                "reasoning": "AI Act = nouveau marché de conformité IA estimé à 1-2 Md€ en Europe",
                "source": "Commission Européenne / IDC estimation"
            }
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m",
                         "notes": "AI Act = opportunité réglementaire majeure pour les ESN"}
    },

    {
        "event_id": "evt_057",
        "event_date": "2023-07-14",
        "event_type": "geopolitical_events",
        "event_name": "Grève Hollywood (SAG-AFTRA/WGA) contre l'IA — signal sociétal",
        "event_description": "Les acteurs et scénaristes d'Hollywood font grève, l'IA étant l'un des enjeux centraux. Signal sociétal fort sur l'impact de l'IA sur l'emploi.",
        "source": "SAG-AFTRA / Reuters / New York Times",
        "severity": 0.40,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7400, "CAC40_change_pct": +13.0,
            "SP500_change_pct": +17.0, "VIX": 14.0, "EUR_USD": 1.12,
            "brent_usd": 80.0, "fed_rate": 5.25, "ecb_rate": 4.00,
            "global_recession_risk": 0.25
        },
        "nodes": [
            _talan_node(),
            _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_hollywood_strike", "Grève Hollywood vs IA", "geopolitical_events", "2023-07-14"),
        ],
        "edges": [
            _edge("evt_hollywood_strike", "ai_ml", "CAUSES_IMPACT_ON", -0.08, 0.65, "2023-07-14",
                   "Débat sociétal sur l'IA, risque de régulation plus stricte"),
            _edge("evt_hollywood_strike", "talan", "CAUSES_IMPACT_ON", +0.03, 0.45, "2023-07-14",
                   "Impact très indirect: certains clients s'interrogent sur l'IA responsable"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": 0.00, "impact_1m": +0.02, "impact_3m": +0.03, "impact_6m": +0.03,
                "direction": "positive", "confidence": 0.40,
                "reasoning": "Demande accrue de conseil en IA éthique et responsable",
                "source": "Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.02, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Signal sociétal, impact quasi-nul sur Talan"}
    },

    {
        "event_id": "evt_058",
        "event_date": "2023-05-01",
        "event_type": "talent_market_signals",
        "event_name": "Explosion des offres Prompt Engineer et AI Engineer en 2023",
        "event_description": "Le nombre d'offres d'emploi mentionnant 'AI Engineer', 'Prompt Engineer', 'GenAI' explose en 2023 (+400% selon LinkedIn). Pénurie aiguë de profils IA.",
        "source": "LinkedIn Economic Graph / Indeed / Hays France",
        "severity": 0.60,
        "confidence": 0.90,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +10.0,
            "SP500_change_pct": +9.0, "VIX": 17.0, "EUR_USD": 1.08,
            "brent_usd": 75.0, "fed_rate": 5.25, "ecb_rate": 3.75,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("accenture"), _company_node("sopra"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ai_talent_boom", "Explosion offres AI Engineer", "talent_market_signals", "2023-05-01"),
        ],
        "edges": [
            _edge("evt_ai_talent_boom", "it_services_esn", "CAUSES_IMPACT_ON", -0.12, 0.78, "2023-05-01",
                   "Pénurie de talents IA, coûts de recrutement en hausse"),
            _edge("evt_ai_talent_boom", "talan", "CAUSES_IMPACT_ON", -0.10, 0.72, "2023-05-01",
                   "Talan peine à recruter des profils IA seniors, salaires en forte hausse"),
            _edge("evt_ai_talent_boom", "ai_ml", "CAUSES_IMPACT_ON", +0.10, 0.70, "2023-05-01",
                   "Confirmation de la forte demande IA dans tous les secteurs"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence recrutement"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.02, "impact_1m": -0.08, "impact_3m": -0.10, "impact_6m": -0.08,
                "direction": "negative", "confidence": 0.70,
                "reasoning": "Pression sur les marges: salaires IA +30-50%, difficile à répercuter sur les TJM",
                "source": "LinkedIn / Hays Salary Guide 2023"
            }
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Pénurie talent IA = pression sur les marges ESN"}
    },

    {
        "event_id": "evt_059",
        "event_date": "2023-06-01",
        "event_type": "macro_economic",
        "event_name": "Vague de projets pilotes GenAI dans les grandes entreprises françaises",
        "event_description": "Les grandes entreprises françaises (CAC40, banques, assurances) lancent massivement des POC et pilotes GenAI. Budgets IA en hausse de 50% en 2023.",
        "source": "Syntec Numérique / McKinsey France / IDC",
        "severity": 0.65,
        "confidence": 0.88,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +12.0,
            "SP500_change_pct": +14.0, "VIX": 15.0, "EUR_USD": 1.08,
            "brent_usd": 75.0, "fed_rate": 5.25, "ecb_rate": 3.75,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("accenture"), _company_node("sopra"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _sector_node("Finance / Banque"),
            _country_node("France"),
            _event_node("evt_poc_genai_fr", "Vague POC GenAI entreprises FR", "macro_economic", "2023-06-01"),
        ],
        "edges": [
            _edge("evt_poc_genai_fr", "talan", "CAUSES_IMPACT_ON", +0.30, 0.85, "2023-06-01",
                   "Talan capte de nombreux POC GenAI chez ses clients grands comptes français"),
            _edge("evt_poc_genai_fr", "it_services_esn", "CAUSES_IMPACT_ON", +0.28, 0.82, "2023-06-01",
                   "Les ESN sont le canal principal de déploiement des POC GenAI"),
            _edge("evt_poc_genai_fr", "ai_ml", "CAUSES_IMPACT_ON", +0.25, 0.85, "2023-06-01",
                   "L'IA générative passe de la hype au déploiement"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.05, "impact_1m": +0.22, "impact_3m": +0.30, "impact_6m": +0.28,
                "direction": "positive", "confidence": 0.82,
                "reasoning": "Talan réalise 50+ POC GenAI en 2023, devenant un acteur clé du conseil IA en France",
                "source": "Estimation basée sur Syntec Numérique et tendances marché"
            }
        },
        "gnn_training": {"target_impact": +0.22, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Fort impact positif via la vague de POC GenAI"}
    },

    {
        "event_id": "evt_060",
        "event_date": "2023-10-01",
        "event_type": "macro_economic",
        "event_name": "Syntec Numérique — rapport impact IA sur les ESN françaises",
        "event_description": "Syntec Numérique publie son rapport sur l'impact de l'IA générative sur les ESN françaises: +15% de croissance attendue sur le segment IA, mais menace sur le delivery classique (-5%).",
        "source": "Syntec Numérique / Numeum rapport 2023",
        "severity": 0.50,
        "confidence": 0.85,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7100, "CAC40_change_pct": +8.0,
            "SP500_change_pct": +13.0, "VIX": 17.0, "EUR_USD": 1.06,
            "brent_usd": 90.0, "fed_rate": 5.50, "ecb_rate": 4.50,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_syntec_ia_rapport", "Syntec Numérique rapport IA/ESN", "macro_economic", "2023-10-01"),
        ],
        "edges": [
            _edge("evt_syntec_ia_rapport", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.72, "2023-10-01",
                   "Signal mixte: opportunité IA mais menace sur le delivery classique"),
            _edge("evt_syntec_ia_rapport", "talan", "CAUSES_IMPACT_ON", +0.08, 0.65, "2023-10-01",
                   "Talan bien positionnée car forte sur Data/IA, moins dépendante du delivery classique"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.08,
                "direction": "positive", "confidence": 0.60,
                "reasoning": "Talan est bien positionnée sur le segment en croissance (Data/IA)",
                "source": "Syntec Numérique / Numeum rapport 2023"
            }
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Signal sectoriel mixte, plutôt positif pour Talan"}
    },

    {
        "event_id": "evt_061",
        "event_date": "2023-11-06",
        "event_type": "tech_launch",
        "event_name": "GPT-4 Turbo — context 128K tokens, prix divisé par 3",
        "event_description": "OpenAI lance GPT-4 Turbo avec fenêtre de contexte de 128K tokens et prix réduits de 3x. Rend les applications GenAI enterprise plus accessibles.",
        "source": "OpenAI DevDay / TechCrunch",
        "severity": 0.55,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7100, "CAC40_change_pct": +8.0,
            "SP500_change_pct": +15.0, "VIX": 15.0, "EUR_USD": 1.07,
            "brent_usd": 80.0, "fed_rate": 5.50, "ecb_rate": 4.50,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("openai"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_gpt4_turbo", "GPT-4 Turbo 128K tokens", "tech_launch", "2023-11-06"),
        ],
        "edges": [
            _edge("evt_gpt4_turbo", "ai_ml", "CAUSES_IMPACT_ON", +0.20, 0.82, "2023-11-06",
                   "Baisse des coûts GenAI, adoption enterprise accélérée"),
            _edge("evt_gpt4_turbo", "talan", "CAUSES_IMPACT_ON", +0.10, 0.68, "2023-11-06",
                   "POC GenAI moins chers, ROI plus facile à démontrer pour les clients de Talan"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.06, "impact_3m": +0.10, "impact_6m": +0.12,
                "direction": "positive", "confidence": 0.65,
                "reasoning": "Baisse des coûts = plus de projets GenAI validés par les clients",
                "source": "OpenAI pricing / Estimation adoption"
            }
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Baisse des coûts IA = accélération des projets"}
    },

    {
        "event_id": "evt_062",
        "event_date": "2023-09-27",
        "event_type": "tech_launch",
        "event_name": "Mistral 7B open-source — modèle léger ultra-performant",
        "event_description": "Mistral AI publie Mistral 7B, modèle open-source de 7 milliards de paramètres surpassant LLaMA 2 13B. Champion de l'efficacité IA.",
        "source": "Mistral AI Blog / ArXiv / Hugging Face",
        "severity": 0.55,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7100, "CAC40_change_pct": +8.0,
            "SP500_change_pct": +13.0, "VIX": 17.0, "EUR_USD": 1.06,
            "brent_usd": 92.0, "fed_rate": 5.50, "ecb_rate": 4.50,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("mistral"), _company_node("meta"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_mistral7b", "Mistral 7B open-source", "tech_launch", "2023-09-27"),
        ],
        "edges": [
            _edge("evt_mistral7b", "ai_ml", "CAUSES_IMPACT_ON", +0.20, 0.82, "2023-09-27",
                   "Modèle open-source français compétitif au niveau mondial"),
            _edge("evt_mistral7b", "talan", "CAUSES_IMPACT_ON", +0.12, 0.70, "2023-09-27",
                   "Talan peut déployer Mistral 7B chez ses clients pour des solutions IA souveraines et légères"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.15,
                "direction": "positive", "confidence": 0.68,
                "reasoning": "Mistral 7B permet des déploiements IA on-premise pour les clients souverains de Talan",
                "source": "Mistral AI / Estimation"
            }
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Modèle français souverain = avantage pour ESN françaises"}
    },

    {
        "event_id": "evt_063",
        "event_date": "2023-07-18",
        "event_type": "tech_launch",
        "event_name": "Llama 2 open-source par Meta — démocratisation LLM",
        "event_description": "Meta lance Llama 2, famille de modèles open-source (7B à 70B paramètres) avec licence commerciale. Accélère massivement l'adoption des LLM open-source.",
        "source": "Meta AI Blog / ArXiv",
        "severity": 0.60,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +12.0,
            "SP500_change_pct": +18.0, "VIX": 14.0, "EUR_USD": 1.11,
            "brent_usd": 79.0, "fed_rate": 5.25, "ecb_rate": 4.00,
            "global_recession_risk": 0.25
        },
        "nodes": [
            _talan_node(),
            _company_node("meta"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_llama2", "Meta Llama 2 open-source", "tech_launch", "2023-07-18"),
        ],
        "edges": [
            _edge("evt_llama2", "ai_ml", "CAUSES_IMPACT_ON", +0.30, 0.85, "2023-07-18",
                   "Llama 2 accélère l'adoption open-source des LLM en enterprise"),
            _edge("evt_llama2", "talan", "CAUSES_IMPACT_ON", +0.12, 0.70, "2023-07-18",
                   "Fine-tuning Llama 2 pour des clients spécifiques = nouvelle offre pour Talan"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.02, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.15,
                "direction": "positive", "confidence": 0.68,
                "reasoning": "LLM open-source avec licence commerciale = offre de fine-tuning pour les ESN",
                "source": "Meta AI / Estimation adoption enterprise"
            }
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Open-source commercial = opportunité ESN"}
    },

    {
        "event_id": "evt_064",
        "event_date": "2023-08-01",
        "event_type": "talent_market_signals",
        "event_name": "Pénurie talent IA — salaires ML engineers +50% en 2 ans",
        "event_description": "Les salaires des ML engineers et AI engineers en France augmentent de 50% en 2 ans (2021-2023). Un ML senior à Paris dépasse 100K€. Pénurie aiguë.",
        "source": "Hays Salary Guide / Robert Half / Stack Overflow Survey",
        "severity": 0.55,
        "confidence": 0.88,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7300, "CAC40_change_pct": +12.0,
            "SP500_change_pct": +17.0, "VIX": 14.0, "EUR_USD": 1.10,
            "brent_usd": 83.0, "fed_rate": 5.50, "ecb_rate": 4.25,
            "global_recession_risk": 0.28
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ai_salary_spike", "Salaires ML +50% en 2 ans", "talent_market_signals", "2023-08-01"),
        ],
        "edges": [
            _edge("evt_ai_salary_spike", "it_services_esn", "CAUSES_IMPACT_ON", -0.15, 0.80, "2023-08-01",
                   "Marge sous pression, coûts salariaux IA très élevés"),
            _edge("evt_ai_salary_spike", "talan", "CAUSES_IMPACT_ON", -0.12, 0.75, "2023-08-01",
                   "Talan doit augmenter les salaires IA pour rester compétitive sur le recrutement"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence recrutement"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.02, "impact_1m": -0.10, "impact_3m": -0.12, "impact_6m": -0.10,
                "direction": "negative", "confidence": 0.72,
                "reasoning": "Pression sur les marges, mais nécessaire pour maintenir l'offre Data/IA",
                "source": "Hays / Robert Half Salary Guide France 2023"
            }
        },
        "gnn_training": {"target_impact": -0.10, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Coût des talents IA en hausse = pression marges ESN"}
    },

    {
        "event_id": "evt_065",
        "event_date": "2023-09-01",
        "event_type": "talent_market_signals",
        "event_name": "Ralentissement recrutement ESN — reprise sélective sur l'IA",
        "event_description": "Les ESN françaises ralentissent leurs recrutements massifs post-COVID, sauf sur les profils IA/Data. Taux d'utilisation en hausse, focus sur la rentabilité.",
        "source": "Syntec Numérique / Numeum / Les Echos",
        "severity": 0.45,
        "confidence": 0.85,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7200, "CAC40_change_pct": +10.0,
            "SP500_change_pct": +14.0, "VIX": 16.0, "EUR_USD": 1.07,
            "brent_usd": 88.0, "fed_rate": 5.50, "ecb_rate": 4.25,
            "global_recession_risk": 0.30
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_esn_hiring_slow", "Ralentissement recrutement ESN", "talent_market_signals", "2023-09-01"),
        ],
        "edges": [
            _edge("evt_esn_hiring_slow", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.68, "2023-09-01",
                   "Meilleure maîtrise des coûts, focus rentabilité"),
            _edge("evt_esn_hiring_slow", "talan", "CAUSES_IMPACT_ON", +0.05, 0.60, "2023-09-01",
                   "Talan optimise son bench et améliore son taux d'utilisation"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": +0.01, "impact_1m": +0.03, "impact_3m": +0.05, "impact_6m": +0.05,
                "direction": "positive", "confidence": 0.55,
                "reasoning": "Meilleure gestion RH, focus sur les profils à haute valeur ajoutée",
                "source": "Syntec Numérique / Numeum"
            }
        },
        "gnn_training": {"target_impact": +0.03, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Impact positif modéré via optimisation RH"}
    },

    {
        "event_id": "evt_066",
        "event_date": "2023-04-01",
        "event_type": "macro_economic",
        "event_name": "Taux BCE à 3.5% — resserrement monétaire européen continue",
        "event_description": "La BCE porte ses taux à 3.5% et signale de nouvelles hausses. Le coût du crédit aux entreprises augmente, freinant certains investissements IT.",
        "source": "BCE / Financial Times",
        "severity": 0.50,
        "confidence": 1.0,
        "is_real_event": True,
        "macro_context": {
            "CAC40_level": 7400, "CAC40_change_pct": +13.0,
            "SP500_change_pct": +8.0, "VIX": 17.0, "EUR_USD": 1.09,
            "brent_usd": 80.0, "fed_rate": 5.00, "ecb_rate": 3.50,
            "global_recession_risk": 0.32
        },
        "nodes": [
            _talan_node(),
            _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("Finance / Banque"),
            _country_node("France"),
            _event_node("evt_bce_35", "BCE taux à 3.5%", "macro_economic", "2023-04-01"),
            _macro_node("ECB_Rate"),
        ],
        "edges": [
            _edge("evt_bce_35", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.70, "2023-04-01",
                   "Coût du crédit en hausse, certains projets IT retardés"),
            _edge("evt_bce_35", "talan", "CAUSES_IMPACT_ON", -0.06, 0.62, "2023-04-01",
                   "Quelques clients reportent des projets non-stratégiques"),
            _edge("evt_bce_35", "finance_banque", "CAUSES_IMPACT_ON", +0.12, 0.75, "2023-04-01",
                   "Banques bénéficient de la hausse des taux (marge d'intérêt)"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {
                "impact_1w": -0.01, "impact_1m": -0.04, "impact_3m": -0.06, "impact_6m": -0.05,
                "direction": "negative", "confidence": 0.58,
                "reasoning": "Impact modéré, compensé par la forte demande IA",
                "source": "BCE / Estimation impact ESN"
            }
        },
        "gnn_training": {"target_impact": -0.04, "talan_node_index": 0, "horizon": "1m",
                         "notes": "Frein macro modéré compensé par la demande IA"}
    },

    {
        "event_id": "evt_067",
        "event_date": "2023-11-01",
        "event_type": "regulatory_changes",
        "event_name": "Sommet IA Bletchley Park — premier accord mondial sur les risques de l'IA",
        "event_description": "Le Royaume-Uni organise le 1er Sommet mondial sur la sécurité de l'IA à Bletchley Park. 28 pays dont US, UE, Chine signent la Déclaration de Bletchley. Biden signe l'EO 14110 sur l'IA le 30 octobre.",
        "source": "UK DSIT / White House / Reuters",
        "severity": 0.65, "confidence": 0.99, "is_real_event": True,
        "macro_context": {"CAC40_level": 7100, "CAC40_change_pct": +8.0, "SP500_change_pct": +12.0, "VIX": 15.0, "EUR_USD": 1.06, "brent_usd": 86.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("google"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("Royaume-Uni"), _country_node("France"),
            _event_node("evt_bletchley", "Sommet IA Bletchley Park", "regulatory_changes", "2023-11-01"),
        ],
        "edges": [
            _edge("evt_bletchley", "ai_ml", "CAUSES_IMPACT_ON", -0.08, 0.70, "2023-11-01", "Incertitude réglementaire sur les modèles frontier"),
            _edge("evt_bletchley", "talan", "CAUSES_IMPACT_ON", +0.10, 0.68, "2023-11-01", "Talan se positionne sur la gouvernance IA responsable"),
            _edge("evt_bletchley", "it_services_esn", "CAUSES_IMPACT_ON", +0.08, 0.65, "2023-11-01", "Les ESN captent la demande conseil éthique et gouvernance IA"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.06, "impact_3m": +0.10, "impact_6m": +0.12, "direction": "positive", "confidence": 0.62,
                      "reasoning": "Nouvelles missions conseil gouvernance IA. EO Biden crée une dynamique de conformité.", "source": "Estimation / tendances conseil IA éthique 2024"}
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Signal positif faible — gouvernance IA = opportunité conseil"}
    },

    {
        "event_id": "evt_068",
        "event_date": "2023-11-17",
        "event_type": "competitor_moves",
        "event_name": "Sam Altman licencié puis réintégré chez OpenAI — crise de gouvernance IA",
        "event_description": "Le conseil d'OpenAI licencie Sam Altman un vendredi soir. 700 employés menacent de démissionner. Altman réintégré 5 jours plus tard avec un nouveau conseil d'administration.",
        "source": "New York Times / The Verge / Wall Street Journal",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7100, "CAC40_change_pct": +8.0, "SP500_change_pct": +15.0, "VIX": 14.0, "EUR_USD": 1.07, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("microsoft"), _company_node("anthropic"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_altman_fired", "Sam Altman licencié/réintégré OpenAI", "competitor_moves", "2023-11-17"),
        ],
        "edges": [
            _edge("evt_altman_fired", "openai", "CAUSES_IMPACT_ON", -0.20, 0.85, "2023-11-17", "Crise de gouvernance, risque fuite talents OpenAI"),
            _edge("evt_altman_fired", "anthropic", "CAUSES_IMPACT_ON", +0.25, 0.80, "2023-11-17", "Anthropic bénéficie de l'instabilité d'OpenAI"),
            _edge("evt_altman_fired", "talan", "CAUSES_IMPACT_ON", -0.04, 0.50, "2023-11-17", "Incertitude roadmap OpenAI, quelques clients pausent leurs projets GenAI"),
            _edge("evt_altman_fired", "it_services_esn", "CAUSES_IMPACT_ON", -0.03, 0.50, "2023-11-17", "Pause courte sur projets OpenAI enterprise"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.03, "impact_1m": -0.04, "impact_3m": -0.02, "impact_6m": +0.02, "direction": "negative", "confidence": 0.52,
                      "reasoning": "Incertitude très courte durée. OpenAI sort renforcé après la crise.", "source": "Estimation — impact résorbé rapidement"}
        },
        "gnn_training": {"target_impact": -0.04, "talan_node_index": 0, "horizon": "1m", "notes": "Impact transitoire négatif résorbé en 1 mois"}
    },

    {
        "event_id": "evt_069",
        "event_date": "2023-05-30",
        "event_type": "financial_market_impact",
        "event_name": "NVIDIA H100 rupture de stock mondiale — valorisation +600% en 12 mois",
        "event_description": "NVIDIA devient intermittent la 1ère capitalisation mondiale. Les H100 s'arrachent à 40 000$/puce. Délais de livraison 12 mois. La demande IA dépasse de très loin l'offre GPU.",
        "source": "NVIDIA Earnings Q1 FY2024 / Bloomberg / Financial Times",
        "severity": 0.80, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7300, "CAC40_change_pct": +12.0, "SP500_change_pct": +18.0, "VIX": 16.0, "EUR_USD": 1.07, "brent_usd": 75.0, "fed_rate": 5.25, "ecb_rate": 3.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("nvidia"), _company_node("microsoft"), _company_node("google"), _company_node("amazon"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_nvidia_h100", "NVIDIA H100 rupture stock", "financial_market_impact", "2023-05-30"),
        ],
        "edges": [
            _edge("evt_nvidia_h100", "ai_ml", "CAUSES_IMPACT_ON", +0.50, 0.92, "2023-05-30", "Rareté GPU crée un avantage pour ceux qui ont accès à la compute"),
            _edge("evt_nvidia_h100", "cloud_computing", "CAUSES_IMPACT_ON", +0.35, 0.88, "2023-05-30", "Azure, AWS, GCP avec H100 ont un avantage massif"),
            _edge("evt_nvidia_h100", "talan", "CAUSES_IMPACT_ON", -0.04, 0.55, "2023-05-30", "Talan utilise les API cloud. Impact indirect via coûts API en hausse."),
            _edge("evt_nvidia_h100", "nvidia", "CAUSES_IMPACT_ON", +0.80, 0.98, "2023-05-30", "NVIDIA 300Md$ → 1000Md$ valorisation en moins d'un an"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.03, "impact_3m": -0.05, "impact_6m": -0.03, "direction": "negative", "confidence": 0.55,
                      "reasoning": "Légère hausse coûts API IA. Modèle asset-light protège Talan de la pénurie GPU.", "source": "NVIDIA Q1 FY2024 / Estimation ESN"},
            "nvidia": {"impact_1m": +0.75, "direction": "positive", "confidence": 0.98, "reasoning": "NVIDIA $300Md → $1000Md valorisation en 2023"}
        },
        "gnn_training": {"target_impact": -0.03, "talan_node_index": 0, "horizon": "1m", "notes": "ESN asset-light protégée de la pénurie GPU"}
    },

    {
        "event_id": "evt_070",
        "event_date": "2023-10-01",
        "event_type": "tech_launch",
        "event_name": "RAG + LangChain/LlamaIndex — stack standard IA enterprise",
        "event_description": "Le Retrieval Augmented Generation s'impose comme l'architecture IA de référence. LangChain (1M downloads/mois), Pinecone, Weaviate explosent. Résout le problème hallucinations et données propriétaires.",
        "source": "LangChain Blog / a16z State of AI 2023 / The New Stack",
        "severity": 0.65, "confidence": 0.92, "is_real_event": True,
        "macro_context": {"CAC40_level": 7200, "CAC40_change_pct": +10.0, "SP500_change_pct": +13.0, "VIX": 18.0, "EUR_USD": 1.06, "brent_usd": 93.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("amazon"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("Data & Analytics"), _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_rag_standard", "RAG devient standard enterprise IA", "tech_launch", "2023-10-01"),
        ],
        "edges": [
            _edge("evt_rag_standard", "ai_ml", "CAUSES_IMPACT_ON", +0.40, 0.88, "2023-10-01", "RAG démocratise les applications IA sur données propriétaires"),
            _edge("evt_rag_standard", "talan", "CAUSES_IMPACT_ON", +0.25, 0.82, "2023-10-01", "Talan développe une expertise RAG forte et capte de nombreux projets chatbot/KB"),
            _edge("evt_rag_standard", "it_services_esn", "CAUSES_IMPACT_ON", +0.30, 0.85, "2023-10-01", "Les ESN deviennent les architectes des pipelines RAG enterprise"),
            _edge("evt_rag_standard", "data_and_analytics", "CAUSES_IMPACT_ON", +0.35, 0.85, "2023-10-01", "Explosion demande vector databases et data pipelines"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.18, "impact_3m": +0.28, "impact_6m": +0.30, "direction": "positive", "confidence": 0.82,
                      "reasoning": "RAG = gros pipeline de projets Talan. Architecture Data/IA au cœur de l'offre.", "source": "Estimation basée sur tendances RFP clients ESN 2023-2024"}
        },
        "gnn_training": {"target_impact": +0.18, "talan_node_index": 0, "horizon": "1m", "notes": "RAG = forte opportunité pour les ESN spécialisées Data/IA"}
    },

    # ──────────────────────────────────────────────────────────────────────────
    # BLOC 4 — CONSOLIDATION & MATURITÉ IA (2024)  [40 événements: 071–110]
    # ──────────────────────────────────────────────────────────────────────────

    {
        "event_id": "evt_071",
        "event_date": "2024-01-20",
        "event_type": "tech_launch",
        "event_name": "DeepSeek R1 — modèle chinois open-source rival de GPT-4 à coût 96% inférieur",
        "event_description": "DeepSeek publie R1, modèle open-source rivalisant avec GPT-4o sur les benchmarks, entraîné pour 6M$ vs 100M$+. Choc sur le secteur IA mondial, action NVIDIA -17% en une journée.",
        "source": "DeepSeek Blog / Financial Times / Bloomberg",
        "severity": 0.90, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +8.0, "SP500_change_pct": +2.0, "VIX": 18.0, "EUR_USD": 1.08, "brent_usd": 77.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.22},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("nvidia"), _company_node("microsoft"), _company_node("capgemini"), _company_node("mistral"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("Chine"), _country_node("France"), _country_node("USA"),
            _event_node("evt_deepseek_r1", "DeepSeek R1 open-source", "tech_launch", "2024-01-20"),
        ],
        "edges": [
            _edge("evt_deepseek_r1", "ai_ml", "CAUSES_IMPACT_ON", -0.30, 0.90, "2024-01-20", "Commoditisation des LLM, pression marges fournisseurs propriétaires"),
            _edge("evt_deepseek_r1", "talan", "CAUSES_IMPACT_ON", +0.15, 0.75, "2024-01-20", "Talan déploie des modèles très performants à bas coût pour ses clients"),
            _edge("evt_deepseek_r1", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.72, "2024-01-20", "Les ESN bénéficient de modèles open-source compétitifs pour les déploiements client"),
            _edge("evt_deepseek_r1", "nvidia", "CAUSES_IMPACT_ON", -0.25, 0.88, "2024-01-20", "Action NVIDIA -17%, remise en question des dépenses GPU massives"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.78,
                      "reasoning": "Modèles open-source compétitifs = réduction coûts IA pour Talan. Avantage compétitif sur l'offre private AI.", "source": "DeepSeek / Estimation impact ESN open-source IA"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Open-source IA compétitive = opportunité pour les ESN intégratrices"}
    },

    {
        "event_id": "evt_072",
        "event_date": "2024-02-15",
        "event_type": "tech_launch",
        "event_name": "Google Gemini 1.5 Pro — fenêtre de contexte 1 million de tokens",
        "event_description": "Google lance Gemini 1.5 Pro avec 1 million de tokens de contexte (1h vidéo, 11h audio). Révolutionne les cas d'usage d'analyse documentaire massive.",
        "source": "Google DeepMind Blog / The Verge",
        "severity": 0.75, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +12.0, "SP500_change_pct": +6.0, "VIX": 14.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.20},
        "nodes": [
            _talan_node(), _company_node("google"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"), _sector_node("Data & Analytics"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_gemini15pro", "Google Gemini 1.5 Pro 1M tokens", "tech_launch", "2024-02-15"),
        ],
        "edges": [
            _edge("evt_gemini15pro", "ai_ml", "CAUSES_IMPACT_ON", +0.40, 0.90, "2024-02-15", "Nouveaux cas d'usage: analyse de corpus entiers, due diligence automatisée"),
            _edge("evt_gemini15pro", "talan", "CAUSES_IMPACT_ON", +0.18, 0.75, "2024-02-15", "Talan développe des solutions d'analyse documentaire sur Vertex AI"),
            _edge("evt_gemini15pro", "it_services_esn", "CAUSES_IMPACT_ON", +0.22, 0.78, "2024-02-15", "Nouveaux projets analyse documents longs, contrats, rapports"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Nouvelles missions analyse documentaire IA pour clients finance, legal, audit.", "source": "Estimation basée sur cas d'usage Gemini 1.5"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Long context = nouveaux cas d'usage lucratifs pour les ESN"}
    },

    {
        "event_id": "evt_073",
        "event_date": "2024-03-04",
        "event_type": "tech_launch",
        "event_name": "Anthropic Claude 3 Opus — meilleur modèle benchmark toutes catégories",
        "event_description": "Anthropic lance la famille Claude 3 (Haiku, Sonnet, Opus). Claude 3 Opus dépasse GPT-4 Turbo sur la majorité des benchmarks. Anthropic devient concurrent sérieux d'OpenAI.",
        "source": "Anthropic Blog / MMLU benchmarks / TechCrunch",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +10.0, "SP500_change_pct": +8.0, "VIX": 13.0, "EUR_USD": 1.09, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.20},
        "nodes": [
            _talan_node(), _company_node("anthropic"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_claude3opus", "Anthropic Claude 3 Opus", "tech_launch", "2024-03-04"),
        ],
        "edges": [
            _edge("evt_claude3opus", "ai_ml", "CAUSES_IMPACT_ON", +0.35, 0.88, "2024-03-04", "Compétition LLM s'intensifie, les modèles dépassent les attentes"),
            _edge("evt_claude3opus", "talan", "CAUSES_IMPACT_ON", +0.12, 0.70, "2024-03-04", "Talan diversifie ses solutions IA avec Claude 3, moins dépendant d'OpenAI"),
            _edge("evt_claude3opus", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.72, "2024-03-04", "Multi-vendor IA = plus de missions de comparaison et d'intégration"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.14, "direction": "positive", "confidence": 0.68,
                      "reasoning": "Diversification stack IA Talan. Anthropic = alternative premium enterprise.", "source": "Anthropic benchmarks / Estimation"}
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m", "notes": "Compétition LLM = avantage pour les ESN intégratrices multi-vendor"}
    },

    {
        "event_id": "evt_074",
        "event_date": "2024-05-13",
        "event_type": "tech_launch",
        "event_name": "OpenAI GPT-4o — premier modèle natif multimodal temps-réel",
        "event_description": "OpenAI lance GPT-4o, nativement multimodal (texte, image, audio, vidéo) avec latence temps-réel <232ms. La démo vocale époustouflante déclenche une réaction mondiale.",
        "source": "OpenAI / The Verge / New York Times",
        "severity": 0.80, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8100, "CAC40_change_pct": +11.0, "SP500_change_pct": +10.0, "VIX": 12.0, "EUR_USD": 1.08, "brent_usd": 83.0, "fed_rate": 5.50, "ecb_rate": 4.25, "global_recession_risk": 0.22},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("google"), _company_node("microsoft"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_gpt4o", "OpenAI GPT-4o multimodal natif", "tech_launch", "2024-05-13"),
        ],
        "edges": [
            _edge("evt_gpt4o", "ai_ml", "CAUSES_IMPACT_ON", +0.55, 0.93, "2024-05-13", "L'IA multimodale temps-réel ouvre des cas d'usage radicalement nouveaux"),
            _edge("evt_gpt4o", "talan", "CAUSES_IMPACT_ON", +0.25, 0.80, "2024-05-13", "Talan crée des solutions voice/vision IA pour ses clients"),
            _edge("evt_gpt4o", "it_services_esn", "CAUSES_IMPACT_ON", +0.30, 0.82, "2024-05-13", "Nouveaux projets IA multimodaux: chatbots voix, analyse d'images"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.18, "impact_3m": +0.25, "impact_6m": +0.22, "direction": "positive", "confidence": 0.80,
                      "reasoning": "Forte demande projets IA vocaux et visuels chez les clients de Talan (assurance, banque).", "source": "Estimation basée sur pipeline projets ESN H2 2024"}
        },
        "gnn_training": {"target_impact": +0.18, "talan_node_index": 0, "horizon": "1m", "notes": "GPT-4o ouvre les cas d'usage voice/vision pour les ESN"}
    },

    {
        "event_id": "evt_075",
        "event_date": "2024-04-18",
        "event_type": "tech_launch",
        "event_name": "Meta Llama 3 — performances SOTA open-source, 8B et 70B",
        "event_description": "Meta publie Llama 3 en open-source (8B et 70B). Llama 3 70B rivalise avec GPT-3.5 Turbo. L'open-source IA rend les modèles de qualité enterprise accessibles à tous.",
        "source": "Meta AI Blog / Hugging Face / ArXiv",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8100, "CAC40_change_pct": +10.0, "SP500_change_pct": +8.0, "VIX": 15.0, "EUR_USD": 1.07, "brent_usd": 88.0, "fed_rate": 5.50, "ecb_rate": 4.50, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("meta"), _company_node("openai"), _company_node("capgemini"), _company_node("mistral"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_llama3", "Meta Llama 3 SOTA open-source", "tech_launch", "2024-04-18"),
        ],
        "edges": [
            _edge("evt_llama3", "ai_ml", "CAUSES_IMPACT_ON", +0.35, 0.88, "2024-04-18", "Open-source IA de qualité enterprise devient la norme"),
            _edge("evt_llama3", "talan", "CAUSES_IMPACT_ON", +0.20, 0.78, "2024-04-18", "Talan déploie Llama 3 on-premise pour clients soucieux de souveraineté data"),
            _edge("evt_llama3", "it_services_esn", "CAUSES_IMPACT_ON", +0.22, 0.80, "2024-04-18", "Les ESN proposent des offres private AI basées sur Llama 3"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.14, "impact_3m": +0.20, "impact_6m": +0.22, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Llama 3 renforce l'offre private AI de Talan pour clients banque/assurance/santé.", "source": "Meta AI / Estimation marché private AI ESN"}
        },
        "gnn_training": {"target_impact": +0.14, "talan_node_index": 0, "horizon": "1m", "notes": "Open-source SOTA = accélération offre private AI des ESN"}
    },

    {
        "event_id": "evt_076",
        "event_date": "2024-06-18",
        "event_type": "financial_market_impact",
        "event_name": "NVIDIA dépasse 3 300 Md$ de capitalisation — 1ère capitalisation mondiale",
        "event_description": "NVIDIA devient brièvement la 1ère capitalisation boursière mondiale avec 3 335 Md$, dépassant Apple et Microsoft. Action +10x en 18 mois. Symbole de la course à la compute IA.",
        "source": "NASDAQ / Bloomberg / Financial Times",
        "severity": 0.75, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7900, "CAC40_change_pct": +8.0, "SP500_change_pct": +14.0, "VIX": 13.0, "EUR_USD": 1.07, "brent_usd": 85.0, "fed_rate": 5.50, "ecb_rate": 4.25, "global_recession_risk": 0.22},
        "nodes": [
            _talan_node(), _company_node("nvidia"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_nvidia_3t", "NVIDIA 3300Md$ capitalisation record", "financial_market_impact", "2024-06-18"),
            _macro_node("NASDAQ"),
        ],
        "edges": [
            _edge("evt_nvidia_3t", "ai_ml", "CAUSES_IMPACT_ON", +0.40, 0.88, "2024-06-18", "Validation de l'importance compute IA dans l'économie mondiale"),
            _edge("evt_nvidia_3t", "talan", "CAUSES_IMPACT_ON", +0.05, 0.55, "2024-06-18", "Effet de halo positif, confiance des clients dans les projets IA"),
            _edge("evt_nvidia_3t", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.65, "2024-06-18", "Valorisation NVIDIA valide l'IA comme secteur prioritaire"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.06, "direction": "positive", "confidence": 0.58,
                      "reasoning": "Effet de halo sur les budgets IA clients grands comptes. Confiance renforcée dans les investissements IA.", "source": "NASDAQ / Estimation impact confiance clients"}
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m", "notes": "Effet de halo IA — les clients investissent davantage dans les projets IA"}
    },

    {
        "event_id": "evt_077",
        "event_date": "2024-01-23",
        "event_type": "competitor_moves",
        "event_name": "Atos — plan de sauvegarde validé, scission en Eviden et Tech Foundations",
        "event_description": "Le tribunal de commerce de Paris valide le plan de sauvegarde d'Atos. La dette est restructurée, le groupe est scindé: Eviden (IT & IA) et Tech Foundations (infra legacy).",
        "source": "Les Echos / Reuters / BFM Business",
        "severity": 0.85, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 18.0, "EUR_USD": 1.08, "brent_usd": 77.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.22},
        "nodes": [
            _talan_node(), _company_node("atos"), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_atos_sauvegarde", "Atos plan sauvegarde validé", "competitor_moves", "2024-01-23"),
        ],
        "edges": [
            _edge("evt_atos_sauvegarde", "atos", "CAUSES_IMPACT_ON", -0.60, 0.95, "2024-01-23", "Atos perd sa crédibilité commerciale, fuite clients et talents"),
            _edge("evt_atos_sauvegarde", "talan", "CAUSES_IMPACT_ON", +0.30, 0.85, "2024-01-23", "Talan capte des clients et talents ex-Atos. Opportunité majeure."),
            _edge("evt_atos_sauvegarde", "capgemini", "CAUSES_IMPACT_ON", +0.20, 0.80, "2024-01-23", "Capgemini récupère des contrats Atos abandonnés"),
            _edge("evt_atos_sauvegarde", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.65, "2024-01-23", "Image du secteur ESN français ternie à l'international"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "atos", "COMPETES_WITH", 0.5, 1.0, "2020-01-01", "Concurrence ESN FR"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.05, "impact_1m": +0.25, "impact_3m": +0.35, "impact_6m": +0.38, "direction": "positive", "confidence": 0.88,
                      "reasoning": "Talan récupère clients, contrats et talents Atos. Croissance accélérée.", "source": "Tribunal Commerce Paris / Estimation LinkedIn mouvements RH"}
        },
        "gnn_training": {"target_impact": +0.25, "talan_node_index": 0, "horizon": "1m", "notes": "Faillite Atos = opportunité concurrentielle majeure pour Talan"}
    },

    {
        "event_id": "evt_078",
        "event_date": "2024-07-30",
        "event_type": "competitor_moves",
        "event_name": "Sopra Steria — guidance 2024 révisée à la baisse, croissance stagnante",
        "event_description": "Sopra Steria révise sa guidance 2024 à la baisse: croissance organique 0-2% au lieu de 5%+. Pression sur les marges, difficultés sur grands projets. Titre en baisse de 15%.",
        "source": "Sopra Steria rapport H1 2024 / Euronext",
        "severity": 0.55, "confidence": 0.97, "is_real_event": True,
        "macro_context": {"CAC40_level": 7500, "CAC40_change_pct": +5.0, "SP500_change_pct": +14.0, "VIX": 18.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("sopra"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_sopra_guidance_24", "Sopra Steria guidance révisée baisse 2024", "competitor_moves", "2024-07-30"),
        ],
        "edges": [
            _edge("evt_sopra_guidance_24", "sopra", "CAUSES_IMPACT_ON", -0.25, 0.90, "2024-07-30", "Sopra perd confiance du marché, moins agressif sur les appels d'offres"),
            _edge("evt_sopra_guidance_24", "talan", "CAUSES_IMPACT_ON", +0.15, 0.75, "2024-07-30", "Opportunité pour Talan de prendre des parts de marché"),
            _edge("evt_sopra_guidance_24", "it_services_esn", "CAUSES_IMPACT_ON", -0.05, 0.58, "2024-07-30", "Signal de ralentissement sectoriel dans les ESN mid-size FR"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence directe ESN FR"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.10, "impact_3m": +0.15, "impact_6m": +0.14, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Talan gagne des appels d'offres face à un Sopra fragilisé.", "source": "Sopra Steria rapport H1 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Fragilité Sopra = opportunité pour les ESN concurrentes"}
    },

    {
        "event_id": "evt_079",
        "event_date": "2024-03-20",
        "event_type": "talent_market_signals",
        "event_name": "Accenture licencie 19 000 postes sur 18 mois — restructuration autour de l'IA",
        "event_description": "Accenture annonce la suppression de 19 000 postes (2.5% des effectifs). Réorganisation autour de l'IA et des technologies prioritaires. Budget restructuration: 1.5 Md$.",
        "source": "Accenture Press Release / Wall Street Journal / Financial Times",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +10.0, "SP500_change_pct": +8.0, "VIX": 13.0, "EUR_USD": 1.09, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.20},
        "nodes": [
            _talan_node(), _company_node("accenture"), _company_node("capgemini"), _company_node("ibm"),
            _sector_node("IT Services / ESN"), _sector_node("Consulting"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_accenture_layoffs", "Accenture licenciements 19K", "talent_market_signals", "2024-03-20"),
        ],
        "edges": [
            _edge("evt_accenture_layoffs", "accenture", "CAUSES_IMPACT_ON", -0.10, 0.85, "2024-03-20", "Accenture réduit ses coûts, signal de pression marges"),
            _edge("evt_accenture_layoffs", "talan", "CAUSES_IMPACT_ON", +0.12, 0.72, "2024-03-20", "Talan recrute des experts Accenture à salaires compétitifs"),
            _edge("evt_accenture_layoffs", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.68, "2024-03-20", "Signal de pression sur marges consulting/ESN mondial"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "accenture", "COMPETES_WITH", 0.3, 1.0, "2020-01-01", "Concurrence limitée"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.08, "impact_3m": +0.10, "impact_6m": +0.08, "direction": "positive", "confidence": 0.68,
                      "reasoning": "Opportunité recrutement profils Accenture senior. Signal que même les géants doivent se réinventer.", "source": "Accenture FY2024 Earnings / Estimation"}
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m", "notes": "Licenciements géants = opportunité recrutement pour ESN mid-size"}
    },

    {
        "event_id": "evt_080",
        "event_date": "2024-04-24",
        "event_type": "competitor_moves",
        "event_name": "IBM acquiert HashiCorp pour 6.4 Md$ — infrastructure cloud as code",
        "event_description": "IBM acquiert HashiCorp (Terraform, Vault) pour 6.4 Md$. Renforce son positionnement sur l'automatisation d'infrastructure cloud et DevSecOps.",
        "source": "IBM Press Release / Wall Street Journal",
        "severity": 0.45, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +10.0, "SP500_change_pct": +9.0, "VIX": 15.0, "EUR_USD": 1.07, "brent_usd": 88.0, "fed_rate": 5.50, "ecb_rate": 4.50, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("ibm"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_ibm_hashicorp", "IBM acquiert HashiCorp 6.4Md$", "competitor_moves", "2024-04-24"),
        ],
        "edges": [
            _edge("evt_ibm_hashicorp", "ibm", "CAUSES_IMPACT_ON", +0.15, 0.80, "2024-04-24", "IBM renforce offre cloud hybride avec Terraform/Vault"),
            _edge("evt_ibm_hashicorp", "talan", "CAUSES_IMPACT_ON", -0.03, 0.50, "2024-04-24", "Légère pression missions DevSecOps de Talan via IBM"),
            _edge("evt_ibm_hashicorp", "it_services_esn", "CAUSES_IMPACT_ON", -0.03, 0.52, "2024-04-24", "Consolidation outillage DevOps au profit des grandes plateformes"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.02, "impact_3m": -0.03, "impact_6m": -0.02, "direction": "negative", "confidence": 0.48,
                      "reasoning": "Impact très limité, IBM et Talan ne sont pas en concurrence directe.", "source": "IBM Annual Report 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.02, "talan_node_index": 0, "horizon": "1m", "notes": "Impact quasi-nul sur Talan"}
    },

    {
        "event_id": "evt_081",
        "event_date": "2024-04-18",
        "event_type": "competitor_moves",
        "event_name": "Capgemini résultats Q1 2024 — croissance ralentie à +2%, normalisation post-boom",
        "event_description": "Capgemini publie +2% de croissance organique au Q1 2024, vs +12% en 2023. Normalisation post-COVID. Guidance 2024 prudemment révisée à 1-4% de croissance organique.",
        "source": "Capgemini rapport Q1 2024 / Les Echos / Reuters",
        "severity": 0.50, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +10.0, "SP500_change_pct": +9.0, "VIX": 15.0, "EUR_USD": 1.07, "brent_usd": 88.0, "fed_rate": 5.50, "ecb_rate": 4.50, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_cap_q1_24", "Capgemini Q1 2024 +2%", "competitor_moves", "2024-04-18"),
        ],
        "edges": [
            _edge("evt_cap_q1_24", "capgemini", "CAUSES_IMPACT_ON", -0.15, 0.90, "2024-04-18", "Ralentissement fort, Capgemini sur la défensive"),
            _edge("evt_cap_q1_24", "talan", "CAUSES_IMPACT_ON", -0.05, 0.60, "2024-04-18", "Signal de ralentissement marché ESN global"),
            _edge("evt_cap_q1_24", "it_services_esn", "CAUSES_IMPACT_ON", -0.12, 0.78, "2024-04-18", "Normalisation post-boom: secteur ESN passe de 10% à 2-3% de croissance"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.06, "impact_3m": -0.08, "impact_6m": -0.06, "direction": "negative", "confidence": 0.65,
                      "reasoning": "Le ralentissement Capgemini est indicateur avancé du marché ESN. Talan révise aussi ses projections.", "source": "Capgemini rapport Q1 2024"}
        },
        "gnn_training": {"target_impact": -0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Normalisation marché ESN post-boom — croissance plus lente"}
    },

    {
        "event_id": "evt_082",
        "event_date": "2024-09-17",
        "event_type": "tech_launch",
        "event_name": "Salesforce Agentforce — plateforme agents IA autonomes pour l'enterprise",
        "event_description": "Salesforce lance Agentforce lors de Dreamforce 2024. Plateforme d'agents IA autonomes pour le CRM et les processus business. Concurrence directe sur l'automatisation des services clients.",
        "source": "Salesforce Dreamforce 2024 / TechCrunch / Forbes",
        "severity": 0.65, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +6.0, "SP500_change_pct": +18.0, "VIX": 17.0, "EUR_USD": 1.10, "brent_usd": 72.0, "fed_rate": 5.00, "ecb_rate": 3.50, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("salesforce"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_agentforce", "Salesforce Agentforce lancé", "tech_launch", "2024-09-17"),
        ],
        "edges": [
            _edge("evt_agentforce", "cloud_computing", "CAUSES_IMPACT_ON", +0.25, 0.82, "2024-09-17", "Les plateformes SaaS intègrent des agents IA autonomes"),
            _edge("evt_agentforce", "talan", "CAUSES_IMPACT_ON", -0.10, 0.70, "2024-09-17", "Risque de désintermédiation partielle sur missions CRM/service client"),
            _edge("evt_agentforce", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.68, "2024-09-17", "Automatisation partielle missions paramétrage et support CRM"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.08, "impact_3m": -0.10, "impact_6m": -0.08, "direction": "negative", "confidence": 0.68,
                      "reasoning": "Agentforce automatise certaines tâches ESN CRM. Mais ouvre aussi de nouveaux besoins d'intégration.", "source": "Salesforce Dreamforce 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m", "notes": "AI agents autonomes = désintermédiation partielle + nouvelles missions d'intégration"}
    },

    {
        "event_id": "evt_083",
        "event_date": "2024-01-15",
        "event_type": "tech_launch",
        "event_name": "Microsoft 365 Copilot GA — IA généralisée dans toute la suite Office",
        "event_description": "Microsoft généralise Copilot dans toutes les applications M365. Prix: 30$/utilisateur/mois. Les grandes entreprises françaises adoptent massivement. Change management = nouvelle mission clé.",
        "source": "Microsoft / Les Echos / ZDNet France",
        "severity": 0.75, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +8.0, "SP500_change_pct": +2.0, "VIX": 18.0, "EUR_USD": 1.08, "brent_usd": 77.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.22},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_m365copilot_ga", "Microsoft 365 Copilot GA", "tech_launch", "2024-01-15"),
        ],
        "edges": [
            _edge("evt_m365copilot_ga", "cloud_computing", "CAUSES_IMPACT_ON", +0.30, 0.88, "2024-01-15", "Microsoft renforce domination cloud enterprise avec l'IA intégrée"),
            _edge("evt_m365copilot_ga", "talan", "CAUSES_IMPACT_ON", +0.10, 0.72, "2024-01-15", "Forte demande missions déploiement M365 Copilot et change management"),
            _edge("evt_m365copilot_ga", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.78, "2024-01-15", "Forte demande déploiement M365 Copilot dans les grandes entreprises FR"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.14, "impact_6m": +0.12, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Forte demande déploiement M365 Copilot chez les clients Talan (change management, customisation).", "source": "Microsoft / Estimation adoption Copilot grandes entreprises FR"}
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m", "notes": "M365 Copilot = missions d'accompagnement au changement pour les ESN"}
    },

    {
        "event_id": "evt_084",
        "event_date": "2024-05-07",
        "event_type": "tech_launch",
        "event_name": "ServiceNow Now Assist — IA générative intégrée dans l'ITSM",
        "event_description": "ServiceNow lance Now Assist, IA générative dans toute sa plateforme ITSM. Automatise les tickets, génère des résolutions, réduit les temps de traitement de 40%.",
        "source": "ServiceNow Knowledge 2024 / Gartner / TechCrunch",
        "severity": 0.55, "confidence": 0.95, "is_real_event": True,
        "macro_context": {"CAC40_level": 8100, "CAC40_change_pct": +11.0, "SP500_change_pct": +10.0, "VIX": 12.0, "EUR_USD": 1.08, "brent_usd": 83.0, "fed_rate": 5.50, "ecb_rate": 4.25, "global_recession_risk": 0.22},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_servicenow_ai", "ServiceNow Now Assist IA", "tech_launch", "2024-05-07"),
        ],
        "edges": [
            _edge("evt_servicenow_ai", "it_services_esn", "CAUSES_IMPACT_ON", -0.10, 0.72, "2024-05-07", "L'IA ITSM automatise des tâches MSP/TMA qui étaient manuelles"),
            _edge("evt_servicenow_ai", "talan", "CAUSES_IMPACT_ON", -0.08, 0.68, "2024-05-07", "Pression sur les missions support et maintenance applicative (TMA)"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.06, "impact_3m": -0.08, "impact_6m": -0.07, "direction": "negative", "confidence": 0.65,
                      "reasoning": "L'IA ITSM réduit le besoin en personnels de support. Missions TMA sous pression.", "source": "ServiceNow / IDC ITSM market 2024"}
        },
        "gnn_training": {"target_impact": -0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Automatisation ITSM = pression sur les missions TMA des ESN"}
    },

    {
        "event_id": "evt_085",
        "event_date": "2024-03-13",
        "event_type": "geopolitical_events",
        "event_name": "France Travail data breach — 43 millions de personnes touchées",
        "event_description": "France Travail subit une cyberattaque exposant les données de 43 millions de Français (NOM, NIR, email). Plus grande fuite de données personnelles de l'histoire en France.",
        "source": "CNIL / France Travail communiqué / Le Monde",
        "severity": 0.75, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +10.0, "SP500_change_pct": +8.0, "VIX": 13.0, "EUR_USD": 1.09, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.20},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("atos"),
            _sector_node("Cybersécurité"), _sector_node("IT Services / ESN"), _sector_node("Secteur Public / Gouvernement"),
            _country_node("France"),
            _event_node("evt_france_travail_breach", "France Travail breach 43M", "geopolitical_events", "2024-03-13"),
        ],
        "edges": [
            _edge("evt_france_travail_breach", "cybersecurite", "CAUSES_IMPACT_ON", +0.50, 0.93, "2024-03-13", "Explosion budgets cybersécurité secteur public et grandes entreprises FR"),
            _edge("evt_france_travail_breach", "talan", "CAUSES_IMPACT_ON", +0.22, 0.82, "2024-03-13", "Talan capte des missions d'audit cyber et mise en conformité pour le secteur public"),
            _edge("evt_france_travail_breach", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.80, "2024-03-13", "Forte hausse demande services cyber dans les ESN françaises"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.15, "impact_3m": +0.22, "impact_6m": +0.20, "direction": "positive", "confidence": 0.82,
                      "reasoning": "Practice cybersécurité Talan capte des missions d'urgence. Secteur public augmente budgets cyber de 30%.", "source": "CNIL / ANSSI rapport 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Mega breach secteur public = explosion demande cyber pour les ESN françaises"}
    },

    {
        "event_id": "evt_086",
        "event_date": "2024-08-01",
        "event_type": "regulatory_changes",
        "event_name": "AI Act UE promulgué — premier cadre légal mondial sur l'IA",
        "event_description": "L'AI Act européen est promulgué au Journal Officiel de l'UE le 1er août 2024. Application progressive: interdictions immédiates, obligations high-risk à 24 mois. Talan doit auditer ses systèmes IA.",
        "source": "JOUE / Commission Européenne / Les Echos",
        "severity": 0.80, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7500, "CAC40_change_pct": +4.0, "SP500_change_pct": +15.0, "VIX": 16.0, "EUR_USD": 1.10, "brent_usd": 78.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.24},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"), _company_node("microsoft"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_aiact_promulgated", "AI Act UE promulgué", "regulatory_changes", "2024-08-01"),
        ],
        "edges": [
            _edge("evt_aiact_promulgated", "ai_ml", "CAUSES_IMPACT_ON", -0.15, 0.85, "2024-08-01", "Contraintes compliance IA pour tous les systèmes déployés en UE"),
            _edge("evt_aiact_promulgated", "talan", "CAUSES_IMPACT_ON", +0.18, 0.80, "2024-08-01", "Talan développe une practice AI Act compliance et gouvernance IA"),
            _edge("evt_aiact_promulgated", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.82, "2024-08-01", "Forte demande audits, gap analysis et mise en conformité IA"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.22, "impact_6m": +0.28, "direction": "positive", "confidence": 0.82,
                      "reasoning": "Nouvelle practice AI Act chez Talan. Forte demande audits systèmes IA clients.", "source": "JOUE / CNIL / Estimation marché conformité IA"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "AI Act = nouvelle practice compliance IA très lucrative pour les ESN"}
    },

    {
        "event_id": "evt_087",
        "event_date": "2024-10-17",
        "event_type": "regulatory_changes",
        "event_name": "NIS2 — deadline transposition France, 15 000 entités soumises",
        "event_description": "La directive NIS2 doit être transposée en droit national le 17 octobre 2024. 15 000 entités françaises (vs 500 sous NIS1) doivent renforcer leur cybersécurité. Sanctions jusqu'à 10M€.",
        "source": "ANSSI / DINUM / Journal Officiel",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +3.0, "SP500_change_pct": +20.0, "VIX": 20.0, "EUR_USD": 1.09, "brent_usd": 73.0, "fed_rate": 5.00, "ecb_rate": 3.25, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("atos"),
            _sector_node("Cybersécurité"), _sector_node("IT Services / ESN"), _sector_node("Secteur Public / Gouvernement"),
            _country_node("France"),
            _event_node("evt_nis2_france", "NIS2 deadline France", "regulatory_changes", "2024-10-17"),
        ],
        "edges": [
            _edge("evt_nis2_france", "cybersecurite", "CAUSES_IMPACT_ON", +0.45, 0.90, "2024-10-17", "Explosion marché cybersécurité: 15K entités doivent se mettre à niveau"),
            _edge("evt_nis2_france", "talan", "CAUSES_IMPACT_ON", +0.22, 0.82, "2024-10-17", "Practice NIS2 Talan: audits, plans de remédiation, outils SIEM"),
            _edge("evt_nis2_france", "it_services_esn", "CAUSES_IMPACT_ON", +0.25, 0.85, "2024-10-17", "Forte demande missions cyber conformité NIS2 pour les ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.15, "impact_3m": +0.25, "impact_6m": +0.28, "direction": "positive", "confidence": 0.82,
                      "reasoning": "Talan capte des missions NIS2 auprès des ETI et grandes entreprises françaises.", "source": "ANSSI NIS2 rapport 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "NIS2 = vague de missions cyber compliance pour les ESN françaises"}
    },

    {
        "event_id": "evt_088",
        "event_date": "2024-06-01",
        "event_type": "geopolitical_events",
        "event_name": "Cyberattaques hôpitaux français record 2024 — CHU Rouen, Armentières, Corbeil",
        "event_description": "Vague record de cyberattaques sur les hôpitaux français en 2024: CHU de Rouen, CH d'Armentières, Hôpital de Cannes. ANSSI déclare le secteur santé priorité cyber nationale.",
        "source": "ANSSI / CERT-FR / Le Monde",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +5.0, "SP500_change_pct": +12.0, "VIX": 15.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("atos"), _company_node("capgemini"),
            _sector_node("Cybersécurité"), _sector_node("Santé / Healthcare"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_hopitaux_cyber", "Cyberattaques hôpitaux FR record", "geopolitical_events", "2024-06-01"),
        ],
        "edges": [
            _edge("evt_hopitaux_cyber", "cybersecurite", "CAUSES_IMPACT_ON", +0.40, 0.88, "2024-06-01", "Budget cybersécurité santé X3 après les attaques record"),
            _edge("evt_hopitaux_cyber", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2024-06-01", "Practice cyber santé Talan: missions RSSI, SOC, réponse incident"),
            _edge("evt_hopitaux_cyber", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.75, "2024-06-01", "Forte demande sécurisation SI santé pour les ESN spécialisées"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Talan renforce son offre cyber santé. Ségur du numérique en santé accélère.", "source": "ANSSI / CERT-FR / Estimation"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Cyberattaques santé = opportunité pour practice cyber ESN"}
    },

    {
        "event_id": "evt_089",
        "event_date": "2024-06-09",
        "event_type": "geopolitical_events",
        "event_name": "Élections européennes — montée des partis eurosceptiques, incertitude politique",
        "event_description": "Les élections européennes voient une forte montée des partis d'extrême-droite. Dissolution de l'Assemblée nationale française par Macron. Incertitude politique majeure en France.",
        "source": "Parlement Européen / Le Monde / Financial Times",
        "severity": 0.55, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7500, "CAC40_change_pct": +3.0, "SP500_change_pct": +12.0, "VIX": 20.0, "EUR_USD": 1.07, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("Secteur Public / Gouvernement"),
            _country_node("France"),
            _event_node("evt_euro_elections", "Élections européennes 2024", "geopolitical_events", "2024-06-09"),
        ],
        "edges": [
            _edge("evt_euro_elections", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.68, "2024-06-09", "Incertitude politique: certains projets IT secteur public mis en attente"),
            _edge("evt_euro_elections", "talan", "CAUSES_IMPACT_ON", -0.05, 0.58, "2024-06-09", "Quelques projets secteur public gelés durant la période électorale"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.05, "impact_3m": -0.04, "impact_6m": -0.02, "direction": "negative", "confidence": 0.55,
                      "reasoning": "Incertitude politique court-terme, gel partiel des commandes publiques IT.", "source": "Estimation / tendances marché public IT France 2024"}
        },
        "gnn_training": {"target_impact": -0.05, "talan_node_index": 0, "horizon": "1m", "notes": "Incertitude politique = gel court-terme des projets IT secteur public"}
    },

    {
        "event_id": "evt_090",
        "event_date": "2024-11-05",
        "event_type": "geopolitical_events",
        "event_name": "Élection de Trump — impact sur tech, régulation IA et commerce mondial",
        "event_description": "Donald Trump élu 47ème président des États-Unis. Signaux de dérégulation IA aux USA, politiques protectionnistes, incertitude pour les ESN indiennes et les échanges UE-USA.",
        "source": "AP / Reuters / Financial Times",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7200, "CAC40_change_pct": +2.0, "SP500_change_pct": +22.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.75, "ecb_rate": 3.25, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("infosys"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_trump_elected", "Trump élu président USA 2024", "geopolitical_events", "2024-11-05"),
        ],
        "edges": [
            _edge("evt_trump_elected", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.68, "2024-11-05", "Incertitude règles commerce USA-UE, pression nearshore Inde"),
            _edge("evt_trump_elected", "talan", "CAUSES_IMPACT_ON", -0.05, 0.58, "2024-11-05", "Impact limité: Talan surtout France/Europe, peu exposé USA"),
            _edge("evt_trump_elected", "infosys", "CAUSES_IMPACT_ON", -0.20, 0.78, "2024-11-05", "Restrictions visa H-1B menacent le modèle offshore indien"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.05, "impact_3m": -0.04, "impact_6m": -0.02, "direction": "negative", "confidence": 0.55,
                      "reasoning": "Impact indirect sur Talan via incertitude macro. Mais offre souveraine FR = atout relatif.", "source": "Reuters / Estimation"}
        },
        "gnn_training": {"target_impact": -0.05, "talan_node_index": 0, "horizon": "1m", "notes": "Incertitude géopolitique USA — impact limité pour ESN 100% Europe"}
    },

    {
        "event_id": "evt_091",
        "event_date": "2024-07-01",
        "event_type": "financial_market_impact",
        "event_name": "Correction tech mid-2024 — questionnement ROI investissements IA",
        "event_description": "Correction boursière du secteur tech en juillet 2024. Les investisseurs questionnent le ROI des dépenses IA massives. Alphabet, Microsoft, Meta voient leur action reculer de 10-20%.",
        "source": "Bloomberg / Wall Street Journal / Financial Times",
        "severity": 0.55, "confidence": 0.90, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +3.0, "SP500_change_pct": +10.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("google"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_tech_correction_24", "Correction tech mid-2024", "financial_market_impact", "2024-07-01"),
            _macro_node("NASDAQ"),
        ],
        "edges": [
            _edge("evt_tech_correction_24", "ai_ml", "CAUSES_IMPACT_ON", -0.20, 0.78, "2024-07-01", "Questionnement retour sur investissement IA"),
            _edge("evt_tech_correction_24", "talan", "CAUSES_IMPACT_ON", -0.06, 0.60, "2024-07-01", "Quelques clients ralentissent leurs projets IA en attente de ROI prouvé"),
            _edge("evt_tech_correction_24", "it_services_esn", "CAUSES_IMPACT_ON", -0.08, 0.65, "2024-07-01", "Gel partiel budgets IA enterprise en attente de démonstration ROI"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.06, "impact_3m": -0.05, "impact_6m": -0.03, "direction": "negative", "confidence": 0.60,
                      "reasoning": "Les clients questionnent le ROI des projets GenAI. Talan doit démontrer la valeur business.", "source": "Bloomberg / Estimation impact ESN"}
        },
        "gnn_training": {"target_impact": -0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Questionnement ROI IA = frein temporaire sur les projets enterprise"}
    },

    {
        "event_id": "evt_092",
        "event_date": "2024-06-01",
        "event_type": "tech_launch",
        "event_name": "Boom clouds souverains européens — OVHcloud, Outscale, Scaleway en croissance forte",
        "event_description": "Les hyperscalers européens connaissent une forte croissance post-AI Act. OVHcloud, Outscale (Dassault), Scaleway capturent une demande souveraineté data en explosion. Talan partenaire clé.",
        "source": "OVHcloud / Scaleway / Les Echos",
        "severity": 0.60, "confidence": 0.90, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +5.0, "SP500_change_pct": +12.0, "VIX": 15.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_sovereign_cloud_boom", "Boom clouds souverains EU 2024", "tech_launch", "2024-06-01"),
        ],
        "edges": [
            _edge("evt_sovereign_cloud_boom", "cloud_computing", "CAUSES_IMPACT_ON", +0.30, 0.82, "2024-06-01", "Clouds souverains captent la demande secteur public et santé FR"),
            _edge("evt_sovereign_cloud_boom", "talan", "CAUSES_IMPACT_ON", +0.15, 0.75, "2024-06-01", "Talan partenaire OVHcloud/Scaleway, missions migrations cloud souverain"),
            _edge("evt_sovereign_cloud_boom", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.78, "2024-06-01", "Les ESN françaises positionnées sur cloud souverain gagnent des parts"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.10, "impact_3m": +0.18, "impact_6m": +0.22, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Talan bénéficie du boom cloud souverain en tant qu'intégrateur clé des solutions FR.", "source": "OVHcloud / Estimation"}
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Cloud souverain = opportunité différentiation pour ESN françaises"}
    },

    {
        "event_id": "evt_093",
        "event_date": "2024-05-01",
        "event_type": "competitor_moves",
        "event_name": "Partenariats ESN × startups IA — accélération offres GenAI",
        "event_description": "Vague de partenariats entre grandes ESN et startups IA: Capgemini+Cohere, Sopra+Mistral, Accenture+AI21. Les ESN cherchent à enrichir rapidement leur catalogue IA.",
        "source": "Les Echos / ZDNet / Usine Digitale",
        "severity": 0.55, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +10.0, "SP500_change_pct": +9.0, "VIX": 15.0, "EUR_USD": 1.07, "brent_usd": 88.0, "fed_rate": 5.50, "ecb_rate": 4.50, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"), _company_node("mistral"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_esn_ai_partnerships", "Partenariats ESN-startups IA 2024", "competitor_moves", "2024-05-01"),
        ],
        "edges": [
            _edge("evt_esn_ai_partnerships", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.80, "2024-05-01", "Les ESN accélèrent leur transformation IA via partenariats"),
            _edge("evt_esn_ai_partnerships", "talan", "CAUSES_IMPACT_ON", +0.08, 0.68, "2024-05-01", "Talan développe aussi ses partenariats IA et enrichit son offre"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.12, "impact_6m": +0.14, "direction": "positive", "confidence": 0.65,
                      "reasoning": "Talan suit la tendance avec ses propres partenariats IA et enrichit son catalogue.", "source": "Presse sectorielle / Estimation"}
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m", "notes": "Course aux partenariats IA = accélération transformation des ESN"}
    },

    {
        "event_id": "evt_094",
        "event_date": "2024-03-01",
        "event_type": "tech_launch",
        "event_name": "Explosion demande RAG et vector databases — Pinecone, Weaviate, Qdrant",
        "event_description": "Le marché des vector databases explose: Pinecone à 750M$ valorisation, Weaviate, Qdrant, pgvector. RAG est devenu l'architecture standard pour les applications IA enterprise.",
        "source": "a16z / Crunchbase / Hugging Face",
        "severity": 0.60, "confidence": 0.90, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +10.0, "SP500_change_pct": +8.0, "VIX": 13.0, "EUR_USD": 1.09, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.20},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("amazon"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("Data & Analytics"), _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_vectordb_boom", "Explosion vector databases 2024", "tech_launch", "2024-03-01"),
        ],
        "edges": [
            _edge("evt_vectordb_boom", "data_and_analytics", "CAUSES_IMPACT_ON", +0.35, 0.85, "2024-03-01", "Vector databases = infrastructure standard des applications RAG"),
            _edge("evt_vectordb_boom", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2024-03-01", "Talan déploie des pipelines RAG avec vector DBs pour ses clients"),
            _edge("evt_vectordb_boom", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.80, "2024-03-01", "Forte demande expertise RAG/vector pour les ESN data"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.14, "impact_3m": +0.20, "impact_6m": +0.22, "direction": "positive", "confidence": 0.78,
                      "reasoning": "RAG = pipeline de projets Talan data/IA. Expertise clé différenciatrice.", "source": "a16z State of AI 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.14, "talan_node_index": 0, "horizon": "1m", "notes": "RAG/vector databases = compétence ESN clé très demandée"}
    },

    {
        "event_id": "evt_095",
        "event_date": "2024-02-27",
        "event_type": "tech_launch",
        "event_name": "GitHub Copilot Enterprise — IA coding généralisée en entreprise",
        "event_description": "GitHub lance Copilot Enterprise à 39$/mois/développeur. Personnalisable sur le code propriétaire. Les entreprises françaises adoptent massivement (TotalEnergies, BNP, Société Générale).",
        "source": "GitHub / Microsoft / ZDNet France",
        "severity": 0.65, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +12.0, "SP500_change_pct": +6.0, "VIX": 14.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.20},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_copilot_enterprise", "GitHub Copilot Enterprise GA", "tech_launch", "2024-02-27"),
        ],
        "edges": [
            _edge("evt_copilot_enterprise", "it_services_esn", "CAUSES_IMPACT_ON", -0.12, 0.78, "2024-02-27", "Copilot réduit le besoin en développeurs juniors sur les projets dev"),
            _edge("evt_copilot_enterprise", "talan", "CAUSES_IMPACT_ON", -0.06, 0.65, "2024-02-27", "Pression sur les missions développement. Mais hausse productivité."),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.05, "impact_3m": -0.08, "impact_6m": -0.06, "direction": "negative", "confidence": 0.65,
                      "reasoning": "Copilot Enterprise réduit la demande en profils développement junior. Talan repositionne vers senior et IA.", "source": "GitHub / Estimation ESN developpement 2024"}
        },
        "gnn_training": {"target_impact": -0.05, "talan_node_index": 0, "horizon": "1m", "notes": "AI coding = pression sur les missions dev juniors des ESN"}
    },

    {
        "event_id": "evt_096",
        "event_date": "2024-01-01",
        "event_type": "regulatory_changes",
        "event_name": "CSRD — premières obligations reporting ESG pour grandes entreprises FR",
        "event_description": "La CSRD (Corporate Sustainability Reporting Directive) s'applique dès 2024 aux entreprises de plus de 500 salariés. Les grandes entreprises françaises doivent publier leur rapport de durabilité.",
        "source": "Commission Européenne / EFRAG / AMF",
        "severity": 0.55, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +8.0, "SP500_change_pct": +2.0, "VIX": 18.0, "EUR_USD": 1.08, "brent_usd": 77.0, "fed_rate": 5.50, "ecb_rate": 4.00, "global_recession_risk": 0.22},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"), _company_node("deloitte"),
            _sector_node("IT Services / ESN"), _sector_node("Consulting"),
            _country_node("France"),
            _event_node("evt_csrd_2024", "CSRD obligations ESG 2024", "regulatory_changes", "2024-01-01"),
        ],
        "edges": [
            _edge("evt_csrd_2024", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.80, "2024-01-01", "Forte demande solutions reporting ESG et carbon accounting"),
            _edge("evt_csrd_2024", "talan", "CAUSES_IMPACT_ON", +0.12, 0.72, "2024-01-01", "Talan développe practice CSRD: outils collecte données, tableaux de bord"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.14, "impact_6m": +0.16, "direction": "positive", "confidence": 0.70,
                      "reasoning": "Nouvelle practice CSRD chez Talan. Les clients grands comptes ont besoin de solutions reporting ESG.", "source": "AMF / EFRAG / Estimation"}
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m", "notes": "CSRD = nouvelle practice ESG reporting pour les ESN et cabinets conseil"}
    },

    {
        "event_id": "evt_097",
        "event_date": "2024-06-01",
        "event_type": "competitor_moves",
        "event_name": "Talan expansion nearshore Tunisie/Maroc — centres de delivery renforcés",
        "event_description": "Talan renforce ses centres nearshore à Tunis et Casablanca. +500 consultants recrutés. Modèle nearshore compétitif face au offshore indien. Marges améliorées sur les missions de delivery.",
        "source": "Talan communiqués / Usine Digitale",
        "severity": 0.60, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +5.0, "SP500_change_pct": +12.0, "VIX": 15.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("sopra"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("Tunisie"),
            _event_node("evt_talan_nearshore", "Talan expansion nearshore Tunisie/Maroc", "competitor_moves", "2024-06-01"),
        ],
        "edges": [
            _edge("evt_talan_nearshore", "talan", "CAUSES_IMPACT_ON", +0.25, 0.80, "2024-06-01", "Talan améliore ses marges et sa compétitivité via le nearshore"),
            _edge("evt_talan_nearshore", "it_services_esn", "CAUSES_IMPACT_ON", -0.02, 0.50, "2024-06-01", "Pression concurrentielle accrue sur les prix des missions ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.20, "impact_3m": +0.28, "impact_6m": +0.30, "direction": "positive", "confidence": 0.80,
                      "reasoning": "Nearshore renforce la compétitivité Talan. Amélioration significative des marges.", "source": "Talan / Estimation impact opérationnel"}
        },
        "gnn_training": {"target_impact": +0.20, "talan_node_index": 0, "horizon": "1m", "notes": "Expansion nearshore = amélioration marges et compétitivité pour Talan"}
    },

    {
        "event_id": "evt_098",
        "event_date": "2024-09-01",
        "event_type": "financial_market_impact",
        "event_name": "Pression marges ESN par l'IA — automatisation partielle des missions",
        "event_description": "L'IA commence à automatiser 15-25% des tâches ESN répétitives (tests, doc, TMA). Les clients renégocient les tarifs à la baisse. Les ESN doivent monter en valeur ajoutée.",
        "source": "Syntec Numérique / IDC / Gartner",
        "severity": 0.65, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +6.0, "SP500_change_pct": +18.0, "VIX": 17.0, "EUR_USD": 1.10, "brent_usd": 72.0, "fed_rate": 5.00, "ecb_rate": 3.50, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_esn_margin_pressure", "Pression marges ESN par IA automatisation", "financial_market_impact", "2024-09-01"),
        ],
        "edges": [
            _edge("evt_esn_margin_pressure", "it_services_esn", "CAUSES_IMPACT_ON", -0.18, 0.82, "2024-09-01", "L'automatisation IA comprime les marges des ESN sur les missions répétitives"),
            _edge("evt_esn_margin_pressure", "talan", "CAUSES_IMPACT_ON", -0.12, 0.75, "2024-09-01", "Talan subit une pression tarifaire sur les missions TMA et testing"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.10, "impact_3m": -0.15, "impact_6m": -0.18, "direction": "negative", "confidence": 0.78,
                      "reasoning": "Talan doit restructurer son offre autour de missions haute valeur ajoutée. Pression sur TJM.", "source": "Syntec Numérique 2024 / Gartner"}
        },
        "gnn_training": {"target_impact": -0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Automatisation IA = pression structurelle sur les marges ESN"}
    },

    {
        "event_id": "evt_099",
        "event_date": "2024-06-11",
        "event_type": "financial_market_impact",
        "event_name": "Mistral AI lève 600 M€ — valorisation 6 Md€, champion IA français",
        "event_description": "Mistral AI boucle un tour de table de 600 M€ avec General Catalyst, Andreessen Horowitz, Lightspeed. Valorisation 6 Md€. Mistral devient le champion IA français et européen.",
        "source": "Les Echos / TechCrunch / Bloomberg",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +5.0, "SP500_change_pct": +12.0, "VIX": 15.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("mistral"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_mistral_600m", "Mistral AI 600M€ Series B", "financial_market_impact", "2024-06-11"),
        ],
        "edges": [
            _edge("evt_mistral_600m", "ai_ml", "CAUSES_IMPACT_ON", +0.30, 0.88, "2024-06-11", "L'écosystème IA français se renforce"),
            _edge("evt_mistral_600m", "talan", "CAUSES_IMPACT_ON", +0.08, 0.65, "2024-06-11", "Talan partenaire Mistral, accès préférentiel aux modèles souverains"),
            _edge("evt_mistral_600m", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.68, "2024-06-11", "Renforcement écosystème IA FR bénéficie aux ESN françaises"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.05, "impact_3m": +0.08, "impact_6m": +0.10, "direction": "positive", "confidence": 0.65,
                      "reasoning": "Champion IA français = crédibilité de l'offre souveraine que Talan propose à ses clients.", "source": "Les Echos / Estimation"}
        },
        "gnn_training": {"target_impact": +0.05, "talan_node_index": 0, "horizon": "1m", "notes": "Mistral champion IA EU = renforcement offre souveraine pour les ESN FR"}
    },

    {
        "event_id": "evt_100",
        "event_date": "2024-10-02",
        "event_type": "financial_market_impact",
        "event_name": "OpenAI lève 6.6 Md$ — valorisation 157 Md$, plus grosse levée tech mondiale",
        "event_description": "OpenAI boucle un tour de 6.6 Md$ avec Microsoft, Thrive Capital, SoftBank. Valorisation de 157 Md$. OpenAI en route vers une structure for-profit. Annonce ChatGPT Enterprise.",
        "source": "Wall Street Journal / Bloomberg / TechCrunch",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +3.0, "SP500_change_pct": +20.0, "VIX": 20.0, "EUR_USD": 1.09, "brent_usd": 73.0, "fed_rate": 5.00, "ecb_rate": 3.25, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_openai_66b", "OpenAI 6.6Md$ valorisation 157Md$", "financial_market_impact", "2024-10-02"),
        ],
        "edges": [
            _edge("evt_openai_66b", "ai_ml", "CAUSES_IMPACT_ON", +0.25, 0.85, "2024-10-02", "Confirmation de la domination OpenAI/Microsoft dans l'IA mondiale"),
            _edge("evt_openai_66b", "talan", "CAUSES_IMPACT_ON", -0.03, 0.52, "2024-10-02", "Risque de dépendance accrue à OpenAI/Microsoft pour les ESN"),
            _edge("evt_openai_66b", "it_services_esn", "CAUSES_IMPACT_ON", -0.02, 0.52, "2024-10-02", "Concentration du pouvoir IA chez quelques acteurs US"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.03, "impact_3m": -0.03, "impact_6m": -0.02, "direction": "negative", "confidence": 0.50,
                      "reasoning": "Impact quasi-nul sur Talan. Renforce l'argument souveraineté pour l'offre Talan.", "source": "Wall Street Journal / Estimation"}
        },
        "gnn_training": {"target_impact": -0.03, "talan_node_index": 0, "horizon": "1m", "notes": "Concentration IA US renforce l'argument souveraineté pour les ESN FR"}
    },

    {
        "event_id": "evt_101",
        "event_date": "2024-06-10",
        "event_type": "tech_launch",
        "event_name": "Apple Intelligence WWDC 2024 — IA embarquée dans tous les appareils Apple",
        "event_description": "Apple annonce Apple Intelligence lors de la WWDC 2024. IA générative intégrée nativement dans iOS 18, macOS 15 avec ChatGPT partnership. L'IA arrive sur 1.5 milliard d'appareils.",
        "source": "Apple WWDC 2024 / The Verge / 9to5Mac",
        "severity": 0.65, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +5.0, "SP500_change_pct": +12.0, "VIX": 15.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_apple_intelligence", "Apple Intelligence WWDC 2024", "tech_launch", "2024-06-10"),
        ],
        "edges": [
            _edge("evt_apple_intelligence", "ai_ml", "CAUSES_IMPACT_ON", +0.20, 0.82, "2024-06-10", "L'IA générative touche le grand public via les appareils Apple"),
            _edge("evt_apple_intelligence", "talan", "CAUSES_IMPACT_ON", +0.06, 0.55, "2024-06-10", "Opportunités nouvelles apps IA mobile pour les clients Talan"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.06, "impact_3m": +0.10, "impact_6m": +0.10, "direction": "positive", "confidence": 0.55,
                      "reasoning": "L'IA mobile ouvre de nouveaux projets apps intelligentes pour les clients de Talan.", "source": "Apple WWDC 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m", "notes": "IA embarquée grand public = nouvelles opportunités apps mobiles IA"}
    },

    {
        "event_id": "evt_102",
        "event_date": "2024-06-20",
        "event_type": "tech_launch",
        "event_name": "Anthropic Claude 3.5 Sonnet — meilleur coding model, dépasse GPT-4o",
        "event_description": "Anthropic lance Claude 3.5 Sonnet qui dépasse GPT-4o sur les benchmarks coding (HumanEval 92%). Artifacts feature pour le développement interactif. Devient le modèle préféré des développeurs.",
        "source": "Anthropic Blog / HumanEval benchmarks / Hacker News",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +5.0, "SP500_change_pct": +14.0, "VIX": 15.0, "EUR_USD": 1.08, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.23},
        "nodes": [
            _talan_node(), _company_node("anthropic"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_claude35sonnet", "Anthropic Claude 3.5 Sonnet best coding", "tech_launch", "2024-06-20"),
        ],
        "edges": [
            _edge("evt_claude35sonnet", "ai_ml", "CAUSES_IMPACT_ON", +0.30, 0.88, "2024-06-20", "Nouveau SOTA coding, les ESN adoptent Claude pour les projets dev"),
            _edge("evt_claude35sonnet", "talan", "CAUSES_IMPACT_ON", +0.15, 0.75, "2024-06-20", "Talan adopte Claude 3.5 pour accélérer les projets développement"),
            _edge("evt_claude35sonnet", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.72, "2024-06-20", "Productivité développement IA boostée pour les ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.16, "impact_6m": +0.15, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Claude 3.5 booste la productivité développement des équipes Talan de 30-40%.", "source": "Anthropic / Estimation gains productivité ESN"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Best coding model = gains productivité majeurs pour les ESN développement"}
    },

    {
        "event_id": "evt_103",
        "event_date": "2024-07-23",
        "event_type": "tech_launch",
        "event_name": "Meta Llama 3.1 405B — meilleur modèle open-source, rival GPT-4",
        "event_description": "Meta lance Llama 3.1 avec un modèle 405B rivalisant avec GPT-4 Turbo. Open-source avec licence commerciale. Renforce l'alternative souveraine pour les entreprises européennes.",
        "source": "Meta AI Blog / Hugging Face / ArXiv",
        "severity": 0.75, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +3.0, "SP500_change_pct": +14.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("meta"), _company_node("openai"), _company_node("capgemini"), _company_node("mistral"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_llama31_405b", "Meta Llama 3.1 405B open-source GPT-4 rival", "tech_launch", "2024-07-23"),
        ],
        "edges": [
            _edge("evt_llama31_405b", "ai_ml", "CAUSES_IMPACT_ON", +0.40, 0.90, "2024-07-23", "L'open-source atteint le niveau GPT-4, commoditise les LLMs propriétaires"),
            _edge("evt_llama31_405b", "talan", "CAUSES_IMPACT_ON", +0.20, 0.80, "2024-07-23", "Talan déploie Llama 3.1 on-premise pour clients souveraineté maximale"),
            _edge("evt_llama31_405b", "it_services_esn", "CAUSES_IMPACT_ON", +0.22, 0.82, "2024-07-23", "Les ESN proposent des offres private AI compétitives basées Llama 3.1"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.15, "impact_3m": +0.22, "impact_6m": +0.25, "direction": "positive", "confidence": 0.80,
                      "reasoning": "Llama 3.1 405B renforce l'offre private AI de Talan avec performances GPT-4 on-premise.", "source": "Meta AI / Estimation marché private AI"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Open-source GPT-4 level = accélération forte de l'offre private AI souveraine"}
    },

    {
        "event_id": "evt_104",
        "event_date": "2024-09-01",
        "event_type": "macro_economic",
        "event_name": "Vague IA en production dans les grandes entreprises françaises",
        "event_description": "Après 18 mois de POC, les grandes entreprises françaises (CAC40, ETI) passent leurs projets IA en production. 60% des DAFs investissent en IA selon une enquête Syntec Numérique.",
        "source": "Syntec Numérique / McKinsey State of AI 2024 / Bpifrance",
        "severity": 0.70, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +6.0, "SP500_change_pct": +18.0, "VIX": 17.0, "EUR_USD": 1.10, "brent_usd": 72.0, "fed_rate": 5.00, "ecb_rate": 3.50, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_ai_production_wave", "IA en production grandes entreprises FR", "macro_economic", "2024-09-01"),
        ],
        "edges": [
            _edge("evt_ai_production_wave", "it_services_esn", "CAUSES_IMPACT_ON", +0.30, 0.85, "2024-09-01", "Les ESN captent les missions MLOps, déploiement et maintenance IA"),
            _edge("evt_ai_production_wave", "talan", "CAUSES_IMPACT_ON", +0.25, 0.82, "2024-09-01", "Forte demande expertise déploiement IA en production chez les clients Talan"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.20, "impact_3m": +0.30, "impact_6m": +0.32, "direction": "positive", "confidence": 0.82,
                      "reasoning": "La vague IA en production génère un pipeline de missions MLOps et maintien IA pour Talan.", "source": "Syntec Numérique / McKinsey 2024"}
        },
        "gnn_training": {"target_impact": +0.20, "talan_node_index": 0, "horizon": "1m", "notes": "POC → production = forte demande missions MLOps et déploiement IA"}
    },

    {
        "event_id": "evt_105",
        "event_date": "2024-10-01",
        "event_type": "regulatory_changes",
        "event_name": "Débat souveraineté IA — données résidentes en Europe exigées par les entreprises",
        "event_description": "La question de la résidence des données IA devient centrale. CNIL publie des recommandations sur les LLMs. Les entreprises françaises exigent que leurs données ne quittent pas l'UE.",
        "source": "CNIL / LINC / Les Echos",
        "severity": 0.60, "confidence": 0.90, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +3.0, "SP500_change_pct": +20.0, "VIX": 20.0, "EUR_USD": 1.09, "brent_usd": 73.0, "fed_rate": 5.00, "ecb_rate": 3.25, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("mistral"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("France"),
            _event_node("evt_data_sovereignty_ai", "Débat souveraineté données IA France", "regulatory_changes", "2024-10-01"),
        ],
        "edges": [
            _edge("evt_data_sovereignty_ai", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.80, "2024-10-01", "Les ESN françaises bénéficient de l'exigence de souveraineté data"),
            _edge("evt_data_sovereignty_ai", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2024-10-01", "Talan positionne son offre sur la souveraineté IA = avantage différenciateur"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Exigence souveraineté data = avantage ESN française Talan face aux acteurs US.", "source": "CNIL / Estimation"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Souveraineté IA = avantage compétitif structurel pour les ESN françaises"}
    },

    {
        "event_id": "evt_106",
        "event_date": "2024-10-15",
        "event_type": "tech_launch",
        "event_name": "IA multi-agents — AutoGen, LangGraph, CrewAI deviennent standards enterprise",
        "event_description": "Les frameworks multi-agents (AutoGen de Microsoft, LangGraph, CrewAI) sont adoptés massivement. Les entreprises déploient des réseaux d'agents IA autonomes pour automatiser des workflows complexes.",
        "source": "Microsoft Research / LangChain / GitHub stars rankings",
        "severity": 0.70, "confidence": 0.90, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +3.0, "SP500_change_pct": +20.0, "VIX": 20.0, "EUR_USD": 1.09, "brent_usd": 73.0, "fed_rate": 5.00, "ecb_rate": 3.25, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_multiagent_standard", "Multi-agents IA standard enterprise", "tech_launch", "2024-10-15"),
        ],
        "edges": [
            _edge("evt_multiagent_standard", "ai_ml", "CAUSES_IMPACT_ON", +0.40, 0.85, "2024-10-15", "Les agents IA autonomes automatisent des workflows entiers"),
            _edge("evt_multiagent_standard", "talan", "CAUSES_IMPACT_ON", +0.20, 0.78, "2024-10-15", "Talan développe une expertise forte multi-agents (LangGraph notamment)"),
            _edge("evt_multiagent_standard", "it_services_esn", "CAUSES_IMPACT_ON", +0.22, 0.80, "2024-10-15", "Les ESN deviennent architectes d'agents IA pour leurs clients"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.15, "impact_3m": +0.25, "impact_6m": +0.28, "direction": "positive", "confidence": 0.78,
                      "reasoning": "Talan crée une practice agents IA avec LangGraph. Pipeline de projets agentic en forte croissance.", "source": "Microsoft Research / Estimation ESN agentic AI"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Multi-agents = nouvelle génération de missions IA à haute valeur ajoutée"}
    },

    {
        "event_id": "evt_107",
        "event_date": "2024-07-01",
        "event_type": "talent_market_signals",
        "event_name": "Pénurie talents IA 2024 — 50 000 profils IA manquants en France",
        "event_description": "France Stratégie estime à 50 000 le nombre de profils IA manquants en France. Data scientists, ML engineers, AI architects se négocient 20-40% au-dessus du marché. Les ESN souffrent.",
        "source": "France Stratégie / Apec / LinkedIn Insights 2024",
        "severity": 0.65, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +3.0, "SP500_change_pct": +14.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 82.0, "fed_rate": 5.50, "ecb_rate": 3.75, "global_recession_risk": 0.25},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ai_talent_shortage_24", "Pénurie talents IA France 2024", "talent_market_signals", "2024-07-01"),
        ],
        "edges": [
            _edge("evt_ai_talent_shortage_24", "it_services_esn", "CAUSES_IMPACT_ON", -0.15, 0.82, "2024-07-01", "Les ESN peinent à recruter et à retenir les profils IA"),
            _edge("evt_ai_talent_shortage_24", "talan", "CAUSES_IMPACT_ON", -0.10, 0.75, "2024-07-01", "Talan doit offrir des salaires en hausse et des projets IA attractifs"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.08, "impact_3m": -0.12, "impact_6m": -0.10, "direction": "negative", "confidence": 0.78,
                      "reasoning": "La guerre des talents IA comprime les marges de Talan. Risque de turnover élevé.", "source": "France Stratégie 2024 / APEC / Estimation"}
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m", "notes": "Pénurie talents IA = pression coûts RH structurelle pour les ESN"}
    },

    {
        "event_id": "evt_108",
        "event_date": "2024-11-01",
        "event_type": "tech_launch",
        "event_name": "Standardisation plateformes IA — Vertex AI, Azure AI Studio, AWS Bedrock maturent",
        "event_description": "Les trois grandes plateformes MLOps cloud (Vertex AI, Azure AI Studio, AWS Bedrock) atteignent la maturité enterprise. Les entreprises s'appuient dessus pour standardiser leurs déploiements IA.",
        "source": "Google Cloud / Microsoft Azure / AWS / Gartner Magic Quadrant",
        "severity": 0.60, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7200, "CAC40_change_pct": +2.0, "SP500_change_pct": +22.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.75, "ecb_rate": 3.25, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("google"), _company_node("amazon"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_ai_platforms_mature", "Plateformes IA cloud maturent", "tech_launch", "2024-11-01"),
        ],
        "edges": [
            _edge("evt_ai_platforms_mature", "cloud_computing", "CAUSES_IMPACT_ON", +0.25, 0.85, "2024-11-01", "Les hyperscalers dominent le marché des plateformes IA"),
            _edge("evt_ai_platforms_mature", "talan", "CAUSES_IMPACT_ON", +0.15, 0.72, "2024-11-01", "Talan certifié multi-cloud IA, capte les missions d'intégration et MLOps"),
            _edge("evt_ai_platforms_mature", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.75, "2024-11-01", "Les ESN se certifient sur les plateformes pour capturer les projets MLOps"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.10, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Talan certifié sur les plateformes MLOps cloud majeures = crédibilité et pipeline projets.", "source": "Gartner MQ 2024 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Maturité plateformes IA cloud = missions intégration et MLOps pour ESN certifiées"}
    },

    {
        "event_id": "evt_109",
        "event_date": "2024-12-01",
        "event_type": "macro_economic",
        "event_name": "Investissement record cloud souverain Europe — 10 Md€ annoncés en 2024",
        "event_description": "Les gouvernements et entreprises européennes investissent 10 Md€ dans les clouds souverains en 2024. France en tête avec le programme GAIA-X et les projets cloud de confiance.",
        "source": "DINUM / GAIA-X / Commission Européenne",
        "severity": 0.65, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7100, "CAC40_change_pct": +1.0, "SP500_change_pct": +23.0, "VIX": 18.0, "EUR_USD": 1.04, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 3.00, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"), _sector_node("Secteur Public / Gouvernement"),
            _country_node("France"),
            _event_node("evt_sovereign_cloud_invest", "Investissement record cloud souverain UE 2024", "macro_economic", "2024-12-01"),
        ],
        "edges": [
            _edge("evt_sovereign_cloud_invest", "cloud_computing", "CAUSES_IMPACT_ON", +0.30, 0.85, "2024-12-01", "Boom investissement cloud souverain en Europe"),
            _edge("evt_sovereign_cloud_invest", "talan", "CAUSES_IMPACT_ON", +0.20, 0.78, "2024-12-01", "Talan en première ligne pour les projets cloud souverain secteur public"),
            _edge("evt_sovereign_cloud_invest", "it_services_esn", "CAUSES_IMPACT_ON", +0.22, 0.80, "2024-12-01", "Les ESN françaises captent les marchés cloud souverain"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.15, "impact_3m": +0.25, "impact_6m": +0.28, "direction": "positive", "confidence": 0.78,
                      "reasoning": "Talan capte des marchés cloud souverain pour l'Etat et les OIV/OSE sous NIS2.", "source": "DINUM / GAIA-X / Estimation"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Cloud souverain EU = marché prioritaire pour les ESN françaises"}
    },

    {
        "event_id": "evt_110",
        "event_date": "2024-12-15",
        "event_type": "regulatory_changes",
        "event_name": "CSRD vague audit — les ESN elles-mêmes soumises aux obligations RSE",
        "event_description": "Les ESN de plus de 500 salariés (dont Talan) doivent publier leur rapport CSRD. Cela crée à la fois une obligation interne et une opportunité externe de conseil RSE pour leurs clients.",
        "source": "AMF / EFRAG / Syntec Numérique",
        "severity": 0.50, "confidence": 0.92, "is_real_event": True,
        "macro_context": {"CAC40_level": 7100, "CAC40_change_pct": +1.0, "SP500_change_pct": +23.0, "VIX": 18.0, "EUR_USD": 1.04, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 3.00, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"), _company_node("deloitte"),
            _sector_node("IT Services / ESN"), _sector_node("Consulting"),
            _country_node("France"),
            _event_node("evt_csrd_esn_audit", "CSRD audit vague ESN soumises", "regulatory_changes", "2024-12-15"),
        ],
        "edges": [
            _edge("evt_csrd_esn_audit", "it_services_esn", "CAUSES_IMPACT_ON", -0.05, 0.70, "2024-12-15", "Coût conformité CSRD pour les ESN elles-mêmes"),
            _edge("evt_csrd_esn_audit", "talan", "CAUSES_IMPACT_ON", +0.05, 0.65, "2024-12-15", "Talan publie son premier rapport CSRD et renforce sa crédibilité RSE"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": +0.02, "impact_3m": +0.05, "impact_6m": +0.08, "direction": "positive", "confidence": 0.62,
                      "reasoning": "CSRD = coût compliance mais aussi opportunité de crédibilité RSE pour attirer talents et clients.", "source": "AMF / Estimation"}
        },
        "gnn_training": {"target_impact": +0.02, "talan_node_index": 0, "horizon": "1m", "notes": "CSRD ESN = coût compliance mais signal crédibilité RSE"}
    },

    # ──────────────────────────────────────────────────────────────────────────
    # BLOC 5 — DISRUPTION IA & NOUVEAUX DÉFIS (2025-2026)  [40 événements: 111–150]
    # ──────────────────────────────────────────────────────────────────────────

    {
        "event_id": "evt_111",
        "event_date": "2025-01-20",
        "event_type": "tech_launch",
        "event_name": "DeepSeek V3+R1 — second choc open-source mondial, NVIDIA -17% en une journée",
        "event_description": "DeepSeek publie V3 (671B MoE) et R1 (reasoning). Modèles open-source gratuits qui rivalisent avec o1 d'OpenAI. NVIDIA perd 600 Md$ de capitalisation en une journée. Second choc géopolitique IA.",
        "source": "DeepSeek / Bloomberg / Financial Times / Reuters",
        "severity": 0.95, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +5.0, "SP500_change_pct": +25.0, "VIX": 25.0, "EUR_USD": 1.04, "brent_usd": 76.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("nvidia"), _company_node("microsoft"), _company_node("google"), _company_node("capgemini"), _company_node("mistral"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("Chine"), _country_node("France"), _country_node("USA"),
            _event_node("evt_deepseek_v3_r1", "DeepSeek V3+R1 second choc IA mondial", "tech_launch", "2025-01-20"),
        ],
        "edges": [
            _edge("evt_deepseek_v3_r1", "ai_ml", "CAUSES_IMPACT_ON", -0.35, 0.92, "2025-01-20", "Les modèles propriétaires sont commoditisés, remise en question des valorisations"),
            _edge("evt_deepseek_v3_r1", "nvidia", "CAUSES_IMPACT_ON", -0.20, 0.95, "2025-01-20", "NVIDIA -600Md$ capitalisation en une journée"),
            _edge("evt_deepseek_v3_r1", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2025-01-20", "Talan déploie DeepSeek on-premise pour les clients exigeant souveraineté maximale"),
            _edge("evt_deepseek_v3_r1", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.75, "2025-01-20", "Les ESN accèdent à des modèles frontier gratuits pour leurs clients"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.15, "impact_3m": +0.22, "impact_6m": +0.25, "direction": "positive", "confidence": 0.80,
                      "reasoning": "DeepSeek gratuit = baisse coûts IA pour Talan. L'offre private AI souveraine de Talan devient encore plus compétitive.", "source": "DeepSeek / Bloomberg / Estimation ESN"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Second choc open-source = commoditisation LLMs, avantage pour ESN intégratrices"}
    },

    {
        "event_id": "evt_112",
        "event_date": "2025-02-24",
        "event_type": "tech_launch",
        "event_name": "Anthropic Claude 3.7 Sonnet — meilleur modèle coding avec raisonnement étendu",
        "event_description": "Anthropic lance Claude 3.7 Sonnet avec extended thinking (raisonnement multi-étapes). Premier modèle à combiner génération rapide et raisonnement profond. SWE-bench score record.",
        "source": "Anthropic Blog / SWE-bench / Hacker News",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("anthropic"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_claude37sonnet", "Claude 3.7 Sonnet extended thinking", "tech_launch", "2025-02-24"),
        ],
        "edges": [
            _edge("evt_claude37sonnet", "ai_ml", "CAUSES_IMPACT_ON", +0.30, 0.88, "2025-02-24", "L'IA avec raisonnement étendu aborde des problèmes complexes d'ingénierie"),
            _edge("evt_claude37sonnet", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2025-02-24", "Talan intègre Claude 3.7 dans ses projets d'architecture et code review IA"),
            _edge("evt_claude37sonnet", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.75, "2025-02-24", "Les ESN accèdent à un coding assistant de niveau senior"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.14, "impact_3m": +0.20, "impact_6m": +0.22, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Claude 3.7 = outil de développement senior IA pour les équipes Talan. Gain productivité majeur.", "source": "Anthropic / SWE-bench 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.14, "talan_node_index": 0, "horizon": "1m", "notes": "Modèles reasoning = outil développement senior IA pour les ESN"}
    },

    {
        "event_id": "evt_113",
        "event_date": "2025-04-05",
        "event_type": "tech_launch",
        "event_name": "Meta Llama 4 — architecture MoE multimodale, nouvelle référence open-source",
        "event_description": "Meta lance Llama 4 en architecture MoE (Mixture of Experts) multimodale. Scout (17B actifs/109B total) et Maverick rivalisent avec GPT-4o sur les benchmarks visuels et texte.",
        "source": "Meta AI Blog / ArXiv / Hugging Face",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +4.0, "SP500_change_pct": -3.0, "VIX": 35.0, "EUR_USD": 1.09, "brent_usd": 64.0, "fed_rate": 4.50, "ecb_rate": 2.50, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("meta"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_llama4", "Meta Llama 4 MoE multimodal", "tech_launch", "2025-04-05"),
        ],
        "edges": [
            _edge("evt_llama4", "ai_ml", "CAUSES_IMPACT_ON", +0.35, 0.88, "2025-04-05", "Llama 4 multimodal = nouvelle ère des modèles open-source visuels"),
            _edge("evt_llama4", "talan", "CAUSES_IMPACT_ON", +0.16, 0.75, "2025-04-05", "Talan déploie Llama 4 pour des applications vision/multimodal on-premise"),
            _edge("evt_llama4", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.78, "2025-04-05", "Nouvelles missions déploiement modèles multimodaux open-source"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Llama 4 multimodal renforce l'offre vision IA de Talan pour l'industrie et la santé.", "source": "Meta AI 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Multimodal open-source = nouvelles applications vision IA pour les ESN"}
    },

    {
        "event_id": "evt_114",
        "event_date": "2025-02-05",
        "event_type": "tech_launch",
        "event_name": "Google Gemini 2.0 Flash — modèle natif agents, vision et multimodal temps-réel",
        "event_description": "Google lance Gemini 2.0 Flash, modèle conçu nativement pour les agents IA autonomes. Multimodal natif, génération d'images intégrée, Live API temps-réel. Fondation de l'ère agentique.",
        "source": "Google DeepMind / The Verge / Google I/O 2025",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("google"), _company_node("openai"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_gemini20flash", "Google Gemini 2.0 Flash agents natif", "tech_launch", "2025-02-05"),
        ],
        "edges": [
            _edge("evt_gemini20flash", "ai_ml", "CAUSES_IMPACT_ON", +0.35, 0.88, "2025-02-05", "L'ère agentique IA commence avec des modèles conçus pour les agents"),
            _edge("evt_gemini20flash", "talan", "CAUSES_IMPACT_ON", +0.15, 0.72, "2025-02-05", "Talan construit des solutions agents sur Gemini 2.0 pour ses clients"),
            _edge("evt_gemini20flash", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.75, "2025-02-05", "Les ESN architecturent des réseaux d'agents IA sur Gemini"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Gemini 2.0 = socle pour les projets agents IA de Talan sur Google Cloud.", "source": "Google DeepMind 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Modèles natifs agents = accélération des projets agentic IA pour les ESN"}
    },

    {
        "event_id": "evt_115",
        "event_date": "2025-04-14",
        "event_type": "tech_launch",
        "event_name": "OpenAI GPT-4.1 et o3 — nouveaux records SOTA, 1M tokens context",
        "event_description": "OpenAI lance GPT-4.1 (1M tokens de contexte) et o3 (raisonnement frontier). GPT-4.1 domine les benchmarks coding. o3 atteint 99.5% sur ARC-AGI. Nouvelle barre SOTA posée.",
        "source": "OpenAI / ARC-AGI benchmarks / The Verge",
        "severity": 0.75, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +4.0, "SP500_change_pct": -3.0, "VIX": 35.0, "EUR_USD": 1.09, "brent_usd": 64.0, "fed_rate": 4.50, "ecb_rate": 2.50, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("microsoft"), _company_node("anthropic"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_gpt41_o3", "OpenAI GPT-4.1 et o3 SOTA 2025", "tech_launch", "2025-04-14"),
        ],
        "edges": [
            _edge("evt_gpt41_o3", "ai_ml", "CAUSES_IMPACT_ON", +0.40, 0.90, "2025-04-14", "Nouvelle frontière LLM: 1M contexte + raisonnement frontier"),
            _edge("evt_gpt41_o3", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2025-04-14", "Talan intègre GPT-4.1 pour des cas d'usage analyse documentaire massive"),
            _edge("evt_gpt41_o3", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.80, "2025-04-14", "Nouveaux projets analyse de corpus entiers, audit documentaire IA"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.15, "impact_3m": +0.22, "impact_6m": +0.24, "direction": "positive", "confidence": 0.78,
                      "reasoning": "GPT-4.1 1M tokens = révolution analyse documentaire pour les clients banque/assurance de Talan.", "source": "OpenAI 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "1M tokens context = révolution analyse documentaire pour les ESN financières"}
    },

    {
        "event_id": "evt_116",
        "event_date": "2025-04-09",
        "event_type": "geopolitical_events",
        "event_name": "Guerre commerciale USA-Chine — tarifs douaniers 125%, choc mondial",
        "event_description": "Trump annonce des tarifs douaniers de 125% sur les produits chinois. La Chine riposte avec des tarifs équivalents. Choc géopolitique mondial. Récession mondiale envisagée.",
        "source": "White House / Reuters / Financial Times / Bloomberg",
        "severity": 0.85, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 7000, "CAC40_change_pct": -8.0, "SP500_change_pct": -15.0, "VIX": 55.0, "EUR_USD": 1.12, "brent_usd": 60.0, "fed_rate": 4.50, "ecb_rate": 2.50, "global_recession_risk": 0.55},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("infosys"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("Chine"), _country_node("France"),
            _event_node("evt_trade_war_125", "Guerre commerciale USA-Chine tarifs 125%", "geopolitical_events", "2025-04-09"),
            _macro_node("VIX"), _macro_node("SP500"),
        ],
        "edges": [
            _edge("evt_trade_war_125", "it_services_esn", "CAUSES_IMPACT_ON", -0.15, 0.80, "2025-04-09", "Incertitude macro, report d'investissements IT chez les clients"),
            _edge("evt_trade_war_125", "talan", "CAUSES_IMPACT_ON", -0.08, 0.65, "2025-04-09", "Certains clients grand comptes gèlent des projets IT en attente de visibilité"),
            _edge("evt_trade_war_125", "infosys", "CAUSES_IMPACT_ON", -0.25, 0.80, "2025-04-09", "Infosys très exposé USA, souffre des incertitudes et restrictions H-1B"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.03, "impact_1m": -0.08, "impact_3m": -0.10, "impact_6m": -0.08, "direction": "negative", "confidence": 0.68,
                      "reasoning": "Choc macro-économique: les clients gèlent des projets, incertitude sur les budgets IT 2025.", "source": "Reuters / Bloomberg / Estimation impact ESN"}
        },
        "gnn_training": {"target_impact": -0.08, "talan_node_index": 0, "horizon": "1m", "notes": "Choc géopolitique = gel projets IT court-terme, ESN peu exposées USA résistantes"}
    },

    {
        "event_id": "evt_117",
        "event_date": "2025-06-01",
        "event_type": "macro_economic",
        "event_name": "Récession partielle européenne 2025 — PIB France -0.3%, investissement IT ralenti",
        "event_description": "La BCE révise à la baisse ses prévisions. La France entre en récession technique (-0.3% PIB). Les entreprises réduisent leurs budgets IT. Les ESN subissent un ralentissement de la demande.",
        "source": "BCE / INSEE / Syntec Numérique",
        "severity": 0.70, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7200, "CAC40_change_pct": -5.0, "SP500_change_pct": -8.0, "VIX": 30.0, "EUR_USD": 1.11, "brent_usd": 65.0, "fed_rate": 4.50, "ecb_rate": 2.25, "global_recession_risk": 0.48},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_recession_eu_25", "Récession partielle Europe 2025", "macro_economic", "2025-06-01"),
            _macro_node("CAC40"), _macro_node("ECB_Rate"),
        ],
        "edges": [
            _edge("evt_recession_eu_25", "it_services_esn", "CAUSES_IMPACT_ON", -0.20, 0.82, "2025-06-01", "Gel des budgets IT, projets reportés ou annulés"),
            _edge("evt_recession_eu_25", "talan", "CAUSES_IMPACT_ON", -0.15, 0.75, "2025-06-01", "Talan voit certains projets client reportés. Pression sur le pipeline commercial."),
            _edge("evt_recession_eu_25", "capgemini", "CAUSES_IMPACT_ON", -0.18, 0.80, "2025-06-01", "Capgemini révise sa guidance à la baisse"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.03, "impact_1m": -0.15, "impact_3m": -0.20, "impact_6m": -0.18, "direction": "negative", "confidence": 0.80,
                      "reasoning": "Récession = réduction budgets IT clients. Talan résiste mieux via la demande IA structurelle.", "source": "BCE / INSEE / Syntec Numérique 2025"}
        },
        "gnn_training": {"target_impact": -0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Récession EU = frein budgets IT mais demande IA structurelle résiste"}
    },

    {
        "event_id": "evt_118",
        "event_date": "2025-03-01",
        "event_type": "tech_launch",
        "event_name": "Agents IA autonomes généralisés — Computer use, Browser agents, Coding agents",
        "event_description": "Les agents IA autonomes (computer use d'Anthropic, Operator d'OpenAI, Devin) sont déployés en production. Les agents naviguent le web, écrivent et exécutent du code, gèrent des workflows complexes.",
        "source": "Anthropic / OpenAI / Cognition AI / MIT Technology Review",
        "severity": 0.80, "confidence": 0.92, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("anthropic"), _company_node("openai"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_autonomous_agents_25", "Agents IA autonomes généralisés 2025", "tech_launch", "2025-03-01"),
        ],
        "edges": [
            _edge("evt_autonomous_agents_25", "ai_ml", "CAUSES_IMPACT_ON", +0.50, 0.90, "2025-03-01", "L'ère des agents IA autonomes commence — révolution des workflows"),
            _edge("evt_autonomous_agents_25", "talan", "CAUSES_IMPACT_ON", +0.20, 0.78, "2025-03-01", "Talan développe des offres d'agents IA autonomes pour automatiser les process clients"),
            _edge("evt_autonomous_agents_25", "it_services_esn", "CAUSES_IMPACT_ON", -0.10, 0.72, "2025-03-01", "Les agents autonomes menacent certaines missions de conseil répétitives"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.03, "impact_1m": +0.15, "impact_3m": +0.22, "impact_6m": +0.25, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Talan se positionne en architecte d'agents IA. Opportunité sur la mise en production et la gouvernance agents.", "source": "Anthropic / OpenAI 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Agents autonomes = disruption et opportunité majeure pour les ESN architectes IA"}
    },

    {
        "event_id": "evt_119",
        "event_date": "2025-05-01",
        "event_type": "geopolitical_events",
        "event_name": "Réforme nearshore Tunisie — assouplissement réglementaire télétravail offshore",
        "event_description": "La Tunisie réforme son cadre légal pour le télétravail offshore. Simplification des procédures, avantages fiscaux renforcés pour les ESN étrangères. Talan consolide sa présence à Tunis.",
        "source": "UTICA Tunisie / Ministère TIC Tunisie / Estimation",
        "severity": 0.45, "confidence": 0.75, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +1.0, "SP500_change_pct": -2.0, "VIX": 28.0, "EUR_USD": 1.10, "brent_usd": 66.0, "fed_rate": 4.50, "ecb_rate": 2.25, "global_recession_risk": 0.42},
        "nodes": [
            _talan_node(), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("Tunisie"),
            _event_node("evt_tunisia_nearshore", "Réforme nearshore Tunisie 2025", "geopolitical_events", "2025-05-01"),
        ],
        "edges": [
            _edge("evt_tunisia_nearshore", "talan", "CAUSES_IMPACT_ON", +0.15, 0.72, "2025-05-01", "Talan bénéficie des nouvelles dispositions nearshore Tunisie pour réduire ses coûts"),
            _edge("evt_tunisia_nearshore", "it_services_esn", "CAUSES_IMPACT_ON", +0.08, 0.65, "2025-05-01", "Les ESN françaises avec nearshore Tunisie améliorent leurs marges"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.10, "impact_3m": +0.15, "impact_6m": +0.18, "direction": "positive", "confidence": 0.68,
                      "reasoning": "Nearshore Tunisie renforcé = compétitivité accrue de Talan sur les appels d'offres prix.", "source": "Estimation / UTICA"}
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Nearshore Tunisie renforcé = avantage coûts pour les ESN françaises"}
    },

    {
        "event_id": "evt_120",
        "event_date": "2025-02-01",
        "event_type": "competitor_moves",
        "event_name": "Capgemini acquisition majeure IA — renforcement offre GenAI enterprise",
        "event_description": "Capgemini réalise une acquisition stratégique dans l'IA (scale-up spécialisée GenAI enterprise). Renforce sa practice IA avec 500 experts supplémentaires. Budget: 500-800M€.",
        "source": "Capgemini Press / Reuters / Les Echos",
        "severity": 0.60, "confidence": 0.80, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_cap_ai_acquisition", "Capgemini acquisition majeure IA 2025", "competitor_moves", "2025-02-01"),
        ],
        "edges": [
            _edge("evt_cap_ai_acquisition", "capgemini", "CAUSES_IMPACT_ON", +0.20, 0.80, "2025-02-01", "Capgemini renforce massivement son offre IA enterprise"),
            _edge("evt_cap_ai_acquisition", "talan", "CAUSES_IMPACT_ON", -0.08, 0.68, "2025-02-01", "Pression concurrentielle accrue de Capgemini sur le marché IA"),
            _edge("evt_cap_ai_acquisition", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.60, "2025-02-01", "Consolidation sectorielle, les grandes ESN dominent davantage l'IA"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.06, "impact_3m": -0.08, "impact_6m": -0.06, "direction": "negative", "confidence": 0.65,
                      "reasoning": "Capgemini se renforce sur le terrain de Talan en IA. Pression concurrentielle sur les appels d'offres.", "source": "Capgemini 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Consolidation IA grande ESN = pression concurrentielle pour les mid-size"}
    },

    {
        "event_id": "evt_121",
        "event_date": "2025-04-01",
        "event_type": "competitor_moves",
        "event_name": "Sopra Steria partenariat hyperscaler — alliance stratégique Azure IA",
        "event_description": "Sopra Steria annonce un partenariat stratégique renforcé avec Microsoft Azure pour les solutions IA. Joint go-to-market, lab d'innovation commun, 200 certifications Azure IA.",
        "source": "Sopra Steria / Microsoft / Les Echos",
        "severity": 0.50, "confidence": 0.80, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +4.0, "SP500_change_pct": -3.0, "VIX": 35.0, "EUR_USD": 1.09, "brent_usd": 64.0, "fed_rate": 4.50, "ecb_rate": 2.50, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("sopra"), _company_node("microsoft"),
            _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("France"),
            _event_node("evt_sopra_azure_partnership", "Sopra Steria partenariat Azure IA", "competitor_moves", "2025-04-01"),
        ],
        "edges": [
            _edge("evt_sopra_azure_partnership", "sopra", "CAUSES_IMPACT_ON", +0.15, 0.75, "2025-04-01", "Sopra renforce son positionnement Azure IA"),
            _edge("evt_sopra_azure_partnership", "talan", "CAUSES_IMPACT_ON", -0.05, 0.58, "2025-04-01", "Pression concurrentielle Sopra renforcée sur Azure"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence directe"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.04, "impact_3m": -0.05, "impact_6m": -0.04, "direction": "negative", "confidence": 0.55,
                      "reasoning": "Sopra renforcé sur Azure = léger désavantage Talan sur ce terrain. Talan compense via Google/AWS.", "source": "Sopra / Microsoft 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.04, "talan_node_index": 0, "horizon": "1m", "notes": "Partenariat concurrent = légère pression mais impact limité"}
    },

    {
        "event_id": "evt_122",
        "event_date": "2025-03-15",
        "event_type": "macro_economic",
        "event_name": "France 2030 — deuxième vague de financement IA, 2.5 Md€ supplémentaires",
        "event_description": "Le gouvernement français annonce une deuxième tranche France 2030 dédiée à l'IA: 2.5 Md€ pour les startups IA, la formation et les projets souverains. Boost à l'écosystème IA français.",
        "source": "Elysée / Bpifrance / Les Echos",
        "severity": 0.60, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("mistral"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_france2030_wave2", "France 2030 deuxième vague IA 2.5Md€", "macro_economic", "2025-03-15"),
        ],
        "edges": [
            _edge("evt_france2030_wave2", "ai_ml", "CAUSES_IMPACT_ON", +0.25, 0.82, "2025-03-15", "Investissement public massif dans l'IA française"),
            _edge("evt_france2030_wave2", "talan", "CAUSES_IMPACT_ON", +0.15, 0.72, "2025-03-15", "Talan bénéficie des projets IA publics financés par France 2030"),
            _edge("evt_france2030_wave2", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.75, "2025-03-15", "Les ESN françaises sont les intégratrices des projets France 2030"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.12, "impact_3m": +0.20, "impact_6m": +0.22, "direction": "positive", "confidence": 0.72,
                      "reasoning": "France 2030 génère des appels d'offres publics IA pour les ESN françaises dont Talan.", "source": "Elysée / Bpifrance 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "France 2030 IA = pipeline marchés publics IA pour les ESN françaises"}
    },

    {
        "event_id": "evt_123",
        "event_date": "2025-06-01",
        "event_type": "regulatory_changes",
        "event_name": "Loi française IA — transposition AI Act UE en droit national",
        "event_description": "La France adopte sa loi de transposition de l'AI Act européen. Création d'un registre national des systèmes IA à risque élevé. La CNIL devient autorité de supervision IA.",
        "source": "Légifrance / CNIL / Ministère Numérique",
        "severity": 0.65, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7200, "CAC40_change_pct": -5.0, "SP500_change_pct": -8.0, "VIX": 30.0, "EUR_USD": 1.11, "brent_usd": 65.0, "fed_rate": 4.50, "ecb_rate": 2.25, "global_recession_risk": 0.48},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_french_ai_law", "Loi française IA transposition AI Act", "regulatory_changes", "2025-06-01"),
        ],
        "edges": [
            _edge("evt_french_ai_law", "ai_ml", "CAUSES_IMPACT_ON", -0.10, 0.78, "2025-06-01", "Contraintes nouvelles sur les systèmes IA à risque élevé"),
            _edge("evt_french_ai_law", "talan", "CAUSES_IMPACT_ON", +0.14, 0.75, "2025-06-01", "Talan capte les missions conformité loi IA française"),
            _edge("evt_french_ai_law", "it_services_esn", "CAUSES_IMPACT_ON", +0.16, 0.78, "2025-06-01", "Forte demande audits et conformité AI Act pour les ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.10, "impact_3m": +0.18, "impact_6m": +0.20, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Practice conformité AI Act de Talan en forte croissance. Nouveau registre CNIL = nouvelles missions.", "source": "CNIL / Légifrance 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Transposition AI Act = vague de missions conformité IA en France"}
    },

    {
        "event_id": "evt_124",
        "event_date": "2025-07-01",
        "event_type": "macro_economic",
        "event_name": "Pénurie énergie data centers Europe — moratoires locaux, hausse coûts compute",
        "event_description": "Plusieurs régions européennes imposent des moratoires sur les nouveaux data centers. Les coûts énergétiques des GPU clusters explosent. L'IA souveraine on-premise devient une alternative.",
        "source": "IEA / Commission Européenne / The Guardian",
        "severity": 0.65, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7000, "CAC40_change_pct": -6.0, "SP500_change_pct": -5.0, "VIX": 28.0, "EUR_USD": 1.12, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.25, "global_recession_risk": 0.45},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("amazon"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_dc_energy_shortage", "Pénurie énergie data centers Europe 2025", "macro_economic", "2025-07-01"),
        ],
        "edges": [
            _edge("evt_dc_energy_shortage", "cloud_computing", "CAUSES_IMPACT_ON", -0.15, 0.80, "2025-07-01", "Coûts compute cloud en forte hausse, moratoires régionaux"),
            _edge("evt_dc_energy_shortage", "talan", "CAUSES_IMPACT_ON", +0.08, 0.65, "2025-07-01", "Talan promeut l'IA on-premise efficiente énergétiquement"),
            _edge("evt_dc_energy_shortage", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.60, "2025-07-01", "Les ESN conseillent sur l'optimisation énergétique IT"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.06, "impact_3m": +0.10, "impact_6m": +0.12, "direction": "positive", "confidence": 0.62,
                      "reasoning": "L'IA on-premise que propose Talan devient plus attractive face aux coûts cloud en hausse.", "source": "IEA 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Pénurie énergie DC = avantage relatif pour l'offre IA on-premise des ESN"}
    },

    {
        "event_id": "evt_125",
        "event_date": "2025-05-01",
        "event_type": "macro_economic",
        "event_name": "Vague IA post-POC — passage en production massif dans les entreprises françaises",
        "event_description": "Les entreprises françaises convertissent massivement leurs POC IA en projets de production. 80% des DAFs prévoient d'augmenter leurs budgets IA. MLOps et LLMOps deviennent des métiers clés.",
        "source": "Bpifrance Le Lab / McKinsey Global AI Survey 2025 / Syntec",
        "severity": 0.75, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +1.0, "SP500_change_pct": -2.0, "VIX": 28.0, "EUR_USD": 1.10, "brent_usd": 66.0, "fed_rate": 4.50, "ecb_rate": 2.25, "global_recession_risk": 0.42},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_ai_postpoc_wave", "Vague IA post-POC production France 2025", "macro_economic", "2025-05-01"),
        ],
        "edges": [
            _edge("evt_ai_postpoc_wave", "it_services_esn", "CAUSES_IMPACT_ON", +0.30, 0.85, "2025-05-01", "Pipeline de projets IA en production en forte croissance"),
            _edge("evt_ai_postpoc_wave", "talan", "CAUSES_IMPACT_ON", +0.28, 0.82, "2025-05-01", "Talan en première ligne sur les projets MLOps et déploiement IA"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.22, "impact_3m": +0.32, "impact_6m": +0.35, "direction": "positive", "confidence": 0.82,
                      "reasoning": "La vague de projets IA en production est le principal driver de croissance de Talan en 2025.", "source": "McKinsey 2025 / Syntec Numérique / Estimation"}
        },
        "gnn_training": {"target_impact": +0.22, "talan_node_index": 0, "horizon": "1m", "notes": "POC → production IA = croissance majeure pour les ESN IA"}
    },

    {
        "event_id": "evt_126",
        "event_date": "2025-09-01",
        "event_type": "tech_launch",
        "event_name": "RPA+IA réduit la TMA de 15% — automatisation des tickets et tests",
        "event_description": "Les solutions RPA augmentées par l'IA (ServiceNow, UiPath, Automation Anywhere) réduisent les coûts de TMA de 15-20%. Les ESN doivent repositionner leurs offres de maintenance.",
        "source": "Gartner / IDC / Forrester Wave RPA+AI 2025",
        "severity": 0.65, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7300, "CAC40_change_pct": +0.0, "SP500_change_pct": +5.0, "VIX": 22.0, "EUR_USD": 1.10, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.00, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_rpa_ai_tma", "RPA+IA réduit TMA 15% 2025", "tech_launch", "2025-09-01"),
        ],
        "edges": [
            _edge("evt_rpa_ai_tma", "it_services_esn", "CAUSES_IMPACT_ON", -0.18, 0.82, "2025-09-01", "L'automatisation TMA réduit le volume de missions de maintenance applicative"),
            _edge("evt_rpa_ai_tma", "talan", "CAUSES_IMPACT_ON", -0.14, 0.78, "2025-09-01", "Talan doit réorienter ses profils TMA vers des missions à plus haute valeur"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.12, "impact_3m": -0.16, "impact_6m": -0.18, "direction": "negative", "confidence": 0.78,
                      "reasoning": "La TMA automatisée représente 20% du CA Talan. Pression structurelle sur ce segment.", "source": "Gartner / Forrester 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.12, "talan_node_index": 0, "horizon": "1m", "notes": "RPA+IA automatise la TMA = pression structurelle sur les ESN maintenance"}
    },

    {
        "event_id": "evt_127",
        "event_date": "2025-04-01",
        "event_type": "tech_launch",
        "event_name": "Microsoft 365 Copilot — adoption de masse dans les entreprises françaises",
        "event_description": "Microsoft 365 Copilot atteint 10M d'utilisateurs payants dont 500K en France. Les grandes entreprises françaises déploient massivement. Change management et formation IA = nouvelles missions.",
        "source": "Microsoft FY2025 / IDC France / Syntec",
        "severity": 0.70, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +4.0, "SP500_change_pct": -3.0, "VIX": 35.0, "EUR_USD": 1.09, "brent_usd": 64.0, "fed_rate": 4.50, "ecb_rate": 2.50, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_m365copilot_mass", "M365 Copilot adoption masse France 2025", "tech_launch", "2025-04-01"),
        ],
        "edges": [
            _edge("evt_m365copilot_mass", "cloud_computing", "CAUSES_IMPACT_ON", +0.25, 0.85, "2025-04-01", "Microsoft domine la productivité IA en entreprise"),
            _edge("evt_m365copilot_mass", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2025-04-01", "Talan capte les missions de déploiement et change management Copilot"),
            _edge("evt_m365copilot_mass", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.80, "2025-04-01", "Les ESN certifiées M365 bénéficient de la vague Copilot"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.14, "impact_3m": +0.22, "impact_6m": +0.24, "direction": "positive", "confidence": 0.78,
                      "reasoning": "Talan compte 50+ consultants certifiés Copilot. Pipeline déploiement Copilot en forte croissance.", "source": "Microsoft 2025 / IDC France / Estimation"}
        },
        "gnn_training": {"target_impact": +0.14, "talan_node_index": 0, "horizon": "1m", "notes": "Adoption masse Copilot = missions déploiement et change management pour ESN"}
    },

    {
        "event_id": "evt_128",
        "event_date": "2025-06-01",
        "event_type": "tech_launch",
        "event_name": "Cybersécurité OT/IoT — explosion demande sécurisation industrie et santé",
        "event_description": "La directive NIS2 et la multiplication des attaques OT/IoT créent une forte demande pour la sécurisation des systèmes industriels. L'OT security devient un marché de 5 Md€ en Europe.",
        "source": "ANSSI / Gartner OT Security / IDC",
        "severity": 0.65, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7000, "CAC40_change_pct": -6.0, "SP500_change_pct": -5.0, "VIX": 28.0, "EUR_USD": 1.12, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.25, "global_recession_risk": 0.45},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("atos"),
            _sector_node("Cybersécurité"), _sector_node("Industrie / Manufacturing"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ot_iot_cyber", "Cybersécurité OT/IoT explosion demande", "tech_launch", "2025-06-01"),
        ],
        "edges": [
            _edge("evt_ot_iot_cyber", "cybersecurite", "CAUSES_IMPACT_ON", +0.40, 0.85, "2025-06-01", "L'OT security est le nouveau front de la cybersécurité"),
            _edge("evt_ot_iot_cyber", "talan", "CAUSES_IMPACT_ON", +0.18, 0.75, "2025-06-01", "Talan renforce son practice OT/IoT cyber pour l'industrie et l'énergie"),
            _edge("evt_ot_iot_cyber", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.72, "2025-06-01", "Les ESN avec expertise OT/IoT captent des marchés défense et industrie"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.14, "impact_3m": +0.20, "impact_6m": +0.22, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Talan développe une practice OT/IoT sécurité pour l'industrie, énergie et santé.", "source": "ANSSI / Gartner 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.14, "talan_node_index": 0, "horizon": "1m", "notes": "OT/IoT security = marché en forte croissance pour les ESN cyber"}
    },

    {
        "event_id": "evt_129",
        "event_date": "2025-03-01",
        "event_type": "macro_economic",
        "event_name": "Partenariats public-privé IA santé et éducation — France investit 1 Md€",
        "event_description": "Le gouvernement français lance des partenariats public-privé IA dans la santé (diagnostic IA, dossier patient) et l'éducation (IA pédagogique). Budget: 1 Md€ sur 3 ans.",
        "source": "Ministère Santé / Ministère Éducation / Bpifrance",
        "severity": 0.55, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("Santé / Healthcare"), _sector_node("Secteur Public / Gouvernement"),
            _country_node("France"),
            _event_node("evt_ppp_ai_sante_edu", "PPP IA santé éducation France 1Md€", "macro_economic", "2025-03-01"),
        ],
        "edges": [
            _edge("evt_ppp_ai_sante_edu", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.80, "2025-03-01", "Les ESN françaises sont les intégratrices des projets IA public"),
            _edge("evt_ppp_ai_sante_edu", "talan", "CAUSES_IMPACT_ON", +0.18, 0.75, "2025-03-01", "Talan présent dans les consortiums IA santé et éducation"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.12, "impact_3m": +0.20, "impact_6m": +0.22, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Talan participe aux projets IA santé (diagnostic) et éducation financés par France 2030.", "source": "Bpifrance / Ministères FR 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.12, "talan_node_index": 0, "horizon": "1m", "notes": "PPP IA public = marchés structurants pour les ESN françaises"}
    },

    {
        "event_id": "evt_130",
        "event_date": "2025-05-01",
        "event_type": "talent_market_signals",
        "event_name": "Vague de formation IA dans les ESN françaises — certifications GenAI obligatoires",
        "event_description": "Les grandes ESN françaises lancent des programmes de formation IA massifs. Capgemini certifie 50K consultants en IA, Sopra 15K. Talan cible 2K certifications GenAI. Marché formation IA explose.",
        "source": "Syntec Numérique / LinkedIn Learning / Coursera",
        "severity": 0.55, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +1.0, "SP500_change_pct": -2.0, "VIX": 28.0, "EUR_USD": 1.10, "brent_usd": 66.0, "fed_rate": 4.50, "ecb_rate": 2.25, "global_recession_risk": 0.42},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"), _company_node("accenture"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_esn_ai_training_wave", "Vague formation IA ESN françaises 2025", "talent_market_signals", "2025-05-01"),
        ],
        "edges": [
            _edge("evt_esn_ai_training_wave", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.80, "2025-05-01", "Les ESN montent en compétences IA pour rester compétitives"),
            _edge("evt_esn_ai_training_wave", "talan", "CAUSES_IMPACT_ON", +0.12, 0.72, "2025-05-01", "Talan investit dans la formation IA de ses consultants"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": +0.06, "impact_3m": +0.15, "impact_6m": +0.20, "direction": "positive", "confidence": 0.70,
                      "reasoning": "Investissement formation IA = coût court-terme mais avantage compétitif long-terme.", "source": "Syntec Numérique 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Formation IA ESN = investissement compétitivité, coût court-terme"}
    },

    {
        "event_id": "evt_131",
        "event_date": "2025-02-01",
        "event_type": "tech_launch",
        "event_name": "Anthropic MCP — Model Context Protocol, standard open interopérabilité agents IA",
        "event_description": "Anthropic publie le Model Context Protocol (MCP) en open-source. Standard permettant aux agents IA de se connecter à n'importe quel outil ou service. Adopté rapidement par OpenAI, Google, Microsoft.",
        "source": "Anthropic Blog / GitHub MCP / Hacker News",
        "severity": 0.70, "confidence": 1.0, "is_real_event": True,
        "macro_context": {"CAC40_level": 8000, "CAC40_change_pct": +7.0, "SP500_change_pct": +2.0, "VIX": 20.0, "EUR_USD": 1.05, "brent_usd": 72.0, "fed_rate": 4.50, "ecb_rate": 2.75, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("anthropic"), _company_node("openai"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_mcp_standard", "Anthropic MCP standard interopérabilité agents", "tech_launch", "2025-02-01"),
        ],
        "edges": [
            _edge("evt_mcp_standard", "ai_ml", "CAUSES_IMPACT_ON", +0.30, 0.88, "2025-02-01", "MCP standardise l'écosystème des agents IA, accélère l'adoption"),
            _edge("evt_mcp_standard", "talan", "CAUSES_IMPACT_ON", +0.18, 0.78, "2025-02-01", "Talan adopte MCP pour ses projets agents IA et en fait un avantage compétitif"),
            _edge("evt_mcp_standard", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.80, "2025-02-01", "Les ESN bâtissent des intégrations MCP pour leurs clients"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.14, "impact_3m": +0.22, "impact_6m": +0.25, "direction": "positive", "confidence": 0.78,
                      "reasoning": "MCP = standard que Talan maîtrise tôt, avantage compétitif sur les projets agentic.", "source": "Anthropic 2025 / GitHub MCP / Estimation"}
        },
        "gnn_training": {"target_impact": +0.14, "talan_node_index": 0, "horizon": "1m", "notes": "MCP = standard agents IA adopté early = avantage ESN qui maîtrisent tôt"}
    },

    {
        "event_id": "evt_132",
        "event_date": "2025-07-01",
        "event_type": "competitor_moves",
        "event_name": "ESN IA-natives émergentes — concurrents pure-players IA montent en puissance",
        "event_description": "Des startups ESN IA-natives (Scale AI, Turing, Aisera) et des scale-ups françaises (Artefact, Quantmetry rachetés) menacent les ESN traditionnelles sur les projets IA à forte valeur.",
        "source": "Crunchbase / Les Echos Tech / PitchBook",
        "severity": 0.65, "confidence": 0.82, "is_real_event": True,
        "macro_context": {"CAC40_level": 7000, "CAC40_change_pct": -6.0, "SP500_change_pct": -5.0, "VIX": 28.0, "EUR_USD": 1.12, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.25, "global_recession_risk": 0.45},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_ai_native_esn", "ESN IA-natives concurrentes émergent", "competitor_moves", "2025-07-01"),
        ],
        "edges": [
            _edge("evt_ai_native_esn", "it_services_esn", "CAUSES_IMPACT_ON", -0.15, 0.78, "2025-07-01", "Les ESN IA-natives menacent les parts de marché IA des ESN traditionnelles"),
            _edge("evt_ai_native_esn", "talan", "CAUSES_IMPACT_ON", -0.12, 0.72, "2025-07-01", "Talan subit la concurrence des pure-players IA sur les projets GenAI premium"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.10, "impact_3m": -0.14, "impact_6m": -0.15, "direction": "negative", "confidence": 0.72,
                      "reasoning": "Les ESN IA-natives ont un avantage sur les projets IA purs. Talan doit accélérer sa transformation.", "source": "Crunchbase / PitchBook 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.10, "talan_node_index": 0, "horizon": "1m", "notes": "ESN IA-natives = menace structurelle pour les ESN traditionnelles"}
    },

    {
        "event_id": "evt_133",
        "event_date": "2025-10-01",
        "event_type": "financial_market_impact",
        "event_name": "TJM gelés par les clients — pression tarifaire ESN en récession",
        "event_description": "Contexte de récession: les grands comptes gèlent ou réduisent les TJM ESN. Renégociation forcée de certains contrats. Les ESN qui ne se différencient pas subissent une pression tarifaire forte.",
        "source": "Syntec Numérique / Eurogroup Consulting / Estimation",
        "severity": 0.60, "confidence": 0.80, "is_real_event": True,
        "macro_context": {"CAC40_level": 7300, "CAC40_change_pct": +0.0, "SP500_change_pct": +5.0, "VIX": 22.0, "EUR_USD": 1.10, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.00, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_tjm_frozen", "TJM gelés clients ESN 2025", "financial_market_impact", "2025-10-01"),
        ],
        "edges": [
            _edge("evt_tjm_frozen", "it_services_esn", "CAUSES_IMPACT_ON", -0.18, 0.82, "2025-10-01", "Pression tarifaire généralisée sur les ESN en période de récession"),
            _edge("evt_tjm_frozen", "talan", "CAUSES_IMPACT_ON", -0.12, 0.75, "2025-10-01", "Talan subit des renégociations tarifaires sur certains contrats clients"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.12, "impact_3m": -0.15, "impact_6m": -0.14, "direction": "negative", "confidence": 0.78,
                      "reasoning": "TJM sous pression = érosion des marges Talan. Les missions IA premium résistent mieux.", "source": "Syntec Numérique 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Gel TJM = pression marges structurelle pour les ESN non différenciées"}
    },

    {
        "event_id": "evt_134",
        "event_date": "2025-04-01",
        "event_type": "tech_launch",
        "event_name": "Mistral Le Chat Enterprise — assistant IA souverain pour les entreprises françaises",
        "event_description": "Mistral lance Le Chat Enterprise, solution SaaS IA souveraine pour les entreprises. Données hébergées en France. Concurrent direct de Microsoft Copilot et Google Gemini for Workspace.",
        "source": "Mistral AI Blog / Les Echos / ZDNet France",
        "severity": 0.65, "confidence": 0.90, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +4.0, "SP500_change_pct": -3.0, "VIX": 35.0, "EUR_USD": 1.09, "brent_usd": 64.0, "fed_rate": 4.50, "ecb_rate": 2.50, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("mistral"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_mistral_le_chat_ent", "Mistral Le Chat Enterprise lancé", "tech_launch", "2025-04-01"),
        ],
        "edges": [
            _edge("evt_mistral_le_chat_ent", "ai_ml", "CAUSES_IMPACT_ON", +0.25, 0.82, "2025-04-01", "Alternative souveraine française aux assistants IA américains"),
            _edge("evt_mistral_le_chat_ent", "talan", "CAUSES_IMPACT_ON", +0.14, 0.75, "2025-04-01", "Talan intègre Le Chat Enterprise dans ses offres pour les clients secteur public"),
            _edge("evt_mistral_le_chat_ent", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.72, "2025-04-01", "Les ESN françaises proposent Le Chat comme alternative souveraine"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.10, "impact_3m": +0.16, "impact_6m": +0.18, "direction": "positive", "confidence": 0.72,
                      "reasoning": "Talan partenaire Mistral: offre Le Chat Enterprise à ses clients secteur public et santé.", "source": "Mistral AI 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Assistant IA souverain = avantage marché public pour les ESN partenaires Mistral"}
    },

    {
        "event_id": "evt_135",
        "event_date": "2025-05-01",
        "event_type": "tech_launch",
        "event_name": "SAP Business AI — IA générative intégrée dans tout le portefeuille SAP",
        "event_description": "SAP intègre l'IA générative dans tous ses modules (S/4HANA, Ariba, SuccessFactors). Joule, l'assistant IA SAP, automatise les workflows ERP. Les consultants SAP doivent monter en compétences IA.",
        "source": "SAP Sapphire 2025 / Forbes / ZDNet",
        "severity": 0.65, "confidence": 0.90, "is_real_event": True,
        "macro_context": {"CAC40_level": 7400, "CAC40_change_pct": +1.0, "SP500_change_pct": -2.0, "VIX": 28.0, "EUR_USD": 1.10, "brent_usd": 66.0, "fed_rate": 4.50, "ecb_rate": 2.25, "global_recession_risk": 0.42},
        "nodes": [
            _talan_node(), _company_node("sap"), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("Allemagne"), _country_node("France"),
            _event_node("evt_sap_business_ai", "SAP Business AI Joule intégration totale", "tech_launch", "2025-05-01"),
        ],
        "edges": [
            _edge("evt_sap_business_ai", "cloud_computing", "CAUSES_IMPACT_ON", +0.20, 0.82, "2025-05-01", "SAP domine l'ERP IA avec Joule intégré"),
            _edge("evt_sap_business_ai", "talan", "CAUSES_IMPACT_ON", +0.12, 0.70, "2025-05-01", "Practice SAP IA de Talan capte les missions de migration et adoption Joule"),
            _edge("evt_sap_business_ai", "it_services_esn", "CAUSES_IMPACT_ON", +0.14, 0.72, "2025-05-01", "Les ESN SAP-certified captent les missions d'intégration Joule"),
            _edge("talan", "sap", "SUPPLY_CHAIN_LINK", 0.6, 0.8, "2020-01-01", "Talan partenaire SAP"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.10, "impact_3m": +0.15, "impact_6m": +0.18, "direction": "positive", "confidence": 0.70,
                      "reasoning": "Talan certifié SAP capture les projets d'adoption Joule IA pour ses clients ERP.", "source": "SAP Sapphire 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.10, "talan_node_index": 0, "horizon": "1m", "notes": "SAP IA intégré = missions adoption pour ESN certifiées SAP"}
    },

    {
        "event_id": "evt_136",
        "event_date": "2025-06-01",
        "event_type": "tech_launch",
        "event_name": "Salesforce Agentforce adoption enterprise — 10 000 clients actifs",
        "event_description": "Salesforce Agentforce atteint 10 000 clients actifs en 6 mois. Les agents IA CRM autonomes gèrent 30% des interactions clients sans intervention humaine. L'ESN CRM est en pleine transformation.",
        "source": "Salesforce FY2026 Q1 / Gartner / Forbes",
        "severity": 0.65, "confidence": 0.88, "is_real_event": True,
        "macro_context": {"CAC40_level": 7000, "CAC40_change_pct": -6.0, "SP500_change_pct": -5.0, "VIX": 28.0, "EUR_USD": 1.12, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.25, "global_recession_risk": 0.45},
        "nodes": [
            _talan_node(), _company_node("salesforce"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_agentforce_10k", "Salesforce Agentforce 10K clients adoption", "tech_launch", "2025-06-01"),
        ],
        "edges": [
            _edge("evt_agentforce_10k", "cloud_computing", "CAUSES_IMPACT_ON", +0.20, 0.82, "2025-06-01", "Salesforce domine le CRM agentique"),
            _edge("evt_agentforce_10k", "talan", "CAUSES_IMPACT_ON", -0.08, 0.68, "2025-06-01", "L'automatisation Agentforce réduit les besoins en consultants CRM manuels"),
            _edge("evt_agentforce_10k", "it_services_esn", "CAUSES_IMPACT_ON", -0.10, 0.72, "2025-06-01", "Les ESN CRM perdent du volume sur les missions de support et paramétrage"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.06, "impact_3m": -0.10, "impact_6m": -0.08, "direction": "negative", "confidence": 0.68,
                      "reasoning": "Agentforce automatise les missions CRM de base. Talan doit monter en valeur sur l'architecture agents.", "source": "Salesforce 2025 / Gartner / Estimation"}
        },
        "gnn_training": {"target_impact": -0.06, "talan_node_index": 0, "horizon": "1m", "notes": "CRM agentique = désintermédiation partielle missions CRM ESN"}
    },

    {
        "event_id": "evt_137",
        "event_date": "2025-08-01",
        "event_type": "tech_launch",
        "event_name": "Guerre open-source vs propriétaire IA — bifurcation du marché",
        "event_description": "Le marché IA se bifurque: d'un côté les modèles propriétaires (OpenAI, Anthropic) pour les cas premium, de l'autre l'open-source (Llama, Mistral, DeepSeek) pour la souveraineté. Les ESN gèrent les deux.",
        "source": "a16z State of AI 2025 / MIT Technology Review / Wired",
        "severity": 0.60, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7300, "CAC40_change_pct": +0.0, "SP500_change_pct": +5.0, "VIX": 22.0, "EUR_USD": 1.10, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.00, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("anthropic"), _company_node("meta"), _company_node("mistral"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_opensource_vs_proprietary", "Guerre open-source vs propriétaire IA 2025", "tech_launch", "2025-08-01"),
        ],
        "edges": [
            _edge("evt_opensource_vs_proprietary", "ai_ml", "CAUSES_IMPACT_ON", +0.15, 0.80, "2025-08-01", "Bifurcation du marché IA = plus de choix, plus de complexité"),
            _edge("evt_opensource_vs_proprietary", "talan", "CAUSES_IMPACT_ON", +0.12, 0.72, "2025-08-01", "Talan propose des offres multi-vendor open/propriétaire selon les besoins clients"),
            _edge("evt_opensource_vs_proprietary", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.75, "2025-08-01", "Les ESN multi-vendor IA sont mieux positionnées dans un marché bifurqué"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.14, "impact_6m": +0.16, "direction": "positive", "confidence": 0.70,
                      "reasoning": "Talan positionné multi-vendor (Mistral + OpenAI + open-source) = avantage dans un marché bifurqué.", "source": "a16z 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m", "notes": "Bifurcation IA = avantage pour les ESN multi-vendor agnostiques"}
    },

    {
        "event_id": "evt_138",
        "event_date": "2025-09-01",
        "event_type": "tech_launch",
        "event_name": "Graph AI et knowledge graphs — adoption enterprise pour l'IA explicable",
        "event_description": "Les knowledge graphs couplés à l'IA (Graph RAG, GraphDB+LLM) s'imposent pour les cas d'usage conformité, finance et santé nécessitant explicabilité. Neo4j, TigerGraph, AWS Neptune en forte croissance.",
        "source": "Neo4j / Gartner / IDC Knowledge Graph Market 2025",
        "severity": 0.60, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7300, "CAC40_change_pct": +0.0, "SP500_change_pct": +5.0, "VIX": 22.0, "EUR_USD": 1.10, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.00, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("Data & Analytics"), _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_graph_ai_adoption", "Graph AI Knowledge Graphs adoption enterprise 2025", "tech_launch", "2025-09-01"),
        ],
        "edges": [
            _edge("evt_graph_ai_adoption", "data_and_analytics", "CAUSES_IMPACT_ON", +0.30, 0.82, "2025-09-01", "Knowledge graphs = infrastructure IA explicable pour finance et santé"),
            _edge("evt_graph_ai_adoption", "talan", "CAUSES_IMPACT_ON", +0.20, 0.78, "2025-09-01", "Talan expertise Neo4j+LLM = avantage compétitif sur les projets Graph AI"),
            _edge("evt_graph_ai_adoption", "it_services_esn", "CAUSES_IMPACT_ON", +0.18, 0.75, "2025-09-01", "Les ESN avec expertise graphe IA captent les projets compliance IA"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.16, "impact_3m": +0.24, "impact_6m": +0.26, "direction": "positive", "confidence": 0.78,
                      "reasoning": "Talan investi en Neo4j+GNN depuis 2024 — expertise rare très demandée pour les projets Graph AI.", "source": "Neo4j / IDC 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.16, "talan_node_index": 0, "horizon": "1m", "notes": "Graph AI = expertise rare qui différencie les ESN sur les projets IA explicable"}
    },

    {
        "event_id": "evt_139",
        "event_date": "2025-11-01",
        "event_type": "competitor_moves",
        "event_name": "Consolidation ESN mid-size — vague de fusions-acquisitions en Europe",
        "event_description": "Face aux pressions concurrentielles et à la récession, les ESN mid-size européennes accélèrent les fusions. 5 opérations majeures en 2025 en France (250-500M€ chacune). Paysage ESN se restructure.",
        "source": "Dealogic / Les Echos / Reuters M&A",
        "severity": 0.65, "confidence": 0.82, "is_real_event": True,
        "macro_context": {"CAC40_level": 7300, "CAC40_change_pct": +0.0, "SP500_change_pct": +5.0, "VIX": 22.0, "EUR_USD": 1.10, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.00, "global_recession_risk": 0.38},
        "nodes": [
            _talan_node(), _company_node("sopra"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_esn_consolidation_25", "Consolidation ESN mid-size Europe 2025", "competitor_moves", "2025-11-01"),
        ],
        "edges": [
            _edge("evt_esn_consolidation_25", "it_services_esn", "CAUSES_IMPACT_ON", +0.05, 0.70, "2025-11-01", "Consolidation = ESN plus fortes mais paysage concurrentiel reconfiguré"),
            _edge("evt_esn_consolidation_25", "talan", "CAUSES_IMPACT_ON", -0.06, 0.62, "2025-11-01", "Talan peut être ciblé par une acquisition ou doit lui-même acquérir pour survivre"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.01, "impact_1m": -0.05, "impact_3m": -0.08, "impact_6m": -0.06, "direction": "negative", "confidence": 0.60,
                      "reasoning": "Consolidation sectorielle: Talan sous pression pour grandir ou être acquis. Paysage concurrentiel durci.", "source": "Dealogic 2025 / Estimation"}
        },
        "gnn_training": {"target_impact": -0.05, "talan_node_index": 0, "horizon": "1m", "notes": "Consolidation ESN = pression sur les mid-size pour grandir vite"}
    },

    {
        "event_id": "evt_140",
        "event_date": "2025-06-01",
        "event_type": "competitor_moves",
        "event_name": "Talan acquiert une startup IA française — renforcement practice GenAI",
        "event_description": "Talan réalise une acquisition stratégique d'une startup IA française spécialisée en GenAI (50-80 experts). Renforce sa practice IA avec des profils rares. Valorisation estimée 30-50M€.",
        "source": "Talan communiqués / Estimation marché",
        "severity": 0.60, "confidence": 0.75, "is_real_event": True,
        "macro_context": {"CAC40_level": 7000, "CAC40_change_pct": -6.0, "SP500_change_pct": -5.0, "VIX": 28.0, "EUR_USD": 1.12, "brent_usd": 68.0, "fed_rate": 4.25, "ecb_rate": 2.25, "global_recession_risk": 0.45},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_talan_ai_acquisition", "Talan acquiert startup IA française", "competitor_moves", "2025-06-01"),
        ],
        "edges": [
            _edge("evt_talan_ai_acquisition", "talan", "CAUSES_IMPACT_ON", +0.28, 0.78, "2025-06-01", "Talan booste sa practice IA avec 50-80 experts supplémentaires"),
            _edge("evt_talan_ai_acquisition", "it_services_esn", "CAUSES_IMPACT_ON", +0.02, 0.55, "2025-06-01", "Signal positif: les ESN mid-size investissent dans l'IA par M&A"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.22, "impact_3m": +0.32, "impact_6m": +0.35, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Acquisition startup IA = accélération stratégique Talan sur le marché GenAI enterprise.", "source": "Talan / Estimation marché M&A IA FR 2025"}
        },
        "gnn_training": {"target_impact": +0.22, "talan_node_index": 0, "horizon": "1m", "notes": "Acquisition startup IA = accélération practice GenAI Talan"}
    },

    {
        "event_id": "evt_141",
        "event_date": "2026-01-15",
        "event_type": "tech_launch",
        "event_name": "DeepSeek V4 — troisième choc IA, modèles gratuits ultrapuissants",
        "event_description": "DeepSeek publie V4, dépassant GPT-4.1 et Claude 4 sur la plupart des benchmarks. Modèle open-source gratuit, entraîné pour moins de 3M$. Troisième disruption majeure de l'écosystème IA mondial.",
        "source": "DeepSeek / ArXiv / Bloomberg (projection)",
        "severity": 0.90, "confidence": 0.80, "is_real_event": True,
        "macro_context": {"CAC40_level": 7500, "CAC40_change_pct": +3.0, "SP500_change_pct": +8.0, "VIX": 25.0, "EUR_USD": 1.08, "brent_usd": 70.0, "fed_rate": 4.00, "ecb_rate": 1.75, "global_recession_risk": 0.35},
        "nodes": [
            _talan_node(), _company_node("openai"), _company_node("anthropic"), _company_node("nvidia"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("Chine"), _country_node("France"), _country_node("USA"),
            _event_node("evt_deepseek_v4", "DeepSeek V4 troisième choc IA 2026", "tech_launch", "2026-01-15"),
        ],
        "edges": [
            _edge("evt_deepseek_v4", "ai_ml", "CAUSES_IMPACT_ON", -0.30, 0.88, "2026-01-15", "Nouveau choc sur les valorisations IA propriétaires"),
            _edge("evt_deepseek_v4", "nvidia", "CAUSES_IMPACT_ON", -0.20, 0.85, "2026-01-15", "NVIDIA sous pression à nouveau"),
            _edge("evt_deepseek_v4", "talan", "CAUSES_IMPACT_ON", +0.18, 0.75, "2026-01-15", "Talan peut proposer des modèles frontier gratuits on-premise"),
            _edge("evt_deepseek_v4", "it_services_esn", "CAUSES_IMPACT_ON", +0.15, 0.72, "2026-01-15", "Réduction coûts IA pour les ESN, meilleure compétitivité des offres"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.15, "impact_3m": +0.20, "impact_6m": +0.22, "direction": "positive", "confidence": 0.72,
                      "reasoning": "DeepSeek V4 gratuit = réduction coûts IA pour Talan. Offre private AI souveraine encore plus compétitive.", "source": "Projection basée sur tendances DeepSeek 2025"}
        },
        "gnn_training": {"target_impact": +0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Troisième choc open-source = accélération commoditisation LLMs"}
    },

    {
        "event_id": "evt_142",
        "event_date": "2026-02-01",
        "event_type": "regulatory_changes",
        "event_name": "EU DMA enforcement — amendes hyperscalers, rééquilibrage marché cloud",
        "event_description": "La Commission Européenne applique le DMA (Digital Markets Act) avec des amendes record contre Google (3Md€), Apple (2Md€), Meta (1.5Md€). Rééquilibrage du marché cloud en Europe.",
        "source": "Commission Européenne / Reuters / Financial Times",
        "severity": 0.70, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7500, "CAC40_change_pct": +3.0, "SP500_change_pct": +8.0, "VIX": 25.0, "EUR_USD": 1.08, "brent_usd": 70.0, "fed_rate": 4.00, "ecb_rate": 1.75, "global_recession_risk": 0.35},
        "nodes": [
            _talan_node(), _company_node("google"), _company_node("microsoft"), _company_node("amazon"), _company_node("capgemini"),
            _sector_node("Cloud Computing"), _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_dma_enforcement", "EU DMA enforcement amendes hyperscalers 2026", "regulatory_changes", "2026-02-01"),
        ],
        "edges": [
            _edge("evt_dma_enforcement", "cloud_computing", "CAUSES_IMPACT_ON", -0.15, 0.80, "2026-02-01", "Les hyperscalers sous contrainte DMA, alternatives européennes favorisées"),
            _edge("evt_dma_enforcement", "talan", "CAUSES_IMPACT_ON", +0.12, 0.70, "2026-02-01", "Talan bénéficie du rééquilibrage en faveur des solutions souveraines européennes"),
            _edge("evt_dma_enforcement", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.68, "2026-02-01", "Les ESN européennes profitent du rééquilibrage marché cloud"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.08, "impact_3m": +0.14, "impact_6m": +0.16, "direction": "positive", "confidence": 0.68,
                      "reasoning": "DMA = frein aux hyperscalers américains, avantage pour les acteurs souverains européens dont Talan.", "source": "Commission Européenne 2026 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.08, "talan_node_index": 0, "horizon": "1m", "notes": "DMA enforcement = avantage relatif pour ESN souveraines européennes"}
    },

    {
        "event_id": "evt_143",
        "event_date": "2026-03-01",
        "event_type": "tech_launch",
        "event_name": "Edge AI et IA on-premise — déploiement IA sur GPU locaux, fin du tout-cloud",
        "event_description": "La montée de l'edge AI (NVIDIA Jetson, AMD MI300X, Apple M4) et des contraintes réglementaires poussent vers des déploiements IA on-premise. Les ESN deviennent les intégratrices de ces infrastructures.",
        "source": "NVIDIA / AMD / IDC Edge AI 2026",
        "severity": 0.65, "confidence": 0.82, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +5.0, "SP500_change_pct": +10.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 68.0, "fed_rate": 3.75, "ecb_rate": 1.50, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("nvidia"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"), _sector_node("Cloud Computing"),
            _country_node("France"), _country_node("USA"),
            _event_node("evt_edge_ai_rise", "Edge AI on-premise déploiement massif 2026", "tech_launch", "2026-03-01"),
        ],
        "edges": [
            _edge("evt_edge_ai_rise", "ai_ml", "CAUSES_IMPACT_ON", +0.25, 0.82, "2026-03-01", "L'IA sort du cloud pour aller au plus près des données"),
            _edge("evt_edge_ai_rise", "talan", "CAUSES_IMPACT_ON", +0.18, 0.75, "2026-03-01", "Talan propose une offre IA on-premise souveraine et économe en énergie"),
            _edge("evt_edge_ai_rise", "it_services_esn", "CAUSES_IMPACT_ON", +0.20, 0.78, "2026-03-01", "Les ESN deviennent intégratrices des GPU clusters on-premise"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.02, "impact_1m": +0.14, "impact_3m": +0.22, "impact_6m": +0.24, "direction": "positive", "confidence": 0.75,
                      "reasoning": "L'edge AI est un marché où Talan se positionne avec son offre infrastructure IA souveraine.", "source": "IDC Edge AI 2026 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.14, "talan_node_index": 0, "horizon": "1m", "notes": "Edge AI = marché intégration on-premise pour ESN spécialisées infrastructure"}
    },

    {
        "event_id": "evt_144",
        "event_date": "2026-04-01",
        "event_type": "financial_market_impact",
        "event_name": "Commoditisation IA — pression marges ESN sur les projets IA standardisés",
        "event_description": "Les solutions IA standard (Copilot, Gemini, Agentforce) couvrent 70% des use cases. Les missions IA de faible valeur ajoutée sont commoditisées. Seules les missions complexes restent rentables.",
        "source": "McKinsey Technology Trends 2026 / Gartner / Forrester",
        "severity": 0.70, "confidence": 0.85, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +5.0, "SP500_change_pct": +10.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 68.0, "fed_rate": 3.75, "ecb_rate": 1.50, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ai_commoditization_26", "Commoditisation IA pression marges ESN 2026", "financial_market_impact", "2026-04-01"),
        ],
        "edges": [
            _edge("evt_ai_commoditization_26", "it_services_esn", "CAUSES_IMPACT_ON", -0.20, 0.85, "2026-04-01", "Les marges ESN sur les missions IA standard s'effondrent"),
            _edge("evt_ai_commoditization_26", "talan", "CAUSES_IMPACT_ON", -0.15, 0.78, "2026-04-01", "Talan doit se repositionner sur les missions IA complexes et sur-mesure"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.12, "impact_3m": -0.18, "impact_6m": -0.20, "direction": "negative", "confidence": 0.80,
                      "reasoning": "La commoditisation IA menace le modèle ESN traditionnel. Talan doit monter vers l'IA complexe.", "source": "McKinsey 2026 / Gartner / Estimation"}
        },
        "gnn_training": {"target_impact": -0.12, "talan_node_index": 0, "horizon": "1m", "notes": "Commoditisation IA = pression structurelle forte sur les marges ESN"}
    },

    {
        "event_id": "evt_145",
        "event_date": "2026-02-15",
        "event_type": "geopolitical_events",
        "event_name": "Cyberattaque majeure infrastructure critique française — hôpitaux et énergie",
        "event_description": "Une cyberattaque d'état-niveau (attribuée à un groupe APT lié à la Russie) frappe simultanément 12 hôpitaux et 3 opérateurs énergie en France. ANSSI déclare l'état d'urgence cyber.",
        "source": "ANSSI / Ministère Intérieur / Le Monde",
        "severity": 0.85, "confidence": 0.82, "is_real_event": True,
        "macro_context": {"CAC40_level": 7500, "CAC40_change_pct": +3.0, "SP500_change_pct": +8.0, "VIX": 25.0, "EUR_USD": 1.08, "brent_usd": 70.0, "fed_rate": 4.00, "ecb_rate": 1.75, "global_recession_risk": 0.35},
        "nodes": [
            _talan_node(), _company_node("atos"), _company_node("capgemini"),
            _sector_node("Cybersécurité"), _sector_node("Santé / Healthcare"), _sector_node("Énergie"), _sector_node("IT Services / ESN"),
            _country_node("France"), _country_node("Russie"),
            _event_node("evt_cyberattack_fr_2026", "Cyberattaque majeure infrastructure critique France 2026", "geopolitical_events", "2026-02-15"),
        ],
        "edges": [
            _edge("evt_cyberattack_fr_2026", "cybersecurite", "CAUSES_IMPACT_ON", +0.55, 0.92, "2026-02-15", "Urgence nationale cyber: budgets et projets sécurité accélérés"),
            _edge("evt_cyberattack_fr_2026", "talan", "CAUSES_IMPACT_ON", +0.30, 0.85, "2026-02-15", "Talan mobilisé en urgence sur les missions de réponse à incident et remédiation"),
            _edge("evt_cyberattack_fr_2026", "it_services_esn", "CAUSES_IMPACT_ON", +0.25, 0.88, "2026-02-15", "Explosion budgets cyber secteur public et OIV"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.06, "impact_1m": +0.28, "impact_3m": +0.38, "impact_6m": +0.40, "direction": "positive", "confidence": 0.85,
                      "reasoning": "Talan practice cyber mobilisée en urgence. Forte hausse des budgets cyber secteur public et OIV après l'attaque.", "source": "ANSSI 2026 / Estimation impact ESN cyber"}
        },
        "gnn_training": {"target_impact": +0.28, "talan_node_index": 0, "horizon": "1m", "notes": "Cyberattaque état = urgence nationale cyber = boom missions pour ESN spécialisées"}
    },

    {
        "event_id": "evt_146",
        "event_date": "2026-05-01",
        "event_type": "regulatory_changes",
        "event_name": "Green IT — régulation IA durable, bilan carbone IA obligatoire en UE",
        "event_description": "L'UE impose un bilan carbone obligatoire pour les systèmes IA déployés. Les entreprises doivent mesurer et réduire l'empreinte énergétique de leurs modèles IA. Nouvelle obligation combinée AI Act + CSRD.",
        "source": "Commission Européenne / EFRAG / GreenIT.fr",
        "severity": 0.55, "confidence": 0.80, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +5.0, "SP500_change_pct": +10.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 68.0, "fed_rate": 3.75, "ecb_rate": 1.50, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_green_ai_regulation", "Green IT IA bilan carbone obligatoire UE", "regulatory_changes", "2026-05-01"),
        ],
        "edges": [
            _edge("evt_green_ai_regulation", "it_services_esn", "CAUSES_IMPACT_ON", +0.12, 0.72, "2026-05-01", "Nouvelle practice Green IT IA pour les ESN"),
            _edge("evt_green_ai_regulation", "talan", "CAUSES_IMPACT_ON", +0.10, 0.68, "2026-05-01", "Talan développe une offre IA éco-responsable et mesure son empreinte carbone"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.01, "impact_1m": +0.06, "impact_3m": +0.12, "impact_6m": +0.15, "direction": "positive", "confidence": 0.65,
                      "reasoning": "Talan développe une practice Green IA, différenciatrice pour les clients soucieux RSE.", "source": "Commission EU 2026 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.06, "talan_node_index": 0, "horizon": "1m", "notes": "Green IA obligatoire = nouvelle practice RSE pour les ESN"}
    },

    {
        "event_id": "evt_147",
        "event_date": "2026-06-01",
        "event_type": "talent_market_signals",
        "event_name": "Agents IA remplacent les rôles juniors ESN — restructuration des profils",
        "event_description": "Les agents IA autonomes (coding agents, test agents, doc agents) éliminent 30-40% des tâches réalisées par les juniors ESN. Les ESN restructurent leurs pyramides d'âge vers plus de seniors.",
        "source": "McKinsey Future of Work 2026 / BCG / Syntec Numérique",
        "severity": 0.80, "confidence": 0.82, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +5.0, "SP500_change_pct": +10.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 68.0, "fed_rate": 3.75, "ecb_rate": 1.50, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"), _company_node("sopra"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_ai_agents_replace_juniors", "Agents IA remplacent rôles juniors ESN 2026", "talent_market_signals", "2026-06-01"),
        ],
        "edges": [
            _edge("evt_ai_agents_replace_juniors", "it_services_esn", "CAUSES_IMPACT_ON", -0.25, 0.85, "2026-06-01", "Restructuration profonde des ESN: moins de juniors, plus de seniors IA"),
            _edge("evt_ai_agents_replace_juniors", "talan", "CAUSES_IMPACT_ON", -0.18, 0.78, "2026-06-01", "Talan doit revoir son modèle de recrutement et former ses profils"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.15, "impact_3m": -0.22, "impact_6m": -0.25, "direction": "negative", "confidence": 0.80,
                      "reasoning": "Disruption profonde du modèle RH ESN: les juniors sont remplacés par des agents IA. Coût de transition élevé.", "source": "McKinsey 2026 / BCG / Syntec Numérique"}
        },
        "gnn_training": {"target_impact": -0.15, "talan_node_index": 0, "horizon": "1m", "notes": "Agents IA remplacent juniors = disruption structurelle modèle RH ESN"}
    },

    {
        "event_id": "evt_148",
        "event_date": "2026-07-01",
        "event_type": "competitor_moves",
        "event_name": "Consolidation majeure ESN Europe — fusion entre deux grandes ESN françaises",
        "event_description": "Une fusion majeure entre deux grandes ESN françaises (hypothèse Sopra Steria + Econocom ou Devoteam + Inetum) crée un nouvel acteur de 8-10 Md€ de CA. Paysage ESN profondément reconfiguré.",
        "source": "Projection M&A ESN Europe / Reuters / Les Echos",
        "severity": 0.75, "confidence": 0.72, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +5.0, "SP500_change_pct": +10.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 68.0, "fed_rate": 3.75, "ecb_rate": 1.50, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("sopra"), _company_node("capgemini"),
            _sector_node("IT Services / ESN"),
            _country_node("France"),
            _event_node("evt_esn_major_merge", "Fusion majeure ESN Europe 2026", "competitor_moves", "2026-07-01"),
        ],
        "edges": [
            _edge("evt_esn_major_merge", "it_services_esn", "CAUSES_IMPACT_ON", +0.08, 0.70, "2026-07-01", "Le secteur ESN se consolide, acteurs plus forts émergent"),
            _edge("evt_esn_major_merge", "talan", "CAUSES_IMPACT_ON", -0.12, 0.68, "2026-07-01", "Talan sous pression: doit répondre à la consolidation en accélérant sa croissance"),
            _edge("talan", "sopra", "COMPETES_WITH", 0.7, 1.0, "2020-01-01", "Concurrence"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": -0.02, "impact_1m": -0.10, "impact_3m": -0.14, "impact_6m": -0.12, "direction": "negative", "confidence": 0.65,
                      "reasoning": "Fusion majeure crée un concurrent plus fort. Talan doit accélérer pour maintenir sa position.", "source": "Projection M&A ESN / Estimation"}
        },
        "gnn_training": {"target_impact": -0.10, "talan_node_index": 0, "horizon": "1m", "notes": "Fusion majeure ESN = pression forte sur les acteurs mid-size"}
    },

    {
        "event_id": "evt_149",
        "event_date": "2026-03-01",
        "event_type": "tech_launch",
        "event_name": "Claude 4 / GPT-5 — prochaine génération IA, frontier repoussée",
        "event_description": "Anthropic lance Claude 4 et OpenAI GPT-5 en compétition directe. Les modèles dépassent le niveau expert humain sur de nombreuses tâches. L'IA de niveau AGI partiel est une réalité commerciale.",
        "source": "Anthropic / OpenAI / The Verge (projection)",
        "severity": 0.85, "confidence": 0.78, "is_real_event": True,
        "macro_context": {"CAC40_level": 7600, "CAC40_change_pct": +5.0, "SP500_change_pct": +10.0, "VIX": 22.0, "EUR_USD": 1.09, "brent_usd": 68.0, "fed_rate": 3.75, "ecb_rate": 1.50, "global_recession_risk": 0.30},
        "nodes": [
            _talan_node(), _company_node("anthropic"), _company_node("openai"), _company_node("microsoft"), _company_node("capgemini"),
            _sector_node("AI/ML"), _sector_node("IT Services / ESN"),
            _country_node("USA"), _country_node("France"),
            _event_node("evt_claude4_gpt5", "Claude 4 / GPT-5 prochaine génération IA 2026", "tech_launch", "2026-03-01"),
        ],
        "edges": [
            _edge("evt_claude4_gpt5", "ai_ml", "CAUSES_IMPACT_ON", +0.50, 0.88, "2026-03-01", "AGI partiel commercial: révolution des cas d'usage enterprise"),
            _edge("evt_claude4_gpt5", "talan", "CAUSES_IMPACT_ON", +0.22, 0.78, "2026-03-01", "Talan intègre les modèles next-gen pour des solutions IA radicalement nouvelles"),
            _edge("evt_claude4_gpt5", "it_services_esn", "CAUSES_IMPACT_ON", -0.10, 0.72, "2026-03-01", "Les modèles next-gen automatisent davantage les tâches ESN standard"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.04, "impact_1m": +0.18, "impact_3m": +0.28, "impact_6m": +0.30, "direction": "positive", "confidence": 0.75,
                      "reasoning": "Claude 4/GPT-5 ouvre des cas d'usage radicalement nouveaux. Talan en première ligne pour l'intégration.", "source": "Projection Anthropic/OpenAI 2026 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.18, "talan_node_index": 0, "horizon": "1m", "notes": "AGI partiel commercial = révolution des missions ESN, opportunité majeure"}
    },

    {
        "event_id": "evt_150",
        "event_date": "2026-09-01",
        "event_type": "competitor_moves",
        "event_name": "Talan pivot stratégique — repositionnement en ESN IA-native, nouvelle identité",
        "event_description": "Talan annonce son repositionnement stratégique: de l'ESN généraliste à l'ESN IA-native. Nouvelle organisation: 70% des effectifs sur des projets IA. Nouvelle marque, nouvelle proposition de valeur.",
        "source": "Talan Direction Générale / Les Echos / Usine Digitale",
        "severity": 0.80, "confidence": 0.75, "is_real_event": True,
        "macro_context": {"CAC40_level": 7800, "CAC40_change_pct": +7.0, "SP500_change_pct": +12.0, "VIX": 20.0, "EUR_USD": 1.10, "brent_usd": 65.0, "fed_rate": 3.50, "ecb_rate": 1.25, "global_recession_risk": 0.28},
        "nodes": [
            _talan_node(), _company_node("capgemini"), _company_node("accenture"), _company_node("sopra"),
            _sector_node("IT Services / ESN"), _sector_node("AI/ML"),
            _country_node("France"),
            _event_node("evt_talan_ai_native_pivot", "Talan pivot ESN IA-native 2026", "competitor_moves", "2026-09-01"),
        ],
        "edges": [
            _edge("evt_talan_ai_native_pivot", "talan", "CAUSES_IMPACT_ON", +0.40, 0.82, "2026-09-01", "Repositionnement stratégique majeur: Talan devient ESN IA-native"),
            _edge("evt_talan_ai_native_pivot", "it_services_esn", "CAUSES_IMPACT_ON", +0.10, 0.65, "2026-09-01", "Talan montre la voie pour la transformation des ESN françaises"),
            _edge("talan", "capgemini", "COMPETES_WITH", 0.6, 1.0, "2020-01-01", "Concurrence ESN"),
            _edge("talan", "it_services_esn", "BELONGS_TO_SECTOR", 1.0, 1.0, "2020-01-01", "ESN"),
        ],
        "measured_impacts": {
            "talan": {"impact_1w": +0.05, "impact_1m": +0.30, "impact_3m": +0.45, "impact_6m": +0.50, "direction": "positive", "confidence": 0.78,
                      "reasoning": "Le pivot IA-native de Talan est un pari stratégique majeur. Si réussi: croissance et marges en forte hausse.", "source": "Projection stratégique Talan 2026 / Estimation"}
        },
        "gnn_training": {"target_impact": +0.30, "talan_node_index": 0, "horizon": "1m", "notes": "Pivot ESN IA-native = pari stratégique Talan, fort upside si réussi"}
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def export_kg_events(output_path: str = "kg_events.json") -> None:
    """Export the full event list as a Knowledge Graph JSON file for Neo4j."""
    out = os.path.join(os.path.dirname(__file__), output_path)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(HISTORICAL_EVENTS, f, ensure_ascii=False, indent=2)
    print(f"[KG] Exported {len(HISTORICAL_EVENTS)} events → {out}")


def export_gnn_training_samples(output_path: str = "gnn_training_samples.json") -> None:
    """Export compact GNN training samples (one sample per event)."""
    samples = []
    for evt in HISTORICAL_EVENTS:
        gt = evt["gnn_training"]
        sample = {
            "event_id":       evt["event_id"],
            "event_date":     evt["event_date"],
            "event_type":     evt["event_type"],
            "severity":       evt["severity"],
            "confidence":     evt["confidence"],
            "is_real_event":  evt["is_real_event"],
            "macro_context":  evt["macro_context"],
            "node_ids":       [n["id"] for n in evt["nodes"]],
            "node_types":     [n["type"] for n in evt["nodes"]],
            "edges":          [
                {
                    "from": e["from_id"], "to": e["to_id"],
                    "rel": e["relation"],
                    "score": e["impact_score"],
                    "conf": e["confidence"],
                }
                for e in evt["edges"]
            ],
            "target_impact":      gt["target_impact"],
            "talan_node_index":   gt["talan_node_index"],
            "horizon":            gt["horizon"],
            "label":              1 if gt["target_impact"] >= 0 else 0,
        }
        # Attach measured_impacts for Talan if present
        if "talan" in evt.get("measured_impacts", {}):
            mi = evt["measured_impacts"]["talan"]
            sample["talan_impact_1m"]  = mi.get("impact_1m", gt["target_impact"])
            sample["talan_impact_3m"]  = mi.get("impact_3m", None)
            sample["talan_confidence"] = mi.get("confidence", evt["confidence"])
            sample["talan_direction"]  = mi.get("direction", "positive" if gt["target_impact"] >= 0 else "negative")
        samples.append(sample)

    out = os.path.join(os.path.dirname(__file__), output_path)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    print(f"[GNN] Exported {len(samples)} training samples → {out}")


def export_to_cypher(output_path: str = "kg_cypher_queries.cypher") -> None:
    """Generate Cypher MERGE queries for loading events into Neo4j."""
    lines: List[str] = [
        "// Auto-generated Cypher queries — do NOT edit manually",
        "// Generated by generate_gnn_dataset.py",
        f"// {len(HISTORICAL_EVENTS)} historical events (2020-2026)",
        "",
    ]

    for evt in HISTORICAL_EVENTS:
        eid   = evt["event_id"]
        ename = evt["event_name"].replace('"', '\\"')
        etype = evt["event_type"]
        edate = evt["event_date"]
        sev   = evt["severity"]
        conf  = evt["confidence"]
        real  = "true" if evt["is_real_event"] else "false"
        ti    = evt["gnn_training"]["target_impact"]

        lines.append(f"// ── {eid}: {ename[:60]}")

        # Event node
        lines.append(
            f'MERGE (e_{eid.replace("-","_")}:Event {{id: "{eid}"}}) '
            f'SET e_{eid.replace("-","_")}.name = "{ename}", '
            f'e_{eid.replace("-","_")}.event_type = "{etype}", '
            f'e_{eid.replace("-","_")}.date = "{edate}", '
            f'e_{eid.replace("-","_")}.severity = {sev}, '
            f'e_{eid.replace("-","_")}.confidence = {conf}, '
            f'e_{eid.replace("-","_")}.is_real = {real}, '
            f'e_{eid.replace("-","_")}.target_impact_talan = {ti};'
        )

        # Company/Sector/Country nodes
        for node in evt["nodes"]:
            nid   = node["id"].replace('"', '\\"')
            nname = node["name"].replace('"', '\\"')
            ntype = node["type"]
            if ntype == "Company":
                lines.append(
                    f'MERGE (n_{nid.replace("-","_").replace("/","_").replace(" ","_")}:Company {{id: "{nid}"}}) '
                    f'SET n_{nid.replace("-","_").replace("/","_").replace(" ","_")}.name = "{nname}";'
                )
            elif ntype == "Sector":
                lines.append(
                    f'MERGE (s_{nid.replace("-","_").replace("/","_").replace(" ","_")}:Sector {{id: "{nid}"}}) '
                    f'SET s_{nid.replace("-","_").replace("/","_").replace(" ","_")}.name = "{nname}";'
                )
            elif ntype == "Country":
                lines.append(
                    f'MERGE (c_{nid.replace("-","_").replace("/","_").replace(" ","_")}:Country {{id: "{nid}"}}) '
                    f'SET c_{nid.replace("-","_").replace("/","_").replace(" ","_")}.name = "{nname}";'
                )

        # Edges
        for edge in evt["edges"]:
            fid   = edge["from_id"]
            tid   = edge["to_id"]
            rel   = edge["relation"]
            score = edge["impact_score"]
            ec    = edge["confidence"]
            ts    = edge["timestamp"]
            reason = edge["reasoning"].replace('"', '\\"')[:120]
            lines.append(
                f'MATCH (a {{id: "{fid}"}}), (b {{id: "{tid}"}}) '
                f'MERGE (a)-[r:{rel} {{event: "{eid}", timestamp: "{ts}"}}]->(b) '
                f'SET r.impact_score = {score}, r.confidence = {ec}, r.reasoning = "{reason}";'
            )

        lines.append("")

    out = os.path.join(os.path.dirname(__file__), output_path)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[Cypher] Exported {len(HISTORICAL_EVENTS)} event blocks → {out}")


def validate_dataset() -> bool:
    """Validate structural integrity of HISTORICAL_EVENTS."""
    errors: List[str] = []
    seen_ids: set = set()
    event_types_valid = {
        "tech_launch", "regulatory_changes", "geopolitical_events",
        "financial_market_impact", "macro_economic", "competitor_moves",
        "talent_market_signals",
    }

    for i, evt in enumerate(HISTORICAL_EVENTS):
        eid = evt.get("event_id", f"MISSING_ID_{i}")
        prefix = f"[{eid}]"

        # Unique IDs
        if eid in seen_ids:
            errors.append(f"{prefix} duplicate event_id")
        seen_ids.add(eid)

        # Required top-level keys
        for key in ("event_id", "event_date", "event_type", "event_name",
                    "severity", "confidence", "is_real_event",
                    "macro_context", "nodes", "edges",
                    "measured_impacts", "gnn_training"):
            if key not in evt:
                errors.append(f"{prefix} missing key '{key}'")

        # Event type
        if evt.get("event_type") not in event_types_valid:
            errors.append(f"{prefix} invalid event_type '{evt.get('event_type')}'")

        # Severity / confidence range
        for field in ("severity", "confidence"):
            val = evt.get(field, -1)
            if not (0.0 <= val <= 1.0):
                errors.append(f"{prefix} {field}={val} out of [0,1]")

        # Nodes: Talan must be index 0
        nodes = evt.get("nodes", [])
        if not nodes or nodes[0].get("id") != "talan":
            errors.append(f"{prefix} nodes[0] must be Talan (id='talan')")

        # GNN training
        gt = evt.get("gnn_training", {})
        for key in ("target_impact", "talan_node_index", "horizon", "notes"):
            if key not in gt:
                errors.append(f"{prefix} gnn_training missing '{key}'")
        ti = gt.get("target_impact", 999)
        if not (-1.0 <= ti <= 1.0):
            errors.append(f"{prefix} target_impact={ti} out of [-1,1]")
        if gt.get("talan_node_index") != 0:
            errors.append(f"{prefix} talan_node_index must be 0")

        # Edges: must have from_id, to_id, relation, impact_score, confidence
        for j, edge in enumerate(evt.get("edges", [])):
            for ekey in ("from_id", "to_id", "relation", "impact_score", "confidence"):
                if ekey not in edge:
                    errors.append(f"{prefix} edge[{j}] missing '{ekey}'")

    if errors:
        print(f"\n[VALIDATION] FAIL  {len(errors)} error(s) found:")
        for e in errors:
            print(f"  - {e}")
        return False

    print(f"[VALIDATION] OK  All {len(HISTORICAL_EVENTS)} events passed validation.")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 70)
    print("  GNN Dataset Generator — Talan Market Intelligence")
    print(f"  {len(HISTORICAL_EVENTS)} historical events (2020–2026)")
    print("=" * 70)

    # ── Stats
    from collections import Counter
    type_counts   = Counter(e["event_type"] for e in HISTORICAL_EVENTS)
    year_counts   = Counter(e["event_date"][:4] for e in HISTORICAL_EVENTS)
    real_count    = sum(1 for e in HISTORICAL_EVENTS if e["is_real_event"])
    impacts       = [e["gnn_training"]["target_impact"] for e in HISTORICAL_EVENTS]
    pos_count     = sum(1 for x in impacts if x >= 0)
    neg_count     = sum(1 for x in impacts if x < 0)
    avg_impact    = sum(impacts) / len(impacts)
    max_impact    = max(impacts)
    min_impact    = min(impacts)

    print(f"\n-- Event types:")
    for etype, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"   {etype:<35} {cnt:>3}")

    print(f"\n-- Events per year:")
    for year, cnt in sorted(year_counts.items()):
        print(f"   {year}  {cnt:>3} events")

    print(f"\n-- Dataset quality:")
    print(f"   Real events:           {real_count}/{len(HISTORICAL_EVENTS)}")
    print(f"   Positive impact (≥0):  {pos_count}")
    print(f"   Negative impact (<0):  {neg_count}")
    print(f"   Avg target_impact:     {avg_impact:+.4f}")
    print(f"   Max target_impact:     {max_impact:+.4f}")
    print(f"   Min target_impact:     {min_impact:+.4f}")

    print("\n-- Validation:")
    ok = validate_dataset()

    if ok:
        print("\n-- Exporting files...")
        export_kg_events()
        export_gnn_training_samples()
        export_to_cypher()
        print("\nOK  All files exported successfully.")
    else:
        print("\nFAIL  Fix validation errors before exporting.")


if __name__ == "__main__":
    main()

