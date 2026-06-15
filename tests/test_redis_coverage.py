"""Additional coverage tests for core/redis_client.py — cache, pub/sub, AI pending."""

from unittest.mock import MagicMock, patch

import pytest

import core.redis_client as rc


@pytest.fixture(autouse=True)
def isolate_memory_state():
    """Reset module-level state between tests so they don't leak."""
    rc._memory_cache.clear()
    rc._rate_limit_memory.clear()
    rc._ai_pending_memory.clear()
    with patch.object(rc, "_get_redis", return_value=None):
        yield
    rc._memory_cache.clear()
    rc._rate_limit_memory.clear()
    rc._ai_pending_memory.clear()


class TestCacheDelete:
    def test_delete_existing_key(self):
        rc._memory_cache["test_del"] = (0, "value")
        rc.cache_delete("test_del")
        assert "test_del" not in rc._memory_cache

    def test_delete_missing_key_no_error(self):
        rc.cache_delete("nonexistent_key")  # should not raise


class TestCacheGetSet:
    def test_set_and_get(self):
        rc.cache_set("mykey", {"data": 123}, ttl_sec=60)
        result = rc.cache_get("mykey", ttl_sec=60)
        assert result == {"data": 123}

    def test_expired_returns_none(self):
        rc._memory_cache["old"] = (0, "stale_value")  # epoch = 0 → expired
        result = rc.cache_get("old", ttl_sec=60)
        assert result is None

    def test_missing_returns_none(self):
        assert rc.cache_get("does_not_exist", ttl_sec=60) is None


class TestRateLimitCheck:
    def test_fail_closed_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.pipeline.side_effect = Exception("redis down")
        with patch.object(rc, "_get_redis", return_value=mock_redis):
            result = rc.rate_limit_check("key", 10, 60, fail_closed=True)
            assert result is False

    def test_fail_open_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.pipeline.side_effect = Exception("redis down")
        with patch.object(rc, "_get_redis", return_value=mock_redis):
            result = rc.rate_limit_check("key", 10, 60, fail_closed=False)
            assert result is True


class TestAiPendingDecrement:
    def test_decrement_in_memory(self):
        rc._ai_pending_memory["user_dec_a"] = 2
        with patch.object(rc, "_get_redis", return_value=None):
            rc.ai_pending_decrement("user_dec_a")
        assert rc._ai_pending_memory["user_dec_a"] == 1
        rc._ai_pending_memory.pop("user_dec_a", None)

    def test_decrement_to_zero_removes_key(self):
        rc._ai_pending_memory["user_dec_b"] = 1
        with patch.object(rc, "_get_redis", return_value=None):
            rc.ai_pending_decrement("user_dec_b")
        assert "user_dec_b" not in rc._ai_pending_memory

    def test_decrement_missing_user(self):
        with patch.object(rc, "_get_redis", return_value=None):
            rc.ai_pending_decrement("nonexistent_decrement")  # defaults to 1, then 0, then del


class TestPublish:
    def test_no_redis_returns_zero(self):
        with patch.object(rc, "_get_redis", return_value=None):
            assert rc.publish("channel", {"msg": "test"}) == 0


class TestSubscribe:
    def test_no_redis_returns_immediately(self):
        with patch.object(rc, "_get_redis", return_value=None):
            rc.subscribe("channel", lambda x: None)  # should return immediately


class TestStartSubscriberThread:
    def test_no_redis_returns_none(self):
        with patch.object(rc, "_get_redis", return_value=None):
            assert rc.start_subscriber_thread("channel", lambda x: None) is None
