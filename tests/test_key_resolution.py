"""Tests for core/key_resolution.py — exchange key resolution."""

from unittest.mock import patch

from core.key_resolution import _is_dev, resolve_exchange_keys


class TestIsDev:
    def test_matching_email(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"):
            assert _is_dev("dev@test.com") is True

    def test_case_insensitive(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", "Dev@Test.com"):
            assert _is_dev("dev@test.com") is True

    def test_with_whitespace(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"):
            assert _is_dev("  dev@test.com  ") is True

    def test_non_matching_email(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"):
            assert _is_dev("other@test.com") is False

    def test_empty_email(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"):
            assert _is_dev("") is False
            assert _is_dev(None) is False

    def test_no_dev_email_configured(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", ""):
            assert _is_dev("anyone@test.com") is False


class TestResolveExchangeKeys:
    def test_local_dev_coinbase(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.COINBASE_API_KEY", "cb_key"),
            patch("core.key_resolution.COINBASE_API_SECRET", "cb_secret"),
        ):
            result = resolve_exchange_keys(None, None, "coinbase")
            assert result == ("cb_key", "cb_secret")

    def test_local_dev_kraken(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.KRAKEN_API_KEY", "kr_key"),
            patch("core.key_resolution.KRAKEN_API_SECRET", "kr_secret"),
        ):
            result = resolve_exchange_keys(None, None, "kraken")
            assert result == ("kr_key", "kr_secret")

    def test_local_dev_no_keys_returns_none(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.COINBASE_API_KEY", ""),
            patch("core.key_resolution.COINBASE_API_SECRET", ""),
            patch("core.key_resolution.KRAKEN_API_KEY", ""),
            patch("core.key_resolution.KRAKEN_API_SECRET", ""),
        ):
            assert resolve_exchange_keys(None, None, "coinbase") is None
            assert resolve_exchange_keys(None, None, "kraken") is None

    def test_dev_email_coinbase(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.COINBASE_API_KEY", "cb_key"),
            patch("core.key_resolution.COINBASE_API_SECRET", "cb_secret"),
        ):
            result = resolve_exchange_keys("uid", "dev@test.com", "coinbase")
            assert result == ("cb_key", "cb_secret")

    def test_dev_email_binance(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.COINBASE_API_KEY", ""),
            patch("core.key_resolution.COINBASE_API_SECRET", ""),
            patch("core.key_resolution.KRAKEN_API_KEY", ""),
            patch("core.key_resolution.KRAKEN_API_SECRET", ""),
            patch("core.config.BINANCE_API_KEY", "bn_key"),
            patch("core.config.BINANCE_API_SECRET", "bn_secret"),
        ):
            result = resolve_exchange_keys("uid", "dev@test.com", "binance")
            assert result == ("bn_key", "bn_secret")

    def test_dev_email_unknown_exchange_returns_none(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.COINBASE_API_KEY", ""),
            patch("core.key_resolution.COINBASE_API_SECRET", ""),
            patch("core.key_resolution.KRAKEN_API_KEY", ""),
            patch("core.key_resolution.KRAKEN_API_SECRET", ""),
        ):
            result = resolve_exchange_keys("uid", "dev@test.com", "unknown")
            assert result is None

    def test_non_dev_user_no_user_id_returns_none(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"):
            assert resolve_exchange_keys(None, "other@test.com", "coinbase") is None

    def test_non_dev_user_calls_supabase(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.get_user_exchange_keys") as mock_get,
        ):
            mock_get.return_value = {"api_key_enc": "enc_k", "api_secret_enc": "enc_s"}
            result = resolve_exchange_keys("user123", "user@example.com", "coinbase")
            assert result == ("enc_k", "enc_s")
            mock_get.assert_called_once_with("user123", "coinbase")

    def test_non_dev_user_no_data_returns_none(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.get_user_exchange_keys") as mock_get,
        ):
            mock_get.return_value = None
            assert resolve_exchange_keys("user123", "user@example.com", "coinbase") is None

    def test_non_dev_user_partial_data_returns_none(self):
        with (
            patch("core.key_resolution.DEV_USER_EMAIL", "dev@test.com"),
            patch("core.key_resolution.get_user_exchange_keys") as mock_get,
        ):
            mock_get.return_value = {"api_key_enc": "key", "api_secret_enc": ""}
            assert resolve_exchange_keys("user123", "user@example.com", "coinbase") is None

    def test_no_dev_email_no_user_id_returns_none(self):
        with patch("core.key_resolution.DEV_USER_EMAIL", ""):
            assert resolve_exchange_keys(None, None, "coinbase") is None
