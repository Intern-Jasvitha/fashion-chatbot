import pytest

from app.services.telemetry_service import (
    EVENT_TOOL_CALL,
    emit_trace_tool_events,
    hash_text,
    redact_text,
    required_field_coverage,
)


class FakePrisma:
    def __init__(self) -> None:
        self.events = []

    async def execute_raw(self, query, *args):
        self.events.append((query, args))



def test_redaction_and_hash_are_deterministic() -> None:
    raw = "Email me at person@example.com or call +1 (555) 111-2222. Ticket 123456789"
    redacted = redact_text(raw)
    assert "person@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert ("[REDACTED_NUMBER]" in redacted) or ("[REDACTED_PHONE]" in redacted)

    h1 = hash_text(raw)
    h2 = hash_text(raw)
    assert h1 == h2
    assert len(h1) == 64


def test_required_field_coverage_contract() -> None:
    payload = {
        "request_id": "req-1",
        "session_id": "sess-1",
        "turn_index": 1,
        "event_type": "USER_MSG",
        "created_at": "2026-02-19T00:00:00+00:00",
    }
    assert required_field_coverage(payload) >= 0.95


@pytest.mark.asyncio
async def test_emit_trace_tool_events_creates_one_event_per_trace_step() -> None:
    prisma = FakePrisma()
    trace = {
        "steps": [
            {
                "step": "intent_router",
                "agent": "intent_router",
                "status": "ok",
                "summary": "Routed request",
                "duration_ms": 12,
                "details": {"intent": "hybrid"},
            },
            {
                "step": "learning_turn_quality",
                "agent": "learning_engine",
                "status": "ok",
                "summary": "Computed scores",
                "details": {"tqs": 42, "kgs": 81},
            },
        ]
    }

    await emit_trace_tool_events(
        prisma,
        request_id="req-1",
        session_id="sess-1",
        turn_index=1,
        created_at_iso="2026-02-19T00:00:00+00:00",
        trace=trace,
        assistant_message_id="msg-a",
        user_id=7,
        customer_id=8,
    )

    assert len(prisma.events) == 2
    for _, args in prisma.events:
        # 5th arg is event_type by insertion order in emit_event
        assert args[4] == EVENT_TOOL_CALL
