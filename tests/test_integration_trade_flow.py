"""End-to-end integration tests for the trade flow.

Covers the complete lifecycle:
- Signal detection → AI decision → paper execution → position tracking → close
- BotState initialization → open position → track → close
- Circuit breaker integration (consecutive losses)
- Semantic kill switch integration
- TP/SL hit mechanics
- Trade eligibility checks

All external APIs (Claude, exchange, notifications) are mocked.
"""

import asyncio
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import core.database as db_mod


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Redirect all database operations to a fresh temp SQLite per test."""
    db_path = str(tmp_path / "test_bot.db")
    log_dir = str(tmp_path / "logs")
    backup_dir = str(tmp_path / "backups")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "LOG_DIR", log_dir)
    monkeypatch.setattr(db_mod, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(db_mod, "_use_postgres_storage", lambda: False)

    pool = db_mod._get_pool()
    while pool:
        try:
            pool.popleft().close()
        except Exception:
            pass

    db_mod.init_db()
    yield db_path


@pytest.fixture(autouse=True)
def mock_externals(monkeypatch):
    """Mock external dependencies so BotState can be instantiated without side effects.
    Patches at core.bot_state.* because bot_state uses `from core.config import ...`."""
    monkeypatch.setattr("core.bot_state.PAPER_TRADING", True)
    monkeypatch.setattr("core.bot_state.TEST_MODE", True)
    monkeypatch.setattr("core.bot_state.ENABLE_FUTURES", False)
    monkeypatch.setattr("core.bot_state.ENABLE_KRAKEN", False)
    monkeypatch.setattr("core.bot_state.DIRECTION_BIAS", "both")
    monkeypatch.setattr("core.bot_state.REQUIRE_TRADE_APPROVAL", False)
    monkeypatch.setattr("core.bot_state.MAX_CONCURRENT_POSITIONS", 8)
    monkeypatch.setattr("core.bot_state.START_BALANCE", 1000.0)
    monkeypatch.setattr("core.bot_state.TARGET_BALANCE", 5000.0)
    monkeypatch.setattr("core.bot_state.TRADE_COOLDOWN_SEC", 0)
    monkeypatch.setattr("core.bot_state.MIN_TRADE_USD", 10.0)
    monkeypatch.setattr("core.bot_state.MIN_PROFIT_AFTER_COSTS", 0.01)
    monkeypatch.setattr("core.bot_state.TRADING_PRESET", "turtle")
    monkeypatch.setattr("core.bot_state.ACTIVE_COINS", ["BTC"])

    mock_agentkit = SimpleNamespace(ready=False, status_snapshot=lambda: {})
    monkeypatch.setattr("core.bot_state.agentkit", mock_agentkit)

    monkeypatch.setattr("core.bot_state.capture_trade_screenshot", AsyncMock())
    monkeypatch.setattr("core.bot_state.send_notification", AsyncMock())
    monkeypatch.setattr("core.bot_state.get_solver_stats", lambda: {})


@pytest.fixture(autouse=True)
def patch_create_task(monkeypatch):
    """Replace asyncio.create_task with a no-op to avoid 'no running event loop' errors
    in synchronous test code. The bot uses fire-and-forget tasks for broadcasts/notifications."""
    _real_create_task = asyncio.create_task

    def _fake_create_task(coro, **kwargs):
        coro.close()
        return MagicMock()

    monkeypatch.setattr("asyncio.create_task", _fake_create_task)
    yield
    monkeypatch.setattr("asyncio.create_task", _real_create_task)


def _create_bot_state():
    from core.bot_state import BotState

    state = BotState()
    state.account = {"balance": 1000.0, "daily_pnl": 0.0, "total_pnl": 0.0}
    return state


def _setup_coin_price(state, symbol="BTC", price=95000.0):
    cs = state.get_coin(symbol)
    cs.price = price
    cs._last_price_ts = time.time()
    cs.raw_prices = [price - 100 + i * 10 for i in range(50)]
    cs.volumes = [100.0] * 50
    cs.indicators = {
        "rsi": 55,
        "atr": 800.0,
        "ema_12": price - 200,
        "ema_26": price - 400,
        "confluence": {"strength": 25, "direction": "buy"},
        "price_action_quality": {"quality": "clean"},
        "volatility_regime": "normal_vol",
    }
    cs.market_cond = "trending"
    return cs


def _make_buy_decision(symbol="BTC", confidence=0.72, entry=95000.0):
    return {
        "action": "buy",
        "symbol": symbol,
        "confidence": confidence,
        "reasoning": "Strong bull flag detected",
        "reasons_to_trade": ["bull_flag", "ema_support"],
        "reasons_to_wait": [],
        "key_signals": ["rsi_bullish"],
        "patterns_detected": ["bull_flag"],
        "market_condition": "trending",
        "confluence_score": 22,
        "order": {
            "side": "buy",
            "entry_price": entry,
            "take_profit": entry + 5000,
            "stop_loss": entry - 2500,
            "size_percent": 20,
        },
    }


# ── Full trade lifecycle ─────────────────────────────────────────────────────


class TestFullTradeLifecycle:
    def test_open_position_via_execute_decision(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        decision = _make_buy_decision()
        state.execute_decision(decision)

        assert len(state.open_positions) == 1
        pos = state.open_positions[0]
        assert pos["side"] == "buy"
        assert pos["symbol"] == "BTC"
        assert state.account["balance"] < 1000.0

    def test_tp_hit_closes_position(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        decision = _make_buy_decision(entry=95000.0)
        state.execute_decision(decision)
        assert len(state.open_positions) == 1

        pos = state.open_positions[0]
        tp_price = pos["tp"]
        state.update_coin_price("BTC", tp_price + 1)

        assert len(state.open_positions) == 0
        assert len(state.trades) == 1
        assert state.trades[0]["win"] is True

    def test_sl_hit_closes_position(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        decision = _make_buy_decision(entry=95000.0)
        state.execute_decision(decision)
        assert len(state.open_positions) == 1

        pos = state.open_positions[0]
        sl_price = pos["sl"]
        state.update_coin_price("BTC", sl_price - 1)

        assert len(state.open_positions) == 0
        assert len(state.trades) == 1

    def test_wait_decision_does_not_open_position(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        decision = {"action": "wait", "reasoning": "No good setup", "confidence": 0.3}
        state.execute_decision(decision)

        assert len(state.open_positions) == 0

    def test_close_all_decision(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        state.execute_decision(_make_buy_decision())
        assert len(state.open_positions) == 1

        pos = state.open_positions[0]
        pos["open_ts"] = "2020-01-01 00:00:00"

        state.execute_decision({"action": "close_all"})
        assert len(state.open_positions) == 0


# ── BotState lifecycle ───────────────────────────────────────────────────────


class TestBotStateLifecycle:
    def test_initial_state(self, temp_db):
        state = _create_bot_state()
        assert state.account["balance"] == 1000.0
        assert isinstance(state.open_positions, list)
        assert state.bot_running is False

    def test_can_trade_when_running(self, temp_db):
        state = _create_bot_state()
        state.bot_running = True
        _setup_coin_price(state)

        ok, reason = state.can_trade("BTC")
        assert ok is True

    def test_cannot_trade_when_balance_zero(self, temp_db):
        state = _create_bot_state()
        state.bot_running = True
        state.account["balance"] = 0.0

        ok, reason = state.can_trade()
        assert ok is False
        assert "balance" in reason.lower()

    def test_persist_and_restore(self, temp_db):
        state = _create_bot_state()
        state.account["balance"] = 1234.56
        state.persist_account()

        from core.bot_state import BotState

        state2 = BotState()
        assert state2.account["balance"] == 1234.56


# ── Circuit breaker integration ──────────────────────────────────────────────


class TestCircuitBreakerIntegration:
    def test_consecutive_losses_trip_breaker(self, temp_db, monkeypatch):
        monkeypatch.setattr("safety.circuit_breaker.MAX_CONSEC_LOSSES", 4)
        state = _create_bot_state()
        state.bot_running = True
        _setup_coin_price(state)

        for _i in range(4):
            state.circuit_breaker.record_loss()

        assert state.circuit_breaker.is_tripped() is True

        ok, reason = state.can_trade()
        assert ok is False
        assert "circuit breaker" in reason.lower()

    def test_win_clears_breaker(self, temp_db, monkeypatch):
        monkeypatch.setattr("safety.circuit_breaker.MAX_CONSEC_LOSSES", 4)
        state = _create_bot_state()
        state.bot_running = True

        for _ in range(3):
            state.circuit_breaker.record_loss()

        state.circuit_breaker.record_win()
        assert state.circuit_breaker.is_tripped() is False
        assert state.circuit_breaker.consecutive_losses == 0

    def test_consecutive_losses_through_trade_closes(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        for i in range(4):
            decision = _make_buy_decision(entry=95000.0, confidence=0.80)
            state.execute_decision(decision)
            assert len(state.open_positions) >= 1, f"Position not opened on iteration {i}"

            pos = state.open_positions[-1]
            sl_price = pos["sl"]
            state.update_coin_price("BTC", sl_price - 1)

            state.update_coin_price("BTC", 95000.0)
            _setup_coin_price(state)

        assert state.circuit_breaker.consecutive_losses >= 4


# ── Semantic kill switch integration ─────────────────────────────────────────


class TestSemanticKillSwitchIntegration:
    def test_isolated_bot_cannot_trade(self, temp_db):
        state = _create_bot_state()
        state.bot_running = True
        _setup_coin_price(state)

        state.semantic_kill_switch._isolated = True
        state.semantic_kill_switch._isolation_until = time.time() + 3600
        state.semantic_kill_switch._isolation_reason = "test isolation"

        ok, reason = state.can_trade()
        assert ok is False
        assert "semantic kill switch" in reason.lower()

    def test_expired_isolation_allows_trading(self, temp_db):
        state = _create_bot_state()
        state.bot_running = True
        _setup_coin_price(state)

        state.semantic_kill_switch._isolated = True
        state.semantic_kill_switch._isolation_until = time.time() - 1
        state.semantic_kill_switch._isolation_reason = "expired"

        ok, reason = state.can_trade()
        assert ok is True


# ── Multiple position management ─────────────────────────────────────────────


class TestMultiplePositions:
    def test_get_position_for_symbol(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        decision = _make_buy_decision()
        state.execute_decision(decision)
        assert len(state.open_positions) == 1

        pos = state.get_position_for_symbol("BTC")
        assert pos is not None
        assert pos["symbol"] == "BTC"

    def test_remove_position(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        decision = _make_buy_decision()
        state.execute_decision(decision)
        assert len(state.open_positions) == 1

        pos = state.open_positions[0]
        state.remove_position(pos)
        assert len(state.open_positions) == 0

    def test_duplicate_symbol_blocked(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        state.execute_decision(_make_buy_decision())
        assert len(state.open_positions) == 1

        ok, reason = state.can_trade("BTC")
        assert ok is False
        assert "already have open position" in reason.lower()


# ── Daily reset and drawdown ─────────────────────────────────────────────────


class TestDailyResetAndDrawdown:
    def test_daily_pnl_tracks_through_trades(self, temp_db):
        state = _create_bot_state()
        _setup_coin_price(state)
        state.bot_running = True

        decision = _make_buy_decision(entry=95000.0)
        state.execute_decision(decision)
        assert len(state.open_positions) == 1

        pos = state.open_positions[0]
        tp_price = pos["tp"]
        state.update_coin_price("BTC", tp_price + 1)

        assert state.account["daily_pnl"] != 0.0

    def test_drawdown_kills_bot(self, temp_db, monkeypatch):
        monkeypatch.setattr("core.bot_state.MAX_DRAWDOWN_PCT", 0.10)
        state = _create_bot_state()
        state.bot_running = True
        state.account["total_pnl"] = -200.0

        state.check_drawdown()

        assert state.bot_running is False
