"""ERP SQLAlchemy ORM models — base de données talan_erp."""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Supplier(Base):
    __tablename__ = "erp_suppliers"

    supplier_id:   Mapped[int]            = mapped_column(Integer, primary_key=True)
    name:          Mapped[str]            = mapped_column(String(200), nullable=False)
    category:      Mapped[Optional[str]]  = mapped_column(String(100))
    country:       Mapped[Optional[str]]  = mapped_column(String(100))
    rating:        Mapped[Optional[float]] = mapped_column(Float)
    payment_terms: Mapped[Optional[str]]  = mapped_column(String(50))

    products:        Mapped[List["Product"]]       = relationship(back_populates="supplier")
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="supplier")


class Customer(Base):
    __tablename__ = "erp_customers"

    customer_id:  Mapped[int]            = mapped_column(Integer, primary_key=True)
    account_id:   Mapped[Optional[int]]  = mapped_column(Integer)  # FK cross-db → crm_accounts
    name:         Mapped[str]            = mapped_column(String(200), nullable=False)
    industry:     Mapped[Optional[str]]  = mapped_column(String(100))
    country:      Mapped[Optional[str]]  = mapped_column(String(100))
    credit_limit: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    created_at:   Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())

    sales_orders: Mapped[List["SalesOrder"]] = relationship(back_populates="customer")
    invoices:     Mapped[List["Invoice"]]    = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "erp_products"

    product_id:  Mapped[int]            = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]            = mapped_column(String(200), nullable=False)
    category:    Mapped[Optional[str]]  = mapped_column(String(100))
    unit_price:  Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    supplier_id: Mapped[Optional[int]]  = mapped_column(ForeignKey("erp_suppliers.supplier_id"))
    stock_qty:   Mapped[Optional[int]]  = mapped_column(Integer)
    unit:        Mapped[Optional[str]]  = mapped_column(String(20))

    supplier: Mapped[Optional["Supplier"]] = relationship(back_populates="products")


class SalesOrder(Base):
    __tablename__ = "erp_sales_orders"

    order_id:     Mapped[int]            = mapped_column(Integer, primary_key=True)
    customer_id:  Mapped[Optional[int]]  = mapped_column(ForeignKey("erp_customers.customer_id"))
    order_date:   Mapped[Optional[date]] = mapped_column(Date)
    status:       Mapped[Optional[str]]  = mapped_column(String(30))
    total_amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    currency:     Mapped[Optional[str]]  = mapped_column(String(10))
    notes:        Mapped[Optional[str]]  = mapped_column(Text)

    customer: Mapped[Optional["Customer"]] = relationship(back_populates="sales_orders")
    invoices: Mapped[List["Invoice"]]      = relationship(back_populates="order")


class PurchaseOrder(Base):
    __tablename__ = "erp_purchase_orders"

    po_id:        Mapped[int]            = mapped_column(Integer, primary_key=True)
    supplier_id:  Mapped[Optional[int]]  = mapped_column(ForeignKey("erp_suppliers.supplier_id"))
    order_date:   Mapped[Optional[date]] = mapped_column(Date)
    status:       Mapped[Optional[str]]  = mapped_column(String(30))
    total_amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    currency:     Mapped[Optional[str]]  = mapped_column(String(10))

    supplier: Mapped[Optional["Supplier"]] = relationship(back_populates="purchase_orders")


class Invoice(Base):
    __tablename__ = "erp_invoices"

    invoice_id:     Mapped[int]            = mapped_column(Integer, primary_key=True)
    customer_id:    Mapped[Optional[int]]  = mapped_column(ForeignKey("erp_customers.customer_id"))
    order_id:       Mapped[Optional[int]]  = mapped_column(ForeignKey("erp_sales_orders.order_id"))
    invoice_date:   Mapped[Optional[date]] = mapped_column(Date)
    due_date:       Mapped[Optional[date]] = mapped_column(Date)
    amount:         Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    payment_status: Mapped[Optional[str]]  = mapped_column(String(20))
    currency:       Mapped[Optional[str]]  = mapped_column(String(10))
    created_at:     Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())

    customer: Mapped[Optional["Customer"]]   = relationship(back_populates="invoices")
    order:    Mapped[Optional["SalesOrder"]] = relationship(back_populates="invoices")
    payments: Mapped[List["Payment"]]        = relationship(back_populates="invoice")


class Payment(Base):
    __tablename__ = "erp_payments"

    payment_id:     Mapped[int]            = mapped_column(Integer, primary_key=True)
    invoice_id:     Mapped[Optional[int]]  = mapped_column(ForeignKey("erp_invoices.invoice_id"))
    payment_date:   Mapped[Optional[date]] = mapped_column(Date)
    amount_paid:    Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    payment_method: Mapped[Optional[str]]  = mapped_column(String(50))
    reference:      Mapped[Optional[str]]  = mapped_column(String(100))

    invoice: Mapped[Optional["Invoice"]] = relationship(back_populates="payments")
