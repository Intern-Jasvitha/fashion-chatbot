"""WRQS Stage-B scoring and candidate selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import inf
from typing import Any, Optional

from app.services.candidate_framework import Candidate, CandidateContext, infer_tie_break_preference
from app.services.candidate_gate import GateResult
from app.services.wrqs_config import WRQSConfig


@dataclass
class CandidateScore:
    candidate_id: str
    stage_a_passed: bool
    stage_a_reason_code: Optional[str]
    wrqs: float
    weighted_positive: float
    weighted_penalty: float
    risk_score: float
    positive_factors: dict[str, float] = field(default_factory=dict)
    penalty_factors: dict[str, float] = field(default_factory=dict)


def score_candidate(
    candidate: Candidate,
    context: CandidateContext,
    config: WRQSConfig,
    stage_a_result: Optional[GateResult] = None,
) -> CandidateScore:
    del context
    if stage_a_result is not None and not stage_a_result.allow:
        return CandidateScore(
            candidate_id=candidate.candidate_id,
            stage_a_passed=False,
            stage_a_reason_code=stage_a_result.reason_code,
            wrqs=-inf,
            weighted_positive=0.0,
            weighted_penalty=0.0,
            risk_score=1.0,
            positive_factors={k: candidate.signals.get(k, 0.0) for k in config.positive_weights},
            penalty_factors={k: candidate.signals.get(k, 0.0) for k in config.penalty_weights},
        )

    pos = {k: float(candidate.signals.get(k, 0.0)) for k in config.positive_weights}
    pen = {k: float(candidate.signals.get(k, 0.0)) for k in config.penalty_weights}

    weighted_positive = sum(config.positive_weights[k] * pos[k] for k in config.positive_weights)
    weighted_penalty = sum(config.penalty_weights[k] * pen[k] for k in config.penalty_weights)
    wrqs = weighted_positive - weighted_penalty
    return CandidateScore(
        candidate_id=candidate.candidate_id,
        stage_a_passed=True,
        stage_a_reason_code=None,
        wrqs=wrqs,
        weighted_positive=weighted_positive,
        weighted_penalty=weighted_penalty,
        risk_score=weighted_penalty,
        positive_factors=pos,
        penalty_factors=pen,
    )


def _candidate_by_id(candidates: list[Candidate], candidate_id: str) -> Optional[Candidate]:
    for candidate in candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    return None


def select_best_candidate(
    *,
    candidates: list[Candidate],
    scores: list[CandidateScore],
    context: CandidateContext,
    config: WRQSConfig,
) -> tuple[Candidate, CandidateScore, dict[str, Any]]:
    finite_scores = [s for s in scores if s.wrqs != -inf]
    if not finite_scores:
        fallback_candidate = candidates[0]
        fallback_score = scores[0]
        return fallback_candidate, fallback_score, {
            "selected_by": "fallback_no_stage_a_pass",
            "reason": fallback_score.stage_a_reason_code,
        }

    ranked = sorted(finite_scores, key=lambda s: s.wrqs, reverse=True)
    winner = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    rationale: dict[str, Any] = {"selected_by": "max_wrqs", "wrqs": winner.wrqs}

    if runner_up and abs(winner.wrqs - runner_up.wrqs) <= config.wrqs_tie_delta:
        preference = infer_tie_break_preference(context.user_message)
        if preference == "sql":
            preferred = next((s for s in ranked if s.candidate_id == "r_sql"), None)
            if preferred and abs(winner.wrqs - preferred.wrqs) <= config.wrqs_tie_delta:
                winner = preferred
                rationale = {
                    "selected_by": "tie_break_sql_preference",
                    "tie_delta": config.wrqs_tie_delta,
                }
        elif preference == "rag":
            preferred = next((s for s in ranked if s.candidate_id == "r_rag"), None)
            if preferred and abs(winner.wrqs - preferred.wrqs) <= config.wrqs_tie_delta:
                winner = preferred
                rationale = {
                    "selected_by": "tie_break_rag_preference",
                    "tie_delta": config.wrqs_tie_delta,
                }
        else:
            close = [s for s in ranked if abs(ranked[0].wrqs - s.wrqs) <= config.wrqs_tie_delta]
            if close:
                winner = min(close, key=lambda s: s.risk_score)
                rationale = {
                    "selected_by": "tie_break_lower_risk",
                    "tie_delta": config.wrqs_tie_delta,
                }

    selected_candidate = _candidate_by_id(candidates, winner.candidate_id) or candidates[0]
    return selected_candidate, winner, rationale

