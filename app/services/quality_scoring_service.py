"""Turn quality (TQS) and knowledge gap (KGS) scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from app.services.wrqs_config import WRQSConfig, get_default_wrqs_config

Intent = Literal["sql", "rag", "hybrid"]

LOW_TQS = 60
HIGH_KGS = 65
CRITICAL_KGS = 80
PENALTY_NORMALIZER = 1.31


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class TurnQualityInput:
    intent: Intent
    positive_factors: dict[str, float] = field(default_factory=dict)
    penalty_factors: dict[str, float] = field(default_factory=dict)
    retrieval_confidence: float = 0.0
    hallucination_risk: float = 0.0
    sql_error: bool = False
    sql_row_count: Optional[int] = None
    rephrase_count: int = 0
    handoff_click: bool = False


@dataclass
class TurnQualityScores:
    tqs: int
    kgs: int
    low_tqs: bool
    high_kgs: bool
    critical_kgs: bool


def compute_tqs(inp: TurnQualityInput, wrqs_weights: Optional[dict[str, dict[str, float]]] = None) -> int:
    """Strict TQS formula from self.md."""
    cfg = get_default_wrqs_config()
    if isinstance(wrqs_weights, dict):
        positive = wrqs_weights.get("positive")
        penalty = wrqs_weights.get("penalty")
        if isinstance(positive, dict) and isinstance(penalty, dict):
            cfg = WRQSConfig(
                positive_weights={str(k): float(v) for k, v in positive.items()},
                penalty_weights={str(k): float(v) for k, v in penalty.items()},
                wrqs_tie_delta=cfg.wrqs_tie_delta,
                min_retrieval_confidence=cfg.min_retrieval_confidence,
                min_support_ratio=cfg.min_support_ratio,
            )
    p = sum(cfg.positive_weights[k] * float(inp.positive_factors.get(k, 0.0)) for k in cfg.positive_weights)
    n = sum(cfg.penalty_weights[k] * float(inp.penalty_factors.get(k, 0.0)) for k in cfg.penalty_weights) / PENALTY_NORMALIZER
    tqs_val = 100.0 * _clamp01(0.70 * p + 0.30 * (1.0 - n))
    return int(round(tqs_val))


def _gap_score(inp: TurnQualityInput) -> float:
    if inp.intent == "sql":
        if inp.sql_error:
            return 1.0
        if int(inp.sql_row_count or 0) == 0:
            return 0.6
        return 0.2
    return 1.0 - _clamp01(inp.retrieval_confidence)


def compute_kgs(inp: TurnQualityInput) -> int:
    """Strict KGS formula from self.md."""
    gap = _gap_score(inp)
    hall = _clamp01(inp.hallucination_risk)
    retry = _clamp01(float(inp.rephrase_count) / 3.0)
    esc = 1.0 if inp.handoff_click else 0.0
    kgs_val = 100.0 * _clamp01(0.45 * gap + 0.25 * hall + 0.20 * retry + 0.10 * esc)
    return int(round(kgs_val))


def classify_turn_quality(
    tqs: int,
    kgs: int,
    *,
    low_tqs_threshold: int = LOW_TQS,
    high_kgs_threshold: int = HIGH_KGS,
    critical_kgs_threshold: int = CRITICAL_KGS,
) -> TurnQualityScores:
    return TurnQualityScores(
        tqs=int(tqs),
        kgs=int(kgs),
        low_tqs=int(tqs) < int(low_tqs_threshold),
        high_kgs=int(kgs) >= int(high_kgs_threshold),
        critical_kgs=int(kgs) >= int(critical_kgs_threshold),
    )
