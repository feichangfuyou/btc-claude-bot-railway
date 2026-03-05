"""Tests for Futures Executor — paper/live perpetual futures execution."""

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
    bot.remove_position = MagicMock(side_effect=lambda p: bot.open_positions.remove(p))
    bot.finalize_paper_close = MagicMock(return_value=0.0)
    bot._track_consecutive = MagicMock()
    bot._trade_just_closed_flag = False
    bot._broadcast_fn = None
    bot.open_position = None
    return bot


@pytest.fixture
def decision():
    return {"confidence": 0.75, "patterns_detected": ["trend"]}


EXEC_MODULE = "executors.futures_executor"
PERP_IDS = {"BTC": "BTC-PERP-INTX", "ETH": "ETH-PERP-INTX", "SOL": "SOL-PERP-INTX"}


class TestExecuteFuturesPaper:
    @pytest.mark.asyncio
    async def test_paper_open_buy(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.ENABLE_FUTURES", True),
            patch(f"{EXEC_MODULE}.PERP_PRODUCT_IDS", PERP_IDS),
            patch(f"{EXEC_MODULE}.MAX_FUTURES_POSITIONS", 3),
            patch(f"{EXEC_MODULE}.db_save_state"),
            patch(f"{EXEC_MODULE}.file_log"),
        ):
            from executors.futures_executor import execute_futures_paper

            await execute_futures_paper(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert mock_bot.account["balance"] == 10000.0 - 500
        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert pos["symbol"] == "BTC"
        assert pos["side"] == "buy"
        assert pos["product_type"] == "futures"
        assert pos["leverage"] == 3
        assert pos["product_id"] == "BTC-PERP-INTX"
        expected_coin_sz = round((500 * 3) / 95000, 8)
        assert pos["coin_size"] == expected_coin_sz
        mock_bot.persist_position.assert_called()
        mock_bot.persist_account.assert_called()

    @pytest.mark.asyncio
    async def test_paper_disabled(self, mock_bot, decision):
        with patch(f"{EXEC_MODULE}.ENABLE_FUTURES", False):
            from executors.futures_executor import execute_futures_paper

            await execute_futures_paper(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert len(mock_bot.open_positions) == 0
        assert mock_bot.account["balance"] == 10000.0
        mock_bot.add_log.assert_any_call("Futures disabled — skipping [BTC]", "dim")

    @pytest.mark.asyncio
    async def test_paper_no_product_id(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.ENABLE_FUTURES", True),
            patch(f"{EXEC_MODULE}.PERP_PRODUCT_IDS", {}),
        ):
            from executors.futures_executor import execute_futures_paper

            await execute_futures_paper(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert len(mock_bot.open_positions) == 0

    @pytest.mark.asyncio
    async def test_paper_insufficient_balance(self, mock_bot, decision):
        mock_bot.account["balance"] = 100.0

        with (
            patch(f"{EXEC_MODULE}.ENABLE_FUTURES", True),
            patch(f"{EXEC_MODULE}.PERP_PRODUCT_IDS", PERP_IDS),
        ):
            from executors.futures_executor import execute_futures_paper

            await execute_futures_paper(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert len(mock_bot.open_positions) == 0
        assert mock_bot.account["balance"] == 100.0


class TestCloseFuturesPosition:
    def _make_pos(self, side="buy", entry=90000, usd_size=500, leverage=3):
        notional = usd_size * leverage
        coin_sz = round(notional / entry, 8) if entry > 0 else 0
        return {
            "id": 1,
            "symbol": "BTC",
            "side": side,
            "entry": entry,
            "tp": entry + 2000 if side == "buy" else entry - 2000,
            "sl": entry - 2000 if side == "buy" else entry + 2000,
            "coin_size": coin_sz,
            "btc_size": coin_sz,
            "usd_size": usd_size,
            "product_type": "futures",
            "leverage": leverage,
            "product_id": "BTC-PERP-INTX",
        }

    def test_close_long_profit(self, mock_bot):
        pos = self._make_pos("buy", entry=90000, usd_size=500, leverage=3)
        mock_bot.open_positions.append(pos)

        with (
            patch(f"{EXEC_MODULE}.FUTURES_LIVE", False),
            patch(f"{EXEC_MODULE}.AI_COST_PER_TRADE", 0.02),
            patch(f"{EXEC_MODULE}.db_save_trade"),
            patch(f"{EXEC_MODULE}.record_trade_memory"),
            patch(f"{EXEC_MODULE}.run_learning_cycle") as mock_learn,
            patch(f"{EXEC_MODULE}.file_log"),
            patch(f"{EXEC_MODULE}.send_notification", new_callable=AsyncMock),
        ):
            from executors.futures_executor import close_futures_position

            close_futures_position(mock_bot, pos, 95000.0, "TP HIT")

        assert len(mock_bot.open_positions) == 0
        trade = mock_bot.trades[0]
        assert trade["win"] is True
        assert trade["pnl"] > 0
        assert trade["product_type"] == "futures"
        assert trade["leverage"] == 3
        mock_learn.assert_not_called()

    def test_close_short_profit(self, mock_bot):
        pos = self._make_pos("sell", entry=95000, usd_size=500, leverage=3)
        mock_bot.open_positions.append(pos)

        with (
            patch(f"{EXEC_MODULE}.FUTURES_LIVE", False),
            patch(f"{EXEC_MODULE}.AI_COST_PER_TRADE", 0.02),
            patch(f"{EXEC_MODULE}.db_save_trade"),
            patch(f"{EXEC_MODULE}.record_trade_memory"),
            patch(f"{EXEC_MODULE}.run_learning_cycle") as mock_learn,
            patch(f"{EXEC_MODULE}.file_log"),
            patch(f"{EXEC_MODULE}.send_notification", new_callable=AsyncMock),
        ):
            from executors.futures_executor import close_futures_position

            close_futures_position(mock_bot, pos, 90000.0, "TP HIT")

        trade = mock_bot.trades[0]
        assert trade["win"] is True
        assert trade["pnl"] > 0
        mock_learn.assert_not_called()

    def test_close_triggers_learning_on_loss(self, mock_bot):
        pos = self._make_pos("buy", entry=95000, usd_size=500, leverage=3)
        mock_bot.open_positions.append(pos)

        with (
            patch(f"{EXEC_MODULE}.FUTURES_LIVE", False),
            patch(f"{EXEC_MODULE}.AI_COST_PER_TRADE", 0.02),
            patch(f"{EXEC_MODULE}.db_save_trade"),
            patch(f"{EXEC_MODULE}.record_trade_memory"),
            patch(f"{EXEC_MODULE}.run_learning_cycle") as mock_learn,
            patch(f"{EXEC_MODULE}.file_log"),
            patch(f"{EXEC_MODULE}.send_notification", new_callable=AsyncMock),
        ):
            from executors.futures_executor import close_futures_position

            close_futures_position(mock_bot, pos, 90000.0, "SL HIT")

        trade = mock_bot.trades[0]
        assert trade["win"] is False
        assert trade["pnl"] < 0
        mock_learn.assert_called_once()
        assert mock_bot._trade_just_closed_flag is True


class TestExecuteFuturesLive:
    @pytest.mark.asyncio
    async def test_live_fallback_to_paper(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.FUTURES_LIVE", False),
            patch(f"{EXEC_MODULE}.ENABLE_FUTURES", True),
            patch(f"{EXEC_MODULE}.PERP_PRODUCT_IDS", PERP_IDS),
            patch(f"{EXEC_MODULE}.MAX_FUTURES_POSITIONS", 3),
            patch(f"{EXEC_MODULE}.db_save_state"),
            patch(f"{EXEC_MODULE}.file_log"),
        ):
            from executors.futures_executor import execute_futures_live

            await execute_futures_live(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert pos["product_type"] == "futures"
        assert "order_id" not in pos

    @pytest.mark.asyncio
    async def test_live_success(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.FUTURES_LIVE", True),
            patch(f"{EXEC_MODULE}.ENABLE_FUTURES", True),
            patch(f"{EXEC_MODULE}.PERP_PRODUCT_IDS", PERP_IDS),
            patch(f"{EXEC_MODULE}.MAX_FUTURES_POSITIONS", 3),
            patch(f"{EXEC_MODULE}.file_log"),
            patch(
                "api.coinbase_api.create_perpetual_order",
                new_callable=AsyncMock,
                return_value="live-order-12345",
                create=True,
            ),
        ):
            from executors.futures_executor import execute_futures_live

            await execute_futures_live(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert mock_bot.account["balance"] == 10000.0 - 500
        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert pos["order_id"] == "live-order-12345"
        assert pos["product_type"] == "futures"

    @pytest.mark.asyncio
    async def test_live_order_failure_falls_back_to_paper(self, mock_bot, decision):
        with (
            patch(f"{EXEC_MODULE}.FUTURES_LIVE", True),
            patch(f"{EXEC_MODULE}.ENABLE_FUTURES", True),
            patch(f"{EXEC_MODULE}.PERP_PRODUCT_IDS", PERP_IDS),
            patch(f"{EXEC_MODULE}.MAX_FUTURES_POSITIONS", 3),
            patch(f"{EXEC_MODULE}.db_save_state"),
            patch(f"{EXEC_MODULE}.file_log"),
            patch(
                "executors.futures_executor.create_perpetual_order",
                new_callable=AsyncMock,
                return_value=None,
                create=True,
            ),
        ):
            from executors.futures_executor import execute_futures_live

            await execute_futures_live(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert len(mock_bot.open_positions) == 1
        pos = mock_bot.open_positions[0]
        assert pos["product_type"] == "futures"
        assert "order_id" not in pos

    @pytest.mark.asyncio
    async def test_live_insufficient_balance_falls_back(self, mock_bot, decision):
        mock_bot.account["balance"] = 100.0

        with (
            patch(f"{EXEC_MODULE}.FUTURES_LIVE", True),
            patch(f"{EXEC_MODULE}.ENABLE_FUTURES", True),
            patch(f"{EXEC_MODULE}.PERP_PRODUCT_IDS", PERP_IDS),
            patch(f"{EXEC_MODULE}.MAX_FUTURES_POSITIONS", 3),
            patch(f"{EXEC_MODULE}.db_save_state"),
            patch(f"{EXEC_MODULE}.file_log"),
        ):
            from executors.futures_executor import execute_futures_live

            await execute_futures_live(mock_bot, "buy", "BTC", 95000, 97000, 93000, 500, 3, decision)

        assert len(mock_bot.open_positions) == 0
