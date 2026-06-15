"""Tests for CCXT executor — exchange init and order flow mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from executors.ccxt_executor import CCXTExecutor

EXEC_MODULE = "executors.ccxt_executor"


class TestCCXTExecutor:
    @pytest.mark.asyncio
    async def test_get_exchange_returns_none_when_ccxt_missing(self, monkeypatch):
        monkeypatch.setattr(f"{EXEC_MODULE}.ccxt", None)
        ex = CCXTExecutor("bybit", "key", "secret")
        result = await ex._get_exchange()
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_trade_buy_success(self):
        ex = CCXTExecutor("bybit", "key", "secret")
        mock_exchange = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock_exchange.amount_to_precision = MagicMock(return_value="0.002")
        mock_exchange.market = MagicMock(return_value={"limits": {"amount": {"min": 0.0001}}})
        mock_exchange.create_market_order = AsyncMock(
            return_value={"id": "ord-1", "status": "closed", "average": 50000.0, "filled": 0.002, "cost": 100.0}
        )

        with patch.object(ex, "_get_exchange", AsyncMock(return_value=mock_exchange)):
            result = await ex.execute_trade("BTC", "buy", 100.0)

        assert result is not None
        assert result["id"] == "ord-1"
        assert result["exchange"] == "bybit"
        assert result["status"] == "filled"

    @pytest.mark.asyncio
    async def test_get_order_status_filled(self):
        ex = CCXTExecutor("okx", "key", "secret")
        mock_exchange = AsyncMock()
        mock_exchange.markets = {"BTC/USDT": {}}
        mock_exchange.fetch_order = AsyncMock(return_value={"status": "closed"})

        with patch.object(ex, "_get_exchange", AsyncMock(return_value=mock_exchange)):
            status = await ex.get_order_status("BTC", "ord-1")

        assert status == "filled"
