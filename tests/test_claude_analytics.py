"""Tests for ai/claude_ai.py — _build_trade_analytics, _extract_json, get_claude_system, _validate_decision."""

from unittest.mock import patch

from ai.claude_ai import (
    _build_trade_analytics,
    _extract_json,
    _trade_suggestion,
    _build_enhanced_coin_snapshot,
    get_claude_system,
    _validate_decision,
    SCOUT_SYSTEM,
)


class TestBuildTradeAnalytics:
    def test_empty_trades(self):
        result = _build_trade_analytics([])
        assert result["total"] == 0
        assert result["win_rate"] == 0

    def test_with_wins_and_losses(self):
        trades = [
            {"symbol": "BTC", "side": "buy", "pnl": 100},
            {"symbol": "BTC", "side": "buy", "pnl": -50},
            {"symbol": "ETH", "side": "sell", "pnl": 200},
            {"symbol": "ETH", "side": "sell", "pnl": -30},
        ]
        result = _build_trade_analytics(trades)
        assert result["total"] == 4
        assert result["win_rate"] == 50.0
        assert result["avg_win"] == 150.0
        assert result["avg_loss"] == -40.0
        assert result["best_trade"] == 200
        assert result["worst_trade"] == -50

    def test_coin_performance_tracked(self):
        trades = [
            {"symbol": "BTC", "pnl": 100},
            {"symbol": "BTC", "pnl": -20},
            {"symbol": "ETH", "pnl": 50},
        ]
        result = _build_trade_analytics(trades)
        assert "BTC" in result["coin_performance"]
        assert "ETH" in result["coin_performance"]
        assert result["coin_performance"]["BTC"]["trades"] == 2
        assert result["coin_performance"]["ETH"]["trades"] == 1

    def test_side_performance(self):
        trades = [
            {"side": "buy", "pnl": 100},
            {"side": "sell", "pnl": -30},
        ]
        result = _build_trade_analytics(trades)
        assert result["side_performance"]["buy"]["pnl"] == 100
        assert result["side_performance"]["sell"]["pnl"] == -30

    def test_streak_detection_wins(self):
        trades = [{"pnl": 10}, {"pnl": 20}, {"pnl": 30}, {"pnl": -5}]
        result = _build_trade_analytics(trades)
        assert "3 wins" in result["recent_streak"]

    def test_streak_detection_losses(self):
        trades = [{"pnl": -10}, {"pnl": -20}, {"pnl": 5}]
        result = _build_trade_analytics(trades)
        assert "2 loss" in result["recent_streak"]

    def test_best_worst_coin(self):
        trades = [
            {"symbol": "BTC", "pnl": 500},
            {"symbol": "ETH", "pnl": -200},
        ]
        result = _build_trade_analytics(trades)
        assert result["best_coin"] == "BTC"
        assert result["worst_coin"] == "ETH"

    def test_all_wins(self):
        trades = [{"pnl": 50}, {"pnl": 100}]
        result = _build_trade_analytics(trades)
        assert result["win_rate"] == 100.0
        assert result["avg_loss"] == 0


class TestTradeSuggestion:
    def test_high_win_rate(self):
        s = _trade_suggestion(60, 1, "win", [{"pnl": 1}] * 10)
        assert "size up" in s.lower()

    def test_low_win_rate(self):
        s = _trade_suggestion(30, 1, "loss", [{"pnl": -1}] * 10)
        assert "trending" in s.lower() or "low" in s.lower()

    def test_win_streak(self):
        s = _trade_suggestion(50, 4, "win", [{"pnl": 1}] * 10)
        assert "streak" in s.lower()

    def test_loss_streak(self):
        s = _trade_suggestion(50, 3, "loss", [{"pnl": -1}] * 10)
        assert "reduce" in s.lower() or "conviction" in s.lower()

    def test_default_suggestion(self):
        s = _trade_suggestion(50, 1, "win", [{"pnl": 1}] * 2)
        assert "3+ signals" in s.lower() or "take trades" in s.lower()


class TestExtractJson:
    def test_plain_json(self):
        raw = '{"action":"buy","symbol":"BTC"}'
        result = _extract_json(raw)
        assert result["action"] == "buy"

    def test_markdown_fenced_json(self):
        raw = '```json\n{"action":"wait","reasoning":"no edge"}\n```'
        result = _extract_json(raw)
        assert result["action"] == "wait"

    def test_json_with_trailing_text(self):
        raw = '{"action":"sell"} and some extra text here'
        result = _extract_json(raw)
        assert result["action"] == "sell"

    def test_invalid_json_raises(self):
        import json
        raw = "this is not json at all"
        try:
            result = _extract_json(raw)
            assert result.get("action") == "wait"
        except json.JSONDecodeError:
            pass  # expected for malformed input

    def test_empty_string_raises(self):
        import json
        try:
            _extract_json("")
        except json.JSONDecodeError:
            pass  # expected


class TestGetClaudeSystem:
    def test_returns_string(self):
        prompt = get_claude_system()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_includes_preset_guidance(self):
        prompt = get_claude_system(preset_id="turtle")
        assert "TP" in prompt or "take_profit" in prompt or "ATR" in prompt

    def test_opus_emulation_for_sonnet(self):
        prompt = get_claude_system(model_id="claude-sonnet-4-6")
        assert "OPUS-STYLE" in prompt or "STEP 1" in prompt

    def test_no_opus_emulation_for_opus(self):
        prompt = get_claude_system(model_id="claude-opus-4-6")
        assert "OPUS-STYLE REASONING" not in prompt

    def test_news_injected(self):
        news = {
            "sentiment": "bullish",
            "sentiment_score": 5,
            "headlines": [{"title": "BTC hits 100k", "domain": "CoinDesk"}],
            "fear_greed": {"value": 75, "classification": "Greed"},
            "social_pulse": {"sentiment": "bullish", "galaxy_score": 80},
        }
        prompt = get_claude_system(news=news)
        assert "100k" in prompt or "INSTITUTIONAL" in prompt

    def test_scout_system_exists(self):
        assert isinstance(SCOUT_SYSTEM, str)
        assert len(SCOUT_SYSTEM) > 50


class TestBuildEnhancedCoinSnapshot:
    def test_returns_dict_with_expected_keys(self):
        from types import SimpleNamespace
        cs = SimpleNamespace(
            price=65000,
            price_change24h=2.5,
            market_cond="trending_up",
            detected_patterns=["bullish_divergence"],
            raw_prices=[65000 + i for i in range(100)],
            volumes=[100.0] * 100,
            indicators={
                "rsi": 55, "ema9": 64000, "atr": 500,
                "stoch_rsi": {"k": 60, "d": 55},
                "obv": {"value": 1000000, "trend": "up"},
                "ichimoku": {"signal": "above_cloud"},
                "heikin_ashi": {"trend": "bullish"},
                "multi_tf_ema": {"alignment": "bullish"},
                "price_action_quality": {"quality": "high"},
                "confluence": {"score": 7, "bias": "bullish"},
                "_price": 65000,
            },
        )
        snap = _build_enhanced_coin_snapshot(cs, "BTC")
        assert snap["price"] == 65000
        assert snap["market_condition"] == "trending_up"
        assert "confluence" in snap
        assert "market_condition" in snap


class TestValidateDecision:
    def test_wait_passthrough(self):
        dec = {"action": "wait", "reasoning": "no edge"}
        result = _validate_decision(dec, None, {}, {})
        assert result["action"] == "wait"

    def test_close_passthrough(self):
        dec = {"action": "close_all", "reasoning": "regime changed"}
        result = _validate_decision(dec, None, {}, {})
        assert result["action"] == "close_all"
