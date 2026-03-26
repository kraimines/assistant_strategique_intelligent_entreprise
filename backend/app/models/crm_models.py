"""CRM SQLAlchemy ORM models — base de données talan_crm."""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    __tablename__ = "crm_accounts"

    account_id:     Mapped[int]            = mapped_column(Integer, primary_key=True)
    name:           Mapped[str]            = mapped_column(String(200), nullable=False)
    industry:       Mapped[Optional[str]]  = mapped_column(String(100))
    country:        Mapped[Optional[str]]  = mapped_column(String(100))
    city:           Mapped[Optional[str]]  = mapped_column(String(100))
    annual_revenue: Mapped[Optional[float]] = mapped_column(Float)
    website:        Mapped[Optional[str]]  = mapped_column(String(255))
    phone:          Mapped[Optional[str]]  = mapped_column(String(50))
    created_at:     Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())
    updated_at:     Mapped[datetime]       = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    contacts:      Mapped[List["Contact"]]     = relationship(back_populates="account")
    opportunities: Mapped[List["Opportunity"]] = relationship(back_populates="account")


class Contact(Base):
    __tablename__ = "crm_contacts"

    contact_id: Mapped[int]            = mapped_column(Integer, primary_key=True)
    account_id: Mapped[Optional[int]]  = mapped_column(ForeignKey("crm_accounts.account_id"))
    first_name: Mapped[str]            = mapped_column(String(50), nullable=False)
    last_name:  Mapped[str]            = mapped_column(String(50), nullable=False)
    email:      Mapped[Optional[str]]  = mapped_column(String(150))
    phone:      Mapped[Optional[str]]  = mapped_column(String(50))
    job_title:  Mapped[Optional[str]]  = mapped_column(String(100))
    country:    Mapped[Optional[str]]  = mapped_column(String(100))
    created_at: Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())

    account:    Mapped[Optional["Account"]]    = relationship(back_populates="contacts")
    activities: Mapped[List["Activity"]]       = relationship(back_populates="contact")


class Opportunity(Base):
    __tablename__ = "crm_opportunities"

    opportunity_id:  Mapped[int]            = mapped_column(Integer, primary_key=True)
    account_id:      Mapped[Optional[int]]  = mapped_column(ForeignKey("crm_accounts.account_id"))
    deal_name:       Mapped[str]            = mapped_column(String(200), nullable=False)
    stage:           Mapped[Optional[str]]  = mapped_column(String(50))
    amount:          Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    probability:     Mapped[Optional[float]] = mapped_column(Float)
    close_date:      Mapped[Optional[date]] = mapped_column(Date)
    currency:        Mapped[Optional[str]]  = mapped_column(String(10))
    owner_id:        Mapped[Optional[int]]  = mapped_column(Integer)
    forecast_amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    lost_reason:     Mapped[Optional[str]]  = mapped_column(Text)
    created_at:      Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())

    account:    Mapped[Optional["Account"]] = relationship(back_populates="opportunities")
    activities: Mapped[List["Activity"]]    = relationship(back_populates="opportunity")


class Activity(Base):
    __tablename__ = "crm_activities"

    activity_id:      Mapped[int]            = mapped_column(Integer, primary_key=True)
    contact_id:       Mapped[Optional[int]]  = mapped_column(ForeignKey("crm_contacts.contact_id"))
    opportunity_id:   Mapped[Optional[int]]  = mapped_column(ForeignKey("crm_opportunities.opportunity_id"))
    activity_type:    Mapped[Optional[str]]  = mapped_column(String(50))
    activity_date:    Mapped[Optional[date]] = mapped_column(Date)
    duration_minutes: Mapped[Optional[int]]  = mapped_column(Integer)
    notes:            Mapped[Optional[str]]  = mapped_column(Text)
    created_by:       Mapped[Optional[int]]  = mapped_column(Integer)

    contact:     Mapped[Optional["Contact"]]     = relationship(back_populates="activities")
    opportunity: Mapped[Optional["Opportunity"]] = relationship(back_populates="activities")
