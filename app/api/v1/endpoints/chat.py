"""Chat endpoint: LangGraph agent orchestrator with intent-based routing."""

from datetime import datetime, timezone
import logging
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from prisma import Prisma

from app.api.dependencies import get_current_user, get_current_user_optional, get_graph, get_prisma
from app.core.config import get_settings
from app.schemas.auth import UserOut
from app.schemas.chat import (
    CanaryRollbackRequest,
    CanaryRollbackResponse,
    CanaryStartRequest,
    CanaryStartResponse,
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatHandoffRequest,
    ChatHandoffResponse,
    ChatHistoryResponse,
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    GoldenRunResponse,
    LearningPreferencesOut,
    LearningPreferencesUpdateRequest,
    OpsDashboardResponse,
    ReleaseStatusResponse,
)
from app.services.candidate_framework import PENALTY_KEYS, POSITIVE_KEYS
from app.services.candidate_signals import candidate_signals
from app.services.correction_memory_service import (
    MEMORY_SCOPE_LONG_TERM,
    MEMORY_SCOPE_SESSION,
    create_correction_memory,
    load_correction_hints,
)
from app.services.feedback_service import create_feedback, ensure_message_in_session, get_latest_feedback_map
from app.services.handoff_service import enqueue_handoff, increment_session_handoff_clicks
from app.services.learning_guardrails_service import (
    classify_learning_eligibility,
    create_learning_exclusion_audit,
)
from app.services.learning_preferences_service import (
    get_learning_preferences,
    long_term_memory_allowed,
    upsert_learning_preferences,
)
from app.services.online_adaptation_service import (
    adaptation_state,
    apply_adaptation,
    build_gap_topic_key,
    detect_rephrase,
    evaluate_adaptation,
    expire_adaptation,
    get_or_create_session_feature,
    persist_turn_scores,
    upsert_knowledge_gap_item,
)
from app.services.ops_dashboard_service import get_ops_dashboard, get_ops_snapshot
from app.services.policy_audit_service import save_policy_audit
from app.services.policy_gate import UserState
from app.services.quality_scoring_service import (
    TurnQualityInput,
    classify_turn_quality,
    compute_kgs,
    compute_tqs,
)
from app.services.release_control_service import (
    evaluate_canary_and_maybe_rollback,
    get_active_wrqs_weights,
    get_release_status,
    is_experiment_dimension_allowed,
    run_golden_gate,
    snapshot_component_versions,
    start_canary_rollout,
)
from app.services.session_service import (
    get_full_history,
    get_latest_assistant_trace,
    get_latest_user_message,
    get_or_create_session,
    save_turn,
)
from app.services.translation_service import translate_to_english, translate_to_language
from app.services.language_helper import LANGUAGE_NAMES
from app.services.telemetry_service import (
    EVENT_ASSISTANT_MSG,
    EVENT_CANDIDATE_SNAPSHOT,
    EVENT_FEEDBACK,
    EVENT_HANDOFF,
    EVENT_TURN_SCORE,
    EVENT_USER_MSG,
    emit_event,
    emit_trace_tool_events,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


async def _resolve_customer_by_name(prisma: Prisma, raw_name: str):
    """Resolve customer by full name or email from customer table."""
    needle = _normalize_name(raw_name)
    if not needle:
        return None

    customers = await prisma.customer.find_many()
    matches = []
    for customer in customers:
        full_name = _normalize_name(f"{customer.firstname} {customer.lastname}")
        email = _normalize_name(getattr(customer, "email", "") or "")
        if needle == full_name or (email and needle == email):
            matches.append(customer)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise HTTPException(
            status_code=400,
            detail="Selected customer name is ambiguous. Use full name or email.",
        )
    return None


def _new_base_trace(
    *,
    request_id: str,
    message: str,
    created_at: datetime,
) -> dict:
    return {
        "request_id": request_id,
        "user_query": message,
        "intent": None,
        "called_agents": [],
        "steps": [],
        "created_at": created_at.isoformat(),
    }


def _split_factors(signals: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    positive = {k: float(signals.get(k, 0.0)) for k in POSITIVE_KEYS}
    penalty = {k: float(signals.get(k, 0.0)) for k in PENALTY_KEYS}
    return positive, penalty


def _build_quality_input(
    *,
    intent: Literal["sql", "rag", "hybrid"],
    result: dict[str, Any],
    answer_text: str,
    rephrase_count: int,
    handoff_click: bool,
) -> TurnQualityInput:
    sql_metadata = result.get("sql_metadata") if isinstance(result.get("sql_metadata"), dict) else {}
    rag_metadata = result.get("rag_metadata") if isinstance(result.get("rag_metadata"), dict) else {}

    selected_id = str(result.get("selected_candidate_id") or "")
    score_rows = result.get("candidate_scores") if isinstance(result.get("candidate_scores"), list) else []
    selected_row = None
    for row in score_rows:
        if isinstance(row, dict) and row.get("candidate_id") == selected_id:
            selected_row = row
            break

    if selected_row:
        positive = selected_row.get("positive_factors") or {}
        penalty = selected_row.get("penalty_factors") or {}
    else:
        candidate_id = "r_plain"
        if intent == "sql":
            candidate_id = "r_sql"
        elif intent == "rag":
            candidate_id = "r_rag"
        elif selected_id:
            candidate_id = selected_id
        signals = candidate_signals(
            candidate_id=candidate_id,
            text=answer_text,
            sql_metadata=sql_metadata,
            rag_metadata=rag_metadata,
        )
        positive, penalty = _split_factors(signals)

    return TurnQualityInput(
        intent=intent,
        positive_factors=positive if isinstance(positive, dict) else {},
        penalty_factors=penalty if isinstance(penalty, dict) else {},
        retrieval_confidence=float(rag_metadata.get("retrieval_confidence", 0.0)),
        hallucination_risk=float(rag_metadata.get("hallucination_risk", 0.0)),
        sql_error=bool(sql_metadata.get("had_error", False)),
        sql_row_count=int(sql_metadata.get("row_count", 0)) if sql_metadata.get("row_count") is not None else None,
        rephrase_count=int(rephrase_count),
        handoff_click=bool(handoff_click),
    )


async def _latest_turn_index(prisma: Prisma, session_id: str) -> int:
    rows = await prisma.query_raw(
        """
        SELECT COALESCE(MAX("turn_index"), 1) AS turn_index
        FROM "chat_event_log"
        WHERE "session_id" = $1
        """,
        session_id,
    )
    if not rows:
        return 1
    row = rows[0]
    payload = dict(row.__dict__) if hasattr(row, "__dict__") else (row if isinstance(row, dict) else {})
    raw = payload.get("turn_index")
    try:
        return int(raw) if raw is not None else 1
    except Exception:
        return 1


@router.post("", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    prisma: Prisma = Depends(get_prisma),
    graph=Depends(get_graph),
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
) -> ChatResponse:
    """Process user message via LangGraph orchestrator with policy guardrails."""
    logger.info("Chat | User query: %s", body.message)

    settings = get_settings()
    request_id = str(uuid4())
    trace_created_at = datetime.now(timezone.utc)
    user_state = UserState.REGISTERED if current_user else UserState.GUEST
    roles = ["customer"] if current_user else []
    consent_flags: dict[str, bool] = {
        "long_term_personalization_opt_in": False,
        "telemetry_learning_opt_in": True,
    }
    active_order_id: Optional[str] = None
    active_design_id: Optional[str] = None
    is_guest = user_state == UserState.GUEST
    requested_session_id = f"guest-{request_id}" if is_guest else body.session_id
    session_id = await get_or_create_session(prisma, requested_session_id)
    base_trace = _new_base_trace(
        request_id=request_id,
        message=body.message,
        created_at=trace_created_at,
    )
    created_at_iso = trace_created_at.isoformat()

    session_feature = None
    previous_user_message: Optional[str] = None
    turn_index = 1
    adaptation_inputs: dict[str, Any] = {}
    correction_hints: list[str] = []
    learning_preferences = {
        "long_term_personalization_opt_in": False,
        "telemetry_learning_opt_in": True,
    }
    release_wrqs_weights: dict[str, dict[str, float]] = {}

    # When user selects non-English: translate input to English for internal processing,
    # process in English, then translate output back to user's language.
    message_for_graph = body.message
    response_lang: Optional[str] = None
    lang_pref_for_graph: Optional[str] = body.language or None
    if body.language and body.language != "en" and body.language in LANGUAGE_NAMES:
        message_for_graph = await translate_to_english(body.message, settings)
        response_lang = body.language
        lang_pref_for_graph = None  # Internal processing stays in English

    # Pass only the new message; checkpoint provides conversation history
    messages = [HumanMessage(content=message_for_graph)]
    config = {"configurable": {"thread_id": session_id}}

    try:
        customer_id = current_user.customer_id if current_user else None
        customer_name = None
        if current_user and current_user.customer:
            customer_name = f"{current_user.customer.firstname} {current_user.customer.lastname}".strip()

        selected_customer_name = (body.selected_customer_name or "").strip()
        if selected_customer_name and current_user:
            selected_customer = await _resolve_customer_by_name(prisma, selected_customer_name)
            if not selected_customer:
                raise HTTPException(status_code=404, detail="Selected customer was not found.")

            selected_customer_id = int(selected_customer.id)
            selected_display_name = f"{selected_customer.firstname} {selected_customer.lastname}".strip()
            if customer_id is not None and int(customer_id) != selected_customer_id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only access your own customer data.",
                )
            customer_id = selected_customer_id
            customer_name = selected_display_name

        if user_state == UserState.REGISTERED and customer_id is None:
            raise HTTPException(
                status_code=400,
                detail="No customer is linked to this login. Provide selected_customer_name.",
            )

        if not is_guest and settings.ENABLE_LEARNING_GOVERNANCE and current_user:
            learning_preferences = await get_learning_preferences(
                prisma,
                user_id=current_user.id,
                customer_id=customer_id,
            )
            consent_flags = {
                "long_term_personalization_opt_in": bool(
                    learning_preferences.get("long_term_personalization_opt_in", False)
                ),
                "telemetry_learning_opt_in": bool(
                    learning_preferences.get("telemetry_learning_opt_in", True)
                ),
            }

        if settings.ENABLE_RELEASE_CONTROLS:
            try:
                active_wrqs = await get_active_wrqs_weights(prisma)
                if active_wrqs:
                    release_wrqs_weights = {
                        "positive": dict(active_wrqs.get("positive_weights", {}) or {}),
                        "penalty": dict(active_wrqs.get("penalty_weights", {}) or {}),
                    }
            except Exception as exc:
                logger.warning("Release WRQS lookup skipped: %s", exc)

        if not is_guest and (settings.ENABLE_LEARNING_SCORING or settings.ENABLE_LEARNING_ONLINE_ADAPTATION):
            session_feature = await get_or_create_session_feature(
                prisma,
                session_id=session_id,
                user_id=current_user.id if current_user else None,
                customer_id=customer_id,
            )
            turn_index = int(session_feature.turn_index) + 1
            previous_user_message = await get_latest_user_message(prisma, session_id)

            if settings.ENABLE_LEARNING_ONLINE_ADAPTATION:
                session_feature = await expire_adaptation(
                    prisma,
                    session_id=session_id,
                    current_turn_index=turn_index,
                )
                adaptation_inputs = adaptation_state(session_feature)

        if not is_guest:
            correction_hints = await load_correction_hints(
                prisma,
                session_id=session_id,
                user_id=current_user.id if current_user else None,
                customer_id=customer_id,
            )

        result = await graph.ainvoke(
            {
                "messages": messages,
                "user_state": user_state.value,
                "roles": roles,
                "consent_flags": consent_flags,
                "active_order_id": active_order_id,
                "active_design_id": active_design_id,
                "user_id": current_user.id if current_user else None,
                "customer_id": customer_id,
                "customer_name": customer_name,
                "trace_request_id": request_id,
                "trace_created_at": trace_created_at,
                "learning_turn_index": turn_index,
                "correction_hints": correction_hints,
                "release_wrqs_weights": release_wrqs_weights or {},
                "lang_pref": lang_pref_for_graph,
                **adaptation_inputs,
                "debug_trace": base_trace,
            },
            config=config,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("LangGraph invoke failed: %s", e)
        raise HTTPException(status_code=500, detail="The assistant encountered an error. Please try again.")

    msgs = result.get("messages") or []
    content = ""
    for m in reversed(msgs):
        if isinstance(m, AIMessage):
            content = m.content if isinstance(m.content, str) else str(m.content)
            break

    # Translate response to user's language when we used input translation
    if response_lang and content:
        content = await translate_to_language(content, response_lang, settings)

    debug_trace = result.get("debug_trace")
    if not isinstance(debug_trace, dict):
        debug_trace = base_trace

    policy_allow_raw = result.get("policy_allow")
    policy_allow = bool(policy_allow_raw) if isinstance(policy_allow_raw, bool) else False
    policy_intent = str(result.get("policy_intent") or "UNKNOWN")
    policy_domain = str(result.get("policy_domain") or "OFF_DOMAIN")
    policy_confidence_raw = result.get("policy_confidence")
    policy_confidence = (
        float(policy_confidence_raw)
        if isinstance(policy_confidence_raw, (float, int))
        else None
    )
    policy_reason_code_raw = result.get("policy_reason_code")
    policy_reason_code = str(policy_reason_code_raw) if isinstance(policy_reason_code_raw, str) else None
    policy_decision_source_raw = result.get("policy_decision_source")
    policy_decision_source = (
        str(policy_decision_source_raw)
        if isinstance(policy_decision_source_raw, str)
        else "unknown"
    )

    await save_policy_audit(
        prisma,
        request_id=request_id,
        session_id=session_id,
        user_id=current_user.id if current_user else None,
        user_state=user_state,
        message=body.message,
        policy_intent=policy_intent,
        policy_domain=policy_domain,
        classifier_confidence=policy_confidence,
        allow=policy_allow,
        reason_code=policy_reason_code,
        decision_source=policy_decision_source,
        trace=debug_trace,
    )

    learning_guardrail = classify_learning_eligibility(
        content=body.message,
        policy_allow=policy_allow,
        policy_reason_code=policy_reason_code,
        telemetry_opt_in=bool(learning_preferences.get("telemetry_learning_opt_in", True)),
    )
    learning_allowed = bool(learning_guardrail.learning_allowed)
    learning_exclusion_reason = learning_guardrail.exclusion_reason_code

    debug_steps = debug_trace.get("steps")
    if isinstance(debug_steps, list):
        debug_steps.append(
            {
                "step": "learning_guardrails",
                "agent": "learning_engine",
                "status": "ok" if learning_allowed else "error",
                "summary": (
                    "Learning guardrails allow this turn for learning."
                    if learning_allowed
                    else "Learning guardrails excluded this turn from learning."
                ),
                "details": {
                    "learning_allowed": learning_allowed,
                    "exclusion_reason_code": learning_exclusion_reason,
                    "policy_reason_code": policy_reason_code,
                    "telemetry_opt_in": bool(learning_preferences.get("telemetry_learning_opt_in", True)),
                },
            }
        )

    if settings.ENABLE_RELEASE_CONTROLS:
        try:
            component_snapshot = await snapshot_component_versions(
                prisma,
                settings=settings,
                status="STABLE",
                canary_percent=0,
            )
            if isinstance(debug_steps, list):
                debug_steps.append(
                    {
                        "step": "release_control_context",
                        "agent": "learning_engine",
                        "status": "ok",
                        "summary": "Loaded component version snapshot for release controls.",
                        "details": {
                            "components": {
                                key: value.get("version_hash")
                                for key, value in component_snapshot.items()
                            }
                        },
                    }
                )
        except Exception as exc:
            logger.warning("Release snapshot skipped: %s", exc)

    if settings.ENABLE_OPS_DASHBOARD:
        try:
            ops_snapshot = await get_ops_snapshot(prisma)
            if isinstance(debug_steps, list):
                debug_steps.append(
                    {
                        "step": "ops_kpi_snapshot",
                        "agent": "learning_engine",
                        "status": "ok",
                        "summary": "Attached compact KPI snapshot for debug trace.",
                        "details": ops_snapshot,
                    }
                )
        except Exception as exc:
            logger.warning("Ops snapshot skipped: %s", exc)

    intent: Literal["sql", "rag", "hybrid"] = result.get("intent") or ("rag" if not policy_allow else "hybrid")
    message_ids = {"user_message_id": None, "assistant_message_id": None}

    learning_step_details: dict[str, Any] = {}
    if settings.ENABLE_LEARNING_SCORING and learning_allowed:
        rephrase_count = 0
        handoff_click = False
        if session_feature is not None:
            rephrase_increment = 1 if detect_rephrase(body.message, previous_user_message) else 0
            rephrase_count = int(session_feature.rephrase_count) + rephrase_increment
            handoff_click = int(session_feature.handoff_clicks) > 0

        quality_input = _build_quality_input(
            intent=intent,
            result=result,
            answer_text=content,
            rephrase_count=rephrase_count,
            handoff_click=handoff_click,
        )
        tqs = compute_tqs(quality_input, wrqs_weights=release_wrqs_weights or None)
        kgs = compute_kgs(quality_input)
        quality = classify_turn_quality(
            tqs,
            kgs,
            low_tqs_threshold=settings.LEARNING_LOW_TQS_THRESHOLD,
            high_kgs_threshold=settings.LEARNING_HIGH_KGS_THRESHOLD,
            critical_kgs_threshold=settings.LEARNING_CRITICAL_KGS_THRESHOLD,
        )
        learning_step_details = {
            "turn_index": turn_index,
            "tqs": quality.tqs,
            "kgs": quality.kgs,
            "low_tqs": quality.low_tqs,
            "high_kgs": quality.high_kgs,
            "critical_kgs": quality.critical_kgs,
            "rephrase_count": rephrase_count,
            "handoff_click": handoff_click,
            "intent": intent,
        }
        debug_steps = debug_trace.get("steps")
        if isinstance(debug_steps, list):
            debug_steps.append(
                {
                    "step": "learning_turn_quality",
                    "agent": "learning_engine",
                    "status": "ok",
                    "summary": "Computed TQS/KGS quality scores for this turn.",
                    "details": learning_step_details,
                }
            )

        if session_feature is not None:
            await persist_turn_scores(
                prisma,
                session_id=session_id,
                turn_index=turn_index,
                tqs=quality.tqs,
                kgs=quality.kgs,
                rephrase_count=rephrase_count,
            )

            adaptation_reason_codes: list[str] = []
            if settings.ENABLE_LEARNING_ONLINE_ADAPTATION:
                decision = evaluate_adaptation(
                    tqs=quality.tqs,
                    kgs=quality.kgs,
                    rephrase_count=rephrase_count,
                    handoff_clicks=int(session_feature.handoff_clicks),
                    current_turn_index=turn_index,
                    low_tqs_threshold=settings.LEARNING_LOW_TQS_THRESHOLD,
                    high_kgs_threshold=settings.LEARNING_HIGH_KGS_THRESHOLD,
                    rag_topk_adapt=settings.LEARNING_RAG_TOPK_ADAPT,
                    ttl_turns=settings.LEARNING_ADAPT_TTL_TURNS,
                )
                adaptation_reason_codes = decision.reason_codes
                if decision.should_apply:
                    await apply_adaptation(
                        prisma,
                        session_id=session_id,
                        decision=decision,
                    )
            learning_step_details["adaptation_reasons"] = adaptation_reason_codes

            if quality.critical_kgs:
                topic_key = build_gap_topic_key(intent, body.message)
                await upsert_knowledge_gap_item(
                    prisma,
                    topic_key=topic_key,
                    intent=intent,
                    trigger_source="KGS_CRITICAL",
                    score=quality.kgs,
                    request_id=request_id,
                    session_id=session_id,
                )
    elif settings.ENABLE_LEARNING_SCORING and not learning_allowed:
        if isinstance(debug_steps, list):
            debug_steps.append(
                {
                    "step": "learning_turn_quality",
                    "agent": "learning_engine",
                    "status": "info",
                    "summary": "Skipped TQS/KGS scoring due to learning guardrail exclusion.",
                    "details": {
                        "learning_allowed": False,
                        "exclusion_reason_code": learning_exclusion_reason,
                    },
                }
            )

    if not is_guest:
        message_ids = await save_turn(prisma, session_id, body.message, content, assistant_trace=debug_trace)

    if settings.ENABLE_LEARNING_GOVERNANCE and not learning_allowed:
        try:
            await create_learning_exclusion_audit(
                prisma,
                request_id=request_id,
                session_id=session_id,
                message_id=message_ids.get("assistant_message_id"),
                user_id=current_user.id if current_user else None,
                customer_id=current_user.customer_id if current_user else None,
                exclusion_reason_code=learning_exclusion_reason or "UNKNOWN_EXCLUSION",
                policy_reason_code=policy_reason_code,
                content=body.message,
            )
        except Exception as exc:
            logger.warning("Learning exclusion audit skipped: %s", exc)

    if settings.ENABLE_LEARNING_TELEMETRY:
        await emit_event(
            prisma,
            request_id=request_id,
            session_id=session_id,
            turn_index=turn_index,
            event_type=EVENT_USER_MSG,
            created_at_iso=created_at_iso,
            message_id=message_ids.get("user_message_id"),
            user_id=current_user.id if current_user else None,
            customer_id=current_user.customer_id if current_user else None,
            content=body.message,
            payload={"intent": intent},
            learning_allowed=learning_allowed,
            learning_exclusion_reason=learning_exclusion_reason,
        )
        await emit_event(
            prisma,
            request_id=request_id,
            session_id=session_id,
            turn_index=turn_index,
            event_type=EVENT_ASSISTANT_MSG,
            created_at_iso=created_at_iso,
            message_id=message_ids.get("assistant_message_id"),
            user_id=current_user.id if current_user else None,
            customer_id=current_user.customer_id if current_user else None,
            content=content,
            payload={"intent": intent, "selected_candidate_id": result.get("selected_candidate_id")},
            learning_allowed=learning_allowed,
            learning_exclusion_reason=learning_exclusion_reason,
        )

        if settings.ENABLE_LEARNING_SCORING and learning_step_details:
            await emit_event(
                prisma,
                request_id=request_id,
                session_id=session_id,
                turn_index=turn_index,
                event_type=EVENT_TURN_SCORE,
                created_at_iso=created_at_iso,
                message_id=message_ids.get("assistant_message_id"),
                user_id=current_user.id if current_user else None,
                customer_id=current_user.customer_id if current_user else None,
                payload=learning_step_details,
                learning_allowed=learning_allowed,
                learning_exclusion_reason=learning_exclusion_reason,
            )

        candidate_set = result.get("candidate_set")
        candidate_scores = result.get("candidate_scores")
        if isinstance(candidate_set, list) or isinstance(candidate_scores, list):
            await emit_event(
                prisma,
                request_id=request_id,
                session_id=session_id,
                turn_index=turn_index,
                event_type=EVENT_CANDIDATE_SNAPSHOT,
                created_at_iso=created_at_iso,
                message_id=message_ids.get("assistant_message_id"),
                user_id=current_user.id if current_user else None,
                customer_id=current_user.customer_id if current_user else None,
                payload={
                    "selected_candidate_id": result.get("selected_candidate_id"),
                    "candidate_set": candidate_set if isinstance(candidate_set, list) else [],
                    "candidate_scores": candidate_scores if isinstance(candidate_scores, list) else [],
                },
                learning_allowed=learning_allowed,
                learning_exclusion_reason=learning_exclusion_reason,
            )

        await emit_trace_tool_events(
            prisma,
            request_id=request_id,
            session_id=session_id,
            turn_index=turn_index,
            created_at_iso=created_at_iso,
            trace=debug_trace,
            assistant_message_id=message_ids.get("assistant_message_id"),
            user_id=current_user.id if current_user else None,
            customer_id=current_user.customer_id if current_user else None,
            learning_allowed=learning_allowed,
            learning_exclusion_reason=learning_exclusion_reason,
        )

    return ChatResponse(
        content=content,
        intent=intent,
        session_id=session_id,
        assistant_message_id=message_ids.get("assistant_message_id"),
        request_id=request_id,
        turn_index=turn_index,
        debug_trace=debug_trace,
    )


@router.post("/feedback", response_model=ChatFeedbackResponse)
async def post_chat_feedback(
    body: ChatFeedbackRequest,
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> ChatFeedbackResponse:
    """Persist explicit user feedback for one assistant message."""
    settings = get_settings()
    if not settings.ENABLE_LEARNING_FEEDBACK:
        raise HTTPException(status_code=503, detail="Feedback collection is currently disabled.")

    session = await prisma.chatsession.find_unique(where={"id": body.session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    in_session = await ensure_message_in_session(
        prisma,
        session_id=body.session_id,
        message_id=body.message_id,
    )
    if not in_session:
        raise HTTPException(status_code=400, detail="Message does not belong to this session.")

    correction_text = (body.correction_text or "").strip()
    learning_preferences = await get_learning_preferences(
        prisma,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
    )
    feedback_guardrail = classify_learning_eligibility(
        content=correction_text or (body.reason_code or body.feedback_type),
        policy_allow=True,
        policy_reason_code=None,
        telemetry_opt_in=bool(learning_preferences.get("telemetry_learning_opt_in", True)),
    )

    feedback_id = await create_feedback(
        prisma,
        session_id=body.session_id,
        message_id=body.message_id,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
        feedback_type=body.feedback_type,
        reason_code=body.reason_code,
        correction_text=correction_text if correction_text else None,
        learning_allowed=feedback_guardrail.learning_allowed,
        learning_exclusion_reason=feedback_guardrail.exclusion_reason_code,
    )

    applied_session_memory = False
    stored_long_term_memory = False
    if body.feedback_type == "DOWN" and correction_text:
        await create_correction_memory(
            prisma,
            session_id=body.session_id,
            message_id=body.message_id,
            source_feedback_id=feedback_id,
            user_id=current_user.id,
            customer_id=current_user.customer_id,
            instruction_text=correction_text,
            memory_scope=MEMORY_SCOPE_SESSION,
            consent_long_term=False,
        )
        applied_session_memory = True

        if long_term_memory_allowed(
            request_consent_long_term=bool(body.consent_long_term),
            preference_long_term_opt_in=bool(
                learning_preferences.get("long_term_personalization_opt_in", False)
            ),
        ):
            await create_correction_memory(
                prisma,
                session_id=body.session_id,
                message_id=body.message_id,
                source_feedback_id=feedback_id,
                user_id=current_user.id,
                customer_id=current_user.customer_id,
                instruction_text=correction_text,
                memory_scope=MEMORY_SCOPE_LONG_TERM,
                consent_long_term=True,
            )
            stored_long_term_memory = True

    if settings.ENABLE_LEARNING_GOVERNANCE and not feedback_guardrail.learning_allowed:
        try:
            await create_learning_exclusion_audit(
                prisma,
                request_id=str(uuid4()),
                session_id=body.session_id,
                message_id=body.message_id,
                user_id=current_user.id,
                customer_id=current_user.customer_id,
                exclusion_reason_code=feedback_guardrail.exclusion_reason_code or "UNKNOWN_EXCLUSION",
                policy_reason_code=None,
                content=correction_text or (body.reason_code or body.feedback_type),
            )
        except Exception as exc:
            logger.warning("Feedback exclusion audit skipped: %s", exc)

    if settings.ENABLE_LEARNING_TELEMETRY:
        request_id = str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        turn_index = await _latest_turn_index(prisma, body.session_id)
        await emit_event(
            prisma,
            request_id=request_id,
            session_id=body.session_id,
            turn_index=turn_index,
            event_type=EVENT_FEEDBACK,
            created_at_iso=now_iso,
            message_id=body.message_id,
            user_id=current_user.id,
            customer_id=current_user.customer_id,
            content=correction_text or None,
                payload={
                    "feedback_type": body.feedback_type,
                    "reason_code": body.reason_code,
                    "consent_long_term": bool(body.consent_long_term),
                },
                learning_allowed=feedback_guardrail.learning_allowed,
                learning_exclusion_reason=feedback_guardrail.exclusion_reason_code,
            )

    return ChatFeedbackResponse(
        feedback_id=feedback_id,
        applied_session_memory=applied_session_memory,
        stored_long_term_memory=stored_long_term_memory,
    )


@router.post("/handoff", response_model=ChatHandoffResponse)
async def post_chat_handoff(
    body: ChatHandoffRequest,
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> ChatHandoffResponse:
    """Create a human-handoff queue item for the selected assistant message."""
    settings = get_settings()
    if not settings.ENABLE_LEARNING_HANDOFF:
        raise HTTPException(status_code=503, detail="Handoff is currently disabled.")

    session = await prisma.chatsession.find_unique(where={"id": body.session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    in_session = await ensure_message_in_session(
        prisma,
        session_id=body.session_id,
        message_id=body.message_id,
    )
    if not in_session:
        raise HTTPException(status_code=400, detail="Message does not belong to this session.")

    handoff_id = await enqueue_handoff(
        prisma,
        session_id=body.session_id,
        message_id=body.message_id,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
        reason_code=body.reason_code,
        notes=body.notes,
    )
    await increment_session_handoff_clicks(
        prisma,
        session_id=body.session_id,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
    )

    if settings.ENABLE_LEARNING_TELEMETRY:
        request_id = str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        turn_index = await _latest_turn_index(prisma, body.session_id)
        await emit_event(
            prisma,
            request_id=request_id,
            session_id=body.session_id,
            turn_index=turn_index,
            event_type=EVENT_HANDOFF,
            created_at_iso=now_iso,
            message_id=body.message_id,
            user_id=current_user.id,
            customer_id=current_user.customer_id,
            payload={
                "handoff_id": handoff_id,
                "reason_code": body.reason_code,
                "notes_present": bool((body.notes or "").strip()),
            },
        )

    return ChatHandoffResponse(handoff_id=handoff_id, status="OPEN")


@router.get("/sessions/{session_id}/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> ChatHistoryResponse:
    """Return full conversation history for a session. 404 if session does not exist."""
    existing = await prisma.chatsession.find_unique(where={"id": session_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found")
    raw = await get_full_history(prisma, session_id)
    feedback_map = await get_latest_feedback_map(
        prisma,
        session_id=session_id,
        user_id=current_user.id,
    )
    for item in raw:
        if item.get("role") != "assistant":
            continue
        message_id = item.get("id")
        if isinstance(message_id, str):
            item["feedback_type"] = feedback_map.get(message_id)
    messages = [ChatMessageOut(**m) for m in raw]
    latest_trace = await get_latest_assistant_trace(prisma, session_id)
    return ChatHistoryResponse(messages=messages, latest_trace=latest_trace)


@router.get("/learning/preferences", response_model=LearningPreferencesOut)
async def get_learning_preferences_endpoint(
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> LearningPreferencesOut:
    prefs = await get_learning_preferences(
        prisma,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
    )
    return LearningPreferencesOut(**prefs)


@router.put("/learning/preferences", response_model=LearningPreferencesOut)
async def put_learning_preferences_endpoint(
    body: LearningPreferencesUpdateRequest,
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> LearningPreferencesOut:
    prefs = await upsert_learning_preferences(
        prisma,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
        long_term_personalization_opt_in=body.long_term_personalization_opt_in,
        telemetry_learning_opt_in=body.telemetry_learning_opt_in,
    )
    return LearningPreferencesOut(**prefs)


@router.get("/ops/dashboard", response_model=OpsDashboardResponse)
async def get_ops_dashboard_endpoint(
    days: Optional[int] = None,
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> OpsDashboardResponse:
    del current_user
    settings = get_settings()
    if not settings.ENABLE_OPS_DASHBOARD:
        raise HTTPException(status_code=503, detail="Ops dashboard is disabled.")
    payload = await get_ops_dashboard(
        prisma,
        days=int(days or settings.OPS_DASHBOARD_DEFAULT_DAYS),
    )
    return OpsDashboardResponse(**payload)


@router.get("/ops/release/status", response_model=ReleaseStatusResponse)
async def get_release_status_endpoint(
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> ReleaseStatusResponse:
    del current_user
    settings = get_settings()
    if not settings.ENABLE_RELEASE_CONTROLS:
        raise HTTPException(status_code=503, detail="Release controls are disabled.")
    payload = await get_release_status(prisma)
    return ReleaseStatusResponse(**payload)


@router.post("/ops/release/golden-run", response_model=GoldenRunResponse)
async def post_release_golden_run(
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> GoldenRunResponse:
    settings = get_settings()
    if not settings.ENABLE_RELEASE_CONTROLS:
        raise HTTPException(status_code=503, detail="Release controls are disabled.")
    payload = await run_golden_gate(
        prisma,
        triggered_by_user_id=current_user.id,
        min_pass_rate=float(settings.RELEASE_GOLDEN_MIN_PASS_RATE),
        run_window_days=int(settings.OPS_DASHBOARD_DEFAULT_DAYS),
    )
    return GoldenRunResponse(**payload)


@router.post("/ops/release/canary/start", response_model=CanaryStartResponse)
async def post_release_canary_start(
    body: CanaryStartRequest,
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> CanaryStartResponse:
    settings = get_settings()
    if not settings.ENABLE_RELEASE_CONTROLS:
        raise HTTPException(status_code=503, detail="Release controls are disabled.")
    dimension = (body.experiment_dimension or "wrqs_weights").strip()
    if not is_experiment_dimension_allowed(dimension):
        raise HTTPException(
            status_code=400,
            detail="Only WRQS weights and response style dimensions are allowed.",
        )
    payload = await start_canary_rollout(
        prisma,
        settings=settings,
        triggered_by_user_id=current_user.id,
        canary_percent=int(body.canary_percent or settings.RELEASE_CANARY_DEFAULT_PERCENT),
    )
    return CanaryStartResponse(**payload)


@router.post("/ops/release/canary/rollback", response_model=CanaryRollbackResponse)
async def post_release_canary_rollback(
    body: CanaryRollbackRequest,
    prisma: Prisma = Depends(get_prisma),
    current_user: UserOut = Depends(get_current_user),
) -> CanaryRollbackResponse:
    del current_user
    settings = get_settings()
    if not settings.ENABLE_RELEASE_CONTROLS:
        raise HTTPException(status_code=503, detail="Release controls are disabled.")
    payload = await evaluate_canary_and_maybe_rollback(
        prisma,
        settings=settings,
        notes=body.notes,
    )
    return CanaryRollbackResponse(**payload)
