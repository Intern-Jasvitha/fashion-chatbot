"""
JWT and password hashing for auth.

Uses passlib's bcrypt_sha256:
- Avoids bcrypt 72-byte password limit
- Secure for production
"""

from datetime import datetime, timedelta
from typing import Any, Optional

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# Use bcrypt_sha256 only (no legacy logic needed)
pwd_context = CryptContext(
    schemes=["bcrypt_sha256"],
    deprecated="auto",
)

ALGORITHM = "HS256"


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create JWT access token. 'sub' should contain user id."""
    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta
        if expires_delta
        else timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    )

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password safely (no 72-byte limit)."""
    return pwd_context.hash(password)
