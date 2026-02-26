from types import SimpleNamespace

import pytest

from app.services.feedback_service import create_feedback, ensure_message_in_session, get_latest_feedback_map


class FakePrisma:
    def __init__(self) -> None:
        self.events = []
        self.message_exists = True
        self.feedback_rows = [
            {"message_id": "msg-1", "feedback_type": "UP"},
            SimpleNamespace(message_id="msg-2", feedback_type="DOWN"),
        ]

    async def query_raw(self, query, *args):
        if 'FROM "chat_message"' in query:
            return [SimpleNamespace(ok=1)] if self.message_exists else []
        if 'FROM "chat_feedback"' in query:
            return self.feedback_rows
        return []

    async def execute_raw(self, query, *args):
        self.events.append((query, args))


@pytest.mark.asyncio
async def test_ensure_message_in_session_validates_ownership() -> None:
    prisma = FakePrisma()
    assert await ensure_message_in_session(prisma, session_id="sess-1", message_id="msg-1") is True

    prisma.message_exists = False
    assert await ensure_message_in_session(prisma, session_id="sess-1", message_id="msg-1") is False


@pytest.mark.asyncio
async def test_create_feedback_redacts_correction_text() -> None:
    prisma = FakePrisma()
    feedback_id = await create_feedback(
        prisma,
        session_id="sess-1",
        message_id="msg-1",
        user_id=1,
        customer_id=2,
        feedback_type="DOWN",
        reason_code="INCORRECT",
        correction_text="My email is person@example.com",
    )

    assert isinstance(feedback_id, str)
    assert len(prisma.events) == 1
    _, args = prisma.events[0]
    # args[7] = redacted content, args[8] = payload_json
    assert "person@example.com" not in (args[7] or "")
    assert "REDACTED_EMAIL" in (args[7] or "")


@pytest.mark.asyncio
async def test_get_latest_feedback_map_per_message() -> None:
    prisma = FakePrisma()
    result = await get_latest_feedback_map(prisma, session_id="sess-1", user_id=10)
    assert result == {"msg-1": "UP", "msg-2": "DOWN"}

    empty = await get_latest_feedback_map(prisma, session_id="sess-1", user_id=None)
    assert empty == {}
