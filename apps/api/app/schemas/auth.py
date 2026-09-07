from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    # Real strength enforcement (length, common-password/sequential-run
    # checks, name/email substring checks) happens in
    # AuthService.register() via app.core.security.password_policy —
    # kept out of the schema layer so it stays testable without pydantic
    # (see tests/test_security_core.py::PasswordPolicyTests).
    password: str = Field(min_length=1, max_length=256)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=32)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=256)


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    """Deliberately has no password_hash field — see §4: 'never return
    password hashes through API' / 'never expose password hashes to
    frontend'. There is no code path that could add one by accident
    without editing this schema, unlike a `model_dump()` of the raw ORM
    object would risk."""

    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    status: str
    email_verified: bool
    roles: list[str] = []
    permissions: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}
