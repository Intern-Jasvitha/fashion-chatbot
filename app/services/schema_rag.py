"""RAG-based schema retrieval from Qdrant sql-agent collection for SQL Agent API.

This is a standalone RAG service - it does NOT fall back to schema_loader.
It requires the sql-agent Qdrant collection to be populated.
"""

import logging
from typing import Optional

from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.core.embeddings import embed_query

logger = logging.getLogger(__name__)

SQL_AGENT_COLLECTION = "sql-agent"
DEFAULT_TOP_K = 10


class SchemaRAGError(Exception):
    """Raised when schema RAG retrieval fails."""
    pass


async def retrieve_schema_context(
    query: str,
    settings: Settings,
    qdrant: QdrantClient,
    top_k: int = DEFAULT_TOP_K,
) -> str:
    """
    Retrieve relevant schema context for a user query from Qdrant sql-agent collection.
    This is RAG-only - no fallback to static schema loader.
    
    Raises SchemaRAGError if:
    - Collection is missing
    - Embedding service fails
    - Search fails
    - No results found
    """
    logger.info("Schema RAG: Starting retrieval for query: %s (top_k=%d)", query[:100], top_k)
    
    # Step 1: Check collection exists
    try:
        logger.info("Schema RAG: Checking if collection '%s' exists in Qdrant", SQL_AGENT_COLLECTION)
        collections = qdrant.get_collections().collections
        collection_names = [c.name for c in collections]
        logger.info("Schema RAG: Available collections: %s", collection_names)
        
        if not any(c.name == SQL_AGENT_COLLECTION for c in collections):
            error_msg = (
                f"Collection '{SQL_AGENT_COLLECTION}' not found in Qdrant. "
                f"Run 'python scripts/load_sql_schema_embeddings.py' to populate it."
            )
            logger.error("Schema RAG: %s", error_msg)
            raise SchemaRAGError(error_msg)
        
        logger.info("Schema RAG: Collection '%s' found", SQL_AGENT_COLLECTION)
    except SchemaRAGError:
        raise
    except Exception as e:
        error_msg = f"Failed to list Qdrant collections: {e}"
        logger.error("Schema RAG: %s", error_msg)
        raise SchemaRAGError(error_msg) from e

    # Step 2: Embed query
    try:
        logger.info("Schema RAG: Embedding query via %s", settings.EMBEDDING_URL)
        query_vector = await embed_query(settings.EMBEDDING_URL, query)
        logger.info("Schema RAG: Query embedded successfully (dim=%d)", len(query_vector))
    except Exception as e:
        error_msg = (
            f"Embedding service failed at {settings.EMBEDDING_URL}: {e}. "
            f"Make sure the embedding service is running."
        )
        logger.error("Schema RAG: %s", error_msg)
        raise SchemaRAGError(error_msg) from e

    # Step 3: Search Qdrant
    try:
        logger.info("Schema RAG: Searching collection '%s' for top %d matches", SQL_AGENT_COLLECTION, top_k)
        response = qdrant.query_points(
            collection_name=SQL_AGENT_COLLECTION,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )
        results = response.points if hasattr(response, 'points') else response
        logger.info("Schema RAG: Search returned %d results", len(results))
    except Exception as e:
        error_msg = f"Qdrant search failed: {e}"
        logger.error("Schema RAG: %s", error_msg)
        raise SchemaRAGError(error_msg) from e

    if not results:
        error_msg = (
            f"No schema chunks found for query. The collection may be empty. "
            f"Run 'python scripts/load_sql_schema_embeddings.py' to populate it."
        )
        logger.error("Schema RAG: %s", error_msg)
        raise SchemaRAGError(error_msg)

    # Step 4: Extract and deduplicate content
    parts = []
    seen: set[str] = set()
    for idx, hit in enumerate(results):
        payload = hit.payload or {}
        content = payload.get("content")
        score = hit.score
        chunk_type = payload.get("type", "unknown")
        
        logger.info(
            "Schema RAG: Hit %d - score=%.4f, type=%s, content_len=%d",
            idx + 1, score, chunk_type, len(content) if content else 0
        )
        
        if content and content.strip() and content not in seen:
            seen.add(content)
            parts.append(content.strip())

    if not parts:
        error_msg = "All retrieved chunks were empty or duplicates"
        logger.error("Schema RAG: %s", error_msg)
        raise SchemaRAGError(error_msg)

    context = "\n\n---\n\n".join(parts)
    logger.info("Schema RAG: Successfully retrieved %d unique chunks (%d chars total)", len(parts), len(context))
    
    return (
        "Relevant schema context (retrieved by semantic similarity to your question):\n\n"
        + context
        + "\n\nUse ONLY the tables and columns described above. If something is missing, infer from the names."
    )
