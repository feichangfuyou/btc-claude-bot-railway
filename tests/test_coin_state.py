"""Tests for core/coin_state.py — CoinState price, indicators, snapshots."""

from core.coin_state import CoinState


class TestCoinStateBasic:
    def test_init_defaults(self):
        cs = CoinState("BTC")
        assert cs.symbol == "BTC"
        assert cs.price == 0.0
        assert cs.price_change24h == 0.0
        assert cs.raw_prices == []
        assert cs.indicators == {}
        assert cs.market_cond == "ranging"

    def test_update_price(self):
        cs = CoinState("ETH")
        cs.update_price(3500.0, volume=100.0, change24h=2.5)
        assert cs.price == 3500.0
        assert cs.price_change24h == 2.5
        assert len(cs.raw_prices) == 1
        assert len(cs.price_history) == 1
        assert cs.price_history[0]["price"] == 3500.0

    def test_price_history_capped_at_100(self):
        cs = CoinState("BTC")
        for i in range(120):
            cs.update_price(50000 + i, volume=10.0)
        assert len(cs.price_history) == 100
        assert len(cs.raw_prices) == 120  # capped at 200

    def test_raw_prices_capped_at_200(self):
        cs = CoinState("SOL")
        for i in range(250):
            cs.update_price(150 + i * 0.1, volume=5.0)
        assert len(cs.raw_prices) == 200

    def test_set_change24h(self):
        cs = CoinState("BTC")
        cs.update_price(50000.0)
        cs.set_change24h(3.14)
        assert cs.price_change24h == 3.14


class TestCoinStatePriceAge:
    def test_price_age_no_price(self):
        cs = CoinState("BTC")
        assert cs.price_age() == float("inf")

    def test_price_age_recent(self):
        cs = CoinState("BTC")
        cs.update_price(50000.0)
        age = cs.price_age()
        assert age < 2.0  # should be almost 0


class TestCoinStateBackfill:
    def test_backfill_prices(self):
        cs = CoinState("BTC")
        prices = [50000 + i for i in range(50)]
        cs.backfill_prices(prices)
        assert len(cs.raw_prices) == 50
        assert cs.indicators  # should have computed indicators

    def test_backfill_with_volumes(self):
        cs = CoinState("BTC")
        prices = [50000 + i for i in range(30)]
        vols = [100.0] * 30
        cs.backfill_prices(prices, vols)
        assert len(cs.volumes) == 30

    def test_backfill_empty(self):
        cs = CoinState("BTC")
        cs.backfill_prices([])
        assert cs.raw_prices == []
        assert cs.indicators == {}


class TestCoinStateIndicators:
    def test_indicators_populated_after_price_update(self):
        cs = CoinState("BTC")
        for i in range(30):
            cs.update_price(50000 + i * 10, volume=50.0)
        assert "ema9" in cs.indicators
        assert "rsi" in cs.indicators
        assert "atr" in cs.indicators
        assert "macd" in cs.indicators
        assert "stoch_rsi" in cs.indicators
        assert "obv" in cs.indicators
        assert "ichimoku" in cs.indicators

    def test_market_condition_set(self):
        cs = CoinState("BTC")
        for i in range(50):
            cs.update_price(50000 + i * 10, volume=50.0)
        assert cs.market_cond in ("ranging", "trending_up", "trending_down", "chaotic")


class TestCoinStateCandles:
    def test_candle_created_on_price_update(self):
        cs = CoinState("BTC")
        cs.update_price(50000.0, volume=10.0)
        assert len(cs.candles) >= 1
        candle = cs.candles[-1]
        assert candle["open"] == 50000.0
        assert candle["close"] == 50000.0

    def test_candle_updates_high_low(self):
        cs = CoinState("BTC")
        cs.update_price(50000.0, volume=10.0)
        cs.update_price(50100.0, volume=10.0)
        cs.update_price(49900.0, volume=10.0)
        candle = cs.candles[-1]
        assert candle["high"] >= 50100.0
        assert candle["low"] <= 49900.0

    def test_candles_capped_at_300(self):
        cs = CoinState("BTC")
        cs._candle_interval = 1
        for i in range(350):
            cs.update_price(50000 + i, volume=1.0)
            cs._current_candle = None  # force new candle each tick
        assert len(cs.candles) <= 300


class TestCoinStateSnapshot:
    def test_snapshot_structure(self):
        cs = CoinState("ETH")
        cs.update_price(3500.0, volume=100.0, change24h=1.5)
        snap = cs.snapshot()
        assert snap["symbol"] == "ETH"
        assert snap["price"] == 3500.0
        assert snap["price_change24h"] == 1.5
        assert "history" in snap
        assert "candles" in snap
        assert "indicators" in snap
        assert "market_condition" in snap
        assert "detected_patterns" in snap

    def test_snapshot_price_age_none_when_no_price(self):
        cs = CoinState("BTC")
        snap = cs.snapshot()
        assert snap["price_age_sec"] is None
