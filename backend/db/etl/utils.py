"""
utils.py — Utilitaires ETL robustes et réutilisables.

Fonctions :
  - Logging
  - Connexion PostgreSQL (context manager)
  - Lecture Excel (header=1 pour ignorer la ligne-titre)
  - Nettoyage / conversion de types pandas
  - Upsert batch sécurisé (gère pd.NA, NaT, numpy types)
  - Helpers FK : get_valid_ids / filter_fk / nullify_fk
"""

import logging
import sys
from contextlib import contextmanager
from typing import List, Set

import pandas as pd
import psycopg2

try:
    from .config import LOG_LEVEL, pg_dsn
except ImportError:
    from config import LOG_LEVEL, pg_dsn


# ── Logging ───────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


_util_log = get_logger("ETL-UTILS")


# ── Connexion PostgreSQL ──────────────────────────────────────────────────────

@contextmanager
def pg_conn(domain: str):
    """Context manager de connexion psycopg2 pour un domaine (hr/crm/erp)."""
    conn = None
    try:
        conn = psycopg2.connect(pg_dsn(domain))
        conn.autocommit = False
        yield conn
    except psycopg2.Error:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def execute_ddl(conn, ddl_sql: str) -> None:
    """Exécute un bloc DDL (CREATE TABLE, CREATE INDEX, …)."""
    cursor = conn.cursor()
    try:
        cursor.execute(ddl_sql)
        conn.commit()
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ── Lecture Excel ─────────────────────────────────────────────────────────────

def read_sheet(excel_path: str, sheet_name: str) -> pd.DataFrame:
    """
    Lit une feuille Excel.
    header=1 : ignore la ligne-titre (row 0) présente dans tous les fichiers.
    """
    try:
        return pd.read_excel(excel_path, sheet_name=sheet_name, header=1)
    except FileNotFoundError:
        raise FileNotFoundError(f"Fichier introuvable : {excel_path}")
    except ValueError as exc:
        raise ValueError(f"Feuille '{sheet_name}' introuvable dans {excel_path} : {exc}")


# ── Nettoyage / conversion pandas ────────────────────────────────────────────

def clean_str_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Strip + remplace '' par None sur les colonnes texte."""
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"": None, "nan": None, "NaT": None, "None": None})
    return df


def coerce_dates(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Convertit des colonnes en date (erreurs → NaT → None à l'upsert)."""
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def to_int_nullable(df: pd.DataFrame, cols: List[str],
                    lo: int = None, hi: int = None) -> pd.DataFrame:
    """Convertit en Int64 nullable, avec clamp optionnel [lo, hi]."""
    df = df.copy()
    for col in cols:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            if lo is not None or hi is not None:
                s = s.where((s.isna()) | ((s >= (lo or -1e18)) & (s <= (hi or 1e18))))
            df[col] = s.astype("Int64")
    return df


def to_float_nullable(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Convertit en float, NaN → None à l'upsert."""
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── Helpers FK ────────────────────────────────────────────────────────────────

def get_valid_ids(conn, schema_table: str, id_col: str) -> Set[str]:
    """Retourne l'ensemble des valeurs existantes d'une colonne PK/UK."""
    cur = conn.cursor()
    cur.execute(f"SELECT {id_col} FROM {schema_table}")
    ids = {str(row[0]) for row in cur.fetchall()}
    cur.close()
    return ids


def filter_fk(df: pd.DataFrame, col: str, valid_ids: Set[str]) -> pd.DataFrame:
    """
    Supprime les lignes dont col n'est pas dans valid_ids.
    Utilisé quand col est un FK NOT NULL (employee_id, etc.).
    """
    if col not in df.columns:
        return df
    before = len(df)
    mask = df[col].astype(str).isin(valid_ids)
    df = df[mask | df[col].isna()].copy()  # garde aussi les NULL légitimes
    dropped = before - len(df)
    if dropped:
        _util_log.warning(f"  ⚠  filter_fk [{col}] : {dropped} ligne(s) orpheline(s) ignorée(s)")
    return df


def nullify_fk(df: pd.DataFrame, col: str, valid_ids: Set[str]) -> pd.DataFrame:
    """
    Met col à None quand la valeur n'existe pas dans valid_ids.
    Utilisé quand col est un FK nullable (manager_id, approved_by, etc.).
    """
    if col not in df.columns:
        return df
    df = df.copy()
    mask = df[col].notna() & ~df[col].astype(str).isin(valid_ids)
    count = int(mask.sum())
    if count:
        _util_log.warning(f"  ⚠  nullify_fk [{col}] : {count} référence(s) invalide(s) → NULL")
    df.loc[mask, col] = None
    return df


# ── Upsert batch ──────────────────────────────────────────────────────────────

def _py_value(v):
    """Convertit une valeur pandas/numpy en type Python natif pour psycopg2."""
    import numpy as np
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, str) and v in ("NaT", "None", "nan", "<NA>", ""):
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v) if not np.isnan(v) else None
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.to_pydatetime()
    return v


def upsert_dataframe(
    conn,
    df: pd.DataFrame,
    table: str,
    pk_cols: List[str],
    batch_size: int = 500,
) -> int:
    """
    INSERT … ON CONFLICT (pk_cols) DO UPDATE SET …
    Gère pd.NA, NaT, numpy scalars, Timestamps.
    Retourne le nombre de lignes traitées.
    """
    if df is None or df.empty:
        return 0

    cols = list(df.columns)
    conflict_clause = ", ".join(pk_cols)
    update_cols = [c for c in cols if c not in pk_cols]

    if update_cols:
        set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
        on_conflict = f"ON CONFLICT ({conflict_clause}) DO UPDATE SET {set_clause}"
    else:
        on_conflict = f"ON CONFLICT ({conflict_clause}) DO NOTHING"

    col_clause = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f'INSERT INTO {table} ({col_clause}) VALUES ({placeholders}) {on_conflict}'

    cursor = conn.cursor()
    total = 0
    try:
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i: i + batch_size]
            # Apply _py_value at tuple construction time to avoid pandas
            # dtype re-inference (assigning back to df converts None → NaT).
            rows = [
                tuple(_py_value(v) for v in row)
                for row in batch.itertuples(index=False, name=None)
            ]
            cursor.executemany(sql, rows)
            total += len(batch)
        conn.commit()
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        cursor.close()
    return total


def get_row_count(conn, schema_table: str) -> int:
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {schema_table}")
        return cur.fetchone()[0]
    finally:
        cur.close()
