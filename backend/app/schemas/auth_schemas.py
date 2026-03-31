"""Pydantic schemas for authentication and user management."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.user_models import Role


class RegisterRequest(BaseModel):
    email:     EmailStr
    password:  str
    full_name: str
    role:      Role = Role.employee

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "alice@talan.com",
                "password": "Secret123!",
                "full_name": "Alice Martin",
                "role": "manager",
            }
        }
    }


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {"email": "alice@talan.com", "password": "Secret123!"}
        }
    }


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int  # seconds


class UserRead(BaseModel):
    id:         int
    email:      str
    full_name:  str
    role:       Role
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfile(UserRead):
    """Extended user info — includes linked HR employee data if available."""
    emp_id:     Optional[int]  = None
    department: Optional[str]  = None
    hire_date:  Optional[date] = None
