"""Chat request/response schemas."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

IntentLiteral = Literal["sql", "rag", "hybrid"]


class TraceStep(BaseModel):
    """One readable step in the agent execution trace."""

    step: str = Field(..., description="Stable step key")
    agent: str = Field(..., description="Agent or component name")
    status: str = Field(..., description="Step status: ok, error, info")
    summary: str = Field(..., description="Human-readable summary")
    duration_ms: Optional[int] = Field(None, description="Step execution time in milliseconds")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured metadata for debugging")


class DebugTrace(BaseModel):
    """Structured trace for a single chat request."""

    request_id: str = Field(..., description="Per-request trace identifier")
    user_query: str = Field(..., description="Original user query for this request")
    intent: Optional[IntentLiteral] = Field(None, description="Final routed intent for this request")
    called_agents: list[str] = Field(default_factory=list, description="Agents called during execution")
    steps: list[TraceStep] = Field(default_factory=list, description="Ordered execution timeline")
    created_at: datetime = Field(..., description="Trace creation time (UTC)")


class ChatMessageOut(BaseModel):
    """Single message in history response."""

    id: str = Field(..., description="Message id")
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message content")
    created_at: datetime = Field(..., description="When the message was created")
    feedback_type: Optional[Literal["UP", "DOWN"]] = Field(
        None,
        description="Latest feedback for this assistant message by current user.",
    )


class ChatHistoryResponse(BaseModel):
    """Full conversation history for a session."""

    messages: list[ChatMessageOut] = Field(..., description="All messages in order")
    latest_trace: Optional[DebugTrace] = Field(None, description="Latest assistant trace in this session")


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str = Field(..., min_length=1, description="User message")
    session_id: Optional[str] = Field(None, description="Optional session id for conversation memory; omit to start a new session")
    selected_customer_name: Optional[str] = Field(
        None,
        description="Optional customer full name to scope responses when no customer is linked to the login.",
    )
    language: Optional[str] = Field(
        None,
        description="ISO 639-1 language code (en, hi, bn, mr, te) for LLM response language.",
    )


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    content: str = Field(..., description="Assistant reply (natural language)")
    intent: IntentLiteral = Field(..., description="Detected intent: sql, rag, or hybrid")
    session_id: str = Field(..., description="Session id for this conversation; send on follow-up requests")
    assistant_message_id: Optional[str] = Field(
        None,
        description="Persisted assistant message id; null for guest mode.",
    )
    request_id: str = Field(..., description="Per-request trace identifier")
    turn_index: int = Field(..., description="1-based turn index for learning/telemetry")
    debug_trace: Optional[DebugTrace] = Field(None, description="Structured execution trace for this request")


class ChatFeedbackRequest(BaseModel):
    """Request body for explicit feedback submission."""

    session_id: str = Field(..., description="Chat session id")
    message_id: str = Field(..., description="Assistant message id being rated")
    feedback_type: Literal["UP", "DOWN"] = Field(..., description="Thumbs up/down feedback")
    reason_code: Optional[str] = Field(None, description="Optional structured feedback reason code")
    correction_text: Optional[str] = Field(
        None,
        description="Optional correction that should influence future responses",
    )
    consent_long_term: bool = Field(
        False,
        description="When true and correction_text is present, save correction for long-term memory.",
    )


class ChatFeedbackResponse(BaseModel):
    """Feedback submission response."""

    feedback_id: str = Field(..., description="Persisted feedback id")
    applied_session_memory: bool = Field(..., description="Whether session correction memory was saved")
    stored_long_term_memory: bool = Field(..., description="Whether long-term correction memory was saved")


class ChatHandoffRequest(BaseModel):
    """Request body for human handoff enqueue."""

    session_id: str = Field(..., description="Chat session id")
    message_id: str = Field(..., description="Assistant message id that triggered handoff")
    reason_code: str = Field(..., description="Reason code for escalation")
    notes: Optional[str] = Field(None, description="Optional free-form notes from user")


class ChatHandoffResponse(BaseModel):
    """Handoff enqueue response."""

    handoff_id: str = Field(..., description="Created handoff queue id")
    status: str = Field(..., description="Initial handoff status")


class LearningPreferencesOut(BaseModel):
    """User-level learning consent preferences."""

    long_term_personalization_opt_in: bool = Field(..., description="Allow long-term personalization memory")
    telemetry_learning_opt_in: bool = Field(..., description="Allow non-identifying learning telemetry")


class LearningPreferencesUpdateRequest(BaseModel):
    """Update payload for learning preferences."""

    long_term_personalization_opt_in: Optional[bool] = Field(
        None,
        description="Set long-term personalization consent.",
    )
    telemetry_learning_opt_in: Optional[bool] = Field(
        None,
        description="Set learning telemetry consent.",
    )


class OpsDashboardResponse(BaseModel):
    """Operational KPI and alert summary."""

    window: dict[str, Any]
    summary: dict[str, Any]
    avg_tqs_by_intent: list[dict[str, Any]]
    top_kgs_topics: list[dict[str, Any]]
    alerts: dict[str, Any]


class ReleaseStatusResponse(BaseModel):
    """Release snapshot for governance debug tooling."""

    components: list[dict[str, Any]]
    latest_golden_run: Optional[dict[str, Any]]
    latest_canary_run: Optional[dict[str, Any]]


class GoldenRunResponse(BaseModel):
    """Golden gate execution summary."""

    status: str
    pass_rate: float
    min_required_pass_rate: float
    total_cases: int
    passed_cases: int
    failures: list[dict[str, Any]]


class CanaryStartRequest(BaseModel):
    """Manual canary start request."""

    canary_percent: Optional[int] = Field(None, description="Optional canary percent override.")
    experiment_dimension: Optional[str] = Field(
        None,
        description="Requested experiment dimension. Only WRQS/response-style dimensions are allowed.",
    )


class CanaryStartResponse(BaseModel):
    """Canary start response."""

    started: bool
    reason: Optional[str] = None
    canary_percent: Optional[int] = None
    baseline_metrics: Optional[dict[str, Any]] = None


class CanaryRollbackRequest(BaseModel):
    """Manual rollback check request."""

    notes: Optional[str] = Field(None, description="Optional operator note for rollback evaluation.")


class CanaryRollbackResponse(BaseModel):
    """Rollback evaluation response."""

    rolled_back: bool
    status: Optional[str] = None
    reason: Optional[str] = None
    kgs_delta: Optional[float] = None
    handoff_rate: Optional[float] = None
    thresholds: Optional[dict[str, Any]] = None
