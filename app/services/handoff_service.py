"""Human handoff queue utilities."""

from __future__ import annotations

import json
from typing import Optional
from uuid import uuid4

from prisma import Prisma


async def enqueue_handoff(
    prisma: Prisma,
    *,
    session_id: str,
    message_id: Optional[str],
    user_id: Optional[int],
    customer_id: Optional[int],
    reason_code: str,
    notes: Optional[str],
    priority: str = "MEDIUM",
) -> str:
    handoff_id = str(uuid4())
    payload = {"notes": (notes or "").strip() or None}
    await prisma.execute_raw(
        """
        INSERT INTO "handoff_queue" (
          "id",
          "session_id",
          "message_id",
          "user_id",
          "customer_id",
          "reason_code",
          "priority",
          "status",
          "payload_json",
          "created_at",
          "updated_at"
        ) VALUES (
          $1,
          $2,
          $3,
          $4,
          $5,
          $6,
          $7,
          'OPEN',
          $8,
          NOW(),
          NOW()
        )
        """,
        handoff_id,
        session_id,
        message_id,
        user_id,
        customer_id,
        reason_code,
        priority,
        json.dumps(payload, default=str),
    )
    return handoff_id


async def increment_session_handoff_clicks(
    prisma: Prisma,
    *,
    session_id: str,
    user_id: Optional[int],
    customer_id: Optional[int],
) -> None:
    """Increment handoff click counters used by adaptation and quality scoring."""
    await prisma.execute_raw(
        """
        INSERT INTO "session_features" (
          "session_id",
          "user_id",
          "customer_id",
          "updated_at"
        ) VALUES (
          $1,
          $2,
          $3,
          NOW()
        )
        ON CONFLICT ("session_id") DO NOTHING
        """,
        session_id,
        user_id,
        customer_id,
    )
    await prisma.execute_raw(
        """
        UPDATE "session_features"
        SET
          "handoff_clicks" = COALESCE("handoff_clicks", 0) + 1,
          "updated_at" = NOW()
        WHERE "session_id" = $1
        """,
        session_id,
    )
