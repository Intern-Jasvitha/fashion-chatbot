from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.graph import nodes


@pytest.mark.asyncio
async def test_hybrid_node_selects_candidate_and_emits_trace(monkeypatch) -> None:
    async def fake_sql_node(state, *, settings):
        del state, settings
        return {
            "sql_result": "Your latest order is shipped.",
            "sql_metadata": {"had_error": False, "row_count": 1},
            "debug_trace": {"steps": []},
        }

    async def fake_rag_node(state, *, settings, qdrant_client):
        del state, settings, qdrant_client
        return {
            "rag_result": "Shipping usually takes 3-5 days.",
            "rag_metadata": {
                "retrieval_confidence": 0.9,
                "support_ratio": 0.9,
                "hallucination_risk": 0.1,
            },
            "debug_trace": {"steps": []},
        }

    async def fake_chat(messages, url):
        del messages, url
        return "Please check your order timeline in account."

    monkeypatch.setattr(nodes, "sql_node", fake_sql_node)
    monkeypatch.setattr(nodes, "rag_node", fake_rag_node)
    monkeypatch.setattr(nodes, "chat", fake_chat)

    settings = SimpleNamespace(
        LLAMA_URL="http://example.local/chat",
        ENABLE_PHASE5_CANDIDATES=True,
        ENABLE_PHASE6_WRQS=True,
    )
    state = {
        "messages": [HumanMessage(content="Where is my order?")],
        "user_state": "REGISTERED",
        "policy_allow": True,
        "policy_intent": "ORDER_SUPPORT",
        "customer_id": 1,
        "user_id": 1,
        "trace_request_id": "test-req",
        "debug_trace": {"request_id": "test-req", "steps": [], "called_agents": []},
    }
    out = await nodes.hybrid_node(state, settings=settings, qdrant_client=object())
    assert out["selected_candidate_id"] in {"r_sql", "r_rag", "r_plain", "r_guided"}
    assert isinstance(out["candidate_set"], list)
    assert isinstance(out["candidate_scores"], list)
    assert out["messages"]


@pytest.mark.asyncio
async def test_hybrid_applies_wrqs_overrides_from_state(monkeypatch) -> None:
    async def fake_sql_node(state, *, settings):
        del state, settings
        return {
            "sql_result": "SQL answer.",
            "sql_metadata": {"had_error": False, "row_count": 1},
            "debug_trace": {"steps": []},
        }

    async def fake_rag_node(state, *, settings, qdrant_client):
        del state, settings, qdrant_client
        return {
            "rag_result": "RAG answer.",
            "rag_metadata": {
                "retrieval_confidence": 0.8,
                "support_ratio": 0.8,
                "hallucination_risk": 0.2,
            },
            "debug_trace": {"steps": []},
        }

    async def fake_chat(messages, url):
        del messages, url
        return "plain answer"

    monkeypatch.setattr(nodes, "sql_node", fake_sql_node)
    monkeypatch.setattr(nodes, "rag_node", fake_rag_node)
    monkeypatch.setattr(nodes, "chat", fake_chat)

    settings = SimpleNamespace(
        LLAMA_URL="http://example.local/chat",
        ENABLE_PHASE5_CANDIDATES=True,
        ENABLE_PHASE6_WRQS=True,
    )
    state = {
        "messages": [HumanMessage(content="Where is my order?")],
        "user_state": "REGISTERED",
        "policy_allow": True,
        "policy_intent": "ORDER_SUPPORT",
        "customer_id": 1,
        "user_id": 1,
        "wrqs_weight_overrides": {"positive": {"Sg": 0.5}, "penalty": {"Ph": 0.1}},
        "trace_request_id": "test-req-override",
        "debug_trace": {"request_id": "test-req-override", "steps": [], "called_agents": []},
    }
    out = await nodes.hybrid_node(state, settings=settings, qdrant_client=object())
    trace_steps = out["debug_trace"]["steps"]
    assert any(step.get("step") == "hybrid_wrqs_override" for step in trace_steps)


@pytest.mark.asyncio
async def test_rag_node_uses_adapted_top_k_and_query_expansion(monkeypatch) -> None:
    captured = {"embed_input": None, "limit": None}

    async def fake_embed_query(url, text):
        del url
        captured["embed_input"] = text
        return [0.1, 0.2, 0.3]

    async def fake_chat(messages, url):
        del messages, url
        return "Generated answer."

    class FakePoint:
        def __init__(self, score: float, idx: str) -> None:
            self.score = score
            self.payload = {"chunk_id": f"c-{idx}", "doc_id": f"d-{idx}", "content": f"doc {idx}"}

    class FakeQdrant:
        def query_points(self, *, collection_name, query, limit, with_payload):
            del collection_name, query, with_payload
            captured["limit"] = limit
            return SimpleNamespace(points=[FakePoint(0.91, "1"), FakePoint(0.81, "2"), FakePoint(0.77, "3"), FakePoint(0.7, "4")])

    monkeypatch.setattr(nodes, "embed_query", fake_embed_query)
    monkeypatch.setattr(nodes, "chat", fake_chat)

    settings = SimpleNamespace(
        EMBEDDING_URL="http://example.local/embed",
        QDRANT_COLLECTION_NAME="test_collection",
        LLAMA_URL="http://example.local/chat",
        ENABLE_PHASE4_RAG_GROUNDING=False,
        LEARNING_RAG_TOPK_BASE=12,
    )
    state = {
        "messages": [HumanMessage(content="Help me choose fabric")],
        "trace_request_id": "test-rag-adapt",
        "debug_trace": {"request_id": "test-rag-adapt", "steps": [], "called_agents": []},
        "query_expansion_enabled": True,
        "rag_top_k_override": 18,
        "clarify_mode": True,
    }

    out = await nodes.rag_node(state, settings=settings, qdrant_client=FakeQdrant())
    assert captured["limit"] == 18
    assert "Related terms and alternatives" in str(captured["embed_input"])
    assert out["messages"]
