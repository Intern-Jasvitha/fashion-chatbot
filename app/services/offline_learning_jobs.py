"""Daily/weekly offline learning jobs for self-learning phases 4/5."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from prisma import Prisma

from app.core.config import get_settings
from app.services.release_control_service import snapshot_component_versions
from app.services.wrqs_config import get_default_wrqs_config


@dataclass
class JobWindow:
    start: date
    end: date


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "__dict__"):
        return dict(row.__dict__)
    return {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


async def _upsert_job_run(
    prisma: Prisma,
    *,
    job_type: str,
    window: JobWindow,
    status: str,
    summary: dict[str, Any],
    config_hash: Optional[str] = None,
) -> None:
    await prisma.execute_raw(
        """
        INSERT INTO "learning_job_run" (
          "id",
          "job_type",
          "window_start",
          "window_end",
          "status",
          "summary_json",
          "config_hash",
          "created_at",
          "updated_at"
        ) VALUES (
          $1,
          $2,
          $3::date,
          $4::date,
          $5,
          $6,
          $7,
          NOW(),
          NOW()
        )
        ON CONFLICT ("job_type", "window_start", "window_end")
        DO UPDATE SET
          "status" = EXCLUDED."status",
          "summary_json" = EXCLUDED."summary_json",
          "config_hash" = EXCLUDED."config_hash",
          "updated_at" = NOW()
        """,
        str(uuid4()),
        job_type,
        window.start.isoformat(),
        window.end.isoformat(),
        status,
        json.dumps(summary, default=str),
        config_hash,
    )


async def run_daily_job(prisma: Prisma, *, target_date: Optional[date] = None) -> dict[str, Any]:
    metric_day = target_date or datetime.now(timezone.utc).date()
    window = JobWindow(start=metric_day, end=metric_day)

    score_rows = await prisma.query_raw(
        """
        SELECT
          COALESCE(AVG(("payload_json"::jsonb ->> 'tqs')::float), 0) AS avg_tqs,
          COALESCE(AVG(("payload_json"::jsonb ->> 'kgs')::float), 0) AS avg_kgs,
          COALESCE(AVG(CASE WHEN (("payload_json"::jsonb ->> 'rephrase_count')::int > 0) THEN 1.0 ELSE 0.0 END), 0) AS rephrase_rate,
          COALESCE(AVG(CASE WHEN (("payload_json"::jsonb ->> 'handoff_click')::boolean = true) THEN 1.0 ELSE 0.0 END), 0) AS handoff_rate
        FROM "chat_event_log"
        WHERE "event_type" = 'TURN_SCORE'
          AND DATE("created_at") = $1::date
        """,
        metric_day.isoformat(),
    )
    score = _row_dict(score_rows[0]) if score_rows else {}

    feedback_rows = await prisma.query_raw(
        """
        SELECT COALESCE(
          COUNT(*) FILTER (WHERE "feedback_type" = 'DOWN')::float / NULLIF(COUNT(*), 0),
          0
        ) AS feedback_down_rate
        FROM "chat_feedback"
        WHERE DATE("created_at") = $1::date
        """,
        metric_day.isoformat(),
    )
    feedback_down_rate = 0.0
    if feedback_rows:
        feedback_down_rate = _to_float(_row_dict(feedback_rows[0]).get("feedback_down_rate"), 0.0)

    avg_tqs = _to_float(score.get("avg_tqs"), 0.0)
    avg_kgs = _to_float(score.get("avg_kgs"), 0.0)
    rephrase_rate = _to_float(score.get("rephrase_rate"), 0.0)
    handoff_rate = _to_float(score.get("handoff_rate"), 0.0)

    await prisma.execute_raw(
        """
        INSERT INTO "learning_daily_metrics" (
          "id",
          "metric_date",
          "avg_tqs",
          "avg_kgs",
          "rephrase_rate",
          "handoff_rate",
          "feedback_down_rate",
          "created_at",
          "updated_at"
        ) VALUES (
          $1,
          $2::date,
          $3,
          $4,
          $5,
          $6,
          $7,
          NOW(),
          NOW()
        )
        ON CONFLICT ("metric_date")
        DO UPDATE SET
          "avg_tqs" = EXCLUDED."avg_tqs",
          "avg_kgs" = EXCLUDED."avg_kgs",
          "rephrase_rate" = EXCLUDED."rephrase_rate",
          "handoff_rate" = EXCLUDED."handoff_rate",
          "feedback_down_rate" = EXCLUDED."feedback_down_rate",
          "updated_at" = NOW()
        """,
        str(uuid4()),
        metric_day.isoformat(),
        avg_tqs,
        avg_kgs,
        rephrase_rate,
        handoff_rate,
        feedback_down_rate,
    )

    feedback_topics = await prisma.query_raw(
        """
        SELECT
          COALESCE(NULLIF("payload_json"::jsonb ->> 'reason_code', ''), 'UNSPECIFIED') AS reason_code,
          COUNT(*)::int AS cnt
        FROM "chat_feedback"
        WHERE "feedback_type" = 'DOWN'
          AND DATE("created_at") = $1::date
        GROUP BY 1
        """,
        metric_day.isoformat(),
    )

    gap_updates = 0
    for row in feedback_topics:
        item = _row_dict(row)
        reason_code = str(item.get("reason_code") or "UNSPECIFIED")
        count = _to_int(item.get("cnt"), 0)
        if count <= 0:
            continue
        topic_key = f"feedback::{reason_code.lower()}"
        await prisma.execute_raw(
            """
            INSERT INTO "knowledge_gap_items" (
              "id",
              "topic_key",
              "intent",
              "status",
              "owner",
              "trigger_source",
              "score",
              "occurrence_count",
              "first_seen_at",
              "last_seen_at",
              "updated_at"
            ) VALUES (
              $1,
              $2,
              'hybrid',
              'NEW',
              NULL,
              'FEEDBACK_DOWN',
              70,
              $3,
              NOW(),
              NOW(),
              NOW()
            )
            ON CONFLICT ("topic_key", "intent")
            DO UPDATE SET
              "occurrence_count" = "knowledge_gap_items"."occurrence_count" + EXCLUDED."occurrence_count",
              "score" = GREATEST("knowledge_gap_items"."score", EXCLUDED."score"),
              "trigger_source" = EXCLUDED."trigger_source",
              "last_seen_at" = NOW(),
              "updated_at" = NOW()
            """,
            str(uuid4()),
            topic_key,
            count,
        )
        gap_updates += 1

    await prisma.execute_raw(
        """
        UPDATE "knowledge_gap_items"
        SET
          "status" = 'IN_REVIEW',
          "updated_at" = NOW()
        WHERE "status" = 'NEW'
          AND "occurrence_count" >= 3
        """
    )

    summary = {
        "metric_date": metric_day.isoformat(),
        "avg_tqs": round(avg_tqs, 4),
        "avg_kgs": round(avg_kgs, 4),
        "rephrase_rate": round(rephrase_rate, 4),
        "handoff_rate": round(handoff_rate, 4),
        "feedback_down_rate": round(feedback_down_rate, 4),
        "gap_updates": gap_updates,
    }
    await _upsert_job_run(
        prisma,
        job_type="DAILY",
        window=window,
        status="SUCCESS",
        summary=summary,
    )
    return summary


def _bounded_weight(base: float, target: float, *, max_delta: float) -> float:
    lo = base - max_delta
    hi = base + max_delta
    return max(lo, min(hi, target))


async def run_weekly_job(prisma: Prisma, *, window_end: Optional[date] = None) -> dict[str, Any]:
    end = window_end or datetime.now(timezone.utc).date()
    start = end - timedelta(days=6)
    window = JobWindow(start=start, end=end)

    rows = await prisma.query_raw(
        """
        SELECT
          COALESCE(AVG("avg_tqs"), 0) AS avg_tqs,
          COALESCE(AVG("avg_kgs"), 0) AS avg_kgs,
          COALESCE(AVG("feedback_down_rate"), 0) AS avg_feedback_down_rate
        FROM "learning_daily_metrics"
        WHERE "metric_date" BETWEEN $1::date AND $2::date
        """,
        start.isoformat(),
        end.isoformat(),
    )
    metrics = _row_dict(rows[0]) if rows else {}
    avg_tqs = _to_float(metrics.get("avg_tqs"), 0.0)
    avg_kgs = _to_float(metrics.get("avg_kgs"), 0.0)
    avg_feedback_down_rate = _to_float(metrics.get("avg_feedback_down_rate"), 0.0)

    base_cfg = get_default_wrqs_config()
    settings = get_settings()
    max_delta = float(settings.LEARNING_WEEKLY_WRQS_MAX_DELTA)
    positive = dict(base_cfg.positive_weights)
    penalty = dict(base_cfg.penalty_weights)

    if avg_kgs >= 65 or avg_feedback_down_rate >= 0.25:
        positive["Sg"] = _bounded_weight(base_cfg.positive_weights["Sg"], base_cfg.positive_weights["Sg"] + 0.01, max_delta=max_delta)
        positive["Su"] = _bounded_weight(base_cfg.positive_weights["Su"], base_cfg.positive_weights["Su"] + 0.01, max_delta=max_delta)
        penalty["Ph"] = _bounded_weight(base_cfg.penalty_weights["Ph"], base_cfg.penalty_weights["Ph"] - 0.01, max_delta=max_delta)
        penalty["Po"] = _bounded_weight(base_cfg.penalty_weights["Po"], base_cfg.penalty_weights["Po"] - 0.01, max_delta=max_delta)
    elif avg_kgs <= 40 and avg_feedback_down_rate <= 0.1 and avg_tqs >= 70:
        positive["Sg"] = _bounded_weight(base_cfg.positive_weights["Sg"], base_cfg.positive_weights["Sg"] - 0.005, max_delta=max_delta)
        positive["Su"] = _bounded_weight(base_cfg.positive_weights["Su"], base_cfg.positive_weights["Su"] - 0.005, max_delta=max_delta)
        penalty["Ph"] = _bounded_weight(base_cfg.penalty_weights["Ph"], base_cfg.penalty_weights["Ph"] + 0.005, max_delta=max_delta)
        penalty["Po"] = _bounded_weight(base_cfg.penalty_weights["Po"], base_cfg.penalty_weights["Po"] + 0.005, max_delta=max_delta)

    weights_blob = {
        "positive": positive,
        "penalty": penalty,
    }
    config_hash = sha256(json.dumps(weights_blob, sort_keys=True).encode("utf-8")).hexdigest()

    version_rows = await prisma.query_raw(
        """
        SELECT COALESCE(MAX("version"), 0) + 1 AS next_version
        FROM "wrqs_config_version"
        """
    )
    next_version = 1
    if version_rows:
        next_version = _to_int(_row_dict(version_rows[0]).get("next_version"), 1)

    await prisma.execute_raw('UPDATE "wrqs_config_version" SET "is_active" = false WHERE "is_active" = true')
    await prisma.execute_raw(
        """
        INSERT INTO "wrqs_config_version" (
          "id",
          "version",
          "positive_weights_json",
          "penalty_weights_json",
          "source_window_start",
          "source_window_end",
          "config_hash",
          "is_active",
          "created_at"
        ) VALUES (
          $1,
          $2,
          $3,
          $4,
          $5::date,
          $6::date,
          $7,
          true,
          NOW()
        )
        """,
        str(uuid4()),
        int(next_version),
        json.dumps(positive, sort_keys=True),
        json.dumps(penalty, sort_keys=True),
        start.isoformat(),
        end.isoformat(),
        config_hash,
    )

    gap_rows = await prisma.query_raw(
        """
        SELECT "topic_key", "last_session_id", "score", "occurrence_count"
        FROM "knowledge_gap_items"
        WHERE "status" IN ('NEW', 'IN_REVIEW')
          AND DATE("last_seen_at") BETWEEN $1::date AND $2::date
          AND "score" >= 70
        ORDER BY "score" DESC, "occurrence_count" DESC
        LIMIT 5
        """,
        start.isoformat(),
        end.isoformat(),
    )

    review_hooks = 0
    for row in gap_rows:
        item = _row_dict(row)
        session_id = item.get("last_session_id")
        topic_key = item.get("topic_key")
        if not isinstance(session_id, str) or not session_id:
            continue
        await prisma.execute_raw(
            """
            INSERT INTO "handoff_queue" (
              "id",
              "session_id",
              "message_id",
              "user_id",
              "customer_id",
              "reason_code",
              "priority",
              "status",
              "payload_json",
              "created_at",
              "updated_at"
            )
            SELECT
              $1,
              $2,
              NULL,
              NULL,
              NULL,
              'WEEKLY_REVIEW',
              'MEDIUM',
              'OPEN',
              $3,
              NOW(),
              NOW()
            WHERE NOT EXISTS (
              SELECT 1
              FROM "handoff_queue"
              WHERE "session_id" = $2
                AND "reason_code" = 'WEEKLY_REVIEW'
                AND "status" IN ('OPEN', 'IN_REVIEW')
            )
            """,
            str(uuid4()),
            session_id,
            json.dumps(
                {
                    "topic_key": topic_key,
                    "score": _to_int(item.get("score"), 0),
                    "occurrence_count": _to_int(item.get("occurrence_count"), 0),
                    "source": "weekly_gap_cluster",
                },
                default=str,
            ),
        )
        review_hooks += 1

    release_components = {}
    if getattr(settings, "ENABLE_RELEASE_CONTROLS", False):
        release_components = await snapshot_component_versions(
            prisma,
            settings=settings,
            status="STABLE",
            canary_percent=0,
        )

    summary = {
        "source_window_start": start.isoformat(),
        "source_window_end": end.isoformat(),
        "avg_tqs": round(avg_tqs, 4),
        "avg_kgs": round(avg_kgs, 4),
        "avg_feedback_down_rate": round(avg_feedback_down_rate, 4),
        "wrqs_version": int(next_version),
        "review_hooks": review_hooks,
        "release_component_count": len(release_components),
    }
    await _upsert_job_run(
        prisma,
        job_type="WEEKLY",
        window=window,
        status="SUCCESS",
        summary=summary,
        config_hash=config_hash,
    )
    return summary
