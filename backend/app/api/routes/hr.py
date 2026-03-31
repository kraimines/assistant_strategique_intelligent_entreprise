"""HR API routes — async SQLAlchemy, full CRUD."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_hr_db, require_role
from app.models.hr_models import Department, Employee, LeaveRequest, PerformanceReview, Skill
from app.schemas.hr_schemas import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeList,
    EmployeeRead,
    EmployeeUpdate,
    LeaveRequestCreate,
    LeaveRequestRead,
    LeaveRequestUpdate,
    PerformanceReviewCreate,
    PerformanceReviewRead,
    SkillCreate,
    SkillRead,
)

router = APIRouter()


# ── Departments ───────────────────────────────────────────────────────────────

@router.get("/departments", response_model=list[DepartmentRead])
async def list_departments(db: AsyncSession = Depends(get_hr_db)):
    result = await db.execute(select(Department).order_by(Department.department_name))
    return result.scalars().all()


@router.get("/departments/{department_id}", response_model=DepartmentRead)
async def get_department(department_id: str, db: AsyncSession = Depends(get_hr_db)):
    dept = await db.get(Department, department_id)
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Département introuvable")
    return dept


@router.post("/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin", "manager"))])
async def create_department(body: DepartmentCreate, db: AsyncSession = Depends(get_hr_db)):
    dept = Department(**body.model_dump())
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


@router.put("/departments/{department_id}", response_model=DepartmentRead,
            dependencies=[Depends(require_role("admin", "manager"))])
async def update_department(department_id: str, body: DepartmentUpdate, db: AsyncSession = Depends(get_hr_db)):
    dept = await db.get(Department, department_id)
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Département introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(dept, field, value)
    await db.commit()
    await db.refresh(dept)
    return dept


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("admin"))])
async def delete_department(department_id: str, db: AsyncSession = Depends(get_hr_db)):
    dept = await db.get(Department, department_id)
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Département introuvable")
    await db.delete(dept)
    await db.commit()


# ── Employees ─────────────────────────────────────────────────────────────────

@router.get("/employees", response_model=EmployeeList)
async def list_employees(
    department_id: Optional[str] = Query(None, description="Filtrer par département"),
    skip:          int            = Query(0, ge=0),
    limit:         int            = Query(50, ge=1, le=200),
    db:            AsyncSession   = Depends(get_hr_db),
):
    q = select(Employee)
    if department_id is not None:
        q = q.where(Employee.department_id == department_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(q.offset(skip).limit(limit).order_by(Employee.last_name))
    return EmployeeList(total=total, items=items_result.scalars().all())


@router.get("/employees/{employee_id}", response_model=EmployeeRead)
async def get_employee(employee_id: str, db: AsyncSession = Depends(get_hr_db)):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    return emp


@router.post("/employees", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin", "manager"))])
async def create_employee(body: EmployeeCreate, db: AsyncSession = Depends(get_hr_db)):
    existing = await db.execute(select(Employee).where(Employee.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email déjà utilisé")
    emp = Employee(**body.model_dump())
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return emp


@router.put("/employees/{employee_id}", response_model=EmployeeRead,
            dependencies=[Depends(require_role("admin", "manager"))])
async def update_employee(employee_id: str, body: EmployeeUpdate, db: AsyncSession = Depends(get_hr_db)):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    await db.commit()
    await db.refresh(emp)
    return emp


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("admin"))])
async def delete_employee(employee_id: str, db: AsyncSession = Depends(get_hr_db)):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    await db.delete(emp)
    await db.commit()


# ── Skills ────────────────────────────────────────────────────────────────────

@router.get("/employees/{employee_id}/skills", response_model=list[SkillRead])
async def get_employee_skills(employee_id: str, db: AsyncSession = Depends(get_hr_db)):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    result = await db.execute(select(Skill).where(Skill.employee_id == employee_id))
    return result.scalars().all()


@router.post("/employees/{employee_id}/skills", response_model=SkillRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin", "manager"))])
async def add_employee_skill(employee_id: str, body: SkillCreate, db: AsyncSession = Depends(get_hr_db)):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    skill = Skill(employee_id=employee_id, **body.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


# ── Leave Requests ────────────────────────────────────────────────────────────

@router.get("/employees/{employee_id}/leaves", response_model=list[LeaveRequestRead])
async def get_employee_leaves(employee_id: str, db: AsyncSession = Depends(get_hr_db)):
    result = await db.execute(select(LeaveRequest).where(LeaveRequest.employee_id == employee_id))
    return result.scalars().all()


@router.post("/employees/{employee_id}/leaves", response_model=LeaveRequestRead,
             status_code=status.HTTP_201_CREATED)
async def create_leave_request(
    employee_id: str,
    body:        LeaveRequestCreate,
    db:          AsyncSession = Depends(get_hr_db),
    _:           object       = Depends(get_current_user),
):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    leave = LeaveRequest(employee_id=employee_id, status="Pending", **body.model_dump())
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    return leave


@router.put("/leaves/{leave_id}", response_model=LeaveRequestRead,
            dependencies=[Depends(require_role("admin", "manager"))])
async def update_leave_request(leave_id: str, body: LeaveRequestUpdate, db: AsyncSession = Depends(get_hr_db)):
    leave = await db.get(LeaveRequest, leave_id)
    if not leave:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Congé introuvable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(leave, field, value)
    await db.commit()
    await db.refresh(leave)
    return leave


# ── Performance Reviews ───────────────────────────────────────────────────────

@router.get("/employees/{employee_id}/reviews", response_model=list[PerformanceReviewRead])
async def get_employee_reviews(employee_id: str, db: AsyncSession = Depends(get_hr_db)):
    result = await db.execute(
        select(PerformanceReview)
        .where(PerformanceReview.employee_id == employee_id)
        .order_by(PerformanceReview.review_period.desc())
    )
    return result.scalars().all()


@router.post("/employees/{employee_id}/reviews", response_model=PerformanceReviewRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role("admin", "manager"))])
async def create_performance_review(
    employee_id: str,
    body:        PerformanceReviewCreate,
    db:          AsyncSession = Depends(get_hr_db),
):
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    review = PerformanceReview(employee_id=employee_id, **body.model_dump())
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


# ── KPIs ──────────────────────────────────────────────────────────────────────

@router.get("/kpis/headcount")
async def headcount_by_dept(db: AsyncSession = Depends(get_hr_db)):
    """Nombre d'employés par département."""
    result = await db.execute(
        select(Department.department_name, func.count(Employee.employee_id).label("count"))
        .outerjoin(Employee, Employee.department_id == Department.department_id)
        .group_by(Department.department_name)
        .order_by(Department.department_name)
    )
    return [{"department": row.department_name, "count": row.count} for row in result]


@router.get("/kpis/avg-salary")
async def avg_salary_by_dept(db: AsyncSession = Depends(get_hr_db)):
    """Salaire moyen par département."""
    result = await db.execute(
        select(Department.department_name, func.avg(Employee.salary).label("avg_salary"))
        .join(Employee, Employee.department_id == Department.department_id)
        .group_by(Department.department_name)
        .order_by(Department.department_name)
    )
    return [
        {"department": row.department_name, "avg_salary": round(float(row.avg_salary or 0), 2)}
        for row in result
    ]
