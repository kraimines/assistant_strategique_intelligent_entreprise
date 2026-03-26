"""Pydantic schemas — domaine HR."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


# ── Department ────────────────────────────────────────────────────────────────

class DepartmentBase(BaseModel):
    name:        str
    cost_center: Optional[str]  = None
    location:    Optional[str]  = None
    budget:      Optional[float] = None


class DepartmentRead(DepartmentBase):
    dept_id: int
    model_config = {"from_attributes": True}


# ── Employee ──────────────────────────────────────────────────────────────────

class EmployeeBase(BaseModel):
    first_name: str
    last_name:  str
    email:      EmailStr
    role:       Optional[str]   = None
    hire_date:  Optional[date]  = None
    salary:     Optional[float] = None
    dept_id:    Optional[int]   = None
    manager_id: Optional[int]   = None
    is_active:  bool            = True


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeRead(EmployeeBase):
    emp_id:     int
    created_at: datetime
    model_config = {"from_attributes": True}


class EmployeeList(BaseModel):
    total: int
    items: list[EmployeeRead]


# ── Skill ─────────────────────────────────────────────────────────────────────

class SkillRead(BaseModel):
    skill_id:         int
    skill_name:       str
    level:            Optional[str] = None
    years_experience: Optional[int] = None
    model_config = {"from_attributes": True}


# ── Leave Request ─────────────────────────────────────────────────────────────

class LeaveRequestRead(BaseModel):
    leave_id:   int
    emp_id:     int
    leave_type: Optional[str]  = None
    start_date: Optional[date] = None
    end_date:   Optional[date] = None
    status:     Optional[str]  = None
    reason:     Optional[str]  = None
    model_config = {"from_attributes": True}


# ── Performance Review ────────────────────────────────────────────────────────

class PerformanceReviewRead(BaseModel):
    review_id:          int
    emp_id:             int
    review_year:        Optional[int]   = None
    delivery_score:     Optional[float] = None
    teamwork_score:     Optional[float] = None
    innovation_score:   Optional[float] = None
    overall_score:      Optional[float] = None
    promotion_eligible: bool            = False
    comments:           Optional[str]   = None
    model_config = {"from_attributes": True}
