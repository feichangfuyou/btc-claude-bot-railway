"""Coverage tests for core/user_config.py — cache eviction, invalidation, UserConfig."""

import time
from unittest.mock import MagicMock, patch

from core.user_config import (
    _USER_CONFIG_CACHE,
    _USER_CONFIG_CACHE_MAX,
    _evict_oldest_if_needed,
    invalidate_user_config_cache,
)


class TestEvictOldestIfNeeded:
    def test_no_eviction_when_under_max(self):
        _USER_CONFIG_CACHE.clear()
        _USER_CONFIG_CACHE["u1"] = (time.time(), MagicMock())
        _evict_oldest_if_needed()
        assert "u1" in _USER_CONFIG_CACHE
        _USER_CONFIG_CACHE.clear()

    def test_eviction_when_over_max(self):
        _USER_CONFIG_CACHE.clear()
        # Fill to slightly over max
        for i in range(_USER_CONFIG_CACHE_MAX + 10):
            _USER_CONFIG_CACHE[f"user_{i}"] = (time.time() - (_USER_CONFIG_CACHE_MAX + 10 - i), MagicMock())
        _evict_oldest_if_needed()
        # Should be at 80% of max
        target = int(_USER_CONFIG_CACHE_MAX * 0.8)
        assert len(_USER_CONFIG_CACHE) <= target
        _USER_CONFIG_CACHE.clear()


class TestInvalidateUserConfigCache:
    def test_removes_from_memory_cache(self):
        _USER_CONFIG_CACHE.clear()
        _USER_CONFIG_CACHE["test_user"] = (time.time(), MagicMock())
        with patch("core.user_config.cache_delete") as mock_del:
            invalidate_user_config_cache("test_user")
        assert "test_user" not in _USER_CONFIG_CACHE
        mock_del.assert_called_once_with("user_config:test_user")
        _USER_CONFIG_CACHE.clear()

    def test_no_error_when_not_cached(self):
        _USER_CONFIG_CACHE.clear()
        with patch("core.user_config.cache_delete"):
            invalidate_user_config_cache("nonexistent")
        _USER_CONFIG_CACHE.clear()
