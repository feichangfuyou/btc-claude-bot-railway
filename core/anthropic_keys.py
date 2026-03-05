"""
Anthropic API key pool for 10k scale.
Round-robin across ANTHROPIC_API_KEYS (comma-separated). Each key: 120 calls/hour.
10 keys = 1,200/hour. Falls back to ANTHROPIC_API_KEY when pool empty.
"""

import threading

from core.config import ANTHROPIC_API_KEY, ANTHROPIC_API_KEYS

_key_index = 0
_key_lock = threading.Lock()


def get_next_key() -> str:
    """Round-robin across API key pool. Thread-safe."""
    global _key_index
    keys = ANTHROPIC_API_KEYS
    if not keys:
        return ANTHROPIC_API_KEY or ""
    with _key_lock:
        key = keys[_key_index % len(keys)]
        _key_index += 1
        return key


def pool_size() -> int:
    """Number of keys in pool (for rate limit scaling)."""
    return max(1, len(ANTHROPIC_API_KEYS)) if ANTHROPIC_API_KEYS else (1 if ANTHROPIC_API_KEY else 0)
