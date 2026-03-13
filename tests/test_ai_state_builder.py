"""Tests for core/ai_state_builder.py — build_ai_state from bot."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_mock_bot(trades=None, positions=None, can_trade=True):
    """Create a mock bot object with the fields ai_state_builder accesses."""
    bot = MagicMock()
    bot.coins = {
        "BTC": SimpleNamespace(
            price=65000,
            indicators={"rsi": 55, "ema9": 64500},
            market_cond="trending_up",
            detected_patterns=["bullish_divergence"],
            raw_prices=[65000],
            price_change24h=2.5,
            candles=[],
            price_history=[],
            avg_atr_history=[500],
            volumes=[100],
        ),
    }
    bot.account = {"balance": 10000, "total_pnl": 500, "daily_pnl": 50}
    bot.open_positions = positions or []
    bot.trades = trades or []
    bot.fear_greed = {"value": 55}
    bot.trading_preset = "turtle"
    bot.claude_model = "claude-sonnet-4-6"
    bot.active_user_id = "test-user"
    bot.profit_goal = 1000
    bot.can_trade.return_value = (can_trade, "" if can_trade else "circuit breaker")
    return bot


class TestBuildAiState:
    def test_basic_state_structure(self):
        with patch("core.ai_state_builder._build_enhanced_coin_snapshot") as mock_snap, \
             patch("core.ai_state_builder._build_trade_analytics") as mock_analytics, \
             patch("core.ai_state_builder.build_memory_briefing") as mock_memory, \
             patch("core.ai_state_builder.get_pattern_verdict") as mock_pv:
            mock_snap.return_value = {"price": 65000, "rsi": 55}
            mock_analytics.return_value = {"win_rate": 0.6}
            mock_memory.return_value = "Memory: 10 trades analyzed"
            mock_pv.return_value = {"verdict": "neutral"}

            from core.ai_state_builder import build_ai_state
            bot = _make_mock_bot()
            state = build_ai_state(bot)

            assert "user_id" in state
            assert state["user_id"] == "test-user"
            assert "coins_snapshot" in state
            assert "BTC" in state["coins_snapshot"]
            assert "account" in state
            assert "open_positions" in state
            assert "trades" in state
            assert "fear_greed" in state
            assert "can_trade" in state
            assert "trading_preset" in state
            assert "claude_model" in state
            assert "memory_briefing" in state
            assert "anti_overtrade" in state
            assert "mission" in state

    def test_anti_overtrade_losing_streak(self):
        with patch("core.ai_state_builder._build_enhanced_coin_snapshot") as mock_snap, \
             patch("core.ai_state_builder._build_trade_analytics") as mock_analytics, \
             patch("core.ai_state_builder.build_memory_briefing") as mock_memory, \
             patch("core.ai_state_builder.get_pattern_verdict") as mock_pv:
            mock_snap.return_value = {"price": 65000}
            mock_analytics.return_value = {}
            mock_memory.return_value = ""
            mock_pv.return_value = {"verdict": "neutral"}

            from core.ai_state_builder import build_ai_state
            trades = [{"pnl": -10}, {"pnl": -20}, {"pnl": -30}, {"pnl": 100}]
            bot = _make_mock_bot(trades=trades)
            state = build_ai_state(bot)

            ao = state["anti_overtrade"]
            assert ao["current_losing_streak"] == 3
            assert ao["heightened_caution"] is True
            assert "required_min_signals" in ao

    def test_progress_in_mission(self):
        with patch("core.ai_state_builder._build_enhanced_coin_snapshot") as mock_snap, \
             patch("core.ai_state_builder._build_trade_analytics") as mock_analytics, \
             patch("core.ai_state_builder.build_memory_briefing") as mock_memory, \
             patch("core.ai_state_builder.get_pattern_verdict") as mock_pv:
            mock_snap.return_value = {"price": 65000}
            mock_analytics.return_value = {}
            mock_memory.return_value = ""
            mock_pv.return_value = {"verdict": "neutral"}

            from core.ai_state_builder import build_ai_state
            bot = _make_mock_bot()
            state = build_ai_state(bot)
            assert "PROFIT GOAL" in state["mission"]
            assert "$500" in state["mission"]  # total_pnl

    def test_no_trades_zero_streak(self):
        with patch("core.ai_state_builder._build_enhanced_coin_snapshot") as mock_snap, \
             patch("core.ai_state_builder._build_trade_analytics") as mock_analytics, \
             patch("core.ai_state_builder.build_memory_briefing") as mock_memory, \
             patch("core.ai_state_builder.get_pattern_verdict") as mock_pv:
            mock_snap.return_value = {"price": 65000}
            mock_analytics.return_value = {}
            mock_memory.return_value = ""
            mock_pv.return_value = {"verdict": "neutral"}

            from core.ai_state_builder import build_ai_state
            bot = _make_mock_bot(trades=[])
            state = build_ai_state(bot)
            assert state["anti_overtrade"]["current_losing_streak"] == 0

    def test_cannot_trade_block_reason(self):
        with patch("core.ai_state_builder._build_enhanced_coin_snapshot") as mock_snap, \
             patch("core.ai_state_builder._build_trade_analytics") as mock_analytics, \
             patch("core.ai_state_builder.build_memory_briefing") as mock_memory, \
             patch("core.ai_state_builder.get_pattern_verdict") as mock_pv:
            mock_snap.return_value = {"price": 65000}
            mock_analytics.return_value = {}
            mock_memory.return_value = ""
            mock_pv.return_value = {"verdict": "neutral"}

            from core.ai_state_builder import build_ai_state
            bot = _make_mock_bot(can_trade=False)
            state = build_ai_state(bot)
            assert state["can_trade"] is False
            assert state["block_reason"] == "circuit breaker"
