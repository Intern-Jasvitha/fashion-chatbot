"""Intent router request/response schemas and agent intent enum."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    """Detected agent type for routing."""

    SQL_AGENT = "sql"
    RAG_AGENT = "rag"
    HYBRID_AGENT = "hybrid"


IntentLiteral = Literal["sql", "rag", "hybrid"]


class IntentRequest(BaseModel):
    """Request body for intent detection."""

    message: str = Field(..., min_length=1, description="User message to classify")


class IntentResponse(BaseModel):
    """Response with detected intent (which agent to call)."""

    intent: IntentLiteral = Field(..., description="Detected agent: sql, rag, or hybrid")
