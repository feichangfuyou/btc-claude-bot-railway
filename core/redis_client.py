"""
Redis client for distributed caching and rate limiting.
When REDIS_URL is unset, falls back to in-memory (single-instance only).
"""

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger("claudebot.redis")

_redis_client: Any | None = None
_redis_available: bool | None = None


def _get_redis():
    """Lazy init Redis connection. Returns None if REDIS_URL unset."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client
    if _redis_available is False:
        return None  # Already tried and failed in this process

    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        _redis_available = False
        return None
    try:
        import redis

        from core.config import REDIS_MAX_CONNECTIONS

        _redis_client = redis.from_url(
            url,
            decode_responses=True,
            max_connections=REDIS_MAX_CONNECTIONS,
        )
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected (max_connections=%d)", REDIS_MAX_CONNECTIONS)
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis unavailable: {e} — using in-memory fallback")
        _redis_available = False
        return None


def is_redis_available() -> bool:
    """True if Redis is connected and usable."""
    r = _get_redis()
    return r is not None


def _invalidate_redis() -> None:
    """Drop cached client after a failed operation; next call retries or uses memory."""
    global _redis_client, _redis_available
    _redis_client = None
    _redis_available = False


# ─── Cache helpers (Redis or in-memory fallback) ─────────────────────────────

_memory_cache: dict[str, tuple[float, Any]] = {}


def cache_get(key: str, ttl_sec: int = 60) -> Any | None:
    """Get cached value. Returns None if miss or expired."""
    r = _get_redis()
    if r:
        try:
            raw = r.get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            return data
        except Exception as e:
            logger.debug(f"Redis cache get error: {e}")
            _invalidate_redis()
    # In-memory fallback
    if key in _memory_cache:
        ts, val = _memory_cache[key]
        if time.time() - ts < ttl_sec:
            return val
        del _memory_cache[key]
    return None


def cache_set(key: str, value: Any, ttl_sec: int = 60) -> None:
    """Set cached value with TTL."""
    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl_sec, json.dumps(value, default=str))
            return
        except Exception as e:
            logger.debug(f"Redis cache set error: {e}")
            _invalidate_redis()
    # In-memory fallback
    _memory_cache[key] = (time.time(), value)


def cache_delete(key: str) -> None:
    """Delete cached value."""
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception:
            pass
    _memory_cache.pop(key, None)


# ─── Rate limiting (distributed when Redis available) ─────────────────────────

_rate_limit_memory: dict[str, tuple[float, int]] = {}


def rate_limit_check(key: str, max_per_window: int, window_sec: int, fail_closed: bool = False) -> bool:
    """
    Increment counter for key. Return True if under limit, False if rate limited.
    Uses Redis INCR + EXPIRE (fixed window).
    fail_closed=True: deny on Redis error (use for auth/sensitive endpoints).
    """
    r = _get_redis()
    if r:
        try:
            full_key = f"ratelimit:{key}"
            pipe = r.pipeline()
            pipe.incr(full_key)
            pipe.expire(full_key, window_sec)
            count, _ = pipe.execute()
            return bool(count <= max_per_window)
        except Exception as e:
            logger.debug(f"Redis rate limit error: {e}")
            _invalidate_redis()
            if fail_closed:
                return False
    # In-memory fallback
    now = time.time()
    if key not in _rate_limit_memory:
        _rate_limit_memory[key] = (now, 1)
        return True
    ts, count = _rate_limit_memory[key]
    if now - ts >= window_sec:
        _rate_limit_memory[key] = (now, 1)
        return True
    if count >= max_per_window:
        return False
    _rate_limit_memory[key] = (ts, count + 1)
    return True


# ─── AI queue depth (per-user limit for Celery AI tasks) ───────────────────────

_ai_pending_memory: dict[str, int] = {}
AI_PENDING_MAX = 2
AI_PENDING_TTL = 300


def ai_pending_check_and_increment(user_id: str) -> bool:
    """
    Check if user can enqueue another AI task (max 2 pending). If under limit, increment and return True.
    Returns False if already at limit. Used before run_ai_analysis.delay().
    """
    r = _get_redis()
    if r:
        try:
            key = f"ai:pending:{user_id}"
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, AI_PENDING_TTL)
            count, _ = pipe.execute()
            if count > AI_PENDING_MAX:
                r.decr(key)
                return False
            return True
        except Exception as e:
            logger.debug(f"AI pending check error: {e}")
            _invalidate_redis()
    # In-memory fallback (single-instance)
    n = _ai_pending_memory.get(user_id, 0)
    if n >= AI_PENDING_MAX:
        return False
    _ai_pending_memory[user_id] = n + 1
    return True


def ai_pending_decrement(user_id: str) -> None:
    """Decrement pending count when AI task completes. Call from Celery worker."""
    r = _get_redis()
    if r:
        try:
            r.decr(f"ai:pending:{user_id}")
        except Exception as e:
            logger.debug(f"AI pending decrement error: {e}")
        return
    n = _ai_pending_memory.get(user_id, 1)
    _ai_pending_memory[user_id] = max(0, n - 1)
    if _ai_pending_memory[user_id] == 0:
        del _ai_pending_memory[user_id]


# ─── Pub/Sub (for future WebSocket broadcast across instances) ───────────────


def publish(channel: str, message: dict) -> int:
    """Publish message to channel. Returns number of subscribers (0 if no Redis)."""
    r = _get_redis()
    if not r:
        return 0
    try:
        return int(r.publish(channel, json.dumps(message, default=str)))
    except Exception as e:
        logger.debug(f"Redis publish error: {e}")
        return 0


def subscribe(channel: str, callback):
    """Subscribe to channel. callback(msg: dict) called on each message. Blocks."""
    r = _get_redis()
    if not r:
        return
    try:
        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        for msg in pubsub.listen():
            if msg["type"] == "message":
                try:
                    data = json.loads(msg["data"])
                    callback(data)
                except Exception as e:
                    logger.warning(f"Pub/sub callback error: {e}")
    except Exception as e:
        logger.warning(f"Redis subscribe error: {e}")


def start_subscriber_thread(channel: str, callback) -> "threading.Thread | None":
    """Start a background thread that subscribes to channel. Returns the thread or None."""
    r = _get_redis()
    if not r:
        return None

    def _run():
        subscribe(channel, callback)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
