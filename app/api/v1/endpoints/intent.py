"""Intent detection endpoint: POST /intent returns which agent to call (sql, rag, hybrid)."""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.llm import chat
from app.schemas.intent import IntentRequest, IntentResponse
from app.services.intent_router import detect_intent

router = APIRouter(prefix="/intent", tags=["intent"])


@router.post("", response_model=IntentResponse)
async def post_detect_intent(
    body: IntentRequest,
    settings: Settings = Depends(get_settings),
) -> IntentResponse:
    """Detect which agent (sql, rag, hybrid) should handle the user message. Detection only."""
    intent = await detect_intent(body.message, chat, settings)
    return IntentResponse(intent=intent.value)
