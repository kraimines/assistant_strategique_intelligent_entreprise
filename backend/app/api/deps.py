"""Shared FastAPI dependencies — injection de sessions DB et utilisateur courant."""
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


# ── Sessions par domaine ───────────────────────────────────────────────────────

def get_hr_db() -> Generator[Session, None, None]:
    yield from get_session("hr")


def get_crm_db() -> Generator[Session, None, None]:
    yield from get_session("crm")


def get_erp_db() -> Generator[Session, None, None]:
    yield from get_session("erp")


# ── Utilisateur courant ────────────────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Valide le JWT et retourne le payload de l'utilisateur.
    Lève HTTP 401 si le token est absent, invalide ou expiré.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return payload


def require_role(*roles: str):
    """
    Dépendance qui vérifie le rôle de l'utilisateur connecté.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role("director", "admin"))])
    """
    def _check(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle requis : {', '.join(roles)}",
            )
        return current_user
    return _check
