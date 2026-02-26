import pytest

from app.services.ops_dashboard_service import get_ops_dashboard


class FakePrisma:
    async def query_raw(self, query, *args):
        del args
        if 'GROUP BY 1' in query and 'FROM "chat_event_log"' in query:
            return [{"intent": "hybrid", "avg_tqs": 62.0, "avg_kgs": 71.0, "turns": 5}]
        if 'FROM "knowledge_gap_items"' in query:
            return [{"topic_key": "hybrid::abc", "intent": "hybrid", "score": 82, "occurrence_count": 4, "status": "IN_REVIEW"}]
        if 'AVG(("payload_json"::jsonb ->> \'tqs\')::float)' in query:
            return [{"avg_tqs": 62.0, "avg_kgs": 71.0, "rephrase_rate": 0.25, "handoff_rate": 0.2}]
        if 'FROM "policy_audit"' in query:
            return [{"blocked_count": 2, "total_count": 10}]
        if 'FROM "chat_message"' in query:
            return [{"assistant_count": 9, "user_count": 10}]
        if 'FROM "learning_exclusion_audit"' in query:
            return [{"cnt": 1}]
        if 'FROM "chat_event_log"' in query and 'event_type" = \'TOOL_CALL\'' in query:
            return [{"sql_error_steps": 3, "sql_total_steps": 10}]
        return []


@pytest.mark.asyncio
async def test_get_ops_dashboard_aggregates_kpis_and_alerts() -> None:
    prisma = FakePrisma()
    payload = await get_ops_dashboard(prisma, days=7)
    assert payload["summary"]["avg_tqs"] == 62.0
    assert payload["summary"]["avg_kgs"] == 71.0
    assert payload["alerts"]["disclosure_risk"]["triggered"] is True
    assert payload["alerts"]["sql_anomaly"]["triggered"] is True
    assert payload["alerts"]["handoff_spike"]["triggered"] is True
