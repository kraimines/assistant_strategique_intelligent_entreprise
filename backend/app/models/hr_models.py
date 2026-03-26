"""HR SQLAlchemy ORM models — base de données talan_hr."""
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey,
    Integer, SmallInteger, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Department(Base):
    __tablename__ = "hr_departments"

    dept_id:     Mapped[int]           = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]           = mapped_column(String(100), nullable=False, unique=True)
    cost_center: Mapped[Optional[str]] = mapped_column(String(50))
    location:    Mapped[Optional[str]] = mapped_column(String(100))
    budget:      Mapped[Optional[float]] = mapped_column(Float)

    employees: Mapped[List["Employee"]] = relationship(back_populates="department")


class Employee(Base):
    __tablename__ = "hr_employees"

    emp_id:       Mapped[int]            = mapped_column(Integer, primary_key=True)
    first_name:   Mapped[str]            = mapped_column(String(50), nullable=False)
    last_name:    Mapped[str]            = mapped_column(String(50), nullable=False)
    email:        Mapped[str]            = mapped_column(String(150), nullable=False, unique=True)
    role:         Mapped[Optional[str]]  = mapped_column(String(100))
    hire_date:    Mapped[Optional[date]] = mapped_column(Date)
    salary:       Mapped[Optional[float]] = mapped_column(Float)
    dept_id:      Mapped[Optional[int]]  = mapped_column(ForeignKey("hr_departments.dept_id"))
    manager_id:   Mapped[Optional[int]]  = mapped_column(ForeignKey("hr_employees.emp_id"))
    is_active:    Mapped[bool]           = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime]       = mapped_column(DateTime, server_default=func.now())

    department: Mapped[Optional["Department"]] = relationship(back_populates="employees")
    skills:     Mapped[List["Skill"]]          = relationship(back_populates="employee")
    reviews:    Mapped[List["PerformanceReview"]] = relationship(back_populates="employee")
    leaves:     Mapped[List["LeaveRequest"]]   = relationship(back_populates="employee")


class Skill(Base):
    __tablename__ = "hr_skills"

    skill_id:         Mapped[int]           = mapped_column(Integer, primary_key=True)
    emp_id:           Mapped[int]           = mapped_column(ForeignKey("hr_employees.emp_id"), nullable=False)
    skill_name:       Mapped[str]           = mapped_column(String(100), nullable=False)
    level:            Mapped[Optional[str]] = mapped_column(String(20))   # junior/mid/senior
    years_experience: Mapped[Optional[int]] = mapped_column(SmallInteger)

    employee: Mapped["Employee"] = relationship(back_populates="skills")


class Project(Base):
    __tablename__ = "hr_projects"

    project_id:        Mapped[int]            = mapped_column(Integer, primary_key=True)
    name:              Mapped[str]            = mapped_column(String(200), nullable=False)
    client_account_id: Mapped[Optional[str]]  = mapped_column(String(50))
    budget:            Mapped[Optional[float]] = mapped_column(Float)
    status:            Mapped[Optional[str]]  = mapped_column(String(30))
    start_date:        Mapped[Optional[date]] = mapped_column(Date)
    end_date:          Mapped[Optional[date]] = mapped_column(Date)


class LeaveRequest(Base):
    __tablename__ = "hr_leave_requests"

    leave_id:   Mapped[int]            = mapped_column(Integer, primary_key=True)
    emp_id:     Mapped[int]            = mapped_column(ForeignKey("hr_employees.emp_id"), nullable=False)
    leave_type: Mapped[Optional[str]]  = mapped_column(String(50))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date:   Mapped[Optional[date]] = mapped_column(Date)
    status:     Mapped[Optional[str]]  = mapped_column(String(20))
    reason:     Mapped[Optional[str]]  = mapped_column(Text)

    employee: Mapped["Employee"] = relationship(back_populates="leaves")


class PerformanceReview(Base):
    __tablename__ = "hr_performance_reviews"

    review_id:          Mapped[int]            = mapped_column(Integer, primary_key=True)
    emp_id:             Mapped[int]            = mapped_column(ForeignKey("hr_employees.emp_id"), nullable=False)
    review_year:        Mapped[Optional[int]]  = mapped_column(SmallInteger)
    delivery_score:     Mapped[Optional[float]] = mapped_column(Float)
    teamwork_score:     Mapped[Optional[float]] = mapped_column(Float)
    innovation_score:   Mapped[Optional[float]] = mapped_column(Float)
    overall_score:      Mapped[Optional[float]] = mapped_column(Float)
    promotion_eligible: Mapped[bool]           = mapped_column(Boolean, default=False)
    comments:           Mapped[Optional[str]]  = mapped_column(Text)

    employee: Mapped["Employee"] = relationship(back_populates="reviews")
