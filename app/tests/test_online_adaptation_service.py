from app.services.online_adaptation_service import (
    apply_wrqs_overrides,
    build_gap_topic_key,
    detect_rephrase,
    evaluate_adaptation,
)
from app.services.wrqs_config import get_default_wrqs_config


def test_detect_rephrase_heuristics() -> None:
    assert detect_rephrase("can you rephrase this", "explain this")
    assert detect_rephrase("where is my order", "where is my order")
    assert not detect_rephrase("show me return policy", "where is my order")


def test_evaluate_adaptation_triggers_and_ttl() -> None:
    decision = evaluate_adaptation(
        tqs=55,
        kgs=70,
        rephrase_count=2,
        handoff_clicks=1,
        current_turn_index=4,
        low_tqs_threshold=60,
        high_kgs_threshold=65,
        rag_topk_adapt=18,
        ttl_turns=3,
    )
    assert decision.should_apply
    assert set(decision.reason_codes) >= {"LOW_TQS", "HIGH_KGS", "REPHRASE_COUNT", "HANDOFF_CLICK"}
    assert decision.adaptation_expires_turn == 7

    none = evaluate_adaptation(
        tqs=80,
        kgs=20,
        rephrase_count=0,
        handoff_clicks=0,
        current_turn_index=4,
        low_tqs_threshold=60,
        high_kgs_threshold=65,
        rag_topk_adapt=18,
        ttl_turns=3,
    )
    assert not none.should_apply


def test_wrqs_override_cap_is_enforced() -> None:
    cfg = get_default_wrqs_config()
    updated = apply_wrqs_overrides(
        cfg,
        {
            "positive": {"Sg": cfg.positive_weights["Sg"] + 0.5},
            "penalty": {"Ph": cfg.penalty_weights["Ph"] - 0.5},
        },
        max_delta=0.10,
    )
    assert updated.positive_weights["Sg"] == cfg.positive_weights["Sg"] + 0.10
    assert updated.penalty_weights["Ph"] == cfg.penalty_weights["Ph"] - 0.10


def test_gap_topic_key_stable_for_same_prompt() -> None:
    k1 = build_gap_topic_key("hybrid", "Where is my order?")
    k2 = build_gap_topic_key("hybrid", "Where is my order?")
    assert k1 == k2
