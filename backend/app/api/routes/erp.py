"""ERP API routes — async SQLAlchemy, full CRUD."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_erp_db, get_current_user, require_role
from app.models.erp_models import Customer, Invoice, Payment, Product, PurchaseOrder, SalesOrder, Supplier
from app.schemas.erp_schemas import (
    CustomerList,
    CustomerRead,
    InvoiceCreate,
    InvoiceList,
    InvoiceRead,
    InvoiceUpdate,
    PaymentCreate,
    PaymentRead,
    ProductList,
    ProductRead,
    SalesOrderCreate,
    SalesOrderList,
    SalesOrderRead,
    SalesOrderUpdate,
    SupplierRead,
)

router = APIRouter()


# ── Suppliers ─────────────────────────────────────────────────────────────────

@router.get("/suppliers", response_model=list[SupplierRead])
async def list_suppliers(
    category: Optional[str] = Query(None),
    skip:     int           = Query(0, ge=0),
    limit:    int           = Query(50, ge=1, le=200),
    db:       AsyncSession  = Depends(get_erp_db),
):
    q = select(Supplier)
    if category:
        q = q.where(Supplier.category == category)
    result = await db.execute(q.offset(skip).limit(limit).order_by(Supplier.name))
    return result.scalars().all()


@router.get("/suppliers/{supplier_id}", response_model=SupplierRead)
async def get_supplier(supplier_id: str, db: AsyncSession = Depends(get_erp_db)):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fournisseur introuvable")
    return supplier


# ── Customers ─────────────────────────────────────────────────────────────────

@router.get("/customers", response_model=CustomerList)
async def list_customers(
    skip:  int           = Query(0, ge=0),
    limit: int           = Query(50, ge=1, le=200),
    db:    AsyncSession  = Depends(get_erp_db),
):
    total_result = await db.execute(select(func.count(Customer.customer_id)))
    total = total_result.scalar_one()
    items_result = await db.execute(
        select(Customer).offset(skip).limit(limit).order_by(Customer.name)
    )
    return CustomerList(total=total, items=items_result.scalars().all())


@router.get("/customers/{customer_id}", response_model=CustomerRead)
async def get_customer(customer_id: str, db: AsyncSession = Depends(get_erp_db)):
    cust = await db.get(Customer, customer_id)
    if not cust:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable")
    return cust


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products", response_model=ProductList)
async def list_products(
    category: Optional[str] = Query(None),
    skip:     int           = Query(0, ge=0),
    limit:    int           = Query(50, ge=1, le=200),
    db:       AsyncSession  = Depends(get_erp_db),
):
    q = select(Product)
    if category:
        q = q.where(Product.category == category)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(q.offset(skip).limit(limit).order_by(Product.name))
    return ProductList(total=total, items=items_result.scalars().all())


@router.get("/products/{product_id}", response_model=ProductRead)
async def get_product(product_id: str, db: AsyncSession = Depends(get_erp_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produit introuvable")
    return product


# ── Sales Orders ──────────────────────────────────────────────────────────────

@router.get("/orders", response_model=SalesOrderList)
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id:   Optional[str] = Query(None),
    skip:          int           = Query(0, ge=0),
    limit:         int           = Query(50, ge=1, le=200),
    db:            AsyncSession  = Depends(get_erp_db),
):
    q = select(SalesOrder)
    if status_filter:
        q = q.where(SalesOrder.status == status_filter)
    if customer_id is not None:
        q = q.where(SalesOrder.customer_id == customer_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(
        q.offset(skip).limit(limit).order_by(SalesOrder.order_date.desc())
    )
    return SalesOrderList(total=total, items=items_result.scalars().all())


@router.get("/orders/{order_id}", response_model=SalesOrderRead)
async def get_order(order_id: str, db: AsyncSession = Depends(get_erp_db)):
    order = await db.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commande introuvable")
    return order


@router.post("/orders", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(get_current_user)])
async def create_order(body: SalesOrderCreate, db: AsyncSession = Depends(get_erp_db)):
    order = SalesOrder(**body.model_dump())
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@router.put("/orders/{order_id}", response_model=SalesOrderRead,
            dependencies=[Depends(require_role("admin", "manager"))])
async def update_order(order_id: str, body: SalesOrderUpdate, db: AsyncSession = Depends(get_erp_db)):
    order = await db.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commande introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(order, field, value)
    await db.commit()
    await db.refresh(order)
    return order


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("admin"))])
async def delete_order(order_id: str, db: AsyncSession = Depends(get_erp_db)):
    order = await db.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commande introuvable")
    await db.delete(order)
    await db.commit()


# ── Invoices ──────────────────────────────────────────────────────────────────

@router.get("/invoices", response_model=InvoiceList)
async def list_invoices(
    payment_status: Optional[str] = Query(None, description="Paid | Pending | Overdue"),
    customer_id:    Optional[str] = Query(None),
    skip:           int           = Query(0, ge=0),
    limit:          int           = Query(50, ge=1, le=200),
    db:             AsyncSession  = Depends(get_erp_db),
):
    q = select(Invoice)
    if payment_status:
        q = q.where(Invoice.payment_status == payment_status)
    if customer_id is not None:
        q = q.where(Invoice.customer_id == customer_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(
        q.offset(skip).limit(limit).order_by(Invoice.issue_date.desc())
    )
    return InvoiceList(total=total, items=items_result.scalars().all())


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(invoice_id: str, db: AsyncSession = Depends(get_erp_db)):
    inv = await db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
    return inv


@router.post("/invoices", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin", "manager"))])
async def create_invoice(body: InvoiceCreate, db: AsyncSession = Depends(get_erp_db)):
    inv = Invoice(**body.model_dump())
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return inv


@router.put("/invoices/{invoice_id}", response_model=InvoiceRead,
            dependencies=[Depends(require_role("admin", "manager"))])
async def update_invoice(invoice_id: str, body: InvoiceUpdate, db: AsyncSession = Depends(get_erp_db)):
    inv = await db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(inv, field, value)
    await db.commit()
    await db.refresh(inv)
    return inv


# ── Payments ──────────────────────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentRead])
async def get_invoice_payments(invoice_id: str, db: AsyncSession = Depends(get_erp_db)):
    inv = await db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
    result = await db.execute(
        select(Payment).where(Payment.invoice_id == invoice_id)
    )
    return result.scalars().all()


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin", "manager"))])
async def add_payment(invoice_id: str, body: PaymentCreate, db: AsyncSession = Depends(get_erp_db)):
    inv = await db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable")
    payment = Payment(invoice_id=invoice_id, **body.model_dump())
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis/revenue")
async def revenue_by_status(db: AsyncSession = Depends(get_erp_db)):
    """Chiffre d'affaires facturé par statut de paiement."""
    result = await db.execute(
        select(
            Invoice.payment_status,
            func.count(Invoice.invoice_id).label("count"),
            func.sum(Invoice.amount).label("total"),
        ).group_by(Invoice.payment_status)
    )
    return [
        {"status": row.payment_status, "count": row.count, "total": float(row.total or 0)}
        for row in result
    ]


@router.get("/kpis/orders-summary")
async def orders_summary(db: AsyncSession = Depends(get_erp_db)):
    """Résumé des commandes par statut."""
    result = await db.execute(
        select(
            SalesOrder.status,
            func.count(SalesOrder.order_id).label("count"),
            func.sum(SalesOrder.amount).label("total"),
        ).group_by(SalesOrder.status)
    )
    return [
        {"status": row.status, "count": row.count, "total": float(row.total or 0)}
        for row in result
    ]
