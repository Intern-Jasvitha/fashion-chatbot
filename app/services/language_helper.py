"""Language instruction helper for multilingual LLM responses."""

from typing import Optional

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "bn": "Bengali (বাংলা)",
    "mr": "Marathi (मराठी)",
    "te": "Telugu (తెలుగు)",
}


def get_language_instruction(lang_pref: Optional[str]) -> str:
    """Return language instruction to append to system prompts.

    Returns empty string for English or None.
    For other languages, returns instruction to respond in that language.
    """
    if not lang_pref or lang_pref == "en":
        return ""

    language_name = LANGUAGE_NAMES.get(lang_pref)
    if not language_name:
        return ""  # Invalid code, skip instruction

    return (
        "\n\nIMPORTANT: You must respond ONLY in {}. The user is communicating in {}, so all your responses must be in that language.".format(
            language_name, language_name
        )
    )
