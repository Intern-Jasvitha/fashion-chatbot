"""Minimal LLM chat client for intent classification and other LLM calls.

Sends HTTP requests to the configured LLAMA_URL. Supports OpenAI-compatible
payloads (messages array) and parses both OpenAI-style and simple response
formats so you can adapt to your local server (llama.cpp, LiteLLM, Ollama, etc.)
without changing the rest of the code.
"""

import logging
from typing import Any, List, Optional

import httpx
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Default timeout for chat completion
CHAT_TIMEOUT = 60.0


def _messages_to_llama_format(messages: list[dict[str, str]]) -> dict[str, str]:
    """Convert messages array to { message, system_prompt } for Llama-style APIs.
    When there are multiple turns (conversation history), fold them into the user message
    so the model has full context."""
    system_parts = []
    turns = []
    for m in messages:
        role = (m.get("role") or "").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
        else:
            turns.append((role, content))
    system_prompt = "\n\n".join(system_parts) if system_parts else ""
    if len(turns) <= 1:
        user_message = turns[0][1] if turns else ""
    else:
        history_blob = "\n".join(f"{r}: {c}" for r, c in turns[:-1])
        user_message = f"Previous conversation:\n{history_blob}\n\nCurrent message: {turns[-1][1]}"
    return {"message": user_message, "system_prompt": system_prompt or "You are a helpful assistant."}


async def chat(
    messages: list[dict[str, str]],
    url: str,
    temperature: float = 0.0,
    seed: int = 42,
) -> str:
    """Send messages to the chat endpoint and return the assistant reply as text.

    Args:
        messages: List of dicts with "role" and "content"
        url: Full URL of the chat API (from settings.LLAMA_URL)
        temperature: Controls randomness (0.0 = deterministic, 1.0 = creative). Default 0.0 for SQL planning.
        seed: Random seed for reproducible sampling when temperature is 0. Default 42.

    Returns:
        The assistant reply content as a string.
    """
    is_openai = "/v1/chat/completions" in url or "openai" in url.lower()

    # Fully deterministic when temperature is 0: top_p=0.0, seed for reproducibility
    top_p = 0.0 if temperature == 0.0 else 0.95

    if is_openai:
        # OpenAI-compatible endpoint (vLLM, LiteLLM, OpenAI itself)
        payload: dict[str, Any] = {
            "messages": messages,
            "model": "default",  # or your model name
            "temperature": temperature,
            "max_tokens": 2048,
            "top_p": top_p,
            "top_k": 1,
            "seed": seed,
        }
    else:
        # Llama-style / simple endpoint (llama.cpp server, etc.)
        payload = _messages_to_llama_format(messages)
        payload["temperature"] = temperature
        payload["top_p"] = top_p
        payload["top_k"] = 1
        payload["seed"] = seed

    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    # OpenAI-style response parsing
    if "choices" in data and len(data["choices"]) > 0:
        msg = data["choices"][0].get("message") or data["choices"][0]
        content = msg.get("content") if isinstance(msg, dict) else None
        if content is not None:
            return content.strip() if isinstance(content, str) else str(content)

    # Simple format fallback
    for key in ("content", "message", "text", "response", "output"):
        if key in data:
            c = data[key]
            return (c.strip() if isinstance(c, str) else str(c))

    raise ValueError(f"Could not extract assistant content from response: {list(data.keys())}")

def _lc_messages_to_dict(messages: List[BaseMessage]) -> list[dict[str, str]]:
    """Convert LangChain messages to list of role/content dicts for chat()."""
    out: list[dict[str, str]] = []
    for m in messages:
        role = "user"
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        elif isinstance(m, SystemMessage):
            role = "system"
        content = m.content if isinstance(m.content, str) else str(m.content)
        out.append({"role": role, "content": content})
    return out


class ChatModelViaHTTP(BaseChatModel):
    """LangChain chat model wrapping the existing HTTP chat() endpoint."""

    url: str = Field(description="Full URL of the chat API")
    timeout: float = Field(default=CHAT_TIMEOUT, description="Request timeout in seconds")

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "chat_via_http"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            self._agenerate(messages, stop, run_manager, **kwargs)
        )

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        msgs = _lc_messages_to_dict(messages)
        content = await chat(msgs, self.url)
        message = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=message)])


def get_langchain_llm(settings: Settings) -> BaseChatModel:
    """Return a LangChain chat model for use in graph nodes. Supports both OpenAI-compatible and Llama-style APIs."""
    return ChatModelViaHTTP(url=settings.LLAMA_URL, timeout=CHAT_TIMEOUT)
