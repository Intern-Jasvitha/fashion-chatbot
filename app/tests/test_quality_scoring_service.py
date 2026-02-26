from app.services.quality_scoring_service import (
    TurnQualityInput,
    classify_turn_quality,
    compute_kgs,
    compute_tqs,
)


def test_tqs_formula_exact_math() -> None:
    inp = TurnQualityInput(
        intent="hybrid",
        positive_factors={
            "Sg": 0.9,
            "Su": 0.8,
            "St": 0.7,
            "Se": 0.6,
            "Sx": 0.5,
            "Sl": 0.4,
            "Sp": 0.3,
        },
        penalty_factors={
            "Ph": 0.2,
            "Po": 0.1,
            "Pd": 0.0,
            "Pa": 0.3,
            "Pv": 0.4,
        },
    )
    # Mirrors formula in self.md and service constants
    assert compute_tqs(inp) == 73


def test_kgs_formula_for_rag_and_sql_paths() -> None:
    rag_inp = TurnQualityInput(
        intent="rag",
        retrieval_confidence=0.2,
        hallucination_risk=0.7,
        rephrase_count=2,
        handoff_click=True,
    )
    assert compute_kgs(rag_inp) == 77

    sql_inp = TurnQualityInput(
        intent="sql",
        sql_error=True,
        hallucination_risk=0.1,
        rephrase_count=0,
        handoff_click=False,
    )
    assert compute_kgs(sql_inp) == 48


def test_quality_threshold_boundaries() -> None:
    at_low = classify_turn_quality(60, 64)
    assert not at_low.low_tqs
    assert not at_low.high_kgs

    below_low = classify_turn_quality(59, 65)
    assert below_low.low_tqs
    assert below_low.high_kgs

    critical = classify_turn_quality(50, 80)
    assert critical.critical_kgs
