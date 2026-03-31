"""CRM API routes — async SQLAlchemy, full CRUD."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_crm_db, get_current_user, require_role
from app.models.crm_models import Account, Activity, Contact, Opportunity
from app.schemas.crm_schemas import (
    AccountCreate,
    AccountList,
    AccountRead,
    AccountUpdate,
    ActivityCreate,
    ActivityRead,
    ContactCreate,
    ContactList,
    ContactRead,
    ContactUpdate,
    OpportunityCreate,
    OpportunityList,
    OpportunityRead,
    OpportunityUpdate,
)

router = APIRouter()


# ── Accounts ──────────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=AccountList)
async def list_accounts(
    industry: Optional[str] = Query(None),
    skip:     int           = Query(0, ge=0),
    limit:    int           = Query(50, ge=1, le=200),
    db:       AsyncSession  = Depends(get_crm_db),
):
    q = select(Account)
    if industry:
        q = q.where(Account.industry == industry)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(q.offset(skip).limit(limit).order_by(Account.name))
    return AccountList(total=total, items=items_result.scalars().all())


@router.get("/accounts/{account_id}", response_model=AccountRead)
async def get_account(account_id: str, db: AsyncSession = Depends(get_crm_db)):
    acc = await db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    return acc


@router.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin", "manager"))])
async def create_account(body: AccountCreate, db: AsyncSession = Depends(get_crm_db)):
    acc = Account(**body.model_dump())
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


@router.put("/accounts/{account_id}", response_model=AccountRead,
            dependencies=[Depends(require_role("admin", "manager"))])
async def update_account(account_id: str, body: AccountUpdate, db: AsyncSession = Depends(get_crm_db)):
    acc = await db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(acc, field, value)
    await db.commit()
    await db.refresh(acc)
    return acc


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("admin"))])
async def delete_account(account_id: str, db: AsyncSession = Depends(get_crm_db)):
    acc = await db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    await db.delete(acc)
    await db.commit()


@router.get("/accounts/{account_id}/contacts", response_model=list[ContactRead])
async def get_account_contacts(account_id: str, db: AsyncSession = Depends(get_crm_db)):
    result = await db.execute(select(Contact).where(Contact.account_id == account_id))
    return result.scalars().all()


@router.get("/accounts/{account_id}/opportunities", response_model=list[OpportunityRead])
async def get_account_opportunities(account_id: str, db: AsyncSession = Depends(get_crm_db)):
    result = await db.execute(
        select(Opportunity).where(Opportunity.account_id == account_id)
    )
    return result.scalars().all()


# ── Contacts ──────────────────────────────────────────────────────────────────

@router.get("/contacts", response_model=ContactList)
async def list_contacts(
    account_id: Optional[str] = Query(None),
    skip:       int           = Query(0, ge=0),
    limit:      int           = Query(50, ge=1, le=200),
    db:         AsyncSession  = Depends(get_crm_db),
):
    q = select(Contact)
    if account_id is not None:
        q = q.where(Contact.account_id == account_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(q.offset(skip).limit(limit).order_by(Contact.last_name))
    return ContactList(total=total, items=items_result.scalars().all())


@router.get("/contacts/{contact_id}", response_model=ContactRead)
async def get_contact(contact_id: str, db: AsyncSession = Depends(get_crm_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact introuvable")
    return contact


@router.post("/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(get_current_user)])
async def create_contact(body: ContactCreate, db: AsyncSession = Depends(get_crm_db)):
    contact = Contact(**body.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.put("/contacts/{contact_id}", response_model=ContactRead,
            dependencies=[Depends(get_current_user)])
async def update_contact(contact_id: str, body: ContactUpdate, db: AsyncSession = Depends(get_crm_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("admin", "manager"))])
async def delete_contact(contact_id: str, db: AsyncSession = Depends(get_crm_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact introuvable")
    await db.delete(contact)
    await db.commit()


# ── Opportunities ─────────────────────────────────────────────────────────────

@router.get("/opportunities", response_model=OpportunityList)
async def list_opportunities(
    stage:  Optional[str] = Query(None, description="Ex: Qualification, Proposal, Won, Lost"),
    skip:   int           = Query(0, ge=0),
    limit:  int           = Query(50, ge=1, le=200),
    db:     AsyncSession  = Depends(get_crm_db),
):
    q = select(Opportunity)
    if stage:
        q = q.where(Opportunity.stage == stage)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(
        q.offset(skip).limit(limit).order_by(Opportunity.close_date.desc())
    )
    return OpportunityList(total=total, items=items_result.scalars().all())


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
async def get_opportunity(opportunity_id: str, db: AsyncSession = Depends(get_crm_db)):
    opp = await db.get(Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunité introuvable")
    return opp


@router.post("/opportunities", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(get_current_user)])
async def create_opportunity(body: OpportunityCreate, db: AsyncSession = Depends(get_crm_db)):
    opp = Opportunity(**body.model_dump())
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


@router.put("/opportunities/{opportunity_id}", response_model=OpportunityRead,
            dependencies=[Depends(get_current_user)])
async def update_opportunity(
    opportunity_id: str,
    body:           OpportunityUpdate,
    db:             AsyncSession = Depends(get_crm_db),
):
    opp = await db.get(Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunité introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(opp, field, value)
    await db.commit()
    await db.refresh(opp)
    return opp


@router.delete("/opportunities/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("admin", "manager"))])
async def delete_opportunity(opportunity_id: str, db: AsyncSession = Depends(get_crm_db)):
    opp = await db.get(Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunité introuvable")
    await db.delete(opp)
    await db.commit()


# ── Activities ────────────────────────────────────────────────────────────────

@router.post("/activities", response_model=ActivityRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(get_current_user)])
async def create_activity(body: ActivityCreate, db: AsyncSession = Depends(get_crm_db)):
    act = Activity(**body.model_dump())
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return act


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis/pipeline")
async def pipeline_by_stage(db: AsyncSession = Depends(get_crm_db)):
    """Résumé du pipeline commercial par étape."""
    result = await db.execute(
        select(
            Opportunity.stage,
            func.count(Opportunity.opportunity_id).label("count"),
            func.sum(Opportunity.amount).label("total_amount"),
        ).group_by(Opportunity.stage)
    )
    return [
        {"stage": row.stage, "count": row.count, "total_amount": float(row.total_amount or 0)}
        for row in result
    ]


@router.get("/kpis/top-accounts")
async def top_accounts_by_revenue(
    limit: int = Query(10, ge=1, le=50),
    db:    AsyncSession = Depends(get_crm_db),
):
    """Top comptes par chiffre d'affaires annuel."""
    result = await db.execute(
        select(Account.account_id, Account.name, Account.annual_revenue, Account.industry)
        .where(Account.annual_revenue.isnot(None))
        .order_by(Account.annual_revenue.desc())
        .limit(limit)
    )
    return [
        {"account_id": row.account_id, "name": row.name,
         "annual_revenue": row.annual_revenue, "industry": row.industry}
        for row in result
    ]
