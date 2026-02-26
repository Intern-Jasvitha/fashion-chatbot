"""SQL Agent API request/response schemas."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class SQLAgentRequest(BaseModel):
    """Request body for POST /api/v1/sql-agent."""

    message: str = Field(..., description="Natural language question to answer with SQL")
    selected_customer_name: Optional[str] = Field(
        None,
        description="Optional customer name to scope the query (for multi-customer users)",
    )


class SQLAgentResponse(BaseModel):
    """Response from POST /api/v1/sql-agent."""

    content: str = Field(..., description="Natural language answer to the user's question")
    sql: Optional[str] = Field(None, description="Executed SQL query (if successful)")
    plan: Optional[dict[str, Any]] = Field(None, description="Structured query plan used to build the SQL")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metadata: row_count, execution_time_ms, total_time_ms, error (if any)",
    )
