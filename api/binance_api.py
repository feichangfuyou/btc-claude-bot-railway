"""
Binance Spot REST API — public market data only (no auth).
Used for instant bootstrap and fallback; Binance has highest liquidity and uptime.
No API keys required for price data.
"""

import json
from typing import Any

import httpx

from core.config import ACTIVE_COINS, PRICE_FETCH_TIMEOUT

BINANCE_REST_URL = "https://api.binance.com"
# Alternative: data-api.binance.vision (EU/US-friendly)


def _binance_symbol(s: str) -> str:
    """BTC -> BTCUSDT, ETH -> ETHUSDT."""
    return f"{s.upper()}USDT"


async def fetch_binance_prices(bot, only_fill_missing: bool = False) -> bool:
    """Fetch all active coin prices from Binance 24hr ticker. Returns True if any updated.
    No API keys needed. May return False in restricted regions (e.g. US 451).
    When only_fill_missing=True, only update symbols that have no price (preserves Coinbase data for chart match)."""
    symbols = [_binance_symbol(s) for s in ACTIVE_COINS]
    params = {"symbols": json.dumps(symbols)}
    try:
        async with httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT) as client:
            r = await client.get(f"{BINANCE_REST_URL}/api/v3/ticker/24hr", params=params)
            if r.status_code != 200:
                return False
            data = r.json()
            if not isinstance(data, list):
                return False
    except Exception:
        return False

    updated = False
    for item in data:
        sym_raw = item.get("symbol", "")
        if not sym_raw.endswith("USDT"):
            continue
        symbol = sym_raw.replace("USDT", "").upper()
        if symbol not in ACTIVE_COINS:
            continue
        if only_fill_missing:
            cs = bot.coins.get(symbol)
            if cs and cs.price > 0:
                continue  # Preserve Coinbase data — don't overwrite with Binance
        try:
            price = float(item.get("lastPrice", 0))
            if price <= 0:
                continue
            vol = float(item.get("volume", 0))
            chg = float(item.get("priceChangePercent", 0))
            bot.update_coin_price(symbol, price, vol, chg)
            updated = True
        except (ValueError, TypeError):
            continue
    return updated


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 168) -> list[dict]:
    """Fetch historical OHLCV candles from Binance. No auth. Returns [{timestamp, price, volume}, ...].
    interval: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d
    limit: max 1500. 168 = 7 days of 1h candles."""
    sym = _binance_symbol(symbol) if len(symbol) <= 5 else symbol
    try:
        r = httpx.get(
            f"{BINANCE_REST_URL}/api/v3/klines",
            params={"symbol": sym, "interval": interval, "limit": limit},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        candles = []
        for row in data:
            # [openTime, open, high, low, close, volume, ...]
            candles.append(
                {
                    "timestamp": int(row[0] / 1000),
                    "price": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        return candles
    except Exception:
        return []


def fetch_top_tickers(limit: int = 500) -> list[dict]:
    """Fetch top symbols by 24h volume for ticker tape. No auth. May return [] in restricted regions."""
    try:
        r = httpx.get(
            f"{BINANCE_REST_URL}/api/v3/ticker/24hr",
            timeout=PRICE_FETCH_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        # Sort by quote volume (USD), filter USDT pairs, take top N
        usdt = [x for x in data if isinstance(x, dict) and str(x.get("symbol", "")).endswith("USDT")]
        usdt.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        result = []
        for item in usdt[:limit]:
            sym = str(item.get("symbol", "")).replace("USDT", "")
            result.append(
                {
                    "sym": sym,
                    "symbol": sym,
                    "price": float(item.get("lastPrice", 0)),
                    "chg24h": float(item.get("priceChangePercent", 0)),
                    "image": None,
                }
            )
        return result
    except Exception:
        return []


def fetch_top_tickers_kraken(limit: int = 500) -> list[dict]:
    """Fallback: top symbols by 24h volume from Kraken (public, no auth). Works when Binance is blocked."""
    try:
        r = httpx.get(
            "https://api.kraken.com/0/public/AssetPairs",
            timeout=PRICE_FETCH_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        ap_data = r.json()
        pairs_info = ap_data.get("result") or {}
        if not isinstance(pairs_info, dict):
            return []
        pair_to_alt = {k: v.get("altname", k) for k, v in pairs_info.items() if isinstance(v, dict)}

        r2 = httpx.get("https://api.kraken.com/0/public/Ticker", timeout=PRICE_FETCH_TIMEOUT)
        if r2.status_code != 200:
            return []
        ticker_data = r2.json()
        tickers = ticker_data.get("result") or {}
        if not isinstance(tickers, dict):
            return []

        rows: list[dict[str, Any]] = []
        for pair, t in tickers.items():
            if not isinstance(t, dict):
                continue
            alt = str(pair_to_alt.get(pair, pair) or pair)
            if "USD" not in alt and "USDT" not in alt:
                continue
            v = t.get("v") or [0, 0]
            vol = float(v[1]) if len(v) > 1 else float(v[0]) if v else 0
            c = t.get("c") or [0]
            price = float(c[0]) if c else 0
            if price <= 0:
                continue
            o = t.get("o") or 0
            open_price = float(o) if o else 0
            chg_pct = ((price - open_price) / open_price * 100) if open_price > 0 else 0.0
            sym = alt.replace("ZUSD", "").replace("USD", "").replace("USDT", "").strip()
            if sym == "XBT":
                sym = "BTC"
            if not sym or len(sym) > 10:
                continue
            rows.append({"sym": sym, "vol": vol, "price": price, "chg": round(chg_pct, 2)})

        rows.sort(key=lambda x: x["vol"], reverse=True)
        seen = set()
        priority = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT"]
        result = []
        for s in priority:
            for row in rows:
                if row["sym"] == s and s not in seen:
                    seen.add(s)
                    result.append(
                        {
                            "sym": row["sym"],
                            "symbol": row["sym"],
                            "price": row["price"],
                            "chg24h": row["chg"],
                            "image": None,
                        }
                    )
                    break
        for row in rows:
            if row["sym"] not in seen and len(result) < limit:
                seen.add(row["sym"])
                result.append(
                    {
                        "sym": row["sym"],
                        "symbol": row["sym"],
                        "price": row["price"],
                        "chg24h": row["chg"],
                        "image": None,
                    }
                )
        return result[:limit]
    except Exception:
        return []
