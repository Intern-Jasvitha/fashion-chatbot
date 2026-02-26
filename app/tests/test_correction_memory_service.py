from types import SimpleNamespace

import pytest

from app.services.correction_memory_service import (
    MEMORY_SCOPE_LONG_TERM,
    MEMORY_SCOPE_SESSION,
    create_correction_memory,
    load_correction_hints,
)


class FakePrisma:
    def __init__(self) -> None:
        self.events = []

    async def execute_raw(self, query, *args):
        self.events.append((query, args))

    async def query_raw(self, query, *args):
        if "memory_scope" in query and "SESSION" in query:
            return [
                {"instruction_redacted": "Use shorter bullets.", "instruction_hash": "h1"},
                {"instruction_redacted": "Use shorter bullets.", "instruction_hash": "h1"},
            ]
        if "LONG_TERM" in query:
            return [
                SimpleNamespace(instruction_redacted="Prefer neutral color palette.", instruction_hash="h2"),
            ]
        return []


@pytest.mark.asyncio
async def test_create_correction_memory_redacts_text() -> None:
    prisma = FakePrisma()
    memory_id = await create_correction_memory(
        prisma,
        session_id="sess-1",
        message_id="msg-1",
        source_feedback_id="fb-1",
        user_id=1,
        customer_id=2,
        instruction_text="contact me at me@example.com",
        memory_scope=MEMORY_SCOPE_SESSION,
        consent_long_term=False,
    )

    assert isinstance(memory_id, str)
    assert len(prisma.events) == 1
    _, args = prisma.events[0]
    assert "me@example.com" not in args[7]


@pytest.mark.asyncio
async def test_load_correction_hints_merges_scopes_and_dedupes() -> None:
    prisma = FakePrisma()
    hints = await load_correction_hints(
        prisma,
        session_id="sess-1",
        user_id=1,
        customer_id=2,
        max_items=8,
    )

    assert hints == ["Use shorter bullets.", "Prefer neutral color palette."]


@pytest.mark.asyncio
async def test_load_correction_hints_without_identity_returns_session_only() -> None:
    prisma = FakePrisma()
    hints = await load_correction_hints(
        prisma,
        session_id="sess-1",
        user_id=None,
        customer_id=None,
        max_items=8,
    )

    assert hints == ["Use shorter bullets."]
