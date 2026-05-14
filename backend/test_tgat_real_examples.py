#!/usr/bin/env python3
"""
test_tgat_real_examples.py
==========================
Teste le TGAT entraîné sur 5 événements réels marquants pour Talan.

Pour chaque événement on :
  1. Construit un snapshot KG (même format que WorldModel.get_snapshot)
  2. Lance l'inférence TGAT (GNNPredictor)
  3. Affiche : prédiction Talan, scores par entité, chemins de propagation

Événements testés :
  A. COVID-19 pandemic (mars 2020)        — impact attendu NÉGATIF fort
  B. Lancement ChatGPT (nov 2022)         — impact attendu POSITIF fort
  C. Crise Atos plan de sauvegarde (jan 2024) — impact attendu POSITIF (concurrent en difficulté)
  D. Promulgation EU AI Act (août 2024)   — impact attendu POSITIF (opportunité conformité)
  E. DeepSeek R1 open-source (jan 2025)   — impact attendu POSITIF modéré (coûts IA en baisse)

Usage :
    cd backend
    python test_tgat_real_examples.py
    python test_tgat_real_examples.py --event covid
    python test_tgat_real_examples.py --event chatgpt --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

# ── Palette terminal ──────────────────────────────────────────────────────────
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def _col(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"

def _bar(value: float, width: int = 30) -> str:
    """ASCII progress bar from -1 to +1."""
    filled = int(abs(value) * width)
    bar = "#" * filled + "." * (width - filled)
    color = GREEN if value >= 0 else RED
    sign  = "+" if value >= 0 else "-"
    return f"{_col(sign + bar[:width], color)} {value:+.3f}"


# ══════════════════════════════════════════════════════════════════════════════
# §1  SNAPSHOTS — 5 événements réels
#     Format identique à WorldModel.get_snapshot() pour être compatible TGAT.
#     Les `id` de nœuds sont des chaînes uniques (on émule les internal IDs Neo4j
#     par des slugs lisibles).
# ══════════════════════════════════════════════════════════════════════════════

def _n(nid: str, name: str, label: str, **props) -> Dict:
    return {"id": nid, "name": name, "labels": [label], **props}

def _e(fid: str, tid: str, rel: str, score: float, conf: float,
       reason: str = "", horizon: str = "short_term",
       direction: str = None) -> Dict:
    if direction is None:
        direction = "negative" if score < 0 else "positive"
    return {
        "from": fid, "to": tid, "type": rel,
        "impact_score": score, "confidence": conf,
        "reason": reason, "time_horizon": horizon,
        "impact_direction": direction,
    }


# ── A. COVID-19 pandemic ──────────────────────────────────────────────────────
COVID_SNAPSHOT: Dict[str, Any] = {
    "center": "Talan",
    "nodes": [
        _n("talan",    "Talan",             "Company",  sector="IT Services / ESN"),
        _n("capgemini","Capgemini",          "Competitor"),
        _n("sopra",    "Sopra Steria",       "Competitor"),
        _n("atos",     "Atos",               "Competitor"),
        _n("accenture","Accenture",          "Competitor"),
        _n("covid19",  "Pandémie COVID-19",  "Event",    event_type="geopolitical_events"),
        _n("it_sector","Secteur IT Services","Sector"),
        _n("cloud_sec","Cloud Computing",    "Sector"),
        _n("france",   "France",             "Geography"),
        _n("cac40",    "CAC40",              "MacroIndicator"),
        _n("vix",      "VIX",                "MacroIndicator"),
    ],
    "edges": [
        _e("covid19","it_sector","CAUSES_IMPACT_ON", -0.55,0.95,
           "Gel massif des budgets IT clients, report ou annulation de projets de transformation",
           "immediate"),
        _e("covid19","talan",   "CAUSES_IMPACT_ON", -0.45,0.90,
           "Talan subit gel de projets, report RFP, passage au télétravail forcé",
           "immediate"),
        _e("covid19","capgemini","CAUSES_IMPACT_ON",-0.40,0.92,
           "Capgemini revoit ses prévisions 2020 à la baisse, -2.4% CA organique",
           "immediate"),
        _e("covid19","cloud_sec","CAUSES_IMPACT_ON",+0.30,0.88,
           "Accélération de la migration cloud pour le télétravail",
           "short_term"),
        _e("covid19","cac40",   "CAUSES_IMPACT_ON", -0.80,0.99,
           "CAC40 chute de 6000 à 3755 points", "immediate"),
        _e("talan",  "it_sector","BELONGS_TO_SECTOR",1.0,1.0,"Talan est une ESN"),
        _e("talan",  "capgemini","COMPETES_WITH",    0.6,1.0,"Concurrence ESN mid-market"),
        _e("talan",  "sopra",   "COMPETES_WITH",     0.7,1.0,"Concurrence directe"),
        _e("it_sector","cloud_sec","CAUSES_IMPACT_ON",-0.10,0.75,
           "Secteur IT fragilisé mais cloud en croissance"),
    ],
}

# ── B. Lancement ChatGPT ──────────────────────────────────────────────────────
CHATGPT_SNAPSHOT: Dict[str, Any] = {
    "center": "Talan",
    "nodes": [
        _n("talan",    "Talan",             "Company",  sector="IT Services / ESN"),
        _n("openai",   "OpenAI",            "Competitor"),
        _n("microsoft","Microsoft",         "Company"),
        _n("google",   "Google/Alphabet",   "Competitor"),
        _n("capgemini","Capgemini",          "Competitor"),
        _n("accenture","Accenture",          "Competitor"),
        _n("chatgpt",  "Lancement ChatGPT", "Event",    event_type="tech_launch"),
        _n("ai_sector","Secteur AI/ML",     "Sector"),
        _n("it_sector","IT Services / ESN", "Sector"),
        _n("france",   "France",            "Geography"),
    ],
    "edges": [
        _e("chatgpt","ai_sector","CAUSES_IMPACT_ON", +0.70,0.98,
           "Début de la révolution IA générative, investissements massifs",
           "immediate"),
        _e("chatgpt","talan",   "CAUSES_IMPACT_ON", +0.28,0.85,
           "Talan positionne ses équipes Data/IA pour capturer la demande conseil GenAI",
           "short_term"),
        _e("chatgpt","it_sector","CAUSES_IMPACT_ON",+0.35,0.90,
           "Explosion de la demande de conseil en IA générative pour les ESN",
           "short_term"),
        _e("chatgpt","capgemini","CAUSES_IMPACT_ON",+0.30,0.88,
           "Capgemini annonce un plan d'investissement 2Md€ en IA générative",
           "medium_term"),
        _e("chatgpt","accenture","CAUSES_IMPACT_ON",+0.35,0.90,
           "Accenture investit 3Md$ en IA en 2023", "medium_term"),
        _e("ai_sector","talan", "CAUSES_IMPACT_ON", +0.25,0.80,
           "Talan capte les projets de POC GenAI des grands comptes",
           "short_term"),
        _e("talan","it_sector", "BELONGS_TO_SECTOR",1.0,1.0,"Talan est une ESN"),
        _e("talan","capgemini", "COMPETES_WITH",    0.6,1.0,"Concurrence ESN"),
        _e("talan","openai",    "COMPETES_WITH",    0.2,0.8,"Partenariat/concurrence IA"),
    ],
}

# ── C. Crise Atos — plan de sauvegarde validé ─────────────────────────────────
ATOS_SNAPSHOT: Dict[str, Any] = {
    "center": "Talan",
    "nodes": [
        _n("talan",    "Talan",             "Company",  sector="IT Services / ESN"),
        _n("atos",     "Atos",              "Competitor"),
        _n("capgemini","Capgemini",          "Competitor"),
        _n("sopra",    "Sopra Steria",       "Competitor"),
        _n("atos_crisis","Atos plan sauvegarde validé","Event",
           event_type="competitor_moves"),
        _n("it_sector","IT Services / ESN", "Sector"),
        _n("cyber_sec","Cybersécurité",      "Sector"),
        _n("france",   "France",            "Geography"),
    ],
    "edges": [
        _e("atos_crisis","atos",    "CAUSES_IMPACT_ON",-0.60,0.95,
           "Atos perd sa crédibilité commerciale, fuite clients et talents",
           "immediate"),
        _e("atos_crisis","talan",   "CAUSES_IMPACT_ON",+0.30,0.85,
           "Talan capte des clients et talents ex-Atos. Opportunité majeure.",
           "short_term"),
        _e("atos_crisis","capgemini","CAUSES_IMPACT_ON",+0.20,0.80,
           "Capgemini récupère des contrats Atos abandonnés", "short_term"),
        _e("atos_crisis","it_sector","CAUSES_IMPACT_ON",-0.08,0.65,
           "Image du secteur ESN français ternie à l'international",
           "medium_term"),
        _e("atos",    "it_sector", "CAUSES_IMPACT_ON",-0.25,0.80,
           "Atos fragilise la réputation du secteur ESN", "medium_term"),
        _e("talan",   "atos",      "COMPETES_WITH",    0.5,1.0,"Concurrence directe"),
        _e("talan",   "it_sector", "BELONGS_TO_SECTOR",1.0,1.0,"Talan est une ESN"),
        _e("talan",   "capgemini", "COMPETES_WITH",    0.6,1.0,"Concurrence ESN"),
    ],
}

# ── D. EU AI Act promulgué ────────────────────────────────────────────────────
AIACT_SNAPSHOT: Dict[str, Any] = {
    "center": "Talan",
    "nodes": [
        _n("talan",    "Talan",             "Company",  sector="IT Services / ESN"),
        _n("capgemini","Capgemini",          "Competitor"),
        _n("accenture","Accenture",          "Competitor"),
        _n("microsoft","Microsoft",         "Company"),
        _n("aiact",   "EU AI Act promulgué","Regulation",
           event_type="regulatory_changes"),
        _n("ai_sector","Secteur AI/ML",     "Sector"),
        _n("it_sector","IT Services / ESN", "Sector"),
        _n("france",   "France",            "Geography"),
    ],
    "edges": [
        _e("aiact","ai_sector", "CAUSES_IMPACT_ON",-0.15,0.85,
           "Contraintes compliance IA pour tous les systèmes déployés en UE",
           "long_term"),
        _e("aiact","talan",     "CAUSES_IMPACT_ON",+0.18,0.80,
           "Talan développe une practice AI Act compliance et gouvernance IA",
           "medium_term"),
        _e("aiact","it_sector", "CAUSES_IMPACT_ON",+0.20,0.82,
           "Forte demande audits, gap analysis et mise en conformité IA",
           "medium_term"),
        _e("aiact","capgemini", "CAUSES_IMPACT_ON",+0.12,0.75,
           "Capgemini capte de grosses missions conformité IA",
           "medium_term"),
        _e("ai_sector","talan", "CAUSES_IMPACT_ON",+0.12,0.72,
           "La demande conseil IA conformité bénéficie à Talan",
           "medium_term"),
        _e("talan","it_sector", "BELONGS_TO_SECTOR",1.0,1.0,"Talan est une ESN"),
        _e("talan","capgemini", "COMPETES_WITH",    0.6,1.0,"Concurrence ESN"),
    ],
}

# ── E. DeepSeek R1 open-source ────────────────────────────────────────────────
DEEPSEEK_SNAPSHOT: Dict[str, Any] = {
    "center": "Talan",
    "nodes": [
        _n("talan",    "Talan",             "Company",  sector="IT Services / ESN"),
        _n("openai",   "OpenAI",            "Competitor"),
        _n("nvidia",   "NVIDIA",            "Company"),
        _n("microsoft","Microsoft",         "Company"),
        _n("capgemini","Capgemini",          "Competitor"),
        _n("mistral",  "Mistral AI",        "Competitor"),
        _n("deepseek", "DeepSeek R1",       "Event",    event_type="tech_launch"),
        _n("ai_sector","Secteur AI/ML",     "Sector"),
        _n("it_sector","IT Services / ESN", "Sector"),
        _n("china",    "Chine",             "Geography"),
        _n("france",   "France",            "Geography"),
    ],
    "edges": [
        _e("deepseek","ai_sector","CAUSES_IMPACT_ON",-0.30,0.90,
           "Commoditisation des LLM, pression marges fournisseurs propriétaires",
           "short_term"),
        _e("deepseek","talan",   "CAUSES_IMPACT_ON",+0.15,0.75,
           "Talan déploie des modèles très performants à bas coût pour ses clients",
           "short_term"),
        _e("deepseek","it_sector","CAUSES_IMPACT_ON",+0.12,0.72,
           "Les ESN accèdent à des modèles open-source frontier pour les déploiements client",
           "short_term"),
        _e("deepseek","nvidia",  "CAUSES_IMPACT_ON",-0.25,0.88,
           "Action NVIDIA -17% en une journée, remise en question des dépenses GPU",
           "immediate"),
        _e("deepseek","openai",  "CAUSES_IMPACT_ON",-0.20,0.85,
           "OpenAI sous pression tarifaire face au modèle gratuit chinois",
           "short_term"),
        _e("ai_sector","talan",  "CAUSES_IMPACT_ON",+0.10,0.68,
           "Baisse des coûts IA = plus de projets validés chez les clients Talan",
           "short_term"),
        _e("talan","it_sector",  "BELONGS_TO_SECTOR",1.0,1.0,"Talan est une ESN"),
        _e("talan","capgemini",  "COMPETES_WITH",    0.6,1.0,"Concurrence ESN"),
        _e("talan","mistral",    "COMPETES_WITH",    0.3,0.8,"Partenariat/concurrence IA"),
    ],
}


SCENARIOS: Dict[str, Dict] = {
    "covid":    {"label": "A. COVID-19 pandemic (11 mars 2020)",
                 "snapshot": COVID_SNAPSHOT,
                 "expected": "NEGATIF fort  (-0.40 a -0.55 attendu)"},
    "chatgpt":  {"label": "B. Lancement ChatGPT (30 nov 2022)",
                 "snapshot": CHATGPT_SNAPSHOT,
                 "expected": "POSITIF fort  (+0.25 a +0.35 attendu)"},
    "atos":     {"label": "C. Atos plan sauvegarde (23 jan 2024)",
                 "snapshot": ATOS_SNAPSHOT,
                 "expected": "POSITIF modere (+0.20 a +0.30 attendu)"},
    "aiact":    {"label": "D. EU AI Act promulgue (1 aout 2024)",
                 "snapshot": AIACT_SNAPSHOT,
                 "expected": "POSITIF modere (+0.12 a +0.20 attendu)"},
    "deepseek": {"label": "E. DeepSeek R1 open-source (20 jan 2025)",
                 "snapshot": DEEPSEEK_SNAPSHOT,
                 "expected": "POSITIF faible (+0.10 a +0.18 attendu)"},
}


# ══════════════════════════════════════════════════════════════════════════════
# §2  INFERENCE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def run_inference(snapshot: Dict[str, Any], trigger: str, verbose: bool = False):
    from app.services.market_analysis.gnn_predictor import GNNPredictor
    predictor = GNNPredictor()
    result = predictor.predict(snapshot, price_data=None, trigger_event=trigger)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# §3  DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def _impact_label(v: float) -> str:
    if v <= -0.5:  return _col("CRITIQUE NEGATIF", RED)
    if v <= -0.2:  return _col("NEGATIF",          RED)
    if v <  -0.05: return _col("Legèrement negatif", YELLOW)
    if v <=  0.05: return _col("Neutre", DIM)
    if v <=  0.2:  return _col("Legèrement positif", GREEN)
    if v <=  0.5:  return _col("POSITIF",            GREEN)
    return _col("TRES POSITIF", GREEN)


def display_result(name: str, scenario: Dict, result: Any, verbose: bool) -> None:
    label    = scenario["label"]
    expected = scenario["expected"]

    print(f"\n{'='*70}")
    print(f" {BOLD}{label}{RESET}")
    print(f" Impact attendu : {YELLOW}{expected}{RESET}")
    print(f"{'='*70}")

    # ── Prédiction Talan ──────────────────────────────────────────────────────
    tp = result.talan_prediction
    if tp:
        print(f"\n  {BOLD}>> Impact predit sur TALAN{RESET}")
        print(f"    Score   : {_bar(tp.predicted_impact)}")
        print(f"    Verdict : {_impact_label(tp.predicted_impact)}")
        print(f"    Confiance : {tp.confidence:.1%}   Hops : {tp.propagation_hops}")
    else:
        print(f"\n  {YELLOW}! Noeud Talan non trouve dans les predictions{RESET}")

    # ── Risque systémique ─────────────────────────────────────────────────────
    sys_risk = result.systemic_risk_score
    risk_col  = RED if sys_risk >= 0.6 else YELLOW if sys_risk >= 0.3 else GREEN
    print(f"\n  {BOLD}>> Risque systemique{RESET} : {_col(f'{sys_risk:.1%}', risk_col)}")

    # ── Toutes les entités impactées ──────────────────────────────────────────
    if result.predictions:
        print(f"\n  {BOLD}>> Entites impactees ({len(result.predictions)} detectees){RESET}")
        sorted_preds = sorted(result.predictions,
                              key=lambda p: abs(p.predicted_impact), reverse=True)
        for p in sorted_preds[:8]:
            marker = " << TALAN" if p.entity_name == "Talan" else ""
            hidden = f"  {_col('[RISQUE CACHE]', RED)}" if p.hidden_risk else ""
            print(f"    {p.entity_name:<30} {_bar(p.predicted_impact, 20)}"
                  f"  conf={p.confidence:.0%}{marker}{hidden}")

    # ── Risques cachés ────────────────────────────────────────────────────────
    if result.top_hidden_risks:
        print(f"\n  {BOLD}>> Risques caches (propagation multi-hop){RESET}")
        for hr in result.top_hidden_risks:
            print(f"    {RED}!{RESET} {hr.entity_name:<28} impact={hr.predicted_impact:+.3f}  "
                  f"hops={hr.propagation_hops}")

    # ── Chemins de propagation ────────────────────────────────────────────────
    if result.propagation_paths:
        print(f"\n  {BOLD}>> Chemins de propagation ({len(result.propagation_paths)} chaines){RESET}")
        for i, path in enumerate(result.propagation_paths[:3]):
            sev_col = RED if path.chain_score < -0.3 else (
                      YELLOW if path.chain_score < 0 else GREEN)
            print(f"\n    Chaîne {i+1}: {_col(path.source_name, BOLD)}"
                  f"  score={_col(f'{path.chain_score:+.3f}', sev_col)}"
                  f"  conf={path.chain_conf:.0%}  horizon={path.time_horizon_label}")
            if verbose:
                for step in path.steps:
                    print(f"      {DIM}→ [{step.relation_type}]{RESET} "
                          f"{step.node_name} ({step.node_type})"
                          f"  impact={step.impact_score:+.3f}  [{step.time_horizon}]")
                    if step.reason:
                        print(f"        {DIM}{step.reason[:100]}{RESET}")

    # ── Modèle actif ──────────────────────────────────────────────────────────
    mode = "TGAT (checkpoint entraîné)" if result.talan_prediction else "heuristique (fallback)"
    print(f"\n  {DIM}Moteur : {mode}  |  trigger='{result.trigger_event[:50]}'{RESET}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# §4  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test TGAT inference sur des événements réels")
    parser.add_argument(
        "--event", choices=list(SCENARIOS.keys()) + ["all"], default="all",
        help="Événement à tester (défaut: tous)")
    parser.add_argument(
        "--verbose", action="store_true",
        help="Afficher les détails des étapes de propagation")
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Sortie JSON brute (pour débogage)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*70}")
    print("  TEST TGAT - Inference sur evenements reels de marche")
    print("  Checkpoint : app/services/market_analysis/checkpoints/tgat_best.pt")
    print("  Metriques  : AUC=0.9227  AP=0.9600  F1=0.9532")
    print(f"{'='*70}{RESET}\n")

    to_run = list(SCENARIOS.items()) if args.event == "all" \
             else [(args.event, SCENARIOS[args.event])]

    for name, scenario in to_run:
        try:
            result = run_inference(
                snapshot=scenario["snapshot"],
                trigger=scenario["label"],
                verbose=args.verbose,
            )
            if args.as_json:
                print(json.dumps(result.model_dump(), indent=2, default=str))
            else:
                display_result(name, scenario, result, verbose=args.verbose)
        except Exception as exc:
            print(f"\n{RED}[ERREUR] {name}: {exc}{RESET}")
            import traceback; traceback.print_exc()

    # ── Récap comparaison attendu/obtenu ──────────────────────────────────────
    if args.event == "all" and not args.as_json:
        print(f"\n{BOLD}{'='*70}")
        print("  RECAP - Attendu vs Obtenu")
        print(f"{'='*70}{RESET}")
        print(f"  {'Événement':<30}  {'Attendu':<35}  {'Obtenu'}")
        print(f"  {'-'*30}  {'-'*35}  {'-'*20}")
        for name, scenario in SCENARIOS.items():
            snapshot = scenario["snapshot"]
            try:
                result = run_inference(snapshot, scenario["label"])
                tp = result.talan_prediction
                obtained = f"{tp.predicted_impact:+.3f}" if tp else "N/A"
                ok = ""
                if tp:
                    v = tp.predicted_impact
                    if "NEGATIF" in scenario["expected"] and v < -0.05:
                        ok = f"{GREEN}OK{RESET}"
                    elif "POSITIF" in scenario["expected"] and v > 0.05:
                        ok = f"{GREEN}OK{RESET}"
                    else:
                        ok = f"{RED}✗{RESET}"
                print(f"  {scenario['label'][:30]:<30}  "
                      f"{scenario['expected']:<35}  {obtained}  {ok}")
            except Exception as exc:
                print(f"  {name:<30}  ERROR: {exc}")
        print()


if __name__ == "__main__":
    main()
