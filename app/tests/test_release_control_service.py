import json
from types import SimpleNamespace

import pytest

from app.services import release_control_service


class FakePrisma:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.golden_runs = [
            {"pass_rate": 0.99, "status": "PASS", "created_at": "2026-02-20T00:00:00Z"}
        ]
        self.active_canary = {
            "id": "canary-1",
            "canary_percent": 10,
            "baseline_metrics_json": json.dumps(
                {"avg_tqs": 70.0, "avg_kgs": 40.0, "handoff_rate": 0.04}
            ),
            "status": "ACTIVE",
        }

    async def query_raw(self, query, *args):
        if 'FROM "wrqs_config_version"' in query:
            return [
                {
                    "version": 2,
                    "config_hash": "wrqs-hash",
                    "positive_weights_json": json.dumps({"Sg": 0.24}),
                    "penalty_weights_json": json.dumps({"Ph": 0.35}),
                }
            ]
        if 'FROM "golden_conversation_case"' in query:
            return [
                {
                    "case_key": "guest-public",
                    "prompt_text": "What is OASIS Halo?",
                    "expected_allow": True,
                    "expected_reason_code": None,
                    "expected_intent": "OASIS_PUBLIC_INFO",
                    "forbidden_terms_json": None,
                    "required_terms_json": None,
                }
            ]
        if 'FROM "golden_conversation_run"' in query:
            return self.golden_runs[:1]
        if 'FROM "learning_daily_metrics"' in query:
            return [{"avg_tqs": 65.0, "avg_kgs": 55.0, "handoff_rate": 0.12}]
        if 'FROM "canary_rollout_run"' in query and "WHERE \"status\" = 'ACTIVE'" in query:
            return [self.active_canary]
        if 'FROM "canary_rollout_run"' in query and "ORDER BY \"created_at\" DESC" in query:
            return [
                {
                    "canary_percent": 10,
                    "rollback_triggered": False,
                    "status": "ACTIVE",
                    "updated_at": "2026-02-20T00:00:00Z",
                }
            ]
        if 'FROM "release_component_version"' in query:
            return [
                {
                    "component_key": "wrqs_config",
                    "version_hash": "wrqs-hash",
                    "version_label": "wrqs-v2",
                    "status": "CANARY",
                    "canary_percent": 10,
                    "updated_at": "2026-02-20T00:00:00Z",
                }
            ]
        return []

    async def execute_raw(self, query, *args):
        self.executed.append((query, args))
        return SimpleNamespace()


class FakeSettings:
    QDRANT_COLLECTION_NAME = "fashion_docs"
    RELEASE_GOLDEN_MIN_PASS_RATE = 0.95
    RELEASE_ROLLBACK_MAX_KGS_DELTA = 8.0
    RELEASE_ROLLBACK_MAX_HANDOFF_RATE = 0.15


@pytest.mark.asyncio
async def test_snapshot_component_versions_records_hashes() -> None:
    prisma = FakePrisma()
    snapshot = await release_control_service.snapshot_component_versions(
        prisma,
        settings=FakeSettings(),
        status="STABLE",
        canary_percent=0,
    )
    assert "policy_prompt" in snapshot
    assert "wrqs_config" in snapshot
    assert any('INSERT INTO "release_component_version"' in q for q, _ in prisma.executed)


@pytest.mark.asyncio
async def test_run_golden_gate_returns_pass_result() -> None:
    prisma = FakePrisma()
    result = await release_control_service.run_golden_gate(
        prisma,
        triggered_by_user_id=1,
        min_pass_rate=0.95,
        run_window_days=7,
    )
    assert result["status"] == "PASS"
    assert result["pass_rate"] >= 0.95
    assert any('INSERT INTO "golden_conversation_run"' in q for q, _ in prisma.executed)


@pytest.mark.asyncio
async def test_canary_start_and_rollback_flow() -> None:
    prisma = FakePrisma()
    started = await release_control_service.start_canary_rollout(
        prisma,
        settings=FakeSettings(),
        triggered_by_user_id=1,
        canary_percent=10,
    )
    assert started["started"] is True
    assert any('INSERT INTO "canary_rollout_run"' in q for q, _ in prisma.executed)

    # Force rollback trigger by worsening KPI delta beyond threshold.
    async def high_kgs_metrics(_prisma, *, days):
        del _prisma, days
        return {"avg_tqs": 60.0, "avg_kgs": 60.0, "handoff_rate": 0.22}

    original = release_control_service._metrics_window
    release_control_service._metrics_window = high_kgs_metrics
    try:
        rolled = await release_control_service.evaluate_canary_and_maybe_rollback(
            prisma,
            settings=FakeSettings(),
            notes="rollback-test",
        )
    finally:
        release_control_service._metrics_window = original

    assert rolled["rolled_back"] is True
    assert any('UPDATE "release_component_version"' in q for q, _ in prisma.executed)
