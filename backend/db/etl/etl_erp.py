"""
etl_erp.py — ETL complet pour le domaine ERP (base talan_erp, schéma erp).

Tables chargées (10) :
  erp_suppliers, erp_customers, erp_products, erp_inventory,
  erp_sales_orders, erp_purchase_orders, erp_invoices, erp_payments,
  erp_order_lines, erp_po_lines
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import EXCEL_FILES
from utils import (
    get_logger, pg_conn, execute_ddl, read_sheet,
    clean_str_cols, coerce_dates, to_int_nullable, to_float_nullable,
    get_valid_ids, filter_fk, nullify_fk, upsert_dataframe, get_row_count,
)

log = get_logger("ETL-ERP")
ERP_PATH = EXCEL_FILES["erp"]

# ── DDL ───────────────────────────────────────────────────────────────────────

DDL = """
CREATE SCHEMA IF NOT EXISTS erp;

CREATE TABLE IF NOT EXISTS erp.erp_suppliers (
    supplier_id   VARCHAR(20)  PRIMARY KEY,
    name          VARCHAR(250) NOT NULL,
    country       VARCHAR(80),
    category      VARCHAR(100),
    contact_email VARCHAR(150),
    phone         VARCHAR(40),
    rating        NUMERIC(4,2),
    payment_terms VARCHAR(80),
    created_at    DATE
);

CREATE TABLE IF NOT EXISTS erp.erp_customers (
    customer_id   VARCHAR(20)  PRIMARY KEY,
    account_id    VARCHAR(20),
    name          VARCHAR(250) NOT NULL,
    country       VARCHAR(80),
    industry      VARCHAR(100),
    credit_limit  NUMERIC(16,2),
    payment_terms VARCHAR(80),
    tax_id        VARCHAR(60),
    created_at    DATE
);

CREATE TABLE IF NOT EXISTS erp.erp_products (
    product_id      VARCHAR(20)  PRIMARY KEY,
    name            VARCHAR(250),
    category        VARCHAR(100),
    unit_price      NUMERIC(14,2),
    currency        VARCHAR(10),
    sku             VARCHAR(80),
    supplier_id     VARCHAR(20)  REFERENCES erp.erp_suppliers(supplier_id),
    unit_of_measure VARCHAR(50),
    created_at      DATE
);

CREATE TABLE IF NOT EXISTS erp.erp_inventory (
    inventory_id      VARCHAR(20)  PRIMARY KEY,
    product_id        VARCHAR(20)  REFERENCES erp.erp_products(product_id),
    warehouse_location VARCHAR(150),
    stock_quantity    INTEGER,
    reorder_level     INTEGER,
    unit_cost         NUMERIC(14,2),
    last_updated      DATE
);

CREATE TABLE IF NOT EXISTS erp.erp_sales_orders (
    order_id        VARCHAR(20)  PRIMARY KEY,
    customer_id     VARCHAR(20)  REFERENCES erp.erp_customers(customer_id),
    order_date      DATE,
    delivery_date   DATE,
    amount          NUMERIC(16,2),
    status          VARCHAR(50),
    sales_rep_id    VARCHAR(20),
    currency        VARCHAR(10),
    notes           TEXT,
    delivery_status VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS erp.erp_purchase_orders (
    po_id             VARCHAR(20)  PRIMARY KEY,
    supplier_id       VARCHAR(20)  REFERENCES erp.erp_suppliers(supplier_id),
    order_date        DATE,
    expected_delivery DATE,
    amount            NUMERIC(16,2),
    status            VARCHAR(50),
    approved_by       VARCHAR(20),
    currency          VARCHAR(10),
    warehouse         VARCHAR(150)
);

CREATE TABLE IF NOT EXISTS erp.erp_invoices (
    invoice_id     VARCHAR(20)  PRIMARY KEY,
    customer_id    VARCHAR(20)  REFERENCES erp.erp_customers(customer_id),
    order_id       VARCHAR(20)  REFERENCES erp.erp_sales_orders(order_id),
    amount         NUMERIC(16,2),
    tax_amount     NUMERIC(16,2),
    issue_date     DATE,
    due_date       DATE,
    payment_status VARCHAR(50),
    currency       VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS erp.erp_payments (
    payment_id     VARCHAR(20)  PRIMARY KEY,
    invoice_id     VARCHAR(20)  REFERENCES erp.erp_invoices(invoice_id),
    payment_date   DATE,
    amount         NUMERIC(16,2),
    payment_method VARCHAR(80),
    reference      VARCHAR(150),
    currency       VARCHAR(10),
    bank_account   VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS erp.erp_order_lines (
    order_line_id   VARCHAR(20)  PRIMARY KEY,
    order_id        VARCHAR(20)  REFERENCES erp.erp_sales_orders(order_id),
    product_id      VARCHAR(20)  REFERENCES erp.erp_products(product_id),
    quantity        NUMERIC(10,2),
    unit_price      NUMERIC(14,2),
    discount_pct    NUMERIC(5,2),
    line_total      NUMERIC(16,2),
    currency        VARCHAR(10),
    delivery_status VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS erp.erp_po_lines (
    po_line_id        VARCHAR(20)  PRIMARY KEY,
    po_id             VARCHAR(20)  REFERENCES erp.erp_purchase_orders(po_id),
    product_id        VARCHAR(20)  REFERENCES erp.erp_products(product_id),
    quantity_ordered  NUMERIC(10,2),
    unit_cost         NUMERIC(14,2),
    line_total        NUMERIC(16,2),
    quantity_received NUMERIC(10,2),
    currency          VARCHAR(10),
    expected_delivery DATE,
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_erp_prod_supplier    ON erp.erp_products(supplier_id);
CREATE INDEX IF NOT EXISTS idx_erp_inv_product      ON erp.erp_inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_erp_so_customer      ON erp.erp_sales_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_erp_so_status        ON erp.erp_sales_orders(status);
CREATE INDEX IF NOT EXISTS idx_erp_po_supplier      ON erp.erp_purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_erp_inv_payment      ON erp.erp_invoices(payment_status);
CREATE INDEX IF NOT EXISTS idx_erp_inv_customer     ON erp.erp_invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_erp_pay_invoice      ON erp.erp_payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_erp_ol_order         ON erp.erp_order_lines(order_id);
CREATE INDEX IF NOT EXISTS idx_erp_ol_product       ON erp.erp_order_lines(product_id);
CREATE INDEX IF NOT EXISTS idx_erp_pl_po            ON erp.erp_po_lines(po_id);
CREATE INDEX IF NOT EXISTS idx_erp_pl_product       ON erp.erp_po_lines(product_id);
"""


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_suppliers(conn) -> int:
    log.info("  Chargement des fournisseurs …")
    df = read_sheet(ERP_PATH, "suppliers")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["created_at"])
    df = to_float_nullable(df, ["rating"])
    cols = ["supplier_id", "name", "country", "category", "contact_email",
            "phone", "rating", "payment_terms", "created_at"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["supplier_id"]).drop_duplicates(subset=["supplier_id"])
    n = upsert_dataframe(conn, df, "erp.erp_suppliers", ["supplier_id"])
    log.info(f"    → {n} ligne(s) dans erp_suppliers")
    return n


def load_customers(conn) -> int:
    log.info("  Chargement des clients …")
    df = read_sheet(ERP_PATH, "customers")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["created_at"])
    df = to_float_nullable(df, ["credit_limit"])
    cols = ["customer_id", "account_id", "name", "country", "industry",
            "credit_limit", "payment_terms", "tax_id", "created_at"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["customer_id"]).drop_duplicates(subset=["customer_id"])
    n = upsert_dataframe(conn, df, "erp.erp_customers", ["customer_id"])
    log.info(f"    → {n} ligne(s) dans erp_customers")
    return n


def load_products(conn) -> int:
    log.info("  Chargement des produits …")
    df = read_sheet(ERP_PATH, "products")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["created_at"])
    df = to_float_nullable(df, ["unit_price"])
    valid_suppliers = get_valid_ids(conn, "erp.erp_suppliers", "supplier_id")
    cols = ["product_id", "name", "category", "unit_price", "currency",
            "sku", "supplier_id", "unit_of_measure", "created_at"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["product_id"]).drop_duplicates(subset=["product_id"])
    df = nullify_fk(df, "supplier_id", valid_suppliers)
    n = upsert_dataframe(conn, df, "erp.erp_products", ["product_id"])
    log.info(f"    → {n} ligne(s) dans erp_products")
    return n


def load_inventory(conn) -> int:
    log.info("  Chargement de l'inventaire …")
    try:
        df = read_sheet(ERP_PATH, "inventory")
    except ValueError:
        log.warning("  Feuille 'inventory' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["last_updated"])
    df = to_int_nullable(df, ["stock_quantity", "reorder_level"], lo=0)
    df = to_float_nullable(df, ["unit_cost"])
    valid_products = get_valid_ids(conn, "erp.erp_products", "product_id")
    cols = ["inventory_id", "product_id", "warehouse_location", "stock_quantity",
            "reorder_level", "unit_cost", "last_updated"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["inventory_id"]).drop_duplicates(subset=["inventory_id"])
    df = filter_fk(df, "product_id", valid_products)
    n = upsert_dataframe(conn, df, "erp.erp_inventory", ["inventory_id"])
    log.info(f"    → {n} ligne(s) dans erp_inventory")
    return n


def load_sales_orders(conn) -> int:
    log.info("  Chargement des commandes clients …")
    df = read_sheet(ERP_PATH, "sales_orders")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["order_date", "delivery_date"])
    df = to_float_nullable(df, ["amount"])
    valid_customers = get_valid_ids(conn, "erp.erp_customers", "customer_id")
    cols = ["order_id", "customer_id", "order_date", "delivery_date", "amount",
            "status", "sales_rep_id", "currency", "notes", "delivery_status"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["order_id"]).drop_duplicates(subset=["order_id"])
    df = nullify_fk(df, "customer_id", valid_customers)
    n = upsert_dataframe(conn, df, "erp.erp_sales_orders", ["order_id"])
    log.info(f"    → {n} ligne(s) dans erp_sales_orders")
    return n


def load_purchase_orders(conn) -> int:
    log.info("  Chargement des commandes fournisseurs …")
    df = read_sheet(ERP_PATH, "purchase_orders")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["order_date", "expected_delivery"])
    df = to_float_nullable(df, ["amount"])
    valid_suppliers = get_valid_ids(conn, "erp.erp_suppliers", "supplier_id")
    cols = ["po_id", "supplier_id", "order_date", "expected_delivery", "amount",
            "status", "approved_by", "currency", "warehouse"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["po_id"]).drop_duplicates(subset=["po_id"])
    df = nullify_fk(df, "supplier_id", valid_suppliers)
    n = upsert_dataframe(conn, df, "erp.erp_purchase_orders", ["po_id"])
    log.info(f"    → {n} ligne(s) dans erp_purchase_orders")
    return n


def load_invoices(conn) -> int:
    log.info("  Chargement des factures …")
    df = read_sheet(ERP_PATH, "invoices")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["issue_date", "due_date"])
    df = to_float_nullable(df, ["amount", "tax_amount"])
    valid_customers = get_valid_ids(conn, "erp.erp_customers",    "customer_id")
    valid_orders    = get_valid_ids(conn, "erp.erp_sales_orders", "order_id")
    cols = ["invoice_id", "customer_id", "order_id", "amount", "tax_amount",
            "issue_date", "due_date", "payment_status", "currency"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["invoice_id"]).drop_duplicates(subset=["invoice_id"])
    df = nullify_fk(df, "customer_id", valid_customers)
    df = nullify_fk(df, "order_id",    valid_orders)
    n = upsert_dataframe(conn, df, "erp.erp_invoices", ["invoice_id"])
    log.info(f"    → {n} ligne(s) dans erp_invoices")
    return n


def load_payments(conn) -> int:
    log.info("  Chargement des paiements …")
    df = read_sheet(ERP_PATH, "payments")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["payment_date"])
    df = to_float_nullable(df, ["amount"])
    valid_invoices = get_valid_ids(conn, "erp.erp_invoices", "invoice_id")
    cols = ["payment_id", "invoice_id", "payment_date", "amount",
            "payment_method", "reference", "currency", "bank_account"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["payment_id"]).drop_duplicates(subset=["payment_id"])
    df = nullify_fk(df, "invoice_id", valid_invoices)
    n = upsert_dataframe(conn, df, "erp.erp_payments", ["payment_id"])
    log.info(f"    → {n} ligne(s) dans erp_payments")
    return n


def load_order_lines(conn) -> int:
    log.info("  Chargement des lignes de commande …")
    try:
        df = read_sheet(ERP_PATH, "order_lines")
    except ValueError:
        log.warning("  Feuille 'order_lines' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = to_float_nullable(df, ["quantity", "unit_price", "discount_pct", "line_total"])
    valid_orders   = get_valid_ids(conn, "erp.erp_sales_orders", "order_id")
    valid_products = get_valid_ids(conn, "erp.erp_products",     "product_id")
    cols = ["order_line_id", "order_id", "product_id", "quantity", "unit_price",
            "discount_pct", "line_total", "currency", "delivery_status"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["order_line_id"]).drop_duplicates(subset=["order_line_id"])
    df = filter_fk(df, "order_id",   valid_orders)
    df = nullify_fk(df, "product_id", valid_products)
    n = upsert_dataframe(conn, df, "erp.erp_order_lines", ["order_line_id"])
    log.info(f"    → {n} ligne(s) dans erp_order_lines")
    return n


def load_po_lines(conn) -> int:
    log.info("  Chargement des lignes de commande fournisseur …")
    try:
        df = read_sheet(ERP_PATH, "po_lines")
    except ValueError:
        log.warning("  Feuille 'po_lines' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["expected_delivery"])
    df = to_float_nullable(df, ["quantity_ordered", "unit_cost", "line_total",
                                  "quantity_received"])
    valid_pos      = get_valid_ids(conn, "erp.erp_purchase_orders", "po_id")
    valid_products = get_valid_ids(conn, "erp.erp_products",        "product_id")
    cols = ["po_line_id", "po_id", "product_id", "quantity_ordered", "unit_cost",
            "line_total", "quantity_received", "currency", "expected_delivery", "notes"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["po_line_id"]).drop_duplicates(subset=["po_line_id"])
    df = filter_fk(df, "po_id",     valid_pos)
    df = nullify_fk(df, "product_id", valid_products)
    n = upsert_dataframe(conn, df, "erp.erp_po_lines", ["po_line_id"])
    log.info(f"    → {n} ligne(s) dans erp_po_lines")
    return n


# ── Point d'entrée ────────────────────────────────────────────────────────────

def run():
    log.info("=" * 70)
    log.info("ETL ERP — Démarrage")
    log.info("=" * 70)

    with pg_conn("erp") as conn:
        log.info("DDL : création du schéma et des tables …")
        execute_ddl(conn, DDL)
        log.info("  ✓ DDL appliqué")

        # Ordre respectant les FK
        load_suppliers(conn)
        load_customers(conn)
        load_products(conn)
        load_inventory(conn)
        load_sales_orders(conn)
        load_purchase_orders(conn)
        load_invoices(conn)
        load_payments(conn)
        load_order_lines(conn)
        load_po_lines(conn)

        log.info("\nStatistiques finales :")
        tables = [
            "erp.erp_suppliers", "erp.erp_customers", "erp.erp_products",
            "erp.erp_inventory", "erp.erp_sales_orders", "erp.erp_purchase_orders",
            "erp.erp_invoices", "erp.erp_payments", "erp.erp_order_lines",
            "erp.erp_po_lines",
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

    log.info("\n✅ ETL ERP terminé avec succès.\n")


if __name__ == "__main__":
    run()
