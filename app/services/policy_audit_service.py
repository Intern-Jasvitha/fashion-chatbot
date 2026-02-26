"""Persistence helpers for policy hard-gate audit records."""

import json
from typing import Optional
from uuid import uuid4

from prisma import Prisma

from app.services.policy_gate import UserState


async def save_policy_audit(
    prisma: Prisma,
    *,
    request_id: str,
    session_id: str,
    user_id: Optional[int],
    user_state: UserState,
    message: str,
    policy_intent: str,
    policy_domain: str,
    classifier_confidence: Optional[float],
    allow: bool,
    reason_code: Optional[str],
    decision_source: str,
    trace: Optional[dict],
) -> None:
    """Persist one policy decision audit row."""
    trace_json: Optional[str] = None
    if trace is not None:
        trace_json = json.dumps(trace, default=str)
    audit_id = str(uuid4())

    await prisma.execute_raw(
        """
        INSERT INTO "policy_audit" (
            "id",
            "request_id",
            "session_id",
            "user_id",
            "user_state",
            "message",
            "policy_intent",
            "policy_domain",
            "classifier_confidence",
            "allow",
            "reason_code",
            "decision_source",
            "trace_json"
        ) VALUES (
            $1,
            $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
        """,
        audit_id,
        request_id,
        session_id,
        user_id,
        user_state.value,
        message,
        policy_intent,
        policy_domain,
        classifier_confidence,
        allow,
        reason_code,
        decision_source,
        trace_json,
    )
