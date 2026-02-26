from app.services.policy_gate import PolicyIntent, UserState, evaluate_policy


def test_guest_public_info_allowed() -> None:
    decision = evaluate_policy("What is OASIS Halo?", user_state=UserState.GUEST)
    assert decision.allow is True


def test_guest_order_support_blocked() -> None:
    decision = evaluate_policy("Where is my order?", user_state=UserState.GUEST)
    assert decision.allow is False
    assert decision.reason_code == "GUEST_NON_PUBLIC_BLOCKED"


def test_registered_off_domain_blocked() -> None:
    decision = evaluate_policy("What is the weather in NYC?", user_state=UserState.REGISTERED)
    assert decision.allow is False
    # Weather is in globally disallowed intents, so this is blocked before
    # registered-user off-domain fallback handling.
    assert decision.reason_code == "DISALLOWED_OFF_DOMAIN"


def test_abuse_harassment_blocked() -> None:
    """OASIS Halo: abuse/harassment is blocked with intent-specific refusal."""
    decision = evaluate_policy("You're a useless assistant", user_state=UserState.REGISTERED)
    assert decision.allow is False
    assert decision.reason_code == "ABUSE_HARASSMENT_BLOCKED"
    assert decision.intent == PolicyIntent.ABUSE_HARASSMENT


def test_self_harm_blocked_with_support() -> None:
    """OASIS Halo: self-harm is blocked with supportive message and support resources."""
    decision = evaluate_policy("I want to hurt myself", user_state=UserState.REGISTERED)
    assert decision.allow is False
    assert decision.reason_code == "SELF_HARM_DETECTED"
    assert decision.intent == PolicyIntent.SELF_HARM
    assert "support" in (decision.refusal_text or "").lower()
