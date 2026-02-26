from datetime import date

import pytest

from app.services import offline_learning_jobs


class FakePrisma:
    def __init__(self) -> None:
        self.executed = []

    async def query_raw(self, query, *args):
        if 'FROM "chat_event_log"' in query:
            return [
                {
                    "avg_tqs": 72.5,
                    "avg_kgs": 41.2,
                    "rephrase_rate": 0.22,
                    "handoff_rate": 0.08,
                }
            ]
        if 'feedback_down_rate' in query and 'FROM "chat_feedback"' in query and 'GROUP BY 1' not in query:
            return [{"feedback_down_rate": 0.3}]
        if 'GROUP BY 1' in query and 'FROM "chat_feedback"' in query:
            return [{"reason_code": "INCORRECT", "cnt": 2}]
        if 'FROM "learning_daily_metrics"' in query:
            return [{"avg_tqs": 70.0, "avg_kgs": 68.0, "avg_feedback_down_rate": 0.28}]
        if 'MAX("version")' in query:
            return [{"next_version": 3}]
        if 'FROM "knowledge_gap_items"' in query and 'ORDER BY "score"' in query:
            return [{"topic_key": "feedback::incorrect", "last_session_id": "sess-10", "score": 82, "occurrence_count": 5}]
        return []

    async def execute_raw(self, query, *args):
        self.executed.append((query, args))


@pytest.mark.asyncio
async def test_run_daily_job_upserts_metrics_and_job_run() -> None:
    prisma = FakePrisma()
    summary = await offline_learning_jobs.run_daily_job(prisma, target_date=date(2026, 2, 20))

    assert summary["metric_date"] == "2026-02-20"
    assert summary["avg_tqs"] == 72.5
    assert summary["feedback_down_rate"] == 0.3
    assert any('INSERT INTO "learning_daily_metrics"' in q for q, _ in prisma.executed)
    assert any('INSERT INTO "learning_job_run"' in q for q, _ in prisma.executed)


@pytest.mark.asyncio
async def test_run_weekly_job_versions_wrqs_and_creates_review_hooks(monkeypatch) -> None:
    prisma = FakePrisma()

    class FakeSettings:
        LEARNING_WEEKLY_WRQS_MAX_DELTA = 0.05
        ENABLE_RELEASE_CONTROLS = True

    async def fake_snapshot_component_versions(*args, **kwargs):
        del args, kwargs
        return {"wrqs_config": {"version_hash": "hash"}}

    monkeypatch.setattr(offline_learning_jobs, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(offline_learning_jobs, "snapshot_component_versions", fake_snapshot_component_versions)
    summary = await offline_learning_jobs.run_weekly_job(prisma, window_end=date(2026, 2, 20))

    assert summary["wrqs_version"] == 3
    assert summary["review_hooks"] == 1
    assert summary["release_component_count"] == 1
    assert any('INSERT INTO "wrqs_config_version"' in q for q, _ in prisma.executed)
    assert any('INSERT INTO "handoff_queue"' in q for q, _ in prisma.executed)
    assert any('INSERT INTO "learning_job_run"' in q for q, _ in prisma.executed)
