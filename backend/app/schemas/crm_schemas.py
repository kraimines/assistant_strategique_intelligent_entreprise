"""Pydantic schemas — domaine CRM."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


# ── Account ───────────────────────────────────────────────────────────────────

class AccountBase(BaseModel):
    name:           str
    industry:       Optional[str]   = None
    country:        Optional[str]   = None
    city:           Optional[str]   = None
    annual_revenue: Optional[float] = None
    website:        Optional[str]   = None
    phone:          Optional[str]   = None


class AccountCreate(AccountBase):
    pass


class AccountRead(AccountBase):
    account_id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AccountList(BaseModel):
    total: int
    items: list[AccountRead]


# ── Contact ───────────────────────────────────────────────────────────────────

class ContactBase(BaseModel):
    account_id: Optional[int]      = None
    first_name: str
    last_name:  str
    email:      Optional[EmailStr] = None
    phone:      Optional[str]      = None
    job_title:  Optional[str]      = None
    country:    Optional[str]      = None


class ContactRead(ContactBase):
    contact_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Opportunity ───────────────────────────────────────────────────────────────

class OpportunityBase(BaseModel):
    account_id:      Optional[int]   = None
    deal_name:       str
    stage:           Optional[str]   = None
    amount:          Optional[float] = None
    probability:     Optional[float] = None
    close_date:      Optional[date]  = None
    currency:        Optional[str]   = None
    forecast_amount: Optional[float] = None
    lost_reason:     Optional[str]   = None


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityRead(OpportunityBase):
    opportunity_id: int
    created_at:     datetime
    model_config = {"from_attributes": True}


class OpportunityList(BaseModel):
    total: int
    items: list[OpportunityRead]


# ── Activity ──────────────────────────────────────────────────────────────────

class ActivityRead(BaseModel):
    activity_id:      int
    contact_id:       Optional[int]  = None
    opportunity_id:   Optional[int]  = None
    activity_type:    Optional[str]  = None
    activity_date:    Optional[date] = None
    duration_minutes: Optional[int]  = None
    notes:            Optional[str]  = None
    model_config = {"from_attributes": True}
