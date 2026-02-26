"""Translation service for multilingual chat: input to English, output to user language."""

import logging
from typing import Optional

from app.core.config import Settings
from app.core.llm import chat
from app.services.language_helper import LANGUAGE_NAMES

logger = logging.getLogger(__name__)

TRANSLATE_TO_ENGLISH_PROMPT = """Translate the following user message to English. Preserve the meaning exactly.
Return ONLY the English translation, no explanation, no quotes, no preamble.
If the message is already in English, return it unchanged."""

TRANSLATE_FROM_ENGLISH_PROMPT = """Translate the following assistant response from English to {target_language}.
Preserve the meaning, tone, and formatting. Return ONLY the translation, no explanation.
The response is from a fashion/order support assistant."""


async def translate_to_english(text: str, settings: Settings) -> str:
    """Translate user message to English for internal processing."""
    if not (text or "").strip():
        return text or ""

    msgs = [
        {"role": "system", "content": TRANSLATE_TO_ENGLISH_PROMPT},
        {"role": "user", "content": text.strip()},
    ]
    try:
        result = await chat(msgs, settings.LLAMA_URL)
        return (result or text).strip()
    except Exception as e:
        logger.warning("Translation to English failed: %s. Using original.", e)
        return text.strip()


async def translate_to_language(
    text: str, lang_code: str, settings: Settings
) -> str:
    """Translate assistant response from English to the user's selected language."""
    if not (text or "").strip():
        return text or ""

    language_name = LANGUAGE_NAMES.get(lang_code)
    if not language_name:
        return text.strip()

    msgs = [
        {
            "role": "system",
            "content": TRANSLATE_FROM_ENGLISH_PROMPT.format(
                target_language=language_name
            ),
        },
        {"role": "user", "content": text.strip()},
    ]
    try:
        result = await chat(msgs, settings.LLAMA_URL)
        return (result or text).strip()
    except Exception as e:
        logger.warning(
            "Translation to %s failed: %s. Using original.", lang_code, e
        )
        return text.strip()
