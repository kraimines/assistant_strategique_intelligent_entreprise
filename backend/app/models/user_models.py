"""User model — stored in talan_hr, used for authentication and RBAC."""
import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Role(str, enum.Enum):
    admin    = "admin"
    manager  = "manager"
    employee = "employee"


class User(Base):
    __tablename__ = "users"

    id:              Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    email:           Mapped[str]      = mapped_column(String(150), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str]      = mapped_column(String(255), nullable=False)
    full_name:       Mapped[str]      = mapped_column(String(150), nullable=False)
    role:            Mapped[Role]     = mapped_column(
                                            Enum(Role, name="user_role"),
                                            default=Role.employee,
                                            nullable=False,
                                        )
    is_active:       Mapped[bool]     = mapped_column(Boolean, default=True, nullable=False)
    created_at:      Mapped[datetime] = mapped_column(
                                            DateTime(timezone=True),
                                            default=lambda: datetime.now(timezone.utc),
                                            nullable=False,
                                        )
