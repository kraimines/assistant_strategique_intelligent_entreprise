"""
run_all_etl.py — Orchestrateur ETL complet

Enchaîne les pipelines dans le bon ordre:
  1. T-04/05 : ETL RH (PostgreSQL talan_hr)
  2. T-06 : ETL CRM (PostgreSQL talan_crm)
  3. T-07 : ETL ERP (PostgreSQL talan_erp)
  4. T-08 : ETL Neo4j (Graphe depuis PostgreSQL)

Usage:
    python run_all_etl.py               # ETL complet
    python run_all_etl.py --skip-neo4j  # PostgreSQL seulement
    python run_all_etl.py --neo4j-only  # Neo4j uniquement
    python run_all_etl.py --hr --crm    # Seulement HR et CRM
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from utils import get_logger

log = get_logger("ETL-MASTER")


def run_step(name: str, module_fn) -> bool:
    """Exécute une step ETL et retourne le succès."""
    log.info(f"\n{'='*70}")
    log.info(f"  {name}")
    log.info(f"{'='*70}\n")
    t0 = time.time()
    try:
        module_fn()
        elapsed = time.time() - t0
        log.info(f"\n  ✅ {name} — {elapsed:.1f}s\n")
        return True
    except Exception as exc:
        log.exception(f"  ❌ {name} échoué")
        return False


def main():
    """Orchestrateu principal."""
    parser = argparse.ArgumentParser(description="ETL complet Talan Platform")
    parser.add_argument("--skip-neo4j", action="store_true", help="Ignorer ETL Neo4j")
    parser.add_argument("--neo4j-only", action="store_true", help="Seulement ETL Neo4j")
    parser.add_argument("--hr", action="store_true", help="Inclure ETL HR")
    parser.add_argument("--crm", action="store_true", help="Inclure ETL CRM")
    parser.add_argument("--erp", action="store_true", help="Inclure ETL ERP")
    
    args = parser.parse_args()
    
    # Par défaut, inclure tous les domaines si aucun n'est spécifié
    run_hr = args.hr or not (args.hr or args.crm or args.erp)
    run_crm = args.crm or not (args.hr or args.crm or args.erp)
    run_erp = args.erp or not (args.hr or args.crm or args.erp)
    
    run_postgres = not args.neo4j_only
    run_neo4j = not args.skip_neo4j
    
    t_start = time.time()
    results = {}
    
    log.info("╔════════════════════════════════════════════════════════════════╗")
    log.info("║           Talan Platform - ETL Orchestrator                    ║")
    log.info("╚════════════════════════════════════════════════════════════════╝")
    
    # Phase 1 : PostgreSQL ETL
    if run_postgres:
        log.info("\n┌─ Phase 1: PostgreSQL ETL ────────────────────────────────┐")
        
        if run_hr:
            from etl_rh import run
            results["T-04/05 RH"] = run_step("T-04/05 : ETL RH", run)
        
        if run_crm:
            from etl_crm import run
            results["T-06 CRM"] = run_step("T-06 : ETL CRM", run)
        
        if run_erp:
            from etl_erp import run
            results["T-07 ERP"] = run_step("T-07 : ETL ERP", run)
        
        log.info("└────────────────────────────────────────────────────────────┘")
    
    # Phase 2 : Neo4j ETL
    if run_neo4j:
        log.info("\n┌─ Phase 2: Neo4j Graph ETL ──────────────────────────────┐")
        from etl_neo4j import run
        results["T-08 Neo4j"] = run_step("T-08 : Population Neo4j", run)
        log.info("└────────────────────────────────────────────────────────────┘")
    
    # Résumé final
    elapsed_total = time.time() - t_start
    log.info(f"\n{'='*70}")
    log.info("                    RÉSUMÉ ETL")
    log.info(f"{'='*70}\n")
    
    all_ok = True
    for step, ok in results.items():
        status = "✅" if ok else "❌"
        log.info(f"  {status}  {step}")
        if not ok:
            all_ok = False
    
    log.info(f"\n  Durée totale : {elapsed_total:.1f}s")
    log.info(f"  Statut global : {'✅ SUCCÈS' if all_ok else '❌ ÉCHEC'}\n")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
