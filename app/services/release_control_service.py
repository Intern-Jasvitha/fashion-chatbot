"""Release controls for golden-gate, canary, rollback, and component version snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from prisma import Prisma

from app.core.config import Settings
from app.graph.nodes import RESULT_FORMATTING_PROMPT, SQL_PLAN_PROMPT, SYSTEM_PROMPT as INTENT_ROUTER_PROMPT
from app.services.policy_agent import POLICY_CLASSIFIER_PROMPT
from app.services.policy_gate import UserState, evaluate_policy
from app.services.wrqs_config import get_default_wrqs_config


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


def _hash_text(value: str) -> str:
    return sha256((value or "").encode("utf-8")).hexdigest()


def _json_load_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    try:
        parsed = json.loads(str(raw))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(x).strip().lower() for x in parsed if str(x).strip()]


async def _upsert_component_version(
    prisma: Prisma,
    *,
    component_key: str,
    version_hash: str,
    version_label: Optional[str],
    status: str,
    canary_percent: int,
    source: Optional[dict[str, Any]],
) -> None:
    await prisma.execute_raw(
        """
        INSERT INTO "release_component_version" (
          "id",
          "component_key",
          "version_hash",
          "version_label",
          "status",
          "canary_percent",
          "source_json",
          "created_at",
          "updated_at"
        ) VALUES (
          $1,
          $2,
          $3,
          $4,
          $5,
          $6,
          $7,
          NOW(),
          NOW()
        )
        ON CONFLICT ("component_key", "version_hash")
        DO UPDATE SET
          "status" = EXCLUDED."status",
          "canary_percent" = EXCLUDED."canary_percent",
          "source_json" = EXCLUDED."source_json",
          "updated_at" = NOW()
        """,
        str(uuid4()),
        component_key,
        version_hash,
        version_label,
        status,
        int(canary_percent),
        json.dumps(source or {}, default=str),
    )


async def get_active_wrqs_weights(prisma: Prisma) -> Optional[dict[str, Any]]:
    rows = await prisma.query_raw(
        """
        SELECT
          "version",
          "config_hash",
          "positive_weights_json",
          "penalty_weights_json"
        FROM "wrqs_config_version"
        WHERE "is_active" = true
        ORDER BY "created_at" DESC
        LIMIT 1
        """
    )
    if not rows:
        return None
    row = _row_dict(rows[0])
    try:
        positive = json.loads(str(row.get("positive_weights_json") or "{}"))
        penalty = json.loads(str(row.get("penalty_weights_json") or "{}"))
    except Exception:
        return None
    if not isinstance(positive, dict) or not isinstance(penalty, dict):
        return None
    return {
        "version": _to_int(row.get("version")),
        "config_hash": str(row.get("config_hash") or ""),
        "positive_weights": {str(k): float(v) for k, v in positive.items()},
        "penalty_weights": {str(k): float(v) for k, v in penalty.items()},
    }


async def snapshot_component_versions(
    prisma: Prisma,
    *,
    settings: Settings,
    status: str = "STABLE",
    canary_percent: int = 0,
) -> dict[str, dict[str, Any]]:
    wrqs_active = await get_active_wrqs_weights(prisma)
    if wrqs_active:
        wrqs_blob = {
            "positive": wrqs_active["positive_weights"],
            "penalty": wrqs_active["penalty_weights"],
        }
        wrqs_hash = str(wrqs_active.get("config_hash") or _hash_text(json.dumps(wrqs_blob, sort_keys=True)))
        wrqs_label = f"wrqs-v{int(wrqs_active.get('version', 0))}"
    else:
        cfg = get_default_wrqs_config()
        wrqs_blob = {
            "positive": cfg.positive_weights,
            "penalty": cfg.penalty_weights,
        }
        wrqs_hash = _hash_text(json.dumps(wrqs_blob, sort_keys=True))
        wrqs_label = "wrqs-default"

    components = {
        "policy_prompt": {
            "version_hash": _hash_text(POLICY_CLASSIFIER_PROMPT),
            "version_label": "policy-classifier-prompt",
            "source": {},
        },
        "intent_router_prompt": {
            "version_hash": _hash_text(INTENT_ROUTER_PROMPT),
            "version_label": "intent-router-prompt",
            "source": {},
        },
        "sql_prompt_bundle": {
            "version_hash": _hash_text(SQL_PLAN_PROMPT + "\n---\n" + RESULT_FORMATTING_PROMPT),
            "version_label": "sql-plan+format",
            "source": {},
        },
        "rag_index": {
            "version_hash": _hash_text(settings.QDRANT_COLLECTION_NAME),
            "version_label": settings.QDRANT_COLLECTION_NAME,
            "source": {"collection": settings.QDRANT_COLLECTION_NAME},
        },
        "wrqs_config": {
            "version_hash": wrqs_hash,
            "version_label": wrqs_label,
            "source": wrqs_blob,
        },
    }

    for key, value in components.items():
        await _upsert_component_version(
            prisma,
            component_key=key,
            version_hash=str(value["version_hash"]),
            version_label=str(value.get("version_label") or ""),
            status=status if key == "wrqs_config" else "STABLE",
            canary_percent=canary_percent if key == "wrqs_config" else 0,
            source=value.get("source"),
        )
    return components


def is_experiment_dimension_allowed(dimension: str) -> bool:
    allowed = {"wrqs_weights", "response_style"}
    return (dimension or "").strip().lower() in allowed


async def run_golden_gate(
    prisma: Prisma,
    *,
    triggered_by_user_id: Optional[int],
    min_pass_rate: float,
    run_window_days: int = 7,
) -> dict[str, Any]:
    rows = await prisma.query_raw(
        """
        SELECT
          "case_key",
          "prompt_text",
          "expected_allow",
          "expected_reason_code",
          "expected_intent",
          "forbidden_terms_json",
          "required_terms_json"
        FROM "golden_conversation_case"
        WHERE "enabled" = true
        ORDER BY "created_at" ASC
        """
    )
    failures: list[dict[str, Any]] = []
    passed = 0
    total = 0
    for row in rows:
        case = _row_dict(row)
        prompt = str(case.get("prompt_text") or "")
        decision = evaluate_policy(prompt, user_state=UserState.REGISTERED)
        total += 1
        ok = bool(decision.allow) == bool(case.get("expected_allow"))
        expected_reason = case.get("expected_reason_code")
        if expected_reason:
            ok = ok and (str(decision.reason_code or "") == str(expected_reason))
        expected_intent = case.get("expected_intent")
        if expected_intent:
            ok = ok and (decision.intent.value == str(expected_intent))

        refusal = (decision.refusal_text or "").lower()
        for forbidden in _json_load_list(case.get("forbidden_terms_json")):
            if forbidden in refusal:
                ok = False
                break
        for required in _json_load_list(case.get("required_terms_json")):
            if required not in refusal:
                ok = False
                break

        if ok:
            passed += 1
        else:
            failures.append(
                {
                    "case_key": case.get("case_key"),
                    "expected_allow": bool(case.get("expected_allow")),
                    "actual_allow": bool(decision.allow),
                    "expected_reason_code": expected_reason,
                    "actual_reason_code": decision.reason_code,
                }
            )

    pass_rate = 1.0 if total == 0 else float(passed) / float(total)
    status = "PASS" if pass_rate >= float(min_pass_rate) else "FAIL"

    await prisma.execute_raw(
        """
        INSERT INTO "golden_conversation_run" (
          "id",
          "triggered_by_user_id",
          "run_window_days",
          "pass_rate",
          "status",
          "fail_summary_json",
          "created_at"
        ) VALUES (
          $1,
          $2,
          $3,
          $4,
          $5,
          $6,
          NOW()
        )
        """,
        str(uuid4()),
        triggered_by_user_id,
        int(run_window_days),
        float(pass_rate),
        status,
        json.dumps(
            {
                "total_cases": total,
                "passed_cases": passed,
                "failures": failures,
            },
            default=str,
        ),
    )
    return {
        "status": status,
        "pass_rate": round(pass_rate, 6),
        "min_required_pass_rate": float(min_pass_rate),
        "total_cases": total,
        "passed_cases": passed,
        "failures": failures,
    }


async def _latest_golden_run(prisma: Prisma) -> Optional[dict[str, Any]]:
    rows = await prisma.query_raw(
        """
        SELECT "pass_rate", "status", "created_at"
        FROM "golden_conversation_run"
        ORDER BY "created_at" DESC
        LIMIT 1
        """
    )
    return _row_dict(rows[0]) if rows else None


async def _metrics_window(prisma: Prisma, *, days: int) -> dict[str, float]:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=max(0, int(days) - 1))
    rows = await prisma.query_raw(
        """
        SELECT
          COALESCE(AVG("avg_tqs"), 0) AS avg_tqs,
          COALESCE(AVG("avg_kgs"), 0) AS avg_kgs,
          COALESCE(AVG("handoff_rate"), 0) AS handoff_rate
        FROM "learning_daily_metrics"
        WHERE "metric_date" BETWEEN $1::date AND $2::date
        """,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    row = _row_dict(rows[0]) if rows else {}
    return {
        "avg_tqs": _to_float(row.get("avg_tqs")),
        "avg_kgs": _to_float(row.get("avg_kgs")),
        "handoff_rate": _to_float(row.get("handoff_rate")),
    }


async def start_canary_rollout(
    prisma: Prisma,
    *,
    settings: Settings,
    triggered_by_user_id: Optional[int],
    canary_percent: int,
) -> dict[str, Any]:
    latest = await _latest_golden_run(prisma)
    min_pass_rate = float(settings.RELEASE_GOLDEN_MIN_PASS_RATE)
    if not latest:
        return {"started": False, "reason": "No golden run found. Run golden gate first."}
    latest_pass_rate = _to_float(latest.get("pass_rate"), 0.0)
    latest_status = str(latest.get("status") or "")
    if latest_status != "PASS" or latest_pass_rate < min_pass_rate:
        return {"started": False, "reason": "Latest golden run did not pass the gate."}

    baseline = await _metrics_window(prisma, days=7)
    await prisma.execute_raw(
        """
        INSERT INTO "canary_rollout_run" (
          "id",
          "triggered_by_user_id",
          "canary_percent",
          "baseline_metrics_json",
          "current_metrics_json",
          "rollback_triggered",
          "status",
          "notes",
          "created_at",
          "updated_at"
        ) VALUES (
          $1,
          $2,
          $3,
          $4,
          $5,
          false,
          'ACTIVE',
          NULL,
          NOW(),
          NOW()
        )
        """,
        str(uuid4()),
        triggered_by_user_id,
        int(canary_percent),
        json.dumps(baseline, default=str),
        json.dumps(baseline, default=str),
    )
    await snapshot_component_versions(
        prisma,
        settings=settings,
        status="CANARY",
        canary_percent=canary_percent,
    )
    return {
        "started": True,
        "canary_percent": int(canary_percent),
        "baseline_metrics": baseline,
    }


async def evaluate_canary_and_maybe_rollback(
    prisma: Prisma,
    *,
    settings: Settings,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    rows = await prisma.query_raw(
        """
        SELECT
          "id",
          "canary_percent",
          "baseline_metrics_json",
          "status"
        FROM "canary_rollout_run"
        WHERE "status" = 'ACTIVE'
        ORDER BY "created_at" DESC
        LIMIT 1
        """
    )
    if not rows:
        return {"rolled_back": False, "reason": "No active canary run."}
    run = _row_dict(rows[0])
    baseline = {}
    try:
        baseline = json.loads(str(run.get("baseline_metrics_json") or "{}"))
    except Exception:
        baseline = {}
    current = await _metrics_window(prisma, days=7)
    kgs_delta = float(current.get("avg_kgs", 0.0)) - _to_float(baseline.get("avg_kgs"), 0.0)
    handoff_rate = _to_float(current.get("handoff_rate"), 0.0)
    should_rollback = (
        kgs_delta > float(settings.RELEASE_ROLLBACK_MAX_KGS_DELTA)
        or handoff_rate > float(settings.RELEASE_ROLLBACK_MAX_HANDOFF_RATE)
    )
    next_status = "ROLLED_BACK" if should_rollback else "ACTIVE"
    await prisma.execute_raw(
        """
        UPDATE "canary_rollout_run"
        SET
          "current_metrics_json" = $2,
          "rollback_triggered" = $3,
          "status" = $4,
          "notes" = $5,
          "updated_at" = NOW()
        WHERE "id" = $1
        """,
        str(run.get("id")),
        json.dumps(current, default=str),
        bool(should_rollback),
        next_status,
        (notes or "").strip() or None,
    )
    if should_rollback:
        await prisma.execute_raw(
            """
            UPDATE "release_component_version"
            SET "status" = 'ROLLED_BACK', "updated_at" = NOW()
            WHERE "component_key" = 'wrqs_config'
            """
        )
    return {
        "rolled_back": bool(should_rollback),
        "status": next_status,
        "kgs_delta": round(kgs_delta, 6),
        "handoff_rate": round(handoff_rate, 6),
        "thresholds": {
            "max_kgs_delta": float(settings.RELEASE_ROLLBACK_MAX_KGS_DELTA),
            "max_handoff_rate": float(settings.RELEASE_ROLLBACK_MAX_HANDOFF_RATE),
        },
    }


async def get_release_status(prisma: Prisma) -> dict[str, Any]:
    components = await prisma.query_raw(
        """
        SELECT
          "component_key",
          "version_hash",
          "version_label",
          "status",
          "canary_percent",
          "updated_at"
        FROM (
          SELECT
            "component_key",
            "version_hash",
            "version_label",
            "status",
            "canary_percent",
            "updated_at",
            ROW_NUMBER() OVER (PARTITION BY "component_key" ORDER BY "updated_at" DESC) AS rn
          FROM "release_component_version"
        ) c
        WHERE c.rn = 1
        ORDER BY "component_key" ASC
        """
    )
    golden = await prisma.query_raw(
        """
        SELECT "pass_rate", "status", "created_at"
        FROM "golden_conversation_run"
        ORDER BY "created_at" DESC
        LIMIT 1
        """
    )
    canary = await prisma.query_raw(
        """
        SELECT
          "canary_percent",
          "rollback_triggered",
          "status",
          "updated_at"
        FROM "canary_rollout_run"
        ORDER BY "created_at" DESC
        LIMIT 1
        """
    )
    return {
        "components": [_row_dict(row) for row in components],
        "latest_golden_run": _row_dict(golden[0]) if golden else None,
        "latest_canary_run": _row_dict(canary[0]) if canary else None,
    }
