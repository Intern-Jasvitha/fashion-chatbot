"""Default WRQS scoring config."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WRQSConfig:
    positive_weights: dict[str, float] = field(
        default_factory=lambda: {
            "Sg": 0.24,
            "Su": 0.18,
            "St": 0.20,
            "Se": 0.14,
            "Sx": 0.10,
            "Sl": 0.08,
            "Sp": 0.06,
        }
    )
    penalty_weights: dict[str, float] = field(
        default_factory=lambda: {
            "Ph": 0.35,
            "Po": 0.40,
            "Pd": 0.30,
            "Pa": 0.18,
            "Pv": 0.08,
        }
    )
    wrqs_tie_delta: float = 0.03
    min_retrieval_confidence: float = 0.35
    min_support_ratio: float = 0.45


def get_default_wrqs_config() -> WRQSConfig:
    return WRQSConfig()

