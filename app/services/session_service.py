"""
Session service: get/create chat sessions, load last N messages, save turns.
Conversation history is stored in PostgreSQL and used as LLM context (last 10 messages).
"""

import json
from typing import Optional

from prisma import Prisma

HISTORY_LIMIT = 10


async def get_or_create_session(prisma: Prisma, session_id: Optional[str] = None) -> str:
    """Return session_id if provided and exists; otherwise create a new ChatSession and return its id."""
    if session_id:
        existing = await prisma.chatsession.find_unique(where={"id": session_id})
        if existing:
            return existing.id
        session = await prisma.chatsession.create(data={"id": session_id})
        return session.id
    session = await prisma.chatsession.create(data={})
    return session.id


async def get_full_history(prisma: Prisma, session_id: str) -> list[dict]:
    """Fetch all messages for session ordered by createdAt ascending; for API history response."""
    messages = await prisma.chatmessage.find_many(
        where={"sessionId": session_id},
        order={"createdAt": "asc"},
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": getattr(m, "createdAt", None) or getattr(m, "created_at", None),
        }
        for m in messages
    ]


async def load_history(prisma: Prisma, session_id: str, limit: int = HISTORY_LIMIT) -> list[dict[str, str]]:
    """Fetch messages for session ordered by createdAt ascending; return only the last `limit` messages."""
    messages = await prisma.chatmessage.find_many(
        where={"sessionId": session_id},
        order={"createdAt": "asc"},
    )
    # Keep last `limit` messages
    trimmed = messages[-limit:] if len(messages) > limit else messages
    return [{"role": m.role, "content": m.content} for m in trimmed]


async def save_turn(
    prisma: Prisma,
    session_id: str,
    user_content: str,
    assistant_content: str,
    assistant_trace: Optional[dict] = None,
) -> dict[str, str]:
    """Append one user message and one assistant message to the session and return message ids."""
    trace_json: Optional[str] = None
    if assistant_trace is not None:
        trace_json = json.dumps(assistant_trace, default=str)

    user_row = await prisma.chatmessage.create(
        data={"sessionId": session_id, "role": "user", "content": user_content, "traceJson": None}
    )
    assistant_row = await prisma.chatmessage.create(
        data={"sessionId": session_id, "role": "assistant", "content": assistant_content, "traceJson": trace_json}
    )
    return {
        "user_message_id": user_row.id,
        "assistant_message_id": assistant_row.id,
    }


async def get_latest_assistant_trace(prisma: Prisma, session_id: str) -> Optional[dict]:
    """Return latest persisted assistant trace for a session, if present and valid JSON."""
    rows = await prisma.chatmessage.find_many(
        where={"sessionId": session_id, "role": "assistant"},
        order={"createdAt": "desc"},
    )
    for row in rows:
        raw = getattr(row, "traceJson", None) or getattr(row, "trace_json", None)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


async def get_latest_user_message(prisma: Prisma, session_id: str) -> Optional[str]:
    """Return latest user message text for a session, if any."""
    rows = await prisma.chatmessage.find_many(
        where={"sessionId": session_id, "role": "user"},
        order={"createdAt": "desc"},
    )
    if not rows:
        return None
    latest = rows[0]
    content = getattr(latest, "content", None)
    return str(content) if content is not None else None
