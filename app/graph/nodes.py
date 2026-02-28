"""LangGraph nodes: policy gate, intent router, SQL agent, RAG agent, Hybrid agent."""

import asyncio
import json
import logging
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.core.embeddings import embed_query
from app.core.llm import chat
from app.graph.state import AgentState
from app.schemas.intent import AgentIntent
from app.services.candidate_signals import candidate_signals
from app.services.candidate_framework import CandidateContext, build_candidate
from app.services.candidate_gate import gate_candidates
from app.services.intent_router import heuristic_override
from app.services.language_helper import get_language_instruction
from app.services.online_adaptation_service import apply_wrqs_overrides
from app.services.policy_agent import evaluate_policy_hard_gate
from app.services.policy_gate import UserState
from app.services.rag_grounding import (
    assess_claim_support,
    build_explainability_metadata,
    build_retrieval_metadata,
    is_recommendation_prompt,
    should_fallback_for_grounding,
)
from app.services.query_preprocessor import preprocess_query_for_sql
from app.services.schema_loader import load_schema_context
from app.services.sql_query_plan import (
    QueryPlanError,
    build_sql_from_plan,
    inject_mandatory_scope,
    parse_query_plan,
)
from app.services.sql_agent import run_sql_agent
from app.services.sql_validator import (
    SqlValidationError,
    enforce_customer_scope,
    run_sql_firewall,
    validate_and_prepare,
)
from app.services.wrqs_config import WRQSConfig, get_default_wrqs_config
from app.services.wrqs_scoring import score_candidate, select_best_candidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# INTENT ROUTER (reused from intent_router)
# ---------------------------------------------------------------------

_INTENT_MAP = {
    "SQL_AGENT": "sql",
    "RAG_AGENT": "rag",
    "HYBRID_AGENT": "hybrid",
    "SQL": "sql",
    "RAG": "rag",
    "HYBRID": "hybrid",
}

SYSTEM_PROMPT = """
You are a strict message router.

Decide which system should answer the user question.

SQL_AGENT:
ONLY if the user wants database rows, counts, numbers, reports, analytics.

RAG_AGENT:
Explanations, help, tutorials, advice, knowledge, policies.

MEMORY QUESTIONS:
Questions about previous conversation -> RAG_AGENT

HYBRID_AGENT:
Needs BOTH database info AND explanation.

Reply ONLY with:
SQL_AGENT
RAG_AGENT
HYBRID_AGENT
"""


def _last_user_message(state: AgentState) -> str:
    """Extract last user message content from state messages."""
    for m in reversed(state.get("messages", []) or []):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


def _history_from_messages(messages: list) -> list[dict[str, str]]:
    """Convert LangChain messages to role/content dicts for legacy chat()."""
    out: list[dict[str, str]] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            continue
        content = m.content if isinstance(m.content, str) else str(m.content)
        out.append({"role": role, "content": content})
    return out


def _correction_hint_message(state: AgentState) -> Optional[dict[str, str]]:
    raw_hints = state.get("correction_hints")
    if not isinstance(raw_hints, list):
        return None
    hints = [str(item).strip() for item in raw_hints if isinstance(item, str) and item.strip()]
    if not hints:
        return None
    condensed = hints[:5]
    guidance = "\n".join(f"- {item}" for item in condensed)
    return {
        "role": "system",
        "content": (
            "Apply these explicit user corrections/preferences from prior feedback when answering:\n"
            f"{guidance}"
        ),
    }


def _truncate_text(value: Any, max_len: int = 2000) -> str:
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_sql_for_log(sql: str, max_len: int = 4000) -> str:
    """Format SQL for readable logging (normalize whitespace, optional truncation)."""
    text = (" " if sql else "").join(s.strip() for s in (sql or "").split())
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_trace(state: AgentState, user_query: str) -> dict[str, Any]:
    existing = state.get("debug_trace") if isinstance(state, dict) else None
    request_id = state.get("trace_request_id") or "unknown"
    existing_request_id = existing.get("request_id") if isinstance(existing, dict) else None
    should_reuse_existing = isinstance(existing, dict) and existing_request_id == request_id
    trace: dict[str, Any] = deepcopy(existing) if should_reuse_existing else {}

    raw_created = trace.get("created_at")
    if not raw_created:
        state_created = state.get("trace_created_at")
        if isinstance(state_created, datetime):
            raw_created = state_created.astimezone(timezone.utc).isoformat()
        elif state_created:
            raw_created = str(state_created)
        else:
            raw_created = _now_iso()

    trace["request_id"] = request_id
    trace["user_query"] = user_query or trace.get("user_query") or ""
    trace["intent"] = state.get("intent") or trace.get("intent")
    trace["created_at"] = raw_created

    steps = trace.get("steps")
    trace["steps"] = steps if isinstance(steps, list) else []

    called = trace.get("called_agents")
    trace["called_agents"] = called if isinstance(called, list) else []
    return trace


def _set_trace_intent(trace: dict[str, Any], intent: str) -> None:
    trace["intent"] = intent


def _mark_called_agent(trace: dict[str, Any], agent: str) -> None:
    called: list[str] = trace["called_agents"]
    if agent not in called:
        called.append(agent)


def _append_step(
    trace: dict[str, Any],
    *,
    step: str,
    agent: str,
    status: str,
    summary: str,
    duration_ms: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    entry: dict[str, Any] = {
        "step": step,
        "agent": agent,
        "status": status,
        "summary": summary,
        "details": details or {},
    }
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    trace["steps"].append(entry)


def _agent_steps(trace: Optional[dict[str, Any]], agent: str) -> list[dict[str, Any]]:
    if not isinstance(trace, dict):
        return []
    steps = trace.get("steps") or []
    if not isinstance(steps, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in steps:
        if isinstance(item, dict) and item.get("agent") == agent:
            filtered.append(deepcopy(item))
    return filtered


# ---------------------------------------------------------------------
# NODES
# ---------------------------------------------------------------------


async def policy_gate_node(
    state: AgentState,
    *,
    settings: Settings,
) -> dict:
    """Phase 2 policy hard gate before intent routing and agent execution."""
    message = _last_user_message(state)
    trace = _ensure_trace(state, message)
    _mark_called_agent(trace, "policy_agent")

    user_state_token = (state.get("user_state") or UserState.GUEST.value).upper()
    user_state = UserState.REGISTERED if user_state_token == UserState.REGISTERED.value else UserState.GUEST

    decision_start = time.perf_counter()
    decision = await evaluate_policy_hard_gate(
        message=message,
        user_state=user_state,
        settings=settings,
    )
    decision_duration_ms = _duration_ms(decision_start)

    _append_step(
        trace,
        step="policy_rules",
        agent="policy_agent",
        status="error" if decision.decision_source == "rules_block" and not decision.allow else "ok",
        summary="Classified request using deterministic policy rules.",
        details={
            "rules_intent": decision.rules_intent.value,
            "rules_domain": decision.rules_domain.value,
            "fast_block": decision.decision_source == "rules_block",
        },
    )

    if decision.llm_skipped:
        _append_step(
            trace,
            step="policy_llm_classifier",
            agent="policy_agent",
            status="info",
            summary="Skipped LLM classifier due to deterministic rules block.",
            details={"decision_source": decision.decision_source},
        )
    else:
        llm_status = "ok" if decision.decision_source == "llm_classifier" else "error"
        llm_summary = (
            "LLM classifier returned policy classification."
            if decision.decision_source == "llm_classifier"
            else "LLM classifier failed validation; used deterministic fallback."
        )
        _append_step(
            trace,
            step="policy_llm_classifier",
            agent="policy_agent",
            status=llm_status,
            summary=llm_summary,
            details={
                "llm_intent": decision.llm_intent.value if decision.llm_intent else None,
                "llm_domain": decision.llm_domain.value if decision.llm_domain else None,
                "llm_confidence": decision.confidence,
                "llm_error": decision.llm_error,
                "llm_raw_response": _truncate_text(decision.llm_raw_response, 500)
                if decision.llm_raw_response
                else None,
            },
        )

    _append_step(
        trace,
        step="policy_hard_gate",
        agent="policy_agent",
        status="ok" if decision.allow else "error",
        summary="Policy hard gate allowed request." if decision.allow else "Policy hard gate blocked request.",
        duration_ms=decision_duration_ms,
        details={
            "user_state": user_state.value,
            "policy_intent": decision.intent.value,
            "policy_domain": decision.domain.value,
            "classifier_confidence": decision.confidence,
            "reason_code": decision.reason_code,
            "decision_source": decision.decision_source,
        },
    )

    result = {
        "policy_allow": decision.allow,
        "policy_intent": decision.intent.value,
        "policy_domain": decision.domain.value,
        "policy_confidence": decision.confidence,
        "policy_reason_code": decision.reason_code,
        "policy_refusal_text": decision.refusal_text,
        "policy_decision_source": decision.decision_source,
        "debug_trace": trace,
    }

    if not decision.allow:
        refusal = decision.refusal_text or "I can't help with that request."
        result["messages"] = [AIMessage(content=refusal)]
        result["intent"] = "rag"
    return result


async def intent_router_node(
    state: AgentState,
    *,
    settings: Settings,
) -> dict:
    """Detect intent and return routing update."""
    message = _last_user_message(state)
    trace = _ensure_trace(state, message)
    _mark_called_agent(trace, "intent_router")

    if not message:
        _set_trace_intent(trace, "hybrid")
        _append_step(
            trace,
            step="intent_router",
            agent="intent_router",
            status="info",
            summary="No user message found; defaulted route to hybrid.",
            details={"final_intent": "hybrid"},
        )
        return {"intent": "hybrid", "debug_trace": trace}

    user_state = (state.get("user_state") or "").upper()
    if user_state == "GUEST":
        _set_trace_intent(trace, "rag")
        _append_step(
            trace,
            step="intent_router_guest_guard",
            agent="intent_router",
            status="ok",
            summary="Forced guest request to rag agent path.",
            details={"user_state": user_state, "final_intent": "rag"},
        )
        return {"intent": "rag", "debug_trace": trace}

    messages_raw = state.get("messages", []) or []
    history = _history_from_messages(messages_raw[-6:]) if messages_raw else []

    if history:
        history_blob = "\n".join(f"{h['role']}: {h['content']}" for h in history)
        user_content = f"Recent conversation:\n{history_blob}\n\nCurrent message: {message}"
    else:
        user_content = message

    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_content}]

    llm_start = time.perf_counter()
    try:
        reply = await chat(msgs, settings.LLAMA_URL)
    except Exception as e:
        final = heuristic_override(message, AgentIntent.HYBRID_AGENT)
        _set_trace_intent(trace, final.value)
        _append_step(
            trace,
            step="intent_router",
            agent="intent_router",
            status="error",
            summary="Intent LLM failed; used heuristic fallback.",
            duration_ms=_duration_ms(llm_start),
            details={
                "error": _truncate_text(e, 500),
                "final_intent": final.value,
                "history_messages_used": len(history),
            },
        )
        logger.warning("LLM intent detection failed: %s", e)
        return {"intent": final.value, "debug_trace": trace}

    token = (reply or "").strip().upper().split("\n")[0].split()[0].strip(".,;:")
    raw_intent = _INTENT_MAP.get(token, "hybrid")
    intent_enum = AgentIntent.SQL_AGENT if raw_intent == "sql" else (
        AgentIntent.RAG_AGENT if raw_intent == "rag" else AgentIntent.HYBRID_AGENT
    )
    final = heuristic_override(message, intent_enum)
    _set_trace_intent(trace, final.value)
    _append_step(
        trace,
        step="intent_router",
        agent="intent_router",
        status="ok",
        summary=f"Routed request to {final.value} agent.",
        duration_ms=_duration_ms(llm_start),
        details={
            "raw_token": token,
            "raw_intent": raw_intent,
            "final_intent": final.value,
            "history_messages_used": len(history),
        },
    )
    logger.info("Intent detected | raw=%s | final=%s", token, final.value)
    return {"intent": final.value, "debug_trace": trace}


# ---------------------------------------------------------------------
# RAG NODE
# ---------------------------------------------------------------------

FINAL_K = 4

MEMORY_PATTERNS = [
    "what did i ask", "what did i say", "my last message", "previous message",
    "earlier i said", "summarize our conversation", "recall our conversation",
    "what was my question", "what did i ask first", "what did i just say",
]

CHAT_SYSTEM_PROMPT = """You are a friendly fashion and design assistant.

Speak naturally and conversationally. You remember the conversation.
Answer naturally like a human assistant.
Do NOT mention documents, sources, or database."""

MEMORY_SYSTEM_PROMPT = """You are a conversation assistant.

The user is asking about previous messages in the chat.
Answer ONLY using the conversation history provided. Do NOT invent anything.
If nothing exists, say you don't have earlier messages yet."""


def _build_context(results: list[Any]) -> str:
    texts = []
    for r in results:
        payload = r.payload or {}
        title = (payload.get("title") or "").strip()
        content = (payload.get("content") or "").strip()
        if title and title.lower() not in content.lower():
            texts.append(f"{title}. {content}")
        else:
            texts.append(content)
    return "\n\n".join(texts)


async def rag_node(
    state: AgentState,
    *,
    settings: Settings,
    qdrant_client: QdrantClient,
) -> dict:
    """RAG agent node: vector search or memory mode, then generate answer."""
    message = _last_user_message(state)
    logger.info("RAG | user: %s", message)

    trace = _ensure_trace(state, message)
    _mark_called_agent(trace, "rag_agent")

    # Note: Question-level blocking removed - SQL-level validation handles scoping

    history = _history_from_messages(state.get("messages", []) or [])
    correction_hint_msg = _correction_hint_message(state)
    lang_pref = state.get("lang_pref")
    lang_instruction = get_language_instruction(lang_pref)
    if correction_hint_msg:
        _append_step(
            trace,
            step="rag_correction_memory",
            agent="rag_agent",
            status="info",
            summary="Applied correction-memory hints to response generation.",
            details={"hint_count": len(state.get("correction_hints") or [])},
        )
    memory_mode = any(p in message.lower() for p in MEMORY_PATTERNS)
    query_expansion_enabled = bool(state.get("query_expansion_enabled"))
    clarify_mode = bool(state.get("clarify_mode"))
    configured_top_k = int(getattr(settings, "LEARNING_RAG_TOPK_BASE", 12))
    rag_top_k = int(state.get("rag_top_k_override") or configured_top_k)
    _append_step(
        trace,
        step="rag_mode",
        agent="rag_agent",
        status="info",
        summary="Selected RAG mode.",
        details={
            "mode": "memory" if memory_mode else "vector_search",
            "history_messages": len(history),
            "query_expansion_enabled": query_expansion_enabled,
            "clarify_mode": clarify_mode,
            "rag_top_k": rag_top_k,
        },
    )

    if memory_mode:
        logger.info("RAG MODE: conversation memory")
        if not history:
            answer = "We just started chatting — I don't have anything to recall yet."
            _append_step(
                trace,
                step="rag_memory_answer",
                agent="rag_agent",
                status="ok",
                summary="Memory question had no prior messages.",
                details={"history_messages": 0},
            )
            return {"messages": [AIMessage(content=answer)], "rag_result": answer, "debug_trace": trace}

        mem_start = time.perf_counter()
        msgs = [{"role": "system", "content": MEMORY_SYSTEM_PROMPT + lang_instruction}]
        if correction_hint_msg:
            msgs.append(correction_hint_msg)
        msgs.extend(history)
        msgs.append({"role": "user", "content": message})
        try:
            answer = (await chat(msgs, settings.LLAMA_URL)).strip()
            _append_step(
                trace,
                step="rag_memory_generation",
                agent="rag_agent",
                status="ok",
                summary="Generated answer from conversation memory.",
                duration_ms=_duration_ms(mem_start),
                details={"history_messages": len(history)},
            )
        except Exception as e:
            logger.warning("RAG memory LLM failed: %s", e)
            answer = "I couldn't recall our conversation. Please try again."
            _append_step(
                trace,
                step="rag_memory_generation",
                agent="rag_agent",
                status="error",
                summary="Memory answer generation failed.",
                duration_ms=_duration_ms(mem_start),
                details={"error": _truncate_text(e, 500)},
            )
        return {"messages": [AIMessage(content=answer)], "rag_result": answer, "debug_trace": trace}

    embed_query_text = message
    if query_expansion_enabled:
        embed_query_text = (
            f"{message}\n"
            "Related terms and alternatives: style options, product guidance, order details, clarifications."
        )
        _append_step(
            trace,
            step="rag_query_expansion",
            agent="rag_agent",
            status="info",
            summary="Expanded query text for retrieval.",
            details={"expanded": True},
        )

    embed_start = time.perf_counter()
    try:
        query_vector = await embed_query(settings.EMBEDDING_URL, embed_query_text)
        _append_step(
            trace,
            step="rag_embedding",
            agent="rag_agent",
            status="ok",
            summary="Generated query embedding.",
            duration_ms=_duration_ms(embed_start),
            details={"embedding_dim": len(query_vector)},
        )
    except Exception as e:
        logger.warning("RAG embedding failed: %s", e)
        answer = "I had trouble searching the knowledge base. Please try again."
        _append_step(
            trace,
            step="rag_embedding",
            agent="rag_agent",
            status="error",
            summary="Failed to generate query embedding.",
            duration_ms=_duration_ms(embed_start),
            details={"error": _truncate_text(e, 500)},
        )
        return {"messages": [AIMessage(content=answer)], "rag_result": answer, "debug_trace": trace}

    retrieve_start = time.perf_counter()
    try:
        response = qdrant_client.query_points(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            query=query_vector,
            limit=rag_top_k,
            with_payload=True,
        )
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)
        answer = "I couldn't search the document index. Please try again."
        _append_step(
            trace,
            step="rag_retrieval",
            agent="rag_agent",
            status="error",
            summary="Vector retrieval failed.",
            duration_ms=_duration_ms(retrieve_start),
            details={"error": _truncate_text(e, 500)},
        )
        return {"messages": [AIMessage(content=answer)], "rag_result": answer, "debug_trace": trace}

    points = list(response.points or [])
    _append_step(
        trace,
        step="rag_retrieval",
        agent="rag_agent",
        status="ok",
        summary=f"Retrieved {len(points)} candidate documents.",
        duration_ms=_duration_ms(retrieve_start),
        details={"retrieved_points": len(points), "top_k": rag_top_k},
    )

    if not points:
        answer = "Hmm — I couldn't find anything helpful. Could you rephrase?"
        return {"messages": [AIMessage(content=answer)], "rag_result": answer, "debug_trace": trace}

    scored = sorted(
        [p for p in points if p.score is not None],
        key=lambda x: x.score,
        reverse=True,
    )
    if not scored:
        answer = "I found documents but couldn't rank them confidently. Could you rephrase?"
        _append_step(
            trace,
            step="rag_scoring",
            agent="rag_agent",
            status="info",
            summary="Retrieved documents had no usable scores.",
            details={"retrieved_points": len(points)},
        )
        return {"messages": [AIMessage(content=answer)], "rag_result": answer, "debug_trace": trace}

    strong = scored[:FINAL_K]
    retrieval_meta = build_retrieval_metadata(strong)
    top_score = strong[0].score or 0.0
    _append_step(
        trace,
        step="rag_scoring",
        agent="rag_agent",
        status="ok",
        summary=f"Selected top {len(strong)} documents for context.",
        details={
            "final_k": len(strong),
            "top_score": round(float(top_score), 4),
            "chunk_ids": retrieval_meta.get("chunk_ids", []),
            "doc_ids": retrieval_meta.get("doc_ids", []),
            "raw_similarity_scores": retrieval_meta.get("raw_similarity_scores", []),
            "retrieval_confidence": retrieval_meta.get("retrieval_confidence", 0.0),
        },
    )

    if not settings.ISREMOVED_GATE:
        retrieval_threshold = 0.35
        if settings.ENABLE_PHASE4_RAG_GROUNDING:
            retrieval_threshold = get_default_wrqs_config().min_retrieval_confidence
        if clarify_mode:
            retrieval_threshold = min(0.90, retrieval_threshold + 0.10)
            _append_step(
                trace,
                step="rag_clarify_mode",
                agent="rag_agent",
                status="info",
                summary="Applied clarify-first threshold boost for low-quality recovery.",
                details={"retrieval_threshold": retrieval_threshold},
            )

        if top_score < retrieval_threshold:
            answer = "I want to make sure I understand — could you explain a bit more?"
            _append_step(
                trace,
                step="rag_quality_gate",
                agent="rag_agent",
                status="info",
                summary="Top retrieval score below confidence threshold.",
                details={"top_score": round(float(top_score), 4), "threshold": retrieval_threshold},
            )
            rag_metadata = {
                "retrieval_confidence": retrieval_meta.get("retrieval_confidence", 0.0),
                "support_ratio": 0.0,
                "hallucination_risk": 1.0,
                "grounding_fallback": True,
            }
            return {
                "messages": [AIMessage(content=answer)],
                "rag_result": answer,
                "rag_metadata": rag_metadata,
                "debug_trace": trace,
            }

    context = _build_context(strong)
    gen_start = time.perf_counter()
    msgs = [{"role": "system", "content": CHAT_SYSTEM_PROMPT + lang_instruction}]
    if correction_hint_msg:
        msgs.append(correction_hint_msg)
    msgs.extend(history)
    msgs.append({"role": "system", "content": f"Helpful background information:\n{context}"})
    msgs.append({"role": "user", "content": message})

    try:
        answer = (await chat(msgs, settings.LLAMA_URL)).strip()
        _append_step(
            trace,
            step="rag_generation",
            agent="rag_agent",
            status="ok",
            summary="Generated response from retrieved context.",
            duration_ms=_duration_ms(gen_start),
            details={"context_docs": len(strong)},
        )
    except Exception as e:
        logger.warning("RAG LLM failed: %s", e)
        answer = "I had trouble generating a response. Please try again."
        _append_step(
            trace,
            step="rag_generation",
            agent="rag_agent",
            status="error",
            summary="Answer generation from retrieved context failed.",
            duration_ms=_duration_ms(gen_start),
            details={"error": _truncate_text(e, 500)},
        )
    support = {
        "support_ratio": 0.0,
        "unsupported_claims": [],
        "hallucination_risk": 0.0,
        "claims_checked": 0,
    }
    explainability = None
    grounding_fallback = False
    if settings.ENABLE_PHASE4_RAG_GROUNDING:
        support = assess_claim_support(answer, context)
        _append_step(
            trace,
            step="rag_grounding_check",
            agent="rag_agent",
            status="ok",
            summary="Evaluated answer claim-to-source support.",
            details={
                "support_ratio": support["support_ratio"],
                "unsupported_claims": support["unsupported_claims"],
                "hallucination_risk": support["hallucination_risk"],
            },
        )

        wrqs_config = get_default_wrqs_config()
        is_recommendation = is_recommendation_prompt(message)
        policy_intent = (state.get("policy_intent") or "").upper()
        design_or_order = policy_intent in ("DESIGN_SUPPORT", "ORDER_SUPPORT")
        min_support = wrqs_config.min_support_ratio
        if is_recommendation or design_or_order:
            min_support = 0.0
        if not settings.ISREMOVED_GATE and should_fallback_for_grounding(
            retrieval_confidence=float(retrieval_meta.get("retrieval_confidence", 0.0)),
            support_ratio=float(support["support_ratio"]),
            min_retrieval_confidence=wrqs_config.min_retrieval_confidence,
            min_support_ratio=min_support,
        ):
            answer = "I want to make sure this is accurate. Could you clarify what detail you need most?"
            grounding_fallback = True
            _append_step(
                trace,
                step="rag_grounding_gate",
                agent="rag_agent",
                status="info",
                summary="Grounding gate triggered clarification fallback.",
                details={
                    "retrieval_confidence": retrieval_meta.get("retrieval_confidence", 0.0),
                    "support_ratio": support["support_ratio"],
                },
            )

        if is_recommendation_prompt(message):
            explainability = build_explainability_metadata(answer, retrieval_meta)
            _append_step(
                trace,
                step="rag_explainability",
                agent="rag_agent",
                status="ok",
                summary="Generated internal recommendation explainability metadata.",
                details=explainability,
            )

    rag_metadata = {
        "retrieval_confidence": retrieval_meta.get("retrieval_confidence", 0.0),
        "support_ratio": support["support_ratio"],
        "hallucination_risk": support["hallucination_risk"],
        "grounding_fallback": grounding_fallback,
        "explainability": explainability or {},
    }
    return {
        "messages": [AIMessage(content=answer)],
        "rag_result": answer,
        "rag_metadata": rag_metadata,
        "debug_trace": trace,
    }


# ---------------------------------------------------------------------
# SQL NODE
# ---------------------------------------------------------------------

SQL_PLAN_PROMPT = """You are a SQL planner. Create a safe JSON query plan for PostgreSQL.

Schema:
{schema}

Return ONLY valid JSON matching this shape:
{{
  "base_table": "table_name",
  "base_alias": "t",
  "select": [{{"table": "t", "column": "col", "alias": "optional"}}],
  "aggregates": [{{"func": "count|sum|avg|min|max", "table": "t", "column": "col_or_*", "alias": "optional", "distinct": false}}],
  "joins": [{{"table": "other_table", "alias": "o", "join_type": "inner|left", "on": [{{"left_table":"t","left_column":"id","right_table":"o","right_column":"x_id"}}]}}],
  "filters": [{{"table": "t", "column": "col", "operator": "=|!=|>|>=|<|<=|in|like|ilike", "value": "scalar_or_array"}}],
  "group_by": [{{"table": "t", "column": "col"}}],
  "order_by": [{{"table": "t", "column": "col", "direction": "asc|desc"}}],
  "limit": 50
}}

Rules:
- Plan ONLY a single SELECT query.
- Never include restricted/global/cross-customer data.
- Use joins when related names are requested.
- Prefer customer-scoped account/order/purchase/ticket queries.

Session scope requirements:
{customer_scope_rules}

User question: {question}
"""

RESULT_FORMATTING_PROMPT = """The user asked: "{question}"

Query results (JSON):
{results}

Summarize these results in clear, natural language. Be concise, accurate, and user-friendly. If there are no rows, say so."""


async def _execute_sql(
    database_url: str,
    sql: str,
    *,
    user_id: Optional[int],
    customer_id: Optional[int],
) -> list[dict[str, Any]]:
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.user_id', $1, true)",
                "" if user_id is None else str(int(user_id)),
            )
            await conn.execute(
                "SELECT set_config('app.customer_id', $1, true)",
                "" if customer_id is None else str(int(customer_id)),
            )
            rows = await conn.fetch(sql)
            return [dict(r) for r in rows]
    finally:
        await conn.close()


async def sql_node(
    state: AgentState,
    *,
    settings: Settings,
    qdrant_client: QdrantClient,
) -> dict:
    """SQL agent node: delegates to run_simple_sql_agent (LLM → SQL → Execute → Format)."""
    message = _last_user_message(state)
    logger.info("SQL AGENT | Incoming user query: %s", message)

    trace = _ensure_trace(state, message)
    _mark_called_agent(trace, "sql_agent")

    user_state = (state.get("user_state") or UserState.GUEST.value).upper()
    if user_state == UserState.GUEST.value:
        answer = "SQL access is available only for signed-in users."
        _append_step(
            trace,
            step="sql_policy_gate",
            agent="sql_agent",
            status="error",
            summary="Blocked SQL tool for guest user.",
        )
        return {
            "messages": [AIMessage(content=answer)],
            "sql_result": answer,
            "sql_metadata": {"had_error": True, "guest_blocked": True},
            "debug_trace": trace,
        }

    user_id = state.get("user_id")
    customer_id = state.get("customer_id")
    customer_name = state.get("customer_name") or "Unknown"

    if customer_id is None:
        answer = (
            "I need a customer context before I can query data. "
            "Please log in with a linked customer account or select a customer."
        )
        _append_step(
            trace,
            step="sql_policy_gate",
            agent="sql_agent",
            status="error",
            summary="Missing customer context for SQL query.",
        )
        return {
            "messages": [AIMessage(content=answer)],
            "sql_result": answer,
            "sql_metadata": {"had_error": True, "missing_customer_context": True},
            "debug_trace": trace,
        }

    simple_start = time.perf_counter()
    try:
        result = await run_sql_agent(
            message=message,
            settings=settings,
            qdrant=qdrant_client,
            customer_id=int(customer_id),
            user_id=user_id,
            customer_name=customer_name,
        )
    except Exception as e:
        logger.exception("run_sql_agent failed: %s", e)
        answer = "I ran into an error while querying the database. Please try again or rephrase."
        _append_step(
            trace,
            step="sql_agent",
            agent="sql_agent",
            status="error",
            summary="SQL agent failed.",
            duration_ms=_duration_ms(simple_start),
            details={"error": _truncate_text(e, 500)},
        )
        return {
            "messages": [AIMessage(content=answer)],
            "sql_result": answer,
            "sql_metadata": {"had_error": True, "sql_agent_error": True},
            "debug_trace": trace,
        }

    content = result.get("content") or "No results found."
    metadata = result.get("metadata") or {}
    had_error = "error" in metadata
    sql_metadata = {
        "had_error": had_error,
        "row_count": metadata.get("row_count", 0),
        "validated_sql": result.get("sql"),
        "latency_ms": metadata.get("total_time_ms") or _duration_ms(simple_start),
    }
    _append_step(
        trace,
        step="sql_agent",
        agent="sql_agent",
        status="ok" if not had_error else "error",
        summary="Ran SQL agent (LLM → SQL → Execute → Format).",
        duration_ms=_duration_ms(simple_start),
        details={"row_count": sql_metadata["row_count"]},
    )
    return {
        "messages": [AIMessage(content=content)],
        "sql_result": content,
        "sql_metadata": sql_metadata,
        "debug_trace": trace,
    }


# ---------------------------------------------------------------------
# HYBRID NODE
# ---------------------------------------------------------------------

SYNTHESIS_SYSTEM_PROMPT = """You are a helpful assistant combining database and document outputs.
Use both when relevant and avoid repetition. Keep the response natural and concise."""

PLAIN_SYSTEM_PROMPT = """You are a helpful fashion assistant.
Answer naturally and safely using only user-visible context. Do not claim hidden data access."""

GUIDED_SYSTEM_PROMPT = """You are a fashion design guide assistant.
Respond as short steps with practical guidance, trade-offs, and alternatives."""


async def hybrid_node(
    state: AgentState,
    *,
    settings: Settings,
    qdrant_client: QdrantClient,
) -> dict:
    """Hybrid agent: produce candidates, run Stage-A gate and WRQS scoring, select final answer."""
    message = _last_user_message(state)
    logger.info("HYBRID AGENT | Incoming user query: %s", message)

    trace = _ensure_trace(state, message)
    _mark_called_agent(trace, "hybrid_agent")

    # Note: Question-level blocking removed - SQL-level validation handles scoping

    history = _history_from_messages(state.get("messages", []) or [])
    correction_hint_msg = _correction_hint_message(state)
    if correction_hint_msg:
        _append_step(
            trace,
            step="hybrid_correction_memory",
            agent="hybrid_agent",
            status="info",
            summary="Applied correction-memory hints to hybrid candidate generation.",
            details={"hint_count": len(state.get("correction_hints") or [])},
        )

    lang_pref = state.get("lang_pref")
    lang_instruction = get_language_instruction(lang_pref)

    async def run_sql() -> dict[str, Any]:
        child_state = dict(state)
        child_state["debug_trace"] = deepcopy(trace)
        return await sql_node(child_state, settings=settings, qdrant_client=qdrant_client)

    async def run_rag() -> dict[str, Any]:
        child_state = dict(state)
        child_state["debug_trace"] = deepcopy(trace)
        return await rag_node(child_state, settings=settings, qdrant_client=qdrant_client)

    parallel_start = time.perf_counter()
    results = await asyncio.gather(run_sql(), run_rag(), return_exceptions=True)

    sql_answer = "The database query could not be completed."
    rag_answer = "The document search could not be completed."
    sql_metadata: dict[str, Any] = {"had_error": True}
    rag_metadata: dict[str, Any] = {"hallucination_risk": 0.6, "support_ratio": 0.0}
    sql_status = "ok"
    rag_status = "ok"

    if isinstance(results[0], BaseException):
        sql_status = "error"
        logger.warning("HYBRID | SQL agent failed: %s", results[0])
        _append_step(
            trace,
            step="hybrid_sql_branch",
            agent="hybrid_agent",
            status="error",
            summary="SQL branch failed before producing output.",
            details={"error": _truncate_text(results[0], 500)},
        )
    else:
        sql_out = results[0]
        sql_answer = sql_out.get("sql_result") or sql_answer
        sql_metadata = sql_out.get("sql_metadata") or {"had_error": False}
        sql_steps = _agent_steps(sql_out.get("debug_trace"), "sql_agent")
        if any(step.get("status") == "error" for step in sql_steps):
            sql_status = "error"
        trace["steps"].extend(sql_steps)
        _mark_called_agent(trace, "sql_agent")

    if isinstance(results[1], BaseException):
        rag_status = "error"
        logger.warning("HYBRID | RAG agent failed: %s", results[1])
        _append_step(
            trace,
            step="hybrid_rag_branch",
            agent="hybrid_agent",
            status="error",
            summary="RAG branch failed before producing output.",
            details={"error": _truncate_text(results[1], 500)},
        )
    else:
        rag_out = results[1]
        rag_answer = rag_out.get("rag_result") or rag_answer
        rag_metadata = rag_out.get("rag_metadata") or rag_metadata
        rag_steps = _agent_steps(rag_out.get("debug_trace"), "rag_agent")
        if any(step.get("status") == "error" for step in rag_steps):
            rag_status = "error"
        trace["steps"].extend(rag_steps)
        _mark_called_agent(trace, "rag_agent")

    _append_step(
        trace,
        step="hybrid_parallel",
        agent="hybrid_agent",
        status="ok" if sql_status == "ok" and rag_status == "ok" else "error",
        summary="Finished SQL and RAG branch execution.",
        duration_ms=_duration_ms(parallel_start),
        details={"sql_status": sql_status, "rag_status": rag_status},
    )

    if not (sql_answer or "").strip():
        sql_answer = "No relevant data was found in the database."
    if not (rag_answer or "").strip():
        rag_answer = "No relevant information was found in the documents."

    plain_start = time.perf_counter()
    plain_msgs = [
        {"role": "system", "content": PLAIN_SYSTEM_PROMPT + lang_instruction},
        *([correction_hint_msg] if correction_hint_msg else []),
        *history,
        {"role": "user", "content": message},
    ]
    try:
        plain_answer = (await chat(plain_msgs, settings.LLAMA_URL) or "").strip()
        if not plain_answer:
            plain_answer = "Could you share a bit more detail so I can help better?"
        _append_step(
            trace,
            step="hybrid_plain_candidate",
            agent="hybrid_agent",
            status="ok",
            summary="Generated plain candidate response.",
            duration_ms=_duration_ms(plain_start),
        )
    except Exception as e:
        plain_answer = "I can help with orders, products, and fashion guidance. Could you rephrase your request?"
        _append_step(
            trace,
            step="hybrid_plain_candidate",
            agent="hybrid_agent",
            status="error",
            summary="Plain candidate generation failed; used fallback.",
            duration_ms=_duration_ms(plain_start),
            details={"error": _truncate_text(e, 500)},
        )

    design_mode = (state.get("policy_intent") or "").upper() == "DESIGN_SUPPORT"
    guided_answer = ""
    if design_mode:
        guided_start = time.perf_counter()
        guided_msgs = [
            {"role": "system", "content": GUIDED_SYSTEM_PROMPT + lang_instruction},
            *([correction_hint_msg] if correction_hint_msg else []),
            *history,
            {"role": "user", "content": message},
        ]
        try:
            guided_answer = (await chat(guided_msgs, settings.LLAMA_URL) or "").strip()
            _append_step(
                trace,
                step="hybrid_guided_candidate",
                agent="hybrid_agent",
                status="ok",
                summary="Generated guided candidate for design intent.",
                duration_ms=_duration_ms(guided_start),
            )
        except Exception as e:
            guided_answer = ""
            _append_step(
                trace,
                step="hybrid_guided_candidate",
                agent="hybrid_agent",
                status="error",
                summary="Guided candidate generation failed.",
                duration_ms=_duration_ms(guided_start),
                details={"error": _truncate_text(e, 500)},
            )

    if not settings.ENABLE_PHASE5_CANDIDATES:
        msgs = [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT + lang_instruction},
            *([correction_hint_msg] if correction_hint_msg else []),
            *history,
            {"role": "system", "content": f"Database result:\n{sql_answer}\n\nDocument knowledge:\n{rag_answer}"},
            {"role": "user", "content": message},
        ]
        combined = (await chat(msgs, settings.LLAMA_URL) or "").strip()
        if not combined:
            combined = f"{sql_answer}\n\n{rag_answer}"
        _set_trace_intent(trace, "hybrid")
        return {
            "messages": [AIMessage(content=combined)],
            "sql_result": sql_answer,
            "rag_result": rag_answer,
            "debug_trace": trace,
        }

    candidates = [
        build_candidate(
            candidate_id="r_sql",
            text=sql_answer,
            source="sql_agent",
            metadata=sql_metadata,
            signals=candidate_signals(candidate_id="r_sql", text=sql_answer, sql_metadata=sql_metadata),
        ),
        build_candidate(
            candidate_id="r_rag",
            text=rag_answer,
            source="rag_agent",
            metadata=rag_metadata,
            signals=candidate_signals(candidate_id="r_rag", text=rag_answer, rag_metadata=rag_metadata),
        ),
        build_candidate(
            candidate_id="r_plain",
            text=plain_answer,
            source="plain_llm",
            signals=candidate_signals(candidate_id="r_plain", text=plain_answer),
        ),
    ]
    if design_mode and guided_answer:
        candidates.append(
            build_candidate(
                candidate_id="r_guided",
                text=guided_answer,
                source="guided_llm",
                signals=candidate_signals(
                    candidate_id="r_guided",
                    text=guided_answer,
                    design_mode=design_mode,
                ),
            )
        )

    context = CandidateContext(
        user_message=message,
        user_state=(state.get("user_state") or UserState.GUEST.value),
        intent=(state.get("intent") or "hybrid"),
        policy_allow=bool(state.get("policy_allow") if state.get("policy_allow") is not None else True),
        policy_reason_code=state.get("policy_reason_code"),
        user_id=state.get("user_id"),
        customer_id=state.get("customer_id"),
    )

    stage_a = gate_candidates(candidates, context)
    _append_step(
        trace,
        step="hybrid_stage_a_gate",
        agent="hybrid_agent",
        status="ok",
        summary="Applied Stage-A compliance gate to all candidates.",
        details={
            item.candidate_id: {
                "allow": stage_a[item.candidate_id].allow,
                "reason_code": stage_a[item.candidate_id].reason_code,
            }
            for item in candidates
        },
    )

    if settings.ENABLE_PHASE6_WRQS:
        wrqs_config = get_default_wrqs_config()
        release_wrqs_weights = state.get("release_wrqs_weights") if isinstance(state.get("release_wrqs_weights"), dict) else {}
        release_positive = release_wrqs_weights.get("positive") if isinstance(release_wrqs_weights.get("positive"), dict) else None
        release_penalty = release_wrqs_weights.get("penalty") if isinstance(release_wrqs_weights.get("penalty"), dict) else None
        if release_positive and release_penalty:
            wrqs_config = WRQSConfig(
                positive_weights={str(k): float(v) for k, v in release_positive.items()},
                penalty_weights={str(k): float(v) for k, v in release_penalty.items()},
                wrqs_tie_delta=wrqs_config.wrqs_tie_delta,
                min_retrieval_confidence=wrqs_config.min_retrieval_confidence,
                min_support_ratio=wrqs_config.min_support_ratio,
            )
            _append_step(
                trace,
                step="hybrid_release_wrqs",
                agent="hybrid_agent",
                status="info",
                summary="Loaded WRQS weights from active release config.",
                details={"source": "release_control"},
            )
        wrqs_overrides = state.get("wrqs_weight_overrides") if isinstance(state.get("wrqs_weight_overrides"), dict) else {}
        if wrqs_overrides:
            wrqs_config = apply_wrqs_overrides(wrqs_config, wrqs_overrides, max_delta=0.10)
            _append_step(
                trace,
                step="hybrid_wrqs_override",
                agent="hybrid_agent",
                status="info",
                summary="Applied session-level WRQS weight overrides.",
                details={"wrqs_weight_overrides": wrqs_overrides},
            )
        scores = [score_candidate(c, context, wrqs_config, stage_a[c.candidate_id]) for c in candidates]
        selected_candidate, _, rationale = select_best_candidate(
            candidates=candidates,
            scores=scores,
            context=context,
            config=wrqs_config,
        )
        _append_step(
            trace,
            step="hybrid_wrqs_scoring",
            agent="hybrid_agent",
            status="ok",
            summary="Scored candidates with WRQS and selected best response.",
            details={
                "scores": [
                    {
                        "candidate_id": s.candidate_id,
                        "stage_a_passed": s.stage_a_passed,
                        "stage_a_reason_code": s.stage_a_reason_code,
                        "wrqs": None if s.wrqs == float("-inf") else round(s.wrqs, 6),
                        "weighted_positive": round(s.weighted_positive, 6),
                        "weighted_penalty": round(s.weighted_penalty, 6),
                        "risk_score": round(s.risk_score, 6),
                    }
                    for s in scores
                ],
                "selection_rationale": rationale,
            },
        )
        final_answer = selected_candidate.text
        selected_candidate_id = selected_candidate.candidate_id
        score_rows = scores
    else:
        allowed = [c for c in candidates if stage_a[c.candidate_id].allow]
        selected = allowed[0] if allowed else candidates[0]
        final_answer = selected.text
        selected_candidate_id = selected.candidate_id
        score_rows = []

    _append_step(
        trace,
        step="hybrid_candidate_selection",
        agent="hybrid_agent",
        status="ok",
        summary=f"Selected candidate {selected_candidate_id}.",
        details={"selected_candidate_id": selected_candidate_id},
    )

    candidate_set = [
        {
            "candidate_id": c.candidate_id,
            "source": c.source,
            "preview": _truncate_text(c.text, 200),
            "stage_a_allow": stage_a[c.candidate_id].allow,
            "stage_a_reason_code": stage_a[c.candidate_id].reason_code,
        }
        for c in candidates
    ]
    candidate_scores = [
        {
            "candidate_id": s.candidate_id,
            "stage_a_passed": s.stage_a_passed,
            "stage_a_reason_code": s.stage_a_reason_code,
            "wrqs": None if s.wrqs == float("-inf") else s.wrqs,
            "weighted_positive": s.weighted_positive,
            "weighted_penalty": s.weighted_penalty,
            "risk_score": s.risk_score,
            "positive_factors": s.positive_factors,
            "penalty_factors": s.penalty_factors,
        }
        for s in score_rows
    ]

    _set_trace_intent(trace, "hybrid")
    return {
        "messages": [AIMessage(content=final_answer)],
        "sql_result": sql_answer,
        "rag_result": rag_answer,
        "sql_metadata": sql_metadata,
        "rag_metadata": rag_metadata,
        "candidate_set": candidate_set,
        "candidate_scores": candidate_scores,
        "selected_candidate_id": selected_candidate_id,
        "debug_trace": trace,
    }
