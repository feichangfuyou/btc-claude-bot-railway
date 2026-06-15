"""Tests for billing handlers — Stripe tiers, Coinbase CDP, manual payments."""

from unittest.mock import MagicMock, patch

from billing.coinbase_handler import TIER_PRICES_USD, _generate_cdp_jwt
from billing.manual_handler import PRICES, get_address_for_crypto, submit_manual_payment
from billing.stripe_handler import (
    TIER_LIMITS,
    check_tier_limit,
    get_max_exchanges,
    get_tier_limit,
)


class TestStripeHandler:
    def test_tier_limits_has_all_tiers(self):
        assert set(TIER_LIMITS) == {"none", "starter", "pro", "elite"}

    def test_starter_max_exchanges(self):
        assert get_max_exchanges("starter") == 1

    def test_elite_has_futures(self):
        assert check_tier_limit("elite", "futures") is True

    def test_none_cannot_trade(self):
        assert check_tier_limit("none", "can_trade") is False

    def test_unknown_tier_falls_back_to_none(self):
        assert get_tier_limit("bogus", "max_coins", 0) == 0

    def test_pro_ai_model(self):
        assert get_tier_limit("pro", "ai_model") == "claude-sonnet-4-6"


class TestCoinbaseHandler:
    def test_tier_prices_usd(self):
        assert TIER_PRICES_USD["starter"] == 49.00
        assert TIER_PRICES_USD["elite"] == 199.00

    def test_cdp_jwt_empty_without_keys(self, monkeypatch):
        monkeypatch.setenv("COINBASE_CDP_KEY_NAME", "")
        monkeypatch.setenv("COINBASE_CDP_PRIVATE_KEY", "")
        assert _generate_cdp_jwt("POST", "/v1/charges") == ""


class TestManualHandler:
    def test_prices_match_tiers(self):
        assert PRICES == {"starter": 49, "pro": 99, "elite": 199}

    def test_get_address_missing_config(self):
        with patch(
            "billing.manual_handler.PAYWALL_ADDRESSES",
            {"BTC": "", "ETH": "", "SOL": "", "USDT": ""},
        ):
            assert get_address_for_crypto("BTC") is None

    def test_get_address_returns_configured(self):
        with patch(
            "billing.manual_handler.PAYWALL_ADDRESSES",
            {"BTC": "bc1qtest", "ETH": "", "SOL": "", "USDT": ""},
        ):
            assert get_address_for_crypto("btc") == "bc1qtest"

    def test_submit_manual_payment_duplicate_txid(self):
        user = MagicMock()
        user.id = "user-123"
        user.email = "test@example.com"

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": 1}]
        )

        with patch("billing.manual_handler.supabase", mock_supabase):
            result = submit_manual_payment(user, "pro", "BTC", "0.01", "tx-dup")

        assert result["error"] == "This Transaction ID has already been submitted."

    def test_submit_manual_payment_success(self):
        user = MagicMock()
        user.id = "user-123"
        user.email = "test@example.com"

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": 99}])

        with patch("billing.manual_handler.supabase", mock_supabase):
            result = submit_manual_payment(user, "starter", "ETH", "0.5", "tx-new")

        assert result["success"] is True
        assert "submitted" in result["message"].lower()
