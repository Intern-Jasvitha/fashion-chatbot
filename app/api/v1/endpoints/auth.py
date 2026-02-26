"""Auth endpoints: signup, login, logout."""

from fastapi import APIRouter, Depends, HTTPException, status

from prisma import Prisma

from app.api.dependencies import get_prisma
from app.schemas.auth import TokenResponse, UserCreate, UserLogin, UserOut
from app.services.auth_service import authenticate, register
from app.core.security import create_access_token
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/signup", response_model=TokenResponse)
async def signup(
    body: UserCreate,
    prisma: Prisma = Depends(get_prisma),
) -> TokenResponse:
    """Register and return token + user (immediate login)."""
    try:
        user = await register(prisma, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: UserLogin,
    prisma: Prisma = Depends(get_prisma),
) -> TokenResponse:
    """Login with email/password. Returns token + user."""
    user = await authenticate(prisma, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token, user=user)


@router.post("/logout")
async def logout() -> dict:
    """Client-side logout; server acknowledges. Optional blacklist can be added later."""
    return {"message": "Logged out"}
