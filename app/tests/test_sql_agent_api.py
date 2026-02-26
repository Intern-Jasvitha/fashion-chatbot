"""Tests for SQL Agent API endpoint and schema RAG."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.auth import CustomerOut, UserOut


def _user_with_customer(customer_id: int = 1, user_id: int = 1) -> UserOut:
    return UserOut(
        id=user_id,
        email="test@example.com",
        name="Test User",
        customer_id=customer_id,
        customer=CustomerOut(
            id=customer_id,
            firstname="Test",
            lastname="User",
            email="test@example.com",
            phoneno=None,
        ),
    )


def _user_without_customer(user_id: int = 1) -> UserOut:
    return UserOut(
        id=user_id,
        email="test@example.com",
        name="Test User",
        customer_id=None,
        customer=None,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.asyncio
async def test_sql_agent_requires_auth(client: TestClient) -> None:
    """POST /api/v1/sql-agent without Bearer token returns 401."""
    response = client.post(
        "/api/v1/sql-agent",
        json={"message": "How many orders do I have?"},
    )
    assert response.status_code == 401


def test_sql_agent_request_response_schema() -> None:
    """SQLAgentRequest and SQLAgentResponse have expected fields."""
    from app.schemas.sql_agent import SQLAgentRequest, SQLAgentResponse

    req = SQLAgentRequest(message="Show my orders")
    assert req.message == "Show my orders"
    assert req.selected_customer_name is None

    resp = SQLAgentResponse(
        content="You have 3 orders.",
        sql="SELECT ...",
        plan={"base_table": "ticket"},
        metadata={"row_count": 3},
    )
    assert resp.content == "You have 3 orders."
    assert resp.sql == "SELECT ..."
    assert resp.metadata["row_count"] == 3


@pytest.mark.asyncio
async def test_schema_rag_fallback_without_collection() -> None:
    """When sql-agent collection is missing, retrieve_schema_context returns full schema."""
    from unittest.mock import MagicMock

    from app.core.config import get_settings
    from app.services.schema_rag import retrieve_schema_context

    settings = get_settings()
    mock_qdrant = MagicMock()
    mock_qdrant.get_collections.return_value.collections = []  # no sql-agent collection

    context = await retrieve_schema_context("how many orders", settings, mock_qdrant)
    assert "ticket" in context or "customer_id" in context
    assert len(context) > 100
