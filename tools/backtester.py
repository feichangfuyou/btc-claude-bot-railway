"""
Historical backtesting engine for ClaudeBot.
Feeds historical candle data through the indicator pipeline to test
strategy performance without risking real money.
Uses exchange APIs (Binance, Coinbase) — same source as live trading.
"""

import httpx

from core.config import AI_COST_PER_TRADE, COINBASE_REST_TICKER, ROUND_TRIP_FEE, coinbase_product_id
from strategy.indicators import (
    calc_atr,
    calc_bb,
    calc_confluence_score,
    calc_ema,
    calc_heikin_ashi_trend,
    calc_ichimoku,
    calc_macd,
    calc_multi_timeframe_ema,
    calc_obv,
    calc_price_action_quality,
    calc_rsi,
    calc_rsi_divergence,
    calc_stoch_rsi,
    calc_vwap,
    detect_regime,
)


def _fetch_coinbase_candles(symbol: str, granularity: int, limit: int = 300) -> list[dict]:
    """Fetch candles from Coinbase. granularity: 3600=1h, 86400=1d. Max 300 per request."""
    try:
        pid = coinbase_product_id(symbol)
        r = httpx.get(
            f"{COINBASE_REST_TICKER}/{pid}/candles",
            params={"granularity": granularity},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        candles = []
        for row in data[:limit]:
            # [time, low, high, open, close] - no volume in Coinbase response
            candles.append(
                {
                    "timestamp": row[0],
                    "price": float(row[4]),
                    "volume": 0.0,
                }
            )
        return list(reversed(candles))
    except Exception:
        return []


def fetch_historical_candles(
    symbol: str = "BTC",
    days: int = 30,
    vs_currency: str = "usd",
    use_hourly: bool = False,
) -> list[dict]:
    """Fetch historical candles from exchange (Binance first, Coinbase fallback).
    - use_hourly=True: hourly granularity
    - use_hourly=False: daily granularity
    """
    sym = symbol.upper()
    limit = min(168 if use_hourly else days, 1500)
    interval = "1h" if use_hourly else "1d"
    granularity = 3600 if use_hourly else 86400

    try:
        from api.binance_api import fetch_klines

        candles = fetch_klines(sym, interval=interval, limit=limit)
    except Exception:
        candles = []

    if not candles:
        candles = _fetch_coinbase_candles(sym, granularity, limit=limit)

    return candles


def run_backtest(
    symbol: str = "BTC",
    days: int = 30,
    initial_balance: float = 250.0,
    position_size_pct: float = 0.20,
    tp_atr_mult: float = 2.5,
    sl_atr_mult: float = 1.0,
    min_confluence: int = 5,
    min_rr: float = 1.8,
    use_hourly: bool = True,
) -> dict:
    """Run a backtest using historical data and the indicator pipeline.
    use_hourly=True (default): fetches hourly candles for days 3-90, better TP/SL simulation.
    """
    candles = fetch_historical_candles(symbol, days, use_hourly=use_hourly)
    min_candles = 30 if not use_hourly else 26
    if len(candles) < min_candles:
        return {"error": "Not enough historical data", "candles": len(candles)}

    balance = initial_balance
    trades = []
    raw_prices = []
    raw_volumes = []
    position = None
    peak_balance = initial_balance
    max_drawdown = 0.0

    for i, candle in enumerate(candles):
        price = candle["price"]
        volume = candle["volume"]
        raw_prices.append(price)
        raw_volumes.append(volume)

        if len(raw_prices) < 26:
            continue

        indicators = _compute_indicators(raw_prices, raw_volumes, price)
        indicators.get("_regime", "ranging")
        confluence = indicators.get("confluence", {})
        conf_strength = confluence.get("strength", 0)
        conf_direction = confluence.get("direction", "neutral")
        atr = indicators.get("atr", 0)

        if position:
            if position["side"] == "buy":
                if price >= position["tp"]:
                    pnl = (position["tp"] - position["entry"]) * position["coin_size"]
                    _close_bt_position(position, trades, pnl, price, "TP HIT", balance)
                    balance += position["usd_size"] + pnl - position["usd_size"] * ROUND_TRIP_FEE - AI_COST_PER_TRADE
                    position = None
                elif price <= position["sl"]:
                    pnl = (position["sl"] - position["entry"]) * position["coin_size"]
                    _close_bt_position(position, trades, pnl, price, "SL HIT", balance)
                    balance += position["usd_size"] + pnl - position["usd_size"] * ROUND_TRIP_FEE - AI_COST_PER_TRADE
                    position = None
            else:
                if price <= position["tp"]:
                    pnl = (position["entry"] - position["tp"]) * position["coin_size"]
                    _close_bt_position(position, trades, pnl, price, "TP HIT", balance)
                    balance += position["usd_size"] + pnl - position["usd_size"] * ROUND_TRIP_FEE - AI_COST_PER_TRADE
                    position = None
                elif price >= position["sl"]:
                    pnl = (position["entry"] - position["sl"]) * position["coin_size"]
                    _close_bt_position(position, trades, pnl, price, "SL HIT", balance)
                    balance += position["usd_size"] + pnl - position["usd_size"] * ROUND_TRIP_FEE - AI_COST_PER_TRADE
                    position = None

            peak_balance = max(peak_balance, balance)
            if peak_balance > 0:
                dd = (peak_balance - balance) / peak_balance
                max_drawdown = max(max_drawdown, dd)
            continue

        if conf_strength < min_confluence:
            continue

        if atr <= 0:
            continue

        action = None
        if conf_direction == "buy" and conf_strength >= min_confluence:
            action = "buy"
        elif conf_direction == "sell" and conf_strength >= min_confluence:
            action = "sell"

        if not action:
            continue

        tp_dist = atr * tp_atr_mult
        sl_dist = atr * sl_atr_mult
        reward = tp_dist
        risk = sl_dist
        if risk <= 0 or reward / risk < min_rr:
            continue

        usd_size = balance * position_size_pct
        if usd_size < 10:
            continue

        coin_size = usd_size / price

        if action == "buy":
            tp = price + tp_dist
            sl = price - sl_dist
        else:
            tp = price - tp_dist
            sl = price + sl_dist

        balance -= usd_size
        position = {
            "side": action,
            "entry": price,
            "tp": tp,
            "sl": sl,
            "coin_size": coin_size,
            "usd_size": usd_size,
            "open_idx": i,
            "timestamp": candle["timestamp"],
        }

    if position:
        final_price = raw_prices[-1]
        if position["side"] == "buy":
            pnl = (final_price - position["entry"]) * position["coin_size"]
        else:
            pnl = (position["entry"] - final_price) * position["coin_size"]
        _close_bt_position(position, trades, pnl, final_price, "END OF DATA", balance)
        balance += position["usd_size"] + pnl - position["usd_size"] * ROUND_TRIP_FEE - AI_COST_PER_TRADE

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)

    return {
        "symbol": symbol,
        "days": days,
        "candles_processed": len(candles),
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "return_pct": round((balance / initial_balance - 1) * 100, 2),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "avg_win": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0,
        "best_trade": round(max((t["pnl"] for t in trades), default=0), 2),
        "worst_trade": round(min((t["pnl"] for t in trades), default=0), 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "profit_factor": round(
            abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses))
            if losses and sum(t["pnl"] for t in losses) != 0
            else 0,
            2,
        ),
        "trades": trades[-50:],
        "parameters": {
            "position_size_pct": position_size_pct,
            "tp_atr_mult": tp_atr_mult,
            "sl_atr_mult": sl_atr_mult,
            "min_confluence": min_confluence,
            "min_rr": min_rr,
        },
    }


def _close_bt_position(position, trades, pnl, exit_price, reason, balance):
    cost = position["usd_size"] * ROUND_TRIP_FEE + AI_COST_PER_TRADE
    net = round(pnl - cost, 2)
    trades.append(
        {
            "side": position["side"],
            "entry": round(position["entry"], 2),
            "exit": round(exit_price, 2),
            "pnl": net,
            "usd_size": round(position["usd_size"], 2),
            "reason": reason,
            "win": net > 0,
        }
    )


def _compute_indicators(raw_prices: list, raw_volumes: list, current_price: float) -> dict:
    """Compute all indicators from raw price history."""
    from strategy.indicators import find_support_resistance

    indicators = {}
    indicators["_price"] = current_price

    ema9 = calc_ema(raw_prices, 9)
    ema21 = calc_ema(raw_prices, 21)
    indicators["ema9"] = ema9
    indicators["ema21"] = ema21
    if ema9 and len(raw_prices) >= 10:
        prev_ema9 = calc_ema(raw_prices[:-1], 9)
        if prev_ema9:
            indicators["ema9_slope"] = round((ema9 - prev_ema9) / max(prev_ema9, 1) * 100, 4)

    indicators["rsi"] = calc_rsi(raw_prices)
    indicators["stoch_rsi"] = calc_stoch_rsi(raw_prices)

    macd_data = calc_macd(raw_prices)
    indicators.update(macd_data)

    indicators["atr"] = calc_atr(raw_prices)
    bb = calc_bb(raw_prices)
    indicators.update(bb)

    indicators["obv"] = calc_obv(raw_prices, raw_volumes)
    indicators["ichimoku"] = calc_ichimoku(raw_prices)
    indicators["heikin_ashi"] = calc_heikin_ashi_trend(raw_prices)
    indicators["volume_ratio"] = _calc_volume_ratio(raw_volumes)

    if len(raw_prices) >= 20:
        vols = raw_volumes[-20:] if len(raw_volumes) >= 20 else [1] * 20
        indicators["vwap"] = calc_vwap(raw_prices[-20:], vols)

    indicators["multi_tf_ema"] = calc_multi_timeframe_ema(raw_prices)
    indicators["price_action_quality"] = calc_price_action_quality(raw_prices)
    indicators["support_resistance"] = find_support_resistance(raw_prices)

    if len(raw_prices) >= 20:
        indicators["rsi_divergence"] = calc_rsi_divergence(raw_prices)

    regime = detect_regime(raw_prices, indicators)
    indicators["_regime"] = regime

    indicators["confluence"] = calc_confluence_score(indicators, regime)
    indicators["momentum"] = round((current_price / raw_prices[-20] - 1) * 100, 2) if len(raw_prices) >= 20 else 0

    return indicators


def _calc_volume_ratio(volumes: list) -> float:
    if len(volumes) < 2:
        return 1.0
    recent = volumes[-1] if volumes else 0
    avg = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else 1
    return round(recent / max(avg, 1), 2)
