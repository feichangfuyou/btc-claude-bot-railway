"""
Per-coin price/indicator state used by BotState.
v2 — computes enhanced indicator suite including Stochastic RSI, OBV,
Ichimoku Cloud, Heikin-Ashi, multi-TF EMA, and price action quality.
"""

import time
from datetime import datetime

from strategy.indicators import (
    calc_atr,
    calc_bb,
    calc_confluence_score,
    calc_ema,
    calc_ema_slope,
    calc_heikin_ashi_trend,
    calc_ichimoku,
    calc_macd,
    calc_momentum,
    calc_multi_timeframe_ema,
    calc_obv,
    calc_price_action_quality,
    calc_rsi,
    calc_rsi_divergence,
    calc_stoch_rsi,
    calc_volume_ratio,
    calc_vwap,
    detect_price_patterns,
    detect_regime,
    detect_volatility_regime,
    find_support_resistance,
)


class CoinState:
    """Tracks price, indicators, and candle data for a single coin."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.price = 0.0
        self.price_change24h = 0.0
        self.price_history: list[dict] = []
        self.raw_prices: list[float] = []
        self.volumes: list[float] = []
        self.indicators: dict = {}
        self.market_cond = "ranging"
        self.avg_atr_history: list[float] = []
        self.candles: list[dict] = []
        self.detected_patterns: list[str] = []
        self._candle_interval = 60
        self._current_candle: dict | None = None
        self._last_price_ts: float = 0.0

    def update_price(self, price: float, volume: float = 0.0, change24h: float = 0.0):
        self.price = price
        self.price_change24h = change24h
        self._last_price_ts = time.time()
        ts = datetime.now().strftime("%H:%M")
        self.price_history = (self.price_history + [{"t": ts, "price": price, "change24h": change24h}])[-100:]
        self.raw_prices = (self.raw_prices + [price])[-200:]
        self.volumes = (self.volumes + [volume])[-200:]
        self._update_candle(price, volume)
        self._recalc_indicators()

    def price_age(self) -> float:
        if self._last_price_ts == 0:
            return float("inf")
        return time.time() - self._last_price_ts

    def set_change24h(self, change24h: float):
        """Update 24h change without affecting price/history (used by stats refresh)."""
        self.price_change24h = change24h

    def touch_price_freshness(self):
        """Mark price as live without changing value (WS ticker heartbeat)."""
        if self.price > 0:
            self._last_price_ts = time.time()

    def backfill_prices(self, prices: list[float], volumes: list[float] | None = None):
        """Warm indicators with historical price series. Used on cold start."""
        if not prices:
            return
        vols = volumes if volumes is not None else [0.0] * len(prices)
        self.raw_prices = (self.raw_prices + prices)[-200:]
        self.volumes = (self.volumes + vols)[-200:]
        self._recalc_indicators()

    def _update_candle(self, price: float, volume: float):
        now = int(time.time())
        candle_time = now - (now % self._candle_interval)

        if self._current_candle and self._current_candle["time"] == candle_time:
            c = self._current_candle
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
            c["volume"] = c["volume"] + volume
            if self.candles and self.candles[-1]["time"] == candle_time:
                self.candles[-1] = c
        else:
            c = {
                "time": candle_time,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
            }
            self._current_candle = c
            self.candles = (self.candles + [c])[-300:]

    def _recalc_indicators(self):
        p = self.raw_prices
        b = calc_bb(p)
        atr = calc_atr(p)
        macd = calc_macd(p)
        self.avg_atr_history = (self.avg_atr_history + [atr])[-50:]
        avg_atr = sum(self.avg_atr_history) / len(self.avg_atr_history)
        sr = find_support_resistance(p)

        stoch = calc_stoch_rsi(p)
        obv = calc_obv(p, self.volumes)
        ichimoku = calc_ichimoku(p)
        ha = calc_heikin_ashi_trend(p)
        mtf = calc_multi_timeframe_ema(p)
        pa_quality = calc_price_action_quality(p)

        self.indicators = {
            "ema9": calc_ema(p, 9),
            "ema21": calc_ema(p, 21),
            "rsi": calc_rsi(p),
            "atr": atr,
            "avg_atr": round(avg_atr, 2),
            "bb_upper": b["upper"],
            "bb_middle": b["middle"],
            "bb_lower": b["lower"],
            "bb_width": b["width"],
            "vwap": calc_vwap(self.raw_prices[-100:], self.volumes[-100:]),
            "macd": macd["macd"],
            "macd_signal": macd["signal"],
            "macd_histogram": macd["histogram"],
            "momentum": calc_momentum(p),
            "ema9_slope": calc_ema_slope(p, 9, 5),
            "volume_ratio": calc_volume_ratio(self.volumes),
            "support_resistance": sr,
            "rsi_divergence": calc_rsi_divergence(p),
            "stoch_rsi": stoch,
            "obv": obv,
            "ichimoku": ichimoku,
            "heikin_ashi": ha,
            "multi_tf_ema": mtf,
            "price_action_quality": pa_quality,
            "_price": self.price,
        }
        self.market_cond = detect_regime(p, self.indicators, self.market_cond)
        self.detected_patterns = detect_price_patterns(p)
        self.indicators["volatility_regime"] = detect_volatility_regime(self.indicators, self.symbol)
        self.indicators["confluence"] = calc_confluence_score(self.indicators, self.market_cond)

    def snapshot(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "price_change24h": self.price_change24h,
            "price_age_sec": round(self.price_age()) if self._last_price_ts > 0 else None,
            "history": self.price_history,
            "candles": self.candles,
            "indicators": self.indicators,
            "market_condition": self.market_cond,
            "detected_patterns": self.detected_patterns,
        }
