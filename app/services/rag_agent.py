"""
Human conversational RAG Agent (memory-aware)
Supports:
1) Knowledge retrieval from Qdrant
2) Conversation memory recall from session history
"""

import logging
from typing import Any, List, Optional

from qdrant_client import QdrantClient

from app.core.config import Settings
from app.core.embeddings import embed_query
from app.core.llm import chat

logger = logging.getLogger(__name__)

TOP_K = 12
FINAL_K = 4

# ---------------------------------------------------------------------
# MEMORY QUESTION DETECTION
# ---------------------------------------------------------------------

MEMORY_PATTERNS = [
    "what did i ask",
    "what did i say",
    "my last message",
    "previous message",
    "earlier i said",
    "summarize our conversation",
    "recall our conversation",
    "what was my question",
    "what did i ask first",
    "what did i just say",
]

def is_memory_question(message: str) -> bool:
    msg = message.lower()
    return any(p in msg for p in MEMORY_PATTERNS)


# ---------------------------------------------------------------------
# PROMPTS
# ---------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """
You are a friendly fashion and design assistant.

Speak naturally and conversationally.
You remember the conversation.
Answer naturally like a human assistant.
Do NOT mention documents, sources, or database.
"""

MEMORY_SYSTEM_PROMPT = """
You are a conversation assistant.

The user is asking about previous messages in the chat.
Answer ONLY using the conversation history provided.
Do NOT invent anything.
If nothing exists, say you don't have earlier messages yet.
"""


# ---------------------------------------------------------------------
# CONTEXT BUILDER
# ---------------------------------------------------------------------

def build_context(results: List[Any]) -> str:
    texts = []
    for r in results:
        payload = r.payload or {}
        title = payload.get("title", "").strip()
        content = payload.get("content", "").strip()

        if title and title.lower() not in content.lower():
            texts.append(f"{title}. {content}")
        else:
            texts.append(content)

    return "\n\n".join(texts)


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

async def run(
    message: str,
    settings: Settings,
    qdrant_client: QdrantClient,
    conversation_history: Optional[List[dict]] = None,
) -> str:

    logger.info("RAG | user: %s", message)

    history = conversation_history or []

    # =========================================================
    # 🧠 MEMORY MODE (SKIP VECTOR SEARCH)
    # =========================================================
    if is_memory_question(message):
        logger.info("RAG MODE: conversation memory")

        if not history:
            return "We just started chatting — I don’t have anything to recall yet."

        messages = [
            {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": message},
        ]

        answer = await chat(messages, settings.LLAMA_URL)
        return answer.strip()

    # =========================================================
    # 📚 KNOWLEDGE MODE (VECTOR SEARCH)
    # =========================================================

    query_vector = await embed_query(settings.EMBEDDING_URL, message)

    response = qdrant_client.query_points(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query=query_vector,
        limit=TOP_K,
        with_payload=True,
    )

    if not response.points:
        return "Hmm — I couldn’t find anything helpful. Could you rephrase?"

    # rank by similarity
    scored = sorted(
        [p for p in response.points if p.score is not None],
        key=lambda x: x.score,
        reverse=True
    )

    strong = scored[:FINAL_K]

    # low confidence → clarify (skipped when ISREMOVED_GATE is True)
    if not getattr(settings, "ISREMOVED_GATE", False) and strong[0].score < 0.35:
        return "I want to make sure I understand — could you explain a bit more?"

    context = build_context(strong)

    # =========================================================
    # HUMAN RESPONSE GENERATION
    # =========================================================

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        *history,
        {
            "role": "system",
            "content": f"Helpful background information:\n{context}"
        },
        {"role": "user", "content": message}
    ]

    answer = await chat(messages, settings.LLAMA_URL)
    return answer.strip()
