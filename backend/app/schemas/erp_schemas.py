"""Pydantic schemas — domaine ERP."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


# ── Supplier ──────────────────────────────────────────────────────────────────

class SupplierRead(BaseModel):
    supplier_id:   int
    name:          str
    category:      Optional[str]   = None
    country:       Optional[str]   = None
    rating:        Optional[float] = None
    payment_terms: Optional[str]   = None
    model_config = {"from_attributes": True}


# ── Customer ──────────────────────────────────────────────────────────────────

class CustomerRead(BaseModel):
    customer_id:  int
    account_id:   Optional[int]   = None
    name:         str
    industry:     Optional[str]   = None
    country:      Optional[str]   = None
    credit_limit: Optional[float] = None
    created_at:   datetime
    model_config = {"from_attributes": True}


class CustomerList(BaseModel):
    total: int
    items: list[CustomerRead]


# ── Product ───────────────────────────────────────────────────────────────────

class ProductRead(BaseModel):
    product_id:  int
    name:        str
    category:    Optional[str]   = None
    unit_price:  Optional[float] = None
    supplier_id: Optional[int]   = None
    stock_qty:   Optional[int]   = None
    unit:        Optional[str]   = None
    model_config = {"from_attributes": True}


# ── Sales Order ───────────────────────────────────────────────────────────────

class SalesOrderRead(BaseModel):
    order_id:     int
    customer_id:  Optional[int]   = None
    order_date:   Optional[date]  = None
    status:       Optional[str]   = None
    total_amount: Optional[float] = None
    currency:     Optional[str]   = None
    model_config = {"from_attributes": True}


class SalesOrderList(BaseModel):
    total: int
    items: list[SalesOrderRead]


# ── Invoice ───────────────────────────────────────────────────────────────────

class InvoiceRead(BaseModel):
    invoice_id:     int
    customer_id:    Optional[int]   = None
    order_id:       Optional[int]   = None
    invoice_date:   Optional[date]  = None
    due_date:       Optional[date]  = None
    amount:         Optional[float] = None
    payment_status: Optional[str]   = None
    currency:       Optional[str]   = None
    created_at:     datetime
    model_config = {"from_attributes": True}


class InvoiceList(BaseModel):
    total: int
    items: list[InvoiceRead]


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentRead(BaseModel):
    payment_id:     int
    invoice_id:     Optional[int]   = None
    payment_date:   Optional[date]  = None
    amount_paid:    Optional[float] = None
    payment_method: Optional[str]   = None
    reference:      Optional[str]   = None
    model_config = {"from_attributes": True}
