"""Reusable candidate signal builders for WRQS and quality scoring."""

from __future__ import annotations

from typing import Any, Optional


def _text_risk_signals(text: str) -> tuple[float, float]:
    words = len((text or "").split())
    ambiguity = 0.75 if words < 12 else (0.45 if words < 24 else 0.20)
    verbosity = 0.75 if words > 220 else (0.35 if words > 120 else 0.10)
    return ambiguity, verbosity


def candidate_signals(
    *,
    candidate_id: str,
    text: str,
    sql_metadata: Optional[dict[str, Any]] = None,
    rag_metadata: Optional[dict[str, Any]] = None,
    design_mode: bool = False,
) -> dict[str, float]:
    """Build normalized WRQS signal vector for a candidate."""
    ambiguity, verbosity = _text_risk_signals(text)
    sql_metadata = sql_metadata or {}
    rag_metadata = rag_metadata or {}

    if candidate_id == "r_sql":
        failed = bool(sql_metadata.get("had_error"))
        return {
            "Sg": 0.95 if not failed else 0.20,
            "Su": 0.95 if not failed else 0.40,
            "St": 0.90 if not failed else 0.25,
            "Se": 0.45,
            "Sx": 0.40,
            "Sl": 0.90,
            "Sp": 0.80,
            "Ph": 0.05 if not failed else 0.80,
            "Po": 0.08,
            "Pd": 0.06,
            "Pa": ambiguity,
            "Pv": verbosity,
        }

    if candidate_id == "r_rag":
        retrieval = float(rag_metadata.get("retrieval_confidence", 0.0))
        support = float(rag_metadata.get("support_ratio", 0.0))
        hallucination = float(rag_metadata.get("hallucination_risk", 0.6))
        has_explainability = bool(rag_metadata.get("explainability"))
        return {
            "Sg": max(0.0, min(1.0, retrieval * support)),
            "Su": 0.70,
            "St": 0.78,
            "Se": 0.85 if has_explainability else 0.50,
            "Sx": 0.55,
            "Sl": 0.90,
            "Sp": 0.72,
            "Ph": hallucination,
            "Po": 0.10,
            "Pd": 0.08,
            "Pa": ambiguity,
            "Pv": verbosity,
        }

    if candidate_id == "r_guided":
        return {
            "Sg": 0.55,
            "Su": 0.80 if design_mode else 0.50,
            "St": 0.82 if design_mode else 0.55,
            "Se": 0.78,
            "Sx": 0.92,
            "Sl": 0.90,
            "Sp": 0.68,
            "Ph": 0.28,
            "Po": 0.12,
            "Pd": 0.10,
            "Pa": ambiguity,
            "Pv": verbosity,
        }

    return {
        "Sg": 0.25,
        "Su": 0.45,
        "St": 0.58,
        "Se": 0.32,
        "Sx": 0.35,
        "Sl": 0.88,
        "Sp": 0.85,
        "Ph": 0.45,
        "Po": 0.12,
        "Pd": 0.12,
        "Pa": ambiguity,
        "Pv": verbosity,
    }
