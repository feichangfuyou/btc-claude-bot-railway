"""Tests for price feed functions — all HTTP/WebSocket calls mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feeds.price_feeds import (
    _bootstrap_prices,
    _extract_symbol_from_product,
    _fetch_binance_prices,
    _fetch_kraken_fallback_prices,
)


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.coins = {}
    for sym in ["BTC", "ETH", "SOL", "DOGE", "LINK", "AVAX", "UNI", "AAVE"]:
        coin = MagicMock()
        coin.price = 0
        bot.coins[sym] = coin
    bot.update_coin_price = MagicMock()
    bot.add_log = MagicMock()
    return bot


# ── _extract_symbol_from_product ─────────────────────────────────────────────


class TestExtractSymbolFromProduct:
    def test_btc_usd(self):
        assert _extract_symbol_from_product("BTC-USD") == "BTC"

    def test_eth_usd(self):
        assert _extract_symbol_from_product("ETH-USD") == "ETH"

    def test_sol_usd(self):
        assert _extract_symbol_from_product("SOL-USD") == "SOL"

    def test_usdt_pair_extracts_symbol(self):
        assert _extract_symbol_from_product("ETH-USDT") == "ETH"

    def test_no_usd_at_all_returns_none(self):
        assert _extract_symbol_from_product("ETH-EUR") is None

    def test_empty_string(self):
        assert _extract_symbol_from_product("") is None

    def test_lowercase_normalised(self):
        assert _extract_symbol_from_product("btc-USD") == "BTC"


# ── _bootstrap_prices ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bootstrap_prices_coinbase_success(mock_bot):
    broadcast_price = AsyncMock()

    with (
        patch(
            "feeds.price_feeds._fetch_coinbase_rest_prices",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "feeds.price_feeds._fetch_binance_prices",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "feeds.price_feeds._fetch_kraken_fallback_prices",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        result = await _bootstrap_prices(mock_bot, broadcast_price)

    assert result is True
    mock_bot.add_log.assert_called_once()
    assert "Coinbase" in mock_bot.add_log.call_args[0][0]
    broadcast_price.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrap_prices_all_fail(mock_bot):
    broadcast_price = AsyncMock()

    with (
        patch(
            "feeds.price_feeds._fetch_coinbase_rest_prices",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "feeds.price_feeds._fetch_binance_prices",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "feeds.price_feeds._fetch_kraken_fallback_prices",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        result = await _bootstrap_prices(mock_bot, broadcast_price)

    assert result is False
    broadcast_price.assert_not_awaited()


@pytest.mark.asyncio
async def test_bootstrap_uses_binance_fill(mock_bot):
    """Coinbase provides some prices, Binance fills the gaps."""
    broadcast_price = AsyncMock()

    with (
        patch(
            "feeds.price_feeds._fetch_coinbase_rest_prices",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "feeds.price_feeds._fetch_binance_prices",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "feeds.price_feeds._fetch_kraken_fallback_prices",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        result = await _bootstrap_prices(mock_bot, broadcast_price)

    assert result is True
    log_msg = mock_bot.add_log.call_args[0][0]
    assert "Coinbase" in log_msg
    assert "Binance" in log_msg


# ── _fetch_binance_prices (import error handling) ────────────────────────────


@pytest.mark.asyncio
async def test_fetch_binance_prices_import_error(mock_bot):
    """Gracefully returns False when binance module is unavailable."""
    with patch(
        "builtins.__import__",
        side_effect=ImportError("No module named 'api.binance_api'"),
    ):
        result = await _fetch_binance_prices(mock_bot)

    assert result is False


# ── _fetch_kraken_fallback_prices ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_kraken_fallback_only_missing(mock_bot):
    """Kraken only fills symbols where price == 0; skips symbols that already have prices."""
    mock_bot.coins["BTC"].price = 95000.0
    mock_bot.coins["ETH"].price = 0
    mock_bot.coins["SOL"].price = 0

    mock_get_ticker = AsyncMock(
        side_effect=lambda sym: {
            "ETH": (3200.0, 1000.0),
            "SOL": (180.0, 500.0),
        }.get(sym, (0, 0))
    )

    with (
        patch.dict("sys.modules", {"api": MagicMock(), "api.kraken_api": MagicMock()}),
        patch("feeds.price_feeds.ACTIVE_COINS", ["BTC", "ETH", "SOL"]),
        patch("api.kraken_api.get_ticker", mock_get_ticker),
    ):
        result = await _fetch_kraken_fallback_prices(mock_bot)

    assert result is True
    calls = mock_bot.update_coin_price.call_args_list
    symbols_updated = [c[0][0] for c in calls]
    assert "BTC" not in symbols_updated
    assert "ETH" in symbols_updated
    assert "SOL" in symbols_updated
