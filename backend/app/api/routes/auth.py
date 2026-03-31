"""Auth routes — register, login, current user profile."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_hr_db
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.hr_models import Department, Employee
from app.models.user_models import User
from app.schemas.auth_schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
    UserRead,
)

router = APIRouter()

_401 = {"description": "Invalid or expired token"}
_403 = {"description": "Account disabled"}
_409 = {"description": "Email already registered"}


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a user account. **Email must be unique.** "
        "Role defaults to `employee`. "
        "Available roles: `admin`, `manager`, `employee`."
    ),
    responses={409: _409},
)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_hr_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain a JWT",
    description=(
        "Authenticates with email + password and returns a signed **Bearer JWT**. "
        "Pass the token in `Authorization: Bearer <token>` for protected endpoints."
    ),
    responses={401: _401, 403: _403},
)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_hr_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    return TokenResponse(access_token=token, expires_in=settings.access_token_expire_minutes * 60)


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Current user profile",
    description=(
        "Returns the authenticated user's profile, enriched with linked HR data "
        "(employee ID, department, hire date) when a matching employee record exists."
    ),
    responses={401: _401},
)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_hr_db),
):
    result = await db.execute(
        select(Employee, Department.name.label("dept_name"))
        .outerjoin(Department, Employee.dept_id == Department.dept_id)
        .where(Employee.email == current_user.email)
    )
    row = result.first()
    profile = UserProfile.model_validate(current_user)
    if row:
        emp, dept_name = row
        profile.emp_id = emp.emp_id
        profile.department = dept_name
        profile.hire_date = emp.hire_date
    return profile
