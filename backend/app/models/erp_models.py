e en market analysis"""ERP SQLAlchemy ORM models — base de données talan_erp."""
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Date, ForeignKey,
    Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Supplier(Base):
    __tablename__ = "erp_suppliers"

    supplier_id:   Mapped[str]               = mapped_column(String(20), primary_key=True)
    name:          Mapped[str]               = mapped_column(String(250), nullable=False)
    country:       Mapped[Optional[str]]     = mapped_column(String(80))
    category:      Mapped[Optional[str]]     = mapped_column(String(100))
    contact_email: Mapped[Optional[str]]     = mapped_column(String(150))
    phone:         Mapped[Optional[str]]     = mapped_column(String(40))
    rating:        Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    payment_terms: Mapped[Optional[str]]     = mapped_column(String(80))
    created_at:    Mapped[Optional[date]]    = mapped_column(Date)

    products:        Mapped[List["Product"]]       = relationship(back_populates="supplier")
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="supplier")


class Customer(Base):
    __tablename__ = "erp_customers"

    customer_id:   Mapped[str]               = mapped_column(String(20), primary_key=True)
    account_id:    Mapped[Optional[str]]     = mapped_column(String(20))  # cross-db ref to crm_accounts
    name:          Mapped[str]               = mapped_column(String(250), nullable=False)
    country:       Mapped[Optional[str]]     = mapped_column(String(80))
    industry:      Mapped[Optional[str]]     = mapped_column(String(100))
    credit_limit:  Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    payment_terms: Mapped[Optional[str]]     = mapped_column(String(80))
    tax_id:        Mapped[Optional[str]]     = mapped_column(String(60))
    created_at:    Mapped[Optional[date]]    = mapped_column(Date)

    sales_orders: Mapped[List["SalesOrder"]] = relationship(back_populates="customer")
    invoices:     Mapped[List["Invoice"]]    = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "erp_products"

    product_id:      Mapped[str]               = mapped_column(String(20), primary_key=True)
    name:            Mapped[Optional[str]]     = mapped_column(String(250))
    category:        Mapped[Optional[str]]     = mapped_column(String(100))
    unit_price:      Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    currency:        Mapped[Optional[str]]     = mapped_column(String(10))
    sku:             Mapped[Optional[str]]     = mapped_column(String(80))
    supplier_id:     Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_suppliers.supplier_id"))
    unit_of_measure: Mapped[Optional[str]]     = mapped_column(String(50))
    created_at:      Mapped[Optional[date]]    = mapped_column(Date)

    supplier:  Mapped[Optional["Supplier"]]  = relationship(back_populates="products")
    inventory: Mapped[List["Inventory"]]     = relationship(back_populates="product")


class SalesOrder(Base):
    __tablename__ = "erp_sales_orders"

    order_id:        Mapped[str]               = mapped_column(String(20), primary_key=True)
    customer_id:     Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_customers.customer_id"))
    order_date:      Mapped[Optional[date]]    = mapped_column(Date)
    delivery_date:   Mapped[Optional[date]]    = mapped_column(Date)
    amount:          Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    status:          Mapped[Optional[str]]     = mapped_column(String(50))
    sales_rep_id:    Mapped[Optional[str]]     = mapped_column(String(20))
    currency:        Mapped[Optional[str]]     = mapped_column(String(10))
    notes:           Mapped[Optional[str]]     = mapped_column(Text)
    delivery_status: Mapped[Optional[str]]     = mapped_column(String(50))

    customer:    Mapped[Optional["Customer"]] = relationship(back_populates="sales_orders")
    invoices:    Mapped[List["Invoice"]]      = relationship(back_populates="order")
    order_lines: Mapped[List["OrderLine"]]    = relationship(back_populates="order")


class PurchaseOrder(Base):
    __tablename__ = "erp_purchase_orders"

    po_id:             Mapped[str]               = mapped_column(String(20), primary_key=True)
    supplier_id:       Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_suppliers.supplier_id"))
    order_date:        Mapped[Optional[date]]    = mapped_column(Date)
    expected_delivery: Mapped[Optional[date]]    = mapped_column(Date)
    amount:            Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    status:            Mapped[Optional[str]]     = mapped_column(String(50))
    approved_by:       Mapped[Optional[str]]     = mapped_column(String(20))
    currency:          Mapped[Optional[str]]     = mapped_column(String(10))
    warehouse:         Mapped[Optional[str]]     = mapped_column(String(150))

    supplier:  Mapped[Optional["Supplier"]] = relationship(back_populates="purchase_orders")
    po_lines:  Mapped[List["POLine"]]       = relationship(back_populates="purchase_order")


class Invoice(Base):
    __tablename__ = "erp_invoices"

    invoice_id:     Mapped[str]               = mapped_column(String(20), primary_key=True)
    customer_id:    Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_customers.customer_id"))
    order_id:       Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_sales_orders.order_id"))
    amount:         Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    tax_amount:     Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    issue_date:     Mapped[Optional[date]]    = mapped_column(Date)
    due_date:       Mapped[Optional[date]]    = mapped_column(Date)
    payment_status: Mapped[Optional[str]]     = mapped_column(String(50))
    currency:       Mapped[Optional[str]]     = mapped_column(String(10))

    customer: Mapped[Optional["Customer"]]   = relationship(back_populates="invoices")
    order:    Mapped[Optional["SalesOrder"]] = relationship(back_populates="invoices")
    payments: Mapped[List["Payment"]]        = relationship(back_populates="invoice")


class Payment(Base):
    __tablename__ = "erp_payments"

    payment_id:     Mapped[str]               = mapped_column(String(20), primary_key=True)
    invoice_id:     Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_invoices.invoice_id"))
    payment_date:   Mapped[Optional[date]]    = mapped_column(Date)
    amount:         Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    payment_method: Mapped[Optional[str]]     = mapped_column(String(80))
    reference:      Mapped[Optional[str]]     = mapped_column(String(150))
    currency:       Mapped[Optional[str]]     = mapped_column(String(10))
    bank_account:   Mapped[Optional[str]]     = mapped_column(String(100))

    invoice: Mapped[Optional["Invoice"]] = relationship(back_populates="payments")


class Inventory(Base):
    __tablename__ = "erp_inventory"

    inventory_id:       Mapped[str]               = mapped_column(String(20), primary_key=True)
    product_id:         Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_products.product_id"))
    warehouse_location: Mapped[Optional[str]]     = mapped_column(String(150))
    stock_quantity:     Mapped[Optional[int]]     = mapped_column(Integer)
    reorder_level:      Mapped[Optional[int]]     = mapped_column(Integer)
    unit_cost:          Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    last_updated:       Mapped[Optional[date]]    = mapped_column(Date)

    product: Mapped[Optional["Product"]] = relationship(back_populates="inventory")


class OrderLine(Base):
    __tablename__ = "erp_order_lines"

    order_line_id:   Mapped[str]               = mapped_column(String(20), primary_key=True)
    order_id:        Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_sales_orders.order_id"))
    product_id:      Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_products.product_id"))
    quantity:        Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    unit_price:      Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    discount_pct:    Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    line_total:      Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    currency:        Mapped[Optional[str]]     = mapped_column(String(10))
    delivery_status: Mapped[Optional[str]]     = mapped_column(String(50))

    order:   Mapped[Optional["SalesOrder"]] = relationship(back_populates="order_lines")


class POLine(Base):
    __tablename__ = "erp_po_lines"

    po_line_id:        Mapped[str]               = mapped_column(String(20), primary_key=True)
    po_id:             Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_purchase_orders.po_id"))
    product_id:        Mapped[Optional[str]]     = mapped_column(ForeignKey("erp_products.product_id"))
    quantity_ordered:  Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    unit_cost:         Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    line_total:        Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    quantity_received: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    currency:          Mapped[Optional[str]]     = mapped_column(String(10))
    expected_delivery: Mapped[Optional[date]]    = mapped_column(Date)
    notes:             Mapped[Optional[str]]     = mapped_column(Text)

    purchase_order: Mapped[Optional["PurchaseOrder"]] = relationship(back_populates="po_lines")
