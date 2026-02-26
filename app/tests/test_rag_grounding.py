from dataclasses import dataclass

from app.services.rag_grounding import (
    assess_claim_support,
    build_retrieval_metadata,
    should_fallback_for_grounding,
)


@dataclass
class FakePoint:
    id: str
    score: float
    payload: dict


def test_build_retrieval_metadata_contains_audit_fields() -> None:
    points = [
        FakePoint(id="1", score=0.88, payload={"chunk_id": "c1", "doc_id": "d1"}),
        FakePoint(id="2", score=0.74, payload={"chunk_id": "c2", "doc_id": "d2"}),
    ]
    meta = build_retrieval_metadata(points)
    assert meta["chunk_ids"] == ["c1", "c2"]
    assert meta["doc_ids"] == ["d1", "d2"]
    assert len(meta["raw_similarity_scores"]) == 2
    assert 0.0 <= meta["retrieval_confidence"] <= 1.0


def test_claim_support_flags_unsupported_content() -> None:
    answer = "Cashmere works for cold weather. Neon silk is ideal for snow storms."
    context = "Cashmere helps keep warmth in cold weather and winter evenings."
    support = assess_claim_support(answer, context)
    assert 0.0 <= support["support_ratio"] <= 1.0
    assert support["hallucination_risk"] >= 0.0
    assert support["unsupported_claims"]


def test_grounding_fallback_trigger() -> None:
    assert should_fallback_for_grounding(retrieval_confidence=0.3, support_ratio=0.8)
    assert should_fallback_for_grounding(retrieval_confidence=0.8, support_ratio=0.2)
    assert not should_fallback_for_grounding(retrieval_confidence=0.8, support_ratio=0.8)

