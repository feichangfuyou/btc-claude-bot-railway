"""Tests for Coinbase Spot Executor — live/paper spot order execution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.account = {"balance": 10000.0, "daily_pnl": 0.0, "total_pnl": 0.0}
    bot.open_positions = []
    bot.trades = []
    bot.coins = {"BTC": MagicMock(price=95000)}
    bot.fear_greed = {"value": 50}
    bot.active_user_id = None
    bot.active_user_email = None
    bot.price_for = MagicMock(return_value=95000.0)
    bot.add_log = MagicMock()
    bot.broadcast_trade_update = AsyncMock()
    bot.persist_position = MagicMock()
    bot.persist_account = MagicMock()
    bot.set_paper_position = MagicMock(
        side_effect=lambda *args, **kwargs: (
            bot.open_positions.append({"symbol": args[1], "side": args[0], "usd_size": args[6]}),
            bot.open_positions[-1],
        )[1]
    )
    bot.remove_position = MagicMock(side_effect=lambda p: bot.open_positions.remove(p))
    bot.finalize_paper_close = MagicMock(return_value=0.0)
    bot._track_consecutive = MagicMock()
    bot._trade_just_closed_flag = False
    bot._broadcast_fn = None
    bot.open_position = None
    return bot


@pytest.fixture
def decision():
    return {"confidence": 0.85, "patterns_detected": ["breakout"]}


EXEC_MODULE = "executors.coinbase_spot_executor"


class TestExecuteCoinbaseSpot:
    @pytest.mark.asyncio
    async def test_buy_success(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("key", "secret")),
            patch(f"{EXEC_MODULE}.is_configured", return_value=True),
            patch(
                f"{EXEC_MODULE}.create_spot_market_order", new_callable=AsyncMock, return_value="order-abc-123456789012"
            ),
        ):
            from executors.coinbase_spot_executor import execute_coinbase_spot

            await execute_coinbase_spot(mock_bot, "buy", "BTC", 95000, 97000, 93000, 0.01, 950, decision)

        assert mock_bot.account["balance"] == 10000.0 - 950
        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert pos["symbol"] == "BTC"
        assert pos["side"] == "buy"
        assert pos["exchange"] == "coinbase"
        assert pos["order_id"] == "order-abc-123456789012"
        mock_bot.persist_position.assert_called()
        mock_bot.persist_account.assert_called()
        mock_bot.broadcast_trade_update.assert_awaited()

    @pytest.mark.asyncio
    async def test_sell_success(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("key", "secret")),
            patch(f"{EXEC_MODULE}.is_configured", return_value=True),
            patch(
                f"{EXEC_MODULE}.create_spot_market_order", new_callable=AsyncMock, return_value="order-sell-12345678901"
            ),
        ):
            from executors.coinbase_spot_executor import execute_coinbase_spot

            await execute_coinbase_spot(mock_bot, "sell", "BTC", 95000, 93000, 97000, 0.01, 950, decision)

        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert pos["side"] == "sell"
        assert pos["exchange"] == "coinbase"

    @pytest.mark.asyncio
    async def test_fallback_to_paper_when_not_configured(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=None),
            patch(f"{EXEC_MODULE}.is_configured", return_value=False),
        ):
            from executors.coinbase_spot_executor import execute_coinbase_spot

            await execute_coinbase_spot(mock_bot, "buy", "BTC", 95000, 97000, 93000, 0.01, 950, decision)

        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert "exchange" not in pos
        assert pos["usd_size"] == 950
        mock_bot.add_log.assert_any_call("⚠ Coinbase not configured — falling back to paper", "warning")

    @pytest.mark.asyncio
    async def test_fallback_to_paper_on_order_failure(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("key", "secret")),
            patch(f"{EXEC_MODULE}.is_configured", return_value=True),
            patch(f"{EXEC_MODULE}.create_spot_market_order", new_callable=AsyncMock, return_value=None),
        ):
            from executors.coinbase_spot_executor import execute_coinbase_spot

            await execute_coinbase_spot(mock_bot, "buy", "BTC", 95000, 97000, 93000, 0.01, 950, decision)

        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert "exchange" not in pos

    @pytest.mark.asyncio
    async def test_fallback_to_paper_on_exception(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("key", "secret")),
            patch(f"{EXEC_MODULE}.is_configured", return_value=True),
            patch(
                f"{EXEC_MODULE}.create_spot_market_order",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
        ):
            from executors.coinbase_spot_executor import execute_coinbase_spot

            await execute_coinbase_spot(mock_bot, "buy", "BTC", 95000, 97000, 93000, 0.01, 950, decision)

        assert len(mock_bot.open_positions) == 1
        assert "exchange" not in mock_bot.open_positions[0]
        mock_bot.broadcast_trade_update.assert_awaited()


class TestCloseCoinbaseSpot:
    def _make_pos(self, side="buy", entry=90000, usd_size=900, coin_size=0.01):
        return {
            "id": 1,
            "symbol": "BTC",
            "side": side,
            "entry": entry,
            "tp": entry + 2000 if side == "buy" else entry - 2000,
            "sl": entry - 2000 if side == "buy" else entry + 2000,
            "coin_size": coin_size,
            "btc_size": coin_size,
            "usd_size": usd_size,
            "exchange": "coinbase",
            "order_id": "original-order-12345",
        }

    @pytest.mark.asyncio
    async def test_close_long_profit(self, mock_bot):
        pos = self._make_pos("buy", entry=90000, coin_size=0.01, usd_size=900)
        mock_bot.open_positions.append(pos)
        mock_bot.price_for.return_value = 95000.0

        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("k", "s")),
            patch(f"{EXEC_MODULE}.create_spot_market_order", new_callable=AsyncMock, return_value="close-order-1234"),
            patch(f"{EXEC_MODULE}.db_save_trade"),
            patch(f"{EXEC_MODULE}.record_trade_memory"),
            patch(f"{EXEC_MODULE}.run_learning_cycle") as mock_learn,
            patch(f"{EXEC_MODULE}.send_notification", new_callable=AsyncMock),
        ):
            from executors.coinbase_spot_executor import close_coinbase_spot

            await close_coinbase_spot(mock_bot, pos, "TP HIT")

        assert len(mock_bot.open_positions) == 0
        assert len(mock_bot.trades) == 1
        trade = mock_bot.trades[0]
        assert trade["win"] is True
        assert trade["pnl"] > 0
        assert trade["exchange"] == "coinbase"
        mock_learn.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_long_loss(self, mock_bot):
        pos = self._make_pos("buy", entry=95000, coin_size=0.01, usd_size=950)
        mock_bot.open_positions.append(pos)
        mock_bot.price_for.return_value = 90000.0

        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("k", "s")),
            patch(f"{EXEC_MODULE}.create_spot_market_order", new_callable=AsyncMock, return_value="close-order-5678"),
            patch(f"{EXEC_MODULE}.db_save_trade"),
            patch(f"{EXEC_MODULE}.record_trade_memory"),
            patch(f"{EXEC_MODULE}.run_learning_cycle") as mock_learn,
            patch(f"{EXEC_MODULE}.send_notification", new_callable=AsyncMock),
        ):
            from executors.coinbase_spot_executor import close_coinbase_spot

            await close_coinbase_spot(mock_bot, pos, "SL HIT")

        trade = mock_bot.trades[0]
        assert trade["win"] is False
        assert trade["pnl"] < 0
        mock_learn.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_short_profit(self, mock_bot):
        pos = self._make_pos("sell", entry=95000, coin_size=0.01, usd_size=950)
        mock_bot.open_positions.append(pos)
        mock_bot.price_for.return_value = 90000.0

        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("k", "s")),
            patch(f"{EXEC_MODULE}.create_spot_market_order", new_callable=AsyncMock, return_value="close-order-9012"),
            patch(f"{EXEC_MODULE}.db_save_trade"),
            patch(f"{EXEC_MODULE}.record_trade_memory"),
            patch(f"{EXEC_MODULE}.run_learning_cycle") as mock_learn,
            patch(f"{EXEC_MODULE}.send_notification", new_callable=AsyncMock),
        ):
            from executors.coinbase_spot_executor import close_coinbase_spot

            await close_coinbase_spot(mock_bot, pos, "TP HIT")

        trade = mock_bot.trades[0]
        assert trade["win"] is True
        assert trade["pnl"] > 0
        mock_learn.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_failure_falls_back(self, mock_bot):
        pos = self._make_pos("buy", entry=90000, coin_size=0.01, usd_size=900)
        mock_bot.open_positions.append(pos)
        mock_bot.price_for.return_value = 95000.0

        with (
            patch(f"{EXEC_MODULE}.resolve_exchange_keys", return_value=("k", "s")),
            patch(f"{EXEC_MODULE}.create_spot_market_order", new_callable=AsyncMock, return_value=None),
            patch(f"{EXEC_MODULE}.send_notification", new_callable=AsyncMock),
        ):
            from executors.coinbase_spot_executor import close_coinbase_spot

            await close_coinbase_spot(mock_bot, pos, "CLOSE ATTEMPT")

        mock_bot.finalize_paper_close.assert_called_once_with(pos, 95000.0, "CLOSE ATTEMPT", exchange="coinbase")
