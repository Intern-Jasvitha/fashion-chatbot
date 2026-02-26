"""Stage-A candidate compliance gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.candidate_framework import Candidate, CandidateContext
from app.services.policy_gate import UserState, evaluate_policy


@dataclass
class GateResult:
    allow: bool
    reason_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def gate_candidate(candidate: Candidate, context: CandidateContext) -> GateResult:
    if not context.policy_allow:
        return GateResult(
            allow=False,
            reason_code="POLICY_HARD_BLOCKED",
            details={"policy_reason_code": context.policy_reason_code},
        )

    # Note: Question-level SQL blocking removed - SQL-level validation handles scoping

    if context.user_state.upper() == UserState.GUEST.value and candidate.candidate_id == "r_sql":
        return GateResult(
            allow=False,
            reason_code="GUEST_SQL_BLOCKED",
            details={"candidate_id": candidate.candidate_id},
        )

    policy_decision = evaluate_policy(
        message=candidate.text or context.user_message,
        user_state=UserState.REGISTERED
        if context.user_state.upper() == UserState.REGISTERED.value
        else UserState.GUEST,
    )
    if not policy_decision.allow:
        return GateResult(
            allow=False,
            reason_code=f"CANDIDATE_POLICY_{policy_decision.reason_code or 'BLOCKED'}",
            details={
                "candidate_policy_intent": policy_decision.intent.value,
                "candidate_policy_domain": policy_decision.domain.value,
            },
        )

    if candidate.signals.get("Po", 0.0) >= 0.95:
        return GateResult(
            allow=False,
            reason_code="OVER_DISCLOSURE_BLOCKED",
            details={"Po": candidate.signals.get("Po", 0.0)},
        )
    return GateResult(allow=True)


def gate_candidates(candidates: list[Candidate], context: CandidateContext) -> dict[str, GateResult]:
    return {candidate.candidate_id: gate_candidate(candidate, context) for candidate in candidates}

