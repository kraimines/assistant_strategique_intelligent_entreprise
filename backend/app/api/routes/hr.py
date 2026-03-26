"""HR API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_hr_db, get_current_user
from app.models.hr_models import Department, Employee, LeaveRequest, PerformanceReview, Skill
from app.schemas.hr_schemas import (
    DepartmentRead,
    EmployeeCreate,
    EmployeeList,
    EmployeeRead,
    LeaveRequestRead,
    PerformanceReviewRead,
    SkillRead,
)

router = APIRouter()


# ── Departments ───────────────────────────────────────────────────────────────

@router.get("/departments", response_model=list[DepartmentRead])
def list_departments(db: Session = Depends(get_hr_db)):
    return db.query(Department).all()


@router.get("/departments/{dept_id}", response_model=DepartmentRead)
def get_department(dept_id: int, db: Session = Depends(get_hr_db)):
    dept = db.get(Department, dept_id)
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Département introuvable")
    return dept


# ── Employees ─────────────────────────────────────────────────────────────────

@router.get("/employees", response_model=EmployeeList)
def list_employees(
    dept_id:  Optional[int] = Query(None, description="Filtrer par département"),
    is_active: bool         = Query(True, description="Employés actifs uniquement"),
    skip:     int           = Query(0, ge=0),
    limit:    int           = Query(50, ge=1, le=200),
    db:       Session       = Depends(get_hr_db),
):
    q = db.query(Employee).filter(Employee.is_active == is_active)
    if dept_id is not None:
        q = q.filter(Employee.dept_id == dept_id)
    total = q.count()
    items = q.offset(skip).limit(limit).all()
    return EmployeeList(total=total, items=items)


@router.get("/employees/{emp_id}", response_model=EmployeeRead)
def get_employee(emp_id: int, db: Session = Depends(get_hr_db)):
    emp = db.get(Employee, emp_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    return emp


@router.get("/employees/{emp_id}/skills", response_model=list[SkillRead])
def get_employee_skills(emp_id: int, db: Session = Depends(get_hr_db)):
    emp = db.get(Employee, emp_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    return db.query(Skill).filter(Skill.emp_id == emp_id).all()


@router.get("/employees/{emp_id}/leaves", response_model=list[LeaveRequestRead])
def get_employee_leaves(emp_id: int, db: Session = Depends(get_hr_db)):
    return db.query(LeaveRequest).filter(LeaveRequest.emp_id == emp_id).all()


@router.get("/employees/{emp_id}/reviews", response_model=list[PerformanceReviewRead])
def get_employee_reviews(emp_id: int, db: Session = Depends(get_hr_db)):
    return db.query(PerformanceReview).filter(PerformanceReview.emp_id == emp_id).all()


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis/headcount")
def headcount_by_dept(db: Session = Depends(get_hr_db)):
    """Retourne le nombre d'employés actifs par département."""
    from sqlalchemy import func
    rows = (
        db.query(Department.name, func.count(Employee.emp_id).label("count"))
        .outerjoin(Employee, Employee.dept_id == Department.dept_id)
        .filter(Employee.is_active == True)
        .group_by(Department.name)
        .all()
    )
    return [{"department": r.name, "count": r.count} for r in rows]
