"""CRM SQLAlchemy ORM models — base de données talan_crm."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    __tablename__ = "crm_accounts"

    account_id:     Mapped[str]               = mapped_column(String(20), primary_key=True)
    name:           Mapped[str]               = mapped_column(String(250), nullable=False)
    industry:       Mapped[Optional[str]]     = mapped_column(String(100))
    country:        Mapped[Optional[str]]     = mapped_column(String(80))
    annual_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    website:        Mapped[Optional[str]]     = mapped_column(String(250))
    phone:          Mapped[Optional[str]]     = mapped_column(String(40))
    city:           Mapped[Optional[str]]     = mapped_column(String(80))
    created_at:     Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at:     Mapped[Optional[datetime]] = mapped_column(DateTime)

    contacts:      Mapped[List["Contact"]]     = relationship(back_populates="account")
    opportunities: Mapped[List["Opportunity"]] = relationship(back_populates="account")


class Contact(Base):
    __tablename__ = "crm_contacts"

    contact_id: Mapped[str]               = mapped_column(String(20), primary_key=True)
    first_name: Mapped[str]               = mapped_column(String(80), nullable=False)
    last_name:  Mapped[str]               = mapped_column(String(80), nullable=False)
    email:      Mapped[Optional[str]]     = mapped_column(String(150))
    phone:      Mapped[Optional[str]]     = mapped_column(String(40))
    account_id: Mapped[Optional[str]]     = mapped_column(ForeignKey("crm_accounts.account_id"))
    job_title:  Mapped[Optional[str]]     = mapped_column(String(150))
    country:    Mapped[Optional[str]]     = mapped_column(String(80))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    account:    Mapped[Optional["Account"]] = relationship(back_populates="contacts")
    activities: Mapped[List["Activity"]]    = relationship(back_populates="contact")


class Opportunity(Base):
    __tablename__ = "crm_opportunities"

    opportunity_id:  Mapped[str]               = mapped_column(String(20), primary_key=True)
    account_id:      Mapped[Optional[str]]     = mapped_column(ForeignKey("crm_accounts.account_id"))
    deal_name:       Mapped[Optional[str]]     = mapped_column(String(250))
    stage:           Mapped[Optional[str]]     = mapped_column(String(80))
    amount:          Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    probability:     Mapped[Optional[int]]     = mapped_column(Integer)
    close_date:      Mapped[Optional[date]]    = mapped_column(Date)
    currency:        Mapped[Optional[str]]     = mapped_column(String(10))
    owner_id:        Mapped[Optional[str]]     = mapped_column(String(20))
    created_at:      Mapped[Optional[datetime]] = mapped_column(DateTime)
    forecast_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    lost_reason:     Mapped[Optional[str]]     = mapped_column(String(250))

    account:    Mapped[Optional["Account"]] = relationship(back_populates="opportunities")
    activities: Mapped[List["Activity"]]    = relationship(back_populates="opportunity")


class Activity(Base):
    __tablename__ = "crm_activities"

    activity_id:      Mapped[str]           = mapped_column(String(20), primary_key=True)
    type:             Mapped[Optional[str]] = mapped_column(String(80))
    date:             Mapped[Optional[date]] = mapped_column(Date)
    contact_id:       Mapped[Optional[str]] = mapped_column(ForeignKey("crm_contacts.contact_id"))
    opportunity_id:   Mapped[Optional[str]] = mapped_column(ForeignKey("crm_opportunities.opportunity_id"))
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    notes:            Mapped[Optional[str]] = mapped_column(Text)
    created_by:       Mapped[Optional[str]] = mapped_column(String(20))

    contact:     Mapped[Optional["Contact"]]     = relationship(back_populates="activities")
    opportunity: Mapped[Optional["Opportunity"]] = relationship(back_populates="activities")


class Lead(Base):
    __tablename__ = "crm_leads"

    lead_id:     Mapped[str]               = mapped_column(String(20), primary_key=True)
    name:        Mapped[Optional[str]]     = mapped_column(String(200))
    email:       Mapped[Optional[str]]     = mapped_column(String(150))
    company:     Mapped[Optional[str]]     = mapped_column(String(200))
    phone:       Mapped[Optional[str]]     = mapped_column(String(40))
    source:      Mapped[Optional[str]]     = mapped_column(String(100))
    status:      Mapped[Optional[str]]     = mapped_column(String(50))
    country:     Mapped[Optional[str]]     = mapped_column(String(80))
    industry:    Mapped[Optional[str]]     = mapped_column(String(100))
    created_at:  Mapped[Optional[datetime]] = mapped_column(DateTime)
    lost_reason: Mapped[Optional[str]]     = mapped_column(String(250))
