"""Error recovery for SQL agent with multi-stage retry logic."""

import logging
from typing import Optional

from app.core.config import Settings
from app.core.llm import chat
from app.services.sql_memory import SQLQueryMemory

logger = logging.getLogger(__name__)


async def recover_from_query_error(
    message: str,
    error: Exception,
    memory: SQLQueryMemory,
    settings: Settings,
) -> Optional[str]:
    """
    Multi-stage error recovery for failed SQL queries.
    
    Stages:
    1. Ask LLM to simplify/rephrase the question
    2. Suggest similar successful queries from memory
    3. Return helpful error message
    
    Returns:
        - Simplified question string to retry (if stage 1 succeeds)
        - Suggestions string (if stage 2 has matches)
        - Error message (fallback)
    """
    logger.info("SQL ERROR RECOVERY | Starting recovery for error: %s", str(error)[:100])
    
    # Stage 1: Auto-simplification
    simplified = await _simplify_question(message, str(error), settings)
    if simplified and simplified != message:
        logger.info("SQL ERROR RECOVERY | Simplified question: %s", simplified)
        return simplified  # Caller will retry with this
    
    # Stage 2: Find similar successful queries from memory
    similar = _find_similar_queries(message, memory)
    if similar:
        logger.info("SQL ERROR RECOVERY | Found %d similar queries", len(similar))
        suggestions = "I couldn't answer that. Here are similar questions that worked:\n"
        suggestions += "\n".join(f"- {s}" for s in similar)
        return suggestions
    
    # Stage 3: Helpful error message
    return _get_helpful_error_message(error)


async def _simplify_question(
    question: str,
    error: str,
    settings: Settings
) -> Optional[str]:
    """Ask Llama to rephrase as a simpler, more specific database query."""
    # Don't simplify if question is already very short
    if len(question.split()) < 5:
        return None
    
    prompt = f"""The user asked: "{question}"

This query failed with error: {error[:200]}

Rephrase this as a simpler, more specific database question about orders, products, or purchases.
Use concrete terms like "orders", "products", "total spent" instead of vague requests.
Respond with ONLY the rephrased question, nothing else.

Examples:
- "What's going on with my account?" → "Show my recent orders"
- "Spending patterns?" → "What is my total spending?"
- "Product stuff" → "List products I purchased"

Simplified question:"""
    
    messages = [{"role": "user", "content": prompt}]
    
    try:
        response = await chat(messages, settings.LLAMA_URL)
        simplified = response.strip()
        
        # Validate it's actually different and simpler/more specific
        if simplified and simplified != question:
            # Must be simpler (shorter or same length) and different
            if len(simplified) <= len(question) * 1.5:
                # Remove quotes if LLM added them
                simplified = simplified.strip('"\'')
                return simplified
        
    except Exception as exc:
        logger.warning("SQL ERROR RECOVERY | Simplification LLM call failed: %s", exc)
    
    return None


def _find_similar_queries(message: str, memory: SQLQueryMemory) -> list[str]:
    """Find similar successful queries from conversation memory."""
    if not memory.recent_queries:
        return []
    
    # Extract key terms from current message
    message_lower = message.lower()
    keywords = set()
    
    # Common SQL-related terms
    query_terms = ["order", "product", "purchase", "buy", "bought", "spent", "total", 
                   "count", "show", "list", "recent", "last", "month", "year", "price"]
    
    for term in query_terms:
        if term in message_lower:
            keywords.add(term)
    
    # If no keywords found, can't match
    if not keywords:
        return []
    
    # Find queries with overlapping keywords
    similar = []
    for query_info in memory.recent_queries:
        past_question = query_info["question"].lower()
        # Count keyword matches
        matches = sum(1 for kw in keywords if kw in past_question)
        if matches >= 2:  # At least 2 keywords match
            similar.append(query_info["question"])
    
    return similar[:3]  # Return top 3 matches


def _get_helpful_error_message(error: Exception) -> str:
    """Generate a user-friendly error message based on the exception."""
    error_str = str(error).lower()

    # PostgreSQL GROUP BY errors
    if "group by" in error_str or "aggregate function" in error_str:
        return (
            "I had trouble structuring that query correctly. "
            "Try asking: 'how many orders do I have?' or 'show my total spending'."
        )

    # Column not found errors
    if "column" in error_str and (
        "does not exist" in error_str or "not found" in error_str
    ):
        return (
            "I tried to access a field that doesn't exist. "
            "Try asking about: orders, products, prices, or dates."
        )

    # JSON parsing errors
    if "json" in error_str or "parse" in error_str:
        return (
            "I had trouble understanding how to query that. "
            "Try rephrasing with more specific terms like 'show my orders' or 'total spent'."
        )
    
    # SQL validation errors
    if "validation" in error_str or "invalid" in error_str:
        return (
            "I couldn't build a safe query for that request. "
            "Please ask about your orders, products, or purchases specifically."
        )
    
    # Scope/permission errors
    if "scope" in error_str or "customer" in error_str:
        return (
            "I can only show you information about your own account. "
            "Try asking about 'my orders' or 'my purchases'."
        )
    
    # Generic fallback
    return (
        "I couldn't answer that question. "
        "Try asking about your orders, products you've purchased, or spending totals."
    )
