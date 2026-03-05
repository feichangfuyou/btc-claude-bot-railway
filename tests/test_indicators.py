"""Unit tests for technical indicators."""

from strategy.indicators import calc_ema, calc_obv, calc_rsi, calc_stoch_rsi


def test_calc_ema_basic():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    ema = calc_ema(prices, 3)
    assert ema is not None
    assert 12 <= ema <= 14


def test_calc_ema_too_short():
    assert calc_ema([10.0], 3) is None


def test_calc_rsi_neutral():
    # Alternating up/down -> RSI near 50
    prices = [100.0 + (1 if i % 2 else -1) for i in range(20)]
    rsi = calc_rsi(prices)
    assert 45 <= rsi <= 55


def test_calc_rsi_oversold():
    # Declining prices
    prices = [100 - i for i in range(20)]
    rsi = calc_rsi(prices)
    assert rsi < 50


def test_calc_rsi_overbought():
    # Rising prices
    prices = [100 + i for i in range(20)]
    rsi = calc_rsi(prices)
    assert rsi > 50


def test_calc_rsi_too_short():
    assert calc_rsi([1.0, 2.0], 14) == 50.0


def test_calc_stoch_rsi_structure():
    prices = list(range(100, 130))
    result = calc_stoch_rsi(prices)
    assert "k" in result
    assert "d" in result
    assert "signal" in result
    assert result["signal"] in ("oversold", "overbought", "bullish_cross", "bearish_cross", "neutral")


def test_calc_obv_structure():
    prices = [100.0, 101.0, 99.0, 102.0]
    volumes = [1000.0, 1500.0, 800.0, 1200.0]
    result = calc_obv(prices, volumes)
    assert "obv" in result
    assert "obv_slope" in result
    assert "divergence" in result
