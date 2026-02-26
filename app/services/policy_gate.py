"""Deterministic Phase 1 policy gate for role/state and scope enforcement."""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional, Sequence


class UserState(str, Enum):
    GUEST = "GUEST"
    REGISTERED = "REGISTERED"


class DomainClass(str, Enum):
    ONLIEST_FASHION = "ONLIEST_FASHION"
    OASIS_PUBLIC = "OASIS_PUBLIC"
    OFF_DOMAIN = "OFF_DOMAIN"
    CONFIDENTIAL = "CONFIDENTIAL"
    UNSAFE = "UNSAFE"


class PolicyIntent(str, Enum):
    ORDER_SUPPORT = "ORDER_SUPPORT"
    DESIGN_SUPPORT = "DESIGN_SUPPORT"
    PRODUCT_SUPPORT = "PRODUCT_SUPPORT"
    ACCOUNT_SUPPORT = "ACCOUNT_SUPPORT"
    OASIS_PUBLIC_INFO = "OASIS_PUBLIC_INFO"
    INTERNAL_METRICS = "INTERNAL_METRICS"
    FINANCIALS = "FINANCIALS"
    POLITICS = "POLITICS"
    WEATHER = "WEATHER"
    SECURITY_BYPASS = "SECURITY_BYPASS"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    ABUSE_HARASSMENT = "ABUSE_HARASSMENT"
    HATE_VIOLENCE = "HATE_VIOLENCE"
    SEXUAL_CONTENT = "SEXUAL_CONTENT"
    SELF_HARM = "SELF_HARM"
    ILLEGAL_INSTRUCTIONS = "ILLEGAL_INSTRUCTIONS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PolicyDecision:
    allow: bool
    intent: PolicyIntent
    domain: DomainClass
    reason_code: Optional[str]
    refusal_text: Optional[str]


# ---------------------------------------------------------------------
# SAFETY-CRITICAL PATTERNS (checked first)
# ---------------------------------------------------------------------

_ABUSE_HARASSMENT_RE = re.compile(
    r"\b(fuck|shit|damn|bastard|idiot|stupid|useless|incompetent|"
    r"hate\s+you|shut\s+up|offensive|profanity|insult|harass|"
    r"dumb\s+assistant|worthless|pathetic|moron)\b",
    re.IGNORECASE,
)
_HATE_VIOLENCE_RE = re.compile(
    r"\b(kill|murder|attack|threaten|bomb|weapon|terrorist|"
    r"hate\s+groups?|racial\s+slur|ethnic\s+cleansing|genocide|"
    r"violence|assault|harm\s+someone)\b",
    re.IGNORECASE,
)
_SEXUAL_CONTENT_RE = re.compile(
    r"\b(sex|sexual\s+content|porn|explicit|nude|nsfw|adult\s+content|"
    r"xxx|erotic)\b",
    re.IGNORECASE,
)
_SELF_HARM_RE = re.compile(
    r"\b(suicide|self\s*harm|cut\s*myself|end\s*my\s*life|kill\s*myself|"
    r"hurt\s*myself|self\s*injury)\b",
    re.IGNORECASE,
)
_ILLEGAL_INSTRUCTIONS_RE = re.compile(
    r"\b(fraud|scam|hack|crack|exploit|steal|counterfeit|forge|"
    r"illegal\s+drugs|money\s+laundering|tax\s+evasion|"
    r"weapon\s+instructions|make\s+a\s+bomb)\b",
    re.IGNORECASE,
)
_PROMPT_INJECTION_RE = re.compile(
    r"\b(bypass|jailbreak|ignore\s+.*instructions?|ignore\s*policy|"
    r"secret\s+key|admin\s+password|disable\s+auth|prompt\s+injection|"
    r"reveal\s+secrets|forget\s+.*rules|new\s+instructions?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------
# ALLOWED / OFF-DOMAIN PATTERNS
# ---------------------------------------------------------------------

_ORDER_RE = re.compile(
    r"\b(order|orders|shipment|shipping|deliver|delivery|tracking|track|"
    r"ticket|tickets|purchase|purchases|return|refund)\b"
)
_DESIGN_RE = re.compile(
    r"\b(design|style|styling|outfit|occasion|fabric|color|dress|fit|"
    r"body\s+type|look|sleeve|mannequin|banarasi|wedding|saree|kurta)\b"
)
_PRODUCT_RE = re.compile(
    r"\b(product|products|catalog|item|items|brand|brands|size|sizes|"
    r"material|collection|handloom|price|pricing)\b"
)
_ACCOUNT_RE = re.compile(
    r"\b(account|profile|login|signup|password|email|phone|address|"
    r"billing|payment\s+method|update\s+email)\b"
)
_OASIS_PUBLIC_RE = re.compile(
    r"\b(oasis|halo|public\s+info|about\s+oasis|what\s+is\s+oasis|"
    r"company\s+overview|design\s+studio)\b"
)
_INTERNAL_METRICS_RE = re.compile(
    r"\b(internal\s+metric|internal\s+metrics|all\s+users|all\s+customers|"
    r"across\s+customers|overall\s+count|company-wide)\b"
)
_FINANCIALS_RE = re.compile(
    r"\b(financial|financials|revenue|profit|sales|margin|income|earnings)\b"
)
_POLITICS_RE = re.compile(
    r"\b(politics|political|election|president|prime\s+minister|"
    r"senate|parliament|vote|campaign)\b"
)
_WEATHER_RE = re.compile(
    r"\b(weather|temperature|forecast|rain|snow|humidity|wind)\b"
)
_SECURITY_BYPASS_RE = _PROMPT_INJECTION_RE  # backward compatibility

_GUEST_SIGNIN_REDIRECT = (
    "Please sign in to continue with order, account, product, or design support."
)
_GUEST_SAFE_ALT = (
    "As a guest, you can ask OASIS public info, such as 'What is OASIS Halo?'."
)
_OFF_DOMAIN_ALT = "I can help with fashion, OASIS products, orders, and account support."
_CONFIDENTIAL_ALT = "I can help with your own account, order, product, and design support requests."

# Severity-based refusal templates for safety-critical content
_HATE_VIOLENCE_REFUSAL = (
    "I cannot assist with content involving hate speech, violence, or threats. "
    "This type of content violates our community guidelines. "
    "I can help with fashion design, product guidance, and order support."
)
def _get_self_harm_refusal(
    support_email: str = "support@onliest.ai",
    support_phone: str = "1-800-XXX-XXXX",
) -> str:
    return (
        f"I'm concerned about what you're going through. Please reach out to Onliest Support "
        f"at {support_email} or call our wellness line at {support_phone}. "
        f"I'm here to help with fashion and product questions when you're ready."
    )
_ABUSE_REFUSAL = (
    "Please communicate respectfully. I'm here to help with Onliest products, "
    "design guidance, and platform support."
)
_ILLEGAL_CONTENT_REFUSAL = (
    "I cannot provide assistance with that request. "
    "I can help with fashion design, product support, and order assistance."
)
_SEXUAL_CONTENT_REFUSAL = (
    "I cannot assist with that type of content. "
    "I can help with fashion design, product guidance, and platform support."
)
_PROMPT_INJECTION_REFUSAL = (
    "I cannot comply with that request. "
    "I'm here to help with Onliest products, design guidance, and order support."
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_intent(message: str) -> PolicyIntent:
    """Classify user message intent. Safety-critical patterns are checked first."""
    text = _normalize(message)
    # Safety-critical patterns (checked first for fast blocking)
    if _SELF_HARM_RE.search(text):
        return PolicyIntent.SELF_HARM
    if _HATE_VIOLENCE_RE.search(text):
        return PolicyIntent.HATE_VIOLENCE
    if _ABUSE_HARASSMENT_RE.search(text):
        return PolicyIntent.ABUSE_HARASSMENT
    if _SEXUAL_CONTENT_RE.search(text):
        return PolicyIntent.SEXUAL_CONTENT
    if _ILLEGAL_INSTRUCTIONS_RE.search(text):
        return PolicyIntent.ILLEGAL_INSTRUCTIONS
    if _PROMPT_INJECTION_RE.search(text):
        return PolicyIntent.PROMPT_INJECTION
    if _INTERNAL_METRICS_RE.search(text):
        return PolicyIntent.INTERNAL_METRICS
    if _FINANCIALS_RE.search(text):
        return PolicyIntent.FINANCIALS
    if _POLITICS_RE.search(text):
        return PolicyIntent.POLITICS
    if _WEATHER_RE.search(text):
        return PolicyIntent.WEATHER
    if _OASIS_PUBLIC_RE.search(text):
        return PolicyIntent.OASIS_PUBLIC_INFO
    if _ORDER_RE.search(text):
        return PolicyIntent.ORDER_SUPPORT
    if _DESIGN_RE.search(text):
        return PolicyIntent.DESIGN_SUPPORT
    if _ACCOUNT_RE.search(text):
        return PolicyIntent.ACCOUNT_SUPPORT
    if _PRODUCT_RE.search(text):
        return PolicyIntent.PRODUCT_SUPPORT
    return PolicyIntent.UNKNOWN


SAFETY_CRITICAL_INTENTS = frozenset({
    PolicyIntent.ABUSE_HARASSMENT,
    PolicyIntent.HATE_VIOLENCE,
    PolicyIntent.SEXUAL_CONTENT,
    PolicyIntent.SELF_HARM,
    PolicyIntent.ILLEGAL_INSTRUCTIONS,
    PolicyIntent.PROMPT_INJECTION,
    PolicyIntent.SECURITY_BYPASS,
})


def classify_domain(message: str, intent: PolicyIntent) -> DomainClass:
    text = _normalize(message)
    if intent in SAFETY_CRITICAL_INTENTS:
        return DomainClass.UNSAFE
    if intent in {
        PolicyIntent.INTERNAL_METRICS,
        PolicyIntent.FINANCIALS,
    }:
        return DomainClass.CONFIDENTIAL
    if intent in {PolicyIntent.POLITICS, PolicyIntent.WEATHER}:
        return DomainClass.OFF_DOMAIN
    if intent == PolicyIntent.OASIS_PUBLIC_INFO:
        return DomainClass.OASIS_PUBLIC
    if intent in {
        PolicyIntent.ORDER_SUPPORT,
        PolicyIntent.DESIGN_SUPPORT,
        PolicyIntent.PRODUCT_SUPPORT,
        PolicyIntent.ACCOUNT_SUPPORT,
    }:
        return DomainClass.ONLIEST_FASHION
    if _OASIS_PUBLIC_RE.search(text):
        return DomainClass.OASIS_PUBLIC
    return DomainClass.OFF_DOMAIN


def _refusal_for_safety_intent(
    intent: PolicyIntent,
    support_email: Optional[str] = None,
    support_phone: Optional[str] = None,
) -> str:
    """Return appropriate refusal text for safety-critical intents."""
    if intent == PolicyIntent.HATE_VIOLENCE:
        return _HATE_VIOLENCE_REFUSAL
    if intent == PolicyIntent.SELF_HARM:
        return _get_self_harm_refusal(
            support_email or "support@onliest.ai",
            support_phone or "1-800-XXX-XXXX",
        )
    if intent == PolicyIntent.ABUSE_HARASSMENT:
        return _ABUSE_REFUSAL
    if intent == PolicyIntent.ILLEGAL_INSTRUCTIONS:
        return _ILLEGAL_CONTENT_REFUSAL
    if intent == PolicyIntent.SEXUAL_CONTENT:
        return _SEXUAL_CONTENT_REFUSAL
    if intent in {PolicyIntent.PROMPT_INJECTION, PolicyIntent.SECURITY_BYPASS}:
        return _PROMPT_INJECTION_REFUSAL
    return _ILLEGAL_CONTENT_REFUSAL


def _guest_refusal_for_non_public() -> str:
    return f"{_GUEST_SIGNIN_REDIRECT} {_GUEST_SAFE_ALT}"


def _refusal_for_off_domain() -> str:
    return f"I can't help with that topic. {_OFF_DOMAIN_ALT}"


def _refusal_for_confidential() -> str:
    return f"I can't provide confidential, internal, or security-sensitive information. {_CONFIDENTIAL_ALT}"


def evaluate_policy(
    message: str,
    user_state: UserState,
    roles: Optional[Sequence[str]] = None,
    consent_flags: Optional[dict[str, bool]] = None,
    active_order_id: Optional[str] = None,
    active_design_id: Optional[str] = None,
) -> PolicyDecision:
    """Evaluate policy decision before routing to any agent."""
    del roles, consent_flags, active_order_id, active_design_id

    intent = classify_intent(message)
    domain = classify_domain(message, intent)

    # Safety-critical intents: always block with intent-specific refusal
    if intent in SAFETY_CRITICAL_INTENTS:
        reason_code = {
            PolicyIntent.ABUSE_HARASSMENT: "ABUSE_HARASSMENT_BLOCKED",
            PolicyIntent.HATE_VIOLENCE: "HATE_VIOLENCE_BLOCKED",
            PolicyIntent.SEXUAL_CONTENT: "SEXUAL_CONTENT_BLOCKED",
            PolicyIntent.SELF_HARM: "SELF_HARM_DETECTED",
            PolicyIntent.ILLEGAL_INSTRUCTIONS: "ILLEGAL_INSTRUCTIONS_BLOCKED",
            PolicyIntent.PROMPT_INJECTION: "PROMPT_INJECTION_BLOCKED",
            PolicyIntent.SECURITY_BYPASS: "PROMPT_INJECTION_BLOCKED",
        }.get(intent, "UNSAFE_CONTENT_BLOCKED")
        return PolicyDecision(
            allow=False,
            intent=intent,
            domain=domain,
            reason_code=reason_code,
            refusal_text=_refusal_for_safety_intent(intent),
        )

    if intent in {
        PolicyIntent.INTERNAL_METRICS,
        PolicyIntent.FINANCIALS,
        PolicyIntent.POLITICS,
        PolicyIntent.WEATHER,
    }:
        if domain == DomainClass.CONFIDENTIAL:
            return PolicyDecision(
                allow=False,
                intent=intent,
                domain=domain,
                reason_code="DISALLOWED_CONFIDENTIAL",
                refusal_text=_refusal_for_confidential(),
            )
        return PolicyDecision(
            allow=False,
            intent=intent,
            domain=domain,
            reason_code="DISALLOWED_OFF_DOMAIN",
            refusal_text=_refusal_for_off_domain(),
        )

    if user_state == UserState.GUEST:
        if domain != DomainClass.OASIS_PUBLIC or intent != PolicyIntent.OASIS_PUBLIC_INFO:
            return PolicyDecision(
                allow=False,
                intent=intent,
                domain=domain,
                reason_code="GUEST_NON_PUBLIC_BLOCKED",
                refusal_text=_guest_refusal_for_non_public(),
            )

    if user_state == UserState.REGISTERED:
        if domain == DomainClass.CONFIDENTIAL:
            return PolicyDecision(
                allow=False,
                intent=intent,
                domain=domain,
                reason_code="REGISTERED_CONFIDENTIAL_BLOCKED",
                refusal_text=_refusal_for_confidential(),
            )
        if domain == DomainClass.OFF_DOMAIN:
            return PolicyDecision(
                allow=False,
                intent=intent,
                domain=domain,
                reason_code="REGISTERED_OFF_DOMAIN_BLOCKED",
                refusal_text=_refusal_for_off_domain(),
            )

    if intent == PolicyIntent.UNKNOWN:
        # Allow ambiguous/context-dependent queries through to intent router
        # Intent router can use conversation history to understand context
        return PolicyDecision(
            allow=True,
            intent=intent,
            domain=domain,
            reason_code=None,
            refusal_text=None,
        )

    return PolicyDecision(
        allow=True,
        intent=intent,
        domain=domain,
        reason_code=None,
        refusal_text=None,
    )
