"""Voice API: TTS endpoint for agent response playback."""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user_optional
from app.core.config import get_settings
from app.schemas.auth import UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class TTSRequest(BaseModel):
    """Request body for TTS endpoint."""

    text: str = Field(..., min_length=1, max_length=4096, description="Text to synthesize")


@router.post("/tts")
async def text_to_speech(
    body: TTSRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional),
):
    """Convert text to speech. Uses VibeVoice when ISVIBEVOICE=true, else OpenAI TTS. Returns audio."""
    del current_user  # Optional auth; works for both guest and authenticated
    settings = get_settings()
    logger.info("TTS using %s", "VibeVoice" if settings.ISVIBEVOICE else "OpenAI")

    if settings.ISVIBEVOICE:
        url = f"{settings.VIBEVOICE_URL.rstrip('/')}/tts"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"text": body.text},
            )
            if response.status_code != 200:
                logger.warning("VibeVoice TTS failed: %s", response.text)
                raise HTTPException(status_code=502, detail="TTS synthesis failed")
            media_type = response.headers.get("content-type") or "audio/mpeg"
            return Response(content=response.content, media_type=media_type)

    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "voice": "alloy",
                "input": body.text,
            },
        )
        if response.status_code != 200:
            logger.warning("OpenAI TTS failed: %s", response.text)
            raise HTTPException(status_code=502, detail="TTS synthesis failed")

        return Response(content=response.content, media_type="audio/mpeg")
