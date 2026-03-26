"""
config.py — Paramètres de connexion et chemins des fichiers Excel.

Centralise la configuration ETL. Modifier uniquement ce fichier pour adapter 
l'ETL à un autre environnement (développement, test, production).

Les variables sont lues depuis les variables d'environnement (.env) avec des 
valeurs par défaut appropriées pour le développement local.
"""

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent.parent  # racine du projet backend/../..
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))  # dossier contenant les .xlsx

EXCEL_FILES = {
    "rh":  DATA_DIR / "RH_Talan_Tunisie.xlsx",
    "crm": DATA_DIR / "CRM_Talan_Tunisie.xlsx",
    "erp": DATA_DIR / "ERP_Talan_Tunisie.xlsx",
}

# ── PostgreSQL (3 bases de données séparées : talan_hr, talan_crm, talan_erp) ──
POSTGRES_HOST     = os.environ.get("POSTGRES_HOST",     "localhost")
POSTGRES_PORT     = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER     = os.environ.get("POSTGRES_USER",     "talan")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "talan_secret")

# 3 bases de données distinctes pour les 3 domaines
POSTGRES_DB_HR  = os.environ.get("POSTGRES_DB_HR",  "talan_hr")
POSTGRES_DB_CRM = os.environ.get("POSTGRES_DB_CRM", "talan_crm")
POSTGRES_DB_ERP = os.environ.get("POSTGRES_DB_ERP", "talan_erp")

# Dictionnaire pour accès unifié par domaine
POSTGRES_DBS = {
    "hr":  POSTGRES_DB_HR,
    "crm": POSTGRES_DB_CRM,
    "erp": POSTGRES_DB_ERP,
}


def pg_connection_string(domain: str) -> str:
    """
    Retourne une connection string SQLAlchemy pour le domaine donné.
    
    Args:
        domain: "hr", "crm" ou "erp"
        
    Returns:
        Connection string compatible SQLAlchemy
    """
    db_name = POSTGRES_DBS.get(domain)
    if not db_name:
        raise ValueError(f"Unknown domain: {domain}. Must be one of {list(POSTGRES_DBS.keys())}")
    
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_HOST}:{POSTGRES_PORT}/{db_name}"
    )


def pg_dsn(domain: str) -> str:
    """
    Retourne une DSN format psycopg2 pour connexion directe.
    
    Args:
        domain: "hr", "crm" ou "erp"
        
    Returns:
        DSN string compatible avec psycopg2.connect()
    """
    db_name = POSTGRES_DBS.get(domain)
    if not db_name:
        raise ValueError(f"Unknown domain: {domain}. Must be one of {list(POSTGRES_DBS.keys())}")
    
    return (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={db_name} "
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )


# ── Neo4j ─────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.environ.get("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.environ.get("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "talan_neo4j")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# ── Environment ───────────────────────────────────────────────────────────────
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")


if __name__ == "__main__":
    # Test configuration
    print("=== ETL Configuration ===")
    print(f"Environment: {ENVIRONMENT}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"\nExcel Files:")
    for domain, path in EXCEL_FILES.items():
        exists = "✓" if path.exists() else "✗"
        print(f"  {exists} {domain.upper()}: {path}")
    
    print(f"\nPostgreSQL:")
    print(f"  Host: {POSTGRES_HOST}:{POSTGRES_PORT}")
    print(f"  User: {POSTGRES_USER}")
    for domain, db in POSTGRES_DBS.items():
        print(f"  {domain.upper()}: {db}")
    
    print(f"\nNeo4j:")
    print(f"  URI: {NEO4J_URI}")
    print(f"  User: {NEO4J_USER}")
    
    print(f"\nLogging:")
    print(f"  Level: {LOG_LEVEL}")
