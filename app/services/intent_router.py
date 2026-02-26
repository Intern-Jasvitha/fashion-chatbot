"""
Production-grade Intent Router
Deterministic scoring layer + LLM fallback
"""

import logging
import re
from typing import Callable, Awaitable, List, Optional
from app.core.config import Settings
from app.schemas.intent import AgentIntent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# STRICT ROUTING PROMPT (LLM FALLBACK ONLY)
# ---------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a strict message router.

Decide which system should answer the user question.

SQL_AGENT:
ONLY if the user wants database rows, counts, numbers,
reports, financial data, user transactions, analytics.

RAG_AGENT:
Explanations, help, tutorials, advice, knowledge, policies.

HYBRID_AGENT:
Needs BOTH database info AND explanation.

Reply ONLY with:
SQL_AGENT
RAG_AGENT
HYBRID_AGENT
"""

# ---------------------------------------------------------------------
# INTENT MAP
# ---------------------------------------------------------------------

_INTENT_MAP = {
    "SQL_AGENT": AgentIntent.SQL_AGENT,
    "RAG_AGENT": AgentIntent.RAG_AGENT,
    "HYBRID_AGENT": AgentIntent.HYBRID_AGENT,
}

DEFAULT_INTENT = AgentIntent.HYBRID_AGENT

# ---------------------------------------------------------------------
# PATTERNS (PRODUCTION SAFE)
# ---------------------------------------------------------------------

AGGREGATION_PATTERNS = [
    r"\bhow much\b",
    r"\bhow many\b",
    r"\btotal\b",
    r"\bsum\b",
    r"\bamount\b",
    r"\baverage\b",
]

LIST_PATTERNS = [
    r"\blist\b",
    r"\bshow\b",
    r"\bdisplay\b",
    r"\bgive me\b",
]

FINANCIAL_WORDS = [
    "tax", "taxes",
    "payment", "payments",
    "transaction", "transactions",
    "revenue", "sales",
    "amount", "balance",
    "invoice", "invoices",
    "spent", "paid", "earned",
]

DATA_NOUNS = [
    "order", "orders",
    "user", "users",
    "customer", "customers",
    "product", "products",
    "ticket", "tickets",
    "purchase", "purchases",
    "employee", "employees",
]

EXPLANATION_WORDS = [
    "explain", "why", "guide",
    "help", "tutorial", "meaning",
    "policy", "how to",
]

ADVICE_WORDS = [
    "recommend", "suggest", "best",
]

PRICE_FILTER_WORDS = [
    "under", "below", "above",
    "cheaper", "price", "cost",
]

MEMORY_KEYWORDS = [
    "what did i say",
    "what did i ask",
    "my last message",
    "previous message",
    "summarize our conversation",
    "recall our conversation",
]

USER_SCOPED_WORDS = [
    "i ", "my ", "me ",
]

# ---------------------------------------------------------------------
# SCORING ENGINE
# ---------------------------------------------------------------------

def score_intent(message: str) -> AgentIntent:
    msg = message.lower().strip()

    sql_score = 0
    rag_score = 0
    hybrid_score = 0

    # MEMORY highest priority
    if any(k in msg for k in MEMORY_KEYWORDS):
        logger.info("Router override → MEMORY → RAG_AGENT")
        return AgentIntent.RAG_AGENT

    # -------------------------------------------------
    # SQL SIGNALS
    # -------------------------------------------------

    # Aggregation
    if any(re.search(p, msg) for p in AGGREGATION_PATTERNS):
        sql_score += 3

    # Financial terms
    if any(word in msg for word in FINANCIAL_WORDS):
        sql_score += 2

    # DB nouns
    if any(noun in msg for noun in DATA_NOUNS):
        sql_score += 2

    # List queries
    if any(re.search(p, msg) for p in LIST_PATTERNS):
        sql_score += 2

    # User scoped numeric queries
    if any(word in msg for word in USER_SCOPED_WORDS) and sql_score > 0:
        sql_score += 2

    # -------------------------------------------------
    # RAG SIGNALS
    # -------------------------------------------------

    if any(word in msg for word in EXPLANATION_WORDS):
        rag_score += 3

    # -------------------------------------------------
    # HYBRID SIGNALS
    # -------------------------------------------------

    if (
        any(word in msg for word in ADVICE_WORDS)
        and any(word in msg for word in PRICE_FILTER_WORDS)
    ):
        hybrid_score += 4

    # -------------------------------------------------
    # DECISION
    # -------------------------------------------------

    logger.info("Routing scores | SQL=%s RAG=%s HYBRID=%s",
                sql_score, rag_score, hybrid_score)

    if hybrid_score >= 4:
        return AgentIntent.HYBRID_AGENT

    if sql_score > rag_score and sql_score >= 3:
        return AgentIntent.SQL_AGENT

    if rag_score > sql_score and rag_score >= 3:
        return AgentIntent.RAG_AGENT

    return DEFAULT_INTENT


def heuristic_override(message: str, proposed_intent: AgentIntent) -> AgentIntent:
    """Apply deterministic scoring; override proposed intent when heuristics are strong."""
    scored = score_intent(message)
    if scored != DEFAULT_INTENT:
        return scored
    return proposed_intent


# ---------------------------------------------------------------------
# MAIN DETECTION
# ---------------------------------------------------------------------

async def detect_intent(
    message: str,
    chat_fn: Callable[[list[dict[str, str]], str], Awaitable[str]],
    settings: Settings,
    conversation_history: Optional[List[dict]] = None,
) -> AgentIntent:

    # -----------------------------
    # 1️⃣ Deterministic Layer First
    # -----------------------------

    deterministic_intent = score_intent(message)

    if deterministic_intent != DEFAULT_INTENT:
        logger.info("Deterministic routing → %s", deterministic_intent)
        return deterministic_intent

    # -----------------------------
    # 2️⃣ LLM Fallback
    # -----------------------------

    if conversation_history:
        history_blob = "\n".join(
            f"{m['role']}: {m['content']}"
            for m in conversation_history[-6:]
        )
        user_content = (
            f"Recent conversation:\n{history_blob}\n\n"
            f"Current message: {message}"
        )
    else:
        user_content = message

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        reply = await chat_fn(messages, settings.LLAMA_URL)
        token = (reply or "").strip().upper()
        token = token.split("\n")[0].split()[0].strip(".,;:")
        intent = _INTENT_MAP.get(token, DEFAULT_INTENT)
        logger.info("LLM routing fallback → %s", intent)
        return intent

    except Exception as e:
        logger.warning("LLM intent detection failed: %s", e)
        return DEFAULT_INTENT