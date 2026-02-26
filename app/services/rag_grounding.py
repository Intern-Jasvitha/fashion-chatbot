"""Grounding and explainability helpers for RAG answers."""

from __future__ import annotations

import re
from typing import Any


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9']+", (text or "").lower())
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "for",
        "of",
        "in",
        "on",
        "is",
        "are",
        "be",
        "as",
        "with",
        "that",
        "this",
        "it",
        "you",
        "your",
        "i",
        "we",
    }
    return {t for t in tokens if len(t) > 2 and t not in stop}


def _normalize_score(score: float) -> float:
    # Qdrant cosine scores are usually [0, 1]; clamp keeps this robust.
    return _clamp01(score)


def build_retrieval_metadata(points: list[Any]) -> dict[str, Any]:
    """Return retrieval metadata for audit/trace purposes."""
    chunk_ids: list[str] = []
    doc_ids: list[str] = []
    raw_scores: list[float] = []
    normalized_scores: list[float] = []

    for idx, point in enumerate(points):
        payload = getattr(point, "payload", None) or {}
        point_id = getattr(point, "id", None)
        score = float(getattr(point, "score", 0.0) or 0.0)

        chunk_id = payload.get("chunk_id") or payload.get("id") or str(point_id or f"chunk-{idx}")
        doc_id = (
            payload.get("doc_id")
            or payload.get("document_id")
            or payload.get("source")
            or payload.get("title")
            or "unknown"
        )

        chunk_ids.append(str(chunk_id))
        doc_ids.append(str(doc_id))
        raw_scores.append(score)
        normalized_scores.append(_normalize_score(score))

    retrieval_confidence = max(normalized_scores) if normalized_scores else 0.0
    return {
        "chunk_ids": chunk_ids,
        "doc_ids": doc_ids,
        "raw_similarity_scores": raw_scores,
        "normalized_similarity_scores": normalized_scores,
        "retrieval_confidence": retrieval_confidence,
    }


def assess_claim_support(answer: str, retrieved_context: str) -> dict[str, Any]:
    """Estimate support ratio by lexical overlap between answer claims and context."""
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", (answer or "").strip()) if s.strip()]
    context_tokens = _tokenize(retrieved_context)

    if not sentences or not context_tokens:
        return {
            "support_ratio": 0.0,
            "unsupported_claims": sentences[:3],
            "hallucination_risk": 1.0,
            "claims_checked": len(sentences),
        }

    supported = 0
    unsupported_claims: list[str] = []
    for sent in sentences:
        claim_tokens = _tokenize(sent)
        if len(claim_tokens) < 3:
            continue
        overlap_ratio = len(claim_tokens & context_tokens) / max(1, len(claim_tokens))
        if overlap_ratio >= 0.35:
            supported += 1
        else:
            unsupported_claims.append(sent)

    claims_checked = max(1, supported + len(unsupported_claims))
    support_ratio = supported / claims_checked
    return {
        "support_ratio": _clamp01(support_ratio),
        "unsupported_claims": unsupported_claims[:5],
        "hallucination_risk": _clamp01(1.0 - support_ratio),
        "claims_checked": claims_checked,
    }


def should_fallback_for_grounding(
    *,
    retrieval_confidence: float,
    support_ratio: float,
    min_retrieval_confidence: float = 0.35,
    min_support_ratio: float = 0.45,
) -> bool:
    return retrieval_confidence < min_retrieval_confidence or support_ratio < min_support_ratio


def is_recommendation_prompt(message: str) -> bool:
    text = (message or "").lower()
    keywords = ("recommend", "suggest", "best", "which one", "what should i wear", "option", "design", "outfit", "outfits")
    return any(k in text for k in keywords)


def build_explainability_metadata(answer: str, retrieval: dict[str, Any]) -> dict[str, Any]:
    """Build internal explainability details for recommendation-like outputs."""
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", (answer or "").strip()) if s.strip()]
    why_this_works = sentences[0] if sentences else "Recommendation aligns with your request and available guidance."
    doc_ids = retrieval.get("doc_ids") or []
    based_on = (
        f"Derived from retrieved document context: {', '.join(doc_ids[:3])}"
        if doc_ids
        else "Derived from retrieved fashion guidance context."
    )

    alt_sentences = [
        s
        for s in sentences
        if "alternativ" in s.lower() or "instead" in s.lower() or "or " in s.lower()
    ]
    alternatives = alt_sentences[:2] if alt_sentences else ["Consider an alternate fabric or color for similar styling intent."]

    return {
        "why_this_works": why_this_works,
        "what_this_is_based_on": based_on,
        "alternatives": alternatives,
    }

