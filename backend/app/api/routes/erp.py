"""ERP API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_erp_db
from app.models.erp_models import Customer, Invoice, Payment, Product, SalesOrder, Supplier
from app.schemas.erp_schemas import (
    CustomerList,
    CustomerRead,
    InvoiceList,
    InvoiceRead,
    PaymentRead,
    ProductRead,
    SalesOrderList,
    SalesOrderRead,
    SupplierRead,
)

router = APIRouter()


# ── Customers ─────────────────────────────────────────────────────────────────

@router.get("/customers", response_model=CustomerList)
def list_customers(
    skip:  int     = Query(0, ge=0),
    limit: int     = Query(50, ge=1, le=200),
    db:    Session = Depends(get_erp_db),
):
    total = db.query(Customer).count()
    items = db.query(Customer).offset(skip).limit(limit).all()
    return CustomerList(total=total, items=items)


@router.get("/customers/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_erp_db)):
    cust = db.get(Customer, customer_id)
    if not cust:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable")
    return cust


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products", response_model=list[ProductRead])
def list_products(
    category: Optional[str] = Query(None),
    skip:     int           = Query(0, ge=0),
    limit:    int           = Query(50, ge=1, le=200),
    db:       Session       = Depends(get_erp_db),
):
    q = db.query(Product)
    if category:
        q = q.filter(Product.category == category)
    return q.offset(skip).limit(limit).all()


# ── Sales Orders ──────────────────────────────────────────────────────────────

@router.get("/orders", response_model=SalesOrderList)
def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id:   Optional[int] = Query(None),
    skip:          int           = Query(0, ge=0),
    limit:         int           = Query(50, ge=1, le=200),
    db:            Session       = Depends(get_erp_db),
):
    q = db.query(SalesOrder)
    if status_filter:
        q = q.filter(SalesOrder.status == status_filter)
    if customer_id is not None:
        q = q.filter(SalesOrder.customer_id == customer_id)
    total = q.count()
    items = q.offset(skip).limit(limit).all()
    return SalesOrderList(total=total, items=items)


# ── Invoices ──────────────────────────────────────────────────────────────────

@router.get("/invoices", response_model=InvoiceList)
def list_invoices(
    payment_status: Optional[str] = Query(None, description="Paid | Pending | Overdue"),
    customer_id:    Optional[int] = Query(None),
    skip:           int           = Query(0, ge=0),
    limit:          int           = Query(50, ge=1, le=200),
    db:             Session       = Depends(get_erp_db),
):
    q = db.query(Invoice)
    if payment_status:
        q = q.filter(Invoice.payment_status == payment_status)
    if customer_id is not None:
        q = q.filter(Invoice.customer_id == customer_id)
    total = q.count()
    items = q.offset(skip).limit(limit).all()
    return InvoiceList(total=total, items=items)


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_erp_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
    return inv


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis/revenue")
def revenue_by_status(db: Session = Depends(get_erp_db)):
    """Résumé du chiffre d'affaires facturé par statut de paiement."""
    from sqlalchemy import func
    rows = (
        db.query(
            Invoice.payment_status,
            func.count(Invoice.invoice_id).label("count"),
            func.sum(Invoice.amount).label("total"),
        )
        .group_by(Invoice.payment_status)
        .all()
    )
    return [
        {"status": r.payment_status, "count": r.count, "total": float(r.total or 0)}
        for r in rows
    ]
