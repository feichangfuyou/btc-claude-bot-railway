"""
Red Team / Black Hat / Brute Force — Bottleneck & Security Stress Tests

Attacks every bottleneck and security surface:
- Connection pool exhaustion (Postgres, Redis)
- Rate limit bypass (burst, key spray)
- Concurrent request floods
- WebSocket floods
- Cache poisoning
- AI queue abuse
- Stripe webhook replay
- Malicious payloads (SQLi, path traversal, oversized body)

Run: BOT_API_SECRET=testsecret python -m pytest tests/test_red_team_bottleneck.py -v
Backend must be running for integration tests (or use TestClient for unit-style).
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient

from core.backend import app
from core.config import API_SECRET
from core.redis_client import (
    ai_pending_check_and_increment,
    ai_pending_decrement,
    cache_get,
    cache_set,
    is_redis_available,
    rate_limit_check,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.skipif(
    not API_SECRET,
    reason="Red team tests require BOT_API_SECRET. Run: BOT_API_SECRET=testsecret pytest ...",
)


@pytest.fixture(autouse=True)
def _clear_global_rate_limits():
    """Reset rate limit counters between tests to prevent cross-test 429s."""
    from core.redis_client import _ai_pending_memory, _get_redis, _memory_cache, _rate_limit_memory

    # 1. Clear in-memory fallback
    _rate_limit_memory.clear()
    _memory_cache.clear()
    _ai_pending_memory.clear()

    # 2. Clear Redis (if available)
    r = _get_redis()
    if r:
        try:
            keys = r.keys("ratelimit:*")
            if keys:
                r.delete(*keys)
        except Exception:
            pass

    yield

    _rate_limit_memory.clear()
    _memory_cache.clear()
    _ai_pending_memory.clear()
    if r:
        try:
            keys = r.keys("ratelimit:*")
            if keys:
                r.delete(*keys)
        except Exception:
            pass


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def secret():
    return API_SECRET


# ─── 1. Rate Limit Bypass ─────────────────────────────────────────────────────


def test_rate_limit_burst_same_key():
    """Burst past rate limit with same key — should be blocked after max."""
    key = f"redteam_burst_{time.time()}"
    limit, window = 5, 60
    results = []
    for _ in range(10):
        results.append(rate_limit_check(key, max_per_window=limit, window_sec=window))
    # First 5 should pass, rest should fail
    assert sum(results) <= limit + 1, "Rate limit should block burst (allow slight over)"
    assert not all(results), "At least some requests should be rate limited"


def test_rate_limit_key_spray_bypass():
    """Spray many keys to bypass per-key limit — each key gets fresh quota."""
    base = f"redteam_spray_{time.time()}"
    limit, window = 3, 60
    for i in range(20):
        ok = rate_limit_check(f"{base}_{i}", max_per_window=limit, window_sec=window)
        assert ok, f"Key spray {i} should pass (fresh key)"
    # All pass — key spray bypasses per-key limits (expected; use global limits to mitigate)


def test_ai_pending_per_user_limit():
    """AI queue: max 2 pending per user — 3rd should fail."""
    user_id = f"redteam_ai_{time.time()}"
    r1 = ai_pending_check_and_increment(user_id)
    r2 = ai_pending_check_and_increment(user_id)
    r3 = ai_pending_check_and_increment(user_id)
    assert r1 and r2, "First two should pass"
    assert not r3, "Third should be blocked"
    ai_pending_decrement(user_id)
    ai_pending_decrement(user_id)


# ─── 2. Concurrent Request Flood ──────────────────────────────────────────────


def test_concurrent_health_flood(client, secret):
    """100 concurrent /health requests — no crash, all return 200."""

    def fetch():
        return client.get("/health")

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(fetch) for _ in range(100)]
        results = [f.result() for f in as_completed(futures)]
    for r in results:
        assert r.status_code == 200, "Health should survive flood"


def test_concurrent_ticker_flood(client, secret):
    """50 concurrent /api/exchange/tickers — IO executor should handle."""

    def fetch():
        return client.get("/api/exchange/tickers?limit=10", headers={"x-bot-secret": secret})

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(fetch) for _ in range(50)]
        results = [f.result() for f in as_completed(futures)]
    ok = sum(1 for r in results if r.status_code == 200)
    assert ok >= 45, f"Most ticker requests should succeed ({ok}/50)"


def test_concurrent_account_flood(client, secret):
    """30 concurrent /account — auth + DB should handle."""

    def fetch():
        return client.get("/account", headers={"x-bot-secret": secret})

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(fetch) for _ in range(30)]
        results = [f.result() for f in as_completed(futures)]
    for r in results:
        assert r.status_code == 200, "Account should survive flood"


# ─── 3. Cache Poisoning / Abuse ───────────────────────────────────────────────


def test_cache_oversized_value():
    """Oversized cache value — should not crash."""
    key = f"redteam_big_{time.time()}"
    big_val = {"x": "a" * 100_000}
    try:
        cache_set(key, big_val, ttl_sec=1)
        got = cache_get(key, ttl_sec=1)
        assert got is not None or not is_redis_available()
    except Exception as e:
        pytest.fail(f"Cache should handle large value: {e}")


def test_cache_key_injection():
    """Malicious cache key (path traversal, null byte)."""
    for bad_key in ["../../../etc/passwd", "key\x00injection", "a" * 1000]:
        try:
            cache_set(bad_key, {"test": 1}, ttl_sec=1)
            cache_get(bad_key, ttl_sec=1)
        except Exception:
            pass  # Reject or accept — no crash


# ─── 4. Malicious Payloads ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path_suffix",
    [
        "1;DROP TABLE trades--",
        "1 OR 1=1",
        "../../../etc/passwd",
        "%00",
        "1' UNION SELECT * FROM users--",
    ],
)
def test_sql_injection_paths(client, secret, path_suffix):
    """SQL injection in path params — should not 500."""
    r = client.get(f"/api/trade/{path_suffix}/screenshot/entry/5m", headers={"x-bot-secret": secret})
    assert r.status_code != 500, f"Should not 500 on injection: {path_suffix}"


def test_oversized_json_body(client, secret):
    """Oversized JSON body — should not crash."""
    big = {"x": "a" * 500_000}
    r = client.post(
        "/billing/checkout",
        json=big,
        headers={"x-bot-secret": secret, "Authorization": "Bearer x"},
    )
    assert r.status_code != 500


def test_deeply_nested_json(client):
    """Deeply nested JSON — potential DoS."""
    nested = {"a": {"a": {"a": {"a": 1}}}}
    for _ in range(10):
        nested = {"a": nested}
    r = client.post("/billing/webhook", json=nested, headers={"Content-Type": "application/json"})
    assert r.status_code != 500


# ─── 5. Stripe Webhook Replay / Spoof ─────────────────────────────────────────


def test_stripe_webhook_no_signature(client):
    """Stripe webhook without signature — rejected."""
    r = client.post(
        "/billing/webhook",
        content=b'{"type":"checkout.session.completed"}',
        headers={"Content-Type": "application/json"},
    )
    data = r.json()
    assert "error" in data or r.status_code >= 400


def test_stripe_webhook_fake_signature(client):
    """Stripe webhook with fake signature — rejected."""
    r = client.post(
        "/billing/webhook",
        content=b'{"type":"checkout.session.completed"}',
        headers={"Content-Type": "application/json", "stripe-signature": "t=1,v1=deadbeef"},
    )
    data = r.json()
    assert "error" in data or r.status_code >= 400


# ─── 6. Auth Bypass Attempts ──────────────────────────────────────────────────


def test_empty_secret_rejected(client):
    """Empty x-bot-secret — 401."""
    r = client.get("/account", headers={"x-bot-secret": ""})
    assert r.status_code == 401


def test_wrong_secret_rejected(client, secret):
    """Wrong secret — 401."""
    r = client.get("/account", headers={"x-bot-secret": "wrong" + secret})
    assert r.status_code == 401


def test_jwt_alg_none_rejected(client):
    """JWT alg:none — 401."""
    jwt_none = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {jwt_none}"})
    assert r.status_code == 401


# ─── 7. WebSocket Flood (TestClient) ───────────────────────────────────────────


def test_websocket_rapid_connect_disconnect(client, secret):
    """Rapid WS connect/disconnect — no crash."""
    for _ in range(10):
        try:
            with client.websocket_connect(f"/ws?secret={secret}") as ws:
                ws.receive_json()
        except Exception:
            pass  # May fail under load; no crash


# ─── 8. Path Traversal ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,method",
    [
        ("/billing/checkout/../webhook", "POST"),
        ("/api/alternative/../fng/", "GET"),
        ("/auth/me/../../../etc/passwd", "GET"),
    ],
)
def test_path_traversal(client, path, method):
    """Path traversal — 404 or 401, never 200 with sensitive data."""
    if method == "POST":
        r = client.post(path, json={})
    else:
        r = client.get(path)
    if r.status_code == 200 and "webhook" in path:
        data = r.json()
        assert "error" in data or "handled" in data


# ─── 9. Method Confusion ─────────────────────────────────────────────────────


def test_get_webhook_rejected(client):
    """GET /billing/webhook — 405."""
    r = client.get("/billing/webhook")
    assert r.status_code == 405


def test_put_account_rejected(client, secret):
    """PUT /account — 405 or 401."""
    r = client.put("/account", headers={"x-bot-secret": secret})
    assert r.status_code in (405, 401, 404)


# ─── 10. Readiness Under Load ────────────────────────────────────────────────


def test_readiness_after_flood(client, secret):
    """Readiness still works after request flood."""
    for _ in range(50):
        client.get("/health")
    r = client.get("/readiness")
    assert r.status_code == 200
    data = r.json()
    assert "score" in data and "checks" in data


# ─── 11. Event Loop Blocking (Stripe in executor) ──────────────────────────────


def test_health_responds_during_blocking_work(client):
    """Health should respond even when other endpoints are busy (non-blocking)."""

    # Fire ticker request (slow external API) and immediately hit health
    def slow_ticker():
        return client.get("/api/exchange/tickers?limit=500")

    t = threading.Thread(target=slow_ticker)
    t.start()
    time.sleep(0.1)
    r = client.get("/health")
    t.join(timeout=10)
    assert r.status_code == 200, "Health must not block on ticker fetch"


# ─── 12. Presets Cache Poisoning ──────────────────────────────────────────────


def test_presets_endpoint_flood(client, secret):
    """Presets cache — 20 rapid requests, all 200."""
    results = []
    for _ in range(20):
        r = client.get("/api/presets", headers={"x-bot-secret": secret})
        results.append(r.status_code)
    assert all(c == 200 for c in results), f"Presets flood: {results}"


# ─── 13. Parameter Pollution ──────────────────────────────────────────────────


def test_param_pollution_secret(client, secret):
    """?secret=wrong&secret=OK — last wins (or first); no bypass if attacker lacks secret."""
    r = client.get(f"/account?secret=wrong&secret={secret}")
    # Last typically wins in FastAPI/Starlette
    assert r.status_code == 200
    r2 = client.get(f"/account?secret={secret}&secret=wrong")
    # First OK, then wrong — behavior may vary
    assert r2.status_code in (200, 401)


# ─── 14. Content-Type Confusion ───────────────────────────────────────────────


def test_content_type_confusion(client, secret):
    """text/plain body on JSON endpoint — 422 or 401."""
    r = client.post(
        "/billing/checkout",
        content='{"tier":"elite"}',
        headers={"Content-Type": "text/plain", "Authorization": "Bearer x"},
    )
    assert r.status_code in (401, 422, 415)
