"""Tests for BotState — core state machine methods."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.bot_state import BotState


@pytest.fixture
def bot():
    with (
        patch("core.bot_state.db_load_state", return_value=None),
        patch("core.bot_state.db_save_state"),
        patch("core.bot_state.db_save_log"),
        patch("core.bot_state.db_save_trade"),
        patch("core.bot_state.db_save_account_snapshot"),
        patch("core.bot_state.record_trade_memory"),
        patch("core.bot_state.run_learning_cycle"),
        patch("core.bot_state.send_notification", new_callable=AsyncMock),
        patch("core.bot_state.record_market_snapshot"),
    ):
        b = BotState()
        yield b


def test_initial_state(bot):
    assert bot.account["balance"] > 0
    assert bot.bot_running is False
    assert len(bot.open_positions) == 0
    assert len(bot.trades) == 0


def test_price_for_unknown_symbol(bot):
    assert bot.price_for("FAKECOIN") == 0.0


def test_min_price_age_no_prices(bot):
    age = bot.min_price_age()
    assert age == 999999.0


def test_add_log(bot):
    bot.add_log("test message", "info")
    assert len(bot.logs) >= 1
    assert bot.logs[0]["msg"] == "test message"


def test_remove_position(bot):
    pos = {"id": 123, "symbol": "BTC", "side": "buy", "entry": 90000}
    bot.open_positions.append(pos)
    assert len(bot.open_positions) == 1
    bot.remove_position(pos)
    assert len(bot.open_positions) == 0


@pytest.mark.asyncio
async def test_finalize_paper_close_long(bot):
    pos = {
        "id": 1,
        "symbol": "BTC",
        "side": "buy",
        "entry": 90000.0,
        "tp": 92000.0,
        "sl": 88000.0,
        "coin_size": 0.01,
        "btc_size": 0.01,
        "usd_size": 900.0,
    }
    bot.open_positions.append(pos)
    initial_balance = bot.account["balance"]

    result = bot.finalize_paper_close(pos, current_price=91000.0, reason="TEST CLOSE")
    await asyncio.sleep(0)  # let pending tasks run

    assert isinstance(result, float)
    assert len(bot.open_positions) == 0
    assert len(bot.trades) == 1
    assert bot.trades[0]["symbol"] == "BTC"
    assert bot.trades[0]["exit"] == 91000.0
    assert bot.account["balance"] != initial_balance


@pytest.mark.asyncio
async def test_finalize_paper_close_short(bot):
    pos = {
        "id": 2,
        "symbol": "ETH",
        "side": "sell",
        "entry": 3000.0,
        "tp": 2800.0,
        "sl": 3200.0,
        "coin_size": 1.0,
        "btc_size": 1.0,
        "usd_size": 3000.0,
    }
    bot.open_positions.append(pos)

    net = bot.finalize_paper_close(pos, current_price=2900.0, reason="SHORT CLOSE")
    await asyncio.sleep(0)

    assert len(bot.open_positions) == 0
    trade = bot.trades[0]
    assert trade["side"] == "sell"
    assert trade["exit"] == 2900.0
    assert net > 0


@pytest.mark.asyncio
async def test_broadcast_trade_update_calls_fn(bot):
    mock_fn = AsyncMock()
    bot.set_broadcast(mock_fn)
    await bot.broadcast_trade_update()
    mock_fn.assert_called_once()
    call_data = mock_fn.call_args[0][0]
    assert call_data["type"] == "trade_update"
    assert "account" in call_data


@pytest.mark.asyncio
async def test_broadcast_trade_update_no_fn(bot):
    await bot.broadcast_trade_update()  # should not raise
