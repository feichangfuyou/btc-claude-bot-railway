"""Tests for Redis client — in-memory fallback path (no Redis needed)."""

from unittest.mock import patch

import pytest

import core.redis_client as rc


@pytest.fixture(autouse=True)
def isolate_memory_state():
    """Reset module-level state between tests so they don't leak."""
    rc._memory_cache.clear()
    rc._rate_limit_memory.clear()
    with patch.object(rc, "_get_redis", return_value=None):
        yield
    rc._memory_cache.clear()
    rc._rate_limit_memory.clear()


# ── Cache ────────────────────────────────────────────────────────────────────


def test_cache_get_miss():
    assert rc.cache_get("unknown_key") is None


def test_cache_set_and_get():
    rc.cache_set("price:BTC", 95000.0, ttl_sec=60)
    assert rc.cache_get("price:BTC", ttl_sec=60) == 95000.0


def test_cache_set_and_get_dict():
    data = {"balance": 1000, "pnl": 50}
    rc.cache_set("account", data, ttl_sec=60)
    assert rc.cache_get("account", ttl_sec=60) == data


def test_cache_expired():
    """Set a value, then mock time.time to simulate expiration."""
    import time

    real_time = time.time()

    with patch("core.redis_client.time") as mock_time:
        mock_time.time.return_value = real_time
        rc.cache_set("expiring", "value", ttl_sec=10)

        mock_time.time.return_value = real_time + 5
        assert rc.cache_get("expiring", ttl_sec=10) == "value"

        mock_time.time.return_value = real_time + 15
        assert rc.cache_get("expiring", ttl_sec=10) is None


def test_cache_delete():
    rc.cache_set("to_delete", 42, ttl_sec=60)
    assert rc.cache_get("to_delete", ttl_sec=60) == 42
    rc.cache_delete("to_delete")
    assert rc.cache_get("to_delete", ttl_sec=60) is None


def test_cache_delete_nonexistent():
    rc.cache_delete("never_set")


# ── Rate limiting ────────────────────────────────────────────────────────────


def test_rate_limit_under_limit():
    assert rc.rate_limit_check("api:call", max_per_window=5, window_sec=60) is True
    assert rc.rate_limit_check("api:call", max_per_window=5, window_sec=60) is True


def test_rate_limit_at_limit():
    key = "api:flood"
    for _ in range(5):
        rc.rate_limit_check(key, max_per_window=5, window_sec=60)
    assert rc.rate_limit_check(key, max_per_window=5, window_sec=60) is False


def test_rate_limit_exact_boundary():
    """Exactly max_per_window calls should all succeed; the next should fail."""
    key = "api:boundary"
    results = [rc.rate_limit_check(key, max_per_window=3, window_sec=60) for _ in range(3)]
    assert all(results)
    assert rc.rate_limit_check(key, max_per_window=3, window_sec=60) is False


def test_rate_limit_window_reset():
    """After the window expires, counter resets and requests are allowed again."""
    import time

    real_time = time.time()
    key = "api:reset"

    with patch("core.redis_client.time") as mock_time:
        mock_time.time.return_value = real_time

        for _ in range(3):
            rc.rate_limit_check(key, max_per_window=3, window_sec=10)
        assert rc.rate_limit_check(key, max_per_window=3, window_sec=10) is False

        mock_time.time.return_value = real_time + 15
        assert rc.rate_limit_check(key, max_per_window=3, window_sec=10) is True


def test_rate_limit_separate_keys():
    """Different keys have independent counters."""
    for _ in range(3):
        rc.rate_limit_check("key_a", max_per_window=3, window_sec=60)
    assert rc.rate_limit_check("key_a", max_per_window=3, window_sec=60) is False
    assert rc.rate_limit_check("key_b", max_per_window=3, window_sec=60) is True
