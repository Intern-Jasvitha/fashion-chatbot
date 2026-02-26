"""Phase 2 policy agent: rules + LLM classification + hard decision matrix."""

from dataclasses import dataclass
import json
import logging
import re
from typing import Optional

from app.core.config import Settings
from app.core.llm import chat
from app.services.policy_gate import (
    DomainClass,
    PolicyIntent,
    SAFETY_CRITICAL_INTENTS,
    UserState,
    _refusal_for_safety_intent,
    classify_domain,
    classify_intent,
)

logger = logging.getLogger(__name__)

DISALLOWED_INTENTS = {
    PolicyIntent.INTERNAL_METRICS,
    PolicyIntent.FINANCIALS,
    PolicyIntent.POLITICS,
    PolicyIntent.WEATHER,
    PolicyIntent.SECURITY_BYPASS,
    PolicyIntent.PROMPT_INJECTION,
    PolicyIntent.ABUSE_HARASSMENT,
    PolicyIntent.HATE_VIOLENCE,
    PolicyIntent.SEXUAL_CONTENT,
    PolicyIntent.SELF_HARM,
    PolicyIntent.ILLEGAL_INSTRUCTIONS,
}

POLICY_CLASSIFIER_PROMPT = """
You are a strict policy classifier for OASIS Halo, an AI fashion assistant.

Classify the user request into:
- intent: one of [
    ORDER_SUPPORT, DESIGN_SUPPORT, PRODUCT_SUPPORT, ACCOUNT_SUPPORT,
    OASIS_PUBLIC_INFO, ABUSE_HARASSMENT, HATE_VIOLENCE, SEXUAL_CONTENT,
    SELF_HARM, ILLEGAL_INSTRUCTIONS, PROMPT_INJECTION,
    INTERNAL_METRICS, FINANCIALS, POLITICS, WEATHER, UNKNOWN
  ]
- domain: one of [ONLIEST_FASHION, OASIS_PUBLIC, OFF_DOMAIN, CONFIDENTIAL, UNSAFE]
- confidence: number from 0.0 to 1.0

For safety-critical content (ABUSE_HARASSMENT, HATE_VIOLENCE, SEXUAL_CONTENT,
SELF_HARM, ILLEGAL_INSTRUCTIONS, PROMPT_INJECTION), set domain to UNSAFE.

Return ONLY valid JSON in this exact shape:
{"intent":"...", "domain":"...", "confidence":0.0}
"""

_GUEST_SIGNIN_REDIRECT = (
    "Please sign in to continue with order, account, product, or design support."
)
_GUEST_SAFE_ALT = (
    "As a guest, you can ask OASIS public info, such as 'What is OASIS Halo?'."
)
_OFF_DOMAIN_ALT = "I can help with fashion, OASIS products, orders, and account support."
_CONFIDENTIAL_ALT = "I can help with your own account, order, product, and design support requests."


@dataclass(frozen=True)
class PolicyAgentDecision:
    allow: bool
    intent: PolicyIntent
    domain: DomainClass
    confidence: Optional[float]
    reason_code: Optional[str]
    refusal_text: Optional[str]
    decision_source: str
    rules_intent: PolicyIntent
    rules_domain: DomainClass
    llm_intent: Optional[PolicyIntent]
    llm_domain: Optional[DomainClass]
    llm_raw_response: Optional[str]
    llm_error: Optional[str]
    llm_skipped: bool


def _guest_refusal_for_non_public() -> str:
    return f"{_GUEST_SIGNIN_REDIRECT} {_GUEST_SAFE_ALT}"


def _refusal_for_off_domain() -> str:
    return f"I can't help with that topic. {_OFF_DOMAIN_ALT}"


def _refusal_for_confidential() -> str:
    return f"I can't provide confidential, internal, or security-sensitive information. {_CONFIDENTIAL_ALT}"


_SAFETY_REASON_CODES = {
    PolicyIntent.ABUSE_HARASSMENT: "ABUSE_HARASSMENT_BLOCKED",
    PolicyIntent.HATE_VIOLENCE: "HATE_VIOLENCE_BLOCKED",
    PolicyIntent.SEXUAL_CONTENT: "SEXUAL_CONTENT_BLOCKED",
    PolicyIntent.SELF_HARM: "SELF_HARM_DETECTED",
    PolicyIntent.ILLEGAL_INSTRUCTIONS: "ILLEGAL_INSTRUCTIONS_BLOCKED",
    PolicyIntent.PROMPT_INJECTION: "PROMPT_INJECTION_BLOCKED",
    PolicyIntent.SECURITY_BYPASS: "PROMPT_INJECTION_BLOCKED",
}


def _matrix_decision(
    *,
    user_state: UserState,
    intent: PolicyIntent,
    domain: DomainClass,
    support_email: Optional[str] = None,
    support_phone: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[str]]:
    if user_state == UserState.GUEST:
        if domain != DomainClass.OASIS_PUBLIC or intent != PolicyIntent.OASIS_PUBLIC_INFO:
            return False, "GUEST_NON_PUBLIC_BLOCKED", _guest_refusal_for_non_public()

    # Safety-critical intents: always block with intent-specific refusal
    if intent in SAFETY_CRITICAL_INTENTS:
        reason_code = _SAFETY_REASON_CODES.get(
            intent, "UNSAFE_CONTENT_BLOCKED"
        )
        return False, reason_code, _refusal_for_safety_intent(
            intent, support_email=support_email, support_phone=support_phone
        )

    if intent in DISALLOWED_INTENTS:
        if domain == DomainClass.CONFIDENTIAL:
            return False, "DISALLOWED_CONFIDENTIAL", _refusal_for_confidential()
        if domain == DomainClass.UNSAFE:
            return False, "UNSAFE_CONTENT_BLOCKED", _refusal_for_confidential()
        return False, "DISALLOWED_OFF_DOMAIN", _refusal_for_off_domain()

    if user_state == UserState.REGISTERED:
        if domain == DomainClass.CONFIDENTIAL:
            return False, "REGISTERED_CONFIDENTIAL_BLOCKED", _refusal_for_confidential()
        if domain == DomainClass.UNSAFE:
            return False, "UNSAFE_CONTENT_BLOCKED", _refusal_for_confidential()
        if domain == DomainClass.OFF_DOMAIN:
            return False, "REGISTERED_OFF_DOMAIN_BLOCKED", _refusal_for_off_domain()

    if intent == PolicyIntent.UNKNOWN:
        # Allow ambiguous/context-dependent queries through to intent router
        # Intent router can use conversation history to understand context
        return True, None, None

    return True, None, None


def _extract_json_blob(raw: str) -> Optional[dict]:
    text = (raw or "").strip()
    if not text:
        return None

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_intent(raw: object) -> Optional[PolicyIntent]:
    if raw is None:
        return None
    token = str(raw).strip().upper()
    try:
        return PolicyIntent(token)
    except ValueError:
        return None


def _parse_domain(raw: object) -> Optional[DomainClass]:
    if raw is None:
        return None
    token = str(raw).strip().upper()
    try:
        return DomainClass(token)
    except ValueError:
        return None


def _parse_confidence(raw: object) -> Optional[float]:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, value))


async def _llm_classify(message: str, settings: Settings) -> tuple[
    Optional[PolicyIntent],
    Optional[DomainClass],
    Optional[float],
    Optional[str],
    Optional[str],
]:
    msgs = [
        {"role": "system", "content": POLICY_CLASSIFIER_PROMPT},
        {"role": "user", "content": message},
    ]
    try:
        raw = await chat(msgs, settings.LLAMA_URL)
    except Exception as exc:
        return None, None, None, None, str(exc)

    parsed = _extract_json_blob(raw)
    if not parsed:
        return None, None, None, raw, "Classifier response was not valid JSON."

    return (
        _parse_intent(parsed.get("intent")),
        _parse_domain(parsed.get("domain")),
        _parse_confidence(parsed.get("confidence")),
        raw,
        None,
    )


def _matrix_kwargs(settings: Settings) -> dict:
    """Build kwargs for _matrix_decision from settings."""
    return {
        "support_email": getattr(settings, "SELF_HARM_SUPPORT_EMAIL", None),
        "support_phone": getattr(settings, "SELF_HARM_SUPPORT_PHONE", None),
    }


async def evaluate_policy_hard_gate(
    *,
    message: str,
    user_state: UserState,
    settings: Settings,
) -> PolicyAgentDecision:
    """Two-step policy decision: deterministic rules first, then LLM classifier."""
    rules_intent = classify_intent(message)
    rules_domain = classify_domain(message, rules_intent)
    matrix_kwargs = _matrix_kwargs(settings)

    if rules_intent in DISALLOWED_INTENTS:
        allow, reason_code, refusal_text = _matrix_decision(
            user_state=user_state,
            intent=rules_intent,
            domain=rules_domain,
            **matrix_kwargs,
        )
        return PolicyAgentDecision(
            allow=allow,
            intent=rules_intent,
            domain=rules_domain,
            confidence=1.0,
            reason_code=reason_code,
            refusal_text=refusal_text,
            decision_source="rules_block",
            rules_intent=rules_intent,
            rules_domain=rules_domain,
            llm_intent=None,
            llm_domain=None,
            llm_raw_response=None,
            llm_error=None,
            llm_skipped=True,
        )

    llm_intent, llm_domain, llm_confidence, llm_raw, llm_error = await _llm_classify(message, settings)
    if llm_intent and llm_domain:
        allow, reason_code, refusal_text = _matrix_decision(
            user_state=user_state,
            intent=llm_intent,
            domain=llm_domain,
            **matrix_kwargs,
        )
        return PolicyAgentDecision(
            allow=allow,
            intent=llm_intent,
            domain=llm_domain,
            confidence=llm_confidence,
            reason_code=reason_code,
            refusal_text=refusal_text,
            decision_source="llm_classifier",
            rules_intent=rules_intent,
            rules_domain=rules_domain,
            llm_intent=llm_intent,
            llm_domain=llm_domain,
            llm_raw_response=llm_raw,
            llm_error=None,
            llm_skipped=False,
        )

    logger.warning("Policy classifier fallback to rules | error=%s | raw=%s", llm_error, llm_raw)
    allow, reason_code, refusal_text = _matrix_decision(
        user_state=user_state,
        intent=rules_intent,
        domain=rules_domain,
        **matrix_kwargs,
    )
    return PolicyAgentDecision(
        allow=allow,
        intent=rules_intent,
        domain=rules_domain,
        confidence=llm_confidence,
        reason_code=reason_code,
        refusal_text=refusal_text,
        decision_source="llm_fallback_rules",
        rules_intent=rules_intent,
        rules_domain=rules_domain,
        llm_intent=None,
        llm_domain=None,
        llm_raw_response=llm_raw,
        llm_error=llm_error or "Classifier output missing required fields.",
        llm_skipped=False,
    )
