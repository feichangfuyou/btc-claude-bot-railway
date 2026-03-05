"""Tests for the trade memory / learning engine (learning/trade_memory.py).

Covers:
- record_trade_memory with mock trades
- build_memory_briefing with few and many trades
- get_pattern_verdict with various pattern inputs
- run_learning_cycle with mocked database
- record_market_snapshot
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.database as db_mod
import learning.trade_memory as tm


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


def _make_coin_state(symbol="BTC", market_cond="trending", indicators=None):
    cs = SimpleNamespace(
        symbol=symbol,
        price=95000.0,
        market_cond=market_cond,
        indicators=indicators or {"rsi": 55, "confluence": {"strength": 20}},
        detected_patterns=["double_bottom"],
    )
    return cs


def _make_trade(**overrides):
    base = {
        "id": 1001,
        "symbol": "BTC",
        "side": "buy",
        "entry": 94000.0,
        "exit": 95000.0,
        "coin_size": 0.002,
        "pnl": 8.50,
        "usd_size": 200.0,
        "reason": "TEST",
        "ts": "12:00:00",
        "win": True,
        "product_type": "spot",
        "onchain": False,
        "leverage": 1,
    }
    base.update(overrides)
    return base


def _make_position(**overrides):
    base = {
        "tp": 96000.0,
        "sl": 93000.0,
        "open_ts": "10:30:00",
        "patterns": ["bull_flag", "ema_crossover"],
        "confidence": 0.72,
        "product_type": "spot",
        "onchain": False,
        "leverage": 1,
    }
    base.update(overrides)
    return base


# ── record_trade_memory ──────────────────────────────────────────────────────


class TestRecordTradeMemory:
    def test_basic_winning_trade(self, temp_db):
        trade = _make_trade(pnl=10.0)
        pos = _make_position()
        cs = _make_coin_state()

        tm.record_trade_memory(trade, pos, cs, fear_greed=55, balance=1000.0)

        rows = db_mod.db_get_recent_trade_contexts(limit=5)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "BTC"
        assert rows[0]["win"] == True  # noqa: E712 — SQLite returns 1/0

    def test_losing_trade(self, temp_db):
        trade = _make_trade(pnl=-5.0, exit=93500.0)
        pos = _make_position()
        cs = _make_coin_state()

        tm.record_trade_memory(trade, pos, cs, fear_greed=30, balance=900.0)

        rows = db_mod.db_get_recent_trade_contexts(limit=5)
        assert len(rows) == 1
        assert rows[0]["win"] == False  # noqa: E712 — SQLite returns 1/0
        assert rows[0]["pnl"] == -5.0

    def test_none_position(self, temp_db):
        trade = _make_trade()
        cs = _make_coin_state()

        tm.record_trade_memory(trade, None, cs, fear_greed=50, balance=1000.0)

        rows = db_mod.db_get_recent_trade_contexts(limit=5)
        assert len(rows) == 1

    def test_none_coin_state(self, temp_db):
        trade = _make_trade()
        pos = _make_position()

        tm.record_trade_memory(trade, pos, None, fear_greed=50, balance=1000.0)

        rows = db_mod.db_get_recent_trade_contexts(limit=5)
        assert len(rows) == 1
        assert rows[0]["regime"] == "unknown"


# ── build_memory_briefing ────────────────────────────────────────────────────


class TestBuildMemoryBriefing:
    def test_briefing_with_few_trades(self, temp_db):
        briefing = tm.build_memory_briefing()

        assert briefing["total_trades_analyzed"] == 0
        assert briefing["learning_active"] is False
        assert "message" in briefing

    def test_briefing_activates_with_enough_trades(self, temp_db):
        cs = _make_coin_state()
        for i in range(6):
            pnl = 5.0 if i % 2 == 0 else -3.0
            trade = _make_trade(id=i, pnl=pnl, ts="12:00:00")
            pos = _make_position()
            db_mod.db_save_trade(trade)
            tm.record_trade_memory(trade, pos, cs, fear_greed=50, balance=1000.0)

        briefing = tm.build_memory_briefing()

        assert briefing["total_trades_analyzed"] >= 5
        assert briefing["learning_active"] is True
        assert "learning_mantra" in briefing

    def test_briefing_returns_dict(self, temp_db):
        result = tm.build_memory_briefing()
        assert isinstance(result, dict)
        assert "total_trades_analyzed" in result


# ── get_pattern_verdict ──────────────────────────────────────────────────────


class TestGetPatternVerdict:
    def test_empty_patterns_returns_neutral(self, temp_db):
        verdict = tm.get_pattern_verdict([], "BTC", "buy", "trending")
        assert verdict["verdict"] == "neutral"
        assert "No patterns" in verdict["reason"]

    def test_no_historical_data(self, temp_db):
        verdict = tm.get_pattern_verdict(["double_bottom"], "BTC", "buy", "trending")
        assert verdict["verdict"] == "neutral"
        assert "No historical data" in verdict["reason"]

    def test_with_historical_winning_patterns(self, temp_db):
        cs = _make_coin_state()
        for i in range(8):
            trade = _make_trade(id=i, pnl=10.0, side="buy")
            pos = _make_position(patterns=["bull_flag"])
            tm.record_trade_memory(trade, pos, cs, fear_greed=50, balance=1000.0)

        verdict = tm.get_pattern_verdict(["bull_flag"], "BTC", "buy", "trending")
        assert verdict["sample_size"] > 0
        assert "avg_win_rate" in verdict
        assert "avg_pnl" in verdict

    def test_with_historical_losing_patterns(self, temp_db):
        cs = _make_coin_state()
        for i in range(8):
            trade = _make_trade(id=i, pnl=-8.0, exit=93000.0, side="buy")
            pos = _make_position(patterns=["head_shoulders"])
            tm.record_trade_memory(trade, pos, cs, fear_greed=50, balance=1000.0)

        verdict = tm.get_pattern_verdict(["head_shoulders"], "BTC", "buy", "trending")
        assert verdict["sample_size"] > 0


# ── run_learning_cycle ───────────────────────────────────────────────────────


class TestRunLearningCycle:
    def test_skips_when_too_few_trades(self, temp_db):
        with patch.object(tm, "db_save_learned_rule") as mock_save:
            tm.run_learning_cycle()
            mock_save.assert_not_called()

    def test_runs_with_sufficient_trades(self, temp_db):
        cs = _make_coin_state()
        for i in range(10):
            trade = _make_trade(id=i, pnl=5.0 if i % 2 == 0 else -3.0)
            pos = _make_position()
            tm.record_trade_memory(trade, pos, cs, fear_greed=50, balance=1000.0)

        tm.run_learning_cycle()


# ── record_market_snapshot ───────────────────────────────────────────────────


class TestRecordMarketSnapshot:
    def test_records_snapshot(self, temp_db):
        cs = _make_coin_state()
        tm.record_market_snapshot(cs, fear_greed=45)

    def test_skips_none_coin_state(self, temp_db):
        tm.record_market_snapshot(None, fear_greed=50)

    def test_skips_zero_price(self, temp_db):
        cs = _make_coin_state()
        cs.price = 0
        with patch.object(tm, "db_save_market_snapshot") as mock_save:
            tm.record_market_snapshot(cs, fear_greed=50)
            mock_save.assert_not_called()
