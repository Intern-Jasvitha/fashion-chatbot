"""Async embedding client for query-time vectors (same API as scripts/load_pdf_rag.py)."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EMBED_TIMEOUT = 60.0


def _parse_embedding_response(data: dict[str, Any], texts_count: int) -> list[list[float]]:
    """Parse embedding API response; support embedding, embeddings, or data[].embedding."""
    if "embedding" in data:
        emb = data["embedding"]
        return emb if isinstance(emb[0], list) else [emb]
    if "embeddings" in data:
        return data["embeddings"]
    if "data" in data:
        return [d["embedding"] for d in data["data"]]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unknown embedding API response: {list(data.keys())}")


async def embed_query(embedding_url: str, query: str) -> list[float]:
    """Embed a single query string. Returns a vector (list of floats).

    Uses the same API contract as scripts/load_pdf_rag.py: POST with {"text": [query]}.
    """
    url = embedding_url.rstrip("/")
    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        response = await client.post(url, json={"text": [query]})
        response.raise_for_status()
        data = response.json()

    vectors = _parse_embedding_response(data, 1)
    if not vectors:
        raise ValueError("Embedding API returned no vector")
    return vectors[0]


async def embed_batch(embedding_url: str, texts: list[str]) -> list[list[float]]:
    """Embed multiple texts. Returns list of vectors."""
    if not texts:
        return []
    url = embedding_url.rstrip("/")
    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        response = await client.post(url, json={"text": texts})
        response.raise_for_status()
        data = response.json()
    return _parse_embedding_response(data, len(texts))
