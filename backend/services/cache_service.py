"""High-performance caching service with LRU L1 (in-memory) + Redis L2 (shared).

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │                   CacheService                      │
  │  ┌────────────────────────────┐  ┌───────────────┐ │
  │  │  L1: In-Memory LRU Cache   │  │  L2: Redis    │ │
  │  │  (OrderedDict, fastest)    │  │  (shared,     │ │
  │  │   - Configurable max size  │  │   persistent) │ │
  │  │   - Auto-evicts LRU first  │  │  - TTL expiry │ │
  │  │   - Thread-safe via lock   │  │  - Cross-     │ │
  │  └────────────────────────────┘  │   process     │ │
  │                                  │  - Pickle     │ │
  │   get(key): L1 -> L2 -> None     │   serialized  │ │
  │   set(key): L1 + L2 async        └───────────────┘ │
  └─────────────────────────────────────────────────────┘

Features:
- L1: LRU eviction, TTL, memory-aware size tracking
- L2: Redis with pickle serialization, async connection pool, TTL
- Graceful Redis fallback (logs warning, continues with L1 only)
- Hit/miss statistics (L1 hits, L2 restores, misses)
- Connection pooling with configurable pool size
- Background TTL pruning for L1
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import pickle
import time
from collections import OrderedDict
from typing import Any, Optional

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Memory Size Estimation ──────────────────────────────────────────────


def _estimate_size(obj: Any) -> int:
    """Roughly estimate the memory size of an object in bytes."""
    try:
        if isinstance(obj, str):
            return len(obj.encode("utf-8"))
        if isinstance(obj, bytes):
            return len(obj)
        if isinstance(obj, dict):
            return sum(_estimate_size(v) for v in obj.values()) + len(obj) * 64
        if isinstance(obj, list):
            return sum(_estimate_size(v) for v in obj) + len(obj) * 8
        if hasattr(obj, "__sizeof__"):
            return obj.__sizeof__()
        return len(str(obj))
    except Exception:
        return 1024


# ── Cache Entry ─────────────────────────────────────────────────────────


class CacheEntry:
    """A single cache entry with metadata for L1 tracking."""

    __slots__ = ("key", "value", "size", "created_at", "accessed_at", "ttl")

    def __init__(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        self.key = key
        self.value = value
        self.size = _estimate_size(value)
        self.created_at = time.monotonic()
        self.accessed_at = self.created_at
        self.ttl = ttl

    @property
    def is_expired(self) -> bool:
        if self.ttl is None or self.ttl <= 0:
            return False
        return (time.monotonic() - self.created_at) > self.ttl

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at


# ── Redis Cache Backend (L2) ────────────────────────────────────────────


class RedisCacheBackend:
    """Redis-based L2 cache backend with async connection pool.

    Uses pickle serialization for complex Python objects.
    TTL is set at the Redis key level for automatic expiry.
    Falls back gracefully if Redis is unavailable.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        pool_size: int = 10,
        key_prefix: str = "manga_cache:",
        default_ttl: int = 3600,
        connect_timeout: float = 3.0,
    ) -> None:
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.connect_timeout = connect_timeout

        self._pool: Optional[Any] = None  # redis.asyncio.ConnectionPool
        self._redis: Optional[Any] = None  # redis.asyncio.Redis
        self._available = False
        self._pool_size = pool_size
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Initialize the Redis connection pool.

        Returns True if Redis is available, False otherwise.
        Logs a warning if Redis is not reachable — the cache will
        continue operating with L1 only.
        """
        if self._available:
            return True

        async with self._lock:
            if self._available:
                return True

            try:
                import redis.asyncio as aioredis

                self._pool = aioredis.ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=self._pool_size,
                    timeout=self.connect_timeout,
                    socket_connect_timeout=self.connect_timeout,
                    socket_keepalive=True,
                    retry_on_timeout=True,
                    decode_responses=False,  # Keep bytes for pickle
                )
                self._redis = aioredis.Redis.from_pool(self._pool)

                # Quick connectivity check
                await self._redis.ping()
                self._available = True
                info = await self._redis.info("server")
                redis_version = info.get("redis_version", "unknown")
                logger.info(
                    "Redis cache backend connected: %s (v%s, pool=%d)",
                    self.redis_url.split("@")[-1] if "@" in self.redis_url else self.redis_url,
                    redis_version,
                    self._pool_size,
                )
                return True

            except Exception as e:
                logger.warning(
                    "Redis unavailable at %s: %s. "
                    "Cache will operate with L1 (in-memory) only. "
                    "Install redis-py and start Redis for multi-process caching.",
                    self.redis_url.split("@")[-1] if "@" in self.redis_url else self.redis_url,
                    e,
                )
                self._available = False
                self._pool = None
                self._redis = None
                return False

    def _make_key(self, key: str) -> str:
        """Prefix a cache key to avoid collisions with other Redis data."""
        # Sanitize key for Redis
        safe_key = key.replace("\n", "").replace("\r", "")
        if len(safe_key) > 500:
            safe_key = hashlib.md5(key.encode()).hexdigest()
        return f"{self.key_prefix}{safe_key}"

    def _serialize(self, entry: CacheEntry) -> bytes:
        """Serialize a CacheEntry for Redis storage using pickle."""
        return pickle.dumps(
            {
                "key": entry.key,
                "value": entry.value,
                "created_at": entry.created_at,
                "ttl": entry.ttl,
                "timestamp": time.time(),
            },
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    def _deserialize(self, data: bytes) -> Optional[CacheEntry]:
        """Deserialize Redis data back into a CacheEntry."""
        try:
            raw = pickle.loads(data)
            entry = CacheEntry(raw["key"], raw["value"], raw.get("ttl"))
            entry.created_at = raw.get("created_at", entry.created_at)
            return entry
        except Exception as e:
            logger.debug("Redis deserialize failed: %s", e)
            return None

    async def save(self, key: str, entry: CacheEntry) -> None:
        """Save a cache entry to Redis with TTL."""
        if not await self._ensure_available():
            return

        try:
            rkey = self._make_key(key)
            data = self._serialize(entry)
            ttl = int(entry.ttl) if entry.ttl and entry.ttl > 0 else self.default_ttl
            await self._redis.setex(rkey, ttl, data)
        except Exception as e:
            logger.debug("Redis save failed for %s: %s", key[:50], e)
            self._available = False

    async def load(self, key: str) -> Optional[CacheEntry]:
        """Load a cache entry from Redis.

        Returns None if not found, expired, or Redis is unavailable.
        """
        if not await self._ensure_available():
            return None

        try:
            rkey = self._make_key(key)
            data = await self._redis.get(rkey)
            if data is None:
                return None
            return self._deserialize(data)
        except Exception as e:
            logger.debug("Redis load failed for %s: %s", key[:50], e)
            self._available = False
            return None

    async def _ensure_available(self) -> bool:
        """Check if Redis is available, with auto-reconnect if previously down.

        Returns True if Redis is available for use.
        """
        if self._available and self._redis is not None:
            return True

        # Try to reconnect if previously marked unavailable
        if not self._available and self._pool is not None:
            try:
                await self._redis.ping()
                self._available = True
                logger.info("Redis reconnected")
                return True
            except Exception:
                pass

        # Try full reconnect if pool is gone
        if self._redis is None or self._pool is None:
            return await self.connect()

        return False

    async def delete(self, key: str) -> None:
        """Delete a key from Redis."""
        if not await self._ensure_available():
            return
        try:
            rkey = self._make_key(key)
            await self._redis.delete(rkey)
        except Exception:
            pass

    async def clear(self) -> int:
        """Clear all cache entries from Redis that match our prefix.

        Returns the count of deleted keys, or -1 if unknown.
        """
        if not await self._ensure_available():
            return 0

        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f"{self.key_prefix}*", count=100
                )
                if keys:
                    deleted += await self._redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info("Redis cache cleared: %d keys deleted", deleted)
            return deleted
        except Exception as e:
            logger.warning("Redis clear failed: %s", e)
            return -1

    async def prune_expired(self) -> int:
        """Redis handles TTL expiry automatically — no manual pruning needed."""
        return 0

    async def get_key_count(self) -> int:
        """Get the approximate number of cached keys in Redis."""
        if not await self._ensure_available():
            return 0
        try:
            cursor = 0
            count = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f"{self.key_prefix}*", count=500
                )
                count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception:
            return -1

    async def scan_keys(self, batch_size: int = 50) -> list[bytes]:
        """Scan all keys matching this cache's prefix.

        Returns list of raw Redis key bytes.
        """
        if not await self._ensure_available():
            return []
        try:
            cursor = 0
            all_keys: list[bytes] = []
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f"{self.key_prefix}*", count=batch_size
                )
                all_keys.extend(keys)
                if cursor == 0:
                    break
            return all_keys
        except Exception:
            self._available = False
            return []

    async def get_raw(self, key: bytes) -> Optional[bytes]:
        """Get raw bytes from Redis by key."""
        if not await self._ensure_available():
            return None
        try:
            return await self._redis.get(key)
        except Exception:
            self._available = False
            return None

    async def deserialize(self, data: bytes) -> Optional[CacheEntry]:
        """Public helper to deserialize Redis data into a CacheEntry."""
        return self._deserialize(data)

    async def get_info(self) -> dict[str, Any]:
        """Get Redis server info for monitoring."""
        if not await self._ensure_available():
            return {"available": False}
        try:
            info = await self._redis.info("server")
            memory = await self._redis.info("memory")
            return {
                "available": True,
                "redis_version": info.get("redis_version", "unknown"),
                "used_memory_human": memory.get("used_memory_human", "unknown"),
                "used_memory_peak_human": memory.get("used_memory_peak_human", "unknown"),
                "key_count": await self.get_key_count(),
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception:
                pass
            self._pool = None
            self._redis = None
            self._available = False
            logger.info("Redis cache backend disconnected")


# ── Cache Service (L1 + L2) ─────────────────────────────────────────────


class CacheService:
    """High-performance caching service with L1 (in-memory LRU) + L2 (Redis).

    Usage:
        cache = CacheService(name="ocr", max_size_mb=50)
        await cache.start()  # Connects to Redis
        await cache.set("key", value, ttl=600)
        result = await cache.get("key")
        await cache.stop()
    """

    def __init__(
        self,
        name: str = "default",
        max_size_mb: int = 256,
        default_ttl_seconds: int = 3600,
        enable_redis: bool = True,
        redis_url: Optional[str] = None,
        prune_interval_seconds: int = 300,
    ) -> None:
        self.name = name
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._default_ttl = default_ttl_seconds
        self._prune_interval = prune_interval_seconds

        # L1: In-memory LRU cache (fastest)
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._current_size: int = 0
        self._lock = asyncio.Lock()

        # Statistics
        self.hits: int = 0
        self.misses: int = 0
        self.evictions: int = 0
        self.l2_restores: int = 0  # L2 (Redis) → L1 restorations

        # L2: Redis backend
        self._redis_backend: Optional[RedisCacheBackend] = None
        self._enable_redis = enable_redis

        if enable_redis:
            effective_redis_url = redis_url or settings.REDIS_URL
            self._redis_backend = RedisCacheBackend(
                redis_url=effective_redis_url,
                pool_size=settings.REDIS_POOL_SIZE,
                key_prefix=f"manga_cache:{name}:",
                default_ttl=default_ttl_seconds,
                connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            )

        # Background tasks
        self._prune_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            "Cache '%s': max=%dMB, ttl=%ds, redis=%s",
            name, max_size_mb, default_ttl_seconds,
            "enabled" if enable_redis else "disabled",
        )

    async def start(self) -> None:
        """Start background tasks and connect to Redis."""
        if self._running:
            return
        self._running = True

        # Connect to Redis
        if self._redis_backend is not None:
            await self._redis_backend.connect()

        # Start background prune loop for L1
        self._prune_task = asyncio.create_task(self._prune_loop())
        logger.debug("Cache '%s' started", self.name)

    async def stop(self) -> None:
        """Stop background tasks and disconnect Redis."""
        self._running = False
        if self._prune_task:
            self._prune_task.cancel()
            try:
                await self._prune_task
            except asyncio.CancelledError:
                pass

        if self._redis_backend is not None:
            await self._redis_backend.close()

        logger.debug("Cache '%s' stopped", self.name)

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache.

        Lookup order: L1 (in-memory) → L2 (Redis) → None.
        If found in L2, restores to L1 for faster subsequent access.

        Args:
            key: Cache key string.

        Returns:
            Cached value or None.
        """
        # ── L1: In-memory check ──────────────────────────────────────────
        async with self._lock:
            entry = self._cache.get(key)

            if entry is not None:
                if entry.is_expired:
                    self._cache.pop(key, None)
                    self._current_size -= entry.size
                    self.misses += 1
                    return None
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                entry.accessed_at = time.monotonic()
                self.hits += 1
                return entry.value

        # ── L2: Redis check (load() handles auto-reconnect internally) ────
        if self._redis_backend is not None:
            redis_entry = await self._redis_backend.load(key)
            if redis_entry is not None and not redis_entry.is_expired:
                async with self._lock:
                    self._cache[key] = redis_entry
                    self._current_size += redis_entry.size
                    self.l2_restores += 1
                    self.hits += 1
                    # Evict L1 if needed
                    await self._evict_if_needed()
                return redis_entry.value

        self.misses += 1
        return None

    async def get_or_compute(
        self,
        key: str,
        compute_fn,
        ttl: Optional[float] = None,
        **kwargs,
    ) -> Any:
        """Get from cache or compute and cache the result.

        Args:
            key: Cache key.
            compute_fn: Async callable that produces the value.
            ttl: TTL in seconds (uses default if None).
            **kwargs: Additional arguments passed to compute_fn.

        Returns:
            Cached or freshly computed value.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await compute_fn(**kwargs)
        await self.set(key, value, ttl=ttl)
        return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
    ) -> None:
        """Set a value in both L1 and L2 (async).

        L1 write is synchronous (in-memory). L2 write is fire-and-forget
        (background task) so it never blocks the caller.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: TTL in seconds. Uses default_ttl if None. Pass 0 for no TTL.
        """
        effective_ttl = self._default_ttl if ttl is None else ttl
        if effective_ttl == 0:
            effective_ttl = None  # None = no expiry

        entry = CacheEntry(key, value, effective_ttl)

        # ── L1: In-memory write ──────────────────────────────────────────
        async with self._lock:
            old_entry = self._cache.get(key)
            if old_entry:
                self._current_size -= old_entry.size

            self._cache[key] = entry
            self._current_size += entry.size
            self._cache.move_to_end(key)

            await self._evict_if_needed()

        # ── L2: Redis write (fire-and-forget) ────────────────────────────
        if self._redis_backend is not None:
            asyncio.create_task(self._redis_backend.save(key, entry))

    async def delete(self, key: str) -> bool:
        """Remove a key from both L1 and L2.

        Args:
            key: Cache key to remove.

        Returns:
            True if key was found in L1.
        """
        found = False
        async with self._lock:
            entry = self._cache.pop(key, None)
            if entry:
                self._current_size -= entry.size
                found = True

        if self._redis_backend is not None:
            await self._redis_backend.delete(key)

        return found

    async def clear(self) -> int:
        """Clear all cached entries from L1 and L2.

        Returns:
            Number of L1 entries cleared.
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._current_size = 0

        if self._redis_backend is not None:
            redis_count = await self._redis_backend.clear()
            logger.info(
                "Cache '%s' cleared: %d L1 entries, %s L2 entries",
                self.name, count,
                redis_count if redis_count >= 0 else "all",
            )
        else:
            logger.info("Cache '%s' cleared: %d entries", self.name, count)

        return count

    async def has(self, key: str) -> bool:
        """Check if a key exists in L1 without fetching it.

        For L2, falls through to get() which is slightly heavier.
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if not entry.is_expired:
                    return True
                self._cache.pop(key, None)
                self._current_size -= entry.size

        # Check L2 via get
        value = await self.get(key)
        return value is not None

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "name": self.name,
            "l1_entries": len(self._cache),
            "memory_size_mb": round(self._current_size / (1024 * 1024), 2),
            "max_size_mb": round(self._max_size_bytes / (1024 * 1024), 2),
            "usage_percent": round(
                (self._current_size / self._max_size_bytes * 100)
                if self._max_size_bytes > 0 else 0, 1
            ),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 1),
            "evictions": self.evictions,
            "l2_restores": self.l2_restores,
            "redis_available": (
                self._redis_backend._available
                if self._redis_backend else False
            ),
        }

    async def get_redis_info(self) -> dict[str, Any]:
        """Get detailed Redis server info."""
        if self._redis_backend is None:
            return {"enabled": False}
        return await self._redis_backend.get_info()

    def get_entries_info(self, max_items: int = 20) -> list[dict[str, Any]]:
        """Get info about current L1 cache entries (for debugging/monitoring)."""
        entries = []
        for key, entry in list(self._cache.items())[-max_items:]:
            entries.append({
                "key": key[:80],
                "size_kb": round(entry.size / 1024, 1),
                "age_seconds": round(entry.age_seconds, 1),
                "ttl": entry.ttl,
                "expired": entry.is_expired,
            })
        entries.sort(key=lambda e: e["age_seconds"], reverse=True)
        return entries

    async def warm_from_redis(self, max_entries: int = 100) -> int:
        """Pre-warm L1 cache from Redis entries.

        Scans Redis for keys matching this cache's prefix and loads them
        into L1. This speeds up cold starts after a restart.

        Args:
            max_entries: Maximum entries to load.

        Returns:
            Number of entries loaded into L1.
        """
        if self._redis_backend is None:
            return 0

        loaded = 0
        try:
            keys = await self._redis_backend.scan_keys(batch_size=50)
            prefix = f"manga_cache:{self.name}:"

            for rkey in keys:
                if loaded >= max_entries:
                    break

                # Extract original key from prefixed Redis key
                rkey_str = rkey.decode() if isinstance(rkey, bytes) else rkey
                if not rkey_str.startswith(prefix):
                    continue
                orig_key = rkey_str[len(prefix):]

                # Load from Redis and put into L1
                data = await self._redis_backend.get_raw(rkey)
                if data:
                    entry = self._redis_backend.deserialize(data)
                    if entry and not entry.is_expired:
                        async with self._lock:
                            self._cache[orig_key] = entry
                            self._current_size += entry.size
                            loaded += 1

            logger.info(
                "Cache '%s' warmed: %d entries from Redis",
                self.name, loaded,
            )
        except Exception as e:
            logger.debug("Redis warm failed: %s", e)

        return loaded

    async def _evict_if_needed(self) -> None:
        """Evict LRU entries from L1 until under max size."""
        while self._current_size > self._max_size_bytes and self._cache:
            key, entry = self._cache.popitem(last=False)
            self._current_size -= entry.size
            self.evictions += 1
            logger.debug("L1 evicted: %s (size=%d bytes)", key[:50], entry.size)

    async def _prune_loop(self) -> None:
        """Periodically clean up expired entries from L1.

        Redis handles its own TTL expiry automatically, so L2 pruning
        is not needed.
        """
        while self._running:
            try:
                await asyncio.sleep(self._prune_interval)
                async with self._lock:
                    expired_keys = [
                        k for k, v in self._cache.items() if v.is_expired
                    ]
                    for k in expired_keys:
                        entry = self._cache.pop(k, None)
                        if entry:
                            self._current_size -= entry.size
                    if expired_keys:
                        logger.debug(
                            "L1 pruned %d expired entries",
                            len(expired_keys),
                        )

                # Redis TTL handles L2 pruning automatically — nothing needed

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Cache prune error: %s", e)


# ── Global Cache Instances ──────────────────────────────────────────────

ocr_cache = CacheService(
    name="ocr",
    max_size_mb=settings.CACHE_OCR_MAX_MB,
    default_ttl_seconds=settings.CACHE_OCR_TTL,
    enable_redis=True,
)

translation_cache = CacheService(
    name="translation",
    max_size_mb=settings.CACHE_TRANSLATION_MAX_MB,
    default_ttl_seconds=settings.CACHE_TRANSLATION_TTL,
    enable_redis=True,
)

image_cache = CacheService(
    name="image",
    max_size_mb=settings.CACHE_IMAGE_MAX_MB,
    default_ttl_seconds=settings.CACHE_IMAGE_TTL,
    enable_redis=True,
)

model_cache = CacheService(
    name="models",
    max_size_mb=settings.CACHE_MODEL_MAX_MB,
    default_ttl_seconds=0,  # No expiry
    enable_redis=True,
)

detection_cache = CacheService(
    name="detection",
    max_size_mb=settings.CACHE_DETECTION_MAX_MB,
    default_ttl_seconds=settings.CACHE_DETECTION_TTL,
    enable_redis=True,
)

ALL_CACHES: dict[str, CacheService] = {
    "ocr": ocr_cache,
    "translation": translation_cache,
    "image": image_cache,
    "models": model_cache,
    "detection": detection_cache,
}


async def start_all_caches() -> None:
    """Start all cache instances (connects to Redis, starts prune loops)."""
    for name, cache in ALL_CACHES.items():
        await cache.start()
    logger.info("All cache instances started")


async def stop_all_caches() -> None:
    """Stop all cache instances (disconnects Redis, stops prune loops)."""
    for name, cache in ALL_CACHES.items():
        await cache.stop()
    logger.info("All cache instances stopped")


async def get_all_cache_stats() -> dict[str, dict[str, Any]]:
    """Get statistics for all caches."""
    stats = {}
    for name, cache in ALL_CACHES.items():
        stat = cache.get_stats()
        # Add Redis info
        redis_info = await cache.get_redis_info()
        stat["redis"] = redis_info
        stats[name] = stat
    return stats
