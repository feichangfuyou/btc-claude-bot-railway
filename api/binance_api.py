import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Any

import httpx

from core.config import ACTIVE_COINS, BINANCE_API_KEY, BINANCE_API_SECRET, PRICE_FETCH_TIMEOUT

BINANCE_REST_URL = "https://api.binance.com"
# Alternative: data-api.binance.vision (EU/US-friendly)


def _binance_symbol(s: str) -> str:
    """BTC -> BTCUSDT, ETH -> ETHUSDT."""
    return f"{s.upper()}USDT"


def _binance_sign(params: dict, secret: str) -> str:
    """Generate Binance HMAC SHA256 signature."""
    query = urllib.parse.urlencode(params)
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def is_configured() -> bool:
    """Return True if Binance API keys are set."""
    return bool(BINANCE_API_KEY and BINANCE_API_SECRET)


async def fetch_binance_prices(bot, only_fill_missing: bool = False) -> bool:
    """Fetch all active coin prices from Binance 24hr ticker. Returns True if any updated.
    No API keys needed. May return False in restricted regions (e.g. US 451).
    When only_fill_missing=True, only update symbols that have no price (preserves Coinbase data for chart match)."""
    active = list(bot.coins.keys()) if bot else ACTIVE_COINS
    symbols = [_binance_symbol(s) for s in active]
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
    active_set = set(active)
    for item in data:
        sym_raw = item.get("symbol", "")
        if not sym_raw.endswith("USDT"):
            continue
        symbol = sym_raw.replace("USDT", "").upper()
        if symbol not in active_set:
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


async def binance_private_request(
    endpoint: str,
    method: str = "GET",
    params: dict | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> Any:
    """Make an authenticated request to Binance."""
    key = api_key or BINANCE_API_KEY
    secret = api_secret or BINANCE_API_SECRET
    if not key or not secret:
        return None

    url = f"{BINANCE_REST_URL}{endpoint}"
    full_params = dict(params or {})
    full_params["timestamp"] = int(time.time() * 1000)
    full_params["recvWindow"] = 5000
    full_params["signature"] = _binance_sign(full_params, secret)

    headers = {"X-MBX-APIKEY": key}
    try:
        async with httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT) as client:
            if method.upper() == "GET":
                r = await client.get(url, headers=headers, params=full_params)
            else:
                # Binance requires params for auth in POST too if not in body
                r = await client.post(url, headers=headers, params=full_params)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def get_balance_usd() -> float:
    """Get Binance account total balance in USDT."""
    res = await binance_private_request("/api/v3/account")
    if not res or "balances" not in res:
        return 0.0
    # Simplification: return USDT balance
    for b in res["balances"]:
        if b["asset"] == "USDT":
            return float(b["free"]) + float(b["locked"])
    return 0.0


async def add_market_order(
    symbol: str,
    side: str,
    quantity: float,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict | None:
    """Place market order on Binance. quantity is in base asset."""
    params = {
        "symbol": _binance_symbol(symbol),
        "side": side.upper(),
        "type": "MARKET",
        "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
    }
    return await binance_private_request(
        "/api/v3/order", method="POST", params=params, api_key=api_key, api_secret=api_secret
    )


async def add_market_order_by_quote(
    symbol: str,
    side: str,
    quote_order_qty: float,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict | None:
    """Place market order by quote (USDT) amount."""
    params = {
        "symbol": _binance_symbol(symbol),
        "side": side.upper(),
        "type": "MARKET",
        "quoteOrderQty": f"{quote_order_qty:.2f}",
    }
    return await binance_private_request(
        "/api/v3/order", method="POST", params=params, api_key=api_key, api_secret=api_secret
    )
