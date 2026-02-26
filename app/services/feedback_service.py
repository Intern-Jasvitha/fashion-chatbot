"""Feedback persistence and lookup utilities."""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import uuid4

from prisma import Prisma

from app.services.telemetry_service import hash_text, redact_text


FEEDBACK_UP = "UP"
FEEDBACK_DOWN = "DOWN"


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "__dict__"):
        return dict(row.__dict__)
    return {}


async def ensure_message_in_session(prisma: Prisma, *, session_id: str, message_id: str) -> bool:
    rows = await prisma.query_raw(
        """
        SELECT 1
        FROM "chat_message"
        WHERE "id" = $1 AND "session_id" = $2
        LIMIT 1
        """,
        message_id,
        session_id,
    )
    return bool(rows)


async def create_feedback(
    prisma: Prisma,
    *,
    session_id: str,
    message_id: Optional[str],
    user_id: Optional[int],
    customer_id: Optional[int],
    feedback_type: str,
    reason_code: Optional[str] = None,
    correction_text: Optional[str] = None,
    learning_allowed: bool = True,
    learning_exclusion_reason: Optional[str] = None,
) -> str:
    """Append a feedback row and return its id."""
    feedback_id = str(uuid4())
    payload = {
        "reason_code": reason_code,
        "has_correction": bool((correction_text or "").strip()),
    }
    content = correction_text or ""
    await prisma.execute_raw(
        """
        INSERT INTO "chat_feedback" (
          "id",
          "session_id",
          "message_id",
          "user_id",
          "customer_id",
          "feedback_type",
          "content_hash",
          "content_redacted",
          "payload_json",
          "learning_allowed",
          "learning_exclusion_reason",
          "created_at"
        ) VALUES (
          $1,
          $2,
          $3,
          $4,
          $5,
          $6,
          $7,
          $8,
          $9,
          $10,
          $11,
          NOW()
        )
        """,
        feedback_id,
        session_id,
        message_id,
        user_id,
        customer_id,
        feedback_type,
        hash_text(content) if content else None,
        redact_text(content) if content else None,
        json.dumps(payload, default=str),
        bool(learning_allowed),
        learning_exclusion_reason,
    )
    return feedback_id


async def get_latest_feedback_map(
    prisma: Prisma,
    *,
    session_id: str,
    user_id: Optional[int],
) -> dict[str, str]:
    """Return latest feedback per assistant message for one user in one session."""
    if user_id is None:
        return {}
    rows = await prisma.query_raw(
        """
        SELECT "message_id", "feedback_type"
        FROM (
          SELECT
            "message_id",
            "feedback_type",
            ROW_NUMBER() OVER (PARTITION BY "message_id" ORDER BY "created_at" DESC) AS rn
          FROM "chat_feedback"
          WHERE "session_id" = $1
            AND "user_id" = $2
            AND "message_id" IS NOT NULL
        ) f
        WHERE f.rn = 1
        """,
        session_id,
        int(user_id),
    )
    out: dict[str, str] = {}
    for row in rows:
        item = _row_dict(row)
        msg_id = item.get("message_id")
        feedback_type = item.get("feedback_type")
        if isinstance(msg_id, str) and isinstance(feedback_type, str):
            out[msg_id] = feedback_type
    return out
