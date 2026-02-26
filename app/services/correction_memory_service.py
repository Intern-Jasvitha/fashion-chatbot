"""Correction memory lifecycle for session and long-term learning."""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from prisma import Prisma

from app.services.telemetry_service import hash_text, redact_text


MEMORY_SCOPE_SESSION = "SESSION"
MEMORY_SCOPE_LONG_TERM = "LONG_TERM"


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "__dict__"):
        return dict(row.__dict__)
    return {}


async def create_correction_memory(
    prisma: Prisma,
    *,
    session_id: str,
    message_id: Optional[str],
    source_feedback_id: Optional[str],
    user_id: Optional[int],
    customer_id: Optional[int],
    instruction_text: str,
    memory_scope: str,
    consent_long_term: bool,
) -> str:
    """Create one correction memory row."""
    redacted = redact_text(instruction_text)
    digest = hash_text(instruction_text)
    memory_id = str(uuid4())
    await prisma.execute_raw(
        """
        INSERT INTO "correction_memory" (
          "id",
          "session_id",
          "message_id",
          "user_id",
          "customer_id",
          "source_feedback_id",
          "memory_scope",
          "instruction_redacted",
          "instruction_hash",
          "consent_long_term",
          "active",
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
          true,
          NOW()
        )
        """,
        memory_id,
        session_id,
        message_id,
        user_id,
        customer_id,
        source_feedback_id,
        memory_scope,
        redacted,
        digest,
        bool(consent_long_term),
    )
    return memory_id


async def load_correction_hints(
    prisma: Prisma,
    *,
    session_id: str,
    user_id: Optional[int],
    customer_id: Optional[int],
    max_items: int = 8,
) -> list[str]:
    """Load active session + long-term corrections for prompt-time guidance."""
    hints: list[str] = []
    seen_hashes: set[str] = set()

    session_rows = await prisma.query_raw(
        """
        SELECT "instruction_redacted", "instruction_hash"
        FROM "correction_memory"
        WHERE "session_id" = $1
          AND "memory_scope" = 'SESSION'
          AND "active" = true
        ORDER BY "created_at" DESC
        LIMIT 6
        """,
        session_id,
    )
    for row in session_rows:
        item = _row_dict(row)
        text = item.get("instruction_redacted")
        digest = item.get("instruction_hash")
        if isinstance(text, str) and text and isinstance(digest, str):
            if digest in seen_hashes:
                continue
            hints.append(text)
            seen_hashes.add(digest)

    if user_id is None and customer_id is None:
        return hints[:max_items]

    long_term_rows = await prisma.query_raw(
        """
        SELECT "instruction_redacted", "instruction_hash"
        FROM "correction_memory"
        WHERE "memory_scope" = 'LONG_TERM'
          AND "active" = true
          AND "consent_long_term" = true
          AND (
            ($1::integer IS NOT NULL AND "user_id" = $1)
            OR ($2::integer IS NOT NULL AND "customer_id" = $2)
          )
        ORDER BY "created_at" DESC
        LIMIT 8
        """,
        user_id,
        customer_id,
    )
    for row in long_term_rows:
        item = _row_dict(row)
        text = item.get("instruction_redacted")
        digest = item.get("instruction_hash")
        if isinstance(text, str) and text and isinstance(digest, str):
            if digest in seen_hashes:
                continue
            hints.append(text)
            seen_hashes.add(digest)

    return hints[:max_items]
