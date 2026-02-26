"""Query preprocessor for SQL agent: detect user-mentioned IDs and add explicit scope instructions."""

import re
from typing import Any


def preprocess_query_for_sql(query: str, customer_id: int) -> dict[str, Any]:
    """
    Detect if query contains numeric IDs that might confuse the LLM.
    Returns enriched context with explicit instructions so the LLM does NOT
    add filters on ticket_id, product_id, or other IDs from the question.
    """
    query = (query or "").strip()
    detected_ids: list[str] = []
    hints: list[str] = []

    # Detect patterns like "order 123", "order #264933961", "ticket 123"
    order_id_pattern = r"\b(?:order|ticket)\s*#?\s*(\d{5,})\b"
    # Detect "product 456", "product #123"
    product_id_pattern = r"\b(?:product)\s*#?\s*(\d{3,})\b"
    # Standalone large numbers (likely order/ticket IDs)
    bare_id_pattern = r"\b(\d{7,})\b"

    if order_ids := re.findall(order_id_pattern, query, re.IGNORECASE):
        detected_ids.extend(order_ids)
        hints.append(
            "The user mentioned order ID(s). DO NOT add filters on ticket_id or product_id."
        )

    if product_ids := re.findall(product_id_pattern, query, re.IGNORECASE):
        for pid in product_ids:
            if pid not in detected_ids:
                detected_ids.append(pid)
        hints.append(
            "The user mentioned product ID(s). DO NOT add filters on product_id."
        )

    if bare_ids := re.findall(bare_id_pattern, query):
        for bid in bare_ids:
            if bid not in detected_ids:
                detected_ids.append(bid)
        hints.append(
            f"The user mentioned numeric ID(s): {', '.join(bare_ids)}. "
            "These are references, NOT filters. ONLY filter by customer_id."
        )

    enhanced_scope_instruction = ""
    if detected_ids:
        enhanced_scope_instruction = (
            f"\n\nCRITICAL: User mentioned ID(s) {detected_ids}. "
            f"These are REFERENCES to data already scoped to customer_id={customer_id}. "
            "NEVER add filters on ticket_id, product_id, or any ID from the question. "
            f"ONLY use: customer_id = {customer_id}"
        )

    return {
        "original_query": query,
        "detected_ids": list(dict.fromkeys(detected_ids)),  # preserve order, dedupe
        "preprocessing_hints": hints,
        "enhanced_scope_instruction": enhanced_scope_instruction,
    }
