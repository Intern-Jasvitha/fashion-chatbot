from app.services.candidate_framework import CandidateContext, build_candidate
from app.services.candidate_gate import GateResult
from app.services.wrqs_config import get_default_wrqs_config
from app.services.wrqs_scoring import score_candidate, select_best_candidate


def test_stage_a_blocked_candidate_gets_negative_infinity() -> None:
    cfg = get_default_wrqs_config()
    ctx = CandidateContext(
        user_message="where is my order",
        user_state="REGISTERED",
        intent="hybrid",
        policy_allow=True,
        user_id=1,
        customer_id=1,
    )
    candidate = build_candidate(
        candidate_id="r_plain",
        source="plain",
        text="test",
        signals={"Sg": 1.0, "Su": 1.0, "St": 1.0},
    )
    score = score_candidate(
        candidate,
        ctx,
        cfg,
        stage_a_result=GateResult(allow=False, reason_code="BLOCKED"),
    )
    assert score.wrqs == float("-inf")
    assert not score.stage_a_passed


def test_wrqs_weighted_math_matches_formula() -> None:
    cfg = get_default_wrqs_config()
    ctx = CandidateContext(
        user_message="where is my order",
        user_state="REGISTERED",
        intent="hybrid",
        policy_allow=True,
        user_id=1,
        customer_id=1,
    )
    candidate = build_candidate(
        candidate_id="r_sql",
        source="sql",
        text="ok",
        signals={
            "Sg": 0.9,
            "Su": 0.8,
            "St": 0.7,
            "Se": 0.6,
            "Sx": 0.5,
            "Sl": 0.4,
            "Sp": 0.3,
            "Ph": 0.2,
            "Po": 0.1,
            "Pd": 0.0,
            "Pa": 0.3,
            "Pv": 0.4,
        },
    )
    score = score_candidate(candidate, ctx, cfg, stage_a_result=GateResult(allow=True))
    expected_pos = sum(cfg.positive_weights[k] * candidate.signals[k] for k in cfg.positive_weights)
    expected_pen = sum(cfg.penalty_weights[k] * candidate.signals[k] for k in cfg.penalty_weights)
    assert abs(score.weighted_positive - expected_pos) < 1e-9
    assert abs(score.weighted_penalty - expected_pen) < 1e-9
    assert abs(score.wrqs - (expected_pos - expected_pen)) < 1e-9


def test_tie_break_prefers_sql_for_user_specific_request() -> None:
    cfg = get_default_wrqs_config()
    ctx = CandidateContext(
        user_message="where is my order",
        user_state="REGISTERED",
        intent="hybrid",
        policy_allow=True,
        user_id=1,
        customer_id=1,
    )
    sql_candidate = build_candidate(
        candidate_id="r_sql",
        source="sql",
        text="sql answer",
        signals={"Sg": 0.75, "Su": 0.75, "St": 0.75, "Ph": 0.2, "Po": 0.2, "Pd": 0.2, "Pa": 0.2, "Pv": 0.2},
    )
    rag_candidate = build_candidate(
        candidate_id="r_rag",
        source="rag",
        text="rag answer",
        signals={"Sg": 0.75, "Su": 0.75, "St": 0.75, "Ph": 0.2, "Po": 0.2, "Pd": 0.2, "Pa": 0.2, "Pv": 0.2},
    )
    sql_score = score_candidate(sql_candidate, ctx, cfg, GateResult(allow=True))
    rag_score = score_candidate(rag_candidate, ctx, cfg, GateResult(allow=True))
    selected, _, rationale = select_best_candidate(
        candidates=[sql_candidate, rag_candidate],
        scores=[rag_score, sql_score],
        context=ctx,
        config=cfg,
    )
    assert selected.candidate_id == "r_sql"
    assert rationale["selected_by"].startswith("tie_break_")

