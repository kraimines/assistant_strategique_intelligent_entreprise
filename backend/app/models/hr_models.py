"""HR SQLAlchemy ORM models — base de données talan_hr."""
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Date, ForeignKey,
    Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Department(Base):
    __tablename__ = "hr_departments"

    department_id:   Mapped[str]            = mapped_column(String(20), primary_key=True)
    department_name: Mapped[str]            = mapped_column(String(150), nullable=False)
    cost_center:     Mapped[Optional[str]]  = mapped_column(String(30))
    location:        Mapped[Optional[str]]  = mapped_column(String(150))
    budget:          Mapped[Optional[int]]  = mapped_column(BigInteger)
    manager_id:      Mapped[Optional[str]]  = mapped_column(String(20))

    employees: Mapped[List["Employee"]] = relationship(back_populates="department")
    projects:  Mapped[List["Project"]]  = relationship(back_populates="department")


class Employee(Base):
    __tablename__ = "hr_employees"

    employee_id:             Mapped[str]                    = mapped_column(String(20), primary_key=True)
    first_name:              Mapped[str]                    = mapped_column(String(80), nullable=False)
    last_name:               Mapped[str]                    = mapped_column(String(80), nullable=False)
    email:                   Mapped[str]                    = mapped_column(String(150), nullable=False, unique=True)
    phone:                   Mapped[Optional[str]]          = mapped_column(String(40))
    role:                    Mapped[Optional[str]]          = mapped_column(String(150))
    department_id:           Mapped[Optional[str]]          = mapped_column(ForeignKey("hr_departments.department_id"))
    hire_date:               Mapped[Optional[date]]         = mapped_column(Date)
    salary:                  Mapped[Optional[Decimal]]      = mapped_column(Numeric(14, 2))
    manager_id:              Mapped[Optional[str]]          = mapped_column(String(20))
    contract_type:           Mapped[Optional[str]]          = mapped_column(String(50))
    country:                 Mapped[Optional[str]]          = mapped_column(String(80))
    city:                    Mapped[Optional[str]]          = mapped_column(String(80))
    hourly_cost:             Mapped[Optional[Decimal]]      = mapped_column(Numeric(10, 2))
    capacity_hours_per_week: Mapped[Optional[int]]          = mapped_column(Integer)

    department: Mapped[Optional["Department"]]       = relationship(back_populates="employees")
    skills:     Mapped[List["Skill"]]                = relationship(back_populates="employee")
    reviews:    Mapped[List["PerformanceReview"]]    = relationship(back_populates="employee")
    leaves:     Mapped[List["LeaveRequest"]]         = relationship(back_populates="employee")


class Skill(Base):
    __tablename__ = "hr_skills"

    skill_id:         Mapped[str]            = mapped_column(String(20), primary_key=True)
    employee_id:      Mapped[str]            = mapped_column(ForeignKey("hr_employees.employee_id"), nullable=False)
    skill_name:       Mapped[str]            = mapped_column(String(150), nullable=False)
    level:            Mapped[Optional[str]]  = mapped_column(String(50))
    years_experience: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1))
    certified:        Mapped[Optional[str]]  = mapped_column(String(30))
    last_assessed:    Mapped[Optional[date]] = mapped_column(Date)

    employee: Mapped["Employee"] = relationship(back_populates="skills")


class Project(Base):
    __tablename__ = "hr_projects"

    project_id:         Mapped[str]            = mapped_column(String(20), primary_key=True)
    project_name:       Mapped[str]            = mapped_column(String(250), nullable=False)
    client_account_id:  Mapped[Optional[str]]  = mapped_column(String(20))
    department_id:      Mapped[Optional[str]]  = mapped_column(ForeignKey("hr_departments.department_id"))
    start_date:         Mapped[Optional[date]] = mapped_column(Date)
    end_date:           Mapped[Optional[date]] = mapped_column(Date)
    budget:             Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    status:             Mapped[Optional[str]]  = mapped_column(String(50))
    project_manager_id: Mapped[Optional[str]]  = mapped_column(String(20))
    currency:           Mapped[Optional[str]]  = mapped_column(String(10))
    required_skills:    Mapped[Optional[str]]  = mapped_column(Text)

    department: Mapped[Optional["Department"]] = relationship(back_populates="projects")


class LeaveRequest(Base):
    __tablename__ = "hr_leave_requests"

    leave_id:       Mapped[str]            = mapped_column(String(20), primary_key=True)
    employee_id:    Mapped[str]            = mapped_column(ForeignKey("hr_employees.employee_id"), nullable=False)
    leave_type:     Mapped[Optional[str]]  = mapped_column(String(80))
    start_date:     Mapped[Optional[date]] = mapped_column(Date)
    end_date:       Mapped[Optional[date]] = mapped_column(Date)
    days_requested: Mapped[Optional[int]]  = mapped_column(Integer)
    status:         Mapped[Optional[str]]  = mapped_column(String(30))
    approved_by:    Mapped[Optional[str]]  = mapped_column(String(20))
    request_date:   Mapped[Optional[date]] = mapped_column(Date)
    notes:          Mapped[Optional[str]]  = mapped_column(Text)

    employee: Mapped["Employee"] = relationship(back_populates="leaves")


class PerformanceReview(Base):
    __tablename__ = "hr_performance_reviews"

    review_id:              Mapped[str]             = mapped_column(String(20), primary_key=True)
    employee_id:            Mapped[str]             = mapped_column(ForeignKey("hr_employees.employee_id"), nullable=False)
    review_period:          Mapped[Optional[str]]   = mapped_column(String(20))
    overall_score:          Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    delivery_quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    teamwork_score:         Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    innovation_score:       Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    technical_skills_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    goals_achieved_pct:     Mapped[Optional[int]]   = mapped_column(Integer)
    promotion_eligible:     Mapped[Optional[str]]   = mapped_column(String(30))
    reviewer_id:            Mapped[Optional[str]]   = mapped_column(String(20))
    review_date:            Mapped[Optional[date]]  = mapped_column(Date)
    comments:               Mapped[Optional[str]]   = mapped_column(Text)

    employee: Mapped["Employee"] = relationship(back_populates="reviews")
