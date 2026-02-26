"""
Auth business logic: register and authenticate users.
"""

from datetime import datetime
from typing import Optional
from prisma import Prisma

from app.schemas.auth import CustomerOut, UserCreate, UserOut
from app.core.security import get_password_hash, verify_password


def _to_customer_out(customer) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        firstname=customer.firstname,
        lastname=customer.lastname,
        email=getattr(customer, "email", None),
        phoneno=getattr(customer, "phoneno", None),
    )


async def register(prisma: Prisma, user_in: UserCreate) -> UserOut:
    """Create new user. Raises ValueError if email already registered."""

    # Check if email exists
    existing = await prisma.user.find_unique(
        where={"email": user_in.email}
    )
    if existing:
        raise ValueError("Email already registered")

    # Hash password
    hashed_password = get_password_hash(user_in.password)

    # Find or create Customer row to link this user to
    customer = await prisma.customer.find_first(where={"email": user_in.email})
    if customer is None:
        max_row = await prisma.customer.find_first(order={"id": "desc"})
        next_id = (max_row.id + 1) if max_row else 1
        customer = await prisma.customer.create(
            data={
                "id": next_id,
                "firstname": (user_in.name or "User").strip() or "User",
                "lastname": "",
                "dob": datetime(2000, 1, 1),
                "email": user_in.email,
            }
        )

    # Create user linked to customer
    user = await prisma.user.create(
        data={
            "email": user_in.email,
            "hashed_password": hashed_password,
            "name": user_in.name,
            "customerId": customer.id,
        },
        include={"customer": True},
    )

    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        customer_id=getattr(user, "customerId", None) or getattr(user, "customer_id", None),
        customer=_to_customer_out(user.customer) if getattr(user, "customer", None) else None,
    )


async def authenticate(
    prisma: Prisma,
    email: str,
    password: str,
) -> Optional[UserOut]:
    """Authenticate user by email and password."""

    user = await prisma.user.find_unique(where={"email": email}, include={"customer": True})

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        customer_id=getattr(user, "customerId", None) or getattr(user, "customer_id", None),
        customer=_to_customer_out(user.customer) if getattr(user, "customer", None) else None,
    )
