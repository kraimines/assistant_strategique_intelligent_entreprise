"""Shared FastAPI dependencies — async DB sessions, JWT auth, RBAC."""
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_access_token

http_bearer = HTTPBearer(auto_error=True)


# ── Async DB sessions per domain ──────────────────────────────────────────────

async def get_hr_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session("hr"):
        yield session


async def get_crm_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session("crm"):
        yield session


async def get_erp_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session("erp"):
        yield session


# ── Current user (reads User row from DB) ─────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(http_bearer),
    db: AsyncSession = Depends(get_hr_db),
):
    """
    Decode JWT, load the User from DB, and return it.
    Raises HTTP 401 if token is invalid or user not found.
    """
    # Import here to avoid circular imports at module load
    from app.models.user_models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user: User | None = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


# ── RBAC ──────────────────────────────────────────────────────────────────────

def require_role(*roles: str):
    """
    Dependency factory: checks that the current user has one of the given roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        @router.get("/managers",   dependencies=[Depends(require_role("admin", "manager"))])
    """
    async def _check(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role(s): {', '.join(roles)}",
            )
        return current_user
    return _check
