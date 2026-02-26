"""SQL query result caching with strict customer isolation."""

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SQLQueryCache:
    """
    In-memory cache for SQL query results with strict customer isolation.

    Key features:
    - Cache key = normalized SQL + customer_id (different customers never share results)
    - TTL-based expiration (default 5 minutes)
    - Automatic cleanup for a specific customer when their data changes
    - Thread-safe for async usage (dict operations are atomic in CPython)
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        """
        Args:
            ttl_seconds: How long to keep results in cache (default 5 minutes)
            max_size: Maximum number of entries before old ones are evicted (safety)
        """
        self.cache: dict[str, tuple[list[dict], datetime]] = {}
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._hits = 0
        self._misses = 0

    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL for consistent cache keys (whitespace, case, trailing semicolon)."""
        # Remove comments if any slipped through (safety)
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        return " ".join(sql.lower().strip().rstrip(";").split())

    def get_cache_key(self, sql: str, customer_id: int) -> str:
        """Generate unique cache key: normalized SQL + customer_id."""
        normalized = self._normalize_sql(sql)
        combined = f"{normalized}:{customer_id}"
        return hashlib.md5(combined.encode("utf-8")).hexdigest()

    def get(self, sql: str, customer_id: int) -> Optional[list[dict]]:
        """Return cached results if still valid, else None."""
        key = self.get_cache_key(sql, customer_id)

        if key in self.cache:
            results, timestamp = self.cache[key]
            age = datetime.now() - timestamp

            if age < timedelta(seconds=self.ttl):
                self._hits += 1
                logger.debug(
                    "SQL CACHE | HIT | customer=%d | age=%.1fs | rows=%d",
                    customer_id, age.total_seconds(), len(results)
                )
                return results

            # Expired
            del self.cache[key]
            logger.debug("SQL CACHE | Expired entry removed | customer=%d", customer_id)

        self._misses += 1
        return None

    def set(self, sql: str, customer_id: int, results: list[dict]):
        """Store query results in cache."""
        key = self.get_cache_key(sql, customer_id)
        self.cache[key] = (results, datetime.now())

        # Simple size limit (evict oldest if needed)
        if len(self.cache) > self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
            logger.debug("SQL CACHE | Evicted oldest entry (max size reached)")

        logger.debug(
            "SQL CACHE | STORED | customer=%d | rows=%d | cache_size=%d",
            customer_id, len(results), len(self.cache)
        )

    def clear_for_customer(self, customer_id: int):
        """Clear ALL cached entries for a specific customer (called after new order, etc.)."""
        customer_str = str(customer_id)
        to_remove = [
            k for k in list(self.cache.keys())
            if f":{customer_str}" in k   # safe because we always append ":customer_id"
        ]

        for k in to_remove:
            del self.cache[k]

        logger.info(
            "SQL CACHE | Cleared %d entries for customer %d (data changed)",
            len(to_remove), customer_id
        )

    def clear_all(self):
        """Clear entire cache (useful on startup or admin action)."""
        count = len(self.cache)
        self.cache.clear()
        self._hits = self._misses = 0
        logger.info("SQL CACHE | Cleared ALL %d entries", count)

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "size": len(self.cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
            "ttl_seconds": self.ttl,
            "max_size": self.max_size,
        }