"""LLM Response Cache for reducing redundant API calls.

Provides an in-memory LRU cache with TTL expiration for LLM responses.
Useful for caching identical requests during parallel agent operations.
"""

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from litellm import ModelResponse


logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached LLM response with metadata."""

    response: ModelResponse
    created_at: float
    hits: int = 0


class ResponseCache:
    """Thread-safe LRU cache for LLM responses with TTL expiration."""

    def __init__(
        self,
        max_size: int | None = None,
        ttl_seconds: float | None = None,
        enabled: bool | None = None,
    ):
        self.max_size = max_size or int(os.environ.get("LLM_CACHE_MAX_SIZE", "100"))
        self.ttl_seconds = ttl_seconds or float(os.environ.get("LLM_CACHE_TTL", "3600"))

        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = os.environ.get("LLM_CACHE_ENABLED", "true").lower() == "true"

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _generate_key(self, model: str, messages: list[dict[str, Any]]) -> str:
        """Generate a deterministic cache key from request parameters."""
        # Create a hashable representation of the request
        key_data = {
            "model": model,
            "messages": messages,
        }
        key_json = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_json.encode()).hexdigest()[:32]

    def get(self, model: str, messages: list[dict[str, Any]]) -> ModelResponse | None:
        """Get a cached response if available and not expired."""
        if not self.enabled:
            return None

        key = self._generate_key(model, messages)

        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[key]

            # Check TTL expiration
            if time.time() - entry.created_at > self.ttl_seconds:
                del self._cache[key]
                self._stats["misses"] += 1
                self._stats["evictions"] += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.hits += 1
            self._stats["hits"] += 1

            logger.debug(f"Cache hit for key {key[:8]}... (hits: {entry.hits})")
            return entry.response

    def put(self, model: str, messages: list[dict[str, Any]], response: ModelResponse) -> None:
        """Cache a response."""
        if not self.enabled:
            return

        key = self._generate_key(model, messages)

        with self._lock:
            # Remove oldest entries if at capacity
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats["evictions"] += 1

            self._cache[key] = CacheEntry(
                response=response,
                created_at=time.time(),
            )

            logger.debug(f"Cached response for key {key[:8]}... (cache size: {len(self._cache)})")

    def invalidate(self, model: str | None = None) -> int:
        """Invalidate cache entries, optionally filtered by model.

        Returns the number of entries invalidated.
        """
        with self._lock:
            if model is None:
                count = len(self._cache)
                self._cache.clear()
                return count

            # Would need to store model in entry to filter - for now just clear all
            count = len(self._cache)
            self._cache.clear()
            return count

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    @property
    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        with self._lock:
            hit_rate = 0.0
            total = self._stats["hits"] + self._stats["misses"]
            if total > 0:
                hit_rate = self._stats["hits"] / total

            return {
                **self._stats,
                "size": len(self._cache),
                "hit_rate": round(hit_rate, 3),
            }


# Global cache instance
_global_cache: ResponseCache | None = None


def get_global_cache() -> ResponseCache:
    """Get the global response cache instance."""
    global _global_cache  # noqa: PLW0603
    if _global_cache is None:
        _global_cache = ResponseCache()
    return _global_cache
