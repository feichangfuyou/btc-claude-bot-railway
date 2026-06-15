"""Tests for Binance executor — API calls mocked."""

from unittest.mock import AsyncMock, patch

import pytest

from executors.binance_executor import BinanceExecutor

EXEC_MODULE = "executors.binance_executor"


class TestBinanceExecutor:
    @pytest.mark.asyncio
    async def test_execute_trade_not_configured(self):
        ex = BinanceExecutor(api_key=None, api_secret=None)
        with patch(f"{EXEC_MODULE}.is_configured", return_value=False):
            result = await ex.execute_trade("BTC", "buy", 100.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_trade_success(self):
        ex = BinanceExecutor(api_key="key", api_secret="secret")
        order = {
            "orderId": 12345,
            "status": "FILLED",
            "executedQty": "0.001",
            "cummulativeQuoteQty": "95.0",
        }
        with patch(f"{EXEC_MODULE}.add_market_order_by_quote", AsyncMock(return_value=order)):
            result = await ex.execute_trade("BTC", "buy", 95.0)

        assert result["id"] == "12345"
        assert result["exchange"] == "binance"
        assert result["status"] == "filled"
        assert result["entry_price"] == 95000.0

    @pytest.mark.asyncio
    async def test_get_order_status(self):
        ex = BinanceExecutor(api_key="key", api_secret="secret")
        with patch(
            f"{EXEC_MODULE}.binance_private_request",
            AsyncMock(return_value={"status": "FILLED"}),
        ):
            status = await ex.get_order_status("BTC", "99")
        assert status == "filled"

    @pytest.mark.asyncio
    async def test_get_balance_error_returns_zero(self):
        ex = BinanceExecutor()
        with patch(f"{EXEC_MODULE}.get_balance_usd", AsyncMock(side_effect=Exception("fail"))):
            balance = await ex.get_balance()
        assert balance == 0.0
