"""In-session online adaptation utilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from prisma import Prisma

from app.services.wrqs_config import WRQSConfig, get_default_wrqs_config


@dataclass
class SessionFeatureSnapshot:
    session_id: str
    user_id: Optional[int]
    customer_id: Optional[int]
    turn_index: int
    rephrase_count: int
    explain_clicks: int
    handoff_clicks: int
    lang_pref: Optional[str]
    short_answer_pref: Optional[bool]
    last_tqs: Optional[int]
    last_kgs: Optional[int]
    clarify_mode: bool
    rag_top_k_override: Optional[int]
    query_expansion_enabled: bool
    wrqs_weight_overrides: dict[str, dict[str, float]]
    adaptation_expires_turn: Optional[int]


@dataclass
class AdaptationDecision:
    should_apply: bool
    reason_codes: list[str]
    clarify_mode: bool = False
    rag_top_k_override: Optional[int] = None
    query_expansion_enabled: bool = False
    wrqs_weight_overrides: dict[str, dict[str, float]] | None = None
    adaptation_expires_turn: Optional[int] = None


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "__dict__"):
        return dict(row.__dict__)
    return {}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "y")
    return bool(value)


def _parse_overrides(raw: Any) -> dict[str, dict[str, float]]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            parsed = json.loads(str(raw))
        except Exception:
            return {}
    out: dict[str, dict[str, float]] = {}
    for section in ("positive", "penalty"):
        data = parsed.get(section)
        if not isinstance(data, dict):
            continue
        out[section] = {}
        for key, value in data.items():
            try:
                out[section][str(key)] = float(value)
            except Exception:
                continue
    return out


def _to_snapshot(data: dict[str, Any], session_id: str) -> SessionFeatureSnapshot:
    return SessionFeatureSnapshot(
        session_id=session_id,
        user_id=data.get("user_id"),
        customer_id=data.get("customer_id"),
        turn_index=_to_int(data.get("turn_index")),
        rephrase_count=_to_int(data.get("rephrase_count")),
        explain_clicks=_to_int(data.get("explain_clicks")),
        handoff_clicks=_to_int(data.get("handoff_clicks")),
        lang_pref=data.get("lang_pref"),
        short_answer_pref=data.get("short_answer_pref"),
        last_tqs=_to_int(data.get("last_tqs"), default=0) if data.get("last_tqs") is not None else None,
        last_kgs=_to_int(data.get("last_kgs"), default=0) if data.get("last_kgs") is not None else None,
        clarify_mode=_to_bool(data.get("clarify_mode")),
        rag_top_k_override=_to_int(data.get("rag_top_k_override"), default=0)
        if data.get("rag_top_k_override") is not None
        else None,
        query_expansion_enabled=_to_bool(data.get("query_expansion_enabled")),
        wrqs_weight_overrides=_parse_overrides(data.get("wrqs_weight_overrides_json")),
        adaptation_expires_turn=_to_int(data.get("adaptation_expires_turn"), default=0)
        if data.get("adaptation_expires_turn") is not None
        else None,
    )


async def _fetch_session_feature(prisma: Prisma, session_id: str) -> Optional[SessionFeatureSnapshot]:
    if not hasattr(prisma, "query_raw"):
        return None
    rows = await prisma.query_raw(
        """
        SELECT
          "session_id",
          "user_id",
          "customer_id",
          "turn_index",
          "rephrase_count",
          "explain_clicks",
          "handoff_clicks",
          "lang_pref",
          "short_answer_pref",
          "last_tqs",
          "last_kgs",
          "clarify_mode",
          "rag_top_k_override",
          "query_expansion_enabled",
          "wrqs_weight_overrides_json",
          "adaptation_expires_turn"
        FROM "session_features"
        WHERE "session_id" = $1
        LIMIT 1
        """,
        session_id,
    )
    if not rows:
        return None
    return _to_snapshot(_row_dict(rows[0]), session_id)


async def get_or_create_session_feature(
    prisma: Prisma,
    *,
    session_id: str,
    user_id: Optional[int],
    customer_id: Optional[int],
) -> SessionFeatureSnapshot:
    """Ensure session_features row exists and return snapshot."""
    await prisma.execute_raw(
        """
        INSERT INTO "session_features" (
          "session_id",
          "user_id",
          "customer_id",
          "updated_at"
        ) VALUES (
          $1, $2, $3, NOW()
        )
        ON CONFLICT ("session_id") DO NOTHING
        """,
        session_id,
        user_id,
        customer_id,
    )
    snapshot = await _fetch_session_feature(prisma, session_id)
    if snapshot is not None:
        return snapshot
    return SessionFeatureSnapshot(
        session_id=session_id,
        user_id=user_id,
        customer_id=customer_id,
        turn_index=0,
        rephrase_count=0,
        explain_clicks=0,
        handoff_clicks=0,
        lang_pref=None,
        short_answer_pref=None,
        last_tqs=None,
        last_kgs=None,
        clarify_mode=False,
        rag_top_k_override=None,
        query_expansion_enabled=False,
        wrqs_weight_overrides={},
        adaptation_expires_turn=None,
    )


async def expire_adaptation(
    prisma: Prisma,
    *,
    session_id: str,
    current_turn_index: int,
) -> SessionFeatureSnapshot:
    """Auto-expire temporary adaptation once TTL is reached."""
    await prisma.execute_raw(
        """
        UPDATE "session_features"
        SET
          "clarify_mode" = false,
          "rag_top_k_override" = NULL,
          "query_expansion_enabled" = false,
          "wrqs_weight_overrides_json" = NULL,
          "adaptation_expires_turn" = NULL,
          "updated_at" = NOW()
        WHERE "session_id" = $1
          AND "adaptation_expires_turn" IS NOT NULL
          AND "adaptation_expires_turn" < $2
        """,
        session_id,
        int(current_turn_index),
    )
    snapshot = await _fetch_session_feature(prisma, session_id)
    if snapshot is None:
        raise RuntimeError("session_features missing after expire_adaptation")
    return snapshot


async def persist_turn_scores(
    prisma: Prisma,
    *,
    session_id: str,
    turn_index: int,
    tqs: int,
    kgs: int,
    rephrase_count: int,
) -> None:
    await prisma.execute_raw(
        """
        UPDATE "session_features"
        SET
          "turn_index" = $2,
          "last_tqs" = $3,
          "last_kgs" = $4,
          "rephrase_count" = $5,
          "updated_at" = NOW()
        WHERE "session_id" = $1
        """,
        session_id,
        int(turn_index),
        int(tqs),
        int(kgs),
        int(rephrase_count),
    )


def detect_rephrase(current_message: str, previous_user_message: Optional[str]) -> bool:
    """Simple deterministic rephrase detector for in-session adaptation."""
    if not previous_user_message:
        return False
    current = " ".join((current_message or "").lower().split())
    previous = " ".join((previous_user_message or "").lower().split())
    if not current or not previous:
        return False
    if current == previous:
        return True
    if any(token in current for token in ("rephrase", "again", "not what i asked", "didn't answer", "did not answer")):
        return True
    return SequenceMatcher(a=current, b=previous).ratio() >= 0.86


def evaluate_adaptation(
    *,
    tqs: int,
    kgs: int,
    rephrase_count: int,
    handoff_clicks: int,
    current_turn_index: int,
    low_tqs_threshold: int,
    high_kgs_threshold: int,
    rag_topk_adapt: int,
    ttl_turns: int,
) -> AdaptationDecision:
    """Apply deterministic trigger rules for online adaptation."""
    reasons: list[str] = []
    if int(tqs) < int(low_tqs_threshold):
        reasons.append("LOW_TQS")
    if int(kgs) >= int(high_kgs_threshold):
        reasons.append("HIGH_KGS")
    if int(rephrase_count) >= 2:
        reasons.append("REPHRASE_COUNT")
    if int(handoff_clicks) > 0:
        reasons.append("HANDOFF_CLICK")

    if not reasons:
        return AdaptationDecision(should_apply=False, reason_codes=[])

    base_cfg = get_default_wrqs_config()
    positive = dict(base_cfg.positive_weights)
    penalty = dict(base_cfg.penalty_weights)

    positive["Sg"] = positive.get("Sg", 0.0) + 0.05
    positive["Su"] = positive.get("Su", 0.0) + 0.04
    penalty["Ph"] = penalty.get("Ph", 0.0) - 0.05
    penalty["Pa"] = penalty.get("Pa", 0.0) - 0.03

    return AdaptationDecision(
        should_apply=True,
        reason_codes=reasons,
        clarify_mode=True,
        rag_top_k_override=int(rag_topk_adapt),
        query_expansion_enabled=True,
        wrqs_weight_overrides={"positive": positive, "penalty": penalty},
        adaptation_expires_turn=int(current_turn_index) + int(ttl_turns),
    )


async def apply_adaptation(
    prisma: Prisma,
    *,
    session_id: str,
    decision: AdaptationDecision,
) -> None:
    if not decision.should_apply:
        return
    await prisma.execute_raw(
        """
        UPDATE "session_features"
        SET
          "clarify_mode" = $2,
          "rag_top_k_override" = $3,
          "query_expansion_enabled" = $4,
          "wrqs_weight_overrides_json" = $5,
          "adaptation_expires_turn" = $6,
          "updated_at" = NOW()
        WHERE "session_id" = $1
        """,
        session_id,
        bool(decision.clarify_mode),
        decision.rag_top_k_override,
        bool(decision.query_expansion_enabled),
        json.dumps(decision.wrqs_weight_overrides or {}, default=str),
        decision.adaptation_expires_turn,
    )


def adaptation_state(snapshot: SessionFeatureSnapshot) -> dict[str, Any]:
    return {
        "clarify_mode": bool(snapshot.clarify_mode),
        "rag_top_k_override": snapshot.rag_top_k_override,
        "query_expansion_enabled": bool(snapshot.query_expansion_enabled),
        "wrqs_weight_overrides": snapshot.wrqs_weight_overrides,
        "short_answer_pref": snapshot.short_answer_pref,
        "lang_pref": snapshot.lang_pref,
    }


def apply_wrqs_overrides(
    config: WRQSConfig,
    overrides: dict[str, dict[str, float]] | None,
    *,
    max_delta: float = 0.10,
) -> WRQSConfig:
    """Merge adaptation-provided weight overrides with +/- max_delta safety caps."""
    if not overrides:
        return config

    positive = dict(config.positive_weights)
    penalty = dict(config.penalty_weights)

    for key, target in (overrides.get("positive") or {}).items():
        if key not in positive:
            continue
        base = float(config.positive_weights[key])
        lo = base - max_delta
        hi = base + max_delta
        positive[key] = max(lo, min(hi, float(target)))

    for key, target in (overrides.get("penalty") or {}).items():
        if key not in penalty:
            continue
        base = float(config.penalty_weights[key])
        lo = base - max_delta
        hi = base + max_delta
        penalty[key] = max(lo, min(hi, float(target)))

    return WRQSConfig(
        positive_weights=positive,
        penalty_weights=penalty,
        wrqs_tie_delta=config.wrqs_tie_delta,
        min_retrieval_confidence=config.min_retrieval_confidence,
        min_support_ratio=config.min_support_ratio,
    )


def build_gap_topic_key(intent: str, user_message: str) -> str:
    normalized = re.sub(r"\s+", " ", (user_message or "").strip().lower())
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{(intent or 'unknown').lower()}::{digest}"


async def upsert_knowledge_gap_item(
    prisma: Prisma,
    *,
    topic_key: str,
    intent: str,
    trigger_source: str,
    score: int,
    request_id: str,
    session_id: str,
) -> None:
    await prisma.execute_raw(
        """
        INSERT INTO "knowledge_gap_items" (
          "id",
          "topic_key",
          "intent",
          "status",
          "trigger_source",
          "score",
          "occurrence_count",
          "last_request_id",
          "last_session_id",
          "first_seen_at",
          "last_seen_at"
        ) VALUES (
          $7,
          $1, $2, 'NEW', $3, $4, 1, $5, $6, NOW(), NOW()
        )
        ON CONFLICT ("topic_key", "intent")
        DO UPDATE SET
          "occurrence_count" = "knowledge_gap_items"."occurrence_count" + 1,
          "score" = GREATEST("knowledge_gap_items"."score", EXCLUDED."score"),
          "trigger_source" = EXCLUDED."trigger_source",
          "last_request_id" = EXCLUDED."last_request_id",
          "last_session_id" = EXCLUDED."last_session_id",
          "last_seen_at" = NOW()
        """,
        topic_key,
        intent,
        trigger_source,
        int(score),
        request_id,
        session_id,
        str(uuid4()),
    )
