"""FastAPI dependencies for Prisma, Qdrant, LangGraph, and auth."""

from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from jose import JWTError, jwt
from prisma import Prisma
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.schemas.auth import CustomerOut, UserOut

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=True,
)


def get_prisma(request: Request) -> Prisma:
    """FastAPI dependency: returns the Prisma client for database access."""
    return request.app.state.prisma


def get_qdrant(request: Request) -> QdrantClient:
    """FastAPI dependency: returns the Qdrant client for vector search."""
    return request.app.state.qdrant


def get_graph(request: Request) -> Any:
    """FastAPI dependency: returns the compiled LangGraph agent orchestrator."""
    return request.app.state.graph


async def _user_from_token(token: str, prisma: Prisma) -> UserOut:
    """Decode JWT token and return user. Raises 401 on invalid token or missing user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        sub: Optional[str] = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except (JWTError, ValueError):
        raise credentials_exception

    user = await prisma.user.find_unique(where={"id": user_id}, include={"customer": True})
    if user is None:
        raise credentials_exception
    customer = getattr(user, "customer", None)
    customer_out = (
        CustomerOut(
            id=customer.id,
            firstname=customer.firstname,
            lastname=customer.lastname,
            email=getattr(customer, "email", None),
            phoneno=getattr(customer, "phoneno", None),
        )
        if customer
        else None
    )
    customer_id = getattr(user, "customerId", None) or getattr(user, "customer_id", None)
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        customer_id=customer_id,
        customer=customer_out,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    prisma: Prisma = Depends(get_prisma),
) -> UserOut:
    """Decode JWT and return current user. Raises 401 if invalid or user not found."""
    return await _user_from_token(token, prisma)


async def get_current_user_optional(
    request: Request,
    prisma: Prisma = Depends(get_prisma),
) -> Optional[UserOut]:
    """Return current user when token exists; return None when missing; reject malformed tokens."""
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _user_from_token(token, prisma)
