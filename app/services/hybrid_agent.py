"""Hybrid Agent: combine SQL (structured data) and RAG (documents) into one answer."""

import asyncio
import logging
from typing import List, Optional

from qdrant_client import QdrantClient

from app.core.config import Settings
from app.core.llm import chat
from app.services.language_helper import get_language_instruction
from app.services.rag_agent import run as run_rag_agent
from app.services.sql_agent import run as run_sql_agent

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a helpful assistant. The user asked a question that required both database data and document knowledge.

You will be given:
1. The user's original question.
2. The answer from the database (structured data).
3. The answer from the documents (knowledge base).

Your job is to combine these into one clear, coherent response. Use both sources when they are relevant. If one source had no relevant information or an error, say so briefly and rely on the other. Do not repeat the same information twice. Write in natural, conversational language. Do not include raw SQL or JSON."""

SYNTHESIS_USER_PROMPT = """User question: {question}

From the database:
{sql_answer}

From the documents:
{rag_answer}

Combined answer:"""


async def run(
    message: str,
    settings: Settings,
    qdrant_client: QdrantClient,
    conversation_history: Optional[List[dict]] = None,
    customer_id: Optional[int] = None,
    customer_name: Optional[str] = None,
    lang_pref: Optional[str] = None,
) -> str:
    """Run SQL and RAG agents in parallel, then synthesize one answer.

    Returns a single natural-language response combining database and document context.
    conversation_history: optional session memory (last 10 messages).
    """
    logger.info("HYBRID AGENT | Incoming user query: %s", message)

    results = await asyncio.gather(
        run_sql_agent(
            message,
            settings,
            conversation_history=conversation_history,
            customer_id=customer_id,
            customer_name=customer_name,
        ),
        run_rag_agent(message, settings, qdrant_client, conversation_history=conversation_history),
        return_exceptions=True,
    )
    sql_answer = results[0] if not isinstance(results[0], BaseException) else "The database query could not be completed."
    rag_answer = results[1] if not isinstance(results[1], BaseException) else "The document search could not be completed."
    if isinstance(results[0], BaseException):
        logger.warning("HYBRID AGENT | SQL agent failed: %s", results[0])
    if isinstance(results[1], BaseException):
        logger.warning("HYBRID AGENT | RAG agent failed: %s", results[1])

    # If both returned empty or generic errors, avoid an extra LLM call
    if not (sql_answer or "").strip():
        sql_answer = "No relevant data was found in the database."
    if not (rag_answer or "").strip():
        rag_answer = "No relevant information was found in the documents."

    history = conversation_history or []
    lang_instruction = get_language_instruction(lang_pref)

    messages = [{"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT + lang_instruction}]
    messages.extend(history)
    messages.append({"role": "system", "content": f"Database result:\n{sql_answer}\n\nDocument knowledge:\n{rag_answer}"})
    messages.append({"role": "user", "content": message})

    try:
        combined = await chat(messages, settings.LLAMA_URL)
        return (combined or "I couldn't combine the results. Please try a more specific question.").strip()
    except Exception as e:
        logger.warning("HYBRID AGENT | Synthesis LLM failed: %s", e)
        return f"From the database: {sql_answer}\n\nFrom the documents: {rag_answer}"
