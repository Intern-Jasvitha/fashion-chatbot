"""Pydantic schemas for auth (login, signup, token, user out)."""

from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator

# Reasonable max to avoid abuse (bcrypt_sha256 has no 72-byte limit).
MAX_PASSWORD_BYTES = 2048


def _check_password_bytes(v: str) -> str:
    if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("Password is too long.")
    return v


class UserCreate(BaseModel):
    """Request body for signup."""

    email: EmailStr
    password: str
    name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        return _check_password_bytes(v)


class UserLogin(BaseModel):
    """Request body for login."""

    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        return _check_password_bytes(v)


class CustomerOut(BaseModel):
    """Customer info associated with a user (from CSV/DB)."""

    id: int
    firstname: str
    lastname: str
    email: Optional[str] = None
    phoneno: Optional[str] = None

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    """User in API responses (no password)."""

    id: int
    email: str
    name: Optional[str]
    customer_id: Optional[int] = None
    customer: Optional[CustomerOut] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Response after login or signup."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut
