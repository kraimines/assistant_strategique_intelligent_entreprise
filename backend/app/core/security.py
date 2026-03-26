"""Authentication and security — JWT + password hashing."""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Hachage des mots de passe ─────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Crée un JWT signé.

    Args:
        data:          Payload à encoder (ex: {"sub": "user_id", "role": "manager"})
        expires_delta: Durée de vie personnalisée. Sinon utilise le paramètre global.

    Returns:
        Token JWT encodé (str)
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {**data, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Décode et valide un JWT.

    Args:
        token: Token JWT à décoder

    Returns:
        Payload décodé

    Raises:
        JWTError: Si le token est invalide ou expiré
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


def extract_subject(token: str) -> str:
    """Retourne le champ 'sub' du token ou lève JWTError."""
    payload = decode_access_token(token)
    sub: str | None = payload.get("sub")
    if sub is None:
        raise JWTError("Token missing 'sub' claim")
    return sub
