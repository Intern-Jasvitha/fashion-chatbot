"""Ops dashboard aggregations for Phase 8 KPI and alert visibility."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from prisma import Prisma


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


async def get_ops_dashboard(prisma: Prisma, *, days: int) -> dict[str, Any]:
    days_safe = max(1, int(days))
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days_safe - 1)

    intent_rows = await prisma.query_raw(
        """
        SELECT
          COALESCE(NULLIF("payload_json"::jsonb ->> 'intent', ''), 'unknown') AS intent,
          COALESCE(AVG(("payload_json"::jsonb ->> 'tqs')::float), 0) AS avg_tqs,
          COALESCE(AVG(("payload_json"::jsonb ->> 'kgs')::float), 0) AS avg_kgs,
          COUNT(*)::int AS turns
        FROM "chat_event_log"
        WHERE "event_type" = 'TURN_SCORE'
          AND DATE("created_at") BETWEEN $1::date AND $2::date
        GROUP BY 1
        ORDER BY turns DESC
        """,
        start_date.isoformat(),
        end_date.isoformat(),
    )

    top_gap_rows = await prisma.query_raw(
        """
        SELECT "topic_key", "intent", "score", "occurrence_count", "status"
        FROM "knowledge_gap_items"
        ORDER BY "score" DESC, "occurrence_count" DESC
        LIMIT 8
        """
    )

    aggregate_rows = await prisma.query_raw(
        """
        SELECT
          COALESCE(AVG(("payload_json"::jsonb ->> 'tqs')::float), 0) AS avg_tqs,
          COALESCE(AVG(("payload_json"::jsonb ->> 'kgs')::float), 0) AS avg_kgs,
          COALESCE(AVG(CASE WHEN (("payload_json"::jsonb ->> 'rephrase_count')::int > 0) THEN 1.0 ELSE 0.0 END), 0) AS rephrase_rate,
          COALESCE(AVG(CASE WHEN (("payload_json"::jsonb ->> 'handoff_click')::boolean = true) THEN 1.0 ELSE 0.0 END), 0) AS handoff_rate
        FROM "chat_event_log"
        WHERE "event_type" = 'TURN_SCORE'
          AND DATE("created_at") BETWEEN $1::date AND $2::date
        """,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    aggregate = _row_dict(aggregate_rows[0]) if aggregate_rows else {}

    refusal_rows = await prisma.query_raw(
        """
        SELECT
          COUNT(*) FILTER (WHERE "allow" = false)::int AS blocked_count,
          COUNT(*)::int AS total_count
        FROM "policy_audit"
        WHERE DATE("created_at") BETWEEN $1::date AND $2::date
        """,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    refusal = _row_dict(refusal_rows[0]) if refusal_rows else {}
    blocked_count = _to_int(refusal.get("blocked_count"))
    total_policy = _to_int(refusal.get("total_count"))
    refusal_quality = 1.0 if total_policy == 0 else max(0.0, 1.0 - (blocked_count / float(total_policy)))

    completion_rows = await prisma.query_raw(
        """
        SELECT
          COUNT(*) FILTER (WHERE "role" = 'assistant')::int AS assistant_count,
          COUNT(*) FILTER (WHERE "role" = 'user')::int AS user_count
        FROM "chat_message"
        WHERE DATE("createdAt") BETWEEN $1::date AND $2::date
        """,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    completion = _row_dict(completion_rows[0]) if completion_rows else {}
    assistant_count = _to_int(completion.get("assistant_count"))
    user_count = _to_int(completion.get("user_count"))
    completion_rate = 1.0 if user_count == 0 else min(1.0, assistant_count / float(user_count))

    disclosure_rows = await prisma.query_raw(
        """
        SELECT COUNT(*)::int AS cnt
        FROM "learning_exclusion_audit"
        WHERE DATE("created_at") BETWEEN $1::date AND $2::date
          AND "exclusion_reason_code" IN ('POLICY_BLOCKED', 'SENSITIVE_PATTERN')
        """,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    disclosure_count = _to_int((_row_dict(disclosure_rows[0]) if disclosure_rows else {}).get("cnt"))

    sql_anomaly_rows = await prisma.query_raw(
        """
        SELECT
          COUNT(*) FILTER (
            WHERE COALESCE("payload_json"::jsonb ->> 'agent', '') = 'sql_agent'
              AND COALESCE("payload_json"::jsonb ->> 'status', '') = 'error'
          )::int AS sql_error_steps,
          COUNT(*) FILTER (
            WHERE COALESCE("payload_json"::jsonb ->> 'agent', '') = 'sql_agent'
          )::int AS sql_total_steps
        FROM "chat_event_log"
        WHERE "event_type" = 'TOOL_CALL'
          AND DATE("created_at") BETWEEN $1::date AND $2::date
        """,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    sql_row = _row_dict(sql_anomaly_rows[0]) if sql_anomaly_rows else {}
    sql_error_steps = _to_int(sql_row.get("sql_error_steps"))
    sql_total_steps = _to_int(sql_row.get("sql_total_steps"))
    sql_anomaly_rate = 0.0 if sql_total_steps == 0 else (sql_error_steps / float(sql_total_steps))

    handoff_rate = _to_float(aggregate.get("handoff_rate"))
    alerts = {
        "disclosure_risk": {
            "triggered": disclosure_count > 0,
            "count": disclosure_count,
        },
        "sql_anomaly": {
            "triggered": sql_anomaly_rate >= 0.2,
            "rate": round(sql_anomaly_rate, 6),
        },
        "handoff_spike": {
            "triggered": handoff_rate >= 0.15,
            "rate": round(handoff_rate, 6),
        },
    }

    return {
        "window": {
            "days": days_safe,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "summary": {
            "avg_tqs": round(_to_float(aggregate.get("avg_tqs")), 4),
            "avg_kgs": round(_to_float(aggregate.get("avg_kgs")), 4),
            "rephrase_rate": round(_to_float(aggregate.get("rephrase_rate")), 4),
            "handoff_rate": round(handoff_rate, 4),
            "refusal_quality": round(refusal_quality, 4),
            "completion_rate": round(completion_rate, 4),
        },
        "avg_tqs_by_intent": [
            {
                "intent": str(_row_dict(row).get("intent") or "unknown"),
                "avg_tqs": round(_to_float(_row_dict(row).get("avg_tqs")), 4),
                "avg_kgs": round(_to_float(_row_dict(row).get("avg_kgs")), 4),
                "turns": _to_int(_row_dict(row).get("turns")),
            }
            for row in intent_rows
        ],
        "top_kgs_topics": [_row_dict(row) for row in top_gap_rows],
        "alerts": alerts,
    }


async def get_ops_snapshot(prisma: Prisma) -> dict[str, Any]:
    dashboard = await get_ops_dashboard(prisma, days=7)
    summary = dashboard.get("summary", {})
    alerts = dashboard.get("alerts", {})
    return {
        "avg_tqs": summary.get("avg_tqs", 0.0),
        "avg_kgs": summary.get("avg_kgs", 0.0),
        "handoff_rate": summary.get("handoff_rate", 0.0),
        "alerts_triggered": [k for k, v in alerts.items() if isinstance(v, dict) and v.get("triggered")],
    }
