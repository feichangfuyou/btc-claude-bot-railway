"""Tests for Supabase Auth REST lookup (Google OAuth JWT edge cases)."""

from unittest.mock import MagicMock, patch

from core.auth import lookup_user_via_auth_api, verify_token


@patch("core.auth.httpx.get")
def test_lookup_user_via_auth_api_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "user-123", "email": "test@example.com"}
    mock_get.return_value = mock_resp

    user = lookup_user_via_auth_api("valid-jwt-token")
    assert user["id"] == "user-123"
    assert user["email"] == "test@example.com"
    assert verify_token("valid-jwt-token") is True


@patch("core.auth.httpx.get")
def test_lookup_user_via_auth_api_rejects_invalid(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_get.return_value = mock_resp

    assert lookup_user_via_auth_api("bad-token") is None
    assert verify_token("bad-token") is False
