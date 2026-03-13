"""Tests for ai/celery_ai_runner.py — MinimalBot and state reconstruction."""

from ai.celery_ai_runner import _MinimalBot


class TestMinimalBot:
    def test_creates_from_empty_state(self):
        bot = _MinimalBot({})
        assert bot.coins == {}
        assert bot.account == {}
        assert bot.open_positions == []
        assert bot.trades == []
        assert bot.fear_greed == {"value": 50}
        assert bot.trading_preset == "turtle"
        assert bot.last_ai_block_reason is None

    def test_creates_from_full_state(self):
        state = {
            "coins_snapshot": {
                "BTC": {
                    "price": 65000,
                    "confluence": {"ema9": 64000},
                    "market_condition": "trending_up",
                    "detected_patterns": ["bullish_engulfing"],
                },
            },
            "account": {"balance": 10000, "total_pnl": 500},
            "open_positions": [{"side": "buy", "symbol": "BTC"}],
            "trades": [{"pnl": 100}],
            "fear_greed": {"value": 72},
            "trading_preset": "soros",
            "claude_model": "claude-opus-4",
            "can_trade": True,
            "block_reason": "",
        }
        bot = _MinimalBot(state)
        assert "BTC" in bot.coins
        assert bot.coins["BTC"].price == 65000
        assert bot.coins["BTC"].market_cond == "trending_up"
        assert bot.account["balance"] == 10000
        assert len(bot.open_positions) == 1
        assert bot.fear_greed["value"] == 72
        assert bot.trading_preset == "soros"
        assert bot.claude_model == "claude-opus-4"

    def test_can_trade_true(self):
        bot = _MinimalBot({"can_trade": True, "block_reason": ""})
        ok, reason = bot.can_trade()
        assert ok is True
        assert reason == ""

    def test_cannot_trade(self):
        bot = _MinimalBot({"can_trade": False, "block_reason": "circuit breaker"})
        ok, reason = bot.can_trade()
        assert ok is False
        assert reason == "circuit breaker"

    def test_add_log_does_not_raise(self):
        bot = _MinimalBot({})
        bot.add_log("test message", "info")

    def test_coins_have_correct_attributes(self):
        state = {
            "coins_snapshot": {
                "ETH": {
                    "price": 3500,
                    "confluence": {"rsi": 60},
                    "market_condition": "ranging",
                    "detected_patterns": [],
                },
            }
        }
        bot = _MinimalBot(state)
        eth = bot.coins["ETH"]
        assert eth.price == 3500
        assert eth.indicators == {"rsi": 60}
        assert eth.market_cond == "ranging"
        assert eth.detected_patterns == []
        assert eth.raw_prices == [3500]

    def test_defaults_when_coin_data_sparse(self):
        state = {"coins_snapshot": {"SOL": {"price": 150}}}
        bot = _MinimalBot(state)
        sol = bot.coins["SOL"]
        assert sol.price == 150
        assert sol.market_cond == "ranging"
        assert sol.detected_patterns == []
