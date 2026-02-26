"""LangGraph state schema for the agent orchestrator."""

from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph import MessagesState, add_messages


class AgentState(MessagesState):
    """Extends MessagesState with agent-specific fields."""

    intent: Optional[Literal["sql", "rag", "hybrid"]] = None
    context: Optional[list] = None  # retrieved documents for RAG
    sql_result: Optional[str] = None
    rag_result: Optional[str] = None
    user_state: Optional[Literal["GUEST", "REGISTERED"]] = None
    roles: Optional[list[str]] = None
    consent_flags: Optional[dict[str, bool]] = None
    active_order_id: Optional[str] = None
    active_design_id: Optional[str] = None
    user_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    trace_request_id: Optional[str] = None
    trace_created_at: Optional[datetime] = None
    debug_trace: Optional[dict[str, Any]] = None
    policy_allow: Optional[bool] = None
    policy_intent: Optional[str] = None
    policy_domain: Optional[str] = None
    policy_confidence: Optional[float] = None
    policy_reason_code: Optional[str] = None
    policy_refusal_text: Optional[str] = None
    policy_decision_source: Optional[str] = None
    candidate_set: Optional[list[dict[str, Any]]] = None
    candidate_scores: Optional[list[dict[str, Any]]] = None
    selected_candidate_id: Optional[str] = None
    learning_turn_index: Optional[int] = None
    clarify_mode: Optional[bool] = None
    rag_top_k_override: Optional[int] = None
    query_expansion_enabled: Optional[bool] = None
    wrqs_weight_overrides: Optional[dict[str, dict[str, float]]] = None
    release_wrqs_weights: Optional[dict[str, dict[str, float]]] = None
    short_answer_pref: Optional[bool] = None
    lang_pref: Optional[str] = None
    correction_hints: Optional[list[str]] = None
    sql_memory: Optional[dict[str, Any]] = None  # SQL query memory for conversation context
