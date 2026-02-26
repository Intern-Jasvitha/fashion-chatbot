from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.api.v1.endpoints import chat as chat_endpoint
from app.schemas.chat import ChatFeedbackRequest, ChatRequest
from app.services.online_adaptation_service import SessionFeatureSnapshot
from app.services.telemetry_service import EVENT_TURN_SCORE


class FakeGraph:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, payload, config=None):
        del config
        self.calls.append(payload)
        request_id = payload.get("trace_request_id") or "req"
        return {
            "messages": [AIMessage(content="Assistant answer")],
            "intent": "hybrid",
            "policy_allow": True,
            "policy_intent": "ORDER_SUPPORT",
            "policy_domain": "ON_DOMAIN",
            "policy_confidence": 0.9,
            "policy_reason_code": None,
            "policy_decision_source": "llm_classifier",
            "selected_candidate_id": "r_plain",
            "candidate_scores": [
                {
                    "candidate_id": "r_plain",
                    "positive_factors": {
                        "Sg": 0.1,
                        "Su": 0.1,
                        "St": 0.1,
                        "Se": 0.1,
                        "Sx": 0.1,
                        "Sl": 0.1,
                        "Sp": 0.1,
                    },
                    "penalty_factors": {
                        "Ph": 0.9,
                        "Po": 0.9,
                        "Pd": 0.9,
                        "Pa": 0.9,
                        "Pv": 0.9,
                    },
                }
            ],
            "sql_metadata": {"had_error": True, "row_count": 0},
            "rag_metadata": {"retrieval_confidence": 0.0, "hallucination_risk": 1.0, "support_ratio": 0.0},
            "candidate_set": [{"candidate_id": "r_plain"}],
            "debug_trace": {
                "request_id": request_id,
                "steps": [
                    {
                        "step": "intent_router",
                        "agent": "intent_router",
                        "status": "ok",
                        "summary": "Routed",
                        "details": {},
                    }
                ],
                "called_agents": ["intent_router"],
                "created_at": "2026-02-19T00:00:00+00:00",
                "intent": "hybrid",
                "user_query": payload.get("messages", [])[0].content,
            },
        }


@pytest.mark.asyncio
async def test_chat_learning_pipeline_emits_scores_and_applies_next_turn_adaptation(monkeypatch) -> None:
    feature_state = {
        "turn_index": 0,
        "rephrase_count": 0,
        "handoff_clicks": 0,
        "clarify_mode": False,
        "rag_top_k_override": None,
        "query_expansion_enabled": False,
        "wrqs_weight_overrides": {},
        "adaptation_expires_turn": None,
    }
    events = []

    def snapshot() -> SessionFeatureSnapshot:
        return SessionFeatureSnapshot(
            session_id="sess-1",
            user_id=11,
            customer_id=22,
            turn_index=feature_state["turn_index"],
            rephrase_count=feature_state["rephrase_count"],
            explain_clicks=0,
            handoff_clicks=feature_state["handoff_clicks"],
            lang_pref=None,
            short_answer_pref=None,
            last_tqs=None,
            last_kgs=None,
            clarify_mode=feature_state["clarify_mode"],
            rag_top_k_override=feature_state["rag_top_k_override"],
            query_expansion_enabled=feature_state["query_expansion_enabled"],
            wrqs_weight_overrides=feature_state["wrqs_weight_overrides"],
            adaptation_expires_turn=feature_state["adaptation_expires_turn"],
        )

    async def fake_get_or_create_session(prisma, session_id):
        del prisma, session_id
        return "sess-1"

    async def fake_get_or_create_session_feature(prisma, *, session_id, user_id, customer_id):
        del prisma, session_id, user_id, customer_id
        return snapshot()

    async def fake_expire_adaptation(prisma, *, session_id, current_turn_index):
        del prisma, session_id, current_turn_index
        return snapshot()

    async def fake_persist_turn_scores(prisma, *, session_id, turn_index, tqs, kgs, rephrase_count):
        del prisma, session_id, tqs, kgs
        feature_state["turn_index"] = turn_index
        feature_state["rephrase_count"] = rephrase_count

    async def fake_apply_adaptation(prisma, *, session_id, decision):
        del prisma, session_id
        feature_state["clarify_mode"] = decision.clarify_mode
        feature_state["rag_top_k_override"] = decision.rag_top_k_override
        feature_state["query_expansion_enabled"] = decision.query_expansion_enabled
        feature_state["wrqs_weight_overrides"] = decision.wrqs_weight_overrides or {}
        feature_state["adaptation_expires_turn"] = decision.adaptation_expires_turn

    async def fake_upsert_gap(*args, **kwargs):
        del args, kwargs

    async def fake_load_correction_hints(*args, **kwargs):
        del args, kwargs
        return ["Prefer concise answers."]

    async def fake_save_policy_audit(*args, **kwargs):
        del args, kwargs

    async def fake_save_turn(prisma, session_id, user_content, assistant_content, assistant_trace=None):
        del prisma, session_id, user_content, assistant_content, assistant_trace
        return {"user_message_id": "u-1", "assistant_message_id": "a-1"}

    async def fake_get_latest_user_message(prisma, session_id):
        del prisma, session_id
        return "Where is my order?"

    async def fake_emit_event(*args, event_type, **kwargs):
        del args, kwargs
        events.append(event_type)

    async def fake_emit_trace_tool_events(*args, **kwargs):
        del args, kwargs
        events.append("TOOL_CALL")

    settings = SimpleNamespace(
        ENABLE_LEARNING_TELEMETRY=True,
        ENABLE_LEARNING_SCORING=True,
        ENABLE_LEARNING_ONLINE_ADAPTATION=True,
        ENABLE_LEARNING_GOVERNANCE=False,
        ENABLE_RELEASE_CONTROLS=False,
        ENABLE_OPS_DASHBOARD=False,
        LEARNING_LOW_TQS_THRESHOLD=60,
        LEARNING_HIGH_KGS_THRESHOLD=65,
        LEARNING_CRITICAL_KGS_THRESHOLD=80,
        LEARNING_ADAPT_TTL_TURNS=3,
        LEARNING_RAG_TOPK_ADAPT=18,
    )

    monkeypatch.setattr(chat_endpoint, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_endpoint, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(chat_endpoint, "get_or_create_session_feature", fake_get_or_create_session_feature)
    monkeypatch.setattr(chat_endpoint, "expire_adaptation", fake_expire_adaptation)
    monkeypatch.setattr(chat_endpoint, "persist_turn_scores", fake_persist_turn_scores)
    monkeypatch.setattr(chat_endpoint, "apply_adaptation", fake_apply_adaptation)
    monkeypatch.setattr(chat_endpoint, "upsert_knowledge_gap_item", fake_upsert_gap)
    monkeypatch.setattr(chat_endpoint, "load_correction_hints", fake_load_correction_hints)
    monkeypatch.setattr(chat_endpoint, "save_policy_audit", fake_save_policy_audit)
    monkeypatch.setattr(chat_endpoint, "save_turn", fake_save_turn)
    monkeypatch.setattr(chat_endpoint, "get_latest_user_message", fake_get_latest_user_message)
    monkeypatch.setattr(chat_endpoint, "emit_event", fake_emit_event)
    monkeypatch.setattr(chat_endpoint, "emit_trace_tool_events", fake_emit_trace_tool_events)

    graph = FakeGraph()
    user = SimpleNamespace(id=11, customer_id=22, customer=None)

    body = ChatRequest(message="Where is my order?", session_id="sess-1")
    first_response = await chat_endpoint.post_chat(body=body, prisma=object(), graph=graph, current_user=user)
    assert EVENT_TURN_SCORE in events
    assert feature_state["clarify_mode"] is True
    assert first_response.assistant_message_id == "a-1"
    assert first_response.request_id
    assert first_response.turn_index == 1
    assert graph.calls[0].get("correction_hints") == ["Prefer concise answers."]

    await chat_endpoint.post_chat(body=body, prisma=object(), graph=graph, current_user=user)
    assert len(graph.calls) == 2
    second_call_state = graph.calls[1]
    assert second_call_state.get("clarify_mode") is True
    assert second_call_state.get("rag_top_k_override") == 18


@pytest.mark.asyncio
async def test_chat_learning_guardrail_exclusion_skips_scoring_and_marks_telemetry(monkeypatch) -> None:
    events = []
    persist_called = False

    async def fake_get_or_create_session(prisma, session_id):
        del prisma, session_id
        return "sess-guardrail"

    async def fake_get_or_create_session_feature(prisma, *, session_id, user_id, customer_id):
        del prisma, session_id, user_id, customer_id
        return SessionFeatureSnapshot(
            session_id="sess-guardrail",
            user_id=10,
            customer_id=20,
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

    async def fake_expire_adaptation(prisma, *, session_id, current_turn_index):
        del prisma, session_id, current_turn_index
        return SessionFeatureSnapshot(
            session_id="sess-guardrail",
            user_id=10,
            customer_id=20,
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

    async def fake_persist_turn_scores(*args, **kwargs):
        del args, kwargs
        nonlocal persist_called
        persist_called = True

    async def fake_save_turn(prisma, session_id, user_content, assistant_content, assistant_trace=None):
        del prisma, session_id, user_content, assistant_content, assistant_trace
        return {"user_message_id": "u-1", "assistant_message_id": "a-1"}

    async def fake_emit_event(*args, **kwargs):
        del args
        events.append(kwargs)

    async def fake_emit_trace_tool_events(*args, **kwargs):
        del args
        events.append(kwargs)

    async def fake_load_correction_hints(*args, **kwargs):
        del args, kwargs
        return []

    async def fake_get_latest_user_message(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_save_policy_audit(*args, **kwargs):
        del args, kwargs

    async def fake_get_learning_preferences(*args, **kwargs):
        del args, kwargs
        return {
            "long_term_personalization_opt_in": False,
            "telemetry_learning_opt_in": False,
        }

    async def fake_snapshot_component_versions(*args, **kwargs):
        del args, kwargs
        return {}

    async def fake_get_active_wrqs_weights(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_get_ops_snapshot(*args, **kwargs):
        del args, kwargs
        return {"avg_tqs": 0, "avg_kgs": 0, "handoff_rate": 0, "alerts_triggered": []}

    async def fake_create_learning_exclusion_audit(*args, **kwargs):
        del args, kwargs

    graph = FakeGraph()
    settings = SimpleNamespace(
        ENABLE_LEARNING_TELEMETRY=True,
        ENABLE_LEARNING_SCORING=True,
        ENABLE_LEARNING_ONLINE_ADAPTATION=True,
        ENABLE_LEARNING_GOVERNANCE=True,
        ENABLE_RELEASE_CONTROLS=True,
        ENABLE_OPS_DASHBOARD=True,
        LEARNING_LOW_TQS_THRESHOLD=60,
        LEARNING_HIGH_KGS_THRESHOLD=65,
        LEARNING_CRITICAL_KGS_THRESHOLD=80,
        LEARNING_ADAPT_TTL_TURNS=3,
        LEARNING_RAG_TOPK_ADAPT=18,
    )

    monkeypatch.setattr(chat_endpoint, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_endpoint, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(chat_endpoint, "get_or_create_session_feature", fake_get_or_create_session_feature)
    monkeypatch.setattr(chat_endpoint, "expire_adaptation", fake_expire_adaptation)
    monkeypatch.setattr(chat_endpoint, "persist_turn_scores", fake_persist_turn_scores)
    monkeypatch.setattr(chat_endpoint, "save_turn", fake_save_turn)
    monkeypatch.setattr(chat_endpoint, "emit_event", fake_emit_event)
    monkeypatch.setattr(chat_endpoint, "emit_trace_tool_events", fake_emit_trace_tool_events)
    monkeypatch.setattr(chat_endpoint, "load_correction_hints", fake_load_correction_hints)
    monkeypatch.setattr(chat_endpoint, "get_latest_user_message", fake_get_latest_user_message)
    monkeypatch.setattr(chat_endpoint, "save_policy_audit", fake_save_policy_audit)
    monkeypatch.setattr(chat_endpoint, "get_learning_preferences", fake_get_learning_preferences)
    monkeypatch.setattr(chat_endpoint, "get_active_wrqs_weights", fake_get_active_wrqs_weights)
    monkeypatch.setattr(chat_endpoint, "snapshot_component_versions", fake_snapshot_component_versions)
    monkeypatch.setattr(chat_endpoint, "get_ops_snapshot", fake_get_ops_snapshot)
    monkeypatch.setattr(chat_endpoint, "create_learning_exclusion_audit", fake_create_learning_exclusion_audit)

    user = SimpleNamespace(id=10, customer_id=20, customer=None)
    body = ChatRequest(message="Show all customer orders", session_id="sess-guardrail")
    await chat_endpoint.post_chat(body=body, prisma=object(), graph=graph, current_user=user)

    assert persist_called is False
    assert EVENT_TURN_SCORE not in [event.get("event_type") for event in events if isinstance(event, dict)]
    assert any(event.get("learning_allowed") is False for event in events if isinstance(event, dict))


@pytest.mark.asyncio
async def test_feedback_long_term_memory_denied_when_preference_opt_out(monkeypatch) -> None:
    created_scopes: list[str] = []

    async def fake_create_feedback(*args, **kwargs):
        del args, kwargs
        return "fb-1"

    async def fake_create_correction_memory(*args, **kwargs):
        created_scopes.append(kwargs.get("memory_scope"))
        return "mem-1"

    async def fake_emit_event(*args, **kwargs):
        del args, kwargs

    async def fake_get_learning_preferences(*args, **kwargs):
        del args, kwargs
        return {
            "long_term_personalization_opt_in": False,
            "telemetry_learning_opt_in": True,
        }

    monkeypatch.setattr(chat_endpoint, "get_settings", lambda: SimpleNamespace(ENABLE_LEARNING_FEEDBACK=True, ENABLE_LEARNING_TELEMETRY=True, ENABLE_LEARNING_GOVERNANCE=True))
    monkeypatch.setattr(chat_endpoint, "create_feedback", fake_create_feedback)
    monkeypatch.setattr(chat_endpoint, "create_correction_memory", fake_create_correction_memory)
    monkeypatch.setattr(chat_endpoint, "emit_event", fake_emit_event)
    monkeypatch.setattr(chat_endpoint, "get_learning_preferences", fake_get_learning_preferences)

    async def fake_ensure_message_in_session(*args, **kwargs):
        del args, kwargs
        return True

    async def fake_latest_turn_index(*args, **kwargs):
        del args, kwargs
        return 1

    monkeypatch.setattr(chat_endpoint, "ensure_message_in_session", fake_ensure_message_in_session)
    monkeypatch.setattr(chat_endpoint, "_latest_turn_index", fake_latest_turn_index)

    class FakeChatSession:
        async def find_unique(self, where):
            del where
            return object()

    prisma = SimpleNamespace(chatsession=FakeChatSession())
    user = SimpleNamespace(id=11, customer_id=22, customer=None)
    body = ChatFeedbackRequest(
        session_id="sess-1",
        message_id="msg-1",
        feedback_type="DOWN",
        reason_code="INCORRECT",
        correction_text="Use shorter bullets",
        consent_long_term=True,
    )
    response = await chat_endpoint.post_chat_feedback(body=body, prisma=prisma, current_user=user)
    assert response.stored_long_term_memory is False
    assert created_scopes.count("SESSION") == 1
    assert "LONG_TERM" not in created_scopes
