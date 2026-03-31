"""Pydantic schemas — domaine HR."""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr


# ── Department ────────────────────────────────────────────────────────────────

class DepartmentBase(BaseModel):
    department_name: str
    cost_center:     Optional[str]   = None
    location:        Optional[str]   = None
    budget:          Optional[int]   = None
    manager_id:      Optional[str]   = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = None
    cost_center:     Optional[str] = None
    location:        Optional[str] = None
    budget:          Optional[int] = None
    manager_id:      Optional[str] = None


class DepartmentRead(DepartmentBase):
    department_id: str
    model_config = {"from_attributes": True}


# ── Employee ──────────────────────────────────────────────────────────────────

class EmployeeBase(BaseModel):
    first_name:              str
    last_name:               str
    email:                   EmailStr
    phone:                   Optional[str]     = None
    role:                    Optional[str]     = None
    hire_date:               Optional[date]    = None
    salary:                  Optional[Decimal] = None
    department_id:           Optional[str]     = None
    manager_id:              Optional[str]     = None
    contract_type:           Optional[str]     = None
    country:                 Optional[str]     = None
    city:                    Optional[str]     = None
    hourly_cost:             Optional[Decimal] = None
    capacity_hours_per_week: Optional[int]     = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    first_name:              Optional[str]     = None
    last_name:               Optional[str]     = None
    email:                   Optional[EmailStr] = None
    phone:                   Optional[str]     = None
    role:                    Optional[str]     = None
    hire_date:               Optional[date]    = None
    salary:                  Optional[Decimal] = None
    department_id:           Optional[str]     = None
    manager_id:              Optional[str]     = None
    contract_type:           Optional[str]     = None
    country:                 Optional[str]     = None
    city:                    Optional[str]     = None
    hourly_cost:             Optional[Decimal] = None
    capacity_hours_per_week: Optional[int]     = None


class EmployeeRead(EmployeeBase):
    employee_id: str
    model_config = {"from_attributes": True}


class EmployeeList(BaseModel):
    total: int
    items: list[EmployeeRead]


# ── Skill ─────────────────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    skill_name:       str
    level:            Optional[str]     = None
    years_experience: Optional[Decimal] = None
    certified:        Optional[str]     = None
    last_assessed:    Optional[date]    = None


class SkillRead(BaseModel):
    skill_id:         str
    employee_id:      str
    skill_name:       str
    level:            Optional[str]     = None
    years_experience: Optional[Decimal] = None
    certified:        Optional[str]     = None
    last_assessed:    Optional[date]    = None
    model_config = {"from_attributes": True}


# ── Leave Request ─────────────────────────────────────────────────────────────

class LeaveRequestCreate(BaseModel):
    leave_type:     Optional[str]  = None
    start_date:     Optional[date] = None
    end_date:       Optional[date] = None
    days_requested: Optional[int]  = None
    notes:          Optional[str]  = None


class LeaveRequestUpdate(BaseModel):
    leave_type:     Optional[str]  = None
    start_date:     Optional[date] = None
    end_date:       Optional[date] = None
    days_requested: Optional[int]  = None
    status:         Optional[str]  = None
    approved_by:    Optional[str]  = None
    notes:          Optional[str]  = None


class LeaveRequestRead(BaseModel):
    leave_id:       str
    employee_id:    str
    leave_type:     Optional[str]  = None
    start_date:     Optional[date] = None
    end_date:       Optional[date] = None
    days_requested: Optional[int]  = None
    status:         Optional[str]  = None
    approved_by:    Optional[str]  = None
    request_date:   Optional[date] = None
    notes:          Optional[str]  = None
    model_config = {"from_attributes": True}


# ── Performance Review ────────────────────────────────────────────────────────

class PerformanceReviewCreate(BaseModel):
    review_period:          Optional[str]     = None
    overall_score:          Optional[Decimal] = None
    delivery_quality_score: Optional[Decimal] = None
    teamwork_score:         Optional[Decimal] = None
    innovation_score:       Optional[Decimal] = None
    technical_skills_score: Optional[Decimal] = None
    goals_achieved_pct:     Optional[int]     = None
    promotion_eligible:     Optional[str]     = None
    comments:               Optional[str]     = None


class PerformanceReviewRead(BaseModel):
    review_id:              str
    employee_id:            str
    review_period:          Optional[str]     = None
    overall_score:          Optional[Decimal] = None
    delivery_quality_score: Optional[Decimal] = None
    teamwork_score:         Optional[Decimal] = None
    innovation_score:       Optional[Decimal] = None
    technical_skills_score: Optional[Decimal] = None
    goals_achieved_pct:     Optional[int]     = None
    promotion_eligible:     Optional[str]     = None
    reviewer_id:            Optional[str]     = None
    review_date:            Optional[date]    = None
    comments:               Optional[str]     = None
    model_config = {"from_attributes": True}
