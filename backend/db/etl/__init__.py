"""
backend.etl — ETL Pipeline pour Talan Platform

Module d'extraction, transformation et chargement des données.

Scripts principaux:
  - config.py : Configuration centralisée (variables d'env, chemins, DSN)
  - utils.py : Fonctions utilitaires (logging, DB, helpers pandas)
  - etl_rh.py : T-04/05 — ETL RH (Excel → talan_hr)
  - etl_crm.py : T-06 — ETL CRM (Excel → talan_crm)
  - etl_erp.py : T-07 — ETL ERP (Excel → talan_erp)
  - etl_neo4j.py : T-08 — Population Neo4j (PostgreSQL → Neo4j)
  - run_all_etl.py : Orchestrateur (exécute tout dans l'ordre)

Usage:
    python -m backend.etl.config         # Vérifier la configuration
    python -m backend.etl.run_all_etl    # Exécuter l'ETL complet
    python -m backend.etl.etl_hr         # RH seulement
    python -m backend.etl.etl_crm        # CRM seulement
    python -m backend.etl.etl_erp        # ERP seulement
    python -m backend.etl.etl_neo4j      # Neo4j seulement
"""

from .config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_DB_HR,
    POSTGRES_DB_CRM,
    POSTGRES_DB_ERP,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    EXCEL_FILES,
    pg_connection_string,
    pg_dsn,
)

__all__ = [
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB_HR",
    "POSTGRES_DB_CRM",
    "POSTGRES_DB_ERP",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "EXCEL_FILES",
    "pg_connection_string",
    "pg_dsn",
]
