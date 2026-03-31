"""Pydantic schemas — domaine CRM."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr


# ── Account ───────────────────────────────────────────────────────────────────

class AccountBase(BaseModel):
    name:           str
    industry:       Optional[str]     = None
    country:        Optional[str]     = None
    city:           Optional[str]     = None
    annual_revenue: Optional[Decimal] = None
    website:        Optional[str]     = None
    phone:          Optional[str]     = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name:           Optional[str]     = None
    industry:       Optional[str]     = None
    country:        Optional[str]     = None
    city:           Optional[str]     = None
    annual_revenue: Optional[Decimal] = None
    website:        Optional[str]     = None
    phone:          Optional[str]     = None


class AccountRead(AccountBase):
    account_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class AccountList(BaseModel):
    total: int
    items: list[AccountRead]


# ── Contact ───────────────────────────────────────────────────────────────────

class ContactBase(BaseModel):
    first_name: str
    last_name:  str
    email:      Optional[EmailStr] = None
    phone:      Optional[str]      = None
    account_id: Optional[str]      = None
    job_title:  Optional[str]      = None
    country:    Optional[str]      = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: Optional[str]      = None
    last_name:  Optional[str]      = None
    email:      Optional[EmailStr] = None
    phone:      Optional[str]      = None
    account_id: Optional[str]      = None
    job_title:  Optional[str]      = None
    country:    Optional[str]      = None


class ContactRead(ContactBase):
    contact_id: str
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ContactList(BaseModel):
    total: int
    items: list[ContactRead]


# ── Opportunity ───────────────────────────────────────────────────────────────

class OpportunityBase(BaseModel):
    account_id:      Optional[str]     = None
    deal_name:       Optional[str]     = None
    stage:           Optional[str]     = None
    amount:          Optional[Decimal] = None
    probability:     Optional[int]     = None
    close_date:      Optional[date]    = None
    currency:        Optional[str]     = None
    owner_id:        Optional[str]     = None
    forecast_amount: Optional[Decimal] = None
    lost_reason:     Optional[str]     = None


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityUpdate(BaseModel):
    account_id:      Optional[str]     = None
    deal_name:       Optional[str]     = None
    stage:           Optional[str]     = None
    amount:          Optional[Decimal] = None
    probability:     Optional[int]     = None
    close_date:      Optional[date]    = None
    currency:        Optional[str]     = None
    owner_id:        Optional[str]     = None
    forecast_amount: Optional[Decimal] = None
    lost_reason:     Optional[str]     = None


class OpportunityRead(OpportunityBase):
    opportunity_id: str
    created_at:     Optional[datetime] = None
    model_config = {"from_attributes": True}


class OpportunityList(BaseModel):
    total: int
    items: list[OpportunityRead]


# ── Activity ──────────────────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    type:             Optional[str]  = None
    date:             Optional[date] = None
    contact_id:       Optional[str]  = None
    opportunity_id:   Optional[str]  = None
    duration_minutes: Optional[int]  = None
    notes:            Optional[str]  = None
    created_by:       Optional[str]  = None


class ActivityRead(BaseModel):
    activity_id:      str
    type:             Optional[str]  = None
    date:             Optional[date] = None
    contact_id:       Optional[str]  = None
    opportunity_id:   Optional[str]  = None
    duration_minutes: Optional[int]  = None
    notes:            Optional[str]  = None
    created_by:       Optional[str]  = None
    model_config = {"from_attributes": True}
