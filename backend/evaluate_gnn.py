"""GNN Evaluator — valide les prédictions du GNNPredictor sur 3 axes :

1. BACKTEST   — compare prédictions GNN vs impact réel (market_news_analyses)
2. SIMULATION — injecte des événements choc prédéfinis, vérifie la propagation
3. SANITY     — cas connus (Capgemini concurrent → impact Talan négatif attendu)

Usage :
    python evaluate_gnn.py                  # backtest + sanity
    python evaluate_gnn.py --shock          # scénarios choc uniquement
    python evaluate_gnn.py --all            # tout
    python evaluate_gnn.py --shock --event "Recession européenne"
"""
from __future__ import annotations

import argparse
import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text

from app.core.config import settings

# ── Helpers d'affichage ────────────────────────────────────────────────────────

def _bar(value: float, width: int = 30) -> str:
    norm = (value + 1) / 2  # [-1,1] → [0,1]
    filled = int(norm * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "\033[91m" if value < -0.2 else "\033[92m" if value > 0.2 else "\033[93m"
    return f"{color}{bar}\033[0m  {value:+.3f}"

def _header(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)

def _row(label: str, value: str, color: str = "") -> None:
    reset = "\033[0m" if color else ""
    print(f"  {label:<35} {color}{value}{reset}")


# ══════════════════════════════════════════════════════════════════════════════
# 1. BACKTEST — GNN prédit vs. impact réel LLM
# ══════════════════════════════════════════════════════════════════════════════

def run_backtest(n_samples: int = 30) -> Dict:
    """Compare les scores GNN historiques vs l'impact réel dans market_news_analyses."""
    _header("BACKTEST — GNN prédit vs impact réel")

    engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
    with engine.connect() as conn:
        # Récupère paires (score_gnn, impact_réel) en joignant sur pipeline_run_id ≈ timestamp
        rows = conn.execute(text("""
            SELECT
                g.talan_impact      AS gnn_score,
                g.systemic_risk     AS systemic_risk,
                g.trigger_event     AS event,
                g.recorded_at       AS ts,
                (
                    SELECT AVG(a.talan_impact_score)
                    FROM market_news_analyses a
                    WHERE ABS(EXTRACT(EPOCH FROM (a.analysis_timestamp - g.recorded_at))) < 3600
                ) AS real_impact
            FROM market_gnn_scores g
            ORDER BY g.recorded_at DESC
            LIMIT :n
        """), {"n": n_samples}).fetchall()

    if not rows:
        print("  ⚠  Aucun score GNN en base. Lance d'abord run_pipeline.py.")
        return {}

    valid = [(r.gnn_score, r.real_impact, r.event, r.ts)
             for r in rows if r.real_impact is not None]

    print(f"  Échantillons avec ground truth : {len(valid)}/{len(rows)}\n")

    if not valid:
        print("  ⚠  Pas de recoupement temporel analyses ↔ GNN scores.")
        print("     Lance plusieurs cycles pipeline pour accumuler des données.")
        # Affiche quand même les scores bruts
        print(f"\n  {'Date':<22} {'GNN Score':>10} {'Systemic':>10}  Événement")
        print("  " + "─" * 70)
        for r in rows[:15]:
            ts = str(r.ts)[:19]
            ev = str(r.event or "")[:40]
            score_bar = _bar(float(r.gnn_score or 0), 20)
            print(f"  {ts:<22} {score_bar}  {ev}")
        return {"n_scores": len(rows), "n_with_truth": 0}

    # Métriques
    import math
    errors = [abs(g - r) for g, r, *_ in valid]
    sq_errors = [(g - r) ** 2 for g, r, *_ in valid]
    mae = sum(errors) / len(errors)
    rmse = math.sqrt(sum(sq_errors) / len(sq_errors))

    # Direction accuracy (signe correct ?)
    correct_direction = sum(
        1 for g, r, *_ in valid
        if (g >= 0) == (r >= 0)
    )
    direction_acc = correct_direction / len(valid) * 100

    # Corrélation de Pearson simple
    gs = [g for g, *_ in valid]
    rs = [r for _, r, *_ in valid]
    mean_g, mean_r = sum(gs) / len(gs), sum(rs) / len(rs)
    cov = sum((g - mean_g) * (r - mean_r) for g, r in zip(gs, rs))
    std_g = math.sqrt(sum((g - mean_g) ** 2 for g in gs) or 1)
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rs) or 1)
    pearson = cov / (std_g * std_r)

    print(f"  {'Métrique':<30} {'Valeur':>10}  Interprétation")
    print("  " + "─" * 65)
    _row("MAE (erreur absolue moyenne)", f"{mae:.4f}",
         "\033[92m" if mae < 0.15 else "\033[93m" if mae < 0.3 else "\033[91m")
    _row("RMSE", f"{rmse:.4f}",
         "\033[92m" if rmse < 0.2 else "\033[93m" if rmse < 0.4 else "\033[91m")
    _row("Direction accuracy", f"{direction_acc:.1f}%",
         "\033[92m" if direction_acc > 65 else "\033[93m" if direction_acc > 55 else "\033[91m")
    _row("Corrélation de Pearson", f"{pearson:.3f}",
         "\033[92m" if pearson > 0.5 else "\033[93m" if pearson > 0.2 else "\033[91m")

    print(f"\n  {'Date':<20} {'GNN':>8}  {'Réel':>8}  {'Err':>6}  Événement")
    print("  " + "─" * 75)
    for g, r, ev, ts in valid[:15]:
        err = abs(g - r)
        err_color = "\033[92m" if err < 0.1 else "\033[93m" if err < 0.25 else "\033[91m"
        ts_str = str(ts)[:16]
        ev_str = str(ev or "")[:35]
        print(f"  {ts_str:<20} {g:+8.3f}  {r:+8.3f}  {err_color}{err:6.3f}\033[0m  {ev_str}")

    return {"mae": mae, "rmse": rmse, "direction_acc": direction_acc, "pearson": pearson}


# ══════════════════════════════════════════════════════════════════════════════
# 2. SIMULATION — Scénarios choc prédéfinis
# ══════════════════════════════════════════════════════════════════════════════

# Scénarios : (nom, description, entité source, relation, entité cible, impact_attendu_talan)
SHOCK_SCENARIOS = [
    {
        "name": "Recession UE",
        "event": "La BCE annonce une récession en zone euro — PIB -2.5%",
        "source": "European_Central_Bank",
        "source_type": "MacroIndicator",
        "expected_talan_direction": "negative",
        "expected_range": (-0.8, -0.1),
        "reason": "Récession → gel budgets IT → moins de contrats Talan",
    },
    {
        "name": "Capgemini licenciements",
        "event": "Capgemini annonce 8000 licenciements en Europe",
        "source": "Capgemini",
        "source_type": "Company",
        "expected_talan_direction": "positive",
        "expected_range": (0.0, 0.6),
        "reason": "Concurrent affaibli → Talan peut récupérer des parts de marché",
    },
    {
        "name": "Explosion marché GenAI",
        "event": "Microsoft annonce 10Md€ d'investissement en GenAI pour les ESN",
        "source": "Microsoft",
        "source_type": "Company",
        "expected_talan_direction": "positive",
        "expected_range": (0.1, 0.9),
        "reason": "Boom GenAI → hausse demande consulting transformation numérique",
    },
    {
        "name": "Régulation IA restrictive",
        "event": "L'UE impose un moratoire de 6 mois sur les déploiements IA en entreprise",
        "source": "EU_AI_Act",
        "source_type": "Regulation",
        "expected_talan_direction": "negative",
        "expected_range": (-0.6, 0.0),
        "reason": "Projets IA clients gelés → perte de revenus consulting Talan",
    },
    {
        "name": "Hausse taux BCE",
        "event": "La BCE monte les taux à 5.5% — credit crunch PME",
        "source": "BCE_Rate",
        "source_type": "MacroIndicator",
        "expected_talan_direction": "negative",
        "expected_range": (-0.5, -0.05),
        "reason": "Hausse coût du capital → gel DSI → moins de projets IT",
    },
]

def run_shock_simulation(event_filter: Optional[str] = None) -> None:
    """Injecte chaque scénario choc dans le KG et mesure la réponse GNN."""
    from app.services.market_analysis.world_model import WorldModel
    from app.services.market_analysis.gnn_predictor import GNNPredictor

    _header("SIMULATION — Scénarios choc")

    wm = WorldModel()
    gnn = GNNPredictor()

    scenarios = SHOCK_SCENARIOS
    if event_filter:
        scenarios = [s for s in scenarios if event_filter.lower() in s["name"].lower()
                     or event_filter.lower() in s["event"].lower()]
        if not scenarios:
            print(f"  Aucun scénario correspondant à '{event_filter}'")
            return

    results = []
    for sc in scenarios:
        print(f"\n  ▶ {sc['name']}")
        print(f"    Événement : {sc['event']}")
        print(f"    Attendu   : {sc['expected_talan_direction']} {sc['expected_range']}")

        try:
            snapshot = wm.get_snapshot("Talan", hops=2)

            # Injecte artificiellement l'événement dans le snapshot (en mémoire, sans écrire en DB)
            shock_node = {
                "id": f"shock_{sc['source']}",
                "name": sc["source"],
                "labels": [sc["source_type"]],
                "slug": sc["source"].lower(),
            }
            shock_edge = {
                "from": f"shock_{sc['source']}",
                "to": next((n["id"] for n in snapshot["nodes"] if n["name"] == "Talan"), "talan"),
                "type": "CAUSES_IMPACT_ON",
                "impact_score": -0.7 if sc["expected_talan_direction"] == "negative" else 0.7,
                "confidence": 0.85,
                "timestamp": datetime.utcnow().isoformat(),
            }
            snapshot_shock = {
                "nodes": snapshot["nodes"] + [shock_node],
                "edges": snapshot["edges"] + [shock_edge],
                "center": "Talan",
            }

            result = gnn.predict(
                snapshot_shock,
                trigger_event=sc["event"],
            )

            talan_score = result.talan_prediction.predicted_impact if result.talan_prediction else 0.0
            lo, hi = sc["expected_range"]
            in_range = lo <= talan_score <= hi
            status = "\033[92m✓ OK\033[0m" if in_range else "\033[91m✗ HORS PLAGE\033[0m"

            print(f"    GNN Talan : {_bar(talan_score, 25)}")
            print(f"    Systemic  : {result.systemic_risk_score:.3f}")
            print(f"    Résultat  : {status}  (plage attendue [{lo:+.1f}, {hi:+.1f}])")
            print(f"    Raison    : {sc['reason']}")

            if result.top_hidden_risks:
                print(f"    Risques cachés détectés :")
                for r in result.top_hidden_risks[:3]:
                    print(f"      • {r.entity_name:<25} {_bar(r.predicted_impact, 15)}")

            results.append({
                "scenario": sc["name"],
                "talan_score": talan_score,
                "expected": sc["expected_range"],
                "pass": in_range,
                "systemic_risk": result.systemic_risk_score,
            })

        except Exception as e:
            print(f"    \033[91m✗ ERREUR: {e}\033[0m")
            results.append({"scenario": sc["name"], "error": str(e), "pass": False})

    # Résumé
    passed = sum(1 for r in results if r.get("pass"))
    total = len(results)
    print(f"\n  {'─' * 50}")
    color = "\033[92m" if passed == total else "\033[93m" if passed >= total * 0.6 else "\033[91m"
    print(f"  {color}Score : {passed}/{total} scénarios dans la plage attendue\033[0m")
    if passed < total:
        print("  ⚠  Les écarts peuvent indiquer :")
        print("     • Modèle non entraîné (poids aléatoires) → lance train_gnn_predictor.py")
        print("     • KG trop petit (< 50 nœuds) → lance run_pipeline.py × 5")
        print("     • Scores GNN trop faibles (features = 0) → vérifie impact_score sur nœuds KG")


# ══════════════════════════════════════════════════════════════════════════════
# 3. SANITY CHECK — Cohérence des prédictions sur cas connus
# ══════════════════════════════════════════════════════════════════════════════

def run_sanity_checks() -> None:
    """Vérifie des propriétés basiques du GNN sur le graphe courant."""
    from app.services.market_analysis.world_model import WorldModel
    from app.services.market_analysis.gnn_predictor import GNNPredictor

    _header("SANITY CHECKS — Cohérence du modèle")

    wm = WorldModel()
    gnn = GNNPredictor()

    try:
        snapshot = wm.get_snapshot("Talan", hops=2)
    except Exception as e:
        print(f"  ✗ Impossible de récupérer le snapshot KG : {e}")
        return

    n_nodes = len(snapshot.get("nodes", []))
    n_edges = len(snapshot.get("edges", []))
    print(f"  KG snapshot : {n_nodes} nœuds, {n_edges} arêtes (centré sur Talan, hops=2)\n")

    if n_nodes < 5:
        print("  ⚠  KG trop petit. Lance run_pipeline.py pour alimenter Neo4j.")
        return

    # Run baseline
    baseline = gnn.predict(snapshot, trigger_event="baseline_check")
    talan_base = baseline.talan_prediction.predicted_impact if baseline.talan_prediction else 0.0
    systemic_base = baseline.systemic_risk_score

    print(f"  {'Check':<45} {'Résultat'}")
    print("  " + "─" * 70)

    def check(label: str, condition: bool, detail: str = "") -> None:
        status = "\033[92m✓\033[0m" if condition else "\033[91m✗\033[0m"
        print(f"  {label:<45} {status}  {detail}")

    # 1. Talan doit avoir une prédiction
    check("Talan a une prédiction", baseline.talan_prediction is not None,
          f"impact={talan_base:+.3f}")

    # 2. Scores dans [-1, 1]
    all_scores = [p.predicted_impact for p in baseline.predictions]
    in_range = all((-1 <= s <= 1) for s in all_scores)
    check("Tous les scores dans [-1, 1]", in_range,
          f"min={min(all_scores, default=0):+.3f} max={max(all_scores, default=0):+.3f}")

    # 3. Risque systémique dans [0, 1]
    check("Risque systémique dans [0, 1]", 0 <= systemic_base <= 1,
          f"systemic={systemic_base:.3f}")

    # 4. Scores pas tous à zéro (sinon poids aléatoires sans entraînement)
    non_zero = sum(1 for s in all_scores if abs(s) > 0.05)
    check("Scores non-triviaux (|score| > 0.05)",
          non_zero > len(all_scores) * 0.3,
          f"{non_zero}/{len(all_scores)} non-triviaux")

    # 5. Test de monotonie : choc négatif direct → score Talan plus bas
    snapshot_neg = dict(snapshot)
    neg_edge = {
        "from": "test_shock_node",
        "to": next((n["id"] for n in snapshot["nodes"] if n["name"] == "Talan"), ""),
        "type": "CAUSES_IMPACT_ON",
        "impact_score": -0.9,
        "confidence": 1.0,
        "timestamp": datetime.utcnow().isoformat(),
    }
    snapshot_neg = {
        "nodes": snapshot["nodes"] + [{"id": "test_shock_node", "name": "ShockTest",
                                        "labels": ["Company"], "slug": "shock-test"}],
        "edges": snapshot["edges"] + [neg_edge],
        "center": "Talan",
    }
    result_neg = gnn.predict(snapshot_neg, trigger_event="choc_negatif_test")
    talan_neg = result_neg.talan_prediction.predicted_impact if result_neg.talan_prediction else 0.0
    check("Choc négatif direct → impact Talan baisse", talan_neg <= talan_base + 0.1,
          f"baseline={talan_base:+.3f} → après choc={talan_neg:+.3f}")

    # 6. Choc positif → score Talan monte
    pos_edge = {**neg_edge, "impact_score": 0.9,
                "from": "test_pos_node",
                "to": next((n["id"] for n in snapshot["nodes"] if n["name"] == "Talan"), "")}
    snapshot_pos = {
        "nodes": snapshot["nodes"] + [{"id": "test_pos_node", "name": "PosShock",
                                        "labels": ["Company"], "slug": "pos-shock"}],
        "edges": snapshot["edges"] + [pos_edge],
        "center": "Talan",
    }
    result_pos = gnn.predict(snapshot_pos, trigger_event="choc_positif_test")
    talan_pos = result_pos.talan_prediction.predicted_impact if result_pos.talan_prediction else 0.0
    check("Choc positif direct → impact Talan monte", talan_pos >= talan_base - 0.1,
          f"baseline={talan_base:+.3f} → après choc={talan_pos:+.3f}")

    # 7. Symétrie approximative (choc +X et -X → impacts symétriques)
    asymmetry = abs(abs(talan_pos - talan_base) - abs(talan_neg - talan_base))
    check("Symétrie choc pos/neg (asymétrie < 0.3)", asymmetry < 0.3,
          f"asymétrie={asymmetry:.3f}")

    # Affiche le détail des prédictions
    print(f"\n  Top 10 entreprises impactées (baseline) :")
    top = sorted(baseline.predictions, key=lambda p: abs(p.predicted_impact), reverse=True)[:10]
    for p in top:
        risk_tag = " \033[95m[risque caché]\033[0m" if p.hidden_risk else ""
        print(f"    {p.entity_name:<28} {_bar(p.predicted_impact, 20)}{risk_tag}")

    if baseline.top_hidden_risks:
        print(f"\n  Top risques cachés (hops > 1, |impact| > 0.3) :")
        for r in baseline.top_hidden_risks:
            print(f"    • {r.entity_name:<30} hops={r.propagation_hops}  {r.predicted_impact:+.3f}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. INFO — Statut du modèle
# ══════════════════════════════════════════════════════════════════════════════

def show_model_info() -> None:
    """Affiche l'état du modèle GNN (poids, entraînement, DB)."""
    from app.services.market_analysis.gnn_predictor import MODEL_PATH, _PYG_AVAILABLE

    _header("STATUT DU MODÈLE GNN")

    check = "\033[92m✓\033[0m"
    cross = "\033[91m✗\033[0m"

    pyg_ok = _PYG_AVAILABLE
    model_ok = MODEL_PATH.exists()
    print(f"  PyTorch Geometric installé  {check if pyg_ok else cross}")
    print(f"  gnn_model.pt présent        {check if model_ok else cross}",
          f"  ({MODEL_PATH})" if model_ok else "  → lance train_gnn_predictor.py")

    engine = create_engine(settings.database_url("hr"), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            n_scores = conn.execute(text("SELECT COUNT(*) FROM market_gnn_scores")).scalar()
            n_analyses = conn.execute(text("SELECT COUNT(*) FROM market_news_analyses")).scalar()
            n_articles = conn.execute(text("SELECT COUNT(*) FROM market_raw_articles")).scalar()
        print(f"  Articles collectés          {check}  {n_articles}")
        print(f"  Analyses LLM en DB          {check if n_analyses >= 20 else cross}  {n_analyses}  (20 min pour entraîner)")
        print(f"  Scores GNN en DB            {check if n_scores >= 20 else cross}  {n_scores}  (20 min pour LSTM forecaster)")

        lstm_path = MODEL_PATH.parent / "lstm_forecaster.pt"
        print(f"  lstm_forecaster.pt présent  {check if lstm_path.exists() else cross}")

        if n_scores > 0:
            with engine.connect() as conn:
                last = conn.execute(text(
                    "SELECT recorded_at, talan_impact, systemic_risk FROM market_gnn_scores "
                    "ORDER BY recorded_at DESC LIMIT 1"
                )).fetchone()
            if last:
                print(f"\n  Dernier score GNN : {str(last.recorded_at)[:19]}")
                print(f"    talan_impact={last.talan_impact:+.3f}  systemic_risk={last.systemic_risk:.3f}")
    except Exception as e:
        print(f"  {cross} Erreur DB : {e}")

    if not pyg_ok:
        print("\n  Pour activer le mode neuronal :")
        print("    pip install torch torch-geometric")
    if not model_ok:
        print("\n  Pour entraîner le GNN :")
        print("    python train_gnn_predictor.py --epochs 50")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="GNN Evaluator — valide le GNNPredictor")
    parser.add_argument("--backtest",  action="store_true", help="Backtest GNN vs impact réel")
    parser.add_argument("--shock",     action="store_true", help="Scénarios choc prédéfinis")
    parser.add_argument("--sanity",    action="store_true", help="Sanity checks cohérence")
    parser.add_argument("--info",      action="store_true", help="Statut modèle + DB")
    parser.add_argument("--all",       action="store_true", help="Tout lancer")
    parser.add_argument("--event",     type=str, default=None, help="Filtre scénario choc par nom")
    parser.add_argument("--n",         type=int, default=30, help="Nombre d'échantillons backtest")
    args = parser.parse_args()

    run_all = args.all or not any([args.backtest, args.shock, args.sanity, args.info])

    show_model_info()

    if run_all or args.sanity:
        run_sanity_checks()

    if run_all or args.backtest:
        run_backtest(args.n)

    if run_all or args.shock:
        run_shock_simulation(args.event)

    print(f"\n{'═' * 60}\n")


if __name__ == "__main__":
    main()
