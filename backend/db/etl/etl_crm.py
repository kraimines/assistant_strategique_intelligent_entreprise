"""
etl_crm.py — ETL complet pour le domaine CRM (base talan_crm, schéma crm).

Tables chargées (6) :
  crm_accounts, crm_contacts, crm_leads, crm_opportunities,
  crm_activities, crm_revenue_history
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import EXCEL_FILES
from utils import (
    get_logger, pg_conn, execute_ddl, read_sheet,
    clean_str_cols, coerce_dates, to_int_nullable, to_float_nullable,
    get_valid_ids, nullify_fk, upsert_dataframe, get_row_count,
)

log = get_logger("ETL-CRM")
CRM_PATH = EXCEL_FILES["crm"]

# ── DDL ───────────────────────────────────────────────────────────────────────

DDL = """
CREATE SCHEMA IF NOT EXISTS crm;

CREATE TABLE IF NOT EXISTS crm.crm_accounts (
    account_id     VARCHAR(20)  PRIMARY KEY,
    name           VARCHAR(250) NOT NULL,
    industry       VARCHAR(100),
    country        VARCHAR(80),
    annual_revenue NUMERIC(18,2),
    website        VARCHAR(250),
    phone          VARCHAR(40),
    city           VARCHAR(80),
    created_at     TIMESTAMP,
    updated_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm.crm_contacts (
    contact_id VARCHAR(20)  PRIMARY KEY,
    first_name VARCHAR(80)  NOT NULL,
    last_name  VARCHAR(80)  NOT NULL,
    email      VARCHAR(150),
    phone      VARCHAR(40),
    account_id VARCHAR(20)  REFERENCES crm.crm_accounts(account_id),
    job_title  VARCHAR(150),
    country    VARCHAR(80),
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm.crm_leads (
    lead_id     VARCHAR(20)  PRIMARY KEY,
    name        VARCHAR(200),
    email       VARCHAR(150),
    company     VARCHAR(200),
    phone       VARCHAR(40),
    source      VARCHAR(100),
    status      VARCHAR(50),
    country     VARCHAR(80),
    industry    VARCHAR(100),
    created_at  TIMESTAMP,
    lost_reason VARCHAR(250)
);

CREATE TABLE IF NOT EXISTS crm.crm_opportunities (
    opportunity_id  VARCHAR(20)  PRIMARY KEY,
    account_id      VARCHAR(20)  REFERENCES crm.crm_accounts(account_id),
    deal_name       VARCHAR(250),
    stage           VARCHAR(80),
    amount          NUMERIC(16,2),
    probability     INTEGER,
    close_date      DATE,
    currency        VARCHAR(10),
    owner_id        VARCHAR(20),
    created_at      TIMESTAMP,
    forecast_amount NUMERIC(16,2),
    lost_reason     VARCHAR(250)
);

CREATE TABLE IF NOT EXISTS crm.crm_activities (
    activity_id      VARCHAR(20)  PRIMARY KEY,
    type             VARCHAR(80),
    date             DATE,
    contact_id       VARCHAR(20)  REFERENCES crm.crm_contacts(contact_id),
    opportunity_id   VARCHAR(20)  REFERENCES crm.crm_opportunities(opportunity_id),
    duration_minutes INTEGER,
    notes            TEXT,
    created_by       VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS crm.crm_revenue_history (
    revenue_id        VARCHAR(20)  PRIMARY KEY,
    account_id        VARCHAR(20)  REFERENCES crm.crm_accounts(account_id),
    year_month        VARCHAR(10),
    revenue           NUMERIC(18,2),
    recurring_revenue NUMERIC(18,2),
    new_revenue       NUMERIC(18,2),
    currency          VARCHAR(10),
    source            VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_crm_contact_account ON crm.crm_contacts(account_id);
CREATE INDEX IF NOT EXISTS idx_crm_opp_account     ON crm.crm_opportunities(account_id);
CREATE INDEX IF NOT EXISTS idx_crm_opp_stage       ON crm.crm_opportunities(stage);
CREATE INDEX IF NOT EXISTS idx_crm_act_contact     ON crm.crm_activities(contact_id);
CREATE INDEX IF NOT EXISTS idx_crm_act_opp         ON crm.crm_activities(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_crm_act_date        ON crm.crm_activities(date);
CREATE INDEX IF NOT EXISTS idx_crm_rev_account     ON crm.crm_revenue_history(account_id);
CREATE INDEX IF NOT EXISTS idx_crm_rev_yearmonth   ON crm.crm_revenue_history(year_month);
CREATE INDEX IF NOT EXISTS idx_crm_lead_status     ON crm.crm_leads(status);
"""


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_accounts(conn) -> int:
    log.info("  Chargement des comptes …")
    df = read_sheet(CRM_PATH, "accounts")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["created_at", "updated_at"])
    df = to_float_nullable(df, ["annual_revenue"])
    cols = ["account_id", "name", "industry", "country", "annual_revenue",
            "website", "phone", "city", "created_at", "updated_at"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["account_id"]).drop_duplicates(subset=["account_id"])
    n = upsert_dataframe(conn, df, "crm.crm_accounts", ["account_id"])
    log.info(f"    → {n} ligne(s) dans crm_accounts")
    return n


def load_contacts(conn) -> int:
    log.info("  Chargement des contacts …")
    df = read_sheet(CRM_PATH, "contacts")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["created_at"])
    valid_accounts = get_valid_ids(conn, "crm.crm_accounts", "account_id")
    cols = ["contact_id", "first_name", "last_name", "email", "phone",
            "account_id", "job_title", "country", "created_at"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["contact_id"]).drop_duplicates(subset=["contact_id"])
    df = nullify_fk(df, "account_id", valid_accounts)
    n = upsert_dataframe(conn, df, "crm.crm_contacts", ["contact_id"])
    log.info(f"    → {n} ligne(s) dans crm_contacts")
    return n


def load_leads(conn) -> int:
    log.info("  Chargement des leads …")
    try:
        df = read_sheet(CRM_PATH, "leads")
    except ValueError:
        log.warning("  Feuille 'leads' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["created_at"])
    cols = ["lead_id", "name", "email", "company", "phone", "source",
            "status", "country", "industry", "created_at", "lost_reason"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["lead_id"]).drop_duplicates(subset=["lead_id"])
    n = upsert_dataframe(conn, df, "crm.crm_leads", ["lead_id"])
    log.info(f"    → {n} ligne(s) dans crm_leads")
    return n


def load_opportunities(conn) -> int:
    log.info("  Chargement des opportunités …")
    df = read_sheet(CRM_PATH, "opportunities")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["close_date", "created_at"])
    df = to_float_nullable(df, ["amount", "forecast_amount"])
    df = to_int_nullable(df, ["probability"], lo=0, hi=100)
    valid_accounts = get_valid_ids(conn, "crm.crm_accounts", "account_id")
    cols = ["opportunity_id", "account_id", "deal_name", "stage", "amount",
            "probability", "close_date", "currency", "owner_id", "created_at",
            "forecast_amount", "lost_reason"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["opportunity_id"]).drop_duplicates(subset=["opportunity_id"])
    df = nullify_fk(df, "account_id", valid_accounts)
    n = upsert_dataframe(conn, df, "crm.crm_opportunities", ["opportunity_id"])
    log.info(f"    → {n} ligne(s) dans crm_opportunities")
    return n


def load_activities(conn) -> int:
    log.info("  Chargement des activités …")
    df = read_sheet(CRM_PATH, "activities")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["date"])
    df = to_int_nullable(df, ["duration_minutes"], lo=0)
    valid_contacts = get_valid_ids(conn, "crm.crm_contacts",     "contact_id")
    valid_opps     = get_valid_ids(conn, "crm.crm_opportunities", "opportunity_id")
    cols = ["activity_id", "type", "date", "contact_id", "opportunity_id",
            "duration_minutes", "notes", "created_by"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["activity_id"]).drop_duplicates(subset=["activity_id"])
    df = nullify_fk(df, "contact_id",     valid_contacts)
    df = nullify_fk(df, "opportunity_id", valid_opps)
    n = upsert_dataframe(conn, df, "crm.crm_activities", ["activity_id"])
    log.info(f"    → {n} ligne(s) dans crm_activities")
    return n


def load_revenue_history(conn) -> int:
    log.info("  Chargement de l'historique revenus …")
    try:
        df = read_sheet(CRM_PATH, "revenue_history")
    except ValueError:
        log.warning("  Feuille 'revenue_history' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = to_float_nullable(df, ["revenue", "recurring_revenue", "new_revenue"])
    valid_accounts = get_valid_ids(conn, "crm.crm_accounts", "account_id")
    cols = ["revenue_id", "account_id", "year_month", "revenue",
            "recurring_revenue", "new_revenue", "currency", "source"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["revenue_id"]).drop_duplicates(subset=["revenue_id"])
    df = nullify_fk(df, "account_id", valid_accounts)
    n = upsert_dataframe(conn, df, "crm.crm_revenue_history", ["revenue_id"])
    log.info(f"    → {n} ligne(s) dans crm_revenue_history")
    return n


# ── Point d'entrée ────────────────────────────────────────────────────────────

def run():
    log.info("=" * 70)
    log.info("ETL CRM — Démarrage")
    log.info("=" * 70)

    with pg_conn("crm") as conn:
        log.info("DDL : création du schéma et des tables …")
        execute_ddl(conn, DDL)
        log.info("  ✓ DDL appliqué")

        load_accounts(conn)
        load_contacts(conn)
        load_leads(conn)
        load_opportunities(conn)
        load_activities(conn)
        load_revenue_history(conn)

        log.info("\nStatistiques finales :")
        tables = [
            "crm.crm_accounts", "crm.crm_contacts", "crm.crm_leads",
            "crm.crm_opportunities", "crm.crm_activities", "crm.crm_revenue_history",
        ]
        total = 0
        for t in tables:
            try:
                n = get_row_count(conn, t)
                total += n
                log.info(f"  {t}: {n} lignes")
            except Exception:
                pass
        log.info(f"  TOTAL : {total} lignes")

    log.info("\n✅ ETL CRM terminé avec succès.\n")


if __name__ == "__main__":
    run()
