"""Learning governance guardrails for telemetry and long-term personalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from prisma import Prisma

from app.services.telemetry_service import hash_text, redact_text


_SENSITIVE_PATTERNS = [
    re.compile(r"\b(ssn|social security|credit card|cvv|cvc|bank account|routing number)\b", re.IGNORECASE),
    re.compile(r"\b(secret key|api key|private key|password|admin password|token)\b", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN shape
]


@dataclass(frozen=True)
class LearningGuardrailDecision:
    learning_allowed: bool
    exclusion_reason_code: Optional[str]
    policy_reason_code: Optional[str]
    content_hash: str
    content_redacted: str


def _matches_sensitive_pattern(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def classify_learning_eligibility(
    *,
    content: str,
    policy_allow: bool,
    policy_reason_code: Optional[str],
    telemetry_opt_in: bool,
) -> LearningGuardrailDecision:
    redacted = redact_text(content or "")
    digest = hash_text(content or "")

    if not telemetry_opt_in:
        return LearningGuardrailDecision(
            learning_allowed=False,
            exclusion_reason_code="USER_TELEMETRY_OPTOUT",
            policy_reason_code=policy_reason_code,
            content_hash=digest,
            content_redacted=redacted,
        )
    if not policy_allow:
        return LearningGuardrailDecision(
            learning_allowed=False,
            exclusion_reason_code="POLICY_BLOCKED",
            policy_reason_code=policy_reason_code,
            content_hash=digest,
            content_redacted=redacted,
        )
    if _matches_sensitive_pattern(content):
        return LearningGuardrailDecision(
            learning_allowed=False,
            exclusion_reason_code="SENSITIVE_PATTERN",
            policy_reason_code=policy_reason_code,
            content_hash=digest,
            content_redacted=redacted,
        )
    return LearningGuardrailDecision(
        learning_allowed=True,
        exclusion_reason_code=None,
        policy_reason_code=policy_reason_code,
        content_hash=digest,
        content_redacted=redacted,
    )


async def create_learning_exclusion_audit(
    prisma: Prisma,
    *,
    request_id: str,
    session_id: str,
    message_id: Optional[str],
    user_id: Optional[int],
    customer_id: Optional[int],
    exclusion_reason_code: str,
    policy_reason_code: Optional[str],
    content: str,
) -> str:
    audit_id = str(uuid4())
    await prisma.execute_raw(
        """
        INSERT INTO "learning_exclusion_audit" (
          "id",
          "request_id",
          "session_id",
          "message_id",
          "user_id",
          "customer_id",
          "exclusion_reason_code",
          "policy_reason_code",
          "content_hash",
          "content_redacted",
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
          NOW()
        )
        """,
        audit_id,
        request_id,
        session_id,
        message_id,
        user_id,
        customer_id,
        exclusion_reason_code,
        policy_reason_code,
        hash_text(content or ""),
        redact_text(content or ""),
    )
    return audit_id
