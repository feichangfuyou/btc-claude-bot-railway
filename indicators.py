"""
Technical indicators used by CoinState and Claude analysis.
Includes confluence scoring for high-probability setups.

v2 — Enhanced with Stochastic RSI, OBV, Ichimoku Cloud,
multi-timeframe analysis, Heikin-Ashi, and regime-weighted confluence.
"""

from typing import Optional


def calc_ema(prices: list, period: int) -> Optional[float]:
    if len(prices) < 2:
        return None
    n = min(period, len(prices))
    k = 2 / (n + 1)
    ema = sum(prices[:n]) / n
    for p in prices[n:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 2)


def calc_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains = losses = 0.0
    for i in range(len(prices) - period, len(prices)):
        d = prices[i] - prices[i - 1]
        if d > 0:
            gains += d
        else:
            losses += abs(d)
    rs = (gains / period) / max(losses / period, 1e-9)
    return round(100 - 100 / (1 + rs), 2)


def calc_stoch_rsi(prices: list, rsi_period: int = 14, stoch_period: int = 14) -> dict:
    """Stochastic RSI — catches momentum shifts earlier than raw RSI."""
    if len(prices) < rsi_period + stoch_period + 1:
        return {"k": 50.0, "d": 50.0, "signal": "neutral"}

    rsi_values = []
    for i in range(stoch_period + 3, 0, -1):
        end_idx = len(prices) - i if i > 0 else len(prices)
        if end_idx < rsi_period + 1:
            continue
        rsi_values.append(calc_rsi(prices[:end_idx], rsi_period))
    rsi_values.append(calc_rsi(prices, rsi_period))

    if len(rsi_values) < stoch_period:
        return {"k": 50.0, "d": 50.0, "signal": "neutral"}

    recent_rsi = rsi_values[-stoch_period:]
    rsi_min = min(recent_rsi)
    rsi_max = max(recent_rsi)
    rsi_range = rsi_max - rsi_min

    if rsi_range < 0.01:
        k = 50.0
    else:
        k = ((recent_rsi[-1] - rsi_min) / rsi_range) * 100

    d_period = min(3, len(rsi_values))
    k_values = []
    for i in range(d_period):
        idx = len(rsi_values) - d_period + i
        window = rsi_values[max(0, idx - stoch_period + 1):idx + 1]
        w_min = min(window)
        w_max = max(window)
        w_range = w_max - w_min
        if w_range < 0.01:
            k_values.append(50.0)
        else:
            k_values.append(((window[-1] - w_min) / w_range) * 100)
    d = sum(k_values) / len(k_values) if k_values else k

    if k < 20 and d < 20:
        signal = "oversold"
    elif k > 80 and d > 80:
        signal = "overbought"
    elif k > d and k < 50:
        signal = "bullish_cross"
    elif k < d and k > 50:
        signal = "bearish_cross"
    else:
        signal = "neutral"

    return {"k": round(k, 2), "d": round(d, 2), "signal": signal}


def calc_obv(prices: list, volumes: list) -> dict:
    """On-Balance Volume — confirms price moves with volume pressure."""
    if len(prices) < 2 or len(volumes) < 2:
        return {"obv": 0, "obv_slope": 0, "divergence": "none"}

    n = min(len(prices), len(volumes))
    prices = prices[-n:]
    volumes = volumes[-n:]

    obv = 0.0
    obv_values = [0.0]
    for i in range(1, len(prices)):
        if prices[i] > prices[i - 1]:
            obv += volumes[i]
        elif prices[i] < prices[i - 1]:
            obv -= volumes[i]
        obv_values.append(obv)

    lookback = min(10, len(obv_values) - 1)
    if lookback < 2:
        return {"obv": round(obv, 2), "obv_slope": 0, "divergence": "none"}

    obv_recent = obv_values[-lookback:]
    obv_slope = (obv_recent[-1] - obv_recent[0]) / max(abs(obv_recent[0]), 1)

    price_recent = prices[-lookback:]
    price_slope = (price_recent[-1] - price_recent[0]) / max(price_recent[0], 1)

    divergence = "none"
    if price_slope > 0.001 and obv_slope < -0.1:
        divergence = "bearish"
    elif price_slope < -0.001 and obv_slope > 0.1:
        divergence = "bullish"

    return {
        "obv": round(obv, 2),
        "obv_slope": round(obv_slope, 4),
        "divergence": divergence,
    }


def calc_ichimoku(prices: list) -> dict:
    """Ichimoku Cloud — trend, momentum, and support/resistance in one."""
    if len(prices) < 52:
        return {
            "tenkan": None,
            "kijun": None,
            "senkou_a": None,
            "senkou_b": None,
            "signal": "neutral",
            "cloud_thickness": 0,
            "price_vs_cloud": "neutral",
        }

    def _mid(data):
        return (max(data) + min(data)) / 2

    tenkan = _mid(prices[-9:])
    kijun = _mid(prices[-26:])
    senkou_a = (tenkan + kijun) / 2
    senkou_b = _mid(prices[-52:])
    price = prices[-1]

    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)
    cloud_thickness = round((cloud_top - cloud_bottom) / price * 100, 4) if price else 0

    if price > cloud_top:
        price_vs_cloud = "above"
    elif price < cloud_bottom:
        price_vs_cloud = "below"
    else:
        price_vs_cloud = "inside"

    if price > cloud_top and tenkan > kijun:
        signal = "strong_bullish"
    elif price > cloud_top:
        signal = "bullish"
    elif price < cloud_bottom and tenkan < kijun:
        signal = "strong_bearish"
    elif price < cloud_bottom:
        signal = "bearish"
    elif tenkan > kijun:
        signal = "weak_bullish"
    elif tenkan < kijun:
        signal = "weak_bearish"
    else:
        signal = "neutral"

    return {
        "tenkan": round(tenkan, 2),
        "kijun": round(kijun, 2),
        "senkou_a": round(senkou_a, 2),
        "senkou_b": round(senkou_b, 2),
        "signal": signal,
        "cloud_thickness": cloud_thickness,
        "price_vs_cloud": price_vs_cloud,
    }


def calc_heikin_ashi_trend(prices: list) -> dict:
    """Heikin-Ashi candle trend — smoothed trend direction and strength."""
    if len(prices) < 10:
        return {"trend": "neutral", "strength": 0, "consecutive": 0}

    ha_close = []
    ha_open = [prices[0]]
    for i in range(len(prices)):
        if i == 0:
            hc = prices[i]
        else:
            o = prices[max(0, i - 1)]
            hc = (o + max(prices[max(0, i - 1):i + 1]) + min(prices[max(0, i - 1):i + 1]) + prices[i]) / 4
        ha_close.append(hc)
        if i > 0:
            ha_open.append((ha_open[-1] + ha_close[-2]) / 2)

    consecutive = 0
    direction = None
    for i in range(len(ha_close) - 1, max(0, len(ha_close) - 20), -1):
        is_bullish = ha_close[i] > ha_open[i]
        if direction is None:
            direction = is_bullish
            consecutive = 1
        elif is_bullish == direction:
            consecutive += 1
        else:
            break

    trend = "bullish" if direction else "bearish"
    if direction is None:
        trend = "neutral"

    strength = min(consecutive, 10) * 10

    return {
        "trend": trend,
        "strength": strength,
        "consecutive": consecutive,
    }


def calc_atr(prices: list, period: int = 14) -> float:
    if len(prices) < 2:
        return 0.0
    trs = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    recent = trs[-period:]
    return round(sum(recent) / len(recent), 2)


def calc_bb(prices: list, period: int = 20) -> dict:
    if len(prices) < 2:
        p = prices[-1] if prices else 0
        return {"upper": p, "middle": p, "lower": p, "width": 0}
    recent = prices[-min(period, len(prices)):]
    mid = sum(recent) / len(recent)
    std = (sum((p - mid) ** 2 for p in recent) / len(recent)) ** 0.5
    return {
        "upper": round(mid + 2 * std, 2),
        "middle": round(mid, 2),
        "lower": round(mid - 2 * std, 2),
        "width": round((4 * std / mid) * 100, 4) if mid else 0,
    }


def calc_vwap(prices: list, volumes: list) -> Optional[float]:
    if not volumes or not prices or len(prices) != len(volumes):
        return None
    total_vol = sum(volumes)
    if total_vol == 0:
        return None
    return round(sum(p * v for p, v in zip(prices, volumes)) / total_vol, 2)


def calc_macd(prices: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    if len(prices) < slow + signal:
        return {"macd": 0, "signal": 0, "histogram": 0}
    ema_fast = calc_ema(prices, fast) or 0
    ema_slow = calc_ema(prices, slow) or 0
    macd_val = round(ema_fast - ema_slow, 2)
    macd_series = []
    for i in range(slow, len(prices)):
        ef = calc_ema(prices[: i + 1], fast) or 0
        es = calc_ema(prices[: i + 1], slow) or 0
        macd_series.append(ef - es)
    sig_val = 0
    if len(macd_series) >= signal:
        k = 2 / (signal + 1)
        sig_val = sum(macd_series[:signal]) / signal
        for v in macd_series[signal:]:
            sig_val = v * k + sig_val * (1 - k)
    sig_val = round(sig_val, 2)
    return {"macd": macd_val, "signal": sig_val, "histogram": round(macd_val - sig_val, 2)}


def calc_momentum(prices: list, period: int = 10) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    return round(((prices[-1] - prices[-period - 1]) / prices[-period - 1]) * 100, 4)


def calc_ema_slope(prices: list, period: int = 9, lookback: int = 5) -> Optional[float]:
    """Rate of change of EMA over lookback periods, as % per period."""
    if len(prices) < period + lookback:
        return None
    ema_now = calc_ema(prices, period)
    ema_prev = calc_ema(prices[:-lookback], period)
    if ema_now is None or ema_prev is None or ema_prev == 0:
        return None
    return round((ema_now - ema_prev) / ema_prev * 100, 4)


def calc_volume_ratio(volumes: list, period: int = 20) -> float:
    """Current volume vs average volume. >1.5 = high volume confirmation."""
    if len(volumes) < period + 1:
        return 1.0
    avg = sum(volumes[-period - 1:-1]) / period
    if avg == 0:
        return 1.0
    return round(volumes[-1] / avg, 2)


def find_support_resistance(prices: list, window: int = 20) -> dict:
    """Simple pivot-based support/resistance from recent price action."""
    if len(prices) < window:
        return {"support": None, "resistance": None}
    recent = prices[-window:]
    lows = []
    highs = []
    for i in range(1, len(recent) - 1):
        if recent[i] <= recent[i - 1] and recent[i] <= recent[i + 1]:
            lows.append(recent[i])
        if recent[i] >= recent[i - 1] and recent[i] >= recent[i + 1]:
            highs.append(recent[i])
    support = round(max(lows), 2) if lows else round(min(recent), 2)
    resistance = round(min(highs), 2) if highs else round(max(recent), 2)
    return {"support": support, "resistance": resistance}


def calc_rsi_divergence(prices: list, period: int = 14, lookback: int = 20) -> Optional[str]:
    """Detect bullish/bearish RSI divergence over lookback window."""
    if len(prices) < period + lookback:
        return None
    mid = len(prices) - lookback // 2
    rsi_recent = calc_rsi(prices, period)
    rsi_earlier = calc_rsi(prices[:mid], period)
    price_recent = prices[-1]
    price_earlier = prices[mid - 1]
    if price_recent < price_earlier and rsi_recent > rsi_earlier:
        return "bullish"
    if price_recent > price_earlier and rsi_recent < rsi_earlier:
        return "bearish"
    return None


def calc_multi_timeframe_ema(prices: list) -> dict:
    """EMAs at multiple effective timeframes for trend alignment."""
    if len(prices) < 50:
        return {"alignment": "neutral", "trend_strength": 0}

    ema5 = calc_ema(prices, 5)
    ema9 = calc_ema(prices, 9)
    ema21 = calc_ema(prices, 21)
    ema50 = calc_ema(prices, 50)

    if not all([ema5, ema9, ema21, ema50]):
        return {"alignment": "neutral", "trend_strength": 0}

    if ema5 > ema9 > ema21 > ema50:
        return {"alignment": "strong_bullish", "trend_strength": 100}
    if ema5 > ema9 > ema21:
        return {"alignment": "bullish", "trend_strength": 75}
    if ema5 < ema9 < ema21 < ema50:
        return {"alignment": "strong_bearish", "trend_strength": 100}
    if ema5 < ema9 < ema21:
        return {"alignment": "bearish", "trend_strength": 75}
    if ema5 > ema9 and ema21 > ema50:
        return {"alignment": "mixed_bullish", "trend_strength": 40}
    if ema5 < ema9 and ema21 < ema50:
        return {"alignment": "mixed_bearish", "trend_strength": 40}
    return {"alignment": "neutral", "trend_strength": 20}


def calc_price_action_quality(prices: list) -> dict:
    """Measures how 'clean' the price action is — cleaner = more tradeable."""
    if len(prices) < 20:
        return {"quality": "low", "score": 0, "noise_ratio": 1.0}

    recent = prices[-20:]
    total_move = abs(recent[-1] - recent[0])
    path_length = sum(abs(recent[i] - recent[i - 1]) for i in range(1, len(recent)))

    if path_length == 0:
        return {"quality": "low", "score": 0, "noise_ratio": 1.0}

    efficiency = total_move / path_length
    noise_ratio = 1 - efficiency

    if efficiency > 0.45:
        quality = "high"
        score = 90
    elif efficiency > 0.20:
        quality = "medium"
        score = 60
    elif efficiency > 0.08:
        quality = "low"
        score = 30
    else:
        quality = "choppy"
        score = 10

    return {
        "quality": quality,
        "score": score,
        "noise_ratio": round(noise_ratio, 4),
        "efficiency": round(efficiency, 4),
    }


# ── Confluence Scoring (v2 — regime-weighted) ────────────────────────────────

_REGIME_WEIGHTS = {
    "trending_up": {
        "ema_bullish": 1.5,
        "ema_bearish": 0.5,
        "rsi_oversold": 1.3,
        "rsi_overbought": 0.7,
        "momentum_up": 1.4,
        "momentum_down": 0.6,
        "ichimoku_bullish": 1.5,
        "ichimoku_bearish": 0.5,
    },
    "trending_down": {
        "ema_bullish": 0.5,
        "ema_bearish": 1.5,
        "rsi_oversold": 0.7,
        "rsi_overbought": 1.3,
        "momentum_up": 0.6,
        "momentum_down": 1.4,
        "ichimoku_bullish": 0.5,
        "ichimoku_bearish": 1.5,
    },
    "ranging": {
        "bb_lower_touch": 1.5,
        "bb_upper_touch": 1.5,
        "rsi_oversold": 1.5,
        "rsi_overbought": 1.5,
        "near_support": 1.5,
        "near_resistance": 1.5,
        "stoch_rsi_oversold": 1.4,
        "stoch_rsi_overbought": 1.4,
    },
    "chaotic": {
        "ema_bullish": 0.5,
        "ema_bearish": 0.5,
        "momentum_up": 0.3,
        "momentum_down": 0.3,
        "high_volume": 1.5,
        "obv_confirms": 1.5,
    },
}


def _regime_weight(regime: str, signal_name: str) -> float:
    return _REGIME_WEIGHTS.get(regime, {}).get(signal_name, 1.0)


def calc_confluence_score(indicators: dict, regime: str) -> dict:
    """
    Multi-factor confluence score: -100 (strong sell) to +100 (strong buy).
    v2: regime-weighted signals, new indicators, quality filter.
    """
    score = 0.0
    signals = []

    rsi = indicators.get("rsi", 50)
    ema9 = indicators.get("ema9")
    ema21 = indicators.get("ema21")
    price = indicators.get("_price", 0)
    bb_lower = indicators.get("bb_lower", 0)
    bb_upper = indicators.get("bb_upper", 0)
    indicators.get("bb_middle", 0)
    macd_hist = indicators.get("macd_histogram", 0)
    momentum = indicators.get("momentum", 0)
    vwap = indicators.get("vwap")
    vol_ratio = indicators.get("volume_ratio", 1.0)
    ema_slope = indicators.get("ema9_slope")
    sr = indicators.get("support_resistance", {})
    divergence = indicators.get("rsi_divergence")
    stoch_rsi = indicators.get("stoch_rsi", {})
    obv_data = indicators.get("obv", {})
    ichimoku = indicators.get("ichimoku", {})
    ha_trend = indicators.get("heikin_ashi", {})
    mtf = indicators.get("multi_tf_ema", {})
    pa_quality = indicators.get("price_action_quality", {})

    # ── EMA crossover ──
    if ema9 and ema21:
        if ema9 > ema21:
            w = _regime_weight(regime, "ema_bullish")
            score += 15 * w
            signals.append("ema_bullish")
        else:
            w = _regime_weight(regime, "ema_bearish")
            score -= 15 * w
            signals.append("ema_bearish")

    # ── RSI ──
    if rsi < 30:
        w = _regime_weight(regime, "rsi_oversold")
        score += 20 * w
        signals.append("rsi_oversold")
    elif rsi < 40:
        score += 10
        signals.append("rsi_low")
    elif rsi > 70:
        w = _regime_weight(regime, "rsi_overbought")
        score -= 20 * w
        signals.append("rsi_overbought")
    elif rsi > 60:
        score -= 10
        signals.append("rsi_high")

    # ── Stochastic RSI ──
    stoch_signal = stoch_rsi.get("signal", "neutral")
    stoch_k = stoch_rsi.get("k", 50)
    if stoch_signal == "oversold" or stoch_k < 15:
        w = _regime_weight(regime, "stoch_rsi_oversold")
        score += 15 * w
        signals.append("stoch_rsi_oversold")
    elif stoch_signal == "overbought" or stoch_k > 85:
        w = _regime_weight(regime, "stoch_rsi_overbought")
        score -= 15 * w
        signals.append("stoch_rsi_overbought")
    elif stoch_signal == "bullish_cross":
        score += 8
        signals.append("stoch_bullish_cross")
    elif stoch_signal == "bearish_cross":
        score -= 8
        signals.append("stoch_bearish_cross")

    # ── Bollinger Bands ──
    if price and bb_lower and price <= bb_lower * 1.002:
        w = _regime_weight(regime, "bb_lower_touch")
        score += 15 * w
        signals.append("bb_lower_touch")
    elif price and bb_upper and price >= bb_upper * 0.998:
        w = _regime_weight(regime, "bb_upper_touch")
        score -= 15 * w
        signals.append("bb_upper_touch")

    # ── MACD ──
    if macd_hist > 0:
        score += 10
        signals.append("macd_bullish")
    elif macd_hist < 0:
        score -= 10
        signals.append("macd_bearish")

    # ── Momentum ──
    if momentum is not None:
        if momentum > 0.5:
            w = _regime_weight(regime, "momentum_up")
            score += 10 * w
            signals.append("momentum_up")
        elif momentum < -0.5:
            w = _regime_weight(regime, "momentum_down")
            score -= 10 * w
            signals.append("momentum_down")

    # ── VWAP ──
    if vwap and price:
        if price > vwap:
            score += 5
            signals.append("above_vwap")
        else:
            score -= 5
            signals.append("below_vwap")

    # ── EMA slope ──
    if ema_slope is not None:
        if ema_slope > 0.05:
            score += 10
            signals.append("ema_slope_up")
        elif ema_slope < -0.05:
            score -= 10
            signals.append("ema_slope_down")

    # ── RSI divergence ──
    if divergence == "bullish":
        score += 15
        signals.append("bullish_divergence")
    elif divergence == "bearish":
        score -= 15
        signals.append("bearish_divergence")

    # ── Support / Resistance ──
    support = sr.get("support")
    resistance = sr.get("resistance")
    if support and price and price <= support * 1.005:
        w = _regime_weight(regime, "near_support")
        score += 10 * w
        signals.append("near_support")
    if resistance and price and price >= resistance * 0.995:
        w = _regime_weight(regime, "near_resistance")
        score -= 10 * w
        signals.append("near_resistance")

    # ── OBV confirmation ──
    obv_div = obv_data.get("divergence", "none")
    obv_slope = obv_data.get("obv_slope", 0)
    if obv_div == "bullish":
        score += 12
        signals.append("obv_bullish_divergence")
    elif obv_div == "bearish":
        score -= 12
        signals.append("obv_bearish_divergence")
    if obv_slope > 0.3 and score > 0:
        w = _regime_weight(regime, "obv_confirms")
        score += 5 * w
        signals.append("obv_confirms")
    elif obv_slope < -0.3 and score < 0:
        w = _regime_weight(regime, "obv_confirms")
        score -= 5 * w
        signals.append("obv_confirms")

    # ── Ichimoku Cloud ──
    ichi_signal = ichimoku.get("signal", "neutral")
    if ichi_signal in ("strong_bullish", "bullish"):
        w = _regime_weight(regime, "ichimoku_bullish")
        bonus = 15 if "strong" in ichi_signal else 10
        score += bonus * w
        signals.append(f"ichimoku_{ichi_signal}")
    elif ichi_signal in ("strong_bearish", "bearish"):
        w = _regime_weight(regime, "ichimoku_bearish")
        bonus = 15 if "strong" in ichi_signal else 10
        score -= bonus * w
        signals.append(f"ichimoku_{ichi_signal}")

    # ── Heikin-Ashi trend ──
    ha_dir = ha_trend.get("trend", "neutral")
    ha_consec = ha_trend.get("consecutive", 0)
    if ha_dir == "bullish" and ha_consec >= 3:
        score += min(ha_consec, 6) * 2
        signals.append("ha_bullish_trend")
    elif ha_dir == "bearish" and ha_consec >= 3:
        score -= min(ha_consec, 6) * 2
        signals.append("ha_bearish_trend")

    # ── Multi-timeframe EMA alignment ──
    mtf_align = mtf.get("alignment", "neutral")
    if mtf_align == "strong_bullish":
        score += 12
        signals.append("mtf_strong_bullish")
    elif mtf_align == "bullish":
        score += 7
        signals.append("mtf_bullish")
    elif mtf_align == "strong_bearish":
        score -= 12
        signals.append("mtf_strong_bearish")
    elif mtf_align == "bearish":
        score -= 7
        signals.append("mtf_bearish")

    # ── Volume confirmation multiplier ──
    vol_bonus = min(vol_ratio - 1.0, 1.0) * 10 if vol_ratio > 1.2 else 0
    if score > 0:
        score += int(vol_bonus)
    elif score < 0:
        score -= int(vol_bonus)
    if vol_ratio > 1.5:
        signals.append("high_volume")

    # ── Price action quality filter ──
    pa_score = pa_quality.get("score", 50)
    if pa_score <= 20:
        score = int(score * 0.6)
        signals.append("choppy_price_action")
    elif pa_score >= 80:
        score = int(score * 1.15)
        signals.append("clean_price_action")

    score = max(-100, min(100, int(score)))

    return {
        "score": score,
        "direction": "buy" if score > 0 else ("sell" if score < 0 else "neutral"),
        "strength": abs(score),
        "signals": signals,
        "signal_count": len(signals),
    }


def detect_volatility_regime(indicators: dict, symbol: str = "BTC") -> str:
    """Classify current volatility: low_vol, normal_vol, high_vol.
    Uses ATR % of price; asset-specific thresholds (SOL runs hotter than BTC)."""
    atr = indicators.get("atr") or indicators.get("avg_atr") or 0
    price = indicators.get("_price") or 0
    bb_width = indicators.get("bb_width") or 0

    if not price or price <= 0:
        return "normal_vol"

    atr_pct = (atr / price * 100) if atr else 0
    vol_proxy = bb_width if bb_width > 0 else atr_pct

    # Asset-specific: alts (SOL, LINK) typically 1.5–2× BTC volatility
    high_mult = 3.5 if symbol in ("SOL", "LINK", "DOGE", "AVAX") else 3.0
    low_mult = 1.2 if symbol in ("SOL", "LINK", "DOGE", "AVAX") else 1.0

    if vol_proxy < low_mult:
        return "low_vol"
    if vol_proxy >= high_mult:
        return "high_vol"
    return "normal_vol"


# Hysteresis thresholds — prevent regime whipsaw (research: 10pp bands cut transitions ~70%)
CHAOTIC_ENTER_ATR_MULT = 2.5  # Enter chaotic when ATR > this × avg
CHAOTIC_EXIT_ATR_MULT = 2.0   # Exit chaotic only when ATR drops below this
TREND_ENTER_VOTES = 2         # Need this many votes to enter trending
TREND_EXIT_VOTES = 1          # Stay trending until votes fall to ±1 or less


def detect_regime(prices: list, indicators: dict, previous_regime: str = "ranging") -> str:
    """Regime detection with hysteresis — reduces whipsaw at boundaries."""
    if len(prices) < 5:
        return previous_regime or "ranging"

    atr = indicators.get("atr", 0)
    avg_atr = indicators.get("avg_atr", atr) or atr

    # Chaotic with hysteresis: harder to exit
    if avg_atr and atr > avg_atr * CHAOTIC_ENTER_ATR_MULT:
        return "chaotic"
    if previous_regime == "chaotic" and avg_atr and atr >= avg_atr * CHAOTIC_EXIT_ATR_MULT:
        return "chaotic"  # Stay chaotic until vol drops more

    ema9 = indicators.get("ema9")
    ema21 = indicators.get("ema21")

    ichi = indicators.get("ichimoku", {})
    ichi_signal = ichi.get("signal", "neutral")

    ha = indicators.get("heikin_ashi", {})
    ha_trend = ha.get("trend", "neutral")
    ha_consec = ha.get("consecutive", 0)

    trend_votes = 0
    if ema9 and ema21 and ema21 != 0:
        diff_pct = abs(ema9 - ema21) / ema21 * 100
        if diff_pct > 0.15:
            trend_votes += 1 if ema9 > ema21 else -1

    if ichi_signal in ("strong_bullish", "bullish"):
        trend_votes += 1
    elif ichi_signal in ("strong_bearish", "bearish"):
        trend_votes -= 1

    if ha_trend == "bullish" and ha_consec >= 3:
        trend_votes += 1
    elif ha_trend == "bearish" and ha_consec >= 3:
        trend_votes -= 1

    # Hysteresis: stay in trending until votes weaken
    if previous_regime == "trending_up" and trend_votes >= TREND_EXIT_VOTES:
        return "trending_up"
    if previous_regime == "trending_down" and trend_votes <= -TREND_EXIT_VOTES:
        return "trending_down"

    if trend_votes >= TREND_ENTER_VOTES:
        return "trending_up"
    if trend_votes <= -TREND_ENTER_VOTES:
        return "trending_down"
    if abs(trend_votes) >= 1 and ema9 and ema21 and ema21 != 0:
        diff_pct = abs(ema9 - ema21) / ema21 * 100
        if diff_pct > 0.15:
            return "trending_up" if trend_votes > 0 else "trending_down"
    return "ranging"


def detect_price_patterns(prices: list, tolerance: float = 0.003) -> list[str]:
    """Detect chart patterns from raw price history."""
    patterns = []
    if len(prices) < 20:
        return patterns

    recent = prices[-60:] if len(prices) >= 60 else prices

    pivots_high = []
    pivots_low = []
    for i in range(2, len(recent) - 2):
        if (
            recent[i] >= recent[i - 1]
            and recent[i] >= recent[i - 2]
            and recent[i] >= recent[i + 1]
            and recent[i] >= recent[i + 2]
        ):
            pivots_high.append((i, recent[i]))
        if (
            recent[i] <= recent[i - 1]
            and recent[i] <= recent[i - 2]
            and recent[i] <= recent[i + 1]
            and recent[i] <= recent[i + 2]
        ):
            pivots_low.append((i, recent[i]))

    if len(pivots_high) >= 2:
        h1, h2 = pivots_high[-2][1], pivots_high[-1][1]
        if abs(h1 - h2) / max(h1, h2) < tolerance:
            patterns.append("double_top")
        if h2 > h1:
            patterns.append("higher_high")
        elif h2 < h1 * (1 - tolerance):
            patterns.append("lower_high")

    if len(pivots_low) >= 2:
        l1, l2 = pivots_low[-2][1], pivots_low[-1][1]
        if abs(l1 - l2) / max(l1, l2) < tolerance:
            patterns.append("double_bottom")
        if l2 > l1:
            patterns.append("higher_low")
        elif l2 < l1 * (1 - tolerance):
            patterns.append("lower_low")

    if len(pivots_high) >= 2 and len(pivots_low) >= 2:
        if pivots_high[-1][1] > pivots_high[-2][1] and pivots_low[-1][1] > pivots_low[-2][1]:
            patterns.append("uptrend_structure")
        if pivots_high[-1][1] < pivots_high[-2][1] and pivots_low[-1][1] < pivots_low[-2][1]:
            patterns.append("downtrend_structure")

    if len(recent) >= 10:
        recent_max = max(recent[-10:])
        lookback_max = max(recent[:-10]) if len(recent) > 10 else recent_max
        if recent[-1] >= lookback_max * (1 - tolerance * 0.5):
            patterns.append("breakout_high")

        recent_min = min(recent[-10:])
        lookback_min = min(recent[:-10]) if len(recent) > 10 else recent_min
        if recent[-1] <= lookback_min * (1 + tolerance * 0.5):
            patterns.append("breakdown_low")

    if len(recent) >= 20:
        bb_width_pct = (max(recent[-20:]) - min(recent[-20:])) / ((max(recent[-20:]) + min(recent[-20:])) / 2) * 100
        if bb_width_pct < 1.5:
            patterns.append("squeeze")

    # ── New: mean reversion setup detection ──
    if len(recent) >= 20:
        rsi = calc_rsi(recent)
        bb = calc_bb(recent)
        if rsi < 35 and recent[-1] < bb["lower"] * 1.005:
            patterns.append("mean_reversion_long")
        if rsi > 65 and recent[-1] > bb["upper"] * 0.995:
            patterns.append("mean_reversion_short")

    # ── New: momentum exhaustion ──
    if len(recent) >= 15:
        last_5_range = max(recent[-5:]) - min(recent[-5:])
        prev_10_range = max(recent[-15:-5]) - min(recent[-15:-5])
        if prev_10_range > 0 and last_5_range / prev_10_range < 0.3:
            if recent[-1] > recent[-10]:
                patterns.append("bullish_exhaustion")
            else:
                patterns.append("bearish_exhaustion")

    return patterns
