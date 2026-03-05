"""
Heavy integration tests for auth: x-bot-secret, Bearer token, ?token= query param.
Run with: BOT_API_SECRET=testsecret123 python -m pytest tests/test_auth_integration.py -v
"""

import pytest
from fastapi.testclient import TestClient

from core.backend import app
from core.config import API_SECRET

pytestmark = pytest.mark.skipif(
    not API_SECRET,
    reason="Auth tests require BOT_API_SECRET. Run: BOT_API_SECRET=testsecret123 pytest ...",
)


@pytest.fixture(autouse=True)
def _clear_global_rate_limits():
    """Reset in-memory rate limit counters between tests so the global IP limiter doesn't cause 429s."""
    from core.redis_client import _rate_limit_memory

    _rate_limit_memory.clear()
    yield
    _rate_limit_memory.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def secret():
    return API_SECRET


# ─── Public routes (no auth required) ─────────────────────────────────────────
@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/readiness",
        "/metrics",
        "/api/config",
        "/",
    ],
)
def test_public_routes_no_auth(client, path):
    """Public routes return 200 without any auth."""
    r = client.get(path)
    assert r.status_code == 200, f"{path} should be public"


# ─── Protected routes: no auth → 401 ─────────────────────────────────────────
@pytest.mark.parametrize(
    "path",
    [
        "/account",
        "/trades",
        "/api/presets",
        "/api/exchange/tickers",
        "/equity",
    ],
)
def test_protected_routes_reject_no_auth(client, path):
    """Protected routes return 401 when no auth provided."""
    r = client.get(path)
    assert r.status_code == 401, f"{path} should require auth"
    data = r.json()
    assert data.get("error") == "unauthorized"


# ─── x-bot-secret header ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "path",
    [
        "/account",
        "/api/presets",
        "/api/exchange/tickers",
    ],
)
def test_x_bot_secret_header(client, path, secret):
    """x-bot-secret header grants access to protected routes."""
    r = client.get(path, headers={"x-bot-secret": secret})
    assert r.status_code == 200, f"{path} with x-bot-secret should succeed"


def test_x_bot_secret_wrong_rejected(client, secret):
    """Wrong x-bot-secret returns 401."""
    r = client.get("/account", headers={"x-bot-secret": "wrongsecret"})
    assert r.status_code == 401
    assert r.json().get("error") == "unauthorized"


# ─── secret query param ──────────────────────────────────────────────────────
def test_secret_query_param(client, secret):
    """?secret= query param grants access."""
    r = client.get(f"/account?secret={secret}")
    assert r.status_code == 200


def test_secret_query_param_wrong_rejected(client):
    """Wrong ?secret= returns 401."""
    r = client.get("/account?secret=wrong")
    assert r.status_code == 401


# ─── Bearer token (must be a valid JWT to pass middleware) ───────────────────
def test_bearer_token_invalid_rejected(client):
    """Authorization: Bearer <invalid> is rejected — middleware validates the JWT."""
    r = client.get("/account", headers={"Authorization": "Bearer fake-jwt-for-gate-test"})
    assert r.status_code == 401, "Invalid Bearer token should be rejected by middleware"


# ─── ?token= query param (requires valid Supabase JWT) ─────────────────────────
def test_token_query_param_invalid_rejected(client):
    """?token= with invalid JWT returns 401."""
    r = client.get("/account?token=invalid-jwt")
    assert r.status_code == 401


def test_token_query_param_empty_rejected(client):
    """?token= empty still requires valid auth."""
    r = client.get("/account?token=")
    assert r.status_code == 401


# ─── Screenshot endpoint (same auth rules) ────────────────────────────────────
def test_screenshot_no_auth_401(client):
    """Trade screenshot without auth returns 401."""
    r = client.get("/api/trade/1/screenshot/entry/5m")
    assert r.status_code == 401


def test_screenshot_with_secret(client, secret):
    """Trade screenshot with ?secret= works (img src use case)."""
    r = client.get(f"/api/trade/1/screenshot/entry/5m?secret={secret}")
    # May be 200 (if trade exists) or 404; should NOT be 401
    assert r.status_code != 401


# ─── SPA routes bypass auth (no 401, may 200 or 404 depending on static) ───────
@pytest.mark.parametrize("path", ["/login", "/signup", "/onboarding", "/dashboard", "/settings"])
def test_spa_routes_bypass_auth(client, path):
    """SPA routes bypass auth — must not return 401."""
    r = client.get(path)
    assert r.status_code != 401, f"{path} should bypass auth (no 401)"


# ─── /auth/* bypasses middleware (uses get_current_user) ──────────────────────
def test_auth_routes_bypass_middleware(client):
    """/auth/me without Bearer returns 401 from route, not middleware."""
    r = client.get("/auth/me")
    # Route validates JWT; without valid token -> 401
    assert r.status_code == 401


# ─── OPTIONS bypasses auth (no 401) ───────────────────────────────────────────
def test_options_bypass(client):
    """OPTIONS requests bypass auth — must not return 401."""
    r = client.options("/account")
    assert r.status_code != 401, "OPTIONS should not be rejected as unauthorized"


# ─── WebSocket auth (TestClient supports ws) ─────────────────────────────────
def test_websocket_with_secret_accepts(client, secret):
    """WebSocket with ?secret= connects."""
    with client.websocket_connect(f"/ws?secret={secret}") as ws:
        data = ws.receive_json()
        assert "type" in data or "balance" in str(data) or "coins" in str(data)


def test_websocket_no_auth_rejected(client):
    """WebSocket without auth is rejected."""
    with pytest.raises(Exception):  # Connection rejected
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()


def test_websocket_wrong_secret_rejected(client):
    """WebSocket with wrong secret is rejected."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?secret=wrong") as ws:
            ws.receive_json()
