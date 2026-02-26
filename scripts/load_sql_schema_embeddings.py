#!/usr/bin/env python3
"""
Load schema embeddings into Qdrant collection "sql-agent" for the SQL Agent API.
Uses schema_chunker for logical units (table definitions, relationships, security rules,
query patterns) and schema_loader for Prisma-backed context. Run this once (or after
schema changes) to enable RAG-based schema retrieval in the SQL Agent API.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams, OptimizersConfigDiff

from app.core.config import get_settings
from app.core.qdrant import create_qdrant_client
from app.services.schema_chunker import generate_all_chunks

COLLECTION_NAME = "sql-agent"
BATCH_EMBED_SIZE = 16

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _embed_batch(url: str, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url.rstrip("/"), json={"text": texts})
        r.raise_for_status()
        data = r.json()
    if "embedding" in data:
        emb = data["embedding"]
        return emb if isinstance(emb[0], list) else [emb]
    if "embeddings" in data:
        return data["embeddings"]
    if "data" in data:
        return [d["embedding"] for d in data["data"]]
    raise ValueError("Unknown embedding response")


def ensure_collection(client: QdrantClient, name: str, dim: int, recreate: bool) -> None:
    collections = [c.name for c in client.get_collections().collections]
    if recreate and name in collections:
        client.delete_collection(name)
        logger.info("Deleted existing collection %s", name)
    if name not in collections or recreate:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=0),
        )
        logger.info("Created collection %s (dim=%d)", name, dim)


def wait_for_indexing(client: QdrantClient, collection: str, timeout_seconds: int = 60) -> None:
    logger.info("Building vector index...")
    client.update_collection(
        collection_name=collection,
        optimizers_config=OptimizersConfigDiff(indexing_threshold=1),
    )
    for _ in range(timeout_seconds):
        info = client.get_collection(collection)
        logger.info("Index progress %d/%d", info.indexed_vectors_count, info.points_count)
        if info.points_count > 0 and info.indexed_vectors_count >= info.points_count:
            logger.info("Semantic search READY")
            return
        time.sleep(1)
    logger.warning("Indexing may still be in progress after %ds", timeout_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load schema RAG embeddings into Qdrant (collection: sql-agent) for SQL Agent API."
    )
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate the collection")
    args = parser.parse_args()

    settings = get_settings()
    client = create_qdrant_client()
    dim = settings.EMBEDDING_DIMENSION

    ensure_collection(client, COLLECTION_NAME, dim, args.recreate)

    chunks = generate_all_chunks()
    if not chunks:
        logger.error("No chunks generated from schema chunker")
        sys.exit(1)

    texts = [c["content"] for c in chunks]
    vectors = []
    for i in range(0, len(texts), BATCH_EMBED_SIZE):
        batch = texts[i : i + BATCH_EMBED_SIZE]
        vectors.extend(_embed_batch(settings.EMBEDDING_URL, batch))
        logger.info("Embedded batch %d-%d/%d", i + 1, min(i + len(batch), len(texts)), len(texts))

    if len(vectors) != len(chunks):
        logger.error("Vector count %d != chunk count %d", len(vectors), len(chunks))
        sys.exit(1)

    points = [
        PointStruct(
            id=c["id"],
            vector=vec,
            payload={"content": c["content"], **c["metadata"]},
        )
        for c, vec in zip(chunks, vectors)
    ]
    client.upsert(COLLECTION_NAME, points)
    logger.info("Upserted %d schema chunks to %s", len(points), COLLECTION_NAME)

    wait_for_indexing(client, COLLECTION_NAME)
    logger.info("DONE — %d schema RAG chunks indexed in %s", len(points), COLLECTION_NAME)


if __name__ == "__main__":
    main()
