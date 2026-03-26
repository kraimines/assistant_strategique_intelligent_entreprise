"""CRM API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_crm_db
from app.models.crm_models import Account, Activity, Contact, Opportunity
from app.schemas.crm_schemas import (
    AccountCreate,
    AccountList,
    AccountRead,
    ActivityRead,
    ContactRead,
    OpportunityList,
    OpportunityRead,
)

router = APIRouter()


# ── Accounts ──────────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=AccountList)
def list_accounts(
    industry: Optional[str] = Query(None),
    skip:     int           = Query(0, ge=0),
    limit:    int           = Query(50, ge=1, le=200),
    db:       Session       = Depends(get_crm_db),
):
    q = db.query(Account)
    if industry:
        q = q.filter(Account.industry == industry)
    total = q.count()
    items = q.offset(skip).limit(limit).all()
    return AccountList(total=total, items=items)


@router.get("/accounts/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_crm_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    return acc


@router.get("/accounts/{account_id}/contacts", response_model=list[ContactRead])
def get_account_contacts(account_id: int, db: Session = Depends(get_crm_db)):
    return db.query(Contact).filter(Contact.account_id == account_id).all()


@router.get("/accounts/{account_id}/opportunities", response_model=list[OpportunityRead])
def get_account_opportunities(account_id: int, db: Session = Depends(get_crm_db)):
    return db.query(Opportunity).filter(Opportunity.account_id == account_id).all()


# ── Opportunities ─────────────────────────────────────────────────────────────

@router.get("/opportunities", response_model=OpportunityList)
def list_opportunities(
    stage:  Optional[str] = Query(None, description="Ex: Qualification, Proposal, Won, Lost"),
    skip:   int           = Query(0, ge=0),
    limit:  int           = Query(50, ge=1, le=200),
    db:     Session       = Depends(get_crm_db),
):
    q = db.query(Opportunity)
    if stage:
        q = q.filter(Opportunity.stage == stage)
    total = q.count()
    items = q.offset(skip).limit(limit).all()
    return OpportunityList(total=total, items=items)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_crm_db)):
    opp = db.get(Opportunity, opportunity_id)
    if not opp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunité introuvable")
    return opp


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis/pipeline")
def pipeline_by_stage(db: Session = Depends(get_crm_db)):
    """Résumé du pipeline commercial par étape."""
    from sqlalchemy import func
    rows = (
        db.query(
            Opportunity.stage,
            func.count(Opportunity.opportunity_id).label("count"),
            func.sum(Opportunity.amount).label("total_amount"),
        )
        .group_by(Opportunity.stage)
        .all()
    )
    return [
        {"stage": r.stage, "count": r.count, "total_amount": float(r.total_amount or 0)}
        for r in rows
    ]
