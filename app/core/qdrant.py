"""Qdrant client factory and dependency."""

from qdrant_client import QdrantClient

from app.core.config import get_settings


def create_qdrant_client() -> QdrantClient:
    """Create a Qdrant client (host/port for Docker or local)."""
    settings = get_settings()
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
