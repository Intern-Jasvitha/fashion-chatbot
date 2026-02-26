"""Candidate response abstractions and signal normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


POSITIVE_KEYS = ("Sg", "Su", "St", "Se", "Sx", "Sl", "Sp")
PENALTY_KEYS = ("Ph", "Po", "Pd", "Pa", "Pv")


@dataclass
class Candidate:
    candidate_id: str
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, float] = field(default_factory=dict)


@dataclass
class CandidateContext:
    user_message: str
    user_state: str
    intent: str
    policy_allow: bool
    policy_reason_code: Optional[str] = None
    user_id: Optional[int] = None
    customer_id: Optional[int] = None


def normalize_signals(signals: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in POSITIVE_KEYS + PENALTY_KEYS:
        out[key] = clamp01(float(signals.get(key, 0.0)))
    return out


def build_candidate(
    *,
    candidate_id: str,
    text: str,
    source: str,
    metadata: Optional[dict[str, Any]] = None,
    signals: Optional[dict[str, float]] = None,
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        text=(text or "").strip(),
        source=source,
        metadata=metadata or {},
        signals=normalize_signals(signals or {}),
    )


def infer_tie_break_preference(message: str) -> Optional[str]:
    text = (message or "").lower()
    sql_keywords = ("my order", "my orders", "my account", "my purchase", "where is my", "ticket")
    rag_keywords = ("policy", "guide", "manual", "explain", "why", "how does")
    if any(k in text for k in sql_keywords):
        return "sql"
    if any(k in text for k in rag_keywords):
        return "rag"
    return None

