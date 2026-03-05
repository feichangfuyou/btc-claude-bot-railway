"""
Kraken Spot REST API — authenticated trading and market data.
Uses Kraken's REST API with HMAC-SHA512 signature auth.
Requires KRAKEN_API_KEY and KRAKEN_API_SECRET in .env.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx

from core.config import (
    KRAKEN_API_KEY,
    KRAKEN_API_SECRET,
    KRAKEN_PAIRS,
    KRAKEN_REST_URL,
    PRICE_FETCH_TIMEOUT,
)


def _kraken_sign(urlpath: str, data: dict, secret: str) -> str:
    """Generate Kraken API-Sign header per Kraken docs."""
    encoded = (str(data["nonce"]) + urllib.parse.urlencode(data)).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def _kraken_pair(symbol: str) -> str:
    """Map bot symbol (BTC, ETH, etc.) to Kraken pair name."""
    return KRAKEN_PAIRS.get(symbol.upper(), f"{symbol.upper()}USD")


def is_configured() -> bool:
    """Return True if Kraken API keys are set."""
    return bool(KRAKEN_API_KEY and KRAKEN_API_SECRET)


async def kraken_public_request(endpoint: str, params: dict = None) -> dict | None:
    """Public Kraken API request (no auth)."""
    url = f"{KRAKEN_REST_URL}/0/public/{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT) as client:
            r = await client.get(url, params=params or {})
            r.raise_for_status()
            data = r.json()
            if data.get("error"):
                return None
            return data.get("result")
    except Exception:
        return None


async def kraken_private_request(
    endpoint: str,
    data: dict = None,
    api_key: str = None,
    api_secret: str = None,
) -> dict | None:
    """Private Kraken API request (authenticated). Uses provided keys or config."""
    key = api_key or KRAKEN_API_KEY
    secret = api_secret or KRAKEN_API_SECRET
    if not key or not secret:
        return None
    urlpath = f"/0/private/{endpoint}"
    url = f"{KRAKEN_REST_URL}{urlpath}"
    data = dict(data or {})
    data["nonce"] = str(int(time.time() * 1000))

    sig = _kraken_sign(urlpath, data, secret)
    headers = {
        "API-Key": key,
        "API-Sign": sig,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = urllib.parse.urlencode(data)
    try:
        async with httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT) as client:
            r = await client.post(url, headers=headers, content=body)
            r.raise_for_status()
            resp = r.json()
            if resp.get("error"):
                return None
            return resp.get("result")
    except Exception:
        return None


async def get_ticker(symbol: str) -> tuple[float, float]:
    """Fetch Kraken ticker for symbol. Returns (price, volume_24h)."""
    pair = _kraken_pair(symbol)
    result = await kraken_public_request("Ticker", {"pair": pair})
    if not result:
        return (0.0, 0.0)
    # Result key may be pair, altname, or pair-specific; use first value
    ticker = result.get(pair) or (next(iter(result.values())) if result else None)
    if not ticker or not isinstance(ticker, dict):
        return (0.0, 0.0)
    # c = last trade close [price, lot_vol], v = volume [today, last_24h]
    try:
        c = ticker.get("c") or [0]
        last = float(c[0]) if c else 0.0
        v = ticker.get("v") or [0, 0]
        vol = float(v[1]) if len(v) > 1 else float(v[0]) if v else 0.0
        return (last, vol)
    except (TypeError, IndexError, ValueError):
        return (0.0, 0.0)


async def get_balance_usd() -> float:
    """Get Kraken account balance in USD (ZUSD)."""
    result = await kraken_private_request("Balance")
    if not result:
        return 0.0
    # ZUSD = USD on Kraken
    usd = result.get("ZUSD", "0")
    try:
        return float(usd)
    except (TypeError, ValueError):
        return 0.0


async def get_trade_balance() -> dict:
    """Get Kraken trade balance (equity, margin, etc)."""
    result = await kraken_private_request("TradeBalance", {"asset": "ZUSD"})
    if not result:
        return {}
    return result


async def add_market_order(
    symbol: str,
    side: str,
    volume: float,
    api_key: str = None,
    api_secret: str = None,
) -> str | None:
    """Place a market order on Kraken. Returns order txid on success."""
    pair = _kraken_pair(symbol)
    order_type = "buy" if side.lower() == "buy" else "sell"
    vol_str = f"{volume:.8f}".rstrip("0").rstrip(".")
    data = {
        "ordertype": "market",
        "pair": pair,
        "type": order_type,
        "volume": vol_str,
    }
    result = await kraken_private_request("AddOrder", data, api_key, api_secret)
    if not result:
        return None
    txids = result.get("txid", [])
    return txids[0] if txids else None


async def add_market_order_by_quote(
    symbol: str,
    side: str,
    volume_quote_usd: float,
    api_key: str = None,
    api_secret: str = None,
) -> str | None:
    """Place market order by quote (USD) amount. Kraken uses 'volume' in base.
    For buy: volume = volume_quote_usd / price. We need price first."""
    price, _ = await get_ticker(symbol)
    if not price or price <= 0:
        return None
    # Add 0.5% buffer for slippage
    volume_base = (volume_quote_usd / price) * 1.005
    return await add_market_order(symbol, side, volume_base, api_key, api_secret)
