"""Stats & KPIs routes — role-gated aggregated metrics per domain."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_crm_db, get_erp_db, get_hr_db, require_role
from app.models.crm_models import Account, Opportunity
from app.models.erp_models import Invoice, SalesOrder
from app.models.hr_models import Department, Employee, LeaveRequest, PerformanceReview
from app.schemas.stats_schemas import CRMStats, ERPStats, HRStats, SyncResult

router = APIRouter()


@router.get(
    "/hr",
    response_model=HRStats,
    summary="HR KPIs",
    description=(
        "Aggregated Human Resources metrics: headcount, active leaves, "
        "average performance score, department count. "
        "Requires **admin** or **manager** role."
    ),
    responses={403: {"description": "Insufficient role"}},
    dependencies=[Depends(require_role("admin", "manager"))],
)
async def hr_stats(db: AsyncSession = Depends(get_hr_db)):
    # total active employees
    emp_count = (await db.execute(
        select(func.count(Employee.emp_id)).where(Employee.is_active == True)
    )).scalar_one()

    # active (pending or approved) leave requests
    leave_count = (await db.execute(
        select(func.count(LeaveRequest.leave_id))
        .where(LeaveRequest.status.in_(["Pending", "Approved"]))
    )).scalar_one()

    # average overall performance score
    avg_perf = (await db.execute(
        select(func.avg(PerformanceReview.overall_score))
    )).scalar_one()

    # department count
    dept_count = (await db.execute(
        select(func.count(Department.dept_id))
    )).scalar_one()

    return HRStats(
        total_employees=emp_count,
        active_leaves=leave_count,
        avg_performance_score=round(float(avg_perf), 2) if avg_perf else None,
        departments_count=dept_count,
    )


@router.get(
    "/crm",
    response_model=CRMStats,
    summary="CRM KPIs",
    description=(
        "Aggregated CRM metrics: total accounts, active pipeline opportunities, "
        "pipeline revenue, and closed-won deals. "
        "Requires **admin** or **manager** role."
    ),
    responses={403: {"description": "Insufficient role"}},
    dependencies=[Depends(require_role("admin", "manager"))],
)
async def crm_stats(db: AsyncSession = Depends(get_crm_db)):
    # total accounts
    account_count = (await db.execute(
        select(func.count(Account.account_id))
    )).scalar_one()

    # active opportunities (not closed)
    active_opps = (await db.execute(
        select(func.count(Opportunity.opportunity_id))
        .where(Opportunity.stage.notin_(["Won", "Lost"]))
    )).scalar_one()

    # pipeline revenue (sum of active)
    pipeline_rev = (await db.execute(
        select(func.sum(Opportunity.amount))
        .where(Opportunity.stage.notin_(["Won", "Lost"]))
    )).scalar_one()

    # won deals
    won = (await db.execute(
        select(func.count(Opportunity.opportunity_id))
        .where(Opportunity.stage == "Won")
    )).scalar_one()

    return CRMStats(
        total_accounts=account_count,
        active_opportunities=active_opps,
        revenue_pipeline=float(pipeline_rev or 0),
        won_deals=won,
    )


@router.get(
    "/erp",
    response_model=ERPStats,
    summary="ERP KPIs",
    description=(
        "Aggregated ERP metrics: total sales orders, paid revenue, "
        "unpaid invoice count and amount. "
        "Requires **admin** role only."
    ),
    responses={403: {"description": "Insufficient role — admin only"}},
    dependencies=[Depends(require_role("admin"))],
)
async def erp_stats(db: AsyncSession = Depends(get_erp_db)):
    # total sales orders
    order_count = (await db.execute(
        select(func.count(SalesOrder.order_id))
    )).scalar_one()

    # total paid revenue
    paid_rev = (await db.execute(
        select(func.sum(Invoice.amount))
        .where(Invoice.payment_status == "Paid")
    )).scalar_one()

    # unpaid invoices count
    unpaid_count = (await db.execute(
        select(func.count(Invoice.invoice_id))
        .where(Invoice.payment_status.in_(["Pending", "Overdue"]))
    )).scalar_one()

    # unpaid amount
    unpaid_amt = (await db.execute(
        select(func.sum(Invoice.amount))
        .where(Invoice.payment_status.in_(["Pending", "Overdue"]))
    )).scalar_one()

    return ERPStats(
        total_orders=order_count,
        total_revenue=float(paid_rev or 0),
        unpaid_invoices=unpaid_count,
        unpaid_amount=float(unpaid_amt or 0),
    )


@router.post(
    "/sync-neo4j",
    response_model=SyncResult,
    summary="Trigger Neo4j sync",
    description=(
        "Manually trigger the PostgreSQL → Neo4j graph sync. "
        "The sync runs automatically every night at 02:00. "
        "Requires **admin** role."
    ),
    responses={403: {"description": "Insufficient role — admin only"}},
    dependencies=[Depends(require_role("admin"))],
)
async def trigger_neo4j_sync():
    from app.services.neo4j_sync import sync_all
    try:
        counts = await sync_all()
        return SyncResult(status="ok", counts=counts, message="Neo4j sync completed successfully")
    except Exception as exc:
        return SyncResult(status="error", counts={}, message=str(exc))
