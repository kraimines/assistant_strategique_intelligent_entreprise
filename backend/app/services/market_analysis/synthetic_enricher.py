"""SyntheticEnricher v3 — 15 event categories, realistic 4-hop chains.

Architecture (BFS max_hops=4 compatible):
  Entity --strong--> Mechanism1 ---> Mechanism2 ---> TalanExposure --DEPENDS_ON--> Talan
  BFS from Mechanism1 = 3 hops to Talan ✓ (fits max_hops=4)

Chain format per template:
  Event → Economic Mechanism → Business Effect → Sector Effect → Talan
condensed into 3 synthetic nodes so BFS fits within max_hops.

Each event category has a NEGATIVE and a POSITIVE scenario to capture
both risk and opportunity propagation.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Edge semantic weights ─────────────────────────────────────────────────────

EDGE_SEMANTIC_WEIGHTS: Dict[str, float] = {
    "IMPACTS":           1.00, "CAUSES_IMPACT_ON": 1.00,
    "DEPENDS_ON":        0.90, "REGULATES":        0.90,
    "SUPPLY_CHAIN_LINK": 0.80, "SUPPLIES":         0.80,
    "INVESTS_IN":        0.75, "COMPETES_WITH":    0.70,
    "INFLUENCES":        0.65, "TRIGGERS_EVENT":   0.65,
    "AFFECTS_INDICATOR": 0.60, "OPERATES_IN":      0.60,
    "BELONGS_TO_SECTOR": 0.60, "SERVES_SECTOR":    0.60,
    "DRIVES":            0.85, "ENABLES":          0.75,
    "ACCELERATES":       0.70, "GENERATES":        0.70,
    "SLOWS":             0.70, "DELAYS":           0.65,
    "RESTRICTS":         0.75, "FREEZES":          0.70,
    "REDUCES":           0.70, "INCREASES":        0.70,
    "CORRELATED_WITH":   0.40, "MENTIONS":         0.15,
    "ACQUIRED":          0.85, "LAUNCHED":         0.70,
    "RECRUITS_IN":       0.50,
}

TEMPORAL_HALF_LIVES: Dict[str, float] = {
    "news": 3.0, "event": 14.0, "regulation": 90.0,
    "macro": 180.0, "macroindicator": 180.0,
    "sector": 365.0, "company": 30.0, "competitor": 30.0,
    "technology": 60.0, "person": 14.0, "country": 180.0,
}


def temporal_decay(days_old: float, entity_type: str) -> float:
    hl = TEMPORAL_HALF_LIVES.get(entity_type.lower(), 30.0)
    return math.exp(-math.log(2) / max(hl, 1.0) * max(days_old, 0.0))


def _sid(name: str) -> str:
    return "synth_" + hashlib.md5(name.lower().encode()).hexdigest()[:10]


# ── Talan exposure nodes (structural layer → Talan) ───────────────────────────

TALAN_EXPOSURE: List[Tuple[str, str, float]] = [
    ("AI Consulting Demand",         "Sector",         0.95),
    ("Digital Transformation",       "Sector",         0.90),
    ("Enterprise IT Services",       "Sector",         0.90),
    ("Cloud Services Spending",      "Sector",         0.85),
    ("Financial Services IT",        "Sector",         0.85),
    ("Public Sector IT",             "Sector",         0.80),
    ("Cybersecurity Demand",         "Sector",         0.80),
    ("Data Engineering",             "Sector",         0.85),
    ("EU Digital Transformation",    "MacroIndicator", 0.90),
    ("European IT Market",           "MacroIndicator", 0.85),
    ("French IT Market",             "MacroIndicator", 0.95),
    ("GenAI Adoption",               "MarketTrend",    0.90),
    ("Banking IT Budgets",           "MacroIndicator", 0.80),
    ("Insurance IT Spending",        "MacroIndicator", 0.75),
    ("Consulting Demand",            "Sector",         0.90),
    ("IT Consulting Market",         "Sector",         0.90),
    ("Enterprise AI Adoption",       "MarketTrend",    0.88),
    ("AI Infrastructure Spending",   "MacroIndicator", 0.82),
    ("Cybersecurity Compliance",     "Sector",         0.78),
    ("Enterprise Innovation Budget", "MacroIndicator", 0.85),
]

# ── Propagation templates ─────────────────────────────────────────────────────
# Structure:
#   trigger_patterns: substring matches (lowercased)
#   trigger_types: entity type matches
#   scenarios: list of (sign, chain, talan_exposure_name)
#     chain: [(node_name, node_type, edge_type, impact_score), ...]
#     last chain node connects to talan_exposure_name via DRIVES/DEPENDS_ON

ChainNode = Tuple[str, str, str, float]   # name, type, edge_from_prev, impact
Scenario  = Tuple[float, List[ChainNode], str]  # sign, chain, target_exposure

_TEMPLATES: List[Tuple[List[str], List[str], List[Scenario]]] = [

    # ═══════════════════════════════════════════════════════════════════════════
    # REGULATORY EVENTS: Central bank decisions, interest rates, compliance laws
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 1. Interest Rate Decisions (ECB/Fed) ──────────────────────────────────
    # CHAIN: Rate ↑ → Corporate capex squeeze → IT budget cuts → Consulting slowdown
    # CHAIN: Rate ↓ → Cheap financing → Investment acceleration → Consulting surge
    (
        ["interest rate", "ecb rate", "fed rate", "rate decision", "rate hike",
         "rate cut", "monetary policy", "fed chairman", "lagarde", "powell",
         "central bank", "rate policy", "inflation target"],
        ["macro_indicator", "regulation", "event", "person"],
        [
            # NEGATIVE: rate hikes → capex squeeze (2 hops)
            (-1.0, [
                ("Financing Cost Surge",          "MacroIndicator", "RESTRICTS",    -0.85),
                ("Enterprise IT Budget Cuts",     "MacroIndicator", "REDUCES",      -0.82),
            ], "Enterprise Innovation Budget"),
            # POSITIVE: rate cuts → investment surge (2 hops)
            (+1.0, [
                ("Financing Cost Relief",         "MacroIndicator", "ENABLES",      +0.85),
                ("Digital Transformation Budgets","MarketTrend",    "DRIVES",       +0.85),
            ], "Enterprise Innovation Budget"),
        ],
    ),

    # ── 2. Regulatory Compliance (AI Act, DORA, NIS2, GDPR) ─────────────────
    # CHAIN: New regulation → Compliance requirement surge → Audit/governance projects → Consulting contracts
    (
        ["eu ai act", "ai act", "dora", "nis2", "gdpr", "data protection",
         "regulatory compliance", "eu regulation", "european regulation",
         "compliance deadline", "compliance requirement", "regulation enforcement"],
        ["regulation", "event"],  # keyword-match only — avoids triggering on every country
        [
            # POSITIVE: regulation → compliance consulting boom (2 hops)
            (+1.0, [
                ("Compliance Audit Requirements", "Regulation", "REGULATES",   +0.90),
                ("Enterprise Compliance Consulting", "Sector",  "GENERATES",   +0.95),
            ], "Cybersecurity Compliance"),
            # POSITIVE: security certifications (2 hops)
            (+1.0, [
                ("Security Audit Mandates",        "Regulation", "REGULATES",  +0.85),
                ("Security Implementation Services","Sector",    "GENERATES",  +0.90),
            ], "Cybersecurity Demand"),
        ],
    ),

    # ── 3. Tax Policy / Labor Law Changes ────────────────────────────────────
    # CHAIN: Tax/labor rule change → HR/payroll systems overhaul → IT project surge
    (
        ["tax reform", "labor law", "payroll regulation", "employment law",
         "minimum wage", "tax code", "labor regulation", "social security",
         "payroll system", "hr compliance", "tax compliance"],
        ["regulation", "event"],  # not "country" — would match all countries
        [
            # POSITIVE: law change → system upgrade demand (2 hops)
            (+1.0, [
                ("HR/Payroll Compliance Mandate",     "Regulation", "REGULATES", +0.80),
                ("HR Technology Consulting",          "Sector",     "GENERATES", +0.85),
            ], "Enterprise IT Services"),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GEOPOLITICAL EVENTS: Trade, sanctions, conflicts, supply chain disruptions
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 4. US-China Trade Relations & Tariffs ────────────────────────────────
    # CHAIN: Trade tension ↑ → Semiconductor export restriction → AI hardware shortage → IT project delays
    # CHAIN: Trade stabilization → Chip availability → Enterprise AI acceleration → Consulting surge
    (
        ["us-china", "trade war", "tariff", "trade tension", "trump-xi",
         "trade stabilization", "trade truce", "china trade", "semiconductor export",
         "tech export control", "beijing summit"],
        ["event", "person", "macro_indicator"],  # keyword-only match for specific trade events
        [
            # NEGATIVE: trade tensions (2 hops)
            (-1.0, [
                ("Semiconductor Export Restrictions", "Regulation",     "RESTRICTS",  -0.88),
                ("Enterprise AI Project Delays",      "MarketTrend",    "REDUCES",    -0.85),
            ], "AI Consulting Demand"),
            # POSITIVE: trade stabilization (2 hops)
            (+1.0, [
                ("AI Chip Supply Recovery",            "MacroIndicator", "ENABLES",    +0.85),
                ("GenAI Integration Consulting Surge", "Sector",         "GENERATES",  +0.92),
            ], "AI Consulting Demand"),
        ],
    ),

    # ── 5. Geopolitical Conflict & Sanctions ─────────────────────────────────
    # CHAIN: Conflict/war → Supply chain disruption → Cost inflation → IT budget freeze
    # CHAIN: Conflict resolution → Confidence return → Investment acceleration
    (
        ["war", "conflict", "sanction", "military", "geopolitical crisis",
         "ukraine", "taiwan", "middle east", "russia invasion", "military tension",
         "sanctions regime", "trade embargo"],
        ["event", "country", "region"],
        [
            # NEGATIVE: conflict/war (2 hops)
            (-1.0, [
                ("Geopolitical Risk Premium Rise",    "MacroIndicator", "REDUCES",    -0.82),
                ("Enterprise Investment Freeze",      "MacroIndicator", "DELAYS",     -0.85),
            ], "European IT Market"),
            # POSITIVE: stabilization (2 hops)
            (+1.0, [
                ("Supply Chain Confidence Recovery",  "MacroIndicator", "ENABLES",    +0.75),
                ("Digital Infrastructure Investment", "Sector",         "GENERATES",  +0.80),
            ], "Digital Transformation"),
        ],
    ),

    # ── 6. Oil & Commodity Shocks ────────────────────────────────────────────
    # CHAIN: Oil shock ↑ → Inflation surge → Interest rate stays high → Corporate capex cuts → IT freeze
    # CHAIN: Oil stabilization → Inflation relief → Investment appetite returns
    (
        ["oil shock", "oil price surge", "opec", "energy crisis", "oil supply",
         "commodity shock", "energy prices", "barrel price", "fuel prices"],
        ["event", "macro_indicator", "country"],
        [
            # NEGATIVE: oil shock (2 hops)
            (-1.0, [
                ("Oil-Driven Cost Inflation",         "MacroIndicator", "REDUCES",    -0.85),
                ("IT Innovation Budget Freeze",       "MacroIndicator", "DELAYS",     -0.88),
            ], "Enterprise Innovation Budget"),
            # POSITIVE: energy stabilization (2 hops)
            (+1.0, [
                ("Energy Price Stabilization",        "MacroIndicator", "ENABLES",    +0.75),
                ("Enterprise Investment Resumption",  "Sector",         "DRIVES",     +0.80),
            ], "Digital Transformation"),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # MACRO / FINANCIAL EVENTS: Inflation, stock crashes, economic cycles
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 7. Inflation & Cost of Living Crisis ──────────────────────────────────
    # CHAIN: Inflation ↑ → Margin compression → Discretionary spending cuts → IT/consulting pullback
    # CHAIN: Inflation ↓ → Margin recovery → Enterprise optimization → AI/automation consulting surge
    (
        ["inflation", "price increase", "cost of living", "cost inflation",
         "margin compression", "cost spiral", "wage inflation", "price spiral"],
        ["macro_indicator", "event"],
        [
            # NEGATIVE: inflation → IT freeze (2 hops)
            (-1.0, [
                ("Enterprise Margin Compression",     "MacroIndicator", "REDUCES",    -0.80),
                ("Discretionary IT Budget Freeze",    "MacroIndicator", "DELAYS",     -0.82),
            ], "IT Consulting Market"),
            # POSITIVE: optimization demand (2 hops)
            (+1.0, [
                ("Cost Optimization Mandate",         "MacroIndicator", "DRIVES",     +0.75),
                ("Efficiency-Focused AI Consulting",  "Sector",         "GENERATES",  +0.82),
            ], "AI Consulting Demand"),
        ],
    ),

    # ── 8. Stock Market Crash / Correction ───────────────────────────────────
    # CHAIN: Market crash → Investor panic → CFO caution → IT budget freeze
    # CHAIN: Market recovery → Confidence surge → Digital investment acceleration
    (
        ["stock market crash", "market correction", "bear market", "stock decline",
         "market plunge", "nasdaq decline", "s&p 500 decline", "market downturn",
         "equity market", "market volatility"],
        ["macro_indicator", "event"],
        [
            # NEGATIVE: market crash (2 hops)
            (-1.0, [
                ("Investor Confidence Collapse",      "MacroIndicator", "REDUCES",    -0.85),
                ("Enterprise IT Budget Contraction",  "Sector",         "IMPACTS",    -0.80),
            ], "Enterprise IT Services"),
            # POSITIVE: market recovery (2 hops)
            (+1.0, [
                ("Investor Confidence Recovery",      "MacroIndicator", "DRIVES",     +0.80),
                ("Digital Transformation Pipeline",   "Sector",         "GENERATES",  +0.85),
            ], "Digital Transformation"),
        ],
    ),

    # ── 9. Banking / Credit Crises ───────────────────────────────────────────
    # CHAIN: Banking crisis → Credit tightens → Corporate capex cut → IT stalls
    # CHAIN: Banking stability → Credit access → Enterprise capex acceleration
    (
        ["banking crisis", "credit crunch", "bank failure", "credit freeze",
         "lending freeze", "banking stress", "credit tightening"],
        ["event", "macro_indicator"],
        [
            # NEGATIVE: credit crisis (2 hops)
            (-1.0, [
                ("Credit Market Tightening",          "MacroIndicator", "RESTRICTS",  -0.85),
                ("IT Project Funding Deferrals",      "Sector",         "DELAYS",     -0.82),
            ], "Enterprise Innovation Budget"),
            # POSITIVE: credit recovery (2 hops)
            (+1.0, [
                ("Credit Market Normalization",       "MacroIndicator", "ENABLES",    +0.80),
                ("Digital Infrastructure Projects",   "Sector",         "GENERATES",  +0.82),
            ], "Enterprise IT Services"),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # TECH / AI DISRUPTION: Breakthroughs, new tools, platform shifts
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 10. AI Breakthroughs & GenAI Wave ─────────────────────────────────────
    # CHAIN: AI breakthrough → Hype/capability surge → Enterprise AI budget allocation → Consulting boom
    (
        ["ai breakthrough", "genai", "large language model", "llm", "ai advancement",
         "generative ai", "ai capability", "ai model", "ai innovation",
         "machine learning", "neural network", "transformer", "ai training"],
        ["technology", "market_trend", "event"],
        [
            # POSITIVE: AI breakthrough (2 hops)
            (+1.0, [
                ("Enterprise AI Budget Surge",          "MarketTrend",  "DRIVES",     +0.90),
                ("AI Strategy & Integration Consulting","Sector",       "GENERATES",  +0.95),
            ], "AI Consulting Demand"),
            # POSITIVE: migration wave (2 hops)
            (+1.0, [
                ("Legacy Modernization Mandate",        "MarketTrend",  "DRIVES",     +0.85),
                ("Migration & Transformation Services", "Sector",       "GENERATES",  +0.90),
            ], "Digital Transformation"),
        ],
    ),

    # ── 11. Cloud Platform Evolution / AWS/Azure/GCP Shifts ──────────────────
    # CHAIN: New cloud feature/pricing → Migration opportunity → Multi-cloud consulting demand
    (
        ["cloud migration", "aws", "azure", "gcp", "google cloud",
         "cloud computing", "cloud platform", "multi-cloud", "cloud strategy",
         "cloud infrastructure", "cloud modernization"],
        ["technology", "company", "market_trend"],
        [
            # POSITIVE: cloud shift (2 hops)
            (+1.0, [
                ("Enterprise Cloud Modernization",    "MarketTrend",    "DRIVES",     +0.83),
                ("Cloud Architecture & Migration",    "Sector",         "GENERATES",  +0.88),
            ], "Cloud Services Spending"),
        ],
    ),

    # ── 12. Cybersecurity Threat Landscape Evolution ──────────────────────────
    # CHAIN: Major vulnerability/exploit → Urgency spike → Security audit surge
    (
        ["cybersecurity", "zero-day", "vulnerability", "cyberattack", "breach",
         "ransomware", "data breach", "security threat", "exploit", "malware"],
        ["event", "technology", "regulation"],
        [
            # POSITIVE: security threat → audit surge (2 hops)
            (+1.0, [
                ("Enterprise Security Urgency Rise",   "MacroIndicator", "DRIVES",    +0.88),
                ("Security Compliance Services",       "Sector",         "GENERATES", +0.93),
            ], "Cybersecurity Demand"),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # COMPETITIVE DYNAMICS: M&A, competitor wins, market consolidation
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 13. Mergers & Acquisitions / Market Consolidation ────────────────────
    # CHAIN: Major M&A → Integration projects → IT transformation consulting boom
    (
        ["merger", "acquisition", "m&a", "acquired", "takeover", "consolidation",
         "private equity", "pe buyout", "acquisition completed", "merger deal"],
        ["event", "company"],
        [
            # POSITIVE: M&A → integration (2 hops)
            (+1.0, [
                ("Enterprise Integration Projects",     "MarketTrend",  "DRIVES",    +0.88),
                ("Integration & Transformation Consulting","Sector",    "GENERATES", +0.90),
            ], "Enterprise IT Services"),
        ],
    ),

    # ── 14. Competitor Wins / Market Share Loss ──────────────────────────────
    # CHAIN: Competitor wins big contract → Lost revenue → Margin pressure → Efficiency drive → Automation consulting
    (
        ["competitor win", "market share loss", "lost contract", "contract loss",
         "competitive threat", "competitor success", "market pressure", "competitive challenge"],
        ["event", "company"],
        [
            # POSITIVE: competitive pressure → automation (2 hops)
            (+1.0, [
                ("Margin Protection Initiative",       "MarketTrend",    "DRIVES",    +0.78),
                ("Process Automation Consulting",      "Sector",         "GENERATES", +0.85),
            ], "AI Consulting Demand"),
        ],
    ),

    # ── 15. Industry Price Wars / Competitive Pressure ──────────────────────
    # CHAIN: Industry pricing collapse → Margin squeeze → Efficiency investments → IT optimization consulting
    (
        ["price war", "pricing pressure", "competitive pressure", "margin squeeze",
         "pricing collapse", "competitive intensity", "price competition"],
        ["event", "macro_indicator"],
        [
            # POSITIVE: pricing pressure → automation (2 hops)
            (+1.0, [
                ("Cost Per Unit Reduction Mandate",    "MacroIndicator", "DRIVES",    +0.75),
                ("Automation & AI Optimization",       "Sector",         "GENERATES", +0.82),
            ], "AI Consulting Demand"),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # TALENT / LABOR EVENTS: Hiring freezes, layoffs, skills shortages
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 16. Tech Layoffs / Hiring Freeze ────────────────────────────────────
    # CHAIN: Layoffs ↑ → Talent supply ↑ + hiring costs ↓ → Margin expansion → Growth initiatives resume
    # CHAIN: But also: talent loss → retention pressure → compensation/benefits IT systems upgrade
    (
        ["layoff", "hiring freeze", "workforce reduction", "job cut", "attrition",
         "tech layoff", "talent exodus", "mass termination", "rif", "severance"],
        ["event"],
        [
            # POSITIVE: layoffs → talent surplus → growth resumes (2 hops)
            (+1.0, [
                ("Hiring Cost Reduction",              "MacroIndicator", "ENABLES",   +0.68),
                ("Growth Initiative Reactivation",     "Sector",         "DRIVES",    +0.70),
            ], "Enterprise Innovation Budget"),
            # POSITIVE: retention pressure → HR IT upgrade (2 hops)
            (+1.0, [
                ("Employee Retention Urgency Rise",    "MacroIndicator", "DRIVES",    +0.72),
                ("HR Technology & Analytics Services", "Sector",         "GENERATES", +0.78),
            ], "Enterprise IT Services"),
        ],
    ),

    # ── 17. Tech Skills Shortage / Talent War ──────────────────────────────────
    # CHAIN: Skills shortage → Hiring costs ↑ → Margin pressure → Automation/outsourcing → Consulting surge
    (
        ["skills shortage", "talent shortage", "hiring difficulty", "talent gap",
         "engineer shortage", "recruitment challenge", "talent war", "compensation pressure"],
        ["event", "macro_indicator"],
        [
            # POSITIVE: talent shortage → automation demand (2 hops)
            (+1.0, [
                ("Salary Escalation Pressure",         "MacroIndicator", "DRIVES",    +0.70),
                ("Staffing Efficiency Consulting",     "Sector",         "GENERATES", +0.78),
            ], "AI Consulting Demand"),
        ],
    ),

    # ── 18. Digital Skills Training Investment ──────────────────────────────
    # CHAIN: Reskilling need → Training investment → Digital literacy programs → IT consulting
    (
        ["reskilling", "training", "skill development", "upskilling",
         "digital literacy", "staff training", "capability building"],
        ["event", "market_trend"],
        [
            # POSITIVE: reskilling → IT consulting (2 hops)
            (+1.0, [
                ("Digital Skills Investment Surge",    "MarketTrend",    "DRIVES",    +0.72),
                ("Digital Training & Development Services","Sector",     "GENERATES", +0.75),
            ], "Enterprise IT Services"),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # ADDITIONAL CORE SCENARIOS (keeping proven winners)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── 19. NVIDIA / AI Hardware Availability ─────────────────────────────────
    (
        ["nvidia", "h200", "gpu", "ai chip", "semiconductor", "h100", "blackwell",
         "chip availability", "gpu shortage", "compute availability"],
        ["company", "technology"],
        [
            # POSITIVE: chip availability (2 hops)
            (+1.0, [
                ("GenAI Project Acceleration",          "MarketTrend",    "DRIVES",      +0.90),
                ("AI Integration & Consulting",         "Sector",         "GENERATES",   +0.95),
            ], "AI Consulting Demand"),
            # NEGATIVE: scarcity (2 hops)
            (-1.0, [
                ("AI Compute Scarcity Crisis",          "MacroIndicator", "SLOWS",       -0.82),
                ("Consulting Pipeline Slowdown",        "Sector",         "IMPACTS",     -0.75),
            ], "AI Consulting Demand"),
        ],
    ),

    # ── 20. Banking & Financial Services Sector ──────────────────────────────
    (
        ["bank", "banking", "fintech", "insurance", "axa", "bnp", "credit agricole",
         "wealth management", "payment", "asset management"],
        ["company", "sector"],
        [
            # POSITIVE: banking digital transformation (2 hops)
            (+1.0, [
                ("Banking AI & Digital Modernization",  "MarketTrend",    "DRIVES",      +0.85),
                ("Banking Consulting Contracts",        "Sector",         "GENERATES",   +0.88),
            ], "Banking IT Budgets"),
            # NEGATIVE: banking sector weakness (2 hops)
            (-1.0, [
                ("Banking Margin Pressure",             "MacroIndicator", "REDUCES",     -0.78),
                ("Financial Services Consulting Decline","Sector",        "IMPACTS",     -0.72),
            ], "Financial Services IT"),
        ],
    ),

    # ── 21. Public Sector Digitalization ─────────────────────────────────────
    (
        ["government", "public sector", "france", "french government",
         "digitalization plan", "government modernization", "public service",
         "ministry", "administration", "state agency"],
        ["event", "regulation"],  # keyword-only to avoid triggering on all countries
        [
            # POSITIVE: government digital programs (2 hops)
            (+1.0, [
                ("Public Sector Digitalization Wave",    "MarketTrend",   "DRIVES",     +0.90),
                ("Public Cloud & Integration Services",  "Sector",        "GENERATES",  +0.85),
            ], "Public Sector IT"),
        ],
    ),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_edge(edges: List[Dict], src: str, dst: str, etype: str) -> bool:
    return any(
        str(e.get("from")) == src and str(e.get("to")) == dst and e.get("type") == etype
        for e in edges
    )


def _make_edge(src, dst, etype, impact, confidence, reason, horizon, half_life) -> Dict:
    sem_w = EDGE_SEMANTIC_WEIGHTS.get(etype, 0.50)
    return {
        "from": src, "to": dst, "type": etype,
        "impact_score": round(float(impact), 4),
        "confidence": confidence, "causality_score": sem_w,
        "reason": reason, "time_horizon": horizon,
        "relation_strength": sem_w, "synthetic": True,
        "half_life_days": float(half_life),
    }


def _match_templates(entity: Dict[str, Any]) -> List[Tuple[float, List[ChainNode], str]]:
    name  = (entity.get("name") or "").lower()
    etype = (entity.get("type") or (entity.get("labels") or [""])[0]).lower()
    result: List[Tuple[float, List[ChainNode], str]] = []
    seen_chain_names: set = set()
    for name_pats, type_pats, scenarios in _TEMPLATES:
        if any(p in name for p in name_pats) or etype in type_pats:
            for sign, chain, target in scenarios:
                chain_key = chain[0][0] if chain else ""
                if chain_key and chain_key not in seen_chain_names:
                    result.append((sign, chain, target))
                    seen_chain_names.add(chain_key)
    return result


# ── Main enricher ─────────────────────────────────────────────────────────────

class SyntheticEnricher:
    """
    Injects economic mechanism chains into the KG snapshot.

    BFS-compatible path structure (max_hops=4):
      Entity --strong--> Mech1(source) ---> Mech2 ---> TalanExposure --DEPENDS_ON--> Talan
      BFS from Mech1 = 3 hops ✓
    """

    def enrich(
        self,
        snapshot: Dict[str, Any],
        extracted_entities: Optional[List[Dict[str, Any]]] = None,
        published_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        import copy
        snapshot = copy.deepcopy(snapshot)
        nodes: List[Dict] = snapshot.get("nodes") or []
        edges: List[Dict] = snapshot.get("edges") or []
        node_map: Dict[str, Dict] = {str(n.get("id", n.get("name", ""))): n for n in nodes}
        # Name→node lookup so we can reuse existing nodes instead of creating duplicates
        node_name_map: Dict[str, Dict] = {n.get("name", ""): n for n in nodes if n.get("name")}

        # ── 1. Find Talan ────────────────────────────────────────────────────
        talan_node = next((n for n in nodes if n.get("name", "").lower() == "talan"), None)
        if not talan_node:
            logger.warning("SyntheticEnricher: Talan not found — skipping")
            return snapshot
        talan_id = str(talan_node.get("id", "talan"))

        # ── 2. Add Talan exposure profile ────────────────────────────────────
        exposure_ids: Dict[str, str] = {}
        for exp_name, exp_type, weight in TALAN_EXPOSURE:
            nid = _sid(exp_name)
            exposure_ids[exp_name] = nid
            if nid not in node_map:
                n = {"id": nid, "name": exp_name, "labels": [exp_type], "slug": nid,
                     "ticker": None, "properties": {"synthetic": True, "exposure_weight": weight}}
                nodes.append(n); node_map[nid] = n; node_name_map[exp_name] = n
            if not _has_edge(edges, nid, talan_id, "DEPENDS_ON"):
                edges.append(_make_edge(nid, talan_id, "DEPENDS_ON", weight, 0.90,
                    f"Talan revenue depends on {exp_name}", "long-term", 365.0))

        # ── 3. Per-entity mechanism injection ───────────────────────────────
        added_n = added_e = 0
        processed_entities = extracted_entities or []

        # Include snapshot entities too
        for sn in nodes:
            if not sn.get("properties", {}).get("synthetic") and sn.get("name","").lower() != "talan":
                processed_entities = processed_entities + [{
                    "name":  sn.get("name", ""),
                    "type":  (sn.get("labels") or ["Company"])[0].lower(),
                    "id":    str(sn.get("id", sn.get("name", ""))),
                }]

        # De-duplicate processed_entities by name so we don't inject the same chain twice
        seen_entity_names: set = set()
        deduped_entities: List[Dict[str, Any]] = []
        for ent in processed_entities:
            nm = (ent.get("name") or "").lower()
            if nm and nm not in seen_entity_names:
                seen_entity_names.add(nm)
                deduped_entities.append(ent)

        for entity in deduped_entities:
            if entity.get("name", "").lower() == "talan":
                continue
            entity_id = str(entity.get("id", entity.get("name", "")))

            # If the entity is not in the current snapshot by ID, try to find
            # an existing node by name (to avoid creating duplicate nodes that
            # cause self-loops in BFS). Only create a new node if truly absent.
            if entity_id not in node_map:
                ename = entity.get("name", "")
                # Try to resolve by name — prefer reusing an existing node ID
                existing_by_name = node_name_map.get(ename)
                if existing_by_name:
                    # Redirect entity_id to the existing node's real ID
                    entity_id = str(existing_by_name.get("id", existing_by_name.get("name", "")))
                else:
                    etype_raw = (entity.get("type") or "company").lower()
                    label_map = {
                        "company": "Company", "competitor": "Competitor",
                        "technology": "Technology", "regulation": "Regulation",
                        "person": "Person", "sector": "Sector", "country": "Country",
                        "event": "Event", "market_trend": "MarketTrend",
                        "markettrend": "MarketTrend", "macro_indicator": "MacroIndicator",
                        "macroindicator": "MacroIndicator", "news": "News",
                    }
                    label = label_map.get(etype_raw, "Company")
                    new_node = {
                        "id": entity_id, "name": ename, "labels": [label],
                        "slug": entity_id, "ticker": None,
                        "properties": {"synthetic": False, "from_analysis": True},
                    }
                    nodes.append(new_node)
                    node_map[entity_id] = new_node
                    node_name_map[ename] = new_node
                    added_n += 1

            scenarios = _match_templates(entity)
            for sign, chain, target_exposure in scenarios[:2]:
                if not chain:
                    continue

                target_id = exposure_ids.get(target_exposure, talan_id)
                hl_node = TEMPORAL_HALF_LIVES.get(chain[0][1].lower(), 30.0)

                # Build chain nodes
                prev_id = entity_id
                chain_node_ids: List[str] = []
                for node_name, node_type, edge_type, impact in chain:
                    nid = _sid(node_name)
                    chain_node_ids.append(nid)
                    if nid not in node_map:
                        nn = {"id": nid, "name": node_name, "labels": [node_type],
                              "slug": nid, "ticker": None,
                              "properties": {"synthetic": True,
                                             "description": f"Economic mechanism: {node_name}",
                                             "sign": sign}}
                        nodes.append(nn); node_map[nid] = nn; added_n += 1

                    sem_w = EDGE_SEMANTIC_WEIGHTS.get(edge_type, 0.60)
                    eff_impact = sign * abs(impact) * sem_w
                    if not _has_edge(edges, prev_id, nid, edge_type):
                        edges.append(_make_edge(
                            prev_id, nid, edge_type, eff_impact, 0.72,
                            f"{entity.get('name','?')} → {node_name}", "1month", hl_node,
                        ))
                        added_e += 1
                    prev_id = nid

                # Last chain node → target exposure
                if chain_node_ids:
                    last_nid = chain_node_ids[-1]
                    last_name = chain[-1][0]
                    last_impact = sign * abs(chain[-1][3]) * 0.88
                    if not _has_edge(edges, last_nid, target_id, "DRIVES"):
                        edges.append(_make_edge(
                            last_nid, target_id, "DRIVES", last_impact, 0.78,
                            f"{last_name} drives {target_exposure}", "long-term", 90.0,
                        ))
                        added_e += 1

        logger.info("SyntheticEnricher v3: +%d mechanism nodes, +%d edges", added_n, added_e)
        snapshot["nodes"] = nodes
        snapshot["edges"] = edges
        return snapshot
