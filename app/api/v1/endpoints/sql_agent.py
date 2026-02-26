"""SQL Agent API endpoint: Plan → Generate → Execute & Correct with schema RAG."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from prisma import Prisma

from app.api.dependencies import get_current_user, get_prisma, get_qdrant
from app.core.config import get_settings
from app.schemas.auth import UserOut
from app.schemas.sql_agent import SQLAgentRequest, SQLAgentResponse
from app.services.sql_agent_simple import run_simple_sql_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sql-agent", tags=["sql-agent"])


def _normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


async def _resolve_customer_by_name(prisma: Prisma, raw_name: str):
    """Resolve customer by full name or email from customer table."""
    needle = _normalize_name(raw_name)
    if not needle:
        return None
    customers = await prisma.customer.find_many()
    matches = []
    for customer in customers:
        full_name = _normalize_name(f"{customer.firstname} {customer.lastname}")
        email = _normalize_name(getattr(customer, "email", "") or "")
        if needle == full_name or (email and needle == email):
            matches.append(customer)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise HTTPException(
            status_code=400,
            detail="Selected customer name is ambiguous. Use full name or email.",
        )
    return None


@router.post("", response_model=SQLAgentResponse)
async def post_sql_agent(
    body: SQLAgentRequest,
    prisma: Prisma = Depends(get_prisma),
    qdrant=Depends(get_qdrant),
    current_user: UserOut = Depends(get_current_user),
) -> SQLAgentResponse:
    """
    Run the SQL Agent: Plan → Generate → Execute & Correct.
    Requires JWT auth. Customer scope is enforced from the authenticated user (or selected_customer_name).
    """
    settings = get_settings()
    customer_id: Optional[int] = current_user.customer_id
    customer_name: Optional[str] = None
    if current_user.customer:
        customer_name = f"{current_user.customer.firstname} {current_user.customer.lastname}".strip()

    selected_customer_name = (body.selected_customer_name or "").strip()
    if selected_customer_name:
        selected_customer = await _resolve_customer_by_name(prisma, selected_customer_name)
        if not selected_customer:
            raise HTTPException(status_code=404, detail="Selected customer was not found.")
        selected_customer_id = int(selected_customer.id)
        if customer_id is not None and int(customer_id) != selected_customer_id:
            raise HTTPException(
                status_code=403,
                detail="You can only access your own customer data.",
            )
        customer_id = selected_customer_id
        customer_name = f"{selected_customer.firstname} {selected_customer.lastname}".strip()

    if customer_id is None:
        raise HTTPException(
            status_code=400,
            detail="No customer is linked to this account. Provide selected_customer_name or link a customer.",
        )

    try:
        result = await run_simple_sql_agent(
            message=body.message,
            settings=settings,
            qdrant=qdrant,
            customer_id=customer_id,
            user_id=current_user.id,
            customer_name=customer_name,
        )
    except Exception as e:
        logger.exception("SQL Agent API failed: %s", e)
        raise HTTPException(status_code=500, detail="The SQL agent encountered an error. Please try again.")

    return SQLAgentResponse(
        content=result["content"],
        sql=result.get("sql"),
        plan=result.get("plan"),
        metadata=result.get("metadata", {}),
    )
