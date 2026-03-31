"""Pydantic schemas — domaine ERP."""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


# ── Supplier ──────────────────────────────────────────────────────────────────

class SupplierRead(BaseModel):
    supplier_id:   str
    name:          str
    country:       Optional[str]     = None
    category:      Optional[str]     = None
    contact_email: Optional[str]     = None
    phone:         Optional[str]     = None
    rating:        Optional[Decimal] = None
    payment_terms: Optional[str]     = None
    created_at:    Optional[date]    = None
    model_config = {"from_attributes": True}


# ── Customer ──────────────────────────────────────────────────────────────────

class CustomerRead(BaseModel):
    customer_id:   str
    account_id:    Optional[str]     = None
    name:          str
    country:       Optional[str]     = None
    industry:      Optional[str]     = None
    credit_limit:  Optional[Decimal] = None
    payment_terms: Optional[str]     = None
    tax_id:        Optional[str]     = None
    created_at:    Optional[date]    = None
    model_config = {"from_attributes": True}


class CustomerList(BaseModel):
    total: int
    items: list[CustomerRead]


# ── Product ───────────────────────────────────────────────────────────────────

class ProductRead(BaseModel):
    product_id:      str
    name:            Optional[str]     = None
    category:        Optional[str]     = None
    unit_price:      Optional[Decimal] = None
    currency:        Optional[str]     = None
    sku:             Optional[str]     = None
    supplier_id:     Optional[str]     = None
    unit_of_measure: Optional[str]     = None
    created_at:      Optional[date]    = None
    model_config = {"from_attributes": True}


class ProductList(BaseModel):
    total: int
    items: list[ProductRead]


# ── Sales Order ───────────────────────────────────────────────────────────────

class SalesOrderCreate(BaseModel):
    customer_id:     Optional[str]     = None
    order_date:      Optional[date]    = None
    delivery_date:   Optional[date]    = None
    amount:          Optional[Decimal] = None
    status:          Optional[str]     = None
    sales_rep_id:    Optional[str]     = None
    currency:        Optional[str]     = None
    notes:           Optional[str]     = None
    delivery_status: Optional[str]     = None


class SalesOrderUpdate(BaseModel):
    status:          Optional[str]     = None
    delivery_date:   Optional[date]    = None
    amount:          Optional[Decimal] = None
    currency:        Optional[str]     = None
    notes:           Optional[str]     = None
    delivery_status: Optional[str]     = None


class SalesOrderRead(BaseModel):
    order_id:        str
    customer_id:     Optional[str]     = None
    order_date:      Optional[date]    = None
    delivery_date:   Optional[date]    = None
    amount:          Optional[Decimal] = None
    status:          Optional[str]     = None
    sales_rep_id:    Optional[str]     = None
    currency:        Optional[str]     = None
    notes:           Optional[str]     = None
    delivery_status: Optional[str]     = None
    model_config = {"from_attributes": True}


class SalesOrderList(BaseModel):
    total: int
    items: list[SalesOrderRead]


# ── Invoice ───────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    customer_id:    Optional[str]     = None
    order_id:       Optional[str]     = None
    amount:         Optional[Decimal] = None
    tax_amount:     Optional[Decimal] = None
    issue_date:     Optional[date]    = None
    due_date:       Optional[date]    = None
    payment_status: Optional[str]     = None
    currency:       Optional[str]     = None


class InvoiceUpdate(BaseModel):
    due_date:       Optional[date]    = None
    amount:         Optional[Decimal] = None
    tax_amount:     Optional[Decimal] = None
    payment_status: Optional[str]     = None
    currency:       Optional[str]     = None


class InvoiceRead(BaseModel):
    invoice_id:     str
    customer_id:    Optional[str]     = None
    order_id:       Optional[str]     = None
    amount:         Optional[Decimal] = None
    tax_amount:     Optional[Decimal] = None
    issue_date:     Optional[date]    = None
    due_date:       Optional[date]    = None
    payment_status: Optional[str]     = None
    currency:       Optional[str]     = None
    model_config = {"from_attributes": True}


class InvoiceList(BaseModel):
    total: int
    items: list[InvoiceRead]


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    payment_date:   Optional[date]    = None
    amount:         Optional[Decimal] = None
    payment_method: Optional[str]     = None
    reference:      Optional[str]     = None
    currency:       Optional[str]     = None
    bank_account:   Optional[str]     = None


class PaymentRead(BaseModel):
    payment_id:     str
    invoice_id:     Optional[str]     = None
    payment_date:   Optional[date]    = None
    amount:         Optional[Decimal] = None
    payment_method: Optional[str]     = None
    reference:      Optional[str]     = None
    currency:       Optional[str]     = None
    bank_account:   Optional[str]     = None
    model_config = {"from_attributes": True}
