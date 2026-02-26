"""Learning consent preference persistence helpers."""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from prisma import Prisma


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "__dict__"):
        return dict(row.__dict__)
    return {}


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _is_missing_relation_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "does not exist" in text and "learning_consent_preference" in text


DEFAULT_LONG_TERM_PERSONALIZATION_OPT_IN = False
DEFAULT_TELEMETRY_LEARNING_OPT_IN = True


async def ensure_learning_preferences(
    prisma: Prisma,
    *,
    user_id: int,
    customer_id: Optional[int],
) -> None:
    try:
        await prisma.execute_raw(
            """
            INSERT INTO "learning_consent_preference" (
              "id",
              "user_id",
              "customer_id",
              "long_term_personalization_opt_in",
              "telemetry_learning_opt_in",
              "created_at",
              "updated_at"
            ) VALUES (
              $1,
              $2,
              $3,
              $4,
              $5,
              NOW(),
              NOW()
            )
            ON CONFLICT ("user_id") DO NOTHING
            """,
            str(uuid4()),
            int(user_id),
            customer_id,
            DEFAULT_LONG_TERM_PERSONALIZATION_OPT_IN,
            DEFAULT_TELEMETRY_LEARNING_OPT_IN,
        )
    except Exception as exc:
        if _is_missing_relation_error(exc):
            return
        raise


async def get_learning_preferences(
    prisma: Prisma,
    *,
    user_id: int,
    customer_id: Optional[int],
) -> dict[str, bool]:
    try:
        await ensure_learning_preferences(
            prisma,
            user_id=user_id,
            customer_id=customer_id,
        )
        rows = await prisma.query_raw(
            """
            SELECT
              "long_term_personalization_opt_in",
              "telemetry_learning_opt_in"
            FROM "learning_consent_preference"
            WHERE "user_id" = $1
            LIMIT 1
            """,
            int(user_id),
        )
    except Exception as exc:
        if _is_missing_relation_error(exc):
            return {
                "long_term_personalization_opt_in": DEFAULT_LONG_TERM_PERSONALIZATION_OPT_IN,
                "telemetry_learning_opt_in": DEFAULT_TELEMETRY_LEARNING_OPT_IN,
            }
        raise
    if not rows:
        return {
            "long_term_personalization_opt_in": DEFAULT_LONG_TERM_PERSONALIZATION_OPT_IN,
            "telemetry_learning_opt_in": DEFAULT_TELEMETRY_LEARNING_OPT_IN,
        }
    row = _row_dict(rows[0])
    return {
        "long_term_personalization_opt_in": _to_bool(
            row.get("long_term_personalization_opt_in"),
            DEFAULT_LONG_TERM_PERSONALIZATION_OPT_IN,
        ),
        "telemetry_learning_opt_in": _to_bool(
            row.get("telemetry_learning_opt_in"),
            DEFAULT_TELEMETRY_LEARNING_OPT_IN,
        ),
    }


async def upsert_learning_preferences(
    prisma: Prisma,
    *,
    user_id: int,
    customer_id: Optional[int],
    long_term_personalization_opt_in: Optional[bool] = None,
    telemetry_learning_opt_in: Optional[bool] = None,
) -> dict[str, bool]:
    current = await get_learning_preferences(
        prisma,
        user_id=user_id,
        customer_id=customer_id,
    )
    next_long_term = (
        bool(long_term_personalization_opt_in)
        if long_term_personalization_opt_in is not None
        else current["long_term_personalization_opt_in"]
    )
    next_telemetry = (
        bool(telemetry_learning_opt_in)
        if telemetry_learning_opt_in is not None
        else current["telemetry_learning_opt_in"]
    )
    try:
        await prisma.execute_raw(
            """
            INSERT INTO "learning_consent_preference" (
              "id",
              "user_id",
              "customer_id",
              "long_term_personalization_opt_in",
              "telemetry_learning_opt_in",
              "created_at",
              "updated_at"
            ) VALUES (
              $1,
              $2,
              $3,
              $4,
              $5,
              NOW(),
              NOW()
            )
            ON CONFLICT ("user_id")
            DO UPDATE SET
              "customer_id" = EXCLUDED."customer_id",
              "long_term_personalization_opt_in" = EXCLUDED."long_term_personalization_opt_in",
              "telemetry_learning_opt_in" = EXCLUDED."telemetry_learning_opt_in",
              "updated_at" = NOW()
            """,
            str(uuid4()),
            int(user_id),
            customer_id,
            next_long_term,
            next_telemetry,
        )
    except Exception as exc:
        if not _is_missing_relation_error(exc):
            raise
    return {
        "long_term_personalization_opt_in": next_long_term,
        "telemetry_learning_opt_in": next_telemetry,
    }


def long_term_memory_allowed(
    *,
    request_consent_long_term: bool,
    preference_long_term_opt_in: bool,
) -> bool:
    return bool(request_consent_long_term and preference_long_term_opt_in)
