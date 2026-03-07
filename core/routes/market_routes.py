import asyncio
import ipaddress
import socket
import time

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from core.auth import AuthenticatedUser, get_active_user
from core.config import (
    API_PROXY_TIMEOUT,
    COINBASE_REST_TICKER,
    KRAKEN_PAIRS,
    PRICE_FETCH_TIMEOUT,
    PRICE_MAX_AGE_SEC,
)
from core.database import file_log
from core.redis_client import cache_get, cache_set
from core.shared import (
    _EXCHANGE_TICKERS_CACHE,
    _EXCHANGE_TICKERS_TTL,
    _io_executor,
    bot,
)
from strategy.symbol_registry import get_coingecko_id

router = APIRouter(tags=["market"])

_ALTERNATIVE_ALLOWED_PATHS: frozenset[str] = frozenset({"fng", "v2/ticker"})

_PROXY_TIMEOUT = min(API_PROXY_TIMEOUT, 5.0)
_PROXY_MAX_RESPONSE_BYTES = 512 * 1024  # 512 KB

_SENSITIVE_RESPONSE_HEADERS = frozenset(
    {
        "set-cookie",
        "x-request-id",
        "x-powered-by",
        "server",
        "x-runtime",
        "x-amzn-requestid",
        "x-amzn-trace-id",
    }
)


def _is_private_ip(hostname: str) -> bool:
    """Return True if hostname resolves to a private/loopback/reserved IP (SSRF guard)."""
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return True  # unresolvable → block
    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            return True
    return False


def _fetch_exchange_tickers_sync(limit: int):
    """Sync helper for run_in_executor — avoids blocking event loop."""
    from api.binance_api import fetch_top_tickers, fetch_top_tickers_kraken

    tickers = fetch_top_tickers(limit=limit)
    if tickers:
        return tickers
    return fetch_top_tickers_kraken(limit=limit)


@router.get("/api/coinbase/ticker")
async def proxy_coinbase_ticker(user: AuthenticatedUser = Depends(get_active_user)):
    """BTC ticker for demo. Serves from bot state when fresh; falls back to Coinbase REST."""
    btc = bot.coins.get("BTC")
    max_age = min(PRICE_MAX_AGE_SEC, 90)
    if btc and btc.price > 0 and btc.price_age() < max_age:
        return {"bitcoin": {"usd": btc.price, "usd_24h_change": btc.price_change24h}}
    url = f"{COINBASE_REST_TICKER}/BTC-USD/stats"
    async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as client:
        r = await client.get(url)
        d = r.json()
        last = float(d.get("last", 0))
        open_24h = float(d.get("open", last))
        change = round(((last - open_24h) / open_24h * 100), 2) if open_24h > 0 else 0
        return {"bitcoin": {"usd": last, "usd_24h_change": change}}


@router.get("/api/coinbase/tickers")
async def proxy_coinbase_tickers(symbols: str = "BTC,ETH,SOL,DOGE,LINK,AVAX,UNI,AAVE", user: AuthenticatedUser = Depends(get_active_user)):
    """Multi-coin ticker. Coinbase primary (matches TradingView chart). CoinGecko fallback for robustness.
    Serves from bot state when fresh; else Coinbase REST; missing symbols from CoinGecko."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return {"coins": {}}
    max_age = min(PRICE_MAX_AGE_SEC, 90)
    has_fresh = any((cs := bot.coins.get(s)) and cs.price > 0 and cs.price_age() < max_age for s in sym_list)
    if has_fresh:
        results = {}
        for sym in sym_list:
            cs = bot.coins.get(sym)
            if cs and cs.price > 0:
                results[sym] = {"price": cs.price, "price_change24h": cs.price_change24h}
        if results:
            return {"coins": results}

    results = {}

    async def fetch_coinbase_one(client: httpx.AsyncClient, sym: str):
        pid = f"{sym}-USD"
        try:
            r = await client.get(f"{COINBASE_REST_TICKER}/{pid}/stats")
            r.raise_for_status()
            d = r.json()
            last = float(d.get("last", 0))
            open_24h = float(d.get("open", last))
            change = round(((last - open_24h) / open_24h * 100), 2) if open_24h > 0 else 0
            return (sym, last, change)
        except Exception:
            return (sym, 0.0, 0.0)

    async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as client:
        tasks = [fetch_coinbase_one(client, s) for s in sym_list]
        for sym, price, change in await asyncio.gather(*tasks):
            if price > 0:
                results[sym] = {"price": price, "price_change24h": change}

    missing = [s for s in sym_list if s not in results]
    if missing:
        sym_to_cg: dict[str, str] = {s: cg for s in missing if (cg := get_coingecko_id(s))}
        if sym_to_cg:
            cg_ids: list[str] = list(dict.fromkeys(sym_to_cg.values()))
            try:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(cg_ids)}&vs_currencies=usd&include_24hr_change=true"
                r = await httpx.AsyncClient(timeout=API_PROXY_TIMEOUT).get(url)
                if r.status_code == 200:
                    data = r.json()
                    for sym, cg_id in sym_to_cg.items():
                        if cg_id in data and isinstance(data[cg_id], dict) and data[cg_id].get("usd"):
                            p = float(data[cg_id]["usd"])
                            ch = float(data[cg_id].get("usd_24h_change") or 0)
                            results[sym] = {"price": p, "price_change24h": ch}
            except Exception as e:
                file_log(f"CoinGecko fallback error: {e}", "warning")

    if not results and "BTC" in sym_list:
        try:
            async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as c:
                r = await c.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
                )
            if r.status_code == 200:
                d = r.json()
                if "bitcoin" in d and isinstance(d["bitcoin"], dict) and d["bitcoin"].get("usd"):
                    results["BTC"] = {
                        "price": float(d["bitcoin"]["usd"]),
                        "price_change24h": float(d["bitcoin"].get("usd_24h_change") or 0),
                    }
        except Exception as e:
            file_log(f"CoinGecko BTC fallback error: {e}", "warning")

    return {"coins": results}


@router.get("/api/exchange/tickers")
async def exchange_tickers(limit: int = 500, user: AuthenticatedUser = Depends(get_active_user)):
    """All exchange symbols by 24h volume (up to 500). Binance first, Kraken fallback when Binance blocked."""
    limit = min(max(limit, 1), 500)
    now = time.time()
    cached = cache_get(f"exchange_tickers:{limit}", ttl_sec=_EXCHANGE_TICKERS_TTL)
    if cached:
        return cached
    if limit in _EXCHANGE_TICKERS_CACHE:
        ts, data = _EXCHANGE_TICKERS_CACHE[limit]
        if now - ts < _EXCHANGE_TICKERS_TTL and data:
            return data
    try:
        loop = asyncio.get_event_loop()
        tickers = await loop.run_in_executor(_io_executor, lambda: _fetch_exchange_tickers_sync(limit))
        if tickers:
            cache_set(f"exchange_tickers:{limit}", tickers, ttl_sec=_EXCHANGE_TICKERS_TTL)
            _EXCHANGE_TICKERS_CACHE[limit] = (now, tickers)
            return tickers
    except Exception as e:
        file_log(f"Exchange tickers error: {e}", "warning")
    result = []
    for sym, cs in bot.coins.items():
        if cs.price > 0:
            result.append(
                {
                    "sym": sym,
                    "symbol": sym,
                    "price": cs.price,
                    "chg24h": cs.price_change24h,
                    "image": None,
                }
            )
    return result[:limit]


@router.get("/api/prices/multi")
async def multi_exchange_prices(symbols: str = "BTC,ETH,SOL,XRP,DOGE,ADA", user: AuthenticatedUser = Depends(get_active_user)):
    """Fetch prices from Binance, Coinbase, and Kraken for arbitrage view. Symbols comma-separated."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()][:20]
    if not sym_list:
        return {}

    result: dict[str, dict[str, float | None]] = {
        sym: {"binance": None, "coinbase": None, "kraken": None} for sym in sym_list
    }

    async def _binance_from_url(url: str) -> bool:
        """Fetch Binance prices from given base URL. Returns True if any filled."""
        filled = False
        try:
            r = await httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT).get(f"{url}/api/v3/ticker/price")
            if r.status_code != 200:
                return False
            data = r.json()
            if not isinstance(data, list):
                return False
            for item in data:
                if isinstance(item, dict) and str(item.get("symbol", "")).endswith("USDT"):
                    sym = str(item.get("symbol", "")).replace("USDT", "")
                    if sym in result:
                        p = float(item.get("price", 0)) or None
                        if p:
                            result[sym]["binance"] = p
                            filled = True
        except Exception as e:
            file_log(f"Binance price fetch error: {e}", "warning")
        return filled

    async def fetch_binance():
        if await _binance_from_url("https://api.binance.com"):
            return
        await _binance_from_url("https://data-api.binance.vision")

    async def fetch_coinbase():
        async def one(sym: str):
            try:
                async with httpx.AsyncClient(timeout=API_PROXY_TIMEOUT) as c:
                    r = await c.get(f"{COINBASE_REST_TICKER}/{sym}-USD/stats")
                    if r.status_code == 200:
                        d = r.json()
                        return (sym, float(d.get("last", 0)) or None)
            except Exception:
                pass
            return (sym, None)

        for sym, price in await asyncio.gather(*[one(s) for s in sym_list]):
            if price:
                result[sym]["coinbase"] = price
        for sym in sym_list:
            if result[sym]["coinbase"] is None:
                cs = bot.coins.get(sym)
                if cs and cs.price > 0:
                    result[sym]["coinbase"] = cs.price

    def _kraken_pair(sym: str) -> str:
        return KRAKEN_PAIRS.get(sym, f"{sym}USD")

    async def fetch_kraken():
        pair_to_sym = {_kraken_pair(s): s for s in sym_list}
        try:
            r = await httpx.AsyncClient(timeout=PRICE_FETCH_TIMEOUT).get(
                "https://api.kraken.com/0/public/Ticker",
                params={"pair": ",".join(pair_to_sym.keys())},
            )
            if r.status_code != 200:
                return
            d = r.json()
            if d.get("error"):
                return
            pairs_data = d.get("result") or {}
            for pair_id, v in pairs_data.items():
                if not isinstance(v, dict):
                    continue
                sym = pair_to_sym.get(pair_id)
                if sym:
                    c = v.get("c") or [0]
                    p = float(c[0]) if c else None
                    if p:
                        result[sym]["kraken"] = p
        except Exception as e:
            file_log(f"Kraken multi-price fetch error: {e}", "warning")

    await asyncio.gather(fetch_binance(), fetch_coinbase(), fetch_kraken())
    return result


@router.get("/api/alternative/{path:path}")
async def proxy_alternative(path: str, request: Request, user: AuthenticatedUser = Depends(get_active_user)):
    """Proxy Alternative.me API (Fear & Greed, CORS bypass). Hardened."""
    if request.method != "GET":
        return JSONResponse({"error": "method not allowed"}, status_code=405)

    if ".." in path or "//" in path or "\\" in path or "/./" in path:
        return JSONResponse({"error": "invalid path"}, status_code=400)

    normalized = path.split("?")[0].strip("/")
    if normalized not in _ALTERNATIVE_ALLOWED_PATHS:
        return JSONResponse({"error": "path not allowed"}, status_code=403)

    target_host = "api.alternative.me"
    if _is_private_ip(target_host):
        return JSONResponse({"error": "upstream blocked"}, status_code=403)

    qs = str(request.url.query)
    url = f"https://{target_host}/{normalized}" + (f"?{qs}" if qs else "")
    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            if len(r.content) > _PROXY_MAX_RESPONSE_BYTES:
                return JSONResponse({"error": "upstream response too large"}, status_code=502)
            data = r.json()
            resp = JSONResponse(data)
            for header in _SENSITIVE_RESPONSE_HEADERS:
                if header in resp.headers:
                    del resp.headers[header]
            return resp
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        return JSONResponse(
            {"error": "upstream unavailable", "detail": str(e)[:100]},
            status_code=502,
        )
    except ValueError:
        return JSONResponse(
            {"error": "upstream returned invalid JSON"},
            status_code=502,
        )
