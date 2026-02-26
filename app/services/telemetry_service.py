"""Telemetry utilities for self-learning event capture."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional
from uuid import uuid4

from prisma import Prisma

EVENT_USER_MSG = "USER_MSG"
EVENT_ASSISTANT_MSG = "ASSISTANT_MSG"
EVENT_TOOL_CALL = "TOOL_CALL"
EVENT_TURN_SCORE = "TURN_SCORE"
EVENT_CANDIDATE_SNAPSHOT = "CANDIDATE_SNAPSHOT"
EVENT_FEEDBACK = "FEEDBACK"
EVENT_HANDOFF = "HANDOFF"

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){1,2}\d{4}\b")
_LONG_NUMBER_RE = re.compile(r"\b\d{8,}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact_text(raw: str) -> str:
    """Mask common PII patterns before storing telemetry content."""
    text = (raw or "").strip()
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _SSN_RE.sub("[REDACTED_SSN]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _LONG_NUMBER_RE.sub("[REDACTED_NUMBER]", text)
    return text


def hash_text(raw: str) -> str:
    """Return SHA256 for idempotent content identity tracking."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def required_field_coverage(event_payload: dict[str, Any]) -> float:
    """Measure required field coverage for telemetry contract tests."""
    required = (
        "request_id",
        "session_id",
        "turn_index",
        "event_type",
        "created_at",
    )
    present = 0
    for key in required:
        if event_payload.get(key) not in (None, ""):
            present += 1
    return present / float(len(required))


def _safe_payload_json(payload: Optional[dict[str, Any]]) -> Optional[str]:
    if payload is None:
        return None
    return json.dumps(payload, default=str)


async def emit_event(
    prisma: Prisma,
    *,
    request_id: str,
    session_id: str,
    turn_index: int,
    event_type: str,
    created_at_iso: str,
    message_id: Optional[str] = None,
    user_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    content: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    learning_allowed: bool = True,
    learning_exclusion_reason: Optional[str] = None,
) -> None:
    """Persist one telemetry event row in chat_event_log."""
    content_hash = hash_text(content) if content else None
    content_redacted = redact_text(content) if content else None
    payload_json = _safe_payload_json(payload)

    await prisma.execute_raw(
        """
        INSERT INTO "chat_event_log" (
            "id",
            "request_id",
            "session_id",
            "turn_index",
            "event_type",
            "message_id",
            "user_id",
            "customer_id",
            "content_hash",
            "content_redacted",
            "payload_json",
            "learning_allowed",
            "learning_exclusion_reason",
            "created_at"
        ) VALUES (
            $1,
            $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::timestamptz
        )
        """,
        str(uuid4()),
        request_id,
        session_id,
        int(turn_index),
        event_type,
        message_id,
        user_id,
        customer_id,
        content_hash,
        content_redacted,
        payload_json,
        bool(learning_allowed),
        learning_exclusion_reason,
        created_at_iso,
    )


async def emit_trace_tool_events(
    prisma: Prisma,
    *,
    request_id: str,
    session_id: str,
    turn_index: int,
    created_at_iso: str,
    trace: Optional[dict[str, Any]],
    assistant_message_id: Optional[str],
    user_id: Optional[int],
    customer_id: Optional[int],
    learning_allowed: bool = True,
    learning_exclusion_reason: Optional[str] = None,
) -> None:
    """Map debug trace steps to TOOL_CALL telemetry events."""
    steps = []
    if isinstance(trace, dict):
        raw_steps = trace.get("steps") or []
        if isinstance(raw_steps, list):
            steps = [s for s in raw_steps if isinstance(s, dict)]

    for step in steps:
        payload = {
            "step": step.get("step"),
            "agent": step.get("agent"),
            "status": step.get("status"),
            "summary": step.get("summary"),
            "duration_ms": step.get("duration_ms"),
            "details": step.get("details") if isinstance(step.get("details"), dict) else {},
        }
        await emit_event(
            prisma,
            request_id=request_id,
            session_id=session_id,
            turn_index=turn_index,
            event_type=EVENT_TOOL_CALL,
            created_at_iso=created_at_iso,
            message_id=assistant_message_id,
            user_id=user_id,
            customer_id=customer_id,
            payload=payload,
            learning_allowed=learning_allowed,
            learning_exclusion_reason=learning_exclusion_reason,
        )
